"""REST API over the same services. Run: uvicorn api:app --reload   then open http://localhost:8000/docs"""
from contextlib import asynccontextmanager
from datetime import date
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import db, services

@asynccontextmanager
async def lifespan(_):
    db.init_indexes(); yield

app = FastAPI(title="Clinic API", lifespan=lifespan)

class NewPatient(BaseModel):
    first_name: str; last_name: str; phone: str | None = None
class NewAppt(BaseModel):
    patient_id: str; doctor_id: str; day: date; time: str
class NewVisit(BaseModel):
    patient_id: str; doctor_id: str; complaint: str
    diagnosis: str = ""; notes: str = ""; status: str = "ongoing"; appointment_id: str | None = None
class Move(BaseModel):
    patient_id: str; day: date; time: str

def _ok(res):
    obj, err = res
    if err: raise HTTPException(409, err)
    return obj

@app.get("/doctors")
def doctors(): return services.list_doctors()
@app.get("/doctors/{doctor_id}/slots")
def slots(doctor_id: str, day: date): return {"free": services.available_slots(doctor_id, day)}
@app.post("/patients")
def new_patient(p: NewPatient): return services.create_patient(p.first_name, p.last_name, p.phone)
@app.get("/patients/{pid}")
def patient(pid: str):
    p = services.get_patient(pid)
    if not p: raise HTTPException(404, "Patient not found")
    return p
@app.get("/patients/{pid}/appointments")
def appts(pid: str): return services.upcoming(pid.upper())
@app.post("/appointments")
def create(a: NewAppt): return _ok(services.book(a.patient_id.upper(), a.doctor_id, a.day, a.time))
@app.put("/appointments/{aid}")
def move(aid: str, m: Move): return _ok(services.reschedule(aid, m.patient_id.upper(), m.day, m.time))
@app.delete("/appointments/{aid}")
def delete(aid: str, patient_id: str):
    if not services.cancel(aid, patient_id.upper()): raise HTTPException(404, "Appointment not found")
    return {"cancelled": True}

# ---- medical history & follow-ups ----
@app.post("/visits")                       # doctor records a visit (also marks the appointment completed)
def add_visit(v: NewVisit):
    try: return services.add_visit(v.patient_id.upper(), v.doctor_id, v.complaint, v.diagnosis,
                                   v.notes, v.status, appointment_id=v.appointment_id)
    except ValueError as e: raise HTTPException(400, str(e))
@app.get("/patients/{pid}/history")
def history(pid: str, limit: int = 10): return services.history(pid.upper(), limit)
@app.get("/doctors/{doctor_id}/schedule")  # day list + each patient's latest visit
def schedule(doctor_id: str, day: date): return services.schedule(doctor_id, day)
