"""Benchmark: Image build and pull times for different image sizes.

Iteration 0 uses unique image labels to force a cold build.
Iteration 1+ reuses the same images to measure cached performance.
"""

from __future__ import annotations

import uuid

from benchmarks.tasks.base import BenchmarkTask, Measurement, measure


class SandboxImageTask(BenchmarkTask):
    name = "sandbox_image"
    description = "Measures sandbox creation with cold (uncached) and warm (cached) images"

    def setup(self, ctx: dict) -> None:
        mod = ctx["module"]
        if ctx["is_modal"]:
            ctx["app"] = mod.App.lookup("bench-sandbox-image", create_if_missing=True)
        else:
            ctx["app"] = mod.App("bench-sandbox-image")

        # Unique tag to bust cache on cold start
        tag = uuid.uuid4().hex[:8]

        ctx["cold_images"] = {
            "minimal": mod.Image.debian_slim().run_commands(f"echo {tag}"),
            "medium": (
                mod.Image.debian_slim()
                .apt_install("git", "curl", "wget")
                .run_commands(f"echo {tag}")
            ),
            "heavy": (
                mod.Image.debian_slim()
                .apt_install("git", "curl", "wget", "build-essential")
                .pip_install("requests", "numpy")
                .run_commands(f"echo {tag}")
            ),
        }

        # Stable images for warm/cached runs
        ctx["warm_images"] = {
            "minimal": mod.Image.debian_slim(),
            "medium": mod.Image.debian_slim().apt_install("git", "curl", "wget"),
            "heavy": (
                mod.Image.debian_slim()
                .apt_install("git", "curl", "wget", "build-essential")
                .pip_install("requests", "numpy")
            ),
        }

    def run(self, ctx: dict, iteration: int) -> list[Measurement]:
        mod = ctx["module"]
        measurements = []

        if iteration == 0:
            images = ctx["cold_images"]
            temp = "cold"
        else:
            images = ctx["warm_images"]
            temp = "cached"

        for label, image in images.items():
            m, sandbox = measure(
                f"create ({label}, {temp})",
                lambda img=image: mod.Sandbox.create(
                    image=img, app=ctx["app"], timeout=300,
                ),
            )
            measurements.append(m)

            if sandbox:
                try:
                    sandbox.terminate()
                except Exception:
                    pass

        return measurements
