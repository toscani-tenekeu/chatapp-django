import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


BASE_URL = os.environ.get("CHATAPP_BASE_URL", "http://127.0.0.1:8000")
OUTPUT_DIR = BASE_DIR / "docs" / "screenshots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def build_driver():
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Firefox(
        service=Service(executable_path="/snap/bin/geckodriver"),
        options=options,
    )
    driver.set_window_size(1440, 1080)
    return driver


def wait_for(driver, selector):
    return WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
    )


def screenshot(driver, name):
    driver.save_screenshot(str(OUTPUT_DIR / name))


def login(driver):
    driver.get(f"{BASE_URL}/signin/")
    wait_for(driver, "form")
    driver.find_element(By.NAME, "email").send_keys("alice@example.com")
    driver.find_element(By.NAME, "password").send_keys("demo-pass-123")
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    wait_for(driver, ".app, .main")


if __name__ == "__main__":
    driver = build_driver()
    try:
        driver.get(f"{BASE_URL}/signin/")
        wait_for(driver, ".auth-box")
        screenshot(driver, "01-signin.png")

        login(driver)
        time.sleep(1)
        screenshot(driver, "02-home.png")

        driver.get(f"{BASE_URL}/room/general/")
        wait_for(driver, "#messages")
        time.sleep(1)
        screenshot(driver, "03-room-general.png")

        driver.get(f"{BASE_URL}/dm/bob/")
        wait_for(driver, "#messages")
        time.sleep(1)
        screenshot(driver, "04-direct-message.png")
        print(f"Screenshots saved to {OUTPUT_DIR.resolve()}")
    finally:
        driver.quit()
