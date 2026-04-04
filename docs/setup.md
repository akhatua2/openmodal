# Setup

## Install

```bash
pip install openmodal
```

## Interactive setup

The fastest way to get started. The wizard checks prerequisites, auto-installs missing tools, walks you through authentication, and configures everything:

```bash
openmodal setup
```

Or pick a provider directly:

```bash
openmodal setup local
openmodal setup gcp
openmodal setup aws
openmodal setup azure
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

### Setup

```bash
openmodal setup gcp
```

The wizard will:

- Check for `gcloud`, `kubectl`, and `gke-gcloud-auth-plugin`
- Auto-install `kubectl` and `gke-gcloud-auth-plugin` via gcloud if missing
- Check authentication (prompts you to run `gcloud auth login` if needed)
- Let you select a GCP project
- Enable required APIs (Compute Engine, Kubernetes Engine, Cloud Build, Artifact Registry)

### Manual setup

If you prefer to set things up manually:

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable compute.googleapis.com container.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com
gcloud components install kubectl gke-gcloud-auth-plugin
```

### Verify

```bash
openmodal run examples/hello_world.py
```

OpenModal uses GKE for all workloads. The cluster is created automatically on first run (~5 min one-time setup).

## AWS

### Prerequisites

- AWS account
- `aws` CLI installed and authenticated
- `eksctl` installed (for cluster creation)
- `helm` installed (for Karpenter and KEDA)
- Docker installed (for image building)

### Setup

```bash
openmodal setup aws
pip install "openmodal[aws]"
```

### Verify

```bash
openmodal --aws run examples/hello_world.py
```

On first run, OpenModal creates an EKS cluster (~15 min one-time setup). After that, it reuses the existing cluster.

## Azure

### Prerequisites

- Azure account with a subscription
- `az` CLI installed and authenticated
- Docker installed (for image building)

### Setup

```bash
openmodal setup azure
```

### Verify

```bash
openmodal --azure run examples/hello_world.py
```

On first run, OpenModal creates an AKS cluster with the KEDA addon (~5 min one-time setup). After that, it reuses the existing cluster.
