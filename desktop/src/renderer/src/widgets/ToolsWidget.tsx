/**
 * ToolsWidget — displays all 36 JARVIS native voice tools organized by phase.
 */

import { useState } from 'react'
import {
  RiSettings3Line, RiCheckboxCircleFill, RiSearchLine,
  RiFolder3Line, RiTerminalBoxLine, RiKeyboardBoxLine,
  RiSearchEyeLine, RiBrainLine, RiWindowLine,
  RiCommandLine, RiShieldLine, RiMailLine, RiMessage2Line,
  RiPhoneLine, RiCameraLine, RiVolumeUpLine
} from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

interface ToolDef {
  name: string
  phase: string
  icon: React.ReactNode
  color: string
}

const TOOLS: ToolDef[] = [
  // Batch A-C: Core Desktop
  { name: 'read_file', phase: 'Core', icon: <RiFolder3Line size={12} />, color: '#10b981' },
  { name: 'write_file', phase: 'Core', icon: <RiFolder3Line size={12} />, color: '#10b981' },
  { name: 'manage_file', phase: 'Core', icon: <RiFolder3Line size={12} />, color: '#10b981' },
  { name: 'open_file', phase: 'Core', icon: <RiFolder3Line size={12} />, color: '#10b981' },
  { name: 'read_directory', phase: 'Core', icon: <RiFolder3Line size={12} />, color: '#10b981' },
  { name: 'create_folder', phase: 'Core', icon: <RiFolder3Line size={12} />, color: '#10b981' },
  { name: 'open_app', phase: 'Core', icon: <RiTerminalBoxLine size={12} />, color: '#6366f1' },
  { name: 'close_app', phase: 'Core', icon: <RiTerminalBoxLine size={12} />, color: '#6366f1' },
  { name: 'run_terminal', phase: 'Core', icon: <RiTerminalBoxLine size={12} />, color: '#6366f1' },
  { name: 'open_project', phase: 'Core', icon: <RiTerminalBoxLine size={12} />, color: '#6366f1' },
  { name: 'ghost_type', phase: 'Core', icon: <RiKeyboardBoxLine size={12} />, color: '#f59e0b' },
  { name: 'press_shortcut', phase: 'Core', icon: <RiKeyboardBoxLine size={12} />, color: '#f59e0b' },
  { name: 'take_screenshot', phase: 'Core', icon: <RiCameraLine size={12} />, color: '#f59e0b' },
  { name: 'set_volume', phase: 'Core', icon: <RiVolumeUpLine size={12} />, color: '#f59e0b' },
  { name: 'google_search', phase: 'Core', icon: <RiSearchEyeLine size={12} />, color: '#3b82f6' },
  { name: 'smart_file_search', phase: 'Core', icon: <RiSearchEyeLine size={12} />, color: '#3b82f6' },
  { name: 'save_note', phase: 'Core', icon: <RiBrainLine size={12} />, color: '#8b5cf6' },
  { name: 'read_notes', phase: 'Core', icon: <RiBrainLine size={12} />, color: '#8b5cf6' },
  { name: 'save_core_memory', phase: 'Core', icon: <RiBrainLine size={12} />, color: '#8b5cf6' },
  { name: 'retrieve_core_memory', phase: 'Core', icon: <RiBrainLine size={12} />, color: '#8b5cf6' },
  { name: 'jarvis_chat', phase: 'Core', icon: <RiMessage2Line size={12} />, color: '#22d3ee' },
  // Batch D: Window Mgmt + Macros
  { name: 'snap_window', phase: 'Desktop', icon: <RiWindowLine size={12} />, color: '#ec4899' },
  { name: 'execute_macro', phase: 'Desktop', icon: <RiCommandLine size={12} />, color: '#ec4899' },
  { name: 'lock_system', phase: 'Desktop', icon: <RiWindowLine size={12} />, color: '#ec4899' },
  // Phase 2: Communications
  { name: 'send_whatsapp', phase: 'Comms', icon: <RiPhoneLine size={12} />, color: '#84cc16' },
  { name: 'open_whatsapp_chat', phase: 'Comms', icon: <RiPhoneLine size={12} />, color: '#84cc16' },
  { name: 'send_telegram', phase: 'Comms', icon: <RiMessage2Line size={12} />, color: '#06b6d4' },
  { name: 'send_email', phase: 'Comms', icon: <RiMailLine size={12} />, color: '#f97316' },
  // Phase 5: Cyber Arsenal
  { name: 'port_scan', phase: 'Cyber', icon: <RiShieldLine size={12} />, color: '#ef4444' },
  { name: 'nmap_scan', phase: 'Cyber', icon: <RiShieldLine size={12} />, color: '#ef4444' },
  { name: 'whois_lookup', phase: 'Cyber', icon: <RiShieldLine size={12} />, color: '#ef4444' },
  { name: 'dns_lookup', phase: 'Cyber', icon: <RiShieldLine size={12} />, color: '#ef4444' },
  { name: 'subdomain_enum', phase: 'Cyber', icon: <RiShieldLine size={12} />, color: '#ef4444' },
  { name: 'hash_identify', phase: 'Cyber', icon: <RiShieldLine size={12} />, color: '#ef4444' },
  { name: 'ip_geolocation', phase: 'Cyber', icon: <RiShieldLine size={12} />, color: '#ef4444' },
]

const PHASES = ['Core', 'Desktop', 'Comms', 'Cyber']
const PHASE_COLORS: Record<string, string> = {
  Core: '#10b981', Desktop: '#ec4899', Comms: '#84cc16', Cyber: '#ef4444'
}

export default function ToolsWidget({ widget }: { widget: WidgetInstance }) {
  const [filter, setFilter] = useState('')
  const [selectedPhase, setSelectedPhase] = useState<string | null>(null)

  const filtered = TOOLS.filter(t => {
    if (selectedPhase && t.phase !== selectedPhase) return false
    if (filter && !t.name.includes(filter.toLowerCase())) return false
    return true
  })

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiSettings3Line />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col p-4">
        {/* Header */}
        <div className="mb-3 flex items-center justify-between border-b border-white/5 pb-3">
          <span className="text-[10px] font-mono tracking-[0.24em] text-emerald-500">{TOOLS.length} NATIVE TOOLS</span>
        </div>

        {/* Search */}
        <div className="mb-3 flex items-center gap-2 rounded-xl border border-white/10 bg-black/40 px-3 py-2">
          <RiSearchLine className="text-zinc-500" size={14} />
          <input
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder="Filter tools..."
            className="flex-1 bg-transparent text-xs text-zinc-200 outline-none placeholder:text-zinc-600"
          />
        </div>

        {/* Phase tabs */}
        <div className="mb-3 flex gap-1.5">
          <button
            onClick={() => setSelectedPhase(null)}
            className={`rounded-lg px-2.5 py-1.5 text-[8px] font-bold tracking-[0.14em] transition-all ${
              !selectedPhase ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'text-zinc-500 border border-white/5'
            }`}
          >
            ALL
          </button>
          {PHASES.map(p => (
            <button
              key={p}
              onClick={() => setSelectedPhase(selectedPhase === p ? null : p)}
              className={`rounded-lg px-2.5 py-1.5 text-[8px] font-bold tracking-[0.14em] transition-all ${
                selectedPhase === p ? 'border' : 'text-zinc-500 border border-white/5'
              }`}
              style={selectedPhase === p ? { backgroundColor: PHASE_COLORS[p] + '20', color: PHASE_COLORS[p], borderColor: PHASE_COLORS[p] + '50' } : undefined}
            >
              {p.toUpperCase()}
            </button>
          ))}
        </div>

        {/* Tool list */}
        <div className="scrollbar-small flex-1 space-y-1 overflow-y-auto pr-1">
          {filtered.map(tool => (
            <div
              key={tool.name}
              className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.02] px-3 py-2.5 transition-all hover:border-emerald-500/20"
            >
              <div className="flex h-6 w-6 items-center justify-center rounded-lg" style={{ backgroundColor: tool.color + '20', color: tool.color }}>
                {tool.icon}
              </div>
              <div className="flex-1">
                <span className="text-[10px] font-bold tracking-[0.1em] text-zinc-200">{tool.name}</span>
              </div>
              <RiCheckboxCircleFill className="text-emerald-500/60" size={12} />
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="mt-2 text-center text-[8px] font-mono tracking-[0.2em] text-zinc-600">
          {filtered.length} / {TOOLS.length} SHOWN
        </div>
      </div>
    </WidgetShell>
  )
}
