"""GPU matrix multiplication benchmark — runs a heavy matmul on a remote GPU."""

import openmodal

app = openmodal.App("gpu-matmul")

gpu_image = (
    openmodal.Image.debian_slim()
    .pip_install("torch", "numpy")
)


@app.function(image=gpu_image, gpu="A100")
def matmul_bench(n: int = 8192):
    import time

    import torch

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device} ({torch.cuda.get_device_name() if device.type == 'cuda' else 'CPU'})")
    print(f"Matrix size: {n}x{n}")

    # Warm up
    a = torch.randn(n, n, device=device)
    b = torch.randn(n, n, device=device)
    torch.matmul(a, b)
    if device.type == "cuda":
        torch.cuda.synchronize()

    # Benchmark
    runs = 10
    start = time.perf_counter()
    for _ in range(runs):
        c = torch.matmul(a, b)
    if device.type == "cuda":
        torch.cuda.synchronize()
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / runs) * 1000
    # FLOPs for matmul: 2 * n^3
    tflops = (2 * n**3 * runs) / elapsed / 1e12

    return {
        "device": str(device),
        "gpu_name": torch.cuda.get_device_name() if device.type == "cuda" else "N/A",
        "matrix_size": n,
        "runs": runs,
        "avg_ms": round(avg_ms, 2),
        "tflops": round(tflops, 2),
    }


@app.local_entrypoint()
def main(n: int = 8192):
    result = matmul_bench.remote(n)
    print(f"\n  {result['gpu_name']}")
    print(f"  {result['matrix_size']}x{result['matrix_size']} matmul")
    print(f"  {result['avg_ms']} ms avg over {result['runs']} runs")
    print(f"  {result['tflops']} TFLOPS\n")
