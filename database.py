"""
ClassFit database module v3

역할
- SQLite DB 스키마 생성
- CSV 기반 초기 데이터 로딩
- 기존 수업 시간표(blocked_schedules)와 실시간 예약(reservations) 충돌 검사
- 예약 신청/취소/조회
- 빈 강의실 및 대체 시간 탐색

v3 수정 핵심
- 예약/현황 조회는 앱에서 캐시하지 않아 DB 반영 지연을 줄인다.
- 예약 INSERT/DELETE는 BEGIN IMMEDIATE 트랜잭션으로 처리해 동시 클릭에 의한 중복 예약을 방지한다.
- SQLite WAL 모드와 busy_timeout을 사용해 여러 사용자의 읽기/쓰기 충돌을 완화한다.
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "classfit.db"
DATA_DIR = BASE_DIR / "data"
ROOMS_CSV_PATH = DATA_DIR / "rooms.csv"
BLOCKED_CSV_PATH = DATA_DIR / "blocked_schedules.csv"

KOREAN_WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


class ClassFitError(Exception):
    """ClassFit DB 처리 중 발생하는 명시적 예외."""


def get_day_from_date(date_text: str) -> str:
    """YYYY-MM-DD 날짜를 한국어 요일 문자로 변환한다."""
    dt = datetime.strptime(date_text, "%Y-%m-%d")
    return KOREAN_WEEKDAYS[dt.weekday()]


def connect_db() -> sqlite3.Connection:
    """SQLite 연결. 다중 사용자 시연을 위해 WAL/timeout 설정을 적용한다."""
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 10000;")
    return conn


def init_db() -> None:
    """SQLite DB 스키마와 인덱스를 생성한다."""
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode = WAL;")
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS rooms (
            room_id TEXT PRIMARY KEY,
            building TEXT NOT NULL,
            floor INTEGER,
            room_number TEXT,
            room_name TEXT NOT NULL,
            capacity INTEGER NOT NULL,
            capacity_avg REAL,
            room_type TEXT,
            location_score INTEGER DEFAULT 3,
            accessibility_score INTEGER DEFAULT 3,
            priority INTEGER DEFAULT 3,
            equipment TEXT DEFAULT 'projector,computer,whiteboard',
            source_course_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS blocked_schedules (
            blocked_id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id TEXT NOT NULL,
            room_id TEXT NOT NULL,
            day TEXT NOT NULL,
            period INTEGER NOT NULL,
            capacity INTEGER,
            source_row INTEGER,
            FOREIGN KEY (room_id) REFERENCES rooms(room_id)
        );

        CREATE TABLE IF NOT EXISTS reservations (
            reservation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT NOT NULL,
            date TEXT NOT NULL,
            day TEXT NOT NULL,
            start_period INTEGER NOT NULL,
            end_period INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            purpose TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id) REFERENCES rooms(room_id)
        );

        CREATE INDEX IF NOT EXISTS idx_blocked_room_day_period
        ON blocked_schedules(room_id, day, period);

        CREATE INDEX IF NOT EXISTS idx_blocked_day_period
        ON blocked_schedules(day, period);

        CREATE INDEX IF NOT EXISTS idx_reservations_room_date_period
        ON reservations(room_id, date, start_period, end_period);

        CREATE INDEX IF NOT EXISTS idx_reservations_date
        ON reservations(date);

        CREATE INDEX IF NOT EXISTS idx_rooms_capacity
        ON rooms(capacity);
        """
    )
    conn.commit()
    conn.close()


def reset_db_from_csv() -> None:
    """CSV 기반으로 rooms, blocked_schedules를 재생성한다. reservations는 빈 상태로 초기화된다."""
    init_db()
    conn = connect_db()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE;")
        cur.execute("DELETE FROM reservations;")
        cur.execute("DELETE FROM blocked_schedules;")
        cur.execute("DELETE FROM rooms;")
        cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('reservations', 'blocked_schedules');")

        with open(ROOMS_CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rooms = []
            for row in reader:
                rooms.append(
                    (
                        row["room_id"],
                        row["building"],
                        int(row["floor"]) if row.get("floor") else None,
                        row.get("room_number", ""),
                        row["room_name"],
                        int(row["capacity"]),
                        float(row["capacity_avg"]) if row.get("capacity_avg") else None,
                        row.get("room_type", "일반강의실"),
                        int(row.get("location_score") or 3),
                        int(row.get("accessibility_score") or 3),
                        int(row.get("priority") or 3),
                        row.get("equipment") or "projector,computer,whiteboard",
                        int(row.get("source_course_count") or 0),
                    )
                )

        cur.executemany(
            """
            INSERT INTO rooms
            (room_id, building, floor, room_number, room_name, capacity, capacity_avg,
             room_type, location_score, accessibility_score, priority, equipment, source_course_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            rooms,
        )

        with open(BLOCKED_CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            blocked = []
            for row in reader:
                blocked.append(
                    (
                        row["course_id"],
                        row["room_id"],
                        row["day"],
                        int(row["period"]),
                        int(row["capacity"]) if row.get("capacity") not in (None, "") else None,
                        int(row["source_row"]) if row.get("source_row") not in (None, "") else None,
                    )
                )

        cur.executemany(
            """
            INSERT INTO blocked_schedules
            (course_id, room_id, day, period, capacity, source_row)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            blocked,
        )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_seed_data() -> None:
    """DB 파일이 없거나 rooms가 비어 있으면 CSV로 초기화한다."""
    init_db()
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM rooms;")
    room_count = cur.fetchone()[0]
    conn.close()
    if room_count == 0:
        reset_db_from_csv()


def get_conflict_details(room_id: str, date: str, start_period: int, end_period: int) -> dict:
    """예약 가능 여부와 실패 원인을 상세히 반환한다."""
    if start_period >= end_period:
        return {"ok": False, "type": "period_error", "message": "종료 교시는 시작 교시보다 커야 합니다."}
    if start_period < 1 or end_period > 13:
        return {"ok": False, "type": "period_error", "message": "예약 가능 교시는 1~12교시입니다."}

    try:
        day = get_day_from_date(date)
    except ValueError:
        return {"ok": False, "type": "date_error", "message": "날짜 형식은 YYYY-MM-DD이어야 합니다."}

    conn = connect_db()
    cur = conn.cursor()

    cur.execute("SELECT room_id FROM rooms WHERE room_id = ?;", (room_id,))
    if cur.fetchone() is None:
        conn.close()
        return {"ok": False, "type": "room_error", "message": "존재하지 않는 강의실입니다."}

    cur.execute(
        """
        SELECT course_id, period
        FROM blocked_schedules
        WHERE room_id = ? AND day = ? AND period >= ? AND period < ?
        ORDER BY period ASC;
        """,
        (room_id, day, start_period, end_period),
    )
    blocked_rows = cur.fetchall()

    cur.execute(
        """
        SELECT reservation_id, start_period, end_period, user_name, purpose
        FROM reservations
        WHERE room_id = ? AND date = ? AND start_period < ? AND ? < end_period
        ORDER BY start_period ASC;
        """,
        (room_id, date, end_period, start_period),
    )
    reservation_rows = cur.fetchall()
    conn.close()

    if blocked_rows:
        periods = ", ".join(f"{p}교시" for _, p in blocked_rows)
        courses = ", ".join(sorted(set(str(c) for c, _ in blocked_rows)))
        return {
            "ok": False,
            "type": "blocked",
            "day": day,
            "periods": periods,
            "courses": courses,
            "message": f"기존 수업과 충돌합니다: {day} {periods} / 학수번호 {courses}",
        }

    if reservation_rows:
        items = [f"예약 #{rid}({s}~{e}교시, {user})" for rid, s, e, user, _ in reservation_rows]
        return {
            "ok": False,
            "type": "reservation",
            "day": day,
            "items": items,
            "message": "실시간 예약과 충돌합니다: " + "; ".join(items),
        }

    return {"ok": True, "type": "none", "day": day, "message": "예약 가능한 시간입니다."}


def add_reservation(room_id: str, date: str, start_period: int, end_period: int, user_name: str, purpose: str = ""):
    """예약 신청. 트랜잭션 안에서 충돌을 재검사한 뒤 저장한다."""
    if start_period >= end_period:
        return False, "예약 실패: 종료 교시는 시작 교시보다 커야 합니다."
    if start_period < 1 or end_period > 13:
        return False, "예약 실패: 예약 가능 교시는 1~12교시입니다."
    if not user_name or not user_name.strip():
        return False, "예약 실패: 예약자명을 입력해야 합니다."

    try:
        day = get_day_from_date(date)
    except ValueError:
        return False, "예약 실패: 날짜 형식은 YYYY-MM-DD이어야 합니다."

    conn = connect_db()
    cur = conn.cursor()
    try:
        # 동시에 여러 사용자가 같은 강의실을 예약해도 여기서 직렬화된다.
        cur.execute("BEGIN IMMEDIATE;")

        cur.execute("SELECT room_id FROM rooms WHERE room_id = ?;", (room_id,))
        if cur.fetchone() is None:
            conn.rollback()
            return False, "예약 실패: 존재하지 않는 강의실입니다."

        cur.execute(
            """
            SELECT course_id, period
            FROM blocked_schedules
            WHERE room_id = ? AND day = ? AND period >= ? AND period < ?
            ORDER BY period ASC;
            """,
            (room_id, day, start_period, end_period),
        )
        blocked = cur.fetchone()
        if blocked:
            conn.rollback()
            return False, f"예약 실패: {day}{blocked[1]}교시에 기존 수업({blocked[0]})이 있습니다."

        cur.execute(
            """
            SELECT reservation_id, start_period, end_period
            FROM reservations
            WHERE room_id = ? AND date = ? AND start_period < ? AND ? < end_period;
            """,
            (room_id, date, end_period, start_period),
        )
        conflict = cur.fetchone()
        if conflict:
            conn.rollback()
            return False, f"예약 실패: 기존 예약 ID {conflict[0]}번({conflict[1]}~{conflict[2]}교시)과 시간이 겹칩니다."

        cur.execute(
            """
            INSERT INTO reservations
            (room_id, date, day, start_period, end_period, user_name, purpose)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (room_id, date, day, start_period, end_period, user_name.strip(), purpose.strip()),
        )
        reservation_id = cur.lastrowid
        conn.commit()
        return True, f"예약 완료: 예약 ID {reservation_id}"
    except sqlite3.Error as exc:
        conn.rollback()
        return False, f"DB 오류: {exc}"
    finally:
        conn.close()


def cancel_reservation(reservation_id: int):
    """예약 취소. 실제로 삭제된 행이 있을 때만 성공 처리한다."""
    conn = connect_db()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE;")
        cur.execute("DELETE FROM reservations WHERE reservation_id = ?;", (int(reservation_id),))
        deleted = cur.rowcount
        if deleted == 0:
            conn.rollback()
            return False, "예약 취소 실패: 해당 예약 ID를 찾을 수 없습니다."
        conn.commit()
        return True, f"예약 ID {reservation_id}번이 취소되었습니다."
    except sqlite3.Error as exc:
        conn.rollback()
        return False, f"DB 오류: {exc}"
    finally:
        conn.close()


def get_available_rooms(date: str, start_period: int, end_period: int, min_capacity: int = 0):
    """특정 날짜/교시에 사용 가능한 강의실 목록을 반환한다."""
    try:
        day = get_day_from_date(date)
    except ValueError:
        return []

    conn = connect_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT r.room_id, r.building, r.floor, r.room_name, r.capacity, r.room_type,
               r.location_score, r.accessibility_score, r.priority
        FROM rooms r
        WHERE r.capacity >= ?
          AND NOT EXISTS (
              SELECT 1 FROM blocked_schedules b
              WHERE b.room_id = r.room_id AND b.day = ? AND b.period >= ? AND b.period < ?
          )
          AND NOT EXISTS (
              SELECT 1 FROM reservations rv
              WHERE rv.room_id = r.room_id AND rv.date = ?
                AND rv.start_period < ? AND ? < rv.end_period
          )
        ORDER BY r.priority DESC, r.capacity ASC, r.room_id ASC;
        """,
        (min_capacity, day, start_period, end_period, date, end_period, start_period),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def search_available_room_slots(date: str, duration: int, min_capacity: int = 1, start_min: int = 1, end_max: int = 13):
    """특정 날짜에 duration만큼 비어 있는 강의실-시간 후보를 모두 찾는다."""
    if duration < 1 or start_min < 1 or end_max > 13 or start_min >= end_max:
        return []
    candidates = []
    for start in range(start_min, end_max - duration + 1):
        end = start + duration
        for row in get_available_rooms(date, start, end, min_capacity):
            candidates.append((*row, start, end))
    return candidates


def recommend_alternative_slots(room_id: str, date: str, duration: int, min_start: int = 1, max_end: int = 13, limit: int = 8):
    """선택 강의실에서 같은 날짜에 가능한 대체 시간대를 추천한다."""
    alternatives = []
    if duration < 1:
        return alternatives
    for start in range(min_start, max_end - duration + 1):
        end = start + duration
        detail = get_conflict_details(room_id, date, start, end)
        if detail["ok"]:
            alternatives.append((room_id, date, start, end))
        if len(alternatives) >= limit:
            break
    return alternatives


def add_recurring_reservations(room_id: str, start_date: str, end_date: str, selected_days: Iterable[str],
                               start_period: int, end_period: int, user_name: str, purpose: str = ""):
    """반복 예약. 일부 실패해도 성공/실패 목록을 모두 반환한다."""
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return [], [{"date": "-", "ok": False, "message": "날짜 형식 오류"}]

    if end_dt < start_dt:
        return [], [{"date": "-", "ok": False, "message": "종료일은 시작일보다 늦어야 합니다."}]

    days = set(selected_days)
    successes: list[dict] = []
    failures: list[dict] = []
    cur_dt = start_dt
    while cur_dt <= end_dt:
        date_text = cur_dt.strftime("%Y-%m-%d")
        day = get_day_from_date(date_text)
        if day in days:
            ok, message = add_reservation(room_id, date_text, start_period, end_period, user_name, purpose)
            record = {"date": date_text, "day": day, "ok": ok, "message": message}
            if ok:
                successes.append(record)
            else:
                failures.append(record)
        cur_dt += timedelta(days=1)
    return successes, failures


if __name__ == "__main__":
    ensure_seed_data()
    print("DB 준비 완료")
    print("예시 사용 가능 강의실:", get_available_rooms("2026-06-01", 5, 7, 30)[:3])
