# Voice Clinic Agent (100% open source)

Caller speaks -> Whisper (ears) -> agent logic (+ optional local LLM) -> MongoDB -> Piper female voice (mouth).

## Setup
1. Install Python 3.10+, Docker, and (Linux) `sudo apt install libportaudio2 espeak-ng`
2. `docker compose up -d`                       # starts MongoDB
3. `python -m venv venv && source venv/bin/activate`   (Windows: `venv\Scripts\activate`)
4. `pip install -r requirements.txt`
5. Download the female voice into `models/`:
   - https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx
   - https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json
6. (Optional, smarter understanding) install https://ollama.com then `ollama pull llama3.2:3b`
7. `python seed.py --reset`                    # 5 doctors, 10 patients (IDs printed), sample bookings
8. `python test_logic.py`                      # sanity checks

## Run
- Keyboard test:  `python main.py --mode text`   (add `--caller 9840011101` to simulate caller-ID)
- Voice test:     `python main.py --mode voice`  (laptop mic + speakers act as the phone)
- REST API:       `uvicorn api:app --reload`      -> http://localhost:8000/docs
- Real calls:     see below

## Real phone calls (Asterisk)
1. Install Asterisk 18+ (`sudo apt install asterisk`), add `asterisk_extensions.conf` to `extensions.conf`,
   create a SIP extension in `pjsip.conf`, `asterisk -rx "core reload"`.
2. `python telephony.py`
3. Free demo: install the Linphone app on a phone/PC on the same Wi-Fi, register to your Asterisk, dial **100**.
4. Real phone number: rent a number/SIP trunk from a telecom provider and route it to extension 100
   (the software is free; the number itself is a rental).

## v2 changes
- **Time parsing rewritten** (`nlu.py`): handles "8am", "8 a.m.", "8:30AM", "8.30 AM", "eight thirty", "half past eight",
  "quarter to nine", "ten in the morning", "at 3"... Always becomes zero-padded 24h `HH:MM`, then ONE conversion to a
  real timezone-aware `datetime` (`services.make_start`). Mongo stores `start_at` / `end_at` datetimes (no more strings).
  With `DEBUG=1` (default) the console prints `[heard] 'text' -> date=... time=...` so you can see every parse.
- **No self-conflicts**: a patient can't hold two appointments at the same time, even with different doctors.
  Checked while choosing a slot (spoken explanation), again when booking AND rescheduling, and enforced by a database index.
- **Follow-up consultation + past records**: new `visits` collection. Say "follow-up consultation" or "past visits".
  Doctors add records via `POST /visits`; `GET /doctors/{id}/schedule?day=YYYY-MM-DD` shows each patient's latest visit.
- **Upgrading**: `pip install -r requirements.txt` (adds tzdata), then `python seed.py --reset`
  (old data is auto-migrated if you skip the reset). Set `TIMEZONE` env var if you're not in Asia/Kolkata.
