# ClassFit Streamlit App v3.2

강의실 기존 수업 시간표와 실시간 예약 데이터를 함께 검사하는 Streamlit 기반 강의실 예약 시스템입니다.

## 핵심 기능

- 대시보드
- 추천 기반 예약
- 강의실 직접 선택 예약
- 반복 예약
- 실시간 현황판
- 빈 강의실 찾기
- 예약 조회/취소
- DB 데이터 관리

## v3 수정 사항

- `데이터/알고리즘 설명` 페이지 제거
- `강의실 상세 분석` 페이지 제거
- 예약/취소/현황/추천 조회에서 Streamlit 캐시 제거
- 예약 성공/취소 후 즉시 `st.rerun()`으로 전체 화면 동기화
- 추천 결과를 세션에 고정하지 않고 DB 기준으로 매번 재계산
- SQLite `BEGIN IMMEDIATE` 트랜잭션으로 동시 예약 충돌 방지
- SQLite WAL 모드와 busy timeout 적용
- 예약 UI를 `추천으로 예약`, `강의실 직접 선택`, `반복 예약` 탭으로 통합


## v3.2 색상/가독성 수정 사항

- Streamlit 테마를 라이트 모드로 고정하는 `.streamlit/config.toml` 추가
- 앱 전체 배경색을 `#F8FAFC`, 패널/카드 배경을 흰색으로 통일
- 제목, 본문, 캡션, 사이드바, 입력창의 글씨색 대비 보정
- selectbox/input/date input의 배경색과 텍스트 색상 충돌 수정
- 상태 배지 색상 재정리: 가능/기존 수업/실시간 예약 구분 유지

## 실행 방법

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 파일 구조

```text
classfit_streamlit_app_v3_1/
├── .streamlit/
│   └── config.toml

├── app.py
├── database.py
├── classfit.db
├── requirements.txt
├── schema.sql
└── data/
    ├── rooms.csv
    ├── blocked_schedules.csv
    ├── lecture_rooms_normalized.csv
    ├── blocked_conflicts.csv
    ├── source_errors.csv
    └── reservations_empty.csv
```

## DB 구조

- `rooms`: 강의실 고정 데이터
- `blocked_schedules`: 기존 수업 때문에 예약 불가능한 요일/교시 데이터
- `reservations`: 사용자가 실시간으로 등록한 예약 데이터

## 배포 주의사항

SQLite는 시연용 프로토타입에는 충분하지만, Streamlit Community Cloud 같은 환경에서는 파일 저장소가 영구 DB처럼 동작하지 않을 수 있습니다. 실제 운영용으로 확장하려면 Supabase/PostgreSQL 같은 외부 DB로 교체하는 것이 좋습니다.


## v3.2 변경 사항

- 사이드바에서 `다크 모드`와 `라이트 모드`를 선택할 수 있습니다.
- 기존 v3.1의 라이트 테마 고정을 제거했습니다.
- 배경색, 글씨색, 입력창, 사이드바, 카드, 상태 배지 색상을 CSS 변수 기반으로 정리했습니다.
- DB 구조와 예약 데이터는 변경하지 않았습니다.
