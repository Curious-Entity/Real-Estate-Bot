import pandas as pd

CSV_PATH = "data/Agent 1 Line.csv"  # change if needed
USE = "median"  # "mean" or "median"
RATIO = 0.70

def num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(r"[^0-9.]", "", regex=True), errors="coerce")

def main():
    df = pd.read_csv(CSV_PATH)

    df["sale_date"] = pd.to_datetime(df["Sale Date"], errors="coerce")
    df["price"] = num(df["Price"])
    df["sqft"] = num(df["Sq Ft Total"])

    # PPSF for SFR baseline
    df["ppsf"] = df["price"] / df["sqft"]

    # basic sanity filters (tune later)
    df = df[df["price"] > 100_000]
    df = df[df["sqft"].between(400, 10_000)]
    df = df[df["ppsf"].between(200, 5000)]

    baseline = float(df["ppsf"].median() if USE == "median" else df["ppsf"].mean())
    thresh = RATIO * baseline

    print("rows:", len(df))
    print("sale date range:", df["sale_date"].min().date(), "to", df["sale_date"].max().date())
    print(f"{USE} ppsf baseline: {baseline:.2f}")
    print(f"{int(RATIO*100)}% threshold: {thresh:.2f}")

    print("\nLowest 10 PPSF (sanity check these addresses):")
    cols = ["MLS #", "Street Address", "Sale Date", "Price", "Sq Ft Total", "ppsf"]
    print(df.sort_values("ppsf")[cols].head(10).to_string(index=False))

if __name__ == "__main__":
    main()
