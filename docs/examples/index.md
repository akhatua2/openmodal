# Examples

OpenModal is API-compatible with Modal. Replace `import modal` with `import openmodal` and everything works.

All examples work on both local Docker (`--local`) and GCP.

For hundreds of additional examples, see the [Modal examples gallery](https://modal.com/docs/examples).

## Getting started

- [Hello, world!](hello_world.md) — `f.local()`, `f.remote()`, `f.map()`
- [Web scraper](web_scraper.md) — custom images, async, parallel execution, CLI args

## GPU serving

- [vLLM serving](vllm_serving.md) — deploy an LLM on a GPU with auto scale-to-zero

## Sandboxes

- [Sandboxes](sandbox.md) — isolated containers for SWE agents, parallel execution

## Training

- [SFT finetuning](sft_finetune.md) — LoRA finetuning with Unsloth on a GPU

## Benchmarks

- [CooperBench](cooperbench.md) — run multi-agent coding benchmarks with OpenModal (one-line import swap)
- [SWE-bench with Harbor](harbor.md) — run SWE-bench evaluations with OpenModal as compute backend
