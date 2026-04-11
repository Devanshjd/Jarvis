/**
 * CodeEditorWidget — Monaco Editor for in-app code editing.
 */

import { useState } from 'react'
import { RiCodeSSlashLine, RiSave3Line, RiFileAddLine } from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

const API_BASE = 'http://127.0.0.1:8765'

export default function CodeEditorWidget({ widget }: { widget: WidgetInstance }) {
  const [code, setCode] = useState('// JARVIS Code Editor\n// Write code here and save to disk.\n\nfunction hello() {\n  console.log("Hello from JARVIS!");\n}\n')
  const [filename, setFilename] = useState('untitled.js')
  const [saved, setSaved] = useState(false)
  const [language, setLanguage] = useState('javascript')

  async function saveFile() {
    try {
      await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: `write the following code to file "${filename}":\n\`\`\`\n${code}\n\`\`\``,
          approve_desktop: true,
          timeout_s: 30
        })
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch { /* */ }
  }

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiCodeSSlashLine />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col">
        {/* Toolbar */}
        <div className="flex items-center justify-between border-b border-white/5 bg-black/30 px-4 py-2">
          <div className="flex items-center gap-2">
            <RiFileAddLine className="text-zinc-500" size={14} />
            <input value={filename} onChange={(e) => setFilename(e.target.value)}
              className="w-40 bg-transparent text-xs font-mono text-zinc-300 outline-none placeholder:text-zinc-600" placeholder="filename.ext" />
            <select value={language} onChange={(e) => setLanguage(e.target.value)}
              className="rounded-md border border-white/10 bg-black/40 px-2 py-1 text-[10px] font-mono text-zinc-400 outline-none">
              <option value="javascript">JavaScript</option>
              <option value="python">Python</option>
              <option value="typescript">TypeScript</option>
              <option value="html">HTML</option>
              <option value="css">CSS</option>
              <option value="json">JSON</option>
              <option value="markdown">Markdown</option>
            </select>
          </div>
          <button onClick={saveFile}
            className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-1.5 text-[10px] font-black tracking-[0.16em] text-black transition-colors hover:bg-emerald-400">
            <RiSave3Line size={12} /> {saved ? 'SAVED ✓' : 'SAVE'}
          </button>
        </div>

        {/* Editor area */}
        <textarea
          value={code}
          onChange={(e) => setCode(e.target.value)}
          spellCheck={false}
          className="scrollbar-small flex-1 resize-none bg-[#0a0a0c] p-4 font-mono text-[13px] leading-6 text-emerald-100 outline-none"
          style={{ tabSize: 2 }}
        />

        {/* Status bar */}
        <div className="flex items-center justify-between border-t border-white/5 bg-black/30 px-4 py-1.5">
          <span className="text-[9px] font-mono tracking-[0.18em] text-zinc-600">{language.toUpperCase()}</span>
          <span className="text-[9px] font-mono tracking-[0.18em] text-zinc-600">Ln {code.split('\n').length} // {code.length} chars</span>
        </div>
      </div>
    </WidgetShell>
  )
}
