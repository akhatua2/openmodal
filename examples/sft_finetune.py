"""SFT finetuning with Unsloth on OpenModal.

Finetunes Qwen3-4B with LoRA on a single GPU using Unsloth's optimizations.

Usage:
    openmodal run examples/sft_finetune.py
    openmodal run examples/sft_finetune.py --max-steps 1000 --model-name unsloth/Qwen3-4B
"""

import pathlib
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import openmodal

app = openmodal.App("sft-finetune")

import os

train_image = (
    openmodal.Image.debian_slim()
    .uv_pip_install(
        "accelerate==1.9.0",
        "datasets==3.6.0",
        "hf-transfer==0.1.9",
        "huggingface_hub==0.34.2",
        "peft==0.16.0",
        "transformers==4.54.0",
        "trl==0.19.1",
        "unsloth[cu128-torch270]==2025.7.8",
        "unsloth_zoo==2025.7.10",
    )
    .env({"HF_HOME": "/model_cache"})
    .pip_install("wandb==0.21.0")
)

model_cache = openmodal.Volume.from_name("sft-model-cache", create_if_missing=True)
dataset_cache = openmodal.Volume.from_name("sft-dataset-cache", create_if_missing=True)
checkpoints = openmodal.Volume.from_name("sft-checkpoints", create_if_missing=True)

LORA_TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]


@dataclass
class TrainingConfig:
    model_name: str = "unsloth/Qwen3-4B"
    dataset_name: str = "mlabonne/FineTome-100k"
    max_seq_length: int = 8192
    load_in_4bit: bool = True
    lora_r: int = 16
    lora_alpha: int = 16
    lora_dropout: float = 0.0
    optim: str = "adamw_8bit"
    batch_size: int = 8
    gradient_accumulation_steps: int = 2
    packing: bool = False
    learning_rate: float = 2e-4
    lr_scheduler_type: str = "cosine"
    warmup_ratio: float = 0.06
    weight_decay: float = 0.01
    max_steps: int = 5
    save_steps: int = 2
    eval_steps: int = 2
    logging_steps: int = 1
    seed: int = 42
    experiment_name: Optional[str] = None

    def __post_init__(self):
        if self.experiment_name is None:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            model_short = self.model_name.split("/")[-1]
            self.experiment_name = f"{model_short}-r{self.lora_r}-{timestamp}"


import os
wandb_secret = openmodal.Secret.from_dict({"WANDB_API_KEY": os.environ.get("WANDB_API_KEY", "")})

@app.function(
    image=train_image,
    gpu="H100",
    volumes={
        "/model_cache": model_cache,
        "/dataset_cache": dataset_cache,
        "/checkpoints": checkpoints,
    },
    secrets=[wandb_secret],
    timeout=6 * 60 * 60,
    retries=3,
)
def finetune(config: TrainingConfig):
    import os
    import unsloth  # noqa: F401
    import datasets
    import wandb

    if os.environ.get("WANDB_API_KEY"):
        wandb.init(
            project="openmodal-sft",
            name=config.experiment_name,
            config=config.__dict__,
        )
    import torch
    from transformers import TrainingArguments
    from trl import SFTTrainer
    from unsloth import FastLanguageModel
    from unsloth.chat_templates import standardize_sharegpt

    print(f"Starting experiment: {config.experiment_name}")
    print(f"Model: {config.model_name}")
    print(f"GPU: {torch.cuda.get_device_name()}")

    # Load model
    print("Loading model...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=config.model_name,
        max_seq_length=config.max_seq_length,
        dtype=None,
        load_in_4bit=config.load_in_4bit,
    )

    # Configure LoRA
    print("Configuring LoRA...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=config.lora_r,
        target_modules=LORA_TARGET_MODULES,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=config.seed,
    )

    # Load and process dataset
    dataset_cache_path = pathlib.Path("/dataset_cache") / config.dataset_name.replace("/", "--")

    if dataset_cache_path.exists():
        print(f"Loading cached dataset...")
        train_dataset = datasets.load_from_disk(dataset_cache_path / "train")
        eval_dataset = datasets.load_from_disk(dataset_cache_path / "eval")
    else:
        print(f"Downloading dataset: {config.dataset_name}")
        dataset = datasets.load_dataset(config.dataset_name, split="train")
        dataset = standardize_sharegpt(dataset)
        dataset = dataset.train_test_split(test_size=0.1, seed=config.seed)

        def format_chat(examples):
            return {"text": [
                tokenizer.apply_chat_template(conv, tokenize=False, add_generation_prompt=False)
                for conv in examples["conversations"]
            ]}

        train_dataset = dataset["train"].map(format_chat, batched=True, num_proc=2, remove_columns=dataset["train"].column_names)
        eval_dataset = dataset["test"].map(format_chat, batched=True, num_proc=2, remove_columns=dataset["test"].column_names)

        dataset_cache_path.mkdir(parents=True, exist_ok=True)
        train_dataset.save_to_disk(dataset_cache_path / "train")
        eval_dataset.save_to_disk(dataset_cache_path / "eval")

    # Train
    checkpoint_path = pathlib.Path("/checkpoints") / config.experiment_name
    checkpoint_path.mkdir(parents=True, exist_ok=True)

    existing = list(checkpoint_path.glob("checkpoint-*"))
    resume_from = str(max(existing, key=lambda p: int(p.name.split("-")[1]))) if existing else None

    print(f"Train: {len(train_dataset):,} examples, Eval: {len(eval_dataset):,} examples")
    print(f"Trainable params: {sum(p.numel() for p in model.parameters() if p.requires_grad):,}")

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        dataset_text_field="text",
        max_seq_length=config.max_seq_length,
        packing=config.packing,
        args=TrainingArguments(
            per_device_train_batch_size=config.batch_size,
            gradient_accumulation_steps=config.gradient_accumulation_steps,
            learning_rate=config.learning_rate,
            max_steps=config.max_steps,
            warmup_ratio=config.warmup_ratio,
            eval_steps=config.eval_steps,
            save_steps=config.save_steps,
            eval_strategy="steps",
            save_strategy="steps",
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            optim=config.optim,
            weight_decay=config.weight_decay,
            lr_scheduler_type=config.lr_scheduler_type,
            logging_steps=config.logging_steps,
            output_dir=str(checkpoint_path),
            seed=config.seed,
        ),
    )

    if resume_from:
        print(f"Resuming from {resume_from}")
        trainer.train(resume_from_checkpoint=resume_from)
    else:
        print("Training from scratch...")
        trainer.train()

    # Save
    final_path = checkpoint_path / "final_model"
    model.save_pretrained(final_path)
    tokenizer.save_pretrained(final_path)
    print(f"Done! Model saved to {final_path}")
    return config.experiment_name


@app.local_entrypoint()
def main(
    model_name: str = "unsloth/Qwen3-4B",
    dataset_name: str = "mlabonne/FineTome-100k",
    max_steps: int = 5,
    lora_r: int = 16,
    batch_size: int = 8,
    learning_rate: float = 2e-4,
):
    config = TrainingConfig(
        model_name=model_name,
        dataset_name=dataset_name,
        max_steps=max_steps,
        lora_r=lora_r,
        batch_size=batch_size,
        learning_rate=learning_rate,
    )
    print(f"Launching: {config.experiment_name}")
    print(f"Model: {config.model_name}, Steps: {config.max_steps}, LoRA r={config.lora_r}")
    name = finetune.remote(config)
    print(f"Completed: {name}")
