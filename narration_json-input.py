"""Kept so the old command still works: python narration_json-input.py

It now runs narrate.py, which reads the API key from .env (never from this file), falls back to a
description built from the data when Gemini is unavailable, and writes the narration where the web page finds it:
static/data/narration.json and static/data/narration.wav.
"""
import narrate

if __name__ == "__main__":
    import os, sys
    narrate.run()
    sys.stdout.flush()
    os._exit(0)          # skip pyttsx3's harmless shutdown error on Windows (files are already saved)
