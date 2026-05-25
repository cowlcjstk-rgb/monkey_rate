import urllib.parse
from selenium.webdriver.common.by import By

from core.types import Item
from core.utils import wait_present, smart_scroll, extract_first_text, clean_price


def _is_blocked(driver) -> bool:
    src = (driver.page_source or "").lower()
    title = (driver.title or "").lower()
    return "captcha" in src or "captcha-delivery" in src or title == "klook.com"


def _normalize_no_space(text: str) -> str:
    return "".join((text or "").lower().split())


def _query_match(title: str, full_text: str, keyword: str) -> bool:
    key = _normalize_no_space(keyword)
    if not key:
        return False
    return (key in _normalize_no_space(title)) or (key in _normalize_no_space(full_text))


def crawl(driver, keyword: str, limit: int = 40):
    results = []
    seen = set()
    encoded = urllib.parse.quote(keyword)

    location = (
        "4,7,4676,17,5,63,5096,50293831,5256,5341,125,254,702414,703145,"
        "701356,216,5373,702317,50042805,541,703023,702320,40290997,40290570"
    )
    selector = "a[href*='/ko/activity/'], a[href*='/activity/']"

    max_pages = 5
    for page in range(1, max_pages + 1):
        if len(results) >= limit:
            break

        url = (
            "https://www.klook.com/ko/search/result/"
            f"?query={encoded}"
            f"&location={location}"
            "&sort=most_relevant"
            "&tab_key=0"
            f"&start={page}"
        )
        driver.get(url)

        if _is_blocked(driver):
            raise RuntimeError("봇 차단(CAPTCHA) 페이지가 열려 데이터 수집이 제한됩니다.")

        try:
            wait_present(driver, selector, timeout=18)
            smart_scroll(driver, selector, target_count=60, max_round=8)
            cards = driver.find_elements(By.CSS_SELECTOR, selector)
        except Exception:
            continue

        for c in cards:
            if len(results) >= limit:
                break
            try:
                link = c.get_attribute("href") or ""
                if not link or link in seen:
                    continue
                seen.add(link)

                title = extract_first_text(c, ["h3", "h4", "[data-testid*='title']", "[class*='title']"])
                if not title:
                    title = (c.get_attribute("aria-label") or "").strip()
                if not title:
                    title = (c.get_attribute("title") or "").strip()

                text_content = ((c.text or "") + "\n" + (c.get_attribute("innerText") or "")).strip()
                if not _query_match(title, text_content, keyword):
                    continue

                price = clean_price(text_content)
                results.append(Item("Klook", title or "상품명 확인", price, link))
            except Exception:
                continue

    return results
