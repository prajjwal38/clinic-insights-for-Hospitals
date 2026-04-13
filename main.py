"""
main.py
=======
FastAPI application exposing the Vanna 2.0 NL-to-SQL chatbot.

Endpoints:
    POST /chat   – Convert a natural-language question to SQL and return results
    GET  /health – Health check with agent memory item count

Run:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import re
import os
import uuid
import sqlite3
import logging
from typing import Any

import pandas as pd
import plotly.express as px
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# ── Vanna 2.0 ─────────────────────────────────────────────────────────────────
from vanna import ArtifactComponent, DataFrameComponent, RichTextComponent
from vanna.core.user import RequestContext
from vanna_setup import get_agent, get_agent_memory, DB_PATH

# ── Tracks how many items were seeded into agent memory at startup ─────────────
_seeded_memory_count: int = 0

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
logger = logging.getLogger("nl2sql")

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Clinic NL2SQL API",
    description="Ask questions about the clinic database in plain English.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Serve the chat UI (no-cache for dev) ─────────────────────────────────────
from fastapi.responses import FileResponse

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/ui")

@app.get("/ui", include_in_schema=False)
@app.get("/ui/", include_in_schema=False)
async def serve_ui():
    return FileResponse(
        os.path.join(_STATIC_DIR, "index.html"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


# ── Request / Response models ─────────────────────────────────────────────────
class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    message: str
    sql_query: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    chart: dict
    chart_type: str


# ── JSON-safe serializer ───────────────────────────────────────────────────────────
def sanitize_for_json(obj: Any) -> Any:
    """
    Recursively convert numpy scalars, pandas Timestamps, and other
    non-JSON-serializable types into plain Python primitives.
    Called on rows and chart dicts before they leave the server.
    """
    import numpy as np
    import math
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(v) for v in obj]
    if isinstance(obj, bool):          # must come before int check
        return obj
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(obj, np.ndarray):
        return sanitize_for_json(obj.tolist())
    if hasattr(obj, 'isoformat'):       # datetime / pd.Timestamp
        return obj.isoformat()
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    return obj


# ── SQL validation ────────────────────────────────────────────────────────────
ALLOWED_STMT = re.compile(r"^\s*SELECT\b", re.IGNORECASE)

BLOCKED_PATTERNS = [
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE)\b",
    r"\b(EXEC|EXECUTE)\b",
    r"\bxp_\w+",
    r"\bsp_\w+",
    r"\b(GRANT|REVOKE)\b",
    r"\bSHUTDOWN\b",
    r"\bsqlite_master\b",
    r"\bsqlite_schema\b",
    r"\bsqlite_temp_master\b",
    r"--",          # SQL single-line comment injection
    r"/\*",         # SQL block comment injection
]
BLOCKED_RE = re.compile("|".join(BLOCKED_PATTERNS), re.IGNORECASE)


def validate_sql(sql: str) -> tuple[bool, str]:
    """
    Validate that `sql` is a safe, read-only SELECT statement.

    Returns:
        (True,  "")        – valid
        (False, error_msg) – invalid
    """
    stripped = sql.strip()
    if not stripped:
        return False, "The generated query is empty."

    if not ALLOWED_STMT.match(stripped):
        return False, (
            "Hold up! 🛑 Is that... a non-SELECT query? "
            "We only do read-only operations here. Go try your dark magic elsewhere!"
        )

    if BLOCKED_RE.search(stripped):
        return False, (
            "Nice try, Bobby Tables! 🕵️‍♂️ "
            "Did you really think I'd let you DROP, UPDATE, or DELETE my precious data? "
            "This is a READ-ONLY zone. Move along before I call the DB admins."
        )

    return True, ""


# ── Direct query execution (bypasses agent for validation+execution) ───────────
def run_query(sql: str) -> tuple[list[str], list[list[Any]]]:
    """
    Execute the SQL query against clinic.db and return (columns, rows).
    Raises RuntimeError on DB errors.
    """
    try:
        conn    = sqlite3.connect(DB_PATH)
        cursor  = conn.cursor()
        cursor.execute(sql)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows    = [list(row) for row in cursor.fetchall()]
        conn.close()
        return columns, rows
    except sqlite3.Error as exc:
        raise RuntimeError(f"Database error: {exc}") from exc


# ── Chart generation ──────────────────────────────────────────────────────────
def generate_chart(columns: list[str], rows: list[list[Any]]) -> tuple[dict, str]:
    """
    Attempt to build a Plotly chart from query results.
    Returns (chart_json_dict, chart_type).
    chart_json_dict is empty when no chart can be inferred.
    """
    if not rows or not columns:
        return {}, "none"

    df = pd.DataFrame(rows, columns=columns)

    # 2-column: categorical × numeric → bar chart
    if len(columns) == 2:
        c0, c1 = columns
        if pd.api.types.is_numeric_dtype(df[c1]):
            fig = px.bar(df, x=c0, y=c1, title=f"{c1} by {c0}")
            return fig.to_dict(), "bar"

    # Date/period in first column → line chart
    if len(columns) >= 2 and rows:
        first_val = str(rows[0][0]) if rows else ""
        if re.match(r"^\d{4}-\d{2}", first_val):
            c0   = columns[0]
            nums = [c for c in columns[1:] if pd.api.types.is_numeric_dtype(df[c])]
            if nums:
                fig = px.line(df, x=c0, y=nums[0], title=f"{nums[0]} over {c0}")
                return fig.to_dict(), "line"

    # Single value result
    if len(columns) == 1 and len(rows) == 1:
        return {}, "value"

    # Multiple columns with numeric → bar on first pair
    num_cols = [c for c in columns if pd.api.types.is_numeric_dtype(df[c])]
    if num_cols and len(columns) > 1:
        x_col = next((c for c in columns if c not in num_cols), columns[0])
        fig   = px.bar(df, x=x_col, y=num_cols[0], title=f"{num_cols[0]} by {x_col}")
        return fig.to_dict(), "bar"

    return {}, "table"


# ── Start-up Seeding ──────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    """
    Seed the Vanna agent memory on startup. 
    This is necessary because DemoAgentMemory is in-memory and 
    lost when the server process restarts.
    """
    global _seeded_memory_count
    from seed_memory import seed_memory
    logger.info("Initializing Agent Memory...")
    _seeded_memory_count = await seed_memory()
    logger.info("Agent Memory initialized with %d items.", _seeded_memory_count)


# ── Extract SQL from Vanna streaming components ───────────────────────────────
_SQL_CODE_FENCE = re.compile(r"```(?:sql)?\s*\n?(.*?)\n?```", re.DOTALL | re.IGNORECASE)
_SQL_SELECT     = re.compile(r"(SELECT\b.+?;)", re.DOTALL | re.IGNORECASE)


def _extract_sql_from_components(components: list) -> str:
    """
    Multi-strategy SQL extractor.
    UiComponent wraps rich_component (RichComponent) and simple_component.
    SQL sometimes appears in simple_component.text as a CSV preview with the
    executed SQL embedded, or in a code-fence in the text.
    """
    all_text: list[str] = []

    for comp in components:
        # Strategy 1: rich_component is an ArtifactComponent with artifact_type=sql
        rich = getattr(comp, "rich_component", None)
        if rich is not None:
            r_type = str(getattr(rich, "type", "")).lower()
            if "artifact" in r_type:
                a_type = str(getattr(rich, "artifact_type", "")).lower()
                content = getattr(rich, "content", "") or ""
                if "sql" in a_type and content.strip():
                    logger.info("SQL via rich ArtifactComponent.")
                    return content.strip()

        # Collect text from simple_component for fallback strategies
        simple = getattr(comp, "simple_component", None)
        if simple is not None:
            text = getattr(simple, "text", "") or ""
            if text:
                all_text.append(text)

    combined = "\n".join(all_text)

    # Strategy 2: ```sql ... ``` code fence in text
    m = _SQL_CODE_FENCE.search(combined)
    if m:
        sql = m.group(1).strip()
        if sql.upper().startswith("SELECT"):
            logger.info("SQL via code-fence fallback.")
            return sql

    # Strategy 3: bare SELECT ... ; in text
    m = _SQL_SELECT.search(combined)
    if m:
        logger.info("SQL via raw-SELECT fallback.")
        return m.group(1).strip()

    return ""



def _extract_message_from_components(components: list) -> str:
    """Extract natural-language summary from components."""
    for comp in components:
        c_type = str(getattr(comp, "type", "")).lower()
        if "richtext" in c_type or "rich_text" in c_type:
            content = getattr(comp, "content", "")
            if isinstance(content, str): return content
            if isinstance(content, list):
                return " ".join(str(b.get("text", b)) if isinstance(b, dict) else str(b) for b in content)
    return ""


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    """
    Returns API health status and the number of seeded memory items.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("SELECT 1")
        conn.close()
        db_status = "connected"
    except Exception:
        db_status = "error"

    return {
        "status": "ok",
        "database": db_status,
        "agent_memory_items": _seeded_memory_count,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Convert a natural-language question to SQL, execute it, and return results.

    Flow:
        1. Send question to Vanna Agent → receive streamed UiComponents
        2. Extract SQL from ArtifactComponent (artifact_type='sql')
        3. Validate the SQL (security gate – SELECT only)
        4. Execute against clinic.db
        5. Generate a Plotly chart heuristically
        6. Return structured response

    Request body:
        { "question": "How many patients are from Mumbai?" }
    """
    question = request.question.strip()
    logger.info("Received question: %s", question)

    if not question:
        return ChatResponse(
            message="Please enter a question.",
            sql_query="",
            columns=[],
            rows=[],
            row_count=0,
            chart={},
            chart_type="none",
        )

    # ── Step 1: Stream agent response and collect components ──────────────────
    agent           = get_agent()
    request_context = RequestContext()   # anonymous / default headers

    collected: list = []
    try:
        async for component in agent.send_message(
            request_context=request_context,
            message=question,
            conversation_id=uuid.uuid4().hex,
        ):
            c_type = str(getattr(component, "type", "unknown"))
            a_type = str(getattr(component, "artifact_type", "n/a"))
            logger.info("Agent yielded component: %s (artifact_type: %s)", c_type, a_type)
            collected.append(component)
    except Exception as exc:
        logger.exception("Agent error during send_message")
        return ChatResponse(
            message=f"Sorry, the AI agent encountered an error: {exc}",
            sql_query="",
            columns=[],
            rows=[],
            row_count=0,
            chart={},
            chart_type="none",
        )

    # ── Step 2: Extract results from agent components ─────────────────────────
    sql = _extract_sql_from_components(collected)

    # Log what each component actually looks like
    for i, comp in enumerate(collected):
        rich = getattr(comp, "rich_component", None)
        simple = getattr(comp, "simple_component", None)
        logger.info(
            "Component[%d] rich_type=%s rows=%s | simple_text_preview=%s",
            i,
            getattr(rich, "type", "?"),
            len(getattr(rich, "rows", None) or []),
            str(getattr(simple, "text", ""))[:80],
        )

    # --- DataFrameComponent is at UiComponent.rich_component ---
    def _read_df_component(comp) -> tuple[list, list] | None:
        """Read rows/columns from UiComponent.rich_component (DataFrameComponent)."""
        rich = getattr(comp, "rich_component", None)
        if rich is None:
            return None

        r_type = str(getattr(rich, "type", "")).lower()
        if "dataframe" not in r_type and "table" not in r_type:
            return None

        cols = getattr(rich, "columns", None)
        rows = getattr(rich, "rows", None)
        if cols and rows:
            normalised = [list(r.values()) if isinstance(r, dict) else list(r) for r in rows]
            return list(cols), normalised

        return None

    if not sql:
        df_result = None
        for comp in collected:
            result = _read_df_component(comp)
            if result:
                df_result = result
                break

        if df_result:
            columns, rows = df_result
            rows   = sanitize_for_json(rows)
            chart, ct = generate_chart(columns, rows)
            chart  = sanitize_for_json(chart)
            summary = _extract_message_from_components(collected)
            return ChatResponse(
                message=summary or f"Found {len(rows)} result(s).",
                sql_query="-- SQL executed by agent internally",
                columns=columns,
                rows=rows,
                row_count=len(rows),
                chart=chart,
                chart_type=ct,
            )

        logger.warning("No SQL or data extracted from agent response")
        return ChatResponse(
            message=(
                "I couldn't generate a query for that... let me guess, you asked me "
                "to delete the database? Or maybe order a pizza? 🍕\n\n"
                "I'm a clinic data assistant. Let's stick to reading about 'patients', "
                "'doctors', or 'invoices' before one of us gets fired, okay?"
            ),
            sql_query="",
            columns=[],
            rows=[],
            row_count=0,
            chart={},
            chart_type="none",
        )

    logger.info("Generated SQL: %s", sql)

    # ── Step 3: Validate the SQL (security gate) ──────────────────────────────
    is_valid, err_msg = validate_sql(sql)
    if not is_valid:
        logger.warning("SQL validation failed: %s | SQL: %s", err_msg, sql)
        return ChatResponse(
            message=f"⚠️ Query blocked: {err_msg}",
            sql_query=sql,
            columns=[],
            rows=[],
            row_count=0,
            chart={},
            chart_type="none",
        )

    # ── Step 4: Execute the query ─────────────────────────────────────────────
    try:
        columns, rows = run_query(sql)
    except RuntimeError as exc:
        logger.error("Query execution failed: %s", exc)
        return ChatResponse(
            message=f"❌ {exc}",
            sql_query=sql,
            columns=[],
            rows=[],
            row_count=0,
            chart={},
            chart_type="none",
        )

    # ── Step 5: Handle empty results ──────────────────────────────────────────
    if not rows:
        return ChatResponse(
            message=(
                "No data found for your question. "
                "Try adjusting the filters or asking a broader question."
            ),
            sql_query=sql,
            columns=columns,
            rows=[],
            row_count=0,
            chart={},
            chart_type="none",
        )

    # ── Step 6: Generate chart ────────────────────────────────────────────────
    rows      = sanitize_for_json(rows)
    chart, chart_type = generate_chart(columns, rows)
    chart     = sanitize_for_json(chart)

    row_count = len(rows)
    summary   = _extract_message_from_components(collected)
    message   = summary or f"Found {row_count} result{'s' if row_count != 1 else ''}."

    logger.info("Returning %d rows, chart_type=%s", row_count, chart_type)

    return ChatResponse(
        message=message,
        sql_query=sql,
        columns=columns,
        rows=rows,
        row_count=row_count,
        chart=chart,
        chart_type=chart_type,
    )
