"""Benchmark: Sandbox creation (cold and warm starts)."""

from __future__ import annotations

from benchmarks.tasks.base import BenchmarkTask, Measurement, measure


class SandboxCreateTask(BenchmarkTask):
    name = "sandbox_create"
    description = "Measures sandbox creation time for cold and warm starts"

    def setup(self, ctx: dict) -> None:
        mod = ctx["module"]
        if ctx["is_modal"]:
            ctx["app"] = mod.App.lookup("bench-sandbox-create", create_if_missing=True)
        else:
            ctx["app"] = mod.App("bench-sandbox-create")
        ctx["image"] = mod.Image.debian_slim()
        ctx["sandboxes"] = []

    def run(self, ctx: dict, iteration: int) -> list[Measurement]:
        mod = ctx["module"]
        label = "cold" if iteration == 0 else "warm"

        m, sandbox = measure(
            f"sandbox.create ({label})",
            lambda: mod.Sandbox.create(image=ctx["image"], app=ctx["app"], timeout=300),
        )

        if sandbox:
            ctx["sandboxes"].append(sandbox)

        return [m]

    def teardown(self, ctx: dict) -> None:
        for s in ctx.get("sandboxes", []):
            try:
                s.terminate()
            except Exception:
                pass
