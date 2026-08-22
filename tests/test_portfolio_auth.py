"""Security test: portfolio tools must apply the VERIFIED user identity, not a
model-supplied one.

Verifies that:
1. The model-facing tool schema exposes no user-id / state argument.
2. A malicious tool call (passing another user's id, or a forged state) still
   writes to the verified user's account (InjectedState wins).
3. With no user context (CLI), tools fail safe (no write).

Requires the .venv deps (langgraph, langchain-core). Run:
    .venv/Scripts/python tests/test_portfolio_auth.py
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.utils.function_calling import convert_to_openai_tool  # noqa: E402
from langgraph.graph import StateGraph  # noqa: E402
from langgraph.prebuilt import ToolNode  # noqa: E402

import config  # noqa: E402
config.DATABASE_URL = ""  # force SQLite regardless of local .env

import app.tools.portfolio_tools as pt  # noqa: E402
from app.agents.state import AgentState  # noqa: E402
from app.utils import user_db  # noqa: E402

ATTACKER_ID = 999
VICTIM_ID = 123


def _use_temp_db():
    tmp = Path(tempfile.mkdtemp()) / "test_bot.db"
    user_db.DB_PATH = tmp
    user_db.init_db()
    return tmp


def _build_tool_graph(tool_obj):
    """Compiled 1-node graph so ToolNode gets a real runtime (as in production)."""
    builder = StateGraph(AgentState)
    builder.add_node("tools", ToolNode([tool_obj]))
    builder.set_entry_point("tools")
    return builder.compile()


def _call_tool(tool_obj, args: dict, user_id: int | None) -> str:
    """Invoke one tool through a compiled graph (same injection path as the agent)."""
    graph = _build_tool_graph(tool_obj)
    msg = AIMessage(
        content="",
        tool_calls=[{"name": tool_obj.name, "args": args, "id": "call_1", "type": "tool_call"}],
    )
    configurable = {"thread_id": "test"}
    if user_id is not None:
        configurable["telegram_user_id"] = user_id
    out = graph.invoke({"messages": [msg]}, config={"configurable": configurable})
    tool_msg = out["messages"][-1]
    return tool_msg.content


def test_schema_hides_user_identity():
    """The model must not see any user-id / state / config parameter."""
    for t in pt.PORTFOLIO_TOOLS:
        schema = convert_to_openai_tool(t)["function"]["parameters"]
        props = schema.get("properties", {})
        assert "config" not in props, f"{t.name}: 'config' leaked into model schema"
        assert "state" not in props, f"{t.name}: 'state' leaked into model schema"
        assert "telegram_id" not in props, f"{t.name}: 'telegram_id' leaked into model schema"


def test_injected_identity_wins_over_malicious_args():
    """Model passes attacker id; write must land on the verified user from config."""
    _use_temp_db()
    content = _call_tool(
        pt.portfolio_add_tool,
        args={
            "symbol": "NTLC",
            "buy_price": 50000,
            "buy_date": "2025-01-15",
            "telegram_id": ATTACKER_ID,                      # direct impersonation attempt
        },
        user_id=VICTIM_ID,
    )
    result = json.loads(content)
    assert result.get("ok"), f"tool call failed unexpectedly: {content}"
    victim_positions = user_db.portfolio_list(VICTIM_ID)
    attacker_positions = user_db.portfolio_list(ATTACKER_ID)
    assert len(victim_positions) == 1 and victim_positions[0]["symbol"] == "NTLC", \
        "position must be written to the verified user"
    assert attacker_positions == [], "attacker account must stay empty"


def test_no_user_context_fails_safe():
    """CLI context (no telegram_user_id in config): no write, clear error."""
    _use_temp_db()
    content = _call_tool(
        pt.portfolio_add_tool,
        args={"symbol": "NTLC", "buy_price": 50000, "buy_date": "2025-01-15"},
        user_id=None,
    )
    result = json.loads(content)
    assert result.get("ok") is False and "error" in result


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
