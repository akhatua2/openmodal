"""Benchmark: Sandbox exec latency for various operations."""

from __future__ import annotations

from benchmarks.tasks.base import BenchmarkTask, Measurement, measure


class SandboxExecTask(BenchmarkTask):
    name = "sandbox_exec"
    description = "Measures exec latency for echo, bash, python, file I/O, network"

    def setup(self, ctx: dict) -> None:
        mod = ctx["module"]
        if ctx["is_modal"]:
            ctx["app"] = mod.App.lookup("bench-sandbox-exec", create_if_missing=True)
        else:
            ctx["app"] = mod.App("bench-sandbox-exec")
        ctx["image"] = mod.Image.debian_slim().apt_install("curl")
        ctx["sandbox"] = mod.Sandbox.create(
            image=ctx["image"], app=ctx["app"], timeout=300,
        )

    def run(self, ctx: dict, iteration: int) -> list[Measurement]:
        sandbox = ctx["sandbox"]
        measurements = []

        # Minimal round-trip
        m, _ = measure("exec (echo)", lambda: sandbox.exec("echo", "hello"))
        measurements.append(m)

        # Bash shell
        m, _ = measure("exec (bash)", lambda: sandbox.exec("bash", "-c", "echo hello"))
        measurements.append(m)

        # Stdout capture
        def _capture():
            proc = sandbox.exec("bash", "-c", "uname -a")
            return proc.stdout.read()
        m, _ = measure("exec + stdout", _capture)
        measurements.append(m)

        # Python interpreter
        m, _ = measure(
            "exec (python3)",
            lambda: sandbox.exec("python3", "-c", "print(sum(range(1000)))"),
        )
        measurements.append(m)

        # File write + read
        def _file_io():
            sandbox.exec("bash", "-c", "echo 'data' > /tmp/bench.txt")
            proc = sandbox.exec("bash", "-c", "cat /tmp/bench.txt")
            return proc.stdout.read()
        m, _ = measure("file write + read", _file_io)
        measurements.append(m)

        # Network
        m, _ = measure(
            "exec (curl)",
            lambda: sandbox.exec(
                "bash", "-c",
                "curl -s -o /dev/null -w '%{http_code}' http://example.com",
            ),
        )
        measurements.append(m)

        # Sequential overhead
        def _sequential():
            for i in range(10):
                sandbox.exec("echo", str(i))
        m, _ = measure("10x sequential exec", _sequential)
        measurements.append(m)

        # Large output
        def _large_output():
            proc = sandbox.exec("bash", "-c", "seq 10000")
            return proc.stdout.read()
        m, _ = measure("exec (large stdout)", _large_output)
        measurements.append(m)

        return measurements

    def teardown(self, ctx: dict) -> None:
        try:
            ctx["sandbox"].terminate()
        except Exception:
            pass
