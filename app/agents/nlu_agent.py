"""NLU: intent/entity extraction, clarification, suggested_worker."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

logger = logging.getLogger(__name__)
from app.models.llm import get_llm

import config
from app.utils.brvm_companies import (
    format_list_for_prompt,
    normalize_entities,
)

from app.agents.utils import get_time_prefix


def _nlu_system_prompt() -> str:
    brvm_list = format_list_for_prompt()
    return f"""BRVM stock assistant NLU. Output CLARIFY or JSON only. F CFA. {get_time_prefix()}

**CRITICAL - Multi-turn context:** You receive the recent conversation (user/assistant turns) followed by the CURRENT user message. Use the history to resolve short follow-ups, pronouns ("it", "that stock", "celle-là", "son cours"), and bare symbols or values:
- If the previous assistant message asked a question (e.g. which stock to add to the portfolio, which period for a chart) and the user replies with a symbol or value, output the intent that question was serving (e.g. portfolio_add with that symbol) — do NOT treat it as a new independent query.
- If the current message refers to something discussed earlier (e.g. "et son dividende ?" after talking about ETIT), reuse the relevant entities from history.
- Only treat the current message as independent when it clearly starts a new topic.

**BRVM symbols only:** (for when the user names a specific company or symbol)
{brvm_list}
Unknown symbol or other exchange → CLARIFY.

**General market questions (NO symbol required):** For "most expensive stock", "highest price stock", "lowest price stock", "cheapest stock", "what is the cheapest?", "should I buy the lowest price stock?" — use intent **market_overview**, suggested_worker **analytics**, and leave entities empty or omit symbol. Do NOT ask for a symbol; the analytics worker will compute from all BRVM stocks.

**How-to questions about this assistant (portfolio, tracking list, price alerts):** When the user asks HOW to do something (e.g. "comment ajouter une action à mon portefeuille ?", "how do I set a price alert?"), the question deserves an ANSWER, not just a bare counter-question. Reply with `CLARIFY:` followed by BOTH:
1. A short explanation (2-3 sentences) of how the feature works and what info is needed, and
2. A follow-up question inviting the user to do it now (asking for the missing details: symbol, buy price/date, target price...).
Example — User: "Comment ajouter une action à mon portefeuille ?"
CLARIFY: Pour ajouter une action à votre portefeuille, donnez-moi simplement son symbole BRVM (ex. ETIT, NTLC, SNTS). Idéalement, précisez aussi le prix et la date d'achat pour un suivi de performance précis. Quelle action voulez-vous ajouter ?

**Intents (exact):** market_overview | price_query | compare | chart | metrics | news | prediction | scrape | update_timeseries | brvm_basics | portfolio_display | portfolio_add | portfolio_remove | tracking_list | tracking_add | target_set | target_list | sgi | company_details | general

**Worker:** analytics (prices, compare, stats, overview) | charts (plot) | timeseries (CSV) | scraper (raw fetch) | news | prediction (trends, hausse/baisse/neutre, technical prediction for a stock) | portfolio | sgi (courtiers BRVM, liste SGI, où ouvrir un compte, tarifs courtiers) | company_details (fiche société: actionnaires, dividende, résultat net, croissance, BNPA, PER, présentation, dirigeants)

**Output:**
A) Unclear → CLARIFY: <short question>
B) Clear → {{"intent": "...", "entities": {{"symbol": "NTLC", ...}} or {{}}, "suggested_worker": "analytics"}}"""


def _extract_user_text(messages: list) -> str:
    for m in reversed(messages):
        if isinstance(m, HumanMessage) and m.content:
            return str(m.content).strip()
    return ""


def _parse_nlu_response(content: str) -> tuple[dict[str, Any] | None, str | None]:
    text = (content or "").strip()
    # Clarification: line starting with CLARIFY:
    if text.upper().startswith("CLARIFY:"):
        clarification = text[8:].strip()
        if clarification:
            return None, clarification
    # Try to find JSON in the response (allow nested braces for "entities")
    def _make_structured(intent: str, entities: dict, worker: str) -> tuple[dict[str, Any], str | None]:
        # Resolve and validate symbols against BRVM list; ask for clarification if unknown
        entities, unknown = normalize_entities(entities)
        if unknown:
            return (
                None,
                f"Société ou symbole introuvable sur la BRVM : {', '.join(unknown)}. Utilisez un symbole de la liste BRVM (ex. NTLC, SLBC, SNTS, Sonatel, Solibra, Nestlé).",
            )
        return {
            "intent": intent,
            "entities": entities,
            "suggested_worker": worker,
        }, None

    for candidate in (text.strip(), re.sub(r"^.*?(\{)", r"\1", text, count=1)):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict) and "intent" in data:
                intent = data.get("intent") or "general"
                entities = data.get("entities") if isinstance(data.get("entities"), dict) else {}
                worker = data.get("suggested_worker") or "analytics"
                return _make_structured(intent, entities, worker)
        except json.JSONDecodeError:
            pass
    # Find first { and match balanced braces
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i, c in enumerate(text[start:], start=start):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(text[start : i + 1])
                        if isinstance(data, dict) and "intent" in data:
                            intent = data.get("intent") or "general"
                            entities = data.get("entities") if isinstance(data.get("entities"), dict) else {}
                            worker = data.get("suggested_worker") or "analytics"
                            return _make_structured(intent, entities, worker)
                    except json.JSONDecodeError:
                        pass
                    break
    # Fallback: treat as unclear
    return None, "Pouvez-vous reformuler votre question ? Par exemple : « Quel est le cours de NTLC ? » ou « Graphique SLBC du 2025-01-01 au 2025-02-21 »."


def _history_for_nlu(messages: list) -> list:
    """Recent conversation turns for the NLU, excluding the current message and
    internal [NLU] routing notes."""
    history = []
    for m in messages[:-1]:
        if isinstance(m, AIMessage) and "[NLU]" in str(getattr(m, "content", "") or ""):
            continue
        if isinstance(m, (HumanMessage, AIMessage)) and getattr(m, "content", None):
            history.append(m)
    return history[-10:]


def run_nlu_node(state: dict, model: str) -> dict:
    logger.info("[GRAPH] node=nlu start")
    messages = state.get("messages") or []
    user_text = _extract_user_text(messages)
    if not user_text:
        return {
            "messages": messages,
            "clarification": "What would you like to know about BRVM stocks?",
            "structured_data": None,
        }

    llm = get_llm(model=model)

    system = _nlu_system_prompt()
    # Give the NLU the recent conversation so it can resolve follow-ups
    # (e.g. a bare "ETIT" answering "which stock do you want to add?").
    history = _history_for_nlu(messages)
    prompt_messages = [SystemMessage(content=system)] + history + [
        HumanMessage(content=f"Current user message: {user_text}")
    ]
    reply = llm.invoke(prompt_messages)
    content = reply.content if hasattr(reply, "content") else str(reply)
    structured_data, clarification = _parse_nlu_response(content)

    if clarification:
        return {
            "messages": messages,
            "clarification": clarification,
            "structured_data": None,
        }

    summary = f"[NLU] intent={structured_data.get('intent')}, entities={structured_data.get('entities')}, suggested_worker={structured_data.get('suggested_worker')}"
    new_messages = list(messages) + [AIMessage(content=summary)]

    return {
        "messages": new_messages,
        "structured_data": structured_data,
        "clarification": None,
    }


def create_nlu_node(model: str):
    def node(state: dict) -> dict:
        return run_nlu_node(state, model)

    return node
