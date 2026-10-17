"""Quick self-checks for the language parsing:  python test_logic.py"""
import nlu
T = lambda s: nlu.parse_time(s)[0]
# --- times: every way a person (or Whisper) might say it ---
cases = {
    "8am": "08:00", "8 am": "08:00", "8 a.m.": "08:00", "8AM": "08:00", "8:30AM": "08:30",
    "8:30 a.m.": "08:30", "8.30 AM": "08:30", "830 am": "08:30", "8 30 am": "08:30",
    "eight am": "08:00", "eight thirty": "08:30", "eight thirty am": "08:30", "half past eight": "08:30",
    "quarter to nine": "08:45", "quarter past nine": "09:15", "9 o'clock": "09:00",
    "ten in the morning": "10:00", "two thirty in the afternoon": "14:30", "tomorrow morning at nine": "09:00",
    "at 3": "15:00", "3 pm": "15:00", "5:30 pm": "17:30", "12 pm": "12:00", "noon": "12:00",
    "at 10:30": "10:30", "17:30": "17:30", "eight oh five am": "08:05", "tomorrow": None, "october twenty fifth": None,
}
for text, want in cases.items():
    assert T(text) == want, (text, T(text), want)
assert "october" in nlu.parse_time("october twenty fifth at 10 am")[1] and T("october twenty fifth at 10 am") == "10:00"
# --- intents ---
for text, want in {"I want to book an appointment": "create", "please cancel my appointment": "delete",
                   "I need to reschedule": "update", "check my appointments": "read",
                   "I'd like a follow up consultation": "followup", "follow-up checkup please": "followup",
                   "read my medical history": "history", "what are my past records": "history"}.items():
    assert nlu.intent(text) == want, (text, nlu.intent(text))
# --- ids, names, yes/no ---
assert nlu.extract_patient_id("4 8 2 9 1 3 R K") == ("482913", "RK")
assert nlu.extract_patient_id("four eight two nine one three, a b") == ("482913", "AB")
assert nlu.extract_name("my name is priya") == "Priya"
assert nlu.yes_no("yes please") is True and nlu.yes_no("no thanks") is False
assert nlu.parse_choice("the second one", 3) == 2
print("All checks passed")
