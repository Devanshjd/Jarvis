import { useCallback, useEffect, useMemo, useState } from 'react'
import { RiComputerLine, RiEyeLine, RiHistoryLine, RiLoader4Line, RiPlayLine, RiShieldCheckLine, RiStopCircleLine, RiTimeLine } from 'react-icons/ri'
import {
  API_BASE,
  fetchJson,
  type DesktopControlAction,
  type DesktopControlObservation,
  type DesktopControlPlan,
  type DesktopControlStatus,
  type DesktopControlStepResult
} from '../lib/types'

const EMPTY_STATUS: DesktopControlStatus = {
  available: false,
  enabled: false,
  session: null,
  recent: []
}

function normaliseStatus(value: Partial<DesktopControlStatus>): DesktopControlStatus {
  return {
    available: Boolean(value.available),
    enabled: Boolean(value.enabled),
    session: value.session ?? null,
    recent: Array.isArray(value.recent) ? value.recent : []
  }
}

function actionLabel(action: DesktopControlAction): string {
  switch (action.action) {
    case 'open_app': return `OPEN APPLICATION: ${String(action.app || 'UNKNOWN')}`
    case 'focus': return `FOCUS APPLICATION: ${String(action.app || 'UNKNOWN')}`
    case 'click': return `CLICK CONTROL: ${String(action.target || 'UNKNOWN')}`
    case 'type_text': return 'TYPE THE REVIEWED TEXT'
    case 'press': return `PRESS KEY: ${String(action.key || 'UNKNOWN')}`
    case 'hotkey': return `PRESS HOTKEY: ${String(action.keys || 'UNKNOWN')}`
    default: return String(action.action || 'UNKNOWN ACTION').replaceAll('_', ' ').toUpperCase()
  }
}

function resultText(result?: DesktopControlStepResult): string {
  if (!result) return 'AWAITING YOUR APPROVAL'
  if (result.ok) return 'VERIFIED'
  return result.blocked ? `HARD-BLOCKED: ${result.blocked}`
    : result.refused ? `REFUSED: ${result.refused}`
      : result.error ? `FAILED: ${result.error}`
        : 'NOT EXECUTED'
}

function resultClass(result?: DesktopControlStepResult): string {
  if (!result) return 'border-white/10 bg-black/30 text-zinc-500'
  return result.ok
    ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300'
    : 'border-red-500/25 bg-red-500/10 text-red-300'
}

function formatAuditAction(action?: DesktopControlAction): string {
  return action ? actionLabel(action) : 'CONTROL EVENT'
}

export default function DesktopControlView() {
  const [status, setStatus] = useState<DesktopControlStatus>(EMPTY_STATUS)
  const [task, setTask] = useState('')
  const [appScope, setAppScope] = useState('')
  const [ttl, setTtl] = useState(120)
  const [plan, setPlan] = useState<DesktopControlPlan | null>(null)
  const [observation, setObservation] = useState<DesktopControlObservation | null>(null)
  const [stepResults, setStepResults] = useState<Record<number, DesktopControlStepResult>>({})
  const [loading, setLoading] = useState(true)
  const [acting, setActing] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const refreshStatus = useCallback(async (showError = false) => {
    try {
      const next = await fetchJson<DesktopControlStatus>(`${API_BASE}/api/desktop/status`)
      setStatus(normaliseStatus(next))
      if (showError) setError('')
    } catch (err) {
      if (showError) setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  const observe = useCallback(async (showError = false) => {
    try {
      const next = await fetchJson<DesktopControlObservation>(`${API_BASE}/api/desktop/observe`, {
        method: 'POST'
      })
      setObservation({
        active_window: next.active_window || '',
        controls: Array.isArray(next.controls) ? next.controls : [],
        note: next.note
      })
      if (showError) setError('')
    } catch (err) {
      if (showError) setError(err instanceof Error ? err.message : String(err))
    }
  }, [])

  useEffect(() => {
    void refreshStatus(true)
    const interval = window.setInterval(() => void refreshStatus(), 1000)
    return () => window.clearInterval(interval)
  }, [refreshStatus])

  const sessionId = status.session?.id
  useEffect(() => {
    if (!sessionId) {
      setObservation(null)
      return
    }
    void observe()
    const interval = window.setInterval(() => void observe(), 5000)
    return () => window.clearInterval(interval)
  }, [observe, sessionId])

  const sessionActive = Boolean(status.enabled && status.session?.active)
  const canPlan = task.trim().length > 0 && acting === null
  const planActions = plan?.actions ?? []
  const completedSteps = useMemo(() => planActions.filter((_, index) => stepResults[index]?.ok).length, [planActions, stepResults])

  async function toggleControl(on: boolean) {
    if (on && !window.confirm('Enable desktop control? It remains scoped, expires automatically, and still requires approval for every step.')) return
    setActing('toggle')
    setError('')
    setMessage('')
    try {
      const next = await fetchJson<DesktopControlStatus>(`${API_BASE}/api/desktop/enable`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ on })
      })
      setStatus(normaliseStatus(next))
      if (!on) {
        setObservation(null)
        setStepResults({})
      }
      setMessage(on ? 'DESKTOP CONTROL ENABLED — START A SCOPED SESSION BEFORE ANY STEP CAN RUN.' : 'DESKTOP CONTROL DISABLED — ANY ACTIVE SESSION WAS ENDED.')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setActing(null)
    }
  }

  async function startSession() {
    if (!task.trim() || !appScope.trim()) return
    setActing('start')
    setError('')
    setMessage('')
    try {
      await fetchJson<unknown>(`${API_BASE}/api/desktop/session/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: task.trim(), app_scope: appScope.trim(), ttl: Math.max(15, Math.min(600, ttl || 120)) })
      })
      setStepResults({})
      setMessage('SCOPED SESSION STARTED. REVIEW THE DETERMINISTIC PLAN, THEN APPROVE ONE STEP AT A TIME.')
      await refreshStatus(true)
      await observe(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setActing(null)
    }
  }

  async function stopSession() {
    setActing('stop')
    setError('')
    setMessage('')
    try {
      await fetchJson<unknown>(`${API_BASE}/api/desktop/session/stop`, { method: 'POST' })
      setObservation(null)
      setMessage('STOP CONFIRMED — THE DESKTOP CONTROL SESSION HAS ENDED.')
      await refreshStatus(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setActing(null)
    }
  }

  async function proposePlan() {
    if (!task.trim()) return
    setActing('plan')
    setError('')
    setMessage('')
    try {
      const next = await fetchJson<DesktopControlPlan>(`${API_BASE}/api/desktop/plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: task.trim() })
      })
      setPlan({ task: next.task || task.trim(), actions: Array.isArray(next.actions) ? next.actions : [], note: next.note })
      setStepResults({})
      setMessage('PLAN GENERATED — NO DESKTOP ACTION HAS RUN.')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setActing(null)
    }
  }

  async function executeStep(action: DesktopControlAction, index: number) {
    setActing(`step:${index}`)
    setError('')
    setMessage('')
    try {
      const result = await fetchJson<DesktopControlStepResult>(`${API_BASE}/api/desktop/step`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      })
      setStepResults((current) => ({ ...current, [index]: result }))
      if (result.ok) setMessage(`STEP ${index + 1} VERIFIED. REVIEW THE NEXT STEP BEFORE APPROVING IT.`)
      else setError(resultText(result))
      await refreshStatus()
      await observe()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setActing(null)
    }
  }

  return (
    <div className="scrollbar-small h-full overflow-y-auto p-5 lg:p-6">
      <div className="mx-auto flex max-w-6xl flex-col gap-5 pb-8">
        <header className="flex flex-col justify-between gap-4 border-b border-white/10 pb-5 lg:flex-row lg:items-end">
          <div>
            <div className="flex items-center gap-2 text-[11px] font-mono tracking-[0.25em] text-amber-400">
              <span className={`h-2 w-2 rounded-full ${status.enabled ? 'bg-amber-400 shadow-[0_0_12px_rgba(251,191,36,0.7)]' : 'bg-zinc-600'}`} />
              DESKTOP CONTROL / HUMAN GATE
            </div>
            <h1 className="mt-2 text-xl font-black tracking-[0.18em] text-zinc-100">SCOPED ACTION CONSOLE</h1>
            <p className="mt-2 max-w-3xl text-xs leading-5 text-zinc-500">
              This is the only desktop-control workflow in the shell: enable it deliberately, bind it to one app, then approve and verify every atomic step.
            </p>
          </div>
          <button
            data-testid="desktop-refresh"
            type="button"
            onClick={() => void refreshStatus(true)}
            disabled={acting !== null}
            className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-[10px] font-black tracking-[0.16em] text-zinc-300 transition-colors hover:border-amber-500/35 hover:text-amber-300 disabled:opacity-50"
          >
            {loading ? <RiLoader4Line className="mr-2 inline animate-spin" /> : null}
            REFRESH STATUS
          </button>
        </header>

        {error ? <div role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div> : null}
        {message ? <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">{message}</div> : null}

        {!status.available && !loading ? (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm leading-6 text-red-200">
            Desktop automation is unavailable on this backend. The control gate remains off and no action can be started here.
          </div>
        ) : null}

        <section className="grid gap-3 lg:grid-cols-3">
          <div className="sb-panel p-4">
            <div className="text-[10px] font-mono tracking-[0.2em] text-zinc-500">CONTROL GATE</div>
            <div className={`mt-2 text-2xl font-black ${status.enabled ? 'text-amber-300' : 'text-zinc-500'}`}>{status.enabled ? 'ARMED' : 'OFF'}</div>
          </div>
          <div className="sb-panel p-4">
            <div className="text-[10px] font-mono tracking-[0.2em] text-zinc-500">APP SCOPE</div>
            <div className="mt-2 truncate text-lg font-black text-zinc-200">{status.session?.app_scope || 'NONE'}</div>
          </div>
          <div className="sb-panel p-4">
            <div className="text-[10px] font-mono tracking-[0.2em] text-zinc-500">SESSION TIMER</div>
            <div className={`mt-2 text-2xl font-black ${sessionActive ? 'text-emerald-300' : 'text-zinc-500'}`}>{sessionActive ? `${status.session?.expires_in ?? 0}S` : 'INACTIVE'}</div>
          </div>
        </section>

        <section className="sb-panel overflow-hidden">
          <div className="flex flex-col gap-4 border-b border-white/10 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="flex items-center gap-2 sb-label"><RiShieldCheckLine /> APPROVE DESKTOP</div>
              <p className="mt-1 text-[11px] leading-5 text-zinc-500">Off by default. Disabling ends the active session immediately.</p>
            </div>
            <button
              data-testid="desktop-enable-toggle"
              type="button"
              disabled={!status.available || acting !== null}
              onClick={() => void toggleControl(!status.enabled)}
              className={`rounded-xl border px-4 py-3 text-[10px] font-black tracking-[0.16em] transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                status.enabled ? 'border-red-500/30 bg-red-500/10 text-red-300 hover:bg-red-500/20' : 'border-amber-500/35 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20'
              }`}
            >
              {acting === 'toggle' ? 'UPDATING GATE' : status.enabled ? 'DISABLE + END SESSION' : 'ENABLE CONTROL GATE'}
            </button>
          </div>

          <div className="grid gap-4 p-5 lg:grid-cols-[1fr_0.8fr]">
            <div className="space-y-3">
              <label className="block">
                <span className="sb-label">TASK YOU ARE APPROVING</span>
                <input
                  data-testid="desktop-task"
                  value={task}
                  onChange={(event) => setTask(event.target.value)}
                  placeholder="Example: open notepad and type: JARVIS test"
                  className="mt-2 w-full rounded-xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-zinc-200 outline-none transition-colors placeholder:text-zinc-600 focus:border-amber-500/40"
                />
              </label>
              <div className="grid gap-3 sm:grid-cols-[1fr_130px]">
                <label className="block">
                  <span className="sb-label">ONE APPROVED APP</span>
                  <input
                    data-testid="desktop-app-scope"
                    value={appScope}
                    onChange={(event) => setAppScope(event.target.value)}
                    placeholder="notepad"
                    className="mt-2 w-full rounded-xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-zinc-200 outline-none transition-colors placeholder:text-zinc-600 focus:border-amber-500/40"
                  />
                </label>
                <label className="block">
                  <span className="sb-label">TTL (SECONDS)</span>
                  <input
                    data-testid="desktop-ttl"
                    type="number"
                    min={15}
                    max={600}
                    value={ttl}
                    onChange={(event) => setTtl(Number(event.target.value) || 120)}
                    className="mt-2 w-full rounded-xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-zinc-200 outline-none transition-colors focus:border-amber-500/40"
                  />
                </label>
              </div>
            </div>
            <div className="flex flex-col justify-end gap-3 rounded-xl border border-white/5 bg-black/20 p-4">
              <p className="text-xs leading-5 text-zinc-400">A session can act only inside the named app and expires automatically. Credentials, payments, transfers, and CAPTCHAs stay blocked even after approval.</p>
              <button
                data-testid="desktop-start-session"
                type="button"
                disabled={!status.available || !status.enabled || !task.trim() || !appScope.trim() || acting !== null}
                onClick={() => void startSession()}
                className="rounded-xl bg-amber-500 px-4 py-3 text-[10px] font-black tracking-[0.16em] text-black transition-colors hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-35"
              >
                {acting === 'start' ? 'STARTING SESSION' : sessionActive ? 'RESTART SCOPED SESSION' : 'START SCOPED SESSION'}
              </button>
            </div>
          </div>
        </section>

        <section className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
          <div className="sb-panel overflow-hidden">
            <div className="flex flex-col gap-3 border-b border-white/10 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="flex items-center gap-2 sb-label"><RiPlayLine /> DETERMINISTIC STEP PLAN</div>
                <p className="mt-1 text-[11px] text-zinc-500">Planning never uses screen content and does not execute anything.</p>
              </div>
              <button
                data-testid="desktop-propose-plan"
                type="button"
                disabled={!canPlan}
                onClick={() => void proposePlan()}
                className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[9px] font-black tracking-[0.14em] text-amber-300 transition-colors hover:bg-amber-500/20 disabled:opacity-35"
              >
                {acting === 'plan' ? 'PLANNING' : 'PROPOSE STEPS'}
              </button>
            </div>

            {!plan ? (
              <div className="flex min-h-48 flex-col items-center justify-center gap-3 px-6 text-center">
                <RiComputerLine className="text-zinc-600" size={28} />
                <p className="max-w-md text-xs leading-5 text-zinc-500">Describe an explicit safe task, then inspect the proposed atomic steps before starting a session or approving a step.</p>
              </div>
            ) : planActions.length === 0 ? (
              <div className="min-h-48 px-5 py-8 text-center text-xs leading-6 text-zinc-400">
                {plan.note || 'No safe deterministic plan was produced. Provide an explicit action such as “open notepad and type: hello”.'}
              </div>
            ) : (
              <div className="divide-y divide-white/5">
                {planActions.map((action, index) => {
                  const outcome = stepResults[index]
                  const previousStepsVerified = planActions.slice(0, index).every((_, previousIndex) => stepResults[previousIndex]?.ok)
                  const canExecute = sessionActive && previousStepsVerified && acting === null && !outcome?.ok
                  return (
                    <article key={`${action.action}-${index}`} data-testid={`desktop-plan-step-${index}`} className="p-5">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div className="min-w-0">
                          <div className="text-[9px] font-mono tracking-[0.16em] text-zinc-600">STEP {index + 1} OF {planActions.length}</div>
                          <h2 className="mt-1 text-sm font-black tracking-[0.08em] text-zinc-100">{actionLabel(action)}</h2>
                        </div>
                        <span className={`rounded border px-2 py-1 text-[9px] font-mono tracking-[0.12em] ${resultClass(outcome)}`}>{outcome?.ok ? 'VERIFIED' : outcome ? 'BLOCKED / REFUSED' : 'PENDING APPROVAL'}</span>
                      </div>
                      <pre className="scrollbar-small mt-3 max-h-40 overflow-auto rounded-lg border border-white/5 bg-black/35 p-3 text-[11px] leading-5 text-zinc-300">{JSON.stringify(action, null, 2)}</pre>
                      {outcome?.verify ? (
                        <div className="mt-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-[11px] leading-5 text-emerald-200">
                          VERIFIED WINDOW: {outcome.verify.before_window || 'UNKNOWN'} → {outcome.verify.after_window || 'UNKNOWN'}
                        </div>
                      ) : null}
                      {outcome && !outcome.ok ? <p className="mt-3 text-xs leading-5 text-red-300">{resultText(outcome)}</p> : null}
                      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                        <p className="text-[11px] leading-5 text-zinc-500">Target window: <span className={observation?.active_window ? 'text-amber-300' : 'text-red-300'}>{observation?.active_window || 'UNCONFIRMED — THE BACKEND WILL FAIL CLOSED FOR TYPING'}</span></p>
                        <button
                          data-testid={`desktop-approve-step-${index}`}
                          type="button"
                          disabled={!canExecute}
                          title={!sessionActive ? 'Start an active scoped session first.' : !previousStepsVerified ? 'Verify the prior step first.' : undefined}
                          onClick={() => void executeStep(action, index)}
                          className="shrink-0 rounded-lg bg-amber-500 px-3 py-2 text-[9px] font-black tracking-[0.14em] text-black transition-colors hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-35"
                        >
                          {acting === `step:${index}` ? 'EXECUTING' : outcome ? 'RETRY STEP' : 'APPROVE STEP'}
                        </button>
                      </div>
                    </article>
                  )
                })}
              </div>
            )}
          </div>

          <div className="flex flex-col gap-5">
            <section className="sb-panel overflow-hidden">
              <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
                <div className="flex items-center gap-2 sb-label"><RiEyeLine /> READ-ONLY TARGET</div>
                <button
                  data-testid="desktop-observe"
                  type="button"
                  disabled={!sessionActive || acting !== null}
                  onClick={() => void observe(true)}
                  className="text-[9px] font-black tracking-[0.14em] text-amber-300 disabled:opacity-35"
                >
                  OBSERVE
                </button>
              </div>
              <div className="p-5">
                <div className="text-[10px] font-mono tracking-[0.16em] text-zinc-500">ACTIVE WINDOW</div>
                <div data-testid="desktop-active-window" className={`mt-2 break-words text-sm font-bold ${observation?.active_window ? 'text-zinc-100' : 'text-zinc-600'}`}>{observation?.active_window || 'NO ACTIVE SCOPED SESSION'}</div>
                <p className="mt-3 text-[11px] leading-5 text-zinc-500">Observation is display-only. It never chooses the next action.</p>
                {observation?.controls?.length ? <div className="mt-3 border-t border-white/5 pt-3 text-[10px] font-mono leading-5 text-zinc-500">VISIBLE LABELS: {observation.controls.slice(0, 6).join(' / ')}</div> : null}
              </div>
            </section>

            <section className="overflow-hidden rounded-2xl border border-red-500/35 bg-red-500/[0.07] p-5 shadow-[0_0_30px_rgba(239,68,68,0.06)]">
              <div className="flex items-center gap-2 text-[10px] font-black tracking-[0.18em] text-red-300"><RiStopCircleLine /> EMERGENCY STOP</div>
              <p className="mt-2 text-xs leading-5 text-red-100/75">Ends the current session immediately. It is always safe to stop; a new task needs a new scoped session.</p>
              <button
                data-testid="desktop-stop"
                type="button"
                disabled={!status.session || acting !== null}
                onClick={() => void stopSession()}
                className="mt-4 w-full rounded-xl border border-red-400/40 bg-red-500/15 px-4 py-3 text-[10px] font-black tracking-[0.18em] text-red-200 transition-colors hover:bg-red-500/25 disabled:cursor-not-allowed disabled:opacity-35"
              >
                {acting === 'stop' ? 'STOPPING' : 'STOP DESKTOP SESSION'}
              </button>
            </section>
          </div>
        </section>

        <section className="sb-panel overflow-hidden">
          <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
            <div className="flex items-center gap-2 sb-label"><RiHistoryLine /> RECENT EXECUTION AUDIT</div>
            <span className="text-[10px] font-mono tracking-[0.14em] text-zinc-600">{completedSteps}/{planActions.length || 0} PLAN STEPS VERIFIED</span>
          </div>
          {status.recent.length === 0 ? (
            <div className="px-5 py-8 text-center text-[11px] font-mono tracking-[0.16em] text-zinc-600">NO DESKTOP ACTIONS EXECUTED</div>
          ) : (
            <div className="divide-y divide-white/5">
              {status.recent.slice().reverse().map((record, index) => (
                <div key={`${record.ts || 'audit'}-${index}`} className="px-5 py-4">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <span className="text-xs font-bold tracking-[0.05em] text-zinc-200">{formatAuditAction(record.action)}</span>
                    <span className="flex items-center gap-1 text-[10px] font-mono text-zinc-600"><RiTimeLine /> {record.ts || 'UNKNOWN TIME'}</span>
                  </div>
                  {record.verify ? <div className="mt-2 text-[11px] text-emerald-300">WINDOW: {record.verify.before_window || 'UNKNOWN'} → {record.verify.after_window || 'UNKNOWN'}</div> : null}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
