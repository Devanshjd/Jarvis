/**
 * EmailWidget — email compose & send via native SMTP or mailto fallback.
 */

import { useState } from 'react'
import { RiMailLine, RiMailSendLine, RiCheckLine, RiAlertLine } from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

export default function EmailWidget({ widget }: { widget: WidgetInstance }) {
  const [to, setTo] = useState('')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null)

  async function sendEmail() {
    if (!to.trim() || !subject.trim()) return
    setSending(true)
    setResult(null)
    try {
      const r = await window.desktopApi.toolSendEmail(to.trim(), subject.trim(), body.trim())
      setResult({ success: r.success, message: r.message || r.error || 'Done' })
      if (r.success) {
        setTimeout(() => {
          setTo('')
          setSubject('')
          setBody('')
          setResult(null)
        }, 3000)
      }
    } catch (err) {
      setResult({ success: false, message: (err as Error).message })
    }
    setSending(false)
  }

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiMailLine />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col gap-3 p-4">
        <div className="flex items-center gap-2 border-b border-white/5 pb-3">
          <RiMailSendLine className="text-emerald-400" size={14} />
          <span className="text-[10px] font-bold tracking-[0.2em] text-emerald-400">COMPOSE</span>
        </div>

        <input
          value={to}
          onChange={(e) => setTo(e.target.value)}
          placeholder="To (email address)..."
          className="rounded-xl border border-white/10 bg-black/40 px-3 py-2.5 text-xs text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-emerald-500/40"
        />
        <input
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder="Subject..."
          className="rounded-xl border border-white/10 bg-black/40 px-3 py-2.5 text-xs text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-emerald-500/40"
        />
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Message body..."
          className="scrollbar-small flex-1 resize-none rounded-xl border border-white/10 bg-black/40 px-3 py-2.5 text-xs text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-emerald-500/40"
        />

        <button
          onClick={sendEmail}
          disabled={sending || !to.trim() || !subject.trim()}
          className="rounded-xl bg-emerald-500 py-2.5 text-xs font-black tracking-[0.18em] text-black transition-colors hover:bg-emerald-400 disabled:opacity-40"
        >
          {sending ? 'SENDING...' : 'SEND EMAIL'}
        </button>

        {result && (
          <div className={`flex items-start gap-2 rounded-xl border px-3 py-2.5 text-[10px] leading-5 ${
            result.success
              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
              : 'border-red-500/30 bg-red-500/10 text-red-200'
          }`}>
            {result.success ? <RiCheckLine className="mt-0.5 shrink-0" /> : <RiAlertLine className="mt-0.5 shrink-0" />}
            <span>{result.message}</span>
          </div>
        )}
      </div>
    </WidgetShell>
  )
}
