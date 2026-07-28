/**
 * Shared types, constants, and utilities for the JARVIS Desktop Shell.
 * Used across App.tsx and all extracted views.
 */

/* ═══════════════════════════════════════════
   Type Definitions
   ═══════════════════════════════════════════ */

export type ProviderInfo = { name?: string; model?: string; local?: boolean }

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
  status?: RuntimeStatus
}

export type ShellTab = 'dashboard' | 'macros' | 'notes' | 'gallery' | 'phone' | 'settings' | 'oracle'
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
