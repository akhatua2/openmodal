"""Metrics collector — polls container for GPU, CPU, memory via exec_in_pod."""

from __future__ import annotations

import logging
import threading
import time

from openmodal.monitor.history import MetricsHistory, MetricsSnapshot
from openmodal.providers.base import CloudProvider

logger = logging.getLogger("openmodal.monitor")


class MetricsCollector:
    def __init__(
        self,
        provider: CloudProvider,
        pod_name: str,
        history: MetricsHistory,
        interval: float = 2.0,
    ):
        self._provider = provider
        self._pod_name = pod_name
        self._history = history
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._has_gpu: bool | None = None
        self._gpu_detect_attempts = 0
        self._prev_cpu_idle: int | None = None
        self._prev_cpu_total: int | None = None

    @property
    def has_gpu(self) -> bool:
        # True if confirmed GPU, also True if unknown (not yet determined)
        return self._has_gpu is not False

    @property
    def stopped(self) -> bool:
        return self._stop_event.is_set()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._history.save(self._pod_name)

    def _poll_loop(self) -> None:
        consecutive_failures = 0
        while not self._stop_event.is_set():
            try:
                snapshot = self._collect()
                self._history.add(snapshot)
                consecutive_failures = 0
            except Exception:
                consecutive_failures += 1
                logger.debug("Metrics poll failed (%d)", consecutive_failures, exc_info=True)
                # Pod might be initializing or terminated — keep retrying
                # but give up after 30 consecutive failures (~1 min)
                if consecutive_failures > 30:
                    break
            self._stop_event.wait(self._interval)

    def _collect(self) -> MetricsSnapshot:
        gpu_util, vram_used, vram_total = self._collect_gpu()
        cpu = self._collect_cpu()
        mem_used, mem_total = self._collect_memory()
        return MetricsSnapshot(
            timestamp=time.time(),
            gpu_util=gpu_util,
            vram_used_gb=vram_used,
            vram_total_gb=vram_total,
            cpu_percent=cpu,
            mem_used_gb=mem_used,
            mem_total_gb=mem_total,
        )

    def _collect_gpu(self) -> tuple[float | None, float | None, float | None]:
        if self._has_gpu is False:
            return None, None, None
        try:
            proc = self._provider.exec_in_pod(
                self._pod_name,
                "bash", "-c",
                "PATH=$PATH:/usr/local/nvidia/bin "
                "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total "
                "--format=csv,noheader,nounits",
            )
            if proc.wait() != 0:
                # Retry a few times — nvidia-smi may not be ready yet
                self._gpu_detect_attempts += 1
                if self._gpu_detect_attempts > 10:
                    self._has_gpu = False
                return None, None, None
            self._has_gpu = True
            line = proc.stdout.read().strip().split("\n")[0]
            parts = [p.strip() for p in line.split(",")]
            return float(parts[0]), float(parts[1]) / 1024, float(parts[2]) / 1024
        except Exception:
            self._gpu_detect_attempts += 1
            if self._gpu_detect_attempts > 10:
                self._has_gpu = False
            return None, None, None

    def _collect_cpu(self) -> float:
        try:
            proc = self._provider.exec_in_pod(
                self._pod_name, "bash", "-c", "head -1 /proc/stat",
            )
            parts = proc.stdout.read().split()
            values = [int(x) for x in parts[1:]]
            idle = values[3]
            total = sum(values)

            if self._prev_cpu_total is not None and self._prev_cpu_idle is not None:
                d_total = total - self._prev_cpu_total
                d_idle = idle - self._prev_cpu_idle
                cpu = ((d_total - d_idle) / d_total) * 100 if d_total > 0 else 0.0
            else:
                cpu = 0.0

            self._prev_cpu_idle = idle
            self._prev_cpu_total = total
            return cpu
        except Exception:
            return 0.0

    def _collect_memory(self) -> tuple[float, float]:
        try:
            proc = self._provider.exec_in_pod(
                self._pod_name, "bash", "-c", "head -3 /proc/meminfo",
            )
            lines = proc.stdout.read().strip().split("\n")
            mem_total_kb = int(lines[0].split()[1])
            mem_available_kb = int(lines[2].split()[1])
            return (
                (mem_total_kb - mem_available_kb) / (1024 * 1024),
                mem_total_kb / (1024 * 1024),
            )
        except Exception:
            return 0.0, 0.0
