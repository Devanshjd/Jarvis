/**
 * VaultWidget — Knowledge Vault entity browser & search.
 * Shows entities, facts, and relationships from SQLite.
 */

import { useState, useEffect } from 'react'
import { RiDatabase2Line, RiSearchLine, RiLinksFill } from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

const api = (window as any).electron || (window as any).desktopApi

type Entity = { name: string; type: string; description: string; fact_count: number; facts?: string }
type Relation = { from_name: string; relation: string; to_name: string }

export default function VaultWidget({ widget }: { widget: WidgetInstance }) {
  const [entities, setEntities] = useState<Entity[]>([])
  const [relations, setRelations] = useState<Relation[]>([])
  const [search, setSearch] = useState('')
  const [mode, setMode] = useState<'entities' | 'relations'>('entities')

  const loadAll = async () => {
    try {
      const r = await api.vaultList()
      if (r.success) setEntities(r.entities || [])
    } catch { /* */ }
  }

  const handleSearch = async (q: string) => {
    setSearch(q)
    if (!q.trim()) { loadAll(); return }
    try {
      const r = await api.vaultQuery(q)
      if (r.success) {
        setEntities(r.entities || [])
        setRelations(r.relations || [])
      }
    } catch { /* */ }
  }

  useEffect(() => { void loadAll() }, [])

  const typeColors: Record<string, string> = {
    person: '#6366f1', language: '#10b981', tool: '#f59e0b', general: '#64748b',
    concept: '#ec4899', security: '#ef4444'
  }

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiDatabase2Line />}
      x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col gap-3 p-4 overflow-y-auto">
        {/* Search */}
        <div className="relative">
          <RiSearchLine className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-600" size={13} />
          <input
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="Search knowledge vault..."
            className="w-full rounded-lg border border-white/10 bg-white/5 pl-8 pr-3 py-2 text-[11px] text-zinc-300 placeholder-zinc-600 outline-none focus:border-cyan-500/30"
          />
        </div>

        {/* Tabs */}
        <div className="flex gap-1">
          <button onClick={() => setMode('entities')}
            className={`rounded-lg px-3 py-1.5 text-[9px] font-mono tracking-[0.15em] transition-all ${
              mode === 'entities' ? 'bg-cyan-500/20 text-cyan-400' : 'text-zinc-500 hover:text-zinc-300'
            }`}>ENTITIES ({entities.length})</button>
          <button onClick={() => setMode('relations')}
            className={`rounded-lg px-3 py-1.5 text-[9px] font-mono tracking-[0.15em] transition-all ${
              mode === 'relations' ? 'bg-cyan-500/20 text-cyan-400' : 'text-zinc-500 hover:text-zinc-300'
            }`}>RELATIONS ({relations.length})</button>
        </div>

        {/* Content */}
        {mode === 'entities' ? (
          <div className="flex flex-col gap-2">
            {entities.length === 0 && (
              <div className="text-center text-zinc-600 text-xs py-6">No entities yet. Say "Remember that..."</div>
            )}
            {entities.map((e, i) => (
              <div key={i} className="rounded-xl border border-white/5 bg-white/[0.02] p-3 space-y-1.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full" style={{ background: typeColors[e.type] || '#64748b' }} />
                    <span className="text-[11px] font-bold text-zinc-200">{e.name}</span>
                    <span className="rounded px-1.5 py-0.5 text-[8px] font-mono tracking-widest text-zinc-500 bg-white/5">{e.type}</span>
                  </div>
                  <span className="text-[9px] text-zinc-600">{e.fact_count || 0} facts</span>
                </div>
                {e.description && (
                  <p className="text-[10px] text-zinc-500 leading-relaxed">{e.description}</p>
                )}
                {e.facts && (
                  <p className="text-[10px] text-zinc-400 leading-relaxed border-l-2 border-cyan-500/20 pl-2">{e.facts}</p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {relations.length === 0 && (
              <div className="text-center text-zinc-600 text-xs py-6">No relationships found.</div>
            )}
            {relations.map((r, i) => (
              <div key={i} className="flex items-center gap-2 rounded-xl border border-white/5 bg-white/[0.02] p-3">
                <span className="text-[11px] font-bold text-indigo-400">{r.from_name}</span>
                <RiLinksFill className="text-zinc-600" size={10} />
                <span className="text-[10px] text-zinc-500 italic">{r.relation}</span>
                <RiLinksFill className="text-zinc-600" size={10} />
                <span className="text-[11px] font-bold text-emerald-400">{r.to_name}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </WidgetShell>
  )
}
