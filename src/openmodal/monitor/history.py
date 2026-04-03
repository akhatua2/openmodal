"""Metrics storage — circular buffer with JSON persistence."""

from __future__ import annotations

import collections
import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

METRICS_DIR = Path.home() / ".openmodal" / "metrics"


@dataclass
class MetricsSnapshot:
    timestamp: float
    gpu_util: float | None = None
    vram_used_gb: float | None = None
    vram_total_gb: float | None = None
    cpu_percent: float = 0.0
    mem_used_gb: float = 0.0
    mem_total_gb: float = 0.0


class MetricsHistory:
    def __init__(self, max_points: int = 900):
        self._buffer: collections.deque[MetricsSnapshot] = collections.deque(maxlen=max_points)
        self._lock = threading.Lock()

    def add(self, snapshot: MetricsSnapshot) -> None:
        with self._lock:
            self._buffer.append(snapshot)

    def get_all(self) -> list[MetricsSnapshot]:
        with self._lock:
            return list(self._buffer)

    def save(self, pod_name: str) -> None:
        METRICS_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            data = [asdict(s) for s in self._buffer]
        (METRICS_DIR / f"{pod_name}.json").write_text(json.dumps(data))

    @classmethod
    def load(cls, pod_name: str) -> MetricsHistory | None:
        path = METRICS_DIR / f"{pod_name}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        history = cls(max_points=max(len(data), 900))
        for d in data:
            history._buffer.append(MetricsSnapshot(**d))
        return history

    @classmethod
    def now(cls) -> float:
        return time.time()
