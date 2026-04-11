/**
 * ToolsWidget — lists all 16 JARVIS plugins with quick-execute buttons.
 */

import { useState, useEffect } from 'react'
import { RiSettings3Line, RiPlayCircleLine, RiCheckboxCircleFill, RiCloseCircleLine } from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

const API_BASE = 'http://127.0.0.1:8765'

interface PluginInfo {
  name: string
  active: boolean
}

const PLUGIN_COLORS: Record<string, string> = {
  voice: '#10b981', automation: '#6366f1', 'web_intel': '#f59e0b', cyber: '#ef4444',
  code_assist: '#8b5cf6', scheduler: '#ec4899', file_manager: '#14b8a6', smart_home: '#06b6d4',
  email: '#f97316', self_improve: '#a855f7', conversation_memory: '#22d3ee', web_automation: '#3b82f6',
  pentest: '#dc2626', messaging: '#84cc16',
}

export default function ToolsWidget({ widget }: { widget: WidgetInstance }) {
  const [plugins, setPlugins] = useState<PluginInfo[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchPlugins()
  }, [])

  async function fetchPlugins() {
    try {
      const resp = await fetch(`${API_BASE}/api/tools/list`)
      const data = await resp.json()
      const plugins = data.plugins || {}
      setPlugins(Object.keys(plugins).map((n) => ({ name: n, active: plugins[n]?.active ?? true })))
    } catch {
      // Fallback to /api/status
      try {
        const resp = await fetch(`${API_BASE}/api/status`)
        const data = await resp.json()
        const names: string[] = data.plugins || []
        setPlugins(names.map((n) => ({ name: n, active: true })))
      } catch { setPlugins([]) }
    } finally {
      setLoading(false)
    }
  }

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiSettings3Line />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col p-4">
        <div className="mb-3 flex items-center justify-between border-b border-white/5 pb-3">
          <span className="text-[10px] font-mono tracking-[0.24em] text-zinc-500">{plugins.length} MODULES LOADED</span>
          <button onClick={fetchPlugins} className="rounded-lg border border-white/10 px-2 py-1 text-[9px] font-bold tracking-[0.18em] text-zinc-400 hover:border-emerald-500/30 hover:text-emerald-400">
            REFRESH
          </button>
        </div>

        <div className="scrollbar-small flex-1 space-y-2 overflow-y-auto pr-1">
          {loading ? (
            <div className="pt-8 text-center text-[10px] font-mono tracking-[0.3em] text-zinc-600 animate-pulse">SCANNING MODULES...</div>
          ) : plugins.length === 0 ? (
            <div className="pt-8 text-center text-[10px] font-mono tracking-[0.3em] text-zinc-600">NO PLUGINS DETECTED</div>
          ) : (
            plugins.map((plugin) => (
              <div
                key={plugin.name}
                className="flex items-center justify-between rounded-xl border border-white/5 bg-white/[0.02] px-4 py-3 transition-all hover:border-emerald-500/20 hover:bg-white/[0.04]"
              >
                <div className="flex items-center gap-3">
                  <div
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: PLUGIN_COLORS[plugin.name] || '#10b981' }}
                  />
                  <span className="text-xs font-bold tracking-[0.12em] text-zinc-200 uppercase">
                    {plugin.name.replace(/_/g, ' ')}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {plugin.active ? (
                    <RiCheckboxCircleFill className="text-emerald-500" size={14} />
                  ) : (
                    <RiCloseCircleLine className="text-zinc-600" size={14} />
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </WidgetShell>
  )
}
