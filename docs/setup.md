# Setup

## Install

```bash
pip install openmodal
```

## Interactive setup

The fastest way to get started is the setup wizard. It checks your prerequisites, walks you through authentication, and configures everything:

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

OpenModal uses GKE for all workloads. The cluster is created automatically on first run.

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

## Azure

### Prerequisites

- Azure account with a subscription
- `az` CLI installed and authenticated
- Docker installed (for image building)

### Authenticate

```bash
az login
```

### Verify

```bash
openmodal --azure run examples/hello_world.py
```

On first run, OpenModal creates an AKS cluster with the KEDA addon (~5 min one-time setup). After that, it reuses the existing cluster.
