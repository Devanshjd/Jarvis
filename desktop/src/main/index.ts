import { app, BrowserWindow, desktopCapturer, globalShortcut, ipcMain, shell, session } from 'electron'
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
      const content = await fs.readFile(filePath, 'utf8')
      return { success: true, content: content.slice(0, 10000) }
    } catch (err: unknown) {
      return { success: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('tool-write-file', async (_event, fileName: string, content: string) => {
    try {
      // If no directory specified, default to Desktop
      let target = fileName
      if (!fileName.includes('/') && !fileName.includes('\\')) {
        target = join(app.getPath('desktop'), fileName)
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
        if (operation === 'delete') {
          await fs.unlink(sourcePath)
          return { success: true, message: `Deleted ${sourcePath}` }
        } else if (operation === 'copy' && destPath) {
          await fs.mkdir(dirname(destPath), { recursive: true })
          await fs.copyFile(sourcePath, destPath)
          return { success: true, message: `Copied to ${destPath}` }
        } else if (operation === 'move' && destPath) {
          await fs.mkdir(dirname(destPath), { recursive: true })
          await fs.rename(sourcePath, destPath)
          return { success: true, message: `Moved to ${destPath}` }
        }
        return { success: false, error: 'Invalid operation or missing destination' }
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
      // Use Windows 'where' and 'dir' for basic search
      const searchDirs = [
        app.getPath('desktop'),
        app.getPath('documents'),
        app.getPath('downloads'),
        app.getPath('pictures')
      ]
      const results: string[] = []
      const keywords = query.toLowerCase().split(/\s+/)

      for (const dir of searchDirs) {
        try {
          const entries = await fs.readdir(dir)
          for (const entry of entries) {
            const lower = entry.toLowerCase()
            if (keywords.some((kw) => lower.includes(kw))) {
              results.push(join(dir, entry))
            }
          }
        } catch {
          // skip inaccessible dirs
        }
      }

      return {
        success: true,
        results: results.slice(0, 20),
        message: results.length > 0 ? `Found ${results.length} files` : 'No files found'
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
      // Use PowerShell SendKeys to type text
      const escaped = text.replace(/'/g, "''").replace(/\+/g, '{+}').replace(/\^/g, '{^}').replace(/%/g, '{%}').replace(/~/g, '{~}')
      spawnSync('powershell', [
        '-Command',
        `Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('${escaped}')`
      ], { shell: true, timeout: 5000 })
      return { success: true, message: `Typed: "${text.slice(0, 50)}"` }
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
