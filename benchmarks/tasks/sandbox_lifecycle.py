"""Benchmark: Full sandbox lifecycle — create, exec, terminate, leak check."""

from __future__ import annotations

import time

from benchmarks.tasks.base import BenchmarkTask, Measurement, measure


class SandboxLifecycleTask(BenchmarkTask):
    name = "sandbox_lifecycle"
    description = "Full create → exec → terminate cycle with resource leak detection"

    def setup(self, ctx: dict) -> None:
        mod = ctx["module"]
        if ctx["is_modal"]:
            ctx["app"] = mod.App.lookup("bench-sandbox-lifecycle", create_if_missing=True)
        else:
            ctx["app"] = mod.App("bench-sandbox-lifecycle")
        ctx["image"] = mod.Image.debian_slim()

    def run(self, ctx: dict, iteration: int) -> list[Measurement]:
        mod = ctx["module"]
        measurements = []

        # Full lifecycle
        m_create, sandbox = measure(
            "lifecycle: create",
            lambda: mod.Sandbox.create(image=ctx["image"], app=ctx["app"], timeout=300),
        )
        measurements.append(m_create)

        if not sandbox:
            return measurements

        m_exec, _ = measure(
            "lifecycle: exec",
            lambda: sandbox.exec("echo", "hello"),
        )
        measurements.append(m_exec)

        m_term, _ = measure(
            "lifecycle: terminate",
            lambda: sandbox.terminate(),
        )
        measurements.append(m_term)

        # Total lifecycle time
        total = m_create.seconds + m_exec.seconds + m_term.seconds
        measurements.append(Measurement("lifecycle: total", total))

        return measurements

    def teardown(self, ctx: dict) -> None:
        # Leak detection — check for leftover resources
        if ctx.get("is_openmodal"):
            time.sleep(3)
            from openmodal.providers import get_provider
            provider = get_provider()
            instances = provider.list_instances()
            leaked = [i for i in instances if "bench-sandbox" in i.get("name", "")]
            if leaked:
                print(f"\n  ⚠ LEAK DETECTED: {len(leaked)} containers not cleaned up:")
                for i in leaked:
                    print(f"    - {i['name']} ({i.get('status', '')})")
            else:
                print("\n  ✓ No resource leaks detected")
