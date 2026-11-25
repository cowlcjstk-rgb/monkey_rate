import re
import time
import json
import html
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def normalize_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", s)
    s = re.sub(r"[^0-9a-zA-Z가-힣]", "", s)
    return s


def contains_keyword(text: str, keyword: str) -> bool:
    t = normalize_text(text)
    k = normalize_text(keyword)
    return bool(k) and (k in t)


def keyword_hit(title: str, full_text: str, keyword: str) -> bool:
    return contains_keyword(title or "", keyword) or contains_keyword(full_text or "", keyword)


def clean_price(text: str) -> str:
    text = text or ""
    won_sign = re.findall(r"₩\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,})", text)
    won_word = re.findall(r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,})\s*원", text)
    krw_word = re.findall(r"KRW\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,})", text, flags=re.IGNORECASE)
    nums = won_sign + won_word + krw_word
    if nums:
        values = [int(n.replace(',', '')) for n in nums]
        return f"{min(values):,}원"

    fallback = re.findall(r"[0-9,]{4,}", text)
    if fallback:
        return fallback[-1]
    return "가격 확인"


def extract_first_text(el, selectors):
    for sel in selectors:
        try:
            t = el.find_element(By.CSS_SELECTOR, sel).text.strip()
            if t:
                return t
        except Exception:
            continue
    return ""


def wait_present(driver, css: str, timeout=12):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, css))
    )


def wait_one(driver, css: str, timeout=12):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, css))
    )


def smart_scroll(driver, css_to_count: str, target_count=25, max_round=8, step=900, pause=0.6):
    last = 0
    for _ in range(max_round):
        elems = driver.find_elements(By.CSS_SELECTOR, css_to_count)
        if len(elems) >= target_count:
            break
        if len(elems) == last:
            break
        last = len(elems)
        driver.execute_script(f"window.scrollBy(0, {step});")
        time.sleep(pause)


def pick_title_from_lines(lines, keyword):
    cleaned = []
    for l in lines:
        s = (l or "").strip()
        if not s:
            continue
        if re.fullmatch(r"\d\.\d", s):
            continue
        if any(x in s for x in ["리뷰", "후기", "명의", "옵션", "선택", "예약", "무료 취소", "즉시 확정"]):
            continue
        if "원" in s or "KRW" in s or "₩" in s or re.search(r"[0-9,]{4,}", s):
            continue
        cleaned.append(s)

    if not cleaned:
        return ""

    for l in cleaned:
        if contains_keyword(l, keyword):
            return l

    return max(cleaned, key=len)


def _organization_name(value):
    if isinstance(value, dict):
        return (value.get("name") or "").strip()
    if isinstance(value, list):
        for entry in value:
            name = _organization_name(entry)
            if name:
                return name
    return ""


def _seller_metadata_from_html(source):
    supplier = ""
    merchant = ""
    scripts = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        source or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for raw in scripts:
        try:
            payload = json.loads(html.unescape(raw))
        except (TypeError, ValueError):
            continue
        stack = payload if isinstance(payload, list) else [payload]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                supplier = supplier or _organization_name(node.get("provider"))
                merchant = merchant or _organization_name(node.get("seller"))
                stack.extend(value for value in node.values() if isinstance(value, (dict, list)))
        if supplier and merchant:
            break

    match = re.search(
        r'<strong\b(?=[^>]*seller-crown-icon)[^>]*>(.*?)</strong>',
        source or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        seller_text = re.sub(r"<[^>]+>", "", match.group(1))
        merchant = html.unescape(seller_text).strip() or merchant
    return supplier, merchant


def enrich_seller_metadata(items, max_workers=8):
    """Read provider/seller names from product pages that publish them."""
    pending = [item for item in items if item.link and (not item.supplier_name or not item.merchant_name)]
    if not pending:
        return items

    def fetch(item):
        try:
            response = requests.get(item.link, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
            if response.status_code >= 400:
                return item, "", ""
            supplier, merchant = _seller_metadata_from_html(response.text)
            return item, supplier, merchant
        except requests.RequestException:
            return item, "", ""

    with ThreadPoolExecutor(max_workers=min(max_workers, len(pending))) as executor:
        futures = [executor.submit(fetch, item) for item in pending]
        for future in as_completed(futures):
            item, supplier, merchant = future.result()
            item.supplier_name = item.supplier_name or supplier
            item.merchant_name = item.merchant_name or merchant
    return items
