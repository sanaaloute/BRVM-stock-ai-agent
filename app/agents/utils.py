"""Agent helpers: current time for prompts."""
from __future__ import annotations

from datetime import datetime


def get_current_time_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_time_prefix() -> str:
    return (
        f"For reference today's date is: {get_current_time_str()}. "
        "Always consider the date to answer questions in order to get the up-to-date information."
    )
