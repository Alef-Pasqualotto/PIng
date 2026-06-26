from contextlib import asynccontextmanager
from sqlite3 import IntegrityError
import io
import asyncio
import queue
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import database
import attendance_events
import network_service
import settings
from app_paths import log_path, resource_path
from logging_config import configure_logging, get_logger


configure_logging()
logger = get_logger("api")


LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
PUBLIC_PATHS = {"/", "/public/classes", "/checkin", "/session/status", "/health", "/public/students/attendance"}


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
    is_public = path in PUBLIC_PATHS or path.startswith("/static/")
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
    device_id: str | None = Field(default=None, min_length=4, max_length=200)
    class_id: int | None = None
    present: int


class SetAttendanceBody(BaseModel):
    present: int


class CheckoutBody(BaseModel):
    checkout: bool


class TestCreateBody(BaseModel):
    class_id: int
    name: str = Field(min_length=1, max_length=100)
    max_score: float = Field(default=10.0, ge=0.0)


class GradeSetBody(BaseModel):
    score: float | None = Field(default=None, ge=0.0)


class TestUpdateMaxScoreBody(BaseModel):
    max_score: float = Field(ge=0.1)


class EnrollBody(BaseModel):
    class_id: int
    student_id: int


class StudentNameBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class MergeStudentBody(BaseModel):
    source_id: int


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
    existing_record = database.get_attendance_record(session["id"], student["id"])
    already_present = existing_record is not None and existing_record["present"] == 1
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
            "already_present": False,
        }
    attendance_events.publish(session["id"], "student_checkin")
    return {
        "ok": True,
        "student_id": student["id"],
        "session_id": session["id"],
        "attendance_id": record["id"],
        "is_enrolled": enrolled,
        "present": record["present"],
        "already_present": already_present,
    }


@app.get("/session/status")
def session_status(class_id: int):
    session = database.get_active_session(class_id)
    return {"is_open": session is not None, "session_id": session["id"] if session else None}


@app.get("/public/students/attendance")
def student_attendance_history(device_id: str, class_id: int):
    student = database.get_student_by_device(device_id)
    if student is None:
        raise HTTPException(404, "Estudante não encontrado para este dispositivo.")
    if not database.is_enrolled(class_id, student["id"]):
        raise HTTPException(400, "Você não está matriculado nesta turma.")
    history = database.get_student_attendance_history(class_id, student["id"])
    return {
        "student_name": student["name"] or "Nome não informado",
        "history": [dict(row) for row in history]
    }


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
    attendance_events.publish(body.session_id, "session_closed")
    return {"ok": True, "session_id": body.session_id}


@app.get("/session/{session_id}/roster")
def session_roster(session_id: int):
    if database.get_session(session_id) is None:
        raise HTTPException(404, "Sessão não encontrada.")
    return database.get_full_session_roster(session_id)


@app.get("/session/{session_id}/events")
async def session_events(session_id: int, request: Request):
    if database.get_session(session_id) is None:
        raise HTTPException(404, "Sessão não encontrada.")
    subscriber = attendance_events.subscribe(session_id)

    async def stream():
        try:
            yield "event: ready\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.to_thread(subscriber.get, True, 15)
                    yield f"event: roster\ndata: {message}\n\n"
                except queue.Empty:
                    yield "event: ping\ndata: {}\n\n"
        finally:
            attendance_events.unsubscribe(session_id, subscriber)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/classes/{class_id}/sessions")
def class_sessions(class_id: int):
    if database.get_class(class_id) is None:
        raise HTTPException(404, "Turma não encontrada.")
    return [dict(row) for row in database.get_sessions_for_class(class_id)]


@app.patch("/attendance/{attendance_id}")
def override_attendance(attendance_id: int, body: AttendanceOverrideBody):
    if attendance_id == -1:
        if body.device_id is None or body.class_id is None:
            raise HTTPException(400, "device_id and class_id are required for creating new attendance.")
        student = database.get_or_create_student(body.device_id)
        session = database.get_active_session(body.class_id)
        if session is None:
            raise HTTPException(400, "A chamada não está aberta para esta turma.")
        record = database.set_student_attendance(session["id"], student["id"], body.present)
        if record is None:
            raise HTTPException(404, "Sessão ou matrícula não encontrada.")
        attendance_events.publish(session["id"], "attendance_override")
        return {"ok": True, "attendance_id": record["id"], "present": body.present}
    elif not database.override_attendance(attendance_id, body.present):
        raise HTTPException(404, "Presença não encontrada.")
    # The teacher UI also updates locally, but publish for any other open dashboard.
    return {"ok": True, "attendance_id": attendance_id, "present": body.present}


@app.put("/session/{session_id}/students/{student_id}/attendance")
def set_attendance(session_id: int, student_id: int, body: SetAttendanceBody):
    record = database.set_student_attendance(session_id, student_id, body.present)
    if record is None:
        raise HTTPException(404, "Sessão ou matrícula não encontrada.")
    attendance_events.publish(session_id, "attendance_override")
    return {"ok": True, "attendance_id": record["id"], "present": body.present}


@app.put("/session/{session_id}/students/{student_id}/checkout")
def student_checkout(session_id: int, student_id: int, body: CheckoutBody):
    if database.get_session(session_id) is None:
        raise HTTPException(404, "Sessão não encontrada.")
    database.record_checkout(session_id, student_id, body.checkout)
    attendance_events.publish(session_id, "checkout_changed")
    return {"ok": True}


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


@app.post("/students/{target_id}/merge")
def merge_students(target_id: int, body: MergeStudentBody):
    if target_id == body.source_id:
        raise HTTPException(400, "O estudante de destino e de origem não podem ser o mesmo.")
    target = database.get_student(target_id)
    source = database.get_student(body.source_id)
    if target is None:
        raise HTTPException(404, "Estudante de destino não encontrado.")
    if source is None:
        raise HTTPException(404, "Estudante de origem não encontrado.")
    if not database.merge_students(target_id, body.source_id):
        raise HTTPException(500, "Erro ao mesclar estudantes.")
    return {"ok": True}


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


# ---------------------------------------------------------------------------
# Tests & Grades Routes
# ---------------------------------------------------------------------------

@app.post("/tests", status_code=201)
def create_test(body: TestCreateBody):
    if database.get_class(body.class_id) is None:
        raise HTTPException(404, "Turma não encontrada.")
    return dict(database.create_test(body.class_id, body.name, body.max_score))


@app.get("/classes/{class_id}/tests")
def get_class_tests(class_id: int):
    if database.get_class(class_id) is None:
        raise HTTPException(404, "Turma não encontrada.")
    return [dict(t) for t in database.get_tests_for_class(class_id)]


@app.delete("/tests/{test_id}", status_code=204)
def delete_test(test_id: int):
    if not database.delete_test(test_id):
        raise HTTPException(404, "Avaliação não encontrada.")


@app.get("/tests/{test_id}/grades")
def get_test_grades(test_id: int):
    if database.get_test(test_id) is None:
        raise HTTPException(404, "Avaliação não encontrada.")
    return database.get_test_grades(test_id)


@app.put("/tests/{test_id}/students/{student_id}/grade")
def set_student_grade(test_id: int, student_id: int, body: GradeSetBody):
    test = database.get_test(test_id)
    if test is None:
        raise HTTPException(404, "Avaliação não encontrada.")
    if body.score is not None and body.score > test["max_score"]:
        raise HTTPException(400, f"A nota não pode ser maior que a nota máxima ({test['max_score']}).")
    database.set_student_grade(test_id, student_id, body.score)
    return {"ok": True}


@app.patch("/tests/{test_id}/max-score")
def update_test_max_score(test_id: int, body: TestUpdateMaxScoreBody):
    if database.get_test(test_id) is None:
        raise HTTPException(404, "Avaliação não encontrada.")
    try:
        database.update_test_max_score(test_id, body.max_score)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}
