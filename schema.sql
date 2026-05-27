PRAGMA foreign_keys = ON;

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