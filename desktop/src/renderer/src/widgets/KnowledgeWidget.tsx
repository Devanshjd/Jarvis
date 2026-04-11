/**
 * KnowledgeWidget — RAG-powered document search + core memory browser.
 * Phase 3: Ingest documents, semantic search, browse knowledge base.
 */

import { useState, useEffect, useCallback } from 'react'
import {
  RiMindMap, RiSearchLine, RiRefreshLine,
  RiTimeLine, RiBrainLine, RiFileAddLine,
  RiDeleteBinLine, RiDatabase2Line, RiLoader4Line,
  RiBookOpenLine, RiFileTextLine
} from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

interface MemoryFact {
  fact: string
  savedAt: string
}

interface VectorDoc {
  id: string
  filename: string
  filePath: string
  ingestedAt: string
  chunks: number
  size: number
}

interface SearchResult {
  text: string
  score: number
  docId: string
  filename: string
  chunkIndex: number
}

type Tab = 'search' | 'documents' | 'memories'

export default function KnowledgeWidget({ widget }: { widget: WidgetInstance }) {
  const [tab, setTab] = useState<Tab>('search')
  const [query, setQuery] = useState('')
  const [ingestPath, setIngestPath] = useState('')
  const [memories, setMemories] = useState<MemoryFact[]>([])
  const [documents, setDocuments] = useState<VectorDoc[]>([])
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [searchType, setSearchType] = useState('')
  const [loading, setLoading] = useState(false)

  const loadData = useCallback(async () => {
    try {
      const [memRes, docRes] = await Promise.all([
        window.desktopApi.toolRetrieveCoreMemory(),
        window.desktopApi.ragListDocuments()
      ])
      if (memRes.memories) setMemories(memRes.memories)
      if (docRes.documents) setDocuments(docRes.documents)
    } catch { /* */ }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  async function handleSearch() {
    if (!query.trim() || loading) return
    setLoading(true)
    try {
      const r = await window.desktopApi.ragSearch(query.trim(), 5)
      if (r.success && r.results) {
        setSearchResults(r.results)
        setSearchType(r.searchType || '')
      }
    } catch { /* */ }
    setLoading(false)
  }

  async function handleIngest() {
    if (!ingestPath.trim() || loading) return
    setLoading(true)
    try {
      const r = await window.desktopApi.ragIngest(ingestPath.trim())
      if (r.success) {
        setIngestPath('')
        await loadData()
      }
    } catch { /* */ }
    setLoading(false)
  }

  async function handleDelete(docId: string) {
    try {
      await window.desktopApi.ragDeleteDocument(docId)
      await loadData()
    } catch { /* */ }
  }

  const tabs: Array<{ key: Tab; label: string; icon: React.ReactNode }> = [
    { key: 'search', label: 'SEARCH', icon: <RiSearchLine size={12} /> },
    { key: 'documents', label: 'DOCS', icon: <RiDatabase2Line size={12} /> },
    { key: 'memories', label: 'MEMORY', icon: <RiBrainLine size={12} /> },
  ]

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiMindMap />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col">
        {/* Tabs */}
        <div className="flex items-center gap-1 border-b border-white/5 bg-black/30 px-3 py-2">
          {tabs.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[8px] font-bold tracking-[0.12em] transition-all ${
                tab === t.key
                  ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30'
                  : 'text-zinc-500 border border-white/5 hover:text-zinc-300'
              }`}
            >
              {t.icon} {t.label}
            </button>
          ))}
          <div className="ml-auto flex items-center gap-1.5 text-[8px] font-mono tracking-[0.14em] text-zinc-600">
            <RiDatabase2Line size={10} /> {documents.length} docs • {memories.length} mem
          </div>
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-hidden">
          {/* SEARCH TAB */}
          {tab === 'search' && (
            <div className="flex h-full flex-col">
              <div className="flex items-center gap-2 border-b border-white/5 bg-black/20 px-3 py-2.5">
                <RiBookOpenLine className="text-zinc-500" size={14} />
                <input
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSearch()}
                  placeholder="Semantic search..."
                  className="flex-1 bg-transparent text-xs text-zinc-200 outline-none placeholder:text-zinc-600"
                />
                <button onClick={handleSearch} disabled={loading} className="rounded-lg bg-purple-500/20 p-2 text-purple-400 hover:bg-purple-500/30 disabled:opacity-40">
                  {loading ? <RiLoader4Line size={12} className="animate-spin" /> : <RiSearchLine size={12} />}
                </button>
              </div>
              <div className="scrollbar-small flex-1 space-y-2 overflow-y-auto p-3">
                {searchResults.length === 0 ? (
                  <div className="flex h-full flex-col items-center justify-center gap-3 text-zinc-600">
                    <RiMindMap size={28} className="opacity-20" />
                    <span className="text-[10px] font-mono tracking-[0.28em]">SEMANTIC SEARCH</span>
                    <span className="text-[9px] text-zinc-700">Ingest docs, then search your knowledge</span>
                  </div>
                ) : (
                  <>
                    <div className="text-[9px] font-mono text-zinc-600">{searchResults.length} results via {searchType}</div>
                    {searchResults.map((r, i) => (
                      <div key={i} className="rounded-xl border border-purple-500/10 bg-purple-500/[0.03] p-3">
                        <div className="mb-1 flex items-center justify-between">
                          <span className="text-[9px] font-bold tracking-[0.12em] text-purple-400">{r.filename} #{r.chunkIndex}</span>
                          <span className="text-[8px] font-mono text-zinc-600">score: {r.score}</span>
                        </div>
                        <div className="text-[11px] leading-5 text-zinc-300">{r.text.slice(0, 300)}{r.text.length > 300 ? '...' : ''}</div>
                      </div>
                    ))}
                  </>
                )}
              </div>
            </div>
          )}

          {/* DOCUMENTS TAB */}
          {tab === 'documents' && (
            <div className="flex h-full flex-col">
              {/* Ingest input */}
              <div className="flex items-center gap-2 border-b border-white/5 bg-black/20 px-3 py-2.5">
                <RiFileAddLine className="text-zinc-500" size={14} />
                <input
                  value={ingestPath}
                  onChange={e => setIngestPath(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleIngest()}
                  placeholder="File path to ingest..."
                  className="flex-1 bg-transparent text-xs text-zinc-200 outline-none placeholder:text-zinc-600"
                />
                <button onClick={handleIngest} disabled={loading || !ingestPath.trim()} className="rounded-lg bg-emerald-500/20 px-3 py-1.5 text-[9px] font-bold tracking-[0.14em] text-emerald-400 hover:bg-emerald-500/30 disabled:opacity-40">
                  {loading ? <RiLoader4Line size={12} className="animate-spin" /> : 'INGEST'}
                </button>
              </div>
              <div className="scrollbar-small flex-1 space-y-2 overflow-y-auto p-3">
                {documents.length === 0 ? (
                  <div className="flex h-full flex-col items-center justify-center gap-3 text-zinc-600">
                    <RiDatabase2Line size={28} className="opacity-20" />
                    <span className="text-[10px] font-mono tracking-[0.28em]">NO DOCUMENTS</span>
                    <span className="text-[9px] text-zinc-700">Ingest files to build your knowledge base</span>
                  </div>
                ) : documents.map(doc => (
                  <div key={doc.id} className="group flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 transition-all hover:border-purple-500/20">
                    <RiFileTextLine className="text-purple-400/60" size={18} />
                    <div className="flex-1">
                      <div className="text-[11px] font-bold text-zinc-200">{doc.filename}</div>
                      <div className="text-[9px] font-mono text-zinc-600">
                        {doc.chunks} chunks • {doc.size.toLocaleString()} chars • {new Date(doc.ingestedAt).toLocaleDateString()}
                      </div>
                    </div>
                    <button
                      onClick={() => handleDelete(doc.id)}
                      className="opacity-0 group-hover:opacity-100 rounded p-1 text-zinc-600 hover:text-red-400"
                    >
                      <RiDeleteBinLine size={14} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* MEMORIES TAB */}
          {tab === 'memories' && (
            <div className="flex h-full flex-col">
              <div className="flex items-center justify-between border-b border-white/5 bg-black/20 px-3 py-2">
                <span className="text-[9px] font-mono tracking-[0.16em] text-zinc-600">{memories.length} CORE MEMORIES</span>
                <button onClick={loadData} className="rounded p-1 text-zinc-500 hover:text-emerald-400">
                  <RiRefreshLine size={12} />
                </button>
              </div>
              <div className="scrollbar-small flex-1 space-y-1.5 overflow-y-auto p-3">
                {memories.length === 0 ? (
                  <div className="flex h-full flex-col items-center justify-center gap-3 text-zinc-600">
                    <RiBrainLine size={28} className="opacity-20" />
                    <span className="text-[10px] font-mono tracking-[0.28em]">NO MEMORIES</span>
                  </div>
                ) : memories.map((mem, idx) => (
                  <div key={idx} className="rounded-xl border border-white/5 bg-white/[0.02] p-2.5">
                    <div className="text-[11px] leading-5 text-zinc-300">{mem.fact}</div>
                    {mem.savedAt && (
                      <div className="mt-1 flex items-center gap-1 text-[8px] font-mono text-zinc-600">
                        <RiTimeLine size={9} /> {new Date(mem.savedAt).toLocaleString()}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </WidgetShell>
  )
}
