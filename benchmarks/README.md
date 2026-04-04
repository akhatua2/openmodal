# Benchmarks

Performance benchmarks for OpenModal sandbox operations. Compare against Modal and track improvements over time.

## Results (v0.3.6, 2026-04-04)

10 runs × 3 iterations each. Values are mean ± std dev.

| Operation | Local | GCP (GKE) | AWS (EKS) | Modal |
|---|---|---|---|---|
| sandbox.create (warm) | 0.25s ±0.01 | 4.33s ±0.49 | 2.01s ±0.01 | 0.20s ±0.28 |
| exec (echo) | 0.06s ±0.01 | 0.12s ±0.06 | 0.17s ±0.02 | 0.56s ±0.69 |
| exec (bash) | 0.06s ±0.00 | 0.11s ±0.04 | 0.19s ±0.06 | 0.10s ±0.05 |
| exec + stdout | 0.06s ±0.00 | 0.10s ±0.02 | 0.19s ±0.04 | 0.19s ±0.10 |
| exec (python3) | 0.08s ±0.01 | 0.11s ±0.02 | 0.21s ±0.04 | 0.11s ±0.06 |
| file write + read | 0.13s ±0.01 | 0.20s ±0.04 | 0.38s ±0.10 | 0.29s ±0.16 |
| exec (curl) | 0.10s ±0.01 | 0.17s ±0.02 | 0.20s ±0.03 | 0.11s ±0.05 |
| 10x sequential exec | 0.62s ±0.01 | 1.01s ±0.19 | 1.86s ±0.23 | 1.05s ±0.52 |
| exec (large stdout) | 0.06s ±0.00 | 0.09s ±0.01 | 0.24s ±0.02 | 0.24s ±0.16 |

### Key findings

- **Exec latency**: OpenModal Local and GCP are faster or tied with Modal on all exec operations
- **AWS exec is ~2x slower than GCP**: due to `kubectl port-forward` proxy (EKS pod IPs aren't directly routable)
- **Sandbox creation**: Modal warm start is ~0.2s vs our 4.3s (GCP) / 2.0s (AWS) — Kubernetes pod scheduling overhead
- **Local Docker is fastest**: ~60ms exec, ~250ms sandbox create. Best for development.

### Bottleneck analysis

| Component | GCP | AWS | What it is |
|---|---|---|---|
| K8s API call | ~170ms | ~170ms | HTTP to API server, etcd write |
| Scheduler | ~170ms | ~170ms | Pick a node, write decision |
| Image pull | ~2s | ~1s | Check registry, pull layers if not cached |
| Container start | ~200ms | ~200ms | Create namespaces, cgroups, start process |
| Port-forward | N/A | ~100ms | AWS/Azure need proxy (pod IPs not routable) |

## Running

```bash
# Run all benchmarks (GCP)
python -m benchmarks.runner

# Specific provider
python -m benchmarks.runner --provider local
python -m benchmarks.runner --provider aws

# Modal comparison
python -m benchmarks.runner --modal

# Specific tasks
python -m benchmarks.runner --tasks sandbox_create sandbox_exec

# More iterations
python -m benchmarks.runner --iterations 5
```

## Tasks

| Task | What it measures |
|---|---|
| `sandbox_create` | Cold start vs warm start creation time |
| `sandbox_exec` | Exec latency: echo, bash, python, file I/O, network, large output |
| `sandbox_lifecycle` | Full create → exec → terminate cycle + resource leak detection |
| `sandbox_image` | Creation time with cold (uncached) and warm (cached) images |
| `sandbox_scale` | Parallel creation at 2x, 4x, 8x concurrency |

## Adding a New Task

Create `benchmarks/tasks/my_task.py`, subclass `BenchmarkTask`:

```python
from benchmarks.tasks.base import BenchmarkTask, Measurement, measure

class MyTask(BenchmarkTask):
    name = "my_task"
    description = "What this measures"

    def setup(self, ctx):
        pass

    def run(self, ctx, iteration):
        m, result = measure("operation name", lambda: do_something())
        return [m]

    def teardown(self, ctx):
        pass
```

Add to `ALL_TASKS` in `benchmarks/runner.py`.

## Results

JSON results saved to `benchmarks/results/<provider>/<timestamp>.json` (gitignored).
