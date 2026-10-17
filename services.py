"""Business logic + all CRUD on MongoDB. The voice agent and the REST API both use this.
Times are converted ONCE into real datetimes (start_at/end_at) and stored that way."""
import difflib, random, re, uuid
from datetime import date, datetime, timedelta
from pymongo.errors import DuplicateKeyError
import config
from db import get_db
from fmt import fmt_date, fmt_time

NOID = {"_id": 0}
TZ = config.TZ
VISIT_STATUS = ("resolved", "improving", "ongoing")

def now(): return datetime.now(TZ)
def _digits(s): return "".join(ch for ch in (s or "") if ch.isdigit())
def _local(dt): return dt.astimezone(TZ)
def hhmm_of(dt): return _local(dt).strftime("%H:%M")

def make_start(d: date, hhmm: str) -> datetime:
    """THE type conversion: (date, 'HH:MM') -> timezone-aware datetime."""
    return datetime(d.year, d.month, d.day, int(hhmm[:2]), int(hhmm[3:]), tzinfo=TZ)

def _end(start): return start + timedelta(minutes=config.SLOT_MINUTES)
def _day_range(d): lo = make_start(d, "00:00"); return lo, lo + timedelta(days=1)

# ---------------- slots & rules ----------------
def all_slots():
    out, m = [], config.OPEN_HOUR * 60
    while m + config.SLOT_MINUTES <= config.CLOSE_HOUR * 60:
        out.append(f"{m // 60:02d}:{m % 60:02d}"); m += config.SLOT_MINUTES
    return out

def valid_time(hhmm): return hhmm in all_slots()

def validate_date(d: date):
    today = now().date()
    if d < today: return "That date has already passed."
    if d.weekday() in config.CLOSED_WEEKDAYS: return f"Sorry, the clinic is closed on {d.strftime('%A')}s."
    if d > today + timedelta(days=config.MAX_ADVANCE_DAYS):
        return f"I can only book up to {config.MAX_ADVANCE_DAYS} days ahead."
    return None

def available_slots(doctor_id, d: date):
    lo, hi = _day_range(d)
    booked = {hhmm_of(a["start_at"]) for a in get_db().appointments.find(
        {"doctor_id": doctor_id, "status": "booked", "start_at": {"$gte": lo, "$lt": hi}}, NOID)}
    free = [s for s in all_slots() if s not in booked]
    if d == now().date():
        cur = now().strftime("%H:%M"); free = [s for s in free if s > cur]
    return free

def nearest(free, hhmm, k=3):
    t = int(hhmm[:2]) * 60 + int(hhmm[3:])
    key = lambda s: abs(int(s[:2]) * 60 + int(s[3:]) - t)
    return sorted(sorted(free, key=key)[:k])

# ---------------- doctors ----------------
def list_doctors(): return list(get_db().doctors.find({}, NOID).sort("doctor_id", 1))
def get_doctor(doctor_id): return get_db().doctors.find_one({"doctor_id": doctor_id}, NOID)

def match_doctor(text):
    text = text.lower(); words = re.findall(r"[a-z]+", text); docs = list_doctors()
    for d in docs:
        if any(re.search(rf"\b{re.escape(k)}\b", text) for k in d["keywords"]): return d
    for d in docs:
        vocab = [w for w in re.findall(r"[a-z]+", f"{d['name']} {d['specialty']}".lower()) if w != "dr" and len(w) > 2]
        for w in words:
            if len(w) > 2 and difflib.get_close_matches(w, vocab, n=1, cutoff=0.8): return d
    return None

# ---------------- patients ----------------
def create_patient(first, last, phone=None):
    """ID = 6 random digits + first letter of first name + first letter of last name."""
    db = get_db()
    for _ in range(50):
        digits = str(random.randint(100000, 999999))
        if db.patients.find_one({"patient_id": {"$regex": f"^{digits}"}}): continue
        doc = {"patient_id": f"{digits}{first[0].upper()}{last[0].upper()}", "first_name": first.title(),
               "last_name": last.title(), "phone": _digits(phone), "created_at": now()}
        try:
            db.patients.insert_one(doc); doc.pop("_id", None); return doc
        except DuplicateKeyError: continue
    raise RuntimeError("Could not generate a unique patient id")

def get_patient(patient_id): return get_db().patients.find_one({"patient_id": patient_id.upper()}, NOID)

def find_patient(digits, letters=""):
    c = get_db().patients
    if letters:
        p = c.find_one({"patient_id": digits + letters.upper()}, NOID)
        if p: return p, True
    found = list(c.find({"patient_id": {"$regex": f"^{digits}"}}, NOID).limit(2))
    return (found[0], False) if len(found) == 1 else (None, False)

def find_patient_by_phone(phone):
    d = _digits(phone)[-10:]
    return get_db().patients.find_one({"phone": {"$regex": f"{d}$"}}, NOID) if len(d) == 10 else None

# ---------------- self-conflict checks ----------------
def patient_conflict(patient_id, start, end, exclude_id=None):
    """Any booked appointment of this patient (with ANY doctor) overlapping [start, end)."""
    q = {"patient_id": patient_id, "status": "booked", "start_at": {"$lt": end}, "end_at": {"$gt": start}}
    if exclude_id: q["appointment_id"] = {"$ne": exclude_id}
    return get_db().appointments.find_one(q, NOID)

def patient_busy_times(patient_id, d: date, exclude_id=None):
    """{'HH:MM': appointment} for everything this patient already has that day."""
    lo, hi = _day_range(d)
    q = {"patient_id": patient_id, "status": "booked", "start_at": {"$gte": lo, "$lt": hi}}
    if exclude_id: q["appointment_id"] = {"$ne": exclude_id}
    return {hhmm_of(a["start_at"]): a for a in get_db().appointments.find(q, NOID)}

def conflict_message(a):
    s = _local(a["start_at"])
    return (f"You already have an appointment with {a['doctor_name']} at {fmt_time(s.strftime('%H:%M'))} "
            f"on {fmt_date(s.date())}, so I can't book two appointments at the same time.")

def _dup_message(e):
    kp = (getattr(e, "details", None) or {}).get("keyPattern", {})
    if "patient_id" in kp:
        return "You already have an appointment at that time, so I can't book two at once."
    return "Sorry, someone just took that slot."

def _check_slot(doctor_id, d, hhmm):
    if not valid_time(hhmm): return "Appointments are only from 8 AM to 6 PM in 30 minute slots."
    err = validate_date(d)
    if err: return err
    if hhmm not in available_slots(doctor_id, d): return "That slot is not available."
    return None

# ---------------- appointments (CRUD) ----------------
def book(patient_id, doctor_id, d: date, hhmm, kind="regular", reason=None, follow_up_of=None):   # CREATE
    err = _check_slot(doctor_id, d, hhmm)
    if err: return None, err
    start = make_start(d, hhmm); end = _end(start)
    clash = patient_conflict(patient_id, start, end)
    if clash: return None, conflict_message(clash)
    doc = {"appointment_id": uuid.uuid4().hex[:8], "patient_id": patient_id, "doctor_id": doctor_id,
           "doctor_name": get_doctor(doctor_id)["name"], "start_at": start, "end_at": end,
           "status": "booked", "type": kind, "reason": reason, "follow_up_of": follow_up_of,
           "created_at": now()}
    try:
        get_db().appointments.insert_one(doc)
    except DuplicateKeyError as e:
        return None, _dup_message(e)
    doc.pop("_id", None)
    return doc, None

def upcoming(patient_id):                                                                      # READ
    q = {"patient_id": patient_id, "status": "booked", "start_at": {"$gte": now()}}
    return list(get_db().appointments.find(q, NOID).sort("start_at", 1))

def reschedule(appointment_id, patient_id, d: date, hhmm):                                     # UPDATE
    appt = get_db().appointments.find_one(
        {"appointment_id": appointment_id, "patient_id": patient_id, "status": "booked"}, NOID)
    if not appt: return None, "I couldn't find that appointment."
    start = make_start(d, hhmm); end = _end(start)
    if start == _local(appt["start_at"]): return None, "That is already your appointment time."
    err = _check_slot(appt["doctor_id"], d, hhmm)
    if err: return None, err
    clash = patient_conflict(patient_id, start, end, exclude_id=appointment_id)   # (was missing before)
    if clash: return None, conflict_message(clash)
    try:
        get_db().appointments.update_one({"appointment_id": appointment_id, "status": "booked"},
            {"$set": {"start_at": start, "end_at": end, "updated_at": now()}})
    except DuplicateKeyError as e:
        return None, _dup_message(e)
    appt.update(start_at=start, end_at=end)
    return appt, None

def cancel(appointment_id, patient_id):                                                        # DELETE (soft)
    r = get_db().appointments.update_one(
        {"appointment_id": appointment_id, "patient_id": patient_id, "status": "booked"},
        {"$set": {"status": "cancelled", "cancelled_at": now()}})
    return r.modified_count == 1

# ---------------- medical history / follow-ups ----------------
def add_visit(patient_id, doctor_id, complaint, diagnosis="", notes="", status="ongoing",
              visit_at=None, appointment_id=None):
    """Doctor's record of a visit. Passing appointment_id also marks that appointment completed."""
    if status not in VISIT_STATUS: raise ValueError(f"status must be one of {VISIT_STATUS}")
    doc = {"visit_id": uuid.uuid4().hex[:8], "patient_id": patient_id, "doctor_id": doctor_id,
           "doctor_name": get_doctor(doctor_id)["name"], "visit_at": visit_at or now(),
           "complaint": complaint, "diagnosis": diagnosis, "notes": notes, "status": status,
           "appointment_id": appointment_id, "created_at": now()}
    get_db().visits.insert_one(doc); doc.pop("_id", None)
    if appointment_id:
        get_db().appointments.update_one({"appointment_id": appointment_id, "patient_id": patient_id},
                                         {"$set": {"status": "completed"}})
    return doc

def history(patient_id, limit=5):
    return list(get_db().visits.find({"patient_id": patient_id}, NOID).sort("visit_at", -1).limit(limit))

def latest_visit(patient_id):
    h = history(patient_id, 1); return h[0] if h else None

def schedule(doctor_id, d: date):
    """Doctor's day list, each with the patient's latest visit so they can check progress."""
    lo, hi = _day_range(d)
    appts = list(get_db().appointments.find(
        {"doctor_id": doctor_id, "status": "booked", "start_at": {"$gte": lo, "$lt": hi}}, NOID).sort("start_at", 1))
    for a in appts:
        p = get_patient(a["patient_id"])
        a["patient_name"] = f"{p['first_name']} {p['last_name']}" if p else "?"
        a["last_visit"] = latest_visit(a["patient_id"])
    return appts
