# Clinic NL2SQL API Specification

## 1. Overview

This document describes the HTTP API exposed by the Clinic NL2SQL backend.

The API allows a client to:

- check whether the service is healthy
- send a natural-language question
- receive generated SQL, tabular results, and optional chart data

---

## 2. Local Development Base URL

When running locally, use:

```text
http://localhost:8000
```

Equivalent loopback URL:

```text
http://127.0.0.1:8000
```

Run the server with:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 3. Content Type

All request and response bodies are JSON unless stated otherwise.

Use this header for requests with a body:

```http
Content-Type: application/json
```

---

## 4. Endpoints Summary

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Check API health, database connectivity, and memory count |
| `POST` | `/chat` | Convert a plain-English question into SQL and return results |

---

## 5. Health Endpoint

### 5.1 Request

**Method**

```http
GET /health
```

**Full Local URL**

```text
http://localhost:8000/health
```

**Request Body**

No request body.

### 5.2 What It Does

This endpoint checks:

- whether the API is running
- whether `clinic.db` can be accessed
- how many agent memory items are currently loaded

### 5.3 Success Response

**Status Code**

```http
200 OK
```

**Example Response**

```json
{
  "status": "ok",
  "database": "connected",
  "agent_memory_items": 21
}
```

### 5.4 Response Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `status` | `string` | API health status |
| `database` | `string` | Database connection state, usually `connected` or `error` |
| `agent_memory_items` | `integer` | Number of currently available seeded memory entries |

### 5.5 cURL Example

```bash
curl http://localhost:8000/health
```

---

## 6. Chat Endpoint

### 6.1 Request

**Method**

```http
POST /chat
```

**Full Local URL**

```text
http://localhost:8000/chat
```

**Request Body Schema**

```json
{
  "question": "string"
}
```

### 6.2 Request Field

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `question` | `string` | Yes | Natural-language question about the clinic database |

### 6.3 Example Request

```json
{
  "question": "Which cities have the most patients?"
}
```

### 6.4 cURL Example

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"question\":\"Which cities have the most patients?\"}"
```

---

## 7. Chat Response Format

### 7.1 Response Schema

```json
{
  "message": "string",
  "sql_query": "string",
  "columns": ["string"],
  "rows": [["any"]],
  "row_count": 0,
  "chart": {},
  "chart_type": "string"
}
```

### 7.2 Response Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `message` | `string` | Human-readable summary or error message |
| `sql_query` | `string` | Generated SQL query or a placeholder if SQL is not exposed |
| `columns` | `array[string]` | Column names returned by the query |
| `rows` | `array[array]` | Query result rows |
| `row_count` | `integer` | Number of returned rows |
| `chart` | `object` | Plotly chart JSON when chart generation is possible |
| `chart_type` | `string` | Chart type such as `bar`, `line`, `value`, `table`, or `none` |

---

## 8. Successful Chat Response Example

### 8.1 Example Question

```json
{
  "question": "Which cities have the most patients?"
}
```

### 8.2 Example Response

```json
{
  "message": "Found 10 results.",
  "sql_query": "SELECT city, COUNT(*) AS patient_count FROM patients GROUP BY city ORDER BY patient_count DESC;",
  "columns": ["city", "patient_count"],
  "rows": [
    ["Mumbai", 28],
    ["Delhi", 24],
    ["Bangalore", 22],
    ["Hyderabad", 20],
    ["Chennai", 19]
  ],
  "row_count": 5,
  "chart": {
    "data": [
      {
        "type": "bar",
        "x": ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai"],
        "y": [28, 24, 22, 20, 19]
      }
    ],
    "layout": {
      "title": {
        "text": "patient_count by city"
      }
    }
  },
  "chart_type": "bar"
}
```

### 8.3 Notes

- `chart` is a Plotly figure dictionary and may be much larger than the shortened example above
- `rows` may contain more records than shown in the example
- `message` may come from the Vanna agent summary if available

---

## 9. Empty Question Response

If the client sends an empty or whitespace-only question, the API returns a valid response object with no results.

### 9.1 Example Request

```json
{
  "question": ""
}
```

### 9.2 Example Response

```json
{
  "message": "Please enter a question.",
  "sql_query": "",
  "columns": [],
  "rows": [],
  "row_count": 0,
  "chart": {},
  "chart_type": "none"
}
```

---

## 10. No Data Found Response

If the generated SQL runs successfully but returns no matching rows, the API returns a no-data message.

### 10.1 Example Response

```json
{
  "message": "No data found for your question. Try adjusting the filters or asking a broader question.",
  "sql_query": "SELECT id, first_name, last_name FROM patients WHERE city = 'Atlantis';",
  "columns": ["id", "first_name", "last_name"],
  "rows": [],
  "row_count": 0,
  "chart": {},
  "chart_type": "none"
}
```

---

## 11. Blocked Query Response

If the generated SQL fails the safety validation, the API blocks execution and returns a safe error response.

### 11.1 Example Response

```json
{
  "message": "Query blocked: Only SELECT queries are permitted. The generated query contains a disallowed operation.",
  "sql_query": "DELETE FROM patients;",
  "columns": [],
  "rows": [],
  "row_count": 0,
  "chart": {},
  "chart_type": "none"
}
```

### 11.2 Why This Happens

The API only allows read-only `SELECT` queries and blocks operations such as:

- `INSERT`
- `UPDATE`
- `DELETE`
- `DROP`
- `ALTER`
- `TRUNCATE`
- comment-based injection patterns

---

## 12. Agent Or Execution Error Response

If the AI agent fails or the database execution fails, the API still returns the same response structure with an error-style message.

### 12.1 Example Agent Error

```json
{
  "message": "Sorry, the AI agent encountered an error: <details>",
  "sql_query": "",
  "columns": [],
  "rows": [],
  "row_count": 0,
  "chart": {},
  "chart_type": "none"
}
```

### 12.2 Example Database Error

```json
{
  "message": "Database error: <details>",
  "sql_query": "SELECT missing_column FROM patients;",
  "columns": [],
  "rows": [],
  "row_count": 0,
  "chart": {},
  "chart_type": "none"
}
```

---

## 13. Example Frontend Usage Flow

### 13.1 Step 1: Check Server Health

```http
GET http://localhost:8000/health
```

Expected result:

- API is up
- database is connected
- memory is seeded

### 13.2 Step 2: Ask a Question

```http
POST http://localhost:8000/chat
Content-Type: application/json
```

Body:

```json
{
  "question": "How many appointments are there by status?"
}
```

Expected result:

- generated SQL
- table columns
- rows
- row count
- optional bar chart

---

## 14. Local Testing Examples

### 14.1 Browser

Open these in the browser:

- `http://localhost:8000/health`
- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`

### 14.2 FastAPI Auto Docs

Because this project uses FastAPI, these documentation routes are normally available by default:

| URL | Purpose |
| --- | --- |
| `http://localhost:8000/docs` | Swagger UI |
| `http://localhost:8000/redoc` | ReDoc documentation |
| `http://localhost:8000/openapi.json` | OpenAPI schema |

---

## 15. API Contract Notes

- The `/chat` endpoint always returns the same high-level response shape
- `row_count` is the number of rows returned in `rows`
- `chart_type` may be `none` even when table data exists
- `chart` may be an empty object when chart generation is not possible
- The backend currently uses HTTP `200 OK` for both successful business results and handled error-style responses

---

## 16. Quick Copy Section

### Health

```bash
curl http://localhost:8000/health
```

### Chat

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"question\":\"How many patients are registered in total?\"}"
```

