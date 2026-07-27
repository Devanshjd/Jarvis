"""
J.A.R.V.I.S — Model Scheduler  (honest VRAM policy for the one-GPU relay)

8 GB of VRAM holds one big model at a time, so the crew is a relay, not a
roundtable. This scheduler makes that honest and efficient:

  · Residents  — tiny models (Vision's moondream, the embedder) stay loaded
                 alongside the active big model.
  · One slot   — the remaining VRAM holds ONE of {gemma, qwen, Foundation-Sec}.
                 A model bigger than the slot "spills" to CPU (slow — flagged).
  · Batching   — reorders pending work so same-model tasks run together,
                 minimising the (few-second) model swaps. Doing all of ULTRON's
                 tasks before swapping to FRIDAY is the whole game.

Pure policy/planning — no model I/O here; the runtime executes the plan and
sets Ollama keep_alive. Tunable to the box via VRAM_BUDGET_GB.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

VRAM_BUDGET_GB = 8.0          # RTX 4060 Laptop
RESIDENT_MAX_GB = 2.0         # models this small stay resident


@dataclass
class ModelSpec:
    name: str
    vram_gb: float

    @property
    def resident(self) -> bool:
        return self.vram_gb <= RESIDENT_MAX_GB


# Footprints for the models on this box (approx, Q-quantised).
MODELS: dict[str, ModelSpec] = {
    "gemma3:4b": ModelSpec("gemma3:4b", 3.3),
    "qwen2.5-coder:7b": ModelSpec("qwen2.5-coder:7b", 4.7),
    "axonvertex/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0_24K":
        ModelSpec("Foundation-Sec-8B", 8.5),
    "moondream:latest": ModelSpec("moondream", 1.7),
    "nomic-embed-text:latest": ModelSpec("nomic-embed", 0.3),
}


@dataclass
class Task:
    agent: str
    model: str


@dataclass
class Step:
    task: Task
    swap: bool = False        # did the big-model slot change for this step?
    spill: bool = False       # does this model exceed the free slot (CPU spill)?
    note: str = ""


class ModelScheduler:
    def __init__(self, budget_gb: float = VRAM_BUDGET_GB) -> None:
        self.budget = budget_gb
        self.active: Optional[str] = None      # current big-slot model

    # ── footprint helpers ────────────────────────────────────────────────
    def _spec(self, model: str) -> ModelSpec:
        return MODELS.get(model, ModelSpec(model, 5.0))

    def resident_load(self) -> float:
        return sum(m.vram_gb for m in MODELS.values() if m.resident)

    def free_slot(self) -> float:
        return self.budget - self.resident_load()

    def spills(self, model: str) -> bool:
        s = self._spec(model)
        return (not s.resident) and s.vram_gb > self.free_slot()

    # ── the plan ─────────────────────────────────────────────────────────
    def plan(self, tasks: list[Task]) -> list[Step]:
        """Reorder tasks to minimise big-model swaps. Resident-model tasks
        (moondream/embed) run in place — they never cause a swap. Non-resident
        tasks are grouped by model, keeping the currently-active model first to
        avoid an opening swap."""
        resident = [t for t in tasks if self._spec(t.model).resident]
        big = [t for t in tasks if not self._spec(t.model).resident]

        # Group big tasks by model, active model first.
        order: list[str] = []
        for t in big:
            if t.model not in order:
                order.append(t.model)
        if self.active in order:
            order.remove(self.active)
            order.insert(0, self.active)

        steps: list[Step] = []
        cur = self.active
        for model in order:
            for t in [x for x in big if x.model == model]:
                swap = (model != cur)
                steps.append(Step(t, swap=swap, spill=self.spills(model),
                                  note="swap" if swap else "warm"))
                cur = model
        self.active = cur
        # Resident tasks can slot in anywhere without a swap — append them.
        for t in resident:
            steps.append(Step(t, swap=False, spill=False, note="resident"))
        return steps

    @staticmethod
    def swap_count(steps: list[Step]) -> int:
        return sum(1 for s in steps if s.swap)


def _demo() -> None:
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sch = ModelScheduler()

    print("=" * 66)
    print(" MODEL SCHEDULER")
    print("=" * 66)
    print(f"\n  VRAM budget {sch.budget} GB  |  residents {sch.resident_load():.1f} GB"
          f"  |  free slot {sch.free_slot():.1f} GB")
    print("  spill check: Foundation-Sec-8B spills to CPU? "
          f"{sch.spills('axonvertex/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0_24K')}")

    U = "axonvertex/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0_24K"
    F = "qwen2.5-coder:7b"
    V = "moondream:latest"
    jumbled = [Task("ULTRON", U), Task("FRIDAY", F), Task("ULTRON", U),
               Task("VISION", V), Task("FRIDAY", F), Task("ULTRON", U)]

    naive_swaps = 0
    prev = None
    for t in jumbled:
        if not MODELS[t.model].resident and t.model != prev:
            naive_swaps += 1
            prev = t.model
    steps = sch.plan(jumbled)

    print(f"\n  jumbled order swaps (naive): {naive_swaps}")
    print("  scheduled order:")
    for s in steps:
        tag = " [SWAP]" if s.swap else ("" if s.note == "resident" else " [warm]")
        spill = " (spills->CPU, slow)" if s.spill else ""
        print(f"    {s.task.agent:<7} {MODELS[s.task.model].name}{tag}{spill}")
    print(f"\n  scheduled swaps: {sch.swap_count(steps)}  "
          f"(saved {naive_swaps - sch.swap_count(steps)})")


if __name__ == "__main__":
    _demo()
