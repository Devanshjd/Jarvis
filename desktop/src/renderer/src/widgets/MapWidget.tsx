/**
 * MapWidget — interactive dark-mode map with geocoding search.
 * Uses Nominatim (free) for geocoding and OSM tiles with dark inversion.
 */

import { useState, useCallback } from 'react'
import {
  RiMapPinLine, RiSearchLine, RiLoader4Line,
  RiCrosshairLine, RiZoomInLine, RiZoomOutLine
} from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

interface GeoResult {
  lat: number
  lon: number
  name: string
}

export default function MapWidget({ widget }: { widget: WidgetInstance }) {
  const [query, setQuery] = useState('')
  const [lat, setLat] = useState(51.5074)
  const [lng, setLng] = useState(-0.1278)
  const [zoom, setZoom] = useState(13)
  const [loading, setLoading] = useState(false)
  const [placeName, setPlaceName] = useState('London, UK')
  const [history, setHistory] = useState<GeoResult[]>([])

  const handleSearch = useCallback(async () => {
    if (!query.trim() || loading) return
    setLoading(true)
    try {
      const resp = await fetch(
        `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query.trim())}&format=json&limit=1`,
        { headers: { 'User-Agent': 'JARVIS-Desktop/1.0' } }
      )
      const results = await resp.json()
      if (results.length > 0) {
        const r = results[0]
        const newLat = parseFloat(r.lat)
        const newLon = parseFloat(r.lon)
        setLat(newLat)
        setLng(newLon)
        setPlaceName(r.display_name?.split(',').slice(0, 3).join(',') || query)
        setZoom(14)
        setHistory(prev => [{ lat: newLat, lon: newLon, name: r.display_name?.split(',')[0] || query }, ...prev.slice(0, 4)])
      }
    } catch { /* geocoding failed */ }
    setLoading(false)
    setQuery('')
  }, [query, loading])

  function goToMyLocation() {
    if ('geolocation' in navigator) {
      navigator.geolocation.getCurrentPosition(pos => {
        setLat(pos.coords.latitude)
        setLng(pos.coords.longitude)
        setPlaceName('Current Location')
        setZoom(15)
      })
    }
  }

  const delta = 0.05 * Math.pow(2, 13 - zoom)

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiMapPinLine />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col">
        {/* Search bar */}
        <div className="flex items-center gap-2 border-b border-white/5 bg-black/40 px-3 py-2">
          <RiSearchLine className="text-zinc-500" size={14} />
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
            placeholder="Search location..."
            className="flex-1 bg-transparent text-xs text-zinc-200 outline-none placeholder:text-zinc-600"
          />
          {loading && <RiLoader4Line className="animate-spin text-emerald-400" size={14} />}
        </div>

        {/* Map iframe — dark theme via CSS filter */}
        <div className="relative flex-1">
          <iframe
            title="JARVIS Map"
            className="h-full w-full border-0 opacity-90"
            src={`https://www.openstreetmap.org/export/embed.html?bbox=${lng - delta}%2C${lat - delta}%2C${lng + delta}%2C${lat + delta}&layer=mapnik&marker=${lat}%2C${lng}`}
            style={{ filter: 'invert(1) hue-rotate(180deg) brightness(0.9) contrast(1.1)' }}
          />

          {/* Map controls */}
          <div className="absolute right-2 top-2 flex flex-col gap-1.5">
            <button onClick={goToMyLocation} className="rounded-lg border border-white/10 bg-black/70 p-2 text-zinc-400 backdrop-blur-md hover:text-emerald-400">
              <RiCrosshairLine size={14} />
            </button>
            <button onClick={() => setZoom(z => Math.min(z + 1, 18))} className="rounded-lg border border-white/10 bg-black/70 p-2 text-zinc-400 backdrop-blur-md hover:text-emerald-400">
              <RiZoomInLine size={14} />
            </button>
            <button onClick={() => setZoom(z => Math.max(z - 1, 3))} className="rounded-lg border border-white/10 bg-black/70 p-2 text-zinc-400 backdrop-blur-md hover:text-emerald-400">
              <RiZoomOutLine size={14} />
            </button>
          </div>

          {/* Location info */}
          <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between">
            <div className="rounded-lg border border-white/10 bg-black/70 px-3 py-1.5 backdrop-blur-md">
              <div className="text-[9px] font-bold tracking-[0.14em] text-emerald-400 line-clamp-1">{placeName}</div>
              <div className="text-[8px] font-mono text-zinc-500">{lat.toFixed(4)}, {lng.toFixed(4)}</div>
            </div>
          </div>
        </div>

        {/* Recent searches */}
        {history.length > 0 && (
          <div className="flex items-center gap-1.5 overflow-x-auto border-t border-white/5 bg-black/40 px-3 py-2 scrollbar-small">
            {history.map((h, i) => (
              <button
                key={i}
                onClick={() => { setLat(h.lat); setLng(h.lon); setPlaceName(h.name); }}
                className="shrink-0 rounded-lg border border-white/5 bg-white/[0.03] px-2.5 py-1 text-[9px] font-bold tracking-[0.1em] text-zinc-400 hover:border-emerald-500/20 hover:text-emerald-400"
              >
                {h.name}
              </button>
            ))}
          </div>
        )}
      </div>
    </WidgetShell>
  )
}
