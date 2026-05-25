import urllib.parse
import requests

from core.types import Item

BASE = "https://travel.interpark.com/tna/api/tour-api/tna-product/externals/products"
CITY_IDS = (
    "9f63ac1e-153b-4919-80a0-35eef6bf5030,"
    "de316ec0-fed4-432d-8026-159d61ef73ff,"
    "fa5ed509-7793-4936-91db-b96fbca974dc,"
    "4cba5f24-69af-4687-a698-9d48a1b92dd5,"
    "a5829547-93bd-4d71-80ec-39ecf41d6093,"
    "b0dfbb16-3107-4a1b-884b-07259e656fea,"
    "c6012a60-a242-4f0c-8db1-cdde7c791ac1,"
    "925aa3bf-765f-4384-b231-8b51aaf2efd5"
)


def _format_price(value) -> str:
    try:
        return f"{int(value):,}원"
    except Exception:
        return "가격 확인"


def crawl(driver, keyword: str, limit: int = 40):
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://travel.interpark.com/",
    })

    results = []
    seen = set()

    page = 1
    size = 20
    max_pages = 10  # 스크롤 추가 로딩 대응 상한

    while len(results) < limit and page <= max_pages:
        params = {
            "page": page,
            "size": size,
            "withAdditionalPrice": "true",
            "withReview": "true",
            "language": "KO",
            "currency": "KRW",
            "sortType": "RECOMMEND",
            "keyword": keyword,
            "maxPrice": "",
            "cityIds": CITY_IDS,
        }

        r = session.get(BASE, params=params, timeout=20)
        if r.status_code >= 400:
            raise RuntimeError(f"인터파크 API 실패: HTTP {r.status_code}")

        data = r.json() if r.text else {}
        body = data.get("body") or []
        page_info = data.get("page") or {}

        if not body:
            break

        for it in body:
            if len(results) >= limit:
                break

            pid = (it.get("id") or "").strip()
            title = (it.get("name") or "").strip()
            if not pid or not title:
                continue

            if pid in seen:
                continue
            seen.add(pid)

            price_obj = it.get("price") or {}
            display_price = price_obj.get("display") or price_obj.get("sales")
            price = _format_price(display_price)

            link = f"https://travel.interpark.com/tna/products/{pid}"
            results.append(Item("인터파크 투어", title, price, link))

        total_pages = int(page_info.get("totalPages") or 0)
        if total_pages and page >= total_pages:
            break
        page += 1

    return results
