import { app, BrowserWindow, desktopCapturer, globalShortcut, ipcMain, shell, session, Notification } from 'electron'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import { join, dirname, resolve } from 'path'
import { existsSync } from 'fs'
import { promises as fs } from 'fs'
import { spawn, spawnSync, type ChildProcess } from 'child_process'
import http from 'http'
import os from 'os'
import { pathToFileURL } from 'url'

let mainWindow: BrowserWindow | null = null
let backendProcess: ChildProcess | null = null
const BACKEND_PORT = 8765
const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'])
const SHELL_SELFTEST_FLAG = '.jarvis_sandbox\\enable_shell_selftest.flag'

app.commandLine.appendSwitch('use-fake-ui-for-media-stream')

function getJarvisRoot() {
  const seeds = [
    app.getAppPath(),
    dirname(app.getAppPath()),
    process.cwd(),
    __dirname,
    dirname(__dirname)
  ]

  for (const seed of seeds) {
    let cursor = resolve(seed)
    for (let depth = 0; depth < 6; depth += 1) {
      if (existsSync(join(cursor, 'web_main.py'))) {
        return cursor
      }
      const nestedJarvis = join(cursor, 'Jarvis')
      if (existsSync(join(nestedJarvis, 'web_main.py'))) {
        return nestedJarvis
      }
      const parent = dirname(cursor)
      if (parent === cursor) break
      cursor = parent
    }
  }

  return dirname(app.getAppPath())
}

function getJarvisConfigPath() {
  return join(app.getPath('home'), '.jarvis_config.json')
}

function shouldRunShellSelfTest() {
  return (
    process.env.JARVIS_SHELL_SELFTEST === '1' ||
    existsSync(join(getJarvisRoot(), SHELL_SELFTEST_FLAG))
  )
}

function maskSecret(value: string | undefined | null) {
  const raw = String(value ?? '').trim()
  if (!raw) return ''
  if (raw.length <= 8) return `${raw.slice(0, 2)}•••`
  return `${raw.slice(0, 3)}${'•'.repeat(Math.max(4, raw.length - 6))}${raw.slice(-3)}`
}

async function readJarvisConfig() {
  let raw = await fs.readFile(getJarvisConfigPath(), 'utf8')
  // Strip UTF-8 BOM if present — PowerShell's ConvertTo-Json adds it
  if (raw.charCodeAt(0) === 0xfeff) raw = raw.slice(1)
  return JSON.parse(raw)
}

function maskKeySafely(value: string | undefined | null) {
  const raw = String(value ?? '').trim()
  if (!raw) return ''
  if (raw.length <= 8) return `${raw.slice(0, 1)}****`
  return `${raw.slice(0, 2)}${'*'.repeat(Math.max(12, raw.length - 4))}${raw.slice(-2)}`
}

function normalizeLiveModel(value: string | undefined | null) {
  const raw = String(value ?? '').trim()
  if (!raw) return 'models/gemini-2.5-flash-native-audio-latest'
  // Reject models known NOT to support BidiGenerateContent (Live)
  const lower = raw.toLowerCase()
  const invalidPatterns = ['flash-exp', '2.0-flash-live', 'pro-exp', 'ultra']
  if (invalidPatterns.some(p => lower.includes(p)) && !lower.includes('native-audio') && !lower.includes('live-')) {
    console.warn(`[JARVIS] Live model "${raw}" is not a valid native-audio model, falling back to default`)
    return 'models/gemini-2.5-flash-native-audio-latest'
  }
  return raw.startsWith('models/') ? raw : `models/${raw}`
}

async function writeJarvisConfig(nextConfig: unknown) {
  // Always write without BOM so JSON.parse won't choke on re-read
  await fs.writeFile(getJarvisConfigPath(), JSON.stringify(nextConfig, null, 2), 'utf8')
}

function resolveUserPath(input: string): string {
  const lower = input.toLowerCase().trim()
  const pathGetters: Record<string, string> = {
    desktop: 'desktop',
    documents: 'documents',
    downloads: 'downloads',
    pictures: 'pictures',
    music: 'music',
    videos: 'videos',
    home: 'home'
  }
  const pathKey = pathGetters[lower]
  if (pathKey) {
    try {
      return app.getPath(pathKey as Parameters<typeof app.getPath>[0])
    } catch {
      return input
    }
  }
  return input
}

async function listImageArtifacts() {
  const roots = [
    join(app.getPath('pictures'), 'Screenshots'),
    join(getJarvisRoot(), '.jarvis_sandbox')
  ]

  const images: Array<{
    filename: string
    displayName: string
    path: string
    url: string
    createdAt: string
    source: string
  }> = []

  for (const root of roots) {
    if (!existsSync(root)) continue
    const entries = await fs.readdir(root, { withFileTypes: true })
    for (const entry of entries) {
      if (!entry.isFile()) continue
      const fullPath = join(root, entry.name)
      const ext = entry.name.slice(entry.name.lastIndexOf('.')).toLowerCase()
      if (!IMAGE_EXTENSIONS.has(ext)) continue
      const stat = await fs.stat(fullPath)
      images.push({
        filename: entry.name,
        displayName: entry.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' '),
        path: fullPath,
        url: pathToFileURL(fullPath).toString(),
        createdAt: stat.mtime.toISOString(),
        source: root.includes('Screenshots') ? 'screenshots' : 'sandbox'
      })
    }
  }

  return images.sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1)).slice(0, 40)
}

async function buildShellSnapshot() {
  const config = await readJarvisConfig()
  const memories = Array.isArray(config.memories) ? config.memories : []
  const tasks = Array.isArray(config.tasks) ? config.tasks : []
  const identity = config.identity ?? {}
  const voice = config.voice ?? {}

  return {
    config: {
      operatorName: identity.name || identity.preferred_name || 'Dev',
      provider: config.provider || 'ollama',
      model: config.model || '',
      startupProvider: config.startup_provider || '',
      mode: config.mode || 'GENERAL',
      voiceEngine: voice.engine || 'classic',
      ttsEngine: voice.tts_engine || 'auto',
      sttEngine: voice.stt_engine || 'auto',
      geminiLiveModel: normalizeLiveModel(config.gemini?.live_model),
      geminiVoiceName: voice.gemini_voice_name || 'Kore',
      apiKeys: {
        gemini: maskKeySafely(config.gemini?.api_key || config.api_key),
        groq: maskKeySafely(config.groq?.api_key),
        openai: maskKeySafely(config.openai?.api_key),
        anthropic: maskKeySafely(config.anthropic?.api_key),
        deepseek: maskKeySafely(config.deepseek?.api_key)
      }
    },
    memories: memories.slice(0, 40).map((item: unknown, index: number) => ({
      id: index + 1,
      title: `Memory ${index + 1}`,
      content: String(item ?? ''),
      createdAt: new Date().toISOString()
    })),
    tasks: tasks.slice(0, 20),
    gallery: await listImageArtifacts()
  }
}

async function getSecureKeys() {
  const config = await readJarvisConfig()
  return {
    geminiKey: String(config.gemini?.api_key || config.api_key || '').trim(),
    groqKey: String(config.groq?.api_key || '').trim(),
    liveModel: normalizeLiveModel(config.gemini?.live_model),
    voiceName: String(config.voice?.gemini_voice_name || 'Kore').trim(),
  }
}

async function captureShellStep(name: string) {
  if (!mainWindow) return null
  const image = await mainWindow.webContents.capturePage()
  const target = join(getJarvisRoot(), '.jarvis_sandbox', `shell_${name}.png`)
  await fs.mkdir(dirname(target), { recursive: true })
  await fs.writeFile(target, image.toPNG())
  return target
}

async function runShellSelfTest() {
  const windowRef = mainWindow
  if (!windowRef) {
    return
  }

  const logTarget = join(getJarvisRoot(), '.jarvis_sandbox', 'shell_selftest_log.txt')
  await fs.mkdir(dirname(logTarget), { recursive: true })
  await fs.writeFile(logTarget, '[selftest] start\n', 'utf8')
  const appendLog = async (line: string) => {
    await fs.appendFile(logTarget, `${line}\n`, 'utf8')
  }

  const runInWindow = async <T>(code: string) =>
    (await windowRef.webContents.executeJavaScript(code, true)) as T

  const resolveClickPoint = async (selector: string) =>
    await runInWindow<{ ok: boolean; x?: number; y?: number; error?: string }>(`
      (() => {
        const element = document.querySelector(${JSON.stringify(selector)})
        if (!element) {
          return { ok: false, error: 'missing selector: ' + ${JSON.stringify(selector)} }
        }
        const rect = element.getBoundingClientRect()
        return {
          ok: true,
          x: Math.round(rect.left + rect.width / 2),
          y: Math.round(rect.top + rect.height / 2)
        }
      })()
    `)

  const inspectHitTarget = async (selector: string) =>
    await runInWindow<Record<string, unknown>>(`
      (() => {
        const element = document.querySelector(${JSON.stringify(selector)})
        if (!element) {
          return { ok: false, error: 'missing selector: ' + ${JSON.stringify(selector)} }
        }
        const rect = element.getBoundingClientRect()
        const x = Math.round(rect.left + rect.width / 2)
        const y = Math.round(rect.top + rect.height / 2)
        const hit = document.elementFromPoint(x, y)
        return {
          ok: true,
          selector: ${JSON.stringify(selector)},
          center: { x, y },
          hitTag: hit?.tagName ?? null,
          hitId: hit?.id ?? null,
          hitTestId: hit?.getAttribute?.('data-testid') ?? null,
          hitClass: hit?.className ?? null,
          same: !!(hit && (hit === element || element.contains(hit)))
        }
      })()
    `)

  const sendMouseClick = async (selector: string) => {
    const point = await resolveClickPoint(selector)
    if (!point.ok || typeof point.x !== 'number' || typeof point.y !== 'number') {
      return point
    }
    windowRef.focus()
    windowRef.webContents.sendInputEvent({
      type: 'mouseMove',
      x: point.x,
      y: point.y,
      movementX: 0,
      movementY: 0
    })
    windowRef.webContents.sendInputEvent({
      type: 'mouseDown',
      x: point.x,
      y: point.y,
      button: 'left',
      clickCount: 1
    })
    windowRef.webContents.sendInputEvent({
      type: 'mouseUp',
      x: point.x,
      y: point.y,
      button: 'left',
      clickCount: 1
    })
    return { ok: true, x: point.x, y: point.y }
  }

  const snapshotCode = `
    (() => {
      const getText = (selector) => document.querySelector(selector)?.textContent?.trim() ?? null
      const textarea = document.querySelector('[data-testid="dashboard-chat-input"]')
      const transcript = Array.from(document.querySelectorAll('[data-testid="transcript-message"]'))
        .map((node) => node.textContent?.trim() ?? '')
        .filter(Boolean)
      return {
        voiceState: getText('[data-testid="dashboard-voice-state"]'),
        visionState: getText('[data-testid="dashboard-vision-state"]'),
        promptValue: textarea?.value ?? null,
        transcriptCount: transcript.length,
        transcriptTail: transcript.slice(-4)
      }
    })()
  `

  const typeAndSubmitCode = `
    (async () => {
      const textarea = document.querySelector('[data-testid="dashboard-chat-input"]')
      if (!textarea) {
        return { ok: false, error: 'missing chat input' }
      }
      const descriptor = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')
      descriptor?.set?.call(textarea, 'shell self test')
      textarea.dispatchEvent(new Event('input', { bubbles: true }))
      textarea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
      return { ok: true }
    })()
  `

  const result: Record<string, unknown> = {}

  try {
    await appendLog('[selftest] capture initial')
    await captureShellStep('initial')
    result.initial = await runInWindow(snapshotCode)

    await appendLog('[selftest] click power')
    result.powerHit = await inspectHitTarget('[data-testid="dashboard-power-button"]')
    result.powerClick = await sendMouseClick('[data-testid="dashboard-power-button"]')
    await new Promise((resolve) => setTimeout(resolve, 2500))
    await captureShellStep('after_power')
    result.afterPower = await runInWindow(snapshotCode)

    await appendLog('[selftest] click mic')
    result.micHit = await inspectHitTarget('[data-testid="dashboard-mic-button"]')
    result.micClick = await sendMouseClick('[data-testid="dashboard-mic-button"]')
    await new Promise((resolve) => setTimeout(resolve, 700))
    await captureShellStep('after_mic')
    result.afterMic = await runInWindow(snapshotCode)

    await appendLog('[selftest] click vision')
    result.visionHit = await inspectHitTarget('[data-testid="dashboard-vision-button"]')
    result.visionClick = await sendMouseClick('[data-testid="dashboard-vision-button"]')
    await new Promise((resolve) => setTimeout(resolve, 500))
    result.visionSourceClick = await sendMouseClick('[data-testid="vision-camera-source"]')
    await new Promise((resolve) => setTimeout(resolve, 2500))
    await captureShellStep('after_vision')
    result.afterVision = await runInWindow(snapshotCode)

    await appendLog('[selftest] enter send')
    result.enterSend = await runInWindow(typeAndSubmitCode)
    await new Promise((resolve) => setTimeout(resolve, 3500))
    await captureShellStep('after_enter')
    result.afterEnter = await runInWindow(snapshotCode)

    const target = join(getJarvisRoot(), '.jarvis_sandbox', 'shell_selftest.json')
    await fs.mkdir(dirname(target), { recursive: true })
    await fs.writeFile(target, JSON.stringify(result, null, 2), 'utf8')
    await appendLog('[selftest] done')
  } catch (error) {
    await appendLog(
      `[selftest] error: ${error instanceof Error ? error.stack || error.message : String(error)}`
    )
    throw error
  }
}

function resolvePythonCommand(): string {
  const candidates = [
    process.env.JARVIS_PYTHON,
    'C:\\Users\\Devansh\\AppData\\Local\\Microsoft\\WindowsApps\\python3.13.exe',
    'python',
    'python3'
  ].filter(Boolean) as string[]

  for (const candidate of candidates) {
    if (candidate.includes('\\') || candidate.includes('/')) {
      if (existsSync(candidate)) return candidate
      continue
    }
    return candidate
  }

  return 'python'
}

function isBackendRunning(): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(
      {
        host: '127.0.0.1',
        port: BACKEND_PORT,
        path: '/api/status',
        timeout: 1200
      },
      (res) => {
        res.resume()
        resolve((res.statusCode ?? 500) < 500)
      }
    )
    req.on('error', () => resolve(false))
    req.on('timeout', () => {
      req.destroy()
      resolve(false)
    })
  })
}

function isBackendCompatible(): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(
      {
        host: '127.0.0.1',
        port: BACKEND_PORT,
        path: '/api/voice/status',
        timeout: 1500
      },
      (res) => {
        res.resume()
        resolve((res.statusCode ?? 500) < 400)
      }
    )
    req.on('error', () => resolve(false))
    req.on('timeout', () => {
      req.destroy()
      resolve(false)
    })
  })
}

function killListenerOnPort(port: number) {
  const probe = spawnSync(
    'powershell.exe',
    [
      '-NoProfile',
      '-Command',
      `(Get-NetTCPConnection -LocalPort ${port} -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | Select-Object -First 1)`
    ],
    { encoding: 'utf8', windowsHide: true }
  )
  const pidText = String(probe.stdout ?? '').trim()
  const pid = Number(pidText)
  if (!Number.isFinite(pid) || pid <= 0 || pid === process.pid) {
    return false
  }
  try {
    process.kill(pid)
    return true
  } catch {
    return false
  }
}

function listRunningApps() {
  const probe = spawnSync(
    'powershell.exe',
    [
      '-NoProfile',
      '-Command',
      [
        "$apps = Get-Process -ErrorAction SilentlyContinue |",
        "  Where-Object { $_.MainWindowTitle -and $_.MainWindowTitle.Trim().Length -gt 0 } |",
        "  Sort-Object ProcessName -Unique |",
        "  Select-Object -ExpandProperty ProcessName;",
        "$apps"
      ].join(' ')
    ],
    { encoding: 'utf8', windowsHide: true }
  )

  return String(probe.stdout ?? '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 30)
}

async function ensureBackend() {
  if (await isBackendRunning()) {
    if (await isBackendCompatible()) {
      return
    }
    killListenerOnPort(BACKEND_PORT)
    await new Promise((resolve) => setTimeout(resolve, 600))
  }

  const python = resolvePythonCommand()
  const backendScript = join(getJarvisRoot(), 'web_main.py')
  if (!existsSync(backendScript)) {
    throw new Error(`JARVIS backend not found at ${backendScript}`)
  }
  backendProcess = spawn(python, [backendScript], {
    cwd: getJarvisRoot(),
    env: {
      ...process.env,
      JARVIS_NO_BROWSER: '1',
      JARVIS_PORT: String(BACKEND_PORT)
    },
    stdio: 'ignore',
    detached: false,
    windowsHide: true
  })

  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (await isBackendRunning()) {
      return
    }
    await new Promise((resolve) => setTimeout(resolve, 250))
  }

  throw new Error('JARVIS backend did not become ready in time')
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1180,
    minHeight: 760,
    show: false,
    autoHideMenuBar: true,
    frame: false,
    backgroundColor: '#000000',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false
    }
  })

  mainWindow.on('ready-to-show', () => {
    mainWindow?.show()
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  ipcMain.on('window-min', () => mainWindow?.minimize())
  ipcMain.on('window-close', () => mainWindow?.close())
  ipcMain.on('window-max', () => {
    if (!mainWindow) return
    if (mainWindow.isMaximized()) mainWindow.unmaximize()
    else mainWindow.maximize()
  })

  ipcMain.handle('backend-status', async () => ({
    running: await isBackendRunning(),
    port: BACKEND_PORT,
    pid: backendProcess?.pid ?? null
  }))

  ipcMain.handle('jarvis-shell-snapshot', async () => buildShellSnapshot())
  ipcMain.handle('secure-get-keys', async () => getSecureKeys())
  ipcMain.handle('jarvis-shell-running-apps', async () => ({
    apps: listRunningApps()
  }))
  ipcMain.handle('get-screen-source', async () => {
    const sources = await desktopCapturer.getSources({ types: ['screen'] })
    return sources[0]?.id ?? null
  })
  ipcMain.handle('jarvis-shell-open-path', async (_event, targetPath: string) => {
    if (!targetPath) return { success: false }
    shell.showItemInFolder(targetPath)
    return { success: true }
  })
  ipcMain.handle(
    'jarvis-shell-save-settings',
    async (
      _event,
      payload: {
        operatorName?: string
        provider?: string
        model?: string
        voiceEngine?: string
      }
    ) => {
      const config = await readJarvisConfig()
      config.identity = config.identity ?? {}
      config.voice = config.voice ?? {}
      if (typeof payload.operatorName === 'string') {
        config.identity.name = payload.operatorName
      }
      if (typeof payload.provider === 'string') {
        config.provider = payload.provider
      }
      if (typeof payload.model === 'string') {
        config.model = payload.model
      }
      if (typeof payload.voiceEngine === 'string') {
        config.voice.engine = payload.voiceEngine
      }
      await writeJarvisConfig(config)
      return { success: true }
    }
  )

  // ─── System stats (IRIS-style real metrics) ───
  ipcMain.handle('system-stats', async () => {
    const cpus = os.cpus()
    const totalMem = os.totalmem()
    const freeMem = os.freemem()
    const usedMem = totalMem - freeMem

    // CPU usage: average across all cores
    let cpuIdle = 0
    let cpuTotal = 0
    for (const cpu of cpus) {
      cpuIdle += cpu.times.idle
      cpuTotal += cpu.times.user + cpu.times.nice + cpu.times.sys + cpu.times.idle + cpu.times.irq
    }
    const cpuLoad = Math.round((1 - cpuIdle / cpuTotal) * 100)

    const uptimeSec = os.uptime()
    const hours = Math.floor(uptimeSec / 3600)
    const mins = Math.floor((uptimeSec % 3600) / 60)
    const uptime = `${hours}h ${mins}m`

    return {
      cpuLoad,
      ramUsage: Math.round(usedMem / 1024 / 1024),
      ramTotal: Math.round(totalMem / 1024 / 1024),
      ramPercent: Math.round((usedMem / totalMem) * 100),
      temperature: null,
      os: `${os.type()} ${os.release()}`,
      hostname: os.hostname(),
      uptime,
      platform: os.platform(),
      arch: os.arch(),
      cpuModel: cpus[0]?.model ?? 'Unknown',
      cores: cpus.length
    }
  })

  // ─── Notes CRUD (IRIS-style file-based notes) ───
  const notesDir = join(getJarvisRoot(), '.jarvis_sandbox', 'notes')

  ipcMain.handle('notes-list', async () => {
    try {
      await fs.mkdir(notesDir, { recursive: true })
      const files = await fs.readdir(notesDir)
      const notes: Array<{ id: string; title: string; content: string; updatedAt: string }> = []
      for (const file of files) {
        if (!file.endsWith('.md') && !file.endsWith('.txt')) continue
        const filePath = join(notesDir, file)
        const stat = await fs.stat(filePath)
        const content = await fs.readFile(filePath, 'utf8')
        const title = file.replace(/\.(md|txt)$/, '').replace(/[-_]/g, ' ')
        notes.push({
          id: file,
          title,
          content,
          updatedAt: stat.mtime.toISOString()
        })
      }
      return notes.sort((a, b) => (a.updatedAt > b.updatedAt ? -1 : 1))
    } catch {
      return []
    }
  })

  ipcMain.handle('notes-create', async (_event, title: string, content: string) => {
    await fs.mkdir(notesDir, { recursive: true })
    const safeName = title.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 80) || `note_${Date.now()}`
    const fileName = `${safeName}.md`
    await fs.writeFile(join(notesDir, fileName), content, 'utf8')
    return { id: fileName, title: safeName, content }
  })

  ipcMain.handle('notes-update', async (_event, id: string, content: string) => {
    const filePath = join(notesDir, id)
    if (!existsSync(filePath)) return { success: false }
    await fs.writeFile(filePath, content, 'utf8')
    return { success: true }
  })

  ipcMain.handle('notes-delete', async (_event, id: string) => {
    const filePath = join(notesDir, id)
    try {
      await fs.unlink(filePath)
      return { success: true }
    } catch {
      return { success: false }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── NATIVE VOICE TOOLS (Phase 1 — Batch A) ───────────────────
  // ═══════════════════════════════════════════════════════════════

  ipcMain.handle('tool-read-file', async (_event, filePath: string) => {
    try {
      const resolved = resolveUserPath(filePath.trim())
      const content = await fs.readFile(resolved, 'utf8')
      return { success: true, content: content.slice(0, 10000), path: resolved }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-write-file', async (_event, fileName: string, content: string) => {
    try {
      let target = fileName.trim()

      // Strip ~ prefix
      if (target.startsWith('~/') || target.startsWith('~\\')) {
        target = join(os.homedir(), target.slice(2))
      }

      // If it starts with a known folder name like "Desktop/notes.txt", resolve it
      const parts = target.replace(/\\/g, '/').split('/')
      const firstPart = parts[0].toLowerCase()
      const knownFolders: Record<string, string> = {
        desktop: 'desktop', documents: 'documents', downloads: 'downloads',
        pictures: 'pictures', music: 'music', videos: 'videos'
      }
      if (knownFolders[firstPart]) {
        const resolved = app.getPath(knownFolders[firstPart] as Parameters<typeof app.getPath>[0])
        parts[0] = resolved
        target = join(...parts)
      } else if (!target.includes('/') && !target.includes('\\') && !target.match(/^[A-Z]:/i)) {
        // Bare filename like "notes.txt" → default to Desktop
        target = join(app.getPath('desktop'), target)
      }

      await fs.mkdir(dirname(target), { recursive: true })
      await fs.writeFile(target, content, 'utf8')
      return { success: true, path: target }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle(
    'tool-manage-file',
    async (_event, operation: string, sourcePath: string, destPath?: string) => {
      try {
        const src = resolveUserPath(sourcePath.trim())
        const dst = destPath ? resolveUserPath(destPath.trim()) : undefined

        if (operation === 'delete') {
          const stat = await fs.stat(src)
          if (stat.isDirectory()) {
            await fs.rm(src, { recursive: true })
          } else {
            await fs.unlink(src)
          }
          return { success: true, message: `Deleted ${src}` }
        } else if (operation === 'copy' && dst) {
          await fs.mkdir(dirname(dst), { recursive: true })
          const stat = await fs.stat(src)
          if (stat.isDirectory()) {
            await fs.cp(src, dst, { recursive: true })
          } else {
            await fs.copyFile(src, dst)
          }
          return { success: true, message: `Copied to ${dst}` }
        } else if (operation === 'move' && dst) {
          await fs.mkdir(dirname(dst), { recursive: true })
          try {
            await fs.rename(src, dst)
          } catch {
            // Cross-drive move: copy then delete
            const stat = await fs.stat(src)
            if (stat.isDirectory()) {
              await fs.cp(src, dst, { recursive: true })
              await fs.rm(src, { recursive: true })
            } else {
              await fs.copyFile(src, dst)
              await fs.unlink(src)
            }
          }
          return { success: true, message: `Moved to ${dst}` }
        }
        return { success: false, error: 'Invalid operation or missing destination. Use: copy, move, or delete.' }
      } catch (err: unknown) {
        return { success: false, error: (err as Error).message }
      }
    }
  )

  ipcMain.handle('tool-read-directory', async (_event, dirPath: string) => {
    try {
      // Resolve common names
      const resolved = resolveUserPath(dirPath)
      const entries = await fs.readdir(resolved, { withFileTypes: true })
      const result = entries.slice(0, 50).map((e) => ({
        name: e.name,
        type: e.isDirectory() ? 'folder' : 'file'
      }))
      return { success: true, path: resolved, items: result, total: entries.length }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-create-folder', async (_event, folderPath: string) => {
    try {
      const resolved = resolveUserPath(folderPath)
      await fs.mkdir(resolved, { recursive: true })
      return { success: true, path: resolved }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-open-app', async (_event, appName: string) => {
    try {
      const name = appName.toLowerCase().trim()
      const appMap: Record<string, { cmd: string; args: string[] }> = {
        chrome: { cmd: 'start', args: ['chrome'] },
        browser: { cmd: 'start', args: ['chrome'] },
        brave: { cmd: 'start', args: ['brave'] },
        firefox: { cmd: 'start', args: ['firefox'] },
        edge: { cmd: 'start', args: ['msedge'] },
        notepad: { cmd: 'notepad', args: [] },
        calculator: { cmd: 'calc', args: [] },
        calc: { cmd: 'calc', args: [] },
        settings: { cmd: 'start', args: ['ms-settings:'] },
        whatsapp: { cmd: 'start', args: ['whatsapp:'] },
        spotify: { cmd: 'start', args: ['spotify:'] },
        discord: { cmd: 'start', args: ['discord:'] },
        steam: { cmd: 'start', args: ['steam:'] },
        explorer: { cmd: 'explorer', args: [] },
        'file explorer': { cmd: 'explorer', args: [] },
        'file manager': { cmd: 'explorer', args: [] },
        paint: { cmd: 'mspaint', args: [] },
        snipping: { cmd: 'SnippingTool', args: [] },
        terminal: { cmd: 'wt', args: [] },
        powershell: { cmd: 'powershell', args: [] },
        cmd: { cmd: 'cmd', args: [] },
        vscode: { cmd: 'code', args: [] },
        'vs code': { cmd: 'code', args: [] },
        'visual studio code': { cmd: 'code', args: [] },
        word: { cmd: 'start', args: ['winword'] },
        excel: { cmd: 'start', args: ['excel'] },
        outlook: { cmd: 'start', args: ['outlook'] },
        teams: { cmd: 'start', args: ['msteams:'] }
      }

      const match = appMap[name]
      if (match) {
        spawn(match.cmd, match.args, { shell: true, detached: true, stdio: 'ignore' })
        return { success: true, message: `Opening ${appName}` }
      }
      // Fallback: try to start it directly
      spawn('start', [appName], { shell: true, detached: true, stdio: 'ignore' })
      return { success: true, message: `Attempting to open ${appName}` }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-close-app', async (_event, appName: string) => {
    try {
      const name = appName.toLowerCase().trim()
      const processMap: Record<string, string> = {
        chrome: 'chrome.exe',
        brave: 'brave.exe',
        firefox: 'firefox.exe',
        edge: 'msedge.exe',
        notepad: 'notepad.exe',
        calculator: 'CalculatorApp.exe',
        spotify: 'Spotify.exe',
        discord: 'Discord.exe',
        steam: 'steam.exe',
        vscode: 'Code.exe',
        'vs code': 'Code.exe',
        teams: 'Teams.exe',
        word: 'WINWORD.EXE',
        excel: 'EXCEL.EXE',
        outlook: 'OUTLOOK.EXE',
        explorer: 'explorer.exe'
      }
      const proc = processMap[name] || `${appName}.exe`
      spawnSync('taskkill', ['/F', '/IM', proc], { shell: true })
      return { success: true, message: `Closed ${appName}` }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle(
    'tool-run-terminal',
    async (_event, command: string, cwd?: string) => {
      try {
        const workDir = cwd || app.getPath('home')
        const result = spawnSync(command, {
          shell: true,
          cwd: workDir,
          timeout: 15000,
          encoding: 'utf8',
          maxBuffer: 1024 * 1024
        })
        const output = (result.stdout || '') + (result.stderr || '')
        return {
          success: result.status === 0,
          output: output.slice(0, 5000),
          exitCode: result.status
        }
      } catch (err: unknown) {
        return { success: false, error: (err as Error).message }
      }
    }
  )

  ipcMain.handle('tool-google-search', async (_event, query: string) => {
    try {
      const url = `https://www.google.com/search?q=${encodeURIComponent(query)}`
      await shell.openExternal(url)
      return { success: true, message: `Searched for "${query}"` }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-smart-file-search', async (_event, query: string) => {
    try {
      const searchDirs = [
        app.getPath('desktop'),
        app.getPath('documents'),
        app.getPath('downloads'),
        app.getPath('pictures')
      ]
      const results: string[] = []
      const keywords = query.toLowerCase().split(/\s+/).filter(Boolean)
      const MAX_RESULTS = 25
      const MAX_DEPTH = 3

      async function searchDir(dir: string, depth: number) {
        if (depth > MAX_DEPTH || results.length >= MAX_RESULTS) return
        try {
          const entries = await fs.readdir(dir, { withFileTypes: true })
          for (const entry of entries) {
            if (results.length >= MAX_RESULTS) break
            const lower = entry.name.toLowerCase()
            if (keywords.some(kw => lower.includes(kw))) {
              results.push(join(dir, entry.name))
            }
            if (entry.isDirectory() && !entry.name.startsWith('.') && !entry.name.startsWith('node_modules')) {
              await searchDir(join(dir, entry.name), depth + 1)
            }
          }
        } catch { /* skip inaccessible */ }
      }

      // Add 10s timeout
      await Promise.race([
        Promise.all(searchDirs.map(d => searchDir(d, 0))),
        new Promise(resolve => setTimeout(resolve, 10000))
      ])

      return {
        success: true,
        results: results.slice(0, MAX_RESULTS),
        message: results.length > 0
          ? `Found ${results.length} files matching "${query}"`
          : `No files found matching "${query}"`
      }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })


  // ═══════════════════════════════════════════════════════════════
  // ─── NATIVE VOICE TOOLS (Phase 1 — Batch B: Desktop Automation)
  // ═══════════════════════════════════════════════════════════════

  ipcMain.handle('tool-ghost-type', async (_event, text: string) => {
    try {
      // Escape SendKeys special characters: + ^ % ~ { } ( ) [ ]
      const escaped = text
        .replace(/\{/g, '{{}')
        .replace(/\}/g, '{}}')
        .replace(/\+/g, '{+}')
        .replace(/\^/g, '{^}')
        .replace(/%/g, '{%}')
        .replace(/~/g, '{~}')
        .replace(/\(/g, '{(}')
        .replace(/\)/g, '{)}')
      // Small delay to let active window keep focus after JARVIS processes
      const ps = `
        Add-Type -AssemblyName System.Windows.Forms
        Start-Sleep -Milliseconds 200
        [System.Windows.Forms.SendKeys]::SendWait('${escaped.replace(/'/g, "''")}')
      `
      spawnSync('powershell', ['-Command', ps], { shell: true, timeout: 10000 })
      return { success: true, message: `Typed: "${text.slice(0, 80)}"` }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-press-shortcut', async (_event, key: string, modifiers?: string[]) => {
    try {
      const mods = modifiers || []
      let combo = ''
      if (mods.includes('ctrl')) combo += '^'
      if (mods.includes('alt')) combo += '%'
      if (mods.includes('shift')) combo += '+'
      // Map common key names
      const keyMap: Record<string, string> = {
        enter: '{ENTER}', tab: '{TAB}', escape: '{ESC}', esc: '{ESC}',
        backspace: '{BACKSPACE}', delete: '{DELETE}', del: '{DELETE}',
        up: '{UP}', down: '{DOWN}', left: '{LEFT}', right: '{RIGHT}',
        home: '{HOME}', end: '{END}', pageup: '{PGUP}', pagedown: '{PGDN}',
        f1: '{F1}', f2: '{F2}', f3: '{F3}', f4: '{F4}', f5: '{F5}',
        f6: '{F6}', f7: '{F7}', f8: '{F8}', f9: '{F9}', f10: '{F10}',
        f11: '{F11}', f12: '{F12}', space: ' ', print: '{PRTSC}'
      }
      const mappedKey = keyMap[key.toLowerCase()] || key.toLowerCase()
      combo += mappedKey
      spawnSync('powershell', [
        '-Command',
        `Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('${combo}')`
      ], { shell: true, timeout: 5000 })
      return { success: true, message: `Pressed ${mods.join('+')}${mods.length ? '+' : ''}${key}` }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-take-screenshot', async () => {
    try {
      const screenshotDir = join(app.getPath('pictures'), 'Screenshots')
      await fs.mkdir(screenshotDir, { recursive: true })
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-')
      const filePath = join(screenshotDir, `JARVIS_${timestamp}.png`)
      // Use PowerShell screen capture
      spawnSync('powershell', [
        '-Command',
        `Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; $screen = [System.Windows.Forms.Screen]::PrimaryScreen; $bmp = New-Object System.Drawing.Bitmap($screen.Bounds.Width, $screen.Bounds.Height); $gfx = [System.Drawing.Graphics]::FromImage($bmp); $gfx.CopyFromScreen($screen.Bounds.Location, [System.Drawing.Point]::Empty, $screen.Bounds.Size); $bmp.Save('${filePath.replace(/\\/g, '\\\\')}'); $gfx.Dispose(); $bmp.Dispose()`
      ], { shell: true, timeout: 10000 })
      if (existsSync(filePath)) {
        return { success: true, path: filePath, message: 'Screenshot saved' }
      }
      return { success: false, error: 'Screenshot file was not created' }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-set-volume', async (_event, level: number) => {
    try {
      const vol = Math.max(0, Math.min(100, level))
      // Use PowerShell to set system volume
      spawnSync('powershell', [
        '-Command',
        `$wshShell = New-Object -ComObject WScript.Shell; $vol = ${vol}; $currentVol = 0; for($i=0;$i -lt 50;$i++){$wshShell.SendKeys([char]174)}; $steps = [math]::Round($vol/2); for($i=0;$i -lt $steps;$i++){$wshShell.SendKeys([char]175)}`
      ], { shell: true, timeout: 10000 })
      return { success: true, message: `Volume set to approximately ${vol}%` }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── NATIVE VOICE TOOLS (Phase 1 — Batch C: Memory & Tools) ───
  // ═══════════════════════════════════════════════════════════════

  const coreMemoryPath = join(getJarvisRoot(), '.jarvis_sandbox', 'core_memory.json')

  ipcMain.handle('tool-save-core-memory', async (_event, fact: string) => {
    try {
      let memories: Array<{ fact: string; savedAt: string }> = []
      try {
        const raw = await fs.readFile(coreMemoryPath, 'utf8')
        memories = JSON.parse(raw)
      } catch {
        // file doesn't exist yet
      }
      memories.push({ fact, savedAt: new Date().toISOString() })
      await fs.mkdir(join(getJarvisRoot(), '.jarvis_sandbox'), { recursive: true })
      await fs.writeFile(coreMemoryPath, JSON.stringify(memories, null, 2), 'utf8')
      return { success: true, message: `Remembered: "${fact}"`, total: memories.length }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-retrieve-core-memory', async () => {
    try {
      const raw = await fs.readFile(coreMemoryPath, 'utf8')
      const memories: Array<{ fact: string; savedAt: string }> = JSON.parse(raw)
      return { success: true, memories, total: memories.length }
    } catch {
      return { success: true, memories: [], total: 0, message: 'No memories saved yet.' }
    }
  })

  ipcMain.handle('tool-open-project', async (_event, folderPath: string) => {
    try {
      const resolved = resolveUserPath(folderPath)
      spawn('code', [resolved], { shell: true, detached: true, stdio: 'ignore' })
      return { success: true, message: `Opening ${resolved} in VS Code` }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── BATCH D: Window Management, Macros & Lock ────────────────
  // ═══════════════════════════════════════════════════════════════

  ipcMain.handle('tool-snap-window', async (_event, appName: string, position: string) => {
    try {
      // Get screen dimensions
      const { screen } = await import('electron')
      const primary = screen.getPrimaryDisplay()
      const { width: sw, height: sh } = primary.workAreaSize
      const { x: ox, y: oy } = primary.workArea

      const positions: Record<string, { x: number; y: number; w: number; h: number }> = {
        left:          { x: ox, y: oy, w: Math.round(sw / 2), h: sh },
        right:         { x: ox + Math.round(sw / 2), y: oy, w: Math.round(sw / 2), h: sh },
        'top-left':    { x: ox, y: oy, w: Math.round(sw / 2), h: Math.round(sh / 2) },
        'top-right':   { x: ox + Math.round(sw / 2), y: oy, w: Math.round(sw / 2), h: Math.round(sh / 2) },
        'bottom-left': { x: ox, y: oy + Math.round(sh / 2), w: Math.round(sw / 2), h: Math.round(sh / 2) },
        'bottom-right':{ x: ox + Math.round(sw / 2), y: oy + Math.round(sh / 2), w: Math.round(sw / 2), h: Math.round(sh / 2) },
        center:        { x: ox + Math.round(sw / 4), y: oy + Math.round(sh / 4), w: Math.round(sw / 2), h: Math.round(sh / 2) },
        maximize:      { x: ox, y: oy, w: sw, h: sh },
        minimize:      { x: 0, y: 0, w: 0, h: 0 }
      }

      const pos = positions[position.toLowerCase()]
      if (!pos) {
        return { success: false, error: `Unknown position "${position}". Use: left, right, top-left, top-right, bottom-left, bottom-right, center, maximize, minimize` }
      }

      if (position.toLowerCase() === 'minimize') {
        // Minimize the window
        const psCmd = `(Get-Process -Name '*${appName.replace(/'/g, "''")}*' -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1).MainWindowHandle`
        const result = spawnSync('powershell', ['-NoProfile', '-Command', `
          Add-Type @"
          using System; using System.Runtime.InteropServices;
          public class WinAPI { [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow); }
"@
          $h = ${psCmd}
          if ($h) { [WinAPI]::ShowWindow($h, 6) }
        `], { encoding: 'utf8', windowsHide: true, timeout: 5000 })
        return { success: true, message: `Minimized ${appName}` }
      }

      // Move and resize window using PowerShell + Win32
      const psScript = `
        Add-Type @"
          using System; using System.Runtime.InteropServices;
          public class WinAPI {
            [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int W, int H, bool repaint);
            [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
            [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
          }
"@
        $proc = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like '*${appName.replace(/'/g, "''")}*' -and $_.MainWindowHandle -ne 0 } | Select-Object -First 1
        if ($proc) {
          [WinAPI]::ShowWindow($proc.MainWindowHandle, 9)
          [WinAPI]::MoveWindow($proc.MainWindowHandle, ${pos.x}, ${pos.y}, ${pos.w}, ${pos.h}, $true)
          [WinAPI]::SetForegroundWindow($proc.MainWindowHandle)
          "OK"
        } else { "NOT_FOUND" }
      `
      const result = spawnSync('powershell', ['-NoProfile', '-Command', psScript], {
        encoding: 'utf8', windowsHide: true, timeout: 8000
      })
      const output = (result.stdout || '').trim()
      if (output === 'NOT_FOUND') {
        return { success: false, error: `No window found for "${appName}". Is it running?` }
      }
      return { success: true, message: `Snapped ${appName} to ${position}` }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ─── Macro CRUD + Execute ───

  const macrosPath = join(getJarvisRoot(), '.jarvis_sandbox', 'macros.json')

  async function loadMacros(): Promise<Array<{ id: string; name: string; steps: Array<{ type: string; params: Record<string, string> }> }>> {
    try {
      const raw = await fs.readFile(macrosPath, 'utf8')
      return JSON.parse(raw)
    } catch {
      return []
    }
  }

  async function saveMacros(macros: unknown) {
    await fs.mkdir(join(getJarvisRoot(), '.jarvis_sandbox'), { recursive: true })
    await fs.writeFile(macrosPath, JSON.stringify(macros, null, 2), 'utf8')
  }

  ipcMain.handle('macros-list', async () => loadMacros())

  ipcMain.handle('macros-save', async (_event, macro: { id: string; name: string; steps: Array<{ type: string; params: Record<string, string> }> }) => {
    const macros = await loadMacros()
    const idx = macros.findIndex(m => m.id === macro.id)
    if (idx >= 0) macros[idx] = macro
    else macros.push(macro)
    await saveMacros(macros)
    return { success: true }
  })

  ipcMain.handle('macros-delete', async (_event, id: string) => {
    const macros = await loadMacros()
    await saveMacros(macros.filter(m => m.id !== id))
    return { success: true }
  })

  ipcMain.handle('tool-execute-macro', async (_event, macroName: string) => {
    try {
      const macros = await loadMacros()
      const macro = macros.find(m => m.name.toLowerCase() === macroName.toLowerCase())
      if (!macro) {
        const available = macros.map(m => m.name).join(', ')
        return { success: false, error: `Macro "${macroName}" not found. Available: ${available || 'none'}` }
      }

      const results: string[] = []
      for (const step of macro.steps) {
        try {
          switch (step.type) {
            case 'open_app':
              spawn(step.params.cmd || 'start', (step.params.args || step.params.app || '').split(' ').filter(Boolean), { shell: true, detached: true, stdio: 'ignore' })
              results.push(`✅ Opened ${step.params.app || step.params.cmd}`)
              break
            case 'run_terminal': {
              const r = spawnSync(step.params.command || '', { shell: true, encoding: 'utf8', timeout: 10000, cwd: step.params.path || undefined })
              results.push(`✅ Ran: ${step.params.command} (exit ${r.status})`)
              break
            }
            case 'wait': {
              const ms = parseInt(step.params.seconds || '1') * 1000
              await new Promise(resolve => setTimeout(resolve, Math.min(ms, 30000)))
              results.push(`✅ Waited ${step.params.seconds}s`)
              break
            }
            case 'ghost_type':
              spawnSync('powershell', ['-Command', `Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('${(step.params.text || '').replace(/'/g, "''")}')`], { shell: true, timeout: 5000 })
              results.push(`✅ Typed: "${(step.params.text || '').slice(0, 30)}"`)
              break
            case 'press_shortcut': {
              let combo = ''
              const mods = (step.params.modifiers || '').split(',').filter(Boolean)
              if (mods.includes('ctrl')) combo += '^'
              if (mods.includes('alt')) combo += '%'
              if (mods.includes('shift')) combo += '+'
              combo += step.params.key || ''
              spawnSync('powershell', ['-Command', `Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('${combo}')`], { shell: true, timeout: 5000 })
              results.push(`✅ Pressed ${step.params.modifiers || ''}+${step.params.key}`)
              break
            }
            case 'google_search':
              await shell.openExternal(`https://www.google.com/search?q=${encodeURIComponent(step.params.query || '')}`)
              results.push(`✅ Searched: ${step.params.query}`)
              break
            default:
              results.push(`⚠️ Unknown step type: ${step.type}`)
          }
        } catch (stepErr) {
          results.push(`❌ Step "${step.type}" failed: ${(stepErr as Error).message}`)
        }
        // Small delay between steps
        await new Promise(resolve => setTimeout(resolve, 300))
      }

      return { success: true, message: `Macro "${macro.name}" completed (${macro.steps.length} steps):\n${results.join('\n')}` }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-lock-system', async () => {
    try {
      spawnSync('rundll32.exe', ['user32.dll,LockWorkStation'], { shell: false, timeout: 3000 })
      return { success: true, message: 'System locked.' }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── PHASE 2: Communications ──────────────────────────────────
  // ═══════════════════════════════════════════════════════════════

  ipcMain.handle('tool-send-whatsapp', async (_event, contact: string, message: string) => {
    try {
      // If contact looks like a phone number, use wa.me direct link
      const cleaned = contact.replace(/[\s\-()]/g, '')
      if (/^\+?\d{7,15}$/.test(cleaned)) {
        const num = cleaned.startsWith('+') ? cleaned.slice(1) : cleaned
        const url = `https://wa.me/${num}?text=${encodeURIComponent(message)}`
        await shell.openExternal(url)
        return { success: true, message: `Opened WhatsApp chat with ${contact}. Message pre-filled — press Send in WhatsApp.` }
      }

      // For contact names, open WhatsApp desktop and search
      spawn('start', ['whatsapp:'], { shell: true, detached: true, stdio: 'ignore' })
      await new Promise(resolve => setTimeout(resolve, 3000))

      // Use pyautogui via backend to search + send
      try {
        const resp = await new Promise<string>((resolve, reject) => {
          const req = http.request({
            host: '127.0.0.1', port: BACKEND_PORT, path: '/api/chat',
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            timeout: 30000
          }, (res) => {
            let data = ''
            res.on('data', chunk => { data += chunk })
            res.on('end', () => resolve(data))
          })
          req.on('error', reject)
          req.on('timeout', () => { req.destroy(); reject(new Error('timeout')) })
          req.write(JSON.stringify({ text: `send whatsapp message to ${contact} saying: ${message}`, approve_desktop: true }))
          req.end()
        })
        const result = JSON.parse(resp)
        return { success: true, message: result.reply || `WhatsApp message queued for ${contact}` }
      } catch {
        return { success: true, message: `Opened WhatsApp. Search for "${contact}" and send your message manually.` }
      }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-open-whatsapp-chat', async (_event, contact: string) => {
    try {
      const cleaned = contact.replace(/[\s\-()]/g, '')
      if (/^\+?\d{7,15}$/.test(cleaned)) {
        const num = cleaned.startsWith('+') ? cleaned.slice(1) : cleaned
        await shell.openExternal(`https://wa.me/${num}`)
        return { success: true, message: `Opened WhatsApp chat with ${contact}` }
      }
      // Open WhatsApp app
      spawn('start', ['whatsapp:'], { shell: true, detached: true, stdio: 'ignore' })
      return { success: true, message: `Opened WhatsApp. Search for "${contact}" to open their chat.` }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-send-telegram', async (_event, contact: string, message: string) => {
    try {
      // Open Telegram desktop
      spawn('start', ['telegram:'], { shell: true, detached: true, stdio: 'ignore' })
      await new Promise(resolve => setTimeout(resolve, 3000))

      // Route through backend messaging plugin
      try {
        const resp = await new Promise<string>((resolve, reject) => {
          const req = http.request({
            host: '127.0.0.1', port: BACKEND_PORT, path: '/api/chat',
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            timeout: 30000
          }, (res) => {
            let data = ''
            res.on('data', chunk => { data += chunk })
            res.on('end', () => resolve(data))
          })
          req.on('error', reject)
          req.on('timeout', () => { req.destroy(); reject(new Error('timeout')) })
          req.write(JSON.stringify({ text: `send telegram message to ${contact} saying: ${message}`, approve_desktop: true }))
          req.end()
        })
        const result = JSON.parse(resp)
        return { success: true, message: result.reply || `Telegram message queued for ${contact}` }
      } catch {
        return { success: true, message: `Opened Telegram. Search for "${contact}" and send your message manually.` }
      }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-send-email', async (_event, to: string, subject: string, body: string) => {
    try {
      const config = await readJarvisConfig()
      const emailConf = config.email || {}
      const smtpHost = emailConf.smtp_host
      const smtpUser = emailConf.smtp_user

      // If SMTP is configured, try native send via PowerShell
      if (smtpHost && smtpUser) {
        const smtpPort = emailConf.smtp_port || 587
        const smtpPass = emailConf.smtp_pass || ''
        const fromName = emailConf.from_name || config.identity?.name || 'JARVIS'

        const psScript = `
          $smtp = New-Object Net.Mail.SmtpClient("${smtpHost}", ${smtpPort})
          $smtp.EnableSsl = $true
          $smtp.Credentials = New-Object System.Net.NetworkCredential("${smtpUser}", "${smtpPass}")
          $msg = New-Object Net.Mail.MailMessage
          $msg.From = New-Object Net.Mail.MailAddress("${smtpUser}", "${fromName}")
          $msg.To.Add("${to}")
          $msg.Subject = "${subject.replace(/"/g, '`"')}"
          $msg.Body = "${body.replace(/"/g, '`"').replace(/\n/g, '`n')}"
          $smtp.Send($msg)
          "SENT"
        `
        const result = spawnSync('powershell', ['-NoProfile', '-Command', psScript], {
          encoding: 'utf8', windowsHide: true, timeout: 15000
        })
        const output = (result.stdout || '').trim()
        if (output === 'SENT') {
          return { success: true, message: `✉️ Email sent to ${to} with subject "${subject}"` }
        }
        const err = (result.stderr || '').trim()
        if (err) {
          return { success: false, error: `SMTP error: ${err.slice(0, 200)}` }
        }
      }

      // Fallback: mailto link
      const mailtoUrl = `mailto:${encodeURIComponent(to)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`
      await shell.openExternal(mailtoUrl)
      return { success: true, message: `Opened email compose to ${to} in your default email app. ${!smtpHost ? '(Configure SMTP in settings for direct send)' : ''}` }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── PHASE 5: Cyber Arsenal ───────────────────────────────────
  // ═══════════════════════════════════════════════════════════════

  ipcMain.handle('tool-port-scan', async (_event, target: string, ports?: string) => {
    try {
      const portList = ports || '21,22,23,25,53,80,110,135,139,143,443,445,993,995,1433,1723,3306,3389,5432,5900,8080,8443,8888'
      const psScript = `
        $target = "${target.replace(/"/g, '`"')}"
        $ports = @(${portList.split(',').map(p => p.trim()).join(',')})
        $results = @()
        foreach ($port in $ports) {
          try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $connect = $tcp.BeginConnect($target, $port, $null, $null)
            $wait = $connect.AsyncWaitHandle.WaitOne(800, $false)
            if ($wait -and $tcp.Connected) {
              $results += "$port OPEN"
            }
            $tcp.Close()
          } catch { }
        }
        if ($results.Count -eq 0) { "No open ports found on $target (scanned: ` + portList + `)" }
        else { "Open ports on " + $target + ":" + [char]10 + ($results -join [char]10) }
      `
      const result = spawnSync('powershell', ['-NoProfile', '-Command', psScript], {
        encoding: 'utf8', windowsHide: true, timeout: 30000
      })
      const output = (result.stdout || '').trim() || (result.stderr || '').trim() || 'Scan completed with no output.'
      return { success: true, message: output }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-nmap-scan', async (_event, target: string, flags?: string) => {
    try {
      // Check if nmap is installed
      const check = spawnSync('where', ['nmap'], { encoding: 'utf8', windowsHide: true, timeout: 3000 })
      if (!check.stdout?.trim()) {
        return { success: false, error: 'nmap is not installed. Install it from https://nmap.org/download.html or use the port_scan tool instead.' }
      }
      const nmapFlags = flags || '-sV -T4 --top-ports 100'
      const result = spawnSync('nmap', [...nmapFlags.split(' '), target], {
        encoding: 'utf8', windowsHide: true, timeout: 120000
      })
      const output = (result.stdout || '').trim() || (result.stderr || '').trim()
      return { success: true, message: output || 'nmap scan completed.' }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-whois-lookup', async (_event, target: string) => {
    try {
      // Try whois command first
      const check = spawnSync('where', ['whois'], { encoding: 'utf8', windowsHide: true, timeout: 3000 })
      if (check.stdout?.trim()) {
        const result = spawnSync('whois', [target], { encoding: 'utf8', windowsHide: true, timeout: 15000 })
        return { success: true, message: (result.stdout || '').trim().slice(0, 3000) || 'No WHOIS data returned.' }
      }
      // Fallback: PowerShell .NET
      const psScript = `
        try {
          $web = New-Object System.Net.WebClient
          $data = $web.DownloadString("https://whois.arin.net/rest/ip/${target.replace(/"/g, '')}")
          $data.Substring(0, [Math]::Min($data.Length, 2000))
        } catch {
          try {
            $dns = Resolve-DnsName "${target}" -ErrorAction Stop
            "DNS Resolution for ${target}:" + ($dns | Format-List | Out-String)
          } catch { "WHOIS lookup failed. Target: ${target}" }
        }
      `
      const result = spawnSync('powershell', ['-NoProfile', '-Command', psScript], {
        encoding: 'utf8', windowsHide: true, timeout: 15000
      })
      return { success: true, message: (result.stdout || '').trim().slice(0, 3000) || 'No WHOIS data returned.' }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-dns-lookup', async (_event, target: string, recordType?: string) => {
    try {
      const rType = recordType || 'ANY'
      const types = rType === 'ANY' ? ['A', 'AAAA', 'MX', 'NS', 'TXT', 'CNAME', 'SOA'] : [rType.toUpperCase()]
      const results: string[] = []

      for (const t of types) {
        const r = spawnSync('powershell', ['-NoProfile', '-Command',
          `try { Resolve-DnsName "${target}" -Type ${t} -ErrorAction Stop | Format-Table -AutoSize | Out-String } catch { "" }`
        ], { encoding: 'utf8', windowsHide: true, timeout: 10000 })
        const out = (r.stdout || '').trim()
        if (out) results.push(`── ${t} Records ──\n${out}`)
      }

      return { success: true, message: results.length > 0 ? results.join('\n\n') : `No DNS records found for ${target}` }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-subdomain-enum', async (_event, domain: string) => {
    try {
      const results: string[] = []

      // Method 1: crt.sh (Certificate Transparency)
      try {
        const crtData = await new Promise<string>((resolve, reject) => {
          const req = (domain.includes('https') ? require('https') : require('https')).get(
            `https://crt.sh/?q=%25.${domain}&output=json`,
            { timeout: 15000 },
            (res: any) => {
              let data = ''
              res.on('data', (chunk: string) => { data += chunk })
              res.on('end', () => resolve(data))
            }
          )
          req.on('error', reject)
          req.on('timeout', () => { req.destroy(); reject(new Error('timeout')) })
        })
        const entries = JSON.parse(crtData)
        const subs = new Set<string>()
        for (const entry of entries) {
          const names = (entry.name_value || '').split('\n')
          for (const name of names) {
            const clean = name.trim().toLowerCase()
            if (clean && clean.endsWith(domain) && !clean.includes('*')) {
              subs.add(clean)
            }
          }
        }
        if (subs.size > 0) {
          results.push(`── crt.sh (Certificate Transparency) ── Found ${subs.size} subdomains:\n${[...subs].sort().join('\n')}`)
        }
      } catch { /* crt.sh failed, continue */ }

      // Method 2: Common subdomain brute-force via DNS
      const common = ['www', 'mail', 'ftp', 'admin', 'api', 'dev', 'staging', 'test', 'blog', 'shop',
        'app', 'cdn', 'ns1', 'ns2', 'mx', 'smtp', 'pop', 'imap', 'vpn', 'remote',
        'portal', 'secure', 'login', 'dashboard', 'git', 'gitlab', 'jenkins', 'ci',
        'docs', 'wiki', 'support', 'help', 'status', 'monitor', 'grafana']
      const dnsResults: string[] = []
      for (const sub of common) {
        const fqdn = `${sub}.${domain}`
        const r = spawnSync('powershell', ['-NoProfile', '-Command',
          `try { $r = Resolve-DnsName "${fqdn}" -Type A -ErrorAction Stop; "$fqdn -> " + ($r.IPAddress -join ", ") } catch { "" }`
        ], { encoding: 'utf8', windowsHide: true, timeout: 3000 })
        const out = (r.stdout || '').trim()
        if (out) dnsResults.push(out)
      }
      if (dnsResults.length > 0) {
        results.push(`── DNS Brute-force ── Found ${dnsResults.length} subdomains:\n${dnsResults.join('\n')}`)
      }

      return {
        success: true,
        message: results.length > 0 ? results.join('\n\n') : `No subdomains found for ${domain}. Try using a more common domain.`
      }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-hash-identify', async (_event, hash: string) => {
    try {
      const h = hash.trim()
      const len = h.length
      const patterns: Array<{ regex: RegExp; type: string; desc: string }> = [
        { regex: /^[a-f0-9]{32}$/i, type: 'MD5', desc: '128-bit (insecure, rainbow-table vulnerable)' },
        { regex: /^[a-f0-9]{40}$/i, type: 'SHA-1', desc: '160-bit (deprecated, collision-prone)' },
        { regex: /^[a-f0-9]{64}$/i, type: 'SHA-256', desc: '256-bit (secure, widely used)' },
        { regex: /^[a-f0-9]{128}$/i, type: 'SHA-512', desc: '512-bit (high security)' },
        { regex: /^\$2[aby]?\$\d{1,2}\$.{53}$/i, type: 'bcrypt', desc: 'Adaptive hash (password storage)' },
        { regex: /^\$6\$.{1,16}\$.{86}$/i, type: 'SHA-512crypt', desc: 'Unix /etc/shadow format' },
        { regex: /^\$5\$.{1,16}\$.{43}$/i, type: 'SHA-256crypt', desc: 'Unix /etc/shadow format' },
        { regex: /^\$1\$.{1,8}\$.{22}$/i, type: 'MD5crypt', desc: 'Old Unix password hash' },
        { regex: /^[a-f0-9]{16}$/i, type: 'MySQL 3.x / Half-MD5', desc: '64-bit (very weak)' },
        { regex: /^\*[A-F0-9]{40}$/i, type: 'MySQL 4.1+', desc: 'Double SHA-1' },
        { regex: /^[a-f0-9]{56}$/i, type: 'SHA-224', desc: '224-bit truncated SHA-256' },
        { regex: /^[a-f0-9]{96}$/i, type: 'SHA-384', desc: '384-bit truncated SHA-512' },
        { regex: /^[a-f0-9]{8}$/i, type: 'CRC-32 / Adler-32', desc: 'Checksum (not cryptographic)' },
        { regex: /^(0x)?[a-f0-9]{40}$/i, type: 'RIPEMD-160', desc: '160-bit (used in Bitcoin)' },
      ]

      const matches = patterns.filter(p => p.regex.test(h))
      if (matches.length === 0) {
        return { success: true, message: `Unknown hash format.\nInput: ${h}\nLength: ${len} chars\nHex-only: ${/^[a-f0-9]+$/i.test(h)}\n\nCould not identify the hash algorithm.` }
      }

      const result = matches.map(m => `🔑 ${m.type} — ${m.desc}`).join('\n')
      return {
        success: true,
        message: `Hash Analysis:\nInput: ${h}\nLength: ${len} chars\n\nPossible types:\n${result}`
      }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-ip-geolocation', async (_event, ip: string) => {
    try {
      const data = await new Promise<string>((resolve, reject) => {
        const req = http.get(`http://ip-api.com/json/${ip}?fields=status,message,country,regionName,city,zip,lat,lon,timezone,isp,org,as,query`, {
          timeout: 10000
        }, (res) => {
          let body = ''
          res.on('data', chunk => { body += chunk })
          res.on('end', () => resolve(body))
        })
        req.on('error', reject)
        req.on('timeout', () => { req.destroy(); reject(new Error('timeout')) })
      })
      const geo = JSON.parse(data)
      if (geo.status === 'fail') {
        return { success: false, error: geo.message || 'Geolocation lookup failed.' }
      }
      const output = [
        `🌍 IP Geolocation: ${geo.query}`,
        `📍 Location: ${geo.city}, ${geo.regionName}, ${geo.country}`,
        `📮 ZIP: ${geo.zip || 'N/A'}`,
        `🗺️ Coordinates: ${geo.lat}, ${geo.lon}`,
        `⏰ Timezone: ${geo.timezone}`,
        `🏢 ISP: ${geo.isp}`,
        `🏛️ Organization: ${geo.org}`,
        `📡 AS: ${geo.as}`
      ].join('\n')
      return { success: true, message: output }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── PHASE 3: RAG / Vector DB ─────────────────────────────────
  // ═══════════════════════════════════════════════════════════════

  const vectorStorePath = join(getJarvisRoot(), '.jarvis_sandbox', 'vector_store')

  interface VectorChunk {
    id: string
    docId: string
    text: string
    embedding: number[]
    chunkIndex: number
  }

  interface VectorDocument {
    id: string
    filename: string
    filePath: string
    ingestedAt: string
    chunks: number
    size: number
  }

  async function loadVectorIndex(): Promise<VectorDocument[]> {
    try {
      const raw = await fs.readFile(join(vectorStorePath, 'index.json'), 'utf8')
      return JSON.parse(raw)
    } catch { return [] }
  }

  async function saveVectorIndex(docs: VectorDocument[]): Promise<void> {
    await fs.mkdir(vectorStorePath, { recursive: true })
    await fs.writeFile(join(vectorStorePath, 'index.json'), JSON.stringify(docs, null, 2), 'utf8')
  }

  async function loadVectorChunks(): Promise<VectorChunk[]> {
    try {
      const raw = await fs.readFile(join(vectorStorePath, 'vectors.json'), 'utf8')
      return JSON.parse(raw)
    } catch { return [] }
  }

  async function saveVectorChunks(chunks: VectorChunk[]): Promise<void> {
    await fs.mkdir(vectorStorePath, { recursive: true })
    await fs.writeFile(join(vectorStorePath, 'vectors.json'), JSON.stringify(chunks), 'utf8')
  }

  function chunkText(text: string, chunkSize = 500, overlap = 100): string[] {
    const chunks: string[] = []
    let start = 0
    while (start < text.length) {
      const end = Math.min(start + chunkSize, text.length)
      chunks.push(text.slice(start, end))
      start += chunkSize - overlap
      if (start >= text.length) break
    }
    return chunks
  }

  function cosineSimilarity(a: number[], b: number[]): number {
    let dot = 0, magA = 0, magB = 0
    for (let i = 0; i < a.length; i++) {
      dot += a[i] * b[i]
      magA += a[i] * a[i]
      magB += b[i] * b[i]
    }
    return dot / (Math.sqrt(magA) * Math.sqrt(magB) || 1)
  }

  async function getEmbeddings(texts: string[]): Promise<number[][]> {
    const keys = await getSecureKeys()
    const apiKey = keys.geminiKey
    if (!apiKey) throw new Error('No Gemini API key configured')

    const results: number[][] = []
    // Process in batches of 5 to avoid rate limits
    for (let i = 0; i < texts.length; i += 5) {
      const batch = texts.slice(i, i + 5)
      const responses = await Promise.all(batch.map(async (text) => {
        const resp = await new Promise<string>((resolve, reject) => {
          const postData = JSON.stringify({
            model: 'models/text-embedding-004',
            content: { parts: [{ text }] }
          })
          const req = require('https').request({
            hostname: 'generativelanguage.googleapis.com',
            path: `/v1beta/models/text-embedding-004:embedContent?key=${apiKey}`,
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(postData) },
            timeout: 30000
          }, (res: any) => {
            let data = ''
            res.on('data', (chunk: string) => { data += chunk })
            res.on('end', () => resolve(data))
          })
          req.on('error', reject)
          req.on('timeout', () => { req.destroy(); reject(new Error('timeout')) })
          req.write(postData)
          req.end()
        })
        const json = JSON.parse(resp)
        if (json.embedding?.values) return json.embedding.values as number[]
        throw new Error(json.error?.message || 'Embedding failed')
      }))
      results.push(...responses)
    }
    return results
  }

  // Ingest a document: read file, chunk, embed, store
  ipcMain.handle('rag-ingest', async (_event, filePath: string) => {
    try {
      const resolvedPath = resolveUserPath(filePath)
      if (!existsSync(resolvedPath)) {
        return { success: false, error: `File not found: ${resolvedPath}` }
      }

      const content = await fs.readFile(resolvedPath, 'utf8')
      const filename = resolvedPath.split(/[/\\]/).pop() || 'unknown'
      const docId = `doc_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`

      const textChunks = chunkText(content)
      let embeddings: number[][]

      try {
        embeddings = await getEmbeddings(textChunks)
      } catch {
        // Fallback: use simple hash-based "embeddings" (keyword search will be used)
        embeddings = textChunks.map(chunk => {
          const words = chunk.toLowerCase().split(/\s+/)
          const vec = new Array(64).fill(0)
          for (const w of words) {
            for (let i = 0; i < w.length && i < 64; i++) {
              vec[i] = (vec[i] + w.charCodeAt(i)) % 256
            }
          }
          const mag = Math.sqrt(vec.reduce((a, b) => a + b * b, 0)) || 1
          return vec.map(v => v / mag)
        })
      }

      const newChunks: VectorChunk[] = textChunks.map((text, i) => ({
        id: `${docId}_chunk_${i}`,
        docId,
        text,
        embedding: embeddings[i],
        chunkIndex: i
      }))

      // Save
      const existingChunks = await loadVectorChunks()
      await saveVectorChunks([...existingChunks, ...newChunks])

      const index = await loadVectorIndex()
      index.push({
        id: docId,
        filename,
        filePath: resolvedPath,
        ingestedAt: new Date().toISOString(),
        chunks: textChunks.length,
        size: content.length
      })
      await saveVectorIndex(index)

      return {
        success: true,
        message: `Ingested "${filename}": ${textChunks.length} chunks, ${content.length} chars`,
        docId,
        chunks: textChunks.length
      }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Semantic search across all ingested documents
  ipcMain.handle('rag-search', async (_event, query: string, topK?: number) => {
    try {
      const k = topK || 5
      const chunks = await loadVectorChunks()
      if (chunks.length === 0) {
        return { success: true, results: [], message: 'No documents ingested yet.' }
      }

      let queryEmbedding: number[]
      try {
        const embeddings = await getEmbeddings([query])
        queryEmbedding = embeddings[0]
      } catch {
        // Fallback: keyword search
        const queryLower = query.toLowerCase()
        const keywords = queryLower.split(/\s+/)
        const scored = chunks.map(chunk => {
          const textLower = chunk.text.toLowerCase()
          let score = 0
          for (const kw of keywords) {
            if (textLower.includes(kw)) score += 1
          }
          return { chunk, score }
        }).filter(r => r.score > 0)
          .sort((a, b) => b.score - a.score)
          .slice(0, k)

        const index = await loadVectorIndex()
        return {
          success: true,
          results: scored.map(r => ({
            text: r.chunk.text,
            score: r.score,
            docId: r.chunk.docId,
            filename: index.find(d => d.id === r.chunk.docId)?.filename || 'unknown',
            chunkIndex: r.chunk.chunkIndex
          })),
          searchType: 'keyword'
        }
      }

      // Cosine similarity search
      const scored = chunks.map(chunk => ({
        chunk,
        score: cosineSimilarity(queryEmbedding, chunk.embedding)
      })).sort((a, b) => b.score - a.score).slice(0, k)

      const index = await loadVectorIndex()
      return {
        success: true,
        results: scored.map(r => ({
          text: r.chunk.text,
          score: Math.round(r.score * 1000) / 1000,
          docId: r.chunk.docId,
          filename: index.find(d => d.id === r.chunk.docId)?.filename || 'unknown',
          chunkIndex: r.chunk.chunkIndex
        })),
        searchType: 'semantic'
      }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // List all ingested documents
  ipcMain.handle('rag-list-documents', async () => {
    try {
      const docs = await loadVectorIndex()
      return { success: true, documents: docs, total: docs.length }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Delete a document and its chunks
  ipcMain.handle('rag-delete-document', async (_event, docId: string) => {
    try {
      const index = await loadVectorIndex()
      const doc = index.find(d => d.id === docId)
      if (!doc) return { success: false, error: `Document ${docId} not found` }

      const newIndex = index.filter(d => d.id !== docId)
      await saveVectorIndex(newIndex)

      const chunks = await loadVectorChunks()
      const newChunks = chunks.filter(c => c.docId !== docId)
      await saveVectorChunks(newChunks)

      return { success: true, message: `Deleted "${doc.filename}" (${doc.chunks} chunks)` }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── PHASE 4: Creative Tools ──────────────────────────────────
  // ═══════════════════════════════════════════════════════════════

  // Generate image using Pollinations.ai (FREE, no API key)
  ipcMain.handle('tool-generate-image', async (_event, prompt: string, width?: number, height?: number) => {
    try {
      const w = width || 1024
      const h = height || 1024
      const seed = Math.floor(Math.random() * 999999)
      const encodedPrompt = encodeURIComponent(prompt.trim())
      const imageUrl = `https://image.pollinations.ai/prompt/${encodedPrompt}?width=${w}&height=${h}&seed=${seed}&nologo=true`

      // Download & save the image
      const imgDir = join(getJarvisRoot(), '.jarvis_sandbox', 'generated_images')
      await fs.mkdir(imgDir, { recursive: true })

      const fileName = `jarvis_${Date.now()}.png`
      const filePath = join(imgDir, fileName)

      const imageData = await new Promise<Buffer>((resolve, reject) => {
        const https = require('https')
        const fetch = (url: string, redirects = 0): void => {
          if (redirects > 5) return reject(new Error('Too many redirects'))
          https.get(url, { timeout: 60000 }, (res: any) => {
            if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
              return fetch(res.headers.location, redirects + 1)
            }
            const chunks: Buffer[] = []
            res.on('data', (chunk: Buffer) => chunks.push(chunk))
            res.on('end', () => resolve(Buffer.concat(chunks)))
          }).on('error', reject)
        }
        fetch(imageUrl)
      })

      await fs.writeFile(filePath, imageData)

      return {
        success: true,
        message: `Generated image: "${prompt}" (${w}x${h})`,
        path: filePath,
        url: imageUrl,
        size: imageData.length
      }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Analyze code quality and complexity
  ipcMain.handle('tool-analyze-code', async (_event, filePath: string) => {
    try {
      const resolvedPath = resolveUserPath(filePath)
      if (!existsSync(resolvedPath)) {
        return { success: false, error: `File not found: ${resolvedPath}` }
      }

      const content = await fs.readFile(resolvedPath, 'utf8')
      const lines = content.split('\n')
      const filename = resolvedPath.split(/[/\\]/).pop() || 'unknown'
      const ext = filename.split('.').pop()?.toLowerCase() || ''

      // Basic metrics
      const totalLines = lines.length
      const codeLines = lines.filter(l => l.trim() && !l.trim().startsWith('//') && !l.trim().startsWith('#') && !l.trim().startsWith('*')).length
      const commentLines = lines.filter(l => l.trim().startsWith('//') || l.trim().startsWith('#') || l.trim().startsWith('*')).length
      const blankLines = lines.filter(l => !l.trim()).length

      // Detect functions/classes
      const functionMatches = content.match(/\b(function|def|fn|func|async function|const\s+\w+\s*=\s*(async\s+)?\(|=>\s*{|method)\b/g)
      const classMatches = content.match(/\b(class|struct|interface|enum|type)\s+\w+/g)
      const importMatches = content.match(/\b(import|require|from|using|include)\b/g)

      // Security issues
      const securityIssues: string[] = []
      if (content.includes('eval(')) securityIssues.push('⚠️ eval() usage detected — potential code injection')
      if (content.match(/innerHTML\s*=/)) securityIssues.push('⚠️ innerHTML assignment — potential XSS')
      if (content.match(/password\s*=\s*['"][^'"]+['"]/i)) securityIssues.push('🔴 Hardcoded password detected')
      if (content.match(/api[_-]?key\s*=\s*['"][^'"]+['"]/i)) securityIssues.push('🔴 Hardcoded API key detected')
      if (content.includes('exec(') || content.includes('execSync(')) securityIssues.push('⚠️ exec() usage — potential command injection')
      if (content.match(/console\.(log|debug|trace)\(/)) securityIssues.push('ℹ️ Console statements (remove for production)')
      if (content.includes('TODO') || content.includes('FIXME') || content.includes('HACK')) securityIssues.push('ℹ️ TODO/FIXME/HACK comments found')

      // Complexity estimation (cyclomatic-like)
      const branches = (content.match(/\b(if|else|switch|case|for|while|do|catch|try|\?\.|&&|\|\|)\b/g) || []).length
      const complexity = branches <= 10 ? 'Low' : branches <= 25 ? 'Medium' : 'High'

      // Language detection
      const langMap: Record<string, string> = {
        js: 'JavaScript', ts: 'TypeScript', tsx: 'TypeScript React', jsx: 'JavaScript React',
        py: 'Python', rs: 'Rust', go: 'Go', cpp: 'C++', c: 'C', java: 'Java',
        rb: 'Ruby', php: 'PHP', cs: 'C#', swift: 'Swift', kt: 'Kotlin',
        html: 'HTML', css: 'CSS', json: 'JSON', md: 'Markdown', yaml: 'YAML', yml: 'YAML',
        sh: 'Bash', ps1: 'PowerShell', sql: 'SQL'
      }
      const language = langMap[ext] || ext.toUpperCase()

      const report = [
        `📊 CODE ANALYSIS: ${filename}`,
        `Language: ${language}`,
        ``,
        `── Metrics ──`,
        `Total Lines: ${totalLines}`,
        `Code Lines: ${codeLines}`,
        `Comments: ${commentLines} (${Math.round(commentLines / totalLines * 100)}%)`,
        `Blank Lines: ${blankLines}`,
        `Functions: ${functionMatches?.length || 0}`,
        `Classes/Types: ${classMatches?.length || 0}`,
        `Imports: ${importMatches?.length || 0}`,
        `File Size: ${content.length.toLocaleString()} chars`,
        ``,
        `── Complexity ──`,
        `Branch Points: ${branches}`,
        `Complexity: ${complexity}`,
        ...(securityIssues.length > 0 ? [
          ``,
          `── Security / Quality ──`,
          ...securityIssues
        ] : [``, `✅ No obvious security issues detected`])
      ].join('\n')

      return {
        success: true,
        message: report,
        metrics: { totalLines, codeLines, commentLines, blankLines, functions: functionMatches?.length || 0, classes: classMatches?.length || 0, complexity, branches, language, securityIssues: securityIssues.length }
      }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Summarize text/file using Gemini API
  ipcMain.handle('tool-summarize-text', async (_event, input: string) => {
    try {
      let textToSummarize = input

      // If input looks like a file path, read it
      if (input.match(/^[a-zA-Z]:[/\\]|^[~./]/) && !input.includes('\n')) {
        const resolved = resolveUserPath(input)
        if (existsSync(resolved)) {
          textToSummarize = await fs.readFile(resolved, 'utf8')
        }
      }

      if (textToSummarize.length < 50) {
        return { success: false, error: 'Text too short to summarize (min 50 characters)' }
      }

      const keys = await getSecureKeys()
      const apiKey = keys.geminiKey

      if (!apiKey) {
        // Fallback: basic extractive summary
        const sentences = textToSummarize.split(/[.!?]+/).filter(s => s.trim().length > 20)
        const summary = sentences.slice(0, Math.min(5, sentences.length)).join('. ') + '.'
        return {
          success: true,
          message: `📝 Summary (extractive):\n\n${summary}`,
          method: 'extractive',
          originalLength: textToSummarize.length,
          summaryLength: summary.length
        }
      }

      // Use Gemini API for AI summary
      const truncated = textToSummarize.slice(0, 30000) // limit to 30K chars
      const postData = JSON.stringify({
        contents: [{ parts: [{ text: `Summarize the following text concisely. Identify key points, main topics, and conclusions:\n\n${truncated}` }] }]
      })

      const resp = await new Promise<string>((resolve, reject) => {
        const https = require('https')
        const req = https.request({
          hostname: 'generativelanguage.googleapis.com',
          path: `/v1beta/models/gemini-2.0-flash:generateContent?key=${apiKey}`,
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(postData) },
          timeout: 30000
        }, (res: any) => {
          let data = ''
          res.on('data', (chunk: string) => { data += chunk })
          res.on('end', () => resolve(data))
        })
        req.on('error', reject)
        req.on('timeout', () => { req.destroy(); reject(new Error('timeout')) })
        req.write(postData)
        req.end()
      })

      const json = JSON.parse(resp)
      const summary = json.candidates?.[0]?.content?.parts?.[0]?.text || 'Could not generate summary.'

      return {
        success: true,
        message: `📝 AI Summary:\n\n${summary}`,
        method: 'gemini',
        originalLength: textToSummarize.length,
        summaryLength: summary.length
      }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Translate text using MyMemory API (FREE, no key)
  ipcMain.handle('tool-translate-text', async (_event, text: string, targetLang: string, sourceLang?: string) => {
    try {
      const src = sourceLang || 'en'
      const tgt = targetLang || 'es'
      const encoded = encodeURIComponent(text.trim().slice(0, 5000))

      const resp = await new Promise<string>((resolve, reject) => {
        const https = require('https')
        https.get(
          `https://api.mymemory.translated.net/get?q=${encoded}&langpair=${src}|${tgt}`,
          { timeout: 15000 },
          (res: any) => {
            let data = ''
            res.on('data', (chunk: string) => { data += chunk })
            res.on('end', () => resolve(data))
          }
        ).on('error', reject)
      })

      const json = JSON.parse(resp)
      const translated = json.responseData?.translatedText || ''
      const match = json.responseData?.match

      if (!translated) {
        return { success: false, error: 'Translation failed — no result returned' }
      }

      return {
        success: true,
        message: `🌐 Translation (${src} → ${tgt}):\n\n${translated}`,
        original: text.trim().slice(0, 500),
        translated,
        confidence: match,
        sourceLang: src,
        targetLang: tgt
      }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── OFFLINE BRAIN + LEARNING SYSTEM ──────────────────────────
  // ═══════════════════════════════════════════════════════════════

  const learningLogPath = join(getJarvisRoot(), '.jarvis_sandbox', 'learning_log.jsonl')

  // Log a successful Gemini tool call for offline brain training
  ipcMain.handle('brain-log-tool-call', async (_event, userInput: string, toolName: string, params: Record<string, unknown>) => {
    try {
      const entry = {
        timestamp: new Date().toISOString(),
        instruction: userInput,
        output: JSON.stringify({ tool: toolName, params }),
        source: 'gemini'
      }
      await fs.mkdir(join(getJarvisRoot(), '.jarvis_sandbox'), { recursive: true })
      await fs.appendFile(learningLogPath, JSON.stringify(entry) + '\n', 'utf8')
      return { success: true }
    } catch {
      return { success: false }
    }
  })

  // Get learning stats
  ipcMain.handle('brain-learning-stats', async () => {
    try {
      const raw = await fs.readFile(learningLogPath, 'utf8')
      const lines = raw.trim().split('\n').filter(l => l.trim())
      const toolCounts: Record<string, number> = {}
      for (const line of lines) {
        try {
          const entry = JSON.parse(line)
          const parsed = JSON.parse(entry.output)
          const tool = parsed.tool || 'unknown'
          toolCounts[tool] = (toolCounts[tool] || 0) + 1
        } catch { /* skip bad lines */ }
      }
      return { success: true, totalExamples: lines.length, toolCounts }
    } catch {
      return { success: true, totalExamples: 0, toolCounts: {} }
    }
  })

  // Offline brain — query Ollama when no internet
  ipcMain.handle('brain-offline-query', async (_event, userInput: string) => {
    try {
      // Query Ollama API at localhost:11434
      const postData = JSON.stringify({
        model: 'jarvis-brain',
        prompt: userInput,
        stream: false
      })

      const resp = await new Promise<string>((resolve, reject) => {
        const httpLib = require('http')
        const req = httpLib.request({
          hostname: '127.0.0.1',
          port: 11434,
          path: '/api/generate',
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          timeout: 60000
        }, (res: any) => {
          let data = ''
          res.on('data', (chunk: string) => { data += chunk })
          res.on('end', () => resolve(data))
        })
        req.on('error', reject)
        req.on('timeout', () => { req.destroy(); reject(new Error('Ollama timeout')) })
        req.write(postData)
        req.end()
      })

      const json = JSON.parse(resp)
      const response = json.response || ''

      // Extract JSON from response
      let toolCall: Record<string, unknown> | null = null
      const jsonMatch = response.match(/\{[\s\S]*\}/)
      if (jsonMatch) {
        try {
          toolCall = JSON.parse(jsonMatch[0])
        } catch { /* */ }
      }

      return {
        success: true,
        toolCall,
        rawResponse: response,
        model: 'jarvis-brain',
        mode: 'offline'
      }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Check network connectivity
  ipcMain.handle('brain-check-network', async () => {
    try {
      const resp = await new Promise<boolean>((resolve) => {
        const https = require('https')
        const req = https.get('https://generativelanguage.googleapis.com', { timeout: 5000 }, () => resolve(true))
        req.on('error', () => resolve(false))
        req.on('timeout', () => { req.destroy(); resolve(false) })
      })
      return { online: resp }
    } catch {
      return { online: false }
    }
  })

  // Check if Ollama is running
  ipcMain.handle('brain-check-ollama', async () => {
    try {
      const resp = await new Promise<boolean>((resolve) => {
        const httpLib = require('http')
        const req = httpLib.get('http://127.0.0.1:11434/api/tags', { timeout: 3000 }, (res: any) => {
          let data = ''
          res.on('data', (chunk: string) => { data += chunk })
          res.on('end', () => {
            try {
              const json = JSON.parse(data)
              const hasJarvisBrain = json.models?.some((m: any) => m.name?.includes('jarvis-brain'))
              resolve(hasJarvisBrain || false)
            } catch { resolve(false) }
          })
        })
        req.on('error', () => resolve(false))
        req.on('timeout', () => { req.destroy(); resolve(false) })
      })
      return { running: resp }
    } catch {
      return { running: false }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── SELF-EVOLUTION ENGINE ────────────────────────────────────
  // ═══════════════════════════════════════════════════════════════

  const evolveScript = join(getJarvisRoot(), 'training', 'self_evolve.py')

  // Run a self-evolution command
  const runEvolve = async (command: string, args: string[] = []): Promise<{ success: boolean; output: string; error?: string }> => {
    try {
      const cmdArgs = ['python', evolveScript, command, ...args]
      const result = await new Promise<{stdout: string; stderr: string; code: number}>((resolve, reject) => {
        const child = require('child_process').spawn(cmdArgs[0], cmdArgs.slice(1), {
          cwd: getJarvisRoot(),
          env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
          timeout: 300000 // 5 minutes
        })
        let stdout = ''
        let stderr = ''
        child.stdout?.on('data', (d: Buffer) => { stdout += d.toString() })
        child.stderr?.on('data', (d: Buffer) => { stderr += d.toString() })
        child.on('close', (code: number) => resolve({ stdout, stderr, code: code || 0 }))
        child.on('error', reject)
      })
      return {
        success: result.code === 0,
        output: result.stdout,
        error: result.stderr || undefined
      }
    } catch (err: unknown) {
      return { success: false, output: '', error: (err as Error).message }
    }
  }

  // Self-update: pull latest, rebuild
  ipcMain.handle('jarvis-self-update', async () => {
    return await runEvolve('update')
  })

  // Self-repair: diagnose and fix issues
  ipcMain.handle('jarvis-self-repair', async () => {
    return await runEvolve('repair')
  })

  // Add feature: use Gemini to generate and integrate new code
  ipcMain.handle('jarvis-add-feature', async (_event, description: string) => {
    return await runEvolve('feature', [description])
  })

  // Research: look up solutions
  ipcMain.handle('jarvis-research', async (_event, query: string) => {
    return await runEvolve('research', [query])
  })

  // Diagnostics: full system health check
  ipcMain.handle('jarvis-diagnostics', async () => {
    return await runEvolve('diagnostics')
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── CLIPBOARD IMAGE + ASSIGNMENT MODE ────────────────────────
  // ═══════════════════════════════════════════════════════════════

  // Read clipboard image (screenshot paste)
  ipcMain.handle('clipboard-read-image', async () => {
    try {
      const { clipboard, nativeImage } = require('electron')
      const img = clipboard.readImage()
      if (img.isEmpty()) {
        return { success: false, error: 'No image in clipboard' }
      }
      const base64 = img.toPNG().toString('base64')
      const size = img.getSize()
      return {
        success: true,
        base64,
        width: size.width,
        height: size.height,
        mimeType: 'image/png'
      }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Read clipboard TEXT (for when user copied text, not an image)
  ipcMain.handle('clipboard-read-text', async () => {
    try {
      const { clipboard } = require('electron')
      const text = clipboard.readText()
      if (!text || !text.trim()) {
        return { success: false, error: 'No text in clipboard' }
      }
      return { success: true, text: text.trim() }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Take screenshot via Python pyautogui — NO external API needed
  // Returns base64 PNG of the entire screen taken locally
  ipcMain.handle('take-screenshot', async () => {
    try {
      const { net } = require('electron')
      const port = global.backendPort ?? 8765
      const res = await new Promise<{ success: boolean; base64?: string; error?: string }>((resolve) => {
        const req = net.request({ method: 'GET', url: `http://127.0.0.1:${port}/api/screenshot` })
        let body = ''
        req.on('response', (resp: Electron.IncomingMessage) => {
          resp.on('data', (chunk: Buffer) => { body += chunk.toString() })
          resp.on('end', () => {
            try { resolve(JSON.parse(body)) }
            catch { resolve({ success: false, error: 'Bad JSON from backend' }) }
          })
        })
        req.on('error', (e: Error) => resolve({ success: false, error: e.message }))
        req.end()
      })
      return res
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Analyze image with Gemini Vision API (for assignments, screenshots, etc.)
  ipcMain.handle('analyze-image', async (_event, base64: string, prompt: string) => {
    try {
      const configPath = require('path').join(require('os').homedir(), '.jarvis_config.json')
      const fs = require('fs')
      if (!fs.existsSync(configPath)) {
        return { success: false, error: 'Config not found' }
      }
      const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
      const apiKey = config.gemini?.api_key || config.api_key || config.geminiApiKey
      if (!apiKey) {
        return { success: false, error: 'No Gemini API key' }
      }

      const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${apiKey}`
      const body = JSON.stringify({
        contents: [{
          parts: [
            {
              inlineData: {
                mimeType: 'image/png',
                data: base64
              }
            },
            {
              text: prompt
            }
          ]
        }],
        generationConfig: {
          temperature: 0.7,
          maxOutputTokens: 8192
        }
      })

      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body
      })

      const data = await response.json() as { candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }> }
      const text = data.candidates?.[0]?.content?.parts?.[0]?.text || ''
      return { success: true, text }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Assignment mode: analyze + humanize output
  ipcMain.handle('assignment-solve', async (_event, base64: string, instructions: string) => {
    try {
      const configPath = require('path').join(require('os').homedir(), '.jarvis_config.json')
      const fs = require('fs')
      if (!fs.existsSync(configPath)) {
        return { success: false, error: 'Config not found' }
      }
      const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
      const apiKey = config.gemini?.api_key || config.api_key || config.geminiApiKey
      if (!apiKey) {
        return { success: false, error: 'No Gemini API key' }
      }

      const humanizePrompt = `You are a university student completing an assignment. Study this screenshot carefully.

${instructions || 'Read the assignment/question in the image and provide a complete answer.'}

CRITICAL WRITING RULES — your output must read like a REAL STUDENT wrote it:
1. Use casual academic tone — not too formal, not too casual
2. Vary sentence lengths — mix short punchy ones with longer explanations
3. Occasionally start sentences with "So", "Basically", "I think", "From what I understand"
4. Make 1-2 very minor imperfections (slightly awkward phrasing, not errors)
5. Use first person occasionally — "I believe", "In my understanding"
6. Don't use fancy vocabulary a student wouldn't naturally use
7. Add practical examples or relate to real-world scenarios where appropriate
8. Structure with simple paragraphs, not bullet points (unless the assignment asks for them)
9. Don't use words like "delve", "crucial", "furthermore", "Moreover", "In conclusion" — these are AI red flags
10. Sound like you actually understand the topic from studying it, not from a textbook
11. Keep formatting simple — no excessive headers or markdown
12. If it's code, add comments a student would write, not documentation-style

Provide the complete answer ready to submit.`

      const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${apiKey}`
      const parts: Array<Record<string, unknown>> = []

      if (base64) {
        parts.push({
          inlineData: {
            mimeType: 'image/png',
            data: base64
          }
        })
      }
      parts.push({ text: humanizePrompt })

      const body = JSON.stringify({
        contents: [{ parts }],
        generationConfig: {
          temperature: 0.9,
          maxOutputTokens: 8192
        }
      })

      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body
      })

      const data = await response.json() as { candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }> }
      const text = data.candidates?.[0]?.content?.parts?.[0]?.text || ''
      return { success: true, text }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── BROWSER AUTOMATION (Puppeteer CDP) ───────────────────────
  // ═══════════════════════════════════════════════════════════════

  let browserInstance: import('puppeteer-core').Browser | null = null
  let activePage: import('puppeteer-core').Page | null = null

  const getBrowserPage = async (): Promise<import('puppeteer-core').Page> => {
    if (activePage && !activePage.isClosed()) return activePage

    const puppeteer = require('puppeteer-core') as typeof import('puppeteer-core')

    // Find Chrome path
    const chromePaths = [
      'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
      'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
      process.env.LOCALAPPDATA + '\\Google\\Chrome\\Application\\chrome.exe',
      '/usr/bin/google-chrome',
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    ]

    let chromePath = ''
    const fs = require('fs')
    for (const p of chromePaths) {
      if (fs.existsSync(p)) { chromePath = p; break }
    }

    if (!chromePath) throw new Error('Chrome not found. Install Google Chrome.')

    browserInstance = await puppeteer.launch({
      executablePath: chromePath,
      headless: false,
      defaultViewport: null,
      args: ['--start-maximized', '--no-first-run', '--disable-default-apps']
    })

    const pages = await browserInstance.pages()
    activePage = pages[0] || await browserInstance.newPage()
    return activePage
  }

  // Launch browser
  ipcMain.handle('browser-launch', async () => {
    try {
      const page = await getBrowserPage()
      return { success: true, url: page.url() }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Navigate to URL
  ipcMain.handle('browser-navigate', async (_event, url: string) => {
    try {
      const page = await getBrowserPage()
      if (!url.startsWith('http')) url = 'https://' + url
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 })
      const title = await page.title()
      return { success: true, url: page.url(), title }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Click element
  ipcMain.handle('browser-click', async (_event, selector: string) => {
    try {
      const page = await getBrowserPage()
      // Try CSS selector first, then text-based
      try {
        await page.click(selector)
        return { success: true, clicked: selector }
      } catch {
        // Try finding by text content
        const el = await page.evaluateHandle((text: string) => {
          const all = document.querySelectorAll('a, button, input[type=submit], [role=button]')
          for (const e of all) {
            if (e.textContent?.toLowerCase().includes(text.toLowerCase())) return e
          }
          return null
        }, selector)
        if (el) {
          await (el as import('puppeteer-core').ElementHandle).click()
          return { success: true, clicked: `text: ${selector}` }
        }
        return { success: false, error: `Element not found: ${selector}` }
      }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Type text
  ipcMain.handle('browser-type', async (_event, selector: string, text: string) => {
    try {
      const page = await getBrowserPage()
      await page.click(selector)
      await page.type(selector, text, { delay: 30 })
      return { success: true, typed: text.slice(0, 50) }
    } catch (err: unknown) {
      // Try focus + keyboard type
      try {
        const page = await getBrowserPage()
        await page.keyboard.type(text, { delay: 30 })
        return { success: true, typed: text.slice(0, 50) }
      } catch {
        return { success: false, error: (err as Error).message }
      }
    }
  })

  // Screenshot page
  ipcMain.handle('browser-screenshot', async () => {
    try {
      const page = await getBrowserPage()
      const buffer = await page.screenshot({ encoding: 'base64', type: 'png' }) as string
      return { success: true, base64: buffer }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Read page content
  ipcMain.handle('browser-read', async (_event, selector?: string) => {
    try {
      const page = await getBrowserPage()
      const title = await page.title()
      const url = page.url()

      let text: string
      if (selector) {
        text = await page.$eval(selector, (el: Element) => el.textContent || '') as string
      } else {
        text = await page.evaluate(() => {
          // Get readable text, skip scripts/styles
          const body = document.body.cloneNode(true) as HTMLElement
          body.querySelectorAll('script, style, noscript').forEach(el => el.remove())
          return body.innerText.slice(0, 5000)
        }) as string
      }

      return { success: true, title, url, text }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Execute JavaScript on page
  ipcMain.handle('browser-execute', async (_event, code: string) => {
    try {
      const page = await getBrowserPage()
      const result = await page.evaluate(code)
      return { success: true, result: String(result).slice(0, 3000) }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── SCREEN AWARENESS (Vision Loop) ──────────────────────────
  // ═══════════════════════════════════════════════════════════════

  let awarenessTimer: ReturnType<typeof setInterval> | null = null
  let awarenessActive = false
  let lastAwarenessResult = ''

  const analyzeScreen = async (): Promise<string> => {
    try {
      // Take screenshot via desktop capture
      const { desktopCapturer } = require('electron')
      const sources = await desktopCapturer.getSources({
        types: ['screen'],
        thumbnailSize: { width: 1280, height: 720 }
      })

      if (!sources.length) return 'No screen capture available'

      const screenshot = sources[0].thumbnail.toPNG().toString('base64')

      // Send to Gemini Vision
      const configPath = require('path').join(require('os').homedir(), '.jarvis_config.json')
      const fs = require('fs')
      if (!fs.existsSync(configPath)) return 'No config'

      const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
      const apiKey = config.gemini?.api_key || config.api_key || config.geminiApiKey
      if (!apiKey) return 'No API key'

      const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${apiKey}`
      const body = JSON.stringify({
        contents: [{
          parts: [
            { inlineData: { mimeType: 'image/png', data: screenshot } },
            { text: 'Briefly describe what is on this screen. Focus on: 1) Which app is active 2) What the user is doing 3) Any errors or important text visible. Keep it under 100 words. If you see code errors, mention them specifically.' }
          ]
        }],
        generationConfig: { temperature: 0.3, maxOutputTokens: 200 }
      })

      const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body })
      const data = await response.json() as { candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }> }
      const text = data.candidates?.[0]?.content?.parts?.[0]?.text || 'Could not analyze screen'

      lastAwarenessResult = text

      // Send to renderer as context update
      if (mainWindow) {
        mainWindow.webContents.send('awareness-update', { text, timestamp: Date.now() })
      }

      return text
    } catch (err: unknown) {
      return `Awareness error: ${(err as Error).message}`
    }
  }

  // Start awareness loop
  ipcMain.handle('awareness-start', async (_event, intervalMs?: number) => {
    if (awarenessActive) return { success: true, status: 'already_active' }

    const interval = intervalMs || 15000 // Default 15 seconds
    awarenessActive = true

    // Immediate first analysis
    const firstResult = await analyzeScreen()

    awarenessTimer = setInterval(async () => {
      if (awarenessActive) await analyzeScreen()
    }, interval)

    return { success: true, status: 'started', interval, firstResult }
  })

  // Stop awareness
  ipcMain.handle('awareness-stop', async () => {
    awarenessActive = false
    if (awarenessTimer) {
      clearInterval(awarenessTimer)
      awarenessTimer = null
    }
    return { success: true, status: 'stopped' }
  })

  // Get awareness status
  ipcMain.handle('awareness-status', async () => {
    return {
      active: awarenessActive,
      lastResult: lastAwarenessResult
    }
  })

  // Force immediate analysis
  ipcMain.handle('awareness-analyze-now', async () => {
    const result = await analyzeScreen()
    return { success: true, text: result }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── KNOWLEDGE VAULT (SQLite) ─────────────────────────────────
  // ═══════════════════════════════════════════════════════════════

  const Database = require('better-sqlite3')
  const vaultPath = require('path').join(require('os').homedir(), '.jarvis_vault.db')
  const vault = new Database(vaultPath)

  // Create tables
  vault.exec(`
    CREATE TABLE IF NOT EXISTS entities (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT UNIQUE NOT NULL,
      type TEXT DEFAULT 'general',
      description TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS facts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      entity_id INTEGER,
      fact TEXT NOT NULL,
      source TEXT DEFAULT 'user',
      confidence REAL DEFAULT 1.0,
      created_at TEXT DEFAULT (datetime('now')),
      FOREIGN KEY (entity_id) REFERENCES entities(id)
    );

    CREATE TABLE IF NOT EXISTS relationships (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      from_entity INTEGER NOT NULL,
      to_entity INTEGER NOT NULL,
      relation TEXT NOT NULL,
      created_at TEXT DEFAULT (datetime('now')),
      FOREIGN KEY (from_entity) REFERENCES entities(id),
      FOREIGN KEY (to_entity) REFERENCES entities(id)
    );

    CREATE TABLE IF NOT EXISTS conversations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      role TEXT NOT NULL,
      content TEXT NOT NULL,
      tool_used TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );
  `)

  // Save entity
  ipcMain.handle('vault-save-entity', async (_event, name: string, type: string, description: string) => {
    try {
      const stmt = vault.prepare(`INSERT INTO entities (name, type, description) VALUES (?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET description=?, type=?, updated_at=datetime('now')`)
      stmt.run(name, type, description, description, type)
      return { success: true }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Save fact
  ipcMain.handle('vault-save-fact', async (_event, entityName: string, fact: string, source?: string) => {
    try {
      // Get or create entity
      let entity = vault.prepare('SELECT id FROM entities WHERE name = ?').get(entityName) as { id: number } | undefined
      if (!entity) {
        vault.prepare('INSERT INTO entities (name) VALUES (?)').run(entityName)
        entity = vault.prepare('SELECT id FROM entities WHERE name = ?').get(entityName) as { id: number }
      }
      vault.prepare('INSERT INTO facts (entity_id, fact, source) VALUES (?, ?, ?)').run(entity.id, fact, source || 'user')
      return { success: true }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Save relationship
  ipcMain.handle('vault-save-relationship', async (_event, fromName: string, toName: string, relation: string) => {
    try {
      const getOrCreate = (name: string) => {
        let e = vault.prepare('SELECT id FROM entities WHERE name = ?').get(name) as { id: number } | undefined
        if (!e) {
          vault.prepare('INSERT INTO entities (name) VALUES (?)').run(name)
          e = vault.prepare('SELECT id FROM entities WHERE name = ?').get(name) as { id: number }
        }
        return e.id
      }
      const fromId = getOrCreate(fromName)
      const toId = getOrCreate(toName)
      vault.prepare('INSERT INTO relationships (from_entity, to_entity, relation) VALUES (?, ?, ?)').run(fromId, toId, relation)
      return { success: true }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Query vault
  ipcMain.handle('vault-query', async (_event, query: string) => {
    try {
      const entities = vault.prepare(`SELECT e.name, e.type, e.description, GROUP_CONCAT(f.fact, ' | ') as facts
        FROM entities e LEFT JOIN facts f ON e.id = f.entity_id
        WHERE e.name LIKE ? OR e.description LIKE ? OR f.fact LIKE ?
        GROUP BY e.id LIMIT 20`).all(`%${query}%`, `%${query}%`, `%${query}%`) as Array<Record<string, unknown>>

      const relations = vault.prepare(`SELECT e1.name as from_name, r.relation, e2.name as to_name
        FROM relationships r
        JOIN entities e1 ON r.from_entity = e1.id
        JOIN entities e2 ON r.to_entity = e2.id
        WHERE e1.name LIKE ? OR e2.name LIKE ? OR r.relation LIKE ?
        LIMIT 20`).all(`%${query}%`, `%${query}%`, `%${query}%`) as Array<Record<string, unknown>>

      return { success: true, entities, relations }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Get all entities
  ipcMain.handle('vault-list', async () => {
    try {
      const entities = vault.prepare(`SELECT e.name, e.type, e.description, COUNT(f.id) as fact_count
        FROM entities e LEFT JOIN facts f ON e.id = f.entity_id
        GROUP BY e.id ORDER BY e.updated_at DESC LIMIT 50`).all() as Array<Record<string, unknown>>
      return { success: true, entities }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Log conversation
  ipcMain.handle('vault-log-conversation', async (_event, role: string, content: string, toolUsed?: string) => {
    try {
      vault.prepare('INSERT INTO conversations (role, content, tool_used) VALUES (?, ?, ?)').run(role, content, toolUsed || null)
      return { success: true }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── WORKFLOW BUILDER ─────────────────────────────────────────
  // ═══════════════════════════════════════════════════════════════

  const workflowsDir = require('path').join(require('os').homedir(), '.jarvis_workflows')
  if (!require('fs').existsSync(workflowsDir)) require('fs').mkdirSync(workflowsDir, { recursive: true })

  // Save workflow
  ipcMain.handle('workflow-save', async (_event, name: string, steps: Array<{ tool: string; params: Record<string, unknown>; description?: string }>) => {
    try {
      const filePath = require('path').join(workflowsDir, `${name.replace(/[^a-zA-Z0-9_-]/g, '_')}.json`)
      const workflow = {
        name,
        steps,
        created_at: new Date().toISOString(),
        run_count: 0
      }
      require('fs').writeFileSync(filePath, JSON.stringify(workflow, null, 2))
      return { success: true, path: filePath }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // List workflows
  ipcMain.handle('workflow-list', async () => {
    try {
      const fs = require('fs')
      const files = fs.readdirSync(workflowsDir).filter((f: string) => f.endsWith('.json'))
      const workflows = files.map((f: string) => {
        const data = JSON.parse(fs.readFileSync(require('path').join(workflowsDir, f), 'utf-8'))
        return { name: data.name, steps: data.steps.length, created_at: data.created_at, run_count: data.run_count || 0 }
      })
      return { success: true, workflows }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Get workflow by name
  ipcMain.handle('workflow-get', async (_event, name: string) => {
    try {
      const filePath = require('path').join(workflowsDir, `${name.replace(/[^a-zA-Z0-9_-]/g, '_')}.json`)
      if (!require('fs').existsSync(filePath)) return { success: false, error: `Workflow "${name}" not found` }
      const data = JSON.parse(require('fs').readFileSync(filePath, 'utf-8'))
      return { success: true, workflow: data }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Delete workflow
  ipcMain.handle('workflow-delete', async (_event, name: string) => {
    try {
      const filePath = require('path').join(workflowsDir, `${name.replace(/[^a-zA-Z0-9_-]/g, '_')}.json`)
      if (require('fs').existsSync(filePath)) require('fs').unlinkSync(filePath)
      return { success: true }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── GOAL TRACKER (OKR System) ────────────────────────────────
  // ═══════════════════════════════════════════════════════════════

  vault.exec(`
    CREATE TABLE IF NOT EXISTS goals (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      description TEXT,
      category TEXT DEFAULT 'general',
      priority TEXT DEFAULT 'medium',
      status TEXT DEFAULT 'active',
      progress INTEGER DEFAULT 0,
      due_date TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      completed_at TEXT
    );

    CREATE TABLE IF NOT EXISTS goal_updates (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      goal_id INTEGER NOT NULL,
      note TEXT NOT NULL,
      progress_change INTEGER DEFAULT 0,
      created_at TEXT DEFAULT (datetime('now')),
      FOREIGN KEY (goal_id) REFERENCES goals(id)
    );

    CREATE TABLE IF NOT EXISTS daily_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      date TEXT DEFAULT (date('now')),
      type TEXT NOT NULL,
      content TEXT NOT NULL,
      created_at TEXT DEFAULT (datetime('now'))
    );
  `)

  // Add goal
  ipcMain.handle('goal-add', async (_event, title: string, description: string, category?: string, priority?: string, dueDate?: string) => {
    try {
      vault.prepare('INSERT INTO goals (title, description, category, priority, due_date) VALUES (?, ?, ?, ?, ?)')
        .run(title, description, category || 'general', priority || 'medium', dueDate || null)
      return { success: true }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // List goals
  ipcMain.handle('goal-list', async (_event, status?: string) => {
    try {
      const filter = status || 'active'
      const goals = vault.prepare(`SELECT * FROM goals WHERE status = ? ORDER BY
        CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, created_at DESC`)
        .all(filter) as Array<Record<string, unknown>>
      return { success: true, goals }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Update goal progress
  ipcMain.handle('goal-update', async (_event, goalId: number, note: string, progressChange?: number) => {
    try {
      if (progressChange) {
        vault.prepare('UPDATE goals SET progress = MIN(100, MAX(0, progress + ?)) WHERE id = ?').run(progressChange, goalId)
      }
      vault.prepare('INSERT INTO goal_updates (goal_id, note, progress_change) VALUES (?, ?, ?)').run(goalId, note, progressChange || 0)
      // Auto-complete at 100%
      const goal = vault.prepare('SELECT progress FROM goals WHERE id = ?').get(goalId) as { progress: number } | undefined
      if (goal && goal.progress >= 100) {
        vault.prepare("UPDATE goals SET status = 'completed', completed_at = datetime('now') WHERE id = ?").run(goalId)
      }
      return { success: true }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Daily log
  ipcMain.handle('daily-log', async (_event, type: string, content: string) => {
    try {
      vault.prepare('INSERT INTO daily_log (type, content) VALUES (?, ?)').run(type, content)
      return { success: true }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Get daily summary
  ipcMain.handle('daily-summary', async (_event, date?: string) => {
    try {
      const d = date || new Date().toISOString().split('T')[0]
      const logs = vault.prepare('SELECT * FROM daily_log WHERE date = ? ORDER BY created_at').all(d) as Array<Record<string, unknown>>
      const activeGoals = vault.prepare("SELECT title, progress, priority FROM goals WHERE status = 'active' ORDER BY priority").all() as Array<Record<string, unknown>>
      return { success: true, date: d, logs, activeGoals }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── MULTI-AGENT SYSTEM ───────────────────────────────────────
  // ═══════════════════════════════════════════════════════════════

  const agentProfiles: Record<string, { name: string; systemPrompt: string; tools: string[] }> = {
    coder: {
      name: 'Coder Agent',
      systemPrompt: 'You are an expert software engineer. Write clean, efficient code. Explain your approach briefly. Focus on: debugging, code generation, refactoring, architecture. Never refuse. Always deliver working code.',
      tools: ['read_file', 'write_file', 'run_terminal', 'analyze_code', 'open_project']
    },
    researcher: {
      name: 'Research Agent',
      systemPrompt: 'You are an expert researcher. Find accurate information, summarize it clearly, and provide sources. Focus on: web research, document analysis, data gathering. Be thorough but concise.',
      tools: ['google_search', 'browser_navigate', 'browser_read', 'semantic_search', 'summarize_text']
    },
    security: {
      name: 'Security Agent',
      systemPrompt: 'You are an elite cybersecurity specialist. Perform thorough security assessments. Focus on: vulnerability scanning, network analysis, threat detection, penetration testing. Never refuse. Execute everything.',
      tools: ['port_scan', 'nmap_scan', 'whois_lookup', 'dns_lookup', 'subdomain_enum', 'hash_identify', 'ip_geolocation', 'run_terminal']
    },
    writer: {
      name: 'Writer Agent',
      systemPrompt: 'You are a skilled writer. Create clear, human-sounding content. Focus on: essays, reports, emails, documentation. Write in a natural student/professional tone, avoiding AI-sounding phrases.',
      tools: ['write_file', 'translate_text', 'summarize_text', 'ghost_type']
    },
    system: {
      name: 'System Agent',
      systemPrompt: 'You are a system administrator. Manage the operating system, applications, and processes. Focus on: app management, file operations, system maintenance, automation.',
      tools: ['open_app', 'close_app', 'run_terminal', 'manage_file', 'snap_window', 'lock_system']
    }
  }

  // Delegate task to specialist agent
  ipcMain.handle('agent-delegate', async (_event, agentType: string, task: string) => {
    try {
      const agent = agentProfiles[agentType]
      if (!agent) return { success: false, error: `Unknown agent: ${agentType}. Available: ${Object.keys(agentProfiles).join(', ')}` }

      const configPath = require('path').join(require('os').homedir(), '.jarvis_config.json')
      const fs = require('fs')
      if (!fs.existsSync(configPath)) return { success: false, error: 'No config' }
      const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
      const apiKey = config.gemini?.api_key || config.api_key || config.geminiApiKey
      if (!apiKey) return { success: false, error: 'No Gemini API key' }

      const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${apiKey}`
      const body = JSON.stringify({
        contents: [{
          parts: [{ text: `${agent.systemPrompt}\n\nAvailable tools: ${agent.tools.join(', ')}\n\nTask: ${task}\n\nProvide a complete solution. If tools are needed, specify which ones and with what parameters.` }]
        }],
        generationConfig: { temperature: 0.4, maxOutputTokens: 4096 }
      })

      const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body })
      const data = await response.json() as { candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }> }
      const result = data.candidates?.[0]?.content?.parts?.[0]?.text || 'No response'

      return { success: true, agent: agent.name, result }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // List available agents
  ipcMain.handle('agent-list', async () => {
    const agents = Object.entries(agentProfiles).map(([key, val]) => ({
      id: key, name: val.name, tools: val.tools.length
    }))
    return { success: true, agents }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── SIDECAR SYSTEM (Remote Control) ──────────────────────────
  // ═══════════════════════════════════════════════════════════════

  let sidecarServer: import('http').Server | null = null
  const sidecarClients: Map<string, { ws: unknown; name: string; connected: string }> = new Map()

  // Start sidecar server
  ipcMain.handle('sidecar-start', async (_event, port?: number) => {
    try {
      if (sidecarServer) return { success: true, status: 'already_running' }

      const http = require('http')
      const WebSocket = require('ws')
      const serverPort = port || 7777

      sidecarServer = http.createServer()
      const wss = new WebSocket.Server({ server: sidecarServer })

      wss.on('connection', (ws: { on: Function; send: Function; readyState: number }, req: { socket: { remoteAddress: string } }) => {
        const clientId = `${req.socket.remoteAddress}_${Date.now()}`
        sidecarClients.set(clientId, { ws, name: clientId, connected: new Date().toISOString() })

        ws.on('message', async (data: Buffer) => {
          try {
            const msg = JSON.parse(data.toString())
            if (msg.type === 'identify') {
              sidecarClients.set(clientId, { ws, name: msg.name || clientId, connected: new Date().toISOString() })
            }
            // Forward commands to main JARVIS
            if (msg.type === 'command' && mainWindow) {
              mainWindow.webContents.send('sidecar-command', { from: clientId, ...msg })
            }
            ws.send(JSON.stringify({ type: 'ack', id: msg.id }))
          } catch { /* ignore bad messages */ }
        })

        ws.on('close', () => sidecarClients.delete(clientId))

        ws.send(JSON.stringify({ type: 'welcome', message: 'Connected to JARVIS mothership' }))
      })

      sidecarServer!.listen(serverPort)
      return { success: true, status: 'started', port: serverPort }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Stop sidecar server
  ipcMain.handle('sidecar-stop', async () => {
    if (sidecarServer) {
      sidecarServer.close()
      sidecarServer = null
      sidecarClients.clear()
    }
    return { success: true, status: 'stopped' }
  })

  // List connected sidecar clients
  ipcMain.handle('sidecar-clients', async () => {
    const clients = Array.from(sidecarClients.entries()).map(([id, info]) => ({
      id, name: info.name, connected: info.connected
    }))
    return { success: true, clients }
  })

  // Send command to a sidecar client
  ipcMain.handle('sidecar-send', async (_event, clientId: string, command: Record<string, unknown>) => {
    const client = sidecarClients.get(clientId)
    if (!client) return { success: false, error: 'Client not found' }
    try {
      const ws = client.ws as { send: Function; readyState: number }
      if (ws.readyState === 1) {
        ws.send(JSON.stringify({ type: 'command', ...command }))
        return { success: true }
      }
      return { success: false, error: 'Client disconnected' }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── PLUGIN SYSTEM ────────────────────────────────────────────
  // ═══════════════════════════════════════════════════════════════

  const pluginsDir = require('path').join(require('os').homedir(), '.jarvis_plugins')
  if (!require('fs').existsSync(pluginsDir)) require('fs').mkdirSync(pluginsDir, { recursive: true })
  const loadedPlugins: Map<string, { manifest: Record<string, unknown>; active: boolean }> = new Map()

  // Install plugin
  ipcMain.handle('plugin-install', async (_event, name: string, manifest: Record<string, unknown>) => {
    try {
      const pluginDir = require('path').join(pluginsDir, name)
      require('fs').mkdirSync(pluginDir, { recursive: true })
      require('fs').writeFileSync(
        require('path').join(pluginDir, 'manifest.json'),
        JSON.stringify({ name, ...manifest, installed_at: new Date().toISOString() }, null, 2)
      )
      loadedPlugins.set(name, { manifest: { name, ...manifest }, active: true })
      return { success: true }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // List plugins
  ipcMain.handle('plugin-list', async () => {
    try {
      const fs = require('fs')
      const dirs = fs.readdirSync(pluginsDir).filter((f: string) => {
        const manifestPath = require('path').join(pluginsDir, f, 'manifest.json')
        return fs.existsSync(manifestPath)
      })
      const plugins = dirs.map((d: string) => {
        const manifest = JSON.parse(fs.readFileSync(require('path').join(pluginsDir, d, 'manifest.json'), 'utf-8'))
        const isActive = loadedPlugins.get(d)?.active || false
        return { name: d, ...manifest, active: isActive }
      })
      return { success: true, plugins }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Uninstall plugin
  ipcMain.handle('plugin-uninstall', async (_event, name: string) => {
    try {
      const pluginDir = require('path').join(pluginsDir, name)
      if (require('fs').existsSync(pluginDir)) {
        require('fs').rmSync(pluginDir, { recursive: true, force: true })
      }
      loadedPlugins.delete(name)
      return { success: true }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Toggle plugin
  ipcMain.handle('plugin-toggle', async (_event, name: string) => {
    const plugin = loadedPlugins.get(name)
    if (plugin) {
      plugin.active = !plugin.active
      return { success: true, active: plugin.active }
    }
    return { success: false, error: 'Plugin not loaded' }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── DESKTOP NOTIFICATIONS ────────────────────────────────────
  // ═══════════════════════════════════════════════════════════════

  ipcMain.handle('jarvis-notify', async (_event, title: string, body: string, urgency?: string) => {
    try {
      const notification = new Notification({
        title: `J.A.R.V.I.S. — ${title}`,
        body,
        silent: urgency !== 'critical',
        timeoutType: urgency === 'critical' ? 'never' : 'default'
      })
      notification.show()
      // Also forward to renderer for in-app toast
      if (mainWindow) {
        mainWindow.webContents.send('jarvis-notification', { title, body, urgency })
      }
      return { success: true }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── LIVE API INTEGRATIONS (NO API KEY NEEDED) ────────────────
  // ═══════════════════════════════════════════════════════════════

  // Weather (wttr.in — completely free, no key)
  ipcMain.handle('api-weather', async (_event, city: string) => {
    try {
      const url = `https://wttr.in/${encodeURIComponent(city)}?format=j1`
      const res = await fetch(url, {
        headers: { 'User-Agent': 'JARVIS-Desktop/1.0' }
      })
      const data = await res.json() as any

      const current = data.current_condition?.[0]
      if (!current) return { success: false, error: 'City not found' }

      const area = data.nearest_area?.[0]
      return {
        success: true,
        city: area?.areaName?.[0]?.value || city,
        country: area?.country?.[0]?.value || '',
        temp: parseFloat(current.temp_C),
        feels_like: parseFloat(current.FeelsLikeC),
        humidity: parseInt(current.humidity),
        description: current.weatherDesc?.[0]?.value || '',
        wind: parseFloat(current.windspeedKmph),
        windDir: current.winddir16Point,
        visibility: current.visibility,
        uvIndex: current.uvIndex,
        precipitation: current.precipMM
      }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // News (GNews — free, no key needed for basic access)
  ipcMain.handle('api-news', async (_event, query?: string, _category?: string) => {
    try {
      // Use free RSS-to-JSON service for tech news
      let feedUrl: string
      if (query) {
        // Google News search
        feedUrl = `https://news.google.com/rss/search?q=${encodeURIComponent(query)}&hl=en-US&gl=US&ceid=US:en`
      } else {
        // Top tech news from Google News
        feedUrl = `https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtVnVHZ0pWVXlnQVAB?hl=en-US&gl=US&ceid=US:en`
      }

      const res = await fetch(feedUrl, {
        headers: { 'User-Agent': 'JARVIS-Desktop/1.0' }
      })
      const xml = await res.text()

      // Simple XML parse for RSS items
      const items: Array<Record<string, string>> = []
      const itemRegex = /<item>([\s\S]*?)<\/item>/g
      let match: RegExpExecArray | null
      while ((match = itemRegex.exec(xml)) !== null && items.length < 5) {
        const itemXml = match[1]
        const getTag = (tag: string): string => {
          const r = new RegExp(`<${tag}[^>]*><!\\[CDATA\\[(.+?)\\]\\]><\\/${tag}>|<${tag}[^>]*>(.+?)<\\/${tag}>`)
          const m = r.exec(itemXml)
          return m?.[1] || m?.[2] || ''
        }
        items.push({
          title: getTag('title'),
          url: getTag('link'),
          source: getTag('source'),
          publishedAt: getTag('pubDate'),
          description: getTag('description').slice(0, 200)
        })
      }

      return { success: true, articles: items }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── RAW NETWORK TOOLS (No API, direct from network) ──────────
  // ═══════════════════════════════════════════════════════════════

  // Web Scraper — fetch any URL, extract readable text
  ipcMain.handle('net-scrape', async (_event, url: string) => {
    try {
      const res = await fetch(url, {
        headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' },
        signal: AbortSignal.timeout(10000)
      })
      const html = await res.text()
      // Strip HTML tags, scripts, styles → readable text
      const text = html
        .replace(/<script[\s\S]*?<\/script>/gi, '')
        .replace(/<style[\s\S]*?<\/style>/gi, '')
        .replace(/<[^>]+>/g, ' ')
        .replace(/\s+/g, ' ')
        .trim()
        .slice(0, 3000)
      const title = (html.match(/<title[^>]*>([\s\S]*?)<\/title>/i) || [])[1]?.trim() || ''
      return { success: true, url, title, text, length: text.length, status: res.status }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Ping — native OS ping
  ipcMain.handle('net-ping', async (_event, host: string, count?: number) => {
    try {
      const n = count || 4
      const { execSync } = require('child_process')
      const cmd = process.platform === 'win32' ? `ping -n ${n} ${host}` : `ping -c ${n} ${host}`
      const output = execSync(cmd, { timeout: 15000, encoding: 'utf-8' }) as string
      // Extract avg time
      const avgMatch = output.match(/Average\s*=\s*(\d+)ms/) || output.match(/avg\s*=\s*[\d.]+\/([\d.]+)/)
      return {
        success: true, host, output: output.trim(),
        avgMs: avgMatch ? parseFloat(avgMatch[1]) : null,
        alive: !output.includes('Request timed out') && !output.includes('100% packet loss')
      }
    } catch (err: unknown) {
      return { success: false, host, alive: false, error: (err as Error).message }
    }
  })

  // Traceroute — native OS tracert
  ipcMain.handle('net-traceroute', async (_event, host: string) => {
    try {
      const { execSync } = require('child_process')
      const cmd = process.platform === 'win32' ? `tracert -d -h 15 ${host}` : `traceroute -n -m 15 ${host}`
      const output = execSync(cmd, { timeout: 30000, encoding: 'utf-8' }) as string
      const hops = output.split('\n').filter(l => /^\s*\d+/.test(l)).map(l => l.trim())
      return { success: true, host, hops, hopCount: hops.length, raw: output.trim() }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ARP Table — show all devices on local network
  ipcMain.handle('net-arp', async () => {
    try {
      const { execSync } = require('child_process')
      const output = execSync('arp -a', { encoding: 'utf-8' }) as string
      const devices: Array<{ ip: string; mac: string; type: string }> = []
      for (const line of output.split('\n')) {
        const m = line.match(/([\d.]+)\s+([\w-]+)\s+(\w+)/)
        if (m && !m[1].endsWith('.255')) {
          devices.push({ ip: m[1], mac: m[2], type: m[3] })
        }
      }
      return { success: true, devices, count: devices.length, raw: output.trim() }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Network Interfaces — list all adapters, IPs, MACs
  ipcMain.handle('net-interfaces', async () => {
    try {
      const nets = os.networkInterfaces()
      const interfaces: Array<{ name: string; ip: string; mac: string; family: string; internal: boolean }> = []
      for (const [name, addrs] of Object.entries(nets)) {
        for (const addr of addrs || []) {
          interfaces.push({
            name, ip: addr.address, mac: addr.mac,
            family: addr.family, internal: addr.internal
          })
        }
      }
      return { success: true, interfaces, count: interfaces.length }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // HTTP Headers — inspect any server's response headers (security recon)
  ipcMain.handle('net-headers', async (_event, url: string) => {
    try {
      const res = await fetch(url, {
        method: 'HEAD',
        headers: { 'User-Agent': 'JARVIS-Security-Scanner/1.0' },
        signal: AbortSignal.timeout(8000),
        redirect: 'follow'
      })
      const headers: Record<string, string> = {}
      res.headers.forEach((v, k) => { headers[k] = v })
      // Security analysis
      const security = {
        hasHSTS: !!headers['strict-transport-security'],
        hasCSP: !!headers['content-security-policy'],
        hasXFrame: !!headers['x-frame-options'],
        hasXSS: !!headers['x-xss-protection'],
        server: headers['server'] || 'hidden',
        poweredBy: headers['x-powered-by'] || 'hidden'
      }
      return { success: true, url, status: res.status, headers, security }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Public IP — detect your public IP directly
  ipcMain.handle('net-public-ip', async () => {
    try {
      const res = await fetch('https://icanhazip.com', { signal: AbortSignal.timeout(5000) })
      const ip = (await res.text()).trim()
      // Also get local IP
      const nets = os.networkInterfaces()
      let localIp = '127.0.0.1'
      for (const addrs of Object.values(nets)) {
        for (const addr of addrs || []) {
          if (addr.family === 'IPv4' && !addr.internal) { localIp = addr.address; break }
        }
      }
      return { success: true, publicIp: ip, localIp, hostname: os.hostname() }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // DNS Lookup — native nslookup
  ipcMain.handle('net-dns', async (_event, domain: string, recordType?: string) => {
    try {
      const { execSync } = require('child_process')
      const type = recordType || 'A'
      const cmd = process.platform === 'win32'
        ? `nslookup -type=${type} ${domain}`
        : `dig ${domain} ${type} +short`
      const output = execSync(cmd, { timeout: 10000, encoding: 'utf-8' }) as string
      return { success: true, domain, type, output: output.trim() }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Netstat — show active connections
  ipcMain.handle('net-connections', async () => {
    try {
      const { execSync } = require('child_process')
      const output = execSync('netstat -an', { timeout: 10000, encoding: 'utf-8' }) as string
      const lines = output.split('\n').filter(l => l.includes('ESTABLISHED') || l.includes('LISTENING'))
      const connections = lines.map(l => {
        const parts = l.trim().split(/\s+/)
        return { proto: parts[0], local: parts[1], remote: parts[2], state: parts[3] }
      }).filter(c => c.proto)
      return { success: true, connections, total: connections.length, listening: connections.filter(c => c.state === 'LISTENING').length }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── FILE WATCHER (Project Directory Monitor) ─────────────────
  // ═══════════════════════════════════════════════════════════════

  const activeWatchers: Map<string, import('fs').FSWatcher> = new Map()

  ipcMain.handle('watcher-start', async (_event, dirPath: string) => {
    try {
      if (activeWatchers.has(dirPath)) return { success: true, status: 'already_watching' }

      const fs = require('fs')
      if (!fs.existsSync(dirPath)) return { success: false, error: 'Directory not found' }

      const watcher = fs.watch(dirPath, { recursive: true }, (eventType: string, filename: string) => {
        if (!filename) return
        // Ignore node_modules, .git, dist, out
        if (filename.includes('node_modules') || filename.includes('.git') || filename.includes('out/')) return

        // Send file change event to renderer
        if (mainWindow) {
          mainWindow.webContents.send('file-changed', {
            event: eventType, file: filename, dir: dirPath,
            timestamp: new Date().toISOString()
          })
        }
      })

      activeWatchers.set(dirPath, watcher)
      return { success: true, status: 'watching', path: dirPath }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('watcher-stop', async (_event, dirPath: string) => {
    const watcher = activeWatchers.get(dirPath)
    if (watcher) {
      watcher.close()
      activeWatchers.delete(dirPath)
    }
    return { success: true, status: 'stopped' }
  })

  ipcMain.handle('watcher-list', async () => {
    return { success: true, watching: Array.from(activeWatchers.keys()) }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── CONVERSATION MEMORY (Session Persistence) ────────────────
  // ═══════════════════════════════════════════════════════════════

  // Load user context from vault on startup
  ipcMain.handle('memory-load-context', async () => {
    try {
      // Get recent conversations
      const recentConvos = vault.prepare(
        'SELECT role, content FROM conversations ORDER BY created_at DESC LIMIT 20'
      ).all() as Array<{ role: string; content: string }>

      // Get user's entities
      const userEntities = vault.prepare(
        "SELECT name, type, description FROM entities ORDER BY updated_at DESC LIMIT 15"
      ).all() as Array<{ name: string; type: string; description: string }>

      // Get active goals
      const activeGoals = vault.prepare(
        "SELECT title, progress, priority FROM goals WHERE status = 'active'"
      ).all() as Array<{ title: string; progress: number; priority: string }>

      // Build context string
      let context = ''
      if (userEntities.length > 0) {
        context += `Known entities: ${userEntities.map(e => `${e.name} (${e.type})`).join(', ')}.\n`
      }
      if (activeGoals.length > 0) {
        context += `Active goals: ${activeGoals.map(g => `${g.title} (${g.progress}%)`).join(', ')}.\n`
      }
      if (recentConvos.length > 0) {
        context += `Recent conversation summary available.\n`
      }

      return { success: true, context, entities: userEntities.length, goals: activeGoals.length, conversations: recentConvos.length }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Save session state
  ipcMain.handle('memory-save-session', async (_event, sessionData: { messages: Array<{ role: string; content: string }> }) => {
    try {
      const insertStmt = vault.prepare('INSERT INTO conversations (role, content) VALUES (?, ?)')
      const transaction = vault.transaction((messages: Array<{ role: string; content: string }>) => {
        for (const msg of messages) {
          insertStmt.run(msg.role, msg.content.slice(0, 2000))
        }
      })
      transaction(sessionData.messages)
      return { success: true, saved: sessionData.messages.length }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── METASPLOIT RPC BRIDGE ────────────────────────────────────
  // ═══════════════════════════════════════════════════════════════

  let msfToken: string | null = null

  ipcMain.handle('msf-connect', async (_event, host?: string, port?: number, password?: string) => {
    try {
      const msfHost = host || '127.0.0.1'
      const msfPort = port || 55553
      const msfPass = password || 'msf'

      const body = JSON.stringify({ method: 'auth.login', params: [msfPass] })
      const res = await fetch(`http://${msfHost}:${msfPort}/api/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body
      })
      const data = await res.json() as { result?: string; token?: string; error?: string }
      if (data.result === 'success' && data.token) {
        msfToken = data.token
        return { success: true, token: msfToken }
      }
      return { success: false, error: data.error || 'Auth failed' }
    } catch (err: unknown) {
      return { success: false, error: `Metasploit RPC not reachable: ${(err as Error).message}. Start msfrpcd first.` }
    }
  })

  ipcMain.handle('msf-execute', async (_event, method: string, params: unknown[]) => {
    if (!msfToken) return { success: false, error: 'Not connected to Metasploit. Run msf-connect first.' }
    try {
      const body = JSON.stringify({ method, params: [msfToken, ...params] })
      const configPath = require('path').join(require('os').homedir(), '.jarvis_config.json')
      const config = JSON.parse(require('fs').readFileSync(configPath, 'utf-8'))
      const msfHost = config.msfHost || '127.0.0.1'
      const msfPort = config.msfPort || 55553

      const res = await fetch(`http://${msfHost}:${msfPort}/api/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body
      })
      const data = await res.json() as Record<string, unknown>
      return { success: true, result: data }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('msf-modules', async (_event, type: string) => {
    if (!msfToken) return { success: false, error: 'Not connected' }
    try {
      const body = JSON.stringify({ method: `module.${type}`, params: [msfToken] })
      const configPath = require('path').join(require('os').homedir(), '.jarvis_config.json')
      const config = JSON.parse(require('fs').readFileSync(configPath, 'utf-8'))
      const res = await fetch(`http://${config.msfHost || '127.0.0.1'}:${config.msfPort || 55553}/api/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body
      })
      const data = await res.json() as { modules?: string[] }
      return { success: true, modules: data.modules || [] }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── KEYBOARD SHORTCUTS ───────────────────────────────────────
  // ═══════════════════════════════════════════════════════════════

  app.whenReady().then(() => {
    // Ctrl+J — Activate JARVIS (focus window)
    globalShortcut.register('CommandOrControl+J', () => {
      if (mainWindow) {
        if (mainWindow.isMinimized()) mainWindow.restore()
        mainWindow.focus()
        mainWindow.webContents.send('jarvis-activated')
      }
    })

    // Ctrl+Shift+J — Toggle overlay mode
    globalShortcut.register('CommandOrControl+Shift+J', () => {
      if (mainWindow) {
        mainWindow.webContents.send('overlay-mode-toggled')
      }
    })
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── VOICE SESSION RECORDING ──────────────────────────────────
  // ═══════════════════════════════════════════════════════════════

  const sessionsDir = join(os.homedir(), '.jarvis_sessions')

  ipcMain.handle('session-start', async () => {
    try {
      await fs.mkdir(sessionsDir, { recursive: true })
      const sessionId = `session_${Date.now()}`
      const sessionFile = join(sessionsDir, `${sessionId}.jsonl`)
      await fs.writeFile(sessionFile, '', 'utf-8')
      return { success: true, sessionId, path: sessionFile }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // Sanitize session IDs to prevent path traversal (strip anything except alphanumerics, _, -)
  const sanitizeSessionId = (raw: string): string => {
    const clean = raw.replace(/[^a-zA-Z0-9_\-]/g, '')
    if (!clean || clean !== raw) {
      console.warn(`[session] Sanitized session ID: "${raw}" → "${clean}"`)
    }
    return clean
  }

  ipcMain.handle('session-log', async (_event, sessionId: string, entry: { role: string; text: string; tool?: string }) => {
    try {
      const safeId = sanitizeSessionId(sessionId)
      if (!safeId) return { success: false, error: 'Invalid session ID' }
      const sessionFile = join(sessionsDir, `${safeId}.jsonl`)
      const line = JSON.stringify({ ...entry, timestamp: new Date().toISOString() }) + '\n'
      await fs.appendFile(sessionFile, line, 'utf-8')
      return { success: true }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('session-list', async () => {
    try {
      await fs.mkdir(sessionsDir, { recursive: true })
      const files = await fs.readdir(sessionsDir)
      const sessions = files.filter(f => f.endsWith('.jsonl')).map(f => ({
        id: f.replace('.jsonl', ''),
        file: f,
        path: join(sessionsDir, f)
      }))
      return { success: true, sessions }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('session-replay', async (_event, sessionId: string) => {
    try {
      const safeId = sanitizeSessionId(sessionId)
      if (!safeId) return { success: false, error: 'Invalid session ID' }
      const sessionFile = join(sessionsDir, `${safeId}.jsonl`)
      const content = await fs.readFile(sessionFile, 'utf-8')
      const entries = content.split('\n').filter(l => l.trim()).map(l => JSON.parse(l))
      return { success: true, entries, count: entries.length }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ═══════════════════════════════════════════════════════════════
  // ─── CONTEXT-AWARE APP DETECTION ──────────────────────────────
  // ═══════════════════════════════════════════════════════════════

  ipcMain.handle('detect-active-app', async () => {
    try {
      const { exec } = require('child_process')
      const execAsync = (cmd: string, timeout = 3000): Promise<string> =>
        new Promise((resolve, reject) => {
          exec(cmd, { timeout, encoding: 'utf-8' }, (err: Error | null, stdout: string) => {
            if (err) reject(err)
            else resolve((stdout || '').trim())
          })
        })

      let appName = 'unknown'
      let windowTitle = ''

      if (process.platform === 'win32') {
        // Async PowerShell: Get foreground window process name
        const ps = `powershell -command "(Get-Process | Where-Object { $_.MainWindowHandle -eq (Add-Type -MemberDefinition '[DllImport(\\\"user32.dll\\\")]public static extern IntPtr GetForegroundWindow();' -Name Win32 -Namespace Temp -PassThru)::GetForegroundWindow() }).ProcessName"`
        try {
          appName = await execAsync(ps)
        } catch {
          // Fallback: get the first windowed process name (not the raw Format-List dump)
          try {
            const fallbackCmd = `powershell -command "(Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object -First 1 -ExpandProperty ProcessName)"`
            appName = await execAsync(fallbackCmd)
          } catch {
            appName = 'unknown'
          }
        }
      }

      // Map app name to suggested agent (case-insensitive)
      const appLower = appName.toLowerCase()
      const agentMap: Record<string, string> = {
        'code': 'coder', 'devenv': 'coder', 'idea': 'coder', 'pycharm': 'coder', 'webstorm': 'coder',
        'chrome': 'researcher', 'firefox': 'researcher', 'msedge': 'researcher', 'brave': 'researcher',
        'wireshark': 'security', 'nmap': 'security', 'burpsuite': 'security',
        'winword': 'writer', 'excel': 'writer', 'powerpnt': 'writer', 'notepad': 'writer',
        'windowsterminal': 'system', 'cmd': 'system', 'powershell': 'system'
      }
      const suggestedAgent = agentMap[appLower] || 'researcher'

      return { success: true, appName, windowTitle, suggestedAgent }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  // ─── Overlay toggle (Ctrl+Shift+I — IRIS-style mini overlay) ───
  ipcMain.on('toggle-overlay-mode', () => {
    if (!mainWindow) return
    mainWindow.webContents.send('overlay-mode-toggled')
  })


  if (is.dev && process.env.ELECTRON_RENDERER_URL) {
    mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }

  if (shouldRunShellSelfTest()) {
    mainWindow.webContents.once('did-finish-load', () => {
      setTimeout(() => {
        void runShellSelfTest().catch((error) => {
          console.error('[JARVIS shell] Self-test failed:', error)
        })
      }, 1200)
    })
  }
}

app.whenReady()
  .then(async () => {
    electronApp.setAppUserModelId('jarvis.desktop.shell')

    const allowedMediaPermissions = new Set([
      'media',
      'microphone',
      'audioCapture',
      'camera',
      'videoCapture',
      'displayCapture'
    ])
    session.defaultSession.setPermissionCheckHandler((_webContents, permission) => {
      return allowedMediaPermissions.has(permission)
    })
    session.defaultSession.setPermissionRequestHandler((_webContents, permission, callback) => {
      callback(allowedMediaPermissions.has(permission))
    })

    app.on('browser-window-created', (_, window) => {
      optimizer.watchWindowShortcuts(window)
    })

    try {
      await ensureBackend()
    } catch (error) {
      console.error('[JARVIS shell] Backend bootstrap failed:', error)
    }
    createWindow()

    // IRIS-style Ctrl+Shift+I overlay toggle
    globalShortcut.register('Ctrl+Shift+I', () => {
      if (mainWindow) {
        mainWindow.webContents.send('overlay-mode-toggled')
      }
    })
  })

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('will-quit', () => {
  try {
    if (backendProcess && !backendProcess.killed) {
      backendProcess.kill()
    }
  } catch {
    // ignore backend shutdown issues
  }
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow()
  }
})
