import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'

type ProviderInfo = {
  name?: string
  model?: string
  local?: boolean
}

type RuntimeStatus = {
  provider?: ProviderInfo
  mode?: string
  agent_mode?: boolean
  voice_enabled?: boolean
  messages?: number
  memories?: number
  tasks?: number
  plugins?: string[]
  waiting_for_input?: boolean
  waiting_summary?: string
}

type ChatMessage = {
  id: number
  role: string
  text: string
  ts: string
}

type ChatResponse = {
  reply: string
  messages: ChatMessage[]
  waiting_for_input: boolean
  processing: boolean
  timed_out?: boolean
  status?: RuntimeStatus
}

const QUICK_RUNS = [
  'tell me the news of india',
  'can you text meet that i am coming on whatsapp',
  '/task',
  '/taskbrain',
  'can you check if my system is running completely safe or not',
]

async function fetchJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init)
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

function formatProvider(provider?: ProviderInfo) {
  if (!provider) return 'Unknown'
  const model = provider.model ? ` // ${provider.model}` : ''
  const locality = provider.local ? ' LOCAL' : ''
  return `${provider.name ?? 'Unknown'}${model}${locality}`
}

function formatRole(role: string) {
  if (role === 'assistant') return 'JARVIS'
  if (role === 'user') return 'YOU'
  return role.toUpperCase()
}

export default function App() {
  const [status, setStatus] = useState<RuntimeStatus | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [prompt, setPrompt] = useState('')
  const [approveDesktop, setApproveDesktop] = useState(false)
  const [busy, setBusy] = useState(false)
  const [streamState, setStreamState] = useState('Ready')
  const [error, setError] = useState('')
  const messagesRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    void refreshAll()
  }, [])

  useEffect(() => {
    const element = messagesRef.current
    if (element) element.scrollTop = element.scrollHeight
  }, [messages])

  async function refreshAll() {
    try {
      const [nextStatus, history] = await Promise.all([
        fetchJson<RuntimeStatus>('/api/status'),
        fetchJson<{ messages: ChatMessage[] }>('/api/history?limit=150'),
      ])
      setStatus(nextStatus)
      setMessages(history.messages ?? [])
      setStreamState(nextStatus.waiting_for_input ? 'Waiting' : 'Ready')
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setStreamState('Offline')
    }
  }

  async function sendPrompt(text?: string) {
    const nextPrompt = (text ?? prompt).trim()
    if (!nextPrompt) return
    setBusy(true)
    setStreamState('Processing')
    setError('')
    try {
      const result = await fetchJson<ChatResponse>('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: nextPrompt,
          approve_desktop: approveDesktop,
        }),
      })
      const history = await fetchJson<{ messages: ChatMessage[] }>('/api/history?limit=150')
      setMessages(history.messages ?? result.messages ?? [])
      if (result.status) setStatus(result.status)
      setStreamState(result.waiting_for_input ? 'Waiting' : result.timed_out ? 'Timed out' : 'Ready')
      if (!text) setPrompt('')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setStreamState('Error')
    } finally {
      setBusy(false)
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    void sendPrompt()
  }

  const heroPills = useMemo(() => {
    return [
      `messages ${status?.messages ?? 0}`,
      `memories ${status?.memories ?? 0}`,
      `tasks ${status?.tasks ?? 0}`,
      status?.agent_mode ? 'agent mode on' : 'agent mode off',
    ]
  }, [status])

  return (
    <div className="shell">
      <header className="topbar">
        <section className="card hero">
          <div className="eyebrow">JARVIS // TypeScript Shell</div>
          <h1>Operator Console</h1>
          <p className="hero-copy">
            React and TypeScript on the surface, Python orchestration underneath.
            This is the new shell for the same JARVIS runtime, built so we can move
            past Tkinter without throwing away the brain.
          </p>
          <div className="pill-row">
            {heroPills.map((pill) => (
              <span className="pill" key={pill}>
                {pill}
              </span>
            ))}
          </div>
        </section>

        <aside className="card status-card">
          <div className="section-head">
            <span>Runtime Status</span>
            <span className={`live-badge ${streamState.toLowerCase().replace(/\s+/g, '-')}`}>{streamState}</span>
          </div>

          <div className="status-grid">
            <div className="status-tile">
              <span className="label">Provider</span>
              <strong>{formatProvider(status?.provider)}</strong>
            </div>
            <div className="status-tile">
              <span className="label">Mode</span>
              <strong>{status?.mode ?? 'General'}</strong>
            </div>
            <div className="status-tile">
              <span className="label">Pending Task</span>
              <strong>{status?.waiting_for_input ? 'Waiting for input' : 'None'}</strong>
            </div>
            <div className="status-tile">
              <span className="label">Plugins</span>
              <strong>{(status?.plugins ?? []).join(', ') || 'Loading…'}</strong>
            </div>
          </div>

          {status?.waiting_summary ? (
            <div className="pending-box">
              <span className="label">Waiting Summary</span>
              <pre>{status.waiting_summary}</pre>
            </div>
          ) : null}
        </aside>
      </header>

      <main className="layout">
        <section className="card stream-card">
          <div className="section-head">
            <span>Conversation Stream</span>
            <button className="ghost" type="button" onClick={() => void refreshAll()}>
              Refresh
            </button>
          </div>

          <div className="message-stream" ref={messagesRef}>
            {messages.map((message) => (
              <article className={`message ${message.role}`} key={`${message.id}-${message.ts}`}>
                <div className="message-meta">
                  <span>{formatRole(message.role)}</span>
                  <span>{message.ts}</span>
                </div>
                <div className="message-body">{message.text}</div>
              </article>
            ))}
          </div>

          <form className="composer" onSubmit={onSubmit}>
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Message JARVIS or issue an operator command..."
            />

            <div className="composer-footer">
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={approveDesktop}
                  onChange={(event) => setApproveDesktop(event.target.checked)}
                />
                Approve desktop actions for this turn
              </label>

              <button className="send" type="submit" disabled={busy}>
                {busy ? 'Processing…' : 'Send'}
              </button>
            </div>
          </form>

          {error ? <div className="error-box">{error}</div> : null}
        </section>

        <aside className="side-column">
          <section className="card quick-card">
            <div className="section-head">
              <span>Quick Runs</span>
            </div>
            <div className="quick-list">
              {QUICK_RUNS.map((item) => (
                <button
                  key={item}
                  className="quick-action"
                  type="button"
                  onClick={() => {
                    setPrompt(item)
                    void sendPrompt(item)
                  }}
                >
                  {item}
                </button>
              ))}
            </div>
          </section>

          <section className="card notes-card">
            <div className="section-head">
              <span>Shell Notes</span>
            </div>
            <ul className="notes-list">
              <li>This is the TypeScript shell. The Python runtime still owns memory, tools, and automation.</li>
              <li>Use the approval toggle when you want keyboard, mouse, screen, or messaging actions to proceed.</li>
              <li>The backend endpoints are `/api/status`, `/api/history`, and `/api/chat`.</li>
            </ul>
          </section>
        </aside>
      </main>
    </div>
  )
}
