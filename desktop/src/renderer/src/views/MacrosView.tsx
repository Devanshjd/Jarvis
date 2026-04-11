import { useEffect, useState, useCallback } from 'react'
import {
  RiAddLine,
  RiCommandLine,
  RiDeleteBinLine,
  RiDragMoveLine,
  RiPlayFill,
  RiSave3Line,
  RiTerminalBoxLine
} from 'react-icons/ri'

/* ═══════════════════════════════════════════
   Macros View — Functional macro builder & runner
   ═══════════════════════════════════════════ */

interface MacroStep {
  type: string
  params: Record<string, string>
}

interface MacroItem {
  id: string
  name: string
  steps: MacroStep[]
}

const STEP_TYPES = [
  { value: 'open_app', label: 'OPEN APP', fields: [{ key: 'app', label: 'App Name', placeholder: 'chrome, discord, notepad...' }] },
  { value: 'run_terminal', label: 'RUN COMMAND', fields: [{ key: 'command', label: 'Command', placeholder: 'npm run dev' }, { key: 'path', label: 'Working Dir (optional)', placeholder: 'C:\\Users\\...' }] },
  { value: 'ghost_type', label: 'TYPE TEXT', fields: [{ key: 'text', label: 'Text', placeholder: 'Hello world...' }] },
  { value: 'press_shortcut', label: 'SHORTCUT', fields: [{ key: 'key', label: 'Key', placeholder: 'n, s, c...' }, { key: 'modifiers', label: 'Modifiers', placeholder: 'ctrl,shift,alt' }] },
  { value: 'google_search', label: 'SEARCH WEB', fields: [{ key: 'query', label: 'Query', placeholder: 'latest news...' }] },
  { value: 'wait', label: 'WAIT', fields: [{ key: 'seconds', label: 'Seconds', placeholder: '2' }] }
]

function newStep(): MacroStep {
  return { type: 'open_app', params: {} }
}

function genId() {
  return `macro_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
}

export default function MacrosView() {
  const [macros, setMacros] = useState<MacroItem[]>([])
  const [selected, setSelected] = useState<MacroItem | null>(null)
  const [editName, setEditName] = useState('')
  const [editSteps, setEditSteps] = useState<MacroStep[]>([])
  const [running, setRunning] = useState(false)
  const [runResult, setRunResult] = useState('')
  const [saving, setSaving] = useState(false)

  const loadMacros = useCallback(async () => {
    try {
      const list = await window.desktopApi.macrosList()
      setMacros(list)
    } catch { /* */ }
  }, [])

  useEffect(() => { loadMacros() }, [loadMacros])

  function selectMacro(macro: MacroItem) {
    setSelected(macro)
    setEditName(macro.name)
    setEditSteps(JSON.parse(JSON.stringify(macro.steps)))
    setRunResult('')
  }

  function createNew() {
    const fresh: MacroItem = { id: genId(), name: 'New Macro', steps: [newStep()] }
    setSelected(fresh)
    setEditName(fresh.name)
    setEditSteps(fresh.steps)
    setRunResult('')
  }

  async function saveCurrent() {
    if (!selected || !editName.trim()) return
    setSaving(true)
    const macro = { id: selected.id, name: editName.trim(), steps: editSteps }
    await window.desktopApi.macrosSave(macro)
    await loadMacros()
    setSelected(macro)
    setSaving(false)
  }

  async function deleteCurrent() {
    if (!selected) return
    await window.desktopApi.macrosDelete(selected.id)
    setSelected(null)
    setEditSteps([])
    setEditName('')
    await loadMacros()
  }

  async function runCurrent() {
    if (!editName.trim()) return
    setRunning(true)
    setRunResult('')
    // Save first, then run
    const macro = { id: selected?.id || genId(), name: editName.trim(), steps: editSteps }
    await window.desktopApi.macrosSave(macro)
    await loadMacros()
    try {
      const r = await window.desktopApi.toolExecuteMacro(editName.trim())
      setRunResult(r.success ? r.message || 'Completed' : `Error: ${r.error}`)
    } catch (err) {
      setRunResult(`Error: ${(err as Error).message}`)
    }
    setRunning(false)
  }

  function updateStep(index: number, field: string, value: string) {
    const next = [...editSteps]
    if (field === 'type') {
      next[index] = { type: value, params: {} }
    } else {
      next[index] = { ...next[index], params: { ...next[index].params, [field]: value } }
    }
    setEditSteps(next)
  }

  function removeStep(index: number) {
    setEditSteps(editSteps.filter((_, i) => i !== index))
  }

  function addStep() {
    setEditSteps([...editSteps, newStep()])
  }

  function moveStep(index: number, dir: -1 | 1) {
    const next = [...editSteps]
    const target = index + dir
    if (target < 0 || target >= next.length) return
    ;[next[index], next[target]] = [next[target], next[index]]
    setEditSteps(next)
  }

  return (
    <div className="flex h-full bg-[#09090b]">
      {/* ─── Left sidebar — Macro list ─── */}
      <aside className="scrollbar-small hidden h-full w-72 flex-col overflow-y-auto border-r border-white/5 bg-[#111113] p-4 lg:flex">
        <div className="mb-4 flex items-center justify-between border-b border-[#27272a] pb-3">
          <h2 className="text-[10px] font-black tracking-[0.24em] text-emerald-500">
            NEURAL PATTERNS
          </h2>
          <button
            onClick={createNew}
            className="rounded-lg border border-[#27272a] bg-[#18181b] p-2 text-zinc-400 transition-colors hover:border-emerald-500/30 hover:text-emerald-400"
          >
            <RiAddLine size={14} />
          </button>
        </div>

        {macros.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 text-zinc-700">
            <RiCommandLine size={28} />
            <span className="text-[10px] font-mono tracking-[0.28em]">NO MACROS YET</span>
            <button onClick={createNew} className="mt-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-[10px] font-bold tracking-[0.16em] text-emerald-400 hover:bg-emerald-500/20">
              CREATE FIRST MACRO
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            {macros.map(macro => (
              <button
                key={macro.id}
                onClick={() => selectMacro(macro)}
                className={`w-full rounded-xl border px-4 py-3 text-left transition-all ${
                  selected?.id === macro.id
                    ? 'border-emerald-500/40 bg-emerald-950/30 text-emerald-300'
                    : 'border-[#27272a] bg-[#18181b] text-zinc-200 hover:border-emerald-500/20'
                }`}
              >
                <div className="text-[11px] font-bold tracking-[0.16em]">{macro.name}</div>
                <div className="mt-1 text-[9px] font-mono tracking-[0.2em] text-zinc-500">
                  {macro.steps.length} STEP{macro.steps.length !== 1 ? 'S' : ''}
                </div>
              </button>
            ))}
          </div>
        )}

        {/* Module library */}
        <div className="mt-6 border-t border-[#27272a] pt-4">
          <h3 className="mb-3 text-[10px] font-bold tracking-[0.22em] text-zinc-500">STEP TYPES</h3>
          <div className="space-y-1.5">
            {STEP_TYPES.map(st => (
              <div key={st.value} className="rounded-lg border border-[#27272a] bg-[#18181b] px-3 py-2 text-[10px] font-bold tracking-[0.16em] text-zinc-400">
                {st.label}
              </div>
            ))}
          </div>
        </div>
      </aside>

      {/* ─── Main editor area ─── */}
      <div className="relative flex-1 overflow-hidden">
        <div className="absolute inset-0 iris-grid-bg" />
        <div className="relative flex h-full flex-col">
          {/* Top toolbar */}
          <div className="z-10 flex items-center gap-3 border-b border-white/5 bg-black/60 px-4 py-3 backdrop-blur-lg">
            <button onClick={createNew} className="rounded-lg border border-[#27272a] bg-[#18181b] p-2.5 text-zinc-400 transition-colors hover:text-emerald-400">
              <RiAddLine size={16} />
            </button>
            {selected && (
              <>
                <input
                  value={editName}
                  onChange={e => setEditName(e.target.value)}
                  className="rounded-lg border border-[#27272a] bg-[#18181b] px-4 py-2.5 text-sm font-bold text-white outline-none focus:border-emerald-500/40"
                  placeholder="Macro name..."
                />
                <div className="flex-1" />
                <button
                  onClick={runCurrent}
                  disabled={running || editSteps.length === 0}
                  className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-950/30 px-5 py-2.5 text-[11px] font-black tracking-[0.18em] text-emerald-400 transition-colors hover:bg-emerald-500/20 disabled:opacity-40"
                >
                  <RiPlayFill className={running ? 'animate-pulse' : ''} /> {running ? 'RUNNING...' : 'RUN'}
                </button>
                <button
                  onClick={saveCurrent}
                  disabled={saving}
                  className="flex items-center gap-2 rounded-lg bg-emerald-500 px-6 py-2.5 text-[11px] font-black tracking-[0.18em] text-black transition-colors hover:bg-emerald-400"
                >
                  <RiSave3Line /> {saving ? 'SAVING...' : 'SAVE'}
                </button>
                <button
                  onClick={deleteCurrent}
                  className="rounded-lg border border-red-500/30 bg-red-500/10 p-2.5 text-red-400 transition-colors hover:bg-red-500/20"
                >
                  <RiDeleteBinLine size={16} />
                </button>
              </>
            )}
          </div>

          {/* Steps editor */}
          {!selected ? (
            <div className="flex flex-1 items-center justify-center">
              <div className="text-center">
                <RiCommandLine size={48} className="mx-auto text-zinc-800" />
                <p className="mt-4 text-[10px] font-mono tracking-[0.3em] text-zinc-700">SELECT OR CREATE A MACRO TO START</p>
                <button onClick={createNew} className="mt-4 rounded-xl bg-emerald-500 px-6 py-3 text-[11px] font-black tracking-[0.18em] text-black hover:bg-emerald-400">
                  + NEW MACRO
                </button>
              </div>
            </div>
          ) : (
            <div className="scrollbar-small flex-1 overflow-y-auto p-6">
              <div className="mx-auto max-w-3xl space-y-3">
                {editSteps.map((step, idx) => {
                  const typeDef = STEP_TYPES.find(s => s.value === step.type) || STEP_TYPES[0]
                  return (
                    <div key={idx} className="group rounded-2xl border border-white/5 bg-[#111113] p-4 transition-all hover:border-emerald-500/20">
                      <div className="mb-3 flex items-center gap-3">
                        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 text-[10px] font-black text-emerald-400">
                          {idx + 1}
                        </span>
                        <select
                          value={step.type}
                          onChange={e => updateStep(idx, 'type', e.target.value)}
                          className="rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-[11px] font-bold tracking-[0.12em] text-emerald-400 outline-none focus:border-emerald-500/40"
                        >
                          {STEP_TYPES.map(st => (
                            <option key={st.value} value={st.value}>{st.label}</option>
                          ))}
                        </select>
                        <div className="flex-1" />
                        <button onClick={() => moveStep(idx, -1)} disabled={idx === 0} className="rounded p-1.5 text-zinc-600 hover:text-zinc-300 disabled:opacity-20">
                          <RiDragMoveLine size={14} className="rotate-180" />
                        </button>
                        <button onClick={() => moveStep(idx, 1)} disabled={idx === editSteps.length - 1} className="rounded p-1.5 text-zinc-600 hover:text-zinc-300 disabled:opacity-20">
                          <RiDragMoveLine size={14} />
                        </button>
                        <button onClick={() => removeStep(idx)} className="rounded p-1.5 text-zinc-600 hover:text-red-400">
                          <RiDeleteBinLine size={14} />
                        </button>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        {typeDef.fields.map(field => (
                          <input
                            key={field.key}
                            value={step.params[field.key] || ''}
                            onChange={e => updateStep(idx, field.key, e.target.value)}
                            placeholder={field.placeholder}
                            className="rounded-xl border border-white/10 bg-black/40 px-3 py-2.5 text-xs text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-emerald-500/40"
                          />
                        ))}
                      </div>
                    </div>
                  )
                })}

                <button
                  onClick={addStep}
                  className="w-full rounded-2xl border border-dashed border-white/10 bg-white/[0.02] py-4 text-[10px] font-bold tracking-[0.2em] text-zinc-500 transition-colors hover:border-emerald-500/30 hover:text-emerald-400"
                >
                  + ADD STEP
                </button>
              </div>

              {/* Run result */}
              {runResult && (
                <div className="mx-auto mt-6 max-w-3xl rounded-2xl border border-emerald-500/20 bg-emerald-900/10 p-4">
                  <div className="mb-2 flex items-center gap-2 text-[10px] font-bold tracking-[0.18em] text-emerald-400">
                    <RiTerminalBoxLine size={14} /> EXECUTION LOG
                  </div>
                  <pre className="whitespace-pre-wrap text-[11px] font-mono leading-6 text-emerald-200/80">
                    {runResult}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
