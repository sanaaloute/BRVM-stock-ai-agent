"""General responder: greetings, chitchat and finance/BRVM education.

Handles every message that needs NO live data and NO specialist worker, in one
direct LLM call (no tools): "bonjour", "c'est quoi la BRVM ?", "what is a
dividend?", "comment fonctionne la bourse ?", "comment ajouter une alerte ?"...
BRVM-specific facts are grounded in the static BRVM_BASICS text so the model
cannot invent them."""
from __future__ import annotations

import logging
from typing import Optional

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

from app.agents.state import AgentState
from app.agents.utils import get_time_prefix
from app.models.llm import get_agent_llm
from app.utils.brvm_basics import get_brvm_basics


def _general_system() -> str:
    return f"""Assistant BRVM (Bourse Régionale des Valeurs Mobilières). {get_time_prefix()}

Réponds DIRECTEMENT à l'utilisateur, en français, de façon claire et pédagogique.

**Ton domaine sans outils :** salutations et conversation courante ; pédagogie boursière (c'est quoi une action, un dividende, un indice, comment fonctionne un marché boursier, risques, diversification...) ; questions sur la BRVM (voir fiche de référence ci-dessous) ; explication de tes fonctionnalités (cours et palmarès, comparaisons, graphiques, actualités, prédictions, fiches sociétés, conseils, portefeuille, liste de suivi, alertes de prix, SGI/courtiers) — explique comment faire et invite l'utilisateur à formuler sa demande.

**Règles :**
- JAMAIS de chiffres de marché (cours, volumes, variations, rendements) : tu n'as pas accès aux données en direct. Pour une donnée actuelle, invite l'utilisateur à demander avec le symbole (ex. « Quel est le cours de SNTS ? »).
- Faits BRVM : tiens-toi à la fiche ci-dessous, n'invente rien.
- Pas de conseil d'investissement personnalisé (« achète X ») : explique les concepts et, si la question s'y prête, rappelle que ce n'est pas un conseil.
- Style : la réponse d'abord, gras et puces si utile. Réponse développée quand le sujet le mérite — pas de plafond de longueur, mais pas de remplissage.

**Fiche BRVM (faits de référence) :**
{get_brvm_basics()}"""


def create_general_node(model: str):
    def node(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
        logger.info("[GRAPH] node=general start")
        # Drop internal routing notes ([NLU] ...) — the responder only needs the
        # real conversation.
        messages = [
            m for m in (state.get("messages") or [])
            if not (isinstance(m, AIMessage) and "[NLU]" in str(getattr(m, "content", "") or ""))
        ]
        llm = get_agent_llm("general", model=model)
        reply = llm.invoke([SystemMessage(content=_general_system())] + messages)
        content = reply.content if hasattr(reply, "content") else str(reply)
        out_messages = list(state.get("messages") or []) + [AIMessage(content=content)]
        return {
            "messages": out_messages,
            "next": "FINISH",
            "multi_workers": [],
            "multi_parallel": False,
            "last_worker": "general",
        }

    return node
