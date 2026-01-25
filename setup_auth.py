"""
setup_auth.py

Open Matrix login in a real Chrome window, let you log in manually (including 2FA),
then save Playwright storage_state to state.json for scan_matrix.py.

Notes:
- If you ever land on the XML/SAML error page (AuthnRequestResponder.ashx),
  just type https://connect.mlslistings.com/ in that SAME tab and proceed.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from playwright.sync_api import sync_playwright


def _env_str(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return default if v is None else str(v)


def main():
    root = Path(__file__).resolve().parent
    env_path = root / ".env"
    if load_dotenv is not None:
        load_dotenv(dotenv_path=env_path, override=True)

    login_url = _env_str("MATRIX_LOGIN_URL", "https://search.mlslistings.com/Matrix/").strip()
    channel = _env_str("BROWSER_CHANNEL", "chrome").strip() or "chrome"
    state_path = root / "state.json"

    print(f"Using MATRIX_LOGIN_URL = {login_url}")
    print(f"Using channel         = {channel}")
    print(f"Env file path         = {env_path}")
    print("")
    print("In the browser window:")
    print("1) If you see the XML/SAML error page at connect.mlslistings.com/SAML/AuthnRequestResponder.ashx")
    print("   then in that SAME window, type this URL in the address bar and press Enter:")
    print("   https://connect.mlslistings.com/")
    print("2) Log in normally (do 2FA if required).")
    print("3) Stop when you can see the Matrix interface (top menu like MY MATRIX / SEARCH).")
    print("4) Come back here and press Enter to save the session.")
    print("")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel=channel, headless=False)
        context = browser.new_context(viewport={"width": 1600, "height": 900})
        page = context.new_page()
        page.goto(login_url, wait_until="domcontentloaded")

        input("After you are logged in and can see Matrix normally, press Enter here... ")

        # Save session
        context.storage_state(path=str(state_path))
        print(f"Saved session to {state_path}")

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
