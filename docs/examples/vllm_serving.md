# vLLM GPU serving

This example deploys a Qwen3.5-35B-A3B model on a GCP H100 GPU
using vLLM, with an OpenAI-compatible API endpoint.

## The code

```python
import openmodal

MODEL_NAME = "Qwen/Qwen3.5-35B-A3B-GPTQ-Int4"
VLLM_PORT = 8000

vllm_image = (
    openmodal.Image.from_registry(
        "nvidia/cuda:12.8.0-devel-ubuntu22.04", add_python="3.12"
    )
    .entrypoint([])
    .apt_install("git")
    .uv_pip_install(
        "vllm",
        "huggingface-hub==0.36.0",
        extra_options="--extra-index-url https://wheels.vllm.ai/nightly",
    )
    .pip_install(
        "transformers @ git+https://github.com/huggingface/transformers.git@main"
    )
    .env({"HF_XET_HIGH_PERFORMANCE": "1"})
)

hf_cache_vol = openmodal.Volume.from_name("huggingface-cache", create_if_missing=True)
vllm_cache_vol = openmodal.Volume.from_name("vllm-cache", create_if_missing=True)

app = openmodal.App("qwen35-vllm-serving")

@app.function(
    image=vllm_image,
    gpu="H100:1",
    scaledown_window=15 * 60,
    timeout=10 * 60,
    volumes={
        "/root/.cache/huggingface": hf_cache_vol,
        "/root/.cache/vllm": vllm_cache_vol,
    },
)
@openmodal.web_server(port=VLLM_PORT, startup_timeout=20 * 60)
@openmodal.concurrent(max_inputs=32)
def serve():
    import subprocess
    subprocess.Popen([
        "vllm", "serve", MODEL_NAME,
        "--host", "0.0.0.0",
        "--port", str(VLLM_PORT),
        "--served-model-name", MODEL_NAME,
        "--max-model-len", "131072",
        "--gpu-memory-utilization", "0.92",
        "--quantization", "gptq_marlin",
        "--dtype", "bfloat16",
        "--language-model-only",
        "--enable-auto-tool-choice",
        "--tool-call-parser", "qwen3_coder",
        "--reasoning-parser", "qwen3",
        "--enable-prefix-caching",
        "--enable-chunked-prefill",
        "--kv-cache-dtype", "fp8_e4m3",
    ])
```

## Deploy

```bash
openmodal deploy coopertrain/serve/vllm_openmodal.py
```

This builds the Docker image, creates an H100 GPU VM, pulls the image,
starts vLLM, and waits for the health check. The endpoint stays up
until the idle timeout (15 minutes of no requests).

## Query the endpoint

```bash
curl http://<IP>:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.5-35B-A3B-GPTQ-Int4",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 64
  }'
```

## What this demonstrates

| Feature | How it's used |
|---|---|
| `Image.from_registry(...)` | CUDA base image with custom Python |
| `.uv_pip_install(...)` | Fast package installation with uv |
| `gpu="H100:1"` | Request GPU hardware |
| `Volume.from_name(...)` | Persistent storage for model weights |
| `@web_server(port=8000)` | Expose an HTTP endpoint |
| `@concurrent(max_inputs=32)` | Handle 32 concurrent requests |
| `scaledown_window=900` | Auto-shutdown after 15 min idle |
