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

OpenModal builds the image, provisions a spot GPU, starts vLLM, and gives you an endpoint:

```
openmodal deploy: vllm-test
  building image...
  creating container (H100)...
  waiting for healthy...
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

## How scale-to-zero works

A background job checks every minute: are there active connections? If nobody has connected for `scaledown_window` seconds, the container is stopped and the GPU node is released. You pay nothing when scaled to zero.

| State | Cost |
|---|---|
| Serving requests | ~$1.20/hr (H100 spot) |
| Idle, within scaledown window | Same |
| Scaled to zero | ~$0.10/hr (cluster overhead) |
| Cluster deleted | $0 |
