"""Creates 5 doctors, 10 sample patients and a few appointments.  python seed.py --reset"""
import sys
from datetime import timedelta
import db, services

DOCTORS = [
    ("D1", "Dr. Meena Iyer", "General Physician", ["fever", "cold", "cough", "general", "checkup", "physician", "headache"]),
    ("D2", "Dr. Arjun Rao", "Cardiologist", ["heart", "chest", "bp", "blood pressure", "cardiologist", "cardiac"]),
    ("D3", "Dr. Fatima Khan", "Dermatologist", ["skin", "rash", "acne", "hair", "dermatologist", "allergy"]),
    ("D4", "Dr. Suresh Nair", "Pediatrician", ["child", "kid", "baby", "children", "pediatrician", "paediatrician"]),
    ("D5", "Dr. Kavita Menon", "Orthopedic", ["bone", "joint", "knee", "back", "fracture", "orthopedic", "orthopaedic"]),
]
# (patient index, doctor, complaint, diagnosis, notes, status, days ago)
VISITS = [
    (0, "D1", "fever and sore throat", "viral fever", "Rest, fluids, paracetamol", "ongoing", 5),
    (0, "D1", "seasonal cold", "common cold", "Steam inhalation", "resolved", 90),
    (1, "D3", "itchy skin rash on arms", "contact dermatitis", "Topical steroid cream", "improving", 12),
    (2, "D2", "chest tightness on climbing stairs", "mild hypertension", "BP medication; recheck in 2 weeks", "ongoing", 14),
    (3, "D5", "knee pain after running", "ligament strain", "Physiotherapy and rest", "improving", 20),
    (4, "D4", "cough and cold", "upper respiratory infection", "Syrup twice daily", "resolved", 8),
    (5, "D1", "migraine headache", "migraine", "Pain relief, avoid triggers", "ongoing", 3),
    (6, "D2", "palpitations", "anxiety related, ECG normal", "Reduce caffeine", "resolved", 40),
    (7, "D3", "acne breakout", "acne vulgaris", "Topical retinoid", "improving", 25),
    (8, "D5", "lower back pain", "muscle spasm", "Muscle relaxant, stretching", "ongoing", 9),
    (9, "D1", "stomach pain and nausea", "gastritis", "Antacids, avoid spicy food", "improving", 6),
]

PATIENTS = [
    ("Arun", "Kumar", "9840011101"), ("Priya", "Lakshmi", "9840011102"),
    ("Ravi", "Shankar", "9840011103"), ("Divya", "Nair", "9840011104"),
    ("Karthik", "Raja", "9840011105"), ("Meera", "Subramanian", "9840011106"),
    ("Vikram", "Singh", "9840011107"), ("Anitha", "Devi", "9840011108"),
    ("Suresh", "Babu", "9840011109"), ("Fatima", "Begum", "9840011110"),
]

def main():
    d = db.get_db()
    if "--reset" in sys.argv:
        for c in ("patients", "doctors", "appointments", "visits"):
            d[c].drop()
    db.init_indexes()
    for did, name, spec, kw in DOCTORS:
        d.doctors.update_one({"doctor_id": did}, {"$set": {"name": name, "specialty": spec, "keywords": kw}}, upsert=True)
    created = [services.create_patient(f, l, p) for f, l, p in PATIENTS] if d.patients.count_documents({}) == 0 else list(d.patients.find({}, {"_id": 0}))
    if d.visits.count_documents({}) == 0:
        for i, did, comp, dx, notes, status, ago in VISITS:
            at = (services.now() - timedelta(days=ago)).replace(hour=11, minute=0, second=0, microsecond=0)
            services.add_visit(created[i]["patient_id"], did, comp, dx, notes, status, visit_at=at)
    # a few sample appointments on upcoming working days
    day, times, n = services.now().date() + timedelta(days=1), ["09:00", "10:30", "14:00", "16:30", "11:00"], 0
    for p in created[:5]:
        while services.validate_date(day):
            day += timedelta(days=1)
        services.book(p["patient_id"], DOCTORS[n % 5][0], day, times[n])
        n += 1
        day += timedelta(days=1)
    print("\nSample patients (use these IDs to test):")
    for p in created:
        print(f"  {p['patient_id']:10} {p['first_name']} {p['last_name']:15} phone {p['phone']}")
    print(f"\nDoctors: {d.doctors.count_documents({})}  Visits: {d.visits.count_documents({})}  Appointments: {d.appointments.count_documents({})}")

if __name__ == "__main__":
    main()
