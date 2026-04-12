// ─── META-LEARNING: How the developer handles requests ───
// This file teaches JARVIS the workflow patterns used to build features.
// Each entry represents a real execution pattern that JARVIS should learn to replicate.

const META_TRAINING: Array<{
  scenario: string
  thinking: string
  steps: Array<{ action: string; tool: string; reasoning: string }>
  outcome: string
}> = [
  {
    scenario: "User says: 'Add browser automation'",
    thinking: "Complex feature. Needs: dependency install, IPC handlers, preload bridge, types, voice tools, voice handlers. Must follow Electron IPC pattern.",
    steps: [
      { action: "Install dependency", tool: "run_terminal", reasoning: "npm install puppeteer-core — use -core to avoid bundling Chromium" },
      { action: "Add IPC handlers", tool: "write_file", reasoning: "Add to main/index.ts — 7 handlers: launch, navigate, click, type, screenshot, read, execute" },
      { action: "Add preload bridge", tool: "write_file", reasoning: "Expose IPC to renderer via preload/index.ts" },
      { action: "Add TypeScript types", tool: "write_file", reasoning: "Update preload/index.d.ts so TS knows the API shape" },
      { action: "Add voice tool declarations", tool: "write_file", reasoning: "Add to GeminiLive tools array so Gemini knows these tools exist" },
      { action: "Add voice execution handlers", tool: "write_file", reasoning: "Add switch cases to handle tool calls from Gemini" },
      { action: "Build & verify", tool: "run_terminal", reasoning: "npm run build — must pass typecheck before committing" },
      { action: "Commit & push", tool: "run_terminal", reasoning: "Descriptive commit message with full feature documentation" }
    ],
    outcome: "Feature fully integrated: voice-activated, type-safe, build-passing"
  },
  {
    scenario: "User says: 'Fix a build error'",
    thinking: "Read the error message carefully. Identify the file and line. Understand the type system issue. Apply minimal fix.",
    steps: [
      { action: "Read error output", tool: "run_terminal", reasoning: "npm run build — capture exact error message and line number" },
      { action: "View the file at error line", tool: "read_file", reasoning: "See the context around the error to understand what went wrong" },
      { action: "Apply fix", tool: "write_file", reasoning: "Minimal edit — don't rewrite whole file, just fix the exact issue" },
      { action: "Rebuild to verify", tool: "run_terminal", reasoning: "Confirm the fix resolved the error without introducing new ones" }
    ],
    outcome: "Error fixed with minimal changes, build passes"
  },
  {
    scenario: "User says: 'Add a new widget'",
    thinking: "Widgets follow a strict pattern: WidgetShell wrapper, IPC data fetching, store registration, toolbar entry, layer import. Must match existing style.",
    steps: [
      { action: "Study existing widget", tool: "read_file", reasoning: "Read SystemWidget.tsx to understand the pattern: imports, state, useEffect, WidgetShell" },
      { action: "Check store types", tool: "read_file", reasoning: "Read useStore.ts to see WidgetType union and WIDGET_DEFAULTS" },
      { action: "Create widget file", tool: "write_file", reasoning: "Follow exact pattern: WidgetShell, icon, data fetching via useEffect + setInterval" },
      { action: "Register in store", tool: "write_file", reasoning: "Add to WidgetType union + WIDGET_DEFAULTS with proper dimensions" },
      { action: "Add to WidgetLayer", tool: "write_file", reasoning: "Import component and add to WIDGET_COMPONENTS record" },
      { action: "Add to WidgetToolbar", tool: "write_file", reasoning: "Import icon, add to WIDGET_ITEMS array with label" },
      { action: "Build & verify", tool: "run_terminal", reasoning: "Typecheck catches missing imports or wrong types" }
    ],
    outcome: "Widget appears in toolbar, opens/closes correctly, fetches live data"
  },
  {
    scenario: "User says: 'Add a new voice tool'",
    thinking: "Voice tools need 3 things: declaration (so Gemini knows it exists), handler (so it actually works), and IPC backend (if it needs system access).",
    steps: [
      { action: "Add tool declaration", tool: "write_file", reasoning: "In GeminiLive tools array: name, description with trigger phrases, params with types" },
      { action: "Add execution handler", tool: "write_file", reasoning: "In the switch statement: call the right API, format the response" },
      { action: "Add IPC handler if needed", tool: "write_file", reasoning: "In main/index.ts: ipcMain.handle with try/catch and typed response" },
      { action: "Add preload bridge", tool: "write_file", reasoning: "Expose in preload/index.ts with proper params" },
      { action: "Add types", tool: "write_file", reasoning: "Update index.d.ts for TypeScript safety" }
    ],
    outcome: "User can say the trigger phrase and JARVIS executes the tool"
  },
  {
    scenario: "User says: 'Test everything'",
    thinking: "Create a comprehensive test script that exercises each subsystem. Log results as training data so the offline brain learns.",
    steps: [
      { action: "Create test script", tool: "write_file", reasoning: "Python script that directly tests SQLite, filesystem, and routing logic" },
      { action: "Run tests", tool: "run_terminal", reasoning: "Execute with UTF-8 encoding on Windows" },
      { action: "Save training data", tool: "write_file", reasoning: "Append JSONL entries mapping user_input -> tool -> response" },
      { action: "Rebuild Ollama model", tool: "run_terminal", reasoning: "ollama create with updated Modelfile incorporating new training data" }
    ],
    outcome: "All subsystems verified, training data generated for offline brain"
  },
  {
    scenario: "User says: 'Research X and implement it'",
    thinking: "Research first, don't guess. Check docs, existing code patterns, then implement following established conventions.",
    steps: [
      { action: "Search for documentation", tool: "google_search", reasoning: "Find official docs or examples for the technology" },
      { action: "Read existing codebase", tool: "read_file", reasoning: "Understand current patterns before adding new code" },
      { action: "Plan implementation", tool: "vault_remember", reasoning: "Save research findings to knowledge vault for future reference" },
      { action: "Implement incrementally", tool: "write_file", reasoning: "Small changes, build after each step" },
      { action: "Test", tool: "run_terminal", reasoning: "Verify each change works before moving to next" },
      { action: "Commit with context", tool: "run_terminal", reasoning: "Explain WHY, not just WHAT, in commit messages" }
    ],
    outcome: "Feature implemented correctly on first try, with research backing decisions"
  },
  {
    scenario: "User says: 'Something is broken, fix it'",
    thinking: "Diagnose before fixing. Read logs, reproduce the issue, understand root cause, then apply targeted fix.",
    steps: [
      { action: "Check error logs", tool: "run_terminal", reasoning: "Read console output, build errors, or runtime exceptions" },
      { action: "Identify the failing component", tool: "read_file", reasoning: "Trace the error to the specific file and function" },
      { action: "Understand the root cause", tool: "read_file", reasoning: "Look at surrounding code — is it a type issue, logic bug, or missing dependency?" },
      { action: "Apply minimal fix", tool: "write_file", reasoning: "Fix only what's broken. Don't refactor unrelated code." },
      { action: "Verify fix", tool: "run_terminal", reasoning: "Build, test, confirm the error is resolved" },
      { action: "Add regression prevention", tool: "vault_remember", reasoning: "Log the bug pattern so we recognize it faster next time" }
    ],
    outcome: "Bug fixed with minimal changes, root cause documented"
  },
  {
    scenario: "Multi-step complex request requiring chaining",
    thinking: "Break into atomic steps. Each step should produce a verifiable result. Chain results between steps.",
    steps: [
      { action: "Decompose the request", tool: "vault_remember", reasoning: "Save the plan as a goal with sub-tasks" },
      { action: "Execute step 1", tool: "delegate_to_agent", reasoning: "Pick the right agent for the first sub-task" },
      { action: "Verify step 1 output", tool: "run_terminal", reasoning: "Confirm the output before proceeding" },
      { action: "Execute step 2 using step 1 results", tool: "delegate_to_agent", reasoning: "Pass previous output as context to next agent" },
      { action: "Final verification", tool: "run_terminal", reasoning: "End-to-end check that everything works together" },
      { action: "Update goal progress", tool: "goal_update", reasoning: "Track completion for accountability" }
    ],
    outcome: "Complex task completed through systematic decomposition and verification"
  }
]

// Convert to JSONL training entries
import * as fs from 'fs'
import * as path from 'path'

const trainingPath = path.join(__dirname, '..', 'training', 'learning_log.jsonl')

const entries = META_TRAINING.flatMap(pattern => {
  // Create a training entry for the scenario itself
  const mainEntry = {
    timestamp: new Date().toISOString(),
    user_input: pattern.scenario.replace("User says: ", "").replace(/'/g, ""),
    tool_used: "meta_workflow",
    tool_params: { steps: pattern.steps.length },
    response: `Thinking: ${pattern.thinking}\nSteps: ${pattern.steps.map(s => s.action).join(" → ")}\nOutcome: ${pattern.outcome}`,
    success: true,
    source: "developer_workflow"
  }

  // Create individual step entries
  const stepEntries = pattern.steps.map(step => ({
    timestamp: new Date().toISOString(),
    user_input: step.action,
    tool_used: step.tool,
    tool_params: {},
    response: step.reasoning,
    success: true,
    source: "developer_workflow_step"
  }))

  return [mainEntry, ...stepEntries]
})

// Append to learning log
const lines = entries.map(e => JSON.stringify(e)).join('\n') + '\n'
fs.appendFileSync(trainingPath, lines, 'utf-8')

console.log(`Saved ${entries.length} meta-learning entries to learning_log.jsonl`)
console.log(`JARVIS now knows ${META_TRAINING.length} workflow patterns`)
