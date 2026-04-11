# JARVIS Training Data

This project can now export task-learning data from JARVIS's live task brain.

## What gets exported

`training_data/jarvis_task_episodes.jsonl`
- Raw sanitized task episodes.
- Includes goal, chosen tool, safe args, status, attempts, and result summary.

`training_data/jarvis_task_planner_sft.jsonl`
- Planner-oriented SFT dataset.
- Each row contains `messages` with:
  - system instruction
  - user goal
  - assistant JSON target describing the tool choice and arguments

`training_data/jarvis_task_procedures.json`
- Learned procedure summaries per tool.
- Useful for analysis, routing rules, and future synthetic data generation.

`training_data/manifest.json`
- Export metadata and counts.

## Export options

Inside JARVIS:

```text
/dataset
/dataset export
```

From the terminal:

```powershell
python training/export_task_brain_dataset.py
python training/export_task_brain_dataset.py --output training_data
```

## Intended use

This dataset is best for:
- tool-routing fine-tuning
- planner fine-tuning
- procedure learning
- synthetic workflow expansion

It is not yet a full conversational training corpus for JARVIS voice/personality.

## Safety

The exporter sanitizes obvious secrets:
- passwords
- API keys
- tokens
- auth/session-like values

Even with redaction, review the generated files before using them for any training run.

## Recommended next step

After enough successful runs, use:
- raw episodes as the ground-truth log
- planner SFT as the first fine-tuning dataset
- procedures JSON to synthesize more operator examples
