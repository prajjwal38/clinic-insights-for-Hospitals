"""
seed_memory.py
==============
Pre-seeds the Vanna 2.0 DemoAgentMemory with known-good question→SQL pairs
covering a variety of clinic query patterns.

Run AFTER setup_database.py:
    python seed_memory.py
"""

import os
import uuid
import asyncio
from dotenv import load_dotenv

load_dotenv()

# ── Vanna 2.0 imports ─────────────────────────────────────────────────────────
from vanna import ToolContext, User
from vanna.integrations.local.agent_memory import DemoAgentMemory
from vanna_setup import get_agent_memory

# ─────────────────────────────────────────────────────────────────────────────
# Known-good Q→SQL pairs for the clinic database
# Format: (question, sql_query)
# ─────────────────────────────────────────────────────────────────────────────
SEED_PAIRS = [
    # ── Patient queries ──────────────────────────────────────────────────────
    (
        "How many patients are registered in total?",
        "SELECT COUNT(*) AS total_patients FROM patients;",
    ),
    (
        "List all patients from Mumbai",
        "SELECT id, first_name, last_name, email, phone, gender "
        "FROM patients WHERE city = 'Mumbai' ORDER BY last_name, first_name;",
    ),
    (
        "How many male and female patients do we have?",
        "SELECT gender, COUNT(*) AS count FROM patients "
        "GROUP BY gender ORDER BY count DESC;",
    ),
    (
        "Show patients registered in the last 30 days",
        "SELECT id, first_name, last_name, city, registered_date "
        "FROM patients "
        "WHERE registered_date >= DATE('now', '-30 days') "
        "ORDER BY registered_date DESC;",
    ),
    (
        "Which cities have the most patients?",
        "SELECT city, COUNT(*) AS patient_count "
        "FROM patients "
        "GROUP BY city "
        "ORDER BY patient_count DESC;",
    ),
    (
        "List all female patients younger than 30",
        "SELECT first_name, last_name, date_of_birth, city "
        "FROM patients "
        "WHERE gender = 'Female' "
        "AND date_of_birth >= DATE('now', '-30 years') "
        "ORDER BY date_of_birth DESC;",
    ),
    # ── Doctor queries ────────────────────────────────────────────────────────
    (
        "List all doctors and their specializations",
        "SELECT name, specialization, department FROM doctors "
        "ORDER BY specialization, name;",
    ),
    (
        "How many appointments does each doctor have?",
        "SELECT d.name, d.specialization, COUNT(a.id) AS appointment_count "
        "FROM doctors d "
        "LEFT JOIN appointments a ON d.id = a.doctor_id "
        "GROUP BY d.id, d.name, d.specialization "
        "ORDER BY appointment_count DESC;",
    ),
    (
        "Who is the busiest doctor?",
        "SELECT d.name, d.specialization, COUNT(a.id) AS appointment_count "
        "FROM doctors d "
        "JOIN appointments a ON d.id = a.doctor_id "
        "GROUP BY d.id, d.name "
        "ORDER BY appointment_count DESC "
        "LIMIT 1;",
    ),
    (
        "Show all cardiologists",
        "SELECT id, name, department, phone FROM doctors "
        "WHERE specialization = 'Cardiology';",
    ),
    # ── Appointment queries ───────────────────────────────────────────────────
    (
        "How many appointments are there by status?",
        "SELECT status, COUNT(*) AS count FROM appointments "
        "GROUP BY status ORDER BY count DESC;",
    ),
    (
        "Show all completed appointments this month",
        "SELECT a.id, p.first_name || ' ' || p.last_name AS patient_name, "
        "d.name AS doctor_name, a.appointment_date "
        "FROM appointments a "
        "JOIN patients p ON a.patient_id = p.id "
        "JOIN doctors d ON a.doctor_id = d.id "
        "WHERE a.status = 'Completed' "
        "AND strftime('%Y-%m', a.appointment_date) = strftime('%Y-%m', 'now') "
        "ORDER BY a.appointment_date DESC;",
    ),
    (
        "How many appointments were made each month in the last 6 months?",
        "SELECT strftime('%Y-%m', appointment_date) AS month, "
        "COUNT(*) AS appointment_count "
        "FROM appointments "
        "WHERE appointment_date >= DATE('now', '-6 months') "
        "GROUP BY month "
        "ORDER BY month;",
    ),
    (
        "Show no-show appointments in the last 3 months",
        "SELECT a.id, p.first_name || ' ' || p.last_name AS patient_name, "
        "d.name AS doctor, a.appointment_date "
        "FROM appointments a "
        "JOIN patients p ON a.patient_id = p.id "
        "JOIN doctors d ON a.doctor_id = d.id "
        "WHERE a.status = 'No-Show' "
        "AND a.appointment_date >= DATE('now', '-3 months') "
        "ORDER BY a.appointment_date DESC;",
    ),
    (
        "How many appointments did each doctor have this year?",
        "SELECT d.name, d.specialization, COUNT(a.id) AS total "
        "FROM doctors d "
        "JOIN appointments a ON d.id = a.doctor_id "
        "WHERE strftime('%Y', a.appointment_date) = strftime('%Y', 'now') "
        "GROUP BY d.id "
        "ORDER BY total DESC;",
    ),
    # ── Financial queries ─────────────────────────────────────────────────────
    (
        "What is the total revenue from paid invoices?",
        "SELECT ROUND(SUM(paid_amount), 2) AS total_revenue "
        "FROM invoices WHERE status = 'Paid';",
    ),
    (
        "How many invoices are unpaid or overdue?",
        "SELECT status, COUNT(*) AS count, "
        "ROUND(SUM(total_amount - paid_amount), 2) AS outstanding_amount "
        "FROM invoices "
        "WHERE status IN ('Pending', 'Overdue') "
        "GROUP BY status;",
    ),
    (
        "What is the average treatment cost per specialization?",
        "SELECT d.specialization, "
        "ROUND(AVG(t.cost), 2) AS avg_cost, "
        "ROUND(MIN(t.cost), 2) AS min_cost, "
        "ROUND(MAX(t.cost), 2) AS max_cost "
        "FROM treatments t "
        "JOIN appointments a ON t.appointment_id = a.id "
        "JOIN doctors d ON a.doctor_id = d.id "
        "GROUP BY d.specialization "
        "ORDER BY avg_cost DESC;",
    ),
    (
        "Show monthly revenue trend for the last 12 months",
        "SELECT strftime('%Y-%m', invoice_date) AS month, "
        "ROUND(SUM(paid_amount), 2) AS revenue "
        "FROM invoices "
        "WHERE invoice_date >= DATE('now', '-12 months') "
        "GROUP BY month "
        "ORDER BY month;",
    ),
    (
        "Which patients have overdue invoices?",
        "SELECT DISTINCT p.id, p.first_name || ' ' || p.last_name AS patient_name, "
        "p.email, COUNT(i.id) AS overdue_count, "
        "ROUND(SUM(i.total_amount - i.paid_amount), 2) AS total_outstanding "
        "FROM patients p "
        "JOIN invoices i ON p.id = i.patient_id "
        "WHERE i.status = 'Overdue' "
        "GROUP BY p.id "
        "ORDER BY total_outstanding DESC;",
    ),
    (
        "What are the most popular treatments?",
        "SELECT treatment_name, COUNT(*) AS frequency, "
        "ROUND(AVG(cost), 2) AS avg_cost "
        "FROM treatments "
        "GROUP BY treatment_name "
        "ORDER BY frequency DESC "
        "LIMIT 10;",
    ),
]


# ── Schema (DDL) for the clinic database ──────────────────────────────────────
SCHEMA_DDL = """
CREATE TABLE patients (
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

CREATE TABLE doctors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    specialization  TEXT NOT NULL,
    department      TEXT NOT NULL,
    phone           TEXT
);

CREATE TABLE appointments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id       INTEGER NOT NULL REFERENCES patients(id),
    doctor_id        INTEGER NOT NULL REFERENCES doctors(id),
    appointment_date DATETIME NOT NULL,
    status           TEXT NOT NULL CHECK(status IN ('Scheduled','Completed','Cancelled','No-Show')),
    notes            TEXT
);

CREATE TABLE treatments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_id   INTEGER NOT NULL REFERENCES appointments(id),
    treatment_name   TEXT NOT NULL,
    cost             REAL NOT NULL,
    duration_minutes INTEGER NOT NULL
);

CREATE TABLE invoices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id    INTEGER NOT NULL REFERENCES patients(id),
    invoice_date  TEXT NOT NULL,
    total_amount  REAL NOT NULL,
    paid_amount   REAL NOT NULL,
    status        TEXT NOT NULL CHECK(status IN ('Paid','Pending','Overdue'))
);
"""

def _make_seed_context(memory: DemoAgentMemory) -> ToolContext:
    """Build a minimal ToolContext for seeding purposes."""
    seed_user = User(
        id="seed-script",
        email="seed@clinic.local",
        group_memberships=["admin"],
    )
    return ToolContext(
        user=seed_user,
        conversation_id=f"seed-{uuid.uuid4().hex[:8]}",
        request_id=f"req-{uuid.uuid4().hex[:8]}",
        agent_memory=memory,
    )


async def seed_memory(memory: DemoAgentMemory = None) -> int:
    """
    Push schema and all seed pairs into the AgentMemory.
    Returns the number of items seeded.
    """
    if memory is None:
        memory = get_agent_memory()

    seeded_count = 0
    ctx = _make_seed_context(memory)

    # 1. Seed Schema (Critical for LLM generation)
    await memory.save_text_memory(content=f"Database Schema:\n{SCHEMA_DDL}", context=ctx)
    print("  [OK] Seeded: Database Schema (DDL)")
    seeded_count += 1

    # 2. Seed Q->SQL Pairs
    for question, sql in SEED_PAIRS:
        await memory.save_tool_usage(
            question=question,
            tool_name="run_sql",
            args={"sql": sql},
            context=ctx,
            success=True,
            metadata={"source": "seed_script"},
        )
        seeded_count += 1
        preview = question[:65] + ("..." if len(question) > 65 else "")
        print(f"  [OK] Seeded: {preview}")

    return seeded_count


if __name__ == "__main__":
    async def run_standalone():
        count = await seed_memory()
        print()
        print("=" * 60)
        print(f"  Agent memory seeded with {count} items (schema + pairs).")
        print("=" * 60)

    asyncio.run(run_standalone())
