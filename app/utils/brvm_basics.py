"""Short BRVM and investing basics (static content for FAQ-style questions)."""
from __future__ import annotations

BRVM_BASICS = """BRVM (Bourse Régionale des Valeurs Mobilières) is the regional stock exchange for the West African Economic and Monetary Union (UEMOA). It is based in Abidjan, Côte d'Ivoire, and lists shares of companies from Benin, Burkina Faso, Côte d'Ivoire, Guinea-Bissau, Mali, Niger, Senegal, and Togo. All listed securities are traded in F CFA (XOF).

How to invest on BRVM:
- Open a securities account with a licensed intermediary (bank or broker) in a UEMOA country.
- Place buy/sell orders through your intermediary; they execute on the BRVM.
- Settlement is in F CFA. Dividends and capital gains may be subject to local tax rules.

This assistant provides data and analysis only for BRVM-listed companies (prices, volume, comparisons, charts, news). It does not provide investment advice or data from other exchanges (e.g. NYSE, NASDAQ, other African bourses)."""


def get_brvm_basics() -> str:
    """Return short BRVM and investing basics text for FAQ-style answers."""
    return BRVM_BASICS.strip()
