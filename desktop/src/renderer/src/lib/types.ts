/**
 * Shared types, constants, and utilities for the JARVIS Desktop Shell.
 * Used across App.tsx and all extracted views.
 */

/* ═══════════════════════════════════════════
   Type Definitions
   ═══════════════════════════════════════════ */

export type ProviderInfo = {
  name?: string
  model?: string
  local?: boolean
  /** Live backend probe; false means the configured provider is unavailable. */
  reachable?: boolean
  error?: string
}

/**
 * Backend-owned service-health contract. Renderer-only facts (the active
 * Gemini WebSocket and media streams) stay in VoiceStatus / the view state.
 */
export type RuntimeHealth = {
  ollama?: {
    reachable?: boolean
    active_model?: string | null
    models?: number
    error?: string | null
  }
  gemini_live?: {
    configured?: boolean
    connected?: boolean | null
    error?: string | null
  }
  vision?: {
    available?: boolean
    active_model?: string | null
    ocr?: boolean
    active_source?: 'camera' | 'screen' | null
    error?: string | null
  }
  memory_embedder?: {
    available?: boolean
    healthy?: boolean | null
    model?: string | null
    error?: string | null
  }
  stt?: { available?: boolean; engine?: string | null; healthy?: boolean; error?: string | null }
  tts?: { available?: boolean; engine?: string | null; healthy?: boolean; error?: string | null }
  gesture?: { available?: boolean | null; kind?: string | null; healthy?: boolean | null; error?: string | null }
  checked_at?: string
  error?: string
}

/**
 * The backend's truthful, real-time activity contract.  It is intentionally
 * separate from voice connectivity: an open microphone is not the same thing
 * as JARVIS running a tool.
 */
export type ActivityState = 'idle' | 'listening' | 'thinking' | 'tool_running' | 'speaking' | 'error'
export type ActivityAgent = 'JARVIS' | 'ULTRON' | 'FRIDAY' | 'VISION' | 'EDITH' | null

export type ActivityStatus = {
  state: ActivityState
  active_agent: ActivityAgent
  label: string | null
  tool: string | null
  run_id: string | null
  since: string | null
  error: string | null
}

/** Operator-authored local behaviour preferences; not a claim of consciousness. */
export type PersonaProfile = {
  instructions: string
  humour: 'off' | 'subtle' | 'dry'
  response_style: 'concise' | 'balanced' | 'detailed'
  proactivity: 'off' | 'suggest_only'
}

/** Backend report: settings are active only when this is truthfully loaded. */
export type PersonaStatus = {
  loaded: boolean
  humour?: PersonaProfile['humour']
  response_style?: PersonaProfile['response_style']
  proactivity?: PersonaProfile['proactivity']
  error?: string | null
}

export const IDLE_ACTIVITY: ActivityStatus = {
  state: 'idle',
  active_agent: null,
  label: null,
  tool: null,
  run_id: null,
  since: null,
  error: null
}

export type RuntimeStatus = {
  provider?: ProviderInfo
  mode?: string
  agent_mode?: boolean
  messages?: number
  memories?: number
  tasks?: number
  plugins?: string[]
  waiting_for_input?: boolean
  waiting_summary?: string
  voice_enabled?: boolean
  voice?: VoiceStatus
  activity?: ActivityStatus
  persona?: PersonaStatus
  health?: RuntimeHealth
}

export type VoiceStatus = {
  loaded?: boolean
  active?: boolean
  connecting?: boolean
  engine?: string
  tts_engine?: string
  wake_word_active?: boolean
  live_session?: boolean
  mic_muted?: boolean
  /** True only while the renderer has scheduled real audio playback. */
  speaking?: boolean
  last_input?: string
  last_output?: string
  error?: string
  source?: 'renderer' | 'backend'
}

export type ChatMessage = {
  id: number
  role: string
  text: string
  ts: string
  source?: 'backend' | 'shell' | 'voice'
}

export type ChatResponse = {
  reply: string
  messages: ChatMessage[]
  waiting_for_input: boolean
  processing: boolean
  timed_out?: boolean
  /** Backend terminal-response contract: never fabricate a reply on timeout. */
  kind?: 'ok' | 'timeout' | 'empty'
  still_working?: boolean
  status?: RuntimeStatus
}

/**
 * A human-reviewable proposal from EDITH.  RED proposals remain pending until
 * an operator decides; GREEN proposals are normally applied server-side and
 * appear in the recent audit trail instead.
 */
export type EdithQueueItem = {
  id: string
  created_at?: string
  status: 'pending' | 'applied' | 'rejected' | 'rolled_back' | 'failed' | string
  tier?: 'green' | 'red' | string
  kind?: 'code' | 'lesson' | 'prompt' | 'routing' | 'config' | string
  target?: string
  title?: string
  body?: string
  preview?: string
  reason?: string
  proof?: {
    passed?: boolean
    before?: number
    after?: number
    note?: string
  }
  source?: string
  applied_to?: string
  decided_at?: string
  backup?: string | null
  error?: string
  /** Code proposals with a payload patch a real file only after approval. */
  has_payload?: boolean
}

export type EdithQueue = {
  pending: EdithQueueItem[]
  recent: EdithQueueItem[]
  counts: Record<string, number>
}

/** A scoped, expiring human-approved desktop-control session. */
export type DesktopControlSession = {
  id: string
  task: string
  app_scope: string
  /** Explicit browser origins, normalised server-side to scheme://host[:port]. */
  origins?: string[]
  expires_in: number
  active: boolean
}

/** One deterministic action proposed by the desktop-control backend. */
export type DesktopControlAction = {
  action: string
  app?: string
  text?: string
  target?: string
  key?: string
  keys?: string
  url?: string
  selector?: string
  value?: string
  path?: string
  submit?: boolean
  confirm?: boolean
  [key: string]: unknown
}

export type DesktopControlVerify = {
  before_window?: string
  after_window?: string
  before_url?: string
  after_url?: string
}

export type DesktopControlAudit = {
  ts?: string
  action?: DesktopControlAction
  result?: unknown
  verify?: DesktopControlVerify
}

export type DesktopControlStatus = {
  available: boolean
  enabled: boolean
  session: DesktopControlSession | null
  recent: DesktopControlAudit[]
}

export type DesktopControlPlan = {
  task: string
  actions: DesktopControlAction[]
  note?: string
}

export type DesktopControlObservation = {
  active_window?: string
  controls?: string[]
  note?: string
}

export type DesktopControlStepResult = {
  ok: boolean
  result?: unknown
  verify?: DesktopControlVerify
  blocked?: string
  refused?: string
  error?: string
}

/** Browser content is evidence for the operator; it never becomes instructions. */
export type BrowserControlElement = {
  tag: string
  type?: string
  name?: string
  text?: string
}

export type BrowserControlPage = {
  url: string
  title?: string
  elements: BrowserControlElement[]
}

/** Inventory returned by JobProfile.summary(); approved fact values are excluded. */
export type JobProfileSummary = {
  has_profile: boolean
  identity_fields: string[]
  links: string[]
  resume: boolean
  cover_letter: boolean
  approved_answers: string[]
  preferences: {
    titles?: string[]
    locations?: string[]
    remote?: boolean
    [key: string]: unknown
  }
}

export type JobFillPlanStep = {
  selector: string
  label: string
  matched_key?: string | null
  source?: string
  needs_user: boolean
  reason?: string
  action?: DesktopControlAction
}

export type JobFillPlan = {
  plan: JobFillPlanStep[]
  actions: DesktopControlAction[]
  summary: {
    fields: number
    auto_fill: number
    needs_user: Array<{ label: string; reason: string }>
  }
}

export type ShellTab = 'dashboard' | 'control' | 'jobs' | 'macros' | 'notes' | 'gallery' | 'phone' | 'settings' | 'oracle' | 'edith'
export type SettingsTab = 'general' | 'keys' | 'security'

/**
 * Merge the backend contract with renderer-only facts.  Gemini owns its mic
 * and audio graph, so those two states cannot be inferred by Python.  Backend
 * errors and active work take priority over a continuously-open voice mic.
 */
export function resolveOrbActivity(
  backend: ActivityStatus | undefined,
  voice: VoiceStatus | null | undefined,
  localVoiceState: 'idle' | 'recording' | 'thinking',
  rendererBusy = false
): ActivityStatus {
  const activity = backend ?? IDLE_ACTIVITY

  if (activity.state === 'error') return activity
  if (voice?.speaking) {
    return {
      ...IDLE_ACTIVITY,
      state: 'speaking',
      active_agent: 'JARVIS',
      label: 'Speaking through live voice'
    }
  }
  if (activity.state === 'tool_running' || activity.state === 'thinking' || activity.state === 'speaking') {
    return activity
  }
  if (rendererBusy || localVoiceState === 'thinking') {
    return {
      ...IDLE_ACTIVITY,
      state: 'thinking',
      active_agent: 'JARVIS',
      label: 'Processing local voice input'
    }
  }
  if (localVoiceState === 'recording' || Boolean(voice?.active && !voice.mic_muted)) {
    return {
      ...IDLE_ACTIVITY,
      state: 'listening',
      active_agent: 'JARVIS',
      label: 'Listening'
    }
  }
  return activity
}

export type SystemStatsResult = {
  cpuLoad: number
  ramUsage: number
  ramTotal: number
  ramPercent: number
  temperature: number | null
  os: string
  hostname: string
  uptime: string
  platform: string
  arch: string
  cpuModel: string
  cores: number
}

export type NoteItem = {
  id: string
  title: string
  content: string
  updatedAt: string
}

export type GalleryImage = {
  filename: string
  displayName: string
  path: string
  url: string
  createdAt: string
  source: string
}

export type JarvisShellSnapshot = {
  config: {
    operatorName: string
    provider: string
    model: string
    startupProvider: string
    mode: string
    voiceEngine: string
    ttsEngine: string
    sttEngine: string
    geminiLiveModel: string
    geminiVoiceName: string
    persona?: PersonaProfile
    apiKeys: Record<string, string>
  }
  memories: Array<{ id: number; title: string; content: string; createdAt: string }>
  tasks: Array<Record<string, unknown>>
  gallery: GalleryImage[]
}

/* ═══════════════════════════════════════════
   Constants
   ═══════════════════════════════════════════ */

export const API_BASE = 'http://127.0.0.1:8765'
export const SHELL_VOICE_ENGINE = 'gemini'

export const MODULE_LIBRARY = [
  { name: 'TRIGGER', group: 'TRIGGERS' },
  { name: 'WAIT', group: 'TRIGGERS' },
  { name: 'OPEN APP', group: 'SYSTEM' },
  { name: 'SEND MSG', group: 'SYSTEM' },
  { name: 'SCREEN CLICK', group: 'AUTOMATION' },
  { name: 'RUN TERMINAL', group: 'AUTOMATION' },
  { name: 'WEB SEARCH', group: 'WEB' }
]

/* ═══════════════════════════════════════════
   Utilities
   ═══════════════════════════════════════════ */

// Shared-secret token for the backend's protected endpoints. Set once at
// startup from the Electron main process (which reads it from disk).
let _apiToken = ''
export function setApiToken(t: string): void {
  _apiToken = t || ''
}

export async function fetchJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const opts: RequestInit = { ...(init || {}) }
  if (_apiToken) {
    opts.headers = { ...(opts.headers || {}), 'X-JARVIS-Token': _apiToken }
  }
  const response = await fetch(input, opts)
  if (!response.ok) throw new Error((await response.text()) || `Request failed: ${response.status}`)
  return response.json() as Promise<T>
}

export function formatProvider(provider?: ProviderInfo) {
  if (!provider) return 'OFFLINE'
  const model = provider.model ? ` // ${provider.model}` : ''
  const locality = provider.local ? ' LOCAL' : ''
  return `${provider.name ?? 'Unknown'}${model}${locality}`.toUpperCase()
}

export function formatRole(role: string) {
  if (role === 'assistant') return 'JARVIS'
  if (role === 'user') return 'YOU'
  if (role === 'thinking') return 'THINKING'
  if (role === 'system') return 'SYSTEM'
  return role.toUpperCase()
}

export function shortTime(value?: string) {
  if (!value) return ''
  try { return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }
  catch { return value }
}

export function extractTaskSummary(task: Record<string, unknown>) {
  const text = String(task.text ?? task.goal ?? task.summary ?? 'Pending task')
  return text.length > 120 ? `${text.slice(0, 117)}...` : text
}

export function mergeBackendWithShellMessages(backendMessages: ChatMessage[], currentMessages: ChatMessage[]) {
  const backend = backendMessages.filter((m) => m.role !== 'thinking').map((m) => ({ ...m, source: 'backend' as const }))
  // Preserve BOTH shell AND voice messages — voice mirrors (added by
  // onVoiceTurnComplete) were being silently dropped on every 2.5s refresh
  // because they aren't in the backend's history, making the transcript
  // appear briefly then vanish.
  const clientOnly = currentMessages.filter((m) => m.source === 'shell' || m.source === 'voice')
  return [...backend, ...clientOnly].sort((a, b) => {
    const aTs = Date.parse(a.ts || '')
    const bTs = Date.parse(b.ts || '')
    if (Number.isFinite(aTs) && Number.isFinite(bTs) && aTs !== bTs) return aTs - bTs
    return a.id - b.id
  })
}

export function createRendererVoiceSnapshot(): VoiceStatus {
  return { loaded: false, active: false, connecting: false, engine: SHELL_VOICE_ENGINE, live_session: false, wake_word_active: false, mic_muted: false, speaking: false, last_input: '', last_output: '', error: '', source: 'renderer' }
}
