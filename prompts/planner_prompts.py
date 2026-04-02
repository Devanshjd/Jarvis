"""
J.A.R.V.I.S — Planner Prompts
Prompt template that instructs the LLM to output structured JSON plans.
"""

# Re-export the planner prompt from core for convenience
from core.planner import PLANNER_PROMPT

__all__ = ["PLANNER_PROMPT"]
