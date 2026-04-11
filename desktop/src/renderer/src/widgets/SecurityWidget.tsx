/**
 * SecurityWidget — pentest dashboard: recon, port scan, vuln scan.
 */

import { useState } from 'react'
import { RiShieldLine, RiRadarLine, RiSendPlaneFill, RiLoader4Line } from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

const API_BASE = 'http://127.0.0.1:8765'

type ScanType = 'recon' | 'port_scan' | 'vuln_scan' | 'subdomain'

interface ScanResult { id: number; type: ScanType; target: string; output: string; ts: string }

const SCAN_LABELS: Record<ScanType, string> = {
  recon: 'Reconnaissance', port_scan: 'Port Scan', vuln_scan: 'Vulnerability Scan', subdomain: 'Subdomain Enum'
}

export default function SecurityWidget({ widget }: { widget: WidgetInstance }) {
  const [target, setTarget] = useState('')
  const [scanType, setScanType] = useState<ScanType>('recon')
  const [results, setResults] = useState<ScanResult[]>([])
  const [loading, setLoading] = useState(false)

  async function runScan() {
    if (!target.trim() || loading) return
    setLoading(true)
    const commands: Record<ScanType, string> = {
      recon: `perform reconnaissance on ${target}`,
      port_scan: `scan ports on ${target}`,
      vuln_scan: `scan for vulnerabilities on ${target}`,
      subdomain: `enumerate subdomains for ${target}`,
    }
    try {
      const resp = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: commands[scanType], approve_desktop: true, timeout_s: 120 })
      })
      const data = await resp.json()
      setResults((prev) => [{
        id: Date.now(), type: scanType, target, output: data.reply || 'Scan completed.', ts: new Date().toISOString()
      }, ...prev])
    } catch (err) {
      setResults((prev) => [{
        id: Date.now(), type: scanType, target, output: `Error: ${err instanceof Error ? err.message : String(err)}`, ts: new Date().toISOString()
      }, ...prev])
    }
    setLoading(false)
  }

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiShieldLine />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col">
        {/* Controls */}
        <div className="space-y-2 border-b border-white/5 bg-black/30 p-4">
          <div className="flex items-center gap-2">
            <input value={target} onChange={(e) => setTarget(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && runScan()}
              placeholder="Target (domain / IP)..." className="flex-1 rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-xs text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-red-500/40" />
            <button onClick={runScan} disabled={loading} className="rounded-xl bg-red-500/80 px-4 py-2 text-[10px] font-black tracking-[0.18em] text-white hover:bg-red-500 disabled:opacity-40">
              {loading ? <RiLoader4Line className="animate-spin" size={14} /> : <RiRadarLine size={14} />}
            </button>
          </div>
          <div className="flex gap-1.5">
            {(['recon', 'port_scan', 'vuln_scan', 'subdomain'] as ScanType[]).map((type) => (
              <button key={type} onClick={() => setScanType(type)}
                className={`rounded-lg px-3 py-1.5 text-[9px] font-bold tracking-[0.14em] transition-all ${scanType === type ? 'bg-red-500/20 text-red-400 border border-red-500/30' : 'text-zinc-500 border border-white/5 hover:border-white/10 hover:text-zinc-300'}`}>
                {SCAN_LABELS[type].toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {/* Results */}
        <div className="scrollbar-small flex-1 space-y-3 overflow-y-auto p-4">
          {results.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-zinc-600">
              <RiShieldLine size={32} className="opacity-20" />
              <span className="text-[10px] font-mono tracking-[0.28em]">SECURITY SCANNER READY</span>
              <span className="text-[9px] text-zinc-700">Enter a target and select scan type</span>
            </div>
          ) : results.map((r) => (
            <div key={r.id} className="rounded-xl border border-red-500/10 bg-red-500/[0.03] p-4">
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[10px] font-bold tracking-[0.16em] text-red-400">{SCAN_LABELS[r.type]} // {r.target}</span>
                <span className="text-[9px] font-mono text-zinc-600">{new Date(r.ts).toLocaleTimeString()}</span>
              </div>
              <div className="mt-2 text-xs leading-6 text-zinc-300 whitespace-pre-wrap font-mono">{r.output}</div>
            </div>
          ))}
        </div>
      </div>
    </WidgetShell>
  )
}
