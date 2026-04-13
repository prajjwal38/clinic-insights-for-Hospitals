# 🏥 Clinic Insights — NL2SQL Chatbot

> Ask questions about clinic data in plain English. Get SQL, results, and charts — powered by a **local LLM (qwen3:8b via Ollama)** with zero cloud API calls.

---

## 📋 Table of Contents

1. [What This Does](#what-this-does)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Installation](#installation)
5. [Database Setup](#database-setup)
6. [Running the App](#running-the-app)
7. [Using the UI](#using-the-ui)
8. [Performance Notes](#performance-notes)
9. [Project Structure](#project-structure)
10. [API Reference](#api-reference)
11. [Troubleshooting](#troubleshooting)

---

## What This Does

This project is a **Natural Language to SQL chatbot** built on top of:

- **[Vanna 2.0](https://vanna.ai/)** — Agentic NL2SQL framework
- **[Ollama](https://ollama.com/)** + **qwen3:8b** — Fully local LLM inference (no cloud, no API keys)
- **FastAPI** — REST backend with interactive Swagger docs
- **SQLite** — Clinic database (patients, doctors, appointments, treatments, invoices)
- **Plotly** — Auto-generated charts from query results

You type a question like _"Which cities have the most patients?"_ — and get back the SQL, a data table, and a bar chart, all running on your local machine.

---

## Architecture

```
Browser (http://localhost:8000)
        │
        ▼
  FastAPI  /chat  (main.py)
        │
        ▼
  Vanna 2.0 Agent  (vanna_setup.py)
   ├─ OllamaLlmService  →  qwen3:8b  (running via Ollama)
   ├─ RunSqlTool        →  clinic.db  (SQLite)
   ├─ DemoAgentMemory   →  22 seeded Q→SQL pairs
   └─ VisualizeDataTool →  Plotly charts
```

**Flow per query:**
1. Question → Vanna Agent
2. Agent calls `qwen3:8b` to generate SQL
3. `RunSqlTool` executes SQL against `clinic.db`
4. `qwen3:8b` summarizes the result
5. FastAPI extracts data, generates Plotly chart, returns JSON
6. UI renders table + chart

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10+ | 3.12 recommended |
| [Ollama](https://ollama.com/download) | Latest | Must be installed and running |
| Git | Any | For cloning |
| GPU (optional) | RTX 3060+ | Strongly recommended for acceptable speed |

> **Without a GPU:** The app still works but expect ~60–90 seconds per query. With a GPU (e.g. RTX 4060), expect ~10–20 seconds after warm-up.

---

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/prajjwal38/clinic-insights-for-Hospitals.git
cd clinic-insights-for-Hospitals
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Pull the local LLM

```bash
ollama pull qwen3:8b
```

> This downloads ~4.7 GB. Do this once. Ollama stores the model locally so subsequent runs are instant.

---

## Database Setup

Run this **once** to create and populate `clinic.db` with 200 synthetic patient records:

```bash
python setup_database.py
```

This creates the following tables:
- `patients` — 200 records (name, city, DOB, gender, registration date)
- `doctors` — specializations, departments
- `appointments` — scheduling with status tracking
- `treatments` — procedures with costs and durations
- `invoices` — billing with payment status

---

## Running the App

### ⚡ Recommended: Keep the model warm in VRAM first

Open **Terminal 1** and run:

```bash
# Windows (PowerShell)
$env:OLLAMA_KEEP_ALIVE = "-1"

# macOS / Linux
export OLLAMA_KEEP_ALIVE=-1
```

Then start the FastAPI server in the **same terminal**:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

> Setting `OLLAMA_KEEP_ALIVE=-1` tells Ollama to **never eject the model from VRAM** between requests. Without this, each query pays a ~30-second cold-start penalty to reload the model from disk.

### What you'll see on startup

```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Waiting for application startup.
nl2sql – Initializing Agent Memory...
  [OK] Seeded: Database Schema (DDL)
  [OK] Seeded: How many patients are registered in total?
  ... (22 items total)
nl2sql – Agent Memory initialized with 22 items.
INFO:     Application startup complete.
```

---

## Using the UI

Open your browser and go to:

**→ http://localhost:8000**

You'll see a dark-themed chat interface. Either:
- Click one of the **quick chips** (Total patients, Patients by city, etc.)
- Or type any free-form question and press `Enter`

### Example questions

```
How many patients are registered in total?
Which cities have the most patients?
Who is the busiest doctor?
What is the total revenue from paid invoices?
How many appointments are there by status?
Show monthly revenue trend for the last 12 months
Which patients have overdue invoices?
```

### What the UI shows

| Section | Description |
|---|---|
| **Step indicator** | Live progress: sending → agent thinking → rendering |
| **Elapsed timer** | Shows how many seconds the query is taking |
| **AI Message** | Natural-language summary from the LLM |
| **SQL** | The exact query that was executed |
| **Chart** | Auto-generated Plotly bar/line chart where applicable |
| **Table** | Full data results with all columns and rows |

### Alternative: Swagger UI

If you prefer a raw API interface:

**→ http://localhost:8000/docs**

Use the `POST /chat` endpoint with body `{ "question": "..." }`.

---

## Performance Notes

### Expected latency

| Scenario | Response time |
|---|---|
| First query (model cold, no `OLLAMA_KEEP_ALIVE`) | ~55–70 seconds |
| **With `OLLAMA_KEEP_ALIVE=-1` (model warm in VRAM)** | **~10–20 seconds** |
| CPU-only (no GPU) | ~90–180 seconds |
| Cloud API (Gemini/GPT-4o) | ~3–8 seconds |

### Why multiple LLM calls?

Vanna 2.0 is an **agentic pipeline**, not a single prompt. Each query involves:
1. LLM reads question → decides to call `run_sql` tool
2. SQL executes → results returned to LLM
3. LLM reads results → generates natural-language summary

That's **2–3 separate LLM inference passes** per question, which is why latency is higher than a simple API call.

### SQLite is not the bottleneck

SQLite query execution takes **< 5ms** regardless of question complexity. All latency is in local LLM inference.

---

## Project Structure

```
clinic-insights-for-Hospitals/
│
├── main.py              # FastAPI app, /chat and /health endpoints
├── vanna_setup.py       # Vanna 2.0 agent wired to OllamaLlmService + SQLite
├── seed_memory.py       # Pre-seeds agent memory with 21 known-good Q→SQL pairs
├── setup_database.py    # Creates and populates clinic.db with synthetic data
│
├── static/
│   └── index.html       # Single-page chat UI (Plotly charts, step indicator)
│
├── requirements.txt     # Python dependencies
├── .gitignore
└── README.md
```

---

## API Reference

### `POST /chat`

Convert a natural language question to SQL and return results.

**Request:**
```json
{ "question": "How many patients are from Mumbai?" }
```

**Response:**
```json
{
  "message": "Found 14 patients from Mumbai.",
  "sql_query": "SELECT COUNT(*) AS count FROM patients WHERE city = 'Mumbai';",
  "columns": ["count"],
  "rows": [[14]],
  "row_count": 1,
  "chart": { ... },
  "chart_type": "value"
}
```

`chart` is a Plotly figure dict (pass directly to `Plotly.react()`).  
`chart_type` is one of: `bar`, `line`, `value`, `table`, `none`.

### `GET /health`

```json
{
  "status": "ok",
  "database": "connected",
  "agent_memory_items": 22
}
```

---

## Troubleshooting

### ❌ "Could not reach the server" in UI

- Make sure `uvicorn main:app --host 0.0.0.0 --port 8000 --reload` is running
- Check the terminal for Python errors

### ❌ Empty/no response after 90+ seconds

- Ollama may have run out of memory. Run `ollama ps` to check if the model is loaded.
- Try: `ollama run qwen3:8b` in a separate terminal to keep the model warm

### ❌ "I wasn't able to generate a SQL query"

- The agent returned a response but no SQL or data was extracted
- Check uvicorn terminal logs for `Component[0] rich_type=...` lines
- Try rephrasing: use concrete entities like "patients", "doctors", "appointments"

### ❌ Internal Server Error (500)

- Check the uvicorn terminal for a Python traceback
- Most common cause: non-JSON-serializable data types (handled by `sanitize_for_json`)

### 🐢 Queries taking 60+ seconds

1. Set `$env:OLLAMA_KEEP_ALIVE = "-1"` before starting uvicorn (keeps model in VRAM)
2. Verify Ollama is using your GPU: `ollama ps` should show `GPU` in PROCESSOR column
3. Consider a smaller model: `ollama pull qwen3:4b` and update `model=` in `vanna_setup.py`

---

## Switching Back to Gemini (Cloud)

To use Google Gemini instead of local Ollama, edit `vanna_setup.py`:

```python
# Replace this:
from vanna.integrations.ollama import OllamaLlmService
llm = OllamaLlmService(model="qwen3:8b")

# With this:
from vanna.integrations.google import GeminiLlmService
llm = GeminiLlmService(model="gemini-2.5-flash", api_key=os.environ.get("GOOGLE_API_KEY"))
```

And add `GOOGLE_API_KEY=your_key_here` to a `.env` file.

---

*Built with Vanna 2.0 · FastAPI · Ollama · qwen3:8b · SQLite · Plotly*
