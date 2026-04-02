# Setup

## Prerequisites

- Python 3.10+
- GCP account with a project
- `gcloud` CLI installed and authenticated

## Install

```bash
pip install openmodal
```

Or from Test PyPI (current):

```bash
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ openmodal
```

## GCP Setup

Authenticate with your GCP project:

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

OpenModal needs the following GCP APIs enabled:

```bash
gcloud services enable compute.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable secretmanager.googleapis.com
```

## Verify

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
