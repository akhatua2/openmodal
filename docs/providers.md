# Providers

OpenModal supports multiple providers through a pluggable interface. All code outside `providers/` is provider-agnostic — your code doesn't change when you switch backends.

## Local (Docker)

Run everything on your local machine using Docker. No cloud account needed.

```bash
openmodal --local run examples/hello_world.py
```

| Feature | How it works |
|---|---|
| `f.remote()` | `docker run` with your function |
| `f.map()` | Parallel calls to the same container |
| Sandboxes | `docker run -d` + `docker exec` |
| GPU | `--gpus all` with NVIDIA Container Toolkit |
| Volumes | Local directories (`~/.openmodal/volumes/`) |
| Image build | `docker build` locally (no registry) |
| Scaling | Single machine |

Best for: development, testing, university labs with GPU machines but no cloud budget.

If you request a GPU that doesn't match your hardware, OpenModal tells you and suggests using cloud instead.

## GCP (default)

Two backends, auto-detected based on your workload:

- **GCE** — raw VMs for `f.remote()` and simple compute
- **GKE** — Kubernetes for GPU serving (`@web_server`), sandboxes, and functions with volumes. Auto-scales with spot GPUs.

```bash
openmodal run examples/hello_world.py          # auto-detects GCE
openmodal deploy examples/vllm_serving.py      # auto-detects GKE (GPU + web_server)
openmodal run examples/sandbox.py              # auto-detects GKE (sandboxes)
```

You can also force a backend if needed: `OPENMODAL_PROVIDER=gce` or `OPENMODAL_PROVIDER=gke`.

## AWS

Single EKS backend for all workloads — Karpenter auto-provisions the right instance type based on your GPU request.

```bash
openmodal --aws run examples/hello_world.py
```

| Feature | How it works |
|---|---|
| `f.remote()` | EKS pod with your function |
| Sandboxes | EKS pod + `kubectl exec` |
| GPU | Karpenter provisions spot GPU nodes (p5, g5, g6) |
| Volumes | S3 + Mountpoint CSI driver |
| Image build | Local `docker build` + ECR push |
| Scale-to-zero | KEDA ScaledObject |
| Scaling | Karpenter auto-provisioning |

Auto-creates the EKS cluster on first run (~15 min one-time setup).

## Azure

Single AKS backend for all workloads — KEDA comes as a built-in addon, so there's nothing extra to install.

```bash
openmodal --azure run examples/hello_world.py
```

| Feature | How it works |
|---|---|
| `f.remote()` | AKS pod with your function |
| Sandboxes | AKS pod + `kubectl exec` |
| GPU | NC/ND-series VMs (not yet tested) |
| Volumes | Azure Blob Storage CSI driver |
| Image build | Local `docker build` + ACR push |
| Scale-to-zero | KEDA (native AKS addon) |
| Scaling | AKS node autoprovisioning |

Auto-creates the AKS cluster on first run (~5 min one-time setup).

## Adding a new provider

All providers implement `CloudProvider` from `providers/base.py`:

```python
class CloudProvider(ABC):
    def create_instance(spec, image_uri, name) -> (name, ip)
    def delete_instance(name)
    def list_instances(app_name) -> [{name, status, ip}]
    def wait_for_healthy(ip, port, timeout) -> bool

    def build_image(dockerfile_dir, name, tag) -> image_uri
    def image_exists(image_uri) -> bool

    def create_sandbox_pod(name, image_uri, timeout, **kwargs)
    def exec_in_pod(pod_name, *args, workdir, env) -> ContainerProcess
    def copy_to_pod(pod_name, local_path, remote_path)
    def copy_from_pod(pod_name, remote_path, local_path)

    def ensure_volume(name) -> uri
    def stream_logs(instance_name) -> Popen | None
    def machine_spec_str(gpu) -> str
    def instance_name(app, func, suffix) -> str
```

To add a provider: create `providers/<name>/` implementing `CloudProvider`, then register it in `providers/__init__.py`.
