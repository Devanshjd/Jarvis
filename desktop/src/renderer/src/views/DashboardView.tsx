import { useEffect, useRef } from 'react'
import {
  RiCameraLine,
  RiCpuLine,
  RiHardDriveLine,
  RiHistoryLine,
  RiMicLine,
  RiMicOffLine,
  RiPhoneFill,
  RiTempColdLine,
  RiTerminalBoxLine,
  RiTimerLine,
  RiWifiLine
} from 'react-icons/ri'
import Sphere from '../components/Sphere'
import CameraFeed from '../components/CameraFeed'
import MarkdownMessage from '../components/MarkdownMessage'
import type {
  ChatMessage,
  RuntimeStatus,
  SystemStatsResult,
  VoiceStatus
} from '../lib/types'
import { formatRole, shortTime } from '../lib/types'
import type { VisionSource } from '../services/JarvisGeminiLive'

/* ═══════════════════════════════════════════
   Dashboard View — IRIS-style 3-column layout
   ═══════════════════════════════════════════ */

export interface DashboardViewProps {
  status: RuntimeStatus | null
  voice: VoiceStatus | null
  backendState: string
  messages: ChatMessage[]
  prompt: string
  setPrompt: (v: string) => void
  approveDesktop: boolean
  setApproveDesktop: (v: boolean) => void
  busy: boolean
  visionSource: VisionSource
  dashboardVisionSource: 'none' | 'camera' | 'screen'
  systemStats: SystemStatsResult | null
  audioLevel: number
  onSend: () => void
  onRefresh: () => void
  onToggleVision: () => void
  onToggleVoice: () => void
  onToggleMic: () => void
  onSetDashboardVision: (s: 'none' | 'camera' | 'screen') => void
}

export default function DashboardView(props: DashboardViewProps) {
  const {
    status, voice, backendState, messages, prompt, setPrompt,
    approveDesktop, setApproveDesktop, busy, visionSource,
    dashboardVisionSource, systemStats, audioLevel,
    onSend, onToggleVision, onToggleVoice, onToggleMic,
    onSetDashboardVision
  } = props

  const scrollRef = useRef<HTMLDivElement | null>(null)
  const backendOnline = backendState !== 'OFFLINE'
  const voiceLive = Boolean(voice?.active || voice?.connecting || status?.voice_enabled)
  const voiceConnecting = Boolean(voice?.connecting)
  const voiceMuted = Boolean(voice?.mic_muted)
  const voiceError = voice?.error || ''

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages])

  const sphereState = busy ? 'thinking' : status?.waiting_for_input ? 'waiting' : voiceLive ? 'listening' : 'idle'

  return (
    <div className="grid h-full min-h-0 grid-cols-12 gap-4 overflow-hidden px-4 py-4">
      {/* ─── LEFT PANEL ─── */}
      <div className="col-span-3 hidden h-full min-h-0 flex-col gap-4 lg:flex">
        {/* Camera / Screen Feed — IRIS optical feed */}
        <div className="iris-panel relative h-72 overflow-hidden p-2">
          <CameraFeed source={dashboardVisionSource} />
          {/* Feed source selector */}
          {dashboardVisionSource === 'none' && (
            <div className="absolute bottom-3 inset-x-3 flex gap-2">
              <button onClick={() => onSetDashboardVision('camera')} className="flex-1 rounded-lg border border-zinc-800 bg-zinc-950/80 py-2 text-[9px] font-bold tracking-[0.2em] text-zinc-400 transition-colors hover:border-emerald-500/30 hover:text-emerald-400">
                CAMERA
              </button>
              <button onClick={() => onSetDashboardVision('screen')} className="flex-1 rounded-lg border border-zinc-800 bg-zinc-950/80 py-2 text-[9px] font-bold tracking-[0.2em] text-zinc-400 transition-colors hover:border-emerald-500/30 hover:text-emerald-400">
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
        <div className="iris-panel p-4">
          <div className="mb-3 flex items-center justify-between border-b border-white/10 pb-3">
            <span className="iris-label">NEURAL UPLINK</span>
            <span className={`text-[10px] font-mono tracking-[0.2em] ${backendOnline ? 'text-emerald-400' : 'text-zinc-600'}`}>
              {backendOnline ? 'LINKED' : 'STANDBY'}
            </span>
          </div>
          <div className="flex items-end justify-between">
            <div>
              <div className="text-[10px] font-mono tracking-[0.2em] text-zinc-600">HOST NODE</div>
              <div className="mt-2 flex items-center gap-2 text-sm font-black text-white">
                <RiWifiLine className={backendOnline ? 'text-emerald-400' : 'text-zinc-600'} />
                {status?.provider?.local ? 'LOCAL' : 'REMOTE'}
              </div>
            </div>
            <div className="text-right">
              <div className="text-[10px] font-mono tracking-[0.2em] text-zinc-600">VOICE MODEL</div>
              <div className="mt-2 text-sm font-black text-white">
                {voiceLive ? 'GEMINI LIVE' : 'GEMINI READY'}
              </div>
            </div>
          </div>
        </div>

        {/* Core Metrics — IRIS-style real system stats */}
        <div className="iris-panel flex-1 p-4">
          <div className="mb-4 border-b border-white/10 pb-3">
            <span className="iris-label">CORE METRICS</span>
          </div>
          <div className="grid h-[calc(100%-2rem)] grid-cols-2 gap-3">
            <div className="iris-metric-card flex flex-col justify-between">
              <div className="flex items-center justify-between text-zinc-500">
                <RiCpuLine size={16} />
                <span className="text-[8px] font-mono tracking-[0.2em]">CPU LOAD</span>
              </div>
              <div className="mt-auto text-right text-lg font-black text-emerald-400">
                {systemStats ? `${systemStats.cpuLoad}%` : '--'}
              </div>
            </div>
            <div className="iris-metric-card flex flex-col justify-between">
              <div className="flex items-center justify-between text-zinc-500">
                <RiHardDriveLine size={16} />
                <span className="text-[8px] font-mono tracking-[0.2em]">RAM</span>
              </div>
              <div className="mt-auto text-right text-lg font-black text-emerald-400">
                {systemStats ? `${systemStats.ramPercent}%` : '--'}
              </div>
            </div>
            <div className="iris-metric-card flex flex-col justify-between">
              <div className="flex items-center justify-between text-zinc-500">
                <RiTempColdLine size={16} />
                <span className="text-[8px] font-mono tracking-[0.2em]">TEMP</span>
              </div>
              <div className="mt-auto text-right text-lg font-black text-emerald-400">
                {systemStats?.temperature != null ? `${systemStats.temperature}°` : '--'}
              </div>
            </div>
            <div className="iris-metric-card flex flex-col justify-between">
              <div className="flex items-center justify-between text-zinc-500">
                <RiTimerLine size={16} />
                <span className="text-[8px] font-mono tracking-[0.2em]">UPTIME</span>
              </div>
              <div className="mt-auto text-right text-lg font-black text-emerald-400">
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
          <div className="rounded-full border border-emerald-500/20 bg-black/40 px-4 py-1.5 text-[10px] font-mono tracking-[0.34em] text-zinc-500 backdrop-blur-md">
            {status?.waiting_for_input ? 'AWAITING INPUT' : busy ? 'PROCESSING' : voiceLive ? 'VOICE CORE ACTIVE' : 'SYSTEM READY'}
          </div>
        </div>

        {/* 3D Sphere — audio-reactive */}
        <div className="h-[46vh] w-[46vh] max-h-[72%] max-w-[92%]">
          <Sphere state={sphereState as 'idle' | 'listening' | 'thinking' | 'waiting'} audioLevel={audioLevel} />
        </div>

        {/* Voice state badge */}
        <div className="absolute bottom-28 left-1/2 -translate-x-1/2">
          <div
            data-testid="dashboard-voice-state"
            className="rounded-full border border-white/10 bg-black/55 px-4 py-2 text-[10px] font-mono tracking-[0.24em] text-zinc-400 backdrop-blur-md"
          >
            {voiceConnecting ? 'VOICE CORE CONNECTING' : voiceLive ? (voiceMuted ? 'VOICE CORE MUTED' : 'VOICE CORE LIVE') : 'VOICE CORE STANDBY'}
          </div>
        </div>

        {/* Vision state badge */}
        <div
          data-testid="dashboard-vision-state"
          className="absolute top-16 right-6 rounded-full border border-white/10 bg-black/55 px-4 py-2 text-[10px] font-mono tracking-[0.24em] text-zinc-500 backdrop-blur-md"
        >
          {visionSource === 'screen' ? 'VISION // SCREEN' : visionSource === 'camera' ? 'VISION // CAMERA' : 'VISION // OFF'}
        </div>

        {/* Bottom control cluster — IRIS pill bar */}
        <div className="absolute bottom-4">
          <div className="iris-panel flex items-center gap-6 rounded-full px-6 py-3 shadow-[0_0_50px_rgba(0,0,0,0.45)]">
            <button
              data-testid="dashboard-vision-button"
              onClick={onToggleVision}
              className={`rounded-full p-3 transition-colors ${visionSource !== 'none' ? 'bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20' : 'text-zinc-500 hover:bg-white/10 hover:text-emerald-300'}`}
            >
              <RiCameraLine size={20} />
            </button>
            <button
              data-testid="dashboard-power-button"
              onClick={onToggleVoice}
              className={`rounded-full border-2 p-4 transition-all ${
                voiceConnecting || voiceLive
                  ? 'border-emerald-400 bg-emerald-500 text-black shadow-[0_0_18px_rgba(16,185,129,0.45)]'
                  : 'border-red-500/50 bg-red-500/10 text-red-400'
              }`}
            >
              <RiPhoneFill size={22} className={voiceConnecting ? 'animate-pulse' : ''} />
            </button>
            <button
              data-testid="dashboard-mic-button"
              onClick={onToggleMic}
              className={`rounded-full p-3 transition-colors ${
                voiceLive && !voiceMuted
                  ? 'bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20'
                  : voiceLive && voiceMuted
                    ? 'bg-red-500/10 text-red-400 hover:bg-red-500/20'
                    : 'text-zinc-500 hover:bg-white/10 hover:text-emerald-300'
              }`}
            >
              {voiceLive && !voiceMuted ? <RiMicLine size={20} /> : <RiMicOffLine size={20} />}
            </button>
          </div>
        </div>
      </div>

      {/* ─── RIGHT PANEL — Transcript + Chat ─── */}
      <div className="col-span-12 flex h-full min-h-0 flex-col overflow-hidden lg:col-span-3">
        <div className="iris-panel flex h-full min-h-0 flex-col p-4">
          <div className="mb-3 flex items-center justify-between border-b border-white/10 pb-3">
            <span className="iris-label flex items-center gap-2">
              <RiTerminalBoxLine />
              TRANSCRIPT
            </span>
            <span className="text-[10px] font-mono tracking-[0.24em] text-emerald-500/70">LIVE-LOG</span>
          </div>

          {/* Live voice I/O — green box (keeps voice working) */}
          {voiceLive && (voice?.last_input || voice?.last_output) && (
            <div className="mb-3 space-y-1.5 rounded-xl border border-emerald-500/15 bg-emerald-900/10 px-3 py-2.5">
              {voice?.last_input && (
                <div className="flex items-start gap-2 text-[10px]">
                  <RiMicLine size={12} className="mt-0.5 shrink-0 text-emerald-400" />
                  <span className="font-mono text-emerald-200/80 line-clamp-2">{voice.last_input}</span>
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
                      ? 'rounded-br-none border-emerald-500/25 bg-emerald-900/20 text-emerald-100/90'
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
                  if (!busy && prompt.trim()) onSend()
                }
              }}
              placeholder="Type a command or ask JARVIS..."
              className="scrollbar-small h-20 w-full resize-none rounded-2xl border border-white/10 bg-black/50 px-4 py-3 text-sm text-zinc-200 outline-none transition-colors placeholder:text-zinc-600 focus:border-emerald-500/40"
            />
            <div className="flex items-center justify-between gap-3">
              <label className="flex items-center gap-2 text-[11px] font-mono tracking-[0.12em] text-zinc-500">
                <input
                  type="checkbox"
                  checked={approveDesktop}
                  onChange={(e) => setApproveDesktop(e.target.checked)}
                  className="h-4 w-4 rounded border-white/10 bg-black"
                />
                APPROVE DESKTOP
              </label>
              <button
                data-testid="dashboard-send-button"
                type="button"
                disabled={busy}
                onClick={onSend}
                className="rounded-xl bg-emerald-500 px-5 py-3 text-xs font-black tracking-[0.18em] text-black transition-all hover:bg-emerald-400 disabled:cursor-default disabled:opacity-60"
              >
                {busy ? 'PROCESSING' : 'SEND'}
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
