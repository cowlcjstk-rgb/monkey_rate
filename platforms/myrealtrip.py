import re
import time
import urllib.parse

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from core.types import Item
from core.utils import extract_first_text, keyword_hit, clean_price, pick_title_from_lines


TH_SELECTED = "cities%3ABangkok%3AChiang+Mai%3APattaya%3APhuket%3AKrabi%3AHua+Hin"
PRICE_WON_RE = re.compile(r"([0-9]{1,3}(?:,[0-9]{3})+)\s*원")


def extract_price_won(text: str) -> str:
    prices = PRICE_WON_RE.findall(text or "")
    if not prices:
        return ""
    nums = [int(p.replace(",", "")) for p in prices]
    return f"{min(nums):,}원"


def _wait_results_stable(driver, cards_css: str, timeout: int = 15, stable_sec: float = 1.0):
    wait = WebDriverWait(driver, timeout)
    wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, cards_css)))

    end = time.time() + timeout
    last_first = None
    last_change = time.time()

    while time.time() < end:
        cards = driver.find_elements(By.CSS_SELECTOR, cards_css)
        first = (cards[0].text or "").strip() if cards else ""
        if first != last_first:
            last_first = first
            last_change = time.time()
        elif time.time() - last_change >= stable_sec:
            return
        time.sleep(0.2)


def crawl(driver, keyword: str, limit: int = 30):
    results = []
    q = urllib.parse.quote_plus(keyword)

    url = (
        "https://www.myrealtrip.com/search"
        f"?tab=tour&q={q}"
        "&extra=&per=20"
        f"&selected={TH_SELECTED}"
    )

    try:
        driver.delete_all_cookies()
        driver.execute_script("window.localStorage.clear(); window.sessionStorage.clear();")
    except Exception:
        pass

    driver.get(url)

    WebDriverWait(driver, 15).until(lambda d: "selected=cities%3ABangkok" in d.current_url)
    WebDriverWait(driver, 15).until(lambda d: d.execute_script("return document.readyState") == "complete")

    cards_css = "div.css-1iyoj2o"
    _wait_results_stable(driver, cards_css, timeout=15, stable_sec=1.0)

    items = driver.find_elements(By.CSS_SELECTOR, cards_css)

    for it in items[:limit]:
        try:
            title = extract_first_text(it, [
                "h3", "h4", "[data-testid*='title']", "[class*='title']", "span[class*='title']", "span.css-1kb0da2",
            ])

            text_content = (it.text or "").strip()
            if not title:
                lines = [l for l in text_content.split("\n") if l.strip()]
                title = pick_title_from_lines(lines, keyword)

            if not keyword_hit(title, text_content, keyword):
                continue

            price_candidate = extract_first_text(it, ["span.css-1445f1u"]).strip()
            if "%" in price_candidate:
                price_candidate = ""

            price = price_candidate or extract_price_won(text_content) or clean_price(text_content)
            link = it.find_element(By.XPATH, "./ancestor::a").get_attribute("href")

            if link and title:
                results.append(Item("마이리얼트립", title, price, link))
        except Exception:
            continue

    return results
