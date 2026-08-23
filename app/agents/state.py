"""Shared state for the agent graph."""
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import BaseMessage

WorkerName = Literal["scraper", "analytics", "timeseries", "charts", "news", "portfolio", "prediction", "sgi", "company_details", "advisor"]
NextWorker = WorkerName | Literal["FINISH"]


class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], "Chat messages"]
    next: NextWorker
    """Single next worker (when multi_workers is empty)."""
    multi_workers: list[WorkerName]
    """List of workers to run. When non-empty, used instead of next."""
    multi_parallel: bool
    """If True, run multi_workers in parallel; else sequential."""
    last_worker: str | None
    """Structural marker set by worker nodes ("multi" for the multi_worker); the
    supervisor FINISHes without an LLM call when it is set, then clears it."""
    image_path: str | None
    image_paths: list[str] | None
    """All charts produced this run (several when the user asked for separate charts)."""
    image_caption: str | None
    """Short (≤ 50 chars) chart caption, e.g. '📊 ETIT, SNTS · 01/06/2026–23/08/2026'."""
    structured_data: dict[str, Any] | None
    clarification: str | None
    conversation_summary: str | None
    telegram_user_id: int | None
