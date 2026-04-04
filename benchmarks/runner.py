"""Benchmark runner — discovers tasks, runs them, generates reports.

Usage:
    # Run all benchmarks against OpenModal
    python -m benchmarks.runner

    # Run against Modal for comparison
    python -m benchmarks.runner --modal

    # Run specific tasks
    python -m benchmarks.runner --tasks sandbox_create sandbox_exec

    # More iterations
    python -m benchmarks.runner --iterations 5

    # Local provider
    python -m benchmarks.runner --provider local
"""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.tasks.base import Measurement
from benchmarks.tasks.sandbox_create import SandboxCreateTask
from benchmarks.tasks.sandbox_exec import SandboxExecTask
from benchmarks.tasks.sandbox_image import SandboxImageTask
from benchmarks.tasks.sandbox_lifecycle import SandboxLifecycleTask
from benchmarks.tasks.sandbox_scale import SandboxScaleTask

ALL_TASKS = [
    SandboxCreateTask(),
    SandboxExecTask(),
    SandboxLifecycleTask(),
    SandboxImageTask(),
    SandboxScaleTask(),
]

TASK_MAP = {t.name: t for t in ALL_TASKS}


@dataclass
class BenchmarkReport:
    provider: str
    timestamp: str
    iterations: int
    version: str
    measurements: list[dict] = field(default_factory=list)

    def save(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(asdict(self), indent=2))
        print(f"\n  Results saved to {path}")


def _get_version(is_modal: bool) -> str:
    if is_modal:
        try:
            import modal
            return getattr(modal, "__version__", "unknown")
        except ImportError:
            return "not installed"
    try:
        import openmodal
        return getattr(openmodal, "__version__", "unknown")
    except ImportError:
        return "not installed"


def _print_summary(measurements: list[Measurement], provider: str):
    print(f"\n{'═' * 70}")
    print(f"  {provider} Benchmark Results")
    print(f"{'═' * 70}")

    # Group by name
    groups: dict[str, list[float]] = {}
    for m in measurements:
        if m.success:
            groups.setdefault(m.name, []).append(m.seconds)

    print(f"\n  {'Operation':<40} {'Min':>7} {'Avg':>7} {'Max':>7} {'N':>3}")
    print(f"  {'─' * 64}")

    for name, vals in groups.items():
        avg = statistics.mean(vals)
        if len(vals) > 1:
            print(f"  {name:<40} {min(vals):>6.2f}s {avg:>6.2f}s {max(vals):>6.2f}s {len(vals):>3}")
        else:
            print(f"  {name:<40} {vals[0]:>6.2f}s {'':>7} {'':>7} {len(vals):>3}")

    # Failures
    failures = [m for m in measurements if not m.success]
    if failures:
        print(f"\n  Failures ({len(failures)}):")
        for m in failures:
            print(f"    ✗ {m.name}: {m.error}")

    print(f"\n{'═' * 70}\n")


def run(
    is_modal: bool,
    provider: str,
    iterations: int,
    task_names: list[str] | None,
):
    # Resolve module
    if is_modal:
        import modal as mod
        provider_label = "Modal"
    else:
        import openmodal as mod
        provider_label = f"OpenModal ({provider})"

    # Select tasks
    if task_names:
        tasks = [TASK_MAP[n] for n in task_names if n in TASK_MAP]
    else:
        tasks = ALL_TASKS

    ctx = {
        "module": mod,
        "provider": provider,
        "is_modal": is_modal,
        "is_openmodal": not is_modal,
    }

    all_measurements: list[Measurement] = []

    print(f"\n  Running {len(tasks)} benchmark tasks ({iterations} iterations each)")
    print(f"  Provider: {provider_label}")
    print(f"  Version: {_get_version(is_modal)}")

    for task in tasks:
        print(f"\n{'─' * 70}")
        print(f"  Task: {task.name}")
        print(f"  {task.description}")
        print(f"{'─' * 70}")

        try:
            task.setup(ctx)
        except Exception as e:
            print(f"  ✗ Setup failed: {e}")
            continue

        for i in range(iterations):
            label = "cold" if i == 0 else f"warm #{i}"
            print(f"\n  ── Iteration {i + 1}/{iterations} ({label}) ──\n")

            try:
                measurements = task.run(ctx, i)
                for m in measurements:
                    status = "✓" if m.success else "✗"
                    extra = f" ({m.error})" if m.error else ""
                    print(f"  {status} {m.name}: {m.seconds:.2f}s{extra}")
                all_measurements.extend(measurements)
            except Exception as e:
                print(f"  ✗ Iteration failed: {e}")
                all_measurements.append(
                    Measurement(f"{task.name} (iteration {i})", 0, success=False, error=str(e))
                )

        try:
            task.teardown(ctx)
        except Exception as e:
            print(f"  ✗ Teardown failed: {e}")

    _print_summary(all_measurements, provider_label)

    report = BenchmarkReport(
        provider=provider_label,
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
        iterations=iterations,
        version=_get_version(is_modal),
        measurements=[asdict(m) for m in all_measurements],
    )

    return report


def main():
    parser = argparse.ArgumentParser(description="OpenModal Benchmark Runner")
    parser.add_argument("--modal", action="store_true", help="Benchmark Modal")
    parser.add_argument("--provider", default="gcp",
                        help="OpenModal provider (gcp, local, aws, azure)")
    parser.add_argument("--iterations", type=int, default=3,
                        help="Iterations per task (default: 3)")
    parser.add_argument("--tasks", nargs="+", default=None,
                        help=f"Tasks to run (default: all). Available: {list(TASK_MAP.keys())}")
    parser.add_argument("--output", default=None, help="Output JSON path")
    args = parser.parse_args()

    if not args.modal and args.provider != "gcp":
        import os
        os.environ["OPENMODAL_PROVIDER"] = args.provider

    report = run(args.modal, args.provider, args.iterations, args.tasks)

    if args.modal:
        provider_slug = "modal"
    else:
        provider_slug = args.provider
    ts = report.timestamp[:19].replace(":", "-")
    output = args.output or f"benchmarks/results/{provider_slug}/{ts}.json"
    report.save(output)


if __name__ == "__main__":
    main()
