/**
 * CodeEditorWidget — code editor with native file read/write via IPC.
 */

import { useState } from 'react'
import {
  RiCodeSSlashLine, RiSave3Line, RiFileAddLine,
  RiFolderOpenLine, RiCheckLine, RiAlertLine
} from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

const LANGUAGES = [
  { value: 'javascript', ext: '.js' },
  { value: 'typescript', ext: '.ts' },
  { value: 'python', ext: '.py' },
  { value: 'html', ext: '.html' },
  { value: 'css', ext: '.css' },
  { value: 'json', ext: '.json' },
  { value: 'markdown', ext: '.md' },
  { value: 'powershell', ext: '.ps1' },
  { value: 'bash', ext: '.sh' },
  { value: 'rust', ext: '.rs' },
  { value: 'cpp', ext: '.cpp' },
]

export default function CodeEditorWidget({ widget }: { widget: WidgetInstance }) {
  const [code, setCode] = useState('// JARVIS Code Editor\n// Write code here and save to disk.\n\nfunction hello() {\n  console.log("Hello from JARVIS!");\n}\n')
  const [filename, setFilename] = useState('untitled.js')
  const [language, setLanguage] = useState('javascript')
  const [status, setStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

  async function saveFile() {
    try {
      const r = await window.desktopApi.toolWriteFile(filename, code)
      if (r.success) {
        setStatus({ type: 'success', message: `Saved to ${r.path}` })
      } else {
        setStatus({ type: 'error', message: r.error || 'Save failed' })
      }
      setTimeout(() => setStatus(null), 3000)
    } catch (err) {
      setStatus({ type: 'error', message: (err as Error).message })
      setTimeout(() => setStatus(null), 3000)
    }
  }

  async function openFile() {
    try {
      const r = await window.desktopApi.toolReadFile(filename)
      if (r.success && r.content) {
        setCode(r.content)
        setStatus({ type: 'success', message: `Opened ${filename}` })
      } else {
        setStatus({ type: 'error', message: r.error || 'Could not read file' })
      }
      setTimeout(() => setStatus(null), 3000)
    } catch (err) {
      setStatus({ type: 'error', message: (err as Error).message })
      setTimeout(() => setStatus(null), 3000)
    }
  }

  function handleTab(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Tab') {
      e.preventDefault()
      const start = e.currentTarget.selectionStart
      const end = e.currentTarget.selectionEnd
      const newCode = code.substring(0, start) + '  ' + code.substring(end)
      setCode(newCode)
      setTimeout(() => {
        e.currentTarget.selectionStart = start + 2
        e.currentTarget.selectionEnd = start + 2
      }, 0)
    }
  }

  const lines = code.split('\n').length

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiCodeSSlashLine />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col">
        {/* Toolbar */}
        <div className="flex items-center justify-between border-b border-white/5 bg-black/30 px-3 py-2">
          <div className="flex items-center gap-2">
            <input
              value={filename}
              onChange={e => setFilename(e.target.value)}
              className="w-36 rounded-lg border border-white/10 bg-black/40 px-2 py-1.5 text-[11px] font-mono text-zinc-300 outline-none focus:border-emerald-500/40"
              placeholder="filename.ext"
            />
            <select
              value={language}
              onChange={e => setLanguage(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/40 px-2 py-1.5 text-[10px] font-mono text-zinc-400 outline-none"
            >
              {LANGUAGES.map(l => (
                <option key={l.value} value={l.value}>{l.value.toUpperCase()}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={openFile}
              className="flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-[9px] font-bold tracking-[0.14em] text-zinc-400 hover:border-emerald-500/30 hover:text-emerald-400"
            >
              <RiFolderOpenLine size={12} /> OPEN
            </button>
            <button
              onClick={saveFile}
              className="flex items-center gap-1 rounded-lg bg-emerald-500 px-3 py-1.5 text-[9px] font-black tracking-[0.14em] text-black hover:bg-emerald-400"
            >
              <RiSave3Line size={12} /> SAVE
            </button>
          </div>
        </div>

        {/* Status bar (ephemeral) */}
        {status && (
          <div className={`flex items-center gap-2 px-3 py-1.5 text-[10px] ${
            status.type === 'success' ? 'bg-emerald-500/10 text-emerald-300' : 'bg-red-500/10 text-red-300'
          }`}>
            {status.type === 'success' ? <RiCheckLine size={12} /> : <RiAlertLine size={12} />}
            {status.message}
          </div>
        )}

        {/* Editor with line numbers */}
        <div className="relative flex flex-1 overflow-hidden bg-[#0a0a0c]">
          {/* Line numbers */}
          <div className="scrollbar-small w-10 flex-shrink-0 overflow-hidden border-r border-white/5 bg-black/40 pt-4 text-right">
            {Array.from({ length: lines }, (_, i) => (
              <div key={i} className="pr-2 text-[11px] font-mono leading-6 text-zinc-700">{i + 1}</div>
            ))}
          </div>
          {/* Code area */}
          <textarea
            value={code}
            onChange={e => setCode(e.target.value)}
            onKeyDown={handleTab}
            spellCheck={false}
            className="scrollbar-small flex-1 resize-none bg-transparent p-4 font-mono text-[13px] leading-6 text-emerald-100 outline-none"
            style={{ tabSize: 2 }}
          />
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-white/5 bg-black/30 px-3 py-1.5">
          <span className="text-[8px] font-mono tracking-[0.16em] text-zinc-600">{language.toUpperCase()}</span>
          <span className="text-[8px] font-mono tracking-[0.16em] text-zinc-600">
            Ln {lines} // {code.length} chars
          </span>
        </div>
      </div>
    </WidgetShell>
  )
}
