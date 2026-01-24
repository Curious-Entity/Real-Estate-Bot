from matrix_scan import ScanConfig, load_config, run_matrix_scan, write_csv, filter_matches

def main():
    cfg: ScanConfig = load_config()

    rows, matches = run_matrix_scan(cfg)

    write_csv(cfg.results_csv, rows)
    write_csv(cfg.matches_csv, matches)

    print(f"Wrote {len(rows)} listings -> {cfg.results_csv}")
    print(f"Wrote {len(matches)} matches  -> {cfg.matches_csv}")

if __name__ == "__main__":
    main()
