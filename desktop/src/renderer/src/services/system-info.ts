/**
 * System info polling — mirrors IRIS's system-info.ts
 * Fetches real CPU, RAM, battery, OS data via Electron IPC or backend API.
 */

export type SystemStats = {
  cpuLoad: number
  ramUsage: number
  ramTotal: number
  temperature: number | null
  os: string
  uptime: string
  battery: number | null
  batteryCharging: boolean
}

const FALLBACK: SystemStats = {
  cpuLoad: 0,
  ramUsage: 0,
  ramTotal: 0,
  temperature: null,
  os: navigator.platform || 'Unknown',
  uptime: '--',
  battery: null,
  batteryCharging: false,
}

let cached: SystemStats = { ...FALLBACK }
let polling = false
let timer: number | null = null

async function fetchStats(): Promise<SystemStats> {
  try {
    // Try backend API first (JARVIS Python backend exposes /api/status)
    const res = await fetch('http://127.0.0.1:8765/api/system-stats', { signal: AbortSignal.timeout(1500) })
    if (res.ok) {
      const data = await res.json()
      return {
        cpuLoad: data.cpu ?? 0,
        ramUsage: data.ram_used ?? 0,
        ramTotal: data.ram_total ?? 0,
        temperature: data.temperature ?? null,
        os: data.os ?? navigator.platform,
        uptime: data.uptime ?? '--',
        battery: data.battery ?? null,
        batteryCharging: data.battery_charging ?? false,
      }
    }
  } catch {
    // Backend not available, use browser APIs
  }

  // Fallback: browser performance.memory + navigator.deviceMemory
  const stats: SystemStats = { ...FALLBACK }

  try {
    // @ts-expect-error -- navigator.getBattery is non-standard
    const battery = await navigator.getBattery?.()
    if (battery) {
      stats.battery = Math.round(battery.level * 100)
      stats.batteryCharging = battery.charging
    }
  } catch {
    // no battery API
  }

  try {
    // @ts-expect-error -- performance.memory is Chrome-only
    const mem = performance.memory
    if (mem) {
      stats.ramUsage = Math.round(mem.usedJSHeapSize / 1024 / 1024)
      stats.ramTotal = Math.round(mem.jsHeapSizeLimit / 1024 / 1024)
    }
  } catch {
    // no memory API
  }

  return stats
}

export function getSystemStats(): SystemStats {
  return { ...cached }
}

export function startSystemPolling(intervalMs = 3000) {
  if (polling) return
  polling = true

  const tick = async () => {
    cached = await fetchStats()
  }

  void tick()
  timer = window.setInterval(() => void tick(), intervalMs)
}

export function stopSystemPolling() {
  polling = false
  if (timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
}
