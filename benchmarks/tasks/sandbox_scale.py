"""Benchmark: Parallel sandbox creation at different scales."""

from __future__ import annotations

import concurrent.futures

from benchmarks.tasks.base import BenchmarkTask, Measurement, measure


class SandboxScaleTask(BenchmarkTask):
    name = "sandbox_scale"
    description = "Measures parallel sandbox creation at 2x, 4x, 8x concurrency"

    def setup(self, ctx: dict) -> None:
        mod = ctx["module"]
        if ctx["is_modal"]:
            ctx["app"] = mod.App.lookup("bench-sandbox-scale", create_if_missing=True)
        else:
            ctx["app"] = mod.App("bench-sandbox-scale")
        ctx["image"] = mod.Image.debian_slim()

    def run(self, ctx: dict, iteration: int) -> list[Measurement]:
        mod = ctx["module"]
        measurements = []
        counts = [2, 4, 8]

        for n in counts:
            def _create_n(count=n):
                sandboxes = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
                    futures = [
                        pool.submit(
                            mod.Sandbox.create,
                            image=ctx["image"], app=ctx["app"], timeout=300,
                        )
                        for _ in range(count)
                    ]
                    for f in concurrent.futures.as_completed(futures):
                        try:
                            sandboxes.append(f.result())
                        except Exception:
                            pass
                return sandboxes

            m, sandboxes = measure(f"create {n}x parallel", _create_n)
            measurements.append(m)

            # Calculate per-sandbox time
            if sandboxes and m.success:
                m.metadata["per_sandbox"] = round(m.seconds / len(sandboxes), 2)
                m.metadata["created"] = len(sandboxes)

            # Cleanup
            if sandboxes:
                for s in sandboxes:
                    try:
                        s.terminate()
                    except Exception:
                        pass

        return measurements
