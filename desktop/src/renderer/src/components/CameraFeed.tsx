import { useEffect, useRef, useState } from 'react'
import { RiCameraLine, RiComputerLine } from 'react-icons/ri'

type CameraFeedProps = {
  source: 'none' | 'camera' | 'screen'
  onStreamReady?: (stream: MediaStream | null) => void
}

/**
 * Live camera/screen feed with IRIS-style corner bracket overlays.
 */
export default function CameraFeed({ source, onStreamReady }: CameraFeedProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [active, setActive] = useState(false)
  const [error, setError] = useState('')
  const streamRef = useRef<MediaStream | null>(null)

  useEffect(() => {
    let cancelled = false

    async function startFeed() {
      // Cleanup previous
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop())
        streamRef.current = null
      }

      if (source === 'none') {
        setActive(false)
        onStreamReady?.(null)
        return
      }

      try {
        let stream: MediaStream

        if (source === 'camera') {
          stream = await navigator.mediaDevices.getUserMedia({
            video: { width: 640, height: 480, facingMode: 'user' },
            audio: false
          })
        } else {
          // Screen capture via Electron
          const sourceId = await window.desktopApi.getScreenSource()
          if (!sourceId) throw new Error('No screen source available')
          stream = await navigator.mediaDevices.getUserMedia({
            audio: false,
            video: {
              // @ts-expect-error Electron desktop capture Chromium-only constraints
              mandatory: {
                chromeMediaSource: 'desktop',
                chromeMediaSourceId: sourceId,
                maxWidth: 1280,
                maxHeight: 720,
                maxFrameRate: 6
              }
            }
          })
        }

        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }

        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          await videoRef.current.play()
        }
        setActive(true)
        setError('')
        onStreamReady?.(stream)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err))
          setActive(false)
          onStreamReady?.(null)
        }
      }
    }

    void startFeed()

    return () => {
      cancelled = true
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop())
        streamRef.current = null
      }
    }
  }, [source])

  if (source === 'none' || (!active && !error)) {
    return (
      <div className="relative flex h-full flex-col items-center justify-center overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950">
        <div className="absolute left-3 top-3 z-10 flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-zinc-600" />
          <span className="text-[9px] font-bold tracking-[0.28em] text-zinc-600">OPTICAL FEED</span>
        </div>
        <RiCameraLine size={28} className="text-zinc-700" />
        <span className="mt-3 text-[10px] font-mono tracking-[0.3em] text-zinc-700">NO SIGNAL</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="relative flex h-full flex-col items-center justify-center overflow-hidden rounded-2xl border border-red-500/20 bg-zinc-950">
        <div className="absolute left-3 top-3 z-10 flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
          <span className="text-[9px] font-bold tracking-[0.28em] text-red-400">FEED ERROR</span>
        </div>
        <RiCameraLine size={28} className="text-red-500/50" />
        <span className="mt-3 max-w-[80%] text-center text-[10px] font-mono text-red-400/60">{error}</span>
      </div>
    )
  }

  const label = source === 'camera' ? 'OPTICAL FEED' : 'SCREEN FEED'
  const Icon = source === 'camera' ? RiCameraLine : RiComputerLine
  const mirrored = source === 'camera'

  return (
    <div className="relative h-full overflow-hidden rounded-2xl border border-zinc-800 bg-black">
      {/* Status label */}
      <div className="absolute left-3 top-3 z-10 flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
        <span className="text-[9px] font-bold tracking-[0.28em] text-emerald-400">{label}</span>
      </div>

      <div className="absolute right-3 top-3 z-10">
        <Icon size={14} className="text-emerald-500/40" />
      </div>

      {/* Video */}
      <video
        ref={videoRef}
        muted
        playsInline
        className="h-full w-full object-cover"
        style={mirrored ? { transform: 'scaleX(-1)' } : undefined}
      />

      {/* Corner brackets overlay — IRIS signature */}
      <CornerBrackets />

      {/* Scan line */}
      <div className="pointer-events-none absolute inset-0 opacity-[0.04]" style={{
        backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(16,185,129,0.5) 2px, rgba(16,185,129,0.5) 3px)',
        backgroundSize: '100% 3px'
      }} />
    </div>
  )
}

function CornerBrackets() {
  const bracketClass = 'absolute w-6 h-6 border-emerald-500/40'

  return (
    <div className="pointer-events-none absolute inset-4 z-10">
      {/* Top-left */}
      <div className={`${bracketClass} top-0 left-0 border-t-2 border-l-2`} />
      {/* Top-right */}
      <div className={`${bracketClass} top-0 right-0 border-t-2 border-r-2`} />
      {/* Bottom-left */}
      <div className={`${bracketClass} bottom-0 left-0 border-b-2 border-l-2`} />
      {/* Bottom-right */}
      <div className={`${bracketClass} bottom-0 right-0 border-b-2 border-r-2`} />
    </div>
  )
}
