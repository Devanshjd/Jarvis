"""
J.A.R.V.I.S — Voice Plugin
Text-to-Speech and Speech-to-Text capabilities.

Features:
    - TTS: JARVIS speaks responses aloud (pyttsx3)
    - STT: Microphone input transcribed to text (SpeechRecognition)
    - Wake word: Say "JARVIS" to activate listening
    - Push-to-talk: Click mic button for one-shot listening
"""

import threading
import queue
import re
import os
import time
import tempfile
import json
import collections
import logging

from core.plugin_manager import PluginBase

try:
    import urllib.request
    import urllib.error
    HAS_URLLIB = True
except Exception:
    HAS_URLLIB = False

try:
    import pyttsx3
    HAS_TTS = True
except ImportError:
    HAS_TTS = False

try:
    import speech_recognition as sr
    HAS_STT = True
except ImportError:
    HAS_STT = False

# Whisper — much better accent handling, works offline
try:
    import whisper as _whisper_module
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False


class VoicePlugin(PluginBase):
    name = "voice"
    description = "Voice input/output — TTS and STT for JARVIS"
    version = "2.0"

    def __init__(self, jarvis):
        super().__init__(jarvis)
        self.recognizer = None
        self.is_enabled = False
        self.is_listening = False
        self.wake_word_active = False
        self._wake_thread = None
        self._tts_queue = queue.Queue()
        self._tts_thread = None
        self._stop_event = threading.Event()
        self._tts_ready = threading.Event()
        self.is_speaking = False       # True while TTS is actively outputting
        self._tts_done_time = 0.0      # timestamp when TTS last finished
        self._last_spoken_text = ""    # what JARVIS last said (for echo filtering)
        self._echo_cooldown = 6.0      # seconds to wait after TTS before listening (was 3.0 — still caught echoes)
        self._mic_locked = False       # Hard lock — mic completely off during TTS
        self._last_processed_text = ""   # last command sent to JARVIS (dedup)
        self._last_processed_time = 0.0  # timestamp of last processed command
        self._recent_spoken = collections.deque(maxlen=10)  # bank of recent TTS phrases for echo detection

        # ── Conversational listening state ──
        self._conversation_active = False   # True = JARVIS is in active conversation
        self._conversation_expires = 0.0    # timestamp when conversation window closes
        self._conversation_timeout = 30.0   # seconds of silence before conversation ends
        self._last_interaction_time = 0.0   # last time user spoke to JARVIS
        self._confirmation_active = False   # True while yes/no confirmation owns the mic
        self._stt_lock = threading.Lock()   # serialize microphone/STT usage
        self._stt_owner = ""
        self._voice_engine_mode = "classic"
        self._gemini_voice = None
        self._logger = logging.getLogger("jarvis.voice")

    def activate(self):
        """Initialize STT and start TTS worker thread."""
        voice_cfg = self.jarvis.config.get("voice", {})
        self._voice_engine_mode = str(voice_cfg.get("engine", "classic")).lower().strip()

        # TTS — must init AND run in the SAME thread (Windows COM requirement)
        if HAS_TTS and not self._prefers_gemini_live():
            self._stop_event.clear()
            self._tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
            self._tts_thread.start()
            # Wait for engine to be ready
            self._tts_ready.wait(timeout=5)

        # STT setup
        if HAS_STT and not self._prefers_gemini_live():
            try:
                self.recognizer = sr.Recognizer()
                self.recognizer.energy_threshold = 300
                self.recognizer.dynamic_energy_threshold = True
                self.recognizer.pause_threshold = 1.2       # wait 1.2s of silence before finalizing (was 0.8 — cut sentences short)
                self.recognizer.phrase_threshold = 0.3       # minimum speech length to consider
                self.recognizer.non_speaking_duration = 0.8  # silence padding around phrases
            except Exception as e:
                print(f"STT init error: {e}")
                self.recognizer = None

        # Whisper model — load in background for better accent recognition
        self._whisper_model = None
        self._stt_engine = voice_cfg.get("stt_engine", "auto")
        if not self._prefers_gemini_live() and HAS_WHISPER and self._stt_engine in ("whisper", "auto"):
            def _load_whisper():
                try:
                    # "base" model = good accuracy, ~150MB, runs on CPU
                    # "small" = better accuracy, ~500MB
                    model_size = self.jarvis.config.get("voice", {}).get("whisper_model", "base")
                    print(f"[JARVIS] Loading Whisper {model_size} model...")
                    self._whisper_model = _whisper_module.load_model(model_size)
                    print(f"[JARVIS] Whisper {model_size} model ready — enhanced voice recognition active")
                except Exception as e:
                    print(f"[JARVIS] Whisper load failed (falling back to Google STT): {e}")
                    self._whisper_model = None
            threading.Thread(target=_load_whisper, daemon=True, name="whisper-load").start()

        # ── Gemini real-time voice (optional upgrade) ──
        if self._prefers_gemini_live():
            try:
                from plugins.voice.gemini_voice import create_gemini_voice
                self._gemini_voice = create_gemini_voice(self.jarvis)
                if self._gemini_voice:
                    self._gemini_voice.on_transcript = self._on_gemini_transcript
                    self._gemini_voice.on_response = self._on_gemini_response
                    self._gemini_voice.on_state_change = self._on_gemini_state
                    print("[JARVIS] Gemini Live voice engine ready")
            except Exception as e:
                print(f"[JARVIS] Gemini voice init failed (using classic): {e}")
                self._gemini_voice = None
                self._voice_engine_mode = "classic"

        # Auto-start wake word listening on boot
        auto_wake = self.jarvis.config.get("voice", {}).get("auto_wake", True)
        if self._prefers_gemini_live():
            if auto_wake and self._gemini_voice:
                try:
                    self.is_enabled = bool(self._gemini_voice.start())
                    if hasattr(self.jarvis, "voice_enabled"):
                        self.jarvis.voice_enabled = self.is_enabled
                    if self.is_enabled:
                        print("[JARVIS] Gemini Live session active")
                except Exception as exc:
                    print(f"[JARVIS] Gemini Live auto-start failed: {exc}")
                    self.is_enabled = False
        elif auto_wake and HAS_STT and self.recognizer:
            self._start_wake_word()
            print("[JARVIS] Wake word listening active — say 'JARVIS' anytime")

    def uses_gemini_live(self) -> bool:
        return self._voice_engine_mode == "gemini" and self._gemini_voice is not None

    def _prefers_gemini_live(self) -> bool:
        return self._voice_engine_mode == "gemini"

    def _transcribe(self, audio) -> str:
        """
        Transcribe audio using the best available STT engine.
        Priority: Whisper (offline, great accents) → Google STT (online fallback).
        """
        # Try Whisper first — handles accents, noisy environments, any speaker
        if self._whisper_model is not None:
            try:
                import tempfile
                import wave
                import io

                # Convert audio to WAV for Whisper
                wav_data = audio.get_wav_data()
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp.write(wav_data)
                    tmp_path = tmp.name

                result = self._whisper_model.transcribe(
                    tmp_path,
                    language="en",       # force English for speed
                    fp16=False,          # CPU compatibility
                )
                text = result.get("text", "").strip()

                # Clean up temp file
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

                if text:
                    return text
            except Exception as e:
                print(f"[JARVIS] Whisper transcribe failed, falling back to Google: {e}")

        # Fallback: Google STT (free, online)
        try:
            text = self.recognizer.recognize_google(audio)
            return text.strip() if text else ""
        except sr.UnknownValueError:
            raise  # let caller handle
        except sr.RequestError as e:
            raise  # let caller handle

    def deactivate(self):
        """Clean up voice resources."""
        self._stop_event.set()
        self.is_enabled = False
        self.wake_word_active = False
        # Send poison pill to unblock the TTS queue
        self._tts_queue.put(None)

    def verbal_confirm(self, question: str, timeout: int = 8) -> bool:
        """
        Ask a yes/no question verbally and listen for the answer.
        Returns True if user says yes, False otherwise.
        Used instead of GUI popups when voice is active.

        Example:
            if voice.verbal_confirm("Send 'I am coming' to Meet on WhatsApp?"):
                # proceed
        """
        if self.uses_gemini_live():
            # Gemini Live should already have asked for confirmation before the
            # tool call. Avoid re-entering a nested mic/session confirmation.
            self._logger.info("Trusting Gemini Live conversational confirmation for: %s", question)
            return True

        previous_conversation = self._conversation_active
        previous_expiry = self._conversation_expires
        self._confirmation_active = True
        self._conversation_active = False

        try:
            self.speak(question)

            while self.is_speaking or self._mic_locked:
                time.sleep(0.2)

            elapsed = time.time() - self._tts_done_time if self._tts_done_time else 999
            remaining = self._echo_cooldown - elapsed
            if remaining > 0:
                time.sleep(remaining)

            if not HAS_STT or not self.recognizer:
                return True

            text = self._listen_for_text(
                owner="confirmation",
                timeout=timeout,
                phrase_time_limit=5,
                ambient_duration=0.3,
                wait_for_slot=True,
                slot_timeout=3.0,
                prompt="[JARVIS] Listening for confirmation...",
            ).lower().strip()
            print(f"[JARVIS] Confirmation response: '{text}'")

            yes_patterns = [
                "yes", "yeah", "yep", "yup", "sure", "go ahead", "do it",
                "send it", "send him the text", "send her the text", "send the text",
                "proceed", "confirm", "okay", "ok", "affirmative",
                "absolutely", "please", "go for it", "right", "correct",
                "that's right", "uh huh", "mm hmm", "yes sir", "yes please",
            ]
            no_patterns = [
                "no", "nah", "nope", "don't", "stop", "cancel", "abort",
                "never mind", "wait", "hold on", "negative", "not yet",
                "don't send", "do not send", "not him", "not her",
            ]

            for phrase in yes_patterns:
                if phrase in text:
                    return True
            for phrase in no_patterns:
                if phrase in text:
                    return False

            print(f"[JARVIS] Unclear response '{text}' - defaulting to no")
            self.speak("I didn't catch a clear yes or no. Cancelling for safety.")
            return False

        except sr.WaitTimeoutError:
            print("[JARVIS] No response heard - cancelling")
            self.speak("No response heard. Cancelling.")
            return False
        except sr.UnknownValueError:
            print("[JARVIS] Couldn't understand confirmation - cancelling")
            self.speak("Couldn't understand. Cancelling for safety.")
            return False
        except Exception as e:
            print(f"[JARVIS] Confirmation error: {e}")
            return False
        finally:
            self._confirmation_active = False
            if previous_conversation:
                self._conversation_active = True
                self._conversation_expires = max(
                    previous_expiry,
                    time.time() + self._conversation_timeout,
                )

    def _update_orb(self, speaking: bool):
        """Update the JARVIS core to reflect speaking state + lock/unlock mic."""
        # ── Hard mic lock: mic is DEAF while JARVIS speaks ──
        if speaking:
            self._mic_locked = True
        else:
            # Keep locked for the cooldown period — _wake_word_loop checks elapsed time
            self._mic_locked = False

        try:
            if hasattr(self.jarvis, 'main_core'):
                self.jarvis.root.after(0, lambda s=speaking: self.jarvis.main_core.set_speaking(s))
            if hasattr(self.jarvis, 'arc') and hasattr(self.jarvis.arc, 'set_speaking'):
                self.jarvis.root.after(0, lambda s=speaking: self.jarvis.arc.set_speaking(s))
            # GPU 3D core (runs in its own thread — no root.after needed)
            core3d = getattr(self.jarvis, 'core_3d', None)
            if core3d:
                core3d.set_speaking(speaking)
        except Exception:
            pass  # UI may not be ready yet

    # ═══════════════════════════════════════════════════════
    # Gemini Real-Time Voice Callbacks
    # ═══════════════════════════════════════════════════════

    def _on_gemini_transcript(self, text: str, is_final: bool):
        """Called when Gemini transcribes user speech."""
        clean = (text or "").strip()
        if not clean:
            return

        if is_final:
            print(f"[JARVIS Gemini] Heard: '{clean}'")
            try:
                if hasattr(self.jarvis, "brain"):
                    self.jarvis.brain.add_user_message(clean)
                self.jarvis.root.after(0, lambda: self.jarvis.chat.add_message("voice", f'Heard: "{clean}"'))
                core3d = getattr(self.jarvis, "core_3d", None)
                if core3d:
                    core3d.add_chat("voice", f'"{clean}"')
            except Exception:
                pass

    def _on_gemini_response(self, text: str):
        """Called when Gemini generates a response."""
        clean = (text or "").strip()
        if not clean:
            return

        print(f"[JARVIS Gemini] Response: {clean[:80]}...")
        try:
            if hasattr(self.jarvis, "brain"):
                latest = self.jarvis.brain.history[-1] if self.jarvis.brain.history else {}
                if latest.get("role") != "assistant" or latest.get("content") != clean:
                    self.jarvis.brain.add_assistant_message(clean)
                    self.jarvis.brain.msg_count += 1

            self.jarvis.root.after(0, lambda: self.jarvis.chat.add_message("assistant", clean))
            core3d = getattr(self.jarvis, "core_3d", None)
            if core3d:
                core3d.add_chat("assistant", clean)

            try:
                self.jarvis.mem.session.add_assistant(clean)
            except Exception:
                pass

            try:
                self.jarvis._update_stats()
            except Exception:
                pass
        except Exception:
            pass

    def _on_gemini_state(self, state: str):
        """Called when Gemini voice state changes."""
        try:
            core3d = getattr(self.jarvis, 'core_3d', None)
            if core3d:
                core3d.set_mode(state)
            if hasattr(self.jarvis, 'main_core'):
                self.jarvis.root.after(0, lambda:
                    self.jarvis.main_core.set_mode(state))
        except Exception:
            pass

    def enable(self):
        """Enable voice — TTS on responses, start wake word."""
        if self.uses_gemini_live():
            ok = self._gemini_voice.start()
            self.is_enabled = bool(ok)
            return bool(ok)
        self.is_enabled = True
        self.speak("Voice systems online, sir.")
        if not self.wake_word_active:
            self._start_wake_word()
        return True

    def disable(self):
        """Disable voice."""
        if self.uses_gemini_live():
            self.is_enabled = False
            self.wake_word_active = False
            if self._gemini_voice:
                self._gemini_voice.stop()
            return
        self.is_enabled = False
        self.wake_word_active = False
        self.speak("Voice systems offline.")

    # ══════════════════════════════════════════════════════════════
    # TEXT-TO-SPEECH (all pyttsx3 calls in ONE thread)
    # ══════════════════════════════════════════════════════════════

    def speak(self, text: str):
        """Queue text to be spoken. Selects best available TTS engine."""
        voice_cfg = self.jarvis.config.get("voice", {})
        engine = str(voice_cfg.get("tts_engine", "auto")).lower().strip()
        if self.uses_gemini_live() and self._gemini_voice:
            clean = self._clean_for_speech(text)
            if clean:
                self._gemini_voice.speak_text(clean)
            return
        if engine == "auto" and os.name == "nt":
            # On this Windows desktop build, the Edge/pygame playback path has
            # been the strongest candidate for hard process exits. Prefer the
            # more stable pyttsx3 worker unless the user explicitly selects a
            # different engine.
            engine = "pyttsx3"

        clean = self._clean_for_speech(text)
        if not clean:
            return

        # Track what JARVIS says for echo detection
        self._last_spoken_text = clean.lower().strip()
        self._recent_spoken.append((self._last_spoken_text, time.time()))

        # Engine priority: elevenlabs > edge-tts > pyttsx3
        if engine == "elevenlabs":
            threading.Thread(target=self._speak_elevenlabs, args=(clean,), daemon=True).start()
            return

        if engine in ("edge", "edge-tts", "auto"):
            # Try edge-tts first (free neural voices, sounds human)
            try:
                import edge_tts as _et  # noqa: F401
                threading.Thread(target=self._speak_edge_tts, args=(clean,), daemon=True).start()
                return
            except ImportError:
                if engine != "auto":
                    print("[DEBUG] edge-tts not installed. pip install edge-tts")

        # Fallback: pyttsx3
        if not HAS_TTS:
            print("[DEBUG] No TTS engine available")
            return
        print(f"[DEBUG] Queuing TTS (pyttsx3): {clean[:60]}...")
        self._tts_queue.put(clean)

    def _tts_worker(self):
        """
        Background thread that owns the pyttsx3 engine.
        Creates a FRESH engine for each utterance to avoid Windows COM issues.
        """
        import pythoncom
        pythoncom.CoInitialize()

        voice_config = self.jarvis.config.get("voice", {})
        rate = voice_config.get("tts_rate", 175)

        # Find preferred voice ID once
        try:
            test_engine = pyttsx3.init()
            voices = test_engine.getProperty("voices")
            preferred = ["david", "james", "daniel", "george", "british", "male"]
            self._voice_id = None
            for voice in voices:
                for kw in preferred:
                    if kw in voice.name.lower():
                        self._voice_id = voice.id
                        print(f"JARVIS voice: {voice.name}")
                        break
                if self._voice_id:
                    break
            if not self._voice_id and voices:
                self._voice_id = voices[0].id
            test_engine.stop()
            del test_engine
        except Exception as e:
            print(f"TTS voice detection error: {e}")
            self._voice_id = None

        self._tts_ready.set()

        # Process queue — fresh engine per utterance
        while not self._stop_event.is_set():
            try:
                text = self._tts_queue.get(timeout=0.5)
                if text is None:
                    break
                print(f"[DEBUG] TTS worker speaking: {text[:50]}...")
                self.is_speaking = True
                self._update_orb(True)
                try:
                    engine = pyttsx3.init()
                    engine.setProperty("rate", rate)
                    engine.setProperty("volume", 0.9)
                    if self._voice_id:
                        engine.setProperty("voice", self._voice_id)
                    engine.say(text)
                    engine.runAndWait()
                    engine.stop()
                    del engine
                except Exception as e:
                    print(f"TTS speak error: {e}")
                finally:
                    self.is_speaking = False
                    self._update_orb(False)
                    import time as _t
                    self._tts_done_time = _t.time()
            except queue.Empty:
                continue

        pythoncom.CoUninitialize()

    def _speak_edge_tts(self, text: str):
        """Speak text using Microsoft Edge neural TTS (free, human-quality)."""
        import asyncio
        import edge_tts

        voice_cfg = self.jarvis.config.get("voice", {})
        # Good male voices: en-GB-RyanNeural (British), en-US-GuyNeural,
        # en-US-AndrewNeural, en-GB-ThomasNeural
        voice = voice_cfg.get("edge_voice", "en-GB-RyanNeural")
        rate = voice_cfg.get("edge_rate", "+0%")  # e.g. "+10%", "-5%"

        self.is_speaking = True
        self._update_orb(True)
        tmp_path = None
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp_path = tmp.name
            tmp.close()

            async def _generate():
                communicate = edge_tts.Communicate(text, voice, rate=rate)
                await communicate.save(tmp_path)

            # Run async in a new event loop (we're in a thread)
            loop = asyncio.new_event_loop()
            loop.run_until_complete(_generate())
            loop.close()

            # Play the audio
            self._play_audio_file(tmp_path)

        except Exception as e:
            print(f"[DEBUG] Edge TTS error: {e}")
            # Fallback to pyttsx3 if edge-tts fails
            if HAS_TTS:
                self._tts_queue.put(text)
        finally:
            self.is_speaking = False
            self._update_orb(False)
            self._tts_done_time = time.time()
            # Clean up temp file
            if tmp_path:
                try:
                    time.sleep(0.5)
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _play_audio_file(self, filepath: str):
        """Play an audio file (mp3/wav). Tries pygame, then PowerShell."""
        try:
            import os as _os
            _os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=24000)
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
            pygame.mixer.music.unload()
            return
        except Exception as e:
            print(f"[DEBUG] pygame playback failed: {e}")

        # Fallback: PowerShell MediaPlayer (less reliable but works without pygame)
        try:
            import subprocess
            # Escape backslashes for PowerShell
            safe_path = filepath.replace("\\", "\\\\")
            ps_cmd = (
                f'Add-Type -AssemblyName presentationCore; '
                f'$player = New-Object System.Windows.Media.MediaPlayer; '
                f'$player.Open([Uri]"{safe_path}"); '
                f'Start-Sleep -Milliseconds 500; '  # let it buffer
                f'$player.Play(); '
                f'while ($player.NaturalDuration.HasTimeSpan -eq $false) {{ Start-Sleep -Milliseconds 100 }}; '
                f'Start-Sleep -Seconds ([math]::Ceiling($player.NaturalDuration.TimeSpan.TotalSeconds + 0.5)); '
                f'$player.Close()'
            )
            subprocess.run(
                ["powershell", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                capture_output=True, timeout=60,
            )
        except Exception as e:
            print(f"[DEBUG] PowerShell audio playback error: {e}")

    def _speak_elevenlabs(self, text: str):
        """Speak text using ElevenLabs TTS API."""
        if not HAS_URLLIB:
            print("[DEBUG] urllib not available for ElevenLabs TTS")
            return

        voice_cfg = self.jarvis.config.get("voice", {})
        api_key = voice_cfg.get("elevenlabs_key", "")
        voice_id = voice_cfg.get("elevenlabs_voice", "pNInz6obpgDQGcFmaJgB")

        if not api_key:
            print("[DEBUG] ElevenLabs API key not configured — set config.voice.elevenlabs_key")
            return

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        }
        body = json.dumps({
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }).encode("utf-8")

        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req) as resp:
                audio_data = resp.read()

            # Save to temp file and play
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.write(audio_data)
            tmp.close()

            # Try pygame.mixer first, fall back to system player
            try:
                import pygame
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                pygame.mixer.music.load(tmp.name)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    import time
                    time.sleep(0.1)
            except Exception:
                # Fallback: use Windows media player silently
                import subprocess
                subprocess.Popen(
                    ["powershell", "-WindowStyle", "Hidden", "-Command",
                     f'(New-Object Media.SoundPlayer "{tmp.name}").PlaySync()'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    shell=True,
                )
                # SoundPlayer only handles .wav; for .mp3 use wmplayer
                import time
                time.sleep(0.5)
                os.system(f'start /min wmplayer "{tmp.name}"')

            # Clean up after a delay
            import time
            time.sleep(2)
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

        except urllib.error.HTTPError as e:
            print(f"[DEBUG] ElevenLabs API error {e.code}: {e.read().decode()}")
        except Exception as e:
            print(f"[DEBUG] ElevenLabs TTS error: {e}")

    def _clean_for_speech(self, text: str) -> str:
        """Clean text for natural, human-sounding speech output."""
        if not text:
            return ""

        # Don't speak raw JSON/dicts
        stripped = text.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            return ""

        # Remove code blocks — replace with brief mention
        text = re.sub(r"```[\s\S]*?```", " I've put the code on screen. ", text)
        # Remove inline code backticks but keep the word
        text = re.sub(r"`([^`]+)`", r"\1", text)
        # Remove markdown formatting but keep text
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)  # bold
        text = re.sub(r"\*([^*]+)\*", r"\1", text)       # italic
        text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)  # headers
        text = re.sub(r"^[-*]\s+", "", text, flags=re.MULTILINE)  # bullets
        text = re.sub(r"[~>|]", "", text)
        # Remove URLs — say "link" naturally
        text = re.sub(r"https?://\S+", "the link", text)
        # Remove emojis and special UI chars
        text = re.sub(r"[⬡◌●✓✗○⚠▶🎤📸🔍💾🔋💿☕🛡️⚡📋🌙☰]", "", text)

        # Make abbreviations speech-friendly
        text = text.replace("CPU", "C P U")
        text = text.replace("RAM", "ram")
        text = text.replace("GB", "gigabytes")
        text = text.replace("MB", "megabytes")
        text = text.replace("API", "A P I")
        text = text.replace("URL", "U R L")
        text = text.replace("SSH", "S S H")
        text = text.replace("DNS", "D N S")

        # Convert numbered lists to natural speech
        text = re.sub(r"^\d+\.\s+", "", text, flags=re.MULTILINE)

        # Clean up whitespace
        text = re.sub(r"\n+", ". ", text)  # newlines become pauses
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"\.\s*\.", ".", text)  # remove double periods

        # Truncate at sentence boundary
        if len(text) > 600:
            cut = text[:600]
            last_period = cut.rfind(".")
            if last_period > 200:
                text = cut[:last_period + 1] + " The rest is on screen."
            else:
                text = cut + "... rest is on screen."
        return text

    # ══════════════════════════════════════════════════════════════
    # SPEECH-TO-TEXT
    # ══════════════════════════════════════════════════════════════

    def _listen_for_text(
        self,
        *,
        owner: str,
        timeout: int,
        phrase_time_limit: int,
        ambient_duration: float = 0.3,
        wait_for_slot: bool = False,
        slot_timeout: float = 2.0,
        prompt: str | None = None,
    ) -> str:
        """Capture and transcribe one utterance while holding the global STT lock."""
        if not HAS_STT or not self.recognizer:
            raise RuntimeError("Speech recognition not available")

        if wait_for_slot:
            acquired = self._stt_lock.acquire(timeout=slot_timeout)
        else:
            acquired = self._stt_lock.acquire(blocking=False)

        if not acquired:
            busy_owner = self._stt_owner or "another voice task"
            raise RuntimeError(f"Voice capture busy ({busy_owner})")

        self.is_listening = True
        self._stt_owner = owner
        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=ambient_duration)
                if prompt:
                    print(prompt)
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            text = self._transcribe(audio)
            return text.strip() if text else ""
        finally:
            self.is_listening = False
            self._stt_owner = ""
            self._stt_lock.release()

    def listen_once(self, callback, error_callback, timeout=10, phrase_limit=20):
        """Listen for a single voice command."""
        if self.uses_gemini_live():
            if not self.is_enabled:
                self.enable()
            error_callback("Gemini Live uses a continuous session. Voice is active — speak naturally.")
            return

        if not HAS_STT or not self.recognizer:
            error_callback("Speech recognition not available. Install: pip install SpeechRecognition pyaudio")
            return

        def _listen():
            try:
                text = self._listen_for_text(
                    owner="listen_once",
                    timeout=timeout,
                    phrase_time_limit=phrase_limit,
                    ambient_duration=0.5,
                    wait_for_slot=True,
                    slot_timeout=3.0,
                )
                if text:
                    callback(text)
            except sr.WaitTimeoutError:
                error_callback("No speech detected — try again, sir")
            except sr.UnknownValueError:
                error_callback("Could not understand audio — please repeat, sir")
            except sr.RequestError as e:
                error_callback(f"Speech service error: {e}")
            except RuntimeError as e:
                error_callback(str(e))
            except Exception as e:
                error_callback(str(e))

        threading.Thread(target=_listen, daemon=True).start()

    # ══════════════════════════════════════════════════════════════
    # WAKE WORD
    # ══════════════════════════════════════════════════════════════

    def _start_wake_word(self):
        if self.uses_gemini_live():
            return
        if not HAS_STT or not self.recognizer:
            return
        # Don't start if already running
        if self._wake_thread and self._wake_thread.is_alive():
            self.wake_word_active = True
            return
        self.wake_word_active = True
        self._wake_thread = threading.Thread(target=self._wake_word_loop, daemon=True)
        self._wake_thread.start()

    def _wake_word_loop(self):
        wake_word = self.jarvis.config.get("voice", {}).get("wake_word", "jarvis").lower()
        print(f"[JARVIS] Wake word loop started — listening for '{wake_word}'")

        while self.wake_word_active and not self._stop_event.is_set():
            if self._confirmation_active:
                time.sleep(0.2)
                continue
            if self.is_listening:
                time.sleep(0.2)
                continue
            # ── HARD MIC LOCK — completely deaf while JARVIS speaks ──
            # This is the primary echo prevention. The mic does NOT open
            # until TTS is fully finished + cooldown has passed.
            if self._mic_locked or self.is_speaking:
                time.sleep(0.3)
                continue
            # Wait after TTS finishes to avoid echo pickup (sound lingers in room)
            elapsed = time.time() - self._tts_done_time if self._tts_done_time else 999
            if elapsed < self._echo_cooldown:
                time.sleep(0.3)
                continue

            # Check if conversation window has expired
            if self._conversation_active and time.time() > self._conversation_expires:
                self._conversation_active = False
                print("[JARVIS] Conversation window closed — back to wake word mode")

            try:
                timeout = 8 if self._conversation_active else 5

                try:
                    text = self._listen_for_text(
                        owner="wake_word",
                        timeout=timeout,
                        phrase_time_limit=15,
                        ambient_duration=0.3,
                        wait_for_slot=False,
                    ).lower()
                    print(f"[JARVIS] Heard: '{text}'")

                    # ── Echo detection: ignore if JARVIS heard itself ──
                    if self._is_echo(text):
                        print(f"[JARVIS] Echo detected — ignoring my own voice")
                        continue

                    # ── Decide if this speech is directed at JARVIS ──
                    is_for_jarvis = self._is_speaking_to_jarvis(text, wake_word)

                    if is_for_jarvis:
                        # Auto-enable TTS
                        if not self.is_enabled:
                            self.is_enabled = True
                            self.jarvis.voice_enabled = True
                            self.jarvis.root.after(0, lambda: self.jarvis.voice_btn.config(
                                text="🎤 On", fg="#00ff88"))

                        # Strip wake word and greetings to get the actual command
                        command = self._extract_command(text, wake_word)

                        # Open conversation window — JARVIS stays attentive
                        self._start_conversation()

                        if command:
                            # ── Dedup: skip if same text was just processed ──
                            if self._is_duplicate(command):
                                print(f"[JARVIS] Duplicate command ignored: '{command}'")
                                continue

                            print(f"[JARVIS] Command: '{command}'")
                            self.jarvis.root.after(0,
                                lambda c=command: self._handle_wake_command(c))
                        else:
                            # Just a greeting like "Hi JARVIS" or "Hey JARVIS"
                            # Respond naturally and keep listening
                            greeting = self._pick_greeting(text)
                            print(f"[JARVIS] Greeting detected — responding: '{greeting}'")
                            self.speak(greeting)
                            # Stay in conversation — wait for TTS then listen
                            time.sleep(1.5)
                            self._listen_followup()

                except sr.UnknownValueError:
                    pass  # No speech detected
                except sr.RequestError as e:
                    print(f"[JARVIS] Google STT error: {e}")
                except RuntimeError:
                    time.sleep(0.2)
                    continue

            except sr.WaitTimeoutError:
                continue
            except Exception as e:
                print(f"[JARVIS] Wake loop error: {e}")
                time.sleep(1)

    def _listen_followup(self):
        """Listen for a follow-up command INSIDE the wake loop thread (no mic conflict)."""
        if self._confirmation_active:
            return
        # Wait for TTS to finish + mic lock to release (prevents echo feedback)
        while self.is_speaking or self._mic_locked:
            time.sleep(0.3)
        # Wait full cooldown — room echo can linger several seconds
        elapsed = time.time() - self._tts_done_time if self._tts_done_time else 999
        if elapsed < self._echo_cooldown:
            time.sleep(self._echo_cooldown - elapsed)

        try:
            text = self._listen_for_text(
                owner="followup",
                timeout=10,
                phrase_time_limit=15,
                ambient_duration=0.3,
                wait_for_slot=False,
                prompt="[JARVIS] Listening for follow-up (conversation active)...",
            ).lower()
            print(f"[JARVIS] Follow-up heard: '{text}'")

            # Echo filter — ignore JARVIS's own voice
            if self._is_echo(text):
                print(f"[JARVIS] Echo detected in follow-up — ignoring")
                return

            # Strip wake word if they said it again
            wake_word = self.jarvis.config.get("voice", {}).get("wake_word", "jarvis").lower()
            command = self._extract_command(text, wake_word)

            if command:
                # Extend conversation window — JARVIS stays attentive
                self._start_conversation()
                self.jarvis.root.after(0, lambda c=command: self._handle_wake_command(c))
            else:
                print("[JARVIS] Empty follow-up, resuming wake loop")
        except sr.WaitTimeoutError:
            print("[JARVIS] No follow-up heard, resuming wake loop")
        except sr.UnknownValueError:
            print("[JARVIS] Couldn't understand follow-up, resuming wake loop")
        except Exception as e:
            print(f"[JARVIS] Follow-up error: {e}")

    # ══════════════════════════════════════════════════════════════
    # CONVERSATIONAL AWARENESS — Makes JARVIS feel alive
    # ══════════════════════════════════════════════════════════════

    def _is_echo(self, text: str) -> bool:
        """
        Detect if what the microphone picked up is JARVIS's own TTS output.
        Uses multiple strategies: recency check, substring match, word overlap,
        and a bank of ALL recently spoken phrases (not just the last one).
        """
        heard = text.lower().strip()

        # ── Strategy 0: Check against ALL recent spoken phrases ──
        # (covers long replies where _last_spoken_text only holds the last chunk)
        now = time.time()
        for spoken_text, spoken_time in self._recent_spoken:
            if now - spoken_time > 12.0:
                continue  # too old
            if self._texts_match(heard, spoken_text):
                return True

        if not self._last_spoken_text:
            return False

        # Extend echo window to match cooldown (was 5s, cooldown is 6s — gap caused leaks)
        if self._tts_done_time and (now - self._tts_done_time > self._echo_cooldown + 2.0):
            return False

        spoken = self._last_spoken_text
        if self._texts_match(heard, spoken):
            return True

        # Common JARVIS output patterns that indicate echo
        echo_phrases = [
            "searching for", "launched", "scanning", "opening",
            "setting reminder", "timer set", "checking",
            "voice systems", "listening", "couldn't quite catch",
            "i couldn't", "let me", "working on", "processing",
            "here's what", "i found", "all systems", "morning dev",
            "what can i", "how can i help", "what do you need",
            "ready when you are", "rest well", "good morning",
            "cpu at", "memory at", "battery at", "running smooth",
            "done sir", "done, sir", "good afternoon", "good evening",
        ]
        for phrase in echo_phrases:
            if phrase in heard and phrase in spoken:
                return True

        return False

    def _texts_match(self, heard: str, spoken: str) -> bool:
        """Check if heard text matches spoken text (substring or word overlap)."""
        # Exact match
        if heard == spoken:
            return True
        # Substring matches
        if len(heard) > 3 and heard in spoken:
            return True
        if len(spoken) > 3 and spoken in heard:
            return True
        # Word overlap — if >35% of heard words come from what JARVIS said
        heard_words = set(heard.split())
        spoken_words = set(spoken.split())
        if len(heard_words) >= 2 and len(spoken_words) >= 2:
            overlap = heard_words & spoken_words
            if len(overlap) / max(len(heard_words), 1) > 0.35:
                return True
        return False

    def _is_speaking_to_jarvis(self, text: str, wake_word: str) -> bool:
        """
        Determine if the user is speaking TO JARVIS or to someone else.

        Three modes of detection:
        1. Wake word present — always for JARVIS ("JARVIS open Chrome")
        2. Conversation active — recent exchange, assume it's for JARVIS
        3. Addressing signals — "can you", "do this", "hey" without naming others
        """
        text_lower = text.lower().strip()

        # Mode 1: Explicit wake word — always for JARVIS
        if wake_word in text_lower:
            return True

        # Mode 2: Conversation window is active — JARVIS is already engaged
        # After an exchange, JARVIS stays attentive for 30s
        if self._conversation_active and time.time() < self._conversation_expires:
            # But filter out clearly not-for-JARVIS speech
            if self._is_obviously_not_for_jarvis(text_lower):
                return False
            return True

        # Mode 3: JARVIS just spoke — next speech is probably a reply
        if self._tts_done_time and (time.time() - self._tts_done_time < 5.0):
            if not self._is_obviously_not_for_jarvis(text_lower):
                return True

        return False

    def _is_obviously_not_for_jarvis(self, text: str) -> bool:
        """Detect speech clearly aimed at someone else (phone call, talking to people)."""
        # Speaking to another person by name (not JARVIS)
        other_people = re.search(
            r"\b(?:hey|hi|hello|bye|goodbye)\s+(?!jarvis)[a-z]+\b", text
        )
        if other_people:
            return True

        # Phone conversation patterns
        phone_patterns = re.search(
            r"\b(?:yeah (?:i'll|i will)|no (?:i|we) (?:can't|won't)|"
            r"see you|talk to you|call you|on the phone|"
            r"hold on|one sec(?:ond)?|be right (?:back|there)|"
            r"speaking|who is this|wrong number)\b", text
        )
        if phone_patterns:
            return True

        # Very short filler speech (sighs, "hmm", "okay", "um")
        if len(text.split()) <= 1 and text in ("hmm", "um", "uh", "okay", "ok",
                                                 "yeah", "no", "mhm", "huh"):
            return True

        return False

    def _extract_command(self, text: str, wake_word: str) -> str:
        """Extract the actual command from speech, stripping greetings and wake word."""
        command = text.lower().strip()

        # Remove wake word
        if wake_word in command:
            parts = command.split(wake_word, 1)
            # Take the part after wake word, or before if wake word is at the end
            after = parts[1].strip() if len(parts) > 1 else ""
            before = parts[0].strip() if parts[0].strip() else ""
            command = after if after else before

        # Remove greeting prefixes
        greetings = [
            "hi", "hey", "hello", "good morning", "good afternoon",
            "good evening", "what's up", "sup", "yo",
        ]
        for g in greetings:
            if command.startswith(g):
                command = command[len(g):].strip()
                # Remove trailing comma or comma-space
                command = command.lstrip(",").strip()

        # Remove filler phrases
        fillers = [
            "can you", "could you", "would you", "please",
            "i need you to", "i want you to", "go ahead and",
        ]
        for f in fillers:
            if command.startswith(f):
                command = command[len(f):].strip()

        return command

    def _start_conversation(self):
        """Open or extend the conversation window."""
        self._conversation_active = True
        self._conversation_expires = time.time() + self._conversation_timeout
        self._last_interaction_time = time.time()
        print(f"[JARVIS] Conversation window open — {self._conversation_timeout}s timeout")

    def _pick_greeting(self, text: str) -> str:
        """Pick a natural greeting response based on what the user said."""
        text_lower = text.lower()
        hour = time.localtime().tm_hour

        # Time-aware greetings
        if "good morning" in text_lower:
            responses = [
                "Morning, Dev. What's on the agenda?",
                "Good morning! Ready when you are.",
                "Morning, sir. How can I help?",
            ]
        elif "good night" in text_lower or "goodnight" in text_lower:
            responses = [
                "Good night, Dev. I'll keep watch.",
                "Rest well, sir. I'll be here.",
                "Night, Dev. See you tomorrow.",
            ]
        elif any(w in text_lower for w in ["what's up", "sup", "how are you"]):
            responses = [
                "All good here, sir. What do you need?",
                "Systems are running smooth. What's up?",
                "Doing well! What can I do for you?",
            ]
        elif any(w in text_lower for w in ["hi", "hey", "hello"]):
            if hour < 12:
                responses = [
                    "Hey, Dev. Good morning! What do you need?",
                    "Morning! What can I help with?",
                    "Hey! Ready to go.",
                ]
            elif hour < 18:
                responses = [
                    "Hey, Dev. What's up?",
                    "Hey! What can I do for you?",
                    "Hi there! What do you need?",
                ]
            else:
                responses = [
                    "Hey, Dev. Working late?",
                    "Evening! What do you need?",
                    "Hey! What can I help with?",
                ]
        else:
            responses = [
                "Yes, sir?",
                "I'm here, Dev.",
                "What do you need?",
                "Listening.",
            ]

        import random
        return random.choice(responses)

    def _is_duplicate(self, command: str) -> bool:
        """Check if this command was just processed (within 5 seconds)."""
        now = time.time()
        cmd_lower = command.lower().strip()
        short_replies = {
            "yes", "yeah", "yep", "yup", "ok", "okay", "no", "nah", "nope",
            "send it", "send the text", "go ahead", "cancel", "stop",
        }

        if self._confirmation_active:
            return False
        if cmd_lower in short_replies:
            return False

        if not self._last_processed_text:
            return False

        # Within dedup window?
        if now - self._last_processed_time > 10.0:
            return False

        last = self._last_processed_text.lower().strip()

        # Exact or near-exact match
        if cmd_lower == last:
            return True

        # Word overlap — if >80% same words, it's a duplicate
        cmd_words = set(cmd_lower.split())
        last_words = set(last.split())
        if len(cmd_words) >= 2 and len(last_words) >= 2:
            overlap = cmd_words & last_words
            ratio = len(overlap) / max(len(cmd_words), len(last_words))
            if ratio > 0.8:
                return True

        return False

    def _handle_wake_command(self, command: str):
        # Dedup — skip if same command was just processed
        if self._is_duplicate(command):
            print(f"[JARVIS] Duplicate detected — skipping: '{command}'")
            return

        self._last_processed_text = command
        self._last_processed_time = time.time()

        self.jarvis.chat.add_message("voice", f'Heard: "{command}"')
        # Show voice input in 3D core HUD
        core3d = getattr(self.jarvis, 'core_3d', None)
        if core3d:
            core3d.add_chat("voice", f'🎤 "{command}"')
        try:
            self.jarvis.send_message(command)
        except Exception as e:
            print(f"[JARVIS] Wake command error: {e}")
            self.jarvis.chat.add_message("system", f"Error processing command: {e}")

    # ══════════════════════════════════════════════════════════════
    # PLUGIN HOOKS
    # ══════════════════════════════════════════════════════════════

    def _handle_tts_command(self, args: str):
        """Handle /tts command to switch TTS engine."""
        voice_cfg = self.jarvis.config.setdefault("voice", {})
        current = voice_cfg.get("tts_engine", "pyttsx3")

        if not args:
            self.jarvis.chat.add_message("system",
                f"Current TTS engine: {current}\n"
                f"Usage: /tts pyttsx3 | /tts elevenlabs")
            return

        choice = args.lower()
        if choice in ("pyttsx3", "elevenlabs"):
            voice_cfg["tts_engine"] = choice
            self.jarvis.chat.add_message("system", f"TTS engine switched to: {choice}")
            if choice == "elevenlabs" and not voice_cfg.get("elevenlabs_key"):
                self.jarvis.chat.add_message("system",
                    "Warning: ElevenLabs API key not set. "
                    "Add \"elevenlabs_key\" to the voice config.")
        else:
            self.jarvis.chat.add_message("system",
                f"Unknown engine '{choice}'. Use: pyttsx3 | elevenlabs")

    def on_command(self, command: str, args: str) -> bool:
        if command in ("/voice", "/v"):
            self.jarvis.toggle_voice()
            return True
        if command == "/say":
            self.speak(args)
            return True
        if command == "/listen":
            self.jarvis.toggle_listening()
            return True
        if command == "/tts":
            self._handle_tts_command(args.strip())
            return True
        return False

    def on_response(self, response: str):
        """Speak AI responses when voice is enabled."""
        print(f"[DEBUG] VoicePlugin.on_response called, is_enabled={self.is_enabled}")
        if self.is_enabled:
            print(f"[DEBUG] Speaking: {response[:50]}...")
            self.speak(response)
            # Extend conversation window — JARVIS stays attentive after speaking
            if not self._confirmation_active and (self._conversation_active or self.wake_word_active):
                self._start_conversation()

    def get_status(self) -> dict:
        voice_cfg = self.jarvis.config.get("voice", {})
        return {
            "name": self.name,
            "active": self.is_enabled,
            "engine": self._voice_engine_mode,
            "tts_engine": voice_cfg.get("tts_engine", "pyttsx3"),
            "tts_available": HAS_TTS,
            "stt_available": HAS_STT,
            "wake_word_active": self.wake_word_active,
            "live_session": bool(self._gemini_voice and self._gemini_voice.active),
        }
