/**
 * Shared types, constants, and utilities for the JARVIS Desktop Shell.
 * Used across App.tsx and all extracted views.
 */

/* ═══════════════════════════════════════════
   Type Definitions
   ═══════════════════════════════════════════ */

export type ProviderInfo = { name?: string; model?: string; local?: boolean }

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
  source?: 'backend' | 'shell'
}

export type ChatResponse = {
  reply: string
  messages: ChatMessage[]
  waiting_for_input: boolean
  processing: boolean
  timed_out?: boolean
  status?: RuntimeStatus
}

export type ShellTab = 'dashboard' | 'macros' | 'notes' | 'gallery' | 'phone' | 'settings'
export type SettingsTab = 'general' | 'keys' | 'security'

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

export async function fetchJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init)
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
  const shell = currentMessages.filter((m) => m.source === 'shell')
  return [...backend, ...shell].sort((a, b) => {
    const aTs = Date.parse(a.ts || '')
    const bTs = Date.parse(b.ts || '')
    if (Number.isFinite(aTs) && Number.isFinite(bTs) && aTs !== bTs) return aTs - bTs
    return a.id - b.id
  })
}

export function createRendererVoiceSnapshot(): VoiceStatus {
  return { loaded: false, active: false, connecting: false, engine: SHELL_VOICE_ENGINE, live_session: false, wake_word_active: false, mic_muted: false, last_input: '', last_output: '', error: '', source: 'renderer' }
}
