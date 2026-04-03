# How it works

## Commands

### `openmodal run app.py`

Run your code on the cloud, clean up when done.

```bash
openmodal run examples/hello_world.py
```

1. Your script runs locally
2. When you call `f.remote(args)`, OpenModal spins up a machine on GCP, runs the function there, sends the result back
3. When your script exits, the machine is deleted

### `openmodal deploy app.py`

Deploy a server that stays up.

```bash
openmodal deploy examples/vllm_serving.py
```

1. Builds a Docker image with your code and dependencies
2. Starts it on a GPU machine
3. Gives you a public URL
4. After no traffic for `scaledown_window`, shuts everything down to save money
5. You redeploy when you need it again

### `openmodal stop app-name`

Shut it down now.

### `openmodal ps`

See what's running.

## What happens when you deploy a GPU server

```
You run: openmodal deploy vllm_serving.py

Step 1: Build
  Your image definition (debian_slim + pip install vllm + ...)
  gets turned into a Dockerfile, built in the cloud, and stored.
  Next time you deploy the same code, this step is skipped.

Step 2: Start
  OpenModal creates a Kubernetes pod requesting a GPU.
  GKE sees "I need an H100" and spins up a spot GPU machine.
  Your container starts on that machine, vLLM loads the model.

Step 3: Serve
  A public IP is assigned. You can send requests to it.
  The deploy command prints the URL and exits.

Step 4: Idle
  A background job checks every minute: "is anyone using this?"
  If no one has sent a request in 5 minutes (or whatever you set):
    → The container is stopped
    → The GPU machine is removed
    → You stop paying
```

## What happens when you call f.remote()

```
You run: result = f.remote(42)

Step 1: A small machine is created on GCP
Step 2: Your script file is copied to it
Step 3: The machine imports your function and calls it with the arguments you passed
Step 4: The result is sent back to your laptop
Step 5: When your script exits, the machine is deleted
```

No bytecode serialization — your actual source file runs on the remote machine. This means the remote machine's Python version doesn't need to match yours.

## Costs

| State | What's running | Cost |
|---|---|---|
| Serving requests | GPU machine + small system machines | ~$3.50/hr (H100 spot) |
| Idle, not yet scaled down | Same | Same |
| Scaled to zero | Small system machines only | ~$0.10/hr (cluster) |
| Cluster deleted | Nothing | $0 |

The `scaledown_window` controls how long the GPU stays after the last request. The cluster itself costs ~$73/mo to keep alive. If you're not using it for days, delete it to save that too.

## GKE vs GCE

OpenModal picks the backend automatically:

- **GPU server** (`gpu` + `@web_server`) → GKE (Kubernetes). Handles scaling, load balancing, public IPs.
- **Everything else** → GCE (plain VMs). Simpler, no cluster needed.

You don't need to think about this. It just works.
