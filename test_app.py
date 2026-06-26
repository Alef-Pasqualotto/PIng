"""
test_app.py — Test suite for the attendance app.

Tests are grouped into:
  - database layer (pure function tests against an in-memory / temp DB)
  - API layer (FastAPI TestClient, exercises all routes)

Run with:
    pytest test_app.py -v
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures — isolated database per test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """
    Each test gets its own fresh SQLite file.
    We monkeypatch database.DB_PATH before importing anything that touches it.
    """
    db_file = tmp_path / "test_attendance.db"
    import database
    import settings
    monkeypatch.setattr(database, "DB_PATH", db_file)
    monkeypatch.setattr(settings, "config_path", lambda: tmp_path / "config.json")
    database.init_db()
    yield db_file


@pytest.fixture()
def client(isolated_db):
    """FastAPI TestClient with hotspot creation/teardown mocked out."""
    with patch("hotspot.create_hotspot"), patch("hotspot.stop_hotspot"):
        import main
        # Re-trigger lifespan manually: init_db already done by isolated_db
        with TestClient(main.app) as c:
            yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_class(name="Math 3A"):
    import database
    return database.create_class(name)


def make_student(device_id="device-test"):
    import database
    return database.get_or_create_student(device_id)


def make_enrolled_student(class_id, device_id="device-enrolled"):
    import database
    s = database.get_or_create_student(device_id)
    database.enroll_student(class_id, s["id"])
    return s


# ===========================================================================
# DATABASE LAYER
# ===========================================================================

class TestClasses:
    def test_create_and_get(self):
        import database
        cls = database.create_class("Math 3A")
        assert cls["name"] == "Math 3A"
        assert cls["id"] is not None

        fetched = database.get_class(cls["id"])
        assert fetched["id"] == cls["id"]

    def test_get_all_classes_sorted(self):
        import database
        database.create_class("Zebra")
        database.create_class("Alpha")
        print("a")
        names = [c["name"] for c in database.get_all_classes()]
        assert names == sorted(names)

    def test_delete_class(self):
        import database
        cls = database.create_class("ToDelete")
        deleted = database.delete_class(cls["id"])
        assert deleted is True
        assert database.get_class(cls["id"]) is None

    def test_delete_nonexistent_class(self):
        import database
        assert database.delete_class(9999) is False

    def test_duplicate_class_name_raises(self):
        import database, sqlite3
        database.create_class("Dup")
        with pytest.raises(sqlite3.IntegrityError):
            database.create_class("Dup")

    def test_get_class_by_session(self):
        import database
        cls = make_class()
        session = database.open_session(cls["id"])
        row = database.get_class_by_session(session["id"])
        assert row["class_id"] == cls["id"]

    def test_get_class_by_session_nonexistent(self):
        import database
        assert database.get_class_by_session(9999) is None


class TestSessions:
    def test_open_session(self):
        import database
        cls = make_class()
        session = database.open_session(cls["id"])
        assert session["class_id"] == cls["id"]
        assert session["is_open"] == 1

    def test_opening_new_session_closes_previous(self):
        import database
        cls = make_class()
        first = database.open_session(cls["id"])
        second = database.open_session(cls["id"])
        # first must now be closed
        assert database.get_session(first["id"])["is_open"] == 0
        assert database.get_session(second["id"])["is_open"] == 1

    def test_close_session(self):
        import database
        cls = make_class()
        session = database.open_session(cls["id"])
        assert database.close_session(session["id"]) is True
        assert database.get_session(session["id"])["is_open"] == 0

    def test_close_nonexistent_session(self):
        import database
        assert database.close_session(9999) is False

    def test_get_active_session(self):
        import database
        cls = make_class()
        session = database.open_session(cls["id"])
        active = database.get_active_session(cls["id"])
        assert active["id"] == session["id"]

    def test_no_active_session_after_close(self):
        import database
        cls = make_class()
        session = database.open_session(cls["id"])
        database.close_session(session["id"])
        assert database.get_active_session(cls["id"]) is None

    def test_get_sessions_for_class(self):
        import database
        cls = make_class()
        database.open_session(cls["id"])
        database.open_session(cls["id"])
        sessions = database.get_sessions_for_class(cls["id"])
        assert len(sessions) == 2


class TestStudents:
    def test_get_or_create_creates_new(self):
        import database
        s = database.get_or_create_student("new-device")
        assert s["device_id"] == "new-device"
        assert s["id"] is not None

    def test_get_or_create_returns_existing(self):
        import database
        s1 = database.get_or_create_student("same-device")
        s2 = database.get_or_create_student("same-device")
        assert s1["id"] == s2["id"]

    def test_update_name(self):
        import database
        s = make_student()
        assert database.update_student_name(s["id"], "Alice") is True
        assert database.get_student(s["id"])["name"] == "Alice"

    def test_update_name_nonexistent(self):
        import database
        assert database.update_student_name(9999, "Ghost") is False

    def test_update_device(self):
        import database
        s = make_student("old-device")
        assert database.update_student_device(s["id"], "new-device") is True
        assert database.get_student(s["id"])["device_id"] == "new-device"

    def test_get_all_students(self):
        import database
        database.get_or_create_student("d1")
        database.get_or_create_student("d2")
        assert len(database.get_all_students()) == 2

    def test_get_student_by_device(self):
        import database
        s = make_student("find-me")
        found = database.get_student_by_device("find-me")
        assert found["id"] == s["id"]

    def test_get_student_by_device_missing(self):
        import database
        assert database.get_student_by_device("no-such-device") is None


class TestEnrollments:
    def test_enroll_and_is_enrolled(self):
        import database
        cls = make_class()
        s = make_student()
        database.enroll_student(cls["id"], s["id"])
        assert database.is_enrolled(cls["id"], s["id"]) is True

    def test_not_enrolled(self):
        import database
        cls = make_class()
        s = make_student()
        assert database.is_enrolled(cls["id"], s["id"]) is False

    def test_duplicate_enrollment_is_silent(self):
        import database
        cls = make_class()
        s = make_student()
        database.enroll_student(cls["id"], s["id"])
        # Should not raise
        database.enroll_student(cls["id"], s["id"])
        enrolled = database.get_enrolled_students(cls["id"])
        assert len(enrolled) == 1

    def test_unenroll(self):
        import database
        cls = make_class()
        s = make_student()
        database.enroll_student(cls["id"], s["id"])
        assert database.unenroll_student(cls["id"], s["id"]) is True
        assert database.is_enrolled(cls["id"], s["id"]) is False

    def test_unenroll_nonexistent(self):
        import database
        assert database.unenroll_student(1, 9999) is False

    def test_get_enrolled_students(self):
        import database
        cls = make_class()
        s1 = database.get_or_create_student("d-a")
        s2 = database.get_or_create_student("d-b")
        database.enroll_student(cls["id"], s1["id"])
        database.enroll_student(cls["id"], s2["id"])
        enrolled = database.get_enrolled_students(cls["id"])
        assert len(enrolled) == 2

    def test_get_classes_for_student(self):
        import database
        c1 = database.create_class("C1")
        c2 = database.create_class("C2")
        s = make_student()
        database.enroll_student(c1["id"], s["id"])
        database.enroll_student(c2["id"], s["id"])
        classes = database.get_classes_for_student(s["id"])
        assert len(classes) == 2


class TestAttendance:
    def test_record_checkin_enrolled_student(self):
        import database
        cls = make_class()
        s = make_enrolled_student(cls["id"])
        session = database.open_session(cls["id"])
        record = database.record_checkin(session["id"], s["id"])
        assert record is not None
        assert record["present"] == 1

    def test_record_checkin_unenrolled_returns_none(self):
        import database
        cls = make_class()
        session = database.open_session(cls["id"])
        s = make_student("not-enrolled")  # no enrollment
        record = database.record_checkin(session["id"], s["id"])
        assert record is None

    def test_record_checkin_is_idempotent(self):
        import database
        cls = make_class()
        s = make_enrolled_student(cls["id"])
        session = database.open_session(cls["id"])
        r1 = database.record_checkin(session["id"], s["id"])
        r2 = database.record_checkin(session["id"], s["id"])
        assert r1["id"] == r2["id"]

    def test_record_checkin_existing_absent_becomes_present(self):
        import database
        cls = make_class()
        s = make_enrolled_student(cls["id"])
        session = database.open_session(cls["id"])
        absent = database.set_student_attendance(session["id"], s["id"], 0)
        checked_in = database.record_checkin(session["id"], s["id"])
        assert checked_in["id"] == absent["id"]
        assert checked_in["present"] == 1
        assert checked_in["overridden_by_teacher"] == 0

    def test_checkin_invalid_session_returns_none(self):
        import database
        s = make_student()
        record = database.record_checkin(9999, s["id"])
        assert record is None

    def test_override_attendance_present(self):
        import database
        cls = make_class()
        s = make_enrolled_student(cls["id"])
        session = database.open_session(cls["id"])
        record = database.record_checkin(session["id"], s["id"])
        assert database.override_attendance(record["id"], present=False) is True
        # Fetch updated record
        updated = database.get_attendance_for_session(session["id"])[0]
        assert updated["present"] == 0
        assert updated["overridden_by_teacher"] == 1

    def test_override_attendance_absent_to_present(self):
        import database
        cls = make_class()
        s = make_enrolled_student(cls["id"])
        session = database.open_session(cls["id"])
        record = database.record_checkin(session["id"], s["id"])
        database.override_attendance(record["id"], present=False)
        database.override_attendance(record["id"], present=True)
        updated = database.get_attendance_for_session(session["id"])[0]
        assert updated["present"] == 1

    def test_override_nonexistent_attendance(self):
        import database
        assert database.override_attendance(9999, True) is False

    def test_teacher_can_mark_absent_student_present(self):
        import database
        cls = make_class()
        student = make_enrolled_student(cls["id"])
        session = database.open_session(cls["id"])
        record = database.set_student_attendance(session["id"], student["id"], True)
        assert record["present"] == 1
        assert record["overridden_by_teacher"] == 1

    def test_get_full_session_roster_absent_students_included(self):
        import database
        cls = make_class()
        present_s = make_enrolled_student(cls["id"], "d-present")
        absent_s  = make_enrolled_student(cls["id"], "d-absent")
        session = database.open_session(cls["id"])
        database.record_checkin(session["id"], present_s["id"])
        # absent_s never checks in

        roster = database.get_full_session_roster(session["id"])
        assert len(roster) == 2
        statuses = {r["student_id"]: r["present"] for r in roster}
        assert statuses[present_s["id"]] == 1
        assert statuses[absent_s["id"]] == 0

    def test_get_full_session_roster_empty_session(self):
        import database
        cls = make_class()
        session = database.open_session(cls["id"])
        # No enrollments at all
        roster = database.get_full_session_roster(session["id"])
        assert roster == []

    def test_get_full_session_roster_nonexistent_session(self):
        import database
        assert database.get_full_session_roster(9999) == []


class TestCSVExport:
    def test_export_contains_header(self):
        import database
        cls = make_class()
        session = database.open_session(cls["id"])
        csv_text = database.export_session_csv(session["id"])
        assert "student_name" in csv_text
        assert "present" in csv_text

    def test_export_rows_match_roster(self):
        import database
        cls = make_class()
        s1 = make_enrolled_student(cls["id"], "d1")
        s2 = make_enrolled_student(cls["id"], "d2")
        session = database.open_session(cls["id"])
        database.record_checkin(session["id"], s1["id"])
        # s2 absent
        csv_text = database.export_session_csv(session["id"])
        lines = [l for l in csv_text.strip().splitlines() if l]
        assert len(lines) == 3  # header + 2 students

    def test_export_present_values(self):
        import database
        cls = make_class()
        s = make_enrolled_student(cls["id"])
        session = database.open_session(cls["id"])
        database.record_checkin(session["id"], s["id"])
        csv_text = database.export_session_csv(session["id"])
        assert "yes" in csv_text  # present=yes


# ===========================================================================
# API LAYER
# ===========================================================================

class TestStudentRoutes:
    def test_student_page_returns_html(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_public_classes(self, client):
        make_class("Turma pública")
        r = client.get("/public/classes")
        assert r.status_code == 200
        assert r.json()[0]["name"] == "Turma pública"

    def test_checkin_success(self, client):
        import database
        cls = make_class()
        s = make_enrolled_student(cls["id"], "api-device")
        database.open_session(cls["id"])
        r = client.post("/checkin", json={"device_id": "api-device", "class_id": cls["id"]})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["is_enrolled"] is True
        assert data["already_present"] is False

    def test_checkin_when_already_present_returns_visual_state(self, client):
        import database
        cls = make_class()
        make_enrolled_student(cls["id"], "already-device")
        database.open_session(cls["id"])
        first = client.post("/checkin", json={"device_id": "already-device", "class_id": cls["id"]})
        second = client.post("/checkin", json={"device_id": "already-device", "class_id": cls["id"]})
        assert first.status_code == 200
        assert first.json()["already_present"] is False
        assert second.status_code == 200
        assert second.json()["already_present"] is True

    def test_checkin_publishes_roster_update(self, client):
        import attendance_events
        import database
        cls = make_class()
        make_enrolled_student(cls["id"], "pub-device")
        session = database.open_session(cls["id"])
        subscriber = attendance_events.subscribe(session["id"])
        try:
            r = client.post("/checkin", json={"device_id": "pub-device", "class_id": cls["id"]})
            assert r.status_code == 200
            assert "student_checkin" in subscriber.get(timeout=1)
        finally:
            attendance_events.unsubscribe(session["id"], subscriber)

    def test_checkin_no_open_session(self, client):
        import database
        cls = make_class()
        make_enrolled_student(cls["id"], "dev-no-session")
        # No session opened
        r = client.post("/checkin", json={"device_id": "dev-no-session", "class_id": cls["id"]})
        assert r.status_code == 400

    def test_checkin_creates_student_on_first_visit(self, client):
        import database
        cls = make_class()
        s = database.get_or_create_student("brand-new")
        database.enroll_student(cls["id"], s["id"])
        database.open_session(cls["id"])
        r = client.post("/checkin", json={"device_id": "brand-new", "class_id": cls["id"]})
        assert r.status_code == 200

    def test_session_status_open(self, client):
        import database
        cls = make_class()
        database.open_session(cls["id"])
        r = client.get(f"/session/status?class_id={cls['id']}")
        assert r.status_code == 200
        assert r.json()["is_open"] is True

    def test_session_status_closed(self, client):
        import database
        cls = make_class()
        r = client.get(f"/session/status?class_id={cls['id']}")
        assert r.json()["is_open"] is False


class TestTeacherClassRoutes:
    def test_teacher_page(self, client):
        r = client.get("/teacher")
        assert r.status_code == 200

    def test_list_classes_empty(self, client):
        r = client.get("/classes")
        assert r.json() == []

    def test_create_class(self, client):
        r = client.post("/classes", json={"name": "Bio 1A"})
        assert r.status_code == 201
        assert r.json()["name"] == "Bio 1A"

    def test_create_class_duplicate_name(self, client):
        client.post("/classes", json={"name": "Dup"})    
        r = client.post("/classes", json={"name": "Dup"})
        assert r.status_code == 409

    def test_delete_class(self, client):
        r = client.post("/classes", json={"name": "ToGo"})
        class_id = r.json()["id"]
        d = client.delete(f"/classes/{class_id}")
        assert d.status_code == 204

    def test_delete_nonexistent_class(self, client):
        r = client.delete("/classes/9999")
        assert r.status_code == 404


class TestTeacherSessionRoutes:
    def test_open_session(self, client):
        import database
        cls = make_class()
        r = client.post("/session/open", json={"class_id": cls["id"]})
        assert r.status_code == 201
        assert r.json()["is_open"] == 1

    def test_open_session_nonexistent_class(self, client):
        r = client.post("/session/open", json={"class_id": 9999})
        assert r.status_code == 404

    def test_close_session(self, client):
        import database
        cls = make_class()
        session = database.open_session(cls["id"])
        r = client.post("/session/close", json={"session_id": session["id"]})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_close_nonexistent_session(self, client):
        r = client.post("/session/close", json={"session_id": 9999})
        assert r.status_code == 404

    def test_session_roster(self, client):
        import database
        cls = make_class()
        make_enrolled_student(cls["id"], "d-roster")
        session = database.open_session(cls["id"])
        r = client.get(f"/session/{session['id']}/roster")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_session_roster_nonexistent(self, client):
        r = client.get("/session/9999/roster")
        assert r.status_code == 404

    def test_class_sessions_list(self, client):
        import database
        cls = make_class()
        database.open_session(cls["id"])
        r = client.get(f"/classes/{cls['id']}/sessions")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_class_sessions_nonexistent_class(self, client):
        r = client.get("/classes/9999/sessions")
        assert r.status_code == 404


class TestAttendanceOverrideRoute:
    def test_override_present_to_absent(self, client):
        import database
        cls = make_class()
        s = make_enrolled_student(cls["id"])
        session = database.open_session(cls["id"])
        record = database.record_checkin(session["id"], s["id"])
        r = client.patch(f"/attendance/{record['id']}", json={"present": 0})
        assert r.status_code == 200
        assert r.json()["present"] == 0

    def test_override_nonexistent(self, client):
        r = client.patch("/attendance/9999", json={"present": 1})
        assert r.status_code == 404

    def test_create_override_for_absent_student(self, client):
        import database
        cls = make_class()
        student = make_enrolled_student(cls["id"])
        session = database.open_session(cls["id"])
        r = client.put(
            f"/session/{session['id']}/students/{student['id']}/attendance",
            json={"present": 1},
        )
        assert r.status_code == 200
        assert r.json()["present"] == 1


class TestNetworkRoutes:
    def test_network_status(self, client):
        with patch("network_service.compatibility", return_value={"supported": True, "detail": "ok"}), \
             patch("hotspot.get_local_ip", return_value="192.168.1.10"):
            r = client.get("/api/network/status")
        assert r.status_code == 200
        assert r.json()["student_url"].startswith("http://192.168.1.10:")

    def test_network_start_failure_is_reported(self, client):
        with patch("network_service.start", side_effect=RuntimeError("sem suporte")):
            r = client.post("/api/network/start")
        assert r.status_code == 503
        assert "sem suporte" in r.json()["detail"]

    def test_network_start_stops_before_netsh_when_unsupported(self):
        with patch("network_service.compatibility", return_value={
            "supported": False,
            "wireless_present": False,
            "reason": "no_wireless_adapter",
            "detail": "Nenhum adaptador Wi-Fi está disponível.",
        }), patch("hotspot.create_hotspot") as create:
            with pytest.raises(RuntimeError, match="Nenhum adaptador"):
                import network_service
                network_service.start()
        create.assert_not_called()

    def test_network_qr_is_png(self, client):
        with patch("network_service.status", return_value={"student_url": "http://192.168.1.10:8000"}):
            r = client.get("/api/network/qr")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"


class TestAdminAccess:
    def test_remote_client_cannot_use_teacher_api(self, isolated_db):
        import main
        with TestClient(main.app, client=("192.168.1.50", 50000)) as remote:
            assert remote.get("/classes").status_code == 403
            assert remote.get("/teacher").status_code == 403

    def test_remote_client_can_use_student_routes(self, isolated_db):
        import main
        with TestClient(main.app, client=("192.168.1.50", 50000)) as remote:
            assert remote.get("/").status_code == 200
            assert remote.get("/public/classes").status_code == 200


class TestDebugLogging:
    def test_log_info_is_local_and_returns_path(self, client):
        r = client.get("/api/debug/log-info")
        assert r.status_code == 200
        assert r.json()["path"].endswith("ping.log")

    def test_log_info_is_blocked_remotely(self, isolated_db):
        import main
        with TestClient(main.app, client=("192.168.1.50", 50000)) as remote:
            assert remote.get("/api/debug/log-info").status_code == 403


class TestCSVExportRoute:
    def test_export_returns_csv(self, client):
        import database
        cls = make_class()
        make_enrolled_student(cls["id"])
        session = database.open_session(cls["id"])
        r = client.get(f"/session/{session['id']}/export")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "student_name" in r.text

    def test_export_nonexistent_session(self, client):
        r = client.get("/session/9999/export")
        assert r.status_code == 404


class TestEnrollmentRoutes:
    def test_list_enrolled_students(self, client):
        import database
        cls = make_class()
        make_enrolled_student(cls["id"], "d-enroll")
        r = client.get(f"/classes/{cls['id']}/students")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_list_enrolled_students_nonexistent_class(self, client):
        r = client.get("/classes/9999/students")
        assert r.status_code == 404

    def test_enroll_student(self, client):
        import database
        cls = make_class()
        s = make_student()
        r = client.post("/enrollments", json={"class_id": cls["id"], "student_id": s["id"]})
        assert r.status_code == 201

    def test_unenroll_student(self, client):
        import database
        cls = make_class()
        s = make_enrolled_student(cls["id"])
        r = client.request(
            "DELETE", "/enrollments",
            json={"class_id": cls["id"], "student_id": s["id"]}
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_unenroll_nonexistent(self, client):
        r = client.request("DELETE", "/enrollments", json={"class_id": 1, "student_id": 9999})
        assert r.status_code == 404


class TestStudentManagementRoutes:
    def test_list_students(self, client):
        import database
        make_student("list-d1")
        make_student("list-d2")
        r = client.get("/students")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_update_student_name(self, client):
        import database
        s = make_student()
        r = client.patch(f"/students/{s['id']}/name", json={"name": "New Name"})
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"

    def test_update_student_name_nonexistent(self, client):
        r = client.patch("/students/9999/name", json={"name": "Ghost"})
        assert r.status_code == 404

    def test_update_student_device(self, client):
        import database
        s = make_student("old-dev")
        r = client.patch(f"/students/{s['id']}/device", json={"device_id": "new-dev"})
        assert r.status_code == 200
        assert r.json()["device_id"] == "new-dev"

    def test_update_student_device_missing_body(self, client):
        import database
        s = make_student()
        r = client.patch(f"/students/{s['id']}/device", json={})
        assert r.status_code == 400

    def test_update_student_device_nonexistent(self, client):
        r = client.patch("/students/9999/device", json={"device_id": "x"})
        assert r.status_code == 404


class TestGradesDatabase:
    def test_create_and_get_test(self):
        import database
        cls = make_class()
        t = database.create_test(cls["id"], "Prova 1", 10.0)
        assert t["name"] == "Prova 1"
        assert t["max_score"] == 10.0
        
        tests = database.get_tests_for_class(cls["id"])
        assert len(tests) == 1
        assert tests[0]["id"] == t["id"]

    def test_set_and_get_student_grade(self):
        import database
        cls = make_class()
        s = make_enrolled_student(cls["id"])
        t = database.create_test(cls["id"], "Prova 1", 10.0)
        
        # Set grade
        assert database.set_student_grade(t["id"], s["id"], 8.5) is True
        
        # Get grades
        grades = database.get_test_grades(t["id"])
        assert len(grades) == 1
        assert grades[0]["student_id"] == s["id"]
        assert grades[0]["score"] == 8.5
        
        # Clear grade
        assert database.set_student_grade(t["id"], s["id"], None) is True
        grades = database.get_test_grades(t["id"])
        assert grades[0]["score"] is None

    def test_update_test_max_score(self):
        import database
        cls = make_class()
        s = make_enrolled_student(cls["id"])
        t = database.create_test(cls["id"], "Prova 1", 10.0)
        
        # Update max score
        assert database.update_test_max_score(t["id"], 15.0) is True
        assert database.get_test(t["id"])["max_score"] == 15.0
        
        # Set a grade equal to 12.0
        database.set_student_grade(t["id"], s["id"], 12.0)
        
        # Trying to update max score to 10.0 should fail because grade 12.0 exists
        try:
            database.update_test_max_score(t["id"], 10.0)
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert "Existem notas" in str(e)


class TestGradesAPIRoutes:
    def test_create_and_list_tests(self, client):
        import database
        cls = make_class()
        
        # Create test
        r = client.post("/tests", json={"class_id": cls["id"], "name": "Prova A", "max_score": 10.0})
        assert r.status_code == 201
        
        # List tests
        r = client.get(f"/classes/{cls['id']}/tests")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["name"] == "Prova A"

    def test_set_student_grade_api(self, client):
        import database
        cls = make_class()
        s = make_enrolled_student(cls["id"])
        t = database.create_test(cls["id"], "Prova A", 10.0)
        
        # Set grade via API
        r = client.put(f"/tests/{t['id']}/students/{s['id']}/grade", json={"score": 9.5})
        assert r.status_code == 200
        
        # Get grades via API
        r = client.get(f"/tests/{t['id']}/grades")
        assert r.status_code == 200
        assert r.json()[0]["score"] == 9.5

    def test_set_grade_exceeds_max(self, client):
        import database
        cls = make_class()
        s = make_enrolled_student(cls["id"])
        t = database.create_test(cls["id"], "Prova A", 10.0)
        
        # Exceeds max
        r = client.put(f"/tests/{t['id']}/students/{s['id']}/grade", json={"score": 10.5})
        assert r.status_code == 400
        assert "nota" in r.text

    def test_update_test_max_score_api(self, client):
        import database
        cls = make_class()
        s = make_enrolled_student(cls["id"])
        t = database.create_test(cls["id"], "Prova A", 10.0)
        
        # Update max score via API
        r = client.patch(f"/tests/{t['id']}/max-score", json={"max_score": 15.0})
        assert r.status_code == 200
        assert database.get_test(t['id'])["max_score"] == 15.0
        
        # Set grade 12.0 via API
        r = client.put(f"/tests/{t['id']}/students/{s['id']}/grade", json={"score": 12.0})
        assert r.status_code == 200
        
        # Update max score to 10.0 should fail with 400
        r = client.patch(f"/tests/{t['id']}/max-score", json={"max_score": 10.0})
        assert r.status_code == 400
        assert "Existem notas" in r.text


class TestStudentMerge:
    def test_database_merge_students_logic(self):
        import database
        # 1. Create classes
        c1 = database.create_class("Math")
        c2 = database.create_class("Science")

        # 2. Create students
        target = database.get_or_create_student("device-target")
        database.update_student_name(target["id"], "Target Student")
        source = database.get_or_create_student("device-source")
        database.update_student_name(source["id"], "Source Student")

        # Enroll target in Math, source in Science (and both in Math so there's duplicate enrollment to test consolidation)
        database.enroll_student(c1["id"], target["id"])
        database.enroll_student(c1["id"], source["id"])
        database.enroll_student(c2["id"], source["id"])

        # 3. Create tests & grades
        t1 = database.create_test(c1["id"], "Test Math", 10.0)
        t2 = database.create_test(c2["id"], "Test Science", 10.0)

        # Target gets 7.0 on Test Math, Source gets 9.0
        database.set_student_grade(t1["id"], target["id"], 7.0)
        database.set_student_grade(t1["id"], source["id"], 9.0)
        # Source gets 8.0 on Test Science, Target has no grade
        database.set_student_grade(t2["id"], source["id"], 8.0)

        # 4. Create sessions & attendance
        s1 = database.open_session(c1["id"])
        # For session 1, target checks in, then is overridden by teacher to 0 (absent)
        target_att = database.record_checkin(s1["id"], target["id"])
        database.override_attendance(target_att["id"], 0)
        # Source checks in (present = 1)
        database.record_checkin(s1["id"], source["id"])

        # For session 2 (Science), only source checks in and gets overridden to 2 (justified)
        s2 = database.open_session(c2["id"])
        source_att2 = database.record_checkin(s2["id"], source["id"])
        database.override_attendance(source_att2["id"], 2)

        # Execute merge
        ok = database.merge_students(target["id"], source["id"])
        assert ok is True

        # Check source student is deleted
        assert database.get_student(source["id"]) is None

        # Check target student got the device_id from source
        updated_target = database.get_student(target["id"])
        assert updated_target["device_id"] == "device-source"

        # Check target enrollments consolidated
        classes = [c["id"] for c in database.get_classes_for_student(target["id"])]
        assert c1["id"] in classes
        assert c2["id"] in classes

        # Check grades resolved
        # Test 1 grade should be max(7.0, 9.0) = 9.0
        grades1 = database.get_test_grades(t1["id"])
        target_grade1 = next(g for g in grades1 if g["student_id"] == target["id"])
        assert target_grade1["score"] == 9.0

        # Test 2 grade should be 8.0
        grades2 = database.get_test_grades(t2["id"])
        target_grade2 = next(g for g in grades2 if g["student_id"] == target["id"])
        assert target_grade2["score"] == 8.0

        # Check attendance resolved
        # Session 1: Target had 0, Source had 1 -> Target should be upgraded to 1
        roster1 = database.get_full_session_roster(s1["id"])
        target_roster1 = next(r for r in roster1 if r["student_id"] == target["id"])
        assert target_roster1["present"] == 1

        # Session 2: Target had nothing, Source had 2 -> Target should have 2
        roster2 = database.get_full_session_roster(s2["id"])
        target_roster2 = next(r for r in roster2 if r["student_id"] == target["id"])
        assert target_roster2["present"] == 2

    def test_merge_api_endpoint(self, client):
        import database
        target = database.get_or_create_student("device-target")
        source = database.get_or_create_student("device-source")

        # Success path
        r = client.post(f"/students/{target['id']}/merge", json={"source_id": source["id"]})
        assert r.status_code == 200
        assert r.json() == {"ok": True}

        # Nonexistent target
        r = client.post("/students/9999/merge", json={"source_id": source["id"]})
        assert r.status_code == 404

        # Nonexistent source
        r = client.post(f"/students/{target['id']}/merge", json={"source_id": 9999})
        assert r.status_code == 404

        # Same student
        r = client.post(f"/students/{target['id']}/merge", json={"source_id": target["id"]})
        assert r.status_code == 400


class TestStudentAbsences:
    def test_database_get_student_attendance_history(self):
        import database
        cls = make_class()
        s = make_enrolled_student(cls["id"])
        
        # Open 2 sessions
        s1 = database.open_session(cls["id"])
        s2 = database.open_session(cls["id"])
        
        # Student present in session 1
        database.record_checkin(s1["id"], s["id"])
        
        # Student absent in session 2 (no record)
        
        history = database.get_student_attendance_history(cls["id"], s["id"])
        assert len(history) == 2
        
        # Order is descending by session id
        assert history[0]["session_id"] == s2["id"]
        assert history[0]["present"] == 0
        
        assert history[1]["session_id"] == s1["id"]
        assert history[1]["present"] == 1

    def test_database_get_student_attendance_history_percentage(self):
        import database
        cls = make_class()
        s = make_enrolled_student(cls["id"])
        
        s1 = database.open_session(cls["id"])
        database.record_checkin(s1["id"], s["id"])
        database.close_session(s1["id"])
        
        history = database.get_student_attendance_history(cls["id"], s["id"])
        assert len(history) == 1
        # Checked in at start and stayed until close, so should be 100%
        assert history[0]["duration_percentage"] == 100

    def test_api_student_attendance_history(self, client):
        import database
        cls = make_class()
        s = make_enrolled_student(cls["id"], "device-absences")
        database.update_student_name(s["id"], "Test Absences")
        
        s1 = database.open_session(cls["id"])
        database.record_checkin(s1["id"], s["id"])
        
        # Nonexistent student device_id
        r = client.get(f"/public/students/attendance?device_id=ghost-device&class_id={cls['id']}")
        assert r.status_code == 404
        
        # Student is not enrolled in a different class
        cls2 = make_class("Other Class")
        r = client.get(f"/public/students/attendance?device_id=device-absences&class_id={cls2['id']}")
        assert r.status_code == 400
        
        # Success path
        r = client.get(f"/public/students/attendance?device_id=device-absences&class_id={cls['id']}")
        assert r.status_code == 200
        data = r.json()
        assert data["student_name"] == "Test Absences"
        assert len(data["history"]) == 1
        assert data["history"][0]["present"] == 1
