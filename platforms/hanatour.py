import base64
import json
import time
import urllib.parse
from typing import Any, Dict, List, Optional

from core.types import Item

API_URL_KEYWORD = "gw.hanatour.com/search/v2/attr/localTour/search"
SEARCH_PAGE = "https://www.hanatour.com/tour-ticket/product"


def _json_loads_safe(s: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(s)
    except Exception:
        return None


def _format_price(price_raw: str) -> str:
    price_raw = (price_raw or "").strip()
    if price_raw.isdigit():
        return f"{int(price_raw):,}원"
    return "가격 확인"


def _extract_items(payload: Dict[str, Any], limit: int) -> List[Item]:
    out: List[Item] = []
    data = (payload or {}).get("data") or {}
    arr = data.get("data") or []

    seen = set()
    for it in arr:
        if len(out) >= limit:
            break

        title = (it.get("localTourTitle") or it.get("prodNm") or "").strip()
        link = (it.get("detailUrl") or "").strip()
        price = _format_price(it.get("discountPrice") or it.get("regularPrice") or "")

        if not title or not link.startswith("http"):
            continue
        if link in seen:
            continue
        seen.add(link)

        out.append(Item("하나투어", title, price, link))

    return out


def _get_latest_api_payload(driver, keyword: str, timeout: int = 15) -> Optional[Dict[str, Any]]:
    try:
        driver.get_log("performance")
    except Exception:
        pass

    end = time.time() + timeout
    last_good = None

    while time.time() < end:
        try:
            logs = driver.get_log("performance")
        except Exception:
            logs = []

        for entry in logs:
            msg = _json_loads_safe(entry.get("message", ""))
            if not msg:
                continue

            message = msg.get("message") or {}
            if message.get("method") != "Network.responseReceived":
                continue

            params = message.get("params") or {}
            response = params.get("response") or {}
            url = response.get("url") or ""

            if API_URL_KEYWORD not in url:
                continue

            request_id = params.get("requestId")
            if not request_id:
                continue

            try:
                body_obj = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
            except Exception:
                continue

            body = (body_obj or {}).get("body") or ""
            if (body_obj or {}).get("base64Encoded") is True:
                try:
                    body = base64.b64decode(body).decode("utf-8", errors="ignore")
                except Exception:
                    continue

            payload = _json_loads_safe(body)
            if not payload:
                continue

            server_kw = ((payload.get("data") or {}).get("keyword") or "").strip()
            if server_kw and server_kw != keyword:
                continue

            last_good = payload

        if last_good:
            return last_good

        time.sleep(0.25)

    return last_good


def crawl(driver, keyword: str, limit: int = 40):
    sub_kw = f"태국 {keyword}".strip()
    sub_kw_enc = urllib.parse.quote(sub_kw)

    driver.get(f"{SEARCH_PAGE}?subKeyword={sub_kw_enc}")

    payload = _get_latest_api_payload(driver, keyword=sub_kw, timeout=15)
    if not payload:
        return []

    return _extract_items(payload, limit=limit)
