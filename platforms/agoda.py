import json
import time

import requests

from core.types import Item
from core.utils import keyword_hit


SEARCH_URL = (
    "https://www.agoda.com/ko-kr/activities/search"
    "?cityId=9395&currency=KRW&cid=1908612"
)
API_URL = "https://www.agoda.com/api/activities/graphql"
SUPPLIER_NAMES = {
    50002: "Kkday",
    50003: "Bcom",
    50005: "GlobalTix",
}
MERCHANT_NAMES_BY_SUPPLIER = {
    50002: "KKday Singapore Pte. Ltd.",
    50003: "Klook Travel Technology Limited",
}
# Verified from Agoda's booking/setup response for this specific activity.
VERIFIED_MERCHANTS = {1641313: "Hungry Hub (THB)"}


def _capture_search_request(driver, timeout: int = 12):
    end = time.time() + timeout
    while time.time() < end:
        try:
            entries = driver.get_log("performance")
        except Exception:
            entries = []
        for entry in entries:
            try:
                message = json.loads(entry.get("message", "{}")).get("message", {})
                request = (message.get("params") or {}).get("request") or {}
                url = request.get("url") or ""
                if "api/activities/graphql?operation=search" not in url or "key=Search" not in url:
                    continue
                if request.get("postData"):
                    return url, json.loads(request["postData"]), request.get("headers") or {}
            except (ValueError, TypeError):
                continue
        time.sleep(0.2)
    return None, None, None


def _format_price(activity):
    pricing = (
        activity.get("activityRepresentativeInfo", {})
        .get("pricingSummary", {})
        .get("pricing", [])
    )
    for currency_price in pricing:
        if currency_price.get("currency") != "KRW":
            continue
        display = currency_price.get("display", {})
        total = (display.get("perBook") or {}).get("total") or {}
        amount = (total.get("allInclusive") or {}).get("chargeTotal")
        if amount is None:
            amount = (total.get("exclusive") or {}).get("chargeTotal")
        if amount is not None:
            return f"{int(amount):,}원"
    return "가격 확인"


def crawl(driver, keyword: str, limit: int = 40):
    if not keyword or not keyword.strip():
        return []

    encoded_keyword = requests.utils.quote(keyword.strip())
    driver.get(f"{SEARCH_URL}&keyword={encoded_keyword}")
    request_url, request_body, request_headers = _capture_search_request(driver)
    if not request_body:
        raise RuntimeError("아고다 검색 API 요청을 확인하지 못했습니다.")

    parsed_url = request_url.split("&pageNumber=", 1)[0]
    base_url = parsed_url.split("&key=", 1)[0]
    session = requests.Session()
    session.headers.update({
        key: value for key, value in request_headers.items()
        if key.lower() not in {"content-length", "host", "connection"}
    })
    for cookie in driver.get_cookies():
        session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"))

    results = []
    seen = set()
    page_size = 1
    for page_number in range(1, 9):
        body = json.loads(json.dumps(request_body))
        search_request = body["variables"]["SearchRequest"]["searchRequest"]
        search_request["searchCriteria"]["pagination"]["number"] = page_number
        body["queryString"] = (
            f"?operation=search&cityId=9395&keyword={encoded_keyword}"
            f"&pageNumber={page_number}"
        )
        response = session.post(
            f"{base_url}&pageNumber={page_number}&key=Search",
            json=body,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json().get("data", {}).get("search", {})
        result = payload.get("result") or {}
        activities = result.get("activities") or []
        if page_number == 1:
            page_size = (result.get("resultInfo") or {}).get("pagination", {}).get("size") or 8

        for activity in activities:
            info = activity.get("activityRepresentativeInfo") or {}
            title = ((activity.get("content") or {}).get("activity") or {}).get("title", "").strip()
            activity_id = info.get("activityId")
            supplier_id = activity.get("masterSupplierId")
            if not title or not activity_id or activity_id in seen:
                continue
            seen.add(activity_id)
            if not keyword_hit(title, "", keyword):
                continue

            link = (
                "https://www.agoda.com/ko-kr/activities/detail"
                f"?activityId={activity_id}&cityId=9395&currency=KRW&cid=1908612"
            )
            results.append(Item(
                "아고다",
                title,
                _format_price(activity),
                link,
                supplier_id=str(supplier_id or ""),
                supplier_name=SUPPLIER_NAMES.get(supplier_id, ""),
                merchant_name=VERIFIED_MERCHANTS.get(
                    int(activity_id), MERCHANT_NAMES_BY_SUPPLIER.get(supplier_id, "")
                ),
            ))
            if len(results) >= limit:
                break

        pagination = (result.get("resultInfo") or {}).get("pagination") or {}
        if len(results) >= limit or not pagination.get("hasMore"):
            break
        page_size = pagination.get("size") or page_size

    return results
