import { useEffect, useMemo, useState } from 'react'
import {
  RiCloseCircleLine,
  RiLock2Line,
  RiRefreshLine,
  RiShieldCheckLine,
  RiSmartphoneLine,
  RiTimeLine,
  RiWifiLine
} from 'react-icons/ri'
import { API_BASE, fetchJson } from '../lib/types'

type TailscaleStatus = {
  installed: boolean
  up: boolean
  ip: string | null
  magicdns: string | null
}

type NetworkStatus = {
  remote_enabled: boolean
  tailscale: TailscaleStatus
  paired: number
}

type PairedDevice = {
  id: string
  name: string
  created: string | null
  last_seen: string | null
  enabled: boolean
  scope: 'phone' | string
}

type DeviceList = {
  remote_enabled: boolean
  devices: PairedDevice[]
}

type PairStart = {
  code?: string
  expires_at?: string
  ttl_seconds?: number
  url?: string | null
  magicdns?: string | null
  tailscale_up?: boolean
  error?: string
}

function formatTime(value: string | null): string {
  if (!value) return 'NEVER SEEN'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'UNKNOWN' : date.toLocaleString()
}

function pairingTime(seconds: number): string {
  const safe = Math.max(0, seconds)
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, '0')}`
}

export default function PhoneView({ backendState }: { backendState: string }) {
  const [network, setNetwork] = useState<NetworkStatus | null>(null)
  const [devices, setDevices] = useState<PairedDevice[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [pairing, setPairing] = useState<PairStart | null>(null)
  const [pairingSeconds, setPairingSeconds] = useState(0)
  const [startingPairing, setStartingPairing] = useState(false)
  const [revoking, setRevoking] = useState<string | null>(null)

  const refresh = async (): Promise<void> => {
    setError('')
    try {
      const [nextNetwork, nextDevices] = await Promise.all([
        fetchJson<NetworkStatus>(`${API_BASE}/api/devices/network`),
        fetchJson<DeviceList>(`${API_BASE}/api/devices`)
      ])
      setNetwork(nextNetwork)
      setDevices(Array.isArray(nextDevices.devices) ? nextDevices.devices : [])
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setNetwork(null)
      setDevices([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
    const interval = window.setInterval(() => void refresh(), 10_000)
    return () => window.clearInterval(interval)
  }, [])

  useEffect(() => {
    if (pairingSeconds <= 0) return
    const interval = window.setInterval(() => {
      setPairingSeconds((seconds) => Math.max(0, seconds - 1))
    }, 1000)
    return () => window.clearInterval(interval)
  }, [pairingSeconds])

  const reachable = Boolean(network?.remote_enabled && network.tailscale.installed && network.tailscale.up && network.tailscale.magicdns)
  const remoteState = !network
    ? { label: loading ? 'CHECKING' : 'UNAVAILABLE', tone: 'text-zinc-500 border-zinc-700 bg-zinc-900/40' }
    : !network.remote_enabled
      ? { label: 'REMOTE OFF', tone: 'text-zinc-500 border-zinc-700 bg-zinc-900/40' }
      : !network.tailscale.installed
        ? { label: 'TAILSCALE NOT INSTALLED', tone: 'text-amber-200 border-amber-500/25 bg-amber-500/5' }
        : !network.tailscale.up
          ? { label: 'TAILSCALE OFFLINE', tone: 'text-amber-200 border-amber-500/25 bg-amber-500/5' }
          : !network.tailscale.magicdns
            ? { label: 'NO TAILNET ADDRESS', tone: 'text-amber-200 border-amber-500/25 bg-amber-500/5' }
            : { label: 'PRIVATE LINK READY', tone: 'text-emerald-200 border-emerald-500/25 bg-emerald-500/5' }

  const pairDisabledReason = useMemo(() => {
    if (!network?.remote_enabled) return 'Remote access is off. Start JARVIS with JARVIS_REMOTE=1 when you are ready to pair.'
    if (!network.tailscale.installed) return 'Install Tailscale on this laptop and your phone first.'
    if (!network.tailscale.up || !network.tailscale.magicdns) return 'Sign in to Tailscale and wait for a tailnet address before pairing.'
    return ''
  }, [network])

  async function startPairing(): Promise<void> {
    if (!reachable) return
    setStartingPairing(true)
    setError('')
    try {
      const result = await fetchJson<PairStart>(`${API_BASE}/api/devices/pair/start`, { method: 'POST' })
      if (!result.code || result.error) throw new Error(result.error || 'The pairing code was not created.')
      setPairing(result)
      setPairingSeconds(Math.max(0, Number(result.ttl_seconds) || 300))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setStartingPairing(false)
    }
  }

  async function revoke(deviceId: string, name: string): Promise<void> {
    if (!window.confirm(`Revoke ${name}? That phone will lose access immediately.`)) return
    setRevoking(deviceId)
    setError('')
    try {
      const result = await fetchJson<{ revoked?: boolean }>(`${API_BASE}/api/devices/revoke`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: deviceId })
      })
      if (!result.revoked) throw new Error('The device was not found or could not be revoked.')
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setRevoking(null)
    }
  }

  async function revokeAll(): Promise<void> {
    if (!devices.length || !window.confirm('Revoke every paired phone? This takes effect immediately.')) return
    setRevoking('all')
    setError('')
    try {
      const result = await fetchJson<{ revoked_all?: number }>(`${API_BASE}/api/devices/revoke`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: 'all' })
      })
      if (result.revoked_all == null) throw new Error('Could not revoke the paired phones.')
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setRevoking(null)
    }
  }

  return (
    <div className="h-full overflow-y-auto bg-[#050505] px-6 py-8 lg:px-10">
      <div className="mx-auto w-full max-w-6xl">
        <div className="mb-8 flex flex-col gap-5 border-b border-white/10 pb-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <div className="rounded-2xl border border-emerald-500/25 bg-emerald-500/5 p-4"><RiSmartphoneLine size={30} className="text-emerald-300" /></div>
            <div>
              <h2 className="text-3xl font-black tracking-tight text-white">Private Phone Link</h2>
              <p className="mt-1 text-[10px] font-mono tracking-[0.18em] text-zinc-500">TAILSCALE INGRESS // PHONE SCOPE ONLY</p>
            </div>
          </div>
          <div className={`rounded-xl border px-3 py-2 text-[10px] font-mono tracking-[0.14em] ${remoteState.tone}`}>{remoteState.label}</div>
        </div>

        {error ? <div className="mb-6 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-[11px] leading-5 text-red-200">{error}</div> : null}

        <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <section className="space-y-6">
            <div className="stormbreaker-setting-card">
              <div className="flex flex-col gap-4 border-b border-white/10 pb-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="stormbreaker-setting-title"><RiWifiLine /> Tailnet Status</div>
                  <p className="mt-2 text-[11px] leading-5 text-zinc-500">FastAPI remains on localhost. Tailscale Serve is the only private route from your phone.</p>
                </div>
                <button type="button" onClick={() => void refresh()} className="inline-flex items-center gap-2 self-start rounded-lg border border-white/10 px-3 py-2 text-[9px] font-mono tracking-[0.12em] text-zinc-400 transition-colors hover:border-zinc-500 hover:text-white"><RiRefreshLine /> REFRESH</button>
              </div>
              <div className="mt-5 grid gap-3 sm:grid-cols-3">
                <div className="rounded-xl border border-white/10 bg-black/25 px-4 py-3"><p className="text-[8px] font-mono tracking-[0.15em] text-zinc-600">REMOTE FLAG</p><p className={`mt-2 text-[11px] font-bold tracking-[0.12em] ${network?.remote_enabled ? 'text-emerald-300' : 'text-zinc-500'}`}>{network?.remote_enabled ? 'ENABLED' : 'OFF'}</p></div>
                <div className="rounded-xl border border-white/10 bg-black/25 px-4 py-3"><p className="text-[8px] font-mono tracking-[0.15em] text-zinc-600">TAILSCALE</p><p className={`mt-2 text-[11px] font-bold tracking-[0.12em] ${network?.tailscale.up ? 'text-emerald-300' : 'text-zinc-500'}`}>{network?.tailscale.up ? 'CONNECTED' : network?.tailscale.installed ? 'OFFLINE' : 'NOT INSTALLED'}</p></div>
                <div className="rounded-xl border border-white/10 bg-black/25 px-4 py-3"><p className="text-[8px] font-mono tracking-[0.15em] text-zinc-600">PAIRED PHONES</p><p className="mt-2 text-[11px] font-bold tracking-[0.12em] text-zinc-200">{network?.paired ?? 0}</p></div>
              </div>
              {network?.tailscale.ip || network?.tailscale.magicdns ? <div className="mt-4 rounded-xl border border-white/10 bg-black/25 px-4 py-3 text-[10px] font-mono leading-5 text-zinc-500"><p>TAILNET IP: <span className="text-zinc-300">{network.tailscale.ip || 'UNKNOWN'}</span></p><p>MAGICDNS: <span className="text-zinc-300">{network.tailscale.magicdns || 'UNKNOWN'}</span></p></div> : null}
            </div>

            <div className="stormbreaker-setting-card">
              <div className="flex items-start gap-3 border-b border-white/10 pb-4"><RiShieldCheckLine size={19} className="mt-0.5 text-emerald-300" /><div><div className="stormbreaker-setting-title">Pair a Phone</div><p className="mt-2 text-[11px] leading-5 text-zinc-500">Pairing starts here, expires in five minutes, and can only grant a phone the safe access scope.</p></div></div>
              {!pairing || pairingSeconds === 0 ? <div className="mt-5"><button type="button" disabled={!reachable || startingPairing} onClick={() => void startPairing()} className="w-full rounded-xl border border-emerald-500/35 bg-emerald-500/10 px-4 py-3 text-[10px] font-black tracking-[0.16em] text-emerald-200 transition-colors hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-45">{startingPairing ? 'CREATING PAIRING CODE' : 'START PHONE PAIRING'}</button><p className="mt-3 text-[10px] leading-5 text-zinc-600">{pairDisabledReason || 'A one-time code is created only after the private link is genuinely ready.'}</p></div> : <div className="mt-5 rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-5"><div className="flex items-center justify-between text-[9px] font-mono tracking-[0.14em]"><span className="text-zinc-500">ONE-TIME PAIRING CODE</span><span className="flex items-center gap-1 text-amber-200"><RiTimeLine /> {pairingTime(pairingSeconds)}</span></div><div className="mt-3 text-center text-5xl font-black tracking-[0.22em] text-emerald-200">{pairing.code}</div><p className="mt-4 break-all rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-[10px] leading-5 text-zinc-400">On the phone, open: <span className="text-zinc-200">{pairing.url || 'No tailnet URL was returned.'}</span></p><p className="mt-3 text-[10px] leading-5 text-zinc-600">The phone client must submit this code once. JARVIS never displays or stores that phone’s raw access token here.</p><button type="button" onClick={() => { setPairing(null); setPairingSeconds(0) }} className="mt-4 text-[9px] font-mono tracking-[0.12em] text-zinc-500 hover:text-zinc-200">DISMISS CODE</button></div>}
            </div>
          </section>

          <aside className="space-y-6">
            <div className="stormbreaker-setting-card">
              <div className="stormbreaker-setting-title"><RiLock2Line /> Phone Scope</div>
              <div className="mt-4 space-y-3 text-[11px] leading-5"><p className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-emerald-100">ALLOWED: chat, runtime status, and voice.</p><p className="rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2 text-red-200">DENIED: desktop control, terminal, settings, job data, self-modification, and device management.</p></div>
              <p className="mt-4 text-[10px] leading-5 text-zinc-600">A lost phone can talk to JARVIS; it cannot operate your PC.</p>
            </div>
            <div className="stormbreaker-setting-card">
              <div className="mb-4 flex items-center justify-between"><div className="stormbreaker-setting-title"><RiSmartphoneLine /> Paired Devices</div>{devices.length > 0 ? <button type="button" disabled={revoking !== null} onClick={() => void revokeAll()} className="text-[8px] font-mono tracking-[0.12em] text-red-300 hover:text-red-100 disabled:opacity-45">REVOKE ALL</button> : null}</div>
              {devices.length === 0 ? <p className="rounded-xl border border-white/10 bg-black/25 px-4 py-6 text-center text-[10px] font-mono tracking-[0.12em] text-zinc-600">NO PAIRED PHONES</p> : <div className="space-y-3">{devices.map((device) => <div key={device.id} className="rounded-xl border border-white/10 bg-black/25 px-4 py-3"><div className="flex items-start justify-between gap-3"><div><p className="text-[11px] font-bold tracking-[0.08em] text-zinc-100">{device.name}</p><p className="mt-1 text-[8px] font-mono tracking-[0.12em] text-zinc-600">SCOPE: {device.scope.toUpperCase()}</p></div><button type="button" disabled={revoking !== null} onClick={() => void revoke(device.id, device.name)} className="rounded border border-red-500/25 px-2 py-1 text-[8px] font-mono tracking-[0.1em] text-red-200 transition-colors hover:bg-red-500/10 disabled:opacity-45">{revoking === device.id ? 'REVOKING' : <><RiCloseCircleLine className="mr-1 inline" />REVOKE</>}</button></div><p className="mt-3 text-[9px] leading-5 text-zinc-600">LAST SEEN: {formatTime(device.last_seen)}</p></div>)}</div>}
            </div>
          </aside>
        </div>

        <p className="mx-auto mt-8 max-w-3xl text-center text-[10px] leading-5 text-zinc-600">Backend: {backendState}. The phone PWA is a separate delivery step: it must be served through the private Tailscale URL before a phone can submit a pairing code. This screen deliberately does not claim that client exists yet.</p>
      </div>
    </div>
  )
}
