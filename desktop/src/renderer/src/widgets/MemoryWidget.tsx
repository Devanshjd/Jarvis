/**
 * MemoryWidget — browse, search, and add core memories via native IPC.
 */

import { useState, useEffect, useCallback } from 'react'
import { RiBrainLine, RiAddLine, RiSearchLine, RiRefreshLine, RiDeleteBinLine } from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

interface MemoryEntry {
  fact: string
  savedAt: string
}

export default function MemoryWidget({ widget }: { widget: WidgetInstance }) {
  const [memories, setMemories] = useState<MemoryEntry[]>([])
  const [filter, setFilter] = useState('')
  const [newMemory, setNewMemory] = useState('')
  const [saving, setSaving] = useState(false)
  const [total, setTotal] = useState(0)

  const loadMemories = useCallback(async () => {
    try {
      const r = await window.desktopApi.toolRetrieveCoreMemory()
      if (r.memories) {
        setMemories(r.memories)
        setTotal(r.total || r.memories.length)
      }
    } catch { /* */ }
  }, [])

  useEffect(() => {
    loadMemories()
  }, [loadMemories])

  const filtered = filter
    ? memories.filter(m => m.fact.toLowerCase().includes(filter.toLowerCase()))
    : memories

  async function addMemory() {
    if (!newMemory.trim() || saving) return
    setSaving(true)
    try {
      const r = await window.desktopApi.toolSaveCoreMemory(newMemory.trim())
      if (r.success) {
        setNewMemory('')
        await loadMemories()
      }
    } catch { /* */ }
    setSaving(false)
  }

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiBrainLine />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col">
        {/* Search + stats */}
        <div className="flex items-center gap-2 border-b border-white/5 bg-black/30 px-4 py-2.5">
          <RiSearchLine className="text-zinc-500" size={14} />
          <input
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder="Filter memories..."
            className="flex-1 bg-transparent text-xs text-zinc-200 outline-none placeholder:text-zinc-600"
          />
          <span className="text-[9px] font-mono tracking-[0.18em] text-zinc-600">{total} ITEMS</span>
          <button onClick={loadMemories} className="rounded p-1 text-zinc-500 hover:text-emerald-400">
            <RiRefreshLine size={12} />
          </button>
        </div>

        {/* Memory list */}
        <div className="scrollbar-small flex-1 space-y-2 overflow-y-auto p-4">
          {filtered.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-zinc-600">
              <RiBrainLine size={28} className="opacity-20" />
              <span className="text-[10px] font-mono tracking-[0.28em]">{filter ? 'NO MATCHES' : 'NO MEMORIES YET'}</span>
              <span className="text-[9px] text-zinc-700">Add facts JARVIS should remember forever</span>
            </div>
          ) : filtered.map((mem, idx) => (
            <div key={idx} className="rounded-xl border border-white/5 bg-white/[0.02] p-3 transition-all hover:border-purple-500/20">
              <div className="text-xs leading-6 text-zinc-300">{mem.fact}</div>
              {mem.savedAt && (
                <div className="mt-1 text-[8px] font-mono text-zinc-600">
                  {new Date(mem.savedAt).toLocaleString()}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Add memory */}
        <div className="flex items-center gap-2 border-t border-white/5 bg-black/30 px-4 py-3">
          <input
            value={newMemory}
            onChange={e => setNewMemory(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addMemory()}
            placeholder="Add a memory..."
            className="flex-1 bg-transparent text-xs text-zinc-200 outline-none placeholder:text-zinc-600"
          />
          <button
            onClick={addMemory}
            disabled={saving || !newMemory.trim()}
            className="rounded-lg bg-emerald-500/20 p-2 text-emerald-400 hover:bg-emerald-500/30 disabled:opacity-40"
          >
            <RiAddLine size={14} />
          </button>
        </div>
      </div>
    </WidgetShell>
  )
}
