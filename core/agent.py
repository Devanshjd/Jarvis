"""
J.A.R.V.I.S — Agent Orchestrator
Ties together: Planner → Safety → Executor → Memory → Response.

Flow:
  1. User message arrives
  2. Planner sends message + context to LLM → gets AgentPlan (JSON)
  3. Safety layer checks if confirmation is needed
  4. Executor runs the tool (if any)
  5. Memory updated with results
  6. Spoken reply sent to user (+ TTS via plugin)
"""

import threading

from core.schemas import AgentPlan, AgentState, ToolResult
from core.planner import build_planning_messages, parse_plan, PLANNER_PROMPT
from core.executor import Executor
from core.safety import needs_confirmation, describe_risk
from core.memory import ShortTermMemory


class Agent:
    """
    The JARVIS agent — an intelligent loop that plans, validates, and executes.
    """

    def __init__(self, jarvis):
        self.jarvis = jarvis
        self.brain = jarvis.brain
        self.memory = jarvis.memory           # long-term (MemoryBank)
        self.short_term = ShortTermMemory()    # session context
        self.executor = Executor(jarvis)
        self.state = AgentState()

        # Callback for confirmation dialogs — set by UI
        self._confirm_callback = None
        self._pending_plan: AgentPlan | None = None

    def process_message(self, text: str, on_reply, on_error):
        """
        Main entry point. Processes a user message through the agent loop.

        Args:
            text: User's message
            on_reply: callback(reply_text, latency_ms)
            on_error: callback(error_text)
        """
        self.short_term.add_user(text)
        self.state.phase = "planning"

        def _run():
            try:
                plan = self._plan(text)
                self.state.current_plan = plan

                if plan.needs_tool and plan.tool_name:
                    # Check safety
                    if needs_confirmation(plan.tool_name, plan.tool_args):
                        self.state.phase = "confirming"
                        self.state.pending_confirmation = True
                        self._pending_plan = plan
                        risk_msg = describe_risk(plan.tool_name, plan.tool_args)
                        # Ask UI for confirmation
                        self.jarvis.root.after(0, lambda: self._request_confirmation(
                            plan, risk_msg, on_reply, on_error,
                        ))
                        return

                    # Safe to execute directly
                    self._execute_and_respond(plan, on_reply, on_error)
                else:
                    # Pure conversation — no tool needed
                    self.state.phase = "responding"
                    reply = plan.spoken_reply
                    self.short_term.add_assistant(reply)
                    self.brain.add_assistant_message(reply)
                    self.brain.msg_count += 1
                    self.jarvis.root.after(0, lambda: on_reply(reply, 0))

            except Exception as e:
                self.state.phase = "idle"
                self.jarvis.root.after(0, lambda: on_error(f"Agent error: {e}"))

        threading.Thread(target=_run, daemon=True).start()

    def _plan(self, user_message: str) -> AgentPlan:
        """Send message to LLM with planning prompt, parse structured output."""
        if not self.brain.provider.is_available():
            info = self.brain.get_provider_info()
            raise ConnectionError(
                f"{info['name']} is not available. "
                f"Check your API key or start the local server."
            )

        # Build context
        mem_context = self.memory.get_context_string()
        stm_context = self.short_term.get_context_string()
        notes = self.jarvis.config.get("notes", "")

        # Combine planning prompt with JARVIS identity
        from core.brain import MODES
        identity = MODES.get(self.brain.mode, MODES["General"])

        full_system = identity + "\n\n" + PLANNER_PROMPT
        if mem_context:
            full_system += f"\n\n{mem_context}"
        if stm_context:
            full_system += f"\n\n{stm_context}"
        if notes:
            full_system += f"\n\n[CURRENT NOTES]\n{notes}"

        # Call the provider directly (synchronous, we're in a thread)
        reply_text, latency = self.brain.provider.chat(
            messages=self.brain.history,
            system_prompt=full_system,
            max_tokens=self.brain.config.get("max_tokens", 2048),
        )

        plan = parse_plan(reply_text)
        return plan

    def _execute_and_respond(self, plan: AgentPlan, on_reply, on_error):
        """Execute the tool and send the response."""
        self.state.phase = "executing"

        result = self.executor.execute(plan.tool_name, plan.tool_args)
        self.short_term.add_tool_result(
            plan.tool_name, result.output if result.success else result.error,
            result.success,
        )
        self.state.last_result = result

        # Build final reply
        self.state.phase = "responding"
        if result.success:
            # Combine JARVIS's spoken reply with tool output
            reply = plan.spoken_reply
            if result.output and result.output not in reply:
                reply += f"\n\n{result.output}"
        else:
            reply = f"{plan.spoken_reply}\n\nHowever, there was an issue: {result.error}"

        self.short_term.add_assistant(reply)
        self.brain.add_assistant_message(reply)
        self.brain.msg_count += 1
        self.state.phase = "idle"

        self.jarvis.root.after(0, lambda: on_reply(reply, 0))

    def _request_confirmation(self, plan: AgentPlan, risk_msg: str,
                              on_reply, on_error):
        """Ask the user for confirmation via the UI."""
        from tkinter import messagebox
        confirmed = messagebox.askyesno(
            "JARVIS — Confirmation Required",
            risk_msg,
        )

        if confirmed:
            # Execute in background
            def _exec():
                self._execute_and_respond(plan, on_reply, on_error)
            threading.Thread(target=_exec, daemon=True).start()
        else:
            self.state.phase = "idle"
            self.state.pending_confirmation = False
            reply = "Understood, sir. Action cancelled."
            self.short_term.add_assistant(reply)
            on_reply(reply, 0)

    def confirm_pending(self, approved: bool, on_reply, on_error):
        """Handle confirmation response for a pending dangerous action."""
        if not self._pending_plan:
            return

        plan = self._pending_plan
        self._pending_plan = None
        self.state.pending_confirmation = False

        if approved:
            def _exec():
                self._execute_and_respond(plan, on_reply, on_error)
            threading.Thread(target=_exec, daemon=True).start()
        else:
            self.state.phase = "idle"
            reply = "Understood, sir. Action cancelled."
            self.short_term.add_assistant(reply)
            on_reply(reply, 0)
