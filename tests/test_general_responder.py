"""General responder + slim NLU routing tests.

Covers the fast path for messages that need NO data and NO specialist worker
(greetings, finance/BRVM education): the NLU prompt stays small (company-name
resolution lives in code), general/brvm_basics intents route to the general
responder in exactly 2 LLM calls (NLU + answer, supervisor skipped), and
get_llm(thinking=False) asks the provider to skip the reasoning chain.

Run:
    .venv/bin/python -m pytest tests/test_general_responder.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

import config  # noqa: E402
config.DATABASE_URL = ""  # force SQLite regardless of local .env

from app.utils import user_db  # noqa: E402


# --- NLU parsing / routing ---------------------------------------------------

def test_missing_or_invalid_worker_uses_intent_map():
    from app.agents.nlu_agent import _parse_nlu_response

    # No suggested_worker at all: intent map decides (never a blind data worker).
    sd, clar = _parse_nlu_response('{"intent": "general", "entities": {}}')
    assert clar is None and sd["suggested_worker"] == "general", sd

    sd, _ = _parse_nlu_response('{"intent": "brvm_basics", "entities": {}}')
    assert sd["suggested_worker"] == "general", sd

    sd, _ = _parse_nlu_response('{"intent": "price_query", "entities": {}}')
    assert sd["suggested_worker"] == "analytics", sd

    # Unknown intent + unknown worker -> general (safe: no data tools there).
    sd, _ = _parse_nlu_response('{"intent": "xyzzy", "entities": {}, "suggested_worker": "bogus"}')
    assert sd["suggested_worker"] == "general", sd


def test_worker_alias_and_multi_passthrough():
    from app.agents.nlu_agent import _parse_nlu_response

    # "scrape" is a near-miss label the model emits for "scraper".
    sd, _ = _parse_nlu_response(
        '{"intent": "price_query", "entities": {"symbol": "NTLC"}, "suggested_worker": "scrape"}'
    )
    assert sd["suggested_worker"] == "scraper", sd

    # Compound request: multi workers travel via structured_data.multi_workers.
    sd, _ = _parse_nlu_response(
        '{"intent": "price_query", "entities": {"symbol": "NTLC"}, "suggested_worker": "analytics,news"}'
    )
    assert sd["multi_workers"] == ["analytics", "news"], sd
    assert sd["suggested_worker"] == "", sd


def test_parser_tolerates_label_prefixes_and_junk():
    """Observed on weak deployment models: they echo the output-spec labels
    ("A) CLARIFY: ...", "unclear → CLARIFY: ...") or emit prose. The parser
    must extract what it can and NEVER dead-end on a reformulation loop."""
    from app.agents.nlu_agent import _parse_nlu_response

    # Label-prefixed CLARIFY still clarifies.
    sd, clar = _parse_nlu_response("A) CLARIFY: Quel symbole voulez-vous consulter ?")
    assert sd is None and clar == "Quel symbole voulez-vous consulter ?", clar

    # Junk clarification ("comment" stub) -> general, not a useless question.
    sd, clar = _parse_nlu_response("unclear → CLARIFY: comment")
    assert clar is None and sd["suggested_worker"] == "general", (sd, clar)

    # Pure prose -> general responder (never the reformulation dead-end).
    sd, clar = _parse_nlu_response("Je ne suis pas sûr de comprendre la demande.")
    assert clar is None and sd["intent"] == "general" and sd["suggested_worker"] == "general", (sd, clar)

    # Label-prefixed JSON still parses.
    sd, clar = _parse_nlu_response('B) {"intent": "price_query", "entities": {"symbol": "NTLC"}, "suggested_worker": "analytics"}')
    assert clar is None and sd["suggested_worker"] == "analytics", (sd, clar)

    # Bare route label instead of JSON (observed live: model answers 'general').
    sd, clar = _parse_nlu_response("general")
    assert clar is None and sd["suggested_worker"] == "general", (sd, clar)


def test_company_name_resolved_in_code_not_prompt():
    from app.agents.nlu_agent import _parse_nlu_response

    # The NLU copies the mention as written; normalize_entities maps it.
    sd, clar = _parse_nlu_response(
        '{"intent": "price_query", "entities": {"symbol": "Sonatel"}, "suggested_worker": "analytics"}'
    )
    assert clar is None, clar
    assert sd["entities"]["symbol"] == "SNTS", sd


def test_nlu_prompt_is_slim():
    from app.agents.nlu_agent import _nlu_system_prompt

    prompt = _nlu_system_prompt()
    assert len(prompt) < 2500, f"NLU prompt grew back to {len(prompt)} chars"
    # The 47-company list must NOT be inlined (spot-check a few entries).
    for token in ("SONATEL", "Solibra", "Nestlé"):
        assert token not in prompt, f"company list leaked into NLU prompt ({token})"


# --- Graph fast path ---------------------------------------------------------

def test_router_model_is_used_for_nlu():
    """Per-task split: the NLU must call get_llm with config.ROUTER_MODEL, not
    the run's primary model."""
    import app.agents.nlu_agent as nlu_mod

    captured: dict = {}

    class _Capture:
        def invoke(self, messages):
            from langchain_core.messages import AIMessage as _AM
            return _AM(content='{"intent": "general", "entities": {}, "suggested_worker": "general"}')

    def _capture_get_agent_llm(agent=None, model=None, **k):
        captured["agent"] = agent
        captured["model"] = model
        return _Capture()

    real = nlu_mod.get_agent_llm
    saved_router = config.ROUTER_MODEL
    nlu_mod.get_agent_llm = _capture_get_agent_llm
    config.ROUTER_MODEL = "gemma4-e4b"
    try:
        nlu_mod.run_nlu_node({"messages": [HumanMessage(content="c est quoi la brvm?")]}, model="nemotron-3-nano")
        assert captured["model"] == "gemma4-e4b", captured
        assert captured["agent"] == "nlu", captured
        config.ROUTER_MODEL = None  # empty -> primary model
        nlu_mod.run_nlu_node({"messages": [HumanMessage(content="c est quoi la brvm?")]}, model="nemotron-3-nano")
        assert captured["model"] == "nemotron-3-nano", captured
    finally:
        nlu_mod.get_agent_llm = real
        config.ROUTER_MODEL = saved_router


def test_pure_greeting_short_circuits_the_classifier():
    """Pure greetings must route to general WITHOUT any LLM call (weak models
    kept re-asking the pending question from history instead)."""
    import app.agents.nlu_agent as nlu_mod

    for text in ["hi", "Salut !", "BONJOUR?", "comment ça va", "merci beaucoup", "Hello"]:
        assert nlu_mod._is_pure_greeting(text), text
    for text in ["salut, quel est le cours de SNTS ?", "bonjour je veux investir", "ca va et toi et le cours NTLC"]:
        assert not nlu_mod._is_pure_greeting(text), text

    def _exploding_get_agent_llm(*a, **k):
        raise AssertionError("greeting must not call the LLM")

    real = nlu_mod.get_agent_llm
    nlu_mod.get_agent_llm = _exploding_get_agent_llm
    try:
        out = nlu_mod.run_nlu_node({"messages": [HumanMessage(content="hi")]}, model="fake")
    finally:
        nlu_mod.get_agent_llm = real
    assert out["clarification"] is None
    assert out["structured_data"]["suggested_worker"] == "general", out["structured_data"]


LLM_CALLS = {"n": 0}


class GeneralFake(GenericFakeChatModel):
    """Content-routed fake: NLU -> general intent; general responder -> greeting."""

    def __init__(self, **kwargs):
        kwargs.setdefault("messages", iter([AIMessage(content="unused")]))
        super().__init__(**kwargs)

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        LLM_CALLS["n"] += 1
        blob = " ".join(str(m.content) for m in messages)[:8000]
        if "BRVM stock assistant NLU" in blob:
            msg = AIMessage(content='{"intent": "general", "entities": {}, "suggested_worker": "general"}')
        elif "Assistant BRVM" in blob:
            msg = AIMessage(content="Bonjour ! Je suis l'assistant BRVM, posez-moi vos questions.")
        else:
            raise RuntimeError("unexpected prompt: " + blob[:200])
        return ChatResult(generations=[ChatGeneration(message=msg)])


def _patch_llm(fake):
    import app.agents.graph as graph_mod
    import app.agents.nlu_agent as nlu_mod
    import app.agents.general_agent as general_mod
    import app.agents.analytics_agent as analytics_mod
    import app.agents.scraper_agent as scraper_mod
    import app.agents.timeseries_agent as timeseries_mod
    import app.agents.charts_agent as charts_mod
    import app.agents.news_agent as news_mod
    import app.agents.portfolio_agent as portfolio_mod
    import app.agents.prediction_agent as prediction_mod
    import app.agents.sgi_agent as sgi_mod
    import app.agents.company_details_agent as company_details_mod

    for mod in (graph_mod, nlu_mod, general_mod, analytics_mod, scraper_mod, timeseries_mod,
                charts_mod, news_mod, portfolio_mod, prediction_mod, sgi_mod,
                company_details_mod):
        mod.get_agent_llm = lambda *a, **k: fake


def test_greeting_routes_to_general_responder():
    user_db.DB_PATH = Path(tempfile.mkdtemp()) / "gen.db"
    user_db.init_db()
    LLM_CALLS["n"] = 0
    _patch_llm(GeneralFake())

    from app.agents.graph import run_agent

    result = run_agent(
        "bonjour",
        model="fake",
        thread_id="gen-e2e",
        telegram_user_id=777,
        checkpointer=MemorySaver(),
    )
    assert not result.get("clarification"), result.get("clarification")
    assert result.get("_fresh_reply", "").startswith("Bonjour"), result.get("_fresh_reply")
    assert (result.get("structured_data") or {}).get("intent") == "general"
    # "bonjour" is a pure greeting: the NLU classifier is skipped (0 calls) and
    # only the general responder calls the LLM (1 call). The supervisor must be
    # bypassed (suggested_worker shortcut) and FINISHes structurally after.
    assert LLM_CALLS["n"] == 1, f"expected 1 LLM call, got {LLM_CALLS['n']}"


# --- LLM factory: thinking switch --------------------------------------------

def test_thinking_flag_controls_extra_body_and_cache():
    import app.models.llm as llm_mod

    old_key = config.AFRIKIA_API_KEY
    config.AFRIKIA_API_KEY = "test-key"
    try:
        fast = llm_mod.get_llm(model="m-fast", thinking=False)
        assert fast.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}, fast.extra_body
        think = llm_mod.get_llm(model="m-fast", thinking=True)
        assert not getattr(think, "extra_body", None), getattr(think, "extra_body", None)
        # Cached per (model, temperature, thinking):
        assert llm_mod.get_llm(model="m-fast", thinking=False) is fast
        assert think is not fast
        # Caller-supplied extra_body is merged, not clobbered.
        custom = llm_mod.get_llm(model="m-fast", thinking=False, extra_body={"top_k": 5})
        assert custom.extra_body["top_k"] == 5
        assert custom.extra_body["chat_template_kwargs"]["enable_thinking"] is False
    finally:
        config.AFRIKIA_API_KEY = old_key


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
