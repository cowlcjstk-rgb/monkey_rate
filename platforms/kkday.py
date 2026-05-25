import urllib.parse
from selenium.webdriver.common.by import By

from core.types import Item
from core.utils import wait_present, smart_scroll, extract_first_text, keyword_hit, clean_price


def _is_blocked(driver) -> bool:
    src = (driver.page_source or "").lower()
    title = (driver.title or "").lower()
    return "captcha" in src or "challenge" in src or title == "kkday.com"


def crawl(driver, keyword: str, limit: int = 40):
    results = []
    encoded = urllib.parse.quote(keyword)

    url = f"https://www.kkday.com/ko/product/search?keyword={encoded}"
    driver.get(url)

    if _is_blocked(driver):
        raise RuntimeError("봇 차단(CAPTCHA) 페이지가 열려 데이터 수집이 제한됩니다.")

    selector = "a[href*='/ko/product/']"
    wait_present(driver, selector, timeout=18)
    smart_scroll(driver, selector, target_count=60, max_round=10)

    items = driver.find_elements(By.CSS_SELECTOR, selector)
    seen = set()

    for it in items:
        if len(results) >= limit:
            break
        try:
            link = it.get_attribute("href") or ""
            if not link or link in seen:
                continue
            seen.add(link)

            title = extract_first_text(it, ["h3", "h4", "[class*='title']", "[data-testid*='title']"])
            if not title:
                title = (it.get_attribute("aria-label") or "").strip()

            text_content = it.text.strip()
            if not keyword_hit(title, text_content, keyword):
                continue

            price = clean_price(text_content)
            if title:
                results.append(Item("KKday", title, price, link))
        except Exception:
            continue

    return results
