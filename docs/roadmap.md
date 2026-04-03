# Roadmap

## What works today

- `f.local()`, `f.remote()`, `f.map()`
- GPU serving with `@web_server` and auto scale-to-zero
- Sandboxes with parallel creation, exec, file transfer
- Harbor / SWE-bench integration
- GKE with spot GPUs (H100, A100, L4)
- GCE for simple compute functions

## What's next

### Horizontal auto-scaling

Currently each deployment runs 1 replica. When a single container can't handle the load (e.g., GPU saturated on vLLM), we need to scale to multiple replicas automatically.

**What's needed:** KEDA (Kubernetes Event-Driven Autoscaler) to scale based on request queue depth. Requires `container.admin` IAM role on the GCP project to install.

**Without KEDA:** A CronJob-based approach that monitors `vllm_num_requests_waiting` from the `/metrics` endpoint and scales replicas up/down. Works within Editor permissions.

### Scheduled functions

Modal supports `@app.function(schedule=modal.Cron("0 9 * * *"))` and `modal.Period(hours=1)` for recurring tasks. Could use GKE CronJobs or Cloud Scheduler.

### FastAPI / ASGI endpoints

Modal supports `@modal.asgi_app` and `@modal.web_endpoint` for serving FastAPI, Flask, etc. Currently we only support `@web_server` (subprocess-based). Adding ASGI support would cover most web serving use cases.

### Container lifecycle hooks

Modal has `@build`, `@enter`, `@exit` decorators for running code at container build time, startup, and shutdown. Useful for loading models into memory once and reusing across requests.

### Stateful GPU classes (`@app.cls`)

Modal supports class-based functions where the class is instantiated once per container and methods are called per request. Important for GPU inference where model loading is expensive.

### Log streaming

Stream container logs back to the CLI in real-time. Currently logs are only visible via `kubectl logs`.

### Scale-from-zero

When a request arrives and no containers are running, automatically spin one up and queue the request. Currently requires a redeploy. KEDA's HTTP add-on or a Cloud Run proxy would solve this.

### Multi-region

Currently hardcoded to `us-central1`. Should auto-detect the best region based on GPU availability and user location.

### AWS provider

The provider abstraction (`providers/base.py`) is ready. An AWS provider using EKS would mirror the GKE implementation.

### Publish to real PyPI

Currently on Test PyPI. Once stable, publish to real PyPI so `pip install openmodal` just works.
