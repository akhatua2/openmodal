<p align="center">
  <img src="openmodal.png" alt="OpenModal" width="600">
</p>

An open-source runtime that implements [Modal](https://modal.com)'s Python interface. Write the same code, run it on your own infrastructure.

```python
import openmodal

app = openmodal.App("my-experiment")

@app.function(gpu="H100")
def train(config):
    ...

results = train.map(configs)
```

## What works

- `f.local()`, `f.remote()`, `f.map()`
- GPU serving with auto scale-to-zero (KEDA)
- Custom images, secrets, retries, volumes
- Sandboxes for SWE agents (parallel creation, exec, file transfer)
- Local Docker provider — no cloud account needed
- GCP provider with spot GPUs (H100, A100, L4)
- AWS provider with EKS, Karpenter, KEDA
- Azure provider with AKS, ACR, KEDA
- CLI: `openmodal run`, `deploy`, `stop`, `ps`, `logs`, `monitor`, `secret`, `setup`
- `openmodal monitor` — live GPU/CPU/memory dashboard
- `openmodal secret` — manage named secrets locally
- Benchmark suite for sandbox performance testing
- [CooperBench](examples/cooperbench.md) integration — one-line import swap (`import openmodal as modal`)
- [Harbor](examples/harbor.md) integration for SWE-bench evaluations

## Quick start

=== "Local (Docker)"

    ```bash
    pip install openmodal
    openmodal --local run examples/hello_world.py
    ```

    Just needs Docker installed. No cloud account, no setup.

=== "GCP"

    ```bash
    pip install openmodal
    openmodal setup gcp
    openmodal run examples/hello_world.py
    ```

    The setup wizard handles authentication, API enablement, and tool installation.

=== "AWS"

    ```bash
    pip install "openmodal[aws]"
    openmodal setup aws
    openmodal --aws run examples/hello_world.py
    ```

    Creates an EKS cluster on first run (~15 min one-time).

=== "Azure"

    ```bash
    pip install openmodal
    openmodal setup azure
    openmodal --azure run examples/hello_world.py
    ```

    Creates an AKS cluster on first run (~5 min one-time).

## How it compares to Modal

The only difference is the import line:

```diff
- import modal
+ import openmodal
```

For hundreds of additional examples, see the [Modal examples gallery](https://modal.com/docs/examples) — the same code works with OpenModal.

## License

Apache-2.0
