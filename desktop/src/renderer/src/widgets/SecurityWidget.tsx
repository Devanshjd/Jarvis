/**
 * SecurityWidget — Cyber Arsenal: port scan, DNS, WHOIS, subdomain, hash ID, IP geo.
 */

import { useState } from 'react'
import {
  RiShieldLine,
  RiRadarLine,
  RiLoader4Line,
  RiGlobalLine,
  RiSearchLine,
  RiFingerprint2Line,
  RiMapPinLine,
  RiServerLine,
  RiTerminalBoxLine,
  RiDeleteBinLine
} from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

type ScanType = 'port_scan' | 'dns_lookup' | 'whois' | 'subdomain' | 'hash_id' | 'ip_geo' | 'nmap'

interface ScanResult {
  id: number
  type: ScanType
  target: string
  output: string
  ts: string
  success: boolean
}

const SCAN_DEFS: Array<{ type: ScanType; label: string; icon: React.ReactNode; placeholder: string }> = [
  { type: 'port_scan', label: 'PORT SCAN', icon: <RiServerLine size={12} />, placeholder: 'IP / domain' },
  { type: 'dns_lookup', label: 'DNS', icon: <RiGlobalLine size={12} />, placeholder: 'domain' },
  { type: 'whois', label: 'WHOIS', icon: <RiSearchLine size={12} />, placeholder: 'domain / IP' },
  { type: 'subdomain', label: 'SUBDOMAINS', icon: <RiRadarLine size={12} />, placeholder: 'domain.com' },
  { type: 'hash_id', label: 'HASH ID', icon: <RiFingerprint2Line size={12} />, placeholder: 'hash string...' },
  { type: 'ip_geo', label: 'GEO', icon: <RiMapPinLine size={12} />, placeholder: 'IP address' },
  { type: 'nmap', label: 'NMAP', icon: <RiTerminalBoxLine size={12} />, placeholder: 'target' },
]

export default function SecurityWidget({ widget }: { widget: WidgetInstance }) {
  const [target, setTarget] = useState('')
  const [scanType, setScanType] = useState<ScanType>('port_scan')
  const [results, setResults] = useState<ScanResult[]>([])
  const [loading, setLoading] = useState(false)

  async function runScan() {
    if (!target.trim() || loading) return
    setLoading(true)
    const t = target.trim()

    try {
      let r: { success: boolean; message?: string; error?: string }

      switch (scanType) {
        case 'port_scan':
          r = await window.desktopApi.toolPortScan(t)
          break
        case 'dns_lookup':
          r = await window.desktopApi.toolDnsLookup(t)
          break
        case 'whois':
          r = await window.desktopApi.toolWhoisLookup(t)
          break
        case 'subdomain':
          r = await window.desktopApi.toolSubdomainEnum(t)
          break
        case 'hash_id':
          r = await window.desktopApi.toolHashIdentify(t)
          break
        case 'ip_geo':
          r = await window.desktopApi.toolIpGeolocation(t)
          break
        case 'nmap':
          r = await window.desktopApi.toolNmapScan(t)
          break
        default:
          r = { success: false, error: 'Unknown scan type' }
      }

      setResults(prev => [{
        id: Date.now(),
        type: scanType,
        target: t,
        output: r.success ? (r.message || 'Done') : `Error: ${r.error}`,
        ts: new Date().toISOString(),
        success: r.success
      }, ...prev])
    } catch (err) {
      setResults(prev => [{
        id: Date.now(),
        type: scanType,
        target: t,
        output: `Error: ${err instanceof Error ? err.message : String(err)}`,
        ts: new Date().toISOString(),
        success: false
      }, ...prev])
    }
    setLoading(false)
  }

  const activeDef = SCAN_DEFS.find(d => d.type === scanType) || SCAN_DEFS[0]

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiShieldLine />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col">
        {/* Controls */}
        <div className="space-y-2.5 border-b border-white/5 bg-black/30 p-3">
          <div className="flex items-center gap-2">
            <input
              value={target}
              onChange={e => setTarget(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && runScan()}
              placeholder={activeDef.placeholder}
              className="flex-1 rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-xs text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-red-500/40"
            />
            <button
              onClick={runScan}
              disabled={loading || !target.trim()}
              className="rounded-xl bg-red-500/80 px-4 py-2 text-[10px] font-black tracking-[0.18em] text-white hover:bg-red-500 disabled:opacity-40"
            >
              {loading ? <RiLoader4Line className="animate-spin" size={14} /> : <RiRadarLine size={14} />}
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {SCAN_DEFS.map(def => (
              <button
                key={def.type}
                onClick={() => setScanType(def.type)}
                className={`flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[8px] font-bold tracking-[0.12em] transition-all ${
                  scanType === def.type
                    ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                    : 'text-zinc-500 border border-white/5 hover:border-white/10 hover:text-zinc-300'
                }`}
              >
                {def.icon} {def.label}
              </button>
            ))}
          </div>
        </div>

        {/* Results */}
        <div className="scrollbar-small flex-1 space-y-2 overflow-y-auto p-3">
          {results.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-zinc-600">
              <RiShieldLine size={28} className="opacity-20" />
              <span className="text-[10px] font-mono tracking-[0.28em]">CYBER ARSENAL READY</span>
              <span className="text-[9px] text-zinc-700">7 tools • Select scan type and enter target</span>
            </div>
          ) : (
            <>
              {results.length > 1 && (
                <button
                  onClick={() => setResults([])}
                  className="mb-1 flex items-center gap-1 text-[9px] font-bold tracking-[0.14em] text-zinc-600 hover:text-red-400"
                >
                  <RiDeleteBinLine size={10} /> CLEAR ALL
                </button>
              )}
              {results.map(r => (
                <div key={r.id} className={`rounded-xl border p-3 ${
                  r.success
                    ? 'border-emerald-500/10 bg-emerald-500/[0.03]'
                    : 'border-red-500/10 bg-red-500/[0.03]'
                }`}>
                  <div className="mb-1 flex items-center justify-between">
                    <span className={`text-[9px] font-bold tracking-[0.14em] ${r.success ? 'text-emerald-400' : 'text-red-400'}`}>
                      {SCAN_DEFS.find(d => d.type === r.type)?.label} // {r.target}
                    </span>
                    <span className="text-[8px] font-mono text-zinc-600">
                      {new Date(r.ts).toLocaleTimeString()}
                    </span>
                  </div>
                  <pre className="mt-1.5 max-h-40 overflow-auto whitespace-pre-wrap text-[10px] leading-5 text-zinc-300 font-mono scrollbar-small">
                    {r.output}
                  </pre>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </WidgetShell>
  )
}
