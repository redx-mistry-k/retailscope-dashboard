"""Capture a README screenshot from the running local Streamlit app.

Requires Playwright and its Chromium browser installed separately.
"""
from pathlib import Path
import os
import shutil

from playwright.sync_api import sync_playwright


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "docs" / "dashboard-overview.png"
    target.parent.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        candidates = [os.environ.get("CHROME_PATH"), shutil.which("chrome"),
                      r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
        executable = next((path for path in candidates if path and Path(path).exists()), None)
        browser = playwright.chromium.launch(headless=True, executable_path=executable)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page.goto("http://127.0.0.1:8501", wait_until="domcontentloaded", timeout=30000)
        page.get_by_text("RetailScope", exact=False).first.wait_for(timeout=30000)
        page.wait_for_timeout(2500)
        if page.locator("text=There are multiple").count():
            raise RuntimeError("Streamlit error is visible in the dashboard")
        page.screenshot(path=str(target), full_page=True)
        print(f"Saved {target} ({target.stat().st_size:,} bytes)")
        browser.close()


if __name__ == "__main__":
    main()
