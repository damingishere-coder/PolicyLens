from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from .domain import StrictModel

RESEARCH_TIMEOUT_SECONDS = 900.0


class ResearchProgress(StrictModel):
    phase: Literal["STARTING", "RESEARCHING", "WEB_SEARCH", "RESPONSE_READY"]
    elapsed_seconds: int = Field(ge=0)
    timeout_seconds: int = Field(ge=1)
    events_observed: int = Field(ge=0)
    web_searches: int = Field(ge=0)
    last_event_elapsed_seconds: int | None = Field(default=None, ge=0)
    cli_version: str = Field(max_length=120)
    argument_profile: str = Field(max_length=100)


class ResearchEventTracker:
    """Retain event counters only, never queries, messages, URLs or tool arguments."""

    def __init__(self) -> None:
        self.offset = 0
        self.pending = b""
        self.phase = "STARTING"
        self.events = 0
        self.search_ids: set[str] = set()
        self.last_event: int | None = None

    def read(self, path: Path, elapsed_seconds: int) -> None:
        with path.open("rb") as stream:
            stream.seek(self.offset)
            chunk = stream.read()
            self.offset = stream.tell()
        lines = (self.pending + chunk).split(b"\n")
        self.pending = lines.pop()
        for line in lines:
            try:
                event = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get("type")
            if kind not in {
                "thread.started",
                "turn.started",
                "turn.completed",
                "turn.failed",
                "item.started",
                "item.updated",
                "item.completed",
                "error",
            }:
                continue
            self.events += 1
            self.last_event = elapsed_seconds
            if kind == "turn.started":
                self.phase = "RESEARCHING"
            elif kind == "turn.completed":
                self.phase = "RESPONSE_READY"
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "web_search":
                if isinstance(item.get("id"), str):
                    self.search_ids.add(item["id"])
                self.phase = "WEB_SEARCH"

    def snapshot(
        self, *, elapsed: int, timeout: int, version: str, profile: str
    ) -> ResearchProgress:
        return ResearchProgress(
            phase=self.phase,
            elapsed_seconds=elapsed,
            timeout_seconds=timeout,
            events_observed=self.events,
            web_searches=len(self.search_ids),
            last_event_elapsed_seconds=self.last_event,
            cli_version=version,
            argument_profile=profile,
        )
