import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  RiCameraLine,
  RiCheckboxCircleFill,
  RiCommandLine,
  RiComputerLine,
  RiFolderImageLine,
  RiLayoutGridLine,
  RiPhoneFill,
  RiPhoneLine,
  RiSettings4Line,
  RiShieldKeyholeLine,
  RiStickyNoteLine,
  RiWifiLine
} from 'react-icons/ri'
import Titlebar from './components/Titlebar'
import LockScreen from './components/LockScreen'
import MiniOverlay from './components/MiniOverlay'
import WidgetLayer from './components/WidgetLayer'
import WidgetToolbar from './components/WidgetToolbar'
import ViewSkeleton from './components/ViewSkeleton'
import { JarvisGeminiLive, type VisionSource, type VoiceBridgeState } from './services/JarvisGeminiLive'
import type {
  ChatMessage,
  ChatResponse,
  JarvisShellSnapshot,
  RuntimeStatus,
  ShellTab,
  SystemStatsResult,
  VoiceStatus
} from './lib/types'
import {
  API_BASE,
  SHELL_VOICE_ENGINE,
  createRendererVoiceSnapshot,
  extractTaskSummary,
  fetchJson,
  formatProvider,
  mergeBackendWithShellMessages
} from './lib/types'

// ─── Views (Dashboard loads eagerly, others lazy for faster boot) ───
import DashboardView from './views/DashboardView'
const MacrosView = lazy(() => import('./views/MacrosView'))
const NotesView = lazy(() => import('./views/NotesView'))
const GalleryView = lazy(() => import('./views/GalleryView'))
const PhoneView = lazy(() => import('./views/PhoneView'))
const SettingsView = lazy(() => import('./views/SettingsView'))

/* ═══════════════════════════════════════════
   Root App — shell state, routing, voice bridge
   ═══════════════════════════════════════════ */

export default function App() {
  const [locked, setLocked] = useState(true)
  const [activeTab, setActiveTab] = useState<ShellTab>('dashboard')
  const [status, setStatus] = useState<RuntimeStatus | null>(null)
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [snapshot, setSnapshot] = useState<JarvisShellSnapshot | null>(null)
  const [prompt, setPrompt] = useState('')
  const [approveDesktop, setApproveDesktop] = useState(false)
  const [busy, setBusy] = useState(false)
  const [backendState, setBackendState] = useState('OFFLINE')
  const [maximized, setMaximized] = useState(false)
  const [error, setError] = useState('')
  const [clock, setClock] = useState(() => new Date())
  const [visionSource, setVisionSource] = useState<VisionSource>('none')
  const [dashboardVisionSource, setDashboardVisionSource] = useState<'none' | 'camera' | 'screen'>('none')
  const [showVisionSourceModal, setShowVisionSourceModal] = useState(false)
  const [overlayMode, setOverlayMode] = useState(false)
  const [audioLevel, setAudioLevel] = useState(0)
  const [systemStats, setSystemStats] = useState<SystemStatsResult | null>(null)

  const voiceBridgeRef = useRef<JarvisGeminiLive | null>(null)
  const approveDesktopRef = useRef(approveDesktop)
  const snapshotRef = useRef<JarvisShellSnapshot | null>(null)
  const statusRef = useRef<RuntimeStatus | null>(null)
  const backendStateRef = useRef('OFFLINE')
  const audioAnimRef = useRef<number>(0)

  // ─── Mirror typed-turn replies from live session into transcript ──────────
  // When the user sends typed text via sendUserText() while voice is active,
  // we want JARVIS's reply to appear in the transcript (not just the green box).
  // We watch last_output, debounce for stability, then commit ONCE per typed turn.
  const expectingLiveReplyRef = useRef(false)
  const lastCommittedOutputRef = useRef('')
  const liveReplyDebounceRef = useRef<number | null>(null)

  // ─── Refresh helpers ───

  const refreshAll = useCallback(async (clearError = true) => {
    try {
      const backendPromise = window.desktopApi?.backendStatus?.() ?? Promise.resolve({ running: false, port: 0, pid: null })
      const snapshotPromise = window.desktopApi?.shellSnapshot?.() ?? Promise.resolve(null as unknown as JarvisShellSnapshot)
      const [nextStatus, history, backend, shellSnapshot] = await Promise.all([
        fetchJson<RuntimeStatus>(`${API_BASE}/api/status`),
        fetchJson<{ messages: ChatMessage[] }>(`${API_BASE}/api/history?limit=120`),
        backendPromise,
        snapshotPromise
      ])
      setStatus(nextStatus)
      setMessages((c) => mergeBackendWithShellMessages(history.messages ?? [], c))
      setBackendState(backend.running ? `LIVE:${backend.port}` : 'OFFLINE')
      if (shellSnapshot) setSnapshot(shellSnapshot)
      statusRef.current = nextStatus
      if (shellSnapshot) snapshotRef.current = shellSnapshot
      backendStateRef.current = backend.running ? `LIVE:${backend.port}` : 'OFFLINE'
      const rv = voiceBridgeRef.current?.snapshot() ?? createRendererVoiceSnapshot()
      setVoiceStatus({ ...rv, engine: SHELL_VOICE_ENGINE, source: 'renderer' })
      if (clearError) setError('')
    } catch (err) {
      setBackendState('OFFLINE')
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [])

  // ─── Boot sequence ───

  useEffect(() => {
    voiceBridgeRef.current = new JarvisGeminiLive(API_BASE, {
      onStateChange: (nextState: VoiceBridgeState) => {
        setVoiceStatus({ ...nextState, source: 'renderer' })
      },
      onBackendTurn: () => refreshAll(false),
      getApproveDesktop: () => approveDesktopRef.current,
      getRealtimeContext: async () => {
        const runningApps = await window.desktopApi?.listRunningApps?.() ?? { apps: [] }
        const cs = snapshotRef.current
        const rs = statusRef.current
        const currentTask = cs?.tasks?.[0] ? extractTaskSummary(cs.tasks[0]) : 'NONE'
        return {
          runningApps: runningApps.apps,
          provider: formatProvider(rs?.provider),
          mode: rs?.mode || cs?.config.mode || 'GENERAL',
          backendState: backendStateRef.current,
          currentTask
        }
      },
      // Mirror voice exchanges into the main transcript so spoken replies
      // appear as proper chat bubbles (not just in the green I/O box).
      onVoiceTurnComplete: (userText: string, jarvisText: string) => {
        const now = new Date().toISOString()
        const newMessages: ChatMessage[] = []
        if (userText && userText.trim()) {
          newMessages.push({
            id: Date.now(),
            role: 'user',
            text: userText.trim(),
            ts: now,
            source: 'voice'
          })
        }
        if (jarvisText && jarvisText.trim()) {
          newMessages.push({
            id: Date.now() + 1,
            role: 'jarvis',
            text: jarvisText.trim(),
            ts: now,
            source: 'voice'
          })
        }
        if (newMessages.length > 0) {
          setMessages((c) => [...c, ...newMessages])
        }
      }
    })

    void refreshAll()
    const refreshTimer = window.setInterval(() => void refreshAll(false), 2500)
    const clockTimer = window.setInterval(() => setClock(new Date()), 1000)

    const statsTimer = window.setInterval(async () => {
      try { setSystemStats(await window.desktopApi?.systemStats()) } catch { /* ignore */ }
    }, 3000)
    void window.desktopApi?.systemStats?.().then(setSystemStats).catch(() => {})

    const cleanupOverlay = window.desktopApi?.onOverlayToggle?.(() => {
      setOverlayMode((prev) => !prev)
    })

    return () => {
      void voiceBridgeRef.current?.stop()
      voiceBridgeRef.current?.stopVision()
      voiceBridgeRef.current = null
      window.clearInterval(refreshTimer)
      window.clearInterval(clockTimer)
      window.clearInterval(statsTimer)
      cleanupOverlay?.()
      cancelAnimationFrame(audioAnimRef.current)
    }
  }, [refreshAll])

  useEffect(() => { approveDesktopRef.current = approveDesktop }, [approveDesktop])
  useEffect(() => { snapshotRef.current = snapshot }, [snapshot])
  useEffect(() => { statusRef.current = status }, [status])
  useEffect(() => { backendStateRef.current = backendState }, [backendState])

  // ─── Mirror live-session JARVIS replies into transcript ───────────────────
  // When the user typed text via sendUserText (expectingLiveReplyRef = true),
  // wait for last_output to settle (1.2s of stability) then commit it as a
  // jarvis message in the transcript. This makes typed conversations feel
  // continuous instead of split between transcript and the green box.
  useEffect(() => {
    const out = voiceStatus?.last_output ?? ''
    if (!expectingLiveReplyRef.current) return
    if (!out || out === lastCommittedOutputRef.current) return

    // Reset the debounce timer on every change — only fire when stable
    if (liveReplyDebounceRef.current !== null) {
      window.clearTimeout(liveReplyDebounceRef.current)
    }
    liveReplyDebounceRef.current = window.setTimeout(() => {
      const finalOut = voiceBridgeRef.current?.snapshot().last_output ?? ''
      if (finalOut && finalOut !== lastCommittedOutputRef.current) {
        setMessages((c) => [
          ...c,
          {
            id: Date.now(),
            role: 'assistant',
            text: finalOut,
            ts: new Date().toISOString(),
            source: 'shell'
          }
        ])
        lastCommittedOutputRef.current = finalOut
      }
      expectingLiveReplyRef.current = false
      liveReplyDebounceRef.current = null
    }, 1200)

    return () => {
      if (liveReplyDebounceRef.current !== null) {
        window.clearTimeout(liveReplyDebounceRef.current)
      }
    }
  }, [voiceStatus?.last_output])

  // ─── Audio level polling for sphere reactivity ───

  useEffect(() => {
    function pollAudio() {
      const bridge = voiceBridgeRef.current as unknown as { analyser?: AnalyserNode }
      if (bridge?.analyser) {
        const data = new Uint8Array(bridge.analyser.frequencyBinCount)
        bridge.analyser.getByteFrequencyData(data)
        let sum = 0
        for (let i = 0; i < data.length; i++) sum += data[i]
        setAudioLevel(sum / data.length / 255)
      } else {
        setAudioLevel(0)
      }
      audioAnimRef.current = requestAnimationFrame(pollAudio)
    }
    audioAnimRef.current = requestAnimationFrame(pollAudio)
    return () => cancelAnimationFrame(audioAnimRef.current)
  }, [])

  // ─── Actions ───

  function appendShellSystemMessage(text: string) {
    setMessages((c) => [...c, { id: Date.now(), role: 'system', text, ts: new Date().toISOString(), source: 'shell' }])
  }

  async function sendPrompt(nextPrompt?: string) {
    const text = (nextPrompt ?? prompt).trim()
    if (!text) return
    setError(''); setPrompt('')

    // ── Route: if Gemini Live session is active, inject into it directly ──────
    // Text typed/pasted in the input box should reach the same JARVIS that is
    // listening on the mic — NOT a separate REST endpoint. The REST path is for
    // when voice is OFF.
    const liveActive = voiceBridgeRef.current?.snapshot().active ?? false
    if (liveActive) {
      const sent = voiceBridgeRef.current?.sendUserText(text)
      if (sent) {
        // Add the user turn to the transcript so it appears in the right panel
        setMessages((c) => [
          ...c,
          { id: Date.now(), role: 'user', text, ts: new Date().toISOString(), source: 'shell' }
        ])
        // Arm the live-reply watcher: the next stable last_output will be
        // mirrored into the transcript as JARVIS's response to this typed turn
        expectingLiveReplyRef.current = true
        return
      }
      // If sendUserText failed (socket just closed), fall through to REST
    }

    // ── Route: REST /api/chat when voice is off ───────────────────────────────
    setBusy(true)
    try {
      const result = await fetchJson<ChatResponse>(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, approve_desktop: approveDesktop })
      })
      setStatus(result.status ?? status)
      // Protect against backend returning null reply (e.g. unrecognised input)
      const messages = result.messages ?? []
      if (messages.length === 0 && result.reply) {
        messages.push({ id: Date.now(), role: 'jarvis', text: result.reply, ts: new Date().toISOString() })
      }
      setMessages((c) => mergeBackendWithShellMessages(messages, c))
      await refreshAll(false)
    } catch (err) {
      setPrompt(text)
      setError(err instanceof Error ? err.message : String(err))
    } finally { setBusy(false) }
  }

  async function startGeminiVoice(cs?: JarvisShellSnapshot | null) {
    setError('')
    appendShellSystemMessage('Voice core start requested.')
    try {
      const sk = await window.desktopApi?.secureGetKeys?.()
      if (!sk) { appendShellSystemMessage('Desktop API unavailable.'); return }
      voiceBridgeRef.current?.setMute(false)
      const ctx = [
        '[JARVIS_CONTEXT] Initial shell session context. Do not answer this update directly.',
        `Provider: ${formatProvider(statusRef.current?.provider)}`,
        `Mode: ${statusRef.current?.mode || cs?.config.mode || 'GENERAL'}`,
        `Backend: ${backendStateRef.current}`,
        `Current task: ${cs?.tasks?.[0] ? extractTaskSummary(cs.tasks[0]) : 'NONE'}`
      ].join('\n')
      await voiceBridgeRef.current?.start({
        apiKey: sk.geminiKey,
        model: cs?.config.geminiLiveModel || snapshot?.config.geminiLiveModel || sk.liveModel,
        voiceName: cs?.config.geminiVoiceName || snapshot?.config.geminiVoiceName || sk.voiceName,
        ambientContext: ctx
      })
      appendShellSystemMessage('Gemini Live session established.')
      setVoiceStatus({ ...(voiceBridgeRef.current?.snapshot() ?? createRendererVoiceSnapshot()), engine: SHELL_VOICE_ENGINE, source: 'renderer' })
    } catch (err) {
      appendShellSystemMessage(`Voice core failed: ${err instanceof Error ? err.message : String(err)}`)
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function toggleVoice() {
    appendShellSystemMessage('Voice control clicked.')
    if (voiceStatus?.active || voiceStatus?.connecting) {
      voiceBridgeRef.current?.stopVision()
      setVisionSource('none')
      await voiceBridgeRef.current?.stop()
      appendShellSystemMessage('Voice core disengaged.')
      setVoiceStatus({
        ...(voiceBridgeRef.current?.snapshot() ?? createRendererVoiceSnapshot()),
        loaded: true, active: false, connecting: false, engine: SHELL_VOICE_ENGINE,
        live_session: false, wake_word_active: false, mic_muted: Boolean(voiceStatus?.mic_muted),
        last_input: voiceStatus?.last_input, last_output: voiceStatus?.last_output, error: '', source: 'renderer'
      })
    } else {
      await startGeminiVoice()
    }
  }

  function toggleMic() {
    if (!voiceStatus?.active && !voiceStatus?.connecting) {
      appendShellSystemMessage('Voice core is offline. Start it first.')
      return
    }
    const next = !Boolean(voiceStatus?.mic_muted)
    voiceBridgeRef.current?.setMute(next)
    appendShellSystemMessage(next ? 'Microphone muted.' : 'Microphone live.')
  }

  async function toggleVision() {
    const bridge = voiceBridgeRef.current
    if (!bridge) return
    if (!voiceStatus?.active && !voiceStatus?.connecting) {
      appendShellSystemMessage('Voice core is offline. Start it first.')
      return
    }
    try {
      if (visionSource === 'none') setShowVisionSourceModal(true)
      else {
        bridge.stopVision()
        setVisionSource('none')
        setShowVisionSourceModal(false)
        appendShellSystemMessage('Vision feed disabled.')
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      appendShellSystemMessage(`Vision failed: ${msg}`)
    }
  }

  async function startVision(mode: Exclude<VisionSource, 'none'>) {
    const bridge = voiceBridgeRef.current
    if (!bridge) return
    try {
      const label = mode === 'camera' ? 'Camera' : 'Screen'
      appendShellSystemMessage(`${label} vision requested.`)
      await bridge.setVisionSource(mode)
      setVisionSource(mode)
      setShowVisionSourceModal(false)
      appendShellSystemMessage(`${label} vision live.`)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      setShowVisionSourceModal(false)
      appendShellSystemMessage(`Vision failed: ${msg}`)
    }
  }

  async function saveSettings(payload: { operatorName?: string; provider?: string; model?: string; voiceEngine?: string; personality?: string; voiceProfile?: string }) {
    await window.desktopApi?.saveSettings?.(payload)
    await refreshAll(false)
  }

  // ─── Navigation ───

  const navItems = [
    { id: 'dashboard', label: 'DASHBOARD', icon: RiLayoutGridLine },
    { id: 'macros', label: 'MACROS', icon: RiCommandLine },
    { id: 'notes', label: 'NOTES', icon: RiStickyNoteLine },
    { id: 'gallery', label: 'GALLERY', icon: RiFolderImageLine },
    { id: 'phone', label: 'PHONE', icon: RiPhoneLine },
    { id: 'settings', label: 'SETTINGS', icon: RiSettings4Line }
  ] as const satisfies Array<{ id: ShellTab; label: string; icon: typeof RiLayoutGridLine }>

  const currentTask = snapshot?.tasks?.[0] ? extractTaskSummary(snapshot.tasks[0]) : 'NONE'
  const lastTranscript = voiceStatus?.last_output || voiceStatus?.last_input || ''

  // ─── Page transition config ───
  const viewTransition = { duration: 0.35, ease: [0.22, 1, 0.36, 1] as const }
  const viewInitial = { opacity: 0, y: 16, scale: 0.98 }
  const viewAnimate = { opacity: 1, y: 0, scale: 1 }
  const viewExit = { opacity: 0, y: -12, scale: 0.98 }
  const dashInitial = { opacity: 0, scale: 0.97, filter: 'blur(6px)' }
  const dashAnimate = { opacity: 1, scale: 1, filter: 'blur(0px)' }
  const dashExit = { opacity: 0, scale: 0.97, filter: 'blur(6px)' }

  // ─── LOCK SCREEN ───
  if (locked) return <LockScreen onUnlock={() => setLocked(false)} />

  // ─── MINI OVERLAY MODE (Ctrl+Shift+I) ───
  if (overlayMode) {
    return (
      <AnimatePresence>
        <MiniOverlay
          voiceActive={Boolean(voiceStatus?.active)}
          voiceConnecting={Boolean(voiceStatus?.connecting)}
          micMuted={Boolean(voiceStatus?.mic_muted)}
          visionActive={visionSource !== 'none'}
          lastTranscript={lastTranscript}
          onToggleVoice={() => void toggleVoice()}
          onToggleMic={toggleMic}
          onToggleVision={() => void toggleVision()}
          onExpand={() => setOverlayMode(false)}
        />
      </AnimatePresence>
    )
  }

  // ─── FULL SHELL ───
  return (
    <div className="h-screen w-screen overflow-hidden bg-black text-zinc-100">
      <Titlebar maximized={maximized} onToggleMax={() => setMaximized((v) => !v)} title="JARVIS OS // SYSTEM" />

      <div className="flex h-[calc(100vh-32px)] flex-col overflow-hidden">
        {/* Header nav */}
        <div className="flex h-14 items-center justify-between border-b border-white/5 bg-zinc-950/80 px-6 backdrop-blur-md">
          <div className="hidden items-center gap-3 lg:flex">
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/8 p-2">
              <RiShieldKeyholeLine className="text-emerald-400" size={20} />
            </div>
            <div className="leading-none">
              <div className="text-sm font-black tracking-[0.22em] text-zinc-100">JARVIS AI</div>
              <div className="mt-1 text-[10px] font-mono tracking-[0.22em] text-emerald-500/70">NEURAL INTERFACE</div>
            </div>
          </div>

          <div className="flex gap-2 rounded-xl border border-white/5 bg-black/40 p-1">
            {navItems.map((item) => {
              const Icon = item.icon
              return (
                <button key={item.id} onClick={() => setActiveTab(item.id)}
                  className={`flex items-center gap-2 rounded-lg px-5 py-2 text-[10px] font-bold tracking-[0.18em] transition-all ${
                    activeTab === item.id
                      ? 'border border-emerald-500/20 bg-emerald-500/20 text-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.08)]'
                      : 'text-zinc-500 hover:bg-white/5 hover:text-zinc-200'
                  }`}
                >
                  <Icon size={14} /> {item.label}
                </button>
              )
            })}
          </div>

          <div className="flex items-center gap-6 text-[10px] font-mono font-bold">
            <div className="flex items-center gap-2 text-emerald-500">
              <RiWifiLine />
              <span>{backendState === 'OFFLINE' ? 'DISCONNECTED' : 'LINKED'}</span>
            </div>
            <div className="hidden items-center gap-2 text-zinc-400 md:flex">
              <RiCheckboxCircleFill />
              <span>{status?.provider?.local ? 'LOCAL' : 'REMOTE'}</span>
            </div>
            <div className="rounded-md bg-zinc-800 px-3 py-2 text-zinc-300">{clock.toLocaleTimeString()}</div>
          </div>
        </div>

        {/* Content — IRIS-style radial gradient bg */}
        <div className="flex-1 overflow-hidden bg-[radial-gradient(circle_at_center,rgba(13,92,74,0.06),transparent_60%)]">
          <AnimatePresence mode="wait">
            {activeTab === 'dashboard' ? (
              <motion.div key="dashboard" initial={dashInitial} animate={dashAnimate} exit={dashExit} transition={viewTransition} className="h-full">
                <DashboardView
                  status={status} voice={voiceStatus} backendState={backendState}
                  messages={messages} prompt={prompt} setPrompt={setPrompt}
                  approveDesktop={approveDesktop} setApproveDesktop={setApproveDesktop}
                  busy={busy} visionSource={visionSource}
                  dashboardVisionSource={dashboardVisionSource}
                  systemStats={systemStats} audioLevel={audioLevel}
                  onSend={() => void sendPrompt()} onRefresh={() => void refreshAll()}
                  onToggleVision={() => void toggleVision()}
                  onToggleVoice={() => void toggleVoice()}
                  onToggleMic={() => toggleMic()}
                  onSetDashboardVision={setDashboardVisionSource}
                />
              </motion.div>
            ) : null}
            <Suspense fallback={<ViewSkeleton />}>
              {activeTab === 'macros' ? (
                <motion.div key="macros" initial={viewInitial} animate={viewAnimate} exit={viewExit} transition={viewTransition} className="h-full"><MacrosView /></motion.div>
              ) : null}
              {activeTab === 'notes' ? (
                <motion.div key="notes" initial={viewInitial} animate={viewAnimate} exit={viewExit} transition={viewTransition} className="h-full"><NotesView /></motion.div>
              ) : null}
              {activeTab === 'gallery' ? (
                <motion.div key="gallery" initial={viewInitial} animate={viewAnimate} exit={viewExit} transition={viewTransition} className="h-full"><GalleryView images={snapshot?.gallery ?? []} /></motion.div>
              ) : null}
              {activeTab === 'phone' ? (
                <motion.div key="phone" initial={viewInitial} animate={viewAnimate} exit={viewExit} transition={viewTransition} className="h-full"><PhoneView backendState={backendState} /></motion.div>
              ) : null}
              {activeTab === 'settings' ? (
                <motion.div key="settings" initial={viewInitial} animate={viewAnimate} exit={viewExit} transition={viewTransition} className="h-full"><SettingsView snapshot={snapshot} onSave={saveSettings} /></motion.div>
              ) : null}
            </Suspense>
          </AnimatePresence>
        </div>

        {/* Bottom status bar */}
        {activeTab !== 'dashboard' ? (
          <div className="border-t border-white/5 bg-zinc-950/80 px-6 py-3 text-[11px] font-mono tracking-[0.18em] text-zinc-500">
            PROVIDER: {formatProvider(status?.provider)} // CURRENT TASK: {currentTask}
          </div>
        ) : null}

        {/* Vision source modal */}
        {showVisionSourceModal && activeTab === 'dashboard' ? (
          <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/80 backdrop-blur-sm">
            <div className="iris-panel w-full max-w-md p-2 shadow-[0_24px_120px_rgba(0,0,0,0.65)]">
              <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
                <span className="text-xs font-black tracking-[0.22em] text-emerald-400">ESTABLISH UPLINK</span>
                <button type="button" onClick={() => setShowVisionSourceModal(false)} className="rounded-lg p-2 text-zinc-500 transition-colors hover:bg-white/5 hover:text-white">×</button>
              </div>
              <div className="grid grid-cols-2 gap-4 p-5">
                <button data-testid="vision-camera-source" type="button" onClick={() => void startVision('camera')}
                  className="group flex flex-col items-center justify-center gap-3 rounded-2xl border border-white/10 bg-black/40 p-6 transition-all hover:border-emerald-500/40 hover:bg-emerald-500/10">
                  <div className="rounded-full bg-zinc-900 p-3 text-zinc-400 transition-colors group-hover:bg-emerald-500 group-hover:text-black"><RiCameraLine size={26} /></div>
                  <span className="text-[10px] font-black tracking-[0.22em] text-zinc-300 group-hover:text-emerald-300">CAMERA FEED</span>
                </button>
                <button data-testid="vision-screen-source" type="button" onClick={() => void startVision('screen')}
                  className="group flex flex-col items-center justify-center gap-3 rounded-2xl border border-white/10 bg-black/40 p-6 transition-all hover:border-emerald-500/40 hover:bg-emerald-500/10">
                  <div className="rounded-full bg-zinc-900 p-3 text-zinc-400 transition-colors group-hover:bg-emerald-500 group-hover:text-black"><RiComputerLine size={26} /></div>
                  <span className="text-[10px] font-black tracking-[0.22em] text-zinc-300 group-hover:text-emerald-300">SCREEN SHARE</span>
                </button>
              </div>
              <div className="border-t border-white/5 px-5 py-4 text-center text-[10px] font-mono tracking-[0.18em] text-zinc-500">SELECT INPUT SOURCE FOR NEURAL PROCESSING</div>
            </div>
          </div>
        ) : null}

        {/* Error toast */}
        {error ? (
          <div className="absolute bottom-5 left-1/2 z-50 -translate-x-1/2 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200 shadow-[0_10px_35px_rgba(0,0,0,0.35)]">{error}</div>
        ) : null}
      </div>

      {/* IRIS-style floating widgets */}
      <WidgetLayer />
      <WidgetToolbar />
    </div>
  )
}
