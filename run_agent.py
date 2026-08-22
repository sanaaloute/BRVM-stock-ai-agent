"""Run BRVM agent (CLI). Memory: data/chat_memory.db unless --no-memory."""
import argparse
import sys

import config
from app.agents import run_agent
from app.agents.graph import CHAT_MEMORY_DB
from app.models.llm import get_default_model


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BRVM stock master agent (scraper + analytics workers).")
    parser.add_argument("query", nargs="?", default="", help="User question (or read from stdin).")
    parser.add_argument("--model", default=None, help="Model override (default: from LLM_PROVIDER/LLM_MODEL).")
    parser.add_argument("--no-memory", action="store_true", help="Disable persistent chat memory for this run.")
    args = parser.parse_args()

    text = (args.query or "").strip()
    if not text and sys.stdin.isatty():
        parser.print_help()
        return 0
    if not text:
        text = sys.stdin.read().strip()
    if not text:
        return 1
    if config.LLM_PROVIDER == "ollama" and config.OLLAMA_CLOUD and not config.OLLAMA_API_KEY:
        print("Error: OLLAMA_API_KEY is required when OLLAMA_CLOUD=true. Create one at https://ollama.com/settings/keys", file=sys.stderr)
        return 1

    model = args.model or get_default_model()
    print("Running agent...")
    if args.no_memory:
        result = run_agent(text, model=model, thread_id="cli")
    else:
        CHAT_MEMORY_DB.parent.mkdir(parents=True, exist_ok=True)
        from langgraph.checkpoint.sqlite import SqliteSaver
        with SqliteSaver.from_conn_string(str(CHAT_MEMORY_DB)) as checkpointer:
            result = run_agent(text, model=model, thread_id="cli", checkpointer=checkpointer)
    reply = result.get("_fresh_reply") or result.get("clarification")
    if reply:
        print(f"\n[assistant]\n{reply}")
    else:
        # Fallback for older run_agent results: print the full transcript.
        messages = result.get("messages") or []
        for m in messages:
            if hasattr(m, "content") and m.content:
                role = getattr(m, "type", "message")
                print(f"\n[{role}]\n{m.content}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
