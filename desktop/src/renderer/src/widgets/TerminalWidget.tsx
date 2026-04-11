/**
 * TerminalWidget — embedded terminal with native IPC command execution.
 * Uses desktopApi.toolRunTerminal for direct OS-level commands.
 */

import { useState, useRef, useEffect } from 'react'
import { RiTerminalBoxLine, RiSendPlaneFill, RiDeleteBinLine } from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

interface TerminalEntry {
  id: number
  type: 'input' | 'output' | 'error' | 'system'
  text: string
  ts: string
  exitCode?: number
}

export default function TerminalWidget({ widget }: { widget: WidgetInstance }) {
  const [entries, setEntries] = useState<TerminalEntry[]>([
    { id: 0, type: 'system', text: 'JARVIS Terminal v2.0 — Native IPC execution.\nType commands to run directly on this system.', ts: new Date().toISOString() }
  ])
  const [cmd, setCmd] = useState('')
  const [running, setRunning] = useState(false)
  const [history, setHistory] = useState<string[]>([])
  const [historyIdx, setHistoryIdx] = useState(-1)
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
    setHistory(prev => [text, ...prev.slice(0, 49)])
    setHistoryIdx(-1)

    const inputEntry: TerminalEntry = { id: Date.now(), type: 'input', text, ts: new Date().toISOString() }
    setEntries(prev => [...prev, inputEntry])

    // Handle built-in commands
    if (text === 'clear' || text === 'cls') {
      setEntries([{ id: Date.now(), type: 'system', text: 'Terminal cleared.', ts: new Date().toISOString() }])
      setRunning(false)
      return
    }

    try {
      const r = await window.desktopApi.toolRunTerminal(text)
      const output = r.success
        ? r.output || '(no output)'
        : r.error || r.output || 'Command failed.'
      setEntries(prev => [...prev, {
        id: Date.now() + 1,
        type: r.success && r.exitCode === 0 ? 'output' : 'error',
        text: output,
        ts: new Date().toISOString(),
        exitCode: r.exitCode ?? undefined
      }])
    } catch (err) {
      setEntries(prev => [...prev, {
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

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') {
      runCommand()
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (history.length > 0) {
        const nextIdx = Math.min(historyIdx + 1, history.length - 1)
        setHistoryIdx(nextIdx)
        setCmd(history[nextIdx])
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (historyIdx > 0) {
        const nextIdx = historyIdx - 1
        setHistoryIdx(nextIdx)
        setCmd(history[nextIdx])
      } else {
        setHistoryIdx(-1)
        setCmd('')
      }
    }
  }

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiTerminalBoxLine />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col bg-[#0a0a0c]">
        {/* Toolbar */}
        <div className="flex items-center justify-between border-b border-white/5 bg-black/40 px-3 py-1.5">
          <span className="text-[8px] font-mono tracking-[0.2em] text-zinc-600">NATIVE SHELL</span>
          <div className="flex items-center gap-2">
            <span className="text-[8px] font-mono tracking-[0.16em] text-zinc-600">{entries.length - 1} CMD</span>
            <button
              onClick={() => setEntries([{ id: Date.now(), type: 'system', text: 'Terminal cleared.', ts: new Date().toISOString() }])}
              className="rounded p-1 text-zinc-600 hover:text-red-400"
            >
              <RiDeleteBinLine size={12} />
            </button>
          </div>
        </div>

        {/* Output area */}
        <div ref={scrollRef} className="scrollbar-small flex-1 overflow-y-auto p-4 font-mono text-[12px] leading-6">
          {entries.map(entry => (
            <div key={entry.id} className="mb-1">
              {entry.type === 'input' ? (
                <div className="flex gap-2">
                  <span className="text-emerald-500 select-none">❯</span>
                  <span className="text-emerald-100">{entry.text}</span>
                </div>
              ) : entry.type === 'error' ? (
                <div className="text-red-400 whitespace-pre-wrap">{entry.text}</div>
              ) : entry.type === 'system' ? (
                <div className="text-zinc-600 whitespace-pre-wrap italic">{entry.text}</div>
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
            onChange={e => setCmd(e.target.value)}
            onKeyDown={handleKeyDown}
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
