import { useCallback, useEffect, useState } from 'react'
import {
  RiAddLine,
  RiDatabase2Line,
  RiDeleteBin6Line,
  RiEdit2Line,
  RiSave3Line,
  RiStickyNoteLine
} from 'react-icons/ri'
import type { NoteItem } from '../lib/types'
import { shortTime } from '../lib/types'

/* ═══════════════════════════════════════════
   Notes View — IRIS-style markdown CRUD
   ═══════════════════════════════════════════ */

export default function NotesView() {
  const [notes, setNotes] = useState<NoteItem[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [newTitle, setNewTitle] = useState('')
  const [showCreate, setShowCreate] = useState(false)

  const selected = notes.find((n) => n.id === selectedId) ?? null

  const refresh = useCallback(async () => {
    try {
      const list = await window.desktopApi?.notesList?.() ?? []
      setNotes(list)
      if (!selectedId && list.length > 0) setSelectedId(list[0].id)
    } catch { /* ignore */ }
  }, [selectedId])

  useEffect(() => { void refresh() }, [])
  useEffect(() => {
    const timer = window.setInterval(() => void refresh(), 5000)
    return () => window.clearInterval(timer)
  }, [refresh])

  async function handleCreate() {
    if (!newTitle.trim()) return
    const result = await window.desktopApi?.notesCreate?.(newTitle.trim(), '')
    if (!result) return
    setNewTitle('')
    setShowCreate(false)
    await refresh()
    setSelectedId(result.id)
    setEditing(true)
    setEditContent('')
  }

  async function handleSave() {
    if (!selected) return
    await window.desktopApi?.notesUpdate?.(selected.id, editContent)
    setEditing(false)
    await refresh()
  }

  async function handleDelete(id: string) {
    await window.desktopApi?.notesDelete?.(id)
    if (selectedId === id) setSelectedId(null)
    await refresh()
  }

  return (
    <div className="grid h-full grid-cols-12 gap-6 bg-[#05070b] p-6">
      {/* Sidebar */}
      <div className="col-span-4 flex h-full flex-col overflow-hidden">
        <div className="mb-4 flex items-center justify-between border-b border-white/10 pb-3">
          <div className="flex items-center gap-2 text-zinc-100">
            <RiStickyNoteLine className="text-emerald-400" />
            <span className="text-xs font-bold tracking-[0.18em]">MEMORY BANK</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono tracking-[0.18em] text-zinc-500">{notes.length} ITEMS</span>
            <button onClick={() => setShowCreate(true)} className="rounded-lg border border-zinc-800 p-1.5 text-zinc-500 transition-colors hover:border-emerald-500/30 hover:text-emerald-400">
              <RiAddLine size={14} />
            </button>
          </div>
        </div>

        {/* Create form */}
        {showCreate && (
          <div className="mb-4 flex gap-2">
            <input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              placeholder="Note title..."
              className="flex-1 rounded-xl border border-white/10 bg-black px-3 py-2 text-xs text-zinc-200 outline-none focus:border-emerald-500/40"
              autoFocus
            />
            <button onClick={handleCreate} className="rounded-xl bg-emerald-500 px-3 py-2 text-xs font-bold text-black">ADD</button>
          </div>
        )}

        <div className="scrollbar-small space-y-2 overflow-y-auto pr-2">
          {notes.length === 0 ? (
            <div className="pt-12 text-center text-xs text-zinc-600">
              <p>No notes yet.</p>
              <p className="mt-2 opacity-60">Click + to create one.</p>
            </div>
          ) : (
            notes.map((note) => (
              <div key={note.id} className="group flex items-start gap-2">
                <button
                  onClick={() => { setSelectedId(note.id); setEditing(false) }}
                  className={`flex-1 rounded-2xl border p-4 text-left transition-all ${
                    selected?.id === note.id
                      ? 'border-emerald-500/30 bg-emerald-500/10 shadow-[0_0_15px_rgba(16,185,129,0.08)]'
                      : 'border-white/5 bg-zinc-900/40 hover:border-white/10 hover:bg-white/5'
                  }`}
                >
                  <div className={`text-xs font-bold ${selected?.id === note.id ? 'text-emerald-100' : 'text-zinc-200'}`}>{note.title}</div>
                  <div className="mt-1 line-clamp-2 text-[10px] text-zinc-500">{note.content.slice(0, 80) || 'Empty note'}</div>
                  <div className="mt-2 text-[10px] font-mono text-zinc-600">{shortTime(note.updatedAt)}</div>
                </button>
                <button
                  onClick={() => handleDelete(note.id)}
                  className="mt-4 rounded-lg p-1.5 text-zinc-700 opacity-0 transition-all hover:bg-red-500/10 hover:text-red-400 group-hover:opacity-100"
                >
                  <RiDeleteBin6Line size={14} />
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Content / Editor */}
      <div className="col-span-8 flex h-full flex-col overflow-hidden rounded-[28px] border border-white/5 bg-black/40">
        {selected ? (
          <>
            <div className="flex items-center justify-between border-b border-white/5 bg-white/5 px-6 py-4">
              <div className="flex items-center gap-2 text-zinc-300">
                <RiDatabase2Line className="opacity-60" />
                <span className="text-xs font-bold tracking-[0.16em]">{selected.title.toUpperCase()}</span>
              </div>
              <div className="flex items-center gap-2">
                {editing ? (
                  <button onClick={handleSave} className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-1.5 text-[10px] font-bold tracking-[0.16em] text-black">
                    <RiSave3Line size={12} /> SAVE
                  </button>
                ) : (
                  <button
                    onClick={() => { setEditing(true); setEditContent(selected.content) }}
                    className="flex items-center gap-1.5 rounded-md border border-white/10 bg-black/20 px-3 py-1.5 text-[10px] font-mono tracking-[0.18em] text-zinc-400 hover:border-emerald-500/30 hover:text-emerald-400"
                  >
                    <RiEdit2Line size={12} /> EDIT
                  </button>
                )}
              </div>
            </div>
            <div className="scrollbar-small flex-1 overflow-y-auto p-8">
              {editing ? (
                <textarea
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  className="h-full w-full resize-none bg-transparent text-[14px] leading-8 text-zinc-300 outline-none"
                  autoFocus
                />
              ) : (
                <div className="whitespace-pre-wrap text-[14px] leading-8 text-zinc-300">
                  {selected.content || <span className="italic text-zinc-600">Empty note — click EDIT to add content.</span>}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 text-zinc-700">
            <RiStickyNoteLine size={44} className="opacity-20" />
            <span className="text-[10px] font-mono tracking-[0.28em]">SELECT A DATA NODE</span>
          </div>
        )}
      </div>
    </div>
  )
}
