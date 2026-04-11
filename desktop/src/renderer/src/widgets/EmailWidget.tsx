/**
 * EmailWidget — email inbox summary and compose.
 */

import { useState } from 'react'
import { RiMailLine, RiMailSendLine, RiRefreshLine, RiInboxLine } from 'react-icons/ri'
import WidgetShell from '../components/WidgetShell'
import type { WidgetInstance } from '../store/useStore'

const API_BASE = 'http://127.0.0.1:8765'

type EmailMode = 'inbox' | 'compose'

interface EmailEntry {
  id: number
  from: string
  subject: string
  preview: string
  time: string
}

export default function EmailWidget({ widget }: { widget: WidgetInstance }) {
  const [mode, setMode] = useState<EmailMode>('inbox')
  const [emails, setEmails] = useState<EmailEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [to, setTo] = useState('')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [sent, setSent] = useState(false)

  async function fetchEmails() {
    setLoading(true)
    try {
      const resp = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'check my email inbox and list the latest emails', approve_desktop: true, timeout_s: 30 })
      })
      const data = await resp.json()
      // Emails displayed as system message in transcript
    } catch { /* */ }
    setLoading(false)
  }

  async function sendEmail() {
    if (!to.trim() || !subject.trim()) return
    try {
      await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: `send email to ${to} with subject "${subject}" and body: ${body}`, approve_desktop: true, timeout_s: 30 })
      })
      setSent(true)
      setTimeout(() => { setSent(false); setTo(''); setSubject(''); setBody('') }, 2000)
    } catch { /* */ }
  }

  return (
    <WidgetShell id={widget.id} title={widget.title} icon={<RiMailLine />} x={widget.x} y={widget.y} width={widget.width} height={widget.height} minimized={widget.minimized}>
      <div className="flex h-full flex-col">
        {/* Tabs */}
        <div className="flex border-b border-white/5">
          <button onClick={() => setMode('inbox')} className={`flex-1 py-2.5 text-[10px] font-bold tracking-[0.2em] transition-colors ${mode === 'inbox' ? 'border-b-2 border-emerald-500 text-emerald-400' : 'text-zinc-500 hover:text-zinc-300'}`}>
            <RiInboxLine className="inline mr-1 mb-0.5" size={12} /> INBOX
          </button>
          <button onClick={() => setMode('compose')} className={`flex-1 py-2.5 text-[10px] font-bold tracking-[0.2em] transition-colors ${mode === 'compose' ? 'border-b-2 border-emerald-500 text-emerald-400' : 'text-zinc-500 hover:text-zinc-300'}`}>
            <RiMailSendLine className="inline mr-1 mb-0.5" size={12} /> COMPOSE
          </button>
        </div>

        {mode === 'inbox' ? (
          <div className="flex-1 flex flex-col p-4">
            <button onClick={fetchEmails} disabled={loading} className="mb-3 flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] py-2.5 text-[10px] font-bold tracking-[0.18em] text-zinc-400 hover:border-emerald-500/30 hover:text-emerald-400">
              <RiRefreshLine className={loading ? 'animate-spin' : ''} size={14} /> {loading ? 'CHECKING...' : 'CHECK INBOX'}
            </button>
            {emails.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center gap-2 text-zinc-600">
                <RiInboxLine size={28} className="opacity-30" />
                <span className="text-[10px] font-mono tracking-[0.28em]">CLICK CHECK INBOX</span>
              </div>
            ) : (
              <div className="scrollbar-small flex-1 space-y-2 overflow-y-auto">
                {emails.map((email) => (
                  <div key={email.id} className="rounded-xl border border-white/5 bg-white/[0.02] p-3 transition-all hover:border-white/10">
                    <div className="text-xs font-bold text-zinc-200">{email.subject}</div>
                    <div className="mt-1 text-[10px] text-zinc-500">{email.from}</div>
                    <div className="mt-1 line-clamp-1 text-[10px] text-zinc-600">{email.preview}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="flex-1 flex flex-col gap-3 p-4">
            <input value={to} onChange={(e) => setTo(e.target.value)} placeholder="To..." className="rounded-xl border border-white/10 bg-black/40 px-3 py-2.5 text-xs text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-emerald-500/40" />
            <input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Subject..." className="rounded-xl border border-white/10 bg-black/40 px-3 py-2.5 text-xs text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-emerald-500/40" />
            <textarea value={body} onChange={(e) => setBody(e.target.value)} placeholder="Message body..." className="scrollbar-small flex-1 resize-none rounded-xl border border-white/10 bg-black/40 px-3 py-2.5 text-xs text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-emerald-500/40" />
            <button onClick={sendEmail} className="rounded-xl bg-emerald-500 py-2.5 text-xs font-black tracking-[0.18em] text-black transition-colors hover:bg-emerald-400">
              {sent ? '✓ SENT' : 'SEND EMAIL'}
            </button>
          </div>
        )}
      </div>
    </WidgetShell>
  )
}
