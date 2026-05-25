import html
import json
import re
import urllib.parse

from core.types import Item


PRODUCT_META_RE = re.compile(
    r'data-shp-contents-id="(?P<id>\d+)"[^>]*data-shp-contents-dtl="(?P<dtl>[^\"]+)"',
    flags=re.IGNORECASE,
)


def _extract_from_source(page_source: str, limit: int):
    results = []
    seen = set()

    for m in PRODUCT_META_RE.finditer(page_source or ""):
        pid = m.group("id")
        if pid in seen:
            continue

        dtl_raw = html.unescape(m.group("dtl"))
        try:
            dtl = json.loads(dtl_raw)
        except Exception:
            continue

        name = ""
        price_val = ""
        for row in dtl:
            key = str(row.get("key") or "")
            value = str(row.get("value") or "")
            if key == "chnl_prod_nm":
                name = value.strip()
            elif key == "price":
                price_val = value.strip()

        if not name:
            continue

        seen.add(pid)
        price = f"{int(price_val):,}원" if price_val.isdigit() else "가격 확인"
        link = f"https://smartstore.naver.com/wittour/products/{pid}"
        results.append(Item("더블유아이티", name, price, link))

        if len(results) >= limit:
            break

    return results


def crawl(driver, keyword: str, limit: int = 40):
    q = urllib.parse.quote(keyword)
    url = f"https://smartstore.naver.com/wittour/search?q={q}"
    driver.get(url)

    # 페이지 소스의 data-shp 메타데이터에서 상품명/가격/ID 파싱
    page_source = driver.page_source or ""
    return _extract_from_source(page_source, limit=limit)
