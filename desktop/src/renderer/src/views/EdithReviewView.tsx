import { useCallback, useEffect, useMemo, useState } from 'react'
import { RiFileCodeLine, RiHistoryLine, RiLoader4Line } from 'react-icons/ri'
import { API_BASE, fetchJson, type EdithQueue, type EdithQueueItem } from '../lib/types'

type EdithAction = 'approve' | 'reject' | 'rollback' | 'approve_all' | 'reject_all'

type EdithReviewViewProps = {
  onPendingCountChange: (count: number) => void
}

function timestamp(value?: string) {
  if (!value) return 'UNKNOWN TIME'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }).toUpperCase()
}

function statusClass(status: string) {
  if (status === 'applied') return 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300'
  if (status === 'rolled_back') return 'border-amber-500/25 bg-amber-500/10 text-amber-300'
  if (status === 'rejected' || status === 'failed') return 'border-red-500/25 bg-red-500/10 text-red-300'
  return 'border-amber-500/25 bg-amber-500/10 text-amber-300'
}

function isPatchableCode(item: EdithQueueItem) {
  return item.kind === 'code' && item.has_payload === true
}

function proofText(item: EdithQueueItem) {
  const proof = item.proof
  if (!proof) return 'NO SANDBOX REPORT'
  if (typeof proof.before === 'number' && typeof proof.after === 'number') {
    return `SCORE ${proof.before} -> ${proof.after}`
  }
  return proof.passed ? proof.note || 'SANDBOX PASSED' : proof.note || 'SANDBOX DID NOT PASS'
}

export default function EdithReviewView({ onPendingCountChange }: EdithReviewViewProps) {
  const [queue, setQueue] = useState<EdithQueue>({ pending: [], recent: [], counts: {} })
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [acting, setActing] = useState<string | null>(null)
  const [reviewedCode, setReviewedCode] = useState<Record<string, boolean>>({})
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const refresh = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true)
    try {
      const next = await fetchJson<EdithQueue>(`${API_BASE}/api/edith/queue?limit=50`)
      const normalised: EdithQueue = {
        pending: Array.isArray(next.pending) ? next.pending : [],
        recent: Array.isArray(next.recent) ? next.recent : [],
        counts: next.counts || {}
      }
      setQueue(normalised)
      onPendingCountChange(normalised.pending.length)
      setReviewedCode((current) => Object.fromEntries(
        Object.entries(current).filter(([id]) => normalised.pending.some((item) => item.id === id)
      )) as Record<string, boolean>)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
      if (showSpinner) setRefreshing(false)
    }
  }, [onPendingCountChange])

  useEffect(() => {
    void refresh()
    const interval = window.setInterval(() => void refresh(), 8000)
    return () => window.clearInterval(interval)
  }, [refresh])

  const pendingCode = useMemo(() => queue.pending.filter(isPatchableCode), [queue.pending])
  // A generic code proposal may not carry a patch, but it still deserves an
  // individual read. Never let the batch endpoint decide any code item.
  const hasAnyPendingCode = useMemo(() => queue.pending.some((item) => item.kind === 'code'), [queue.pending])
  const allCounts = Object.entries(queue.counts).filter(([, count]) => count > 0)

  async function decide(action: EdithAction, item?: EdithQueueItem) {
    if (action === 'reject_all' && !window.confirm('Reject every pending EDITH proposal? Rejected drafts are not applied.')) return
    const key = item ? `${action}:${item.id}` : action
    setActing(key)
    setError('')
    setMessage('')
    try {
      const needsId = action !== 'approve_all' && action !== 'reject_all'
      await fetchJson<unknown>(`${API_BASE}/api/edith/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: needsId ? JSON.stringify({ id: item?.id }) : undefined
      })
      const label = action === 'approve' ? 'APPROVED'
        : action === 'reject' ? 'REJECTED'
          : action === 'rollback' ? 'ROLLED BACK'
            : action === 'approve_all' ? 'NON-CODE DIGEST APPROVED'
              : 'DIGEST REJECTED'
      setMessage(item ? `${label}: ${item.target || item.title || item.id}` : label)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setActing(null)
    }
  }

  return (
    <div className="scrollbar-small h-full overflow-y-auto p-5 lg:p-6">
      <div className="mx-auto flex max-w-6xl flex-col gap-5 pb-8">
        <header className="flex flex-col justify-between gap-4 border-b border-white/10 pb-5 sm:flex-row sm:items-end">
          <div>
            <div className="flex items-center gap-2 text-[11px] font-mono tracking-[0.25em] text-emerald-400">
              <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_12px_rgba(74,222,128,0.7)]" />
              EDITH / HUMAN REVIEW GATE
            </div>
            <h1 className="mt-2 text-xl font-black tracking-[0.18em] text-zinc-100">IMPROVEMENT DIGEST</h1>
            <p className="mt-2 max-w-2xl text-xs leading-5 text-zinc-500">
              Green changes already pass through safely. Red changes stay here until you inspect the evidence and decide.
            </p>
          </div>
          <button
            data-testid="edith-refresh"
            type="button"
            onClick={() => void refresh(true)}
            disabled={refreshing}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-[10px] font-black tracking-[0.16em] text-zinc-300 transition-colors hover:border-amber-500/35 hover:text-amber-300 disabled:opacity-50"
          >
            {refreshing ? <RiLoader4Line className="animate-spin" /> : null}
            {refreshing ? 'SYNCING' : 'REFRESH'}
          </button>
        </header>

        <section className="grid gap-3 sm:grid-cols-3">
          <div className="sb-panel p-4">
            <div className="text-[10px] font-mono tracking-[0.2em] text-zinc-500">AWAITING REVIEW</div>
            <div data-testid="edith-pending-count" className="mt-2 text-3xl font-black text-amber-400">{queue.pending.length}</div>
          </div>
          <div className="sb-panel p-4">
            <div className="text-[10px] font-mono tracking-[0.2em] text-zinc-500">PATCHABLE CODE</div>
            <div className="mt-2 text-3xl font-black text-red-300">{pendingCode.length}</div>
          </div>
          <div className="sb-panel p-4">
            <div className="text-[10px] font-mono tracking-[0.2em] text-zinc-500">AUDIT TRAIL</div>
            <div className="mt-2 text-3xl font-black text-zinc-200">{queue.recent.length}</div>
          </div>
        </section>

        {error ? (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>
        ) : null}
        {message ? (
          <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">{message}</div>
        ) : null}

        <section className="sb-panel overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-white/10 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="sb-label">PENDING PROPOSALS</div>
              <p className="mt-1 text-[11px] text-zinc-500">Inspect a code diff before approving. A passed sandbox proves it loads, not that it improves quality.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                data-testid="edith-approve-all-non-code"
                type="button"
                disabled={queue.pending.length === 0 || hasAnyPendingCode || acting !== null}
                title={hasAnyPendingCode ? 'Review code items one by one before approval.' : undefined}
                onClick={() => void decide('approve_all')}
                className="rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-[9px] font-black tracking-[0.14em] text-emerald-300 transition-colors hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-35"
              >
                APPROVE ALL NON-CODE
              </button>
              <button
                data-testid="edith-reject-all"
                type="button"
                disabled={queue.pending.length === 0 || acting !== null}
                onClick={() => void decide('reject_all')}
                className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-[9px] font-black tracking-[0.14em] text-red-300 transition-colors hover:bg-red-500/20 disabled:cursor-not-allowed disabled:opacity-35"
              >
                REJECT DIGEST
              </button>
            </div>
          </div>

          {loading ? (
            <div className="flex min-h-48 items-center justify-center gap-3 text-[11px] font-mono tracking-[0.22em] text-zinc-500">
              <RiLoader4Line className="animate-spin text-amber-400" /> LOADING REVIEW QUEUE
            </div>
          ) : queue.pending.length === 0 ? (
            <div className="flex min-h-52 flex-col items-center justify-center gap-3 px-6 text-center">
              <div className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-4 py-2 text-[10px] font-black tracking-[0.2em] text-emerald-300">QUEUE CLEAR</div>
              <p className="max-w-md text-xs leading-5 text-zinc-500">This is normal: safe green changes can apply after their sandbox passes. Red proposals appear here only when EDITH needs your sign-off.</p>
            </div>
          ) : (
            <div className="divide-y divide-white/5">
              {queue.pending.map((item) => {
                const patchableCode = isPatchableCode(item)
                const approveKey = `approve:${item.id}`
                const rejectKey = `reject:${item.id}`
                const reviewed = Boolean(reviewedCode[item.id])
                return (
                  <article key={item.id} data-testid={`edith-item-${item.id}`} className="p-5">
                    <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2 text-[9px] font-mono tracking-[0.16em]">
                          <span className={`rounded border px-2 py-1 uppercase ${item.tier === 'red' ? 'border-red-500/30 bg-red-500/10 text-red-300' : 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300'}`}>{item.tier || 'RED'}</span>
                          <span className="rounded border border-white/10 bg-black/30 px-2 py-1 text-zinc-400">{item.kind || 'PROPOSAL'}</span>
                          <span className="text-zinc-600">{timestamp(item.created_at)}</span>
                        </div>
                        <h2 className="mt-3 break-words text-sm font-black tracking-[0.08em] text-zinc-100">{item.title || item.target || 'UNTITLED PROPOSAL'}</h2>
                        {item.target ? <div className="mt-2 font-mono text-xs text-amber-300/90">TARGET: {item.target}</div> : null}
                      </div>
                      <div className="flex shrink-0 flex-wrap gap-2">
                        <button
                          data-testid={`edith-reject-${item.id}`}
                          type="button"
                          disabled={acting !== null}
                          onClick={() => void decide('reject', item)}
                          className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-[9px] font-black tracking-[0.14em] text-red-300 transition-colors hover:bg-red-500/20 disabled:opacity-40"
                        >
                          {acting === rejectKey ? 'REJECTING' : 'REJECT'}
                        </button>
                        <button
                          data-testid={`edith-approve-${item.id}`}
                          type="button"
                          disabled={acting !== null || (patchableCode && !reviewed)}
                          onClick={() => void decide('approve', item)}
                          className="rounded-lg bg-amber-500 px-3 py-2 text-[9px] font-black tracking-[0.14em] text-black transition-colors hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-35"
                        >
                          {acting === approveKey ? 'APPLYING' : patchableCode ? 'APPROVE PATCH' : 'APPROVE'}
                        </button>
                      </div>
                    </div>

                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      <div className="rounded-xl border border-white/5 bg-black/20 p-3">
                        <div className="text-[9px] font-mono tracking-[0.16em] text-zinc-500">WHY IT IS GATED</div>
                        <p className="mt-2 text-xs leading-5 text-zinc-300">{item.reason || 'This proposal needs explicit operator review.'}</p>
                      </div>
                      <div className="rounded-xl border border-white/5 bg-black/20 p-3">
                        <div className="text-[9px] font-mono tracking-[0.16em] text-zinc-500">SANDBOX EVIDENCE</div>
                        <p className={`mt-2 text-xs leading-5 ${item.proof?.passed ? 'text-emerald-300' : 'text-amber-300'}`}>{proofText(item)}</p>
                      </div>
                    </div>

                    {patchableCode ? (
                      <div className="mt-4 rounded-xl border border-amber-500/25 bg-amber-950/10 p-4">
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                          <div className="flex items-center gap-2 text-[10px] font-black tracking-[0.18em] text-amber-300"><RiFileCodeLine /> PROPOSED CODE DIFF</div>
                          <span className="text-[10px] font-mono tracking-[0.12em] text-red-300">APPROVAL PATCHES THE FILE ON NEXT BACKEND RESTART</span>
                        </div>
                        <pre className="scrollbar-small mt-3 max-h-80 overflow-auto rounded-lg border border-black/50 bg-black/55 p-3 text-[11px] leading-5 text-zinc-300">{item.body || item.preview || 'No draft body was supplied by the backend.'}</pre>
                        <label className="mt-4 flex cursor-pointer items-start gap-2 text-xs leading-5 text-zinc-300">
                          <input
                            data-testid={`edith-reviewed-${item.id}`}
                            type="checkbox"
                            checked={reviewed}
                            onChange={(event) => setReviewedCode((current) => ({ ...current, [item.id]: event.target.checked }))}
                            className="mt-0.5 h-4 w-4 shrink-0 rounded border-white/20 bg-black accent-amber-400"
                          />
                          <span>I reviewed this diff and understand that approval patches <span className="font-mono text-amber-300">{item.target || 'the target file'}</span> after the next backend restart.</span>
                        </label>
                      </div>
                    ) : item.preview || item.body ? (
                      <div className="mt-4 rounded-xl border border-white/5 bg-black/20 p-3">
                        <div className="text-[9px] font-mono tracking-[0.16em] text-zinc-500">PREVIEW</div>
                        <pre className="scrollbar-small mt-2 max-h-48 overflow-auto whitespace-pre-wrap text-xs leading-5 text-zinc-300">{item.body || item.preview}</pre>
                      </div>
                    ) : null}
                  </article>
                )
              })}
            </div>
          )}
        </section>

        <section className="sb-panel overflow-hidden">
          <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
            <div className="flex items-center gap-2 sb-label"><RiHistoryLine /> RECENT DECISIONS</div>
            {allCounts.length > 0 ? <div className="text-[10px] font-mono tracking-[0.14em] text-zinc-500">{allCounts.map(([status, count]) => `${status.toUpperCase()}: ${count}`).join(' / ')}</div> : null}
          </div>
          {queue.recent.length === 0 ? (
            <div className="px-5 py-10 text-center text-[11px] font-mono tracking-[0.2em] text-zinc-600">NO AUDIT EVENTS YET</div>
          ) : (
            <div className="divide-y divide-white/5">
              {queue.recent.map((item) => {
                const rollbackKey = `rollback:${item.id}`
                const canRollback = item.status === 'applied' && Boolean(item.applied_to)
                return (
                  <div key={item.id} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`rounded border px-2 py-1 text-[9px] font-mono tracking-[0.14em] ${statusClass(item.status)}`}>{item.status.toUpperCase()}</span>
                        <span className="text-[10px] font-mono text-zinc-600">{timestamp(item.decided_at || item.created_at)}</span>
                      </div>
                      <div className="mt-2 truncate text-xs font-bold tracking-[0.05em] text-zinc-200">{item.target || item.title || item.id}</div>
                      {item.applied_to ? <div className="mt-1 truncate font-mono text-[10px] text-zinc-500">APPLIED: {item.applied_to}</div> : null}
                      {item.error ? <div className="mt-1 text-[11px] text-red-300">{item.error}</div> : null}
                    </div>
                    {canRollback ? (
                      <button
                        data-testid={`edith-rollback-${item.id}`}
                        type="button"
                        disabled={acting !== null}
                        onClick={() => void decide('rollback', item)}
                        className="shrink-0 rounded-lg border border-amber-500/30 bg-amber-950/30 px-3 py-2 text-[9px] font-black tracking-[0.14em] text-amber-300 transition-colors hover:bg-amber-500/20 disabled:opacity-40"
                      >
                        {acting === rollbackKey ? 'UNDOING' : 'UNDO'}
                      </button>
                    ) : null}
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
