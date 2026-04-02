# Hello, world!

This example demonstrates the core features of OpenModal:

- Run functions locally with `f.local()`
- Run functions remotely on GCP with `f.remote()`
- Run functions in parallel with `f.map()`

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
    # Run locally
    print(f.local(1000))

    # Run remotely on GCP
    print(f.remote(1000))

    # Run in parallel on GCP
    total = 0
    for ret in f.map(range(200)):
        total += ret
    print(total)
```

## Run it

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

1. `f.local(1000)` ran on your machine — printed `hello 1000`, returned `1000000`
2. `f.remote(1000)` created a GCE container, sent the function call to it, and returned the result
3. `f.map(range(200))` sent 200 calls to the remote container in parallel and streamed results back

The container was automatically cleaned up when the script finished.
