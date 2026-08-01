import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  API_BASE,
  fetchJson,
  type BrowserControlElement,
  type BrowserControlPage,
  type DesktopControlAction,
  type JobFillPlan,
  type JobProfileSummary
} from '../lib/types'

type AnswerDraft = { key: string; value: string }

type ProfileDraft = {
  identity: Record<string, string>
  links: Record<string, string>
  resumePath: string
  coverLetterPath: string
  workAuthorization: string
  approvedAnswers: AnswerDraft[]
  titles: string
  locations: string
  remote: boolean
}

type JobsViewProps = {
  /** Evidence is captured by the scoped browser console, never fabricated here. */
  initialPage: BrowserControlPage | null
  /** Sends reviewed actions back to Control. It does not execute any action. */
  onQueueReviewedFills: (actions: DesktopControlAction[]) => void
}

const IDENTITY_FIELDS = [
  ['full_name', 'Full legal name'],
  ['first_name', 'First name'],
  ['last_name', 'Last name'],
  ['email', 'Email'],
  ['phone', 'Phone'],
  ['location', 'Address or location'],
  ['city', 'City'],
  ['country', 'Country'],
  ['postcode', 'Postcode']
] as const

const LINK_FIELDS = [
  ['linkedin', 'LinkedIn URL'],
  ['github', 'GitHub URL'],
  ['portfolio', 'Portfolio URL'],
  ['website', 'Website URL']
] as const

function emptyDraft(): ProfileDraft {
  return {
    identity: {},
    links: {},
    resumePath: '',
    coverLetterPath: '',
    workAuthorization: '',
    approvedAnswers: [
      { key: 'salary_expectation', value: '' },
      { key: 'notice_period', value: '' },
      { key: 'willing_to_relocate', value: '' }
    ],
    titles: '',
    locations: '',
    remote: false
  }
}

function splitLines(value: string): string[] {
  return value.split(/[\n,]+/).map((item) => item.trim()).filter(Boolean)
}

function selectorSuggestion(element: BrowserControlElement): string | null {
  const name = String(element.name || '').trim().replaceAll('"', '\\"')
  // Browser extraction exposes `name` from either a DOM name or id. Match both
  // sources without guessing which one it was. A generic tag selector such as
  // `input` could fill the wrong field, so it is never eligible for auto-fill.
  if (name) return `:is([name="${name}"], [id="${name}"])`
  return null
}

function pageFields(page: BrowserControlPage): Array<Record<string, string>> {
  return page.elements.flatMap((element) => {
    const selector = selectorSuggestion(element)
    if (!selector) return []
    return [{
      selector,
      label: String(element.text || element.name || `${element.tag || 'form'} field`).trim(),
      tag: String(element.tag || '').trim(),
      type: String(element.type || '').trim(),
      name: String(element.name || '').trim()
    }]
  })
}

function actionKind(action: DesktopControlAction | undefined): string {
  switch (action?.action) {
    case 'fill': return 'FILL'
    case 'select': return 'SELECT'
    case 'upload': return 'UPLOAD'
    default: return 'NO ACTION'
  }
}

function hasSubmission(action: DesktopControlAction): boolean {
  return action.submit === true || /\b(submit|send|post|publish|apply)\b/i.test(
    [action.action, action.selector].filter(Boolean).join(' ')
  )
}

function summaryKeys(summary: JobProfileSummary | null): string[] {
  if (!summary) return []
  return [...summary.identity_fields, ...summary.links, ...summary.approved_answers]
}

export default function JobsView({ initialPage, onQueueReviewedFills }: JobsViewProps) {
  const [summary, setSummary] = useState<JobProfileSummary | null>(null)
  const [draft, setDraft] = useState<ProfileDraft>(() => emptyDraft())
  const [plan, setPlan] = useState<JobFillPlan | null>(null)
  const [loadingProfile, setLoadingProfile] = useState(true)
  const [saving, setSaving] = useState(false)
  const [planning, setPlanning] = useState(false)
  const [replaceExisting, setReplaceExisting] = useState(false)
  const [localOnlyAcknowledged, setLocalOnlyAcknowledged] = useState(false)
  const [reviewAcknowledged, setReviewAcknowledged] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const loadProfile = useCallback(async () => {
    setLoadingProfile(true)
    try {
      const next = await fetchJson<JobProfileSummary>(`${API_BASE}/api/jobs/profile`)
      setSummary(next)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoadingProfile(false)
    }
  }, [])

  useEffect(() => { void loadProfile() }, [loadProfile])

  useEffect(() => {
    // A new extract is new evidence; an old review must never be reused.
    setPlan(null)
    setReviewAcknowledged(false)
  }, [initialPage?.url])

  const hasApprovedFact = useMemo(() => {
    const values = [
      ...Object.values(draft.identity),
      ...Object.values(draft.links),
      ...draft.approvedAnswers.map((answer) => answer.value)
    ]
    return values.some((value) => value.trim().length > 0)
  }, [draft])

  const reviewedActions = useMemo(
    () => (plan?.actions ?? []).filter((action) => !hasSubmission(action)),
    [plan]
  )
  const safelyAddressableFields = useMemo(() => initialPage ? pageFields(initialPage) : [], [initialPage])
  const requiresReplacementAcknowledgement = Boolean(summary?.has_profile)
  const canSave = hasApprovedFact && localOnlyAcknowledged && (!requiresReplacementAcknowledgement || replaceExisting) && !saving

  function setIdentity(key: string, value: string) {
    setDraft((current) => ({ ...current, identity: { ...current.identity, [key]: value } }))
  }

  function setLink(key: string, value: string) {
    setDraft((current) => ({ ...current, links: { ...current.links, [key]: value } }))
  }

  function setAnswer(index: number, key: keyof AnswerDraft, value: string) {
    setDraft((current) => ({
      ...current,
      approvedAnswers: current.approvedAnswers.map((answer, answerIndex) => answerIndex === index ? { ...answer, [key]: value } : answer)
    }))
  }

  function removeAnswer(index: number) {
    setDraft((current) => ({ ...current, approvedAnswers: current.approvedAnswers.filter((_, answerIndex) => answerIndex !== index) }))
  }

  async function saveProfile() {
    if (!canSave) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const approvedAnswers = Object.fromEntries(
        draft.approvedAnswers
          .map((answer) => [answer.key.trim(), answer.value.trim()] as const)
          .filter(([key, value]) => Boolean(key && value))
      )
      const data = {
        identity: Object.fromEntries(Object.entries(draft.identity).map(([key, value]) => [key, value.trim()]).filter(([, value]) => Boolean(value))),
        links: Object.fromEntries(Object.entries(draft.links).map(([key, value]) => [key, value.trim()]).filter(([, value]) => Boolean(value))),
        resume_path: draft.resumePath.trim(),
        cover_letter_path: draft.coverLetterPath.trim(),
        work_authorization: draft.workAuthorization.trim(),
        approved_answers: approvedAnswers,
        preferences: {
          titles: splitLines(draft.titles),
          locations: splitLines(draft.locations),
          remote: draft.remote
        }
      }
      const next = await fetchJson<JobProfileSummary>(`${API_BASE}/api/jobs/profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data })
      })
      setSummary(next)
      // The API cannot read values back, and neither does this view after save.
      setDraft(emptyDraft())
      setLocalOnlyAcknowledged(false)
      setReplaceExisting(false)
      setMessage('LOCAL PROFILE SAVED. VALUES HAVE BEEN CLEARED FROM THIS SCREEN; ONLY THE FACT INVENTORY REMAINS.')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  async function planFill() {
    if (!initialPage || safelyAddressableFields.length === 0 || !summary?.has_profile) return
    setPlanning(true)
    setError('')
    setMessage('')
    try {
      const next = await fetchJson<JobFillPlan>(`${API_BASE}/api/jobs/plan_fill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fields: safelyAddressableFields })
      })
      setPlan({
        plan: Array.isArray(next.plan) ? next.plan : [],
        actions: Array.isArray(next.actions) ? next.actions : [],
        summary: next.summary ?? { fields: 0, auto_fill: 0, needs_user: [] }
      })
      setReviewAcknowledged(false)
      setMessage('FACTS-ONLY REVIEW READY. NO FIELD HAS BEEN FILLED.')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setPlanning(false)
    }
  }

  function queueReviewedFills() {
    if (!reviewAcknowledged || reviewedActions.length === 0) return
    onQueueReviewedFills(reviewedActions)
  }

  const inventory = summaryKeys(summary)

  return (
    <div className="scrollbar-small h-full overflow-y-auto p-5 lg:p-6">
      <div className="mx-auto flex max-w-6xl flex-col gap-5 pb-8">
        <header className="flex flex-col justify-between gap-4 border-b border-white/10 pb-5 lg:flex-row lg:items-end">
          <div>
            <div className="flex items-center gap-2 text-[11px] font-mono tracking-[0.25em] text-amber-400">
              <span className="h-2 w-2 rounded-full bg-amber-400 shadow-[0_0_12px_rgba(251,191,36,0.7)]" />
              JOB APPLICATION MODE / FACTS ONLY
            </div>
            <h1 className="mt-2 text-xl font-black tracking-[0.18em] text-zinc-100">PROFILE + FILL REVIEW</h1>
            <p className="mt-2 max-w-3xl text-xs leading-5 text-zinc-500">JARVIS copies only facts you approve. It never writes an answer, uploads an unreviewed file, or submits an application for you.</p>
          </div>
          <button type="button" onClick={() => void loadProfile()} disabled={loadingProfile || saving} className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-[10px] font-black tracking-[0.16em] text-zinc-300 transition-colors hover:border-amber-500/35 hover:text-amber-300 disabled:opacity-50">
            {loadingProfile ? 'CHECKING LOCAL PROFILE' : 'REFRESH FACT INVENTORY'}
          </button>
        </header>

        {error ? <div role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div> : null}
        {message ? <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">{message}</div> : null}

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div className="sb-panel p-4"><div className="text-[10px] font-mono tracking-[0.2em] text-zinc-500">LOCAL PROFILE</div><div className={`mt-2 text-2xl font-black ${summary?.has_profile ? 'text-emerald-300' : 'text-zinc-500'}`}>{summary?.has_profile ? 'READY' : 'EMPTY'}</div></div>
          <div className="sb-panel p-4"><div className="text-[10px] font-mono tracking-[0.2em] text-zinc-500">APPROVED FACTS</div><div className="mt-2 text-2xl font-black text-zinc-200">{inventory.length}</div></div>
          <div className="sb-panel p-4"><div className="text-[10px] font-mono tracking-[0.2em] text-zinc-500">RÉSUMÉ ON FILE</div><div className={`mt-2 text-2xl font-black ${summary?.resume ? 'text-emerald-300' : 'text-zinc-500'}`}>{summary?.resume ? 'YES' : 'NO'}</div></div>
          <div className="sb-panel p-4"><div className="text-[10px] font-mono tracking-[0.2em] text-zinc-500">FILL REVIEW</div><div className={`mt-2 text-2xl font-black ${initialPage?.elements.length ? 'text-amber-300' : 'text-zinc-500'}`}>{initialPage?.elements.length ? 'EVIDENCE READY' : 'AWAITING EXTRACT'}</div></div>
        </section>

        <section className="sb-panel overflow-hidden">
          <div className="border-b border-white/10 px-5 py-4">
            <div className="sb-label">APPROVED FACT INVENTORY</div>
            <p className="mt-1 text-[11px] leading-5 text-zinc-500">For privacy, this screen knows which facts exist but never asks the backend to reveal their saved values.</p>
          </div>
          <div className="p-5">
            {loadingProfile ? <div className="text-xs text-zinc-500">Reading the local inventory…</div> : inventory.length ? <div className="flex flex-wrap gap-2">{inventory.map((key) => <span key={key} className="rounded border border-emerald-500/20 bg-emerald-500/5 px-2.5 py-1.5 text-[10px] font-mono tracking-[0.1em] text-emerald-200">PROFILE.{key.toUpperCase()}</span>)}{summary?.resume ? <span className="rounded border border-emerald-500/20 bg-emerald-500/5 px-2.5 py-1.5 text-[10px] font-mono tracking-[0.1em] text-emerald-200">PROFILE.RESUME_PATH</span> : null}{summary?.cover_letter ? <span className="rounded border border-emerald-500/20 bg-emerald-500/5 px-2.5 py-1.5 text-[10px] font-mono tracking-[0.1em] text-emerald-200">PROFILE.COVER_LETTER_PATH</span> : null}</div> : <div className="text-xs leading-5 text-zinc-500">No approved facts are on file yet. Enter only information you are happy for JARVIS to reuse verbatim.</div>}
          </div>
        </section>

        <section className="sb-panel overflow-hidden">
          <div className="border-b border-white/10 px-5 py-4">
            <div className="sb-label">LOCAL PROFILE EDITOR</div>
            <p className="mt-1 text-[11px] leading-5 text-zinc-500">Inputs are sent only to the local JARVIS backend and saved outside the repository. Saving replaces the prior profile; saved values are never populated back into these fields.</p>
          </div>
          <div className="space-y-6 p-5">
            {requiresReplacementAcknowledgement ? <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs leading-5 text-amber-100">A local profile already exists. Its values are intentionally hidden. Saving this editor <strong>replaces</strong> it, so re-enter every fact you want to retain.</div> : null}
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {IDENTITY_FIELDS.map(([key, label]) => <label key={key} className="block"><span className="sb-label">{label}</span><input value={draft.identity[key] ?? ''} onChange={(event) => setIdentity(key, event.target.value)} autoComplete="off" className="mt-2 w-full rounded-xl border border-white/10 bg-black/40 px-3 py-3 text-sm text-zinc-200 outline-none focus:border-amber-500/40" /></label>)}
            </div>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {LINK_FIELDS.map(([key, label]) => <label key={key} className="block"><span className="sb-label">{label}</span><input value={draft.links[key] ?? ''} onChange={(event) => setLink(key, event.target.value)} autoComplete="off" className="mt-2 w-full rounded-xl border border-white/10 bg-black/40 px-3 py-3 text-sm text-zinc-200 outline-none focus:border-amber-500/40" /></label>)}
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <label className="block"><span className="sb-label">Approved résumé path</span><input value={draft.resumePath} onChange={(event) => setDraft((current) => ({ ...current, resumePath: event.target.value }))} autoComplete="off" placeholder="C:\\path\\to\\resume.pdf" className="mt-2 w-full rounded-xl border border-white/10 bg-black/40 px-3 py-3 font-mono text-sm text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-amber-500/40" /></label>
              <label className="block"><span className="sb-label">Approved cover letter path</span><input value={draft.coverLetterPath} onChange={(event) => setDraft((current) => ({ ...current, coverLetterPath: event.target.value }))} autoComplete="off" placeholder="C:\\path\\to\\cover-letter.pdf" className="mt-2 w-full rounded-xl border border-white/10 bg-black/40 px-3 py-3 font-mono text-sm text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-amber-500/40" /></label>
              <label className="block"><span className="sb-label">Work authorization</span><input value={draft.workAuthorization} onChange={(event) => setDraft((current) => ({ ...current, workAuthorization: event.target.value }))} autoComplete="off" className="mt-2 w-full rounded-xl border border-white/10 bg-black/40 px-3 py-3 text-sm text-zinc-200 outline-none focus:border-amber-500/40" /></label>
            </div>

            <div className="rounded-xl border border-white/5 bg-black/20 p-4">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"><div><div className="sb-label">REUSABLE SCREENING ANSWERS</div><p className="mt-1 text-[11px] leading-5 text-zinc-500">Only answers you approve word-for-word. Do not add credentials, free-form essays, or anything that needs context.</p></div><button type="button" onClick={() => setDraft((current) => ({ ...current, approvedAnswers: [...current.approvedAnswers, { key: '', value: '' }] }))} className="rounded-lg border border-white/10 px-3 py-2 text-[9px] font-black tracking-[0.14em] text-zinc-300 hover:border-amber-500/35 hover:text-amber-300">ADD ANSWER</button></div>
              <div className="mt-4 space-y-3">{draft.approvedAnswers.map((answer, index) => <div key={index} className="grid gap-3 sm:grid-cols-[0.72fr_1.28fr_auto]"><input value={answer.key} onChange={(event) => setAnswer(index, 'key', event.target.value)} autoComplete="off" placeholder="e.g. notice_period" className="rounded-xl border border-white/10 bg-black/40 px-3 py-3 font-mono text-sm text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-amber-500/40" /><input value={answer.value} onChange={(event) => setAnswer(index, 'value', event.target.value)} autoComplete="off" placeholder="Your approved verbatim answer" className="rounded-xl border border-white/10 bg-black/40 px-3 py-3 text-sm text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-amber-500/40" /><button type="button" onClick={() => removeAnswer(index)} className="rounded-xl border border-red-500/25 px-3 text-[9px] font-black tracking-[0.14em] text-red-300 hover:bg-red-500/10">REMOVE</button></div>)}</div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <label className="block"><span className="sb-label">Target titles</span><textarea value={draft.titles} onChange={(event) => setDraft((current) => ({ ...current, titles: event.target.value }))} placeholder="Security Analyst, SOC Analyst" className="scrollbar-small mt-2 h-20 w-full resize-none rounded-xl border border-white/10 bg-black/40 px-3 py-3 text-sm text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-amber-500/40" /></label>
              <label className="block"><span className="sb-label">Target locations</span><textarea value={draft.locations} onChange={(event) => setDraft((current) => ({ ...current, locations: event.target.value }))} placeholder="London, Remote" className="scrollbar-small mt-2 h-20 w-full resize-none rounded-xl border border-white/10 bg-black/40 px-3 py-3 text-sm text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-amber-500/40" /></label>
            </div>
            <div className="flex flex-col gap-3 border-t border-white/5 pt-5">
              <p className="text-[11px] leading-5 text-zinc-500">Include at least one identity fact, link, or reusable screening answer before saving. A file path alone cannot establish a fillable profile inventory.</p>
              <label className="flex cursor-pointer items-start gap-2 text-xs leading-5 text-zinc-300"><input type="checkbox" checked={draft.remote} onChange={(event) => setDraft((current) => ({ ...current, remote: event.target.checked }))} className="mt-0.5 h-4 w-4 rounded border-white/20 bg-black accent-amber-400" /><span>Remote roles are an approved preference for ranking.</span></label>
              <label className="flex cursor-pointer items-start gap-2 text-xs leading-5 text-zinc-300"><input type="checkbox" checked={localOnlyAcknowledged} onChange={(event) => setLocalOnlyAcknowledged(event.target.checked)} className="mt-0.5 h-4 w-4 rounded border-white/20 bg-black accent-amber-400" /><span>I approve these exact facts for local storage and verbatim reuse in job forms. I understand JARVIS will not make up answers.</span></label>
              {requiresReplacementAcknowledgement ? <label className="flex cursor-pointer items-start gap-2 text-xs leading-5 text-amber-100"><input type="checkbox" checked={replaceExisting} onChange={(event) => setReplaceExisting(event.target.checked)} className="mt-0.5 h-4 w-4 rounded border-amber-500/40 bg-black accent-amber-400" /><span>I understand this replaces the existing profile, whose values are hidden from this editor.</span></label> : null}
              <button type="button" disabled={!canSave} onClick={() => void saveProfile()} className="self-start rounded-xl bg-amber-500 px-4 py-3 text-[10px] font-black tracking-[0.16em] text-black transition-colors hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-35">{saving ? 'SAVING LOCAL PROFILE' : 'SAVE APPROVED LOCAL FACTS'}</button>
            </div>
          </div>
        </section>

        <section className="sb-panel overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-white/10 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
            <div><div className="sb-label">FACTS-ONLY FILL REVIEW</div><p className="mt-1 text-[11px] leading-5 text-zinc-500">The source is the latest browser extract. Review mappings by source key, then return the steps to Control for individual approval.</p></div>
            <button type="button" disabled={safelyAddressableFields.length === 0 || !summary?.has_profile || planning} onClick={() => void planFill()} className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-[10px] font-black tracking-[0.16em] text-amber-300 transition-colors hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-35">{planning ? 'BUILDING REVIEW' : 'PLAN FACTS-ONLY FILL'}</button>
          </div>
          <div className="p-5">
            {!initialPage ? <div className="rounded-xl border border-white/5 bg-black/20 p-4 text-xs leading-5 text-zinc-500">Open Control, start a browser-scoped session, navigate to an allowed application page, then use <strong className="text-zinc-300">READ PAGE ELEMENTS</strong> and <strong className="text-zinc-300">PREPARE JOB FILL REVIEW</strong>. No page evidence has been handed to this view yet.</div> : <div className="rounded-xl border border-white/5 bg-black/20 p-4"><div className="text-[10px] font-mono tracking-[0.16em] text-zinc-500">EXTRACTED PAGE</div><div className="mt-2 break-all font-mono text-xs text-amber-300">{initialPage.url}</div><div className="mt-2 text-[11px] text-zinc-500">{initialPage.elements.length} observed page element{initialPage.elements.length === 1 ? '' : 's'} • {safelyAddressableFields.length} safely addressable • no actions executed</div></div>}
            {initialPage && !summary?.has_profile ? <p className="mt-4 text-xs leading-5 text-amber-200">Save at least one approved fact first. The planner will not guess a profile or fill from anything else.</p> : null}
            {initialPage && safelyAddressableFields.length === 0 ? <p className="mt-4 text-xs leading-5 text-amber-200">This extract has no fields with a stable name or id. JARVIS will not auto-fill using a broad selector; use Control to review the page manually.</p> : null}
            {plan ? <div className="mt-5 space-y-5"><div className="grid gap-3 sm:grid-cols-3"><div className="rounded-lg border border-white/5 bg-black/20 p-3"><div className="text-[9px] font-mono tracking-[0.14em] text-zinc-500">OBSERVED FIELDS</div><div className="mt-1 text-xl font-black text-zinc-100">{plan.summary.fields}</div></div><div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3"><div className="text-[9px] font-mono tracking-[0.14em] text-emerald-300">PROFILE MAPPINGS</div><div className="mt-1 text-xl font-black text-emerald-200">{plan.summary.auto_fill}</div></div><div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3"><div className="text-[9px] font-mono tracking-[0.14em] text-amber-300">YOU NEED TO FILL</div><div className="mt-1 text-xl font-black text-amber-200">{plan.summary.needs_user.length}</div></div></div>
              <div className="divide-y divide-white/5 overflow-hidden rounded-xl border border-white/5">{plan.plan.map((step, index) => <div key={`${step.selector}-${index}`} className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-start sm:justify-between"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className={`rounded border px-2 py-1 text-[9px] font-mono tracking-[0.12em] ${step.needs_user ? 'border-amber-500/30 bg-amber-500/10 text-amber-200' : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'}`}>{step.needs_user ? 'NEEDS YOU' : actionKind(step.action)}</span>{!step.needs_user ? <span className="text-[9px] font-mono tracking-[0.12em] text-emerald-300">{String(step.source || 'profile fact').toUpperCase()}</span> : null}</div><div className="mt-2 text-sm font-bold text-zinc-100">{step.label || step.selector || 'Unnamed field'}</div><div className="mt-1 text-[11px] leading-5 text-zinc-500">{step.needs_user ? step.reason || 'You fill this field yourself.' : 'Will copy an approved local fact verbatim. Its value stays hidden here.'}</div></div><span className="shrink-0 break-all font-mono text-[10px] text-zinc-600">{step.selector || 'NO SELECTOR'}</span></div>)}</div>
              {reviewedActions.length ? <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/5 p-4"><label className="flex cursor-pointer items-start gap-2 text-xs leading-5 text-zinc-200"><input type="checkbox" checked={reviewAcknowledged} onChange={(event) => setReviewAcknowledged(event.target.checked)} className="mt-0.5 h-4 w-4 rounded border-white/20 bg-black accent-amber-400" /><span>I reviewed every profile mapping. I understand these are queued only, each browser fill still needs approval in Control, and unknown fields remain for me.</span></label><button type="button" disabled={!reviewAcknowledged} onClick={queueReviewedFills} className="mt-4 rounded-xl bg-amber-500 px-4 py-3 text-[10px] font-black tracking-[0.16em] text-black transition-colors hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-35">QUEUE {reviewedActions.length} REVIEWED FILL STEP{reviewedActions.length === 1 ? '' : 'S'} IN CONTROL</button><p className="mt-3 text-[11px] leading-5 text-zinc-500">Submit is deliberately absent. After reviewed fills, you return to Control and make any final application click through its separate confirmation.</p></div> : <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4 text-xs leading-5 text-amber-100">There are no safe automatic fills. Complete the marked fields yourself; JARVIS will not invent a value.</div>}</div> : null}
          </div>
        </section>
      </div>
    </div>
  )
}
