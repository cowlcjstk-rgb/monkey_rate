import re
import urllib.parse

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from core.types import Item
from core.utils import enrich_seller_metadata, keyword_hit


SEARCH_URL = "https://nol.yanolja.com/discovery/list/search/PRODUCT_CATEGORY_GLOBAL_TNA"
SEARCH_FILTER = (
    "4XAAjW4YDKiGgVn9lFSyTxpjxAorLCVFlxeJFDYNPXa0IMAZYlWKBPjR2h8r0yXJwu8wF7wadfsuPxuBSPhiaxMxce7ZESB1T"
    "WgSqrIKaJC9tR8drYAuegjF30cyJERTKFRM7zoa4V71dKMTF8ZB6AMNazbqMAf"
)
CARD_SELECTOR = "a[data-card-type='basic'][href*='/tna/products/']"


def _read_cards(driver):
    return driver.execute_script(
        """
        return [...document.querySelectorAll(arguments[0])].map(card => {
            const price = card.querySelector('[aria-label^="판매가"]');
            const title = card.querySelector('span.line-clamp-2');
            const merchant = card.querySelector("div[class*='bg-fill-primary-weak']");
            return {
                title: title?.innerText?.trim() || '',
                price: price?.getAttribute('aria-label') || '',
                merchant: merchant?.innerText?.trim() || '',
                text: card.innerText || '',
                link: card.href || ''
            };
        });
        """,
        CARD_SELECTOR,
    )


def _price_text(card):
    match = re.search(r"판매가\s*([0-9,]+)\s*원", card.get("price", ""))
    if not match:
        # Fallback for a markup change while keeping price extraction to KRW values.
        match = re.search(r"최대할인가\s*([0-9,]+)\s*원", card.get("text", ""))
    return f"{match.group(1)}원" if match else "가격 확인"


def crawl(driver, keyword: str, limit: int = 40):
    if not keyword or not keyword.strip():
        return []

    query = urllib.parse.urlencode({"filter": SEARCH_FILTER, "q": keyword.strip()})
    driver.get(f"{SEARCH_URL}?{query}")
    WebDriverWait(driver, 25).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, CARD_SELECTOR))
    )

    seen = set()
    results = []
    for _ in range(10):
        for card in _read_cards(driver):
            link = card.get("link", "")
            title = card.get("title", "")
            if not link or not title or link in seen:
                continue
            seen.add(link)
            if not keyword_hit(title, "", keyword):
                continue
            results.append(Item("NOL", title, _price_text(card), link, merchant_name=card.get("merchant", "")))
            if len(results) >= limit:
                return enrich_seller_metadata(results)

        previous_count = len(seen)
        more_button = driver.execute_script(
            """return [...document.querySelectorAll('button')]
                .find(button => (button.innerText || '').includes('더보기')) || null;"""
        )
        if not more_button:
            break
        driver.execute_script("arguments[0].click()", more_button)
        try:
            WebDriverWait(driver, 8).until(lambda d: len(_read_cards(d)) > previous_count)
        except Exception:
            break

    return enrich_seller_metadata(results)
