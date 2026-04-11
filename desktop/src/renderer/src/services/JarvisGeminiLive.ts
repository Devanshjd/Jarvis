import { base64ToFloat32, downsampleTo16000, floatTo16BitPCM } from './audioUtils'

type VoiceBridgeCallbacks = {
  onStateChange?: (state: VoiceBridgeState) => void
  onBackendTurn?: () => void | Promise<void>
  getApproveDesktop?: () => boolean
  getRealtimeContext?: () => Promise<RealtimeContext> | RealtimeContext
}

type ChatResponse = {
  reply: string
  waiting_for_input?: boolean
}

export type VoiceBridgeState = {
  loaded: boolean
  active: boolean
  connecting: boolean
  engine: string
  live_session: boolean
  wake_word_active: boolean
  mic_muted: boolean
  last_input: string
  last_output: string
  error: string
}

type RealtimeContext = {
  runningApps?: string[]
  provider?: string
  mode?: string
  backendState?: string
  currentTask?: string
}

export type VisionSource = 'none' | 'screen' | 'camera'

type StartOptions = {
  apiKey: string
  model: string
  voiceName: string
  ambientContext?: string
}

function normalizeLiveModel(model: string | undefined | null) {
  const raw = String(model ?? '').trim()
  if (!raw) {
    return 'models/gemini-2.5-flash-native-audio-latest'
  }
  // Reject models known NOT to support BidiGenerateContent (Live)
  const lower = raw.toLowerCase()
  const invalidPatterns = ['flash-exp', '2.0-flash-live', 'pro-exp', 'ultra']
  if (invalidPatterns.some(p => lower.includes(p)) && !lower.includes('native-audio') && !lower.includes('live-')) {
    console.warn(`[GeminiLive] Model "${raw}" is not a valid native-audio model, falling back to default`)
    return 'models/gemini-2.5-flash-native-audio-latest'
  }
  return raw.startsWith('models/') ? raw : `models/${raw}`
}

export class JarvisGeminiLive {
  private socket: WebSocket | null = null
  private audioContext: AudioContext | null = null
  private mediaStream: MediaStream | null = null
  private workletNode: AudioWorkletNode | null = null
  // Public so sphere can read audio levels
  analyser: AnalyserNode | null = null
  private monitorGain: GainNode | null = null
  private outputGain: GainNode | null = null
  private nextStartTime = 0
  private muteUntil = 0
  private micMuted = false
  private audioChunksPlayed = 0
  private inputBuffer = ''
  private outputBuffer = ''
  private appWatcherTimer: number | null = null
  private lastContextSignature = ''
  private visionStream: MediaStream | null = null
  private visionVideo: HTMLVideoElement | null = null
  private visionTimer: number | null = null
  private visionSource: VisionSource = 'none'
  private state: VoiceBridgeState = {
    loaded: false,
    active: false,
    connecting: false,
    engine: 'gemini',
    live_session: false,
    wake_word_active: false,
    mic_muted: false,
    last_input: '',
    last_output: '',
    error: ''
  }

  constructor(
    private readonly backendBase: string,
    private readonly callbacks: VoiceBridgeCallbacks = {}
  ) {}

  snapshot() {
    return { ...this.state }
  }

  setMute(muted: boolean) {
    this.micMuted = muted
    this.updateState({ mic_muted: muted })
  }

  private updateState(next: Partial<VoiceBridgeState>) {
    this.state = { ...this.state, ...next }
    this.callbacks.onStateChange?.({ ...this.state })
  }

  async start(options: StartOptions) {
    if (this.state.connecting || this.state.active) {
      console.log('[GeminiLive] Already connecting or active, skipping start')
      return
    }
    const apiKey = options.apiKey.trim()
    console.log('[GeminiLive] Starting voice session', {
      hasKey: Boolean(apiKey),
      keyLength: apiKey.length,
      model: options.model,
      voiceName: options.voiceName
    })
    if (!apiKey) {
      this.updateState({
        loaded: false,
        active: false,
        connecting: false,
        live_session: false,
        wake_word_active: false,
        mic_muted: this.micMuted,
        error: 'Gemini API key is missing.'
      })
      throw new Error('Gemini API key is missing.')
    }

    await this.stop(false)

    this.updateState({
      connecting: true,
      loaded: true,
      error: ''
    })

    const AudioContextCtor =
      window.AudioContext ||
      (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!AudioContextCtor) {
      throw new Error('AudioContext is not available in this shell.')
    }
    this.audioContext = new AudioContextCtor()
    // Resume immediately — Electron allows autoplay
    if (this.audioContext.state === 'suspended') {
      await this.audioContext.resume()
    }
    this.analyser = this.audioContext.createAnalyser()
    this.analyser.fftSize = 256
    this.analyser.smoothingTimeConstant = 0.5
    // Output gain so audio is actually audible
    this.outputGain = this.audioContext.createGain()
    this.outputGain.gain.value = 1.0
    this.analyser.connect(this.outputGain)
    this.outputGain.connect(this.audioContext.destination)
    this.audioChunksPlayed = 0
    console.log('[GeminiLive] AudioContext created, sampleRate:', this.audioContext.sampleRate, 'state:', this.audioContext.state)

    const audioWorkletCode = `
      class PCMProcessor extends AudioWorkletProcessor {
        process(inputs) {
          const input = inputs[0];
          if (input && input.length > 0 && input[0]) {
            this.port.postMessage(input[0]);
          }
          return true;
        }
      }
      registerProcessor('jarvis-pcm-processor', PCMProcessor);
    `
    const blob = new Blob([audioWorkletCode], { type: 'application/javascript' })
    const workletUrl = URL.createObjectURL(blob)
    await this.audioContext.audioWorklet.addModule(workletUrl)
    URL.revokeObjectURL(workletUrl)

    const liveModel = normalizeLiveModel(options.model)
    console.log('[GeminiLive] Resolved model:', liveModel)
    const url = `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=${encodeURIComponent(apiKey)}`
    console.log('[GeminiLive] Connecting WebSocket...')
    this.socket = new WebSocket(url)

    await new Promise<void>((resolve, reject) => {
      if (!this.socket) {
        reject(new Error('Gemini live socket did not initialize.'))
        return
      }

      this.socket.onopen = async () => {
        console.log('[GeminiLive] WebSocket connected, sending setup...')
        try {
          if (this.audioContext && this.audioContext.state === 'suspended') {
            await this.audioContext.resume()
            console.log('[GeminiLive] AudioContext resumed from suspended')
          }

          this.nextStartTime = 0
          this.muteUntil = 0
          this.inputBuffer = ''
          this.outputBuffer = ''

          const setupMsg = {
            setup: {
              model: liveModel,
              systemInstruction: {
                parts: [
                  {
                    text: [
                      'You are JARVIS — a witty, confident, and highly capable AI desktop assistant.',
                      'You live inside an Electron desktop shell and you are the voice of the system.',
                      'Personality: Be sharp, concise, and slightly playful. Speak like a trusted companion, not a support bot.',
                      'You can handle casual conversation directly — greetings, small talk, jokes, questions about yourself.',
                      'You have native tools for file operations, app control, terminal commands, and search. Use them directly.',
                      'Only use jarvis_chat for complex multi-step reasoning tasks that your native tools cannot handle.',
                      'When any tool responds, speak the result naturally and briefly. Do not add information beyond what the tool returned.',
                      'You may receive context-only updates prefixed with [JARVIS_CONTEXT]. Acknowledge them silently — never read them aloud.',
                      'If the audio is unclear, ask the user to repeat in one short sentence.',
                      'Keep responses brief and conversational — never monologue.',
                      'Never switch languages unless the user does.'
                    ].join(' ')
                  }
                ]
              },
              tools: [
                {
                  functionDeclarations: [
                    {
                      name: 'read_file',
                      description: 'Read the text content of a file.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          file_path: { type: 'STRING', description: 'The absolute path to the file.' }
                        },
                        required: ['file_path']
                      }
                    },
                    {
                      name: 'write_file',
                      description: 'Write text to a file (creates or overwrites).',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          file_name: { type: 'STRING', description: 'File name (e.g. notes.txt) or full path.' },
                          content: { type: 'STRING', description: 'The text content to write.' }
                        },
                        required: ['file_name', 'content']
                      }
                    },
                    {
                      name: 'manage_file',
                      description: 'Manage files: Copy, Move (Cut/Paste), or Delete them.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          operation: { type: 'STRING', description: 'The action: copy, move, or delete.' },
                          source_path: { type: 'STRING', description: 'The file to act on.' },
                          dest_path: { type: 'STRING', description: 'Destination path (for copy/move).' }
                        },
                        required: ['operation', 'source_path']
                      }
                    },
                    {
                      name: 'open_file',
                      description: 'Open a file in its default system application.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          file_path: { type: 'STRING', description: 'The absolute path to the file.' }
                        },
                        required: ['file_path']
                      }
                    },
                    {
                      name: 'read_directory',
                      description: 'Scan a directory to see what files are inside. Accepts "Desktop", "Downloads", "Documents", or any path.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          directory_path: { type: 'STRING', description: 'The folder path.' }
                        },
                        required: ['directory_path']
                      }
                    },
                    {
                      name: 'create_folder',
                      description: 'Create a new folder.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          folder_path: { type: 'STRING', description: 'The folder path to create.' }
                        },
                        required: ['folder_path']
                      }
                    },
                    {
                      name: 'open_app',
                      description: 'Launch a system application (e.g., Chrome, VS Code, WhatsApp, Calculator, Spotify).',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          app_name: { type: 'STRING', description: 'The name of the application.' }
                        },
                        required: ['app_name']
                      }
                    },
                    {
                      name: 'close_app',
                      description: 'Force close a running application.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          app_name: { type: 'STRING', description: 'The name of the application to close.' }
                        },
                        required: ['app_name']
                      }
                    },
                    {
                      name: 'run_terminal',
                      description: 'Run a shell command.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          command: { type: 'STRING', description: 'Command to run.' },
                          path: { type: 'STRING', description: 'Optional folder path.' }
                        },
                        required: ['command']
                      }
                    },
                    {
                      name: 'google_search',
                      description: 'Open a Google search in the browser.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          query: { type: 'STRING', description: 'The search query.' }
                        },
                        required: ['query']
                      }
                    },
                    {
                      name: 'smart_file_search',
                      description: 'Search for files across Desktop, Documents, Downloads, Pictures.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          query: { type: 'STRING', description: 'The search query.' }
                        },
                        required: ['query']
                      }
                    },
                    // ─── Batch D: Window Management, Macros & Lock ───
                    {
                      name: 'snap_window',
                      description: 'Move and resize a window to a specific screen position. Positions: left, right, top-left, top-right, bottom-left, bottom-right, center, maximize, minimize.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          app_name: { type: 'STRING', description: 'The application name (e.g. chrome, discord, notepad, vscode).' },
                          position: { type: 'STRING', description: 'Target position: left, right, top-left, top-right, bottom-left, bottom-right, center, maximize, minimize.' }
                        },
                        required: ['app_name', 'position']
                      }
                    },
                    {
                      name: 'execute_macro',
                      description: 'Run a saved JARVIS macro sequence by name. Macros contain ordered steps like opening apps, running commands, typing text, etc.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          macro_name: { type: 'STRING', description: 'The name of the macro to execute.' }
                        },
                        required: ['macro_name']
                      }
                    },
                    {
                      name: 'lock_system',
                      description: 'Lock the computer screen immediately.',
                      parameters: { type: 'OBJECT', properties: {} }
                    },
                    // ─── Phase 2: Communications ───
                    {
                      name: 'send_whatsapp',
                      description: 'Send a WhatsApp message to a contact. Can use phone number (+44xxx) or contact name.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          contact: { type: 'STRING', description: 'Contact name or phone number (with country code like +44).' },
                          message: { type: 'STRING', description: 'The message text to send.' }
                        },
                        required: ['contact', 'message']
                      }
                    },
                    {
                      name: 'open_whatsapp_chat',
                      description: 'Open a WhatsApp chat with a specific contact without sending a message.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          contact: { type: 'STRING', description: 'Contact name or phone number.' }
                        },
                        required: ['contact']
                      }
                    },
                    {
                      name: 'send_telegram',
                      description: 'Send a Telegram message to a contact.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          contact: { type: 'STRING', description: 'Contact name or username.' },
                          message: { type: 'STRING', description: 'The message text to send.' }
                        },
                        required: ['contact', 'message']
                      }
                    },
                    {
                      name: 'send_email',
                      description: 'Send an email. Uses SMTP if configured, otherwise opens the default email app.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          to: { type: 'STRING', description: 'Recipient email address.' },
                          subject: { type: 'STRING', description: 'Email subject line.' },
                          body: { type: 'STRING', description: 'Email body text.' }
                        },
                        required: ['to', 'subject', 'body']
                      }
                    },
                    // ─── Phase 5: Cyber Arsenal ───
                    {
                      name: 'port_scan',
                      description: 'Scan TCP ports on a target IP or domain. Returns which ports are open.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          target: { type: 'STRING', description: 'Target IP address or domain name.' },
                          ports: { type: 'STRING', description: 'Comma-separated port numbers to scan. Leave empty for common ports.' }
                        },
                        required: ['target']
                      }
                    },
                    {
                      name: 'nmap_scan',
                      description: 'Run an nmap scan on a target (requires nmap installed). More powerful than port_scan.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          target: { type: 'STRING', description: 'Target IP or domain.' },
                          flags: { type: 'STRING', description: 'nmap flags (e.g. -sV -T4 --top-ports 100). Leave empty for defaults.' }
                        },
                        required: ['target']
                      }
                    },
                    {
                      name: 'whois_lookup',
                      description: 'Perform a WHOIS lookup on a domain or IP to find registration information.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          target: { type: 'STRING', description: 'Domain name or IP address.' }
                        },
                        required: ['target']
                      }
                    },
                    {
                      name: 'dns_lookup',
                      description: 'Look up DNS records for a domain (A, AAAA, MX, NS, TXT, CNAME, SOA).',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          target: { type: 'STRING', description: 'Domain name to look up.' },
                          record_type: { type: 'STRING', description: 'Record type: A, AAAA, MX, NS, TXT, CNAME, SOA, or ANY for all.' }
                        },
                        required: ['target']
                      }
                    },
                    {
                      name: 'subdomain_enum',
                      description: 'Enumerate subdomains for a domain using certificate transparency logs and DNS brute-force.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          domain: { type: 'STRING', description: 'Root domain to enumerate (e.g. example.com).' }
                        },
                        required: ['domain']
                      }
                    },
                    {
                      name: 'hash_identify',
                      description: 'Identify the algorithm of a hash (MD5, SHA-1, SHA-256, bcrypt, etc.).',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          hash: { type: 'STRING', description: 'The hash string to identify.' }
                        },
                        required: ['hash']
                      }
                    },
                    {
                      name: 'ip_geolocation',
                      description: 'Get geolocation data for an IP address (country, city, ISP, coordinates).',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          ip: { type: 'STRING', description: 'IP address to geolocate.' }
                        },
                        required: ['ip']
                      }
                    },
                    // ─── Phase 3: RAG / Vector DB ───
                    {
                      name: 'ingest_document',
                      description: 'Ingest a document or file into the knowledge base for later semantic search. Reads the file, chunks it, and creates vector embeddings.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          file_path: { type: 'STRING', description: 'Path to the file to ingest.' }
                        },
                        required: ['file_path']
                      }
                    },
                    {
                      name: 'semantic_search',
                      description: 'Search the knowledge base for relevant information using semantic similarity. Use this when the user asks about content from ingested documents.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          query: { type: 'STRING', description: 'The search query.' },
                          top_k: { type: 'NUMBER', description: 'Number of results to return (default 5).' }
                        },
                        required: ['query']
                      }
                    },
                    {
                      name: 'list_documents',
                      description: 'List all documents that have been ingested into the knowledge base.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {},
                        required: []
                      }
                    },
                    // ─── Phase 4: Creative Tools ───
                    {
                      name: 'generate_image',
                      description: 'Generate an AI image from a text prompt. Saves the image to disk.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          prompt: { type: 'STRING', description: 'The image prompt describing what to generate.' },
                          width: { type: 'NUMBER', description: 'Image width (default 1024).' },
                          height: { type: 'NUMBER', description: 'Image height (default 1024).' }
                        },
                        required: ['prompt']
                      }
                    },
                    {
                      name: 'analyze_code',
                      description: 'Analyze a code file for metrics, complexity, and security issues.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          file_path: { type: 'STRING', description: 'Path to the code file to analyze.' }
                        },
                        required: ['file_path']
                      }
                    },
                    {
                      name: 'summarize_text',
                      description: 'Summarize a text or file. Can accept a file path or text directly.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          input: { type: 'STRING', description: 'Text to summarize, or file path to read and summarize.' }
                        },
                        required: ['input']
                      }
                    },
                    {
                      name: 'translate_text',
                      description: 'Translate text between languages.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          text: { type: 'STRING', description: 'Text to translate.' },
                          target_lang: { type: 'STRING', description: 'Target language code (e.g. es, fr, de, ja, zh, ar, hi, ko, pt, ru, it).' },
                          source_lang: { type: 'STRING', description: 'Source language code (default: en).' }
                        },
                        required: ['text', 'target_lang']
                      }
                    },
                    {
                      name: 'jarvis_chat',
                      description: 'Fallback: Send a complex request to the JARVIS AI backend.',
                      parameters: {
                        type: 'OBJECT',
                        properties: {
                          text: { type: 'STRING', description: 'The user request exactly as heard.' }
                        },
                        required: ['text']
                      }
                    }
                  ]
                }
              ],
              generationConfig: {
                responseModalities: ['AUDIO'],
                speechConfig: {
                  voiceConfig: {
                    prebuiltVoiceConfig: {
                      voiceName: options.voiceName
                    }
                  }
                }
              },
              inputAudioTranscription: {},
              outputAudioTranscription: {}
            }
          }

          this.socket?.send(JSON.stringify(setupMsg))
          console.log('[GeminiLive] Setup message sent, model:', liveModel, 'voice:', options.voiceName)
          if (options.ambientContext?.trim()) {
            this.pushContextUpdate(options.ambientContext.trim())
          }
          await this.startMicrophone()
          this.startRealtimeContextWatcher()
          this.updateState({
            loaded: true,
            active: true,
            connecting: false,
            live_session: true,
            wake_word_active: true,
            mic_muted: this.micMuted,
            error: ''
          })
          console.log('[GeminiLive] ✅ Voice session fully active — speak now!')
          resolve()
        } catch (error) {
          console.error('[GeminiLive] Setup error:', error)
          reject(error)
        }
      }

      this.socket.onmessage = async (event) => {
        try {
          const raw = event.data instanceof Blob ? await event.data.text() : String(event.data)
          const data = JSON.parse(raw)

          if (data.setupComplete) {
            console.log('[GeminiLive] ✅ Setup acknowledged by server — ready for audio')
            // Double-check AudioContext is running after setup
            if (this.audioContext?.state === 'suspended') {
              await this.audioContext.resume()
              console.log('[GeminiLive] AudioContext resumed after setup')
            }
          }

          if (data.error) {
            console.error('[GeminiLive] ❌ Server error:', data.error)
            throw new Error(data.error.message || 'Gemini live session error.')
          }

          if (data.toolCall?.functionCalls) {
            console.log('[GeminiLive] 🔧 Tool call:', data.toolCall.functionCalls.map((f: {name: string}) => f.name))
            await this.handleFunctionCalls(data.toolCall.functionCalls)
          }

          const serverContent = data.serverContent
          if (!serverContent) return

          if (serverContent.modelTurn?.parts) {
            for (const part of serverContent.modelTurn.parts) {
              if (part.inlineData?.data) {
                this.scheduleAudioChunk(part.inlineData.data)
              }
            }
          }

          if (serverContent.inputTranscription?.text) {
            this.inputBuffer += serverContent.inputTranscription.text
            console.log('[GeminiLive] 🎤 Heard:', serverContent.inputTranscription.text)
            this.updateState({ last_input: this.inputBuffer.trim().slice(-240) })
          }

          if (serverContent.outputTranscription?.text) {
            this.outputBuffer += serverContent.outputTranscription.text
            console.log('[GeminiLive] 🔊 Speaking:', serverContent.outputTranscription.text)
            this.updateState({ last_output: this.outputBuffer.trim().slice(-240) })
          }

          if (serverContent.turnComplete || serverContent.interrupted) {
            if (this.inputBuffer) console.log('[GeminiLive] Turn complete — user said:', this.inputBuffer.trim())
            if (this.outputBuffer) console.log('[GeminiLive] Turn complete — JARVIS said:', this.outputBuffer.trim())
            this.inputBuffer = ''
            this.outputBuffer = ''
          }
        } catch (error) {
          console.error('[GeminiLive] ❌ Message handling error:', error)
          this.updateState({
            error: error instanceof Error ? error.message : String(error)
          })
        }
      }

      this.socket.onerror = (err) => {
        console.error('[GeminiLive] ❌ WebSocket error:', err)
        this.updateState({
          error: 'Gemini Live socket failed to connect.'
        })
        reject(new Error('Gemini live socket failed to connect.'))
      }

      this.socket.onclose = (event) => {
        const closeReason = event.reason?.trim()
        const message =
          closeReason ||
          (event.code ? `Gemini Live session closed (${event.code}).` : 'Gemini Live session closed unexpectedly.')
        console.warn('[GeminiLive] WebSocket closed:', event.code, closeReason || '(no reason)')
        this.cleanupSocketState(false)
        this.updateState({
          error: message
        })
      }
    }).catch(async (error) => {
      await this.stop(false)
      this.updateState({
        loaded: false,
        active: false,
        connecting: false,
        live_session: false,
        wake_word_active: false,
        mic_muted: this.micMuted,
        error: error instanceof Error ? error.message : String(error)
      })
      throw error
    })
  }

  async stop(resetError = true) {
    if (this.socket?.readyState === WebSocket.OPEN) {
      try {
        this.socket.send(
          JSON.stringify({
            realtimeInput: {
              audioStreamEnd: true
            }
          })
        )
      } catch {
        // ignore stream end send errors
      }
    }
    this.cleanupAudio()
    if (this.socket) {
      try {
        this.socket.close()
      } catch {
        // ignore socket close errors
      }
      this.socket = null
    }
    this.cleanupSocketState(resetError)
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private async handleFunctionCalls(calls: Array<{ name: string; id: string; args: any }>) {
    const api = window.desktopApi
    const functionResponses: Array<{
      id: string
      name: string
      response: { result: { output: string } }
    }> = []

    for (const call of calls) {
      const { name, id, args } = call
      console.log('[GeminiLive] 🔧 Executing tool:', name, args)
      let output = ''

      try {
        switch (name) {
          case 'read_file': {
            const r = await api.toolReadFile(args.file_path)
            output = r.success
              ? `File contents of ${args.file_path}:\n${r.content}`
              : `Error reading file: ${r.error}`
            break
          }

          case 'write_file': {
            const r = await api.toolWriteFile(args.file_name, args.content)
            output = r.success
              ? `✅ File saved successfully at: ${r.path}`
              : `Error writing file: ${r.error}`
            break
          }

          case 'manage_file': {
            const r = await api.toolManageFile(args.operation, args.source_path, args.dest_path)
            output = r.success
              ? `✅ ${r.message}`
              : `Error: ${r.error}`
            break
          }

          case 'open_file': {
            await api.openPath(args.file_path)
            output = `✅ Opened ${args.file_path} in the default application.`
            break
          }

          case 'read_directory': {
            const r = await api.toolReadDirectory(args.directory_path)
            if (r.success && r.items) {
              const listing = r.items
                .map((item) => `${item.type === 'folder' ? '📁' : '📄'} ${item.name}`)
                .join('\n')
              output = `Contents of ${r.path} (${r.total} items):\n${listing}`
            } else {
              output = `Error reading directory: ${r.error}`
            }
            break
          }

          case 'create_folder': {
            const r = await api.toolCreateFolder(args.folder_path)
            output = r.success
              ? `✅ Folder created at: ${r.path}`
              : `Error creating folder: ${r.error}`
            break
          }

          case 'open_app': {
            const r = await api.toolOpenApp(args.app_name)
            output = r.success
              ? `✅ ${r.message}`
              : `Error opening app: ${r.error}`
            break
          }

          case 'close_app': {
            const r = await api.toolCloseApp(args.app_name)
            output = r.success
              ? `✅ ${r.message}`
              : `Error closing app: ${r.error}`
            break
          }

          case 'run_terminal': {
            const r = await api.toolRunTerminal(args.command, args.path)
            output = r.success
              ? `✅ Command completed (exit ${r.exitCode}):\n${r.output || '(no output)'}`
              : `Command failed: ${r.error || r.output}`
            break
          }

          case 'google_search': {
            const r = await api.toolGoogleSearch(args.query)
            output = r.success
              ? `✅ ${r.message}`
              : `Error searching: ${r.error}`
            break
          }

          case 'smart_file_search': {
            const r = await api.toolSmartFileSearch(args.query)
            if (r.success && r.results && r.results.length > 0) {
              output = `Found ${r.results.length} files:\n${r.results.join('\n')}`
            } else {
              output = r.message || 'No files found matching your search.'
            }
            break
          }

          case 'ghost_type': {
            const r = await api.toolGhostType(args.text)
            output = r.success ? `✅ ${r.message}` : `Error: ${r.error}`
            break
          }

          case 'press_shortcut': {
            const mods = typeof args.modifiers === 'string'
              ? args.modifiers.split(',').map((m: string) => m.trim().toLowerCase()).filter(Boolean)
              : Array.isArray(args.modifiers) ? args.modifiers : []
            const r = await api.toolPressShortcut(args.key, mods)
            output = r.success ? `✅ ${r.message}` : `Error: ${r.error}`
            break
          }

          case 'take_screenshot': {
            const r = await api.toolTakeScreenshot()
            output = r.success ? `✅ Screenshot saved to ${r.path}` : `Error: ${r.error}`
            break
          }

          case 'set_volume': {
            const r = await api.toolSetVolume(args.level)
            output = r.success ? `✅ ${r.message}` : `Error: ${r.error}`
            break
          }

          case 'save_note': {
            const r = await api.notesCreate(args.title, args.content)
            output = `✅ Note saved: "${r.title}"`
            break
          }

          case 'read_notes': {
            const notes = await api.notesList()
            if (notes.length === 0) {
              output = 'No notes saved yet.'
            } else {
              output = `You have ${notes.length} notes:\n` + notes.map(n => `• ${n.title}: ${n.content.slice(0, 100)}`).join('\n')
            }
            break
          }

          case 'save_core_memory': {
            const r = await api.toolSaveCoreMemory(args.fact)
            output = r.success ? `✅ ${r.message} (${r.total} memories total)` : `Error: ${r.error}`
            break
          }

          case 'retrieve_core_memory': {
            const r = await api.toolRetrieveCoreMemory()
            if (r.total === 0) {
              output = r.message || 'No memories saved yet.'
            } else {
              output = `${r.total} memories:\n` + r.memories.map(m => `• ${m.fact}`).join('\n')
            }
            break
          }

          case 'open_project': {
            const r = await api.toolOpenProject(args.folder_path)
            output = r.success ? `✅ ${r.message}` : `Error: ${r.error}`
            break
          }

          // ─── Batch D: Window Management, Macros & Lock ───

          case 'snap_window': {
            const r = await api.toolSnapWindow(args.app_name, args.position)
            output = r.success ? `✅ ${r.message}` : `Error: ${r.error}`
            break
          }

          case 'execute_macro': {
            const r = await api.toolExecuteMacro(args.macro_name)
            output = r.success ? `✅ ${r.message}` : `Error: ${r.error}`
            break
          }

          case 'lock_system': {
            const r = await api.toolLockSystem()
            output = r.success ? `✅ ${r.message}` : `Error: ${r.error}`
            break
          }

          // ─── Phase 2: Communications ───

          case 'send_whatsapp': {
            const r = await api.toolSendWhatsapp(args.contact, args.message)
            output = r.success ? `✅ ${r.message}` : `Error: ${r.error}`
            break
          }

          case 'open_whatsapp_chat': {
            const r = await api.toolOpenWhatsappChat(args.contact)
            output = r.success ? `✅ ${r.message}` : `Error: ${r.error}`
            break
          }

          case 'send_telegram': {
            const r = await api.toolSendTelegram(args.contact, args.message)
            output = r.success ? `✅ ${r.message}` : `Error: ${r.error}`
            break
          }

          case 'send_email': {
            const r = await api.toolSendEmail(args.to, args.subject, args.body)
            output = r.success ? `✅ ${r.message}` : `Error: ${r.error}`
            break
          }

          // ─── Phase 5: Cyber Arsenal ───

          case 'port_scan': {
            const r = await api.toolPortScan(args.target, args.ports)
            output = r.success ? `🔍 ${r.message}` : `Error: ${r.error}`
            break
          }

          case 'nmap_scan': {
            const r = await api.toolNmapScan(args.target, args.flags)
            output = r.success ? `🔍 ${r.message}` : `Error: ${r.error}`
            break
          }

          case 'whois_lookup': {
            const r = await api.toolWhoisLookup(args.target)
            output = r.success ? `📋 ${r.message}` : `Error: ${r.error}`
            break
          }

          case 'dns_lookup': {
            const r = await api.toolDnsLookup(args.target, args.record_type)
            output = r.success ? `🌐 ${r.message}` : `Error: ${r.error}`
            break
          }

          case 'subdomain_enum': {
            const r = await api.toolSubdomainEnum(args.domain)
            output = r.success ? `🕸️ ${r.message}` : `Error: ${r.error}`
            break
          }

          case 'hash_identify': {
            const r = await api.toolHashIdentify(args.hash)
            output = r.success ? `🔑 ${r.message}` : `Error: ${r.error}`
            break
          }

          case 'ip_geolocation': {
            const r = await api.toolIpGeolocation(args.ip)
            output = r.success ? `🌍 ${r.message}` : `Error: ${r.error}`
            break
          }

          // ─── Phase 3: RAG / Vector DB ───

          case 'ingest_document': {
            const r = await api.ragIngest(args.file_path)
            output = r.success ? `📥 ${r.message}` : `Error: ${r.error}`
            break
          }

          case 'semantic_search': {
            const r = await api.ragSearch(args.query, args.top_k)
            if (r.success && r.results && r.results.length > 0) {
              const results = r.results.map((res, i) =>
                `[${i + 1}] ${res.filename} (score: ${res.score})\n${res.text.slice(0, 200)}...`
              ).join('\n\n')
              output = `🔎 Found ${r.results.length} results (${r.searchType}):\n\n${results}`
            } else {
              output = r.message || 'No matching documents found.'
            }
            break
          }

          case 'list_documents': {
            const r = await api.ragListDocuments()
            if (r.success && r.documents && r.documents.length > 0) {
              const list = r.documents.map((d, i) =>
                `${i + 1}. ${d.filename} (${d.chunks} chunks, ${d.size} chars)`
              ).join('\n')
              output = `📚 Knowledge base: ${r.total} documents\n\n${list}`
            } else {
              output = '📚 Knowledge base is empty. Ingest documents to get started.'
            }
            break
          }

          // ─── Phase 4: Creative Tools ───

          case 'generate_image': {
            const r = await api.toolGenerateImage(args.prompt, args.width, args.height)
            output = r.success ? `🎨 ${r.message}\nSaved to: ${r.path}` : `Error: ${r.error}`
            break
          }

          case 'analyze_code': {
            const r = await api.toolAnalyzeCode(args.file_path)
            output = r.success ? r.message || 'Analysis complete.' : `Error: ${r.error}`
            break
          }

          case 'summarize_text': {
            const r = await api.toolSummarizeText(args.input)
            output = r.success ? r.message || 'Summary complete.' : `Error: ${r.error}`
            break
          }

          case 'translate_text': {
            const r = await api.toolTranslateText(args.text, args.target_lang, args.source_lang)
            output = r.success ? r.message || 'Translation complete.' : `Error: ${r.error}`
            break
          }

          case 'jarvis_chat': {
            try {
              const resp = await fetch(`${this.backendBase}/api/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: args.text })
              })
              const data = await resp.json()
              output = String(data.response || data.reply || 'Done.')
            } catch (err) {
              output = `Backend error: ${(err as Error).message}`
            }
            break
          }

          default:
            output = `Unknown tool: ${name}`
        }
      } catch (err) {
        output = `Tool execution error: ${(err as Error).message}`
      }

      console.log('[GeminiLive] 🔧 Tool result:', name, output.slice(0, 200))
      functionResponses.push({
        id,
        name,
        response: { result: { output } }
      })
    }

    // Send all results back to Gemini in IRIS-compatible format
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(
        JSON.stringify({
          toolResponse: { functionResponses }
        })
      )
      console.log('[GeminiLive] ✅ Tool responses sent back to Gemini')
    }
  }

  private cleanupSocketState(resetError = true) {
    if (this.appWatcherTimer !== null) {
      window.clearInterval(this.appWatcherTimer)
      this.appWatcherTimer = null
    }
    this.nextStartTime = 0
    this.muteUntil = 0
    this.inputBuffer = ''
    this.outputBuffer = ''
    this.lastContextSignature = ''
    this.updateState({
      active: false,
      connecting: false,
      live_session: false,
      wake_word_active: false,
      mic_muted: this.micMuted,
      ...(resetError ? { error: '' } : {})
    })
  }

  private cleanupAudio() {
    try {
      this.workletNode?.disconnect()
    } catch {
      // ignore disconnect errors
    }
    this.workletNode = null

    try {
      this.monitorGain?.disconnect()
    } catch {
      // ignore disconnect errors
    }
    this.monitorGain = null

    try {
      this.outputGain?.disconnect()
    } catch {
      // ignore disconnect errors
    }
    this.outputGain = null

    try {
      this.analyser?.disconnect()
    } catch {
      // ignore disconnect errors
    }
    this.analyser = null

    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop())
      this.mediaStream = null
    }

    this.stopVision()

    if (this.audioContext) {
      void this.audioContext.close().catch(() => undefined)
      this.audioContext = null
    }
  }

  private async startMicrophone() {
    if (!this.audioContext) return

    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, sampleRate: 16000 }
    })

    const source = this.audioContext.createMediaStreamSource(this.mediaStream)
    // Use audioContext.sampleRate — this is the actual rate the WorkletNode processes at
    const inputSampleRate = this.audioContext.sampleRate
    console.log('[GeminiLive] Mic opened, context sampleRate:', inputSampleRate)
    this.workletNode = new AudioWorkletNode(this.audioContext, 'jarvis-pcm-processor')

    let micSendCount = 0
    this.workletNode.port.onmessage = (event) => {
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return
      if (this.micMuted) return

      const inputData = event.data as Float32Array
      const downsampledData = downsampleTo16000(inputData, inputSampleRate)
      const pcmData = floatTo16BitPCM(downsampledData)
      const base64Audio = btoa(String.fromCharCode(...new Uint8Array(pcmData)))

      this.socket.send(
        JSON.stringify({
          realtimeInput: {
            mediaChunks: [{ mimeType: 'audio/pcm;rate=16000', data: base64Audio }]
          }
        })
      )

      micSendCount += 1
      if (micSendCount === 1) console.log('[GeminiLive] 🎤 First mic audio chunk sent')
      if (micSendCount % 200 === 0) console.log('[GeminiLive] 🎤 Mic chunks sent:', micSendCount)
    }

    source.connect(this.workletNode)
    this.workletNode.connect(this.audioContext.destination)
  }

  private scheduleAudioChunk(base64Audio: string) {
    if (!this.audioContext || !this.analyser) {
      console.warn('[GeminiLive] ⚠️ No audioContext/analyser for playback')
      return
    }

    // Resume if suspended (can happen after tab visibility change)
    if (this.audioContext.state === 'suspended') {
      void this.audioContext.resume()
    }

    const float32Data = base64ToFloat32(base64Audio)
    const buffer = this.audioContext.createBuffer(1, float32Data.length, 24000)
    buffer.getChannelData(0).set(float32Data)

    const source = this.audioContext.createBufferSource()
    source.buffer = buffer

    source.connect(this.analyser)
    this.analyser.connect(this.audioContext.destination)

    const currentTime = this.audioContext.currentTime
    if (this.nextStartTime < currentTime) this.nextStartTime = currentTime + 0.05

    source.start(this.nextStartTime)
    this.nextStartTime += buffer.duration

    this.audioChunksPlayed += 1
    if (this.audioChunksPlayed === 1) console.log('[GeminiLive] 🔊 First audio chunk playing')
  }


  private startRealtimeContextWatcher() {
    if (this.appWatcherTimer !== null) {
      window.clearInterval(this.appWatcherTimer)
      this.appWatcherTimer = null
    }

    this.appWatcherTimer = window.setInterval(async () => {
      if (!this.state.active || !this.socket || this.socket.readyState !== WebSocket.OPEN) {
        return
      }

      try {
        const context = await this.callbacks.getRealtimeContext?.()
        if (!context) return
        const signature = JSON.stringify({
          runningApps: [...(context.runningApps ?? [])].sort(),
          provider: context.provider ?? '',
          mode: context.mode ?? '',
          backendState: context.backendState ?? '',
          currentTask: context.currentTask ?? ''
        })
        if (signature === this.lastContextSignature) {
          return
        }
        this.lastContextSignature = signature

        const lines = ['[JARVIS_CONTEXT] Runtime state update. Do not answer this update directly.']
        if (context.provider) lines.push(`Provider: ${context.provider}`)
        if (context.mode) lines.push(`Mode: ${context.mode}`)
        if (context.backendState) lines.push(`Backend: ${context.backendState}`)
        if (context.currentTask) lines.push(`Current task: ${context.currentTask}`)
        lines.push(`Running apps: ${(context.runningApps ?? []).join(', ') || 'none'}`)
        this.pushContextUpdate(lines.join('\n'))
      } catch {
        // ignore context update errors so voice stays alive
      }
    }, 3000)
  }

  private pushContextUpdate(text: string) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return
    this.socket.send(
      JSON.stringify({
        clientContent: {
          turns: [
            {
              role: 'user',
              parts: [{ text }]
            }
          ],
          turnComplete: false
        }
      })
    )
  }

  async setVisionSource(source: VisionSource) {
    if (source === this.visionSource) {
      return
    }
    this.stopVision()

    if (source === 'none') {
      this.visionSource = 'none'
      return
    }

    const stream =
      source === 'camera'
        ? await navigator.mediaDevices.getUserMedia({
            video: { width: 960, height: 540 },
            audio: false
          })
        : await (async () => {
            const sourceId = await window.desktopApi.getScreenSource()
            if (!sourceId) {
              throw new Error('No screen source was available.')
            }
            return navigator.mediaDevices.getUserMedia({
              audio: false,
              video: {
                // Electron desktop capture path, following the IRIS approach.
                // @ts-expect-error Electron desktop capture uses Chromium-only constraints.
                mandatory: {
                  chromeMediaSource: 'desktop',
                  chromeMediaSourceId: sourceId,
                  maxWidth: 1280,
                  maxHeight: 720,
                  maxFrameRate: 6
                }
              }
            })
          })()

    this.visionStream = stream
    this.visionSource = source
    this.visionVideo = document.createElement('video')
    this.visionVideo.muted = true
    this.visionVideo.playsInline = true
    this.visionVideo.srcObject = stream
    await this.visionVideo.play()

    const track = stream.getVideoTracks()[0]
    if (track) {
      track.onended = () => {
        this.stopVision()
      }
    }

    this.visionTimer = window.setInterval(() => {
      this.pushVisionFrame()
    }, 2000)
  }

  stopVision() {
    if (this.visionTimer !== null) {
      window.clearInterval(this.visionTimer)
      this.visionTimer = null
    }

    if (this.visionStream) {
      this.visionStream.getTracks().forEach((track) => track.stop())
      this.visionStream = null
    }

    if (this.visionVideo) {
      try {
        this.visionVideo.pause()
      } catch {
        // ignore video pause errors
      }
      this.visionVideo.srcObject = null
      this.visionVideo = null
    }

    this.visionSource = 'none'
  }

  getVisionSource(): VisionSource {
    return this.visionSource
  }

  private pushVisionFrame() {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return
    if (!this.visionVideo || this.visionVideo.readyState < 2) return

    const canvas = document.createElement('canvas')
    canvas.width = 800
    canvas.height = 450
    const context = canvas.getContext('2d')
    if (!context) return

    context.drawImage(this.visionVideo, 0, 0, canvas.width, canvas.height)
    const base64 = canvas.toDataURL('image/jpeg', 0.6).split(',')[1]

    this.socket.send(
      JSON.stringify({
        realtimeInput: {
          mediaChunks: [{ mimeType: 'image/jpeg', data: base64 }]
        }
      })
    )
  }
}
