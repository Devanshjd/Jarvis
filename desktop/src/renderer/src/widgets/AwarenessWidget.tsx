/**
 * AwarenessWidget — Shows screen awareness status, last analysis,
 * and toggle control. Also shows browser automation status.
 */

import { useState, useEffect } from 'react'
import { RiEyeLine, RiEyeOffLine, RiGlobalLine, RiRefreshLine, RiCamera2Line } from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

const api = (window as any).electron || (window as any).desktopApi

export default function AwarenessWidget({ widget }: { widget: WidgetInstance }) {
  const [active, setActive] = useState(false)
  const [lastResult, setLastResult] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [history, setHistory] = useState<Array<{ text: string; time: string }>>([])

  const checkStatus = async () => {
    try {
      const r = await api.awarenessStatus()
      setActive(r.active)
      if (r.lastResult && r.lastResult !== lastResult) {
        setLastResult(r.lastResult)
      }
    } catch { /* */ }
  }

  useEffect(() => {
    void checkStatus()
    const timer = setInterval(checkStatus, 5000)
    return () => clearInterval(timer)
  }, [])

  const toggleAwareness = async () => {
    if (active) {
      await api.awarenessStop()
      setActive(false)
    } else {
      const r = await api.awarenessStart()
      setActive(r.success)
      if (r.firstResult) {
        setLastResult(r.firstResult)
        setHistory(prev => [{ text: r.firstResult, time: new Date().toLocaleTimeString() }, ...prev].slice(0, 5))
      }
    }
  }

  const analyzeNow = async () => {
    setAnalyzing(true)
    try {
      const r = await api.awarenessAnalyzeNow()
      if (r.success) {
        setLastResult(r.text)
        setHistory(prev => [{ text: r.text, time: new Date().toLocaleTimeString() }, ...prev].slice(0, 5))
      }
    } catch { /* */ }
    setAnalyzing(false)
  }

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiEyeLine />}
      x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col gap-3 p-4 overflow-y-auto">
        {/* Status bar */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${active ? 'bg-emerald-400 animate-pulse' : 'bg-zinc-600'}`} />
            <span className="text-[10px] font-mono tracking-[0.2em] text-zinc-400">
              {active ? 'WATCHING' : 'INACTIVE'}
            </span>
          </div>
          <div className="flex gap-1.5">
            <button onClick={analyzeNow} disabled={analyzing}
              className="rounded-lg bg-cyan-500/10 px-3 py-1.5 text-[9px] font-mono tracking-widest text-cyan-400 hover:bg-cyan-500/20 transition-all disabled:opacity-50">
              <RiCamera2Line className={`inline mr-1 ${analyzing ? 'animate-spin' : ''}`} size={11} />
              ANALYZE
            </button>
            <button onClick={toggleAwareness}
              className={`rounded-lg px-3 py-1.5 text-[9px] font-mono tracking-widest transition-all ${
                active
                  ? 'bg-red-500/10 text-red-400 hover:bg-red-500/20'
                  : 'bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20'
              }`}>
              {active ? <><RiEyeOffLine className="inline mr-1" size={11} />STOP</> : <><RiEyeLine className="inline mr-1" size={11} />START</>}
            </button>
          </div>
        </div>

        {/* Last result */}
        {lastResult && (
          <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3">
            <div className="text-[8px] font-mono tracking-[0.2em] text-zinc-600 mb-1.5">LATEST OBSERVATION</div>
            <p className="text-[10px] text-zinc-300 leading-relaxed">{lastResult.slice(0, 400)}</p>
          </div>
        )}

        {/* History */}
        {history.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-[8px] font-mono tracking-[0.2em] text-zinc-600">HISTORY</div>
            {history.map((h, i) => (
              <div key={i} className="rounded-lg border border-white/3 bg-white/[0.01] px-3 py-2">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[8px] text-zinc-600">{h.time}</span>
                </div>
                <p className="text-[9px] text-zinc-500 leading-relaxed">{h.text.slice(0, 150)}...</p>
              </div>
            ))}
          </div>
        )}

        {!lastResult && !active && (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center">
            <RiEyeLine className="text-zinc-700" size={32} />
            <p className="text-[10px] text-zinc-600">Screen awareness is off.<br/>Click START to monitor your screen.</p>
          </div>
        )}
      </div>
    </WidgetShell>
  )
}
