import sqlite3
import csv
import io
from pathlib import Path
from datetime import datetime, timezone
from app_paths import database_path

DB_PATH = database_path()


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
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
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
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                closed_at  TEXT
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
                checked_out_at        TEXT,
                overridden_by_teacher INTEGER NOT NULL DEFAULT 0,
                UNIQUE(session_id, student_id)
            );

            CREATE TABLE IF NOT EXISTS tests (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id   INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
                name       TEXT NOT NULL,
                max_score  REAL NOT NULL DEFAULT 10.0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(class_id, name)
            );

            CREATE TABLE IF NOT EXISTS grades (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id    INTEGER NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                score      REAL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(test_id, student_id)
            );
        """)
        # Run ALTER TABLE commands for backward compatibility
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN closed_at TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE attendance ADD COLUMN checked_out_at TEXT")
        except sqlite3.OperationalError:
            pass


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
            "UPDATE sessions SET is_open = 0, closed_at = datetime('now') WHERE id = ?", (session_id,)
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
        
        enrolled = is_enrolled(class_found["class_id"], student_id)
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


def calculate_duration(checked_in_at: str | None, checked_out_at: str | None, is_open: int, closed_at: str | None) -> int | None:
    if not checked_in_at:
        return None
    try:
        in_time = datetime.fromisoformat(checked_in_at.replace(" ", "T"))
        if checked_out_at:
            out_time = datetime.fromisoformat(checked_out_at.replace(" ", "T"))
        elif is_open:
            out_time = datetime.now(timezone.utc).replace(tzinfo=None)
        elif closed_at:
            out_time = datetime.fromisoformat(closed_at.replace(" ", "T"))
        else:
            return None
        diff = out_time - in_time
        return max(0, int(diff.total_seconds() // 60))
    except Exception:
        return None


def calculate_percentage(checked_in_at: str | None, checked_out_at: str | None, is_open: int, closed_at: str | None, session_created_at: str) -> int | None:
    if not checked_in_at:
        return None
    try:
        in_time = datetime.fromisoformat(checked_in_at.replace(" ", "T"))
        if checked_out_at:
            out_time = datetime.fromisoformat(checked_out_at.replace(" ", "T"))
        elif is_open:
            out_time = datetime.now(timezone.utc).replace(tzinfo=None)
        elif closed_at:
            out_time = datetime.fromisoformat(closed_at.replace(" ", "T"))
        else:
            return None
        student_seconds = max(0.0, (out_time - in_time).total_seconds())

        session_start = datetime.fromisoformat(session_created_at.replace(" ", "T"))
        if is_open:
            session_end = datetime.now(timezone.utc).replace(tzinfo=None)
        elif closed_at:
            session_end = datetime.fromisoformat(closed_at.replace(" ", "T"))
        else:
            return None
        session_seconds = (session_end - session_start).total_seconds()

        if session_seconds <= 0.0:
            return 100

        percent = (student_seconds / session_seconds) * 100.0
        return min(100, max(0, int(round(percent))))
    except Exception:
        return None


def get_full_session_roster(session_id: int) -> list[dict]:
    """
    Returns the complete picture for a session:
      - Enrolled students who checked in    (present=1)
      - Enrolled students who did NOT check in (present=0)

    Each entry has: attendance_id, student_id, student_name, device_id,
                    present, checked_in_at, checked_out_at, is_enrolled,
                    overridden_by_teacher, duration, duration_percentage
    """
    with get_connection() as conn:
        session = conn.execute(
            "SELECT class_id, is_open, created_at, closed_at FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not session:
            return []
        class_id = session["class_id"]
        is_open = session["is_open"]
        created_at = session["created_at"]
        closed_at = session["closed_at"]

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
                a.checked_out_at,
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

        result = []
        for r in enrolled:
            d = dict(r)
            d["duration"] = calculate_duration(d["checked_in_at"], d["checked_out_at"], is_open, closed_at)
            d["duration_percentage"] = calculate_percentage(d["checked_in_at"], d["checked_out_at"], is_open, closed_at, created_at)
            result.append(d)
        return result


def override_attendance(attendance_id: int, present: int) -> bool:
    """Teacher manually marks a student's attendance status."""
    with get_connection() as conn:
        cur = conn.execute(
            """
            UPDATE attendance
            SET present = ?, overridden_by_teacher = 1
            WHERE id = ?
            """,
            (present, attendance_id)
        )
        return cur.rowcount > 0


def set_student_attendance(session_id: int, student_id: int, present: int) -> sqlite3.Row | None:
    """Creates or updates an attendance row for an enrolled student."""
    class_row = get_class_by_session(session_id)
    if class_row is None or not is_enrolled(class_row["class_id"], student_id):
        return None
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO attendance (
                session_id, student_id, present, overridden_by_teacher
            ) VALUES (?, ?, ?, 1)
            ON CONFLICT(session_id, student_id) DO UPDATE SET
                present = excluded.present,
                overridden_by_teacher = 1
            """,
            (session_id, student_id, present),
        )
        return conn.execute(
            "SELECT * FROM attendance WHERE session_id = ? AND student_id = ?",
            (session_id, student_id),
        ).fetchone()


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
        "checked_out_at",
        "duration_minutes",
        "overridden_by_teacher",
        "session_date",
    ])

    status_map = {
        0: "Ausente",
        1: "Presente",
        2: "Ausência Justificada",
        3: "Presença Falsificada",
    }

    for r in roster:
        present_status = status_map.get(r["present"], "Ausente")
        writer.writerow([
            r["attendance_id"] or "—",
            r["student_id"],
            r["student_name"] or "—",
            r["device_id"],
            present_status,
            "yes" if r["is_enrolled"] else "no",
            r["checked_in_at"] or "—",
            r["checked_out_at"] or "—",
            r["duration"] if r["duration"] is not None else "—",
            "yes" if r["overridden_by_teacher"] else "no",
            session["date"] if session else "—",
        ])

    return output.getvalue()


def record_checkout(session_id: int, student_id: int, checkout: bool) -> bool:
    """Sets the exit time for a student to now, or clears it."""
    with get_connection() as conn:
        if checkout:
            conn.execute(
                """
                INSERT INTO attendance (session_id, student_id, checked_out_at, present, overridden_by_teacher)
                VALUES (?, ?, datetime('now'), 1, 1)
                ON CONFLICT(session_id, student_id) DO UPDATE SET
                    checked_out_at = datetime('now')
                """,
                (session_id, student_id)
            )
        else:
            conn.execute(
                """
                UPDATE attendance
                SET checked_out_at = NULL
                WHERE session_id = ? AND student_id = ?
                """,
                (session_id, student_id)
            )
        return True


def get_student_attendance_history(class_id: int, student_id: int) -> list[dict]:
    """Returns all session dates and presence status for a student in a class, ordered by date."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT 
                s.id AS session_id,
                s.date,
                s.is_open,
                s.created_at,
                s.closed_at,
                a.present,
                a.checked_in_at,
                a.checked_out_at
            FROM sessions s
            LEFT JOIN attendance a ON a.session_id = s.id AND a.student_id = ?
            WHERE s.class_id = ?
            ORDER BY s.date DESC, s.id DESC
            """,
            (student_id, class_id)
        ).fetchall()
        
        result = []
        for r in rows:
            d = dict(r)
            present = d["present"] if d["present"] is not None else 0
            d["present"] = present
            if present == 1:
                d["duration_percentage"] = calculate_percentage(
                    d["checked_in_at"], d["checked_out_at"], d["is_open"], d["closed_at"], d["created_at"]
                )
            else:
                d["duration_percentage"] = None
            result.append(d)
        return result


# ---------------------------------------------------------------------------
# Tests & Grades
# ---------------------------------------------------------------------------

def create_test(class_id: int, name: str, max_score: float = 10.0) -> sqlite3.Row:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO tests (class_id, name, max_score) VALUES (?, ?, ?)",
            (class_id, name.strip(), max_score)
        )
        return conn.execute(
            "SELECT * FROM tests WHERE class_id = ? AND name = ?",
            (class_id, name.strip())
        ).fetchone()


def get_tests_for_class(class_id: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM tests WHERE class_id = ? ORDER BY name",
            (class_id,)
        ).fetchall()


def get_test(test_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM tests WHERE id = ?", (test_id,)
        ).fetchone()


def delete_test(test_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM tests WHERE id = ?", (test_id,))
        return cur.rowcount > 0


def update_test_max_score(test_id: int, new_max_score: float) -> bool:
    with get_connection() as conn:
        # Check if there are any grades higher than the new max_score
        highest = conn.execute(
            "SELECT MAX(score) as max_score FROM grades WHERE test_id = ?",
            (test_id,)
        ).fetchone()
        if highest and highest["max_score"] is not None and highest["max_score"] > new_max_score:
            raise ValueError(f"Existem notas lançadas maiores que {new_max_score}.")
        
        cur = conn.execute(
            "UPDATE tests SET max_score = ? WHERE id = ?",
            (new_max_score, test_id)
        )
        return cur.rowcount > 0


def get_test_grades(test_id: int) -> list[dict]:
    with get_connection() as conn:
        test = conn.execute("SELECT class_id FROM tests WHERE id = ?", (test_id,)).fetchone()
        if not test:
            return []
        class_id = test["class_id"]

        rows = conn.execute(
            """
            SELECT
                s.id AS student_id,
                s.name AS student_name,
                s.device_id,
                g.id AS grade_id,
                g.score
            FROM enrollments e
            JOIN students s ON s.id = e.student_id
            LEFT JOIN grades g ON g.student_id = s.id AND g.test_id = ?
            WHERE e.class_id = ?
            ORDER BY s.name, s.registered_at
            """,
            (test_id, class_id)
        ).fetchall()
        return [dict(r) for r in rows]


def set_student_grade(test_id: int, student_id: int, score: float | None) -> bool:
    with get_connection() as conn:
        if score is None:
            conn.execute(
                "DELETE FROM grades WHERE test_id = ? AND student_id = ?",
                (test_id, student_id)
            )
        else:
            conn.execute(
                """
                INSERT INTO grades (test_id, student_id, score, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(test_id, student_id) DO UPDATE SET
                    score = excluded.score,
                    updated_at = datetime('now')
                """,
                (test_id, student_id, score)
            )
        return True


def merge_students(target_id: int, source_id: int) -> bool:
    if target_id == source_id:
        return False
    with get_connection() as conn:
        # Check that both target and source exist
        target = conn.execute("SELECT id FROM students WHERE id = ?", (target_id,)).fetchone()
        source = conn.execute("SELECT id, device_id FROM students WHERE id = ?", (source_id,)).fetchone()
        if not target or not source:
            return False
            
        source_device_id = source["device_id"]
        
        # 1. Consolidate enrollments: Insert or ignore enrollments for target_id using classes source_id is enrolled in
        conn.execute(
            """
            INSERT OR IGNORE INTO enrollments (class_id, student_id)
            SELECT class_id, ? FROM enrollments WHERE student_id = ?
            """,
            (target_id, source_id)
        )
        conn.execute("DELETE FROM enrollments WHERE student_id = ?", (source_id,))
        
        # 2. Consolidate attendance logs
        source_atts = conn.execute("SELECT * FROM attendance WHERE student_id = ?", (source_id,)).fetchall()
        for sa in source_atts:
            # Check if target already has an attendance record for this session
            ta = conn.execute(
                "SELECT * FROM attendance WHERE session_id = ? AND student_id = ?",
                (sa["session_id"], target_id)
            ).fetchone()
            if ta:
                # If target was absent (present = 0) and source was present (1, 2, 3), upgrade target's record
                if ta["present"] == 0 and sa["present"] != 0:
                    conn.execute(
                        """
                        UPDATE attendance
                        SET present = ?, checked_in_at = ?, checked_out_at = ?, overridden_by_teacher = ?
                        WHERE id = ?
                        """,
                        (sa["present"], sa["checked_in_at"], sa["checked_out_at"], sa["overridden_by_teacher"], ta["id"])
                    )
            else:
                # Target has no attendance record, move source's record to target
                conn.execute("UPDATE attendance SET student_id = ? WHERE id = ?", (target_id, sa["id"]))
        conn.execute("DELETE FROM attendance WHERE student_id = ?", (source_id,))
        
        # 3. Consolidate grades
        source_grades = conn.execute("SELECT * FROM grades WHERE student_id = ?", (source_id,)).fetchall()
        for sg in source_grades:
            tg = conn.execute(
                "SELECT * FROM grades WHERE test_id = ? AND student_id = ?",
                (sg["test_id"], target_id)
            ).fetchone()
            if tg:
                # If both have grades, resolve to the higher score
                new_score = None
                if tg["score"] is not None and sg["score"] is not None:
                    new_score = max(tg["score"], sg["score"])
                elif tg["score"] is not None:
                    new_score = tg["score"]
                else:
                    new_score = sg["score"]
                conn.execute(
                    "UPDATE grades SET score = ?, updated_at = datetime('now') WHERE id = ?",
                    (new_score, tg["id"])
                )
            else:
                # Move grade
                conn.execute("UPDATE grades SET student_id = ? WHERE id = ?", (target_id, sg["id"]))
        conn.execute("DELETE FROM grades WHERE student_id = ?", (source_id,))
        
        # 4. Delete the source student record (releasing the unique constraint on device_id)
        conn.execute("DELETE FROM students WHERE id = ?", (source_id,))
        
        # 5. Assign the source student's device_id to the target student
        conn.execute("UPDATE students SET device_id = ? WHERE id = ?", (source_device_id, target_id))
        
        return True
