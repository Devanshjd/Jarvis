/**
 * WeatherWidget — live weather via Open-Meteo (FREE, no API key needed).
 * Uses ip-api.com for auto-location, then Open-Meteo for weather data.
 */

import { useState, useEffect, useCallback } from 'react'
import {
  RiSunLine, RiCloudLine, RiDrizzleLine, RiMistLine,
  RiThunderstormsLine, RiSnowflakeLine, RiRefreshLine,
  RiMapPinLine, RiWindyLine, RiDropLine, RiTempColdLine
} from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

interface WeatherData {
  temperature: number
  feelsLike: number
  condition: string
  humidity: number
  windSpeed: number
  windDir: number
  city: string
  country: string
  code: number
  isDay: boolean
  high: number
  low: number
  uv: number
  precipitation: number
}

const WMO_CODES: Record<number, string> = {
  0: 'Clear Sky', 1: 'Mainly Clear', 2: 'Partly Cloudy', 3: 'Overcast',
  45: 'Fog', 48: 'Depositing Rime Fog',
  51: 'Light Drizzle', 53: 'Moderate Drizzle', 55: 'Dense Drizzle',
  61: 'Slight Rain', 63: 'Moderate Rain', 65: 'Heavy Rain',
  71: 'Slight Snowfall', 73: 'Moderate Snowfall', 75: 'Heavy Snowfall',
  80: 'Slight Showers', 81: 'Moderate Showers', 82: 'Violent Showers',
  95: 'Thunderstorm', 96: 'Thunderstorm + Hail', 99: 'Thunderstorm + Heavy Hail'
}

function getWeatherIcon(code: number, size = 32) {
  if (code >= 95) return <RiThunderstormsLine size={size} />
  if (code >= 71 && code <= 77) return <RiSnowflakeLine size={size} />
  if (code >= 51 && code <= 67) return <RiDrizzleLine size={size} />
  if (code >= 80 && code <= 82) return <RiDrizzleLine size={size} />
  if (code >= 45 && code <= 48) return <RiMistLine size={size} />
  if (code >= 2 && code <= 3) return <RiCloudLine size={size} />
  return <RiSunLine size={size} />
}

function windDirection(deg: number): string {
  const dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
  return dirs[Math.round(deg / 45) % 8]
}

export default function WeatherWidget({ widget }: { widget: WidgetInstance }) {
  const [weather, setWeather] = useState<WeatherData | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState('')

  const fetchWeather = useCallback(async () => {
    try {
      setLoading(true)

      // Step 1: Get location from IP
      const geoResp = await fetch('http://ip-api.com/json/?fields=city,country,lat,lon')
      const geo = await geoResp.json()
      const { lat, lon, city, country } = geo

      // Step 2: Get weather from Open-Meteo (FREE, no key)
      const url = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,wind_direction_10m,weather_code,is_day,precipitation&daily=temperature_2m_max,temperature_2m_min,uv_index_max&timezone=auto&forecast_days=1`
      const wxResp = await fetch(url)
      const wx = await wxResp.json()

      const c = wx.current
      setWeather({
        temperature: Math.round(c.temperature_2m),
        feelsLike: Math.round(c.apparent_temperature),
        condition: WMO_CODES[c.weather_code] || 'Unknown',
        humidity: c.relative_humidity_2m,
        windSpeed: Math.round(c.wind_speed_10m),
        windDir: c.wind_direction_10m,
        city,
        country,
        code: c.weather_code,
        isDay: c.is_day === 1,
        high: Math.round(wx.daily.temperature_2m_max[0]),
        low: Math.round(wx.daily.temperature_2m_min[0]),
        uv: Math.round(wx.daily.uv_index_max[0]),
        precipitation: c.precipitation
      })
      setLastUpdated(new Date().toLocaleTimeString())
    } catch {
      // Fallback
      setWeather({
        temperature: 18, feelsLike: 16, condition: 'Partly Cloudy', humidity: 65,
        windSpeed: 12, windDir: 225, city: 'London', country: 'UK',
        code: 2, isDay: true, high: 21, low: 14, uv: 3, precipitation: 0
      })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchWeather()
    const timer = setInterval(fetchWeather, 300_000) // every 5 minutes
    return () => clearInterval(timer)
  }, [fetchWeather])

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiCloudLine />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col p-5">
        {loading && !weather ? (
          <div className="flex flex-1 items-center justify-center text-[10px] font-mono tracking-[0.3em] text-zinc-500 animate-pulse">
            FETCHING WEATHER...
          </div>
        ) : weather ? (
          <>
            {/* Location + refresh */}
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-[10px] font-mono tracking-[0.2em] text-emerald-500">
                <RiMapPinLine size={12} /> {weather.city}, {weather.country}
              </div>
              <button onClick={fetchWeather} className="rounded-lg p-1.5 text-zinc-500 transition-colors hover:text-emerald-400">
                <RiRefreshLine size={14} className={loading ? 'animate-spin' : ''} />
              </button>
            </div>

            {/* Main display */}
            <div className="flex items-center justify-between">
              <div>
                <div className="text-5xl font-black text-white">{weather.temperature}°</div>
                <div className="mt-1 text-[11px] font-bold tracking-[0.14em] text-zinc-300">{weather.condition}</div>
                <div className="mt-0.5 text-[10px] font-mono text-zinc-500">
                  Feels like {weather.feelsLike}° • H:{weather.high}° L:{weather.low}°
                </div>
              </div>
              <div className="text-emerald-400/80">{getWeatherIcon(weather.code, 48)}</div>
            </div>

            {/* Detail grid */}
            <div className="mt-4 grid grid-cols-3 gap-2">
              <div className="rounded-xl border border-white/5 bg-white/[0.03] p-2.5 text-center">
                <RiDropLine className="mx-auto mb-1 text-blue-400" size={14} />
                <div className="text-[8px] font-mono tracking-[0.18em] text-zinc-600">HUMIDITY</div>
                <div className="text-sm font-bold text-white">{weather.humidity}%</div>
              </div>
              <div className="rounded-xl border border-white/5 bg-white/[0.03] p-2.5 text-center">
                <RiWindyLine className="mx-auto mb-1 text-cyan-400" size={14} />
                <div className="text-[8px] font-mono tracking-[0.18em] text-zinc-600">WIND</div>
                <div className="text-sm font-bold text-white">{weather.windSpeed} <span className="text-[9px] text-zinc-400">km/h {windDirection(weather.windDir)}</span></div>
              </div>
              <div className="rounded-xl border border-white/5 bg-white/[0.03] p-2.5 text-center">
                <RiTempColdLine className="mx-auto mb-1 text-amber-400" size={14} />
                <div className="text-[8px] font-mono tracking-[0.18em] text-zinc-600">UV INDEX</div>
                <div className="text-sm font-bold text-white">{weather.uv}</div>
              </div>
            </div>

            {/* Timestamp */}
            {lastUpdated && (
              <div className="mt-auto pt-2 text-center text-[8px] font-mono tracking-[0.2em] text-zinc-600">
                UPDATED {lastUpdated}
              </div>
            )}
          </>
        ) : null}
      </div>
    </WidgetShell>
  )
}
