# Clinic NL2SQL Project Overview

## 1. Project Summary

This project converts plain English questions into SQL queries for a clinic database.

The main goal is:

> Let a user ask business questions like "How many patients are from Mumbai?" and get back structured database results without writing SQL manually.

This is an **NL2SQL system** built with:

- `FastAPI` for the backend API
- `Vanna 2.0` for natural-language-to-SQL generation
- `Google Gemini` as the LLM behind Vanna
- `SQLite` as the clinic database
- `Pandas + Plotly` for result shaping and chart generation

---

## 2. Problem Statement

Non-technical users usually cannot query a database directly.

They know the business question:

- How many appointments were completed this month?
- Which doctors are busiest?
- Which patients have overdue invoices?

But they do not know:

- SQL syntax
- table names
- join relationships
- filtering logic
- aggregation logic

So the problem this project solves is:

> How can we allow a user to ask questions in natural language and safely transform those questions into correct SQL queries over a clinic database?

---

## 3. What Is Happening In This Project

At a high level, the system does this:

1. A user sends a plain-English question to the API.
2. The API forwards that question to the Vanna agent.
3. Vanna uses Gemini plus previously seeded memory to generate SQL.
4. The backend extracts the SQL from the agent response.
5. The backend validates that the SQL is safe.
6. The backend runs the SQL directly on `clinic.db`.
7. The backend converts the result into JSON.
8. The backend tries to generate a chart from the result.
9. The API returns message + SQL + rows + chart metadata.

So the project is not "chat only".

It is actually a full pipeline:

`Question -> AI Agent -> SQL -> Validation -> Database -> Results -> Optional Visualization -> API Response`

---

## 4. Core Purpose Of Each File

| File | Responsibility |
| --- | --- |
| `main.py` | Main FastAPI application. Exposes `/chat` and `/health`. Handles SQL validation, query execution, and chart generation. |
| `vanna_setup.py` | Builds and caches the Vanna agent. Connects Gemini, SQLite runner, tools, and shared memory. |
| `seed_memory.py` | Preloads the Vanna memory with schema information and known good question-to-SQL examples. |
| `setup_database.py` | Creates `clinic.db` and fills it with realistic dummy clinic data. |
| `clinic.db` | The SQLite database queried by the application. |
| `requirements.txt` | Python dependencies for the project. |
| `.env` | Stores environment configuration like `GOOGLE_API_KEY`. |
| `c42d0ec1e6e11801/` | Generated output artifacts such as exported query result CSV files. |

---

## 5. Architecture

### 5.1 High-Level Architecture

```text
User / Frontend / API Client
            |
            v
      FastAPI (`main.py`)
            |
            v
     Vanna Agent (`vanna_setup.py`)
            |
    -------------------------
    |           |           |
    v           v           v
 Gemini LLM   Memory      SQL Tool Registry
                |               |
                v               v
      Seeded Question/SQL     SQLite Runner
           Knowledge              |
                                  v
                           `clinic.db`
                                  |
                                  v
                         Query Result Dataset
                                  |
                                  v
                    Pandas + Plotly Chart Builder
                                  |
                                  v
                           JSON API Response
```

### 5.2 Runtime Component Roles

| Component | Role |
| --- | --- |
| `FastAPI app` | Entry point for HTTP requests |
| `Vanna Agent` | Interprets user question and generates SQL-oriented response components |
| `GeminiLlmService` | LLM used by Vanna for reasoning and SQL generation |
| `DemoAgentMemory` | Temporary in-memory knowledge store for schema and successful query examples |
| `RunSqlTool` | Tool registered inside Vanna to support SQL execution workflows |
| `VisualizeDataTool` | Tool registered for chart-oriented responses |
| `SqliteRunner` | Connects Vanna tooling to the SQLite database |
| `main.py run_query()` | Direct SQL execution path after safety validation |
| `generate_chart()` | Heuristic chart builder using result shape |

---

## 6. How Things Are Connected

### 6.1 Main Connection Chain

The main dependency chain is:

- `main.py` imports `get_agent`, `get_agent_memory`, and `DB_PATH` from `vanna_setup.py`
- `vanna_setup.py` creates the shared Vanna agent and shared memory
- `main.py` calls the agent for NL-to-SQL generation
- `main.py` executes the generated SQL against `clinic.db`
- `seed_memory.py` fills the same shared memory instance used by the agent
- `setup_database.py` creates the database that both the agent tools and direct query executor rely on

### 6.2 Startup Connection

When the API starts:

1. FastAPI triggers the startup event.
2. The startup event imports and calls `seed_memory()`.
3. `seed_memory()` pushes schema + example Q-to-SQL pairs into shared memory.
4. From that point onward, the Vanna agent has context about the clinic schema and example query patterns.

This is important because the current memory backend is **in-memory only**.

That means:

- if the server restarts, memory is lost
- so the application reseeds memory every startup

---

## 7. Request Flow

### 7.1 `/chat` Flow

```text
POST /chat
   |
   v
Receive question
   |
   v
Send message to Vanna agent
   |
   v
Collect streamed components
   |
   +--> Extract natural-language summary
   |
   +--> Extract SQL artifact
   |
   v
Validate SQL
   |
   +--> If unsafe: block request
   |
   v
Run SQL on SQLite database
   |
   +--> If execution error: return error message
   |
   v
Build chart from result shape
   |
   v
Return structured response
```

### 7.2 `/health` Flow

`GET /health` checks:

- whether the database is reachable
- whether agent memory is available
- how many memory items are currently stored

This endpoint is useful for debugging startup and readiness.

---

## 8. API Naming And Port Details

### 8.1 Application Port

The app is intended to run with:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

So the default API port is:

- `8000`

### 8.2 Endpoint Names

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Health and readiness check |
| `POST` | `/chat` | Accepts a natural-language question and returns SQL + results + chart |

### 8.3 Request/Response Model Names

| Model | Purpose |
| --- | --- |
| `ChatRequest` | Input model with field `question` |
| `ChatResponse` | Output model with message, SQL, columns, rows, row count, chart, and chart type |

---

## 9. Database Architecture

The project uses a single SQLite database:

- Database file: `clinic.db`

### 9.1 Tables

| Table | Purpose |
| --- | --- |
| `patients` | Stores patient profile and registration information |
| `doctors` | Stores doctor profile, specialization, and department |
| `appointments` | Connects patients and doctors with appointment events |
| `treatments` | Stores treatments performed for completed appointments |
| `invoices` | Stores payment and billing information for patients |

### 9.2 Relationships

```text
patients
   |
   +--> appointments <--+ doctors
             |
             +--> treatments
             |
             +--> business linkage to invoices happens through patient_id

patients
   |
   +--> invoices
```

### 9.3 Data Volume Generated By `setup_database.py`

The database builder creates approximately:

- `200` patients
- `15` doctors
- `500` appointments
- `350` treatments
- `300` invoices

This gives the AI enough realistic sample data to answer many clinic analytics questions.

---

## 10. AI Memory Design

The memory layer is used to improve SQL generation quality.

It stores:

- the clinic schema DDL
- known good question-to-SQL examples

This helps the model learn:

- correct table names
- correct columns
- correct join paths
- common analytics patterns
- domain-specific wording such as appointments, invoices, patients, doctors, treatments

### 10.1 Seed Content

`seed_memory.py` preloads examples for:

- patient questions
- doctor questions
- appointment questions
- finance questions
- treatment popularity and revenue trends

This is one of the most important parts of the project because it reduces random SQL generation mistakes.

---

## 11. SQL Safety Layer

The project does not blindly run any SQL coming from the LLM.

Before execution, `main.py` validates the SQL and allows only safe read queries.

### Allowed

- `SELECT ...`

### Blocked

- `INSERT`
- `UPDATE`
- `DELETE`
- `DROP`
- `ALTER`
- `TRUNCATE`
- `CREATE`
- `REPLACE`
- `EXEC`
- `GRANT`
- `REVOKE`
- direct system schema access like `sqlite_master`
- SQL comment-based injection patterns

This is the project's main protection layer against destructive or unsafe SQL.

---

## 12. Visualization Logic

After query execution, the system tries to automatically create a chart.

Current chart heuristics:

- 2 columns where second column is numeric -> `bar` chart
- first column looks like `YYYY-MM` and a numeric column exists -> `line` chart
- single cell result -> `value`
- otherwise -> `table` or no chart

So the charting logic is not fully AI-designed.

It is a rule-based helper built on top of query results.

---

## 13. Current Working Flow In Simple Words

If someone asks:

> "Which cities have the most patients?"

the project currently does this:

1. Receives the question in `/chat`
2. Sends it to Vanna
3. Vanna checks its memory and schema context
4. Gemini helps produce SQL
5. Backend extracts the SQL
6. Backend confirms it is a safe `SELECT`
7. SQLite runs the query
8. Result rows are converted into JSON
9. A bar chart may be generated automatically
10. Response is returned to the client

---

## 14. Current Problem Areas / Notes

The project structure is solid for a prototype, but there are some important realities:

| Area | Current State |
| --- | --- |
| Memory persistence | `DemoAgentMemory` is in-memory only, so knowledge is lost after restart |
| Startup dependency | Memory must be reseeded every time the app starts |
| Environment dependency | `GOOGLE_API_KEY` must exist in `.env` |
| Database type | SQLite is simple and good for demo/prototype, but not ideal for high concurrency production use |
| Security model | SQL is validated, but the user model is currently a default admin-like resolver |
| Visualization | Chart creation is heuristic, not guaranteed to match every result set perfectly |
| Standalone seeding script | `seed_memory.py` uses `asyncio.run(...)` in `__main__` but does not currently import `asyncio` |

---

## 15. Architecture In One Sentence

This project is a **FastAPI-based clinic analytics backend** where **Vanna + Gemini translate natural language into SQL**, the backend **validates and executes that SQL on SQLite**, and then returns **structured data plus optional charts**.

---

## 16. Recommended Mental Model

The easiest way to understand this codebase is to think in 4 layers:

| Layer | What it does |
| --- | --- |
| `Data Layer` | `clinic.db` and its tables |
| `AI Layer` | Vanna agent + Gemini + memory |
| `Backend Layer` | FastAPI endpoints, SQL validation, query execution |
| `Presentation Layer` | JSON response and optional chart payload |

Short version:

`Database knowledge + AI translation + backend safety + visual response`

---

## 17. If You Want To Explain This Project To Someone Else

You can say:

> This is an NL2SQL clinic assistant. A user asks a question in normal English, the system converts it into SQL using Vanna and Gemini, safely runs it on a clinic SQLite database, and returns both table results and chart-ready output through a FastAPI API.

---

## 18. Suggested Next Documentation Files

If we want to organize the project even better later, the next useful files would be:

- `README.md` -> quick start and setup
- `API_SPEC.md` -> request and response examples
- `DATABASE_SCHEMA.md` -> detailed table and column documentation
- `DEPLOYMENT.md` -> environment variables and production deployment steps
