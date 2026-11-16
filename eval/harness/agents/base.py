from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

TRACE_SCHEMA = 1


@dataclass
class RunContext:
    out: Path
    result_chars: int


class AgentUnderTest(Protocol):
    name: str
    modes: set[str]

    def version(self) -> str: ...

    def setup(self, config: dict, ctx: RunContext) -> None: ...

    def run(self, task: dict) -> dict: ...
