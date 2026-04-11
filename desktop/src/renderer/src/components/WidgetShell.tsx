/**
 * WidgetShell — reusable floating container for IRIS-style widgets.
 * Draggable, closable, minimizable with glassmorphism styling.
 */

import { useRef, useCallback, type ReactNode } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { RiCloseLine, RiSubtractLine } from 'react-icons/ri'
import { useStore } from '../store/useStore'

interface WidgetShellProps {
  id: string
  title: string
  icon?: ReactNode
  children: ReactNode
  width?: number
  height?: number
  x?: number
  y?: number
  minimized?: boolean
  className?: string
}

export default function WidgetShell({
  id, title, icon, children, width = 400, height = 320, x = 100, y = 100, minimized = false, className = ''
}: WidgetShellProps) {
  const closeWidget = useStore((s) => s.closeWidget)
  const minimizeWidget = useStore((s) => s.minimizeWidget)
  const moveWidget = useStore((s) => s.moveWidget)

  const dragRef = useRef<{ startX: number; startY: number; originX: number; originY: number } | null>(null)
  const shellRef = useRef<HTMLDivElement>(null)

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault()
    const target = e.target as HTMLElement
    if (target.closest('button') || target.closest('input') || target.closest('textarea') || target.closest('select')) return
    dragRef.current = { startX: e.clientX, startY: e.clientY, originX: x, originY: y }
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
  }, [x, y])

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragRef.current) return
    const dx = e.clientX - dragRef.current.startX
    const dy = e.clientY - dragRef.current.startY
    moveWidget(id, dragRef.current.originX + dx, dragRef.current.originY + dy)
  }, [id, moveWidget])

  const onPointerUp = useCallback(() => {
    dragRef.current = null
  }, [])

  return (
    <AnimatePresence>
      {!minimized && (
        <motion.div
          ref={shellRef}
          initial={{ opacity: 0, scale: 0.92, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.92, y: 12 }}
          transition={{ type: 'spring', stiffness: 320, damping: 28 }}
          className={`fixed z-50 flex flex-col overflow-hidden rounded-2xl border border-white/8 bg-[#0a0c0e]/88 shadow-[0_24px_80px_rgba(0,0,0,0.65)] backdrop-blur-xl ${className}`}
          style={{ left: x, top: y, width, height }}
        >
          {/* Title bar — draggable */}
          <div
            className="flex h-10 shrink-0 cursor-grab items-center justify-between border-b border-white/6 bg-white/[0.03] px-4 active:cursor-grabbing"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
          >
            <div className="flex items-center gap-2">
              {icon && <span className="text-emerald-400 text-sm">{icon}</span>}
              <span className="text-[10px] font-bold tracking-[0.24em] text-zinc-400 select-none">{title.toUpperCase()}</span>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => minimizeWidget(id)}
                className="rounded-md p-1 text-zinc-500 transition-colors hover:bg-white/10 hover:text-zinc-300"
              >
                <RiSubtractLine size={14} />
              </button>
              <button
                onClick={() => closeWidget(id)}
                className="rounded-md p-1 text-zinc-500 transition-colors hover:bg-red-500/20 hover:text-red-400"
              >
                <RiCloseLine size={14} />
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-hidden">
            {children}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
