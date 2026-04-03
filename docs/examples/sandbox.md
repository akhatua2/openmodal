# Sandboxes

Sandboxes are isolated containers you can exec commands into — like SSH into a fresh machine. They're used by SWE agents to run code, edit files, and run tests in a clean environment.

## Basic usage

```python
import openmodal

app = openmodal.App("my-agent")
image = openmodal.Image.debian_slim().apt_install("git").pip_install("requests")

sandbox = openmodal.Sandbox.create(image=image, app=app, timeout=300)

result = sandbox.exec("echo hello")
print(result.output)      # "hello"
print(result.returncode)  # 0

sandbox.exec("git clone https://github.com/pallets/click.git /workspace")
sandbox.exec("cd /workspace && python3 -m pytest tests/")

sandbox.terminate()
```

## How it works

Each sandbox is a Kubernetes pod on GKE:

1. `Sandbox.create()` → creates a pod with your image, keeps it alive with `sleep`
2. `sandbox.exec(command)` → runs bash commands inside the pod via Kubernetes exec API
3. Files persist between execs — the pod stays alive until you terminate it
4. `sandbox.terminate()` → deletes the pod

## Parallel sandboxes

Multiple sandboxes run simultaneously on the same cluster. Each is fully isolated.

```python
import concurrent.futures

def run_agent(agent_id):
    sandbox = openmodal.Sandbox.create(image=image, app=app)
    sandbox.exec(f"echo 'agent {agent_id}' > /tmp/id.txt")
    result = sandbox.exec("cat /tmp/id.txt")
    sandbox.terminate()
    return result.output

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(run_agent, range(4)))
```

## Performance

With cached images on warm nodes:

| Operation | Latency |
|---|---|
| `Sandbox.create()` | ~5s |
| `sandbox.exec()` | ~0.2s |
| `sandbox.terminate()` | instant |
| 4 parallel sandboxes | ~5s (not 4x5s) |

First run builds the image (~2-3 min via Cloud Build). After that, the image is cached and creation is fast.

## Isolation

Each sandbox is its own pod:
- Separate filesystem — files in one sandbox don't appear in another
- Separate processes — nothing shared between sandboxes
- Separate network — each pod gets its own IP

## Run the example

```bash
openmodal run examples/sandbox.py
```

```
Launching 4 sandboxes in parallel...

Agent 0 (sandbox-test-4bb1bb27): create=5.3s total=11.3s
Agent 1 (sandbox-test-6f4a83f3): create=5.3s total=11.5s
Agent 2 (sandbox-test-c5696129): create=5.2s total=11.7s
Agent 3 (sandbox-test-c8ecb817): create=4.2s total=10.4s

All 4 agents passed in 11.7s
```
