# ClassFit 데이터 전처리 결과 v2

## 원본 파일
- 파일명: 시간표 및 강의계획서 목록.xlsx
- 시트명: empty
- 원본 컬럼: 학수번호, 강의시간, 강의실, 정원

## 전처리 요약
- 원본 강좌 행 수: 266
- 강의실-강좌 정규화 행 수: 301
- 추출된 고유 강의실 수: 40
- 기존 수업 차단 시간표 행 수: 896
- 동일 강의실/요일/교시 중복 슬롯 수: 82
- 파싱 오류 수: 0
- 실시간 예약 데이터 수: 0개, reservations 테이블은 빈 상태로 생성

## 생성 파일
- classfit.db: SQLite DB
- database.py: DB 접근 및 예약 신청/취소 코드
- schema.sql: SQLite 테이블 생성 SQL
- data/rooms.csv: 강의실 고정 데이터
- data/blocked_schedules.csv: 기존 수업으로 예약 불가능한 시간표
- data/lecture_rooms_normalized.csv: 원본 강좌-강의실 정규화 데이터
- data/blocked_conflicts.csv: 같은 강의실/요일/교시에 여러 수업이 있는 원본상 중복 슬롯 목록
- data/source_errors.csv: 파싱 실패 데이터
- data/reservations_empty.csv: 빈 실시간 예약 테이블 형식

## 테이블 설명

### rooms
강의실 고정 정보 테이블.
- capacity는 해당 강의실이 원본 시간표에서 가진 정원 값 중 최댓값으로 추정했다.
- equipment는 모든 강의실에 기본값 `projector,computer,whiteboard`를 넣었다.
- room_type은 capacity 기준으로 자동 분류했다.

### blocked_schedules
기존 수업 시간표를 요일/교시 단위로 분해한 테이블.
예약 기능에서 이 테이블과 겹치면 예약 불가로 처리한다.

### reservations
사용자가 프로그램 실행 중 예약하면 INSERT되는 실시간 예약 테이블.
초기 상태는 비어 있다.

## 예약 방식
이 데이터는 실제 시간이 아니라 `요일 + 교시` 기반이다.
예를 들어 `2026-06-01`이 월요일이면, `start_period=5`, `end_period=7` 예약은 월 5~6교시 예약으로 처리된다.
구간은 `[start_period, end_period)` 방식이다.

## 팀원 A가 공유할 핵심 함수
- init_db()
- get_all_rooms()
- get_room(room_id)
- get_blocked_by_room_day(room_id, day)
- get_available_rooms(date, start_period, end_period, min_capacity)
- add_reservation(room_id, date, start_period, end_period, user_name, purpose)
- cancel_reservation(reservation_id)
- get_all_reservations()
- build_reservation_cache()
- has_conflict_binary_search(cache, room_id, date, new_start, new_end)
