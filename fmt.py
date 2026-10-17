"""Turns typed values (dates/times) into friendly spoken text."""
import config

def fmt_date(d):
    return f"{d.strftime('%A')}, {d.day} {d.strftime('%B')}"

def fmt_time(hhmm):
    h, m = int(hhmm[:2]), int(hhmm[3:])
    return f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"

def fmt_dt(dt):
    dt = dt.astimezone(config.TZ)
    return f"{fmt_date(dt.date())} at {fmt_time(dt.strftime('%H:%M'))}"

def join_list(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
