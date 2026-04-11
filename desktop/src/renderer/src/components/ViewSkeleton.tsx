/**
 * Loading skeleton shown while lazy-loaded views are being imported.
 * Matches IRIS's shimmer + spinner pattern.
 */

import { RiLoader4Line } from 'react-icons/ri'

export default function ViewSkeleton() {
  return (
    <div className="h-full w-full p-8">
      <div className="relative flex h-full w-full flex-col gap-6 overflow-hidden rounded-2xl border border-white/5 bg-zinc-950/40 p-6 shadow-xl backdrop-blur-xl">
        {/* Shimmer sweep */}
        <div className="absolute inset-0 z-10 -translate-x-full animate-[shimmer_2s_infinite] bg-gradient-to-r from-transparent via-white/5 to-transparent" />

        {/* Header skeleton */}
        <div className="flex items-center gap-4 border-b border-white/5 pb-6">
          <div className="h-12 w-12 animate-pulse rounded-xl bg-white/5" />
          <div className="flex flex-col gap-2">
            <div className="h-6 w-48 animate-pulse rounded bg-white/5" />
            <div className="h-3 w-24 animate-pulse rounded bg-white/5" />
          </div>
        </div>

        {/* Content skeleton */}
        <div className="grid flex-1 grid-cols-2 gap-6">
          <div className="h-full animate-pulse rounded-xl bg-white/5 opacity-50" />
          <div className="flex flex-col gap-6">
            <div className="h-32 animate-pulse rounded-xl bg-white/5 opacity-50" />
            <div className="flex-1 animate-pulse rounded-xl bg-white/5 opacity-50" />
          </div>
        </div>

        {/* Centered spinner */}
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-emerald-500/50">
          <RiLoader4Line className="animate-spin text-4xl" />
          <span className="text-[10px] font-mono tracking-[0.3em]">INITIALIZING MODULE...</span>
        </div>
      </div>
    </div>
  )
}
