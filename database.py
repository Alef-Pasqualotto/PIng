import sqlite3
import csv
import io
from pathlib import Path

DB_PATH = Path(__file__).parent / "attendance.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # rows behave like dicts
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create all tables if they don't exist yet."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS classes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id   INTEGER NOT NULL REFERENCES classes(id),
                date       TEXT NOT NULL DEFAULT (date('now')),
                is_open    INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS students (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id     TEXT NOT NULL UNIQUE,
                name          TEXT,
                registered_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS enrollments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id    INTEGER NOT NULL REFERENCES classes(id),
                student_id  INTEGER NOT NULL REFERENCES students(id),
                enrolled_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(class_id, student_id)
            );

            CREATE TABLE IF NOT EXISTS attendance (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id            INTEGER NOT NULL REFERENCES sessions(id),
                student_id            INTEGER NOT NULL REFERENCES students(id),
                present               INTEGER NOT NULL DEFAULT 1,
                checked_in_at         TEXT NOT NULL DEFAULT (datetime('now')),
                overridden_by_teacher INTEGER NOT NULL DEFAULT 0,
                UNIQUE(session_id, student_id)
            );
        """)


# ---------------------------------------------------------------------------
# Classes
# ---------------------------------------------------------------------------

def create_class(name: str) -> sqlite3.Row:
    with get_connection() as conn:
        conn.execute("INSERT INTO classes (name) VALUES (?)", (name,))
        return conn.execute(
            "SELECT * FROM classes WHERE name = ?", (name,)
        ).fetchone()


def get_all_classes() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM classes ORDER BY name"
        ).fetchall()


def get_class(class_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM classes WHERE id = ?", (class_id,)
        ).fetchone()


def delete_class(class_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM classes WHERE id = ?", (class_id,))
        return cur.rowcount > 0
    
def get_class_by_session(session_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT class_id FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def open_session(class_id: int) -> sqlite3.Row:
    """Open a new session for a class. Closes any previously open session first."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE sessions SET is_open = 0 WHERE class_id = ? AND is_open = 1",
            (class_id,)
        )
        conn.execute(
            "INSERT INTO sessions (class_id) VALUES (?)", (class_id,)
        )
        return conn.execute(
            "SELECT * FROM sessions WHERE class_id = ? ORDER BY id DESC LIMIT 1",
            (class_id,)
        ).fetchone()


def close_session(session_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE sessions SET is_open = 0 WHERE id = ?", (session_id,)
        )
        return cur.rowcount > 0


def get_session(session_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()


def get_active_session(class_id: int) -> sqlite3.Row | None:
    """Returns the currently open session for a class, if any."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM sessions WHERE class_id = ? AND is_open = 1",
            (class_id,)
        ).fetchone()


def get_sessions_for_class(class_id: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM sessions WHERE class_id = ? ORDER BY date DESC",
            (class_id,)
        ).fetchall()


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------

def get_or_create_student(device_id: str) -> sqlite3.Row:
    """Returns the student for this device, creating one if it's the first visit."""
    with get_connection() as conn:
        student = conn.execute(
            "SELECT * FROM students WHERE device_id = ?", (device_id,)
        ).fetchone()
        if student is None:
            conn.execute(
                "INSERT INTO students (device_id) VALUES (?)", (device_id,)
            )
            student = conn.execute(
                "SELECT * FROM students WHERE device_id = ?", (device_id,)
            ).fetchone()
        return student


def update_student_name(student_id: int, name: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE students SET name = ? WHERE id = ?", (name, student_id)
        )
        return cur.rowcount > 0


def update_student_device(student_id: int, new_device_id: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE students SET device_id = ? WHERE id = ?",
            (new_device_id, student_id)
        )
        return cur.rowcount > 0


def get_all_students() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM students ORDER BY name, registered_at"
        ).fetchall()


def get_student(student_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM students WHERE id = ?", (student_id,)
        ).fetchone()
    
def get_student_by_device(device_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM students WHERE device_id = ?", (device_id,)
        ).fetchone()


# ---------------------------------------------------------------------------
# Enrollments
# ---------------------------------------------------------------------------

def enroll_student(class_id: int, student_id: int) -> sqlite3.Row | None:
    """Enrolls a student in a class. Silently ignores duplicate enrollments."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO enrollments (class_id, student_id)
            VALUES (?, ?)
            ON CONFLICT(class_id, student_id) DO NOTHING
            """,
            (class_id, student_id)
        )
        return conn.execute(
            "SELECT * FROM enrollments WHERE class_id = ? AND student_id = ?",
            (class_id, student_id)
        ).fetchone()


def unenroll_student(class_id: int, student_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM enrollments WHERE class_id = ? AND student_id = ?",
            (class_id, student_id)
        )
        return cur.rowcount > 0


def get_enrolled_students(class_id: int) -> list[sqlite3.Row]:
    """Returns all students enrolled in a class, ordered by name."""
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                s.id,
                s.name,
                s.device_id,
                s.registered_at,
                e.enrolled_at
            FROM enrollments e
            JOIN students s ON s.id = e.student_id
            WHERE e.class_id = ?
            ORDER BY s.name, s.registered_at
            """,
            (class_id,)
        ).fetchall()


def get_classes_for_student(student_id: int) -> list[sqlite3.Row]:
    """Returns all classes a student is enrolled in."""
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                c.id,
                c.name,
                c.created_at,
                e.enrolled_at
            FROM enrollments e
            JOIN classes c ON c.id = e.class_id
            WHERE e.student_id = ?
            ORDER BY c.name
            """,
            (student_id,)
        ).fetchall()


def is_enrolled(class_id: int, student_id: int) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM enrollments WHERE class_id = ? AND student_id = ?",
            (class_id, student_id)
        ).fetchone()
        return row is not None


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

def record_checkin(session_id: int, student_id: int) -> sqlite3.Row | None:
    """
    Records a check-in.
    If the student already has a record for this session
    (e.g. they refreshed the page), returns the existing one unchanged.
    If the student is not enrolled in the class, it can't check-in
    """
    with get_connection() as conn:
        
        # Verify if the studend is enrolled in the class of the session
        class_found = get_class_by_session(session_id)
        if class_found is None:
            return None
        
        enrolled = is_enrolled(class_found["id"], student_id)
        if not enrolled:
            return None
        

        conn.execute(
            """
            INSERT INTO attendance (session_id, student_id)
            VALUES (?, ?)
            ON CONFLICT(session_id, student_id) DO NOTHING
            """,
            (session_id, student_id)
        )
        return conn.execute(
            "SELECT * FROM attendance WHERE session_id = ? AND student_id = ?",
            (session_id, student_id)
        ).fetchone()


def get_attendance_for_session(session_id: int) -> list[sqlite3.Row]:
    """Returns all attendance records for a session, joined with student info."""
    with get_connection() as conn:
        session = conn.execute(
            "SELECT class_id FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        class_id = session["class_id"] if session else None

        return conn.execute(
            """
            SELECT
                a.id,
                a.present,
                a.checked_in_at,
                a.overridden_by_teacher,
                s.id   AS student_id,
                s.name AS student_name,
                s.device_id,
                CASE WHEN e.student_id IS NOT NULL THEN 1 ELSE 0 END AS is_enrolled
            FROM attendance a
            JOIN students s ON s.id = a.student_id
            LEFT JOIN enrollments e
                ON e.student_id = s.id AND e.class_id = ?
            WHERE a.session_id = ?
            ORDER BY a.checked_in_at
            """,
            (class_id, session_id)
        ).fetchall()


def get_full_session_roster(session_id: int) -> list[dict]:
    """
    Returns the complete picture for a session:
      - Enrolled students who checked in    (present=1)
      - Enrolled students who did NOT check in (present=0)

    Each entry has: attendance_id, student_id, student_name, device_id,
                    present, checked_in_at, is_enrolled,
                    overridden_by_teacher
    """
    with get_connection() as conn:
        session = conn.execute(
            "SELECT class_id FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not session:
            return []
        class_id = session["class_id"]

        # Enrolled students — left join catches those who never checked in
        enrolled = conn.execute(
            """
            SELECT
                a.id              AS attendance_id,
                s.id              AS student_id,
                s.name            AS student_name,
                s.device_id,
                COALESCE(a.present, 0)            AS present,
                a.checked_in_at,
                COALESCE(a.overridden_by_teacher, 0) AS overridden_by_teacher,
                1                 AS is_enrolled
            FROM enrollments e
            JOIN students s ON s.id = e.student_id
            LEFT JOIN attendance a
                ON a.student_id = s.id AND a.session_id = ?
            WHERE e.class_id = ?
            ORDER BY s.name, s.registered_at
            """,
            (session_id, class_id)
        ).fetchall()

        return [dict(r) for r in enrolled]


def override_attendance(attendance_id: int, present: bool) -> bool:
    """Teacher manually marks a student as present or absent."""
    with get_connection() as conn:
        cur = conn.execute(
            """
            UPDATE attendance
            SET present = ?, overridden_by_teacher = 1
            WHERE id = ?
            """,
            (1 if present else 0, attendance_id)
        )
        return cur.rowcount > 0


def export_session_csv(session_id: int) -> str:
    """Returns a CSV string of the full session roster, including absences."""
    roster = get_full_session_roster(session_id)
    session = get_session(session_id)

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "attendance_id",
        "student_id",
        "student_name",
        "device_id",
        "present",
        "is_enrolled",
        "checked_in_at",
        "overridden_by_teacher",
        "session_date",
    ])

    for r in roster:
        writer.writerow([
            r["attendance_id"] or "—",
            r["student_id"],
            r["student_name"] or "—",
            r["device_id"],
            "yes" if r["present"] else "no",
            "yes" if r["is_enrolled"] else "no",
            r["checked_in_at"] or "—",
            "yes" if r["overridden_by_teacher"] else "no",
            session["date"] if session else "—",
        ])

    return output.getvalue()