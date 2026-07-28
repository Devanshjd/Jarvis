import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  RiCameraLine,
  RiCheckboxCircleFill,
  RiCodeSSlashLine,
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
  ActivityStatus,
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
  IDLE_ACTIVITY,
  SHELL_VOICE_ENGINE,
  createRendererVoiceSnapshot,
  extractTaskSummary,
  fetchJson,
  formatProvider,
  mergeBackendWithShellMessages,
  resolveOrbActivity,
  setApiToken
} from './lib/types'
import { blobToWavBase64 } from './services/audioUtils'

// ─── Views (Dashboard loads eagerly, others lazy for faster boot) ───
import DashboardView from './views/DashboardView'
const MacrosView = lazy(() => import('./views/MacrosView'))
const NotesView = lazy(() => import('./views/NotesView'))
const GalleryView = lazy(() => import('./views/GalleryView'))
const OracleView = lazy(() => import('./views/OracleView'))
const PhoneView = lazy(() => import('./views/PhoneView'))
const SettingsView = lazy(() => import('./views/SettingsView'))

/* ═══════════════════════════════════════════
   Root App — shell state, routing, voice bridge
   ═══════════════════════════════════════════ */

export default function App() {
  const [locked, setLocked] = useState(true)
  const [activeTab, setActiveTab] = useState<ShellTab>('dashboard')
  const [status, setStatus] = useState<RuntimeStatus | null>(null)
  const [activity, setActivity] = useState<ActivityStatus>(IDLE_ACTIVITY)
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [snapshot, setSnapshot] = useState<JarvisShellSnapshot | null>(null)
  const [prompt, setPrompt] = useState('')
  const [approveDesktop, setApproveDesktop] = useState(false)
  const [busy, setBusy] = useState(false)
  const [localVoiceState, setLocalVoiceState] = useState<'idle' | 'recording' | 'thinking'>('idle')
  const localRecorderRef = useRef<MediaRecorder | null>(null)
  const localChunksRef = useRef<Blob[]>([])
  const [backendState, setBackendState] = useState('OFFLINE')
  const [maximized, setMaximized] = useState(false)
  const [error, setError] = useState('')
  const [clock, setClock] = useState(() => new Date())
  const [visionSource, setVisionSource] = useState<VisionSource>('none')
  const [crewReady, setCrewReady] = useState(0)
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
  // Refs so the gesture poller reads current state without stale closures.
  const activeTabRef = useRef<ShellTab>('dashboard')
  const voiceActiveRef = useRef(false)
  const gestureTsRef = useRef<number>(-1)

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
      setActivity(nextStatus.activity ?? IDLE_ACTIVITY)
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

  // Activity changes can be brief (for example a fast local tool call), so
  // poll the small truthful activity contract more often than chat history.
  useEffect(() => {
    let alive = true
    let inFlight = false
    const poll = async (): Promise<void> => {
      if (inFlight) return
      inFlight = true
      try {
        const next = await fetchJson<Pick<RuntimeStatus, 'activity'>>(`${API_BASE}/api/status`)
        if (alive) setActivity(next.activity ?? IDLE_ACTIVITY)
      } catch {
        // Keep the last honest state when the backend is briefly restarting.
      } finally {
        inFlight = false
      }
    }
    void poll()
    const id = window.setInterval(() => void poll(), 500)
    return () => { alive = false; window.clearInterval(id) }
  }, [])

  // Multi-agent crew readiness (isolated, non-critical polling)
  useEffect(() => {
    let alive = true
    const load = (): void => {
      fetchJson<{ agents?: Record<string, { bound?: boolean }> }>(`${API_BASE}/api/team/status`)
        .then((d) => { if (alive) setCrewReady(Object.values(d.agents ?? {}).filter((a) => a.bound).length) })
        .catch(() => { /* team endpoint optional */ })
    }
    load()
    const id = setInterval(load, 15000)
    return () => { alive = false; clearInterval(id) }
  }, [])

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

  // When a reminder fires, log it and speak it aloud via local TTS.
  useEffect(() => {
    window.desktopApi.onReminderFired?.((text: string) => {
      setMessages((c) => [...c, { id: Date.now(), role: 'system', text: `⏰ Reminder: ${text}`, ts: new Date().toISOString(), source: 'shell' }])
      void fetch(`${API_BASE}/api/tts/speak`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: `Reminder: ${text}`, play: true })
      }).catch(() => {})
    })
  }, [])

  // Fully-local voice: click to record, click to stop → Whisper→Ollama→Piper
  // on the backend, all offline. Turn-based; no Gemini, no cloud, no API cap.
  async function handleLocalVoice() {
    // If recording, stop → process.
    if (localVoiceState === 'recording') {
      localRecorderRef.current?.stop()
      return
    }
    if (localVoiceState === 'thinking') return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const rec = new MediaRecorder(stream)
      localChunksRef.current = []
      rec.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) localChunksRef.current.push(e.data)
      }
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        setLocalVoiceState('thinking')
        try {
          const blob = new Blob(localChunksRef.current, { type: 'audio/webm' })
          const wavB64 = await blobToWavBase64(blob)
          const r = await fetchJson<{
            success: boolean; transcript?: string; reply?: string
            reply_audio_base64?: string; error?: string
          }>(`${API_BASE}/api/voice/local`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ audio_base64: wavB64, speak: true })
          })
          if (r?.transcript) {
            setMessages((c) => [...c, { id: Date.now(), role: 'user', text: r.transcript!, ts: new Date().toISOString(), source: 'shell' }])
          }
          if (r?.reply) {
            setMessages((c) => [...c, { id: Date.now() + 1, role: 'assistant', text: r.reply!, ts: new Date().toISOString(), source: 'shell' }])
          }
          if (!r?.success && r?.error) appendShellSystemMessage(`Local voice: ${r.error}`)
          // Reply audio is already played host-side by the backend (winsound).
        } catch (err) {
          appendShellSystemMessage(`Local voice failed: ${err instanceof Error ? err.message : String(err)}`)
        } finally {
          setLocalVoiceState('idle')
        }
      }
      localRecorderRef.current = rec
      rec.start()
      setLocalVoiceState('recording')
    } catch (err) {
      appendShellSystemMessage(`Mic error: ${err instanceof Error ? err.message : String(err)}`)
      setLocalVoiceState('idle')
    }
  }

  // Load the backend's shared-secret token ASAP so protected API calls
  // (agent/execute, self-modify) authenticate. Must run before those calls.
  useEffect(() => {
    window.desktopApi.getApiToken?.().then((t) => setApiToken(t || '')).catch(() => {})
  }, [])

  // Keep refs current for the gesture poller.
  useEffect(() => { activeTabRef.current = activeTab }, [activeTab])
  useEffect(() => { voiceActiveRef.current = Boolean(voiceStatus?.active || voiceStatus?.connecting) }, [voiceStatus])

  // Poll the backend for the latest hand gesture and drive real UI actions:
  //   open palm → start the voice core
  //   peace     → switch to the next view
  // (Backend already speaks a confirmation; this adds the actual control.)
  useEffect(() => {
    const TAB_ORDER: ShellTab[] = ['dashboard', 'macros', 'notes', 'gallery', 'oracle', 'phone', 'settings']
    const iv = setInterval(async () => {
      try {
        const r = await fetchJson<{ gesture: string | null; ts: number }>(`${API_BASE}/api/gesture/last`)
        if (!r?.gesture || !r.ts) return
        if (gestureTsRef.current < 0) { gestureTsRef.current = r.ts; return }  // baseline on load
        if (r.ts <= gestureTsRef.current) return
        gestureTsRef.current = r.ts
        if (Date.now() / 1000 - r.ts > 4) return                               // ignore stale
        if (r.gesture === 'open_palm') {
          if (!voiceActiveRef.current) void startGeminiVoice()
        } else if (r.gesture === 'peace') {
          const idx = TAB_ORDER.indexOf(activeTabRef.current)
          setActiveTab(TAB_ORDER[(idx + 1) % TAB_ORDER.length])
        }
      } catch {
        /* backend may be momentarily unavailable */
      }
    }, 500)
    return () => clearInterval(iv)
  }, [])

  // ─── Actions ───

  function appendShellSystemMessage(text: string) {
    setMessages((c) => [...c, { id: Date.now(), role: 'system', text, ts: new Date().toISOString(), source: 'shell' }])
  }

  // When the dashboard camera turns on, ask the backend to run Face ID and
  // greet the owner if recognised (cooldown-guarded server-side). Speaks
  // aloud via local Piper TTS and logs the greeting to the transcript.
  function handleSetDashboardVision(next: 'none' | 'camera' | 'screen') {
    setDashboardVisionSource(next)
    if (next === 'none' && visionSource === 'camera') {
      // Camera turned off from the dashboard → also blind the voice (it was
      // borrowing the dashboard stream, which is about to stop).
      voiceBridgeRef.current?.stopVision()
      setVisionSource('none')
    }
  }

  // Fires when the dashboard optical feed's camera stream is ready. The
  // dashboard is the SINGLE owner of the webcam — everything else borrows
  // this one stream instead of opening its own (which caused the Windows
  // "camera in use" black-screen conflict).
  function handleCameraStreamReady(stream: MediaStream | null) {
    if (!stream) return

    // 1) Face ID greeting — grab ONE frame from the shared stream and send it
    //    to the backend (backend never touches the camera).
    try {
      const track = stream.getVideoTracks()[0]
      const video = document.createElement('video')
      video.muted = true
      video.playsInline = true
      video.srcObject = stream
      void video.play().then(() => {
        setTimeout(() => {
          try {
            const canvas = document.createElement('canvas')
            canvas.width = 640
            canvas.height = 480
            const ctx = canvas.getContext('2d')
            if (!ctx || !track) return
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
            const b64 = canvas.toDataURL('image/jpeg', 0.7)
            void fetchJson<{ greeted: boolean; text?: string }>(
              `${API_BASE}/api/faceid/greet_frame`,
              {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image_base64: b64, speak: true })
              }
            )
              .then((r) => {
                if (r?.greeted && r.text) appendShellSystemMessage(r.text)
              })
              .catch(() => {})
          } catch {
            /* greeting is best-effort */
          }
        }, 600) // let the sensor expose a real (non-black) frame first
      })
    } catch {
      /* ignore */
    }

    // 2) Give the LIVE VOICE eyes by REUSING this same stream — no second
    //    getUserMedia, so no camera conflict.
    if (voiceStatus?.active || voiceStatus?.connecting) {
      voiceBridgeRef.current?.attachVisionStream(stream)
      setVisionSource('camera')
    }
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
    { id: 'oracle', label: 'ORACLE', icon: RiCodeSSlashLine },
    { id: 'phone', label: 'PHONE', icon: RiPhoneLine },
    { id: 'settings', label: 'SETTINGS', icon: RiSettings4Line }
  ] as const satisfies Array<{ id: ShellTab; label: string; icon: typeof RiLayoutGridLine }>

  const currentTask = snapshot?.tasks?.[0] ? extractTaskSummary(snapshot.tasks[0]) : 'NONE'
  const lastTranscript = voiceStatus?.last_output || voiceStatus?.last_input || ''
  const orbActivity = resolveOrbActivity(activity, voiceStatus, localVoiceState, busy)

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
      <Titlebar maximized={maximized} onToggleMax={() => setMaximized((v) => !v)} title="STORMBREAKER // TACTICAL AI" />

      <div className="flex h-[calc(100vh-32px)] overflow-hidden">
        {/* ─── LEFT COMMAND RAIL — vertical nav ─── */}
        <nav className="flex w-[78px] flex-col items-center gap-1 border-r border-white/5 bg-zinc-950/80 py-4 backdrop-blur-md">
          <div className="mb-4 rounded-xl border border-amber-500/25 bg-amber-500/10 p-2 shadow-[0_0_18px_rgba(255,176,32,0.12)]">
            <RiShieldKeyholeLine className="text-amber-400" size={22} />
          </div>
          {navItems.map((item) => {
            const Icon = item.icon
            const active = activeTab === item.id
            return (
              <button key={item.id} onClick={() => setActiveTab(item.id)} title={item.label}
                className={`group relative flex w-full flex-col items-center gap-1 py-2.5 transition-all ${
                  active ? 'text-amber-400' : 'text-zinc-500 hover:text-zinc-200'
                }`}
              >
                <span className={`absolute left-0 top-1/2 h-9 w-[3px] -translate-y-1/2 rounded-r-full transition-all ${active ? 'bg-amber-400 shadow-[0_0_12px_rgba(255,176,32,0.6)]' : 'bg-transparent'}`} />
                <span className={`flex h-11 w-11 items-center justify-center rounded-xl transition-all ${active ? 'border border-amber-500/25 bg-amber-500/15 shadow-[0_0_15px_rgba(255,176,32,0.1)]' : 'group-hover:bg-white/5'}`}>
                  <Icon size={19} />
                </span>
                <span className="text-[8px] font-bold tracking-[0.1em]">{item.label}</span>
              </button>
            )
          })}
        </nav>

        {/* ─── MIDDLE COLUMN — brand bar + content ─── */}
        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="flex h-14 items-center justify-between border-b border-white/5 bg-zinc-950/50 px-6 backdrop-blur-md">
            <div className="leading-none">
              <div className="text-sm font-black tracking-[0.3em] text-zinc-100">STORMBREAKER</div>
              <div className="mt-1 text-[10px] font-mono tracking-[0.24em] text-amber-500/70">JARVIS TACTICAL CORE</div>
            </div>
            <div className="flex items-center gap-3 text-[10px] font-mono tracking-[0.22em] text-zinc-600">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-500/60" />
              {activeTab.toUpperCase()}
            </div>
          </div>

        {/* Content — Stormbreaker-style radial gradient bg */}
        <div className="flex-1 overflow-hidden bg-[radial-gradient(circle_at_center,rgba(255,176,32,0.05),transparent_60%)]">
          <AnimatePresence mode="wait">
            {activeTab === 'dashboard' ? (
              <motion.div key="dashboard" initial={dashInitial} animate={dashAnimate} exit={dashExit} transition={viewTransition} className="h-full">
                <DashboardView
                  status={status} voice={voiceStatus} backendState={backendState}
                  messages={messages} prompt={prompt} setPrompt={setPrompt}
                  approveDesktop={approveDesktop} setApproveDesktop={setApproveDesktop}
                  busy={busy} visionSource={visionSource}
                  dashboardVisionSource={dashboardVisionSource}
                  systemStats={systemStats} audioLevel={audioLevel} activity={orbActivity}
                  onSend={() => void sendPrompt()} onRefresh={() => void refreshAll()}
                  onToggleVision={() => void toggleVision()}
                  onToggleVoice={() => void toggleVoice()}
                  onToggleMic={() => toggleMic()}
                  onSetDashboardVision={handleSetDashboardVision}
                  onCameraStreamReady={handleCameraStreamReady}
                  onLocalVoice={() => void handleLocalVoice()}
                  localVoiceState={localVoiceState}
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
              {activeTab === 'oracle' ? (
                <motion.div key="oracle" initial={viewInitial} animate={viewAnimate} exit={viewExit} transition={viewTransition} className="h-full"><OracleView /></motion.div>
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
              PROVIDER: {formatProvider(status?.provider)} // CREW: {crewReady} SPECIALISTS // CURRENT TASK: {currentTask}
            </div>
          ) : null}
        </div>
        {/* ─── close MIDDLE COLUMN ─── */}

        {/* ─── RIGHT UTILITY RAIL — live status ─── */}
        <aside className="flex w-[74px] flex-col items-center gap-5 border-l border-white/5 bg-zinc-950/80 py-5 backdrop-blur-md">
          <div className={`flex flex-col items-center gap-1.5 ${backendState === 'OFFLINE' ? 'text-red-400' : 'text-amber-400'}`}>
            <RiWifiLine size={18} />
            <span className="text-[8px] font-bold tracking-[0.1em]">{backendState === 'OFFLINE' ? 'OFFLINE' : 'LINKED'}</span>
          </div>
          <div className="flex flex-col items-center gap-1.5 text-zinc-400">
            <RiCheckboxCircleFill size={16} />
            <span className="text-[8px] font-bold tracking-[0.1em]">{status?.provider?.local ? 'LOCAL' : 'REMOTE'}</span>
          </div>
          <div className="h-px w-8 bg-white/10" />
          <div className="mt-auto flex flex-col items-center gap-0.5 text-zinc-300">
            <span className="text-[11px] font-mono tabular-nums">{clock.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
            <span className="text-[8px] font-mono tracking-[0.1em] text-zinc-600">LOCAL TIME</span>
          </div>
        </aside>

        {/* Vision source modal */}
        {showVisionSourceModal && activeTab === 'dashboard' ? (
          <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/80 backdrop-blur-sm">
            <div className="sb-panel w-full max-w-md p-2 shadow-[0_24px_120px_rgba(0,0,0,0.65)]">
              <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
                <span className="text-xs font-black tracking-[0.22em] text-amber-400">ESTABLISH LINK</span>
                <button type="button" onClick={() => setShowVisionSourceModal(false)} className="rounded-lg p-2 text-zinc-500 transition-colors hover:bg-white/5 hover:text-white">×</button>
              </div>
              <div className="grid grid-cols-2 gap-4 p-5">
                <button data-testid="vision-camera-source" type="button" onClick={() => void startVision('camera')}
                  className="group flex flex-col items-center justify-center gap-3 rounded-2xl border border-white/10 bg-black/40 p-6 transition-all hover:border-amber-500/40 hover:bg-amber-500/10">
                  <div className="rounded-full bg-zinc-900 p-3 text-zinc-400 transition-colors group-hover:bg-amber-500 group-hover:text-black"><RiCameraLine size={26} /></div>
                  <span className="text-[10px] font-black tracking-[0.22em] text-zinc-300 group-hover:text-amber-300">CAMERA FEED</span>
                </button>
                <button data-testid="vision-screen-source" type="button" onClick={() => void startVision('screen')}
                  className="group flex flex-col items-center justify-center gap-3 rounded-2xl border border-white/10 bg-black/40 p-6 transition-all hover:border-amber-500/40 hover:bg-amber-500/10">
                  <div className="rounded-full bg-zinc-900 p-3 text-zinc-400 transition-colors group-hover:bg-amber-500 group-hover:text-black"><RiComputerLine size={26} /></div>
                  <span className="text-[10px] font-black tracking-[0.22em] text-zinc-300 group-hover:text-amber-300">SCREEN SHARE</span>
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

      {/* Stormbreaker-style floating widgets */}
      <WidgetLayer />
      <WidgetToolbar />
    </div>
  )
}
