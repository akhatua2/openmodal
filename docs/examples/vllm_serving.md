# GPU serving with vLLM

Deploy a model on a GPU and get an OpenAI-compatible endpoint. Scales to zero when idle, scales back up on next deploy.

## The code

```python
import openmodal

MODEL_NAME = "Qwen/Qwen3.5-0.8B"

vllm_image = (
    openmodal.Image.from_registry("nvidia/cuda:12.8.0-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .apt_install("git")
    .uv_pip_install("vllm", "huggingface-hub==0.36.0",
                    extra_options="--extra-index-url https://wheels.vllm.ai/nightly")
    .pip_install("transformers @ git+https://github.com/huggingface/transformers.git@main")
)

app = openmodal.App("vllm-test")

@app.function(
    image=vllm_image,
    gpu="H100",
    scaledown_window=5 * 60,
    timeout=10 * 60,
)
@openmodal.web_server(port=8000, startup_timeout=20 * 60)
@openmodal.concurrent(max_inputs=8)
def serve():
    import subprocess
    subprocess.Popen([
        "vllm", "serve", MODEL_NAME,
        "--host", "0.0.0.0", "--port", "8000",
        "--served-model-name", MODEL_NAME,
        "--max-model-len", "4096",
        "--enforce-eager",
    ])
```

## Deploy

```bash
openmodal deploy examples/vllm_serving.py
```

First deploy builds the Docker image (~10 min), provisions an H100 spot GPU node, starts vLLM, and returns an endpoint:

```
openmodal deploy: vllm-test
  building image...
  image: us-central1-docker.pkg.dev/.../vllm-test:a9b8fa41ec13
  creating container (H100)...
  waiting for healthy (timeout: 1200s)...
  serve => http://104.155.171.209:8000
deploy complete.
```

Subsequent deploys skip the image build (cached) and reuse the endpoint.

## Query

```bash
curl http://104.155.171.209:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"Qwen/Qwen3.5-0.8B","messages":[{"role":"user","content":"What is 2+2?"}],"max_tokens":16}'
```

Works with any OpenAI-compatible client:

```python
from openai import OpenAI
client = OpenAI(base_url="http://104.155.171.209:8000/v1", api_key="unused")
resp = client.chat.completions.create(
    model="Qwen/Qwen3.5-0.8B",
    messages=[{"role": "user", "content": "What is 2+2?"}],
)
print(resp.choices[0].message.content)
```

## Scale-to-zero

After `scaledown_window` (5 min in this example) of no traffic:

1. Idle monitor detects no active connections
2. Deployment scales to 0 replicas — pod terminated
3. GKE node autoscaler removes the H100 GPU node (~5 min)
4. GPU cost drops to $0

Total time from last request to $0: `scaledown_window` + ~5 min node drain.

## Stop manually

```bash
openmodal stop vllm-test
```

## How it works

| Feature | Implementation |
|---|---|
| `gpu="H100"` | GKE spot GPU node pool, scales 0→1 on demand |
| `@web_server(port=8000)` | Kubernetes Deployment + LoadBalancer Service |
| `scaledown_window=300` | CronJob checks connections every minute |
| `@concurrent(max_inputs=8)` | vLLM handles concurrency natively |
| Image caching | Cloud Build + Artifact Registry, hash-based |
