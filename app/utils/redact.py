"""Format agent output to plain text for chat clients (deterministic, no LLM call).

Previously this rewrote every reply with an LLM — one extra model call per
message (latency + cost). The rewrite is now a set of regex transforms:
drop internal details (file paths, tool names), then strip markdown.
"""
from __future__ import annotations

import re

# Drop lines that mention file paths or tool usage (internal details)
_PATH_LINE = re.compile(
    r"/tmp/|/var/|chart_.*\.png|image_path|saved at .*\.(png|jpg)|stored at|image at\s|Send image at",
    re.IGNORECASE,
)
_TOOL_LINE = re.compile(
    r"plot_company_chart|get_timeseries|scrape_sikafinance|scrape_richbourse|scrape_brvm|get_stock_metrics|compare_stocks|compute_metrics|ensure_timeseries|list_timeseries_status|I used (?:the )?\w+ (?:tool|function)|called \w+ tool|get_sgi_data|fetch_sgi_data|fetch_sgi_url|get_company_details|fetch_company_details|get_all_trends|get_trends_by_option|get_stock_prediction_detail|get_sikafinance_actualites|get_sikafinance_communiques|get_richbourse_dividends|get_market_news|get_company_news|get_brvm_official_announcements|get_market_overview|get_brvm_basics|get_company_info|portfolio_add|portfolio_remove|get_portfolio|tracking_add|tracking_remove|get_tracking|target_add|target_remove|get_targets",
    re.IGNORECASE,
)

_MD_HEADER = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_MD_BOLD = re.compile(r"\*\*([^*]*)\*\*|__([^_]*)__")
_MD_ITALIC = re.compile(r"(?<!\w)\*([^*\n]+)\*(?!\w)")
_MD_BACKTICK = re.compile(r"`([^`]*)`")
_TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLE_SEP = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def _strip_internal_refs(text: str) -> str:
    lines = text.split("\n")
    out = [ln for ln in lines if not _PATH_LINE.search(ln) and not _TOOL_LINE.search(ln)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _table_row_to_line(line: str) -> str:
    """Convert a markdown table row '| a | b |' to 'a · b'. Separator rows -> ''."""
    if _TABLE_SEP.match(line):
        return ""
    m = _TABLE_ROW.match(line)
    if not m:
        return line
    cells = [c.strip() for c in m.group(1).split("|")]
    return " · ".join(c for c in cells if c)


def _to_plain_text(text: str) -> str:
    """Markdown → plain text (headers, bold, italic, backticks, tables)."""
    if not text:
        return text
    text = _MD_HEADER.sub("", text)
    text = _MD_BOLD.sub(lambda m: m.group(1) if m.group(1) is not None else m.group(2), text)
    text = _MD_BACKTICK.sub(r"\1", text)
    text = _MD_ITALIC.sub(r"\1", text)
    lines = [_table_row_to_line(ln) for ln in text.split("\n")]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def redact_for_chat(raw_output: str, model: str | None = None) -> str:
    """Return a plain-text, internal-detail-free version of the agent reply.

    `model` is accepted for backwards compatibility and ignored (no LLM used).
    """
    raw = (raw_output or "").strip()
    if not raw:
        return "No answer."
    out = _strip_internal_refs(raw)
    out = _to_plain_text(out)
    return out or "No answer."
