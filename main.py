"""Run:  python main.py --mode text   (keyboard)   |   python main.py --mode voice   (mic + speaker)"""
import argparse
import db, speech
from agent import Agent

ap = argparse.ArgumentParser()
ap.add_argument("--mode", choices=["text", "voice"], default="text")
ap.add_argument("--caller", help="simulate caller-ID, e.g. 9840011101")
args = ap.parse_args()

db.init_indexes()
if args.mode == "voice":
    print("Loading speech models (first run downloads ~500 MB)...")
    speech.load_models()
    io = speech.MicIO()
else:
    io = speech.TextIO()
Agent(io, args.caller).run()
