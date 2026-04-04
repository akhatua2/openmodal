# Roadmap

## What works today

- `f.local()`, `f.remote()`, `f.map()`
- GPU serving with `@web_server` and auto scale-to-zero (KEDA)
- Sandboxes with parallel creation, exec, file transfer
- Custom images, secrets, retries, volumes
- Local Docker provider (CPU and GPU)
- GCP provider with spot GPUs (H100, A100, L4) and cluster autoscaling
- AWS provider with EKS, Karpenter, KEDA, ECR
- Azure provider with AKS, ACR, KEDA
- `openmodal monitor` — live GPU/CPU/memory dashboard
- `openmodal secret` — local secret management
- `openmodal setup` — interactive setup wizard with auto-install
- Benchmark suite for sandbox performance testing
- CooperBench integration (one-line import swap)
- Harbor / SWE-bench integration
- Published on [PyPI](https://pypi.org/project/openmodal/) with auto-publish on version bump

## What's next

### Stateful GPU classes (`@app.cls`)

Class-based functions where the class is instantiated once per container and methods are called per request. Important for GPU inference where model loading is expensive.

### Container lifecycle hooks

`@build`, `@enter`, `@exit` decorators for running code at container build time, startup, and shutdown.

### FastAPI / ASGI endpoints

`@modal.asgi_app` and `@modal.web_endpoint` for serving FastAPI, Flask, etc. Currently only `@web_server` (subprocess-based) is supported.

### Scheduled functions

`@app.function(schedule=modal.Cron("0 9 * * *"))` for recurring tasks.

### SLURM provider

Run on university HPC clusters via SLURM + Singularity. No sudo or Kubernetes needed — just SSH + `sbatch`.

### Multi-region

Currently hardcoded to `us-central1` (GCP) / `us-east-1` (AWS). Should auto-detect the best region based on GPU availability.
