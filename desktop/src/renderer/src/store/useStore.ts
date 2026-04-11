/**
 * Zustand global store — replaces all prop-drilling in App.tsx.
 * Slices: shell, voice, chat, widgets.
 */

import { create } from 'zustand'

/* ═══════════════════════════════════════════
   Type Definitions
   ═══════════════════════════════════════════ */

export type ShellTab = 'dashboard' | 'macros' | 'notes' | 'gallery' | 'phone' | 'settings'
export type SettingsTab = 'general' | 'keys' | 'security'
export type VisionSource = 'none' | 'camera' | 'screen'

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
   Widget Types
   ═══════════════════════════════════════════ */

export type WidgetType =
  | 'weather'
  | 'terminal'
  | 'system'
  | 'tools'
  | 'map'
  | 'stock'
  | 'email'
  | 'research'
  | 'code-editor'
  | 'knowledge'
  | 'security'
  | 'memory'

export interface WidgetInstance {
  id: string
  type: WidgetType
  title: string
  x: number
  y: number
  width: number
  height: number
  minimized: boolean
}

export const WIDGET_DEFAULTS: Record<WidgetType, { title: string; width: number; height: number }> = {
  weather:       { title: 'Weather',          width: 340, height: 320 },
  terminal:      { title: 'Terminal',          width: 600, height: 400 },
  system:        { title: 'System Monitor',   width: 420, height: 360 },
  tools:         { title: 'Tools & Plugins',  width: 400, height: 500 },
  map:           { title: 'Map',              width: 500, height: 400 },
  stock:         { title: 'Stock Tracker',    width: 420, height: 380 },
  email:         { title: 'Email',            width: 500, height: 450 },
  research:      { title: 'Deep Research',    width: 520, height: 480 },
  'code-editor': { title: 'Code Editor',      width: 700, height: 500 },
  knowledge:     { title: 'Knowledge Graph',  width: 500, height: 400 },
  security:      { title: 'Security Suite',   width: 520, height: 460 },
  memory:        { title: 'Memory Bank',      width: 440, height: 400 },
}

/* ═══════════════════════════════════════════
   Store Interface
   ═══════════════════════════════════════════ */

interface JarvisStore {
  // Shell
  activeTab: ShellTab
  setActiveTab: (tab: ShellTab) => void
  backendState: string
  setBackendState: (s: string) => void
  locked: boolean
  setLocked: (v: boolean) => void
  overlayMode: boolean
  setOverlayMode: (v: boolean) => void
  toggleOverlayMode: () => void

  // Runtime
  status: RuntimeStatus | null
  setStatus: (s: RuntimeStatus | null) => void
  snapshot: JarvisShellSnapshot | null
  setSnapshot: (s: JarvisShellSnapshot | null) => void
  systemStats: SystemStatsResult | null
  setSystemStats: (s: SystemStatsResult | null) => void

  // Voice
  voiceStatus: VoiceStatus | null
  setVoiceStatus: (v: VoiceStatus | null) => void
  audioLevel: number
  setAudioLevel: (v: number) => void
  visionSource: VisionSource
  setVisionSource: (v: VisionSource) => void
  dashboardVisionSource: VisionSource
  setDashboardVisionSource: (v: VisionSource) => void
  showVisionSourceModal: boolean
  setShowVisionSourceModal: (v: boolean) => void

  // Chat
  messages: ChatMessage[]
  setMessages: (msgs: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => void
  prompt: string
  setPrompt: (v: string) => void
  approveDesktop: boolean
  setApproveDesktop: (v: boolean) => void
  busy: boolean
  setBusy: (v: boolean) => void
  error: string
  setError: (v: string) => void

  // Widgets
  widgets: WidgetInstance[]
  openWidget: (type: WidgetType) => void
  closeWidget: (id: string) => void
  toggleWidget: (type: WidgetType) => void
  moveWidget: (id: string, x: number, y: number) => void
  minimizeWidget: (id: string) => void
}

/* ═══════════════════════════════════════════
   Store Implementation
   ═══════════════════════════════════════════ */

let _widgetCounter = 0

export const useStore = create<JarvisStore>((set, get) => ({
  // Shell
  activeTab: 'dashboard',
  setActiveTab: (tab) => set({ activeTab: tab }),
  backendState: 'OFFLINE',
  setBackendState: (s) => set({ backendState: s }),
  locked: true,
  setLocked: (v) => set({ locked: v }),
  overlayMode: false,
  setOverlayMode: (v) => set({ overlayMode: v }),
  toggleOverlayMode: () => set((s) => ({ overlayMode: !s.overlayMode })),

  // Runtime
  status: null,
  setStatus: (s) => set({ status: s }),
  snapshot: null,
  setSnapshot: (s) => set({ snapshot: s }),
  systemStats: null,
  setSystemStats: (s) => set({ systemStats: s }),

  // Voice
  voiceStatus: null,
  setVoiceStatus: (v) => set({ voiceStatus: v }),
  audioLevel: 0,
  setAudioLevel: (v) => set({ audioLevel: v }),
  visionSource: 'none',
  setVisionSource: (v) => set({ visionSource: v }),
  dashboardVisionSource: 'none',
  setDashboardVisionSource: (v) => set({ dashboardVisionSource: v }),
  showVisionSourceModal: false,
  setShowVisionSourceModal: (v) => set({ showVisionSourceModal: v }),

  // Chat
  messages: [],
  setMessages: (msgs) => set((s) => ({
    messages: typeof msgs === 'function' ? msgs(s.messages) : msgs
  })),
  prompt: '',
  setPrompt: (v) => set({ prompt: v }),
  approveDesktop: false,
  setApproveDesktop: (v) => set({ approveDesktop: v }),
  busy: false,
  setBusy: (v) => set({ busy: v }),
  error: '',
  setError: (v) => set({ error: v }),

  // Widgets
  widgets: [],
  openWidget: (type) => {
    const existing = get().widgets.find((w) => w.type === type)
    if (existing) {
      // bring to front / unminimize
      set((s) => ({
        widgets: s.widgets.map((w) => w.id === existing.id ? { ...w, minimized: false } : w)
      }))
      return
    }
    const defaults = WIDGET_DEFAULTS[type]
    _widgetCounter += 1
    const offset = (_widgetCounter % 6) * 30
    const widget: WidgetInstance = {
      id: `${type}-${Date.now()}`,
      type,
      title: defaults.title,
      x: 120 + offset,
      y: 80 + offset,
      width: defaults.width,
      height: defaults.height,
      minimized: false,
    }
    set((s) => ({ widgets: [...s.widgets, widget] }))
  },
  closeWidget: (id) => set((s) => ({ widgets: s.widgets.filter((w) => w.id !== id) })),
  toggleWidget: (type) => {
    const existing = get().widgets.find((w) => w.type === type)
    if (existing) {
      get().closeWidget(existing.id)
    } else {
      get().openWidget(type)
    }
  },
  moveWidget: (id, x, y) => set((s) => ({
    widgets: s.widgets.map((w) => w.id === id ? { ...w, x, y } : w)
  })),
  minimizeWidget: (id) => set((s) => ({
    widgets: s.widgets.map((w) => w.id === id ? { ...w, minimized: !w.minimized } : w)
  })),
}))
