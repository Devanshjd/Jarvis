/**
 * MemoryWidget — browse, search, and add memories.
 */

import { useState, useEffect } from 'react'
import { RiBrainLine, RiAddLine, RiSearchLine } from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import { useStore, type WidgetInstance } from '../store/useStore'

const API_BASE = 'http://127.0.0.1:8765'

export default function MemoryWidget({ widget }: { widget: WidgetInstance }) {
  const snapshot = useStore((s) => s.snapshot)
  const memories = snapshot?.memories || []
  const [filter, setFilter] = useState('')
  const [newMemory, setNewMemory] = useState('')
  const [saving, setSaving] = useState(false)

  const filtered = filter
    ? memories.filter((m) => m.content.toLowerCase().includes(filter.toLowerCase()))
    : memories

  async function addMemory() {
    if (!newMemory.trim() || saving) return
    setSaving(true)
    try {
      await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: `remember this: ${newMemory}`, approve_desktop: false, timeout_s: 30 })
      })
      setNewMemory('')
    } catch { /* */ }
    setSaving(false)
  }

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiBrainLine />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col">
        {/* Search */}
        <div className="flex items-center gap-2 border-b border-white/5 bg-black/30 px-4 py-2.5">
          <RiSearchLine className="text-zinc-500" size={14} />
          <input value={filter} onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter memories..." className="flex-1 bg-transparent text-xs text-zinc-200 outline-none placeholder:text-zinc-600" />
          <span className="text-[9px] font-mono tracking-[0.18em] text-zinc-600">{filtered.length} ITEMS</span>
        </div>

        {/* Memory list */}
        <div className="scrollbar-small flex-1 space-y-2 overflow-y-auto p-4">
          {filtered.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-zinc-600">
              <RiBrainLine size={28} className="opacity-20" />
              <span className="text-[10px] font-mono tracking-[0.28em]">{filter ? 'NO MATCHES' : 'NO MEMORIES YET'}</span>
            </div>
          ) : filtered.map((mem) => (
            <div key={mem.id} className="rounded-xl border border-white/5 bg-white/[0.02] p-3 transition-all hover:border-emerald-500/20">
              <div className="text-xs leading-6 text-zinc-300">{mem.content}</div>
              <div className="mt-1 text-[9px] font-mono text-zinc-600">Memory #{mem.id}</div>
            </div>
          ))}
        </div>

        {/* Add memory */}
        <div className="flex items-center gap-2 border-t border-white/5 bg-black/30 px-4 py-3">
          <input value={newMemory} onChange={(e) => setNewMemory(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addMemory()}
            placeholder="Add a memory..." className="flex-1 bg-transparent text-xs text-zinc-200 outline-none placeholder:text-zinc-600" />
          <button onClick={addMemory} disabled={saving} className="rounded-lg bg-emerald-500/20 p-2 text-emerald-400 hover:bg-emerald-500/30 disabled:opacity-40">
            <RiAddLine size={14} />
          </button>
        </div>
      </div>
    </WidgetShell>
  )
}
