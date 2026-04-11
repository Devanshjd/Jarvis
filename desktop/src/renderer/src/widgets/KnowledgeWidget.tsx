/**
 * KnowledgeWidget — knowledge graph browser.
 */

import { useState } from 'react'
import { RiMindMap, RiSearchLine, RiAddLine } from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

const API_BASE = 'http://127.0.0.1:8765'

interface KnowledgeEntry { id: number; topic: string; content: string }

export default function KnowledgeWidget({ widget }: { widget: WidgetInstance }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<KnowledgeEntry[]>([])
  const [loading, setLoading] = useState(false)

  async function search() {
    if (!query.trim()) return
    setLoading(true)
    try {
      const resp = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: `search knowledge graph for: ${query}`, approve_desktop: false, timeout_s: 30 })
      })
      const data = await resp.json()
      setResults([{ id: Date.now(), topic: query, content: data.reply || 'No knowledge found.' }])
    } catch { setResults([]) }
    setLoading(false)
  }

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiMindMap />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col">
        <div className="flex items-center gap-2 border-b border-white/5 bg-black/30 px-4 py-3">
          <RiSearchLine className="text-zinc-500" size={14} />
          <input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && search()}
            placeholder="Search knowledge..." className="flex-1 bg-transparent text-xs text-zinc-200 outline-none placeholder:text-zinc-600" />
        </div>
        <div className="scrollbar-small flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="text-center text-[10px] font-mono text-zinc-500 animate-pulse">QUERYING KNOWLEDGE GRAPH...</div>
          ) : results.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-zinc-600">
              <RiMindMap size={32} className="opacity-20" />
              <span className="text-[10px] font-mono tracking-[0.28em]">SEARCH YOUR KNOWLEDGE</span>
              <span className="text-[9px] text-zinc-700">Facts, context, and learned patterns</span>
            </div>
          ) : results.map((r) => (
            <div key={r.id} className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
              <div className="mb-2 text-[10px] font-bold tracking-[0.16em] text-emerald-400 uppercase">{r.topic}</div>
              <div className="text-xs leading-6 text-zinc-300 whitespace-pre-wrap">{r.content}</div>
            </div>
          ))}
        </div>
      </div>
    </WidgetShell>
  )
}
