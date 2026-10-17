"""Real phone calls via Asterisk (free PBX) + AudioSocket. Run: python telephony.py
Asterisk streams the caller's voice to this TCP server (8 kHz, 16-bit) and plays back what we send."""
import socket, threading, time
import numpy as np
import db, speech
from agent import Agent

def _resample(x, n):
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)

class AudioSocketIO:
    def __init__(self, conn): self.conn, self.buf = conn, b""

    def _read_exact(self, n):
        while len(self.buf) < n:
            d = self.conn.recv(4096)
            if not d: raise ConnectionError
            self.buf += d
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def frame(self):
        t = self._read_exact(1)[0]
        ln = int.from_bytes(self._read_exact(2), "big")
        return t, (self._read_exact(ln) if ln else b"")

    def _drain(self):   # throw away what the caller "said" while we were talking (echo)
        self.conn.setblocking(False)
        try:
            while True:
                d = self.conn.recv(65536)
                if not d: raise ConnectionError
                self.buf += d
        except BlockingIOError:
            pass
        finally:
            self.conn.setblocking(True)
        while len(self.buf) >= 3:
            ln = int.from_bytes(self.buf[1:3], "big")
            if len(self.buf) < 3 + ln: break
            if self.buf[0] == 0: raise ConnectionError
            self.buf = self.buf[3 + ln:]

    def say(self, text):
        print("Asha:", text)
        x, sr = speech.synth(text)
        y = _resample(x, int(len(x) * 8000 / sr))
        pcm = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
        for i in range(0, len(pcm), 320):                      # 20 ms per frame
            c = pcm[i:i + 320]
            self.conn.sendall(b"\x10" + len(c).to_bytes(2, "big") + c)
            time.sleep(0.018)
        self._drain()

    def listen(self, max_s=12, silence_s=1.0, thr=0.012):
        frames, started, silent, ticks = [], False, 0, 0
        while ticks < max_s / 0.02:
            t, p = self.frame()
            if t == 0: raise ConnectionError                   # hang-up
            if t != 0x10: continue
            x = np.frombuffer(p, dtype="<i2").astype(np.float32) / 32768
            ticks += 1
            if len(x) and float(np.sqrt(np.mean(x ** 2))) > thr:
                started, silent = True, 0; frames.append(x)
            elif started:
                frames.append(x); silent += 1
                if silent >= silence_s / 0.02: break
        if not frames: return ""
        a = np.concatenate(frames)
        text = speech.transcribe(_resample(a, len(a) * 2).astype(np.float32))
        print("Caller:", text)
        return text

def handle(conn):
    try:
        io = AudioSocketIO(conn)
        io.frame()                       # first frame = call UUID
        Agent(io).run()
    except (ConnectionError, OSError):
        pass
    finally:
        conn.close()

if __name__ == "__main__":
    db.init_indexes(); speech.load_models()
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", 9092)); s.listen(10)
    print("Voice agent waiting for calls on port 9092 ...")
    while True:
        c, _ = s.accept()
        threading.Thread(target=handle, args=(c,), daemon=True).start()
