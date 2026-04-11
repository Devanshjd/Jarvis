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

  // Analyze image with Gemini Vision API (for assignments, screenshots, etc.)
  ipcMain.handle('analyze-image', async (_event, base64: string, prompt: string) => {
    try {
      const configPath = require('path').join(require('os').homedir(), '.jarvis_config.json')
      const fs = require('fs')
      if (!fs.existsSync(configPath)) {
        return { success: false, error: 'Config not found' }
      }
      const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
      const apiKey = config.geminiApiKey
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
      const apiKey = config.geminiApiKey
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
