"""
populate.py — Seeds the database with test data.
Run once before testing: python populate.py

Creates:
  - 3 classes
  - 10 students (with device IDs and names)
  - Enrollments (each student in 1 or 2 classes)
  - 1 open session per class
  - Attendance records (some present, some absent, one guest)
"""

import database
from datetime import datetime

database.init_db()

# ---------------------------------------------------------------------------
# Classes
# ---------------------------------------------------------------------------

print("Creating classes...")
math   = database.create_class("Math 3A")
history = database.create_class("History 2B")
science = database.create_class("Science 1C")

print(f"  {dict(math)}")
print(f"  {dict(history)}")
print(f"  {dict(science)}")

# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------

print("\nCreating students...")
student_data = [
    ("device-ana",     "Ana Silva"),
    ("device-bruno",   "Bruno Costa"),
    ("device-carla",   "Carla Mendes"),
    ("device-diego",   "Diego Souza"),
    ("device-elena",   "Elena Rocha"),
    ("device-fabio",   "Fabio Lima"),
    ("device-giovana", "Giovana Nunes"),
    ("device-hugo",    "Hugo Ferreira"),
    ("device-iris",    "Iris Campos"),
    ("device-joao",    "João Pereira"),
]

students = []
for device_id, name in student_data:
    s = database.get_or_create_student(device_id)
    database.update_student_name(s["id"], name)
    s = database.get_student(s["id"])
    students.append(s)
    print(f"  {s['name']} (device: {s['device_id']})")

# Unpack for readability
ana, bruno, carla, diego, elena, fabio, giovana, hugo, iris, joao = students

# ---------------------------------------------------------------------------
# Enrollments
# ---------------------------------------------------------------------------

print("\nEnrolling students...")

# Math 3A: Ana, Bruno, Carla, Diego, Elena, Fabio
for s in [ana, bruno, carla, diego, elena, fabio]:
    database.enroll_student(math["id"], s["id"])
    print(f"  {s['name']} → Math 3A")

# History 2B: Carla, Diego, Giovana, Hugo, Iris
for s in [carla, diego, giovana, hugo, iris]:
    database.enroll_student(history["id"], s["id"])
    print(f"  {s['name']} → History 2B")

# Science 1C: Elena, Fabio, Hugo, Iris, João
for s in [elena, fabio, hugo, iris, joao]:
    database.enroll_student(science["id"], s["id"])
    print(f"  {s['name']} → Science 1C")

# ---------------------------------------------------------------------------
# Sessions (one open per class)
# ---------------------------------------------------------------------------

print("\nOpening sessions...")
math_session    = database.open_session(math["id"])
history_session = database.open_session(history["id"])
science_session = database.open_session(science["id"])

print(f"  Math 3A    session id: {math_session['id']}")
print(f"  History 2B session id: {history_session['id']}")
print(f"  Science 1C session id: {science_session['id']}")

# ---------------------------------------------------------------------------
# Attendance — Math 3A
# Ana, Bruno, Carla present. Diego, Elena, Fabio absent.
# João checks in as a guest (not enrolled in Math).
# ---------------------------------------------------------------------------

print("\nRecording attendance for Math 3A...")
for s in [ana, bruno, carla]:
    database.record_checkin(math_session["id"], s["id"])
    print(f"  {s['name']} checked in")

print(f"  Diego, Elena, Fabio did not check in (absent)")

# Guest
database.record_checkin(math_session["id"], joao["id"])
print(f"  João checked in as GUEST (not enrolled in Math 3A)")

# ---------------------------------------------------------------------------
# Attendance — History 2B
# Carla, Diego, Giovana present. Hugo, Iris absent.
# ---------------------------------------------------------------------------

print("\nRecording attendance for History 2B...")
for s in [carla, diego, giovana]:
    database.record_checkin(history_session["id"], s["id"])
    print(f"  {s['name']} checked in")

print(f"  Hugo, Iris did not check in (absent)")

# ---------------------------------------------------------------------------
# Attendance — Science 1C
# All present except João. Elena overridden by teacher to absent.
# ---------------------------------------------------------------------------

print("\nRecording attendance for Science 1C...")
for s in [elena, fabio, hugo, iris]:
    database.record_checkin(science_session["id"], s["id"])
    print(f"  {s['name']} checked in")

print(f"  João did not check in (absent)")

# Teacher overrides Elena to absent in Science
elena_attendance = database.record_checkin(science_session["id"], elena["id"])
database.override_attendance(elena_attendance["id"], present=False)
print(f"  Elena overridden by teacher → absent")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "="*50)
print("Database populated. Summary:")
print(f"  Classes  : 3")
print(f"  Students : {len(students)}")
print(f"  Sessions : 3 (all open)")
print(f"  Math 3A  : 3 present, 3 absent, 1 guest")
print(f"  History  : 3 present, 2 absent")
print(f"  Science  : 3 present, 1 absent, 1 override")
print("="*50)
print("\nUseful IDs for Postman:")
print(f"  Math 3A    class_id={math['id']}    session_id={math_session['id']}")
print(f"  History 2B class_id={history['id']}  session_id={history_session['id']}")
print(f"  Science 1C class_id={science['id']}  session_id={science_session['id']}")
print(f"  Ana student_id={ana['id']}  Bruno student_id={bruno['id']}  João student_id={joao['id']}")