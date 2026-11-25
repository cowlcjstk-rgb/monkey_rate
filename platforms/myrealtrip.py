# platforms/myrealtrip.py
import time
import re
import urllib.parse

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from core.types import Item
from core.utils import extract_first_text, keyword_hit, clean_price, pick_title_from_lines, enrich_seller_metadata


TH_SELECTED = "cities%3ABangkok%3AChiang+Mai%3APattaya%3APhuket%3AKrabi%3AHua+Hin"

_PRICE_WON_RE = re.compile(r"([0-9]{1,3}(?:,[0-9]{3})+)\s*원")


def extract_price_won(text: str) -> str:
    """
    카드 텍스트에서 'xx,xxx원' 금액들을 모두 뽑아
    - 쿠폰 전/후 가격이 함께 있으면 보통 더 작은 값이 최종가라 min() 사용
    """
    prices = _PRICE_WON_RE.findall(text or "")
    if not prices:
        return ""
    nums = [int(p.replace(",", "")) for p in prices]
    return f"{min(nums):,}원"


def _wait_results_stable(driver, cards_css: str, timeout: int = 15, stable_sec: float = 1.0):
    """
    결과 카드가 '한 번 갱신되고' 난 뒤 안정화될 때까지 대기.
    (초기 렌더/이전 상태 → XHR 반영 후 렌더) 타이밍 문제 방지용
    """
    wait = WebDriverWait(driver, timeout)
    wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, cards_css)))

    end = time.time() + timeout
    last_first = None
    last_change = time.time()

    while time.time() < end:
        cards = driver.find_elements(By.CSS_SELECTOR, cards_css)
        first = (cards[0].text or "").strip() if cards else ""
        if first != last_first:
            last_first = first
            last_change = time.time()
        else:
            if time.time() - last_change >= stable_sec:
                return
        time.sleep(0.2)
    # 타임아웃이어도 최소 로딩은 된 상태라 그냥 진행


def crawl(driver, keyword: str, limit: int = 30):
    results = []
    q = urllib.parse.quote_plus(keyword)

    url = (
        "https://www.myrealtrip.com/search"
        f"?tab=tour&q={q}"
        "&extra=&per=20"
        f"&selected={TH_SELECTED}"
    )

    # ✅ (권장) 캐시 드라이버/세션 꼬임 방지: 쿠키/스토리지 정리
    try:
        driver.delete_all_cookies()
        driver.execute_script("window.localStorage.clear(); window.sessionStorage.clear();")
    except:
        pass

    driver.get(url)

    # ✅ URL이 유지되는지 확인(리다이렉트/상태복원으로 파라미터 누락 방지)
    WebDriverWait(driver, 15).until(lambda d: "selected=cities%3ABangkok" in d.current_url)

    # ✅ 렌더 완료 대기 (eager 로딩 보완)
    WebDriverWait(driver, 15).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

    # 클래스명은 배포 때마다 바뀔 수 있어, 상품 링크를 기준으로 카드를 찾는다.
    cards_css = "a[href*='/products/']"
    _wait_results_stable(driver, cards_css, timeout=15, stable_sec=1.0)

    items = driver.find_elements(By.CSS_SELECTOR, cards_css)

    seen = set()
    for it in items:
        try:
            link = it.get_attribute("href") or ""
            if not link or link in seen:
                continue
            seen.add(link)

            title = extract_first_text(it, [
                "h3", "h4",
                "[data-testid*='title']",
                "[class*='title']",
                "span[class*='title']",
                "span.css-1kb0da2",
            ])

            text_content = (it.text or "").strip()

            if not title:
                lines = [l for l in text_content.split("\n") if l.strip()]
                title = pick_title_from_lines(lines, keyword)

            # 검색 결과의 상품명과 부가 설명 어디든 검색어가 있으면 유지한다.
            if not keyword_hit(title, text_content, keyword):
                continue

            # ✅ 가격: 퍼센트(쿠폰율)로 잡히는 케이스 방지
            price_candidate = extract_first_text(it, ["span.css-1445f1u"]).strip()
            if "%" in price_candidate:
                price_candidate = ""

            # 후보가 없거나 이상하면 카드 텍스트에서 '원' 금액 추출(쿠폰가 포함 시 최종가로 보통 min)
            price = price_candidate or extract_price_won(text_content) or clean_price(text_content)

            if link and title:
                results.append(Item("마이리얼트립", title, price, link))
                if len(results) >= limit:
                    break
        except:
            continue

    return enrich_seller_metadata(results)
