import os
import time
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

LOGIN_URL = os.environ.get("MATRIX_LOGIN_URL", "").strip()
CHANNEL = os.environ.get("BROWSER_CHANNEL", "chrome").strip().lower()

# Save state.json next to this file (NOT relative to current working directory)
STATE_PATH = Path(__file__).with_name("state.json")

if not LOGIN_URL:
    raise RuntimeError(f"MATRIX_LOGIN_URL missing in {ENV_PATH}")

MENU_TEXT = "MY MATRIX"
CONNECT_URL = os.environ.get("MATRIX_RESULTS_URL", "").strip()

def any_page_has_text(context, text: str) -> bool:
    for pg in context.pages:
        try:
            if pg.is_closed():
                continue
            if pg.locator(f"text={text}").count() > 0:
                return True
        except Exception:
            continue
    return False

def first_page_with_text(context, text: str):
    for pg in context.pages:
        try:
            if pg.is_closed():
                continue
            if pg.locator(f"text={text}").count() > 0:
                return pg
        except Exception:
            continue
    return None

print("Using MATRIX_LOGIN_URL =", LOGIN_URL)
print("Using channel          =", CHANNEL)
print("Env path               =", ENV_PATH)
print("Will save state to     =", STATE_PATH)

with sync_playwright() as p:
    browser = p.chromium.launch(channel=CHANNEL, headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto(LOGIN_URL, wait_until="domcontentloaded")

    print("\nLogin in the browser window.")
    print("After you can see the Matrix menu, press Enter here to save state.json.\n")

    deadline = time.time() + 300
    while time.time() < deadline:
        # Recover if stuck on responder
        for pg in list(context.pages):
            try:
                if pg.is_closed():
                    continue
                if "AuthnRequestResponder" in pg.url:
                    pg.goto(CONNECT_URL, wait_until="domcontentloaded")
            except Exception:
                continue

        if any_page_has_text(context, MENU_TEXT):
            break
        time.sleep(1)

    if not any_page_has_text(context, MENU_TEXT):
        raise RuntimeError("Login not detected within 5 minutes (MY MATRIX not found).")

    # IMPORTANT: visit connect domain before saving state, so cookies for that domain exist too
    page.goto(CONNECT_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    input("Press Enter to save state.json...")

    context.storage_state(path=str(STATE_PATH))
    context.close()
    browser.close()

print(f"Saved session to {STATE_PATH}")
