/**
 * TerminalWidget — embedded terminal with command execution.
 * Sends commands to the Python backend.
 */

import { useState, useRef, useEffect } from 'react'
import { RiTerminalBoxLine, RiSendPlaneFill } from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

const API_BASE = 'http://127.0.0.1:8765'

interface TerminalEntry {
  id: number
  type: 'input' | 'output' | 'error'
  text: string
  ts: string
}

export default function TerminalWidget({ widget }: { widget: WidgetInstance }) {
  const [entries, setEntries] = useState<TerminalEntry[]>([
    { id: 0, type: 'output', text: 'JARVIS Terminal v1.0 — Type commands below.\nBackend execution via Python runtime.', ts: new Date().toISOString() }
  ])
  const [cmd, setCmd] = useState('')
  const [running, setRunning] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight)
  }, [entries])

  async function runCommand() {
    const text = cmd.trim()
    if (!text || running) return
    setCmd('')
    setRunning(true)

    const inputEntry: TerminalEntry = { id: Date.now(), type: 'input', text, ts: new Date().toISOString() }
    setEntries((prev) => [...prev, inputEntry])

    try {
      const resp = await fetch(`${API_BASE}/api/terminal/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          command: text,
          timeout_s: 60
        })
      })
      const data = await resp.json()
      const output = data.error
        ? `Error: ${data.error}`
        : [data.stdout, data.stderr].filter(Boolean).join('\n') || 'Command executed (no output).'
      setEntries((prev) => [...prev, {
        id: Date.now() + 1,
        type: data.error || data.returncode !== 0 ? 'error' : 'output',
        text: output,
        ts: new Date().toISOString()
      }])
    } catch (err) {
      setEntries((prev) => [...prev, {
        id: Date.now() + 1,
        type: 'error',
        text: `Error: ${err instanceof Error ? err.message : String(err)}`,
        ts: new Date().toISOString()
      }])
    } finally {
      setRunning(false)
      inputRef.current?.focus()
    }
  }

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiTerminalBoxLine />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col bg-[#0a0a0c]">
        {/* Output area */}
        <div ref={scrollRef} className="scrollbar-small flex-1 overflow-y-auto p-4 font-mono text-[12px] leading-6">
          {entries.map((entry) => (
            <div key={entry.id} className="mb-1">
              {entry.type === 'input' ? (
                <div className="flex gap-2">
                  <span className="text-emerald-500 select-none">❯</span>
                  <span className="text-emerald-100">{entry.text}</span>
                </div>
              ) : entry.type === 'error' ? (
                <div className="text-red-400 whitespace-pre-wrap">{entry.text}</div>
              ) : (
                <div className="text-zinc-400 whitespace-pre-wrap">{entry.text}</div>
              )}
            </div>
          ))}
          {running && (
            <div className="text-emerald-500/50 animate-pulse">Processing...</div>
          )}
        </div>

        {/* Input */}
        <div className="flex items-center gap-2 border-t border-white/5 bg-black/40 px-4 py-3">
          <span className="text-emerald-500 text-sm select-none font-bold">❯</span>
          <input
            ref={inputRef}
            value={cmd}
            onChange={(e) => setCmd(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && runCommand()}
            placeholder="Enter command..."
            className="flex-1 bg-transparent text-sm text-zinc-200 outline-none placeholder:text-zinc-600 font-mono"
            autoFocus
          />
          <button
            onClick={runCommand}
            disabled={running}
            className="rounded-lg bg-emerald-500/20 p-2 text-emerald-400 transition-colors hover:bg-emerald-500/30 disabled:opacity-40"
          >
            <RiSendPlaneFill size={14} />
          </button>
        </div>
      </div>
    </WidgetShell>
  )
}
