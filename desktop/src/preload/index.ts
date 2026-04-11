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

  // ─── Native Voice Tools (Phase 1) ───
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
  toolOpenProject: (folderPath: string) => ipcRenderer.invoke('tool-open-project', folderPath)
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
