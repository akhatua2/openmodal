# OpenModal

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
- GPU serving with auto scale-to-zero
- Custom images, secrets, retries, volumes
- Sandboxes for SWE agents
- Local Docker provider — no cloud account needed
- GCP provider with spot GPUs (H100, A100, L4)
- AWS provider with EKS, Karpenter, KEDA
- Azure provider with AKS, ACR, KEDA
- CLI: `openmodal run`, `deploy`, `stop`, `ps`

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
    gcloud auth login
    openmodal run examples/hello_world.py
    ```

    See the [setup guide](setup.md) for GCP prerequisites.

=== "AWS"

    ```bash
    pip install "openmodal[aws]"
    aws login
    openmodal --aws run examples/hello_world.py
    ```

    Creates an EKS cluster on first run (~15 min one-time).

=== "Azure"

    ```bash
    pip install openmodal
    az login
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
