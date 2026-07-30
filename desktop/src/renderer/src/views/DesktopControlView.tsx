import { useCallback, useEffect, useMemo, useState } from 'react'
import { RiComputerLine, RiEyeLine, RiHistoryLine, RiLoader4Line, RiPlayLine, RiShieldCheckLine, RiStopCircleLine, RiTimeLine } from 'react-icons/ri'
import {
  API_BASE,
  fetchJson,
  type BrowserControlElement,
  type BrowserControlPage,
  type DesktopControlAction,
  type DesktopControlObservation,
  type DesktopControlPlan,
  type DesktopControlStatus,
  type DesktopControlStepResult
} from '../lib/types'

type BrowserActionKind = 'navigate' | 'extract' | 'click_dom' | 'fill' | 'select' | 'upload' | 'browser_shot'

type BrowserDraft = {
  kind: BrowserActionKind
  url: string
  selector: string
  text: string
  value: string
  path: string
  submit: boolean
}

type BrowserQueueItem = {
  id: string
  action: DesktopControlAction
  result?: DesktopControlStepResult
  submissionReviewed?: boolean
}

const BROWSER_HARD_BLOCK_RE = /\b(pass\s?word|passwd|pwd|pass\s?phrase|\bpin\b|otp|2fa|mfa|cvv|cvc|card\s*number|credit\s*card|debit\s*card|ssn|social\s*security|seed\s*phrase|private\s*key|secret\s*key|api[_\s-]?key|captcha|recaptcha|hcaptcha|i'?m\s*not\s*a\s*robot|\bbuy\b|\bsell\b|\btrade\b|transfer|wire|withdraw|deposit|send\s*money|pay(ment)?|purchase|checkout|place\s*(the\s*)?order|confirm\s*order)\b/i

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
    case 'navigate': return `BROWSER NAVIGATE: ${String(action.url || 'UNKNOWN')}`
    case 'extract': return 'READ PAGE ELEMENTS'
    case 'click_dom': return `BROWSER CLICK: ${String(action.selector || 'UNKNOWN')}`
    case 'fill': return `BROWSER FILL: ${String(action.selector || 'UNKNOWN')}`
    case 'select': return `BROWSER SELECT: ${String(action.selector || 'UNKNOWN')}`
    case 'upload': return `BROWSER UPLOAD: ${String(action.selector || 'UNKNOWN')}`
    case 'browser_shot': return 'CAPTURE BROWSER EVIDENCE'
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

function verifyText(verify?: DesktopControlStepResult['verify']): string | null {
  if (!verify) return null
  if (verify.before_url !== undefined || verify.after_url !== undefined) {
    return `URL: ${verify.before_url || 'UNKNOWN'} -> ${verify.after_url || 'UNKNOWN'}`
  }
  if (verify.before_window !== undefined || verify.after_window !== undefined) {
    return `WINDOW: ${verify.before_window || 'UNKNOWN'} -> ${verify.after_window || 'UNKNOWN'}`
  }
  return null
}

function isSubmission(action: DesktopControlAction): boolean {
  if (action.submit === true) return true
  return /\b(submit|send|post|publish|apply)\b/i.test([
    action.selector,
    action.text,
    action.value
  ].filter(Boolean).join(' '))
}

function browserDraftAction(draft: BrowserDraft): DesktopControlAction | null {
  if (draft.kind === 'navigate') return draft.url.trim() ? { action: 'navigate', url: draft.url.trim() } : null
  if (draft.kind === 'extract' || draft.kind === 'browser_shot') return { action: draft.kind }
  if (draft.kind === 'click_dom') return draft.selector.trim() ? { action: 'click_dom', selector: draft.selector.trim(), submit: draft.submit } : null
  if (draft.kind === 'fill') return draft.selector.trim() ? { action: 'fill', selector: draft.selector.trim(), text: draft.text } : null
  if (draft.kind === 'select') return draft.selector.trim() ? { action: 'select', selector: draft.selector.trim(), value: draft.value } : null
  if (draft.kind === 'upload') return draft.selector.trim() && draft.path.trim() ? { action: 'upload', selector: draft.selector.trim(), path: draft.path.trim() } : null
  return null
}

function browserActionBlockReason(action: DesktopControlAction): string | null {
  const blob = [action.url, action.selector, action.text, action.value, action.path].filter(Boolean).join(' ')
  return BROWSER_HARD_BLOCK_RE.test(blob)
    ? 'THIS ACTION APPEARS TO INVOLVE CREDENTIALS, A CAPTCHA, OR A FINANCIAL TRANSACTION. JARVIS WILL NOT QUEUE IT.'
    : null
}

function selectorSuggestion(element: BrowserControlElement): string {
  const name = String(element.name || '').trim().replaceAll('"', '\\"')
  // The backend exposes its `name` field from either the DOM name *or* id.
  // Match both without guessing which source supplied it.
  if (name) return `:is([name="${name}"], [id="${name}"])`
  return element.tag || '*'
}

function asPage(result: unknown): BrowserControlPage | null {
  if (!result || typeof result !== 'object') return null
  const value = result as Record<string, unknown>
  if (typeof value.url !== 'string') return null
  const elements = Array.isArray(value.elements) ? value.elements.filter((item): item is BrowserControlElement => Boolean(item && typeof item === 'object')) : []
  return { url: value.url, title: typeof value.title === 'string' ? value.title : '', elements }
}

function screenshotDataUrl(result: unknown): string | null {
  if (!result || typeof result !== 'object') return null
  const b64 = (result as Record<string, unknown>).b64
  return typeof b64 === 'string' && b64 ? `data:image/png;base64,${b64}` : null
}

export default function DesktopControlView() {
  const [status, setStatus] = useState<DesktopControlStatus>(EMPTY_STATUS)
  const [task, setTask] = useState('')
  const [appScope, setAppScope] = useState('')
  const [originText, setOriginText] = useState('')
  const [ttl, setTtl] = useState(120)
  const [plan, setPlan] = useState<DesktopControlPlan | null>(null)
  const [observation, setObservation] = useState<DesktopControlObservation | null>(null)
  const [stepResults, setStepResults] = useState<Record<number, DesktopControlStepResult>>({})
  const [browserDraft, setBrowserDraft] = useState<BrowserDraft>({
    kind: 'navigate', url: '', selector: '', text: '', value: '', path: '', submit: false
  })
  const [browserQueue, setBrowserQueue] = useState<BrowserQueueItem[]>([])
  const [browserPage, setBrowserPage] = useState<BrowserControlPage | null>(null)
  const [browserScreenshot, setBrowserScreenshot] = useState<string | null>(null)
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
    if (!sessionId || !status.session?.app_scope) {
      setObservation(null)
      return
    }
    void observe()
    const interval = window.setInterval(() => void observe(), 5000)
    return () => window.clearInterval(interval)
  }, [observe, sessionId, status.session?.app_scope])

  const sessionActive = Boolean(status.enabled && status.session?.active)
  const parsedOrigins = useMemo(() => originText.split(/[\s,]+/).map((origin) => origin.trim()).filter(Boolean), [originText])
  const hasScope = Boolean(appScope.trim() || parsedOrigins.length > 0)
  const hasNativeScope = Boolean(status.session?.app_scope)
  const hasBrowserScope = Boolean(status.session?.origins?.length)
  const canPlan = task.trim().length > 0 && Boolean(appScope.trim()) && acting === null
  const draftedBrowserAction = useMemo(() => browserDraftAction(browserDraft), [browserDraft])
  const draftedBrowserBlock = useMemo(() => draftedBrowserAction ? browserActionBlockReason(draftedBrowserAction) : null, [draftedBrowserAction])
  const planActions = plan?.actions ?? []
  const completedSteps = useMemo(() => planActions.filter((_, index) => stepResults[index]?.ok).length, [planActions, stepResults])

  async function toggleControl(on: boolean) {
    if (on && !window.confirm('Enable Computer Use? It remains scoped, expires automatically, and still requires approval for every step.')) return
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
        setBrowserQueue([])
        setBrowserPage(null)
        setBrowserScreenshot(null)
      }
      setMessage(on ? 'COMPUTER USE ENABLED — START A SCOPED SESSION BEFORE ANY STEP CAN RUN.' : 'COMPUTER USE DISABLED — ANY ACTIVE SESSION WAS ENDED.')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setActing(null)
    }
  }

  async function startSession() {
    if (!task.trim() || !hasScope) return
    setActing('start')
    setError('')
    setMessage('')
    try {
      await fetchJson<unknown>(`${API_BASE}/api/desktop/session/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task: task.trim(),
          app_scope: appScope.trim(),
          origins: parsedOrigins,
          ttl: Math.max(15, Math.min(600, ttl || 120))
        })
      })
      setStepResults({})
      setBrowserQueue([])
      setBrowserPage(null)
      setBrowserScreenshot(null)
      setMessage('SCOPED SESSION STARTED. REVIEW EACH PROPOSED ACTION, THEN APPROVE ONE STEP AT A TIME.')
      await refreshStatus(true)
      if (appScope.trim()) await observe(true)
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
      setBrowserPage(null)
      setBrowserScreenshot(null)
      setMessage('STOP CONFIRMED — THE COMPUTER USE SESSION HAS ENDED.')
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

  function recordBrowserEvidence(result: unknown, verify?: DesktopControlStepResult['verify']) {
    const page = asPage(result)
    if (page) setBrowserPage(page)
    else if (verify?.after_url) {
      setBrowserPage((current) => ({ url: verify.after_url || current?.url || '', title: current?.title || '', elements: current?.elements || [] }))
    }
    const shot = screenshotDataUrl(result)
    if (shot) setBrowserScreenshot(shot)
  }

  function proposeBrowserAction() {
    if (!sessionActive || !hasBrowserScope) {
      setError('START A BROWSER-SCOPED SESSION BEFORE PROPOSING A BROWSER ACTION.')
      return
    }
    const action = draftedBrowserAction
    if (!action) {
      setError('COMPLETE THE REQUIRED BROWSER ACTION DETAILS BEFORE ADDING IT TO THE REVIEW QUEUE.')
      return
    }
    const blocked = browserActionBlockReason(action)
    if (blocked) {
      setError(blocked)
      return
    }
    setError('')
    setMessage('BROWSER ACTION PROPOSED — REVIEW ITS EXACT PAYLOAD BEFORE APPROVING IT.')
    setBrowserQueue((current) => [...current, {
      id: `${Date.now()}-${current.length}`,
      action,
      submissionReviewed: false
    }])
  }

  async function executeBrowserAction(item: BrowserQueueItem) {
    setActing(`browser:${item.id}`)
    setError('')
    setMessage('')
    const action = isSubmission(item.action) ? { ...item.action, confirm: true } : item.action
    try {
      const result = await fetchJson<DesktopControlStepResult>(`${API_BASE}/api/desktop/step`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      })
      setBrowserQueue((current) => current.map((queued) => queued.id === item.id ? { ...queued, result } : queued))
      recordBrowserEvidence(result.result, result.verify)
      if (result.ok) setMessage(`BROWSER STEP VERIFIED: ${actionLabel(action)}.`)
      else setError(resultText(result))
      await refreshStatus()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setActing(null)
    }
  }

  function draftFromElement(element: BrowserControlElement) {
    const selector = selectorSuggestion(element)
    const tag = String(element.tag || '').toLowerCase()
    const type = String(element.type || '').toLowerCase()
    if (tag === 'select') {
      setBrowserDraft((current) => ({ ...current, kind: 'select', selector, value: '' }))
    } else if (tag === 'textarea' || tag === 'input') {
      setBrowserDraft((current) => ({ ...current, kind: 'fill', selector, text: '' }))
    } else {
      const submit = /\b(submit|send|post|publish|apply)\b/i.test(String(element.text || ''))
      setBrowserDraft((current) => ({ ...current, kind: 'click_dom', selector, submit }))
    }
    setMessage('PAGE ELEMENT LOADED INTO THE BROWSER ACTION DRAFT. REVIEW AND ADD IT TO THE QUEUE YOURSELF.')
  }

  return (
    <div className="scrollbar-small h-full overflow-y-auto p-5 lg:p-6">
      <div className="mx-auto flex max-w-6xl flex-col gap-5 pb-8">
        <header className="flex flex-col justify-between gap-4 border-b border-white/10 pb-5 lg:flex-row lg:items-end">
          <div>
            <div className="flex items-center gap-2 text-[11px] font-mono tracking-[0.25em] text-amber-400">
              <span className={`h-2 w-2 rounded-full ${status.enabled ? 'bg-amber-400 shadow-[0_0_12px_rgba(251,191,36,0.7)]' : 'bg-zinc-600'}`} />
              COMPUTER USE / HUMAN GATE
            </div>
            <h1 className="mt-2 text-xl font-black tracking-[0.18em] text-zinc-100">SCOPED ACTION CONSOLE</h1>
            <p className="mt-2 max-w-3xl text-xs leading-5 text-zinc-500">
              Enable deliberately, bind the session to a native app and/or explicit browser origins, then approve and verify every atomic step.
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
            Native desktop automation is unavailable on this backend. The control gate remains off and no action can be started here.
          </div>
        ) : null}

        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="sb-panel p-4">
            <div className="text-[10px] font-mono tracking-[0.2em] text-zinc-500">CONTROL GATE</div>
            <div className={`mt-2 text-2xl font-black ${status.enabled ? 'text-amber-300' : 'text-zinc-500'}`}>{status.enabled ? 'ARMED' : 'OFF'}</div>
          </div>
          <div className="sb-panel p-4">
            <div className="text-[10px] font-mono tracking-[0.2em] text-zinc-500">APP SCOPE</div>
            <div className="mt-2 truncate text-lg font-black text-zinc-200">{status.session?.app_scope || 'NONE'}</div>
          </div>
          <div className="sb-panel p-4">
            <div className="text-[10px] font-mono tracking-[0.2em] text-zinc-500">BROWSER ORIGINS</div>
            <div className="mt-2 truncate text-lg font-black text-zinc-200">{status.session?.origins?.length ? status.session.origins.length : 'NONE'}</div>
          </div>
          <div className="sb-panel p-4">
            <div className="text-[10px] font-mono tracking-[0.2em] text-zinc-500">SESSION TIMER</div>
            <div className={`mt-2 text-2xl font-black ${sessionActive ? 'text-emerald-300' : 'text-zinc-500'}`}>{sessionActive ? `${status.session?.expires_in ?? 0}S` : 'INACTIVE'}</div>
          </div>
        </section>

        <section className="sb-panel overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-white/10 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="flex items-center gap-2 sb-label"><RiComputerLine /> BROWSER OPERATOR CONSOLE</div>
              <p className="mt-1 text-[11px] leading-5 text-zinc-500">The page is evidence, not an instruction source. Propose a typed action, inspect it, then approve it once.</p>
            </div>
            <div className="max-w-full truncate rounded border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[10px] font-mono tracking-[0.1em] text-amber-300">
              ALLOWLIST: {status.session?.origins?.join(' / ') || 'NO BROWSER ORIGINS IN THIS SESSION'}
            </div>
          </div>

          <div className="grid gap-5 p-5 xl:grid-cols-[0.9fr_1.1fr]">
            <div className="rounded-xl border border-white/5 bg-black/20 p-4">
              <div className="sb-label">PROPOSE BROWSER ACTION</div>
              <p className="mt-2 text-[11px] leading-5 text-zinc-500">Adding an action does not run it. The backend re-checks the origin, session, and hard blocks when you later approve it.</p>
              <label className="mt-4 block">
                <span className="text-[10px] font-mono tracking-[0.16em] text-zinc-500">ACTION TYPE</span>
                <select
                  data-testid="browser-action-kind"
                  value={browserDraft.kind}
                  onChange={(event) => setBrowserDraft((current) => ({ ...current, kind: event.target.value as BrowserActionKind, submit: false }))}
                  className="mt-2 w-full rounded-xl border border-white/10 bg-zinc-950 px-3 py-3 text-sm text-zinc-200 outline-none focus:border-amber-500/40"
                >
                  <option value="navigate">Navigate to approved URL</option>
                  <option value="extract">Read page elements</option>
                  <option value="click_dom">Click an element</option>
                  <option value="fill">Fill a text field</option>
                  <option value="select">Select an option</option>
                  <option value="upload">Upload an approved file</option>
                  <option value="browser_shot">Capture page screenshot</option>
                </select>
              </label>

              {browserDraft.kind === 'navigate' ? (
                <label className="mt-3 block">
                  <span className="text-[10px] font-mono tracking-[0.16em] text-zinc-500">FULL URL</span>
                  <input data-testid="browser-url" value={browserDraft.url} onChange={(event) => setBrowserDraft((current) => ({ ...current, url: event.target.value }))} placeholder="https://approved-site.example/page" className="mt-2 w-full rounded-xl border border-white/10 bg-black/40 px-3 py-3 text-sm text-zinc-200 outline-none focus:border-amber-500/40" />
                </label>
              ) : null}

              {['click_dom', 'fill', 'select', 'upload'].includes(browserDraft.kind) ? (
                <label className="mt-3 block">
                  <span className="text-[10px] font-mono tracking-[0.16em] text-zinc-500">CSS SELECTOR</span>
                  <input data-testid="browser-selector" value={browserDraft.selector} onChange={(event) => setBrowserDraft((current) => ({ ...current, selector: event.target.value }))} placeholder='Example: [name="email"]' className="mt-2 w-full rounded-xl border border-white/10 bg-black/40 px-3 py-3 font-mono text-sm text-zinc-200 outline-none focus:border-amber-500/40" />
                </label>
              ) : null}

              {browserDraft.kind === 'fill' ? (
                <label className="mt-3 block">
                  <span className="text-[10px] font-mono tracking-[0.16em] text-zinc-500">TEXT TO FILL</span>
                  <textarea data-testid="browser-fill-text" value={browserDraft.text} onChange={(event) => setBrowserDraft((current) => ({ ...current, text: event.target.value }))} className="scrollbar-small mt-2 h-20 w-full resize-none rounded-xl border border-white/10 bg-black/40 px-3 py-3 text-sm text-zinc-200 outline-none focus:border-amber-500/40" />
                </label>
              ) : null}

              {browserDraft.kind === 'select' ? (
                <label className="mt-3 block">
                  <span className="text-[10px] font-mono tracking-[0.16em] text-zinc-500">OPTION VALUE</span>
                  <input data-testid="browser-select-value" value={browserDraft.value} onChange={(event) => setBrowserDraft((current) => ({ ...current, value: event.target.value }))} className="mt-2 w-full rounded-xl border border-white/10 bg-black/40 px-3 py-3 text-sm text-zinc-200 outline-none focus:border-amber-500/40" />
                </label>
              ) : null}

              {browserDraft.kind === 'upload' ? (
                <label className="mt-3 block">
                  <span className="text-[10px] font-mono tracking-[0.16em] text-zinc-500">REVIEWED LOCAL FILE PATH</span>
                  <input data-testid="browser-upload-path" value={browserDraft.path} onChange={(event) => setBrowserDraft((current) => ({ ...current, path: event.target.value }))} placeholder="C:\\path\\to\\approved-file.pdf" className="mt-2 w-full rounded-xl border border-white/10 bg-black/40 px-3 py-3 font-mono text-sm text-zinc-200 outline-none focus:border-amber-500/40" />
                </label>
              ) : null}

              {browserDraft.kind === 'click_dom' ? (
                <label className="mt-3 flex cursor-pointer items-start gap-2 text-xs leading-5 text-zinc-300">
                  <input data-testid="browser-is-submission" type="checkbox" checked={browserDraft.submit} onChange={(event) => setBrowserDraft((current) => ({ ...current, submit: event.target.checked }))} className="mt-0.5 h-4 w-4 rounded border-white/20 bg-black accent-amber-400" />
                  <span>This click submits, sends, posts, publishes, or applies in my name. It will require a distinct final confirmation.</span>
                </label>
              ) : null}

              {draftedBrowserBlock ? <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-[11px] leading-5 text-red-200">{draftedBrowserBlock}</div> : null}

              <button
                data-testid="browser-propose-action"
                type="button"
                disabled={!sessionActive || !hasBrowserScope || !draftedBrowserAction || Boolean(draftedBrowserBlock) || acting !== null}
                onClick={proposeBrowserAction}
                className="mt-4 w-full rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-[10px] font-black tracking-[0.16em] text-amber-300 transition-colors hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-35"
              >
                ADD TO BROWSER REVIEW QUEUE
              </button>
            </div>

            <div className="overflow-hidden rounded-xl border border-white/5 bg-black/20">
              <div className="border-b border-white/5 px-4 py-3">
                <div className="flex items-center gap-2 text-[10px] font-black tracking-[0.16em] text-zinc-300"><RiEyeLine /> LIVE PAGE EVIDENCE</div>
                <div data-testid="browser-live-url" className={`mt-2 break-all font-mono text-[11px] ${browserPage?.url ? 'text-amber-300' : 'text-zinc-600'}`}>{browserPage?.url || 'NO PAGE OBSERVED — NAVIGATE, THEN PROPOSE “READ PAGE ELEMENTS”.'}</div>
                {browserPage?.title ? <div className="mt-1 text-xs text-zinc-400">{browserPage.title}</div> : null}
              </div>
              {browserPage?.elements?.length ? (
                <div className="scrollbar-small max-h-72 overflow-y-auto divide-y divide-white/5">
                  {browserPage.elements.map((element, index) => (
                    <button key={`${element.tag}-${element.name}-${index}`} data-testid={`browser-element-${index}`} type="button" onClick={() => draftFromElement(element)} className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-amber-500/[0.06]">
                      <span className="rounded border border-white/10 bg-black/40 px-2 py-1 font-mono text-[9px] text-zinc-400">{element.tag || 'ELEMENT'}</span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-xs font-bold text-zinc-200">{element.text || element.name || 'UNLABELLED ELEMENT'}</span>
                        <span className="mt-1 block truncate font-mono text-[10px] text-zinc-600">{selectorSuggestion(element)} {element.type ? `// ${element.type}` : ''}</span>
                      </span>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="flex min-h-40 items-center justify-center px-5 text-center text-xs leading-5 text-zinc-600">Extracted elements appear here as operator evidence. Selecting one only prepares a draft; it never clicks or fills it.</div>
              )}
              {browserScreenshot ? <img src={browserScreenshot} alt="Browser evidence captured by JARVIS" className="max-h-80 w-full border-t border-white/5 object-contain" /> : null}
            </div>
          </div>

          <div className="border-t border-white/10">
            <div className="flex items-center justify-between px-5 py-4">
              <div className="sb-label">BROWSER REVIEW QUEUE</div>
              <span className="text-[10px] font-mono tracking-[0.14em] text-zinc-600">{browserQueue.filter((item) => item.result?.ok).length}/{browserQueue.length} VERIFIED</span>
            </div>
            {browserQueue.length === 0 ? (
              <div className="px-5 pb-6 text-center text-[11px] font-mono tracking-[0.14em] text-zinc-600">NO BROWSER ACTIONS PROPOSED</div>
            ) : (
              <div className="divide-y divide-white/5">
                {browserQueue.map((item, index) => {
                  const submission = isSubmission(item.action)
                  const earlierVerified = browserQueue.slice(0, index).every((previous) => previous.result?.ok)
                  const canExecute = sessionActive && hasBrowserScope && earlierVerified && acting === null && !item.result?.ok && (!submission || item.submissionReviewed)
                  return (
                    <article key={item.id} data-testid={`browser-queue-${index}`} className="px-5 py-4">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-[9px] font-mono tracking-[0.14em] text-zinc-600">STEP {index + 1}</span>
                            <span className={`rounded border px-2 py-1 text-[9px] font-mono tracking-[0.12em] ${resultClass(item.result)}`}>{item.result?.ok ? 'VERIFIED' : item.result ? 'BLOCKED / REFUSED' : 'PENDING APPROVAL'}</span>
                            {submission ? <span className="rounded border border-red-500/30 bg-red-500/10 px-2 py-1 text-[9px] font-mono tracking-[0.12em] text-red-300">SUBMISSION REVIEW REQUIRED</span> : null}
                          </div>
                          <h3 className="mt-2 text-xs font-black tracking-[0.08em] text-zinc-100">{actionLabel(item.action)}</h3>
                          <pre className="scrollbar-small mt-3 max-h-36 overflow-auto rounded-lg border border-white/5 bg-black/35 p-3 text-[11px] leading-5 text-zinc-300">{JSON.stringify(item.action, null, 2)}</pre>
                          {verifyText(item.result?.verify) ? <div className="mt-3 text-[11px] text-emerald-300">VERIFIED {verifyText(item.result?.verify)}</div> : null}
                          {item.result && !item.result.ok ? <div className="mt-3 text-xs leading-5 text-red-300">{resultText(item.result)}</div> : null}
                          {submission ? (
                            <label className="mt-4 flex cursor-pointer items-start gap-2 text-xs leading-5 text-zinc-300">
                              <input data-testid={`browser-submission-reviewed-${index}`} type="checkbox" checked={Boolean(item.submissionReviewed)} onChange={(event) => setBrowserQueue((current) => current.map((queued) => queued.id === item.id ? { ...queued, submissionReviewed: event.target.checked } : queued))} className="mt-0.5 h-4 w-4 shrink-0 rounded border-white/20 bg-black accent-red-400" />
                              <span>I reviewed the completed action and explicitly confirm this submission in my name.</span>
                            </label>
                          ) : null}
                        </div>
                        <button
                          data-testid={`browser-approve-${index}`}
                          type="button"
                          disabled={!canExecute}
                          title={!sessionActive ? 'Start a scoped session first.' : !hasBrowserScope ? 'This session has no browser origin allowlist.' : !earlierVerified ? 'Verify the earlier browser step first.' : submission && !item.submissionReviewed ? 'Review and confirm this submission first.' : undefined}
                          onClick={() => void executeBrowserAction(item)}
                          className={`shrink-0 rounded-lg px-3 py-2 text-[9px] font-black tracking-[0.14em] transition-colors disabled:cursor-not-allowed disabled:opacity-35 ${submission ? 'border border-red-500/35 bg-red-500/15 text-red-200 hover:bg-red-500/25' : 'bg-amber-500 text-black hover:bg-amber-400'}`}
                        >
                          {acting === `browser:${item.id}` ? 'EXECUTING' : item.result ? 'RETRY STEP' : submission ? 'CONFIRM + APPROVE SUBMISSION' : 'APPROVE STEP'}
                        </button>
                      </div>
                    </article>
                  )
                })}
              </div>
            )}
          </div>
        </section>

        <section className="sb-panel overflow-hidden">
          <div className="flex flex-col gap-4 border-b border-white/10 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="flex items-center gap-2 sb-label"><RiShieldCheckLine /> APPROVE COMPUTER USE</div>
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
              <label className="block">
                <span className="sb-label">APPROVED BROWSER ORIGINS</span>
                <textarea
                  data-testid="desktop-browser-origins"
                  value={originText}
                  onChange={(event) => setOriginText(event.target.value)}
                  placeholder="https://example.com, https://careers.example.org"
                  className="scrollbar-small mt-2 h-20 w-full resize-none rounded-xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-zinc-200 outline-none transition-colors placeholder:text-zinc-600 focus:border-amber-500/40"
                />
                <p className="mt-2 text-[10px] leading-5 text-zinc-600">Comma or line separated. Only these exact origins can be opened or acted on; redirects outside them are refused.</p>
              </label>
            </div>
            <div className="flex flex-col justify-end gap-3 rounded-xl border border-white/5 bg-black/20 p-4">
              <p className="text-xs leading-5 text-zinc-400">A session needs at least one scope. Native input is bound to one app; browser actions are bound to approved origins. Credentials, payments, transfers, and CAPTCHAs stay blocked even after approval.</p>
              <button
                data-testid="desktop-start-session"
                type="button"
                disabled={!status.available || !status.enabled || !task.trim() || !hasScope || acting !== null}
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
                <div className="flex items-center gap-2 sb-label"><RiPlayLine /> NATIVE APP STEP PLAN</div>
                <p className="mt-1 text-[11px] text-zinc-500">A deterministic native-app plan. Planning never uses screen content and does not execute anything.</p>
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
                <p className="max-w-md text-xs leading-5 text-zinc-500">For a native-app plan, include one approved app above. Browser actions are proposed in the separate browser console below.</p>
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
                  const canExecute = sessionActive && hasNativeScope && previousStepsVerified && acting === null && !outcome?.ok
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
                      {verifyText(outcome?.verify) ? (
                        <div className="mt-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-[11px] leading-5 text-emerald-200">
                          VERIFIED {verifyText(outcome?.verify)}
                        </div>
                      ) : null}
                      {outcome && !outcome.ok ? <p className="mt-3 text-xs leading-5 text-red-300">{resultText(outcome)}</p> : null}
                      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                        <p className="text-[11px] leading-5 text-zinc-500">Target window: <span className={observation?.active_window ? 'text-amber-300' : 'text-red-300'}>{observation?.active_window || 'UNCONFIRMED — THE BACKEND WILL FAIL CLOSED FOR TYPING'}</span></p>
                        <button
                          data-testid={`desktop-approve-step-${index}`}
                          type="button"
                          disabled={!canExecute}
                          title={!sessionActive ? 'Start an active scoped session first.' : !hasNativeScope ? 'This is a native-app action; start a session with one approved app.' : !previousStepsVerified ? 'Verify the prior step first.' : undefined}
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
                  {verifyText(record.verify) ? <div className="mt-2 text-[11px] text-emerald-300">{verifyText(record.verify)}</div> : null}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
