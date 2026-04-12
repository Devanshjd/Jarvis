import { contextBridge, ipcRenderer } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'

const desktopApi = {
  windowMin: () => ipcRenderer.send('window-min'),
  windowMax: () => ipcRenderer.send('window-max'),
  windowClose: () => ipcRenderer.send('window-close'),
  backendStatus: () => ipcRenderer.invoke('backend-status'),
  shellSnapshot: () => ipcRenderer.invoke('jarvis-shell-snapshot'),
  listRunningApps: () => ipcRenderer.invoke('jarvis-shell-running-apps'),
  getScreenSource: () => ipcRenderer.invoke('get-screen-source'),
  secureGetKeys: () => ipcRenderer.invoke('secure-get-keys'),
  openPath: (targetPath: string) => ipcRenderer.invoke('jarvis-shell-open-path', targetPath),
  saveSettings: (payload: unknown) => ipcRenderer.invoke('jarvis-shell-save-settings', payload),

  // System stats (IRIS-style real metrics)
  systemStats: () => ipcRenderer.invoke('system-stats'),

  // Notes CRUD
  notesList: () => ipcRenderer.invoke('notes-list'),
  notesCreate: (title: string, content: string) => ipcRenderer.invoke('notes-create', title, content),
  notesUpdate: (id: string, content: string) => ipcRenderer.invoke('notes-update', id, content),
  notesDelete: (id: string) => ipcRenderer.invoke('notes-delete', id),

  // Overlay mode toggle listener
  onOverlayToggle: (callback: () => void) => {
    ipcRenderer.on('overlay-mode-toggled', () => callback())
    return () => {
      ipcRenderer.removeAllListeners('overlay-mode-toggled')
    }
  },

  // ─── Native Voice Tools (Phase 1 — Batch A) ───
  toolReadFile: (filePath: string) => ipcRenderer.invoke('tool-read-file', filePath),
  toolWriteFile: (fileName: string, content: string) =>
    ipcRenderer.invoke('tool-write-file', fileName, content),
  toolManageFile: (operation: string, sourcePath: string, destPath?: string) =>
    ipcRenderer.invoke('tool-manage-file', operation, sourcePath, destPath),
  toolReadDirectory: (dirPath: string) => ipcRenderer.invoke('tool-read-directory', dirPath),
  toolCreateFolder: (folderPath: string) => ipcRenderer.invoke('tool-create-folder', folderPath),
  toolOpenApp: (appName: string) => ipcRenderer.invoke('tool-open-app', appName),
  toolCloseApp: (appName: string) => ipcRenderer.invoke('tool-close-app', appName),
  toolRunTerminal: (command: string, cwd?: string) =>
    ipcRenderer.invoke('tool-run-terminal', command, cwd),
  toolGoogleSearch: (query: string) => ipcRenderer.invoke('tool-google-search', query),
  toolSmartFileSearch: (query: string) => ipcRenderer.invoke('tool-smart-file-search', query),

  // ─── Native Voice Tools (Phase 1 — Batch B: Desktop Automation) ───
  toolGhostType: (text: string) => ipcRenderer.invoke('tool-ghost-type', text),
  toolPressShortcut: (key: string, modifiers?: string[]) =>
    ipcRenderer.invoke('tool-press-shortcut', key, modifiers),
  toolTakeScreenshot: () => ipcRenderer.invoke('tool-take-screenshot'),
  toolSetVolume: (level: number) => ipcRenderer.invoke('tool-set-volume', level),

  // ─── Native Voice Tools (Phase 1 — Batch C: Memory & Tools) ───
  toolSaveCoreMemory: (fact: string) => ipcRenderer.invoke('tool-save-core-memory', fact),
  toolRetrieveCoreMemory: () => ipcRenderer.invoke('tool-retrieve-core-memory'),
  toolOpenProject: (folderPath: string) => ipcRenderer.invoke('tool-open-project', folderPath),

  // ─── Batch D: Window Management, Macros & Lock ───
  toolSnapWindow: (appName: string, position: string) =>
    ipcRenderer.invoke('tool-snap-window', appName, position),
  toolExecuteMacro: (macroName: string) =>
    ipcRenderer.invoke('tool-execute-macro', macroName),
  toolLockSystem: () => ipcRenderer.invoke('tool-lock-system'),

  // ─── Macro CRUD ───
  macrosList: () => ipcRenderer.invoke('macros-list'),
  macrosSave: (macro: { id: string; name: string; steps: Array<{ type: string; params: Record<string, string> }> }) =>
    ipcRenderer.invoke('macros-save', macro),
  macrosDelete: (id: string) => ipcRenderer.invoke('macros-delete', id),

  // ─── Phase 2: Communications ───
  toolSendWhatsapp: (contact: string, message: string) =>
    ipcRenderer.invoke('tool-send-whatsapp', contact, message),
  toolOpenWhatsappChat: (contact: string) =>
    ipcRenderer.invoke('tool-open-whatsapp-chat', contact),
  toolSendTelegram: (contact: string, message: string) =>
    ipcRenderer.invoke('tool-send-telegram', contact, message),
  toolSendEmail: (to: string, subject: string, body: string) =>
    ipcRenderer.invoke('tool-send-email', to, subject, body),

  // ─── Phase 5: Cyber Arsenal ───
  toolPortScan: (target: string, ports?: string) =>
    ipcRenderer.invoke('tool-port-scan', target, ports),
  toolNmapScan: (target: string, flags?: string) =>
    ipcRenderer.invoke('tool-nmap-scan', target, flags),
  toolWhoisLookup: (target: string) =>
    ipcRenderer.invoke('tool-whois-lookup', target),
  toolDnsLookup: (target: string, recordType?: string) =>
    ipcRenderer.invoke('tool-dns-lookup', target, recordType),
  toolSubdomainEnum: (domain: string) =>
    ipcRenderer.invoke('tool-subdomain-enum', domain),
  toolHashIdentify: (hash: string) =>
    ipcRenderer.invoke('tool-hash-identify', hash),
  toolIpGeolocation: (ip: string) =>
    ipcRenderer.invoke('tool-ip-geolocation', ip),

  // ─── Phase 3: RAG / Vector DB ───
  ragIngest: (filePath: string) =>
    ipcRenderer.invoke('rag-ingest', filePath),
  ragSearch: (query: string, topK?: number) =>
    ipcRenderer.invoke('rag-search', query, topK),
  ragListDocuments: () =>
    ipcRenderer.invoke('rag-list-documents'),
  ragDeleteDocument: (docId: string) =>
    ipcRenderer.invoke('rag-delete-document', docId),

  // ─── Phase 4: Creative Tools ───
  toolGenerateImage: (prompt: string, width?: number, height?: number) =>
    ipcRenderer.invoke('tool-generate-image', prompt, width, height),
  toolAnalyzeCode: (filePath: string) =>
    ipcRenderer.invoke('tool-analyze-code', filePath),
  toolSummarizeText: (input: string) =>
    ipcRenderer.invoke('tool-summarize-text', input),
  toolTranslateText: (text: string, targetLang: string, sourceLang?: string) =>
    ipcRenderer.invoke('tool-translate-text', text, targetLang, sourceLang),

  // ─── Offline Brain + Learning ───
  brainLogToolCall: (userInput: string, toolName: string, params: Record<string, unknown>) =>
    ipcRenderer.invoke('brain-log-tool-call', userInput, toolName, params),
  brainLearningStats: () =>
    ipcRenderer.invoke('brain-learning-stats'),
  brainOfflineQuery: (userInput: string) =>
    ipcRenderer.invoke('brain-offline-query', userInput),
  brainCheckNetwork: () =>
    ipcRenderer.invoke('brain-check-network'),
  brainCheckOllama: () =>
    ipcRenderer.invoke('brain-check-ollama'),

  // ─── Self-Evolution ───
  jarvisSelfUpdate: () =>
    ipcRenderer.invoke('jarvis-self-update'),
  jarvisSelfRepair: () =>
    ipcRenderer.invoke('jarvis-self-repair'),
  jarvisAddFeature: (description: string) =>
    ipcRenderer.invoke('jarvis-add-feature', description),
  jarvisResearch: (query: string) =>
    ipcRenderer.invoke('jarvis-research', query),
  jarvisDiagnostics: () =>
    ipcRenderer.invoke('jarvis-diagnostics'),

  // ─── Clipboard & Assignment ───
  clipboardReadImage: () =>
    ipcRenderer.invoke('clipboard-read-image'),
  analyzeImage: (base64: string, prompt: string) =>
    ipcRenderer.invoke('analyze-image', base64, prompt),
  assignmentSolve: (base64: string, instructions: string) =>
    ipcRenderer.invoke('assignment-solve', base64, instructions),

  // ─── Browser Automation ───
  browserLaunch: () =>
    ipcRenderer.invoke('browser-launch'),
  browserNavigate: (url: string) =>
    ipcRenderer.invoke('browser-navigate', url),
  browserClick: (selector: string) =>
    ipcRenderer.invoke('browser-click', selector),
  browserType: (selector: string, text: string) =>
    ipcRenderer.invoke('browser-type', selector, text),
  browserScreenshot: () =>
    ipcRenderer.invoke('browser-screenshot'),
  browserRead: (selector?: string) =>
    ipcRenderer.invoke('browser-read', selector),
  browserExecute: (code: string) =>
    ipcRenderer.invoke('browser-execute', code),

  // ─── Screen Awareness ───
  awarenessStart: (intervalMs?: number) =>
    ipcRenderer.invoke('awareness-start', intervalMs),
  awarenessStop: () =>
    ipcRenderer.invoke('awareness-stop'),
  awarenessStatus: () =>
    ipcRenderer.invoke('awareness-status'),
  awarenessAnalyzeNow: () =>
    ipcRenderer.invoke('awareness-analyze-now'),

  // ─── Knowledge Vault ───
  vaultSaveEntity: (name: string, type: string, description: string) =>
    ipcRenderer.invoke('vault-save-entity', name, type, description),
  vaultSaveFact: (entityName: string, fact: string, source?: string) =>
    ipcRenderer.invoke('vault-save-fact', entityName, fact, source),
  vaultSaveRelationship: (from: string, to: string, relation: string) =>
    ipcRenderer.invoke('vault-save-relationship', from, to, relation),
  vaultQuery: (query: string) =>
    ipcRenderer.invoke('vault-query', query),
  vaultList: () =>
    ipcRenderer.invoke('vault-list'),
  vaultLogConversation: (role: string, content: string, tool?: string) =>
    ipcRenderer.invoke('vault-log-conversation', role, content, tool),

  // ─── Workflow Builder ───
  workflowSave: (name: string, steps: Array<{ tool: string; params: Record<string, unknown> }>) =>
    ipcRenderer.invoke('workflow-save', name, steps),
  workflowList: () =>
    ipcRenderer.invoke('workflow-list'),
  workflowGet: (name: string) =>
    ipcRenderer.invoke('workflow-get', name),
  workflowDelete: (name: string) =>
    ipcRenderer.invoke('workflow-delete', name),

  // ─── Goal Tracker ───
  goalAdd: (title: string, description: string, category?: string, priority?: string, dueDate?: string) =>
    ipcRenderer.invoke('goal-add', title, description, category, priority, dueDate),
  goalList: (status?: string) =>
    ipcRenderer.invoke('goal-list', status),
  goalUpdate: (goalId: number, note: string, progressChange?: number) =>
    ipcRenderer.invoke('goal-update', goalId, note, progressChange),
  dailyLog: (type: string, content: string) =>
    ipcRenderer.invoke('daily-log', type, content),
  dailySummary: (date?: string) =>
    ipcRenderer.invoke('daily-summary', date),

  // ─── Multi-Agent ───
  agentDelegate: (agentType: string, task: string) =>
    ipcRenderer.invoke('agent-delegate', agentType, task),
  agentList: () =>
    ipcRenderer.invoke('agent-list'),

  // ─── Sidecar ───
  sidecarStart: (port?: number) =>
    ipcRenderer.invoke('sidecar-start', port),
  sidecarStop: () =>
    ipcRenderer.invoke('sidecar-stop'),
  sidecarClients: () =>
    ipcRenderer.invoke('sidecar-clients'),
  sidecarSend: (clientId: string, command: Record<string, unknown>) =>
    ipcRenderer.invoke('sidecar-send', clientId, command),

  // ─── Plugin System ───
  pluginInstall: (name: string, manifest: Record<string, unknown>) =>
    ipcRenderer.invoke('plugin-install', name, manifest),
  pluginList: () =>
    ipcRenderer.invoke('plugin-list'),
  pluginUninstall: (name: string) =>
    ipcRenderer.invoke('plugin-uninstall', name),
  pluginToggle: (name: string) =>
    ipcRenderer.invoke('plugin-toggle', name),

  // ─── Notifications ───
  jarvisNotify: (title: string, body: string, urgency?: string) =>
    ipcRenderer.invoke('jarvis-notify', title, body, urgency),
  onNotification: (callback: (data: { title: string; body: string; urgency?: string }) => void) => {
    ipcRenderer.on('jarvis-notification', (_event, data) => callback(data))
  },

  // ─── Live APIs ───
  apiWeather: (city: string) =>
    ipcRenderer.invoke('api-weather', city),
  apiNews: (query?: string, category?: string) =>
    ipcRenderer.invoke('api-news', query, category),

  // ─── File Watcher ───
  watcherStart: (dirPath: string) =>
    ipcRenderer.invoke('watcher-start', dirPath),
  watcherStop: (dirPath: string) =>
    ipcRenderer.invoke('watcher-stop', dirPath),
  watcherList: () =>
    ipcRenderer.invoke('watcher-list'),
  onFileChanged: (callback: (data: { event: string; file: string; dir: string }) => void) => {
    ipcRenderer.on('file-changed', (_event, data) => callback(data))
  },

  // ─── Conversation Memory ───
  memoryLoadContext: () =>
    ipcRenderer.invoke('memory-load-context'),
  memorySaveSession: (sessionData: { messages: Array<{ role: string; content: string }> }) =>
    ipcRenderer.invoke('memory-save-session', sessionData),

  // ─── Metasploit ───
  msfConnect: (host?: string, port?: number, password?: string) =>
    ipcRenderer.invoke('msf-connect', host, port, password),
  msfExecute: (method: string, params: unknown[]) =>
    ipcRenderer.invoke('msf-execute', method, params),
  msfModules: (type: string) =>
    ipcRenderer.invoke('msf-modules', type)
}

if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('electron', {
      ...electronAPI,
      ipcRenderer: {
        ...electronAPI.ipcRenderer,
        invoke: (channel: string, ...args: unknown[]) => ipcRenderer.invoke(channel, ...args)
      }
    })
    contextBridge.exposeInMainWorld('desktopApi', desktopApi)
  } catch {
    // ignore bridge exposure errors during dev reload
  }
} else {
  // @ts-ignore
  window.electron = electronAPI
  // @ts-ignore
  window.desktopApi = desktopApi
}
