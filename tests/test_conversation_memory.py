"""Conversation memory tests: multi-turn context, clarification persistence,
config-driven history window, and TTL-based stale-thread cleanup.

Reproduces the reported bug: "How to add a stock to my portfolio?" ->
"which stock?" -> "ETIT" must add ETIT to the portfolio, NOT answer with
its price.

Run:
    .venv/Scripts/python tests/test_conversation_memory.py
"""
import sys
import tempfile
import time
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from pydantic import Field  # noqa: E402

import config  # noqa: E402
config.DATABASE_URL = ""  # force SQLite regardless of local .env

from app.utils import user_db  # noqa: E402

USER_ID = 456


def _patch_llm(fake):
    """Point every get_llm consumer at the fake model."""
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

    for mod in (graph_mod, nlu_mod, analytics_mod, scraper_mod, timeseries_mod,
                charts_mod, news_mod, portfolio_mod, prediction_mod, sgi_mod,
                company_details_mod):
        mod.get_llm = lambda *a, **k: fake


class MultiTurnFake(GenericFakeChatModel):
    """Routes on prompt content and records every NLU prompt it receives.

    Turn 1 (no history, portfolio question) -> CLARIFY.
    Turn 2 ("ETIT" after the clarification) -> portfolio_add for ETIT.
    """

    CLARIFICATION: ClassVar[str] = (
        "Pour ajouter une action a votre portefeuille, donnez-moi simplement son symbole "
        "BRVM (ex. ETIT, NTLC). Idealement, precisez aussi le prix et la date d'achat. "
        "Quelle action voulez-vous ajouter ?"
    )

    nlu_prompts: list = Field(default_factory=list)

    def __init__(self, **kwargs):
        kwargs.setdefault("messages", iter([AIMessage(content="unused")]))
        super().__init__(**kwargs)

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        blob = " ".join(str(m.content) for m in messages)[:6000]
        if "BRVM stock assistant NLU" in blob:
            self.nlu_prompts.append(blob)
            if "Current user message: ETIT" in blob:
                # Context resolution: the clarification asked which stock to add.
                msg = AIMessage(
                    content='{"intent": "portfolio_add", "entities": {"symbol": "ETIT"}, '
                    '"suggested_worker": "portfolio"}'
                )
            else:
                msg = AIMessage(content=f"CLARIFY: {self.CLARIFICATION}")
        elif "BRVM portfolio worker" in blob:
            if isinstance(messages[-1], ToolMessage):
                msg = AIMessage(content="ETIT ajoute a votre portefeuille avec succes.")
            else:
                msg = AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "portfolio_add",
                        "args": {"symbol": "ETIT"},
                        "id": "c1",
                        "type": "tool_call",
                    }],
                )
        else:
            msg = AIMessage(content="Réponse générique.")
        return ChatResult(generations=[ChatGeneration(message=msg)])


def test_clarification_turn_is_persisted_and_contextualized():
    """The reported scenario: a bare 'ETIT' after a clarification must be
    resolved via conversation history into portfolio_add, not a price query."""
    user_db.DB_PATH = Path(tempfile.mkdtemp()) / "mem.db"
    user_db.init_db()
    fake = MultiTurnFake()
    _patch_llm(fake)

    from app.agents.graph import get_compiled_graph, run_agent

    cp = MemorySaver()
    graph = get_compiled_graph("fake", cp)

    # Turn 1: portfolio question -> clarification
    r1 = run_agent(
        "Comment ajouter une action a mon portefeuille ?",
        model="fake",
        thread_id="mem-scenario",
        telegram_user_id=USER_ID,
        checkpointer=cp,
    )
    assert r1.get("clarification"), f"turn 1 should clarify, got {r1.get('structured_data')}"

    # The clarification exchange must be SAVED in the checkpoint (the old code
    # reverted it, so turn 2 started from zero).
    state = graph.get_state({"configurable": {"thread_id": "mem-scenario"}})
    saved = [str(m.content) for m in (state.values or {}).get("messages", [])]
    assert any("portefeuille" in c.lower() for c in saved), f"history lost: {saved}"
    assert any("Comment ajouter" in c for c in saved), f"user question lost: {saved}"

    # Turn 2: bare symbol -> must be resolved with the turn-1 context
    r2 = run_agent(
        "ETIT",
        model="fake",
        thread_id="mem-scenario",
        telegram_user_id=USER_ID,
        checkpointer=cp,
    )
    assert not r2.get("clarification"), f"turn 2 must not clarify again: {r2.get('clarification')}"
    sd = r2.get("structured_data") or {}
    assert sd.get("intent") == "portfolio_add", f"wrong intent: {sd}"
    assert (sd.get("entities") or {}).get("symbol") == "ETIT", f"wrong entities: {sd}"

    # The NLU on turn 2 must have SEEN the turn-1 exchange in its prompt.
    assert len(fake.nlu_prompts) >= 2, "expected 2 NLU calls"
    turn2_prompt = fake.nlu_prompts[-1]
    assert "Comment ajouter" in turn2_prompt, "turn-1 question missing from NLU prompt"
    assert "Quelle action voulez-vous ajouter" in turn2_prompt, (
        "clarification missing from NLU prompt"
    )


def test_nlu_prompt_guides_howto_answers():
    """Prompt regression: how-to questions about the assistant must be answered
    with an explanation + follow-up question, not a bare counter-question."""
    from app.agents.nlu_agent import _nlu_system_prompt

    prompt = _nlu_system_prompt()
    assert "How-to questions about this assistant" in prompt
    assert "explanation" in prompt.lower()
    assert "follow-up question" in prompt.lower()


def test_condense_respects_config_window():
    from app.agents.graph import _condense_to_user_final_pairs

    pairs = []
    for i in range(6):
        pairs.append(HumanMessage(content=f"q{i}"))
        pairs.append(AIMessage(content=f"a{i}"))
    original = config.MEMORY_MAX_MESSAGES
    try:
        config.MEMORY_MAX_MESSAGES = 4
        out = _condense_to_user_final_pairs(pairs)
        assert len(out) == 4, f"expected 4, got {len(out)}"
        assert out[0].content == "q4" and out[-1].content == "a5", [m.content for m in out]
    finally:
        config.MEMORY_MAX_MESSAGES = original


def _put_checkpoint(saver, thread_id: str) -> str:
    from langgraph.checkpoint.base import empty_checkpoint

    cp = empty_checkpoint()
    saver.put(
        {"configurable": {"thread_id": thread_id, "checkpoint_ns": "", "checkpoint_id": cp["id"]}},
        cp,
        {"source": "input", "step": -1, "writes": None, "parents": {}},
        {},
    )
    return cp["id"]


def test_cleanup_stale_threads():
    """Threads inactive > MEMORY_TTL_HOURS are wiped; fresh ones survive."""
    import app.api.chat as chat_mod

    tmpdir = Path(tempfile.mkdtemp())
    db_path = tmpdir / "chat_memory.db"

    original_db = chat_mod.CHAT_MEMORY_DB
    original_cp = chat_mod._checkpointer
    original_ttl = config.MEMORY_TTL_HOURS
    try:
        chat_mod.CHAT_MEMORY_DB = db_path
        chat_mod._checkpointer = None  # force re-creation on the temp DB
        config.MEMORY_TTL_HOURS = 24

        import sqlite3
        from langgraph.checkpoint.sqlite import SqliteSaver

        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        saver = SqliteSaver(conn)
        stale_cp_id = _put_checkpoint(saver, "stale-thread")
        fresh_cp_id = _put_checkpoint(saver, "fresh-thread")

        # stale: 48h ago; fresh: now
        with chat_mod._activity_connect() as conn2:
            chat_mod._ensure_activity_table(conn2)
            now = time.time()
            conn2.execute(
                "INSERT INTO thread_activity (thread_id, last_seen) VALUES (?, ?)",
                ("stale-thread", now - 48 * 3600),
            )
            conn2.execute(
                "INSERT INTO thread_activity (thread_id, last_seen) VALUES (?, ?)",
                ("fresh-thread", now),
            )

        chat_mod._checkpointer = saver
        chat_mod.cleanup_stale_threads()

        cfg = lambda tid, cid: {
            "configurable": {"thread_id": tid, "checkpoint_ns": "", "checkpoint_id": cid}
        }
        assert saver.get_tuple(cfg("stale-thread", stale_cp_id)) is None, "stale thread not wiped"
        assert saver.get_tuple(cfg("fresh-thread", fresh_cp_id)) is not None, "fresh thread wrongly wiped"

        with chat_mod._activity_connect() as conn3:
            rows = conn3.execute("SELECT thread_id FROM thread_activity").fetchall()
        assert [r[0] for r in rows] == ["fresh-thread"], rows
    finally:
        chat_mod.CHAT_MEMORY_DB = original_db
        chat_mod._checkpointer = original_cp
        config.MEMORY_TTL_HOURS = original_ttl


def test_cleanup_disabled_when_ttl_zero():
    import app.api.chat as chat_mod

    original_ttl = config.MEMORY_TTL_HOURS
    try:
        config.MEMORY_TTL_HOURS = 0
        # Must be a no-op (no DB access, no error).
        chat_mod.cleanup_stale_threads()
    finally:
        config.MEMORY_TTL_HOURS = original_ttl


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
