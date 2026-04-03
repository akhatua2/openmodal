# Changelog

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
