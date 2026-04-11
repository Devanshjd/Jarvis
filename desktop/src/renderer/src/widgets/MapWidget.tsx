/**
 * MapWidget — interactive dark-mode Leaflet map.
 */

import { useState } from 'react'
import { RiMapPinLine, RiSearchLine } from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

export default function MapWidget({ widget }: { widget: WidgetInstance }) {
  const [query, setQuery] = useState('')
  const [lat, setLat] = useState(51.5074)
  const [lng, setLng] = useState(-0.1278)

  function handleSearch() {
    if (!query.trim()) return
    // For now, use a tile-based approach with an iframe
    const url = `https://www.openstreetmap.org/export/embed.html?bbox=${lng - 0.05},${lat - 0.03},${lng + 0.05},${lat + 0.03}&layer=mapnik&marker=${lat},${lng}`
  }

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiMapPinLine />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col">
        {/* Search bar */}
        <div className="flex items-center gap-2 border-b border-white/5 bg-black/40 px-4 py-2">
          <RiSearchLine className="text-zinc-500" size={14} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Search location..."
            className="flex-1 bg-transparent text-xs text-zinc-200 outline-none placeholder:text-zinc-600"
          />
        </div>

        {/* Map iframe — dark theme via CartoDB */}
        <div className="relative flex-1">
          <iframe
            title="JARVIS Map"
            className="h-full w-full border-0 opacity-90"
            src={`https://www.openstreetmap.org/export/embed.html?bbox=${lng - 0.08}%2C${lat - 0.05}%2C${lng + 0.08}%2C${lat + 0.05}&layer=mapnik`}
            style={{ filter: 'invert(1) hue-rotate(180deg) brightness(0.9) contrast(1.1)' }}
          />
          <div className="absolute bottom-2 right-2 rounded-lg border border-white/10 bg-black/70 px-3 py-1.5 text-[9px] font-mono tracking-[0.18em] text-emerald-400 backdrop-blur-md">
            {lat.toFixed(4)}, {lng.toFixed(4)}
          </div>
        </div>
      </div>
    </WidgetShell>
  )
}
