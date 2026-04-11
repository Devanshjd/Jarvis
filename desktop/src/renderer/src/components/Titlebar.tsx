import { useMemo } from 'react'
import {
  RiCloseLine,
  RiCheckboxBlankLine,
  RiCheckboxMultipleBlankLine,
  RiSubtractLine
} from 'react-icons/ri'

export default function Titlebar({
  maximized,
  title = 'JARVIS OS // SYSTEM',
  onToggleMax
}: {
  maximized: boolean
  title?: string
  onToggleMax?: () => void
}) {
  const windowLabel = useMemo(() => title.toUpperCase(), [title])

  return (
    <div className="drag-region flex h-8 items-center justify-between border-b border-white/5 bg-zinc-950/90 px-4 backdrop-blur-md">
      <div className="pointer-events-none absolute left-1/2 top-1/2 flex -translate-x-1/2 -translate-y-1/2 items-center gap-2 opacity-65">
        <div className="h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_10px_#10b981] animate-pulse" />
        <div className="text-[11px] font-bold tracking-[0.28em] text-zinc-300">{windowLabel}</div>
      </div>

      <div className="no-drag ml-auto flex h-full">
        <button
          onClick={() => window.desktopApi.windowMin()}
          className="flex h-full w-12 items-center justify-center text-zinc-400 transition-colors hover:bg-white/10 hover:text-white"
        >
          <RiSubtractLine size={16} />
        </button>
        <button
          onClick={() => {
            onToggleMax?.()
            window.desktopApi.windowMax()
          }}
          className="flex h-full w-12 items-center justify-center text-zinc-400 transition-colors hover:bg-white/10 hover:text-white"
        >
          {maximized ? <RiCheckboxMultipleBlankLine size={14} /> : <RiCheckboxBlankLine size={14} />}
        </button>
        <button
          onClick={() => window.desktopApi.windowClose()}
          className="flex h-full w-12 items-center justify-center text-zinc-400 transition-colors hover:bg-red-600 hover:text-white"
        >
          <RiCloseLine size={18} />
        </button>
      </div>
    </div>
  )
}
