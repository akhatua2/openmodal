# Changelog

## 0.3.13 (2026-04-05)

### Added
- **`Dict` — distributed key-value store** backed by Redis. Shared across all running functions. `d = openmodal.Dict.from_name("my-dict"); d["key"] = value`
- **`Queue` — distributed FIFO queue** backed by Redis. Producer/consumer pattern across pods. `q = openmodal.Queue.from_name("work"); q.put(item); q.get()`
- Redis pod is deployed lazily (only when Dict/Queue are first used) and cleaned up on `openmodal stop`
- Works on all providers: GCP (GKE), AWS (EKS), Azure (AKS), local Docker

## 0.3.12 (2026-04-05)

### Added
- **Scheduled functions (`Cron`, `Period`)** — `@app.function(schedule=openmodal.Cron("* * * * *"))` creates a Kubernetes CronJob on deploy. Supports all providers (GCP, AWS, Azure, local Docker).
- **`openmodal ps` shows cron jobs** — lists active CronJobs alongside running containers
- **`openmodal stop` cleans up cron jobs** — deletes CronJobs when stopping an app
- New example: `examples/uptime_monitor.py` — pings a URL every minute

## 0.3.11 (2026-04-04)

### Added
- **`cpu=` and `memory=` params on `@app.function()`** — request custom CPU/memory for remote functions (closes #4)
- **GCP Node Auto-Provisioning (NAP)** — cluster auto-creates node pools for any CPU/memory request
- **Azure Node Auto-Provisioning** — same as GCP, cluster creates right-sized nodes on the fly

## 0.3.10 (2026-04-04)

### Changed
- **Azure image builds now use ACR Tasks** — `az acr build` replaces local `docker build` + push. No local Docker needed (same as GCP).
- Architecture docs page with Mermaid diagrams

## 0.3.9 (2026-04-04)

### Changed
- Default sandbox resource requests: 0.25 CPU, 256 MB RAM on all K8s providers — fixes cluster autoscaler not scaling up when many sandboxes are created
- GCP sandbox node pool: `e2-small` → `e2-standard-8` (fits ~32 pods/node), max nodes 10 → 100
- AWS Karpenter general nodepool: added larger instance types (`t3.xlarge`, `t3.2xlarge`, `m5.2xlarge`)
- Azure default node pool: `Standard_B2s` → `Standard_D8s_v5`, max nodes 3 → 100
- `openmodal setup gcp` auto-installs `kubectl` and `gke-gcloud-auth-plugin` if missing

### Fixed
- GKE preflight now checks for `gke-gcloud-auth-plugin` with a clear error message

### Tested
- Sandbox creation and exec verified on GCP (GKE), AWS (EKS), and Azure (AKS)
- GKE autoscaling verified: 30 sandboxes triggers node scale-up within 60s

## 0.3.8 (2026-04-04)

### Added
- **CooperBench integration** — run multi-agent coding benchmarks on OpenModal with a one-line import swap (`import openmodal as modal`)
- CooperBench example and docs page

### Fixed
- `ContainerProcess.returncode` is now a public attribute (was `_returncode`), matching Modal's API

## 0.3.7 (2026-04-04)

### Added
- **Benchmark suite** — `benchmarks/` with tasks for sandbox create, exec, scaling, lifecycle, and image tests. Run with `python -m benchmarks.runner`
- GKE provider now builds a default agent image when no image is specified
- Unique pod names (UUID suffix) — eliminates name conflicts and removes `sleep(2)` from pod creation

### Changed
- Smaller default nodes: GCP `e2-small` (2 CPU, 2GB), AWS `t3.small` (2 CPU, 2GB)
- AWS and Azure now show `2 vCPU, 4 GB RAM` instead of raw machine type names
- Disabled log streaming during `f.remote()` and `f.map()` — use `openmodal logs` instead
- Clean spinner output during cluster creation (no more log messages leaking through)

### Fixed
- GKE `create_instance` crashing with empty image when no `image=` specified
- Type errors in KEDA scaledown calls across AWS and Azure providers

## 0.3.6 (2026-04-03)

### Added
- **`openmodal monitor`** — live resource utilization dashboard showing GPU, VRAM, CPU, and memory sparkline graphs
- Background metrics collection starts automatically during `openmodal run` — `monitor` shows full history even if started later
- Saved metrics persist to `~/.openmodal/metrics/` — view after runs complete with `openmodal monitor <app>`
- `exec_in_pod` now supports `container` parameter for multi-container pods
- `rich` dependency for terminal UI

## 0.3.5 (2026-04-03)

### Added
- **`openmodal secret`** CLI — `create`, `list`, `delete` named secrets stored in `~/.openmodal/secrets/`
- `Secret.from_name()` now loads from the local secret store (no cloud secret manager permissions needed)
- **`add_python` uses python-build-standalone** — installs any Python version (3.10–3.13) on any base image via pre-compiled builds from Astral

### Changed
- SFT example uses `nvidia/cuda:12.8.1-devel-ubuntu24.04` base image (ships with Python 3.12 + CUDA)
- SFT example uses `Secret.from_name("wandb-secret")` instead of inline env var
- GPU containers now set `LD_LIBRARY_PATH` and `NVIDIA_VISIBLE_DEVICES` for proper CUDA detection

### Fixed
- `Volume.from_name()` is now lazy — no longer tries to create buckets at import time, which was crashing inside remote containers where cloud CLIs aren't installed
- `delete_instance` no longer force-kills pods — uses default grace period so the sync-upload sidecar has time to push volume data back to cloud storage

## 0.3.4 (2026-04-03)

### Changed
- **Volumes rewritten** — replaced CSI drivers (GCS FUSE, S3 Mountpoint, Azure Blob CSI) with init container sync. Volumes now sync from cloud storage at startup and back on shutdown. Same filesystem mount paths, no Workload Identity or IAM admin needed.
- GKE cluster no longer requires GCS FUSE addon or Workload Identity
- EKS cluster no longer installs S3 CSI driver addon
- GPU node pools restricted to zones a/b/c to avoid accelerator availability errors

### Fixed
- Pickle deserialization of user-defined classes (e.g. dataclasses) in remote execution
- GKE cluster RBAC binding failure no longer crashes setup on shared projects
- All ruff lint errors across the codebase (import sorting, line length, unused variables)
- Fixed ty type checker configuration and type errors in agent and volume code

### Removed
- GCS FUSE CSI driver dependency
- S3 CSI driver and IRSA setup for volumes
- Azure Blob CSI volume specs
- Bucket-level IAM grant logic from GCP storage

## 0.3.3 (2026-04-03)

### Added
- **`openmodal setup`** — interactive setup wizard with arrow-key provider picker
- Per-provider setup: checks prerequisites, selects GCP project / Azure subscription, enables APIs

### Removed
- **GCE bare VM provider** — GCP now uses GKE for all workloads, simplifying the codebase

### Changed
- GCP defaults to GKE instead of auto-detecting between GCE and GKE
- Simplified provider routing (removed `gce`/`eks`/`aks` aliases)
- Docs workflow only triggers on changes to `docs/` or `mkdocs.yml`

## 0.3.2 (2026-04-03)

### Added
- **Azure provider** — AKS with built-in KEDA addon, ACR, Azure Blob Storage CSI. `openmodal --azure run`
- **`--azure` CLI flag** for running on Azure AKS

### Tested
- `hello_world`, `sandbox`, `webscraper` all pass on Azure
- GPU testing deferred to a later release

## 0.3.1 (2026-04-03)

### Added
- **AWS provider** — EKS with Karpenter, KEDA, ECR, S3 Mountpoint CSI. `openmodal --aws run`
- **`--aws` CLI flag** for running on AWS EKS
- **`--local` CLI flag** for running on local Docker (replaces `OPENMODAL_PROVIDER=local`)
- **`__version__`** attribute on the openmodal package
- **Auto-publish to PyPI** via GitHub Actions on version bump
- GPU validation on local provider with helpful error messages

### Fixed
- Stale Test PyPI reference in GCE provider startup script
- ECR repository creation race condition with parallel sandboxes
- EKS pod connectivity via kubectl port-forward (pod IPs not directly routable)

## 0.3.0 (2026-04-03)

### Added
- **Local Docker provider** — `f.remote()`, `f.map()`, sandboxes all work on local Docker
- Published to real PyPI (`pip install openmodal`)

### Changed
- Image install switched from Test PyPI to real PyPI

## 0.2.1 (2026-04-02)

Initial release on Test PyPI.

### Added
- **GCP provider** — GCE for simple compute, GKE for GPU serving and sandboxes
- `f.local()`, `f.remote()`, `f.map()`
- GPU serving with `@web_server` and auto scale-to-zero (CronJob-based)
- Custom images, secrets, retries, volumes
- Sandboxes with parallel creation, exec, file transfer
- Harbor / SWE-bench integration
- CLI: `openmodal run`, `deploy`, `stop`, `ps`
- MkDocs documentation site
