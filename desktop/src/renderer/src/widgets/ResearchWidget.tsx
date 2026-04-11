/**
 * ResearchWidget — deep web research panel.
 */

import { useState } from 'react'
import { RiSearchEyeLine, RiSendPlaneFill, RiLoader4Line } from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

const API_BASE = 'http://127.0.0.1:8765'

interface ResearchResult { id: number; query: string; summary: string; ts: string }

export default function ResearchWidget({ widget }: { widget: WidgetInstance }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<ResearchResult[]>([])
  const [loading, setLoading] = useState(false)

  async function runResearch() {
    if (!query.trim() || loading) return
    setLoading(true)
    const currentQuery = query
    setQuery('')
    try {
      const resp = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: `research: ${currentQuery}`, approve_desktop: false, timeout_s: 120 })
      })
      const data = await resp.json()
      setResults((prev) => [{
        id: Date.now(),
        query: currentQuery,
        summary: data.reply || 'No results found.',
        ts: new Date().toISOString()
      }, ...prev])
    } catch (err) {
      setResults((prev) => [{
        id: Date.now(),
        query: currentQuery,
        summary: `Error: ${err instanceof Error ? err.message : String(err)}`,
        ts: new Date().toISOString()
      }, ...prev])
    }
    setLoading(false)
  }

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiSearchEyeLine />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col">
        {/* Search bar */}
        <div className="flex items-center gap-2 border-b border-white/5 bg-black/30 px-4 py-3">
          <input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && runResearch()}
            placeholder="What do you want to research?" className="flex-1 bg-transparent text-xs text-zinc-200 outline-none placeholder:text-zinc-600" />
          <button onClick={runResearch} disabled={loading} className="rounded-lg bg-emerald-500/20 p-2 text-emerald-400 hover:bg-emerald-500/30 disabled:opacity-40">
            {loading ? <RiLoader4Line size={14} className="animate-spin" /> : <RiSendPlaneFill size={14} />}
          </button>
        </div>

        {/* Results */}
        <div className="scrollbar-small flex-1 space-y-3 overflow-y-auto p-4">
          {loading && (
            <div className="flex items-center gap-2 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-3">
              <RiLoader4Line className="animate-spin text-emerald-400" size={14} />
              <span className="text-[11px] text-emerald-300">Researching... this may take a minute</span>
            </div>
          )}
          {results.length === 0 && !loading ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-zinc-600">
              <RiSearchEyeLine size={32} className="opacity-20" />
              <span className="text-[10px] font-mono tracking-[0.28em]">ENTER A RESEARCH QUERY</span>
            </div>
          ) : results.map((r) => (
            <div key={r.id} className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
              <div className="mb-2 text-[10px] font-bold tracking-[0.16em] text-emerald-400 uppercase">{r.query}</div>
              <div className="text-xs leading-6 text-zinc-300 whitespace-pre-wrap">{r.summary}</div>
              <div className="mt-2 text-[9px] font-mono text-zinc-600">{new Date(r.ts).toLocaleTimeString()}</div>
            </div>
          ))}
        </div>
      </div>
    </WidgetShell>
  )
}
