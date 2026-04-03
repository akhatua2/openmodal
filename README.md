# OpenModal

[![PyPI](https://img.shields.io/pypi/v/openmodal)](https://pypi.org/project/openmodal/)

A cloud-agnostic runtime that implements [Modal](https://modal.com)'s Python interface.

I built this because I wanted to run Modal on my own GCP account. Modal's API is clean and I didn't want to learn a different one. So OpenModal lets you write the same code and run it on your own infrastructure.

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
- GCP with spot GPUs (H100, A100, L4)
- AWS with EKS, Karpenter, KEDA
- Azure with AKS, ACR, KEDA
- Local Docker provider — no cloud account needed
- CLI: `openmodal run`, `deploy`, `stop`, `ps`, `logs`

## Get started

```bash
pip install openmodal

# Interactive setup — checks prerequisites, configures your provider
openmodal setup

# Or just run directly
openmodal --local run examples/hello_world.py   # Local (just needs Docker)
openmodal run examples/hello_world.py           # GCP (default)
openmodal --aws run examples/hello_world.py     # AWS
openmodal --azure run examples/hello_world.py   # Azure
```

[Setup guide](docs/setup.md) · [Examples](docs/examples/) · [Modal docs](https://modal.com/docs/guide) (same API, just swap the import)

## License

Apache-2.0
