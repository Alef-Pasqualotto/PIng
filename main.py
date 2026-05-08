from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from pathlib import Path
import io
import database
import hotspot
from contextlib import asynccontextmanager

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("lifespan")
    # startup
    database.init_db()
    try:
        hotspot.create_hotspot()
    except Exception as e:
        print(f"[hotspot] Could not create hotspot automatically: {e}")
        print("[hotspot] Start it manually if needed.")
    yield

    # shutdown
    try:
        hotspot.stop_hotspot()
    except Exception as e:
        print(f"[hotspot] Could not stop hotspot: {e}")

app = FastAPI(title="PIng teste App", lifespan=lifespan)
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# ---------------------------------------------------------------------------
# Pydantic models (request bodies)
# ---------------------------------------------------------------------------

class CheckinBody(BaseModel):
    device_id: str
    class_id: int          # student selects which class they're checking into

class ClassBody(BaseModel):
    name: str

class SessionOpenBody(BaseModel):
    class_id: int

class SessionCloseBody(BaseModel):
    session_id: int

class AttendanceOverrideBody(BaseModel):
    present: bool

class EnrollBody(BaseModel):
    class_id: int
    student_id: int

class StudentNameBody(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# Student routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def student_page(request: Request):
    print("student_page")
    """Serves the student check-in page."""
    classes = database.get_all_classes()
    return templates.TemplateResponse(
        "student.html",
        {"request": request, "classes": [dict(c) for c in classes]}
    )


@app.post("/checkin")
def checkin(body: CheckinBody):
    """
    Called by the student page when the student submits check-in.
    1. Finds or creates the student record for this device.
    2. Checks that a session is open for the requested class.
    3. Records the attendance.
    """
    # Resolve student
    student = database.get_or_create_student(body.device_id)

    # Verify an active session exists
    session = database.get_active_session(body.class_id)
    if session is None:
        raise HTTPException(
            status_code=400,
            detail="Check-in is not open for this class right now."
        )

    # Record check-in (idempotent — safe to call twice)
    record = database.record_checkin(session["id"], student["id"])

    enrolled = database.is_enrolled(body.class_id, student["id"])

    return {
        "ok": True,
        "student_id": student["id"],
        "session_id": session["id"],
        "attendance_id": record["id"],
        "is_enrolled": enrolled,
        "is_guest": not enrolled,
    }


@app.get("/session/status")
def session_status(class_id: int):
    """
    Lightweight poll endpoint for the student page.
    Returns whether check-in is currently open for a given class.
    """
    session = database.get_active_session(class_id)
    return {
        "is_open": session is not None,
        "session_id": session["id"] if session else None,
    }


# ---------------------------------------------------------------------------
# Teacher routes — pages
# ---------------------------------------------------------------------------

@app.get("/teacher", response_class=HTMLResponse)
def teacher_dashboard(request: Request):
    """Serves the teacher dashboard."""
    classes = database.get_all_classes()
    return templates.TemplateResponse(
        "teacher.html",
        {"request": request, "classes": [dict(c) for c in classes]}
    )


# ---------------------------------------------------------------------------
# Teacher routes — classes
# ---------------------------------------------------------------------------

@app.get("/classes")
def list_classes():
    classes = database.get_all_classes()
    return [dict(c) for c in classes]


@app.post("/classes", status_code=201)
def create_class(body: ClassBody):
    cls = database.create_class(body.name)
    return dict(cls)


@app.delete("/classes/{class_id}", status_code=204)
def delete_class(class_id: int):
    deleted = database.delete_class(class_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Class not found.")


# ---------------------------------------------------------------------------
# Teacher routes — sessions
# ---------------------------------------------------------------------------

@app.post("/session/open", status_code=201)
def open_session(body: SessionOpenBody):
    cls = database.get_class(body.class_id)
    if cls is None:
        raise HTTPException(status_code=404, detail="Class not found.")
    session = database.open_session(body.class_id)
    return dict(session)


@app.post("/session/close")
def close_session(body: SessionCloseBody):
    closed = database.close_session(body.session_id)
    if not closed:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"ok": True, "session_id": body.session_id}


@app.get("/session/{session_id}/roster")
def session_roster(session_id: int):
    """
    Returns the full roster for a session:
    enrolled present, enrolled absent, and guests.
    """
    session = database.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    roster = database.get_full_session_roster(session_id)
    return roster


@app.get("/classes/{class_id}/sessions")
def class_sessions(class_id: int):
    """Lists all past sessions for a class."""
    cls = database.get_class(class_id)
    if cls is None:
        raise HTTPException(status_code=404, detail="Class not found.")
    sessions = database.get_sessions_for_class(class_id)
    return [dict(s) for s in sessions]


# ---------------------------------------------------------------------------
# Teacher routes — attendance override
# ---------------------------------------------------------------------------

@app.patch("/attendance/{attendance_id}")
def override_attendance(attendance_id: int, body: AttendanceOverrideBody):
    """Teacher manually sets a student as present or absent."""
    updated = database.override_attendance(attendance_id, body.present)
    if not updated:
        raise HTTPException(status_code=404, detail="Attendance record not found.")
    return {"ok": True, "attendance_id": attendance_id, "present": body.present}


# ---------------------------------------------------------------------------
# Teacher routes — CSV export
# ---------------------------------------------------------------------------

@app.get("/session/{session_id}/export")
def export_session(session_id: int):
    """Streams a CSV file with the full attendance roster for a session."""
    session = database.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    csv_content = database.export_session_csv(session_id)
    filename = f"attendance_session_{session_id}_{session['date']}.csv"

    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ---------------------------------------------------------------------------
# Teacher routes — enrollments
# ---------------------------------------------------------------------------

@app.get("/classes/{class_id}/students")
def enrolled_students(class_id: int):
    """Lists all students enrolled in a class."""
    cls = database.get_class(class_id)
    if cls is None:
        raise HTTPException(status_code=404, detail="Class not found.")
    students = database.get_enrolled_students(class_id)
    return [dict(s) for s in students]


@app.post("/enrollments", status_code=201)
def enroll_student(body: EnrollBody):
    enrollment = database.enroll_student(body.class_id, body.student_id)
    return dict(enrollment)


@app.delete("/enrollments")
def unenroll_student(body: EnrollBody):
    removed = database.unenroll_student(body.class_id, body.student_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Enrollment not found.")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Teacher routes — students
# ---------------------------------------------------------------------------

@app.get("/students")
def list_students():
    """Lists all students known to the system (enrolled anywhere or guests)."""
    students = database.get_all_students()
    return [dict(s) for s in students]


@app.patch("/students/{student_id}/name")
def update_name(student_id: int, body: StudentNameBody):
    """Teacher assigns or corrects a student's display name."""
    updated = database.update_student_name(student_id, body.name)
    if not updated:
        raise HTTPException(status_code=404, detail="Student not found.")
    return {"ok": True, "student_id": student_id, "name": body.name}


@app.patch("/students/{student_id}/device")
async def update_device(student_id: int, request: Request):
    """
    Teacher updates the device ID for a student (e.g. student got a new phone).
    Expects JSON body: { "device_id": "new-device-id" }
    """
    body = await request.json()
    new_device_id = body.get("device_id")
    if not new_device_id:
        raise HTTPException(status_code=400, detail="device_id is required.")
    updated = database.update_student_device(student_id, new_device_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Student not found.")
    return {"ok": True, "student_id": student_id, "device_id": new_device_id}
