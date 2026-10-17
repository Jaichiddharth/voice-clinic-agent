"""Understanding what the caller said: intent, dates, times, ids, names. Rules first, local LLM as fallback."""
import json, re
from datetime import datetime
import requests
import config

# ---------- yes / no ----------
def yes_no(text):
    w = set(re.findall(r"[a-z']+", text.lower()))
    pos = w & {"yes", "yeah", "yep", "yup", "sure", "correct", "right", "ok", "okay", "confirm",
               "absolutely", "definitely", "proceed", "fine", "affirmative"}
    neg = w & {"no", "nope", "nah", "not", "wrong", "incorrect", "don't", "dont", "never"}
    if pos and not neg: return True
    if neg and not pos: return False
    return None

# ---------- intent ----------
RULES = [
    ("exit", r"\b(bye|goodbye|hang up|that'?s all|that is all|nothing else|i'?m done)\b"),
    ("delete", r"\b(cancel|delete|remove|drop)\b"),
    ("update", r"\b(re-?schedul\w*|change|move|update|modify|shift|postpone|edit)\b"),
    ("followup", r"\b(follow[- ]?up|re-?check\w*|review|not (getting )?better)\b"),
    ("history", r"\b(history|past (visits?|records?)|previous (visits?|records?)|medical records?|health records?)\b"),
    ("availability", r"\b(availab\w*|free slots?|open slots?|slots?)\b"),
    ("read", r"\b(check|view|list|existing|my appointments?|status|upcoming|what do i have|read)\b"),
    ("create", r"\b(book|schedul\w*|make|new|create|fix|set up|arrange|need|want|see a doctor|consult\w*|appointment)\b"),
]
INTENTS = {"create", "read", "update", "delete", "availability", "followup", "history", "exit"}

def _llm_json(prompt):
    try:
        r = requests.post(config.OLLAMA_URL, json={"model": config.OLLAMA_MODEL, "prompt": prompt,
                          "stream": False, "format": "json", "options": {"temperature": 0}}, timeout=20)
        return json.loads(r.json()["response"])
    except Exception:
        return None

def intent(text):
    t = text.lower()
    for name, pat in RULES:
        if re.search(pat, t):
            return name
    out = _llm_json("Classify the caller of a doctor clinic into one intent: create (book), read (check appointments), "
                    "update (reschedule), delete (cancel), availability, followup (follow-up consultation about an "
                    "earlier health problem), history (past visit records), exit, unknown. "
                    f'Reply as JSON {{"intent": "..."}}. Caller said: "{text}"')
    i = (out or {}).get("intent", "unknown")
    return i if i in INTENTS else "unknown"

# ---------- time & date: spoken words -> typed values ----------
# Pipeline: transcript text -> find time phrase -> numbers -> 'HH:MM' (24h, zero-padded) -> datetime in services.
_W = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                 "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_T = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50}

def _num(s):
    s = s.lower().strip()
    if s.isdigit(): return int(s)
    m = re.fullmatch(r"o[h']?[\s-]?(\w+)", s)            # "oh five" -> 5
    if m and m[1] in _W: return _W[m[1]]
    parts = re.split(r"[\s-]+", s)
    if parts[0] in _T: return _T[parts[0]] + (_W.get(parts[1], 0) if len(parts) > 1 else 0)
    return _W.get(s)

_UNIT = "one|two|three|four|five|six|seven|eight|nine"
_H = rf"(?:\d{{1,2}}|{_UNIT}|ten|eleven|twelve)"
_M = rf"(?:(?:twenty|thirty|forty|fifty)(?:[\s-](?:{_UNIT}))?|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|o[h']?[\s-]?(?:{_UNIT}))"
_MER = r"(?:(?P<mer>[ap])\.?\s?m\b\.?)"
_CUE = re.compile(r"\b(?:in the\s+|this\s+)?(?:morning|afternoon|evening)\b", re.I)
_PATTERNS = [re.compile(p, re.I) for p in (
    rf"\b(?P<kind>half|quarter)\s+(?P<dir>past|to)\s+(?P<h>{_H})\b(?:\s*{_MER})?",   # half past eight
    rf"\b(?P<h>\d{{1,2}})\s?[:.]\s?(?P<m>\d{{2}})(?!\d)(?:\s*{_MER})?",                # 8:30 / 8.30 / 8.30 am
    rf"\b(?P<hm>\d{{3,4}})\s*{_MER}",                                                # 830am
    rf"\b(?P<h>\d{{1,2}})\s(?P<m>[0-5]\d)\s*{_MER}",                                # 8 30 am
    rf"\b(?P<h>{_H})\s+(?P<m>{_M})\b(?:\s*{_MER})?",                                # eight thirty (am)
    rf"\b(?P<h>{_H})\s*{_MER}",                                                       # 8am / 8 a.m. / eight am
    rf"\b(?P<h>{_H})\s*o'?\s?clock\b(?:\s*{_MER})?",                                # 8 o'clock
    rf"\b(?P<h>{_H})\s+(?:in the\s+)?(?:morning|afternoon|evening)\b",               # ten in the morning
    r"\b(?:noon|midday)\b",                                                           # noon
    rf"\bat\s+(?P<h>{_H})\b",                                                         # at 3
)]

def _to_hhmm(m, cue):
    g = m.groupdict()
    if m.re.groups == 0:
        return "12:00"
    mer = (g.get("mer") or "").lower()
    if g.get("kind"):
        h = _num(g["h"])
        if h is None: return None
        if g["kind"] == "half": mi = 30
        elif g["dir"] == "past": mi = 15
        else: mi, h = 45, (h - 1) or 12
    elif g.get("hm"):
        h, mi = divmod(int(g["hm"]), 100)
    else:
        h = _num(g["h"]); mi = _num(g["m"]) if g.get("m") else 0
    if h is None or mi is None: return None
    if mer == "p" and h < 12: h += 12
    elif mer == "a" and h == 12: h = 0
    elif not mer:
        if cue in ("afternoon", "evening") and h < 12: h += 12
        elif cue == "morning": pass
        elif 1 <= h <= 7: h += 12            # clinic hours: "3" means 3 PM
    if not (0 <= h <= 23 and 0 <= mi <= 59): return None
    return f"{h:02d}:{mi:02d}"

def parse_time(text):
    """Returns ('HH:MM' or None, text-with-the-time-phrase-removed)."""
    cm = re.search(r"\b(morning|afternoon|evening)\b", text, re.I)
    cue = cm[1].lower() if cm else None
    for p in _PATTERNS:
        for m in p.finditer(text):
            hhmm = _to_hhmm(m, cue)
            if hhmm:
                return hhmm, _CUE.sub(" ", text[:m.start()] + " " + text[m.end():])
    return None, _CUE.sub(" ", text)

def parse_date(text):
    from dateparser.search import search_dates
    if not text.strip():
        return None
    try:
        found = search_dates(text, languages=["en"], settings={
            "PREFER_DATES_FROM": "future", "RELATIVE_BASE": datetime.now(config.TZ).replace(tzinfo=None)})
    except Exception:
        found = None
    return found[0][1].date() if found else None

def parse_datetime(text):
    hhmm, rest = parse_time(text)
    d = parse_date(rest)
    if config.DEBUG:
        print(f"  [heard] {text!r} -> date={d} time={hhmm}")
    return d, hhmm

# ---------- ids, names, numbers ----------
DIGIT_WORDS = {"zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4",
               "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9"}
LETTER_WORDS = {"kay": "K", "are": "R", "why": "Y", "you": "U", "see": "C", "bee": "B", "dee": "D",
                "jay": "J", "em": "M", "en": "N", "pea": "P", "tee": "T", "eye": "I", "ex": "X"}
STOP = {"is", "my", "it", "id", "at", "to", "um", "uh", "of", "in", "on", "an", "no", "ok", "its"}

def extract_patient_id(text):
    """'4 8 2 9 1 3 R K' -> ('482913', 'RK')"""
    digits, letters = "", ""
    for tk in re.findall(r"[a-zA-Z]+|\d+", text.lower()):
        if tk.isdigit():
            if len(digits) < 6: digits += tk
        elif tk in DIGIT_WORDS and len(digits) < 6:
            digits += DIGIT_WORDS[tk]
        elif len(digits) >= 6:
            if tk in LETTER_WORDS: letters += LETTER_WORDS[tk]
            elif tk not in STOP and len(tk) <= 2: letters += tk.upper()
    return digits[:6], letters[:2]

def digits_only(text):
    out = ""
    for tk in re.findall(r"[a-zA-Z]+|\d+", text.lower()):
        out += tk if tk.isdigit() else DIGIT_WORDS.get(tk, "")
    return out

NAME_STOP = {"my", "name", "is", "it's", "its", "i", "am", "this", "the", "first", "last",
             "surname", "it", "me", "call", "mr", "mrs", "ms"}

def extract_name(text):
    words = [w for w in re.findall(r"[A-Za-z]+", text) if w.lower() not in NAME_STOP]
    return words[0].capitalize() if words else None

ORD = {"first": 1, "one": 1, "second": 2, "two": 2, "third": 3, "three": 3,
       "fourth": 4, "four": 4, "fifth": 5, "five": 5}

def parse_choice(text, n):
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w == "last": return n
        v = int(w) if w.isdigit() else ORD.get(w)
        if v and 1 <= v <= n: return v
    return None
