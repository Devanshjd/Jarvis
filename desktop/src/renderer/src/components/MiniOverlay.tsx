import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  RiCameraLine,
  RiMicLine,
  RiMicOffLine,
  RiPhoneFill,
  RiDragMove2Line,
  RiExpandUpDownLine,
  RiExpandLeftRightFill
} from 'react-icons/ri'

type MiniOverlayProps = {
  voiceActive: boolean
  voiceConnecting: boolean
  micMuted: boolean
  visionActive: boolean
  lastTranscript: string
  onToggleVoice: () => void
  onToggleMic: () => void
  onToggleVision: () => void
  onExpand: () => void
}

export default function MiniOverlay({
  voiceActive,
  voiceConnecting,
  micMuted,
  visionActive,
  lastTranscript,
  onToggleVoice,
  onToggleMic,
  onToggleVision,
  onExpand
}: MiniOverlayProps) {
  const [position, setPosition] = useState({ x: 0, y: 0 })
  const [dragging, setDragging] = useState(false)
  const [showTranscript, setShowTranscript] = useState(false)
  const dragRef = useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null)

  function handleMouseDown(e: React.MouseEvent) {
    setDragging(true)
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      origX: position.x,
      origY: position.y
    }
  }

  useEffect(() => {
    if (!dragging) return

    function handleMouseMove(e: MouseEvent) {
      if (!dragRef.current) return
      setPosition({
        x: dragRef.current.origX + (e.clientX - dragRef.current.startX),
        y: dragRef.current.origY + (e.clientY - dragRef.current.startY)
      })
    }

    function handleMouseUp() {
      setDragging(false)
      dragRef.current = null
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [dragging])

  return (
    <motion.div
      initial={{ y: 40, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      exit={{ y: 40, opacity: 0 }}
      style={{
        position: 'fixed',
        bottom: 24,
        left: '50%',
        transform: `translate(calc(-50% + ${position.x}px), ${position.y}px)`,
        zIndex: 9999
      }}
    >
      <div className="flex flex-col items-center gap-2">
        {/* Transcript bubble */}
        <AnimatePresence>
          {showTranscript && lastTranscript && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              className="max-w-sm rounded-2xl border border-zinc-800 bg-zinc-950/95 px-4 py-3 text-xs text-zinc-300 shadow-[0_8px_40px_rgba(0,0,0,0.6)] backdrop-blur-xl"
            >
              {lastTranscript}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Pill control bar */}
        <div className="flex items-center gap-1 rounded-full border border-zinc-800 bg-zinc-950/95 px-2 py-1.5 shadow-[0_8px_40px_rgba(0,0,0,0.6)] backdrop-blur-xl">
          {/* Drag handle */}
          <div
            onMouseDown={handleMouseDown}
            className="cursor-grab rounded-full p-2 text-zinc-600 transition-colors hover:bg-white/5 hover:text-zinc-400 active:cursor-grabbing"
          >
            <RiDragMove2Line size={14} />
          </div>

          <div className="mx-1 h-4 w-px bg-zinc-800" />

          {/* Vision */}
          <button
            onClick={onToggleVision}
            className={`rounded-full p-2 transition-colors ${visionActive ? 'bg-emerald-500/15 text-emerald-400' : 'text-zinc-500 hover:bg-white/5 hover:text-zinc-300'}`}
          >
            <RiCameraLine size={16} />
          </button>

          {/* Power / Voice */}
          <button
            onClick={onToggleVoice}
            className={`rounded-full p-2.5 transition-all ${
              voiceActive || voiceConnecting
                ? 'bg-emerald-500 text-black shadow-[0_0_14px_rgba(16,185,129,0.4)]'
                : 'bg-red-500/15 text-red-400 hover:bg-red-500/25'
            }`}
          >
            <RiPhoneFill size={16} className={voiceConnecting ? 'animate-pulse' : ''} />
          </button>

          {/* Mic */}
          <button
            onClick={onToggleMic}
            className={`rounded-full p-2 transition-colors ${
              voiceActive && !micMuted
                ? 'bg-emerald-500/15 text-emerald-400'
                : voiceActive && micMuted
                  ? 'bg-red-500/10 text-red-400'
                  : 'text-zinc-500 hover:bg-white/5'
            }`}
          >
            {voiceActive && !micMuted ? <RiMicLine size={16} /> : <RiMicOffLine size={16} />}
          </button>

          <div className="mx-1 h-4 w-px bg-zinc-800" />

          {/* Toggle transcript */}
          <button
            onClick={() => setShowTranscript((v) => !v)}
            className="rounded-full p-2 text-zinc-500 transition-colors hover:bg-white/5 hover:text-zinc-300"
          >
            <RiExpandUpDownLine size={14} />
          </button>

          {/* Expand back to full UI */}
          <button
            onClick={onExpand}
            className="rounded-full p-2 text-zinc-500 transition-colors hover:bg-white/5 hover:text-emerald-400"
          >
            <RiExpandLeftRightFill size={14} />
          </button>
        </div>

        {/* Status line */}
        <div className="text-[8px] font-mono tracking-[0.3em] text-zinc-600">
          {voiceConnecting ? 'CONNECTING' : voiceActive ? (micMuted ? 'MUTED' : 'LIVE') : 'STANDBY'}
        </div>
      </div>
    </motion.div>
  )
}
