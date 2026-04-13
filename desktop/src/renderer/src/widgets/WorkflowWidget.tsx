/**
 * WorkflowWidget — Visual agent loop execution monitor.
 *
 * Inspired by usejarvis.dev's workflow builder. Shows:
 * - Live execution plan with step-by-step progress
 * - Execution mode per step (screen/api/direct)
 * - Struggle detection indicator
 * - Routing statistics
 *
 * Polls /api/agent-loop/status and /api/struggle/status.
 */

import { useState, useEffect, useCallback } from 'react'
import {
  RiFlowChart, RiCheckLine, RiCloseLine, RiLoader4Line,
  RiAlertLine, RiComputerLine, RiCloudLine, RiTerminalBoxLine,
  RiRefreshLine, RiEyeLine, RiPulseLine
} from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

const BACKEND = 'http://127.0.0.1:8765'

/* ═══════════════════════════════════════════
   Types
   ═══════════════════════════════════════════ */

interface StepData {
  description: string
  status: string
  attempts: number
  result: string
  error: string
  mode: string
}

interface AgentLoopStatus {
  status: string
  goal?: string
  current_step?: number
  total_steps?: number
  iterations?: number
  struggle_score?: number
  steps?: StepData[]
  progress?: string[]
}

interface StruggleStatus {
  score: number
  is_struggling: boolean
  reason: string
  suggestion: string
  consecutive_failures: number
  mode_switches: number
}

/* ═══════════════════════════════════════════
   Sub-components
   ═══════════════════════════════════════════ */

function ModeIcon({ mode }: { mode: string }) {
  switch (mode) {
    case 'screen':
      return <RiComputerLine className="text-purple-400" title="Screen control (mouse/keyboard)" />
    case 'api':
      return <RiCloudLine className="text-cyan-400" title="API tool call" />
    case 'direct':
      return <RiTerminalBoxLine className="text-amber-400" title="System command" />
    default:
      return <RiPulseLine className="text-zinc-500" title="Auto-detect" />
  }
}

function StepStatus({ status }: { status: string }) {
  switch (status) {
    case 'succeeded':
      return <RiCheckLine className="text-emerald-400 shrink-0" />
    case 'failed':
      return <RiCloseLine className="text-red-400 shrink-0" />
    case 'running':
      return <RiLoader4Line className="text-cyan-400 animate-spin shrink-0" />
    case 'adapting':
      return <RiRefreshLine className="text-amber-400 animate-spin shrink-0" />
    case 'verifying':
      return <RiEyeLine className="text-purple-400 animate-pulse shrink-0" />
    default:
      return <div className="w-4 h-4 rounded-full bg-white/10 shrink-0" />
  }
}

function StruggleBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.round(score * 100))
  const color =
    pct > 70 ? '#ef4444'
    : pct > 40 ? '#f59e0b'
    : '#10b981'
  return (
    <div className="flex items-center gap-2">
      <span className="iris-label text-[9px] w-16 shrink-0">STRUGGLE</span>
      <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-[10px] font-mono text-zinc-500 w-8 text-right">{pct}%</span>
    </div>
  )
}

function StepNode({ step, index, isCurrent }: { step: StepData; index: number; isCurrent: boolean }) {
  return (
    <div
      className={`
        relative flex items-start gap-3 p-3 rounded-xl transition-all duration-300
        ${isCurrent ? 'bg-white/[0.06] ring-1 ring-emerald-500/30' : 'bg-white/[0.02]'}
        ${step.status === 'failed' ? 'ring-1 ring-red-500/20' : ''}
      `}
    >
      {/* Step number + connector */}
      <div className="flex flex-col items-center shrink-0">
        <div className={`
          w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold
          ${step.status === 'succeeded' ? 'bg-emerald-500/20 text-emerald-400' :
            step.status === 'failed' ? 'bg-red-500/20 text-red-400' :
            step.status === 'running' ? 'bg-cyan-500/20 text-cyan-400' :
            'bg-white/5 text-zinc-500'}
        `}>
          {step.status === 'succeeded' ? <RiCheckLine /> : index + 1}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <StepStatus status={step.status} />
          <span className="text-xs text-zinc-200 truncate">{step.description}</span>
        </div>

        <div className="flex items-center gap-3 text-[10px] text-zinc-500">
          <span className="flex items-center gap-1">
            <ModeIcon mode={step.mode} />
            {step.mode || 'auto'}
          </span>
          {step.attempts > 0 && (
            <span>attempt {step.attempts}</span>
          )}
        </div>

        {step.error && step.status === 'failed' && (
          <p className="mt-1 text-[10px] text-red-400/80 truncate">{step.error}</p>
        )}
        {step.result && step.status === 'succeeded' && (
          <p className="mt-1 text-[10px] text-emerald-400/60 truncate">{step.result}</p>
        )}
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════
   Main Widget
   ═══════════════════════════════════════════ */

export default function WorkflowWidget({ widget }: { widget: WidgetInstance }) {
  const [loop, setLoop] = useState<AgentLoopStatus>({ status: 'idle' })
  const [struggle, setStruggle] = useState<StruggleStatus>({
    score: 0, is_struggling: false, reason: '', suggestion: '',
    consecutive_failures: 0, mode_switches: 0
  })

  const fetchStatus = useCallback(async () => {
    try {
      const [loopResp, struggleResp] = await Promise.all([
        fetch(`${BACKEND}/api/agent-loop/status`, { signal: AbortSignal.timeout(3000) }),
        fetch(`${BACKEND}/api/struggle/status`, { signal: AbortSignal.timeout(3000) })
      ])
      if (loopResp.ok) setLoop(await loopResp.json())
      if (struggleResp.ok) setStruggle(await struggleResp.json())
    } catch { /* non-critical */ }
  }, [])

  useEffect(() => {
    void fetchStatus()
    // Poll faster when active, slower when idle
    const interval = loop.status === 'running' ? 1000 : 5000
    const timer = setInterval(fetchStatus, interval)
    return () => clearInterval(timer)
  }, [fetchStatus, loop.status])

  const isActive = loop.status === 'running'
  const steps = loop.steps || []
  const progress = loop.progress || []

  return (
    <WidgetShell
      id={widget.id}
      title={widget.title}
      icon={<RiFlowChart />}
      x={widget.x}
      y={widget.y}
      width={widget.width}
      height={widget.height}
      minimized={widget.minimized}
    >
      <div className="flex h-full flex-col gap-3 p-4 overflow-hidden">
        {/* Header stats */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${
              isActive ? 'bg-emerald-400 animate-pulse' :
              loop.status === 'stuck' ? 'bg-amber-400 animate-pulse' :
              loop.status === 'failed' ? 'bg-red-400' :
              'bg-zinc-600'
            }`} />
            <span className="iris-label text-[10px]">
              {isActive ? 'EXECUTING' :
               loop.status === 'completed' ? 'COMPLETE' :
               loop.status === 'stuck' ? 'STUCK' :
               loop.status === 'failed' ? 'FAILED' : 'IDLE'}
            </span>
          </div>
          {isActive && loop.iterations !== undefined && (
            <span className="text-[10px] font-mono text-zinc-500">
              iter {loop.iterations} • step {(loop.current_step || 0) + 1}/{loop.total_steps || 0}
            </span>
          )}
        </div>

        {/* Goal */}
        {loop.goal && (
          <div className="px-3 py-2 rounded-lg bg-white/[0.03] border border-white/5">
            <p className="text-xs text-zinc-300 leading-relaxed">{loop.goal}</p>
          </div>
        )}

        {/* Struggle indicator */}
        <StruggleBar score={struggle.score} />

        {struggle.is_struggling && struggle.suggestion && (
          <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-500/5 border border-amber-500/10">
            <RiAlertLine className="text-amber-400 shrink-0 mt-0.5" />
            <p className="text-[10px] text-amber-300/80">{struggle.suggestion}</p>
          </div>
        )}

        {/* Step nodes */}
        {steps.length > 0 ? (
          <div className="flex-1 overflow-y-auto space-y-2 pr-1 custom-scroll">
            {steps.map((step, i) => (
              <StepNode
                key={i}
                step={step}
                index={i}
                isCurrent={i === (loop.current_step || 0) && isActive}
              />
            ))}
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center space-y-2">
              <RiFlowChart className="w-10 h-10 text-zinc-700 mx-auto" />
              <p className="text-xs text-zinc-600">No active workflow</p>
              <p className="text-[10px] text-zinc-700">
                Give JARVIS a complex task and the agent loop<br />
                will show live execution progress here.
              </p>
            </div>
          </div>
        )}

        {/* Live progress log */}
        {progress.length > 0 && (
          <div className="border-t border-white/5 pt-2 max-h-20 overflow-y-auto custom-scroll">
            {progress.slice(-4).map((msg, i) => (
              <p key={i} className="text-[10px] text-zinc-500 leading-relaxed truncate">
                {msg}
              </p>
            ))}
          </div>
        )}
      </div>
    </WidgetShell>
  )
}
