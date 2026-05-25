import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from core.driver import build_driver
from core.utils import normalize_text
from platforms import PLATFORM_CRAWLERS

st.set_page_config(page_title="가격 비교 검색", page_icon="💸", layout="wide")

st.markdown(
    """
    <style>
        .block-container {padding-top: 1.1rem; padding-bottom: 1.8rem; max-width: 1380px;}
        .stTabs [data-baseweb="tab-list"] {gap: 8px;}
        .stTabs [data-baseweb="tab"] {height: 40px; border-radius: 10px; padding: 0 14px;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("가격 비교 검색")
st.caption("플랫폼별 가격을 한 화면에서 비교하고 추적합니다.")

BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = BASE_DIR / "runtime"
RUNTIME_DIR.mkdir(exist_ok=True)
RECENT_FILE = RUNTIME_DIR / "recent_searches.json"
EXPORT_FILE = RUNTIME_DIR / "price_compare_export.xlsx"


def extract_price_number(price_str: str):
    nums = re.findall(r"[0-9,]+", price_str or "")
    if not nums:
        return None
    try:
        return int(nums[-1].replace(",", ""))
    except ValueError:
        return None


def get_driver():
    return build_driver(headless=True)


def get_reliability_label(platform: str, price_num):
    if price_num is None:
        return "가격확인필요"
    realtime_platforms = {"인터파크 투어", "몽키트래블", "더블유아이티", "타이클럽"}
    return "즉시반영" if platform in realtime_platforms else "변동가능"


def failure_code(msg: str):
    m = (msg or "").lower()
    if any(x in m for x in ["captcha", "robot", "bot"]):
        return "CAPTCHA"
    if any(x in m for x in ["timeout", "timed out", "read timed out"]):
        return "TIMEOUT"
    if any(x in m for x in ["selector", "no such element", "stale", "json"]):
        return "구조변경"
    if any(x in m for x in ["403", "404", "500", "connection", "ssl"]):
        return "접근오류"
    return "기타"


def load_recent_searches():
    if not RECENT_FILE.exists():
        return []
    try:
        data = json.loads(RECENT_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_recent_searches(data):
    RECENT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_keywords_csv(text: str):
    return [normalize_text(x) for x in (text or "").split(",") if normalize_text(x)]


def tokenize_query(text: str):
    return [t for t in re.split(r"[\s,/|+]+", normalize_text(text)) if t]


def query_match_score(title: str, query: str) -> int:
    title_norm = normalize_text(title)
    query_norm = normalize_text(query)
    if not query_norm:
        return 1
    if query_norm in title_norm:
        return 3

    tokens = [t for t in tokenize_query(query) if len(t) >= 2]
    if not tokens:
        return 1 if query_norm in title_norm else 0

    hit = sum(1 for t in tokens if t in title_norm)
    if hit == len(tokens):
        return 2
    if hit >= 1:
        return 1
    return 0


PLATFORM_ROW_COLORS = {
    "몽키트래블": "#f8e7a7",
    "와그": "#dbe4ff",
    "하나투어": "#d9efff",
    "인터파크 투어": "#d7f3e3",
    "더블유아이티": "#f7dcec",
    "타이클럽": "#f8dada",
    "마이리얼트립": "#e3dcfb",
}

RELIABILITY_COLORS = {
    "즉시반영": ("", "#166534"),
    "변동가능": ("", "#92400e"),
    "가격확인필요": ("", "#374151"),
}


def style_result_table(df: pd.DataFrame):
    def _platform_style(v):
        bg = PLATFORM_ROW_COLORS.get(v, "")
        return f"background-color: {bg}; color: #111827; font-weight: 800;" if bg else "font-weight: 700;"

    styler = df.style

    if "신뢰도" in df.columns:
        for label, (bg, fg) in RELIABILITY_COLORS.items():
            styler = styler.map(
                lambda v, target=label, bg=bg, fg=fg: f"color: {fg}; font-weight: 800;" if v == target else "",
                subset=["신뢰도"],
            )

    if "상품명" in df.columns:
        styler = styler.map(
            lambda v: "background-color: #f97316; color: #ffffff; font-weight: 900;" if isinstance(v, str) and "최저가" in v else "",
            subset=["상품명"],
        )

    if "플랫폼" in df.columns:
        styler = styler.map(_platform_style, subset=["플랫폼"])

    return styler


def record_recent_search(config: dict):
    recent = load_recent_searches()
    signature = json.dumps(config, ensure_ascii=False, sort_keys=True)
    recent = [item for item in recent if json.dumps(item, ensure_ascii=False, sort_keys=True) != signature]
    recent.insert(0, config)
    save_recent_searches(recent[:10])


def collect_one(name, crawler, keyword):
    t0 = time.perf_counter()
    driver = None
    try:
        driver = get_driver()
        items = crawler(driver, keyword)
        elapsed = round((time.perf_counter() - t0) * 1000)
        if len(items) == 0:
            return {
                "name": name,
                "items": [],
                "log": {
                    "플랫폼": name,
                    "상태": "결과없음",
                    "건수": 0,
                    "실패코드": "-",
                    "메모": "검색 결과 없음",
                    "요청시간(ms)": elapsed,
                    "수집시각": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                },
            }
        return {
            "name": name,
            "items": items,
            "log": {
                "플랫폼": name,
                "상태": "성공",
                "건수": len(items),
                "실패코드": "-",
                "메모": "-",
                "요청시간(ms)": elapsed,
                "수집시각": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        }
    except Exception as e:
        elapsed = round((time.perf_counter() - t0) * 1000)
        return {
            "name": name,
            "items": [],
            "log": {
                "플랫폼": name,
                "상태": "실패",
                "건수": 0,
                "실패코드": failure_code(str(e)),
                "메모": str(e),
                "요청시간(ms)": elapsed,
                "수집시각": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        }
    finally:
        try:
            if driver is not None:
                driver.quit()
        except Exception:
            pass


all_platforms = list(PLATFORM_CRAWLERS.keys())

if "result_df" not in st.session_state:
    st.session_state.result_df = None
if "log_df" not in st.session_state:
    st.session_state.log_df = None
if "last_keyword" not in st.session_state:
    st.session_state.last_keyword = ""
if "search_seq" not in st.session_state:
    st.session_state.search_seq = 0
if "active_recent" not in st.session_state:
    st.session_state.active_recent = None
if "run_recent_cfg" not in st.session_state:
    st.session_state.run_recent_cfg = None
if "search_keyword_input" not in st.session_state:
    st.session_state.search_keyword_input = ""
if "sort_low_toggle" not in st.session_state:
    st.session_state.sort_low_toggle = True
if "platforms_input" not in st.session_state:
    st.session_state.platforms_input = all_platforms if "all_platforms" in locals() else []
if "reliability_input" not in st.session_state:
    st.session_state.reliability_input = ["즉시반영", "변동가능", "가격확인필요"]
if "min_price_input" not in st.session_state:
    st.session_state.min_price_input = 0
if "max_price_input" not in st.session_state:
    st.session_state.max_price_input = 0
if "name_include_input" not in st.session_state:
    st.session_state.name_include_input = ""
if "name_exclude_input" not in st.session_state:
    st.session_state.name_exclude_input = ""

recent_searches = load_recent_searches()

if st.session_state.active_recent:
    cfg = st.session_state.active_recent
    st.session_state.search_keyword_input = cfg.get("keyword", "")
    st.session_state.sort_low_toggle = cfg.get("sort_low", True)
    st.session_state.platforms_input = cfg.get("platforms", all_platforms)
    st.session_state.reliability_input = cfg.get("reliability", ["즉시반영", "변동가능", "가격확인필요"])
    st.session_state.min_price_input = cfg.get("min_price", 0)
    st.session_state.max_price_input = cfg.get("max_price", 0)
    st.session_state.name_include_input = cfg.get("name_include", "")
    st.session_state.name_exclude_input = cfg.get("name_exclude", "")
    st.session_state.active_recent = None

if st.session_state.run_recent_cfg:
    cfg = st.session_state.run_recent_cfg
    st.session_state.search_keyword_input = cfg.get("keyword", "")
    st.session_state.sort_low_toggle = cfg.get("sort_low", True)
    st.session_state.platforms_input = cfg.get("platforms", all_platforms)
    st.session_state.reliability_input = cfg.get("reliability", ["즉시반영", "변동가능", "가격확인필요"])
    st.session_state.min_price_input = cfg.get("min_price", 0)
    st.session_state.max_price_input = cfg.get("max_price", 0)
    st.session_state.name_include_input = cfg.get("name_include", "")
    st.session_state.name_exclude_input = cfg.get("name_exclude", "")

with st.form("search_form", clear_on_submit=False):
    c1, c2, c3, c4 = st.columns([6.2, 1.4, 1.6, 1.2])
    with c1:
        keyword = st.text_input("검색어", key="search_keyword_input")
    with c2:
        sort_low = st.toggle("낮은 가격순", key="sort_low_toggle")
    with c3:
        run = st.form_submit_button("검색 실행", use_container_width=True)
    with c4:
        with st.popover("도움말"):
            st.markdown(
                """
                - `검색어`: 각 플랫폼 사이트에 실제로 전달되는 검색 키워드
                - `상품명 포함(공백무시)`: 수집된 결과에서 상품명 기준으로 한 번 더 필터
                - `상품명 제외(공백무시)`: 제외 키워드가 포함된 상품명 숨김
                - `낮은 가격순`: 결과를 가격 오름차순으로 정렬
                - `신뢰도`: 즉시반영(현재값 바로 반영) / 변동가능(사이트 상황에 따라 바뀔 수 있음) / 가격확인필요
                - `몽키기준비교`: 선택한 몽키트래블 상품 기준으로 저가 비교
                """
            )

with st.expander("필터/플랫폼 설정", expanded=True):
    p1, p2 = st.columns([2.5, 1.5])
    with p1:
        selected_platforms = st.multiselect("포함 플랫폼", options=all_platforms, key="platforms_input")
    with p2:
        reliability_filter = st.multiselect("신뢰도", ["즉시반영", "변동가능", "가격확인필요"], key="reliability_input")

    f1, f2, f3, f4 = st.columns([1.0, 1.0, 1.7, 1.7])
    with f1:
        min_price = st.number_input("최소가격", min_value=0, step=1000, key="min_price_input")
    with f2:
        max_price = st.number_input("최대가격", min_value=0, step=1000, help="0이면 제한 없음", key="max_price_input")
    with f3:
        name_filter = st.text_input("상품명 포함(공백무시)", help="여러 단어는 콤마(,)로 구분하세요. 예: 담넌,수상시장,왕궁", key="name_include_input")
    with f4:
        name_exclude_filter = st.text_input("상품명 제외(공백무시)", help="여러 단어는 콤마(,)로 구분하세요. 예: 공지,보험,호텔", key="name_exclude_input")

if st.session_state.run_recent_cfg:
    cfg = st.session_state.run_recent_cfg
    keyword = cfg.get("keyword", keyword)
    sort_low = cfg.get("sort_low", sort_low)
    selected_platforms = cfg.get("platforms", selected_platforms)
    reliability_filter = cfg.get("reliability", reliability_filter)
    min_price = cfg.get("min_price", min_price)
    max_price = cfg.get("max_price", max_price)
    name_filter = cfg.get("name_include", name_filter)
    name_exclude_filter = cfg.get("name_exclude", name_exclude_filter)
    run = True

if run and keyword and selected_platforms:
    st.session_state.search_seq += 1
    # 새 검색 시작 시 이전 결과/추적값을 먼저 초기화해 화면 잔상을 방지
    st.session_state.result_df = None
    st.session_state.log_df = None
    st.session_state.last_keyword = keyword
    current_config = {
        "keyword": keyword,
        "sort_low": bool(sort_low),
        "platforms": list(selected_platforms),
        "reliability": list(reliability_filter),
        "min_price": int(min_price),
        "max_price": int(max_price),
        "name_include": name_filter,
        "name_exclude": name_exclude_filter,
    }
    record_recent_search(current_config)
    recent_searches = [current_config] + [item for item in recent_searches if item != current_config]
    all_items = []
    logs = []
    st.session_state.run_recent_cfg = None

    with st.status("데이터 수집 중...", expanded=True):
        futures = []
        with ThreadPoolExecutor(max_workers=min(6, len(selected_platforms))) as ex:
            for name in selected_platforms:
                futures.append(ex.submit(collect_one, name, PLATFORM_CRAWLERS[name], keyword))

            for fut in as_completed(futures):
                result = fut.result()
                logs.append(result["log"])
                all_items.extend(result["items"])
                st.write(f"- {result['name']} {result['log']['상태']} ({result['log']['건수']}건)")

    st.session_state.log_df = pd.DataFrame(logs).sort_values(by=["상태", "플랫폼"]).reset_index(drop=True)

    if all_items:
        df = pd.DataFrame([
            {"플랫폼": x.platform, "상품명": x.title, "가격": x.price, "링크": x.link}
            for x in all_items
        ])
        df["가격숫자"] = df["가격"].apply(extract_price_number)
        df["신뢰도"] = df.apply(lambda r: get_reliability_label(r["플랫폼"], r["가격숫자"]), axis=1)
        df["검색점수"] = df["상품명"].apply(lambda x: query_match_score(x, keyword))
        df["지역"] = df["상품명"].str.extract(r"(방콕|파타야|푸켓|치앙마이|태국)", expand=False).fillna("기타")
        st.session_state.result_df = df
    else:
        st.session_state.result_df = None

if st.session_state.result_df is None:
    if st.session_state.log_df is not None:
        st.warning("검색 결과가 없습니다. 수집로그 탭에서 실패 사유를 확인해 주세요.")
else:
    raw_df = st.session_state.result_df.copy()
    search_seq = st.session_state.search_seq

    if min_price > 0:
        raw_df = raw_df[(raw_df["가격숫자"].notna()) & (raw_df["가격숫자"] >= min_price)]
    if max_price > 0:
        raw_df = raw_df[(raw_df["가격숫자"].notna()) & (raw_df["가격숫자"] <= max_price)]
    if reliability_filter:
        raw_df = raw_df[raw_df["신뢰도"].isin(reliability_filter)]
    # 2점 이상은 본표시, 1점은 잡음 가능성이 있어 기본적으로 제외
    raw_df = raw_df[raw_df["검색점수"] >= 2]
    include_keys = parse_keywords_csv(name_filter)
    if include_keys:
        raw_df = raw_df[
            raw_df["상품명"].apply(
                lambda x: any(k in normalize_text(x) for k in include_keys)
            )
        ]
    exclude_keys = parse_keywords_csv(name_exclude_filter)
    if exclude_keys:
        raw_df = raw_df[
            raw_df["상품명"].apply(
                lambda x: all(k not in normalize_text(x) for k in exclude_keys)
            )
        ]

    if sort_low:
        raw_df = raw_df.sort_values(by=["검색점수", "가격숫자"], ascending=[False, True], na_position="last")
    else:
        raw_df = raw_df.sort_values(by=["검색점수", "가격숫자"], ascending=[False, True], na_position="last")

    cheapest_num = raw_df["가격숫자"].dropna().min() if raw_df["가격숫자"].notna().any() else None

    monkey_df = raw_df[(raw_df["플랫폼"] == "몽키트래블") & (raw_df["가격숫자"].notna())].copy()
    monkey_base_price_num = None
    monkey_base_title = None

    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("최저가", f"{int(cheapest_num):,}원" if cheapest_num is not None else "-")
    s2.metric("비교 가능 건수", f"{len(raw_df)}")
    s3.metric("플랫폼", f"{raw_df['플랫폼'].nunique()}")
    s4.metric("즉시반영", f"{len(raw_df[raw_df['신뢰도']=='즉시반영'])}")
    s5.metric("기준 플랫폼", "몽키트래블")

    tabs = st.tabs(["전체비교", "몽키기준비교", "플랫폼별", "수집로그"])

    with tabs[0]:
        show_df = raw_df.copy()
        if cheapest_num is not None:
            show_df["상품명"] = show_df.apply(
                lambda r: f"🏆 최저가 | {r['상품명']}" if r["가격숫자"] == cheapest_num else r["상품명"],
                axis=1,
            )

        watch_price_overall = st.number_input(
            "추적 기준가(이하)",
            min_value=0,
            value=0,
            step=1000,
            key=f"overall_watch_price_{search_seq}",
        )
        if watch_price_overall > 0:
            show_df = show_df[(show_df["가격숫자"].notna()) & (show_df["가격숫자"] <= watch_price_overall)].copy()

        table_df = show_df[["플랫폼", "상품명", "가격", "신뢰도", "링크"]].copy()
        st.dataframe(
            style_result_table(table_df),
            use_container_width=True,
            hide_index=True,
            column_config={"링크": st.column_config.LinkColumn("링크", display_text="바로가기")},
        )

    with tabs[1]:
        if monkey_df.empty:
            st.info("몽키트래블 가격 데이터가 없어 기준 비교를 표시할 수 없습니다.")
        else:
            monkey_df = monkey_df.sort_values(by=["가격숫자"]).reset_index(drop=True)
            monkey_df["라벨"] = monkey_df.apply(lambda r: f"{r['상품명']} ({r['가격']})", axis=1)
            selected_monkey = st.selectbox(
                "기준 몽키 상품",
                options=monkey_df["라벨"].tolist(),
                index=0,
                key=f"monkey_select_{search_seq}",
            )
            base_row = monkey_df[monkey_df["라벨"] == selected_monkey].iloc[0]
            monkey_base_price_num = float(base_row["가격숫자"])
            monkey_base_title = base_row["상품명"]

            st.caption(f"기준 상품: {monkey_base_title} / {base_row['가격']}")
            st.link_button("기준 몽키 상품 바로가기", base_row["링크"], use_container_width=False)

            cheaper = raw_df[
                (raw_df["플랫폼"] != "몽키트래블")
                & (raw_df["가격숫자"].notna())
                & (raw_df["가격숫자"] < monkey_base_price_num)
            ].copy()

            if cheaper.empty:
                st.info("기준가보다 저렴한 상품이 없습니다.")
            else:
                cheaper["비교기준"] = monkey_base_title
                cheaper["기준가"] = f"{int(monkey_base_price_num):,}원"
                cheaper["차이"] = cheaper["가격숫자"].apply(lambda x: f"-{math.ceil(monkey_base_price_num - float(x)):,}원")
                cheaper = cheaper.sort_values(by=["가격숫자"])
                st.dataframe(
                    style_result_table(cheaper[["플랫폼", "상품명", "가격", "기준가", "차이", "비교기준", "링크"]]),
                    use_container_width=True,
                    hide_index=True,
                    column_config={"링크": st.column_config.LinkColumn("링크", display_text="바로가기")},
                )

            watch_price = st.number_input(
                "추적 기준가(이하)",
                min_value=0,
                value=int(monkey_base_price_num),
                step=1000,
                key=f"monkey_watch_{search_seq}",
            )
            tracked = raw_df[(raw_df["가격숫자"].notna()) & (raw_df["가격숫자"] <= watch_price)].copy()
            if tracked.empty:
                st.info("설정 기준 이하 상품이 없습니다.")
            else:
                tracked["변화"] = tracked["가격숫자"].apply(lambda x: f"-{math.ceil(float(watch_price) - float(x)):,}원")
                tracked["새로 내려감"] = tracked["가격숫자"].apply(lambda x: "NEW" if x < watch_price else "")
                tracked = tracked.sort_values(by=["가격숫자"])
                st.dataframe(
                    style_result_table(tracked[["플랫폼", "상품명", "가격", "변화", "새로 내려감", "링크"]]),
                    use_container_width=True,
                    hide_index=True,
                    column_config={"링크": st.column_config.LinkColumn("링크", display_text="바로가기")},
                )

            st.markdown("---")
            with st.expander("최근 검색 기록", expanded=False):
                if not recent_searches:
                    st.info("최근 검색 기록이 없습니다. 검색을 한 번 실행하면 여기에 쌓입니다.")
                else:
                    for idx, item in enumerate(recent_searches[:10], start=1):
                        label = (
                            f"{idx}. {item.get('keyword', '')}"
                            f" | 플랫폼 {len(item.get('platforms', []))}개"
                            f" | 추적가 {item.get('max_price', 0) or 0:,}원 이하"
                        )
                        left, right = st.columns([5, 1.2])
                        with left:
                            st.caption(label)
                        with right:
                            if st.button("불러오기", key=f"recent_load_{idx}_{search_seq}", use_container_width=True):
                                st.session_state.run_recent_cfg = item
                                st.rerun()

    with tabs[2]:
        p1, p2 = st.columns([2, 2])
        with p1:
            pf_selected = st.multiselect(
                "플랫폼 선택",
                options=sorted(raw_df["플랫폼"].unique()),
                default=sorted(raw_df["플랫폼"].unique()),
                key=f"platform_select_{search_seq}",
            )
        with p2:
            pf_sort = st.selectbox("정렬", ["낮은 가격순", "높은 가격순", "이름순"], index=0, key=f"platform_sort_{search_seq}")

        pf_df = raw_df[raw_df["플랫폼"].isin(pf_selected)].copy() if pf_selected else pd.DataFrame(columns=raw_df.columns)
        if pf_sort == "낮은 가격순":
            pf_df = pf_df.sort_values(by=["가격숫자"], na_position="last")
        elif pf_sort == "높은 가격순":
            pf_df = pf_df.sort_values(by=["가격숫자"], ascending=False, na_position="last")
        else:
            pf_df = pf_df.sort_values(by=["상품명"])

        st.dataframe(
            style_result_table(pf_df[["플랫폼", "상품명", "가격", "신뢰도", "지역", "링크"]]),
            use_container_width=True,
            hide_index=True,
            column_config={"링크": st.column_config.LinkColumn("링크", display_text="바로가기")},
        )

    with tabs[3]:
        log_df = st.session_state.log_df if st.session_state.log_df is not None else pd.DataFrame(columns=["플랫폼", "상태", "건수", "실패코드", "메모", "요청시간(ms)", "수집시각"])
        st.dataframe(log_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    e1, e2 = st.columns(2)
    with e1:
        csv_bytes = raw_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("CSV 다운로드", data=csv_bytes, file_name="price_compare.csv", mime="text/csv", use_container_width=True)
    with e2:
        raw_df.to_excel(EXPORT_FILE, index=False)
        st.download_button("엑셀 다운로드", data=EXPORT_FILE.read_bytes(), file_name="price_compare.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
