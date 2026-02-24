"""Wunderbots TTS — ElevenLabs voices.

Uses ElevenLabs Flash v2.5 for fast, expressive character voices.
Falls back gracefully if API key is missing or quota is exhausted.

Voice casting:
  Nova  — confident young woman, the leader
  Bolt  — energetic kid, comic relief
  Pip   — soft, gentle, quiet genius
  Experts — rotated from a pool of distinct voices
"""
import os
import logging
import requests

log = logging.getLogger("wunderbots.tts")

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"
MODEL_ID = "eleven_flash_v2_5"  # Fast, cheap (0.5 credits/char on Starter+)

# ─── Voice IDs ───────────────────────────────────────────────────────────────
# These are ElevenLabs default library voices. You can swap them for custom
# voices or clones by updating the IDs.
#
# Browse voices: https://elevenlabs.io/voice-library
# Or list via API: GET /v1/voices

GUIDE_VOICES = {
    # Nova — confident, warm, leader energy
    "nova": "EXAVITQu4vr4xnSDxMaL",    # "Bella" — young female, warm & clear
    # Bolt — energetic, playful, kid-like
    "bolt": "TxGEqnHWrfWFTfGW9XjX",     # "Josh" — young male, upbeat & energetic
    # Pip — soft, gentle, thoughtful
    "pip": "MF3mGyEYCl7XYWbV9V6O",       # "Elli" — soft female, gentle & kind
}

# Pool of voices for rotating experts (each episode gets different experts)
EXPERT_VOICE_POOL = [
    "pNInz6obpgDQGcFmaJgB",   # "Adam" — deep male, authoritative
    "21m00Tcm4TlvDq8ikWAM",   # "Rachel" — professional female
    "yoZ06aMxZJJ28mfd3POQ",   # "Sam" — friendly male
    "jBpfuIE2acCO8z3wKNLl",   # "Gigi" — animated female
    "VR6AewLTigWG4xSOukaG",   # "Arnold" — strong male
    "ThT5KcBeYPX3keUQqHPh",   # "Dorothy" — warm older female
]

# ─── Emotion → voice settings mapping ────────────────────────────────────────
# ElevenLabs doesn't use explicit vocal directions like Groq Orpheus.
# Instead, it reads emotion from text cues and we tune stability/similarity.
# Lower stability = more expressive/emotional, higher = more consistent.

EMOTION_SETTINGS = {
    "excited":    {"stability": 0.3, "similarity_boost": 0.8},
    "happy":      {"stability": 0.4, "similarity_boost": 0.75},
    "silly":      {"stability": 0.25, "similarity_boost": 0.7},
    "surprised":  {"stability": 0.3, "similarity_boost": 0.75},
    "explaining": {"stability": 0.55, "similarity_boost": 0.8},
    "thinking":   {"stability": 0.5, "similarity_boost": 0.8},
    "shy":        {"stability": 0.6, "similarity_boost": 0.85},
    "neutral":    {"stability": 0.5, "similarity_boost": 0.75},
}

# For backward compat with the old Groq module
EMOTION_DIRECTIONS = {k: "" for k in EMOTION_SETTINGS}


def build_expert_voice_map(characters: dict) -> dict:
    """Build a character_id → voice_id map for an episode's characters."""
    voice_map = {}
    expert_idx = 0

    for char_id, char in characters.items():
        if char_id in GUIDE_VOICES:
            voice_map[char_id] = GUIDE_VOICES[char_id]
        else:
            # Rotate through expert voice pool
            voice_map[char_id] = EXPERT_VOICE_POOL[expert_idx % len(EXPERT_VOICE_POOL)]
            expert_idx += 1

    return voice_map


def generate_speech(text: str, voice_id: str, emotion: str = "neutral") -> bytes:
    """Generate speech audio via ElevenLabs API.

    Args:
        text: The dialogue text to speak
        voice_id: ElevenLabs voice ID
        emotion: Emotion key for voice settings tuning

    Returns:
        MP3 audio bytes
    """
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY not set")

    if not text.strip():
        raise ValueError("Empty text")

    settings = EMOTION_SETTINGS.get(emotion, EMOTION_SETTINGS["neutral"])

    url = f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": {
            "stability": settings["stability"],
            "similarity_boost": settings["similarity_boost"],
        },
    }

    response = requests.post(url, json=payload, headers=headers, timeout=30)

    if response.status_code != 200:
        error_detail = response.text[:200]
        log.error(f"ElevenLabs API error {response.status_code}: {error_detail}")
        raise RuntimeError(f"ElevenLabs TTS failed: {response.status_code}")

    return response.content
