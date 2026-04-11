/**
 * SystemWidget — live CPU, RAM, temperature gauges.
 * Pulls from existing system-stats IPC handler.
 */

import { useState, useEffect } from 'react'
import { RiCpuLine, RiHardDriveLine, RiTempColdLine, RiTimerLine, RiComputerLine } from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance, SystemStatsResult } from '../store/useStore'

function GaugeRing({ percent, label, color = '#10b981' }: { percent: number; label: string; color?: string }) {
  const radius = 36
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (percent / 100) * circumference
  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative h-20 w-20">
        <svg className="h-full w-full -rotate-90" viewBox="0 0 80 80">
          <circle cx="40" cy="40" r={radius} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="5" />
          <circle
            cx="40" cy="40" r={radius} fill="none" stroke={color} strokeWidth="5"
            strokeDasharray={circumference} strokeDashoffset={offset}
            strokeLinecap="round"
            className="transition-all duration-700"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center text-lg font-black text-white">
          {percent}%
        </div>
      </div>
      <span className="text-[9px] font-mono tracking-[0.24em] text-zinc-500">{label}</span>
    </div>
  )
}

export default function SystemWidget({ widget }: { widget: WidgetInstance }) {
  const [stats, setStats] = useState<SystemStatsResult | null>(null)

  useEffect(() => {
    const fetch = async () => {
      try { setStats(await window.desktopApi.systemStats()) } catch { /* */ }
    }
    void fetch()
    const timer = setInterval(fetch, 2000)
    return () => clearInterval(timer)
  }, [])

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiCpuLine />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col gap-4 p-5">
        {/* Gauge row */}
        <div className="flex items-center justify-around">
          <GaugeRing percent={stats?.cpuLoad ?? 0} label="CPU" />
          <GaugeRing percent={stats?.ramPercent ?? 0} label="RAM" color="#6366f1" />
        </div>

        {/* Info grid */}
        <div className="grid grid-cols-2 gap-2">
          <div className="flex items-center gap-2 rounded-xl border border-white/5 bg-white/[0.02] px-3 py-2.5">
            <RiComputerLine className="text-zinc-500" size={14} />
            <div>
              <div className="text-[8px] font-mono tracking-[0.2em] text-zinc-600">HOSTNAME</div>
              <div className="text-[11px] font-bold text-zinc-300">{stats?.hostname ?? '--'}</div>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-xl border border-white/5 bg-white/[0.02] px-3 py-2.5">
            <RiTimerLine className="text-zinc-500" size={14} />
            <div>
              <div className="text-[8px] font-mono tracking-[0.2em] text-zinc-600">UPTIME</div>
              <div className="text-[11px] font-bold text-zinc-300">{stats?.uptime ?? '--'}</div>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-xl border border-white/5 bg-white/[0.02] px-3 py-2.5">
            <RiHardDriveLine className="text-zinc-500" size={14} />
            <div>
              <div className="text-[8px] font-mono tracking-[0.2em] text-zinc-600">RAM</div>
              <div className="text-[11px] font-bold text-zinc-300">{stats ? `${stats.ramUsage} / ${stats.ramTotal} MB` : '--'}</div>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-xl border border-white/5 bg-white/[0.02] px-3 py-2.5">
            <RiTempColdLine className="text-zinc-500" size={14} />
            <div>
              <div className="text-[8px] font-mono tracking-[0.2em] text-zinc-600">CPU MODEL</div>
              <div className="line-clamp-1 text-[10px] font-bold text-zinc-300">{stats?.cpuModel ?? '--'}</div>
            </div>
          </div>
        </div>

        {/* Platform info */}
        <div className="mt-auto rounded-xl border border-white/5 bg-white/[0.02] px-4 py-2 text-center">
          <span className="text-[9px] font-mono tracking-[0.2em] text-zinc-500">
            {stats ? `${stats.os} // ${stats.arch} // ${stats.cores} CORES` : 'LOADING...'}
          </span>
        </div>
      </div>
    </WidgetShell>
  )
}
