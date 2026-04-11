/**
 * GoalsWidget — Live goal tracker with progress rings.
 * Pulls from goal-list and goal-update IPC handlers.
 */

import { useState, useEffect } from 'react'
import { RiFocus3Line, RiAddLine, RiFireLine, RiArrowUpLine } from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

const api = (window as any).electron || (window as any).desktopApi

type Goal = {
  id: number; title: string; description: string; progress: number
  priority: string; status: string; category: string; created_at: string
}

function ProgressBar({ percent, priority }: { percent: number; priority: string }) {
  const color = priority === 'high' ? '#ef4444' : priority === 'medium' ? '#f59e0b' : '#10b981'
  return (
    <div className="h-1.5 w-full rounded-full bg-white/5 overflow-hidden">
      <div
        className="h-full rounded-full transition-all duration-700"
        style={{ width: `${percent}%`, background: `linear-gradient(90deg, ${color}, ${color}88)` }}
      />
    </div>
  )
}

export default function GoalsWidget({ widget }: { widget: WidgetInstance }) {
  const [goals, setGoals] = useState<Goal[]>([])
  const [newGoal, setNewGoal] = useState('')

  const loadGoals = async () => {
    try {
      const r = await api.goalList('active')
      if (r.success) setGoals(r.goals || [])
    } catch { /* */ }
  }

  useEffect(() => {
    void loadGoals()
    const timer = setInterval(loadGoals, 10000)
    return () => clearInterval(timer)
  }, [])

  const addGoal = async () => {
    if (!newGoal.trim()) return
    await api.goalAdd(newGoal, '', 'general', 'medium')
    setNewGoal('')
    await loadGoals()
  }

  const totalProgress = goals.length ? Math.round(goals.reduce((a, g) => a + g.progress, 0) / goals.length) : 0

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiFocus3Line />}
      x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col gap-3 p-4 overflow-y-auto">
        {/* Overall progress */}
        <div className="flex items-center justify-between">
          <span className="text-[9px] font-mono tracking-[0.2em] text-zinc-500">OVERALL PROGRESS</span>
          <span className="text-sm font-black text-emerald-400">{totalProgress}%</span>
        </div>
        <ProgressBar percent={totalProgress} priority="medium" />

        {/* Goals list */}
        <div className="flex flex-col gap-2 mt-1">
          {goals.length === 0 && (
            <div className="text-center text-zinc-600 text-xs py-6">No active goals. Add one below.</div>
          )}
          {goals.map((g) => (
            <div key={g.id} className="rounded-xl border border-white/5 bg-white/[0.02] p-3 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {g.priority === 'high' && <RiFireLine className="text-red-400" size={12} />}
                  {g.priority === 'medium' && <RiArrowUpLine className="text-amber-400" size={12} />}
                  <span className="text-[11px] font-bold text-zinc-200">{g.title}</span>
                </div>
                <span className="text-[10px] font-mono text-zinc-500">{g.progress}%</span>
              </div>
              <ProgressBar percent={g.progress} priority={g.priority} />
            </div>
          ))}
        </div>

        {/* Quick add */}
        <div className="flex gap-2 mt-auto">
          <input
            value={newGoal}
            onChange={(e) => setNewGoal(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addGoal()}
            placeholder="Add a goal..."
            className="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-[11px] text-zinc-300 placeholder-zinc-600 outline-none focus:border-emerald-500/30"
          />
          <button onClick={addGoal} className="rounded-lg bg-emerald-500/20 p-2 text-emerald-400 hover:bg-emerald-500/30 transition-all">
            <RiAddLine size={14} />
          </button>
        </div>
      </div>
    </WidgetShell>
  )
}
