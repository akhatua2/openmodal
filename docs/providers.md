# Providers

OpenModal supports multiple cloud providers through a pluggable provider interface. All code outside `providers/` is cloud-agnostic — adding a new provider is just a new directory.

## Current providers

### GCP (default)

Two backends:

- **GCE** — raw VMs for `f.remote()`, simple compute. Used when no GPU serving or volumes needed.
- **GKE** — Kubernetes for GPU serving (`@web_server`), sandboxes, and functions with volumes. Auto-scales with spot GPUs.

Set explicitly: `OPENMODAL_PROVIDER=gce` or `OPENMODAL_PROVIDER=gke`

Auto-detection: GKE for GPU + web_server or volumes, sandboxes. GCE for everything else.

## Planned providers

### Local (Docker)

Run everything on your local machine using Docker. No cloud account needed.

| Feature | Implementation |
|---|---|
| `f.remote()` | `docker run` with function source mounted |
| Sandboxes | `docker run -d`, `docker exec` for commands |
| GPU | `docker run --gpus '"device=N"'` with NVIDIA runtime |
| Volumes | Local directories bind-mounted into containers |
| Image build | `docker build` (no registry push) |
| Scaling | None — single machine |

Best for: development, testing, university labs with GPU machines but no cloud budget.

Set with: `OPENMODAL_PROVIDER=local`

### AWS (EKS)

Same architecture as GKE but on AWS infrastructure.

| GCP Service | AWS Equivalent |
|---|---|
| GKE | EKS (Elastic Kubernetes Service) |
| GCE | EC2 |
| Cloud Build | Local build + ECR push |
| Artifact Registry | ECR (Elastic Container Registry) |
| GCS buckets | S3 + Mountpoint CSI driver |
| Secret Manager | Secrets Manager + CSI driver |
| Spot instances | EC2 Spot |
| Node autoscaler | Karpenter |
| Load Balancer | NLB (Network Load Balancer) |

GPU instances on AWS:

| Instance | GPU | VRAM | Spot $/hr |
|---|---|---|---|
| g5.xlarge | 1x A10G | 24 GB | ~$0.35 |
| g6.xlarge | 1x L4 | 24 GB | ~$0.30 |
| p4d.24xlarge | 8x A100 | 320 GB | ~$8 |
| p5.48xlarge | 8x H100 | 640 GB | ~$20 |

Key differences from GCP:
- No Autopilot equivalent — must use Karpenter for auto-provisioning
- S3 Mountpoint CSI is append-only (not full POSIX like GCS FUSE)
- GPU node cold start is ~3-7 min (vs ~2-5 min on GKE with Image Streaming)
- SSH via key pairs instead of `gcloud compute ssh`

Set with: `OPENMODAL_PROVIDER=aws`

## Provider interface

All providers implement `CloudProvider` from `providers/base.py`:

```python
class CloudProvider(ABC):
    # Core
    def create_instance(spec, image_uri, name) -> (name, ip)
    def delete_instance(name)
    def list_instances(app_name) -> [{name, status, ip}]
    def wait_for_healthy(ip, port, timeout) -> bool
    
    # Images
    def build_image(dockerfile_dir, name, tag) -> image_uri
    def image_exists(image_uri) -> bool
    
    # Sandboxes
    def create_sandbox_pod(name, image_uri, timeout, **kwargs)
    def exec_in_pod(pod_name, *args, workdir, env) -> ContainerProcess
    def copy_to_pod(pod_name, local_path, remote_path)
    def copy_from_pod(pod_name, remote_path, local_path)
    
    # Volumes & secrets
    def ensure_volume(name) -> uri
    def stream_logs(instance_name) -> Popen | None
    
    # Display
    def machine_spec_str(gpu) -> str
    def instance_name(app, func, suffix) -> str
```

To add a new provider: create `providers/<name>/` implementing `CloudProvider`, then register it in `providers/__init__.py`.
