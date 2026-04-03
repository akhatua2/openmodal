# Changelog

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
