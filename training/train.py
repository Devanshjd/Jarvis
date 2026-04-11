# JARVIS AI — LoRA Fine-Tuning Script
# Uses PEFT + TRL for parameter-efficient fine-tuning
# Supports: Gemma, Llama, Mistral, Phi base models

import os
import json
import torch
from pathlib import Path
from datetime import datetime


def train(config_path: str):
    """Run LoRA fine-tuning from a config file."""

    # ─── Load Config ───
    with open(config_path) as f:
        config = json.load(f)

    model_name = config["model_name"]
    output_dir = config["output_dir"]
    lora_config = config["lora"]
    train_config = config["training"]

    print(f"\n{'='*60}")
    print(f"  JARVIS LoRA Training")
    print(f"  Model: {model_name}")
    print(f"  Stage: {config['stage']}")
    print(f"  Output: {output_dir}")
    print(f"{'='*60}\n")

    # ─── Imports ───
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        TrainingArguments,
        BitsAndBytesConfig,
    )
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from trl import SFTTrainer
    from datasets import load_dataset, concatenate_datasets, Dataset

    # ─── Load Training Data ───
    print("📦 Loading training data...")
    data_dir = Path("datasets") / config["stage"]
    all_data = []

    # Load processed data if available
    processed_dir = Path("processed") / config["stage"]
    if processed_dir.exists():
        for f in processed_dir.glob("*.json"):
            with open(f) as fh:
                entries = json.load(fh)
                all_data.extend(entries)
            print(f"  Loaded {len(entries)} entries from {f.name}")

    if not all_data:
        # Try loading directly from HuggingFace
        for ds_name in config["data"]["datasets"]:
            try:
                from pipeline import DATASETS
                stage_datasets = DATASETS.get(config["stage"], [])
                ds_info = next((d for d in stage_datasets if d["name"] == ds_name), None)
                if ds_info:
                    print(f"  Loading {ds_name} from HuggingFace...")
                    ds = load_dataset(ds_info["hf_id"], split="train")
                    max_samples = config["data"].get("max_samples_per_dataset", 50000)
                    if len(ds) > max_samples:
                        ds = ds.shuffle(seed=42).select(range(max_samples))

                    for row in ds:
                        entry = {}
                        if "instruction" in row and "output" in row:
                            entry = {"instruction": row["instruction"], "input": row.get("input", ""), "output": row["output"]}
                        elif "question" in row and "answer" in row:
                            entry = {"instruction": row["question"], "input": "", "output": row["answer"]}
                        elif "prompt" in row and "response" in row:
                            entry = {"instruction": row["prompt"], "input": "", "output": row["response"]}
                        elif "text" in row:
                            entry = {"instruction": "Continue:", "input": "", "output": str(row["text"])[:2000]}
                        if entry:
                            all_data.append(entry)
                    print(f"  ✅ {ds_name}: {len(ds)} entries")
            except Exception as e:
                print(f"  ⚠️ {ds_name}: {e}")

    if not all_data:
        print("❌ No training data found. Run 'python pipeline.py download' first.")
        return

    print(f"\n📊 Total training entries: {len(all_data):,}")

    # ─── Format as chat template ───
    def format_entry(entry):
        instruction = entry.get("instruction", "")
        inp = entry.get("input", "")
        output = entry.get("output", "")

        if inp:
            text = f"### Instruction:\n{instruction}\n\n### Input:\n{inp}\n\n### Response:\n{output}"
        else:
            text = f"### Instruction:\n{instruction}\n\n### Response:\n{output}"
        return {"text": text}

    formatted = [format_entry(e) for e in all_data]
    dataset = Dataset.from_list(formatted)

    # Split into train/eval
    split = dataset.train_test_split(test_size=0.05, seed=42)
    train_dataset = split["train"]
    eval_dataset = split["test"]
    print(f"  Train: {len(train_dataset):,}  Eval: {len(eval_dataset):,}\n")

    # ─── Load Model (4-bit quantized) ───
    print(f"🧠 Loading model: {model_name}...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)

    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # ─── LoRA Config ───
    print("🔧 Applying LoRA adapter...")
    peft_config = LoraConfig(
        r=lora_config["r"],
        lora_alpha=lora_config["lora_alpha"],
        lora_dropout=lora_config["lora_dropout"],
        target_modules=lora_config["target_modules"],
        task_type=lora_config["task_type"],
        bias="none",
    )
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()

    # ─── Training Arguments ───
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=train_config["num_epochs"],
        per_device_train_batch_size=train_config["per_device_batch_size"],
        gradient_accumulation_steps=train_config["gradient_accumulation_steps"],
        learning_rate=train_config["learning_rate"],
        warmup_ratio=train_config["warmup_ratio"],
        weight_decay=train_config["weight_decay"],
        fp16=train_config["fp16"],
        logging_steps=train_config["logging_steps"],
        save_steps=train_config["save_steps"],
        eval_steps=train_config["eval_steps"],
        eval_strategy="steps",
        save_total_limit=train_config["save_total_limit"],
        report_to="wandb" if config.get("wandb") else "none",
        run_name=config.get("wandb", {}).get("run_name", "jarvis-training"),
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
    )

    # ─── Trainer ───
    print("\n🚀 Starting training...\n")
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
        max_seq_length=train_config["max_seq_length"],
    )

    # Train!
    trainer.train()

    # ─── Save ───
    print(f"\n💾 Saving model to {output_dir}...")
    trainer.save_model()
    tokenizer.save_pretrained(output_dir)

    # Save training log
    log = {
        "model": model_name,
        "stage": config["stage"],
        "total_entries": len(all_data),
        "train_entries": len(train_dataset),
        "eval_entries": len(eval_dataset),
        "completed_at": datetime.now().isoformat(),
        "output_dir": output_dir,
    }
    log_path = Path("logs") / f"training_{config['stage']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)

    print(f"\n✅ Training complete!")
    print(f"  Model saved: {output_dir}")
    print(f"  Log saved: {log_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="JARVIS LoRA Fine-Tuning")
    parser.add_argument("--config", type=str, required=True, help="Path to training config JSON")
    args = parser.parse_args()
    train(args.config)
