"""
J.A.R.V.I.S — Agent Schemas
Structured models for agent planning and execution.

Uses dataclasses (stdlib) instead of Pydantic to avoid extra dependencies.
The Brain parses JSON from the LLM into these structures.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentPlan:
    """Structured plan produced by the LLM planner."""

    user_intent: str                          # What the user wants
    needs_tool: bool = False                  # Does this require a tool/action?
    tool_name: Optional[str] = None           # Which tool to invoke
    tool_args: dict = field(default_factory=dict)  # Arguments for the tool
    requires_confirmation: bool = False       # Ask user before executing?
    spoken_reply: str = ""                    # What JARVIS says back

    def to_dict(self) -> dict:
        return {
            "user_intent": self.user_intent,
            "needs_tool": self.needs_tool,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "requires_confirmation": self.requires_confirmation,
            "spoken_reply": self.spoken_reply,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentPlan":
        return cls(
            user_intent=data.get("user_intent", ""),
            needs_tool=data.get("needs_tool", False),
            tool_name=data.get("tool_name"),
            tool_args=data.get("tool_args", {}),
            requires_confirmation=data.get("requires_confirmation", False),
            spoken_reply=data.get("spoken_reply", ""),
        )

    @classmethod
    def chat_only(cls, intent: str, reply: str) -> "AgentPlan":
        """Quick constructor for pure conversation (no tool needed)."""
        return cls(user_intent=intent, spoken_reply=reply)


@dataclass
class ToolResult:
    """Result from executing a tool."""

    success: bool
    output: str = ""
    error: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class AgentState:
    """Snapshot of the agent's current processing state."""

    phase: str = "idle"        # idle, planning, confirming, executing, responding
    current_plan: Optional[AgentPlan] = None
    last_result: Optional[ToolResult] = None
    pending_confirmation: bool = False
