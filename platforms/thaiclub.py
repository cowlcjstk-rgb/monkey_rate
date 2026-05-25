import urllib.parse
from selenium.webdriver.common.by import By

from core.types import Item
from core.utils import clean_price


def _normalize_no_space(text: str) -> str:
    return "".join((text or "").lower().split())


def crawl(driver, keyword: str, limit: int = 40):
    results = []
    seen = set()

    q = urllib.parse.quote(keyword)
    url = f"https://thaiclubtour.com/search.php?keyword={q}&x=0&y=0"
    driver.get(url)

    # 실제 검색 결과 상품 링크 패턴
    links = driver.find_elements(By.CSS_SELECTOR, "a[href*='item.php?t=']")

    for a in links:
        if len(results) >= limit:
            break
        try:
            href = (a.get_attribute("href") or "").replace("&amp;", "&")
            if not href or href in seen:
                continue
            seen.add(href)

            text_content = ((a.text or "") + "\n" + (a.get_attribute("innerText") or "")).strip()
            if not text_content:
                continue
            key = _normalize_no_space(keyword)
            if key and key not in _normalize_no_space(text_content):
                continue

            lines = [x.strip() for x in text_content.split("\n") if x.strip()]
            title = lines[0] if lines else "상품명 확인"
            price = clean_price(text_content)

            results.append(Item("타이클럽", title, price, href))
        except Exception:
            continue

    return results
