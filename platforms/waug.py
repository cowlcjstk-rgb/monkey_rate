import time
import urllib.parse
from selenium.webdriver.common.by import By

from core.types import Item
from core.utils import wait_present, smart_scroll, extract_first_text, clean_price


def crawl(driver, keyword: str, limit: int = 40):
    results = []
    encoded = urllib.parse.quote(keyword)

    url = f"https://www.waug.com/ko/search?keyword={encoded}&click_search=true&areaIds=11%2C6%2C8%2C9"
    driver.get(url)

    card_selector = "a[href*='/ko/activities/'], a[href*='/activities/'], a[href*='/goods/']"

    try:
        wait_present(driver, card_selector, timeout=18)
    except Exception:
        time.sleep(2)

    smart_scroll(driver, card_selector, target_count=60, max_round=10)
    items = driver.find_elements(By.CSS_SELECTOR, card_selector)

    if not items:
        all_anchors = driver.find_elements(By.CSS_SELECTOR, "a[href]")
        items = [a for a in all_anchors if "/activities/" in (a.get_attribute("href") or "") or "/goods/" in (a.get_attribute("href") or "")]

    seen = set()

    for it in items:
        if len(results) >= limit:
            break
        try:
            link = it.get_attribute("href") or ""
            if not link or link in seen:
                continue
            seen.add(link)

            title = extract_first_text(it, ["h3", "h4", "[class*='title']"]).strip()
            text_content = (it.text or "").strip()
            if not text_content:
                text_content = (it.get_attribute("innerText") or "").strip()

            if not title and text_content:
                title = text_content.split("\n")[0].strip()

            price = clean_price(text_content)

            if title:
                results.append(Item("와그", title, price, link))
        except Exception:
            continue

    return results
