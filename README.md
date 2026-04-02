# OpenModal

A cloud-agnostic runtime that implements [Modal](https://modal.com)'s Python interface. I built this because I wanted to run Modal on my own GCP account OpenModal lets you write the same code and run it on your own infrastructure.

```python
import openmodal  # swap this for modal and it works the same

app = openmodal.App("my-experiment")

@app.function(gpu="H100")
def train(config):
    ...

results = train.map(configs)
```

## What works

- `f.local()`, `f.remote()`, `f.map()`
- Custom images, secrets, retries, volumes
- `@web_server`, `@concurrent`
- Async functions
- CLI: `openmodal run`, `deploy`, `stop`, `ps`

GCP backend today. Provider abstraction for AWS/Azure is there, just needs implementing.

## Get started

```bash
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ openmodal
openmodal run examples/hello_world.py
```

[Setup guide](docs/setup.md) · [Examples](docs/examples/) · [Modal docs](https://modal.com/docs/guide) (same API, just swap the import)

## License

Apache-2.0
