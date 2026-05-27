"""
ClassFit database module
역할: 팀원 A - SQLite DB 스키마 생성, 강의실 조회, 예약 신청/취소, 중복 예약 방지

자료구조:
- dict: DB 조회 결과 캐시
- list: 조회 결과 목록
- SQLite table: rooms, blocked_schedules, reservations

알고리즘:
- SQL WHERE 기반 해시/인덱스 조회
- 구간 중복 검사: start_period < new_end AND new_start < end_period
- 이진 탐색: 캐시된 예약 시간표에서 중복 구간 빠른 확인
"""

import csv
import sqlite3
from bisect import bisect_left
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "classfit.db"
ROOMS_CSV_PATH = BASE_DIR / "data" / "rooms.csv"
BLOCKED_CSV_PATH = BASE_DIR / "data" / "blocked_schedules.csv"

KOREAN_WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


def get_day_from_date(date_text: str) -> str:
    """YYYY-MM-DD 날짜를 한국어 요일 문자로 변환."""
    dt = datetime.strptime(date_text, "%Y-%m-%d")
    return KOREAN_WEEKDAYS[dt.weekday()]


def connect_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    """SQLite DB 스키마 생성."""
    conn = connect_db()
    cur = conn.cursor()

    cur.executescript("""
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

    CREATE INDEX IF NOT EXISTS idx_reservations_room_date_period
    ON reservations(room_id, date, start_period, end_period);

    CREATE INDEX IF NOT EXISTS idx_rooms_capacity
    ON rooms(capacity);
    """)

    conn.commit()
    conn.close()


def reset_db_from_csv():
    """
    CSV 기반으로 rooms, blocked_schedules를 다시 생성.
    reservations는 실시간 예약 테이블이므로 초기화된다.
    """
    init_db()
    conn = connect_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM reservations;")
    cur.execute("DELETE FROM blocked_schedules;")
    cur.execute("DELETE FROM rooms;")

    with open(ROOMS_CSV_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rooms = []
        for row in reader:
            rooms.append((
                row["room_id"],
                row["building"],
                int(row["floor"]) if row["floor"] else None,
                row["room_number"],
                row["room_name"],
                int(row["capacity"]),
                float(row["capacity_avg"]) if row["capacity_avg"] else None,
                row["room_type"],
                int(row["location_score"]),
                int(row["accessibility_score"]),
                int(row["priority"]),
                row["equipment"],
                int(row["source_course_count"]),
            ))

    cur.executemany("""
    INSERT INTO rooms
    (room_id, building, floor, room_number, room_name, capacity, capacity_avg,
     room_type, location_score, accessibility_score, priority, equipment, source_course_count)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, rooms)

    with open(BLOCKED_CSV_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        blocked = []
        for row in reader:
            blocked.append((
                row["course_id"],
                row["room_id"],
                row["day"],
                int(row["period"]),
                int(row["capacity"]) if row["capacity"] else None,
                int(row["source_row"]) if row["source_row"] else None,
            ))

    cur.executemany("""
    INSERT INTO blocked_schedules
    (course_id, room_id, day, period, capacity, source_row)
    VALUES (?, ?, ?, ?, ?, ?);
    """, blocked)

    conn.commit()
    conn.close()


def get_all_rooms():
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT room_id, building, floor, room_name, capacity, room_type,
           location_score, accessibility_score, priority, equipment
    FROM rooms
    ORDER BY building, floor, room_number;
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def get_room(room_id: str):
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT room_id, building, floor, room_name, capacity, room_type,
           location_score, accessibility_score, priority, equipment
    FROM rooms
    WHERE room_id = ?;
    """, (room_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_blocked_by_room_day(room_id: str, day: str):
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT course_id, room_id, day, period
    FROM blocked_schedules
    WHERE room_id = ? AND day = ?
    ORDER BY period ASC;
    """, (room_id, day))
    rows = cur.fetchall()
    conn.close()
    return rows


def has_blocked_conflict(room_id: str, day: str, start_period: int, end_period: int):
    """
    기존 수업 시간표와 충돌하는지 검사.
    기간은 [start_period, end_period) 방식이다.
    예: 5~7 입력 시 5교시, 6교시를 예약한다.
    """
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT course_id, period
    FROM blocked_schedules
    WHERE room_id = ?
      AND day = ?
      AND period >= ?
      AND period < ?
    ORDER BY period ASC;
    """, (room_id, day, start_period, end_period))
    row = cur.fetchone()
    conn.close()
    return row is not None


def has_reservation_conflict(room_id: str, date: str, start_period: int, end_period: int):
    """
    실시간 예약 데이터와 충돌하는지 검사.
    구간 중복 조건:
    기존 시작 < 새 종료 AND 새 시작 < 기존 종료
    """
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT reservation_id, start_period, end_period
    FROM reservations
    WHERE room_id = ?
      AND date = ?
      AND start_period < ?
      AND ? < end_period;
    """, (room_id, date, end_period, start_period))
    row = cur.fetchone()
    conn.close()
    return row is not None


def add_reservation(room_id: str, date: str, start_period: int, end_period: int,
                    user_name: str, purpose: str = ""):
    """
    예약 신청.
    1. 강의실 존재 확인
    2. 시간 입력 검증
    3. 기존 수업 시간표 충돌 확인
    4. 실시간 예약 충돌 확인
    5. 충돌 없으면 INSERT
    """
    if start_period >= end_period:
        return False, "예약 실패: 종료 교시는 시작 교시보다 커야 합니다."

    try:
        day = get_day_from_date(date)
    except ValueError:
        return False, "예약 실패: 날짜 형식은 YYYY-MM-DD이어야 합니다."

    conn = connect_db()
    cur = conn.cursor()

    try:
        cur.execute("BEGIN IMMEDIATE;")

        cur.execute("SELECT room_id FROM rooms WHERE room_id = ?;", (room_id,))
        if cur.fetchone() is None:
            conn.rollback()
            return False, "예약 실패: 존재하지 않는 강의실입니다."

        cur.execute("""
        SELECT course_id, period
        FROM blocked_schedules
        WHERE room_id = ?
          AND day = ?
          AND period >= ?
          AND period < ?
        ORDER BY period ASC;
        """, (room_id, day, start_period, end_period))
        blocked = cur.fetchone()

        if blocked:
            conn.rollback()
            return False, f"예약 실패: {day}{blocked[1]}교시에 기존 수업({blocked[0]})이 있습니다."

        cur.execute("""
        SELECT reservation_id, start_period, end_period
        FROM reservations
        WHERE room_id = ?
          AND date = ?
          AND start_period < ?
          AND ? < end_period;
        """, (room_id, date, end_period, start_period))
        conflict = cur.fetchone()

        if conflict:
            conn.rollback()
            return False, f"예약 실패: 기존 예약 ID {conflict[0]}번과 시간이 겹칩니다."

        cur.execute("""
        INSERT INTO reservations
        (room_id, date, day, start_period, end_period, user_name, purpose)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (room_id, date, day, start_period, end_period, user_name, purpose))

        reservation_id = cur.lastrowid
        conn.commit()
        return True, f"예약 완료: 예약 ID {reservation_id}"

    except sqlite3.Error as e:
        conn.rollback()
        return False, f"DB 오류: {e}"

    finally:
        conn.close()


def cancel_reservation(reservation_id: int):
    """예약 취소."""
    conn = connect_db()
    cur = conn.cursor()

    cur.execute("SELECT reservation_id FROM reservations WHERE reservation_id = ?;", (reservation_id,))
    row = cur.fetchone()

    if row is None:
        conn.close()
        return False, "예약 취소 실패: 해당 예약 ID를 찾을 수 없습니다."

    cur.execute("DELETE FROM reservations WHERE reservation_id = ?;", (reservation_id,))
    conn.commit()
    conn.close()
    return True, f"예약 ID {reservation_id}번이 취소되었습니다."


def get_all_reservations():
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT reservation_id, room_id, date, day, start_period, end_period, user_name, purpose, created_at
    FROM reservations
    ORDER BY date ASC, start_period ASC;
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def get_available_rooms(date: str, start_period: int, end_period: int, min_capacity: int = 0):
    """
    특정 날짜/교시에 사용 가능한 강의실 목록 반환.
    기존 수업과 실시간 예약을 모두 제외한다.
    """
    try:
        day = get_day_from_date(date)
    except ValueError:
        return []

    conn = connect_db()
    cur = conn.cursor()

    cur.execute("""
    SELECT r.room_id, r.building, r.floor, r.room_name, r.capacity, r.room_type,
           r.location_score, r.accessibility_score, r.priority
    FROM rooms r
    WHERE r.capacity >= ?
      AND NOT EXISTS (
          SELECT 1
          FROM blocked_schedules b
          WHERE b.room_id = r.room_id
            AND b.day = ?
            AND b.period >= ?
            AND b.period < ?
      )
      AND NOT EXISTS (
          SELECT 1
          FROM reservations rv
          WHERE rv.room_id = r.room_id
            AND rv.date = ?
            AND rv.start_period < ?
            AND ? < rv.end_period
      )
    ORDER BY r.priority DESC, r.capacity ASC;
    """, (min_capacity, day, start_period, end_period, date, end_period, start_period))

    rows = cur.fetchall()
    conn.close()
    return rows


# 자료구조: dict
# 알고리즘: DB 조회 결과 캐싱
def build_reservation_cache():
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT room_id, date, start_period, end_period
    FROM reservations
    ORDER BY room_id, date, start_period ASC;
    """)
    rows = cur.fetchall()
    conn.close()

    cache = {}
    for room_id, date, start, end in rows:
        key = (room_id, date)
        cache.setdefault(key, []).append((start, end))

    return cache


# 자료구조: 캐시 리스트
# 알고리즘: 이진 탐색 + 구간 중복 검사
def has_conflict_binary_search(cache: dict, room_id: str, date: str,
                               new_start: int, new_end: int) -> bool:
    intervals = cache.get((room_id, date), [])
    if not intervals:
        return False

    starts = [interval[0] for interval in intervals]
    pos = bisect_left(starts, new_start)

    if pos > 0:
        prev_start, prev_end = intervals[pos - 1]
        if new_start < prev_end and prev_start < new_end:
            return True

    if pos < len(intervals):
        next_start, next_end = intervals[pos]
        if new_start < next_end and next_start < new_end:
            return True

    return False


if __name__ == "__main__":
    init_db()
    print("DB 연결 성공")
    print(f"강의실 수: {len(get_all_rooms())}")
    print("예시 사용 가능 강의실:", get_available_rooms("2026-06-01", 5, 7, 30)[:5])