import requests
import re

from core.types import Item

SEARCH_API = "https://www.monkeytravel.com/api/search/productList.php"
TARGET_PARTS = [3, 4, 5, 8]


def _build_link(menu_json, product_id: int) -> str:
    # 몽키트래블은 검색 링크가 아니라 상품 상세 링크를 바로 사용한다.
    # product_id만 바뀌는 형태로 고정한다.
    return f"https://www.monkeytravel.com/th/ko/tour/bangkok/product/product_detail.php?product_id={product_id}"


def _parse_price(value) -> str:
    if value is None:
        return "가격 확인"

    if isinstance(value, (int, float)):
        n = int(value)
        return f"{n:,}원" if n > 0 else "가격 확인"

    s = str(value)
    nums = re.findall(r"\d+", s)
    if not nums:
        return "가격 확인"

    n = int(nums[0])
    return f"{n:,}원" if n > 0 else "가격 확인"


def _normalize_no_space(text: str) -> str:
    return "".join((text or "").lower().split())


def crawl(driver, keyword: str, limit: int = 40):
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.monkeytravel.com",
        "Referer": "https://www.monkeytravel.com/",
    })

    rows = []
    for part in TARGET_PARTS:
        payload = {
            "site": "monkey",
            "lang": "ko",
            "branch": "1",
            "part": part,
            "searchTextSynonyms": keyword,
            "searchTextSynonyms2": "",
            "pageSize": 0,
        }

        r = session.post(SEARCH_API, json=payload, timeout=20)
        if r.status_code >= 400:
            continue

        obj = r.json() if r.text else {}
        if not obj.get("result"):
            continue

        data = obj.get("data") or {}
        rows.extend(data.get("productDataList") or [])

    if not rows:
        raise RuntimeError("몽키트래블 검색 결과가 없습니다.")

    key = _normalize_no_space(keyword)
    matched_rows = []
    for row in rows:
        title = (row.get("productName") or "").strip()
        if not title:
            continue
        if key and key in _normalize_no_space(title):
            matched_rows.append(row)

    source_rows = matched_rows

    results = []
    seen = set()

    for row in source_rows:
        if len(results) >= limit:
            break

        pid = row.get("product_id")
        title = (row.get("productName") or "").strip()
        if not pid or not title:
            continue

        if pid in seen:
            continue
        seen.add(pid)

        price = _parse_price(row.get("lowPrice"))
        link = _build_link(row.get("menuJson"), int(pid))

        results.append(Item("몽키트래블", title, price, link))

    return results
