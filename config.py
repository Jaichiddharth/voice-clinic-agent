import os
from zoneinfo import ZoneInfo

CLINIC_NAME = "Sunrise Clinic"
AGENT_NAME = "Asha"

# --- Database ---
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = "clinic"

# --- Booking rules ---
OPEN_HOUR = 8            # 8 AM
CLOSE_HOUR = 18          # 6 PM (last slot starts 5:30 PM)
SLOT_MINUTES = 30
CLOSED_WEEKDAYS = {6}    # 0=Mon ... 6=Sun. Use set() to open all 7 days
MAX_ADVANCE_DAYS = 60

# --- Speech (all local, free) ---
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small.en")   # use base.en on weak PCs
PIPER_MODEL = os.getenv("PIPER_MODEL", "models/en_US-amy-medium.onnx")  # female voice

# --- Optional local LLM via Ollama (used only when keyword rules fail) ---
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

# --- Time & debugging ---
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")   # clinic's local time
TZ = ZoneInfo(TIMEZONE)
DEBUG = os.getenv("DEBUG", "1") == "1"             # prints what the agent heard and how it parsed it
