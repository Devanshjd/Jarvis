# JARVIS AI Training Infrastructure
# This script downloads, preprocesses, and organizes training datasets
# for fine-tuning the JARVIS model.

import os
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# ═══════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════

TRAINING_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = TRAINING_DIR / "datasets"
PROCESSED_DIR = TRAINING_DIR / "processed"
CONFIGS_DIR = TRAINING_DIR / "configs"
LOGS_DIR = TRAINING_DIR / "logs"

# Create directories
for d in [DATA_DIR, PROCESSED_DIR, CONFIGS_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════
# Dataset Registry — Complete 4-Stage Pipeline
# ═══════════════════════════════════════════════════════════════

DATASETS = {
    # ─── Stage 1: Foundation (Pre-training) ───
    "stage1_foundation": [
        {
            "name": "FineWeb-Edu",
            "hf_id": "HuggingFaceFW/finewebedu",
            "subset": "sample-10BT",
            "description": "High-quality educational web text for broad language understanding",
            "size_gb": 12,
            "priority": "HIGH"
        },
        {
            "name": "Open-Web-Math",
            "hf_id": "open-web-math/open-web-math",
            "description": "Mathematical content from the web for numerical fluency",
            "size_gb": 8,
            "priority": "HIGH"
        },
        {
            "name": "The-Stack-v2-Dedup",
            "hf_id": "bigcode/the-stack-v2-dedup",
            "subset": "Python",
            "description": "Deduplicated source code for code comprehension",
            "size_gb": 20,
            "priority": "MEDIUM"
        },
    ],

    # ─── Stage 2: Instruction Tuning (SFT) ───
    "stage2_sft": [
        {
            "name": "SlimOrca",
            "hf_id": "Open-Orca/SlimOrca",
            "description": "518K GPT-4 traces — general reasoning",
            "size_gb": 1.2,
            "priority": "HIGH"
        },
        {
            "name": "OpenThoughts-114k",
            "hf_id": "open-thoughts/OpenThoughts-114k",
            "description": "Chain-of-thought reasoning traces",
            "size_gb": 0.5,
            "priority": "HIGH"
        },
        {
            "name": "CodeFeedback-157K",
            "hf_id": "m-a-p/CodeFeedback-Filtered-Instruction",
            "description": "Code instruction-response pairs",
            "size_gb": 0.8,
            "priority": "HIGH"
        },
        {
            "name": "Cybersecurity-Dataset-v1",
            "hf_id": "Canstralian/CyberSecurityDataset-v1",
            "description": "Cybersecurity domain knowledge",
            "size_gb": 0.3,
            "priority": "HIGH"
        },
        {
            "name": "SecGPT",
            "hf_id": "Clouditera/SecGPT",
            "description": "Security-focused instruction tuning",
            "size_gb": 0.4,
            "priority": "MEDIUM"
        },
    ],

    # ─── Stage 3: Domain Specialization ───
    "stage3_domain": [
        {
            "name": "Massive-1.2M-Cyber",
            "hf_id": "thekyungcheolkim/Massive-1.2M-Cyber",
            "description": "1.2M cybersecurity entries for deep domain knowledge",
            "size_gb": 2.5,
            "priority": "HIGH"
        },
        {
            "name": "MathInstruct",
            "hf_id": "TIGER-Lab/MathInstruct",
            "description": "Mathematical problem-solving instruction",
            "size_gb": 0.6,
            "priority": "MEDIUM"
        },
        {
            "name": "CTF-Dojo",
            "hf_id": "zgimszhd61/CTF-Dojo",
            "description": "Capture the Flag challenges for offensive security reasoning",
            "size_gb": 0.2,
            "priority": "MEDIUM"
        },
    ],

    # ─── Stage 4: Alignment (RLHF/DPO) ───
    "stage4_alignment": [
        {
            "name": "OpenAssistant-OASST2",
            "hf_id": "OpenAssistant/oasst2",
            "description": "Human feedback data for alignment",
            "size_gb": 0.4,
            "priority": "HIGH"
        },
        {
            "name": "UltraChat-200K",
            "hf_id": "HuggingFaceH4/ultrachat_200k",
            "description": "200K high-quality conversations for chat quality",
            "size_gb": 1.0,
            "priority": "HIGH"
        },
        {
            "name": "WildChat-1M",
            "hf_id": "allenai/WildChat-1M",
            "description": "1M real-world conversations for robustness",
            "size_gb": 3.5,
            "priority": "MEDIUM"
        },
    ],
}


# ═══════════════════════════════════════════════════════════════
# Download Functions
# ═══════════════════════════════════════════════════════════════

def check_huggingface_cli():
    """Check if huggingface-cli is installed."""
    try:
        subprocess.run(["huggingface-cli", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def install_dependencies():
    """Install required Python packages."""
    packages = [
        "datasets",
        "transformers",
        "torch",
        "accelerate",
        "peft",
        "trl",
        "bitsandbytes",
        "huggingface_hub",
        "wandb",
        "sentencepiece",
    ]
    print("📦 Installing training dependencies...")
    for pkg in packages:
        print(f"  Installing {pkg}...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg, "-q"],
            capture_output=True
        )
    print("✅ Dependencies installed.\n")


def download_dataset(dataset_info: dict, stage: str):
    """Download a single dataset from HuggingFace."""
    name = dataset_info["name"]
    hf_id = dataset_info["hf_id"]
    subset = dataset_info.get("subset")
    target_dir = DATA_DIR / stage / name.replace(" ", "_")

    if target_dir.exists() and any(target_dir.iterdir()):
        print(f"  ⏭️  {name} already downloaded, skipping.")
        return True

    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"  📥 Downloading {name} ({hf_id})...")
    try:
        from datasets import load_dataset
        if subset:
            ds = load_dataset(hf_id, subset, split="train", cache_dir=str(target_dir))
        else:
            ds = load_dataset(hf_id, split="train", cache_dir=str(target_dir))

        # Save info
        info = {
            "name": name,
            "hf_id": hf_id,
            "subset": subset,
            "num_rows": len(ds),
            "columns": ds.column_names,
            "downloaded_at": datetime.now().isoformat(),
        }
        with open(target_dir / "info.json", "w") as f:
            json.dump(info, f, indent=2)

        print(f"  ✅ {name}: {len(ds):,} rows downloaded.")
        return True
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        return False


def download_stage(stage: str, priority_filter: str = None):
    """Download all datasets for a given training stage."""
    datasets = DATASETS.get(stage, [])
    if not datasets:
        print(f"❌ Unknown stage: {stage}")
        return

    print(f"\n{'='*60}")
    print(f"📦 Stage: {stage.upper()}")
    print(f"{'='*60}")

    for ds in datasets:
        if priority_filter and ds["priority"] != priority_filter:
            continue
        download_dataset(ds, stage)


def download_all(priority_filter: str = None):
    """Download all datasets across all stages."""
    for stage in DATASETS:
        download_stage(stage, priority_filter)


# ═══════════════════════════════════════════════════════════════
# Processing Functions
# ═══════════════════════════════════════════════════════════════

def process_to_jarvis_format(input_dir: Path, output_path: Path, max_samples: int = None):
    """Convert dataset to JARVIS instruction format: {instruction, input, output}."""
    try:
        from datasets import load_from_disk
        ds = load_from_disk(str(input_dir))
    except Exception:
        return False

    processed = []
    for i, row in enumerate(ds):
        if max_samples and i >= max_samples:
            break

        # Try common column mappings
        entry = {}
        if "instruction" in row and "output" in row:
            entry = {"instruction": row["instruction"], "input": row.get("input", ""), "output": row["output"]}
        elif "question" in row and "answer" in row:
            entry = {"instruction": row["question"], "input": "", "output": row["answer"]}
        elif "prompt" in row and "response" in row:
            entry = {"instruction": row["prompt"], "input": "", "output": row["response"]}
        elif "text" in row:
            entry = {"instruction": "Continue the following:", "input": "", "output": row["text"][:2000]}
        else:
            continue

        processed.append(entry)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)

    print(f"  ✅ Processed {len(processed)} entries → {output_path.name}")
    return True


# ═══════════════════════════════════════════════════════════════
# Training Config Generator
# ═══════════════════════════════════════════════════════════════

def generate_training_config(
    base_model: str = "google/gemma-2-2b-it",
    stage: str = "stage2_sft",
    output_name: str = "jarvis-v1"
):
    """Generate a LoRA fine-tuning config for the given stage."""

    config = {
        "model_name": base_model,
        "output_dir": f"./outputs/{output_name}_{stage}",
        "stage": stage,

        # LoRA config
        "lora": {
            "r": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.05,
            "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
            "task_type": "CAUSAL_LM"
        },

        # Training hyperparameters
        "training": {
            "num_epochs": 3,
            "per_device_batch_size": 4,
            "gradient_accumulation_steps": 4,
            "learning_rate": 2e-4,
            "warmup_ratio": 0.03,
            "weight_decay": 0.01,
            "max_seq_length": 2048,
            "fp16": True,
            "logging_steps": 10,
            "save_steps": 500,
            "eval_steps": 500,
            "save_total_limit": 3,
        },

        # Data
        "data": {
            "stage": stage,
            "datasets": [ds["name"] for ds in DATASETS.get(stage, [])],
            "max_samples_per_dataset": 50000,
        },

        # Wandb
        "wandb": {
            "project": "jarvis-training",
            "run_name": f"{output_name}_{stage}_{datetime.now().strftime('%Y%m%d')}",
        }
    }

    config_path = CONFIGS_DIR / f"{output_name}_{stage}.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"📋 Config saved: {config_path}")
    return config


# ═══════════════════════════════════════════════════════════════
# Status Report
# ═══════════════════════════════════════════════════════════════

def print_status():
    """Print the current status of all datasets and training stages."""
    print("\n" + "═" * 70)
    print("  JARVIS TRAINING PIPELINE STATUS")
    print("═" * 70)

    total_datasets = 0
    downloaded = 0
    total_size = 0

    for stage, datasets in DATASETS.items():
        print(f"\n📦 {stage.upper()}")
        print("─" * 50)
        for ds in datasets:
            total_datasets += 1
            total_size += ds["size_gb"]
            target = DATA_DIR / stage / ds["name"].replace(" ", "_")
            exists = target.exists() and any(target.iterdir()) if target.exists() else False
            status = "✅" if exists else "⬜"
            if status == "✅":
                downloaded += 1
            priority_badge = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(ds["priority"], "⚪")
            print(f"  {status} {priority_badge} {ds['name']:<30} {ds['size_gb']:>6.1f} GB  ({ds['hf_id']})")

    print(f"\n{'─' * 50}")
    print(f"  Downloaded: {downloaded}/{total_datasets} datasets")
    print(f"  Total size: ~{total_size:.1f} GB")
    print(f"  Data dir:   {DATA_DIR}")
    print("═" * 70)


# ═══════════════════════════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="JARVIS Training Pipeline")
    parser.add_argument("command", choices=["status", "install", "download", "process", "config", "all"],
                       help="Command to run")
    parser.add_argument("--stage", type=str, default=None,
                       help="Training stage (stage1_foundation, stage2_sft, stage3_domain, stage4_alignment)")
    parser.add_argument("--priority", type=str, default=None, choices=["HIGH", "MEDIUM", "LOW"],
                       help="Filter by priority")
    parser.add_argument("--model", type=str, default="google/gemma-2-2b-it",
                       help="Base model for training config")
    parser.add_argument("--name", type=str, default="jarvis-v1",
                       help="Output model name")

    args = parser.parse_args()

    if args.command == "status":
        print_status()

    elif args.command == "install":
        install_dependencies()

    elif args.command == "download":
        if args.stage:
            download_stage(args.stage, args.priority)
        else:
            download_all(args.priority)

    elif args.command == "config":
        stage = args.stage or "stage2_sft"
        generate_training_config(args.model, stage, args.name)

    elif args.command == "all":
        install_dependencies()
        download_all("HIGH")  # Start with HIGH priority only
        for stage in DATASETS:
            generate_training_config(args.model, stage, args.name)
        print_status()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
