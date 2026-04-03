# Hello, world!

The basics: run functions locally, remotely, and in parallel.

## The code

```python
import sys
import openmodal

app = openmodal.App("example-hello-world")

@app.function()
def f(i):
    if i % 2 == 0:
        print("hello", i)
    else:
        print("world", i, file=sys.stderr)
    return i * i

@app.local_entrypoint()
def main():
    print(f.local(1000))     # runs on your machine
    print(f.remote(1000))    # runs in a container
    total = 0
    for ret in f.map(range(200)):  # 200 calls in parallel
        total += ret
    print(total)
```

## Run it

=== "Local (Docker)"

    ```bash
    openmodal --local run examples/hello_world.py
    ```

    ```
    ✓ Initialized.
    ✓ Created objects.
    ✓ Container created. (local CPU • localhost • 0s)
    ✓ Container ready. (2s total)
    hello 1000
    1000000
    1000000
    2646700
    ✓ Containers cleaned up.
    ✓ App completed.
    ```

=== "GCP"

    ```bash
    openmodal run examples/hello_world.py
    ```

    ```
    ✓ Initialized.
    ✓ Created objects.
    ✓ Container created. (2 vCPU, 2 GB RAM • 34.135.113.28 • 14s)
    ✓ Container ready. (60s total)
    hello 1000
    1000000
    1000000
    2646700
    ✓ Containers cleaned up.
    ✓ App completed.
    ```

## What happened?

1. `f.local(1000)` ran on your machine — returned `1000000`
2. `f.remote(1000)` ran inside a container (Docker or cloud VM) — same result
3. `f.map(range(200))` sent 200 calls to the container in parallel

The container was automatically cleaned up when the script finished.
