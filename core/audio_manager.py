import pyaudio
import wave
import numpy as np
from threading import Thread
import time
from collections import deque

class AudioManager:
    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.is_listening = False
        self.voice_isolation_enabled = True
        self.feedback_suppression = True
        self.my_voice_signature = None
        self.audio_buffer = deque(maxlen=100)
        self.fatigue_detector = FatigueDetector()
        
    def start_voice_isolation(self):
        """Improved voice isolation to prevent feedback loops"""
        def audio_callback():
            while self.is_listening:
                try:
                    # Record audio chunk
                    chunk = self.record_chunk()
                    
                    # Suppress feedback from my own voice
                    if self.feedback_suppression:
                        chunk = self.suppress_feedback(chunk)
                    
                    # Voice activity detection
                    if self.is_human_voice(chunk):
                        self.audio_buffer.append(chunk)
                        
                    # Fatigue detection from voice patterns
                    self.fatigue_detector.analyze_voice(chunk)
                    
                except Exception as e:
                    print(f"Audio processing error: {e}")
                    
                time.sleep(0.01)
        
        Thread(target=audio_callback, daemon=True).start()
    
    def suppress_feedback(self, audio_chunk):
        """Remove my own voice from input to prevent feedback"""
        if self.my_voice_signature is not None:
            # Spectral subtraction to remove my voice frequency patterns
            return self.spectral_subtract(audio_chunk, self.my_voice_signature)
        return audio_chunk
    
    def is_human_voice(self, chunk):
        """Better voice activity detection"""
        # Analyze frequency patterns, energy levels
        energy = np.sum(chunk ** 2)
        return energy > 0.01  # Threshold for voice activity
    
    def learn_my_voice(self, my_speech_sample):
        """Learn JARVIS voice signature to filter it out"""
        self.my_voice_signature = np.fft.fft(my_speech_sample)
    
    def spectral_subtract(self, signal, noise_signature):
        """Remove noise signature from signal"""
        signal_fft = np.fft.fft(signal)
        clean_fft = signal_fft - 0.5 * noise_signature
        return np.fft.ifft(clean_fft).real

class FatigueDetector:
    def __init__(self):
        self.voice_patterns = []
        self.fatigue_indicators = 0
        
    def analyze_voice(self, audio_chunk):
        """Detect fatigue from voice patterns"""
        # Analyze pitch stability, speaking rate, energy
        pitch_variance = self.get_pitch_variance(audio_chunk)
        speaking_rate = self.get_speaking_rate(audio_chunk)
        
        if pitch_variance > 0.7 or speaking_rate < 0.8:
            self.fatigue_indicators += 1
        else:
            self.fatigue_indicators = max(0, self.fatigue_indicators - 1)
    
    def is_user_tired(self):
        return self.fatigue_indicators > 5
    
    def get_pitch_variance(self, chunk):
        # Simplified pitch analysis
        return np.std(chunk) / (np.mean(np.abs(chunk)) + 1e-10)
    
    def get_speaking_rate(self, chunk):
        # Simplified speaking rate analysis
        return len(chunk) / (np.sum(np.abs(chunk)) + 1e-10)

# Hindi language support
class HindiSupport:
    def __init__(self):
        self.hindi_responses = {
            'greeting': ['नमस्ते Dev', 'क्या हाल है?', 'कैसे हो आप?'],
            'confirmation': ['हाँ, हो गया', 'बिल्कुल', 'ठीक है'],
            'processing': ['एक मिनट रुकिये', 'काम चल रहा है', 'बस हो जाएगा'],
            'error': ['माफ करना, कुछ गलत हुआ', 'दोबारा कोशिश करते हैं'],
            'fatigue': ['आप थके लगते हैं', 'थोड़ा आराम करिये']
        }
    
    def get_hindi_response(self, category):
        import random
        return random.choice(self.hindi_responses.get(category, ['ठीक है']))