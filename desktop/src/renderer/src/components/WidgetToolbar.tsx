/**
 * WidgetToolbar — quick-access bar for opening/closing widgets.
 * IRIS-style pill buttons along the bottom-left of the UI.
 */

import { motion, AnimatePresence } from 'framer-motion'
import {
  RiCloudLine, RiCpuLine, RiTerminalBoxLine, RiSettings3Line,
  RiMapPinLine, RiStockLine, RiMailLine, RiSearchEyeLine,
  RiCodeSSlashLine, RiMindMap, RiShieldLine, RiBrainLine,
  RiAppsLine
} from 'react-icons/ri'
import { useState } from 'react'
import { useStore, type WidgetType } from '../store/useStore'

const WIDGET_ITEMS: Array<{ type: WidgetType; label: string; icon: React.ComponentType<{ size: number; className?: string }> }> = [
  { type: 'weather',       label: 'Weather',     icon: RiCloudLine },
  { type: 'system',        label: 'System',      icon: RiCpuLine },
  { type: 'terminal',      label: 'Terminal',    icon: RiTerminalBoxLine },
  { type: 'tools',         label: 'Tools',       icon: RiSettings3Line },
  { type: 'map',           label: 'Map',         icon: RiMapPinLine },
  { type: 'stock',         label: 'Stocks',      icon: RiStockLine },
  { type: 'email',         label: 'Email',       icon: RiMailLine },
  { type: 'research',      label: 'Research',    icon: RiSearchEyeLine },
  { type: 'code-editor',   label: 'Code',        icon: RiCodeSSlashLine },
  { type: 'knowledge',     label: 'Knowledge',   icon: RiMindMap },
  { type: 'security',      label: 'Security',    icon: RiShieldLine },
  { type: 'memory',        label: 'Memory',      icon: RiBrainLine },
]

export default function WidgetToolbar() {
  const [expanded, setExpanded] = useState(false)
  const widgets = useStore((s) => s.widgets)
  const toggleWidget = useStore((s) => s.toggleWidget)

  return (
    <div className="fixed bottom-4 left-4 z-40 flex items-end gap-2">
      {/* Toggle button */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className={`rounded-full border p-3 transition-all shadow-[0_8px_32px_rgba(0,0,0,0.4)] ${
          expanded
            ? 'border-emerald-500/30 bg-emerald-500/20 text-emerald-400'
            : 'border-white/10 bg-[#0a0c0e]/90 text-zinc-400 hover:border-emerald-500/20 hover:text-emerald-400'
        } backdrop-blur-xl`}
      >
        <RiAppsLine size={18} />
      </button>

      {/* Widget buttons */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, x: -20, scale: 0.9 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: -20, scale: 0.9 }}
            transition={{ type: 'spring', stiffness: 400, damping: 25 }}
            className="flex items-center gap-1.5 rounded-2xl border border-white/8 bg-[#0a0c0e]/90 px-3 py-2 shadow-[0_16px_60px_rgba(0,0,0,0.5)] backdrop-blur-xl"
          >
            {WIDGET_ITEMS.map((item) => {
              const isOpen = widgets.some((w) => w.type === item.type)
              const Icon = item.icon
              return (
                <button
                  key={item.type}
                  onClick={() => toggleWidget(item.type)}
                  title={item.label}
                  className={`group relative rounded-xl p-2.5 transition-all ${
                    isOpen
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : 'text-zinc-500 hover:bg-white/5 hover:text-zinc-300'
                  }`}
                >
                  <Icon size={16} />
                  {/* Tooltip */}
                  <span className="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 rounded-md bg-zinc-800 px-2 py-1 text-[9px] font-bold tracking-[0.14em] text-zinc-200 opacity-0 transition-opacity group-hover:opacity-100 whitespace-nowrap">
                    {item.label}
                  </span>
                  {/* Active dot */}
                  {isOpen && (
                    <span className="absolute -bottom-0.5 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-emerald-400" />
                  )}
                </button>
              )
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
