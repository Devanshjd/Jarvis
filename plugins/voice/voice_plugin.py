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

    def activate(self):
        """Initialize STT and start TTS worker thread."""
        # TTS — must init AND run in the SAME thread (Windows COM requirement)
        if HAS_TTS:
            self._stop_event.clear()
            self._tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
            self._tts_thread.start()
            # Wait for engine to be ready
            self._tts_ready.wait(timeout=5)

        # STT setup
        if HAS_STT:
            try:
                self.recognizer = sr.Recognizer()
                self.recognizer.energy_threshold = 300
                self.recognizer.dynamic_energy_threshold = True
                self.recognizer.pause_threshold = 0.8
            except Exception as e:
                print(f"STT init error: {e}")
                self.recognizer = None

        # Auto-start wake word listening on boot
        auto_wake = self.jarvis.config.get("voice", {}).get("auto_wake", True)
        if auto_wake and HAS_STT and self.recognizer:
            self._start_wake_word()
            print("[JARVIS] Wake word listening active — say 'JARVIS' anytime")

    def deactivate(self):
        """Clean up voice resources."""
        self._stop_event.set()
        self.is_enabled = False
        self.wake_word_active = False
        # Send poison pill to unblock the TTS queue
        self._tts_queue.put(None)

    def enable(self):
        """Enable voice — TTS on responses, start wake word."""
        self.is_enabled = True
        self.speak("Voice systems online, sir.")
        if not self.wake_word_active:
            self._start_wake_word()

    def disable(self):
        """Disable voice."""
        self.is_enabled = False
        self.wake_word_active = False
        self.speak("Voice systems offline.")

    # ══════════════════════════════════════════════════════════════
    # TEXT-TO-SPEECH (all pyttsx3 calls in ONE thread)
    # ══════════════════════════════════════════════════════════════

    def speak(self, text: str):
        """Queue text to be spoken."""
        voice_cfg = self.jarvis.config.get("voice", {})
        engine = voice_cfg.get("tts_engine", "pyttsx3")

        if engine == "elevenlabs":
            clean = self._clean_for_speech(text)
            if clean:
                threading.Thread(target=self._speak_elevenlabs, args=(clean,), daemon=True).start()
            return

        if not HAS_TTS:
            print("[DEBUG] TTS not available")
            return
        clean = self._clean_for_speech(text)
        if clean:
            print(f"[DEBUG] Queuing TTS: {clean[:60]}...")
            self._tts_queue.put(clean)
        else:
            print("[DEBUG] Clean text was empty, nothing to speak")

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
                    import time as _t
                    self._tts_done_time = _t.time()
            except queue.Empty:
                continue

        pythoncom.CoUninitialize()

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
        """Clean text for natural speech output."""
        # Remove code blocks
        text = re.sub(r"```[\s\S]*?```", "code block omitted", text)
        # Remove inline code
        text = re.sub(r"`[^`]+`", "", text)
        # Remove markdown
        text = re.sub(r"[*_#~>|]", "", text)
        # Remove URLs
        text = re.sub(r"https?://\S+", "link", text)
        # Remove special chars
        text = re.sub(r"[⬡◌●✓○⚠▶🎤📸]", "", text)
        # Clean whitespace
        text = re.sub(r"\s+", " ", text).strip()
        # Truncate long responses
        if len(text) > 500:
            # Cut at sentence boundary
            cut = text[:500]
            last_period = cut.rfind(".")
            if last_period > 200:
                text = cut[:last_period + 1] + " Full response is on screen, sir."
            else:
                text = cut + "... Full response is on screen, sir."
        return text

    # ══════════════════════════════════════════════════════════════
    # SPEECH-TO-TEXT
    # ══════════════════════════════════════════════════════════════

    def listen_once(self, callback, error_callback, timeout=10, phrase_limit=20):
        """Listen for a single voice command."""
        if not HAS_STT or not self.recognizer:
            error_callback("Speech recognition not available. Install: pip install SpeechRecognition pyaudio")
            return

        def _listen():
            try:
                with sr.Microphone() as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
                text = self.recognizer.recognize_google(audio)
                if text:
                    callback(text)
            except sr.WaitTimeoutError:
                error_callback("No speech detected — try again, sir")
            except sr.UnknownValueError:
                error_callback("Could not understand audio — please repeat, sir")
            except sr.RequestError as e:
                error_callback(f"Speech service error: {e}")
            except Exception as e:
                error_callback(str(e))

        threading.Thread(target=_listen, daemon=True).start()

    # ══════════════════════════════════════════════════════════════
    # WAKE WORD
    # ══════════════════════════════════════════════════════════════

    def _start_wake_word(self):
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
            # ── Prevent feedback loop: skip while TTS is speaking ──
            if self.is_speaking:
                time.sleep(0.2)
                continue
            # Also wait 1.5s after TTS finishes to avoid echo pickup
            if self._tts_done_time and (time.time() - self._tts_done_time < 1.5):
                time.sleep(0.2)
                continue

            try:
                with sr.Microphone() as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                    audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)

                try:
                    text = self.recognizer.recognize_google(audio).lower()
                    print(f"[JARVIS] Heard: '{text}'")

                    if wake_word in text:
                        # Auto-enable TTS so JARVIS speaks the response back
                        if not self.is_enabled:
                            self.is_enabled = True
                            self.jarvis.voice_enabled = True
                            self.jarvis.root.after(0, lambda: self.jarvis.voice_btn.config(
                                text="🎤 On", fg="#00ff88"))

                        # Extract command after wake word
                        parts = text.split(wake_word, 1)
                        after = parts[1].strip() if len(parts) > 1 else ""

                        # Remove filler words at the start
                        for filler in ["can you", "could you", "please", "hey", "yo"]:
                            if after.startswith(filler):
                                after = after[len(filler):].strip()

                        if after:
                            # "JARVIS open Chrome" → process immediately
                            print(f"[JARVIS] Wake command: '{after}'")
                            self.jarvis.root.after(0,
                                lambda c=after: self._handle_wake_command(c))
                        else:
                            # Just "JARVIS" → say "Yes sir?" then listen for
                            # follow-up RIGHT HERE in this same thread, so we
                            # don't fight over the microphone.
                            print("[JARVIS] Wake word only — saying 'Yes sir?' then listening...")
                            self.speak("Yes, sir?")
                            # Wait for TTS to finish before listening
                            import time
                            time.sleep(1.5)
                            self._listen_followup()

                except sr.UnknownValueError:
                    pass  # No speech detected, loop again
                except sr.RequestError as e:
                    print(f"[JARVIS] Google STT error: {e}")

            except sr.WaitTimeoutError:
                continue
            except Exception as e:
                print(f"[JARVIS] Wake loop error: {e}")
                import time
                time.sleep(1)

    def _listen_followup(self):
        """Listen for a follow-up command INSIDE the wake loop thread (no mic conflict)."""
        # Wait for TTS to finish before listening (prevents echo feedback)
        while self.is_speaking:
            time.sleep(0.2)
        # Extra cooldown after TTS
        if self._tts_done_time and (time.time() - self._tts_done_time < 1.5):
            time.sleep(1.5 - (time.time() - self._tts_done_time))

        try:
            print("[JARVIS] Listening for follow-up command...")
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio = self.recognizer.listen(source, timeout=8, phrase_time_limit=15)

            text = self.recognizer.recognize_google(audio).lower()
            print(f"[JARVIS] Follow-up heard: '{text}'")

            # Strip wake word if they said it again
            wake_word = self.jarvis.config.get("voice", {}).get("wake_word", "jarvis").lower()
            if wake_word in text:
                text = text.split(wake_word, 1)[1].strip()

            if text:
                self.jarvis.root.after(0, lambda c=text: self._handle_wake_command(c))
            else:
                print("[JARVIS] Empty follow-up, resuming wake loop")
        except sr.WaitTimeoutError:
            print("[JARVIS] No follow-up heard, resuming wake loop")
        except sr.UnknownValueError:
            print("[JARVIS] Couldn't understand follow-up, resuming wake loop")
        except Exception as e:
            print(f"[JARVIS] Follow-up error: {e}")

    def _handle_wake_command(self, command: str):
        self.jarvis.chat.add_message("voice", f'Heard: "{command}"')
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

    def get_status(self) -> dict:
        voice_cfg = self.jarvis.config.get("voice", {})
        return {
            "name": self.name,
            "active": self.is_enabled,
            "tts_engine": voice_cfg.get("tts_engine", "pyttsx3"),
            "tts_available": HAS_TTS,
            "stt_available": HAS_STT,
            "wake_word_active": self.wake_word_active,
        }
