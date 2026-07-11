"""LangGraph: NLU -> supervisor -> workers (scraper|analytics|timeseries|charts|news|portfolio)."""
from __future__ import annotations

import inspect
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)
from langgraph.graph import StateGraph

import config
from app.models.llm import get_default_model, get_llm
from langgraph.checkpoint.memory import MemorySaver

from app.agents.state import AgentState, NextWorker, WorkerName

CHAT_MEMORY_DB = Path(__file__).resolve().parent.parent / "data" / "chat_memory.db"
from app.agents.utils import get_time_prefix
from app.agents.analytics_agent import create_analytics_agent, get_analytics_agent_system
from app.agents.charts_agent import create_charts_agent, _extract_image_path_from_messages, get_charts_agent_system
from app.agents.news_agent import create_news_agent, get_news_agent_system
from app.agents.nlu_agent import create_nlu_node
from app.agents.scraper_agent import create_scraper_agent, get_scraper_agent_system
from app.agents.timeseries_agent import create_timeseries_agent, get_timeseries_agent_system
from app.agents.portfolio_agent import create_portfolio_agent, get_portfolio_agent_system
from app.agents.prediction_agent import create_prediction_agent, get_prediction_agent_system
from app.agents.sgi_agent import create_sgi_agent, get_sgi_agent_system
from app.agents.company_details_agent import create_company_details_agent, get_company_details_agent_system

# Keep only the last N condensed messages (user + final AI pairs) per thread.
# Configurable via MEMORY_MAX_MESSAGES env var (default 20 = 10 exchanges).
MEMORY_MAX_MESSAGES = getattr(config, "MEMORY_MAX_MESSAGES", 20)

SUPERVISOR_SYSTEM_TEMPLATE = """BRVM router. Output one label only. {time_line}

**Rule:** Last message is worker response (data/chart/news) → output FINISH. Do not chain workers.

**Workers:**
- SCRAPER — Fetch raw data (palmarès, variation, CSV)
- ANALYTICS — Prices, compare, stats, market overview (numbers, no plots)
- TIMESERIES — CSV maintenance only: list/update CSVs. Use ONLY when the user explicitly asks to update timeseries files or check their status. Never route normal price/metrics/compare/chart/news questions here.
- CHARTS — Plot/graph of stock price
- NEWS — Actualités, communiqués, dividends
- PREDICTION — Stock predictions, trends table, hausse/baisse/neutre, technical trend for a symbol
- PORTFOLIO — My portfolio, tracking list, price alerts
- SGI — Brokers/courtiers BRVM (liste des SGI, où ouvrir un compte, tarifs, contacts)
- COMPANY_DETAILS — Single-company fiche société: actionnaires, dividende, résultat net, croissance, BNPA, PER, présentation, dirigeants (Sika Finance; data cached per symbol)
- FINISH — Done, greeting, or off-topic

**Output:** One of SCRAPER | ANALYTICS | TIMESERIES | CHARTS | NEWS | PREDICTION | PORTFOLIO | SGI | COMPANY_DETAILS | FINISH
(For multi: ANALYTICS,NEWS or SCRAPER|CHARTS — do NOT include TIMESERIES in multi.)"""


def _get_supervisor_system() -> str:
    return SUPERVISOR_SYSTEM_TEMPLATE.format(time_line=get_time_prefix())


def _parse_next(response: str) -> tuple[NextWorker, list[WorkerName], bool]:
    """
    Parse supervisor output. Returns (next, multi_workers, multi_parallel).
    - If multi_workers non-empty: use those; multi_parallel=True for comma, False for pipe.
    - Else: next is the single worker or FINISH.
    """
    text = (response or "").strip().upper()
    # Sequential: WORKER1|WORKER2
    if "|" in text:
        parts = [p.strip() for p in text.split("|") if p.strip()]
        workers: list[WorkerName] = []
        for p in parts:
            w = _label_to_worker(p)
            # TIMESERIES should not be auto-chained with other workers; it is for explicit CSV maintenance only.
            if w and w != "FINISH" and w != "timeseries":
                workers.append(w)
        if workers:
            return "FINISH", workers, False  # sequential
    # Parallel: WORKER1,WORKER2
    if "," in text:
        parts = [p.strip() for p in text.split(",") if p.strip()]
        workers = []
        for p in parts:
            w = _label_to_worker(p)
            # TIMESERIES should not be auto-chained with other workers; it is for explicit CSV maintenance only.
            if w and w != "FINISH" and w != "timeseries":
                workers.append(w)
        if workers:
            return "FINISH", workers, True  # parallel
    # Single
    w = _label_to_worker(text)
    return (w or "FINISH"), [], False


def _label_to_worker(label: str) -> WorkerName | Literal["FINISH"] | None:
    label = (label or "").strip().upper()
    if "SCRAPER" in label:
        return "scraper"
    if "ANALYTICS" in label:
        return "analytics"
    if "TIMESERIES" in label:
        return "timeseries"
    if "CHARTS" in label:
        return "charts"
    if "NEWS" in label:
        return "news"
    if "PREDICTION" in label or "PREDICT" in label or "TREND" in label:
        return "prediction"
    if "PORTFOLIO" in label:
        return "portfolio"
    if "SGI" in label or "COURTIER" in label or "BROKER" in label:
        return "sgi"
    if "COMPANY_DETAILS" in label or "FICHE" in label or "SOCIÉTÉ" in label or "SOCIETE" in label or "ACTIONNAIRES" in label or "DIVIDENDE" in label or "RÉSULTAT NET" in label or "RESULTAT NET" in label:
        return "company_details"
    if "FINISH" in label or not label:
        return "FINISH"
    return None


def _condense_to_user_final_pairs(messages: list) -> list:
    """
    Reduce message list to [user, final_ai, user, final_ai, ...] where final_ai is the
    reply sent to the user (last AIMessage before next HumanMessage, excluding NLU).
    """
    out: list = []
    max_messages = getattr(config, "MEMORY_MAX_MESSAGES", MEMORY_MAX_MESSAGES)
    i = 0
    while i < len(messages):
        if not isinstance(messages[i], HumanMessage):
            i += 1
            continue
        user_msg = messages[i]
        j = i + 1
        final_ai = None
        while j < len(messages):
            if isinstance(messages[j], HumanMessage):
                break
            if isinstance(messages[j], AIMessage):
                content = str(getattr(messages[j], "content", "") or "")
                if "[NLU]" not in content:
                    final_ai = messages[j]
            j += 1
        if final_ai is not None:
            out.append(user_msg)
            out.append(final_ai)
        i = j if j > i else i + 1
    return out[-max_messages:]


def _build_supervisor_node(model: str):
    llm = get_llm(model=model)

    def supervisor(state: AgentState) -> dict:
        logger.info("[GRAPH] node=supervisor start")
        messages = state.get("messages") or []
        structured_data = state.get("structured_data")

        if not messages:
            return {
                "messages": messages,
                "next": "FINISH",
                "multi_workers": [],
                "multi_parallel": False,
            }

        last_msg = messages[-1]
        last_content = (last_msg.content if hasattr(last_msg, "content") else "") or ""
        # If last message is worker response (not NLU), finish—avoid endless loops
        if isinstance(last_msg, AIMessage) and "[NLU]" not in str(last_content) and len(str(last_content).strip()) > 20:
            return {
                "messages": messages,
                "next": "FINISH",
                "multi_workers": [],
                "multi_parallel": False,
            }
        if structured_data and "[NLU]" in str(last_content):
            suggested = (structured_data.get("suggested_worker") or "").strip().lower()
            if suggested in ("scraper", "analytics", "timeseries", "charts", "news", "portfolio", "prediction", "sgi", "company_details"):
                return {
                    "messages": messages,
                    "next": suggested,
                    "multi_workers": [],
                    "multi_parallel": False,
                }

        time_system = _get_supervisor_system()
        to_send = [SystemMessage(content=time_system)] + list(messages)
        reply = llm.invoke(to_send)
        content = reply.content if hasattr(reply, "content") else str(reply)
        next_worker, multi_workers, multi_parallel = _parse_next(content)
        logger.info("[GRAPH] supervisor -> next=%s multi=%s", next_worker, multi_workers or None)
        out: dict = {
            "messages": messages,
            "next": next_worker,
            "multi_workers": [],
            "multi_parallel": False,
        }
        if multi_workers:
            out["multi_workers"] = multi_workers
            out["multi_parallel"] = multi_parallel
        return out

    return supervisor


def _log_tools_from_messages(messages: list, agent_name: str) -> None:
    """Log tool calls found in messages for debugging."""
    for m in messages:
        if isinstance(m, ToolMessage) and getattr(m, "name", None):
            logger.info("[GRAPH] agent=%s tool=%s", agent_name, m.name)
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            for tc in m.tool_calls:
                name = tc.get("name", "?") if isinstance(tc, dict) else getattr(tc, "name", "?")
                logger.info("[GRAPH] agent=%s tool_call=%s", agent_name, name)


def _entities_hint(structured_data: dict | None) -> str:
    if not structured_data or not isinstance(structured_data.get("entities"), dict):
        return ""
    ent = structured_data["entities"]
    if not ent:
        return ""
    parts = [f"{k}={v}" for k, v in ent.items() if v]
    if not parts:
        return ""
    return f"\n**CRITICAL - Use these for the CURRENT question (do NOT use symbols from previous messages):** {', '.join(parts)}"


def _build_worker_node(
    agent_builder,
    model: str,
    *,
    worker_name: str = "worker",
    extract_image_path: bool = False,
    prepend_system: str | None | Callable[[], str] = None,
):
    agent = agent_builder(model=model)

    def node(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
        logger.info("[GRAPH] node=%s start", worker_name)
        messages = state.get("messages") or []
        structured_data = state.get("structured_data")
        time_line = get_time_prefix()
        if prepend_system:
            if callable(prepend_system):
                try:
                    sig = inspect.signature(prepend_system)
                    if len(sig.parameters) >= 1:
                        system_content = prepend_system(state)
                    else:
                        system_content = prepend_system()
                except Exception:
                    system_content = prepend_system()
            else:
                system_content = prepend_system
            entities_hint = _entities_hint(structured_data)
            if entities_hint:
                system_content = system_content.rstrip() + entities_hint
            messages = [SystemMessage(content=system_content)] + list(messages)
        else:
            prefix = time_line
            entities_hint = _entities_hint(structured_data)
            if entities_hint:
                prefix = prefix.rstrip() + entities_hint
            messages = [SystemMessage(content=prefix)] + list(messages)
        # Forward the run config so tool-level injections (RunnableConfig, e.g.
        # the verified user id for portfolio tools) reach nested agents — also
        # across the multi-worker's thread pool where context vars don't flow.
        result = agent.invoke({"messages": messages}, config=config)
        out_messages = result.get("messages", messages)
        _log_tools_from_messages(out_messages, worker_name)
        out: dict = {"messages": out_messages, "next": "FINISH"}
        if extract_image_path:
            path = _extract_image_path_from_messages(out_messages)
            if path:
                out["image_path"] = path
        return out

    return node


def route_after_nlu(state: AgentState) -> Literal["supervisor", "__end__"]:
    if state.get("clarification"):
        return "__end__"
    return "supervisor"


def route_after_supervisor(
    state: AgentState,
) -> Literal["scraper", "analytics", "timeseries", "charts", "news", "portfolio", "prediction", "sgi", "company_details", "multi_worker", "__end__"]:
    multi = state.get("multi_workers") or []
    if multi:
        return "multi_worker"
    next_ = state.get("next") or "FINISH"
    if next_ == "scraper":
        return "scraper"
    if next_ == "analytics":
        return "analytics"
    if next_ == "timeseries":
        return "timeseries"
    if next_ == "charts":
        return "charts"
    if next_ == "news":
        return "news"
    if next_ == "prediction":
        return "prediction"
    if next_ == "portfolio":
        return "portfolio"
    if next_ == "sgi":
        return "sgi"
    if next_ == "company_details":
        return "company_details"
    return "__end__"


def _build_multi_worker_node(
    worker_nodes: dict[WorkerName, Callable[..., dict]],
    model: str,
) -> Callable[..., dict]:
    """Run multiple workers in parallel or sequential, merge results."""

    def multi_worker(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
        workers = state.get("multi_workers") or []
        logger.info("[GRAPH] node=multi_worker workers=%s parallel=%s", workers, state.get("multi_parallel", False))
        parallel = state.get("multi_parallel", False)
        if not workers:
            return {
                "messages": state.get("messages", []),
                "next": "FINISH",
                "multi_workers": [],
                "multi_parallel": False,
            }

        messages = list(state.get("messages") or [])
        image_path = state.get("image_path")
        valid = {"scraper", "analytics", "timeseries", "charts", "news", "portfolio", "prediction", "sgi", "company_details"}
        workers = [w for w in workers if w in valid and w in worker_nodes]

        if parallel:
            # Run all workers with same input state, merge new AIMessages (preserve worker order)
            base_len = len(messages)
            worker_results: dict[WorkerName, dict] = {}
            with ThreadPoolExecutor(max_workers=len(workers)) as ex:
                futures = {ex.submit(worker_nodes[w], state, config): w for w in workers}
                for fut in as_completed(futures):
                    wn = futures[fut]
                    try:
                        res = fut.result()
                        worker_results[wn] = res
                    except Exception as e:
                        logger.warning("Worker %s failed: %s", wn, e)
            all_new: list = []
            for wn in workers:
                res = worker_results.get(wn)
                if not res:
                    continue
                msgs = res.get("messages") or []
                for m in msgs[base_len:]:
                    if isinstance(m, AIMessage):
                        all_new.append(m)
                if res.get("image_path") and not image_path:
                    image_path = res["image_path"]
            out_messages = messages + all_new
        else:
            # Sequential: run each worker, pass accumulated state to next
            current: AgentState = dict(state)
            for wn in workers:
                result = worker_nodes[wn](current, config)
                current = dict(result)
                if "messages" in result:
                    current["messages"] = result["messages"]
                if result.get("image_path"):
                    current["image_path"] = result["image_path"]
            out_messages = current.get("messages") or messages

        out: dict = {
            "messages": out_messages,
            "next": "FINISH",
            "multi_workers": [],
            "multi_parallel": False,
        }
        if image_path:
            out["image_path"] = image_path
        return out

    return multi_worker


def create_master_graph(model: str | None = None, checkpointer: Any | None = None) -> Any:
    model = model or get_default_model()
    builder = StateGraph(AgentState)

    builder.add_node("nlu", create_nlu_node(model))
    builder.add_node("supervisor", _build_supervisor_node(model))

    worker_nodes_map: dict[WorkerName, Callable[..., dict]] = {}
    scraper_n = _build_worker_node(create_scraper_agent, model, worker_name="scraper", prepend_system=get_scraper_agent_system)
    analytics_n = _build_worker_node(create_analytics_agent, model, worker_name="analytics", prepend_system=get_analytics_agent_system)
    timeseries_n = _build_worker_node(create_timeseries_agent, model, worker_name="timeseries", prepend_system=get_timeseries_agent_system)
    charts_n = _build_worker_node(create_charts_agent, model, worker_name="charts", extract_image_path=True, prepend_system=get_charts_agent_system)
    news_n = _build_worker_node(create_news_agent, model, worker_name="news", prepend_system=get_news_agent_system)

    def _portfolio_system(state: AgentState) -> str:
        return get_portfolio_agent_system(state.get("telegram_user_id") or 0)
    portfolio_n = _build_worker_node(create_portfolio_agent, model, worker_name="portfolio", prepend_system=_portfolio_system)
    prediction_n = _build_worker_node(create_prediction_agent, model, worker_name="prediction", prepend_system=get_prediction_agent_system)
    sgi_n = _build_worker_node(create_sgi_agent, model, worker_name="sgi", prepend_system=get_sgi_agent_system)
    company_details_n = _build_worker_node(create_company_details_agent, model, worker_name="company_details", prepend_system=get_company_details_agent_system)

    builder.add_node("scraper", scraper_n)
    builder.add_node("analytics", analytics_n)
    builder.add_node("timeseries", timeseries_n)
    builder.add_node("charts", charts_n)
    builder.add_node("news", news_n)
    builder.add_node("portfolio", portfolio_n)
    builder.add_node("prediction", prediction_n)
    builder.add_node("sgi", sgi_n)
    builder.add_node("company_details", company_details_n)

    worker_nodes_map["scraper"] = scraper_n
    worker_nodes_map["analytics"] = analytics_n
    worker_nodes_map["timeseries"] = timeseries_n
    worker_nodes_map["charts"] = charts_n
    worker_nodes_map["news"] = news_n
    worker_nodes_map["portfolio"] = portfolio_n
    worker_nodes_map["prediction"] = prediction_n
    worker_nodes_map["sgi"] = sgi_n
    worker_nodes_map["company_details"] = company_details_n

    builder.add_node("multi_worker", _build_multi_worker_node(worker_nodes_map, model))

    builder.set_entry_point("nlu")
    builder.add_conditional_edges("nlu", route_after_nlu)
    builder.add_conditional_edges("supervisor", route_after_supervisor)
    builder.add_edge("scraper", "supervisor")
    builder.add_edge("analytics", "supervisor")
    builder.add_edge("timeseries", "supervisor")
    builder.add_edge("charts", "supervisor")
    builder.add_edge("news", "supervisor")
    builder.add_edge("portfolio", "supervisor")
    builder.add_edge("prediction", "supervisor")
    builder.add_edge("sgi", "supervisor")
    builder.add_edge("company_details", "supervisor")
    builder.add_edge("multi_worker", "supervisor")

    cp = checkpointer if checkpointer is not None else MemorySaver()
    return builder.compile(checkpointer=cp)


# Compile the graph once per (model, checkpointer): building 9 ReAct workers on
# every request is wasteful. A None checkpointer (CLI --no-memory) keeps the old
# behavior — a fresh MemorySaver graph per call.
_compiled_cache: dict[tuple[str, int], Any] = {}
_compiled_lock = threading.Lock()


def get_compiled_graph(model: str | None = None, checkpointer: Any | None = None) -> Any:
    if checkpointer is None:
        return create_master_graph(model=model, checkpointer=None)
    key = (model or get_default_model(), id(checkpointer))
    with _compiled_lock:
        graph = _compiled_cache.get(key)
        if graph is None:
            graph = create_master_graph(model=key[0], checkpointer=checkpointer)
            _compiled_cache[key] = graph
    return graph


def run_agent(
    query: str,
    model: str | None = None,
    thread_id: str | None = None,
    telegram_user_id: int | None = None,
    checkpointer: Any | None = None,
) -> dict:
    model = model or get_default_model()
    graph = get_compiled_graph(model=model, checkpointer=checkpointer)
    configurable: dict[str, Any] = {"thread_id": thread_id or "default"}
    if telegram_user_id is not None:
        # Server-verified identity: portfolio tools read it from here (never from
        # the model's tool arguments).
        configurable["telegram_user_id"] = telegram_user_id
    run_config = {
        "configurable": configurable,
        "recursion_limit": config.RECURSION_LIMIT,
    }
    current = graph.get_state(run_config)
    existing = (current.values or {}).get("messages") or []
    # Keep only last N messages as [user, final_ai, user, final_ai, ...]
    condensed = _condense_to_user_final_pairs(existing)
    messages = list(condensed) + [HumanMessage(content=query)]
    initial: AgentState = {"messages": messages}
    if telegram_user_id is not None:
        initial["telegram_user_id"] = telegram_user_id

    def _revert_messages() -> None:
        try:
            graph.update_state(run_config, {"messages": condensed})
        except Exception as upd_err:
            logger.warning("Could not revert messages on failure: %s", upd_err)

    def _persist_clarification(clarification: str) -> None:
        """Save the clarifying exchange so the next turn has full context."""
        try:
            history = list(condensed) + [
                HumanMessage(content=query),
                AIMessage(content=clarification),
            ]
            max_messages = getattr(config, "MEMORY_MAX_MESSAGES", MEMORY_MAX_MESSAGES)
            graph.update_state(run_config, {"messages": history[-max_messages:]})
        except Exception as upd_err:
            logger.warning("Could not persist clarification turn: %s", upd_err)

    last_error: BaseException | None = None
    for attempt in range(3):
        try:
            result = graph.invoke(initial, config=run_config)
            if result.get("clarification"):
                _persist_clarification(result["clarification"])
                return result
            # Success: store only [user, final_ai, ...], last 10
            new_condensed = _condense_to_user_final_pairs(result.get("messages") or [])
            try:
                graph.update_state(run_config, {"messages": new_condensed})
            except Exception as upd_err:
                logger.warning("Could not update state with condensed messages: %s", upd_err)
            return result
        except Exception as e:
            _revert_messages()
            if "recursion" in str(e).lower() or "GraphRecursionError" in type(e).__name__:
                logger.warning("Graph hit recursion limit, returning partial result: %s", e)
                try:
                    state = graph.get_state(run_config)
                    vals = state.values or {}
                    if vals and vals.get("messages"):
                        return vals
                except Exception as get_err:
                    logger.warning("Could not get partial state: %s", get_err)
            last_error = e
            err_str = str(e).lower()
            is_retryable = (
                "503" in err_str
                or "ssl" in err_str
                or "eof" in err_str
                or "connection" in err_str
                or "connect" in err_str
                or "timeout" in err_str
            )
            if is_retryable and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    raise last_error or RuntimeError("Agent invocation failed")
