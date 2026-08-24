import os
from pathlib import Path
from app.models.schemas import TraceEvent

LOG_PATH = Path(os.getenv("TRACE_LOG_PATH", "logs/trace.jsonl"))


def log_turn(trace: TraceEvent):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(trace.model_dump_json() + "\n")