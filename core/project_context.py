"""
J.A.R.V.I.S — Project Context Preamble

Pulls relevant project decisions, learned skills, and bug patterns from
the knowledge graph and formats them as a preamble to be injected into
research / planning / chat prompts.

The problem this solves: JARVIS's research tool used to go straight to
its generic training knowledge and produce reports that ignored the
project's actual decisions (e.g. recommending an EOL chip after we'd
already locked the architecture). With this preamble, every research run
starts grounded in what the user has already decided.

Usage:
    from core.project_context import build_preamble

    preamble = build_preamble(query="goggles compute architecture")
    full_prompt = preamble + "\n\n" + research_query

The preamble is intentionally compact — typically 500-2000 chars — so
it doesn't blow the LLM context window. Pulls only the most relevant
entities matching the query.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger("jarvis.project_context")


# Entity types we consider "project context" — these get pulled into the preamble
_CONTEXT_ENTITY_TYPES = {
    "project_decision",       # locked-in architecture / scope decisions
    "bom_item",                # bill-of-materials parts with prices
    "architecture_component",  # a piece of the system we agreed on
    "learned_skill",           # past successful task patterns
    "bug_pattern",             # past diagnostic + fix patterns
    "constraint",              # hard rules (budget, no-soldering, etc.)
    "goal",                    # what the user is building toward
    "milestone",               # phased delivery markers
}


def build_preamble(
    query: str = "",
    max_entities: int = 12,
    max_chars: int = 2400,
    knowledge_graph: Optional[Any] = None,
) -> str:
    """Build a project context preamble for injection into an LLM prompt.

    Pulls the most relevant KG entities for the query and formats them as
    a structured preamble. If the KG is unavailable or empty, returns "".

    Args:
        query: The user's research/planning query — used to rank relevance
        max_entities: Cap on number of entities included
        max_chars: Cap on total preamble length
        knowledge_graph: KG instance (auto-resolves if None)
    """
    kg = knowledge_graph
    if kg is None:
        try:
            from core.knowledge_graph import KnowledgeGraph
            kg = KnowledgeGraph()
        except Exception as e:
            logger.debug("Could not load KG for preamble: %s", e)
            return ""

    # Get context-relevant entities — try the LLM context helper first
    raw_context = ""
    try:
        raw_context = kg.get_context_for_llm(query or "") or ""
    except Exception:
        pass

    # Parse the loose text into structured entries we can filter
    entries = _parse_entries(raw_context)

    # Filter to entities we consider project context
    project_entries = [
        e for e in entries
        if e["type"] in _CONTEXT_ENTITY_TYPES or _is_project_related(e["name"])
    ]

    if not project_entries:
        return ""

    # Score by query relevance — exact name match > word overlap > type weight
    project_entries.sort(
        key=lambda e: -_relevance_score(e, query),
    )
    project_entries = project_entries[:max_entities]

    # Build the preamble
    lines = [
        "═══ PROJECT CONTEXT (use these as ground truth — do NOT make up "
        "competing facts) ═══",
    ]
    for e in project_entries:
        type_label = e["type"].replace("_", " ").upper()
        lines.append(f"\n• [{type_label}] {e['name']}:")
        for fact in e["facts"][:6]:  # cap facts per entity
            lines.append(f"    - {fact}")

    lines.append(
        "\n═══ INSTRUCTIONS ═══\n"
        "When answering, REFERENCE the context above by name (e.g. "
        "'per learned_skill `pi_zero_compute`...'). Do NOT recommend "
        "components, OSes, or architectures that contradict locked-in "
        "project_decision entries. If the context is silent on a topic, "
        "say so honestly — don't fill the gap with generic knowledge."
    )

    preamble = "\n".join(lines)
    if len(preamble) > max_chars:
        preamble = preamble[: max_chars - 80].rsplit("\n", 1)[0] + (
            "\n\n... (preamble truncated)\n"
            "═══ INSTRUCTIONS ═══\n"
            "Reference the context above. Don't invent contradicting facts."
        )
    return preamble


def _parse_entries(raw: str) -> list[dict]:
    """Parse KG context dump into structured entries.

    Expected format (loose):
        name (type): predicate=value, predicate=value, ...
    """
    entries: list[dict] = []
    if not raw:
        return entries

    # Match lines like "  name (type): pred=val, pred=val"
    pattern = re.compile(
        r"^\s+(?P<name>\S[^()\n]*?)\s+\((?P<type>[a-z_]+)\):\s*(?P<body>.+?)$",
        re.MULTILINE,
    )
    for m in pattern.finditer(raw):
        body = m.group("body").strip()
        facts = []
        for chunk in body.split(", "):
            chunk = chunk.strip()
            if "=" in chunk:
                pred, val = chunk.split("=", 1)
                facts.append(f"{pred.strip()}: {val.strip()}")
            else:
                facts.append(chunk)
        entries.append({
            "name": m.group("name").strip(),
            "type": m.group("type").strip(),
            "facts": facts,
        })
    return entries


def _is_project_related(name: str) -> bool:
    """Heuristic: is this entity name about our project work?"""
    n = name.lower()
    keywords = (
        "stormbreaker", "jarvis", "goggles", "pi_zero", "pi 5", "raspberry",
        "ollama", "tesseract", "piper", "moondream", "gemma", "charon",
        "agent_loop", "thinking_layer", "honest_verifier", "context_awareness",
        "skill", "bom", "drdo", "edge", "wifi_link", "split_compute",
    )
    return any(k in n for k in keywords)


def _relevance_score(entry: dict, query: str) -> float:
    """Rank entries by how relevant they are to the query."""
    q = (query or "").lower()
    if not q:
        return 1.0  # no query → return everything equally
    name_lower = entry["name"].lower()
    score = 0.0

    # Direct name match wins big
    if q in name_lower:
        score += 10.0
    elif any(w in name_lower for w in q.split() if len(w) > 3):
        score += 5.0

    # Type-based weighting — locked decisions matter most
    type_weights = {
        "project_decision": 3.0,
        "constraint": 2.5,
        "architecture_component": 2.5,
        "bom_item": 2.0,
        "goal": 2.0,
        "milestone": 1.8,
        "learned_skill": 1.5,
        "bug_pattern": 1.0,
    }
    score += type_weights.get(entry["type"], 0.5)

    # Recency: if "completed_at" or "updated_at" appear, that's a fresh entry
    for f in entry["facts"]:
        f_lower = f.lower()
        if "2026" in f_lower or "updated" in f_lower:
            score += 0.5
            break

    # Bonus: facts mentioning query keywords
    facts_blob = " ".join(entry["facts"]).lower()
    for word in q.split():
        if len(word) > 3 and word in facts_blob:
            score += 0.5

    return score


def save_decision(
    name: str,
    decision: str,
    rationale: str = "",
    locked: bool = True,
    knowledge_graph: Optional[Any] = None,
    **extra_facts: str,
) -> bool:
    """Persist a project decision into the knowledge graph.

    Use this when the user commits to an architecture/component/scope choice
    so future research grounds in it.

    Example:
        save_decision(
            name="pi_zero_compute_brick",
            decision="Pi Zero 2 W on goggles, WiFi to Windows PC running JARVIS Desktop as the brain",
            rationale="Cheapest path — uses existing PC, no Pi 5 needed for v0",
            cost_gbp="15",
            phase="v0",
        )
    """
    kg = knowledge_graph
    if kg is None:
        try:
            from core.knowledge_graph import KnowledgeGraph
            kg = KnowledgeGraph()
        except Exception:
            return False
    try:
        facts = {
            "decision": decision[:500],
            "rationale": rationale[:500] if rationale else "",
            "locked": "yes" if locked else "no",
            "saved_at": _now_iso(),
            **{k: str(v)[:300] for k, v in extra_facts.items()},
        }
        kg.add_entity(name, "project_decision", facts)
        return True
    except Exception as e:
        logger.warning("save_decision failed for %s: %s", name, e)
        return False


def save_bom_item(
    name: str,
    description: str,
    cost: str,
    vendor: str = "",
    quantity: int = 1,
    phase: str = "v0",
    knowledge_graph: Optional[Any] = None,
) -> bool:
    """Persist a BOM line item into the knowledge graph."""
    kg = knowledge_graph
    if kg is None:
        try:
            from core.knowledge_graph import KnowledgeGraph
            kg = KnowledgeGraph()
        except Exception:
            return False
    try:
        facts = {
            "description": description[:400],
            "cost": str(cost)[:50],
            "vendor": vendor[:150] if vendor else "",
            "quantity": str(quantity),
            "phase": phase,
            "saved_at": _now_iso(),
        }
        kg.add_entity(name, "bom_item", facts)
        return True
    except Exception as e:
        logger.warning("save_bom_item failed for %s: %s", name, e)
        return False


def _now_iso() -> str:
    import time
    return time.strftime("%Y-%m-%d %H:%M:%S")
