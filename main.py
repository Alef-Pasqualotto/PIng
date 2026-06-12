from contextlib import asynccontextmanager
from sqlite3 import IntegrityError
import io
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import database
import network_service
import settings
from app_paths import log_path, resource_path
from logging_config import configure_logging, get_logger


configure_logging()
logger = get_logger("api")


LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
PUBLIC_PATHS = {"/", "/public/classes", "/checkin", "/session/status", "/health"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup: database=%s", database.DB_PATH)
    database.init_db()
    yield
    logger.info("Application shutdown requested")
    network_service.stop_if_started()


app = FastAPI(title="PIng", lifespan=lifespan, docs_url=None, redoc_url=None)
static_dir = resource_path("static")
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.middleware("http")
async def local_admin_only(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.perf_counter()
    path = request.url.path
    is_public = True #path in PUBLIC_PATHS or path.startswith("/static/")
    client_host = request.client.host if request.client else ""
    if not is_public and client_host not in LOCAL_HOSTS:
        logger.warning("request=%s denied method=%s path=%s client=%s", request_id, request.method, path, client_host)
        return JSONResponse(
            status_code=403,
            content={"detail": "Esta operação só está disponível no aplicativo do professor."},
            headers={"X-Request-ID": request_id},
        )
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request=%s unhandled method=%s path=%s client=%s", request_id, request.method, path, client_host)
        raise
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    log = logger.warning if response.status_code >= 400 else logger.info
    log(
        "request=%s method=%s path=%s status=%s client=%s duration_ms=%.1f",
        request_id, request.method, path, response.status_code, client_host, elapsed_ms,
    )
    return response


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    logger.warning("Database integrity error: path=%s error=%s", request.url.path, exc)
    return JSONResponse(status_code=409, content={"detail": "O registro já existe ou está em uso."})


class CheckinBody(BaseModel):
    device_id: str = Field(min_length=4, max_length=200)
    class_id: int


class ClassBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class SessionOpenBody(BaseModel):
    class_id: int


class SessionCloseBody(BaseModel):
    session_id: int


class AttendanceOverrideBody(BaseModel):
    device_id: str = Field(min_length=4, max_length=200)
    class_id: int
    present: bool


class EnrollBody(BaseModel):
    class_id: int
    student_id: int


class StudentNameBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class NetworkConfigBody(BaseModel):
    ssid: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=8, max_length=63)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/debug/log-info")
def log_info():
    path = log_path()
    logger.debug("Log information requested: path=%s", path)
    return {"path": str(path), "exists": path.exists(), "size": path.stat().st_size if path.exists() else 0}


@app.get("/", response_class=HTMLResponse)
def student_page(request: Request):
    return FileResponse(resource_path("templates", "student.html"), media_type="text/html")


@app.get("/public/classes")
def public_classes():
    return [dict(row) for row in database.get_all_classes()]


@app.post("/checkin")
def checkin(body: CheckinBody):
    student = database.get_or_create_student(body.device_id)
    session = database.get_active_session(body.class_id)
    if session is None:
        raise HTTPException(400, "A chamada não está aberta para esta turma.")
    record = database.record_checkin(session["id"], student["id"])
    enrolled = database.is_enrolled(body.class_id, student["id"])
    if record is None:
        return {
            "ok": False,
            "student_id": student["id"],
            "session_id": session["id"],
            "attendance_id": None,
            "is_enrolled": enrolled,
            "present": None,
        }
    return {
        "ok": True,
        "student_id": student["id"],
        "session_id": session["id"],
        "attendance_id": record["id"],
        "is_enrolled": enrolled,\
        "present": True,
    }


@app.get("/session/status")
def session_status(class_id: int):
    session = database.get_active_session(class_id)
    return {"is_open": session is not None, "session_id": session["id"] if session else None}


@app.get("/teacher", response_class=HTMLResponse)
def teacher_dashboard(request: Request):
    return FileResponse(resource_path("templates", "teacher.html"), media_type="text/html")


@app.get("/classes")
def list_classes():
    return [dict(row) for row in database.get_all_classes()]


@app.post("/classes", status_code=201)
def create_class(body: ClassBody):
    return dict(database.create_class(body.name.strip()))


@app.delete("/classes/{class_id}", status_code=204)
def delete_class(class_id: int):
    if not database.delete_class(class_id):
        raise HTTPException(404, "Turma não encontrada.")


@app.post("/session/open", status_code=201)
def open_session(body: SessionOpenBody):
    if database.get_class(body.class_id) is None:
        raise HTTPException(404, "Turma não encontrada.")
    return dict(database.open_session(body.class_id))


@app.post("/session/close")
def close_session(body: SessionCloseBody):
    if not database.close_session(body.session_id):
        raise HTTPException(404, "Sessão não encontrada.")
    return {"ok": True, "session_id": body.session_id}


@app.get("/session/{session_id}/roster")
def session_roster(session_id: int):
    if database.get_session(session_id) is None:
        raise HTTPException(404, "Sessão não encontrada.")
    return database.get_full_session_roster(session_id)


@app.get("/classes/{class_id}/sessions")
def class_sessions(class_id: int):
    if database.get_class(class_id) is None:
        raise HTTPException(404, "Turma não encontrada.")
    return [dict(row) for row in database.get_sessions_for_class(class_id)]


@app.patch("/attendance/{attendance_id}")
def override_attendance(attendance_id: int, body: AttendanceOverrideBody):
    if attendance_id == -1:
        checkin(body)
    elif not database.override_attendance(attendance_id, body.present):
        raise HTTPException(404, "Presença não encontrada.")
    return {"ok": True, "attendance_id": attendance_id, "present": body.present}


@app.put("/session/{session_id}/students/{student_id}/attendance")
def set_attendance(session_id: int, student_id: int, body: AttendanceOverrideBody):
    record = database.set_student_attendance(session_id, student_id, body.present)
    if record is None:
        raise HTTPException(404, "Sessão ou matrícula não encontrada.")
    return {"ok": True, "attendance_id": record["id"], "present": body.present}


@app.get("/session/{session_id}/export")
def export_session(session_id: int):
    session = database.get_session(session_id)
    if session is None:
        raise HTTPException(404, "Sessão não encontrada.")
    filename = f"presenca_sessao_{session_id}_{session['date']}.csv"
    return StreamingResponse(
        io.StringIO(database.export_session_csv(session_id)),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/classes/{class_id}/students")
def enrolled_students(class_id: int):
    if database.get_class(class_id) is None:
        raise HTTPException(404, "Turma não encontrada.")
    return [dict(row) for row in database.get_enrolled_students(class_id)]


@app.post("/enrollments", status_code=201)
def enroll_student(body: EnrollBody):
    enrollment = database.enroll_student(body.class_id, body.student_id)
    if enrollment is None:
        raise HTTPException(404, "Turma ou estudante não encontrado.")
    return dict(enrollment)


@app.delete("/enrollments")
def unenroll_student(body: EnrollBody):
    if not database.unenroll_student(body.class_id, body.student_id):
        raise HTTPException(404, "Matrícula não encontrada.")
    return {"ok": True}


@app.get("/students")
def list_students():
    return [dict(row) for row in database.get_all_students()]


@app.patch("/students/{student_id}/name")
def update_name(student_id: int, body: StudentNameBody):
    if not database.update_student_name(student_id, body.name.strip()):
        raise HTTPException(404, "Estudante não encontrado.")
    return {"ok": True, "student_id": student_id, "name": body.name.strip()}


@app.patch("/students/{student_id}/device")
async def update_device(student_id: int, request: Request):
    body = await request.json()
    device_id = str(body.get("device_id", "")).strip()
    if not device_id:
        raise HTTPException(400, "device_id é obrigatório.")
    if not database.update_student_device(student_id, device_id):
        raise HTTPException(404, "Estudante não encontrado.")
    return {"ok": True, "student_id": student_id, "device_id": device_id}


@app.get("/api/network/status")
def network_status():
    return network_service.status()


@app.get("/api/network/qr")
def network_qr():
    import qrcode

    image = qrcode.make(network_service.status()["student_url"])
    output = io.BytesIO()
    image.save(output, format="PNG")
    return Response(content=output.getvalue(), media_type="image/png")


@app.put("/api/network/config")
def network_config(body: NetworkConfigBody):
    settings.update_network(body.ssid, body.password)
    return network_service.status()


@app.post("/api/network/start")
def network_start():
    try:
        return network_service.start()
    except RuntimeError as exc:
        raise HTTPException(503, f"Não foi possível iniciar o hotspot: {exc}") from exc


@app.post("/api/network/stop")
def network_stop():
    try:
        return network_service.stop()
    except RuntimeError as exc:
        raise HTTPException(503, f"Não foi possível parar o hotspot: {exc}") from exc
