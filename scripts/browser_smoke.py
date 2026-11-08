"""Exercise the running app's six tabs and three browser downloads.

Optional: requires Playwright and Chrome. Start Streamlit on port 8501 first.
"""
from __future__ import annotations

from pathlib import Path
import os
import re
import shutil
import tempfile

from playwright.sync_api import sync_playwright


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    candidates = [os.environ.get("CHROME_PATH"), shutil.which("chrome"),
                  r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
    executable = next((path for path in candidates if path and Path(path).exists()), None)
    with sync_playwright() as playwright, tempfile.TemporaryDirectory(dir=root) as folder:
        browser = playwright.chromium.launch(headless=True, executable_path=executable)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        page.goto("http://127.0.0.1:8501", wait_until="domcontentloaded", timeout=30000)
        page.get_by_text("RetailScope", exact=False).first.wait_for(timeout=30000)
        for label in ("Overview", "Sampling", "Market Estimates", "Geographic Analysis", "Data Quality", "Reports"):
            page.get_by_role("tab", name=re.compile(label)).click()
            page.wait_for_timeout(250)
            assert not page.get_by_text("Uncaught app execution").count(), label
        expected = [
            ("Download executive PDF", "RetailScope_Stakeholder_Report.pdf", b"%PDF-"),
            ("Download regional estimates", "RetailScope_Regional_Estimates.csv", b"data_provenance"),
            ("Download surveyed sample", "RetailScope_Survey_Sample.csv", b"data_provenance"),
        ]
        for label, filename, marker in expected:
            with page.expect_download(timeout=15000) as request:
                page.get_by_role("button", name=re.compile(label)).click()
            download = request.value
            assert download.suggested_filename == filename
            saved = Path(folder) / filename
            download.save_as(saved)
            assert marker in saved.read_bytes()
            print(f"{filename}: {saved.stat().st_size:,} bytes")
        print("Six browser tabs and three downloads: OK")
        browser.close()


if __name__ == "__main__":
    main()
