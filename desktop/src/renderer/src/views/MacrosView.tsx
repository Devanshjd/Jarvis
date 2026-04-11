import {
  RiCommandLine,
  RiPlayFill,
  RiSave3Line
} from 'react-icons/ri'
import { MODULE_LIBRARY } from '../lib/types'

/* ═══════════════════════════════════════════
   Macros View — IRIS-style workflow editor placeholder
   ═══════════════════════════════════════════ */

export default function MacrosView() {
  return (
    <div className="flex h-full bg-[#09090b]">
      <aside className="scrollbar-small hidden h-full w-72 overflow-y-auto border-r border-white/5 bg-[#111113] p-4 lg:block">
        <h2 className="mb-6 border-b border-[#27272a] pb-2 text-[10px] font-black tracking-[0.24em] text-emerald-500">
          MODULE LIBRARY
        </h2>
        <div className="space-y-6">
          {['TRIGGERS', 'SYSTEM', 'AUTOMATION', 'WEB'].map((group) => (
            <div key={group}>
              <h3 className="mb-3 text-[10px] font-bold tracking-[0.22em] text-zinc-500">{group}</h3>
              <div className="space-y-2">
                {MODULE_LIBRARY.filter((i) => i.group === group).map((i) => (
                  <div key={i.name} className="rounded-xl border border-[#27272a] bg-[#18181b] px-4 py-3 text-[11px] font-bold tracking-[0.18em] text-zinc-200 transition-colors hover:border-emerald-500/40 hover:bg-[#1d1d20] cursor-grab">
                    {i.name}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </aside>
      <div className="relative flex-1 overflow-hidden">
        <div className="absolute left-4 top-4 z-10 flex items-center gap-3">
          <button className="rounded-lg border border-[#27272a] bg-[#18181b] p-3 text-zinc-500 transition-colors hover:text-emerald-400">+</button>
          <div className="rounded-lg border border-[#27272a] bg-[#18181b] px-4 py-3 text-sm font-bold text-zinc-200">Neural Patterns (0)</div>
          <div className="rounded-lg border border-[#27272a] bg-[#18181b] px-4 py-3 text-sm font-bold text-white">New JARVIS Macro</div>
          <button className="flex items-center gap-2 rounded-lg border border-[#27272a] bg-[#18181b] px-5 py-3 text-[11px] font-black tracking-[0.18em] text-emerald-400">
            <RiPlayFill /> RUN
          </button>
          <button className="flex items-center gap-2 rounded-lg bg-emerald-500 px-6 py-3 text-[11px] font-black tracking-[0.18em] text-black">
            <RiSave3Line /> SAVE
          </button>
        </div>
        <div className="absolute inset-0 iris-grid-bg" />
        <div className="flex h-full items-center justify-center">
          <div className="text-center">
            <RiCommandLine size={48} className="mx-auto text-zinc-800" />
            <p className="mt-4 text-[10px] font-mono tracking-[0.3em] text-zinc-700">DRAG MODULES FROM SIDEBAR TO BUILD MACROS</p>
            <p className="mt-2 text-[10px] font-mono tracking-[0.2em] text-zinc-800">REACTFLOW EDITOR — COMING SOON</p>
          </div>
        </div>
      </div>
    </div>
  )
}
