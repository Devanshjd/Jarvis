import { useEffect, useRef } from 'react'
import {
  RiCameraLine,
  RiCpuLine,
  RiHardDriveLine,
  RiHistoryLine,
  RiMicLine,
  RiMicOffLine,
  RiPhoneFill,
  RiStopCircleLine,
  RiTempColdLine,
  RiTerminalBoxLine,
  RiTimerLine,
  RiWifiLine
} from 'react-icons/ri'
import Sphere from '../components/Sphere'
import CameraFeed from '../components/CameraFeed'
import MarkdownMessage from '../components/MarkdownMessage'
import type {
  ActivityStatus,
  ChatMessage,
  RuntimeStatus,
  SystemStatsResult,
  VoiceLifecycleState,
  VoiceStopRecord,
  VoiceTiming,
  VoiceStatus
} from '../lib/types'
import { formatRole, shortTime } from '../lib/types'
import type { VisionSource } from '../services/JarvisGeminiLive'

/* ═══════════════════════════════════════════
   Dashboard View — Stormbreaker-style 3-column layout
   ═══════════════════════════════════════════ */

export interface DashboardViewProps {
  status: RuntimeStatus | null
  voice: VoiceStatus | null
  backendState: string
  messages: ChatMessage[]
  prompt: string
  setPrompt: (v: string) => void
  busy: boolean
  visionSource: VisionSource
  dashboardVisionSource: 'none' | 'camera' | 'screen'
  systemStats: SystemStatsResult | null
  audioLevel: number
  activity: ActivityStatus
  stillWorking: boolean
  voiceTiming: VoiceTiming | null
  voiceLifecycle: VoiceLifecycleState
  lastVoiceStop: VoiceStopRecord | null
  waitAvailable: boolean
  onSend: () => void
  onRefresh: () => void
  onToggleVision: () => void
  onToggleVoice: () => void
  onToggleMic: () => void
  onStopVoiceTurn: () => void
  onSetDashboardVision: (s: 'none' | 'camera' | 'screen') => void
  onCameraStreamReady?: (stream: MediaStream | null) => void
  onLocalVoice?: () => void
  localVoiceState?: 'idle' | 'recording' | 'thinking'
}

export default function DashboardView(props: DashboardViewProps) {
  const {
    status, voice, backendState, messages, prompt, setPrompt,
    busy, visionSource,
    dashboardVisionSource, systemStats, audioLevel,
    activity, stillWorking,
    voiceTiming, voiceLifecycle, lastVoiceStop, waitAvailable,
    onSend, onToggleVision, onToggleVoice, onToggleMic, onStopVoiceTurn,
    onSetDashboardVision, onCameraStreamReady, onLocalVoice, localVoiceState = 'idle'
  } = props

  const scrollRef = useRef<HTMLDivElement | null>(null)
  const backendOnline = backendState !== 'OFFLINE' && Boolean(status)
  const voiceLive = Boolean(voice?.active || voice?.connecting || status?.voice_enabled)
  const voiceConnecting = Boolean(voice?.connecting)
  const voiceMuted = Boolean(voice?.mic_muted)
  const voiceError = voice?.error || ''
  const health = status?.health
  const localBrainOffline = Boolean(status?.provider?.local) && (
    status?.provider?.reachable === false || health?.ollama?.reachable === false
  )
  const geminiConfigured = health?.gemini_live?.configured
  // The centre and dashboard optical feed share their real stream state. This
  // prevents a visible camera/screen feed from being labelled "VISION OFF".
  const activeVisionSource = visionSource !== 'none' ? visionSource : dashboardVisionSource
  const visionUnavailable = health?.vision?.available === false
  const readinessText = !backendOnline
    ? 'BACKEND OFFLINE'
    : localBrainOffline
      ? 'LOCAL BRAIN OFFLINE'
      : 'SYSTEM READY'
  const voiceModelText = voiceError
    ? 'VOICE DISCONNECTED'
    : voiceConnecting
      ? 'GEMINI CONNECTING'
      : voiceLive
        ? 'GEMINI LIVE'
        : geminiConfigured === true
          ? 'GEMINI CONFIGURED'
          : geminiConfigured === false
            ? 'GEMINI UNCONFIGURED'
            : 'VOICE STATUS UNKNOWN'
  const backendSpeaking = Boolean(voiceTiming?.speaking)
  const rendererSpeaking = Boolean(voice?.speaking)
  const hostSpeaking = backendSpeaking || (activity.state === 'speaking' && !rendererSpeaking)
  let voiceCoreText: string
  if (hostSpeaking) voiceCoreText = 'PIPER SPEAKING'
  else if (rendererSpeaking) voiceCoreText = 'GEMINI SPEAKING'
  else if (voiceLifecycle === 'thinking') voiceCoreText = 'LOCAL VOICE THINKING'
  else if (voiceLifecycle === 'listening') voiceCoreText = 'VOICE LISTENING'
  else if (voiceLifecycle === 'cancelled') voiceCoreText = `CANCELLED // ${lastVoiceStop?.scope.toUpperCase() ?? 'TURN'}`
  else if (voiceError) voiceCoreText = 'VOICE DISCONNECTED'
  else if (voiceConnecting) voiceCoreText = 'VOICE CORE CONNECTING'
  else if (voiceLive) voiceCoreText = voiceMuted ? 'VOICE CORE MUTED' : 'VOICE CORE LIVE'
  else voiceCoreText = 'VOICE CORE STANDBY'
  const timing = voiceTiming?.last
  const hasVoiceDiagnostics = Boolean(
    timing?.first_audio_ms != null || timing?.total_ms != null || lastVoiceStop
  )
  const stopSummary = lastVoiceStop
    ? lastVoiceStop.scope === 'thinking'
      ? 'LAST WAIT: WHOLE TURN STOPPED'
      : lastVoiceStop.source === 'renderer'
        ? 'LAST WAIT: GEMINI PLAYBACK STOPPED'
        : 'LAST WAIT: PIPER SPEECH STOPPED'
    : null
  const visionText = visionUnavailable
    ? 'VISION UNAVAILABLE'
    : activeVisionSource === 'screen'
      ? 'VISION // SCREEN'
      : activeVisionSource === 'camera'
        ? 'VISION // CAMERA'
        : 'VISION // OFF'

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, stillWorking])

  const activityAgent = activity.active_agent ?? 'JARVIS'
  const activityText = activity.state === 'error'
    ? activity.error || 'JARVIS ENCOUNTERED AN ERROR'
    : activity.label || (activity.state === 'idle' ? readinessText : activity.state.replace('_', ' ').toUpperCase())
  const activityColor = activity.state === 'error' || !backendOnline || localBrainOffline
    ? 'border-red-500/35 text-red-300'
    : activity.state === 'tool_running' && activity.active_agent === 'ULTRON'
      ? 'border-red-400/35 text-red-300'
      : activity.state === 'tool_running' && activity.active_agent === 'FRIDAY'
        ? 'border-cyan-400/35 text-cyan-300'
        : activity.state === 'tool_running' && activity.active_agent === 'VISION'
          ? 'border-violet-400/35 text-violet-300'
          : activity.state === 'tool_running' && activity.active_agent === 'EDITH'
            ? 'border-emerald-400/35 text-emerald-300'
            : 'border-amber-500/20 text-zinc-400'

  return (
    <div className="grid h-full min-h-0 grid-cols-12 gap-4 overflow-hidden px-4 py-4">
      {/* ─── LEFT PANEL ─── */}
      <div className="col-span-3 hidden h-full min-h-0 flex-col gap-4 lg:flex">
        {/* Camera / Screen Feed — Stormbreaker optical feed */}
        <div className="sb-panel relative h-72 overflow-hidden p-2">
          <CameraFeed source={dashboardVisionSource} onStreamReady={onCameraStreamReady} />
          {/* Feed source selector */}
          {dashboardVisionSource === 'none' && (
            <div className="absolute bottom-3 inset-x-3 flex gap-2">
              <button onClick={() => onSetDashboardVision('camera')} className="flex-1 rounded-lg border border-zinc-800 bg-zinc-950/80 py-2 text-[9px] font-bold tracking-[0.2em] text-zinc-400 transition-colors hover:border-amber-500/30 hover:text-amber-400">
                CAMERA
              </button>
              <button onClick={() => onSetDashboardVision('screen')} className="flex-1 rounded-lg border border-zinc-800 bg-zinc-950/80 py-2 text-[9px] font-bold tracking-[0.2em] text-zinc-400 transition-colors hover:border-amber-500/30 hover:text-amber-400">
                SCREEN
              </button>
            </div>
          )}
          {dashboardVisionSource !== 'none' && (
            <button onClick={() => onSetDashboardVision('none')} className="absolute bottom-3 right-3 rounded-lg border border-zinc-800 bg-zinc-950/80 px-3 py-1.5 text-[9px] font-bold tracking-[0.16em] text-red-400 transition-colors hover:border-red-500/30">
              STOP
            </button>
          )}
        </div>

        {/* Neural Uplink */}
        <div className="sb-panel p-4">
          <div className="mb-3 flex items-center justify-between border-b border-white/10 pb-3">
            <span className="sb-label">NEURAL UPLINK</span>
            <span className={`text-[10px] font-mono tracking-[0.2em] ${backendOnline ? 'text-amber-400' : 'text-red-400'}`}>
              {backendOnline ? 'LINKED' : 'OFFLINE'}
            </span>
          </div>
          <div className="flex items-end justify-between">
            <div>
              <div className="text-[10px] font-mono tracking-[0.2em] text-zinc-600">HOST NODE</div>
              <div className={`mt-2 flex items-center gap-2 text-sm font-black ${localBrainOffline || !backendOnline ? 'text-red-300' : 'text-white'}`}>
                <RiWifiLine className={localBrainOffline || !backendOnline ? 'text-red-400' : 'text-amber-400'} />
                {localBrainOffline ? 'LOCAL BRAIN OFFLINE' : status?.provider?.local ? 'LOCAL' : status ? 'REMOTE' : 'CHECKING'}
              </div>
            </div>
            <div className="text-right">
              <div className="text-[10px] font-mono tracking-[0.2em] text-zinc-600">VOICE MODEL</div>
              <div className={`mt-2 text-sm font-black ${voiceError ? 'text-red-300' : 'text-white'}`}>
                {voiceModelText}
              </div>
            </div>
          </div>
        </div>

        {/* Core Metrics — Stormbreaker-style real system stats */}
        <div className="sb-panel flex-1 p-4">
          <div className="mb-4 border-b border-white/10 pb-3">
            <span className="sb-label">CORE METRICS</span>
          </div>
          <div className="grid h-[calc(100%-2rem)] grid-cols-2 gap-3">
            <div className="sb-metric-card flex flex-col justify-between">
              <div className="flex items-center justify-between text-zinc-500">
                <RiCpuLine size={16} />
                <span className="text-[8px] font-mono tracking-[0.2em]">CPU LOAD</span>
              </div>
              <div className="mt-auto text-right text-lg font-black text-amber-400">
                {systemStats ? `${systemStats.cpuLoad}%` : '--'}
              </div>
            </div>
            <div className="sb-metric-card flex flex-col justify-between">
              <div className="flex items-center justify-between text-zinc-500">
                <RiHardDriveLine size={16} />
                <span className="text-[8px] font-mono tracking-[0.2em]">RAM</span>
              </div>
              <div className="mt-auto text-right text-lg font-black text-amber-400">
                {systemStats ? `${systemStats.ramPercent}%` : '--'}
              </div>
            </div>
            <div className="sb-metric-card flex flex-col justify-between">
              <div className="flex items-center justify-between text-zinc-500">
                <RiTempColdLine size={16} />
                <span className="text-[8px] font-mono tracking-[0.2em]">TEMP</span>
              </div>
              <div className="mt-auto text-right text-lg font-black text-amber-400">
                {systemStats?.temperature != null ? `${systemStats.temperature}°` : '--'}
              </div>
            </div>
            <div className="sb-metric-card flex flex-col justify-between">
              <div className="flex items-center justify-between text-zinc-500">
                <RiTimerLine size={16} />
                <span className="text-[8px] font-mono tracking-[0.2em]">UPTIME</span>
              </div>
              <div className="mt-auto text-right text-lg font-black text-amber-400">
                {systemStats?.uptime ?? '--'}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ─── CENTER PANEL — Sphere + Controls ─── */}
      <div className="relative col-span-12 flex h-full min-h-0 flex-col items-center justify-center overflow-hidden lg:col-span-6">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(13,92,74,0.14),transparent_58%)]" />

        {/* Status badge */}
        <div className="pointer-events-none absolute inset-x-0 top-8 flex justify-center">
          <div className="rounded-full border border-amber-500/20 bg-black/40 px-4 py-1.5 text-[10px] font-mono tracking-[0.34em] text-zinc-500 backdrop-blur-md">
            {status?.waiting_for_input && activity.state !== 'error' && !localBrainOffline ? 'AWAITING INPUT' : activityText.toUpperCase()}
          </div>
        </div>

        {/* 3D Sphere — audio-reactive */}
        <div className="h-[46vh] w-[46vh] max-h-[72%] max-w-[92%]">
          <Sphere state={activity.state} agent={activity.active_agent} audioLevel={audioLevel} />
        </div>

        {/* Backend activity is factual; the color identifies a crew member only
            while the backend says that specialist is actually running. */}
        <div className="absolute bottom-20 left-1/2 -translate-x-1/2">
          <div
            data-testid="dashboard-activity-state"
            className={`rounded-full border bg-black/55 px-4 py-2 text-[10px] font-mono tracking-[0.2em] backdrop-blur-md ${activityColor}`}
            title={activity.tool || undefined}
          >
            {activity.state === 'idle' && activityText === 'SYSTEM READY' ? 'JARVIS // STANDBY' : `${activityAgent} // ${activityText.toUpperCase()}`}
          </div>
        </div>

        {/* Voice state badge */}
        <div className="absolute bottom-32 left-1/2 -translate-x-1/2">
          <div
            data-testid="dashboard-voice-state"
            className="rounded-full border border-white/10 bg-black/55 px-4 py-2 text-[10px] font-mono tracking-[0.24em] text-zinc-400 backdrop-blur-md"
          >
            {voiceCoreText}
          </div>
        </div>

        {/* Vision state badge */}
        <div
          data-testid="dashboard-vision-state"
          className="absolute top-16 right-6 rounded-full border border-white/10 bg-black/55 px-4 py-2 text-[10px] font-mono tracking-[0.24em] text-zinc-500 backdrop-blur-md"
        >
          {visionText}
        </div>

        {/* Bottom control cluster — Stormbreaker pill bar */}
        <div className="absolute bottom-4">
          <div className="sb-panel flex items-center gap-6 rounded-full px-6 py-3 shadow-[0_0_50px_rgba(0,0,0,0.45)]">
            <button
              data-testid="dashboard-vision-button"
              onClick={onToggleVision}
              className={`rounded-full p-3 transition-colors ${activeVisionSource !== 'none' ? 'bg-amber-500/10 text-amber-300 hover:bg-amber-500/20' : 'text-zinc-500 hover:bg-white/10 hover:text-amber-300'}`}
            >
              <RiCameraLine size={20} />
            </button>
            <button
              data-testid="dashboard-power-button"
              onClick={onToggleVoice}
              className={`rounded-full border-2 p-4 transition-all ${
                voiceConnecting || voiceLive
                  ? 'border-amber-400 bg-amber-500 text-black shadow-[0_0_18px_rgba(255,176,32,0.45)]'
                  : voiceError
                    ? 'border-red-500/50 bg-red-500/10 text-red-400'
                    : 'border-white/10 bg-white/5 text-zinc-500 hover:border-amber-500/40 hover:text-amber-300'
              }`}
            >
              <RiPhoneFill size={22} className={voiceConnecting ? 'animate-pulse' : ''} />
            </button>
            <button
              data-testid="dashboard-mic-button"
              onClick={onToggleMic}
              className={`rounded-full p-3 transition-colors ${
                voiceLive && !voiceMuted
                  ? 'bg-amber-500/10 text-amber-400 hover:bg-amber-500/20'
                  : voiceLive && voiceMuted
                    ? 'bg-red-500/10 text-red-400 hover:bg-red-500/20'
                    : 'text-zinc-500 hover:bg-white/10 hover:text-amber-300'
              }`}
            >
              {voiceLive && !voiceMuted ? <RiMicLine size={20} /> : <RiMicOffLine size={20} />}
            </button>
            {/* Local (offline) voice — click to record, click to stop */}
            {waitAvailable ? <button
              data-testid="dashboard-stop-voice-turn"
              onClick={onStopVoiceTurn}
              title="Stop the current local voice turn"
              className="flex items-center gap-2 rounded-full border border-red-500/45 bg-red-500/15 px-3 py-2 text-[9px] font-black tracking-[0.14em] text-red-200 transition-colors hover:bg-red-500/25"
            >
              <RiStopCircleLine size={16} /> WAIT
            </button> : null}
            <button
              data-testid="dashboard-localvoice-button"
              onClick={onLocalVoice}
              disabled={waitAvailable}
              title="Local voice (offline) — click to talk, click to stop"
              className={`flex items-center gap-2 rounded-full px-3 py-2 text-[9px] font-bold tracking-[0.14em] transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${
                localVoiceState === 'recording'
                  ? 'bg-red-500 text-white shadow-[0_0_16px_rgba(239,68,68,0.5)] animate-pulse'
                  : localVoiceState === 'thinking'
                    ? 'bg-amber-500/20 text-amber-300'
                    : 'text-zinc-500 hover:bg-white/10 hover:text-amber-300'
              }`}
            >
              <RiMicLine size={16} />
              {localVoiceState === 'recording' ? 'STOP' : localVoiceState === 'thinking' ? '…' : 'LOCAL'}
            </button>
          </div>
        </div>
      </div>

      {/* ─── RIGHT PANEL — Transcript + Chat ─── */}
      <div className="col-span-12 flex h-full min-h-0 flex-col overflow-hidden lg:col-span-3">
        <div className="sb-panel flex h-full min-h-0 flex-col p-4">
          <div className="mb-3 flex items-center justify-between border-b border-white/10 pb-3">
            <span className="sb-label flex items-center gap-2">
              <RiTerminalBoxLine />
              TRANSCRIPT
            </span>
            <span className={`text-[10px] font-mono tracking-[0.24em] ${stillWorking ? 'animate-pulse text-amber-300' : 'text-amber-500/70'}`}>
              {stillWorking ? 'JARVIS // STILL WORKING' : 'LIVE-LOG'}
            </span>
          </div>

          {/* Live voice I/O — green box (keeps voice working) */}
          {voiceLive && (voice?.last_input || voice?.last_output) && (
            <div className="mb-3 space-y-1.5 rounded-xl border border-amber-500/15 bg-amber-900/10 px-3 py-2.5">
              {voice?.last_input && (
                <div className="flex items-start gap-2 text-[10px]">
                  <RiMicLine size={12} className="mt-0.5 shrink-0 text-amber-400" />
                  <span className="font-mono text-amber-200/80 line-clamp-2">{voice.last_input}</span>
                </div>
              )}
              {voice?.last_output && (
                <div className="flex items-start gap-2 text-[10px]">
                  <span className="mt-0.5 shrink-0 text-[10px] text-cyan-400">🔊</span>
                  <span className="font-mono text-cyan-200/70 line-clamp-2">{voice.last_output}</span>
                </div>
              )}
            </div>
          )}

          {/* Measured controller facts only — no estimated latency or fake cancel state. */}
          {hasVoiceDiagnostics ? <div
            data-testid="voice-timing"
            className={`mb-3 rounded-xl border px-3 py-2.5 font-mono ${timing?.cancelled || lastVoiceStop ? 'border-amber-500/25 bg-amber-500/5' : 'border-emerald-500/20 bg-emerald-500/5'}`}
          >
            <div className="mb-1.5 text-[8px] tracking-[0.2em] text-zinc-500">VOICE DIAGNOSTICS // MEASURED</div>
            <div className="grid grid-cols-3 gap-2 text-[9px] tracking-[0.08em] text-zinc-300">
              <span>FIRST {timing?.first_audio_ms != null ? `${timing.first_audio_ms}MS` : '—'}</span>
              <span>TOTAL {timing?.total_ms != null ? `${timing.total_ms}MS` : '—'}</span>
              <span>{timing?.chunks != null ? `${timing.chunks} CHUNK${timing.chunks === 1 ? '' : 'S'}` : 'NO AUDIO'}</span>
            </div>
            {stopSummary ? <div className="mt-1.5 text-[8px] tracking-[0.14em] text-amber-200">{stopSummary}</div> : null}
          </div> : null}

          {/* Messages */}
          <div ref={scrollRef} className="scrollbar-small min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
            {messages.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-zinc-700">
                <RiHistoryLine size={24} />
                <span className="text-[10px] font-mono tracking-[0.34em]">NO DATA STREAM</span>
              </div>
            ) : (
              messages
                // Never render messages with null/empty text (backend null-reply guard)
                .filter((msg) => msg.text != null && String(msg.text).trim() !== '')
                .map((msg) => (
                <div
                  key={`${msg.id}-${msg.ts}`}
                  data-testid="transcript-message"
                  className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
                >
                  <div className={`max-w-[94%] rounded-xl border px-4 py-3 text-[12px] font-mono leading-6 ${
                    msg.role === 'user'
                      ? 'rounded-br-none border-amber-500/25 bg-amber-900/20 text-amber-100/90'
                      : msg.role === 'system'
                        ? 'rounded-bl-none border-zinc-700 bg-zinc-900/30 text-zinc-500 italic'
                        : 'rounded-bl-none border-white/5 bg-zinc-900/50 text-zinc-300'
                  }`}>
                    <div className="mb-2 flex items-center justify-between gap-4 text-[9px] uppercase tracking-[0.24em] text-zinc-500">
                      <span>{formatRole(msg.role)}</span>
                      <span>{shortTime(msg.ts)}</span>
                    </div>
                    <div className="whitespace-pre-wrap break-words">
                      {msg.role === 'assistant' ? (
                        <MarkdownMessage content={msg.text ?? ''} />
                      ) : (
                        String(msg.text ?? '')
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Chat input */}
          <form
            onSubmit={(e) => { e.preventDefault(); onSend() }}
            className="mt-4 space-y-3 border-t border-white/5 pt-4"
          >
            <textarea
              data-testid="dashboard-chat-input"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  e.stopPropagation()
                  if (!busy && !stillWorking && prompt.trim()) onSend()
                }
              }}
              onPaste={(e) => {
                // Explicit paste handler — ensures Ctrl+V always works in Electron
                // even when clipboard security context is restricted
                const pasted = e.clipboardData?.getData('text')
                if (pasted) {
                  e.preventDefault()
                  const ta = e.currentTarget
                  const start = ta.selectionStart ?? prompt.length
                  const end = ta.selectionEnd ?? prompt.length
                  const next = prompt.slice(0, start) + pasted + prompt.slice(end)
                  setPrompt(next)
                  // Restore cursor after pasted text
                  requestAnimationFrame(() => {
                    ta.selectionStart = ta.selectionEnd = start + pasted.length
                  })
                }
              }}
              placeholder="Type or paste a command — Ctrl+V works here..."
              className="scrollbar-small h-20 w-full resize-none rounded-2xl border border-white/10 bg-black/50 px-4 py-3 text-sm text-zinc-200 outline-none transition-colors placeholder:text-zinc-600 focus:border-amber-500/40"
            />
            <div className="flex items-center justify-between gap-3">
              <span className="text-[10px] font-mono tracking-[0.12em] text-zinc-600">DESKTOP ACTIONS REQUIRE THE CONTROL GATE</span>
              <button
                data-testid="dashboard-send-button"
                type="button"
                disabled={busy || stillWorking}
                onClick={onSend}
                className="rounded-xl bg-amber-500 px-5 py-3 text-xs font-black tracking-[0.18em] text-black transition-all hover:bg-amber-400 disabled:cursor-default disabled:opacity-60"
              >
                {busy ? 'PROCESSING' : stillWorking ? 'WORKING' : 'SEND'}
              </button>
            </div>
            {voiceError ? (
              <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-[11px] leading-6 text-red-200">
                {voiceError}
              </div>
            ) : null}
          </form>
        </div>
      </div>
    </div>
  )
}
