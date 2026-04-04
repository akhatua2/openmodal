"""Base class for benchmark tasks."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Measurement:
    name: str
    seconds: float
    success: bool = True
    error: str = ""
    metadata: dict = field(default_factory=dict)


class BenchmarkTask:
    """Base class for all benchmark tasks.

    Subclasses implement:
      - name: human-readable task name
      - description: what this task measures
      - setup(): one-time setup before iterations
      - run(iteration): the actual benchmark code
      - teardown(): cleanup after all iterations
    """

    name: str = ""
    description: str = ""

    def setup(self, ctx: dict) -> None:
        """Called once before any iterations."""

    def run(self, ctx: dict, iteration: int) -> list[Measurement]:
        """Run one iteration. Return list of measurements."""
        raise NotImplementedError

    def teardown(self, ctx: dict) -> None:
        """Called once after all iterations."""


def measure(name: str, fn, **metadata):
    """Time a function call and return a Measurement."""
    start = time.time()
    try:
        result = fn()
        elapsed = time.time() - start
        return Measurement(name, elapsed, metadata=metadata), result
    except Exception as e:
        elapsed = time.time() - start
        return Measurement(name, elapsed, success=False, error=str(e), metadata=metadata), None
