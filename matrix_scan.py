import csv
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ----------------------------
# Config
# ----------------------------

@dataclass
class ScanConfig:
    env_path: Path
    state_path: Path
    out_dir: Path
    results_csv: Path
    matches_csv: Path

    browser_channel: str
    headless: bool

    home_url: str
    query: str

    # optional match filters
    match_max_price: Optional[int] = None
    match_min_sqft: Optional[int] = None
    match_min_lot_size: Optional[int] = None
    match_max_ppsf: Optional[float] = None

    # debug
    debug: bool = False


def _to_bool(s: str) -> bool:
    return str(s).strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_int(s: str) -> Optional[int]:
    s = (s or "").strip()
    if not s:
        return None
    m = re.search(r"([\d,]+)", s)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


def _parse_money(s: str) -> Optional[int]:
    # "$788,000" -> 788000
    return _parse_int(s)


def _parse_float(s: str) -> Optional[float]:
    s = (s or "").strip()
    if not s:
        return None
    m = re.search(r"([\d,.]+)", s)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _debug(cfg: ScanConfig, *args):
    if cfg.debug:
        print("[debug]", *args)


def load_config() -> ScanConfig:
    base_dir = Path(__file__).resolve().parent
    env_path = base_dir / ".env"
    load_dotenv(dotenv_path=env_path, override=True)

    # IMPORTANT: use paths relative to THIS FILE, not your PowerShell working directory
    state_path = base_dir / "state.json"

    out_dir_env = os.environ.get("OUT_DIR", "").strip()
    if out_dir_env:
        out_dir = Path(out_dir_env)
        if not out_dir.is_absolute():
            out_dir = base_dir / out_dir
    else:
        out_dir = base_dir / "out" / "data"
    results_csv = out_dir / "results.csv"
    matches_csv = out_dir / "matches.csv"

    browser_channel = os.environ.get("BROWSER_CHANNEL", "chrome").strip().lower()
    headless = _to_bool(os.environ.get("HEADLESS", "0"))

    # Prefer the Matrix results URL when HOME_URL is unset (connect.mlslistings.com is just a landing page).
    home_url = (
        os.environ.get("MATRIX_HOME_URL", "").strip()
        or os.environ.get("MATRIX_RESULTS_URL", "").strip()
        or "https://search.mlslistings.com/Matrix/Default.aspx?"
    )
    if not (home_url.startswith("http://") or home_url.startswith("https://")):
        home_url = "https://search.mlslistings.com/Matrix/Default.aspx?"

    query = os.environ.get("MATRIX_QUERY", "").strip()
    if not query:
        query = os.environ.get("MATRIX_SHORTHAND", "").strip()

    match_max_ppsf = _parse_float(os.environ.get("PPSF_THRESHOLD", "")) or _parse_float(
        os.environ.get("MATCH_MAX_PPSF", "")
    )
    match_min_lot_size = _parse_int(os.environ.get("MIN_LOT_SIZE", ""))

    cfg = ScanConfig(
        env_path=env_path,
        state_path=state_path,
        out_dir=out_dir,
        results_csv=results_csv,
        matches_csv=matches_csv,
        browser_channel=browser_channel,
        headless=headless,
        home_url=home_url,
        query=query,
        match_max_price=_parse_int(os.environ.get("MATCH_MAX_PRICE", "")),
        match_min_sqft=_parse_int(os.environ.get("MATCH_MIN_SQFT", "")),
        match_min_lot_size=match_min_lot_size,
        match_max_ppsf=match_max_ppsf,
        debug=_to_bool(os.environ.get("DEBUG", "0")),
    )
    if cfg.match_max_ppsf is not None and cfg.match_max_ppsf > 10_000:
        print(
            f"WARNING: PPSF_THRESHOLD={cfg.match_max_ppsf} is extremely high. PPSF is usually ~500-2000."
        )
    return cfg


# ----------------------------
# CSV helpers (exported)
# ----------------------------

def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    headers = ["MLS", "Street Address", "Price", "Sq Ft Total", "Lot Size", "PPSF"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow({h: r.get(h, "") for h in headers})


def filter_matches(cfg: ScanConfig, rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    # If no filters, matches = all listings
    if (
        cfg.match_max_price is None
        and cfg.match_min_sqft is None
        and cfg.match_min_lot_size is None
        and cfg.match_max_ppsf is None
    ):
        return rows

    out: List[Dict[str, str]] = []
    for r in rows:
        price = _parse_int(r.get("Price", ""))
        sqft = _parse_int(r.get("Sq Ft Total", ""))
        lot = _parse_int(r.get("Lot Size", ""))
        ppsf = _parse_float(r.get("PPSF", ""))

        if cfg.match_max_price is not None and price is not None and price > cfg.match_max_price:
            continue
        if cfg.match_min_sqft is not None and sqft is not None and sqft < cfg.match_min_sqft:
            continue
        if cfg.match_min_lot_size is not None:
            if lot is None or lot < cfg.match_min_lot_size:
                continue
        if cfg.match_max_ppsf is not None:
            if ppsf is None or ppsf > cfg.match_max_ppsf:
                continue

        out.append(r)
    return out


# ----------------------------
# Matrix scan logic (exported)
# ----------------------------

MENU_TEXT = "MY MATRIX"

# Your Matrix DOM IDs (from your HTML screenshot)
SPEEDBAR_INPUT = "#ctl01_m_ucSpeedBar_m_tbSpeedBar"
SPEEDBAR_GO = "#ctl01_m_ucSpeedBar_m_lnkGo"

PAGE_SIZE_SELECT = "#m_ucDisplayPicker_m_ddlPageSize"
RESULTS_TABLE = "table.displayGrid"  # slightly more tolerant than the full class chain


def _wait_logged_in(cfg: ScanConfig, page) -> None:
    # If state.json works, "MY MATRIX" should exist quickly
    page.wait_for_selector(f"text={MENU_TEXT}", timeout=60_000)


def _run_search(cfg: ScanConfig, page) -> None:
    if not cfg.query:
        raise RuntimeError(
            "MATRIX_QUERY is empty. Put something like 'RESI A 95008' in .env as MATRIX_QUERY "
            "(or set MATRIX_SHORTHAND)."
        )

    page.wait_for_selector(SPEEDBAR_INPUT, timeout=60_000)
    page.locator(SPEEDBAR_INPUT).fill(cfg.query)
    page.locator(SPEEDBAR_GO).click()

    page.wait_for_selector(RESULTS_TABLE, timeout=60_000)


def _set_page_size_250(cfg: ScanConfig, page) -> None:
    # Not all accounts show the dropdown; treat as best-effort
    try:
        page.wait_for_selector(PAGE_SIZE_SELECT, timeout=15_000)
        page.select_option(PAGE_SIZE_SELECT, "250")
        page.wait_for_timeout(1500)
        page.wait_for_selector(RESULTS_TABLE, timeout=60_000)
    except PlaywrightTimeoutError:
        _debug(cfg, "Page size selector not found; continuing.")


def _get_header_map(cfg: ScanConfig, page) -> Dict[str, int]:
    table = page.locator(RESULTS_TABLE).first
    headers = [h.strip() for h in table.locator("thead tr th").all_inner_texts()]
    idx = {_norm(h): i for i, h in enumerate(headers)}

    def pick(*names: str) -> int:
        for n in names:
            k = _norm(n)
            if k in idx:
                return idx[k]
        raise RuntimeError(f"Could not find column among {names}. Headers seen: {headers}")

    return {
        "mls": pick("MLS #", "MLS#", "MLS"),
        "addr": pick("Street Address", "Address"),
        "price": pick("Price"),
        "sqft": pick("SqFt", "Sq Ft", "Sq Ft Total"),
        "lot": pick("Lot Size", "Lot SqFt", "Lot"),
    }


def _extract_rows(cfg: ScanConfig, page) -> List[Dict[str, str]]:
    table = page.locator(RESULTS_TABLE).first
    col = _get_header_map(cfg, page)

    trs = table.locator("tbody tr")
    n = trs.count()

    rows: List[Dict[str, str]] = []
    for i in range(n):
        tr = trs.nth(i)
        tds = tr.locator("td")

        mls = tds.nth(col["mls"]).inner_text().strip()
        addr = tds.nth(col["addr"]).inner_text().strip()
        price_raw = tds.nth(col["price"]).inner_text().strip()
        sqft_raw = tds.nth(col["sqft"]).inner_text().strip()
        lot_raw = tds.nth(col["lot"]).inner_text().strip()

        price = _parse_money(price_raw)
        sqft = _parse_int(sqft_raw)
        lot = _parse_int(lot_raw)

        ppsf = ""
        if price is not None and sqft not in (None, 0):
            ppsf = f"{price / sqft:.2f}"

        rows.append(
            {
                "MLS": mls,
                "Street Address": addr,
                "Price": str(price) if price is not None else "",
                "Sq Ft Total": str(sqft) if sqft is not None else "",
                "Lot Size": str(lot) if lot is not None else "",
                "PPSF": ppsf,
            }
        )

    return rows


def run_matrix_scan(cfg: ScanConfig) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    if not cfg.state_path.exists():
        raise RuntimeError(f"Missing {cfg.state_path}. Run setup_auth.py first.")

    cfg.out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel=cfg.browser_channel, headless=cfg.headless)
        context = browser.new_context(storage_state=str(cfg.state_path))
        page = context.new_page()

        _debug(cfg, "Going to:", cfg.home_url)
        page.goto(cfg.home_url, wait_until="domcontentloaded")
        _debug(cfg, "Landed on:", page.url)

        _wait_logged_in(cfg, page)
        _run_search(cfg, page)
        _set_page_size_250(cfg, page)

        rows = _extract_rows(cfg, page)
        matches = filter_matches(cfg, rows)

        context.close()
        browser.close()

    return rows, matches
