from os import environ
from pathlib import Path
from shutil import which

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


def _pick_chrome_binary() -> str | None:
    env_path = environ.get("CHROME_BINARY")
    if env_path and Path(env_path).is_file():
        return env_path

    for path in [
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ]:
        if Path(path).is_file():
            return path

    for name in ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable"]:
        found = which(name)
        if found:
            return found

    return None


def _pick_chromedriver_binary() -> str | None:
    env_path = environ.get("CHROMEDRIVER_BINARY")
    if env_path and Path(env_path).is_file():
        return env_path

    for path in [
        "/usr/bin/chromedriver",
        "/usr/local/bin/chromedriver",
    ]:
        if Path(path).is_file():
            return path

    found = which("chromedriver")
    if found:
        return found

    return None


def build_driver(headless: bool = True):
    chrome_options = Options()
    binary = _pick_chrome_binary()
    if binary:
        chrome_options.binary_location = binary

    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
    }
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.page_load_strategy = "eager"

    chromedriver = _pick_chromedriver_binary()
    if chromedriver:
        service = Service(chromedriver)
    else:
        service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(20)

    try:
        driver.execute_cdp_cmd("Network.enable", {})
    except Exception:
        pass

    return driver
