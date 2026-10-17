"""The conversation brain: greets, identifies the patient, then runs book / check / reschedule / cancel."""
import config, nlu, services
from fmt import fmt_date, fmt_time, fmt_dt, join_list

def describe(a):
    base = f"{a['doctor_name']} on {fmt_dt(a['start_at'])}"
    return base + (", a follow-up consultation" if a.get("type") == "follow_up" else "")

STATUS_TEXT = {"resolved": "marked as resolved", "improving": "improving but not fully resolved",
               "ongoing": "still ongoing"}

class Hangup(Exception):
    pass

class Agent:
    def __init__(self, io, caller_phone=None):
        self.io, self.caller = io, caller_phone
        self.doctors = services.list_doctors()

    # ----- conversation helpers -----
    def say(self, t): self.io.say(t)

    def hear(self, tries=3):
        for i in range(tries):
            t = self.io.listen()
            if t: return t
            if i < tries - 1: self.say("Sorry, I didn't catch that. Could you say it again?")
        raise Hangup()

    def ask(self, q, tries=3):
        self.say(q); return self.hear(tries)

    def confirm(self, q):
        self.say(q)
        for _ in range(3):
            a = nlu.yes_no(self.hear())
            if a is not None: return a
            self.say("Please say yes or no.")
        return False

    # ----- main flow -----
    def run(self):
        try:
            self.say(f"Hello, and welcome to {config.CLINIC_NAME}. I'm {config.AGENT_NAME}, your virtual assistant.")
            patient = self.identify()
            if not patient:
                self.say("Sorry, I couldn't verify your details. Please call again. Goodbye."); return
            self.say(f"Thank you, {patient['first_name']}.")
            handlers = {"create": self.book, "availability": self.book, "read": self.read,
                        "update": self.update, "delete": self.delete,
                        "followup": self.followup, "history": self.history}
            prompt = ("How can I help you today? You can book, check, reschedule or cancel an appointment, "
                      "book a follow-up consultation, or hear your past visits.")
            while True:
                intent = nlu.intent(self.ask(prompt))
                if intent == "exit": break
                if intent not in handlers:
                    prompt = "Sorry, I can book, check, reschedule or cancel appointments, arrange a follow-up consultation, or read your past visits. Which would you like?"
                    continue
                handlers[intent](patient)
                if not self.confirm("Is there anything else I can help you with?"): break
                prompt = "What else would you like to do?"
            self.say(f"Thank you for calling {config.CLINIC_NAME}. Take care. Goodbye!")
        except Hangup:
            try: self.say("I'm not able to hear you. Please call again. Goodbye.")
            except Exception: pass
        except ConnectionError:
            pass  # caller hung up

    # ----- identification / registration -----
    def identify(self):
        if self.caller:
            p = services.find_patient_by_phone(self.caller)
            if p and self.confirm(f"I see you're calling from a number registered to {p['first_name']} {p['last_name']}. Is that you?"):
                return p
        if self.confirm("Do you already have a patient ID with us?"):
            for _ in range(3):
                digits, letters = nlu.extract_patient_id(
                    self.ask("Please say your patient ID: six digits followed by two letters."))
                if len(digits) != 6:
                    self.say("I need all six digits."); continue
                p, exact = services.find_patient(digits, letters)
                if p and (exact or self.confirm(f"Am I speaking with {p['first_name']} {p['last_name']}?")):
                    return p
                self.say("I couldn't find that ID.")
            if not self.confirm("Would you like to register as a new patient?"):
                return None
        return self.register()

    def _ask_name(self, q):
        text = self.ask(q)
        for _ in range(2):
            n = nlu.extract_name(text)
            if n: return n
            text = self.ask("Sorry, could you repeat that name?")
        return None

    def register(self):
        for _ in range(2):
            first = self._ask_name("Let's register you. What is your first name?")
            last = self._ask_name("And your last name?")
            if not (first and last): return None
            phone = None
            if self.caller and self.confirm("Shall I use the number you're calling from as your contact number?"):
                phone = self.caller
            else:
                for _ in range(2):
                    phone = nlu.digits_only(self.ask("Please say your ten digit mobile number."))
                    if len(phone) >= 10: break
                    phone = None; self.say("That doesn't sound like ten digits.")
            if self.confirm(f"I have {first} {last}. Is that correct?"):
                p = services.create_patient(first, last, phone)
                spelled = ", ".join(p["patient_id"])
                self.say(f"You're registered. Your patient ID is {spelled}. I'll repeat it: {spelled}. Please note it down.")
                return p
        return None

    # ----- picking doctor / slot -----
    def choose_doctor(self):
        names = "; ".join(f"{d['name']}, {d['specialty']}" for d in self.doctors)
        text = self.ask(f"Which doctor would you like to see? We have {names}. You can also tell me a specialty or a health concern.")
        for i in range(3):
            d = services.match_doctor(text)
            if d: return d
            if i < 2: text = self.ask("Sorry, I couldn't match that. Please say a doctor's name or a specialty, like cardiologist or skin.")
        return None

    def _speak_slots(self, free):
        if len(free) <= 5: return join_list([fmt_time(s) for s in free])
        return f"{len(free)} slots between {fmt_time(free[0])} and {fmt_time(free[-1])}, for example {join_list([fmt_time(s) for s in free[:3]])}"

    def choose_slot(self, doctor, patient, exclude_id=None):
        """Collects day+time, converts to typed values, and checks BOTH the doctor's and the patient's calendar."""
        text = self.ask("Which day would you like, and at what time?")
        d = t = None
        for _ in range(5):
            nd, nt = nlu.parse_datetime(text)
            d, t = nd or d, nt or t
            if not d:
                text = self.ask("Sorry, I didn't get the day. You can say tomorrow, Monday, or a date like October twentieth."); continue
            err = services.validate_date(d)
            if err:
                self.say(err); d = t = None
                text = self.ask("Please tell me another day."); continue
            free_doc = services.available_slots(doctor["doctor_id"], d)
            busy = services.patient_busy_times(patient["patient_id"], d, exclude_id)
            free = [s for s in free_doc if s not in busy]      # doctor free AND patient free
            if not free:
                self.say(f"Sorry, there are no slots on {fmt_date(d)} with {doctor['name']} that fit around your other appointments.")
                d = t = None; text = self.ask("Please tell me another day."); continue
            if t is None:
                self.say(f"On {fmt_date(d)}, {doctor['name']} has {self._speak_slots(free)}.")
                text = self.ask("What time would you like?"); continue
            if t in free:
                return d, t
            if t in busy:                                      # the "two doctors, same time" case
                self.say(services.conflict_message(busy[t]))
            elif not services.valid_time(t):
                self.say("Appointments are available only between 8 AM and 6 PM, in 30 minute slots.")
            else:
                self.say(f"Sorry, {fmt_time(t)} is not available.")
            self.say(f"The closest free times are {join_list([fmt_time(s) for s in services.nearest(free, t)])}.")
            t = None; text = self.ask("Which time would you like?")
        self.say("I'm having trouble finding a suitable slot. Please try again later.")
        return None

    def _pick(self, patient, verb):
        appts = services.upcoming(patient["patient_id"])
        if not appts:
            self.say("You have no upcoming appointments."); return None
        if len(appts) == 1:
            self.say(f"You have one appointment, with {describe(appts[0])}."); return appts[0]
        self.say(f"You have {len(appts)} upcoming appointments.")
        for i, a in enumerate(appts, 1):
            self.say(f"Number {i}: {describe(a)}.")
        text = self.ask(f"Which one would you like to {verb}? Say the number.")
        for _ in range(2):
            c = nlu.parse_choice(text, len(appts))
            if c: return appts[c - 1]
            text = self.ask("Sorry, please say a number from the list.")
        return None

    # ----- the four operations -----
    def book(self, patient):                                   # CREATE
        doc = self.choose_doctor()
        if not doc:
            self.say("Sorry, I couldn't work out which doctor you need."); return
        self._book_with(patient, doc)

    def _book_with(self, patient, doc, kind="regular", reason=None, follow_up_of=None):
        slot = self.choose_slot(doc, patient)
        if not slot: return
        d, t = slot
        label = "a follow-up consultation with" if kind == "follow_up" else ""
        if not self.confirm(f"Shall I book {label} {doc['name']} on {fmt_date(d)} at {fmt_time(t)}?".replace("  ", " ")):
            self.say("Okay, I haven't booked anything."); return
        appt, err = services.book(patient["patient_id"], doc["doctor_id"], d, t, kind, reason, follow_up_of)
        self.say(err or f"Done! Your appointment with {describe(appt)} is confirmed.")

    def followup(self, patient):                               # FOLLOW-UP CONSULTATION
        v = services.latest_visit(patient["patient_id"])
        if not v:
            if self.confirm("I don't see any earlier visits on file for you. Would you like to book a regular appointment instead?"):
                self.book(patient)
            return
        self.say(f"Your most recent visit was on {fmt_date(v['visit_at'].astimezone(config.TZ).date())} with "
                 f"{v['doctor_name']} for {v['complaint']}. It was {STATUS_TEXT[v['status']]}.")
        doc = services.get_doctor(v["doctor_id"])
        if not self.confirm(f"Would you like a follow-up consultation with {doc['name']} to check how you're doing?"):
            if not self.confirm("Would you like to see a different doctor for this follow-up?"):
                self.say("Okay, I haven't booked anything."); return
            doc = self.choose_doctor()
            if not doc:
                self.say("Sorry, I couldn't work out which doctor you need."); return
        self._book_with(patient, doc, "follow_up", v["complaint"], v["visit_id"])

    def history(self, patient):                                # PAST RECORDS
        visits = services.history(patient["patient_id"], 3)
        if not visits:
            self.say("I don't see any earlier visits on file for you."); return
        self.say(f"Here are your last {len(visits)} visit{'s' if len(visits) > 1 else ''}.")
        for v in visits:
            dx = f", diagnosed as {v['diagnosis']}" if v.get("diagnosis") else ""
            self.say(f"On {fmt_date(v['visit_at'].astimezone(config.TZ).date())}, with {v['doctor_name']}, for "
                     f"{v['complaint']}{dx}. It was {STATUS_TEXT[v['status']]}.")

    def read(self, patient):                                   # READ
        appts = services.upcoming(patient["patient_id"])
        if not appts:
            self.say("You have no upcoming appointments."); return
        self.say(f"You have {len(appts)} upcoming appointment{'s' if len(appts) > 1 else ''}.")
        for i, a in enumerate(appts, 1):
            self.say(f"Number {i}: {describe(a)}.")

    def update(self, patient):                                 # UPDATE
        appt = self._pick(patient, "reschedule")
        if not appt: return
        slot = self.choose_slot(services.get_doctor(appt["doctor_id"]), patient, appt["appointment_id"])
        if not slot: return
        d, t = slot
        if not self.confirm(f"Shall I move it to {fmt_date(d)} at {fmt_time(t)}?"):
            self.say("Okay, I've left it unchanged."); return
        new, err = services.reschedule(appt["appointment_id"], patient["patient_id"], d, t)
        self.say(err or f"Done! Your appointment is now with {describe(new)}.")

    def delete(self, patient):                                 # DELETE
        appt = self._pick(patient, "cancel")
        if not appt: return
        if not self.confirm(f"Are you sure you want to cancel your appointment with {describe(appt)}?"):
            self.say("Okay, I've kept your appointment."); return
        ok = services.cancel(appt["appointment_id"], patient["patient_id"])
        self.say("Your appointment has been cancelled." if ok else "Sorry, I couldn't cancel it.")
