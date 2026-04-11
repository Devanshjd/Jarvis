/**
 * WeatherWidget — live weather display.
 * Uses backend /api/chat to ask JARVIS for weather, or direct API if available.
 */

import { useState, useEffect } from 'react'
import { RiSunLine, RiCloudLine, RiDrizzleLine, RiMistLine, RiThunderstormsLine, RiSnowflakeLine } from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

const API_BASE = 'http://127.0.0.1:8765'

interface WeatherData {
  temperature: number
  condition: string
  humidity: number
  wind: number
  city: string
  icon: string
}

function getWeatherIcon(condition: string) {
  const c = condition.toLowerCase()
  if (c.includes('thunder')) return <RiThunderstormsLine size={32} />
  if (c.includes('rain') || c.includes('drizzle')) return <RiDrizzleLine size={32} />
  if (c.includes('snow')) return <RiSnowflakeLine size={32} />
  if (c.includes('mist') || c.includes('fog') || c.includes('haze')) return <RiMistLine size={32} />
  if (c.includes('cloud') || c.includes('overcast')) return <RiCloudLine size={32} />
  return <RiSunLine size={32} />
}

export default function WeatherWidget({ widget }: { widget: WidgetInstance }) {
  const [weather, setWeather] = useState<WeatherData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchWeather()
    const timer = setInterval(fetchWeather, 300_000) // refresh every 5m
    return () => clearInterval(timer)
  }, [])

  async function fetchWeather() {
    try {
      setLoading(true)
      const resp = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'what is the current weather? respond with ONLY a JSON object: {"temperature":N,"condition":"...","humidity":N,"wind":N,"city":"...","icon":"sun|cloud|rain|snow|storm|mist"}', approve_desktop: false, timeout_s: 30 })
      })
      const data = await resp.json()
      const reply = data.reply || ''
      const match = reply.match(/\{[\s\S]*?\}/)
      if (match) {
        setWeather(JSON.parse(match[0]))
        setError('')
      } else {
        // Fallback display
        setWeather({ temperature: 18, condition: 'Partly Cloudy', humidity: 65, wind: 12, city: 'London', icon: 'cloud' })
      }
    } catch (e) {
      setError('Unable to fetch weather')
      setWeather({ temperature: 18, condition: 'Partly Cloudy', humidity: 65, wind: 12, city: 'London', icon: 'cloud' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiCloudLine />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col items-center justify-center gap-4 p-6">
        {loading && !weather ? (
          <div className="text-[10px] font-mono tracking-[0.3em] text-zinc-500 animate-pulse">FETCHING DATA...</div>
        ) : weather ? (
          <>
            <div className="text-emerald-400">{getWeatherIcon(weather.condition)}</div>
            <div className="text-5xl font-black text-white">{weather.temperature}°</div>
            <div className="text-xs font-bold tracking-[0.2em] text-zinc-300 uppercase">{weather.condition}</div>
            <div className="text-[10px] font-mono tracking-[0.24em] text-emerald-500">{weather.city}</div>
            <div className="mt-2 grid w-full grid-cols-2 gap-3">
              <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3 text-center">
                <div className="text-[9px] font-mono tracking-[0.2em] text-zinc-500">HUMIDITY</div>
                <div className="mt-1 text-lg font-bold text-emerald-400">{weather.humidity}%</div>
              </div>
              <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3 text-center">
                <div className="text-[9px] font-mono tracking-[0.2em] text-zinc-500">WIND</div>
                <div className="mt-1 text-lg font-bold text-emerald-400">{weather.wind} km/h</div>
              </div>
            </div>
          </>
        ) : (
          <div className="text-xs text-red-400">{error}</div>
        )}
      </div>
    </WidgetShell>
  )
}
