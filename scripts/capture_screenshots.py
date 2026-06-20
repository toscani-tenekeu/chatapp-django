import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault(
    "PLAYWRIGHT_BROWSERS_PATH",
    str(BASE_DIR / ".venv" / "playwright-browsers"),
)

from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("CHATAPP_BASE_URL", "http://127.0.0.1:8000")
OUTPUT_DIR = BASE_DIR / "docs" / "screenshots"
DESKTOP = {"width": 1440, "height": 1000}
MOBILE = {"width": 390, "height": 844}


def capture(page, name, selector=None):
    if selector:
        page.wait_for_selector(selector)
    page.wait_for_timeout(250)
    page.screenshot(path=OUTPUT_DIR / name)
    print(f"  captured {name}")


def login(page):
    page.goto(f"{BASE_URL}/signin/")
    page.locator("[name=email]").fill("alice@example.com")
    page.locator("[name=password]").fill("demo-pass-123")
    page.locator("button[type=submit]").click()
    page.wait_for_selector(".app")


def port_is_open(host, port):
    with socket.socket() as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


@contextmanager
def app_server():
    parsed = urlparse(BASE_URL)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    if port_is_open(host, port):
        yield
        return

    process = subprocess.Popen(
        [
            str(BASE_DIR / ".venv" / "bin" / "daphne"),
            "-b", host,
            "-p", str(port),
            "chatapp.asgi:application",
        ],
        cwd=BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(60):
            if process.poll() is not None:
                raise RuntimeError("Daphne stopped before the capture session started.")
            if port_is_open(host, port):
                break
            time.sleep(0.25)
        else:
            raise RuntimeError(f"Daphne did not open {host}:{port}.")
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def capture_gallery(page):
    page.goto(f"{BASE_URL}/signin/")
    capture(page, "01-signin.png", ".auth-box")

    page.locator("[name=email]").fill("alice@example.com")
    page.locator("[name=password]").fill("wrong-password")
    page.locator("button[type=submit]").click()
    capture(page, "02-signin-error.png", ".messages-flash")

    page.goto(f"{BASE_URL}/signup/")
    capture(page, "03-signup.png", ".auth-box")

    login(page)
    capture(page, "04-home-social-states.png", "#pending-section")

    page.goto(f"{BASE_URL}/?q=e")
    capture(page, "05-search-users-rooms.png", ".search-panel")

    page.goto(f"{BASE_URL}/?q=introuvable")
    capture(page, "06-search-empty.png", ".search-panel")

    page.goto(f"{BASE_URL}/room/general/")
    capture(page, "07-room-general.png", "#messages")

    page.goto(f"{BASE_URL}/room/frontend/")
    capture(page, "08-room-frontend.png", "#messages")

    page.goto(f"{BASE_URL}/dm/bob/")
    capture(page, "09-direct-message-bob.png", "#messages")

    page.goto(f"{BASE_URL}/dm/carole/")
    capture(page, "10-direct-message-carole.png", "#messages")

    page.goto(f"{BASE_URL}/")
    page.evaluate("localStorage.setItem('nexchat-theme', 'light')")
    page.reload()
    capture(page, "11-home-light-theme.png", ".app")

    page.evaluate("localStorage.setItem('nexchat-theme', 'dark')")
    page.set_viewport_size(MOBILE)
    page.goto(f"{BASE_URL}/")
    capture(page, "12-mobile-home.png", ".mobile-header")

    page.locator("#hamburger").click()
    capture(page, "13-mobile-navigation.png", ".sidebar.open")

    page.goto(f"{BASE_URL}/room/general/")
    capture(page, "14-mobile-room.png", "#messages")

    page.locator("#members-btn").click()
    capture(page, "15-mobile-room-members.png", ".room-sidebar.open")

    page.goto(f"{BASE_URL}/dm/bob/")
    capture(page, "16-mobile-direct-message.png", "#messages")


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for old_capture in OUTPUT_DIR.glob("*.png"):
        old_capture.unlink()

    with app_server(), sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport=DESKTOP, device_scale_factor=1)
        try:
            capture_gallery(page)
        finally:
            browser.close()
    print(f"Screenshots saved to {OUTPUT_DIR.resolve()}")
