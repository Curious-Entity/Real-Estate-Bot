import os
import re
import csv
import time
import math
import smtplib
import logging
from pathlib import Path
from dataclasses import dataclass
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List, Dict, Any, Tuple

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError


# ----------------------------
# Paths
# ----------------------------
ROOT = Path(__file__).resolve().parent
LOGS = ROOT / "logs"
OUT = ROOT / "out"
LOGS.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)


# ----------------------------
# Env helpers
# ----------------------------
def _env_bool(name: str, default: int = 0) -> bool:
    v = os.getenv(name, str(default)).strip()
    return v in ("1", "true", "True", "YES", "yes", "y")


def _env_float(name: str, default: float) -> float:
    v = os.getenv(name, "").strip()
    if not v:
        return float(default)
    return float(v)


def _env_str(name: str, default: str = "") -> str:
    v = os.getenv(name, "").strip()
    return v if v else default


# ----------------------------
# Logging
# ----------------------------
def setup_logger(level: str) -> logging.Logger:
    logger = logging.getLogger("matrix_scan")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    fmt = logging.Formatter("[%(levelname)s] %(message)s")

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(LOGS / "scan.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(fh)

    return logger


def step(msg: str, logger: logging.Logger) -> None:
    print(f"[scan] {msg}")
    logger.info(f"[scan] {msg}")


@dataclass
class Cfg:
    login_url: str
    results_url: str
    shorthand: str
    ppsf_threshold: float
    min_lot_size: float
    bootstrap_only: bool
    headless: bool
    browser_channel: str
    log_level: str
    debug_pause_on_error: bool

    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str
    alert_to: str
    alert_from: str


# ----------------------------
# Parsing helpers
# ----------------------------
def norm_txt(s: str) -> str:
    if s is None:
        return ""
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_int(s: str) -> Optional[int]:
    s = norm_txt(s)
    m = re.search(r"[\d,]+", s)
    if not m:
        return None
    return int(m.group(0).replace(",", ""))


def parse_price(s: str) -> Optional[int]:
    return parse_int(s)


def safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


MLS_RE = re.compile(r"\bML\d{7,}\b", re.I)


# ----------------------------
# Matrix UI selectors
# ----------------------------
SELECT_ALL_LINK = "#m_lnkCheckAllLink"
ACTIONS_TAB = "#m_ltbActionMenu"
EXPORT_BUTTON = "#m_lbExport"
EXPORT_CONFIRM = "#m_btnExport"
RESULTS_TABLE = "table.displayGrid"


# ----------------------------
# Diagnostics
# ----------------------------
def dump_diag(page, slug: str, logger: logging.Logger) -> None:
    try:
        page.screenshot(path=str(LOGS / f"{slug}.png"), full_page=True)
        logger.info(f"[diag] screenshot: logs/{slug}.png")
    except Exception as e:
        logger.warning(f"[diag] screenshot failed: {e}")

    try:
        html = page.content()
        (LOGS / f"{slug}.html").write_text(html, encoding="utf-8")
        logger.info(f"[diag] html: logs/{slug}.html")
    except Exception as e:
        logger.warning(f"[diag] html dump failed: {e}")

    try:
        lines = []
        for i, fr in enumerate(page.frames):
            lines.append(f"[{i}] name={fr.name!r} url={fr.url}")
        (LOGS / f"{slug}_frames.txt").write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"[diag] frames: logs/{slug}_frames.txt")
    except Exception as e:
        logger.warning(f"[diag] frames dump failed: {e}")


# ----------------------------
# Navigation helpers
# ----------------------------
def goto_matrix_home(page, cfg: Cfg, logger: logging.Logger):
    logger.info("[nav] goto Matrix home")
    page.goto(cfg.login_url, wait_until="domcontentloaded")

    # Sometimes you land on SAML responder via GET (XML error). Kick back.
    if "AuthnRequestResponder.ashx" in page.url:
        logger.warning("[warn] AuthnRequestResponder detected; redirecting to connect root then Matrix.")
        page.goto("https://connect.mlslistings.com/", wait_until="domcontentloaded")
        page.goto(cfg.login_url, wait_until="domcontentloaded")


def ensure_matrix_ui(page, timeout_ms: int = 60000):
    deadline = time.time() + timeout_ms / 1000.0
    sels = [r"text=/MY\s+MATRIX/i", r"text=/SEARCH/i", r"text=/DIRECTORY/i"]
    while time.time() < deadline:
        for s in sels:
            if page.locator(s).count() > 0:
                return
        time.sleep(0.2)
    raise PWTimeoutError("Matrix UI not detected. Session may be expired.")


def run_shorthand_search(page, shorthand: str, logger: logging.Logger):
    logger.info(f"[nav] running shorthand search: {shorthand!r}")

    candidates = [
        "input[placeholder*='Shorthand']",
        "input[aria-label*='Shorthand']",
        "input[placeholder*='Enter Shorthand']",
        "input[placeholder*='Enter Shorthand or MLS']",
        "input[placeholder*='Enter Shorthand or MLS#']",
        "input[placeholder*='Enter Shorthand or MLS#']",
        "input[placeholder*='Enter Shorthand or MLS#']",
        "input[placeholder*='Enter Shorthand or MLS#']",
        "input[placeholder*='Enter Shorthand or MLS#']",
        "input[placeholder*='Enter Shorthand or MLS#']",
        "input[placeholder*='Enter Shorthand or MLS#']",
        "input[placeholder*='Enter Shorthand or MLS#']",
        "input[placeholder*='Enter Shorthand or MLS#']",
        "input[placeholder*='Enter Shorthand or MLS#']",
        "input[placeholder*='Enter Shorthand or MLS#']",
        "input[placeholder*='Enter Shorthand or MLS#']",
        "input[placeholder*='Enter Shorthand or MLS#']",
        "input[placeholder*='Enter Shorthand or MLS#']",
        "input[placeholder*='Shorthand or MLS']",
        "input[placeholder*='Shorthand']",
        "input[placeholder*='MLS#']",
        "input[placeholder*='MLS #']",
        "input[type='text']",
    ]

    box = None
    for sel in candidates:
        loc = page.locator(sel).first
        if loc.count() > 0:
            box = loc
            break
    if box is None:
        raise RuntimeError("Could not find shorthand/speedbar input.")

    box.click()
    box.fill(shorthand)
    try:
        box.press("Enter")
    except Exception:
        pass


def get_results_page(page, logger: logging.Logger):
    if page is None:
        raise RuntimeError("No page available")
    if not page.is_closed() and "Results.aspx" in page.url:
        return page

    ctx = page.context
    open_pages = [p for p in ctx.pages if not p.is_closed()]
    for p in reversed(open_pages):
        if "Results.aspx" in p.url:
            if p != page:
                logger.info(f"[nav] switching to results page: {p.url}")
            return p
    if not page.is_closed():
        return page
    if open_pages:
        logger.info(f"[nav] switching to last open page: {open_pages[-1].url}")
        return open_pages[-1]
    raise RuntimeError("No active page available")


def find_locator_any_frame(page, selector: str, logger: logging.Logger, timeout_ms: int = 60000):
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        try:
            page = get_results_page(page, logger)
            if page.locator(selector).count() > 0:
                return page.locator(selector)
            for fr in page.frames:
                try:
                    if fr.locator(selector).count() > 0:
                        return fr.locator(selector)
                except Exception:
                    continue
        except Exception:
            pass
        time.sleep(0.2)
    raise PWTimeoutError(f"Timed out waiting for selector: {selector}")


def wait_for_results_ready(page, logger: logging.Logger):
    step("waiting for results grid", logger)
    try:
        find_locator_any_frame(page, RESULTS_TABLE, logger, timeout_ms=60000)
    except PWTimeoutError:
        # Some accounts render without displayGrid class; fallback to the "All" link.
        find_locator_any_frame(page, SELECT_ALL_LINK, logger, timeout_ms=60000)


def export_results_csv(page, cfg: Cfg, logger: logging.Logger) -> Path:
    def click_loc(loc):
        try:
            loc.scroll_into_view_if_needed()
        except Exception:
            pass
        loc.click()

    def ensure_actions_open(page):
        # If Export is already visible, skip clicking Actions to save time.
        try:
            page = get_results_page(page, logger)
            find_locator_any_frame(page, EXPORT_BUTTON, logger, timeout_ms=1500)
            return
        except Exception:
            pass

        step("opening Actions tab", logger)
        try:
            page = get_results_page(page, logger)
            click_loc(find_locator_any_frame(page, ACTIONS_TAB, logger, timeout_ms=30000))
        except PWTimeoutError:
            # Fallback by visible text if ID changes.
            page = get_results_page(page, logger)
            click_loc(page.locator("text=Actions").first)

    step("clicking All", logger)
    page = get_results_page(page, logger)
    click_loc(find_locator_any_frame(page, SELECT_ALL_LINK, logger, timeout_ms=60000))

    ensure_actions_open(page)

    step("clicking Export", logger)
    page = get_results_page(page, logger)
    click_loc(find_locator_any_frame(page, EXPORT_BUTTON, logger, timeout_ms=30000))

    step("confirming Export", logger)
    page = get_results_page(page, logger)
    find_locator_any_frame(page, EXPORT_CONFIRM, logger, timeout_ms=30000)
    with page.expect_download(timeout=60000) as dl_info:
        click_loc(find_locator_any_frame(page, EXPORT_CONFIRM, logger, timeout_ms=30000))
    download = dl_info.value

    export_path = OUT / "results_export.csv"
    download.save_as(export_path)
    return export_path


def _norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _pick_header(headers: List[str], *names: str) -> Optional[str]:
    lookup = {_norm_key(h): h for h in headers}
    for n in names:
        k = _norm_key(n)
        if k in lookup:
            return lookup[k]
    return None


def load_export_csv(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        col_mls = _pick_header(headers, "MLS #", "MLS#", "MLS", "MLS Number")
        col_addr = _pick_header(headers, "Street Address", "Address", "Street Addr", "Street")
        col_price = _pick_header(headers, "Price", "List Price", "Current Price")
        col_sqft = _pick_header(headers, "Sq Ft", "SqFt", "Sq Ft Total", "Total Sq Ft", "Square Feet")
        col_lot = _pick_header(headers, "Lot Size", "Lot SqFt", "Lot Sq Ft", "Lot", "Lot Size (Sq Ft)")

        missing = [k for k, v in {
            "MLS": col_mls,
            "Address": col_addr,
            "Price": col_price,
            "SqFt": col_sqft,
            "Lot": col_lot,
        }.items() if v is None]
        if missing:
            raise RuntimeError(f"Export CSV missing columns: {missing}. Headers: {headers}")

        rows: List[Dict[str, Any]] = []
        for r in reader:
            mls = norm_txt(r.get(col_mls, ""))
            addr = norm_txt(r.get(col_addr, ""))
            price = parse_price(r.get(col_price, ""))
            sqft = parse_int(r.get(col_sqft, ""))
            lot = parse_int(r.get(col_lot, ""))

            ppsf = safe_div(price, sqft)
            rows.append({
                "MLS": mls,
                "Street Address": addr,
                "Price": price,
                "Sq Ft Total": sqft,
                "Lot Size": lot,
                "PPSF": ppsf,
            })

    return rows


# ----------------------------
# Grid detection + extraction
# ----------------------------
def find_results_table_any_frame(page, logger: logging.Logger, timeout_ms: int = 60000):
    """
    Find the real Results grid table. We require multiple column labels to avoid false positives.
    """
    deadline = time.time() + timeout_ms / 1000.0

    while time.time() < deadline:
        for fr in page.frames:
            try:
                # Must include these texts somewhere in the table
                tables = fr.locator("table") \
                    .filter(has_text=re.compile(r"\bMLS\s*#\b", re.I)) \
                    .filter(has_text=re.compile(r"Street\s+Address", re.I)) \
                    .filter(has_text=re.compile(r"\bPrice\b", re.I)) \
                    .filter(has_text=re.compile(r"\bSqFt\b|\bSq\s*Ft\b", re.I)) \
                    .filter(has_text=re.compile(r"Lot\s+Size|Lot\s+SqFt|Lot\s+Sq\s*Ft", re.I))

                if tables.count() == 0:
                    continue

                # pick the table with most rows
                best = None
                best_rows = -1
                for i in range(min(tables.count(), 20)):
                    t = tables.nth(i)
                    rows = t.locator("tr").count()
                    if rows > best_rows:
                        best_rows = rows
                        best = t

                if best is not None and best_rows >= 2:
                    logger.info(f"[run] results grid detected (rows_in_table={best_rows})")
                    return fr, best

            except Exception:
                continue

        time.sleep(0.2)

    raise PWTimeoutError("Timed out finding results grid table (across frames).")


def extract_table_rows(table) -> Tuple[List[str], List[List[str]]]:
    """
    Matrix sometimes uses TH, sometimes TD for headers.
    We find a header row by looking for a row containing both 'MLS #' and 'Street Address'.
    """
    header_row = table.locator("tr") \
        .filter(has_text=re.compile(r"\bMLS\s*#\b", re.I)) \
        .filter(has_text=re.compile(r"Street\s+Address", re.I)) \
        .first

    if header_row.count() == 0:
        header_row = table.locator("tr").first

    header_cells = header_row.locator("th, td")
    headers = [norm_txt(x) for x in header_cells.all_inner_texts()]

    # Data rows: any row with tds
    data_rows = []
    trs = table.locator("tr").filter(has=table.locator("td"))
    for i in range(trs.count()):
        row_txt = norm_txt(trs.nth(i).inner_text())
        # skip header-like rows
        if re.search(r"\bMLS\s*#\b", row_txt, re.I) and re.search(r"Street\s+Address", row_txt, re.I):
            continue

        tds = [norm_txt(x) for x in trs.nth(i).locator("td").all_inner_texts()]
        if any(tds):
            data_rows.append(tds)

    return headers, data_rows


def header_index(headers: List[str], variants: List[str]) -> Optional[int]:
    hlow = [h.lower() for h in headers]
    for v in variants:
        vlow = v.lower()
        for i, h in enumerate(hlow):
            if h == vlow or vlow in h:
                return i
    return None


def parse_listings_from_table(table, logger: logging.Logger, page_no: int) -> List[Dict[str, Any]]:
    headers, rows = extract_table_rows(table)

    # Try to map columns (best case)
    mls_i  = header_index(headers, ["MLS #", "MLS"])
    addr_i = header_index(headers, ["Street Address", "Address"])
    price_i= header_index(headers, ["Price", "Current Price", "List Price"])
    sqft_i = header_index(headers, ["SqFt", "Sq Ft"])
    lot_i  = header_index(headers, ["Lot Size", "Lot SqFt", "Lot Sq Ft", "Lot"])

    listings: List[Dict[str, Any]] = []

    for tds in rows:
        row_join = " | ".join(tds)

        # MLS: robust fallback (don’t depend on headers)
        mls = ""
        if mls_i is not None and mls_i < len(tds):
            mls = norm_txt(tds[mls_i])
        m = MLS_RE.search(row_join)
        if m:
            mls = m.group(0).upper()

        if not mls.startswith("ML"):
            continue

        # Address
        addr = ""
        if addr_i is not None and addr_i < len(tds):
            addr = norm_txt(tds[addr_i])
        else:
            # common layout: MLS column then address column
            if mls_i is not None and (mls_i + 1) < len(tds):
                addr = norm_txt(tds[mls_i + 1])

        # Price
        price = None
        if price_i is not None and price_i < len(tds):
            price = parse_price(tds[price_i])
        else:
            mprice = re.search(r"\$\s*[\d,]+", row_join)
            if mprice:
                price = parse_price(mprice.group(0))

        # SqFt
        sqft = None
        if sqft_i is not None and sqft_i < len(tds):
            sqft = parse_int(tds[sqft_i])

        # Lot
        lot = None
        if lot_i is not None and lot_i < len(tds):
            lot = parse_int(tds[lot_i])

        ppsf = safe_div(price, sqft)

        listings.append({
            "MLS": mls,
            "Street Address": addr,
            "Price": price,
            "Sq Ft Total": sqft,
            "Lot Size": lot,
            "PPSF": ppsf,
        })

    if page_no == 1 and len(listings) == 0:
        # If we found the grid but got zero listings, we need a snapshot for diagnosis.
        (LOGS / "page1_headers.txt").write_text("\n".join(headers), encoding="utf-8")

    return listings


def click_next_page_near_table(frame, table, logger: logging.Logger) -> bool:
    """
    Avoid clicking random 'Next'. Try to click the 'Next' that is in the same general area as the table:
    - Matrix has "Previous Next · 1-25 of 28" above/below the grid.
    Strategy:
      - look for a 'Next' link that is close to the table in DOM by checking within a common ancestor container.
    Fallback:
      - click the first visible 'Next' link inside the frame, but stop if it doesn’t change the MLS set.
    """
    # Try: within the table's parent container, find Next
    try:
        container = table.locator("xpath=ancestor::*[self::div or self::td or self::section][1]")
        nxt = container.locator("a:has-text('Next')").first
        if nxt.count() > 0:
            try:
                nxt.click(timeout=2000)
                logger.info("[nav] next page")
                return True
            except Exception:
                pass
    except Exception:
        pass

    # Fallback: global Next link in this frame (least safe)
    nxt = frame.locator("a:has-text('Next')").first
    if nxt.count() == 0:
        return False
    try:
        cls = (nxt.get_attribute("class") or "").lower()
        aria = (nxt.get_attribute("aria-disabled") or "").lower()
        if "disabled" in cls or aria == "true":
            return False
    except Exception:
        pass

    try:
        nxt.click(timeout=2000)
        logger.info("[nav] next page")
        return True
    except Exception:
        return False


def collect_all_pages(page, logger: logging.Logger, max_pages: int = 10) -> List[Dict[str, Any]]:
    all_listings: List[Dict[str, Any]] = []
    seen_signatures = set()

    for page_no in range(1, max_pages + 1):
        frame, table = find_results_table_any_frame(page, logger, timeout_ms=60000)

        # signature = first few MLS values we can see in the table text
        table_text = norm_txt(table.inner_text())
        sig = tuple(MLS_RE.findall(table_text)[:5])
        if sig in seen_signatures and sig:
            logger.info("[nav] paging stopped (table content repeating)")
            break
        if sig:
            seen_signatures.add(sig)

        listings = parse_listings_from_table(table, logger, page_no=page_no)
        all_listings.extend(listings)

        # If there is no next, stop.
        if not click_next_page_near_table(frame, table, logger):
            break

        # Give Matrix time to re-render the grid
        time.sleep(0.6)

    # De-dupe by MLS
    by_mls = {}
    for r in all_listings:
        by_mls[r["MLS"]] = r
    return list(by_mls.values())


# ----------------------------
# Email
# ----------------------------
def send_email(cfg: Cfg, subject: str, body: str, logger: logging.Logger) -> None:
    if not cfg.smtp_host or not cfg.smtp_user or not cfg.smtp_pass or not cfg.alert_to or not cfg.alert_from:
        logger.warning("[email] SMTP env not fully configured; skipping email.")
        return

    msg = MIMEMultipart()
    msg["From"] = cfg.alert_from
    msg["To"] = cfg.alert_to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port) as server:
        server.starttls()
        server.login(cfg.smtp_user, cfg.smtp_pass)
        server.sendmail(cfg.alert_from, [cfg.alert_to], msg.as_string())

    logger.info(f"[email] sent to {cfg.alert_to}")


# ----------------------------
# Output + Summary
# ----------------------------
def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def summarize(listings: List[Dict[str, Any]]) -> Dict[str, Any]:
    ppsf_vals = [x["PPSF"] for x in listings if isinstance(x.get("PPSF"), (int, float)) and x["PPSF"] is not None]
    def stat(arr):
        if not arr:
            return None
        arr2 = sorted(arr)
        return {
            "min": arr2[0],
            "median": arr2[len(arr2)//2],
            "max": arr2[-1],
            "avg": sum(arr2) / len(arr2),
        }

    return {"n": len(listings), "ppsf": stat(ppsf_vals)}


# ----------------------------
# Main
# ----------------------------
def main():
    load_dotenv(dotenv_path=ROOT / ".env")

    cfg = Cfg(
        login_url=_env_str("MATRIX_LOGIN_URL", "https://search.mlslistings.com/Matrix/"),
        results_url=_env_str("MATRIX_RESULTS_URL", ""),
        shorthand=_env_str("MATRIX_SHORTHAND", "RESI A 95008"),
        ppsf_threshold=_env_float("PPSF_THRESHOLD", 789.25),
        min_lot_size=_env_float("MIN_LOT_SIZE", 5000.0),
        bootstrap_only=_env_bool("BOOTSTRAP_ONLY", 1),
        headless=_env_bool("HEADLESS", 0),
        browser_channel=_env_str("BROWSER_CHANNEL", "chrome"),
        log_level=_env_str("LOG_LEVEL", "INFO"),
        debug_pause_on_error=_env_bool("DEBUG_PAUSE_ON_ERROR", 1),

        smtp_host=_env_str("SMTP_HOST", ""),
        smtp_port=int(_env_float("SMTP_PORT", 587)),
        smtp_user=_env_str("SMTP_USER", ""),
        smtp_pass=_env_str("SMTP_PASS", ""),
        alert_to=_env_str("ALERT_TO", ""),
        alert_from=_env_str("ALERT_FROM", ""),
    )

    logger = setup_logger(cfg.log_level)

    print("\n=== Matrix Scan ===")
    print(f"login_url       : {cfg.login_url}")
    print(f"results_url_set : {bool(cfg.results_url)}")
    print(f"shorthand       : {cfg.shorthand!r}")
    print(f"PPSF_THRESHOLD  : {cfg.ppsf_threshold}")
    print(f"MIN_LOT_SIZE    : {cfg.min_lot_size}")
    print(f"BOOTSTRAP_ONLY  : {int(cfg.bootstrap_only)}")
    print(f"HEADLESS        : {int(cfg.headless)}")
    print(f"BROWSER_CHANNEL : {cfg.browser_channel}")
    print(f"LOG_LEVEL       : {cfg.log_level}\n")

    if cfg.ppsf_threshold > 5000:
        logger.warning(f"[warn] PPSF_THRESHOLD={cfg.ppsf_threshold} is extremely high. PPSF is usually ~500–2000.")

    state_path = ROOT / "state.json"
    if not state_path.exists():
        raise RuntimeError("state.json not found. Run python setup_auth.py first.")

    with sync_playwright() as p:
        browser = None
        context = None
        page = None

        try:
            browser = p.chromium.launch(
                channel=cfg.browser_channel if cfg.browser_channel else None,
                headless=cfg.headless,
            )
            context = browser.new_context(
                storage_state=str(state_path),
                viewport={"width": 1600, "height": 900},
                accept_downloads=True,
            )
            page = context.new_page()

            goto_matrix_home(page, cfg, logger)
            ensure_matrix_ui(page, timeout_ms=60000)

            # Try results_url, but it can expire. Fallback to shorthand.
            if cfg.results_url:
                logger.info("[nav] results_url provided; attempting direct results_url first")
                try:
                    page.goto(cfg.results_url, wait_until="domcontentloaded")
                except Exception as e:
                    logger.warning(f"[warn] results_url navigation failed ({e}); falling back to shorthand")

            if "Results.aspx" not in page.url:
                run_shorthand_search(page, cfg.shorthand, logger)

            page = get_results_page(page, logger)
            wait_for_results_ready(page, logger)

            export_path = export_results_csv(page, cfg, logger)
            step(f"exported file: {export_path}", logger)

            listings = load_export_csv(export_path)

            # If we found the grid but parsed 0 listings, dump a hard diagnostic.
            if len(listings) == 0:
                logger.error("[ERROR] Parsed 0 listings. Dumping diagnostics: logs/no_listings.*")
                dump_diag(page, "no_listings", logger)

            # Filter matches
            matches = []
            for r in listings:
                lot = r.get("Lot Size") or 0
                ppsf = r.get("PPSF")
                if lot < cfg.min_lot_size:
                    continue
                if ppsf is None:
                    continue
                if ppsf <= cfg.ppsf_threshold:
                    matches.append(r)
            matches.sort(key=lambda x: (x["PPSF"] if x["PPSF"] is not None else 1e18))

            fields = ["MLS", "Street Address", "Price", "Sq Ft Total", "Lot Size", "PPSF"]
            write_csv(OUT / "results.csv", listings, fields)
            write_csv(OUT / "matches.csv", matches, fields)

            summ_all = summarize(listings)
            summ_match = summarize(matches)

            print("=== Summary ===")
            print(f"total_listings  : {summ_all['n']}")
            print(f"matches         : {summ_match['n']}")
            if summ_all["ppsf"]:
                print(
                    f"ppsf_all        : min={summ_all['ppsf']['min']:.2f} "
                    f"med={summ_all['ppsf']['median']:.2f} "
                    f"avg={summ_all['ppsf']['avg']:.2f} "
                    f"max={summ_all['ppsf']['max']:.2f}"
                )
            if summ_match["ppsf"]:
                print(
                    f"ppsf_matches    : min={summ_match['ppsf']['min']:.2f} "
                    f"med={summ_match['ppsf']['median']:.2f} "
                    f"avg={summ_match['ppsf']['avg']:.2f} "
                    f"max={summ_match['ppsf']['max']:.2f}"
                )
            print("wrote           : out/results.csv, out/matches.csv")

            if cfg.bootstrap_only:
                print("[run] BOOTSTRAP_ONLY=1 => no emails sent")
            else:
                if len(matches) == 0:
                    print("[run] 0 matches => no email sent")
                else:
                    subject = f"MLS Matrix Bot: {len(matches)} matches"
                    lines = []
                    lines.append(f"Found {len(matches)} matches out of {len(listings)} total.\n")
                    lines.append(f"Filters:")
                    lines.append(f"- Lot Size >= {cfg.min_lot_size}")
                    lines.append(f"- PPSF <= {cfg.ppsf_threshold}\n")
                    lines.append("Top matches:\n")
                    for r in matches[:25]:
                        price = r["Price"]
                        sqft = r["Sq Ft Total"]
                        lot = r["Lot Size"]
                        ppsf = r["PPSF"]
                        lines.append(
                            f"{r['MLS']} | {r['Street Address']} | "
                            f"${price:,} | {sqft} sf | lot {lot:,} | PPSF {ppsf:.2f}"
                        )
                    send_email(cfg, subject, "\n".join(lines), logger)
                    print(f"[run] emailed {len(matches)} match(es)")

            print("[run] done ✅")

        except Exception as e:
            logger.error(f"[ERROR] {e}")
            if page is not None:
                dump_diag(page, "exception", logger)

            if cfg.debug_pause_on_error and page is not None:
                print("\nDebug pause ON. Browser is still open. Press Enter to close...")
                try:
                    input()
                except KeyboardInterrupt:
                    pass
            raise

        finally:
            try:
                if context is not None:
                    context.close()
            except Exception:
                pass
            try:
                if browser is not None:
                    browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
