"""
ClassFit Streamlit App v3.2
강의실 예약·추천 시스템

v3 수정 사항
- 불필요 페이지 제거: 알고리즘 설명 페이지, 강의실 상세 분석 페이지 삭제
- 예약/현황/추천 조회는 캐시 없이 DB에서 즉시 조회
- 추천 결과를 세션에 고정하지 않고 매번 DB 기준으로 재계산
- 예약 성공/취소 후 즉시 rerun하여 모든 화면에 반영
- 예약하기 화면을 추천 예약/직접 예약/반복 예약 탭으로 통합
- UI/UX 개선: 카드형 대시보드, 명확한 상태 배지, 한 화면 예약 플로우
- v3.1: 라이트 테마 고정, 배경색/글씨색 대비 보정, 입력창/사이드바 색상 정리
- v3.2: 사이드바에서 다크/라이트 모드 선택 가능, 테마 CSS 변수화
"""

from __future__ import annotations

import heapq
import sqlite3
from datetime import date as DateType, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import database as db

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "classfit.db"
PERIODS = list(range(1, 13))
END_PERIODS = list(range(2, 14))
KOREAN_DAYS = ["월", "화", "수", "목", "금", "토", "일"]
DAY_ORDER = {day: idx for idx, day in enumerate(KOREAN_DAYS)}
STATUS_ORDER = ["가능", "수업", "예약"]

st.set_page_config(
    page_title="ClassFit | 강의실 예약 시스템",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded",
)

def apply_theme_css(theme_choice: str) -> None:
    """사이드바에서 선택한 화면 테마를 앱 전체에 적용한다."""
    palettes = {
        "라이트 모드": {
            "cf-bg": "#F8FAFC",
            "cf-panel": "#FFFFFF",
            "cf-panel-soft": "#F1F5F9",
            "cf-sidebar": "#FFFFFF",
            "cf-border": "#E2E8F0",
            "cf-text": "#0F172A",
            "cf-muted": "#475569",
            "cf-muted-2": "#64748B",
            "cf-primary": "#2563EB",
            "cf-primary-soft": "#EFF6FF",
            "cf-hero-bg": "linear-gradient(135deg, #DBEAFE 0%, #FFFFFF 58%, #E0F2FE 100%)",
            "cf-input-bg": "#FFFFFF",
            "cf-input-border": "#CBD5E1",
            "cf-shadow": "0 6px 18px rgba(15, 23, 42, 0.05)",
            "cf-success-bg": "#F0FDF4",
            "cf-success-text": "#166534",
            "cf-success-border": "#BBF7D0",
            "cf-info-bg": "#EFF6FF",
            "cf-info-text": "#1D4ED8",
            "cf-info-border": "#BFDBFE",
            "cf-danger-bg": "#FEF2F2",
            "cf-danger-text": "#991B1B",
            "cf-danger-border": "#FECACA",
        },
        "다크 모드": {
            "cf-bg": "#020617",
            "cf-panel": "#0F172A",
            "cf-panel-soft": "#111827",
            "cf-sidebar": "#0B1120",
            "cf-border": "#334155",
            "cf-text": "#E5E7EB",
            "cf-muted": "#CBD5E1",
            "cf-muted-2": "#94A3B8",
            "cf-primary": "#60A5FA",
            "cf-primary-soft": "#172554",
            "cf-hero-bg": "linear-gradient(135deg, #172554 0%, #0F172A 56%, #082F49 100%)",
            "cf-input-bg": "#111827",
            "cf-input-border": "#475569",
            "cf-shadow": "0 10px 24px rgba(0, 0, 0, 0.28)",
            "cf-success-bg": "#052E16",
            "cf-success-text": "#BBF7D0",
            "cf-success-border": "#166534",
            "cf-info-bg": "#0C4A6E",
            "cf-info-text": "#BAE6FD",
            "cf-info-border": "#0284C7",
            "cf-danger-bg": "#450A0A",
            "cf-danger-text": "#FECACA",
            "cf-danger-border": "#991B1B",
        },
    }

    palette = palettes.get(theme_choice, palettes["다크 모드"])
    css_vars = "\n".join(f"        --{name}: {value};" for name, value in palette.items())

    css = """
    <style>
    :root {
""" + css_vars + """
    }

    html, body, [data-testid="stAppViewContainer"], .stApp {
        background: var(--cf-bg) !important;
        color: var(--cf-text) !important;
    }

    .main .block-container {
        padding-top: 1.2rem;
        padding-bottom: 3rem;
        max-width: 1400px;
    }

    h1, h2, h3, h4, h5, h6,
    p, span, label, div,
    [data-testid="stMarkdownContainer"],
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li {
        color: var(--cf-text) !important;
    }

    .stCaptionContainer, .stCaptionContainer p,
    small, .caption, [data-testid="stCaptionContainer"] {
        color: var(--cf-muted-2) !important;
    }

    [data-testid="stSidebar"] {
        background: var(--cf-sidebar) !important;
        border-right: 1px solid var(--cf-border);
    }
    [data-testid="stSidebar"] * {
        color: var(--cf-text) !important;
    }

    .hero {
        padding: 1.25rem 1.35rem;
        border-radius: 1.1rem;
        background: var(--cf-hero-bg);
        border: 1px solid var(--cf-border);
        margin-bottom: 1rem;
        box-shadow: var(--cf-shadow);
    }
    .hero h1 {
        font-size: 2rem;
        margin: 0 0 .35rem 0;
        color: var(--cf-text) !important;
    }
    .hero p {
        margin: 0;
        color: var(--cf-muted) !important;
    }

    .metric-card {
        padding: 1rem;
        border-radius: 1rem;
        border: 1px solid var(--cf-border);
        background: var(--cf-panel);
        box-shadow: var(--cf-shadow);
    }
    .metric-label {
        font-size: .86rem;
        color: var(--cf-muted-2) !important;
        margin-bottom: .25rem;
    }
    .metric-value {
        font-size: 1.55rem;
        font-weight: 800;
        color: var(--cf-text) !important;
    }

    .status-legend {
        display: flex;
        gap: .5rem;
        flex-wrap: wrap;
        margin: .5rem 0 1rem 0;
    }
    .badge {
        padding: .28rem .6rem;
        border-radius: 999px;
        font-size: .85rem;
        font-weight: 700;
        border: 1px solid var(--cf-border);
    }
    .ok {
        background: var(--cf-success-bg);
        color: var(--cf-success-text) !important;
        border-color: var(--cf-success-border);
    }
    .blocked {
        background: var(--cf-info-bg);
        color: var(--cf-info-text) !important;
        border-color: var(--cf-info-border);
    }
    .reserved {
        background: var(--cf-danger-bg);
        color: var(--cf-danger-text) !important;
        border-color: var(--cf-danger-border);
    }

    .muted-box {
        padding: .85rem 1rem;
        border-radius: .9rem;
        background: var(--cf-panel-soft);
        border: 1px solid var(--cf-border);
        color: var(--cf-text) !important;
    }
    .muted-box b { color: var(--cf-text) !important; }

    .danger-box {
        padding: .85rem 1rem;
        border-radius: .9rem;
        background: var(--cf-danger-bg);
        border: 1px solid var(--cf-danger-border);
        color: var(--cf-danger-text) !important;
        font-weight: 700;
    }
    .success-box {
        padding: .85rem 1rem;
        border-radius: .9rem;
        background: var(--cf-success-bg);
        border: 1px solid var(--cf-success-border);
        color: var(--cf-success-text) !important;
        font-weight: 700;
    }

    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div,
    div[data-baseweb="textarea"] > div,
    [data-testid="stDateInput"] input,
    [data-testid="stNumberInput"] input,
    textarea, input {
        background-color: var(--cf-input-bg) !important;
        color: var(--cf-text) !important;
        border-color: var(--cf-input-border) !important;
    }
    div[data-baseweb="select"] span,
    div[data-baseweb="input"] input,
    div[data-baseweb="textarea"] textarea {
        color: var(--cf-text) !important;
    }
    div[data-baseweb="popover"],
    div[data-baseweb="popover"] * {
        background-color: var(--cf-panel) !important;
        color: var(--cf-text) !important;
    }
    [role="option"]:hover {
        background-color: var(--cf-panel-soft) !important;
    }

    .stButton > button,
    .stDownloadButton > button,
    [data-testid="stFormSubmitButton"] button {
        border-radius: .65rem !important;
        font-weight: 700 !important;
    }

    div[data-testid="stDataFrame"] {
        border-radius: .8rem;
        overflow: hidden;
        background: var(--cf-panel) !important;
        border: 1px solid var(--cf-border);
    }

    button[data-baseweb="tab"] {
        color: var(--cf-muted) !important;
        font-weight: 700;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: var(--cf-primary) !important;
    }

    hr {
        border-color: var(--cf-border) !important;
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 공통 DB 조회: 실시간 반영을 위해 cache_data를 사용하지 않는다.
# -----------------------------------------------------------------------------
def query_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def ensure_database_ready() -> None:
    try:
        db.ensure_seed_data()
    except Exception as exc:
        st.error(f"DB 준비 중 오류가 발생했습니다: {exc}")
        st.stop()


def get_rooms_df() -> pd.DataFrame:
    return query_df(
        """
        SELECT room_id, building, floor, room_number, room_name, capacity,
               capacity_avg, room_type, location_score, accessibility_score,
               priority, equipment, source_course_count
        FROM rooms
        ORDER BY building, floor, room_number
        """
    )


def get_reservations_df() -> pd.DataFrame:
    return query_df(
        """
        SELECT reservation_id, room_id, date, day, start_period, end_period,
               user_name, purpose, created_at
        FROM reservations
        ORDER BY date DESC, start_period ASC, reservation_id DESC
        """
    )


def get_blocked_df() -> pd.DataFrame:
    return query_df(
        """
        SELECT blocked_id, course_id, room_id, day, period, capacity, source_row
        FROM blocked_schedules
        ORDER BY room_id, day, period
        """
    )


def weekday_from_date(selected_date: DateType) -> str:
    return KOREAN_DAYS[selected_date.weekday()]


def period_range_text(start: int, end: int) -> str:
    return f"{start}~{end}교시"


def validate_period(start_period: int, end_period: int) -> tuple[bool, str]:
    if start_period < 1 or end_period > 13:
        return False, "교시는 1교시부터 12교시까지만 사용할 수 있습니다."
    if start_period >= end_period:
        return False, "종료 교시는 시작 교시보다 커야 합니다. 예: 5~7은 5, 6교시 사용입니다."
    return True, "OK"


def rerun_with_flash(kind: str, message: str) -> None:
    st.session_state["flash"] = {"kind": kind, "message": message}
    st.rerun()


def show_flash() -> None:
    flash = st.session_state.pop("flash", None)
    if not flash:
        return
    if flash["kind"] == "success":
        st.success(flash["message"])
    elif flash["kind"] == "warning":
        st.warning(flash["message"])
    else:
        st.error(flash["message"])


def status_label(value: str) -> str:
    if value == "가능":
        return "🟢 가능"
    if value == "수업":
        return "🔵 수업"
    if value == "예약":
        return "🔴 예약"
    return str(value)


def render_metric_card(label: str, value: str) -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_legend() -> None:
    st.markdown(
        """
        <div class="status-legend">
            <span class="badge ok">🟢 가능</span>
            <span class="badge blocked">🔵 기존 수업</span>
            <span class="badge reserved">🔴 실시간 예약</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# 추천 및 현황 계산
# -----------------------------------------------------------------------------
def capacity_fit_score(capacity: int, required: int) -> int:
    waste = capacity - required
    if waste < 0:
        return -999
    if waste <= 5:
        return 35
    if waste <= 15:
        return 30
    if waste <= 30:
        return 22
    if waste <= 50:
        return 14
    return 7


def available_rooms_df(selected_date: DateType, start_period: int, end_period: int, min_capacity: int) -> pd.DataFrame:
    rows = db.get_available_rooms(selected_date.isoformat(), start_period, end_period, min_capacity)
    columns = [
        "room_id", "building", "floor", "room_name", "capacity", "room_type",
        "location_score", "accessibility_score", "priority",
    ]
    return pd.DataFrame(rows, columns=columns)


def compute_room_score(row: pd.Series, min_capacity: int, preferred_building: str | None,
                       preferred_floor: int | None, preferred_room_type: str | None) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    cap_score = capacity_fit_score(int(row["capacity"]), min_capacity)
    score += cap_score
    reasons.append(f"정원 적합 +{cap_score}")

    if preferred_building and preferred_building != "상관없음":
        if row["building"] == preferred_building:
            score += 18
            reasons.append("건물 일치 +18")
        else:
            reasons.append("건물 불일치 +0")

    if preferred_floor is not None:
        floor_gap = abs(int(row["floor"]) - int(preferred_floor))
        floor_score = max(0, 12 - floor_gap * 3)
        score += floor_score
        reasons.append(f"층 거리 {floor_gap} / +{floor_score}")

    if preferred_room_type and preferred_room_type != "상관없음":
        if row["room_type"] == preferred_room_type:
            score += 12
            reasons.append("유형 일치 +12")
        else:
            reasons.append("유형 불일치 +0")

    base_score = int(row["location_score"]) + int(row["accessibility_score"]) + int(row["priority"])
    score += base_score
    reasons.append(f"기본 선호도 +{base_score}")
    return int(score), reasons


def build_recommendations(selected_date: DateType, start_period: int, end_period: int, min_capacity: int,
                          preferred_building: str | None, preferred_floor: int | None,
                          preferred_room_type: str | None, top_n: int = 10) -> pd.DataFrame:
    candidates = available_rooms_df(selected_date, start_period, end_period, min_capacity)
    if candidates.empty:
        return candidates

    heap: list[tuple[int, int, str, dict]] = []
    for _, row in candidates.iterrows():
        score, reasons = compute_room_score(row, min_capacity, preferred_building, preferred_floor, preferred_room_type)
        item = row.to_dict()
        item["score"] = score
        item["capacity_waste"] = int(row["capacity"]) - int(min_capacity)
        item["reason"] = " / ".join(reasons)
        heapq.heappush(heap, (-score, item["capacity_waste"], str(row["room_id"]), item))

    rows = [heapq.heappop(heap)[3] for _ in range(min(top_n, len(heap)))]
    return pd.DataFrame(rows).reset_index(drop=True)


def build_daily_matrix(selected_date: DateType, room_ids: list[str]) -> pd.DataFrame:
    day = weekday_from_date(selected_date)
    date_text = selected_date.isoformat()
    blocked = query_df("SELECT room_id, period FROM blocked_schedules WHERE day = ?", (day,))
    reservations = query_df(
        """
        SELECT room_id, reservation_id, start_period, end_period
        FROM reservations
        WHERE date = ?
        """,
        (date_text,),
    )

    rows = []
    for room_id in room_ids:
        row = {"강의실": room_id}
        for period in PERIODS:
            cell = "가능"
            if not blocked[(blocked["room_id"] == room_id) & (blocked["period"] == period)].empty:
                cell = "수업"
            if not reservations[
                (reservations["room_id"] == room_id)
                & (reservations["start_period"] <= period)
                & (period < reservations["end_period"])
            ].empty:
                cell = "예약"
            row[f"{period}교시"] = status_label(cell)
        rows.append(row)
    return pd.DataFrame(rows)


def get_room_day_timetable(room_id: str, selected_date: DateType) -> pd.DataFrame:
    day = weekday_from_date(selected_date)
    date_text = selected_date.isoformat()
    blocked = query_df(
        "SELECT period, course_id FROM blocked_schedules WHERE room_id = ? AND day = ? ORDER BY period",
        (room_id, day),
    )
    reservations = query_df(
        """
        SELECT reservation_id, start_period, end_period, user_name, purpose
        FROM reservations
        WHERE room_id = ? AND date = ?
        ORDER BY start_period
        """,
        (room_id, date_text),
    )
    rows = []
    for period in PERIODS:
        status = "가능"
        detail = "-"
        matched_block = blocked[blocked["period"] == period]
        if not matched_block.empty:
            status = "수업"
            detail = f"기존 수업 {matched_block.iloc[0]['course_id']}"
        matched_reservation = reservations[
            (reservations["start_period"] <= period) & (period < reservations["end_period"])
        ]
        if not matched_reservation.empty:
            r = matched_reservation.iloc[0]
            status = "예약"
            detail = f"예약 #{int(r['reservation_id'])} / {r['user_name']} / {r['purpose']}"
        rows.append({"교시": period, "상태": status_label(status), "상세": detail})
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# 앱 시작
# -----------------------------------------------------------------------------
ensure_database_ready()
show_flash()

rooms_df = get_rooms_df()
blocked_df = get_blocked_df()
reservations_df = get_reservations_df()
room_options = rooms_df["room_id"].tolist()

st.sidebar.title("🏫 ClassFit")
st.sidebar.caption("DB 연동형 강의실 예약 시스템")
theme_choice = st.sidebar.selectbox(
    "화면 테마",
    ["다크 모드", "라이트 모드"],
    index=0,
    key="theme_choice",
    help="다크/라이트 모드를 즉시 전환합니다. DB 데이터에는 영향을 주지 않습니다.",
)
apply_theme_css(theme_choice)
page = st.sidebar.radio(
    "메뉴",
    ["대시보드", "예약하기", "실시간 현황판", "빈 강의실 찾기", "예약 관리", "데이터 관리"],
)

if st.sidebar.button("🔄 DB 새로고침", use_container_width=True):
    st.rerun()

now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
st.sidebar.caption(f"조회 시각: {now_text}")

with st.sidebar.expander("DB 초기화", expanded=False):
    st.caption("CSV 원본 기준으로 DB를 다시 만들고, 실시간 예약은 모두 삭제합니다.")
    confirm_reset = st.checkbox("초기화 동의")
    if st.button("초기 데이터로 리셋", disabled=not confirm_reset, use_container_width=True):
        try:
            db.reset_db_from_csv()
            for key in ["search_condition", "booking_user", "booking_purpose"]:
                st.session_state.pop(key, None)
            rerun_with_flash("success", "DB를 CSV 원본 기준으로 초기화했습니다.")
        except Exception as exc:
            st.error(f"초기화 실패: {exc}")


# -----------------------------------------------------------------------------
# 대시보드
# -----------------------------------------------------------------------------
if page == "대시보드":
    st.markdown(
        """
        <div class="hero">
            <h1>ClassFit 강의실 예약 시스템</h1>
            <p>기존 수업 시간표와 실시간 예약 DB를 동시에 검사해서, 실제로 사용 가능한 강의실만 추천합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_metric_card("강의실", f"{len(rooms_df):,}개")
    with c2:
        render_metric_card("기존 수업 차단", f"{len(blocked_df):,}개")
    with c3:
        render_metric_card("실시간 예약", f"{len(reservations_df):,}건")
    with c4:
        avg_capacity = rooms_df["capacity"].mean() if not rooms_df.empty else 0
        render_metric_card("평균 수용 인원", f"{avg_capacity:.1f}명")

    st.divider()
    left, right = st.columns([1.15, 0.85])
    with left:
        st.subheader("오늘 강의실 현황")
        dashboard_date = st.date_input("현황 날짜", value=DateType.today())
        render_legend()
        preview_rooms = rooms_df.sort_values(["floor", "room_id"])["room_id"].head(15).tolist()
        matrix = build_daily_matrix(dashboard_date, preview_rooms)
        st.dataframe(matrix, use_container_width=True, hide_index=True)
        st.caption("대시보드는 상위 15개 강의실만 미리 보여준다. 전체는 실시간 현황판에서 확인한다.")

    with right:
        st.subheader("최근 예약")
        if reservations_df.empty:
            st.info("아직 실시간 예약이 없습니다.")
        else:
            recent = reservations_df.head(8).copy()
            recent["시간"] = recent.apply(lambda r: period_range_text(int(r["start_period"]), int(r["end_period"])), axis=1)
            st.dataframe(
                recent[["reservation_id", "room_id", "date", "day", "시간", "user_name", "purpose"]],
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("강의실 유형")
        type_count = rooms_df.groupby("room_type", as_index=False)["room_id"].count().rename(columns={"room_id": "개수"})
        st.bar_chart(type_count.set_index("room_type"))


# -----------------------------------------------------------------------------
# 예약하기: 추천 예약 / 직접 예약 / 반복 예약
# -----------------------------------------------------------------------------
elif page == "예약하기":
    st.title("예약하기")
    st.caption("추천으로 예약하거나, 강의실을 직접 선택해서 예약할 수 있습니다. 모든 예약은 DB에 즉시 저장됩니다.")

    tab_reco, tab_direct, tab_recurring = st.tabs(["추천으로 예약", "강의실 직접 선택", "반복 예약"])

    with tab_reco:
        st.subheader("1단계. 예약 조건 입력")
        with st.form("recommend_search_form"):
            a, b, c = st.columns(3)
            selected_date = a.date_input("예약 날짜", value=DateType.today(), key="rec_date")
            start_period = b.selectbox("시작 교시", PERIODS, index=0, key="rec_start")
            end_period = c.selectbox("종료 교시", END_PERIODS, index=1, key="rec_end", help="종료 교시는 포함하지 않습니다. 예: 5~7 = 5, 6교시")

            d, e, f, g = st.columns(4)
            min_capacity = d.number_input("필요 인원", min_value=1, max_value=300, value=30, step=1, key="rec_capacity")
            building_options = ["상관없음"] + sorted(rooms_df["building"].dropna().unique().tolist())
            preferred_building = e.selectbox("선호 건물", building_options, key="rec_building")
            floor_options = ["상관없음"] + sorted(rooms_df["floor"].dropna().astype(int).unique().tolist())
            preferred_floor_raw = f.selectbox("선호 층", floor_options, key="rec_floor")
            type_options = ["상관없음"] + sorted(rooms_df["room_type"].dropna().unique().tolist())
            preferred_room_type = g.selectbox("강의실 유형", type_options, key="rec_type")

            submitted = st.form_submit_button("사용 가능한 강의실 추천", use_container_width=True)

        if submitted:
            valid, msg = validate_period(int(start_period), int(end_period))
            if not valid:
                st.error(msg)
                st.session_state.pop("search_condition", None)
            else:
                st.session_state["search_condition"] = {
                    "date": selected_date.isoformat(),
                    "start_period": int(start_period),
                    "end_period": int(end_period),
                    "min_capacity": int(min_capacity),
                    "preferred_building": preferred_building,
                    "preferred_floor": None if preferred_floor_raw == "상관없음" else int(preferred_floor_raw),
                    "preferred_room_type": preferred_room_type,
                }

        condition = st.session_state.get("search_condition")
        if condition:
            st.divider()
            st.subheader("2단계. 추천 결과 확인")
            search_date = DateType.fromisoformat(condition["date"])
            result = build_recommendations(
                search_date,
                condition["start_period"],
                condition["end_period"],
                condition["min_capacity"],
                condition["preferred_building"],
                condition["preferred_floor"],
                condition["preferred_room_type"],
                top_n=10,
            )
            title = f"{condition['date']} ({weekday_from_date(search_date)}) {period_range_text(condition['start_period'], condition['end_period'])} / {condition['min_capacity']}명 이상"
            st.markdown(f"**조회 조건:** {title}")

            if result.empty:
                st.error("현재 DB 기준으로 조건을 만족하는 강의실이 없습니다.")
                st.info("인원 조건을 낮추거나 시간대를 바꿔서 다시 조회하세요.")
            else:
                display = result[["room_id", "room_name", "capacity", "capacity_waste", "room_type", "floor", "score", "reason"]].copy()
                display = display.rename(
                    columns={
                        "room_id": "강의실ID",
                        "room_name": "강의실명",
                        "capacity": "정원",
                        "capacity_waste": "남는 좌석",
                        "room_type": "유형",
                        "floor": "층",
                        "score": "추천점수",
                        "reason": "추천근거",
                    }
                )
                st.dataframe(display, use_container_width=True, hide_index=True)

                st.subheader("3단계. 예약 확정")
                with st.form("recommend_book_form"):
                    room_id = st.selectbox("예약할 강의실", result["room_id"].tolist())
                    selected_row = result[result["room_id"] == room_id].iloc[0]
                    st.markdown(
                        f"""
                        <div class="muted-box">
                        선택 강의실: <b>{selected_row['room_name']}</b> / 정원 {int(selected_row['capacity'])}명 / 추천점수 {int(selected_row['score'])}점
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    u1, u2 = st.columns(2)
                    user_name = u1.text_input("예약자명", key="booking_user", placeholder="예: 홍길동")
                    purpose = u2.text_input("사용 목적", key="booking_purpose", placeholder="예: 팀 프로젝트 회의")
                    confirm = st.form_submit_button("선택 강의실 예약 확정", type="primary", use_container_width=True)

                if confirm:
                    ok, message = db.add_reservation(
                        room_id=room_id,
                        date=condition["date"],
                        start_period=condition["start_period"],
                        end_period=condition["end_period"],
                        user_name=user_name,
                        purpose=purpose,
                    )
                    if ok:
                        st.session_state.pop("search_condition", None)
                        rerun_with_flash("success", message)
                    else:
                        st.error(message)
                        st.warning(db.get_conflict_details(room_id, condition["date"], condition["start_period"], condition["end_period"])["message"])

    with tab_direct:
        st.subheader("강의실 직접 선택 예약")
        with st.form("direct_reservation_form"):
            a, b = st.columns(2)
            room_id = a.selectbox("강의실", room_options, key="direct_room")
            selected_date = b.date_input("예약 날짜", value=DateType.today(), key="direct_date")
            c, d = st.columns(2)
            start_period = c.selectbox("시작 교시", PERIODS, index=0, key="direct_start")
            end_period = d.selectbox("종료 교시", END_PERIODS, index=1, key="direct_end")
            e, f = st.columns(2)
            user_name = e.text_input("예약자명", key="direct_user", placeholder="예: 홍길동")
            purpose = f.text_input("사용 목적", key="direct_purpose", placeholder="예: 발표 연습")
            submit = st.form_submit_button("예약 신청", type="primary", use_container_width=True)

        col_left, col_right = st.columns([0.9, 1.1])
        with col_left:
            st.markdown("#### 선택 강의실 당일 시간표")
            st.dataframe(get_room_day_timetable(room_id, selected_date), use_container_width=True, hide_index=True)
        with col_right:
            st.markdown("#### 예약 가능 여부 미리보기")
            valid, msg = validate_period(int(start_period), int(end_period))
            if not valid:
                st.error(msg)
            else:
                detail = db.get_conflict_details(room_id, selected_date.isoformat(), int(start_period), int(end_period))
                if detail["ok"]:
                    st.markdown(f"<div class='success-box'>{detail['message']}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='danger-box'>{detail['message']}</div>", unsafe_allow_html=True)
                    duration = int(end_period) - int(start_period)
                    alternatives = db.recommend_alternative_slots(room_id, selected_date.isoformat(), duration, limit=5)
                    if alternatives:
                        alt_df = pd.DataFrame(alternatives, columns=["room_id", "date", "start_period", "end_period"])
                        alt_df["가능 시간"] = alt_df.apply(lambda r: period_range_text(int(r["start_period"]), int(r["end_period"])), axis=1)
                        st.caption("같은 강의실의 대체 시간")
                        st.dataframe(alt_df[["room_id", "date", "가능 시간"]], use_container_width=True, hide_index=True)

        if submit:
            valid, msg = validate_period(int(start_period), int(end_period))
            if not valid:
                st.error(msg)
            else:
                ok, message = db.add_reservation(
                    room_id=room_id,
                    date=selected_date.isoformat(),
                    start_period=int(start_period),
                    end_period=int(end_period),
                    user_name=user_name,
                    purpose=purpose,
                )
                if ok:
                    rerun_with_flash("success", message)
                else:
                    st.error(message)

    with tab_recurring:
        st.subheader("반복 예약")
        st.caption("정기 스터디/회의처럼 날짜 범위 안에서 특정 요일만 일괄 예약합니다.")
        with st.form("recurring_reservation_form"):
            a, b, c = st.columns(3)
            room_id = a.selectbox("강의실", room_options, key="repeat_room")
            start_date = b.date_input("시작일", value=DateType.today(), key="repeat_start_date")
            end_date = c.date_input("종료일", value=DateType.today(), key="repeat_end_date")
            d, e, f = st.columns(3)
            selected_days = d.multiselect("반복 요일", KOREAN_DAYS[:5], default=[weekday_from_date(start_date)], key="repeat_days")
            start_period = e.selectbox("시작 교시", PERIODS, index=0, key="repeat_start")
            end_period = f.selectbox("종료 교시", END_PERIODS, index=1, key="repeat_end")
            g, h = st.columns(2)
            user_name = g.text_input("예약자명", key="repeat_user", placeholder="예: 홍길동")
            purpose = h.text_input("사용 목적", key="repeat_purpose", placeholder="예: 정기 스터디")
            submit = st.form_submit_button("반복 예약 실행", type="primary", use_container_width=True)

        if submit:
            valid, msg = validate_period(int(start_period), int(end_period))
            if not valid:
                st.error(msg)
            elif not selected_days:
                st.error("반복 요일을 하나 이상 선택하세요.")
            else:
                successes, failures = db.add_recurring_reservations(
                    room_id=room_id,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                    selected_days=selected_days,
                    start_period=int(start_period),
                    end_period=int(end_period),
                    user_name=user_name,
                    purpose=purpose,
                )
                st.success(f"반복 예약 처리 완료: 성공 {len(successes)}건 / 실패 {len(failures)}건")
                if successes:
                    st.markdown("##### 성공 목록")
                    st.dataframe(pd.DataFrame(successes), use_container_width=True, hide_index=True)
                if failures:
                    st.markdown("##### 실패 목록")
                    st.dataframe(pd.DataFrame(failures), use_container_width=True, hide_index=True)


# -----------------------------------------------------------------------------
# 실시간 현황판
# -----------------------------------------------------------------------------
elif page == "실시간 현황판":
    st.title("실시간 현황판")
    st.caption("선택 날짜 기준으로 강의실별 교시 상태를 확인합니다. 수업은 요일 기준, 예약은 날짜 기준입니다.")
    render_legend()

    f1, f2, f3 = st.columns(3)
    selected_date = f1.date_input("날짜", value=DateType.today())
    floor_filter = f2.selectbox("층", ["전체"] + sorted(rooms_df["floor"].dropna().astype(int).unique().tolist()))
    type_filter = f3.selectbox("유형", ["전체"] + sorted(rooms_df["room_type"].dropna().unique().tolist()))

    filtered_rooms = rooms_df.copy()
    if floor_filter != "전체":
        filtered_rooms = filtered_rooms[filtered_rooms["floor"] == int(floor_filter)]
    if type_filter != "전체":
        filtered_rooms = filtered_rooms[filtered_rooms["room_type"] == type_filter]

    matrix = build_daily_matrix(selected_date, filtered_rooms["room_id"].tolist())
    st.markdown(f"**{selected_date} ({weekday_from_date(selected_date)}) 기준 / {len(filtered_rooms)}개 강의실**")
    st.dataframe(matrix, use_container_width=True, hide_index=True)

    raw_values = matrix.drop(columns=["강의실"]).replace({"🟢 가능": "가능", "🔵 수업": "수업", "🔴 예약": "예약"}).stack()
    status_count = raw_values.value_counts().reindex(STATUS_ORDER, fill_value=0).rename_axis("상태").reset_index(name="개수")
    st.subheader("상태 요약")
    st.bar_chart(status_count.set_index("상태"))


# -----------------------------------------------------------------------------
# 빈 강의실 찾기
# -----------------------------------------------------------------------------
elif page == "빈 강의실 찾기":
    st.title("빈 강의실 찾기")
    st.caption("날짜·사용 길이·필요 인원만으로 가능한 강의실과 시간대를 한 번에 찾습니다.")

    with st.form("free_room_search_form"):
        a, b, c, d = st.columns(4)
        selected_date = a.date_input("사용 날짜", value=DateType.today())
        duration = b.selectbox("사용 길이", [1, 2, 3, 4, 5], index=1, format_func=lambda x: f"{x}교시")
        min_capacity = c.number_input("필요 인원", min_value=1, max_value=300, value=30, step=1)
        top_n = d.slider("표시 개수", min_value=5, max_value=100, value=30, step=5)
        e, f = st.columns(2)
        start_min = e.selectbox("탐색 시작 교시", PERIODS, index=0)
        end_max = f.selectbox("탐색 종료 상한", END_PERIODS, index=len(END_PERIODS) - 1, help="13이면 12교시까지 사용 가능")
        submit = st.form_submit_button("빈 강의실 찾기", use_container_width=True)

    if submit:
        if int(start_min) + int(duration) > int(end_max):
            st.error("탐색 범위가 사용 길이보다 짧습니다.")
        else:
            rows = db.search_available_room_slots(
                selected_date.isoformat(), int(duration), int(min_capacity), int(start_min), int(end_max)
            )
            columns = [
                "room_id", "building", "floor", "room_name", "capacity", "room_type",
                "location_score", "accessibility_score", "priority", "start_period", "end_period",
            ]
            result = pd.DataFrame(rows, columns=columns)
            if result.empty:
                st.error("조건에 맞는 빈 강의실이 없습니다.")
            else:
                result["남는 좌석"] = result["capacity"] - int(min_capacity)
                result["가능 시간"] = result.apply(lambda r: period_range_text(int(r["start_period"]), int(r["end_period"])), axis=1)
                result = result.sort_values(["start_period", "남는 좌석", "priority"], ascending=[True, True, False]).head(top_n)
                st.success(f"가능 후보 {len(rows)}개 중 상위 {len(result)}개를 표시합니다.")
                st.dataframe(
                    result[["가능 시간", "room_id", "room_name", "capacity", "남는 좌석", "room_type", "floor", "priority"]],
                    use_container_width=True,
                    hide_index=True,
                )
                st.info("예약까지 바로 진행하려면 '예약하기 → 추천으로 예약'에서 같은 조건을 입력하세요.")


# -----------------------------------------------------------------------------
# 예약 관리
# -----------------------------------------------------------------------------
elif page == "예약 관리":
    st.title("예약 관리")
    st.caption("실시간 예약 데이터를 조회하고 취소합니다. 취소 즉시 DB에서 삭제됩니다.")

    if reservations_df.empty:
        st.info("현재 실시간 예약 데이터가 없습니다.")
    else:
        f1, f2, f3, f4 = st.columns(4)
        room_filter = f1.selectbox("강의실", ["전체"] + room_options)
        use_date_filter = f2.checkbox("날짜 필터")
        date_filter = f3.date_input("날짜", value=DateType.today(), disabled=not use_date_filter)
        user_filter = f4.text_input("예약자 검색")

        filtered = reservations_df.copy()
        if room_filter != "전체":
            filtered = filtered[filtered["room_id"] == room_filter]
        if use_date_filter:
            filtered = filtered[filtered["date"] == date_filter.isoformat()]
        if user_filter.strip():
            filtered = filtered[filtered["user_name"].str.contains(user_filter.strip(), na=False)]
        filtered["시간"] = filtered.apply(lambda r: period_range_text(int(r["start_period"]), int(r["end_period"])), axis=1)

        st.dataframe(
            filtered[["reservation_id", "room_id", "date", "day", "시간", "user_name", "purpose", "created_at"]],
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "예약 목록 CSV 다운로드",
            data=filtered.to_csv(index=False).encode("utf-8-sig"),
            file_name="classfit_reservations.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.divider()
        st.subheader("예약 취소")
        if filtered.empty:
            st.warning("현재 필터 조건에서 취소할 예약이 없습니다.")
        else:
            cancel_id = st.selectbox("취소할 예약 ID", filtered["reservation_id"].astype(int).tolist())
            confirm = st.checkbox("선택한 예약을 취소합니다")
            if st.button("예약 취소", type="primary", disabled=not confirm, use_container_width=True):
                ok, message = db.cancel_reservation(int(cancel_id))
                if ok:
                    rerun_with_flash("success", message)
                else:
                    st.error(message)


# -----------------------------------------------------------------------------
# 데이터 관리
# -----------------------------------------------------------------------------
elif page == "데이터 관리":
    st.title("데이터 관리")
    st.caption("DB와 원본 테이블을 확인합니다. 발표용 설명 페이지가 아니라 운영 확인용 페이지입니다.")

    c1, c2, c3 = st.columns(3)
    with c1:
        render_metric_card("rooms", f"{len(rooms_df):,}행")
    with c2:
        render_metric_card("blocked_schedules", f"{len(blocked_df):,}행")
    with c3:
        render_metric_card("reservations", f"{len(reservations_df):,}행")

    st.divider()
    tab1, tab2, tab3 = st.tabs(["강의실 데이터", "기존 수업 차단", "실시간 예약"])
    with tab1:
        st.dataframe(rooms_df, use_container_width=True, hide_index=True)
        st.download_button(
            "rooms.csv 다운로드",
            data=rooms_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="rooms_from_db.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with tab2:
        st.dataframe(blocked_df, use_container_width=True, hide_index=True)
        st.download_button(
            "blocked_schedules.csv 다운로드",
            data=blocked_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="blocked_schedules_from_db.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with tab3:
        st.dataframe(reservations_df, use_container_width=True, hide_index=True)
        st.download_button(
            "reservations.csv 다운로드",
            data=reservations_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="reservations_from_db.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.divider()
    st.subheader("무결성 점검")
    orphan_blocked = query_df(
        """
        SELECT b.* FROM blocked_schedules b
        LEFT JOIN rooms r ON b.room_id = r.room_id
        WHERE r.room_id IS NULL
        """
    )
    orphan_res = query_df(
        """
        SELECT rv.* FROM reservations rv
        LEFT JOIN rooms r ON rv.room_id = r.room_id
        WHERE r.room_id IS NULL
        """
    )
    if orphan_blocked.empty and orphan_res.empty:
        st.success("강의실 참조 무결성 문제 없음")
    else:
        st.error("무결성 문제가 발견되었습니다.")
        if not orphan_blocked.empty:
            st.write("blocked_schedules 문제")
            st.dataframe(orphan_blocked, use_container_width=True, hide_index=True)
        if not orphan_res.empty:
            st.write("reservations 문제")
            st.dataframe(orphan_res, use_container_width=True, hide_index=True)
