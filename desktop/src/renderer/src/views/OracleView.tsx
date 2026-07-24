import { useState } from 'react'
import { RiDatabase2Line, RiSearchLine, RiFileCodeLine, RiLoader4Line } from 'react-icons/ri'
import { API_BASE, fetchJson } from '../lib/types'

/* ═══════════════════════════════════════════
   Code Oracle — local RAG over a repository.
   Pick a repo → Index → ask questions → answers
   with file:line citations. 100% local.
   ═══════════════════════════════════════════ */

interface Source {
  file: string
  lines: string
  score: number
}

export default function OracleView() {
  const [repo, setRepo] = useState('')
  const [indexing, setIndexing] = useState(false)
  const [indexInfo, setIndexInfo] = useState<string>('')
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [answer, setAnswer] = useState('')
  const [sources, setSources] = useState<Source[]>([])
  const [error, setError] = useState('')

  async function doIndex() {
    if (!repo.trim() || indexing) return
    setIndexing(true)
    setError('')
    setIndexInfo('')
    try {
      const r = await fetchJson<{
        success: boolean; files_indexed?: number; chunks?: number
        elapsed_s?: number; error?: string
      }>(`${API_BASE}/api/oracle/index`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_path: repo.trim() })
      })
      if (r.success) {
        setIndexInfo(`✓ indexed ${r.files_indexed} files · ${r.chunks} chunks · ${r.elapsed_s}s`)
      } else {
        setError(r.error || 'Index failed')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setIndexing(false)
  }

  async function doAsk() {
    if (!question.trim() || !repo.trim() || asking) return
    setAsking(true)
    setError('')
    setAnswer('')
    setSources([])
    try {
      const r = await fetchJson<{
        success: boolean; answer?: string; sources?: Source[]; error?: string
      }>(`${API_BASE}/api/oracle/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_path: repo.trim(), question: question.trim() })
      })
      if (r.success) {
        setAnswer(r.answer || '(no answer)')
        setSources(r.sources || [])
      } else {
        setError(r.error || 'Ask failed')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setAsking(false)
  }

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col gap-4 overflow-y-auto p-6">
      <div>
        <h1 className="text-lg font-black tracking-[0.22em] text-zinc-100">CODE ORACLE</h1>
        <p className="mt-1 text-[11px] font-mono tracking-[0.18em] text-amber-500/70">
          ASK A REPOSITORY QUESTIONS — 100% LOCAL RAG
        </p>
      </div>

      {/* Repo + Index */}
      <div className="sb-panel p-4">
        <label className="sb-label mb-2 flex items-center gap-2">
          <RiDatabase2Line /> REPOSITORY PATH
        </label>
        <div className="flex gap-2">
          <input
            value={repo}
            onChange={(e) => setRepo(e.target.value)}
            placeholder="C:\path\to\repo"
            className="flex-1 rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-amber-500/40"
          />
          <button
            onClick={doIndex}
            disabled={indexing || !repo.trim()}
            className="flex items-center gap-2 rounded-lg bg-amber-500 px-5 py-2.5 text-[11px] font-black tracking-[0.16em] text-black transition-colors hover:bg-amber-400 disabled:opacity-40"
          >
            {indexing ? <RiLoader4Line className="animate-spin" /> : <RiDatabase2Line />}
            {indexing ? 'INDEXING…' : 'INDEX'}
          </button>
        </div>
        {indexInfo && <div className="mt-2 text-[11px] font-mono text-emerald-400/80">{indexInfo}</div>}
        <p className="mt-2 text-[10px] text-zinc-600">
          Index once per repo (re-run to refresh). Skips node_modules/.git/etc.
        </p>
      </div>

      {/* Ask */}
      <div className="sb-panel p-4">
        <label className="sb-label mb-2 flex items-center gap-2">
          <RiSearchLine /> ASK
        </label>
        <div className="flex gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void doAsk() }}
            placeholder="where is authentication handled?"
            className="flex-1 rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-amber-500/40"
          />
          <button
            onClick={doAsk}
            disabled={asking || !question.trim() || !repo.trim()}
            className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-950/30 px-5 py-2.5 text-[11px] font-black tracking-[0.16em] text-amber-400 transition-colors hover:bg-amber-500/20 disabled:opacity-40"
          >
            {asking ? <RiLoader4Line className="animate-spin" /> : <RiSearchLine />}
            {asking ? 'THINKING…' : 'ASK'}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Answer */}
      {answer && (
        <div className="sb-panel p-4">
          <div className="mb-2 text-[10px] font-bold tracking-[0.18em] text-amber-400">ANSWER</div>
          <pre className="whitespace-pre-wrap text-[13px] leading-6 text-zinc-200">{answer}</pre>
          {sources.length > 0 && (
            <div className="mt-4 border-t border-white/10 pt-3">
              <div className="mb-2 text-[10px] font-bold tracking-[0.18em] text-zinc-500">SOURCES</div>
              <div className="space-y-1.5">
                {sources.map((s, i) => (
                  <div key={i} className="flex items-center gap-2 text-[11px] font-mono text-zinc-400">
                    <RiFileCodeLine className="text-amber-500/60" />
                    <span className="text-amber-300/90">{s.file}:{s.lines}</span>
                    <span className="text-zinc-600">score {s.score}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
