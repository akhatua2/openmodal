# OpenModal

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
- GKE with spot GPUs (H100, A100, L4)
- Local Docker provider — no cloud account needed
- CLI: `openmodal run`, `deploy`, `stop`, `ps`

## Get started

```bash
pip install openmodal

# Local (just needs Docker)
openmodal --local run examples/hello_world.py

# GCP
gcloud auth login
openmodal run examples/hello_world.py
```

[Setup guide](docs/setup.md) · [Examples](docs/examples/) · [Modal docs](https://modal.com/docs/guide) (same API, just swap the import)

## License

Apache-2.0
