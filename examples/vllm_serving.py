"""Serve Qwen3.5-0.8B on a GPU with vLLM via OpenModal."""

import openmodal

MODEL_NAME = "Qwen/Qwen3.5-0.8B"
VLLM_PORT = 8000

vllm_image = (
    openmodal.Image.from_registry("nvidia/cuda:12.8.0-devel-ubuntu22.04", add_python="3.12")
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
)

app = openmodal.App("vllm-test")


@app.function(
    image=vllm_image,
    gpu="L4",
    scaledown_window=5 * 60,
    timeout=10 * 60,
)
@openmodal.web_server(port=VLLM_PORT, startup_timeout=20 * 60)
@openmodal.concurrent(max_inputs=8)
def serve():
    import subprocess

    subprocess.Popen([
        "vllm", "serve", MODEL_NAME,
        "--host", "0.0.0.0",
        "--port", str(VLLM_PORT),
        "--served-model-name", MODEL_NAME,
        "--max-model-len", "4096",
        "--enforce-eager",
    ])


@app.local_entrypoint()
def main():
    import requests

    url = serve.web_url
    print(f"Endpoint: {url}")

    resp = requests.post(f"{url}/v1/chat/completions", json={
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": "Say hello in one word."}],
        "max_tokens": 16,
    })
    print(resp.json()["choices"][0]["message"]["content"])
