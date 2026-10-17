"""Ears (faster-whisper) + mouth (Piper, female voice). Everything runs locally and free."""
import os, shutil, subprocess, sys, tempfile, threading
import numpy as np
import soundfile as sf
import config

SR = 16000
_stt, _lock = None, threading.Lock()

def load_models():
    global _stt
    if _stt is None:
        from faster_whisper import WhisperModel
        _stt = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")

def transcribe(audio16k):
    load_models()
    with _lock:
        segs, _ = _stt.transcribe(audio16k, language="en", beam_size=1, vad_filter=True)
        return " ".join(s.text for s in segs).strip()

def synth(text):
    """Text -> (float32 mono samples, sample_rate). Piper 'amy' = female voice."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp.close()
    try:
        if os.path.exists(config.PIPER_MODEL):
            subprocess.run([sys.executable, "-m", "piper", "-m", config.PIPER_MODEL, "-f", tmp.name],
                           input=text.encode(), check=True, capture_output=True)
        elif shutil.which("espeak-ng"):   # emergency fallback, robotic female voice
            subprocess.run(["espeak-ng", "-v", "en-us+f3", "-s", "155", "-w", tmp.name, text], check=True)
        else:
            raise RuntimeError("No TTS found: download the Piper voice (see README) or install espeak-ng")
        data, sr = sf.read(tmp.name, dtype="float32")
    finally:
        os.remove(tmp.name)
    return (data.mean(axis=1) if data.ndim > 1 else data), sr

class TextIO:
    """Keyboard test mode - no microphone needed."""
    def say(self, text): print(f"\n  {config.AGENT_NAME}: {text}")
    def listen(self):
        try: return input("  You: ").strip()
        except EOFError: raise ConnectionError

class MicIO:
    """Computer microphone + speakers = pretend phone call."""
    def say(self, text):
        import sounddevice as sd
        print(f"\n  {config.AGENT_NAME}: {text}")
        data, sr = synth(text)
        sd.play(data, sr); sd.wait()

    def listen(self, max_seconds=12, silence_seconds=1.2, threshold=0.012):
        import sounddevice as sd
        block, frames, started, silent, ticks = int(SR * 0.1), [], False, 0, 0
        print("  (listening...)")
        with sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=block) as st:
            while ticks < max_seconds * 10:
                data, _ = st.read(block); ticks += 1
                if float(np.sqrt(np.mean(data ** 2))) > threshold:
                    started, silent = True, 0; frames.append(data)
                elif started:
                    frames.append(data); silent += 1
                    if silent >= silence_seconds * 10: break
        if not frames: return ""
        text = transcribe(np.concatenate(frames).flatten())
        print(f"  You: {text}")
        return text
