# SFT finetuning with Unsloth

Finetune an LLM with LoRA on a single GPU using [Unsloth](https://github.com/unslothai/unsloth)'s optimized training.

## Run

```bash
openmodal run examples/sft_finetune.py
```

With custom settings:

```bash
openmodal run examples/sft_finetune.py --model-name unsloth/Qwen3-4B --max-steps 1000 --lora-r 32
```

## What it does

1. Provisions a GPU (H100 spot by default)
2. Downloads Qwen3-4B (4-bit quantized) and the FineTome-100k dataset
3. Applies LoRA adapters and trains with Unsloth's optimized kernels
4. Saves checkpoints and final model to persistent volumes
5. Auto-retries if the spot instance is preempted

## The code

```python
import openmodal

app = openmodal.App("sft-finetune")

train_image = (
    openmodal.Image.debian_slim()
    .uv_pip_install(
        "accelerate", "datasets", "peft",
        "transformers", "trl",
        "unsloth[cu128-torch270]",
    )
    .env({"HF_HOME": "/model_cache"})
)

model_cache = openmodal.Volume.from_name("sft-model-cache", create_if_missing=True)
checkpoints = openmodal.Volume.from_name("sft-checkpoints", create_if_missing=True)

@app.function(
    image=train_image,
    gpu="H100",
    volumes={"/model_cache": model_cache, "/checkpoints": checkpoints},
    timeout=6 * 60 * 60,
    retries=3,
)
def finetune(config):
    from unsloth import FastLanguageModel
    from trl import SFTTrainer

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=config.model_name,
        load_in_4bit=True,
    )
    # ... LoRA setup, dataset loading, training ...
    trainer.train()
    model.save_pretrained("/checkpoints/final_model")

@app.local_entrypoint()
def main(model_name="unsloth/Qwen3-4B", max_steps=5):
    finetune.remote(TrainingConfig(model_name=model_name, max_steps=max_steps))
```

## Features used

| Feature | How it's used |
|---|---|
| `gpu="H100"` | Single GPU for training |
| `Volume.from_name(create_if_missing=True)` | Persistent storage for model weights and checkpoints |
| `retries=3` | Auto-retry on spot preemption |
| `timeout=6*60*60` | 6 hour max training time |
| `finetune.remote(config)` | Runs training on the GPU |
| CLI args (`--max-steps`, `--lora-r`) | Tweak hyperparameters from command line |
