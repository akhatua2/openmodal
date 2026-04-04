# Running CooperBench with OpenModal

Run [CooperBench](https://github.com/cooperbench/CooperBench) multi-agent coding benchmarks using OpenModal as the compute backend — on your own GCP, AWS, or local Docker.

## How it works

CooperBench spawns coding agents (2 per task in coop mode) inside sandboxed containers. Each agent gets a Docker image with a codebase and implements a feature. The agents can message each other to coordinate.

OpenModal replaces Modal as the sandbox provider with **one line change**:

```python
# In coopertrain/agents/mini_swe_agent_v2/environments/modal.py
# before
import modal
# after
import openmodal as modal
```

Everything else — `modal.Sandbox.create()`, `sandbox.exec()`, `sandbox.terminate()`, `modal.Image.from_registry()`, `modal.App.lookup()` — works identically.

## Setup

```bash
# Install OpenModal
pip install openmodal

# Clone CooperBench / CooperTrain
git clone https://github.com/cooperbench/CooperBench.git
cd CooperTrain

# Swap the import
sed -i 's/import modal/import openmodal as modal/' \
  coopertrain/agents/mini_swe_agent_v2/environments/modal.py
```

## Run (local Docker)

```bash
OPENMODAL_PROVIDER=local cooperbench run \
  --setting coop \
  -r dspy_task -t 8563 -f 1,2 \
  -m gpt-4.1-mini \
  -a mini_swe_agent_v2_train \
  --no-auto-eval
```

## Run (GCP)

```bash
# Setup GKE cluster (one-time)
openmodal setup

# Run on GKE
cooperbench run \
  --setting coop \
  -r dspy_task -t 8563 -f 1,2 \
  -m gpt-4.1-mini \
  -a mini_swe_agent_v2_train \
  --no-auto-eval
```

## Run (AWS)

```bash
# Setup EKS cluster (one-time)
openmodal setup

# Run on EKS
OPENMODAL_PROVIDER=aws cooperbench run \
  --setting coop \
  -r dspy_task -t 8563 -f 1,2 \
  -m gpt-4.1-mini \
  -a mini_swe_agent_v2_train \
  --no-auto-eval
```

## Example results

```
  agent     feature    status        cost    steps    lines
  agent1    1          Submitted    $0.03       31       74
  agent2    2          Submitted    $0.07       35      462

total: $0.10 time: 464s
```

## Solo mode

Run a single agent on multiple features:

```bash
cooperbench run \
  --setting solo \
  -r dspy_task -t 8563 -f 1,2 \
  -m gpt-4.1-mini \
  -a mini_swe_agent_v2_train \
  --no-auto-eval
```

## Full benchmark suite

Run all tasks in the lite subset:

```bash
cooperbench run \
  --setting coop \
  -s lite \
  -m gpt-4.1-mini \
  -a mini_swe_agent_v2_train \
  -c 20
```

## How it compares to Modal

| | Modal | OpenModal |
|---|---|---|
| Import | `import modal` | `import openmodal as modal` |
| Infrastructure | Modal's cloud | Your GCP / AWS / local Docker |
| Cost | Modal pricing | Your cloud costs only |
| Code changes | None | One line |
