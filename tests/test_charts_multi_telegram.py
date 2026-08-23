"""Tests for multi-chart comparison plumbing and Telegram delivery shaping:

- app/utils/plots.py: plot_timeseries_multi (several series on ONE chart)
- app/tools/stock_tools.py: plot_company_chart with symbols="A,B"
- app/agents/charts_agent.py: image paths + short caption extraction
- app/bot/telegram_bot.py: split_text (no more truncation) + _short_caption

Offline: load_series is monkeypatched with synthetic rows.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from langchain_core.messages import ToolMessage  # noqa: E402

from app.agents.charts_agent import (  # noqa: E402
    _extract_chart_caption_from_messages,
    _extract_image_path_from_messages,
    _extract_image_paths_from_messages,
)
from app.bot.telegram_bot import CHART_CAPTION_CHARS, MAX_MESSAGE_LENGTH, _short_caption, split_text  # noqa: E402
from app.utils import plots  # noqa: E402


# --- split_text ---------------------------------------------------------------


def test_split_text_short_message_single_chunk():
    assert split_text("Bonjour") == ["Bonjour"]


def test_split_text_long_message_no_truncation():
    text = "\n".join(f"Ligne {i} " + "x" * 80 for i in range(200))
    chunks = split_text(text)
    assert len(chunks) > 1
    assert all(len(c) <= MAX_MESSAGE_LENGTH for c in chunks)
    # No content lost and no "tronqué" marker added
    joined = "\n".join(chunks)
    assert "tronqué" not in joined
    for i in range(200):
        assert f"Ligne {i} " in joined


def test_split_text_no_newlines_hard_cut():
    text = "a" * (MAX_MESSAGE_LENGTH * 2 + 10)
    chunks = split_text(text)
    assert all(len(c) <= MAX_MESSAGE_LENGTH for c in chunks)
    assert "".join(chunks) == text


# --- _short_caption ------------------------------------------------------------


def test_short_caption_fallback_and_limit():
    assert _short_caption(None) == "📊 Graphique"
    assert _short_caption("") == "📊 Graphique"
    long_caption = "📊 " + ", ".join(["SYMBOLTRESLONG"] * 10)
    out = _short_caption(long_caption)
    assert len(out) <= CHART_CAPTION_CHARS
    out_suffix = _short_caption(long_caption, " (1/2)")
    assert len(out_suffix) <= CHART_CAPTION_CHARS
    assert out_suffix.endswith("(1/2)")


# --- charts_agent extraction ---------------------------------------------------


def _chart_tool_msg(payload: dict) -> ToolMessage:
    return ToolMessage(content=json.dumps(payload), tool_call_id="t1", name="plot_company_chart")


def test_extract_image_paths_multiple_charts():
    msgs = [
        _chart_tool_msg({"image_path": "/tmp/chart_a.png", "symbol": "ETIT", "start_date": "2026-06-01", "end_date": "2026-08-23"}),
        _chart_tool_msg({"image_path": "/tmp/chart_b.png", "symbol": "SNTS", "start_date": "2026-06-01", "end_date": "2026-08-23"}),
    ]
    assert _extract_image_paths_from_messages(msgs) == ["/tmp/chart_a.png", "/tmp/chart_b.png"]
    # Single-image compat accessor returns the last chart (legacy behavior)
    assert _extract_image_path_from_messages(msgs) == "/tmp/chart_b.png"


def test_extract_image_paths_dedupes_and_skips_errors():
    msgs = [
        _chart_tool_msg({"image_path": "/tmp/chart_a.png", "symbol": "ETIT"}),
        _chart_tool_msg({"error": "Aucune donnée pour cette période.", "image_path": None}),
    ]
    assert _extract_image_paths_from_messages(msgs) == ["/tmp/chart_a.png"]


def test_extract_caption_single_symbol():
    msgs = [_chart_tool_msg({"image_path": "/tmp/c.png", "symbol": "ETIT", "start_date": "2026-06-01", "end_date": "2026-08-23"})]
    caption = _extract_chart_caption_from_messages(msgs)
    assert caption == "📊 ETIT · 01/06/2026–23/08/2026"
    assert len(caption) <= CHART_CAPTION_CHARS


def test_extract_caption_comparison_symbols():
    msgs = [_chart_tool_msg({
        "image_path": "/tmp/c.png",
        "symbols": ["ETIT", "SNTS"],
        "start_date": "2026-06-01",
        "end_date": "2026-08-23",
    })]
    caption = _extract_chart_caption_from_messages(msgs)
    assert "ETIT" in caption and "SNTS" in caption
    assert len(caption) <= CHART_CAPTION_CHARS


# --- plot_timeseries_multi -----------------------------------------------------


def _fake_rows(symbol, start_date, end_date, fetch_if_missing=True):
    base = {"ETIT": 30.0, "SNTS": 900.0}.get(symbol)
    if base is None:
        return []
    rows = []
    d = start_date
    while d <= end_date:
        rows.append({"date": d, "price": base + (d - start_date).days})
        d += timedelta(days=1)
    return rows


def test_plot_timeseries_multi_one_chart_two_series(monkeypatch):
    monkeypatch.setattr(plots, "load_series", _fake_rows)
    out = plots.plot_timeseries_multi(["ETIT", "SNTS"], date(2026, 6, 1), date(2026, 8, 23))
    try:
        assert out["error"] is None
        assert out["symbols"] == ["ETIT", "SNTS"]
        assert out["missing_symbols"] == []
        assert out["points_count"] > 0
        assert Path(out["image_path"]).exists()
        assert out["image_path"].endswith(".png")
    finally:
        Path(out["image_path"]).unlink(missing_ok=True)


def test_plot_timeseries_multi_reports_missing(monkeypatch):
    monkeypatch.setattr(plots, "load_series", _fake_rows)
    out = plots.plot_timeseries_multi(["ETIT", "INCONNU"], date(2026, 6, 1), date(2026, 8, 23))
    try:
        assert out["symbols"] == ["ETIT"]
        assert out["missing_symbols"] == ["INCONNU"]
        assert "INCONNU" in out["error"]
        assert Path(out["image_path"]).exists()
    finally:
        Path(out["image_path"]).unlink(missing_ok=True)


def test_plot_timeseries_multi_all_missing_returns_error(monkeypatch):
    monkeypatch.setattr(plots, "load_series", lambda *a, **k: [])
    out = plots.plot_timeseries_multi(["AAA", "BBB"], date(2026, 6, 1), date(2026, 8, 23))
    assert out["image_path"] is None
    assert out["error"]


# --- plot_company_chart tool with symbols --------------------------------------


def test_plot_tool_comparison_routes_to_multi(monkeypatch, tmp_path):
    from app.tools import stock_tools

    img = tmp_path / "chart_cmp.png"
    img.write_bytes(b"png")
    called = {}

    def fake_multi(symbols, start, end, chart_type="line"):
        called["symbols"] = symbols
        return {
            "symbols": symbols,
            "missing_symbols": [],
            "start_date": "2026-06-01",
            "end_date": "2026-08-23",
            "image_path": str(img),
            "points_count": 10,
            "error": None,
        }

    monkeypatch.setattr(stock_tools, "plot_timeseries_multi_service", fake_multi)
    out = json.loads(stock_tools._plot_company_chart("ETIT", "2026-06-01", "2026-08-23", symbols="ETIT,SNTS"))
    assert called["symbols"] == ["ETIT", "SNTS"]
    assert out["symbols"] == ["ETIT", "SNTS"]
    assert out["image_path"] == str(img)


def test_plot_tool_single_symbol_unaffected(monkeypatch):
    from app.tools import stock_tools

    def fake_single(symbol, start, end, chart_type="line"):
        return {"symbol": symbol, "start_date": start, "end_date": end, "image_path": "/tmp/x.png", "points_count": 5, "error": None}

    monkeypatch.setattr(stock_tools, "plot_timeseries_service", fake_single)
    out = json.loads(stock_tools._plot_company_chart("ETIT", "2026-06-01", "2026-08-23"))
    assert out["symbol"] == "ETIT"
    assert out["image_path"] == "/tmp/x.png"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
