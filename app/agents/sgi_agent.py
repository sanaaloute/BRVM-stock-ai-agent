"""SGI worker: list BRVM brokers (SGI), read local data, fetch if missing, fetch URL content when needed."""
from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from app.models.llm import get_llm
from app.agents.utils import get_time_prefix
from app.tools.stock_tools import (
    get_sgi_data_tool,
    fetch_sgi_data_tool,
    fetch_sgi_url_tool,
)


def get_sgi_agent_system() -> str:
    return f"""SGI (courtiers BRVM). Répondre aux questions sur les sociétés de gestion et d'intermédiation. {get_time_prefix()}

**Règle:** Toujours appeler d'abord get_sgi_data pour lire les données locales (app/data/sgi_brvm.json).
- Si get_sgi_data renvoie "no_local_data", appeler fetch_sgi_data pour télécharger depuis Rich Bourse, puis get_sgi_data à nouveau.
- Si l'utilisateur demande des détails depuis une URL (fiche SGI, tarifs, site web), utiliser fetch_sgi_url avec l'URL fournie dans les données SGI (detail_url, tarifs_url, documents_url, website).

**Outils:** get_sgi_data (filtres optionnels: name_filter, country_filter) | fetch_sgi_data (si fichier absent) | fetch_sgi_url (pour une URL d'une SGI)

**Réponse:** Résumer les infos (nom, pays, note, montant min, adresse, téléphone, site, email). Ne pas exposer de chemins de fichiers dans la réponse."""


SGI_TOOLS = [
    get_sgi_data_tool,
    fetch_sgi_data_tool,
    fetch_sgi_url_tool,
]


def create_sgi_agent(model: str | None = None):
    llm = get_llm(model=model)
    return create_react_agent(llm, SGI_TOOLS)
