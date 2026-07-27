"""
J.A.R.V.I.S — Vault Seed

Teaches JARVIS how it is being built. Writes the architecture, the real
decisions (with the numbers behind them), and a starter free dataset into the
knowledge vault so JARVIS can RECALL them — a persistent, correctable record of
its own design, not chatter.

Run:  python -m core.vault_seed        (from repo root)
      python core/vault_seed.py
"""
from __future__ import annotations

import io
import sys

try:
    from core.vault import Vault
except ImportError:
    from vault import Vault


# (folder, title, tags, body) — real content from how JARVIS is being built.
BUILD_KNOWLEDGE: list[tuple[str, str, list[str], str]] = [
    ("Architecture", "Multi-Agent Team", ["architecture", "agents"],
     "JARVIS leads a crew of named specialists, each a different brain + toolkit "
     "(not a persona in a mask):\n\n"
     "- **JARVIS** — orchestrator/all-rounder, gemma3:4b, always warm. Routes and "
     "dispatches; the hard reasoning is delegated.\n"
     "- **ULTRON** — cybersecurity, Foundation-Sec-8B. See [[Security Model - Foundation-Sec-8B]].\n"
     "- **FRIDAY** — code/dev, qwen2.5-coder:7b, Code Oracle.\n"
     "- **VISION** — perception, moondream, screen/face/gesture.\n"
     "- **EDITH** — improvement & oversight. See [[EDITH Improvement Loop]].\n\n"
     "They communicate through a hub + shared blackboard, never a direct mesh. A "
     "specialist requests another via a handoff, mediated by JARVIS. On 8GB VRAM "
     "the team is a relay (one model at a time), not a parallel roundtable."),

    ("Architecture", "EDITH Improvement Loop", ["architecture", "self-improvement"],
     "EDITH watches the team, learns from mistakes, and drafts upgrades — then "
     "**proves them in the sandbox before keeping them**. It is NOT fully "
     "autonomous (see [[Self-Improvement is Human-Gated]]).\n\n"
     "Loop: watch -> propose -> apply to an isolated copy -> run the sandbox "
     "harness -> decide.\n"
     "- Green tier (lessons, prompts, routing weights, config, vault notes): "
     "auto-apply after a sandbox pass.\n"
     "- Red tier (code with system access, safety gates, the sandbox itself): "
     "always human-gated, even if the sandbox passes.\n\n"
     "Un-gameable rule: EDITH can never edit the sandbox or its tests, holds out "
     "tasks it can't see, and any change that lowers a metric escalates instead "
     "of applying. Everything is logged to this vault and one-click revertible."),

    ("Architecture", "Escalation Ladder", ["architecture", "escalation", "privacy"],
     "When stuck, JARVIS climbs only as far as it must; the human is the LAST rung:\n\n"
     "1. Local specialist takes the task.\n"
     "2. EDITH self-fixes — sandbox, retry N times.\n"
     "3. Private web search (SearXNG) the error — free, minimal leak.\n"
     "4. Cloud frontier (Claude / GPT) reasons it out — OPT-IN only.\n"
     "5. You. 'I need you for this one.'\n\n"
     "Before anything reaches rung 4 it passes a privacy scrubber (Presidio + "
     "gitleaks): PII redacted, secrets blocked, only a minimal generic question "
     "leaves the box. Cloud advises; the sandbox and human gates still decide. A "
     "hard budget cap prevents runaway spend. Local-first is the founding value."),

    ("Architecture", "Memory Vault", ["architecture", "memory", "obsidian"],
     "This vault is JARVIS's durable, human-browsable brain — the persistent form "
     "of the blackboard. Loop: capture a decision/finding, recall it later, "
     "correct it by hand in Obsidian. It makes JARVIS's memory auditable.\n\n"
     "Split of labour: the vault holds durable, human-relevant knowledge; the "
     "SQLite/vector store holds ephemeral state and the search index built FROM "
     "the vault. Semantic recall (sqlite-vec) layers on top of keyword recall."),

    ("Decisions", "Model Choice - keep JARVIS 4b", ["decision", "models"],
     "**Decision:** keep the JARVIS orchestrator on gemma3:4b. Do not upsize.\n\n"
     "**Why:** measured on the 23-task security battery, bigger did NOT help — "
     "gemma3:12b scored the same 82% as 4b, and qwen2.5-coder:7b scored 65%. The "
     "orchestrator's job is routing + conversation + dispatch; the hard reasoning "
     "is delegated to specialists, so it doesn't need to be big. An 8b always-"
     "resident orchestrator also tightens the 8GB VRAM budget and worsens "
     "specialist swapping. Test-don't-assume if its conversation ever feels weak."),

    ("Decisions", "Security Model - Foundation-Sec-8B", ["decision", "security", "models"],
     "**Decision:** ULTRON uses Cisco's Foundation-Sec-8B (continued-pretrained on "
     "CVE/CWE/MITRE) as an opt-in specialist (JARVIS_SECURITY_MODEL=1).\n\n"
     "**Why:** it is the most accurate local security model measured — 86% overall "
     "and 100% on the hard tier, beating the 82% general models on multi-part "
     "reasoning (SSRF chains, privesc, XXE). Trade-off: slow (~45s, up to 130s) "
     "because Q8 spills past 8GB VRAM. So it's 'call in the analyst', not the "
     "always-on default. Specialization beat size. See [[Deterministic tools beat bigger models]]."),

    ("Decisions", "SAST - Bandit over Semgrep", ["decision", "security", "tools"],
     "**Decision:** use Bandit for static code-vuln scanning, not Semgrep.\n\n"
     "**Why:** Semgrep has no native Windows engine — its scan failed on this box. "
     "Bandit is pure-Python, runs natively on Windows/py3.13, and Python is what "
     "JARVIS's own code and FRIDAY's work are written in. Proven to catch command "
     "injection (CWE-78), SQLi (CWE-89), weak hash (CWE-327), hardcoded secret "
     "(CWE-259). Semgrep left as a later hook for multi-language via WSL/Docker."),

    ("Decisions", "No 27B on this box", ["decision", "hardware"],
     "**Decision:** do not run 27B+ models locally. Ceiling on this machine is "
     "~12-14B.\n\n**Why:** the box is an RTX 4060 Laptop (8GB VRAM) with 15.6GB "
     "system RAM. A 27B (Q4 ~17GB) exceeds total memory — it won't load, or swaps "
     "to disk at minutes-per-token. 32GB RAM would let it LOAD but not run fast; "
     "the 8GB VRAM is the real cap and can't be upgraded on a laptop. Fast big "
     "models are a desktop-GPU decision, not a RAM one."),

    ("Security", "Security Proficiency", ["security", "measurement"],
     "JARVIS's security-analyst reasoning is measured honestly by the sandbox "
     "harness (training/security_harness.py): mid/high/expert tasks verified "
     "against objective criteria, 0 false positives. Default gemma3:4b scores 82% "
     "(19/23); Foundation-Sec-8B scores 86% (100% on the hard tier). It measures "
     "recon/triage/analysis/remediation reasoning — NOT autonomous exploitation, "
     "which stays human-driven. Remaining gaps are precise-taxonomy recall, being "
     "closed with real tools (Bandit, and next the [[OWASP Top 10 2021]] / CWE data)."),

    ("Lessons", "Deterministic tools beat bigger models", ["lesson", "principle"],
     "The pattern proven repeatedly while building JARVIS: for anything with a "
     "correct algorithm or dataset, a real TOOL beats a bigger LLM.\n\n"
     "- CVSS scoring: LLM guessing (wrong) -> exact calculator (100%).\n"
     "- Code vulns: LLM guessing CWEs -> Bandit (real, cited findings).\n\n"
     "So the highest-leverage upgrades are tools and data (Semgrep/Bandit, CWE/"
     "OWASP datasets, sqlite-vec), not fancier models. Let the model REASON; pull "
     "exact facts from tools."),

    ("Lessons", "Self-Improvement is Human-Gated", ["lesson", "safety"],
     "JARVIS improves its own code only via propose -> sandbox-test -> human "
     "approve. Never fully autonomous. An autonomous self-modifier on an 8B model "
     "is a degradation spiral: a flawed change makes it worse, then it 'improves' "
     "from the worse baseline and errors compound. The sandbox is the automated "
     "gate; the human is the last line for anything risky or irreversible."),

    ("Projects", "Stormbreaker", ["project", "wearable", "hardware"],
     "Stormbreaker is the wearable spinoff: AR glasses (RayNeo/XReal display) + "
     "camera + mic + gesture, tethered by Wi-Fi to the PC 'backpack brain'. It "
     "does NOT get its own AI — it gets a window into this one. The whole crew "
     "([[Multi-Agent Team]]) stays on the PC; VISION processes the glasses' camera "
     "feed, JARVIS speaks to the HUD. Split-compute: heavy models on the PC, the "
     "glasses stay light. Same team, another I/O surface."),
]


OWASP_TOP10_2021 = (
    "A curated free dataset JARVIS can learn from — the OWASP Top 10 (2021), the "
    "ten most critical web-app security risks. Recall these when triaging web "
    "findings.\n\n"
    "1. **A01 Broken Access Control** — users acting outside their permissions "
    "(includes IDOR, CWE-639).\n"
    "2. **A02 Cryptographic Failures** — weak/missing crypto exposing data "
    "(weak hashes, plaintext, bad TLS).\n"
    "3. **A03 Injection** — untrusted input in a command/query (SQLi CWE-89, "
    "command injection CWE-78, XSS).\n"
    "4. **A04 Insecure Design** — missing security controls by design, not just "
    "a bug.\n"
    "5. **A05 Security Misconfiguration** — default creds, verbose errors, open "
    "cloud storage, missing headers.\n"
    "6. **A06 Vulnerable & Outdated Components** — known-CVE libraries/deps.\n"
    "7. **A07 Identification & Authentication Failures** — weak auth, session "
    "fixation, credential stuffing.\n"
    "8. **A08 Software & Data Integrity Failures** — unsigned updates, insecure "
    "deserialization (CWE-502).\n"
    "9. **A09 Security Logging & Monitoring Failures** — attacks go undetected.\n"
    "10. **A10 Server-Side Request Forgery (SSRF)** — server fetches an attacker "
    "URL (e.g. cloud metadata → IAM creds).\n\n"
    "Related: [[Security Proficiency]]. Next dataset to add: the full MITRE CWE "
    "catalogue for a deterministic CWE lookup."
)


def seed_all(vault: "Vault") -> int:
    vault.ensure()
    n = 0
    for folder, title, tags, body in BUILD_KNOWLEDGE:
        vault.write(folder, title, body, tags=tags, type="knowledge")
        n += 1
    vault.write("Datasets", "OWASP Top 10 2021", OWASP_TOP10_2021,
                tags=["dataset", "owasp", "security"], type="dataset")
    n += 1
    return n


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    v = Vault()
    count = seed_all(v)
    st = v.stats()
    print("=" * 62)
    print(" JARVIS KNOWLEDGE VAULT -- seeded")
    print("=" * 62)
    print(f"\n  location : {st['root']}")
    print(f"  seeded   : {count} notes")
    print(f"  total    : {st['notes']} notes, {st['links']} wikilinks")
    print(f"  folders  : " + ", ".join(f"{k}:{v_}" for k, v_ in st['folders'].items() if v_))

    print("\n  -- recall demo: 'why did we keep jarvis on 4b?' --")
    print("  " + v.recall("why did we keep jarvis on the 4b model", k=1).replace("\n", "\n  "))
    print("\n  -- recall demo: 'what is SSRF in owasp' --")
    print("  " + v.recall("SSRF server side request forgery owasp", k=1).replace("\n", "\n  "))
    print(f"\n  Open the folder in Obsidian as a vault to browse the graph.")


if __name__ == "__main__":
    main()
