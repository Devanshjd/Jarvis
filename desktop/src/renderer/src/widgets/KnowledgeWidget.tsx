/**
 * KnowledgeWidget — core memory knowledge browser + search via native IPC.
 */

import { useState, useEffect, useCallback } from 'react'
import {
  RiMindMap, RiSearchLine, RiRefreshLine,
  RiTimeLine, RiBrainLine
} from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

interface MemoryFact {
  fact: string
  savedAt: string
}

export default function KnowledgeWidget({ widget }: { widget: WidgetInstance }) {
  const [query, setQuery] = useState('')
  const [memories, setMemories] = useState<MemoryFact[]>([])
  const [loading, setLoading] = useState(false)

  const loadKnowledge = useCallback(async () => {
    setLoading(true)
    try {
      const r = await window.desktopApi.toolRetrieveCoreMemory()
      if (r.memories) {
        setMemories(r.memories)
      }
    } catch { /* */ }
    setLoading(false)
  }, [])

  useEffect(() => {
    loadKnowledge()
  }, [loadKnowledge])

  const filtered = query.trim()
    ? memories.filter(m => m.fact.toLowerCase().includes(query.toLowerCase()))
    : memories

  // Group by date
  const grouped = filtered.reduce<Record<string, MemoryFact[]>>((acc, m) => {
    const date = m.savedAt ? new Date(m.savedAt).toLocaleDateString() : 'Unknown'
    if (!acc[date]) acc[date] = []
    acc[date].push(m)
    return acc
  }, {})

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiMindMap />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col">
        <div className="flex items-center gap-2 border-b border-white/5 bg-black/30 px-4 py-3">
          <RiSearchLine className="text-zinc-500" size={14} />
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search knowledge..."
            className="flex-1 bg-transparent text-xs text-zinc-200 outline-none placeholder:text-zinc-600"
          />
          <span className="text-[9px] font-mono tracking-[0.16em] text-zinc-600">{memories.length}</span>
          <button onClick={loadKnowledge} className="rounded p-1 text-zinc-500 hover:text-emerald-400">
            <RiRefreshLine size={12} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>

        <div className="scrollbar-small flex-1 overflow-y-auto p-4">
          {loading && memories.length === 0 ? (
            <div className="text-center text-[10px] font-mono text-zinc-500 animate-pulse">LOADING KNOWLEDGE...</div>
          ) : filtered.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-zinc-600">
              <RiBrainLine size={28} className="opacity-20" />
              <span className="text-[10px] font-mono tracking-[0.28em]">{query ? 'NO MATCHES' : 'KNOWLEDGE GRAPH EMPTY'}</span>
              <span className="text-[9px] text-zinc-700">Memories saved via voice appear here</span>
            </div>
          ) : (
            <div className="space-y-4">
              {Object.entries(grouped).map(([date, facts]) => (
                <div key={date}>
                  <div className="mb-2 flex items-center gap-2 text-[9px] font-bold tracking-[0.18em] text-zinc-600">
                    <RiTimeLine size={10} /> {date}
                  </div>
                  <div className="space-y-1.5">
                    {facts.map((mem, idx) => (
                      <div key={idx} className="rounded-xl border border-white/5 bg-white/[0.02] p-3 transition-all hover:border-purple-500/20">
                        <div className="text-xs leading-6 text-zinc-300">{mem.fact}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </WidgetShell>
  )
}
