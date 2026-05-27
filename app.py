"""
ClassFit Streamlit App
우선순위 큐와 구간 겹침 검사를 활용한 강의실 예약 및 최적 추천 서비스 프로토타입

핵심 자료구조/알고리즘
- SQLite table: rooms, blocked_schedules, reservations
- dict/list: 예약 데이터 캐시 및 시간표 구성
- set/조건 검사: 유형/조건 필터링
- 구간 겹침 검사: 기존 예약과 신규 예약 충돌 판단
- 점수 기반 정렬/Top-K 추천: 사용 가능한 강의실 추천
"""

from __future__ import annotations

import sqlite3
from datetime import date as DateType
from pathlib import Path
from typing import Iterable

import pandas as pd
import streamlit as st

import database as db

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "classfit.db"
DATA_DIR = BASE_DIR / "data"
PERIODS = list(range(1, 13))
KOREAN_DAYS = ["월", "화", "수", "목", "금", "토", "일"]


# -----------------------------------------------------------------------------
# 기본 설정
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="ClassFit | 강의실 예약 추천 시스템",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main .block-container {padding-top: 2rem; padding-bottom: 3rem;}
    .metric-card {
        background: #f8fafc;
        border: 1px solid #e5e7eb;
        border-radius: 14px;
        padding: 18px;
    }
    .small-muted {color: #6b7280; font-size: 0.9rem;}
    .ok-box {
        padding: 0.85rem 1rem;
        border-radius: 0.75rem;
        border: 1px solid #bbf7d0;
        background: #f0fdf4;
    }
    .warn-box {
        padding: 0.85rem 1rem;
        border-radius: 0.75rem;
        border: 1px solid #fde68a;
        background: #fffbeb;
    }
    .bad-box {
        padding: 0.85rem 1rem;
        border-radius: 0.75rem;
        border: 1px solid #fecaca;
        background: #fef2f2;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# DB / 데이터 접근 함수
# -----------------------------------------------------------------------------
def ensure_database_ready() -> None:
    """배포 환경에서 DB가 없거나 비어 있으면 CSV 기반으로 자동 복구."""
    try:
        db.init_db()
        if not DB_PATH.exists():
            db.reset_db_from_csv()
            return
        conn = sqlite3.connect(DB_PATH)
        count = pd.read_sql_query("SELECT COUNT(*) AS cnt FROM rooms", conn).iloc[0]["cnt"]
        conn.close()
        if int(count) == 0:
            db.reset_db_from_csv()
    except Exception as exc:  # Streamlit 화면에서 즉시 원인 확인 가능
        st.error(f"DB 초기화 중 오류가 발생했습니다: {exc}")
        st.stop()


@st.cache_data(ttl=3)
def query_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def clear_cache() -> None:
    st.cache_data.clear()


@st.cache_data(ttl=5)
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


@st.cache_data(ttl=5)
def get_reservations_df() -> pd.DataFrame:
    return query_df(
        """
        SELECT reservation_id, room_id, date, day, start_period, end_period,
               user_name, purpose, created_at
        FROM reservations
        ORDER BY date DESC, start_period ASC
        """
    )


@st.cache_data(ttl=5)
def get_blocked_df() -> pd.DataFrame:
    return query_df(
        """
        SELECT blocked_id, course_id, room_id, day, period, capacity, source_row
        FROM blocked_schedules
        ORDER BY room_id, day, period
        """
    )


def get_room_options() -> list[str]:
    rooms = get_rooms_df()
    return rooms["room_id"].tolist()


def weekday_from_date(selected_date: DateType) -> str:
    return KOREAN_DAYS[selected_date.weekday()]


def validate_period(start_period: int, end_period: int) -> tuple[bool, str]:
    if start_period < 1 or end_period > 13:
        return False, "교시는 1교시부터 12교시까지만 입력할 수 있습니다."
    if start_period >= end_period:
        return False, "종료 교시는 시작 교시보다 커야 합니다. 예: 5~7은 5, 6교시 사용입니다."
    return True, "OK"


def available_rooms_df(
    selected_date: DateType,
    start_period: int,
    end_period: int,
    min_capacity: int,
) -> pd.DataFrame:
    """기존 수업 + 실시간 예약을 제외한 사용 가능 강의실 반환."""
    date_text = selected_date.isoformat()
    rows = db.get_available_rooms(date_text, start_period, end_period, min_capacity)
    columns = [
        "room_id",
        "building",
        "floor",
        "room_name",
        "capacity",
        "room_type",
        "location_score",
        "accessibility_score",
        "priority",
    ]
    return pd.DataFrame(rows, columns=columns)


def capacity_fit_score(capacity: int, required: int) -> int:
    """정원 낭비 최소화 점수. required 이상만 들어온다고 가정."""
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


def build_recommendations(
    selected_date: DateType,
    start_period: int,
    end_period: int,
    min_capacity: int,
    preferred_building: str | None,
    preferred_floor: int | None,
    preferred_room_type: str | None,
    top_n: int = 10,
) -> pd.DataFrame:
    """
    사용 가능한 강의실에 점수를 부여해 Top-K 추천.
    알고리즘 관점: 후보 필터링 -> 점수 계산 -> 정렬/Top-K 선택.
    """
    candidates = available_rooms_df(selected_date, start_period, end_period, min_capacity)
    if candidates.empty:
        return candidates

    scored_rows = []
    for _, row in candidates.iterrows():
        score = 0
        reasons = []

        # 1. 수용 인원 조건: 사용 가능 후보는 이미 capacity >= min_capacity
        cap_score = capacity_fit_score(int(row["capacity"]), min_capacity)
        score += cap_score
        reasons.append(f"정원 적합 +{cap_score}")

        # 2. 선호 건물
        if preferred_building and preferred_building != "상관없음":
            if row["building"] == preferred_building:
                score += 18
                reasons.append("선호 건물 일치 +18")
            else:
                reasons.append("선호 건물 불일치 +0")

        # 3. 선호 층과의 거리
        if preferred_floor is not None:
            floor_gap = abs(int(row["floor"]) - int(preferred_floor))
            floor_score = max(0, 12 - floor_gap * 3)
            score += floor_score
            reasons.append(f"층 접근성 +{floor_score}")

        # 4. 강의실 유형
        if preferred_room_type and preferred_room_type != "상관없음":
            if row["room_type"] == preferred_room_type:
                score += 12
                reasons.append("유형 일치 +12")
            else:
                reasons.append("유형 불일치 +0")

        # 5. 기존 데이터 기반 기본 점수
        base_score = int(row["location_score"]) + int(row["accessibility_score"]) + int(row["priority"])
        score += base_score
        reasons.append(f"기본 선호도 +{base_score}")

        result = row.to_dict()
        result["score"] = int(score)
        result["capacity_waste"] = int(row["capacity"]) - int(min_capacity)
        result["reason"] = " / ".join(reasons)
        scored_rows.append(result)

    result_df = pd.DataFrame(scored_rows)
    result_df = result_df.sort_values(
        by=["score", "capacity_waste", "capacity"],
        ascending=[False, True, True],
    ).head(top_n)
    return result_df.reset_index(drop=True)


def period_badges(periods: Iterable[int]) -> str:
    items = sorted(set(int(p) for p in periods))
    return ", ".join(f"{p}교시" for p in items) if items else "없음"


def get_room_timetable(room_id: str, selected_date: DateType) -> pd.DataFrame:
    """특정 강의실의 선택 날짜 기준 시간표. 기존 수업은 요일 기준, 예약은 날짜 기준."""
    day = weekday_from_date(selected_date)
    date_text = selected_date.isoformat()
    blocked = query_df(
        """
        SELECT period, course_id
        FROM blocked_schedules
        WHERE room_id = ? AND day = ?
        ORDER BY period
        """,
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
        for _, b in blocked[blocked["period"] == period].iterrows():
            status = "수업"
            detail = f"기존 수업 {b['course_id']}"
            break
        for _, r in reservations.iterrows():
            if int(r["start_period"]) <= period < int(r["end_period"]):
                status = "예약"
                detail = f"예약 #{r['reservation_id']} / {r['user_name']} / {r['purpose']}"
                break
        rows.append({"교시": period, "상태": status, "상세": detail})
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# 화면 구성
# -----------------------------------------------------------------------------
ensure_database_ready()

st.sidebar.title("🏫 ClassFit")
st.sidebar.caption("강의실 예약 · 충돌 검사 · 최적 추천")
page = st.sidebar.radio(
    "메뉴",
    [
        "대시보드",
        "강의실 추천",
        "예약 신청",
        "예약 조회/취소",
        "강의실 시간표",
        "데이터/알고리즘 설명",
    ],
)

if st.sidebar.button("🔄 화면 새로고침", use_container_width=True):
    clear_cache()
    st.rerun()

with st.sidebar.expander("DB 관리"):
    st.warning("초기화하면 실시간 예약 데이터가 모두 삭제됩니다.")
    if st.button("CSV 기준으로 DB 초기화", use_container_width=True):
        db.reset_db_from_csv()
        clear_cache()
        st.success("DB를 초기화했습니다.")
        st.rerun()

rooms_df = get_rooms_df()
reservations_df = get_reservations_df()
blocked_df = get_blocked_df()

# -----------------------------------------------------------------------------
# 대시보드
# -----------------------------------------------------------------------------
if page == "대시보드":
    st.title("ClassFit 강의실 예약 추천 시스템")
    st.write("기존 수업 시간표를 자동으로 차단하고, 실시간 예약과 충돌하지 않는 강의실을 추천합니다.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("강의실 수", f"{len(rooms_df):,}개")
    c2.metric("기존 수업 차단 시간", f"{len(blocked_df):,}개")
    c3.metric("실시간 예약", f"{len(reservations_df):,}건")
    c4.metric("강의실 유형", f"{rooms_df['room_type'].nunique():,}종")

    st.divider()
    left, right = st.columns([1.1, 0.9])
    with left:
        st.subheader("강의실 목록")
        st.dataframe(
            rooms_df[["room_id", "floor", "capacity", "room_type", "priority", "source_course_count"]],
            use_container_width=True,
            hide_index=True,
        )
    with right:
        st.subheader("강의실 유형별 개수")
        type_count = rooms_df.groupby("room_type", as_index=False)["room_id"].count()
        type_count = type_count.rename(columns={"room_id": "count"})
        st.bar_chart(type_count.set_index("room_type"))

        st.subheader("요일별 기존 수업 차단 수")
        day_count = blocked_df.groupby("day", as_index=False)["blocked_id"].count()
        day_count["day_order"] = day_count["day"].map({d: i for i, d in enumerate(KOREAN_DAYS)})
        day_count = day_count.sort_values("day_order").drop(columns="day_order")
        st.bar_chart(day_count.set_index("day"))

# -----------------------------------------------------------------------------
# 강의실 추천
# -----------------------------------------------------------------------------
elif page == "강의실 추천":
    st.title("강의실 추천")
    st.caption("시간 충돌을 먼저 제거한 뒤, 정원 낭비·건물·층·유형 점수로 Top-K 강의실을 추천합니다.")

    with st.form("recommend_form"):
        a, b, c = st.columns(3)
        selected_date = a.date_input("예약 날짜", value=DateType.today())
        start_period = b.selectbox("시작 교시", PERIODS, index=0)
        end_period = c.selectbox("종료 교시", list(range(2, 14)), index=1, help="종료 교시는 포함하지 않습니다. 예: 5~7 = 5, 6교시")

        d, e, f, g = st.columns(4)
        min_capacity = d.number_input("필요 인원", min_value=1, max_value=300, value=30, step=1)
        building_options = ["상관없음"] + sorted(rooms_df["building"].dropna().unique().tolist())
        preferred_building = e.selectbox("선호 건물", building_options)
        floor_options = ["상관없음"] + sorted(rooms_df["floor"].dropna().astype(int).unique().tolist())
        preferred_floor_raw = f.selectbox("선호 층", floor_options)
        type_options = ["상관없음"] + sorted(rooms_df["room_type"].dropna().unique().tolist())
        preferred_room_type = g.selectbox("강의실 유형", type_options)

        submitted = st.form_submit_button("추천 받기", use_container_width=True)

    if submitted:
        valid, msg = validate_period(int(start_period), int(end_period))
        if not valid:
            st.error(msg)
        else:
            preferred_floor = None if preferred_floor_raw == "상관없음" else int(preferred_floor_raw)
            result = build_recommendations(
                selected_date,
                int(start_period),
                int(end_period),
                int(min_capacity),
                preferred_building,
                preferred_floor,
                preferred_room_type,
                top_n=10,
            )

            st.subheader(f"추천 결과: {selected_date} ({weekday_from_date(selected_date)}) {start_period}~{end_period}교시")
            if result.empty:
                st.error("조건을 만족하면서 사용 가능한 강의실이 없습니다. 날짜, 교시, 인원 조건을 완화하세요.")
            else:
                st.dataframe(
                    result[[
                        "room_id", "room_name", "capacity", "capacity_waste", "room_type",
                        "floor", "score", "reason"
                    ]],
                    use_container_width=True,
                    hide_index=True,
                )

                top = result.iloc[0]
                st.success(f"1순위 추천: {top['room_id']} / 점수 {top['score']}점 / 정원 {top['capacity']}명")

                with st.expander("추천된 강의실로 바로 예약하기"):
                    with st.form("quick_reservation_form"):
                        room_id = st.selectbox("예약할 강의실", result["room_id"].tolist())
                        user_name = st.text_input("예약자명", placeholder="예: 홍길동")
                        purpose = st.text_input("사용 목적", placeholder="예: 팀 프로젝트 회의")
                        quick_submit = st.form_submit_button("이 조건으로 예약 신청", use_container_width=True)
                    if quick_submit:
                        if not user_name.strip():
                            st.error("예약자명을 입력하세요.")
                        else:
                            ok, message = db.add_reservation(
                                room_id=room_id,
                                date=selected_date.isoformat(),
                                start_period=int(start_period),
                                end_period=int(end_period),
                                user_name=user_name.strip(),
                                purpose=purpose.strip(),
                            )
                            clear_cache()
                            if ok:
                                st.success(message)
                            else:
                                st.error(message)

# -----------------------------------------------------------------------------
# 예약 신청
# -----------------------------------------------------------------------------
elif page == "예약 신청":
    st.title("예약 신청")
    st.caption("기존 수업 시간표와 실시간 예약을 모두 검사한 뒤 충돌이 없을 때만 저장합니다.")

    with st.form("reservation_form"):
        c1, c2 = st.columns([1, 1])
        room_id = c1.selectbox("강의실", get_room_options())
        selected_date = c2.date_input("예약 날짜", value=DateType.today())

        c3, c4 = st.columns(2)
        start_period = c3.selectbox("시작 교시", PERIODS, index=0)
        end_period = c4.selectbox("종료 교시", list(range(2, 14)), index=1, help="종료 교시는 포함하지 않습니다. 예: 3~5 = 3, 4교시")

        c5, c6 = st.columns(2)
        user_name = c5.text_input("예약자명", placeholder="예: 홍길동")
        purpose = c6.text_input("사용 목적", placeholder="예: 발표 연습")

        submit = st.form_submit_button("예약 신청", use_container_width=True)

    if submit:
        valid, msg = validate_period(int(start_period), int(end_period))
        if not valid:
            st.error(msg)
        elif not user_name.strip():
            st.error("예약자명을 입력하세요.")
        else:
            ok, message = db.add_reservation(
                room_id=room_id,
                date=selected_date.isoformat(),
                start_period=int(start_period),
                end_period=int(end_period),
                user_name=user_name.strip(),
                purpose=purpose.strip(),
            )
            clear_cache()
            if ok:
                st.success(message)
            else:
                st.error(message)

    st.divider()
    st.subheader("선택 강의실 시간표 미리보기")
    if "room_id" in locals():
        tt = get_room_timetable(room_id, selected_date)
        st.dataframe(tt, use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# 예약 조회 / 취소
# -----------------------------------------------------------------------------
elif page == "예약 조회/취소":
    st.title("예약 조회 / 취소")

    if reservations_df.empty:
        st.info("현재 실시간 예약 데이터가 없습니다.")
    else:
        f1, f2, f3 = st.columns(3)
        room_filter = f1.selectbox("강의실 필터", ["전체"] + get_room_options())
        date_filter = f2.date_input("날짜 필터", value=None)
        user_filter = f3.text_input("예약자 검색")

        filtered = reservations_df.copy()
        if room_filter != "전체":
            filtered = filtered[filtered["room_id"] == room_filter]
        if date_filter:
            filtered = filtered[filtered["date"] == date_filter.isoformat()]
        if user_filter.strip():
            filtered = filtered[filtered["user_name"].str.contains(user_filter.strip(), na=False)]

        st.dataframe(filtered, use_container_width=True, hide_index=True)

        st.subheader("예약 취소")
        if filtered.empty:
            st.warning("취소할 예약이 없습니다.")
        else:
            cancel_id = st.selectbox("취소할 예약 ID", filtered["reservation_id"].astype(int).tolist())
            confirm = st.checkbox("정말 취소합니다")
            if st.button("예약 취소", type="primary", use_container_width=True):
                if not confirm:
                    st.error("취소 확인 체크가 필요합니다.")
                else:
                    ok, message = db.cancel_reservation(int(cancel_id))
                    clear_cache()
                    if ok:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)

# -----------------------------------------------------------------------------
# 강의실 시간표
# -----------------------------------------------------------------------------
elif page == "강의실 시간표":
    st.title("강의실 시간표")
    st.caption("기존 수업은 요일 기준, 실시간 예약은 선택 날짜 기준으로 표시합니다.")

    c1, c2 = st.columns(2)
    room_id = c1.selectbox("강의실 선택", get_room_options())
    selected_date = c2.date_input("날짜 선택", value=DateType.today())
    day = weekday_from_date(selected_date)

    room_info = rooms_df[rooms_df["room_id"] == room_id].iloc[0]
    st.write(f"**{room_info['room_name']}** / {room_info['room_type']} / 정원 {room_info['capacity']}명 / {day}요일")

    timetable = get_room_timetable(room_id, selected_date)
    st.dataframe(timetable, use_container_width=True, hide_index=True)

    status_count = timetable.groupby("상태", as_index=False)["교시"].count().rename(columns={"교시": "count"})
    st.bar_chart(status_count.set_index("상태"))

# -----------------------------------------------------------------------------
# 데이터 / 알고리즘 설명
# -----------------------------------------------------------------------------
elif page == "데이터/알고리즘 설명":
    st.title("데이터 구조와 알고리즘 설명")

    st.subheader("DB 테이블")
    st.markdown(
        """
        | 테이블 | 역할 |
        |---|---|
        | `rooms` | 강의실 고정 정보 저장 |
        | `blocked_schedules` | 기존 수업 때문에 예약 불가능한 요일/교시 저장 |
        | `reservations` | 사용자가 실시간으로 신청한 예약 저장 |
        """
    )

    st.subheader("핵심 알고리즘")
    st.markdown(
        """
        | 자료구조/알고리즘 | 적용 위치 | 설명 |
        |---|---|---|
        | SQLite + 인덱스 조회 | 예약/수업 충돌 검사 | `room_id`, `date`, `period` 조건으로 빠르게 조회 |
        | 구간 겹침 검사 | 실시간 예약 충돌 방지 | `기존시작 < 새종료 AND 새시작 < 기존종료` |
        | 선형 탐색/필터링 | 후보 강의실 추출 | 정원, 시간, 기존 수업 조건을 만족하는 강의실 선별 |
        | 점수 기반 정렬 | 강의실 추천 | 정원 낭비, 건물, 층, 유형, 기본 점수로 랭킹 계산 |
        | dict/list 캐시 | 예약 데이터 캐싱 | DB 조회 결과를 메모리에 저장해 반복 검사 최적화 |
        """
    )

    st.subheader("현재 원본 데이터")
    tab1, tab2, tab3 = st.tabs(["rooms", "blocked_schedules", "reservations"])
    with tab1:
        st.dataframe(rooms_df, use_container_width=True, hide_index=True)
    with tab2:
        st.dataframe(blocked_df, use_container_width=True, hide_index=True)
    with tab3:
        st.dataframe(reservations_df, use_container_width=True, hide_index=True)

    st.subheader("실행 방법")
    st.code("pip install -r requirements.txt\nstreamlit run app.py", language="bash")
