# Sandboxes

Sandboxes are isolated containers you can exec commands into — like SSH into a fresh machine. They're used by SWE agents to run code, edit files, and run tests in a clean environment.

## Basic usage

```python
import openmodal

app = openmodal.App("my-agent")
image = openmodal.Image.debian_slim().apt_install("git").pip_install("requests")

sandbox = openmodal.Sandbox.create(image=image, app=app, timeout=300)

proc = sandbox.exec("bash", "-c", "echo hello")
print(proc.stdout.read())   # "hello"
print(proc.returncode)      # 0

sandbox.exec("bash", "-c", "git clone https://github.com/pallets/click.git /workspace")
sandbox.exec("bash", "-c", "cd /workspace && python3 -m pytest tests/")

sandbox.terminate()
```

## How it works

1. `Sandbox.create()` creates a container with your image, keeps it alive with `sleep`
2. `sandbox.exec(...)` runs commands inside the container
3. Files persist between execs — the container stays alive until you terminate it
4. `sandbox.terminate()` deletes the container

On GCP this creates a Kubernetes pod. With `--local` it creates a Docker container. Your code is the same either way.

## Parallel sandboxes

Multiple sandboxes run simultaneously. Each is fully isolated.

```python
import concurrent.futures

def run_agent(agent_id):
    sandbox = openmodal.Sandbox.create(image=image, app=app)
    sandbox.exec("bash", "-c", f"echo 'agent {agent_id}' > /tmp/id.txt")
    proc = sandbox.exec("bash", "-c", "cat /tmp/id.txt")
    sandbox.terminate()
    return proc.stdout.read()

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(run_agent, range(4)))
```

## Performance

| Operation | Local Docker | GCP (warm) |
|---|---|---|
| `Sandbox.create()` | ~13s (first), ~1s (cached) | ~5s |
| `sandbox.exec()` | ~0.07s | ~0.2s |
| `sandbox.terminate()` | instant | instant |
| 4 parallel sandboxes | ~13s (first), ~1s (cached) | ~5s |

First run builds the image. After that, the image is cached and creation is fast.

## Run the example

=== "Local"

    ```bash
    openmodal --local run examples/sandbox.py
    ```

=== "GCP"

    ```bash
    openmodal run examples/sandbox.py
    ```

```
Launching 4 sandboxes in parallel...

Agent 0 (sandbox-test-758f3413): create=13.0s total=17.5s
Agent 1 (sandbox-test-645e1385): create=13.1s total=17.6s
Agent 2 (sandbox-test-92d7bfaa): create=13.0s total=17.6s
Agent 3 (sandbox-test-b82102c1): create=13.1s total=17.6s

All 4 agents passed in 17.6s
```
