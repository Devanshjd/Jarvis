import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { RiShieldKeyholeLine, RiLockLine, RiDeleteBackLine } from 'react-icons/ri'

type LockScreenProps = {
  onUnlock: () => void
}

const DEFAULT_PIN = '1234'
const PIN_LENGTH = 4

export default function LockScreen({ onUnlock }: LockScreenProps) {
  const [pin, setPin] = useState('')
  const [error, setError] = useState(false)
  const [success, setSuccess] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  function handleDigit(digit: string) {
    if (pin.length >= PIN_LENGTH) return
    const next = pin + digit
    setPin(next)
    setError(false)

    if (next.length === PIN_LENGTH) {
      if (next === DEFAULT_PIN) {
        setSuccess(true)
        setTimeout(() => onUnlock(), 600)
      } else {
        setError(true)
        setTimeout(() => {
          setPin('')
          setError(false)
        }, 800)
      }
    }
  }

  function handleBackspace() {
    setPin((prev) => prev.slice(0, -1))
    setError(false)
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key >= '0' && e.key <= '9') {
      handleDigit(e.key)
    } else if (e.key === 'Backspace') {
      handleBackspace()
    } else if (e.key === 'Enter' && pin.length === PIN_LENGTH) {
      // Already handled in handleDigit
    }
  }

  const padKeys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '', '0', 'back']

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[100] flex flex-col items-center justify-center overflow-hidden"
      style={{
        background: 'radial-gradient(circle at 50% 30%, rgba(16,185,129,0.06), transparent 50%), #000'
      }}
      onKeyDown={handleKeyDown}
      tabIndex={0}
      ref={(el) => el?.focus()}
    >
      {/* Scan line animation */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden opacity-[0.03]">
        <div className="absolute inset-0" style={{
          backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255,255,255,0.5) 2px, rgba(255,255,255,0.5) 4px)',
          backgroundSize: '100% 4px'
        }} />
      </div>

      {/* Top status bar */}
      <div className="absolute top-0 inset-x-0 flex items-center justify-between px-8 py-4">
        <div className="flex items-center gap-2 text-[10px] font-mono tracking-[0.3em] text-zinc-600">
          <div className="h-1.5 w-1.5 rounded-full bg-emerald-500/50 animate-pulse" />
          JARVIS SECURITY PROTOCOL
        </div>
        <div className="text-[10px] font-mono tracking-[0.3em] text-zinc-600">
          {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>

      {/* Shield icon */}
      <motion.div
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ delay: 0.2, type: 'spring', stiffness: 200 }}
        className="mb-8"
      >
        <div className={`rounded-full border-2 p-6 transition-all duration-500 ${
          success
            ? 'border-emerald-400 bg-emerald-500/20 shadow-[0_0_60px_rgba(16,185,129,0.3)]'
            : error
              ? 'border-red-500 bg-red-500/10 shadow-[0_0_40px_rgba(239,68,68,0.2)]'
              : 'border-zinc-700 bg-zinc-900/50'
        }`}>
          {success ? (
            <RiShieldKeyholeLine size={48} className="text-emerald-400" />
          ) : (
            <RiLockLine size={48} className={error ? 'text-red-400' : 'text-zinc-400'} />
          )}
        </div>
      </motion.div>

      {/* Title */}
      <motion.div
        initial={{ y: 10, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.3 }}
        className="mb-2 text-2xl font-black tracking-[0.3em] text-white"
      >
        JARVIS
      </motion.div>

      <motion.div
        initial={{ y: 10, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.4 }}
        className="mb-10 text-[10px] font-mono tracking-[0.4em] text-zinc-500"
      >
        {success ? 'IDENTITY VERIFIED' : error ? 'ACCESS DENIED' : 'AWAITING AUTHORIZATION'}
      </motion.div>

      {/* PIN dots */}
      <div className="mb-8 flex gap-4">
        {Array.from({ length: PIN_LENGTH }).map((_, i) => (
          <motion.div
            key={i}
            animate={{
              scale: pin.length === i ? [1, 1.2, 1] : 1,
              borderColor: error
                ? '#ef4444'
                : success
                  ? '#10b981'
                  : i < pin.length
                    ? '#10b981'
                    : 'rgba(255,255,255,0.15)'
            }}
            transition={{ duration: 0.15 }}
            className="flex h-14 w-14 items-center justify-center rounded-2xl border-2 bg-zinc-950"
          >
            {i < pin.length ? (
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                className={`h-3 w-3 rounded-full ${success ? 'bg-emerald-400' : error ? 'bg-red-400' : 'bg-emerald-400'}`}
              />
            ) : null}
          </motion.div>
        ))}
      </div>

      {/* Number pad */}
      <motion.div
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.5 }}
        className="grid grid-cols-3 gap-3"
      >
        {padKeys.map((key, i) => {
          if (key === '') return <div key={i} />
          if (key === 'back') {
            return (
              <button
                key={i}
                onClick={handleBackspace}
                className="flex h-16 w-16 items-center justify-center rounded-2xl border border-zinc-800 bg-zinc-900/50 text-zinc-400 transition-all hover:border-zinc-600 hover:bg-zinc-800 active:scale-95"
              >
                <RiDeleteBackLine size={20} />
              </button>
            )
          }
          return (
            <button
              key={i}
              onClick={() => handleDigit(key)}
              className="flex h-16 w-16 items-center justify-center rounded-2xl border border-zinc-800 bg-zinc-900/50 text-lg font-bold text-white transition-all hover:border-emerald-500/30 hover:bg-zinc-800 active:scale-95 active:bg-emerald-500/20"
            >
              {key}
            </button>
          )
        })}
      </motion.div>

      {/* Hidden input for keyboard */}
      <input
        ref={inputRef}
        type="text"
        className="absolute opacity-0 pointer-events-none"
        onKeyDown={handleKeyDown}
        autoFocus
      />

      {/* Bottom hint */}
      <div className="absolute bottom-8 text-[10px] font-mono tracking-[0.2em] text-zinc-700">
        DEFAULT PIN: 1234 — CONFIGURE IN SETTINGS
      </div>
    </motion.div>
  )
}
