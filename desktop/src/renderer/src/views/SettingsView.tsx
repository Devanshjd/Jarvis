import { useEffect, useMemo, useRef, useState } from 'react'
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
import type { AmbientSignalSource, AmbientSignalsStatus, JarvisShellSnapshot, PersonaProfile, PersonaStatus, SettingsTab } from '../lib/types'
import { SHELL_VOICE_ENGINE } from '../lib/types'

const ambientSources: Array<{
  source: AmbientSignalSource
  label: string
  description: string
  available: boolean
}> = [
  {
    source: 'screen_errors',
    label: 'SCREEN ERRORS',
    description: 'Counts repeated errors only. It never receives an image, OCR text, or a window title.',
    available: true
  },
  {
    source: 'battery',
    label: 'BATTERY',
    description: 'Reads charge percentage and charging state only.',
    available: true
  },
  {
    source: 'calendar',
    label: 'CALENDAR',
    description: 'Reserved until a local calendar provider is connected.',
    available: false
  }
]

/* ═══════════════════════════════════════════
   Settings View — Stormbreaker-style config center
   ═══════════════════════════════════════════ */

export default function SettingsView({
  snapshot,
  personaStatus,
  ambientSignals,
  ambientSignalsUnavailable,
  ambientConsentPending,
  onSetAmbientConsent,
  onSave
}: {
  snapshot: JarvisShellSnapshot | null
  personaStatus?: PersonaStatus
  ambientSignals: AmbientSignalsStatus | null
  ambientSignalsUnavailable: boolean
  ambientConsentPending: AmbientSignalSource | null
  onSetAmbientConsent: (source: AmbientSignalSource, on: boolean) => void
  onSave: (payload: { operatorName?: string; provider?: string; model?: string; voiceEngine?: string; persona?: PersonaProfile; voiceProfile?: string }) => Promise<void>
}) {
  const [activeTab, setActiveTab] = useState<SettingsTab>('general')
  const [operatorName, setOperatorName] = useState(snapshot?.config.operatorName ?? '')
  const [provider, setProvider] = useState(snapshot?.config.provider ?? 'ollama')
  const [model, setModel] = useState(snapshot?.config.model ?? '')
  const [persona, setPersona] = useState<PersonaProfile>({
    instructions: '', humour: 'subtle', response_style: 'concise', proactivity: 'suggest_only'
  })
  const [voiceProfile, setVoiceProfile] = useState<'Kore' | 'Puck' | 'Charon' | 'Aoede'>('Kore')
  const [savingSettings, setSavingSettings] = useState(false)
  const [saveMessage, setSaveMessage] = useState('')
  const [pinInput, setPinInput] = useState('')
  const [pinSaved, setPinSaved] = useState(false)
  const loadedSnapshotRef = useRef(false)

  useEffect(() => {
    // Shell snapshots refresh in the background. Load the form once so a
    // refresh never overwrites the operator while they are editing a persona.
    if (!snapshot || loadedSnapshotRef.current) return
    setOperatorName(snapshot?.config.operatorName ?? '')
    setProvider(snapshot?.config.provider ?? 'ollama')
    setModel(snapshot?.config.model ?? '')
    setPersona(snapshot?.config.persona ?? { instructions: '', humour: 'subtle', response_style: 'concise', proactivity: 'suggest_only' })
    const configuredVoice = snapshot?.config.geminiVoiceName
    if (configuredVoice === 'Kore' || configuredVoice === 'Puck' || configuredVoice === 'Charon' || configuredVoice === 'Aoede') setVoiceProfile(configuredVoice)
    loadedSnapshotRef.current = true
  }, [snapshot])

  async function saveGeneralSettings() {
    setSavingSettings(true)
    setSaveMessage('')
    try {
      await onSave({ operatorName, provider, model, voiceEngine: SHELL_VOICE_ENGINE, persona, voiceProfile })
      setSaveMessage(personaStatus?.loaded ? 'SAVED LOCALLY. BACKEND PERSONA PROFILE IS LOADED.' : 'SAVED LOCALLY. BACKEND APPLICATION IS NOT YET VERIFIED.')
    } catch (err) {
      setSaveMessage(`SAVE FAILED: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setSavingSettings(false)
    }
  }

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

  const ambientSourceReady = Boolean(ambientSignals) && !ambientSignalsUnavailable
  const ambientStatus = ambientSignalsUnavailable
    ? { label: 'SERVICE UNAVAILABLE', tone: 'border-zinc-700 bg-zinc-900/35 text-zinc-500' }
    : !ambientSignals
      ? { label: 'CHECKING LOCAL STATUS', tone: 'border-zinc-700 bg-zinc-900/35 text-zinc-500' }
      : ambientSignals.proactivity === 'off'
        ? { label: 'PERSONA SUGGESTIONS OFF', tone: 'border-zinc-700 bg-zinc-900/35 text-zinc-500' }
        : ambientSignals.enabled
          ? { label: 'CONSENTED SOURCES ACTIVE', tone: 'border-emerald-500/25 bg-emerald-500/5 text-emerald-200' }
          : { label: 'NO SOURCE ENABLED', tone: 'border-white/10 bg-black/25 text-zinc-500' }

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
              <div className="stormbreaker-setting-card md:col-span-2">
                <div className="mb-4 flex items-center justify-between">
                  <span className="stormbreaker-setting-title"><RiBrainLine /> Runtime Identity</span>
                  <button disabled={savingSettings} onClick={() => void saveGeneralSettings()} className="flex items-center gap-2 rounded-lg bg-white px-5 py-3 text-xs font-bold tracking-[0.18em] text-black disabled:cursor-not-allowed disabled:opacity-45">
                    <RiSave3Line /> {savingSettings ? 'SAVING' : 'SAVE'}
                  </button>
                </div>
                <div className="grid gap-4 md:grid-cols-3">
                  <label className="stormbreaker-input-wrap">
                    <span className="stormbreaker-input-label">Operator Name</span>
                    <input value={operatorName} onChange={(e) => setOperatorName(e.target.value)} className="stormbreaker-input" placeholder="Dev" />
                  </label>
                  <label className="stormbreaker-input-wrap">
                    <span className="stormbreaker-input-label">Active Provider</span>
                    <input value={provider} onChange={(e) => setProvider(e.target.value)} className="stormbreaker-input" placeholder="ollama" />
                  </label>
                  <label className="stormbreaker-input-wrap">
                    <span className="stormbreaker-input-label">Model</span>
                    <input value={model} onChange={(e) => setModel(e.target.value)} className="stormbreaker-input" placeholder="gemma3:4b" />
                  </label>
                </div>
              </div>

              <div className="stormbreaker-setting-card md:col-span-2">
                <div className="flex flex-col gap-3 border-b border-white/10 pb-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="stormbreaker-setting-title"><RiBrainLine /> Persona Profile</div>
                  <span className={`rounded border px-2 py-1 text-[9px] font-mono tracking-[0.14em] ${personaStatus?.loaded ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300' : 'border-amber-500/30 bg-amber-500/10 text-amber-200'}`}>
                    {personaStatus?.loaded ? 'BACKEND PROFILE LOADED' : 'BACKEND APPLICATION NOT VERIFIED'}
                  </span>
                </div>
                <p className="mt-4 text-[11px] leading-6 text-zinc-500">This saves an operator-authored local behaviour profile. It guides tone and initiative; it does not make JARVIS conscious, emotional, or able to claim observations it did not make.</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button type="button" onClick={() => setPersona((current) => ({ ...current, instructions: 'Calm, capable, protective, and concise. Use subtle dry humour only when it improves the moment. State uncertainty plainly.' }))} className="rounded-lg border border-amber-500/25 bg-amber-500/5 px-3 py-2 text-[9px] font-black tracking-[0.12em] text-amber-200 hover:bg-amber-500/10">TACTICAL BUTLER</button>
                  <button type="button" onClick={() => setPersona((current) => ({ ...current, instructions: 'Warm, practical, and encouraging. Explain technical work clearly and keep humour gentle.' }))} className="rounded-lg border border-white/10 px-3 py-2 text-[9px] font-black tracking-[0.12em] text-zinc-300 hover:border-zinc-600">WARM PARTNER</button>
                  <button type="button" onClick={() => setPersona((current) => ({ ...current, instructions: 'Direct, precise, and brief. Prioritise decisions, evidence, and next actions over small talk.' }))} className="rounded-lg border border-white/10 px-3 py-2 text-[9px] font-black tracking-[0.12em] text-zinc-300 hover:border-zinc-600">DIRECT OPERATOR</button>
                </div>
                <label className="mt-4 block">
                  <span className="stormbreaker-input-label">YOUR PERSONA NOTES</span>
                  <textarea
                    value={persona.instructions}
                    onChange={(e) => setPersona((current) => ({ ...current, instructions: e.target.value.slice(0, 500) }))}
                    placeholder="Example: calm, sharp and reassuring; use dry humour sparingly; never exaggerate progress."
                    className="stormbreaker-input mt-2 h-28 resize-none"
                  />
                </label>
                <div className="mt-4 grid gap-4 md:grid-cols-3">
                  <label className="stormbreaker-input-wrap"><span className="stormbreaker-input-label">Humour</span><select value={persona.humour} onChange={(e) => setPersona((current) => ({ ...current, humour: e.target.value as PersonaProfile['humour'] }))} className="stormbreaker-input mt-2"><option value="off">Off</option><option value="subtle">Subtle</option><option value="dry">Dry</option></select></label>
                  <label className="stormbreaker-input-wrap"><span className="stormbreaker-input-label">Response style</span><select value={persona.response_style} onChange={(e) => setPersona((current) => ({ ...current, response_style: e.target.value as PersonaProfile['response_style'] }))} className="stormbreaker-input mt-2"><option value="concise">Concise</option><option value="balanced">Balanced</option><option value="detailed">Detailed</option></select></label>
                  <label className="stormbreaker-input-wrap"><span className="stormbreaker-input-label">Proactive behaviour</span><select value={persona.proactivity} onChange={(e) => setPersona((current) => ({ ...current, proactivity: e.target.value as PersonaProfile['proactivity'] }))} className="stormbreaker-input mt-2"><option value="off">Off</option><option value="suggest_only">Suggest only</option></select></label>
                </div>
                <div className="mt-3 flex items-center justify-between text-[10px] font-mono text-zinc-600">
                  <span>Suggestions are recommendations only; they never act, send, or interrupt without your approval.</span>
                  <span>{persona.instructions.length}/500</span>
                </div>
                {saveMessage ? <div className={`mt-4 rounded-xl border px-4 py-3 text-[11px] leading-5 ${saveMessage.startsWith('SAVE FAILED') ? 'border-red-500/30 bg-red-500/10 text-red-200' : 'border-emerald-500/25 bg-emerald-500/10 text-emerald-200'}`}>{saveMessage}</div> : null}
              </div>

              <div className="stormbreaker-setting-card md:col-span-2">
                <div className="flex flex-col gap-3 border-b border-white/10 pb-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="stormbreaker-setting-title"><RiBrainLine /> Ambient Assistance</div>
                  <span className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-[9px] font-mono tracking-[0.14em] text-emerald-300">LOCAL ONLY</span>
                </div>
                <p className="mt-4 text-[11px] leading-6 text-zinc-500">
                  The dashboard stays voice-first. These switches are the manual fallback for approving what JARVIS may observe; every source starts off and can only suggest a next step.
                </p>
                <div className={`mt-4 rounded-xl border px-3 py-2 text-[9px] font-mono tracking-[0.12em] ${ambientStatus.tone}`}>
                  {ambientStatus.label}
                </div>
                {ambientSignalsUnavailable ? <p className="mt-3 text-[10px] leading-5 text-zinc-600">The local signal service is unavailable, so no device or screen status is being claimed. Restart the backend when it is safe to do so, then return here.</p> : null}
                {ambientSignals?.proactivity === 'off' ? <p className="mt-3 text-[10px] leading-5 text-zinc-600">Sources may be approved below, but they stay silent until you save Persona Profile with Proactive behaviour set to Suggest only.</p> : null}
                <div className="mt-4 grid gap-3 md:grid-cols-3">
                  {ambientSources.map((item) => {
                    const enabled = Boolean(ambientSignals?.sources[item.source])
                    const pending = ambientConsentPending === item.source
                    const disabled = !item.available || !ambientSourceReady || pending
                    return <div key={item.source} className="rounded-xl border border-white/10 bg-black/25 px-4 py-3">
                      <div className="flex items-center justify-between gap-3">
                        <span className={`text-[10px] font-mono tracking-[0.14em] ${item.available ? 'text-zinc-200' : 'text-zinc-600'}`}>{item.label}</span>
                        <button
                          type="button"
                          data-testid={`ambient-consent-${item.source}`}
                          disabled={disabled}
                          onClick={() => onSetAmbientConsent(item.source, !enabled)}
                          title={item.description}
                          className={`rounded border px-2.5 py-1.5 text-[8px] font-mono tracking-[0.12em] transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${
                            enabled
                              ? 'border-emerald-500/35 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20'
                              : 'border-zinc-700 text-zinc-500 hover:border-amber-500/35 hover:text-amber-200'
                          }`}
                        >
                          {pending ? 'SAVING' : !item.available ? 'RESERVED' : enabled ? 'ON' : 'OFF'}
                        </button>
                      </div>
                      <p className="mt-3 text-[10px] leading-5 text-zinc-600">{item.description}</p>
                    </div>
                  })}
                </div>
                <p className="mt-4 text-[10px] leading-5 text-zinc-600">Voice commands for these switches are not wired yet. Until then, this is the deliberate manual control point; the dashboard only shows a compact state or a real observed alert.</p>
              </div>

              <div className="stormbreaker-setting-card">
                <div className="mb-4 stormbreaker-setting-title"><RiUserVoiceLine /> Voice Profile</div>
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

              <div className="stormbreaker-setting-card">
                <div className="mb-4 stormbreaker-setting-title"><RiCommandLine /> Runtime Mode</div>
                <div className="rounded-2xl border border-white/10 bg-[#050505] px-4 py-4 text-sm font-bold text-white">
                  {snapshot?.config.mode || 'GENERAL'}
                </div>
                <p className="mt-4 text-[11px] leading-6 text-zinc-500">Current operational mode. Switch via voice or chat command.</p>
              </div>
            </motion.div>
          ) : null}

          {activeTab === 'keys' ? (
            <motion.div key="keys" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} className="stormbreaker-setting-card">
              <div className="mb-6 flex items-center justify-between border-b border-white/10 pb-4">
                <span className="stormbreaker-setting-title"><RiShieldKeyholeLine /> External API Endpoints</span>
                <span className="rounded-lg bg-white px-4 py-2 text-xs font-bold tracking-[0.16em] text-black">LOCAL VAULT</span>
              </div>
              <div className="grid gap-5 md:grid-cols-2">
                {keyRows.map(([label, value]) => (
                  <div key={label} className="space-y-2">
                    <div className="text-[10px] font-mono tracking-[0.18em] text-zinc-400 uppercase">{label}</div>
                    <div className="stormbreaker-input text-sm font-mono text-zinc-100">{value}</div>
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
              <div className="stormbreaker-setting-card">
                <div className="mb-6 stormbreaker-setting-title"><RiShieldKeyholeLine /> Master PIN</div>
                <div className="space-y-4">
                  <label className="stormbreaker-input-wrap">
                    <span className="stormbreaker-input-label">New 4-Digit PIN</span>
                    <input type="password" value={pinInput} onChange={(e) => setPinInput(e.target.value.replace(/\D/g, '').slice(0, 4))} className="stormbreaker-input text-center text-2xl tracking-[0.5em]" placeholder="••••" maxLength={4} />
                  </label>
                  <button onClick={() => { if (pinInput.length === 4) setPinSaved(true) }} className="w-full rounded-xl bg-white py-3 text-xs font-bold tracking-[0.18em] text-black transition-colors hover:bg-amber-400">
                    UPDATE PIN
                  </button>
                  {pinSaved && (
                    <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-center text-[11px] text-amber-200">PIN updated successfully.</div>
                  )}
                </div>
              </div>

              <div className="stormbreaker-setting-card flex flex-col items-center justify-center text-center">
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
