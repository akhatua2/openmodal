# Setup

## Install

```bash
pip install openmodal
```

## Local (Docker)

If you just want to try OpenModal without a cloud account, all you need is Docker:

```bash
openmodal --local run examples/hello_world.py
```

That's it. No cloud credentials, no API keys. Functions run in Docker containers on your machine.

If you have NVIDIA GPUs and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) installed, GPU functions work too.

## GCP

For cloud GPUs, spot instances, and auto scale-to-zero, you'll need a GCP project.

### Prerequisites

- GCP account with a project
- `gcloud` CLI installed

### Authenticate

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### Enable APIs

```bash
gcloud services enable compute.googleapis.com
gcloud services enable container.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable artifactregistry.googleapis.com
```

### Verify

```bash
openmodal run examples/hello_world.py
```

You should see:

```
✓ Initialized.
✓ Created objects.
✓ Container created. (2 vCPU, 2 GB RAM • 34.135.113.28 • 14s)
✓ Container ready. (60s total)
hello 1000
1000000
1000000
2646700
✓ Containers cleaned up.
✓ App completed.
```

OpenModal auto-detects the right backend: GKE for GPU workloads and sandboxes, GCE for simple compute.

## AWS

### Prerequisites

- AWS account
- `aws` CLI installed and authenticated
- `eksctl` installed (for cluster creation)
- `helm` installed (for Karpenter and KEDA)
- Docker installed (for image building)

### Authenticate

```bash
aws login
```

### Install AWS extras

```bash
pip install "openmodal[aws]"
```

### Verify

```bash
openmodal --aws run examples/hello_world.py
```

On first run, OpenModal creates an EKS cluster (~15 min one-time setup). After that, it reuses the existing cluster.
