import os
import pandas as pd

def _to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce")

def calculate_ppsf(price: float, sqft: float, lot: float) -> float:
    # matches PPSF_finder.py exactly
    if lot >= 5 * sqft:
        denom = 0.9 * sqft + 0.1 * lot
        return price / denom
    return price / sqft

def compute_threshold_from_csv(csv_path: str, min_lot_size: int = 5000) -> dict:
    df = pd.read_csv(csv_path)

    need = {"Price", "Sq Ft Total", "Lot Size"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"Sold CSV missing columns: {sorted(missing)}")

    df["price"] = _to_num(df["Price"])
    df["sqft"] = _to_num(df["Sq Ft Total"])
    df["lot"] = _to_num(df["Lot Size"])

    df = df.dropna(subset=["price", "sqft", "lot"])
    df = df[(df["price"] > 100_000) & (df["sqft"] >= 400)]
    df = df[df["lot"] >= min_lot_size]

    df["ppsf"] = df.apply(lambda r: calculate_ppsf(r["price"], r["sqft"], r["lot"]), axis=1)
    df = df[df["ppsf"].between(200, 5000)]

    if df.empty:
        raise ValueError("No rows after filtering. Check Lot Size formatting and filters.")

    return {
        "median": float(df["ppsf"].quantile(0.5)),
        "p10": float(df["ppsf"].quantile(0.1)),
        "count": int(len(df)),
    }
