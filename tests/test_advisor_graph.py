"""Advisor worker tests (fake LLM, no network, no CSV).

1. Supervisor label ADVISOR routes to the advisor worker (unit + full graph run).
2. Tool shapes: get_stock_advice / get_market_recommendations wrap the
   (monkeypatched) scoring engine into the expected JSON payloads.
3. Identity injection: get_portfolio_advice reads the verified telegram_user_id
   from the run config (never from tool args) and fails safe without one.

Run:
    .venv/bin/python tests/test_advisor_graph.py
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.graph import StateGraph  # noqa: E402
from langgraph.prebuilt import ToolNode  # noqa: E402

import config  # noqa: E402
config.DATABASE_URL = ""  # force SQLite regardless of local .env

from app.agents.state import AgentState  # noqa: E402
from app.services import scoring  # noqa: E402
from app.tools import advisor_tools as at  # noqa: E402
from app.utils import user_db  # noqa: E402

USER_ID = 123
ATTACKER_ID = 999

FAKE_SCORE = {
    "symbol": "NTLC",
    "score": 73.3,
    "signal": "Achat",
    "reasons": ["Tendance haussière : cours au-dessus des MM50 et MM200"],
    "technicals": {"momentum": 18.5, "block": 70.0},
    "fundamentals": {"per": 9.0, "block": 65.0},
    "data_warnings": [],
    "error": None,
}

FAKE_ALL = {
    "as_of": "2026-08-21",
    "ranked": [
        {"symbol": "NTLC", "score": 73.3, "signal": "Achat", "reasons": ["Tendance haussière"], "data_warnings": []},
        {"symbol": "SNTS", "score": 60.0, "signal": "Accumuler", "reasons": ["Momentum 6 mois : +12,3 %"], "data_warnings": []},
        {"symbol": "BOAC", "score": 45.0, "signal": "Neutre", "reasons": [], "data_warnings": []},
        {"symbol": "SGBC", "score": 31.5, "signal": "Alléger", "reasons": ["Tendance baissière"], "data_warnings": []},
    ],
    "insufficient": [{"symbol": "SITAB", "score": None, "signal": None, "error": "Pas de série historique en cache"}],
}


class patch_scoring:
    """Monkeypatch scoring.score_symbol / score_all, restoring originals after."""

    def __enter__(self):
        self._saved = (scoring.score_symbol, scoring.score_all)
        scoring.score_symbol = lambda symbol: dict(FAKE_SCORE, symbol=symbol)
        scoring.score_all = lambda symbols=None: FAKE_ALL
        return self

    def __exit__(self, *exc):
        scoring.score_symbol, scoring.score_all = self._saved


class AdvisorFake(GenericFakeChatModel):
    """Content-routed fake: NLU -> suggested_worker=advisor (supervisor then
    short-circuits without an LLM call); advisor worker -> one
    get_market_recommendations tool call, then a final French answer."""

    def __init__(self, **kwargs):
        super().__init__(messages=iter([AIMessage(content="unused")]), **kwargs)

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        from langchain_core.messages import ToolMessage
        from langchain_core.outputs import ChatGeneration, ChatResult

        blob = " ".join(str(m.content) for m in messages)[:4000]
        if "BRVM stock assistant NLU" in blob:
            msg = AIMessage(
                content='{"intent": "advice", "entities": {}, "suggested_worker": "advisor"}'
            )
        elif "BRVM investment advisor" in blob:
            if isinstance(messages[-1], ToolMessage):
                msg = AIMessage(content="ADVISOR-REPLY: NTLC ressort en tête des achats.")
            else:
                msg = AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "get_market_recommendations",
                        "args": {"top_n": 2},
                        "id": "c1",
                        "type": "tool_call",
                    }],
                )
        else:
            raise RuntimeError("unexpected prompt: " + blob[:200])
        return ChatResult(generations=[ChatGeneration(message=msg)])


def _patch_llm(fake):
    """Point every get_llm consumer at the fake model (all workers build eagerly)."""
    import app.agents.graph as graph_mod
    import app.agents.nlu_agent as nlu_mod
    import app.agents.analytics_agent as analytics_mod
    import app.agents.scraper_agent as scraper_mod
    import app.agents.timeseries_agent as timeseries_mod
    import app.agents.charts_agent as charts_mod
    import app.agents.news_agent as news_mod
    import app.agents.portfolio_agent as portfolio_mod
    import app.agents.prediction_agent as prediction_mod
    import app.agents.sgi_agent as sgi_mod
    import app.agents.company_details_agent as company_details_mod
    import app.agents.advisor_agent as advisor_mod

    for mod in (graph_mod, nlu_mod, analytics_mod, scraper_mod, timeseries_mod,
                charts_mod, news_mod, portfolio_mod, prediction_mod, sgi_mod,
                company_details_mod, advisor_mod):
        mod.get_llm = lambda *a, **k: fake


def _use_temp_db():
    tmp = Path(tempfile.mkdtemp()) / "advisor_test.db"
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
    return out["messages"][-1].content


# ---------------- Routing ----------------
def test_supervisor_label_routes_to_advisor():
    from app.agents.graph import _parse_next, route_after_supervisor

    assert _parse_next("ADVISOR") == ("advisor", [], False)
    assert route_after_supervisor({"next": "advisor", "multi_workers": []}) == "advisor"


def test_full_advisor_flow_with_fake_llm():
    with patch_scoring():
        _patch_llm(AdvisorFake())
        from app.agents.graph import run_agent

        result = run_agent(
            "quelles actions acheter ?",
            model="fake",
            thread_id="advisor-e2e",
            telegram_user_id=USER_ID,
            checkpointer=MemorySaver(),
        )
    messages = result.get("messages") or []
    last = str(messages[-1].content)
    assert "ADVISOR-REPLY" in last, last
    tool_names = [getattr(m, "name", None) for m in messages]
    assert "get_market_recommendations" in tool_names, tool_names


# ---------------- Tool shapes ----------------
def test_get_stock_advice_tool_shape():
    with patch_scoring():
        out = json.loads(at.get_stock_advice_tool.invoke({"symbol": "NTLC"}))
    assert out["symbol"] == "NTLC"
    assert out["score"] == 73.3 and out["signal"] == "Achat"
    assert out["reasons"] == ["Tendance haussière : cours au-dessus des MM50 et MM200"]
    assert out["metrics"] == {"momentum": 18.5, "per": 9.0}, out["metrics"]
    assert out["data_warnings"] == [] and out["error"] is None


def test_get_stock_advice_unknown_symbol():
    out = json.loads(at.get_stock_advice_tool.invoke({"symbol": "XXXX"}))
    assert "error" in out and "XXXX" in out["error"], out


def test_get_market_recommendations_tool_shape():
    with patch_scoring():
        out = json.loads(at.get_market_recommendations_tool.invoke({"top_n": 2}))
    assert out["as_of"] == "2026-08-21"
    assert [b["symbol"] for b in out["top_buys"]] == ["NTLC", "SNTS"], out["top_buys"]
    assert [s["symbol"] for s in out["top_sells"]] == ["SGBC", "BOAC"], out["top_sells"]
    assert out["top_buys"][0]["reasons"] == ["Tendance haussière"]
    assert out["insufficient_count"] == 1


# ---------------- Identity injection ----------------
def test_portfolio_advice_without_context_fails_safe():
    _use_temp_db()
    content = _call_tool(at.get_portfolio_advice_tool, args={}, user_id=None)
    result = json.loads(content)
    assert result.get("ok") is False and "error" in result, content


def test_portfolio_advice_uses_verified_identity():
    _use_temp_db()
    user_db.portfolio_add(USER_ID, "NTLC", 50000, "2025-01-15")
    real_palmares = user_db.fetch_palmares
    user_db.fetch_palmares = lambda *a, **k: [{"symbol": "NTLC", "cours_actuel": 55000}]
    try:
        with patch_scoring():
            content = _call_tool(at.get_portfolio_advice_tool, args={}, user_id=USER_ID)
    finally:
        user_db.fetch_palmares = real_palmares
    result = json.loads(content)
    assert result.get("ok") is True, content
    positions = result.get("positions") or []
    assert len(positions) == 1 and positions[0]["symbol"] == "NTLC", positions
    assert positions[0]["score"] == 73.3 and positions[0]["signal"] == "Achat"
    assert positions[0]["gain_loss_pct"] == 10.0, positions  # 55000 vs 50000
    assert "1 position" in result.get("summary_hint", "")
    # The attacker's account stays empty: identity came from the config only.
    assert user_db.portfolio_list(ATTACKER_ID) == []


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
