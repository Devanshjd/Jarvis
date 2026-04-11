import { useState } from 'react'
import {
  RiAndroidLine,
  RiCommandLine,
  RiLinkM,
  RiSmartphoneLine,
  RiWifiLine
} from 'react-icons/ri'

/* ═══════════════════════════════════════════
   Phone View — IRIS-style ADB device control
   ═══════════════════════════════════════════ */

export default function PhoneView({ backendState }: { backendState: string }) {
  const [ip, setIp] = useState('')
  const [port, setPort] = useState('5555')
  const [status, setStatus] = useState<'idle' | 'coming-soon'>('idle')

  return (
    <div className="flex h-full items-center justify-center bg-[#050505] p-10">
      <div className="grid w-full max-w-6xl grid-cols-12 gap-10">
        <div className="col-span-4 flex flex-col gap-6">
          <div className="rounded-3xl border border-emerald-900/40 bg-black p-6">
            <div className="flex items-center gap-4">
              <div className="rounded-xl border border-emerald-400/30 bg-emerald-950/40 p-3">
                <RiAndroidLine className="text-emerald-400" size={24} />
              </div>
              <div>
                <h2 className="text-xl font-bold text-white">Connect Device</h2>
                <p className="mt-1 text-[10px] font-mono tracking-[0.18em] text-emerald-400/70">WIRELESS ADB</p>
              </div>
            </div>
          </div>
          <div className="rounded-3xl border border-emerald-900/40 bg-zinc-950 p-6">
            <div className="mt-2 space-y-4">
              <label className="block">
                <div className="mb-2 text-xs font-bold tracking-[0.16em] text-emerald-300/80">IP ADDRESS</div>
                <div className="flex items-center rounded-xl border border-emerald-900/50 bg-black px-4 py-4 text-sm font-mono text-emerald-400">
                  <RiWifiLine className="mr-3" />
                  <input value={ip} onChange={(e) => setIp(e.target.value)} placeholder="192.168.1.xxx" className="w-full bg-transparent outline-none placeholder:text-emerald-900" />
                </div>
              </label>
              <label className="block">
                <div className="mb-2 text-xs font-bold tracking-[0.16em] text-emerald-300/80">PORT</div>
                <div className="flex items-center rounded-xl border border-emerald-900/50 bg-black px-4 py-4 text-sm font-mono text-emerald-400">
                  <RiLinkM className="mr-3" />
                  <input value={port} onChange={(e) => setPort(e.target.value)} placeholder="5555" className="w-full bg-transparent outline-none placeholder:text-emerald-900" />
                </div>
              </label>
              <button onClick={() => setStatus('coming-soon')} className="w-full rounded-xl border border-emerald-400/50 bg-emerald-950 py-4 text-xs font-black tracking-[0.18em] text-emerald-300 transition-colors hover:bg-emerald-400 hover:text-black">
                CONNECT SECURELY
              </button>
            </div>
          </div>
        </div>

        <div className="col-span-4 flex items-center justify-center">
          <div className="h-[620px] w-[310px] rounded-[3rem] border-[10px] border-zinc-800 bg-zinc-950 shadow-2xl">
            <div className="relative flex h-full items-center justify-center overflow-hidden rounded-[2.2rem] bg-gradient-to-b from-emerald-950/20 to-black">
              <div className="absolute top-0 left-1/2 h-6 w-28 -translate-x-1/2 rounded-b-xl bg-zinc-800" />
              <RiSmartphoneLine size={72} className="text-emerald-900" />
              <div className="absolute bottom-28 text-[10px] font-mono tracking-[0.28em] text-emerald-900">
                {status === 'coming-soon' ? 'ADB LAYER NEXT' : 'AWAITING TARGET'}
              </div>
            </div>
          </div>
        </div>

        <div className="col-span-4">
          <div className="flex h-full flex-col rounded-3xl border border-white/5 bg-[#111] p-6">
            <div className="mb-8 border-b border-white/5 pb-4">
              <h3 className="text-xs font-bold tracking-[0.18em] text-white">DEVICE LINK STACK</h3>
              <p className="mt-2 text-[10px] font-mono tracking-[0.16em] text-zinc-500">BACKEND {backendState} // MOBILE SESSION STANDBY</p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              {[['ADB', 'PENDING'], ['SCREEN', 'OFF'], ['NOTIFS', 'OFF'], ['TOOLS', 'NEXT']].map(([item, value]) => (
                <div key={item} className="flex min-h-32 flex-col items-center justify-center rounded-2xl border border-white/5 bg-black/50 p-6 text-center">
                  <RiCommandLine className="mb-3 text-zinc-500" size={24} />
                  <span className="text-[10px] font-bold tracking-[0.18em] text-zinc-200">{item}</span>
                  <span className="mt-3 text-[10px] font-mono tracking-[0.2em] text-emerald-400">{value}</span>
                </div>
              ))}
            </div>
            <div className="mt-6 rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-4 text-[11px] leading-6 text-emerald-100/80">
              ADB wireless connection, live screen streaming, and touch simulation will be wired behind this view.
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
