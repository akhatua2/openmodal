# GPU serving with vLLM

Deploy a model on a GPU and get an OpenAI-compatible endpoint. Scales to zero when idle.

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

```
openmodal deploy: vllm-test
  building image...
  image: us-central1-docker.pkg.dev/.../vllm-test:a9b8fa41ec13
  creating container (H100)...
  waiting for healthy (timeout: 1200s)...
  serve => http://104.155.171.209:8000
deploy complete.
```

## Query

```bash
curl http://104.155.171.209:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"Qwen/Qwen3.5-0.8B","messages":[{"role":"user","content":"What is 2+2?"}],"max_tokens":16}'
```

Works with any OpenAI client:

```python
from openai import OpenAI
client = OpenAI(base_url="http://104.155.171.209:8000/v1", api_key="unused")
resp = client.chat.completions.create(
    model="Qwen/Qwen3.5-0.8B",
    messages=[{"role": "user", "content": "What is 2+2?"}],
)
print(resp.choices[0].message.content)
```

## Stop

```bash
openmodal stop vllm-test
```

## Under the hood

When you run `openmodal deploy`, here's what happens:

**Building the image**

Your image definition (`debian_slim().pip_install(...)`) gets turned into a Dockerfile and built via Google Cloud Build. The built image is stored in Artifact Registry. If you deploy the same code again, the image is already cached and this step is skipped.

**Starting the server**

OpenModal sees `gpu="H100"` + `@web_server` and picks GKE (Kubernetes) as the backend. It creates three things:

- A **Deployment** — tells Kubernetes "run one copy of this container with an H100 GPU"
- A **Service** — gives it a public IP so you can send requests to it
- A **CronJob** — checks every minute if anyone is using the server

GKE doesn't have an H100 machine sitting around, so it provisions one (a spot instance, ~60% cheaper). This takes a few minutes. Once the machine is ready, your container starts, vLLM loads the model, and the health check passes.

**Scaling down**

The CronJob runs every minute and checks: are there any active TCP connections to port 8000? If there haven't been any for `scaledown_window` seconds (5 min in this example), it scales the Deployment to 0 — meaning the container is stopped.

Once the container is gone, the H100 machine has nothing running on it. GKE's node autoscaler notices this and removes the machine after ~5 minutes. Now you're paying $0 for GPUs.

**Costs**

| State | What you pay |
|---|---|
| Serving requests | ~$1.20/hr (H100 spot) |
| Idle, within scaledown window | Same |
| Scaled to zero | ~$0.10/hr (cluster overhead) |
| Cluster deleted | $0 |
