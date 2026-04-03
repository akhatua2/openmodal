# How it works

## Commands

### `openmodal run app.py`

Ephemeral execution. Creates cloud resources, runs your code, tears everything down on exit.

```bash
openmodal run examples/hello_world.py
openmodal run examples/webscraper.py --url http://example.com
```

What happens:
1. Loads your Python file, finds the `openmodal.App`
2. For each `@app.function`: creates a cloud container (GCE VM or GKE pod)
3. Runs `@app.local_entrypoint()` on your machine
4. `f.remote(args)` sends the function call to the cloud container, returns the result
5. `f.map(iterable)` sends calls in parallel
6. On exit: deletes all cloud resources

### `openmodal deploy app.py`

Persistent deployment. Creates resources and keeps them running until idle timeout.

```bash
openmodal deploy examples/vllm_serving.py
```

What happens:
1. Builds a Docker image via Cloud Build, pushes to Artifact Registry
2. If the function has `gpu` + `@web_server`: uses GKE (Kubernetes)
   - Creates a Deployment (keeps the pod running)
   - Creates a LoadBalancer Service (public IP)
   - Creates a CronJob (monitors idle connections, scales to 0 after `scaledown_window`)
3. Otherwise: uses GCE (single VM with idle watchdog)
4. Waits for health check to pass
5. Prints the endpoint URL

### `openmodal stop app-name`

Deletes all resources for an app.

```bash
openmodal stop vllm-test
```

### `openmodal ps`

Lists running containers.

```bash
openmodal ps
```

## Under the hood

### Provider auto-detection

OpenModal picks the right backend automatically:

| Function has | Provider | Why |
|---|---|---|
| `gpu` + `@web_server` | GKE | Needs auto-scaling, load balancing |
| Everything else | GCE | Simpler, no cluster overhead |

Override with `OPENMODAL_PROVIDER=gke` or `OPENMODAL_PROVIDER=gce`.

### GKE (GPU serving)

For `@web_server` functions with GPUs, OpenModal uses Google Kubernetes Engine:

```
openmodal deploy → Cloud Build (image) → GKE Deployment + Service + CronJob
                                              ↓
                                    Node autoscaler provisions GPU node
                                              ↓
                                    Pod starts, pulls image, runs vLLM
                                              ↓
                                    Health check passes → endpoint live
                                              ↓
                                    CronJob monitors every minute
                                              ↓
                                    No traffic for scaledown_window
                                              ↓
                                    Scales replicas to 0 → pod dies
                                              ↓
                                    Node autoscaler removes GPU node → $0
```

- GPU node pools use **spot instances** (~60-70% cheaper)
- Images are cached in Artifact Registry (rebuild only when code changes)
- The cluster auto-provisions on first deploy if it doesn't exist

### GCE (compute functions)

For `f.remote()` and `f.map()`, OpenModal creates GCE VMs:

```
f.remote(args) → Create GCE VM → Install Python + openmodal → Start agent
                                              ↓
                                    Send (module, function, args) to agent
                                              ↓
                                    Agent imports module, calls function
                                              ↓
                                    Returns result → VM deleted on exit
```

- Functions are shipped as source code (not pickled bytecode), so Python version mismatches don't matter
- The openmodal package is installed in the VM so `import openmodal` works in your code
- For custom images: Docker image is built once, agent is added on top

### Image building

Images are built via Google Cloud Build and pushed to Artifact Registry:

```python
image = openmodal.Image.debian_slim().pip_install("requests", "beautifulsoup4")
```

Becomes this Dockerfile:
```dockerfile
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y python3 python3-pip ...
RUN pip install requests beautifulsoup4
RUN pip install openmodal
COPY your_script.py /opt/your_script.py
CMD ["python", "-m", "openmodal.runtime.web_server"]
```

Images are hash-tagged — if the Dockerfile hasn't changed, the build is skipped entirely.

### Scale-to-zero

For GKE deployments, a CronJob runs every minute:

1. Check: is the pod Ready?  (if not, skip — still starting up)
2. Check: are there active TCP connections on the serve port?
3. If connections: update `last-active` timestamp
4. If no connections and idle > `scaledown_window`: scale Deployment to 0 replicas
5. GKE node autoscaler removes the empty GPU node (~5 min after pod is gone)

Total time from last request to $0: `scaledown_window` + ~5 min.
