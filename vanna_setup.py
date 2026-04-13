"""
vanna_setup.py
==============
Configures and exposes the Vanna 2.0 Agent wired to the clinic.db SQLite
database using local Ollama (qwen3:8b) as the LLM.

Usage:
    from vanna_setup import get_agent
    agent = get_agent()
"""

import os
from functools import lru_cache
from dotenv import load_dotenv

# ── Load .env before any Vanna imports ────────────────────────────────────────
load_dotenv()

# ── Vanna 2.0 imports (exact paths as required by the framework) ──────────────
from vanna import Agent, AgentConfig
from vanna.core.registry import ToolRegistry
from vanna.core.user import UserResolver, User, RequestContext
from vanna.tools import RunSqlTool, VisualizeDataTool
from vanna.tools.agent_memory import (
    SaveQuestionToolArgsTool,
    SearchSavedCorrectToolUsesTool,
)
from vanna.integrations.sqlite import SqliteRunner
from vanna.integrations.local.agent_memory import DemoAgentMemory
from vanna.integrations.ollama import OllamaLlmService

# ── Database path ─────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "clinic.db")

# ── Global agent memory (singleton so seed_memory.py shares the same instance)
_agent_memory: DemoAgentMemory | None = None

def get_agent_memory() -> DemoAgentMemory:
    """Return the shared DemoAgentMemory singleton."""
    global _agent_memory
    if _agent_memory is None:
        _agent_memory = DemoAgentMemory(max_items=500)
    return _agent_memory


class DefaultUserResolver(UserResolver):
    """
    A simple UserResolver that returns the same default user for every request.
    In production, decode a JWT or session cookie here instead.
    """

    async def resolve_user(self, request_context: RequestContext) -> User:
        # Return a permissive admin user so all tools are accessible.
        return User(
            id="default-user",
            email="admin@clinic.local",
            group_memberships=["users", "admin"],
        )


@lru_cache(maxsize=1)
def get_agent() -> Agent:
    """
    Build and return the configured Vanna 2.0 Agent (cached singleton).

    Components wired:
        • GeminiLlmService   → generates SQL from natural language
        • RunSqlTool         → executes SQL against clinic.db
        • VisualizeDataTool  → creates Plotly charts from query results
        • SaveQuestionToolArgsTool      → stores successful Q→SQL pairs
        • SearchSavedCorrectToolUsesTool → retrieves similar past Q→SQL pairs
        • DemoAgentMemory    → in-memory store for the above tools
        • DefaultUserResolver → grants all requests admin-level access
    """
    # 1. LLM service ────────────────────────────────────────────────────────────
    llm = OllamaLlmService(
        model="qwen3:8b",
        # host="http://localhost:11434",  # Default host for Ollama
    )

    # 2. Agent memory ───────────────────────────────────────────────────────────
    memory = get_agent_memory()

    # 3. Tool registry ──────────────────────────────────────────────────────────
    tools = ToolRegistry()

    # SQL execution tool — connects to the clinic SQLite database
    sql_runner = SqliteRunner(database_path=DB_PATH)
    tools.register_local_tool(
        RunSqlTool(sql_runner=sql_runner),
        access_groups=["users", "admin"],
    )

    # Visualisation tool — generates Plotly charts from DataFrames
    tools.register_local_tool(
        VisualizeDataTool(),
        access_groups=["users", "admin"],
    )

    # Memory tools — save and retrieve successful question->SQL pairs
    tools.register_local_tool(
        SaveQuestionToolArgsTool(),
        access_groups=["users", "admin"],
    )
    tools.register_local_tool(
        SearchSavedCorrectToolUsesTool(),
        access_groups=["users", "admin"],
    )

    # 4. User resolver ──────────────────────────────────────────────────────────
    user_resolver = DefaultUserResolver()

    # 5. Agent configuration ────────────────────────────────────────────────────
    config = AgentConfig()

    # 6. Assemble the agent ─────────────────────────────────────────────────────
    agent = Agent(
        llm_service=llm,
        tool_registry=tools,
        agent_memory=memory,
        user_resolver=user_resolver,
        config=config,
    )

    return agent
