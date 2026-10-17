from datetime import datetime, timedelta
from pymongo import MongoClient
from pymongo.errors import OperationFailure
import config

_client = None

def get_db():
    global _client
    if _client is None:
        # tz_aware: datetimes come back in the clinic's timezone, never "naive"
        _client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=3000,
                              tz_aware=True, tzinfo=config.TZ)
    return _client[config.DB_NAME]

def _migrate_legacy(db):
    """Old records stored date/time as strings. Convert them to a real datetime (start_at)."""
    for a in list(db.appointments.find({"start_at": {"$exists": False}, "date": {"$exists": True}})):
        start = datetime.strptime(f"{a['date']} {a['time']}", "%Y-%m-%d %H:%M").replace(tzinfo=config.TZ)
        db.appointments.update_one({"_id": a["_id"]}, {
            "$set": {"start_at": start, "end_at": start + timedelta(minutes=config.SLOT_MINUTES),
                     "type": "regular"},
            "$unset": {"date": "", "time": ""}})

def init_indexes():
    db = get_db()
    try:
        db.appointments.drop_index("doctor_id_1_date_1_time_1")   # old string-based guard
    except OperationFailure:
        pass
    _migrate_legacy(db)
    db.patients.create_index("patient_id", unique=True)
    db.patients.create_index("phone")
    db.doctors.create_index("doctor_id", unique=True)
    db.appointments.create_index("appointment_id", unique=True)
    booked = {"status": "booked"}
    # Guard 1: a doctor can't have two active bookings at the same moment.
    db.appointments.create_index([("doctor_id", 1), ("start_at", 1)], unique=True,
                                 partialFilterExpression=booked, name="uniq_doctor_slot")
    # Guard 2: a patient can't be in two places at the same moment (even with different doctors).
    db.appointments.create_index([("patient_id", 1), ("start_at", 1)], unique=True,
                                 partialFilterExpression=booked, name="uniq_patient_slot")
    db.visits.create_index([("patient_id", 1), ("visit_at", -1)])
    db.visits.create_index("visit_id", unique=True)
