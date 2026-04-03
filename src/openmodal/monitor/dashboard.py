"""Dashboard renderer — sparkline-based resource display using rich."""

from __future__ import annotations

import shutil

from rich.text import Text

from openmodal.monitor.history import MetricsHistory

SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _sparkline(values: list[float], max_val: float, width: int) -> str:
    """Render a fixed-width sparkline. New data enters from the right."""
    if not values:
        return " " * width
    values = values[-width:]
    chars = []
    for v in values:
        ratio = min(v / max_val, 1.0) if max_val > 0 else 0
        idx = int(ratio * (len(SPARK_CHARS) - 1))
        chars.append(SPARK_CHARS[idx])
    spark = "".join(chars)
    return spark.rjust(width)


class Dashboard:
    def __init__(self, history: MetricsHistory, pod_name: str, has_gpu: bool = True):
        self._history = history
        self._pod_name = pod_name
        self.has_gpu = has_gpu

    def render(self) -> Text:
        cols, _ = shutil.get_terminal_size()
        snapshots = self._history.get_all()
        spark_width = max(cols - 30, 20)

        if not snapshots:
            return Text(f"\n  {self._pod_name} · waiting for metrics...\n")

        elapsed = snapshots[-1].timestamp - snapshots[0].timestamp
        mins, secs = divmod(int(elapsed), 60)
        time_str = f"{mins}m {secs}s" if mins else f"{secs}s"

        latest = snapshots[-1]
        lines = []

        # Header
        gpu_label = ""
        if self.has_gpu and latest.vram_total_gb:
            gpu_label = f" · {latest.vram_total_gb:.0f}GB GPU"
        lines.append(f"  {self._pod_name}{gpu_label} · {time_str}")
        lines.append("")

        if self.has_gpu:
            gpu_vals = [s.gpu_util or 0 for s in snapshots]
            gpu_pct = latest.gpu_util or 0
            lines.append(f"  GPU  {gpu_pct:3.0f}% {_sparkline(gpu_vals, 100, spark_width)}")

            vram_vals = [s.vram_used_gb or 0 for s in snapshots]
            vram_max = latest.vram_total_gb or 80
            vram_used = latest.vram_used_gb or 0
            lines.append(
                f"  VRAM {vram_used:3.0f}/{vram_max:.0f} GB "
                f"{_sparkline(vram_vals, vram_max, spark_width - 7)}"
            )

        cpu_vals = [s.cpu_percent for s in snapshots]
        cpu_pct = latest.cpu_percent
        lines.append(f"  CPU  {cpu_pct:3.0f}% {_sparkline(cpu_vals, 100, spark_width)}")

        mem_vals = [s.mem_used_gb for s in snapshots]
        mem_max = latest.mem_total_gb or 256
        mem_used = latest.mem_used_gb
        lines.append(
            f"  RAM  {mem_used:3.0f}/{mem_max:.0f} GB "
            f"{_sparkline(mem_vals, mem_max, spark_width - 7)}"
        )

        lines.append("")
        return Text("\n".join(lines))
