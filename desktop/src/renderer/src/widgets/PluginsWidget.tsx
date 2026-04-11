/**
 * PluginsWidget — Shows installed plugins, toggle active/inactive.
 */

import { useState, useEffect } from 'react'
import { RiPlugLine, RiToggleLine, RiToggleFill, RiDeleteBin5Line } from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

const api = (window as any).electron || (window as any).desktopApi

type Plugin = { name: string; version?: string; description?: string; active: boolean; tools?: string[] }

export default function PluginsWidget({ widget }: { widget: WidgetInstance }) {
  const [plugins, setPlugins] = useState<Plugin[]>([])

  const loadPlugins = async () => {
    try {
      const r = await api.pluginList()
      if (r.success) setPlugins(r.plugins || [])
    } catch { /* */ }
  }

  useEffect(() => { void loadPlugins() }, [])

  const togglePlugin = async (name: string) => {
    await api.pluginToggle(name)
    await loadPlugins()
  }

  const uninstallPlugin = async (name: string) => {
    await api.pluginUninstall(name)
    await loadPlugins()
  }

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiPlugLine />}
      x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col gap-3 p-4 overflow-y-auto">
        {/* Stats bar */}
        <div className="flex items-center justify-between">
          <span className="text-[9px] font-mono tracking-[0.2em] text-zinc-500">
            {plugins.length} PLUGINS INSTALLED
          </span>
          <span className="text-[9px] font-mono tracking-[0.2em] text-emerald-500">
            {plugins.filter(p => p.active).length} ACTIVE
          </span>
        </div>

        {/* Plugins list */}
        <div className="flex flex-col gap-2">
          {plugins.length === 0 && (
            <div className="text-center text-zinc-600 text-xs py-8">
              No plugins installed.<br/>
              <span className="text-[10px] text-zinc-700">Say "Install a plugin" to JARVIS</span>
            </div>
          )}
          {plugins.map((p) => (
            <div key={p.name} className={`rounded-xl border p-3 space-y-2 transition-all ${
              p.active ? 'border-emerald-500/15 bg-emerald-500/[0.02]' : 'border-white/5 bg-white/[0.02] opacity-60'
            }`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <RiPlugLine className={p.active ? 'text-emerald-400' : 'text-zinc-600'} size={14} />
                  <div>
                    <span className="text-[11px] font-bold text-zinc-200">{p.name}</span>
                    {p.version && <span className="ml-2 text-[9px] text-zinc-600">v{p.version}</span>}
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <button onClick={() => togglePlugin(p.name)}
                    className="rounded p-1 hover:bg-white/5 transition-all">
                    {p.active
                      ? <RiToggleFill className="text-emerald-400" size={18} />
                      : <RiToggleLine className="text-zinc-600" size={18} />
                    }
                  </button>
                  <button onClick={() => uninstallPlugin(p.name)}
                    className="rounded p-1 hover:bg-red-500/10 text-zinc-600 hover:text-red-400 transition-all">
                    <RiDeleteBin5Line size={13} />
                  </button>
                </div>
              </div>
              {p.description && (
                <p className="text-[10px] text-zinc-500">{p.description}</p>
              )}
              {p.tools && p.tools.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {p.tools.map((t: string) => (
                    <span key={t} className="rounded px-1.5 py-0.5 text-[8px] font-mono bg-white/5 text-zinc-500">{t}</span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </WidgetShell>
  )
}
