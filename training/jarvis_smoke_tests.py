"""
JARVIS smoke tests.

Focused regression checks for the runtime behaviors that keep breaking:
- boot greeting leaks
- reply normalization for local models
- direct-control follow-through for messaging
- local send-status responses
- security/task routing
- chain progress/completion callbacks
- self-modification follow-through messaging

Usage:
    python training/jarvis_smoke_tests.py
"""

from __future__ import annotations

import sys
import time
import traceback
import tempfile
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.chain_engine import ChainEngine  # noqa: E402
import core.chain_engine as chain_module  # noqa: E402
from core.executor import Executor  # noqa: E402
from core.orchestrator import Priority, Task, TaskOrchestrator, TaskType  # noqa: E402
from core.capability_registry import CapabilityRegistry  # noqa: E402
from core.memory import MemorySystem  # noqa: E402
from core.presence import PresenceEngine  # noqa: E402
from core.schemas import ToolResult  # noqa: E402
from core.task_brain import TaskBrain  # noqa: E402
from core.headless_runtime import HeadlessJarvisRuntime  # noqa: E402
from ui.app import JarvisApp  # noqa: E402


class BrainStub:
    def __init__(self):
        self.config = {"provider": "ollama", "max_tokens": 512}
        self.mode = "General"
        self.history = []
        self.msg_count = 0

    def add_assistant_message(self, reply: str) -> None:
        self.history.append({"role": "assistant", "content": reply})


class MemoryStub:
    def get_context_string(self) -> str:
        return ""

    def add(self, text: str) -> bool:
        return True


class PluginManagerStub:
    def __init__(self):
        self.plugins = {
            "messaging": object(),
            "cyber": object(),
            "email": object(),
            "pentest": object(),
        }

    def get_plugin(self, name: str):
        return self.plugins.get(name)


class RootStub:
    def after(self, delay_ms: int, callback):
        callback()


class ChatStub:
    def __init__(self):
        self.messages = []

    def add_message(self, role: str, text: str) -> None:
        self.messages.append((role, text))


class SelfModifyStub:
    def __init__(self):
        self.writes = []
        self.reloads = []

    def test_code(self, code: str, test_type: str = "syntax") -> dict:
        return {"success": True, "message": "Syntax valid.", "output": ""}

    def write_file(self, filepath: str, content: str, reason: str) -> dict:
        self.writes.append((filepath, content, reason))
        return {"success": True, "message": f"Written: {filepath} ({content.count(chr(10)) + 1} lines)"}

    def reload_plugin(self, plugin_name: str) -> dict:
        self.reloads.append(plugin_name)
        return {"success": True, "message": f"Reloaded: plugins.{plugin_name}"}


def make_jarvis_stub(**overrides):
    jarvis = SimpleNamespace(
        brain=BrainStub(),
        memory=MemoryStub(),
        plugin_manager=PluginManagerStub(),
        config={},
        root=RootStub(),
        chat=ChatStub(),
        direct_control_preferred=False,
        awareness=SimpleNamespace(
            get_current_context=lambda: "",
            get_clipboard_context=lambda: "",
        ),
        mem=SimpleNamespace(get_full_context=lambda: ""),
        screen_monitor=SimpleNamespace(
            get_screen_context=lambda: "",
            struggle_score=0,
        ),
    )
    for key, value in overrides.items():
        setattr(jarvis, key, value)
    return jarvis


def make_orchestrator():
    jarvis = make_jarvis_stub()
    orch = TaskOrchestrator(jarvis)
    jarvis.orchestrator = orch
    jarvis.capabilities = CapabilityRegistry(jarvis)
    return orch


def test_boot_greeting_hides_pending_task_text():
    app = SimpleNamespace(
        config={
            "learned": {"total_sessions": 2},
            "tasks": [
                {"text": "You are designing a cinematic ultra realistic AI interface...", "done": False},
                {"text": "scan my network", "done": False},
            ],
        }
    )
    greeting = PresenceEngine(app).get_boot_greeting()
    if "You are designing" in greeting:
        raise AssertionError(f"boot greeting leaked task text: {greeting}")
    if "2 pending tasks" not in greeting:
        raise AssertionError(f"boot greeting missing task count: {greeting}")


def test_normalize_reply_cleans_local_model_noise():
    summary = JarvisApp._normalize_reply('{"summary":"Summary only.","results":[{"title":"a"}]}')
    if summary != "Summary only.":
        raise AssertionError(f"summary extraction failed: {summary!r}")

    noisy = JarvisApp._normalize_reply(
        '餸菜！ (Songcai!) That\'s Cantonese for "Let\'s go!" - it seems you\'re suggesting direct control.'
    )
    if "餸菜" in noisy or "songcai" in noisy.lower():
        raise AssertionError(f"decorative prefix was not stripped: {noisy!r}")

    json_reply = JarvisApp._normalize_reply('```json\n{"response":"Absolutely. Sending it now."}\n```')
    if json_reply != "Absolutely. Sending it now.":
        raise AssertionError(f"JSON fence unwrap failed: {json_reply!r}")


def test_security_phrase_routes_to_tool():
    orch = make_orchestrator()
    kind = orch.classify("can you check if my system is running completely safe or not")
    if kind != TaskType.TOOL:
        raise AssertionError(f"security query routed as {kind} instead of TOOL")


def test_operator_memory_context_filters_secrets_and_prompt_payloads():
    mem = MemorySystem({
        "memories": [
            "Dev prefers concise replies.",
            "University credentials: ID: dj23aau@herts.ac.uk | Password: Devansh09978",
            "You are designing a cinematic interface. CORE DESIGN PRINCIPLES: energy core. OUTPUT REQUIREMENT: realism.",
        ]
    })
    context = mem.get_full_context()
    if "Dev prefers concise replies." not in context:
        raise AssertionError(f"expected safe memory to remain in context: {context}")
    if "password" in context.lower() or "dj23aau@herts.ac.uk" in context.lower():
        raise AssertionError(f"secret memory leaked into context: {context}")
    if "You are designing a cinematic interface" in context:
        raise AssertionError(f"prompt payload leaked into operator memory context: {context}")


def test_task_brain_filters_junk_and_secrets_from_learning():
    with tempfile.TemporaryDirectory() as td:
        brain = TaskBrain(path=Path(td) / "task_brain.json")
        brain.record_task_outcome(
            goal="You are designing a cinematic interface. CORE DESIGN PRINCIPLES: energy core. OUTPUT REQUIREMENT: realism.",
            tool_name="send_msg",
            args={"contact": "and", "message": "I am here", "password": "secret123"},
            status="completed",
            result_text="api_key = sk-abcdef1234567890",
            attempts=1,
            step="completed",
        )
        episode = brain.get_recent_episodes(limit=1)[0]
        if episode["goal"]:
            raise AssertionError(f"prompt payload should not be learned as a goal: {episode}")
        if "contact" in episode["args"]:
            raise AssertionError(f"junk contact value should not be kept: {episode}")
        if episode["args"].get("password") != "[redacted]":
            raise AssertionError(f"sensitive args should be redacted: {episode}")
        if episode["result"]:
            raise AssertionError(f"secret-bearing result should not be learned: {episode}")


def test_direct_control_retry_reuses_recent_send():
    orch = make_orchestrator()
    orch.jarvis.direct_control_preferred = True
    orch._last_action = {
        "tool": "send_msg",
        "args": {"contact": "meet", "platform": "whatsapp", "message": "i am coming"},
        "time": time.time(),
        "result": "The previous send did not complete.",
        "success": False,
    }
    calls = []

    def fake_execute(tool_name: str, tool_args: dict) -> ToolResult:
        calls.append((tool_name, dict(tool_args)))
        return ToolResult(success=True, output="Message sent to Meet on WhatsApp. Verified.")

    orch.executor.execute = fake_execute
    task = Task(priority=int(Priority.HIGH), text="yes try now", task_type=TaskType.SIMPLE)
    result = orch._local_pipeline(task)

    if not result.success:
        raise AssertionError(f"local retry failed: {result.reply}")
    if not calls or calls[0][0] != "send_msg":
        raise AssertionError(f"recent send was not retried: {calls}")
    if "direct keyboard and mouse control" not in result.reply.lower():
        raise AssertionError(f"direct-control lead text missing: {result.reply}")


def test_recent_send_status_stays_local():
    orch = make_orchestrator()
    orch._last_action = {
        "tool": "send_msg",
        "args": {"contact": "meet", "platform": "whatsapp"},
        "time": time.time(),
        "result": "I typed the message to Meet on WhatsApp and pressed Enter.",
        "success": True,
    }
    task = Task(priority=int(Priority.HIGH), text="did you sent it", task_type=TaskType.SIMPLE)
    result = orch._local_pipeline(task)

    if not result.success:
        raise AssertionError(f"status query did not stay local: {result.reply}")
    if "typed the message" not in result.reply.lower():
        raise AssertionError(f"unexpected status reply: {result.reply}")


def test_send_request_with_and_in_message_stays_tool():
    orch = make_orchestrator()
    text = "try texting meet on whatsapp that i am coming through keyboard and mouose"
    kind = orch.classify(text)
    if kind != TaskType.TOOL:
        raise AssertionError(f"send request was misclassified as {kind} instead of TOOL")

    args = orch._build_tool_args("send_msg", text, None)
    if args.get("contact") != "meet":
        raise AssertionError(f"contact was not extracted correctly: {args}")
    if args.get("platform") != "whatsapp":
        raise AssertionError(f"platform was not extracted correctly: {args}")
    if args.get("message") != "i am coming":
        raise AssertionError(f"direct-control text leaked into the message body: {args}")
    if not orch.jarvis.direct_control_preferred:
        raise AssertionError("direct keyboard/mouse preference was not enabled from the same request")


def test_pending_send_followup_bypasses_fastpaths():
    orch = make_orchestrator()
    orch.task_sessions.start_or_update(
        goal="send a message",
        tool_name="send_msg",
        args={"platform": "whatsapp", "message": "i am coming"},
        required_args=["contact", "platform", "message"],
        user_text="send a message",
    )
    orch.task_sessions.set_waiting(
        missing_args=["contact"],
        prompts=["Who should I send it to?"],
        args={"platform": "whatsapp", "message": "i am coming"},
        result_text="Waiting for contact.",
    )
    if not orch.should_bypass_fastpaths("meet"):
        raise AssertionError("pending follow-up 'meet' should bypass local fast paths and return to the orchestrator")


def test_pending_ambiguous_contact_choice_merges_numbered_option():
    orch = make_orchestrator()
    pending_tool = {
        "tool": "send_msg",
        "args": {
            "platform": "whatsapp",
            "message": "i am coming",
            "contact_options": ["Dishant Meet Ent", "Meet Abyankar W"],
        },
        "missing": ["I found multiple WhatsApp matches for Meet: 1. Dishant Meet Ent; 2. Meet Abyankar W. Which one should I use?"],
        "time": time.time(),
    }
    merged = orch._merge_pending_tool_args(
        "send_msg",
        pending_tool,
        dict(pending_tool["args"]),
        {},
        "2",
    )
    if merged.get("contact") != "Meet Abyankar W":
        raise AssertionError(f"numeric ambiguous contact choice was not resolved: {merged}")


def test_tool_pipeline_waits_for_ambiguous_contact_choice():
    orch = make_orchestrator()

    def fake_execute(tool_name: str, tool_args: dict) -> ToolResult:
        return ToolResult(
            success=False,
            error="I found multiple WhatsApp matches for Meet: 1. Dishant Meet Ent; 2. Meet Abyankar W. Which one should I use?",
            data={
                "kind": "ambiguous_contact",
                "options": ["Dishant Meet Ent", "Meet Abyankar W"],
                "query": "Meet",
            },
        )

    orch.executor.execute = fake_execute
    task = Task(priority=int(Priority.HIGH), text="text meet on whatsapp that i am coming", task_type=TaskType.TOOL)
    result = orch._tool_pipeline(task)

    if result.success:
        raise AssertionError(f"ambiguous contact should not count as success: {result.reply}")
    if "multiple whatsapp matches" not in result.reply.lower():
        raise AssertionError(f"unexpected ambiguity reply: {result.reply}")
    waiting = orch.task_sessions.get_waiting_session()
    if not waiting:
        raise AssertionError("waiting session was not preserved for ambiguous contact choice")
    if waiting.args.get("contact_options") != ["Dishant Meet Ent", "Meet Abyankar W"]:
        raise AssertionError(f"contact options were not stored for follow-up: {waiting.args}")


def test_ai_pipeline_rescues_send_request_back_to_tools():
    orch = make_orchestrator()
    calls = []

    def fake_tool_pipeline(task):
        calls.append((task.text, dict(task.metadata)))
        return SimpleNamespace(success=True, reply="rescued", pipeline="tool_pipeline")

    orch._tool_pipeline = fake_tool_pipeline
    task = Task(priority=int(Priority.HIGH), text="can you text meet that im coming on whatsapp", task_type=TaskType.REASONING)
    result = orch._ai_pipeline(task)

    if not calls:
        raise AssertionError("AI pipeline did not rescue a send request back to the tool path")
    if result.reply != "rescued":
        raise AssertionError(f"unexpected rescue result: {result.reply}")


def test_open_and_send_request_stays_single_operator_tool():
    orch = make_orchestrator()
    text = "open whatsapp and text meet that i am coming"
    kind = orch.classify(text)
    if kind != TaskType.TOOL:
        raise AssertionError(f"combined desktop send request was misclassified as {kind} instead of TOOL")

    match = orch.jarvis.capabilities.resolve_request(text)
    if not match:
        raise AssertionError("capability registry failed to resolve a dominant operator tool")
    if match.capability.name != "send_msg":
        raise AssertionError(f"expected send_msg, got {match.capability.name}")


def test_ai_pipeline_rescues_operator_request_via_capability_registry():
    orch = make_orchestrator()
    calls = []

    def fake_tool_pipeline(task):
        calls.append((task.text, dict(task.metadata)))
        return SimpleNamespace(success=True, reply="rescued via capability registry", pipeline="tool_pipeline")

    orch._tool_pipeline = fake_tool_pipeline
    task = Task(
        priority=int(Priority.HIGH),
        text="open whatsapp and text meet that i am coming",
        task_type=TaskType.REASONING,
    )
    result = orch._ai_pipeline(task)

    if not calls:
        raise AssertionError("AI pipeline did not rescue the operator request back to the tool path")
    planned_tool = calls[0][1].get("planned_tool")
    if planned_tool != "send_msg":
        raise AssertionError(f"expected planned_tool=send_msg, got {planned_tool!r}")
    if result.reply != "rescued via capability registry":
        raise AssertionError(f"unexpected rescue result: {result.reply}")


def test_tool_queries_are_not_cached_as_fake_success():
    orch = make_orchestrator()
    query = "can you text meet that im coming on whatsapp"
    orch.post_process(
        task_type=TaskType.TOOL,
        query=query,
        result="Message sent to Meet on WhatsApp. Verified.",
        latency=10.0,
        success=True,
        pipeline="tool_pipeline",
    )
    kind = orch.classify(query)
    if kind == TaskType.CACHED:
        raise AssertionError("tool query was cached and would skip real execution on repeat")


def test_pending_message_followup_skips_local_greeting():
    orch = make_orchestrator()
    orch.get_optimal_route = lambda _text: "local_pipeline"
    orch.task_sessions.start_or_update(
        goal="send again",
        tool_name="send_msg",
        args={"contact": "meet", "platform": "whatsapp"},
        required_args=["contact", "platform", "message"],
        user_text="send again",
    )
    waiting = orch.task_sessions.set_waiting(
        missing_args=["message"],
        prompts=["What should the message say?"],
        args={"contact": "meet", "platform": "whatsapp"},
        result_text="Waiting for message.",
    )
    orch._sync_task_state_compat()

    local_calls = []
    tool_calls = []

    def fake_local(task):
        local_calls.append(task.text)
        return SimpleNamespace(success=True, reply="Hello, sir. How can I assist you?", pipeline="local_pipeline")

    def fake_tool(task):
        tool_calls.append(task.text)
        return SimpleNamespace(success=True, reply="Message sent to Meet on WhatsApp. Verified.", pipeline="tool_pipeline")

    orch._local_pipeline = fake_local
    orch._tool_pipeline = fake_tool

    replies = []
    task = Task(priority=int(Priority.HIGH), text="hi", task_type=TaskType.TOOL)
    task.metadata["pending_tool"] = waiting.to_pending_tool()
    task.on_reply = lambda reply, latency: replies.append(reply)
    orch._execute_task(task)

    if local_calls:
        raise AssertionError(f"local greeting path should not run for pending operator follow-up: {local_calls}")
    if not tool_calls:
        raise AssertionError("pending operator follow-up did not reach tool pipeline")
    if not replies or "Message sent to Meet" not in replies[0]:
        raise AssertionError(f"unexpected reply for pending message follow-up: {replies}")


def test_waiting_retry_affirmation_retries_recent_screen_action():
    orch = make_orchestrator()
    orch.task_sessions.start_or_update(
        goal="click the send button",
        tool_name="screen_click",
        args={"description": "send button"},
        required_args=["description"],
        user_text="click the send button",
    )
    orch.task_sessions.mark_executing(
        args={"description": "send button"},
        step="executing:screen_click",
    )
    orch.task_sessions.record_result(
        success=False,
        result_text="Could not click 'send button'",
        args={"description": "send button"},
        step="failed",
        keep_active=False,
    )
    orch.task_sessions.start_or_update(
        goal="click the send button",
        tool_name="screen_click",
        args={"description": "send button"},
        required_args=["description"],
        user_text="click the send button",
    )
    orch.task_sessions.set_waiting(
        missing_args=[],
        prompts=["I hit resistance while trying to click send button. Say 'try again' and I'll rerun it directly."],
        args={"description": "send button"},
        result_text="Could not click 'send button'",
        step="awaiting_retry",
    )
    orch._sync_task_state_compat()

    calls = []

    def fake_execute(tool_name: str, tool_args: dict) -> ToolResult:
        calls.append((tool_name, dict(tool_args)))
        return ToolResult(success=True, output="Clicked 'send button' at (120, 220)")

    orch.executor.execute = fake_execute
    task = Task(priority=int(Priority.HIGH), text="yes", task_type=TaskType.SIMPLE)
    result = orch._local_pipeline(task)

    if not result.success:
        raise AssertionError(f"retry confirmation did not succeed: {result.reply}")
    if not calls or calls[0][0] != "screen_click":
        raise AssertionError(f"recent screen action was not retried: {calls}")
    if "retrying click send button now" not in result.reply.lower():
        raise AssertionError(f"retry lead text missing: {result.reply}")


def test_correction_retries_recent_operator_action_without_ai():
    orch = make_orchestrator()
    orch._last_action = {
        "tool": "screen_click",
        "args": {"description": "send button"},
        "time": time.time(),
        "result": "Could not click 'send button'",
        "success": False,
        "status": "failed",
        "step": "failed",
    }
    calls = []

    def fake_execute(tool_name: str, tool_args: dict) -> ToolResult:
        calls.append((tool_name, dict(tool_args)))
        return ToolResult(success=True, output="Clicked 'send button' at (120, 220)")

    orch.executor.execute = fake_execute
    orch._ai_pipeline = lambda task: (_ for _ in ()).throw(AssertionError("correction should not fall into AI pipeline"))

    task = Task(priority=int(Priority.HIGH), text="you didn't click it", task_type=TaskType.TOOL)
    result = orch._tool_pipeline(task)

    if not result.success:
        raise AssertionError(f"correction retry failed: {result.reply}")
    if not calls or calls[0][0] != "screen_click":
        raise AssertionError(f"recent operator action was not retried: {calls}")
    if "i see the issue" not in result.reply.lower():
        raise AssertionError(f"correction retry lead missing: {result.reply}")


def test_retryable_tool_failure_enters_retry_waiting_state():
    orch = make_orchestrator()

    def fake_execute(tool_name: str, tool_args: dict) -> ToolResult:
        return ToolResult(success=False, error="Could not click 'send button'")

    orch.executor.execute = fake_execute
    task = Task(priority=int(Priority.HIGH), text="click the send button", task_type=TaskType.TOOL)
    task.metadata["planned_tool"] = "screen_click"
    result = orch._tool_pipeline(task)

    waiting = orch.task_sessions.get_waiting_session()
    if result.success:
        raise AssertionError(f"retryable failure should not report success: {result.reply}")
    if not waiting or waiting.step != "awaiting_retry":
        raise AssertionError(f"retryable operator failure did not preserve awaiting_retry state: {waiting}")
    if "say 'try again'" not in result.reply.lower():
        raise AssertionError(f"retry guidance missing from operator failure reply: {result.reply}")


def test_chain_engine_reports_progress_and_completion():
    original_save = chain_module._save_chain
    chain_module._save_chain = lambda chain: None
    try:
        class DummyExecutor:
            def execute(self, tool_name: str, args: dict):
                return SimpleNamespace(success=True, output=f"{tool_name} ok", error="")

        jarvis = SimpleNamespace(orchestrator=SimpleNamespace(executor=DummyExecutor()))
        engine = ChainEngine(jarvis)
        progress = []
        done = []

        chain = engine.create_chain(
            "Smoke Chain",
            [
                {"step_id": "one", "tool_name": "foo", "tool_args": {}},
                {"step_id": "two", "tool_name": "bar", "tool_args": {}, "depends_on": ["one"]},
            ],
        )
        engine.execute_chain(
            chain,
            progress_cb=lambda msg: progress.append(msg),
            done_cb=lambda chain_obj: done.append(chain_obj.status),
            background=False,
        )
    finally:
        chain_module._save_chain = original_save

    if len(progress) < 4:
        raise AssertionError(f"expected progress updates, got {progress}")
    if done != ["done"]:
        raise AssertionError(f"done callback did not fire correctly: {done}")


def test_modify_file_reports_reload_for_plugins():
    sm = SelfModifyStub()
    executor = Executor(make_jarvis_stub(self_modify=sm))
    result = executor._modify_file(
        {
            "filepath": "plugins/demo/demo_plugin.py",
            "content": "print('ok')\n",
            "reason": "smoke test",
        }
    )
    if not result.success:
        raise AssertionError(f"plugin modify failed: {result.error}")
    if "Reloaded:" not in result.output:
        raise AssertionError(f"plugin reload message missing: {result.output}")
    if sm.reloads != ["demo"]:
        raise AssertionError(f"unexpected plugin reloads: {sm.reloads}")


def test_modify_file_warns_when_restart_may_be_needed():
    sm = SelfModifyStub()
    executor = Executor(make_jarvis_stub(self_modify=sm))
    result = executor._modify_file(
        {
            "filepath": "core/demo.py",
            "content": "print('ok')\n",
            "reason": "smoke test",
        }
    )
    if not result.success:
        raise AssertionError(f"core modify failed: {result.error}")
    if "restart" not in result.output.lower() and "reload" not in result.output.lower():
        raise AssertionError(f"restart/reload guidance missing: {result.output}")


def test_headless_runtime_handles_basic_turn():
    runtime = HeadlessJarvisRuntime()
    try:
        voice = runtime.voice_snapshot()
        if "voice" not in runtime.plugin_manager.plugins:
            raise AssertionError("headless runtime should expose the voice plugin for the desktop shell")
        if voice.get("engine") != "gemini":
            raise AssertionError(f"unexpected headless voice engine: {voice}")
        result = runtime.process_text("hi", timeout=20)
        reply = (result.get("reply") or "").strip()
        if not reply:
            raise AssertionError(f"headless runtime returned empty reply: {result}")
        if not result.get("messages"):
            raise AssertionError(f"headless runtime returned no visible messages: {result}")
    finally:
        runtime.shutdown()


TESTS = [
    ("boot_greeting_hides_pending_task_text", test_boot_greeting_hides_pending_task_text),
    ("normalize_reply_cleans_local_model_noise", test_normalize_reply_cleans_local_model_noise),
    ("security_phrase_routes_to_tool", test_security_phrase_routes_to_tool),
    ("operator_memory_context_filters_secrets_and_prompt_payloads", test_operator_memory_context_filters_secrets_and_prompt_payloads),
    ("task_brain_filters_junk_and_secrets_from_learning", test_task_brain_filters_junk_and_secrets_from_learning),
    ("direct_control_retry_reuses_recent_send", test_direct_control_retry_reuses_recent_send),
    ("recent_send_status_stays_local", test_recent_send_status_stays_local),
    ("send_request_with_and_in_message_stays_tool", test_send_request_with_and_in_message_stays_tool),
    ("pending_send_followup_bypasses_fastpaths", test_pending_send_followup_bypasses_fastpaths),
    ("pending_ambiguous_contact_choice_merges_numbered_option", test_pending_ambiguous_contact_choice_merges_numbered_option),
    ("tool_pipeline_waits_for_ambiguous_contact_choice", test_tool_pipeline_waits_for_ambiguous_contact_choice),
    ("ai_pipeline_rescues_send_request_back_to_tools", test_ai_pipeline_rescues_send_request_back_to_tools),
    ("open_and_send_request_stays_single_operator_tool", test_open_and_send_request_stays_single_operator_tool),
    ("ai_pipeline_rescues_operator_request_via_capability_registry", test_ai_pipeline_rescues_operator_request_via_capability_registry),
    ("tool_queries_are_not_cached_as_fake_success", test_tool_queries_are_not_cached_as_fake_success),
    ("pending_message_followup_skips_local_greeting", test_pending_message_followup_skips_local_greeting),
    ("waiting_retry_affirmation_retries_recent_screen_action", test_waiting_retry_affirmation_retries_recent_screen_action),
    ("correction_retries_recent_operator_action_without_ai", test_correction_retries_recent_operator_action_without_ai),
    ("retryable_tool_failure_enters_retry_waiting_state", test_retryable_tool_failure_enters_retry_waiting_state),
    ("chain_engine_reports_progress_and_completion", test_chain_engine_reports_progress_and_completion),
    ("modify_file_reports_reload_for_plugins", test_modify_file_reports_reload_for_plugins),
    ("modify_file_warns_when_restart_may_be_needed", test_modify_file_warns_when_restart_may_be_needed),
    ("headless_runtime_handles_basic_turn", test_headless_runtime_handles_basic_turn),
]


def main() -> int:
    print("JARVIS smoke tests")
    print(f"Repo: {REPO_ROOT}")
    failures = 0

    for name, test_fn in TESTS:
        try:
            test_fn()
        except Exception as exc:
            failures += 1
            print(f"[FAIL] {name}")
            print(f"       {exc}")
            tb = traceback.format_exc().strip().splitlines()
            for line in tb[-6:]:
                print(f"       {line}")
        else:
            print(f"[PASS] {name}")

    passed = len(TESTS) - failures
    print(f"\nSummary: {passed}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
