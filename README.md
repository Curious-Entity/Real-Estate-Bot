# MLS Listing Opportunity Scanner

A Python automation project for screening MLS Matrix listings against configurable investment criteria.

The scanner restores an authenticated Matrix session, runs a configured property search, exports listings to CSV, and identifies properties that meet defined lot-size and price-per-square-foot thresholds. It can also send email alerts for qualifying matches.

> Requires authorized access to MLS Matrix. Use only in accordance with your MLS provider's terms, data-license restrictions, and applicable privacy requirements.

## Features

- Automates MLS Matrix searches with Playwright
- Supports a Matrix shorthand search or direct results URL
- Exports available search results to CSV
- Normalizes listing details including price, square footage, and lot size
- Calculates price per square foot
- Filters listings by configurable lot-size and PPSF thresholds
- Writes complete results and matches to CSV
- Optionally emails a summary of qualifying properties
- Captures logs and diagnostic artifacts when automation fails

## Project structure

```text
├── scan_matrix.py     # Main search, export, filtering, and alert workflow
├── setup_auth.py      # Saves an authenticated Playwright browser session
├── smtp_test.py       # Tests SMTP alert configuration
├── PPSF_finder.py     # Historical price-per-square-foot analysis
└── requirements.txt
```

## Requirements

- Python 3.10+
- Google Chrome
- Valid MLS Matrix access
- Optional SMTP credentials for alerts

## Installation

```bash
git clone https://github.com/Curious-Entity/Real-Estate-Bot.git
cd Real-Estate-Bot
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## Configuration

Create a local `.env` file:

```env
MATRIX_LOGIN_URL=https://search.mlslistings.com/Matrix/
MATRIX_SHORTHAND=RESI A 95008
PPSF_THRESHOLD=789.25
MIN_LOT_SIZE=5000
BOOTSTRAP_ONLY=1
HEADLESS=0
BROWSER_CHANNEL=chrome
LOG_LEVEL=INFO
DEBUG_PAUSE_ON_ERROR=1

# Optional SMTP alerts
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your-email@example.com
SMTP_PASS=your-app-password
ALERT_TO=recipient@example.com
ALERT_FROM=your-email@example.com
```

Never commit `.env`, `state.json`, MLS exports, screenshots, or logs.

## Authenticate

The project uses a saved Playwright browser session so credentials and MFA can be completed manually.

```bash
python setup_auth.py
```

Sign in through the Chrome window, complete any required MFA, then return to the terminal and press Enter. The script saves a local `state.json` session file.

## Run a scan

```bash
python scan_matrix.py
```

The workflow restores the session, runs the configured search, exports results, calculates PPSF, applies the filters, writes CSV output, and—when enabled—emails qualifying listings.

## Output

```text
out/results.csv   # All parsed listings
out/matches.csv   # Listings matching the configured filters
logs/scan.log     # Runtime and diagnostic log
```

## Historical PPSF analysis

`PPSF_finder.py` analyzes a local historical-sales CSV and prints market PPSF statistics:

```bash
python PPSF_finder.py
```

## Limitations

- Matrix UI structure and export behavior may change over time.
- Saved sessions expire and require re-authentication.
- PPSF is a screening heuristic, not an appraisal or investment recommendation.
- Listing data should be validated through normal real-estate due diligence.

## Security and data handling

Do not publish MLS exports, captured pages, screenshots, authenticated browser state, or SMTP credentials. Keep these local-only:

```text
.env
state.json
data/
out/
logs/
```
