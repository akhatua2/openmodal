# Running SWE-bench with Harbor

Run SWE-bench evaluations using [Harbor](https://harborframework.com) with OpenModal as the compute backend.

## Install

```bash
pip install "openmodal[harbor]"
```

## Run

```bash
harbor run \
  --agent mini-swe-agent \
  --model openai/gpt-5.4 \
  --environment-import-path openmodal.integrations.harbor_env:ModalEnvironment \
  --dataset swe-bench/swe-bench-verified \
  --n-tasks 1
```

This creates a sandbox, runs the agent against a SWE-bench task, verifies the patch, and reports results.

## What happens

1. Harbor downloads a SWE-bench task (e.g., a Django bug)
2. OpenModal creates a container with the task's Docker image
3. The agent runs inside the container — reads the bug, edits code, runs tests
4. Harbor uploads test files, runs verification, reports pass/fail
5. Container is cleaned up

## Options

**Different agents:**
```bash
harbor run --agent claude-code --model anthropic/claude-sonnet-4-5-20250929 \
  --environment-import-path openmodal.integrations.harbor_env:ModalEnvironment \
  --dataset swe-bench/swe-bench-verified --n-tasks 5

harbor run --agent openhands --model openai/gpt-5.4 \
  --environment-import-path openmodal.integrations.harbor_env:ModalEnvironment \
  --dataset swe-bench/swe-bench-verified --n-tasks 5
```

**Multiple attempts:**
```bash
harbor run --agent mini-swe-agent --model openai/gpt-5.4 \
  --environment-import-path openmodal.integrations.harbor_env:ModalEnvironment \
  --dataset swe-bench/swe-bench-verified --n-tasks 10 --n-attempts 3
```

**View results:**
```bash
harbor view jobs
```

## How it compares to Modal

With Modal:
```bash
harbor run --agent mini-swe-agent --env modal --dataset swe-bench/swe-bench-verified
```

With OpenModal:
```bash
harbor run --agent mini-swe-agent \
  --environment-import-path openmodal.integrations.harbor_env:ModalEnvironment \
  --dataset swe-bench/swe-bench-verified
```

Same agents, same datasets, same results — runs on your own infrastructure.
