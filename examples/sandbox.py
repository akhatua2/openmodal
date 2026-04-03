"""Test parallel sandboxes — simulates multiple SWE agents working simultaneously."""

import time
import concurrent.futures
import openmodal

app = openmodal.App("sandbox-test")

sandbox_image = openmodal.Image.debian_slim().apt_install("git", "curl").pip_install("requests")


def run_agent(agent_id: int) -> dict:
    t0 = time.time()
    sandbox = openmodal.Sandbox.create(image=sandbox_image, app=app, timeout=300)
    create_time = time.time() - t0

    results = []

    t1 = time.time()
    proc = sandbox.exec("bash", "-c", "echo 'Hello from sandbox'")
    stdout = proc.stdout.read()
    results.append(f"  [{agent_id}] echo: {stdout} ({time.time()-t1:.2f}s)")
    assert "Hello from sandbox" in stdout

    proc = sandbox.exec("bash", "-c", "python3 --version")
    stdout = proc.stdout.read()
    results.append(f"  [{agent_id}] python: {stdout}")
    assert "Python 3" in stdout

    proc = sandbox.exec("bash", "-c", "git --version")
    results.append(f"  [{agent_id}] git: {proc.stdout.read()}")

    proc = sandbox.exec("bash", "-c", "python3 -c 'import requests; print(requests.__version__)'")
    results.append(f"  [{agent_id}] requests: {proc.stdout.read()}")

    sandbox.exec("bash", "-c", f"echo 'agent-{agent_id}-data' > /tmp/test.txt")
    proc = sandbox.exec("bash", "-c", "cat /tmp/test.txt")
    stdout = proc.stdout.read()
    assert f"agent-{agent_id}-data" in stdout
    results.append(f"  [{agent_id}] persistence: ok")

    t1 = time.time()
    sandbox.exec("bash", "-c", "cd /tmp && git clone https://github.com/pallets/click.git --depth 1 2>&1 | tail -3")
    proc = sandbox.exec("bash", "-c", "find /tmp/click -name '*.py' | wc -l")
    count = proc.stdout.read().strip()
    results.append(f"  [{agent_id}] git clone + find: {count} files ({time.time()-t1:.1f}s)")
    assert int(count) > 10

    proc = sandbox.exec("bash", "-c", "ls /nonexistent 2>&1")
    assert proc.wait() != 0
    results.append(f"  [{agent_id}] error handling: ok")

    t1 = time.time()
    proc = sandbox.exec("bash", "-c", "sleep 3 && echo 'done sleeping'")
    assert "done sleeping" in proc.stdout.read()
    results.append(f"  [{agent_id}] sleep 3: ({time.time()-t1:.1f}s)")

    sandbox.terminate()
    return {
        "agent": agent_id,
        "sandbox": sandbox.id,
        "create": create_time,
        "total": time.time() - t0,
        "log": "\n".join(results),
    }


@app.local_entrypoint()
def main():
    n = 4
    print(f"Launching {n} sandboxes in parallel...\n")

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(run_agent, range(n)))

    for r in results:
        print(f"Agent {r['agent']} ({r['sandbox']}): create={r['create']:.1f}s total={r['total']:.1f}s")
        print(r["log"])
        print()

    print(f"All {n} agents passed in {time.time() - t0:.1f}s")
