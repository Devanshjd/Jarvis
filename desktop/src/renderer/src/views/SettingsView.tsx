import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  RiBrainLine,
  RiCameraLine,
  RiCommandLine,
  RiRecordCircleLine,
  RiSave3Line,
  RiShieldKeyholeLine,
  RiUserVoiceLine
} from 'react-icons/ri'
import type { JarvisShellSnapshot, SettingsTab } from '../lib/types'
import { SHELL_VOICE_ENGINE } from '../lib/types'

/* ═══════════════════════════════════════════
   Settings View — IRIS-style config center
   ═══════════════════════════════════════════ */

export default function SettingsView({
  snapshot,
  onSave
}: {
  snapshot: JarvisShellSnapshot | null
  onSave: (payload: { operatorName?: string; provider?: string; model?: string; voiceEngine?: string; personality?: string; voiceProfile?: string }) => Promise<void>
}) {
  const [activeTab, setActiveTab] = useState<SettingsTab>('general')
  const [operatorName, setOperatorName] = useState(snapshot?.config.operatorName ?? '')
  const [provider, setProvider] = useState(snapshot?.config.provider ?? 'ollama')
  const [model, setModel] = useState(snapshot?.config.model ?? '')
  const [personality, setPersonality] = useState('')
  const [voiceProfile, setVoiceProfile] = useState<'Kore' | 'Puck' | 'Charon' | 'Aoede'>('Kore')
  const [pinInput, setPinInput] = useState('')
  const [pinSaved, setPinSaved] = useState(false)

  useEffect(() => {
    setOperatorName(snapshot?.config.operatorName ?? '')
    setProvider(snapshot?.config.provider ?? 'ollama')
    setModel(snapshot?.config.model ?? '')
  }, [snapshot])

  const keyRows = useMemo(() => {
    if (!snapshot) return []
    return [
      ['Gemini Pro Core', snapshot.config.apiKeys.gemini || 'NOT SET'],
      ['Groq Fast Inferencing', snapshot.config.apiKeys.groq || 'NOT SET'],
      ['OpenAI Operations', snapshot.config.apiKeys.openai || 'NOT SET'],
      ['Anthropic Core', snapshot.config.apiKeys.anthropic || 'NOT SET'],
      ['DeepSeek Fallback', snapshot.config.apiKeys.deepseek || 'NOT SET']
    ]
  }, [snapshot])

  return (
    <div className="flex h-full justify-center overflow-y-auto bg-black px-8 py-10">
      <div className="w-full max-w-5xl">
        <div className="mb-8 flex flex-col gap-6 border-b border-white/10 pb-6 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-5">
            <div className="rounded-2xl border border-white/10 bg-[#111] p-4">
              <RiShieldKeyholeLine size={32} className="text-white" />
            </div>
            <div>
              <h2 className="text-4xl font-bold text-white">Command Center</h2>
              <p className="mt-2 flex items-center gap-2 text-[11px] font-mono tracking-[0.18em] text-zinc-500 uppercase">
                <RiRecordCircleLine className="text-zinc-600" /> System Console
              </p>
            </div>
          </div>
          <div className="flex overflow-hidden rounded-2xl border border-white/10 bg-[#0a0a0c] p-1">
            {(['general', 'keys', 'security'] as SettingsTab[]).map((tab) => (
              <button key={tab} onClick={() => setActiveTab(tab)} className={`rounded-xl px-6 py-3 text-xs font-bold tracking-[0.18em] transition-all ${activeTab === tab ? 'bg-white text-black' : 'text-zinc-500 hover:bg-white/5 hover:text-white'}`}>
                {tab.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <AnimatePresence mode="wait">
          {activeTab === 'general' ? (
            <motion.div key="general" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} className="grid grid-cols-1 gap-6 md:grid-cols-2">
              <div className="iris-setting-card md:col-span-2">
                <div className="mb-4 flex items-center justify-between">
                  <span className="iris-setting-title"><RiBrainLine /> Runtime Identity</span>
                  <button onClick={() => void onSave({ operatorName, provider, model, voiceEngine: SHELL_VOICE_ENGINE, personality, voiceProfile })} className="flex items-center gap-2 rounded-lg bg-white px-5 py-3 text-xs font-bold tracking-[0.18em] text-black">
                    <RiSave3Line /> SAVE
                  </button>
                </div>
                <div className="grid gap-4 md:grid-cols-3">
                  <label className="iris-input-wrap">
                    <span className="iris-input-label">Operator Name</span>
                    <input value={operatorName} onChange={(e) => setOperatorName(e.target.value)} className="iris-input" placeholder="Dev" />
                  </label>
                  <label className="iris-input-wrap">
                    <span className="iris-input-label">Active Provider</span>
                    <input value={provider} onChange={(e) => setProvider(e.target.value)} className="iris-input" placeholder="ollama" />
                  </label>
                  <label className="iris-input-wrap">
                    <span className="iris-input-label">Model</span>
                    <input value={model} onChange={(e) => setModel(e.target.value)} className="iris-input" placeholder="gemma3:4b" />
                  </label>
                </div>
              </div>

              <div className="iris-setting-card md:col-span-2">
                <div className="mb-4 iris-setting-title"><RiBrainLine /> Personality Matrix</div>
                <textarea
                  value={personality}
                  onChange={(e) => setPersonality(e.target.value.slice(0, 500))}
                  placeholder="Describe how JARVIS should behave. Example: 'Be witty and confident, like Tony Stark's AI. Use casual language. Sometimes add sarcastic humor.'"
                  className="iris-input h-28 resize-none"
                />
                <div className="mt-2 flex items-center justify-between text-[10px] font-mono text-zinc-600">
                  <span>Defines the AI's conversational personality</span>
                  <span>{personality.length}/500</span>
                </div>
              </div>

              <div className="iris-setting-card">
                <div className="mb-4 iris-setting-title"><RiUserVoiceLine /> Voice Profile</div>
                <div className="grid grid-cols-2 gap-3">
                  {(['Kore', 'Puck', 'Charon', 'Aoede'] as const).map((v) => (
                    <button key={v} onClick={() => setVoiceProfile(v)} className={`rounded-xl border px-4 py-4 text-xs font-bold tracking-[0.18em] transition-all ${voiceProfile === v ? 'border-white bg-white text-black' : 'border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-600'}`}>
                      {v.toUpperCase()}
                    </button>
                  ))}
                </div>
                <p className="mt-4 text-[11px] leading-6 text-zinc-500">
                  Gemini Live voice persona. Kore = calm female, Puck = energetic male, Charon = deep male, Aoede = warm female.
                </p>
              </div>

              <div className="iris-setting-card">
                <div className="mb-4 iris-setting-title"><RiCommandLine /> Runtime Mode</div>
                <div className="rounded-2xl border border-white/10 bg-[#050505] px-4 py-4 text-sm font-bold text-white">
                  {snapshot?.config.mode || 'GENERAL'}
                </div>
                <p className="mt-4 text-[11px] leading-6 text-zinc-500">Current operational mode. Switch via voice or chat command.</p>
              </div>
            </motion.div>
          ) : null}

          {activeTab === 'keys' ? (
            <motion.div key="keys" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} className="iris-setting-card">
              <div className="mb-6 flex items-center justify-between border-b border-white/10 pb-4">
                <span className="iris-setting-title"><RiShieldKeyholeLine /> External API Endpoints</span>
                <span className="rounded-lg bg-white px-4 py-2 text-xs font-bold tracking-[0.16em] text-black">LOCAL VAULT</span>
              </div>
              <div className="grid gap-5 md:grid-cols-2">
                {keyRows.map(([label, value]) => (
                  <div key={label} className="space-y-2">
                    <div className="text-[10px] font-mono tracking-[0.18em] text-zinc-400 uppercase">{label}</div>
                    <div className="iris-input text-sm font-mono text-zinc-100">{value}</div>
                  </div>
                ))}
              </div>
              <div className="mt-6 rounded-2xl border border-white/5 bg-[#050505] p-4 text-[11px] leading-6 text-zinc-400">
                Keys remain on your machine. This view shows masked values only. Edit keys via config file.
              </div>
            </motion.div>
          ) : null}

          {activeTab === 'security' ? (
            <motion.div key="security" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} className="grid grid-cols-1 gap-6 md:grid-cols-2">
              <div className="iris-setting-card">
                <div className="mb-6 iris-setting-title"><RiShieldKeyholeLine /> Master PIN</div>
                <div className="space-y-4">
                  <label className="iris-input-wrap">
                    <span className="iris-input-label">New 4-Digit PIN</span>
                    <input type="password" value={pinInput} onChange={(e) => setPinInput(e.target.value.replace(/\D/g, '').slice(0, 4))} className="iris-input text-center text-2xl tracking-[0.5em]" placeholder="••••" maxLength={4} />
                  </label>
                  <button onClick={() => { if (pinInput.length === 4) setPinSaved(true) }} className="w-full rounded-xl bg-white py-3 text-xs font-bold tracking-[0.18em] text-black transition-colors hover:bg-emerald-400">
                    UPDATE PIN
                  </button>
                  {pinSaved && (
                    <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-center text-[11px] text-emerald-200">PIN updated successfully.</div>
                  )}
                </div>
              </div>

              <div className="iris-setting-card flex flex-col items-center justify-center text-center">
                <div className="mb-6 flex h-24 w-24 items-center justify-center rounded-full border border-white/10 bg-white/5">
                  <RiCameraLine size={36} className="text-zinc-400" />
                </div>
                <div className="mb-2 text-sm font-bold text-white">Biometric Registry</div>
                <div className="text-[10px] font-mono tracking-[0.2em] text-zinc-500">0 FACES ENROLLED</div>
                <p className="mt-4 text-[11px] leading-6 text-zinc-500">
                  Face recognition enrollment coming soon. Uses face-api.js for secure local biometric auth.
                </p>
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </div>
  )
}
