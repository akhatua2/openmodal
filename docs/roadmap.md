# Roadmap

## What works today

- `f.local()`, `f.remote()`, `f.map()`
- GPU serving with `@web_server` and auto scale-to-zero
- Sandboxes with parallel creation, exec, file transfer
- Harbor / SWE-bench integration
- Local Docker provider (CPU and GPU)
- GCP provider with spot GPUs (H100, A100, L4)
- AWS provider with EKS, Karpenter, KEDA, ECR, S3
- Azure provider with AKS, ACR, KEDA, Azure Blob Storage CSI
- Published on [PyPI](https://pypi.org/project/openmodal/) with auto-publish on version bump

## What's next

### Scale-from-zero

When a request arrives and no containers are running, automatically spin one up. Currently requires a redeploy.

### Horizontal auto-scaling

Currently each deployment runs 1 replica. Need KEDA or a CronJob-based approach to scale replicas based on request queue depth.

### Stateful GPU classes (`@app.cls`)

Class-based functions where the class is instantiated once per container and methods are called per request. Important for GPU inference where model loading is expensive.

### Container lifecycle hooks

`@build`, `@enter`, `@exit` decorators for running code at container build time, startup, and shutdown.

### FastAPI / ASGI endpoints

`@modal.asgi_app` and `@modal.web_endpoint` for serving FastAPI, Flask, etc. Currently only `@web_server` (subprocess-based) is supported.

### Scheduled functions

`@app.function(schedule=modal.Cron("0 9 * * *"))` for recurring tasks.

### Multi-region

Currently hardcoded to `us-central1`. Should auto-detect the best region based on GPU availability.
