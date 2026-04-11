export {}

declare global {
  interface JarvisShellSnapshot {
    config: {
      operatorName: string
      provider: string
      model: string
      startupProvider: string
      mode: string
      voiceEngine: string
      ttsEngine: string
      sttEngine: string
      geminiLiveModel: string
      geminiVoiceName: string
      apiKeys: Record<string, string>
    }
    memories: Array<{
      id: number
      title: string
      content: string
      createdAt: string
    }>
    tasks: Array<Record<string, unknown>>
    gallery: Array<{
      filename: string
      displayName: string
      path: string
      url: string
      createdAt: string
      source: string
    }>
  }

  interface SystemStatsResult {
    cpuLoad: number
    ramUsage: number
    ramTotal: number
    ramPercent: number
    temperature: number | null
    os: string
    hostname: string
    uptime: string
    platform: string
    arch: string
    cpuModel: string
    cores: number
  }

  interface NoteItem {
    id: string
    title: string
    content: string
    updatedAt: string
  }

  interface MacroStep {
    type: string
    params: Record<string, string>
  }

  interface MacroItem {
    id: string
    name: string
    steps: MacroStep[]
  }

  interface Window {
    electron: {
      ipcRenderer: {
        invoke: (channel: string, ...args: unknown[]) => Promise<unknown>
        on: (channel: string, listener: (...args: unknown[]) => void) => void
        removeAllListeners: (channel: string) => void
      }
    }
    desktopApi: {
      windowMin: () => void
      windowMax: () => void
      windowClose: () => void
      backendStatus: () => Promise<{ running: boolean; port: number; pid: number | null }>
      shellSnapshot: () => Promise<JarvisShellSnapshot>
      listRunningApps: () => Promise<{ apps: string[] }>
      getScreenSource: () => Promise<string | null>
      secureGetKeys: () => Promise<{
        geminiKey: string
        groqKey: string
        liveModel: string
        voiceName: string
      }>
      openPath: (targetPath: string) => Promise<{ success: boolean }>
      saveSettings: (payload: {
        operatorName?: string
        provider?: string
        model?: string
        voiceEngine?: string
      }) => Promise<{ success: boolean }>
      systemStats: () => Promise<SystemStatsResult>
      notesList: () => Promise<NoteItem[]>
      notesCreate: (title: string, content: string) => Promise<{ id: string; title: string; content: string }>
      notesUpdate: (id: string, content: string) => Promise<{ success: boolean }>
      notesDelete: (id: string) => Promise<{ success: boolean }>
      onOverlayToggle: (callback: () => void) => () => void

      // ─── Native Voice Tools (Phase 1) ───
      toolReadFile: (filePath: string) => Promise<{ success: boolean; content?: string; error?: string }>
      toolWriteFile: (fileName: string, content: string) => Promise<{ success: boolean; path?: string; error?: string }>
      toolManageFile: (operation: string, sourcePath: string, destPath?: string) => Promise<{ success: boolean; message?: string; error?: string }>
      toolReadDirectory: (dirPath: string) => Promise<{ success: boolean; path?: string; items?: Array<{ name: string; type: string }>; total?: number; error?: string }>
      toolCreateFolder: (folderPath: string) => Promise<{ success: boolean; path?: string; error?: string }>
      toolOpenApp: (appName: string) => Promise<{ success: boolean; message?: string; error?: string }>
      toolCloseApp: (appName: string) => Promise<{ success: boolean; message?: string; error?: string }>
      toolRunTerminal: (command: string, cwd?: string) => Promise<{ success: boolean; output?: string; exitCode?: number | null; error?: string }>
      toolGoogleSearch: (query: string) => Promise<{ success: boolean; message?: string; error?: string }>
      toolSmartFileSearch: (query: string) => Promise<{ success: boolean; results?: string[]; message?: string; error?: string }>

      // ─── Batch B: Desktop Automation ───
      toolGhostType: (text: string) => Promise<{ success: boolean; message?: string; error?: string }>
      toolPressShortcut: (key: string, modifiers?: string[]) => Promise<{ success: boolean; message?: string; error?: string }>
      toolTakeScreenshot: () => Promise<{ success: boolean; path?: string; message?: string; error?: string }>
      toolSetVolume: (level: number) => Promise<{ success: boolean; message?: string; error?: string }>

      // ─── Batch C: Memory & Tools ───
      toolSaveCoreMemory: (fact: string) => Promise<{ success: boolean; message?: string; total?: number; error?: string }>
      toolRetrieveCoreMemory: () => Promise<{ success: boolean; memories: Array<{ fact: string; savedAt: string }>; total: number; message?: string }>
      toolOpenProject: (folderPath: string) => Promise<{ success: boolean; message?: string; error?: string }>

      // ─── Batch D: Window Management, Macros & Lock ───
      toolSnapWindow: (appName: string, position: string) => Promise<{ success: boolean; message?: string; error?: string }>
      toolExecuteMacro: (macroName: string) => Promise<{ success: boolean; message?: string; error?: string }>
      toolLockSystem: () => Promise<{ success: boolean; message?: string; error?: string }>

      // ─── Macro CRUD ───
      macrosList: () => Promise<MacroItem[]>
      macrosSave: (macro: MacroItem) => Promise<{ success: boolean }>
      macrosDelete: (id: string) => Promise<{ success: boolean }>

      // ─── Phase 2: Communications ───
      toolSendWhatsapp: (contact: string, message: string) => Promise<{ success: boolean; message?: string; error?: string }>
      toolOpenWhatsappChat: (contact: string) => Promise<{ success: boolean; message?: string; error?: string }>
      toolSendTelegram: (contact: string, message: string) => Promise<{ success: boolean; message?: string; error?: string }>
      toolSendEmail: (to: string, subject: string, body: string) => Promise<{ success: boolean; message?: string; error?: string }>

      // ─── Phase 5: Cyber Arsenal ───
      toolPortScan: (target: string, ports?: string) => Promise<{ success: boolean; message?: string; error?: string }>
      toolNmapScan: (target: string, flags?: string) => Promise<{ success: boolean; message?: string; error?: string }>
      toolWhoisLookup: (target: string) => Promise<{ success: boolean; message?: string; error?: string }>
      toolDnsLookup: (target: string, recordType?: string) => Promise<{ success: boolean; message?: string; error?: string }>
      toolSubdomainEnum: (domain: string) => Promise<{ success: boolean; message?: string; error?: string }>
      toolHashIdentify: (hash: string) => Promise<{ success: boolean; message?: string; error?: string }>
      toolIpGeolocation: (ip: string) => Promise<{ success: boolean; message?: string; error?: string }>

      // ─── Phase 3: RAG / Vector DB ───
      ragIngest: (filePath: string) => Promise<{ success: boolean; message?: string; docId?: string; chunks?: number; error?: string }>
      ragSearch: (query: string, topK?: number) => Promise<{ success: boolean; results?: Array<{ text: string; score: number; docId: string; filename: string; chunkIndex: number }>; searchType?: string; message?: string; error?: string }>
      ragListDocuments: () => Promise<{ success: boolean; documents?: Array<{ id: string; filename: string; filePath: string; ingestedAt: string; chunks: number; size: number }>; total?: number; error?: string }>
      ragDeleteDocument: (docId: string) => Promise<{ success: boolean; message?: string; error?: string }>

      // ─── Phase 4: Creative Tools ───
      toolGenerateImage: (prompt: string, width?: number, height?: number) => Promise<{ success: boolean; message?: string; path?: string; url?: string; size?: number; error?: string }>
      toolAnalyzeCode: (filePath: string) => Promise<{ success: boolean; message?: string; metrics?: Record<string, unknown>; error?: string }>
      toolSummarizeText: (input: string) => Promise<{ success: boolean; message?: string; method?: string; originalLength?: number; summaryLength?: number; error?: string }>
      toolTranslateText: (text: string, targetLang: string, sourceLang?: string) => Promise<{ success: boolean; message?: string; translated?: string; confidence?: number; error?: string }>

      // ─── Offline Brain + Learning ───
      brainLogToolCall: (userInput: string, toolName: string, params: Record<string, unknown>) => Promise<{ success: boolean }>
      brainLearningStats: () => Promise<{ success: boolean; totalExamples: number; toolCounts: Record<string, number> }>
      brainOfflineQuery: (userInput: string) => Promise<{ success: boolean; toolCall?: Record<string, unknown> | null; rawResponse?: string; model?: string; mode?: string; error?: string }>
      brainCheckNetwork: () => Promise<{ online: boolean }>
      brainCheckOllama: () => Promise<{ running: boolean }>

      // ─── Self-Evolution ───
      jarvisSelfUpdate: () => Promise<{ success: boolean; output: string; error?: string }>
      jarvisSelfRepair: () => Promise<{ success: boolean; output: string; error?: string }>
      jarvisAddFeature: (description: string) => Promise<{ success: boolean; output: string; error?: string }>
      jarvisResearch: (query: string) => Promise<{ success: boolean; output: string; error?: string }>
      jarvisDiagnostics: () => Promise<{ success: boolean; output: string; error?: string }>

      // ─── Clipboard & Assignment ───
      clipboardReadImage: () => Promise<{ success: boolean; base64?: string; width?: number; height?: number; error?: string }>
      analyzeImage: (base64: string, prompt: string) => Promise<{ success: boolean; text?: string; error?: string }>
      assignmentSolve: (base64: string, instructions: string) => Promise<{ success: boolean; text?: string; error?: string }>

      // ─── Browser Automation ───
      browserLaunch: () => Promise<{ success: boolean; url?: string; error?: string }>
      browserNavigate: (url: string) => Promise<{ success: boolean; url?: string; title?: string; error?: string }>
      browserClick: (selector: string) => Promise<{ success: boolean; clicked?: string; error?: string }>
      browserType: (selector: string, text: string) => Promise<{ success: boolean; typed?: string; error?: string }>
      browserScreenshot: () => Promise<{ success: boolean; base64?: string; error?: string }>
      browserRead: (selector?: string) => Promise<{ success: boolean; title?: string; url?: string; text?: string; error?: string }>
      browserExecute: (code: string) => Promise<{ success: boolean; result?: string; error?: string }>

      // ─── Screen Awareness ───
      awarenessStart: (intervalMs?: number) => Promise<{ success: boolean; status: string; interval?: number; firstResult?: string }>
      awarenessStop: () => Promise<{ success: boolean; status: string }>
      awarenessStatus: () => Promise<{ active: boolean; lastResult: string }>
      awarenessAnalyzeNow: () => Promise<{ success: boolean; text: string }>

      // ─── Knowledge Vault ───
      vaultSaveEntity: (name: string, type: string, description: string) => Promise<{ success: boolean; error?: string }>
      vaultSaveFact: (entityName: string, fact: string, source?: string) => Promise<{ success: boolean; error?: string }>
      vaultSaveRelationship: (from: string, to: string, relation: string) => Promise<{ success: boolean; error?: string }>
      vaultQuery: (query: string) => Promise<{ success: boolean; entities?: Array<Record<string, unknown>>; relations?: Array<Record<string, unknown>>; error?: string }>
      vaultList: () => Promise<{ success: boolean; entities?: Array<Record<string, unknown>>; error?: string }>
      vaultLogConversation: (role: string, content: string, tool?: string) => Promise<{ success: boolean; error?: string }>

      // ─── Workflow Builder ───
      workflowSave: (name: string, steps: Array<{ tool: string; params: Record<string, unknown> }>) => Promise<{ success: boolean; path?: string; error?: string }>
      workflowList: () => Promise<{ success: boolean; workflows?: Array<Record<string, unknown>>; error?: string }>
      workflowGet: (name: string) => Promise<{ success: boolean; workflow?: Record<string, unknown>; error?: string }>
      workflowDelete: (name: string) => Promise<{ success: boolean; error?: string }>

      // ─── Goal Tracker ───
      goalAdd: (title: string, description: string, category?: string, priority?: string, dueDate?: string) => Promise<{ success: boolean; error?: string }>
      goalList: (status?: string) => Promise<{ success: boolean; goals?: Array<Record<string, unknown>>; error?: string }>
      goalUpdate: (goalId: number, note: string, progressChange?: number) => Promise<{ success: boolean; error?: string }>
      dailyLog: (type: string, content: string) => Promise<{ success: boolean; error?: string }>
      dailySummary: (date?: string) => Promise<{ success: boolean; date?: string; logs?: Array<Record<string, unknown>>; activeGoals?: Array<Record<string, unknown>>; error?: string }>

      // ─── Multi-Agent ───
      agentDelegate: (agentType: string, task: string) => Promise<{ success: boolean; agent?: string; result?: string; error?: string }>
      agentList: () => Promise<{ success: boolean; agents: Array<{ id: string; name: string; tools: number }> }>

      // ─── Sidecar ───
      sidecarStart: (port?: number) => Promise<{ success: boolean; status?: string; port?: number; error?: string }>
      sidecarStop: () => Promise<{ success: boolean; status: string }>
      sidecarClients: () => Promise<{ success: boolean; clients: Array<{ id: string; name: string; connected: string }> }>
      sidecarSend: (clientId: string, command: Record<string, unknown>) => Promise<{ success: boolean; error?: string }>

      // ─── Plugin System ───
      pluginInstall: (name: string, manifest: Record<string, unknown>) => Promise<{ success: boolean; error?: string }>
      pluginList: () => Promise<{ success: boolean; plugins?: Array<Record<string, unknown>>; error?: string }>
      pluginUninstall: (name: string) => Promise<{ success: boolean; error?: string }>
      pluginToggle: (name: string) => Promise<{ success: boolean; active?: boolean; error?: string }>

      // ─── Notifications ───
      jarvisNotify: (title: string, body: string, urgency?: string) => Promise<{ success: boolean; error?: string }>
      onNotification: (callback: (data: { title: string; body: string; urgency?: string }) => void) => void
    }
  }
}
