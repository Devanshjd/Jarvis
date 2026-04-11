/**
 * StockWidget — real-time financial ticker tracking.
 */

import { useState } from 'react'
import { RiStockLine, RiSearchLine, RiArrowUpLine, RiArrowDownLine } from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

const API_BASE = 'http://127.0.0.1:8765'

interface StockData {
  symbol: string
  price: number
  change: number
  changePercent: number
}

export default function StockWidget({ widget }: { widget: WidgetInstance }) {
  const [symbol, setSymbol] = useState('')
  const [stocks, setStocks] = useState<StockData[]>([
    { symbol: 'AAPL', price: 198.45, change: 2.34, changePercent: 1.19 },
    { symbol: 'GOOGL', price: 175.23, change: -1.12, changePercent: -0.64 },
    { symbol: 'MSFT', price: 420.87, change: 5.67, changePercent: 1.37 },
  ])
  const [loading, setLoading] = useState(false)

  async function addStock() {
    if (!symbol.trim()) return
    setLoading(true)
    try {
      const resp = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: `Get the current stock price for ${symbol.toUpperCase()}. Respond with ONLY JSON: {"symbol":"${symbol.toUpperCase()}","price":0,"change":0,"changePercent":0}`,
          approve_desktop: false, timeout_s: 30
        })
      })
      const data = await resp.json()
      const match = (data.reply || '').match(/\{[\s\S]*?\}/)
      if (match) {
        const stockData = JSON.parse(match[0])
        setStocks((prev) => [...prev.filter((s) => s.symbol !== stockData.symbol), stockData])
      }
    } catch { /* */ }
    setSymbol('')
    setLoading(false)
  }

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiStockLine />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col p-4">
        {/* Search */}
        <div className="mb-3 flex items-center gap-2">
          <div className="flex flex-1 items-center gap-2 rounded-xl border border-white/10 bg-black/40 px-3 py-2">
            <RiSearchLine className="text-zinc-500" size={14} />
            <input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} onKeyDown={(e) => e.key === 'Enter' && addStock()}
              placeholder="TICKER..." className="flex-1 bg-transparent text-xs font-mono text-zinc-200 outline-none placeholder:text-zinc-600" />
          </div>
          <button onClick={addStock} disabled={loading} className="rounded-xl bg-emerald-500 px-4 py-2 text-[10px] font-black tracking-[0.18em] text-black">
            {loading ? '...' : 'ADD'}
          </button>
        </div>

        {/* Stock list */}
        <div className="scrollbar-small flex-1 space-y-2 overflow-y-auto">
          {stocks.map((stock) => (
            <div key={stock.symbol} className="flex items-center justify-between rounded-xl border border-white/5 bg-white/[0.02] px-4 py-3">
              <div>
                <div className="text-sm font-black text-white">{stock.symbol}</div>
                <div className="text-[10px] font-mono text-zinc-500">EQUITY</div>
              </div>
              <div className="text-right">
                <div className="text-lg font-bold text-white">${stock.price.toFixed(2)}</div>
                <div className={`flex items-center justify-end gap-1 text-xs font-bold ${stock.change >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {stock.change >= 0 ? <RiArrowUpLine size={12} /> : <RiArrowDownLine size={12} />}
                  {stock.change >= 0 ? '+' : ''}{stock.change.toFixed(2)} ({stock.changePercent.toFixed(2)}%)
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </WidgetShell>
  )
}
