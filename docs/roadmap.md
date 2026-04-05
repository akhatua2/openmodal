# Roadmap

## Modal API compatibility

How OpenModal compares to the [Modal Python API](https://modal.com/docs/reference).

### Supported

| Feature | Modal | OpenModal |
|---|:---:|:---:|
| **Application construction** | | |
| `App` | ✓ | ✓ |
| `@app.function()` | ✓ | ✓ |
| `@app.local_entrypoint()` | ✓ | ✓ |
| **Serverless execution** | | |
| `Function.remote()` | ✓ | ✓ |
| `Function.local()` | ✓ | ✓ |
| `Function.map()` | ✓ | ✓ |
| **Web integrations** | | |
| `@web_server(port)` | ✓ | ✓ |
| **Function semantics** | | |
| `@modal.concurrent` | ✓ | ✓ |
| **Scheduling** | | |
| `modal.Cron` | ✓ | ✓ |
| `modal.Period` | ✓ | ✓ |
| **Exception handling** | | |
| `retries=N` | ✓ | ✓ |
| **Sandboxes** | | |
| `Sandbox.create()` | ✓ | ✓ |
| `Sandbox.exec()` | ✓ | ✓ |
| `Sandbox.filesystem` | ✓ | ✓ |
| `ContainerProcess` | ✓ | ✓ |
| **Container configuration** | | |
| `Image.debian_slim()` | ✓ | ✓ |
| `Image.from_registry()` | ✓ | ✓ |
| `Image.from_dockerfile()` | ✓ | ✓ |
| `.pip_install()` | ✓ | ✓ |
| `.uv_pip_install()` | ✓ | ✓ |
| `.apt_install()` | ✓ | ✓ |
| `.run_commands()` | ✓ | ✓ |
| `.env()` | ✓ | ✓ |
| `.workdir()` | ✓ | ✓ |
| `.entrypoint()` | ✓ | ✓ |
| `Secret.from_name()` | ✓ | ✓ |
| `Secret.from_dict()` | ✓ | ✓ |
| **Resource configuration** | | |
| `gpu=` | ✓ | ✓ |
| `cpu=` | ✓ | ✓ |
| `memory=` | ✓ | ✓ |
| `timeout=` | ✓ | ✓ |
| `scaledown_window=` | ✓ | ✓ |
| **Persistent storage** | | |
| `Volume` | ✓ | ✓ |
| **CLI** | | |
| `run` | ✓ | ✓ |
| `deploy` | ✓ | ✓ |
| `stop` | ✓ | ✓ |
| `secret create/list/delete` | ✓ | ✓ |
| `ps` / `logs` | ✗ | ✓ |
| `monitor` | ✗ | ✓ |
| `setup` | ✗ | ✓ |

### Not yet supported

| Feature | Status |
|---|---|
| **High priority** | |
| `Function.spawn()` | Planned |
| `modal.Dict` / `modal.Queue` | Planned |
| **Medium priority** | |
| `Function.starmap()` / `.for_each()` | Planned |
| `modal.Retries(backoff=)` | Planned |
| `CloudBucketMount` | Planned |
| `.add_local_file()` / `.add_local_dir()` | Planned |
| `.add_local_python_source()` | Planned |
| `.run_function()` | Planned |
| `.pip_install_from_requirements()` / `.pip_install_from_pyproject()` | Planned |
| `serve` (hot-reload) | Planned |
| `shell` | Planned |
| `volume ls/put/get/rm` | Planned |
| Multi-region | Planned |
| **Lower priority** | |
| `@app.cls()` / `Cls` / `@modal.method` | Planned — ergonomic, not blocking |
| `@modal.enter` / `@modal.exit` | Planned — ergonomic, not blocking |
| `@modal.batched` | Planned — ergonomic, not blocking |
| `@modal.fastapi_endpoint` | Planned — ergonomic, not blocking |
| `@modal.asgi_app` / `@modal.wsgi_app` | Planned — ergonomic, not blocking |
| `modal.parameter()` / `Cls.with_options()` | Planned |
| `@app.include()` | |
| `Image.from_scratch()` / `Image.micromamba()` | |
| `Secret.from_dotenv()` | |
| `ephemeral_disk=` | |
| GPU fallback lists | |
| Memory snapshots | |
| `FileIO` | |
| `snapshot_filesystem()` | |
| Port tunnels | |
| `modal.Proxy` / `modal.forward()` | |
| Rolling / recreate strategies | |
| Environments (dev/staging/prod) | |
| `container exec` | |
| `NetworkFileSystem` | Deprecated in Modal |

## OpenModal-only features

Things we support that Modal doesn't:

- **Multi-cloud** — GCP, AWS, Azure, and local Docker from one API
- **Self-hosted** — runs on your own infrastructure, no vendor lock-in
- **Local Docker mode** — free local testing with GPU passthrough (`--local`)
- **Live terminal dashboard** — `openmodal monitor` with real-time GPU/CPU/memory sparklines
- **Historical metrics** — persisted metrics with circular buffer
- **Interactive setup wizard** — `openmodal setup` for each cloud provider
- **Harbor / CooperBench integration** — experiment tracking compatibility

## Infra roadmap

### SLURM provider

Run on university HPC clusters via SLURM + Singularity. No sudo or Kubernetes needed — just SSH + `sbatch`.
