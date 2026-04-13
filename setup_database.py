"""
setup_database.py
=================
Creates and populates the clinic.db SQLite database with realistic dummy data.

Run: python setup_database.py
"""

import sqlite3
import random
import os
from datetime import datetime, timedelta, date

# ── Constants ──────────────────────────────────────────────────────────────────
DB_PATH = "clinic.db"
SEED    = 42
random.seed(SEED)

# ── Lookup tables ──────────────────────────────────────────────────────────────
FIRST_NAMES = [
    "Aarav", "Aditya", "Akash", "Amit", "Ananya", "Anjali", "Arjun",
    "Deepa", "Divya", "Gaurav", "Ishaan", "Kavya", "Kiran", "Lakshmi",
    "Manish", "Meera", "Mohit", "Nisha", "Pooja", "Priya", "Rahul",
    "Raj", "Riya", "Rohan", "Sakshi", "Sanjay", "Sara", "Shreya",
    "Sneha", "Suresh", "Tanvi", "Varun", "Vijay", "Vimal", "Yash",
    "Zara", "Nikhil", "Kritika", "Siddharth", "Swati", "Harsh",
    "Neha", "Kunal", "Preeti", "Vivek", "Shweta", "Abhishek",
    "Chandni", "Girish", "Heena",
]

LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Gupta", "Kumar", "Singh", "Mehta",
    "Joshi", "Rao", "Nair", "Iyer", "Reddy", "Choudhary", "Malhotra",
    "Khanna", "Bose", "Chatterjee", "Agarwal", "Jain", "Tiwari",
    "Banerjee", "Desai", "Shah", "Pillai", "Naidu",
]

CITIES = [
    "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai",
    "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Lucknow",
]

GENDERS   = ["Male", "Female", "Other"]
DOMAINS   = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com"]

DOCTORS = [
    # (name, specialization, department)
    ("Dr. Ramesh Sharma",    "Cardiology",    "Cardiology"),
    ("Dr. Priya Nair",       "Cardiology",    "Cardiology"),
    ("Dr. Suresh Kumar",     "Cardiology",    "Cardiology"),
    ("Dr. Anita Mehta",      "Dermatology",   "Dermatology"),
    ("Dr. Vikram Reddy",     "Dermatology",   "Dermatology"),
    ("Dr. Kavitha Iyer",     "Dermatology",   "Dermatology"),
    ("Dr. Amit Patel",       "Orthopedics",   "Orthopedics"),
    ("Dr. Sunita Gupta",     "Orthopedics",   "Orthopedics"),
    ("Dr. Rahul Verma",      "Orthopedics",   "Orthopedics"),
    ("Dr. Deepak Joshi",     "General",       "General Medicine"),
    ("Dr. Meena Rao",        "General",       "General Medicine"),
    ("Dr. Arun Singh",       "General",       "General Medicine"),
    ("Dr. Pooja Malhotra",   "Pediatrics",    "Pediatrics"),
    ("Dr. Kiran Bose",       "Pediatrics",    "Pediatrics"),
    ("Dr. Sneha Agarwal",    "Pediatrics",    "Pediatrics"),
]

APPOINTMENT_STATUSES = ["Scheduled", "Completed", "Cancelled", "No-Show"]
STATUS_WEIGHTS       = [0.15, 0.55, 0.20, 0.10]   # realistic distribution

TREATMENTS = {
    "Cardiology":  ["ECG", "Echocardiography", "Stress Test", "Angioplasty", "Pacemaker Check"],
    "Dermatology": ["Skin Biopsy", "Acne Treatment", "Laser Therapy", "Allergy Testing", "Phototherapy"],
    "Orthopedics": ["X-Ray", "Physiotherapy", "Bone Density Test", "Joint Aspiration", "Splinting"],
    "General":     ["Blood Test", "Urine Test", "General Check-up", "Vaccination", "Thyroid Panel"],
    "Pediatrics":  ["Growth Assessment", "Immunization", "Developmental Screening", "Nutrition Counseling", "Vision Test"],
}

TREATMENT_COST_RANGES = {
    "Cardiology":  (500,  5000),
    "Dermatology": (200,  3000),
    "Orthopedics": (300,  4000),
    "General":     (50,   1500),
    "Pediatrics":  (100,  2000),
}

INVOICE_STATUSES = ["Paid", "Pending", "Overdue"]
INV_STATUS_WEIGHTS = [0.55, 0.30, 0.15]


# ── Helpers ─────────────────────────────────────────────────────────────────────
def rnd_date(start: date, end: date) -> date:
    """Return a random date between start and end (inclusive)."""
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def rnd_datetime(start: date, end: date) -> str:
    """Return a random datetime string (YYYY-MM-DD HH:MM:SS) between start and end."""
    d    = rnd_date(start, end)
    hour = random.randint(8, 17)
    mins = random.choice([0, 15, 30, 45])
    return f"{d} {hour:02d}:{mins:02d}:00"


def maybe_null(value, probability: float = 0.12):
    """Return None with given probability, else return value."""
    return None if random.random() < probability else value


# ── Schema creation ──────────────────────────────────────────────────────────────
CREATE_STATEMENTS = """
CREATE TABLE IF NOT EXISTS patients (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    email           TEXT,
    phone           TEXT,
    date_of_birth   TEXT NOT NULL,
    gender          TEXT NOT NULL,
    city            TEXT NOT NULL,
    registered_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS doctors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    specialization  TEXT NOT NULL,
    department      TEXT NOT NULL,
    phone           TEXT
);

CREATE TABLE IF NOT EXISTS appointments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id       INTEGER NOT NULL REFERENCES patients(id),
    doctor_id        INTEGER NOT NULL REFERENCES doctors(id),
    appointment_date DATETIME NOT NULL,
    status           TEXT NOT NULL CHECK(status IN ('Scheduled','Completed','Cancelled','No-Show')),
    notes            TEXT
);

CREATE TABLE IF NOT EXISTS treatments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_id   INTEGER NOT NULL REFERENCES appointments(id),
    treatment_name   TEXT NOT NULL,
    cost             REAL NOT NULL,
    duration_minutes INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS invoices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id    INTEGER NOT NULL REFERENCES patients(id),
    invoice_date  TEXT NOT NULL,
    total_amount  REAL NOT NULL,
    paid_amount   REAL NOT NULL,
    status        TEXT NOT NULL CHECK(status IN ('Paid','Pending','Overdue'))
);
"""


def build_database():
    # Remove stale database so we always start fresh
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.executescript(CREATE_STATEMENTS)

    today  = date.today()
    yr_ago = today - timedelta(days=365)

    # ── 1. Doctors (15) ────────────────────────────────────────────────────────
    doctor_rows = []
    for name, spec, dept in DOCTORS:
        phone = f"+91-{random.randint(7000000000, 9999999999)}"
        doctor_rows.append((name, spec, dept, phone))

    cursor.executemany(
        "INSERT INTO doctors (name, specialization, department, phone) VALUES (?,?,?,?)",
        doctor_rows,
    )
    doctor_ids = [row[0] for row in cursor.execute("SELECT id FROM doctors").fetchall()]

    # Build a map: doctor_id → specialization
    doc_spec  = {}
    doc_rows  = cursor.execute("SELECT id, specialization FROM doctors").fetchall()
    for did, spec in doc_rows:
        doc_spec[did] = spec

    # ── 2. Patients (200) ──────────────────────────────────────────────────────
    # Make some patients "frequent visitors" by assigning a weight
    patient_ids: list[int] = []
    for _ in range(200):
        fn    = random.choice(FIRST_NAMES)
        ln    = random.choice(LAST_NAMES)
        email = maybe_null(f"{fn.lower()}.{ln.lower()}{random.randint(1,99)}@{random.choice(DOMAINS)}")
        phone = maybe_null(f"+91-{random.randint(7000000000, 9999999999)}")
        dob   = rnd_date(date(1950, 1, 1), date(2015, 12, 31))
        gen   = random.choices(GENDERS, weights=[0.48, 0.48, 0.04])[0]
        city  = random.choice(CITIES)
        reg   = rnd_date(yr_ago, today)

        cursor.execute(
            "INSERT INTO patients (first_name, last_name, email, phone, date_of_birth, gender, city, registered_date) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (fn, ln, email, phone, str(dob), gen, city, str(reg)),
        )
        patient_ids.append(cursor.lastrowid)

    # ── 3. Appointments (500) ─────────────────────────────────────────────────
    # 20 "busy" patients get ~5-10 appointments; rest get 1-3
    busy_patients   = random.sample(patient_ids, 20)
    busy_weight_map = {pid: random.randint(5, 10) for pid in busy_patients}

    # Build weighted patient list to draw from
    appt_patient_pool = []
    for pid in patient_ids:
        weight = busy_weight_map.get(pid, random.randint(1, 3))
        appt_patient_pool.extend([pid] * weight)

    # Some doctors are busier
    busy_doctors   = random.sample(doctor_ids, 5)
    doctor_weights = [4 if did in busy_doctors else 1 for did in doctor_ids]

    completed_appt_ids: list[int] = []
    appt_patient_map: dict[int, int] = {}   # appt_id → patient_id for invoices

    appointment_rows = []
    for _ in range(500):
        pid    = random.choice(appt_patient_pool)
        did    = random.choices(doctor_ids, weights=doctor_weights)[0]
        dt     = rnd_datetime(yr_ago, today)
        status = random.choices(APPOINTMENT_STATUSES, weights=STATUS_WEIGHTS)[0]
        notes  = maybe_null(random.choice([
            "Follow-up required", "Lab results pending", "Prescribed medication",
            "Referred to specialist", "Routine checkup", "Post-surgery review",
            "Chronic condition monitoring", "Vaccination administered",
        ]), 0.35)

        appointment_rows.append((pid, did, dt, status, notes))

    cursor.executemany(
        "INSERT INTO appointments (patient_id, doctor_id, appointment_date, status, notes) "
        "VALUES (?,?,?,?,?)",
        appointment_rows,
    )

    # Retrieve all appointments to know their IDs and filter completed ones
    all_appts = cursor.execute(
        "SELECT id, patient_id, doctor_id, status FROM appointments"
    ).fetchall()
    for aid, pid, did, status in all_appts:
        appt_patient_map[aid] = pid
        if status == "Completed":
            completed_appt_ids.append((aid, did))

    # ── 4. Treatments (350) – only for completed appointments ─────────────────
    if len(completed_appt_ids) < 350:
        # sample with replacement if we don't have enough completed appts
        sampled = random.choices(completed_appt_ids, k=350)
    else:
        sampled = random.sample(completed_appt_ids, 350)

    treatment_rows = []
    for aid, did in sampled:
        spec        = doc_spec.get(did, "General")
        t_name      = random.choice(TREATMENTS.get(spec, TREATMENTS["General"]))
        lo, hi      = TREATMENT_COST_RANGES.get(spec, (50, 5000))
        cost        = round(random.uniform(lo, hi), 2)
        duration    = random.choice([15, 20, 30, 45, 60, 90])
        treatment_rows.append((aid, t_name, cost, duration))

    cursor.executemany(
        "INSERT INTO treatments (appointment_id, treatment_name, cost, duration_minutes) "
        "VALUES (?,?,?,?)",
        treatment_rows,
    )

    # ── 5. Invoices (300) ─────────────────────────────────────────────────────
    # Pick 300 distinct patients (or repeat if fewer than 300)
    invoice_patient_ids = random.choices(patient_ids, k=300)

    invoice_rows = []
    for pid in invoice_patient_ids:
        inv_date     = rnd_date(yr_ago, today)
        total        = round(random.uniform(100, 15000), 2)
        inv_status   = random.choices(INVOICE_STATUSES, weights=INV_STATUS_WEIGHTS)[0]

        if inv_status == "Paid":
            paid = total
        elif inv_status == "Pending":
            paid = round(total * random.uniform(0, 0.5), 2)
        else:   # Overdue
            paid = round(total * random.uniform(0, 0.3), 2)

        invoice_rows.append((pid, str(inv_date), total, paid, inv_status))

    cursor.executemany(
        "INSERT INTO invoices (patient_id, invoice_date, total_amount, paid_amount, status) "
        "VALUES (?,?,?,?,?)",
        invoice_rows,
    )

    conn.commit()

    # ── Summary ───────────────────────────────────────────────────────────────
    n_patients    = cursor.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    n_doctors     = cursor.execute("SELECT COUNT(*) FROM doctors").fetchone()[0]
    n_appts       = cursor.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
    n_treatments  = cursor.execute("SELECT COUNT(*) FROM treatments").fetchone()[0]
    n_invoices    = cursor.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]

    conn.close()

    print("=" * 55)
    print(f"  clinic.db created successfully!")
    print("=" * 55)
    print(f"  Created {n_patients}   patients")
    print(f"  Created {n_doctors}    doctors")
    print(f"  Created {n_appts}  appointments")
    print(f"  Created {n_treatments}  treatments")
    print(f"  Created {n_invoices}  invoices")
    print("=" * 55)


if __name__ == "__main__":
    build_database()
