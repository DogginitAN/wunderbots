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
    "nova": "rRiIQLylyhtZZrjx61F1",     # Custom — curious adventurous young girl, warm leader energy
    # Bolt — energetic, playful, kid-like
    "bolt": "2f1b6Q2ICKpLzWrEEYVE",     # Custom voice — energetic goofy cartoon boy, lovable sidekick
    # Pip — soft, gentle, thoughtful
    "pip": "cN9lACJjByQco3FyvGzE",       # Custom voice — soft, gentle, whimsical fairy/owl character
}

# Pool of voices for rotating experts (each episode gets different experts)
EXPERT_VOICES_FEMALE = [
    "67oeJmj7jIMsdE6yXPr5",   # Custom F1 — warm mentor, Ms. Frizzle energy
    "ZT9u07TYPVl83ejeLakq",   # Custom F2 — cool calm scientist
    "y5LC9pxhb6k0W8IrQUXS",   # Custom F3 — energetic adventurer
    "0rEo3eAjssGDUCXHYENf",   # Custom F4 — gentle grandmother storyteller
]

EXPERT_VOICES_MALE = [
    "MDLAMJ0jxkpYkjXbmG4t",   # Custom M1 — booming enthusiast, jolly and dramatic
    "g2W4HAjKvdW93AmsjsOx",   # Custom M2 — nerdy professor, quick-talking and fascinated
    "Fz7HYdHHCP1EF1FLn46C",   # Custom M3 — laid-back guide, smooth and chill
    "n1PvBOwxb8X6m7tahp2h",   # Custom M4 — dramatic storyteller, theatrical and epic
]

# Fallback combined pool for episodes without gender data
EXPERT_VOICE_POOL = EXPERT_VOICES_FEMALE + EXPERT_VOICES_MALE

# Narrator / VJ voice — reads transitions, act headers, celebration
# Should sound like an exciting kids' show announcer
NARRATOR_VOICE = "MDLAMJ0jxkpYkjXbmG4t"  # PLACEHOLDER — replace with custom narrator voice

# ─── Emotion → voice settings + stage directions ─────────────────────────────
# ElevenLabs reads emotion from textual cues. We prepend stage directions
# that make the voice more animated and expressive — like a cartoon show.
# Lower stability = more expressive delivery, more variation.

EMOTION_SETTINGS = {
    "excited":    {"stability": 0.2, "similarity_boost": 0.75, "style": 0.4},
    "happy":      {"stability": 0.25, "similarity_boost": 0.75, "style": 0.3},
    "silly":      {"stability": 0.15, "similarity_boost": 0.65, "style": 0.5},
    "surprised":  {"stability": 0.2, "similarity_boost": 0.7, "style": 0.4},
    "explaining": {"stability": 0.35, "similarity_boost": 0.8, "style": 0.2},
    "thinking":   {"stability": 0.35, "similarity_boost": 0.8, "style": 0.2},
    "shy":        {"stability": 0.4, "similarity_boost": 0.85, "style": 0.15},
    "neutral":    {"stability": 0.3, "similarity_boost": 0.75, "style": 0.2},
}

# Stage directions prepended to text — ElevenLabs interprets these as
# performance cues, making the voice delivery more animated and character-like.
# These are NOT spoken aloud; ElevenLabs uses them to color the delivery.
EMOTION_DIRECTIONS = {
    "excited":    "*with big excited energy, like a kid on Christmas morning*",
    "happy":      "*warmly, with a big smile in the voice*",
    "silly":      "*being goofy and playful, hamming it up*",
    "surprised":  "*gasping with genuine surprise and wonder*",
    "explaining": "*enthusiastically teaching, like a favorite teacher*",
    "thinking":   "*thoughtfully, working through an idea out loud*",
    "shy":        "*softly and gently, a little quiet but sincere*",
    "neutral":    "*in a warm, friendly, animated tone*",
}

# Character-specific voice directions that layer on top of emotion
CHARACTER_DIRECTIONS = {
    "nova":  "Speaking as Nova, a confident and curious young adventurer. ",
    "bolt":  "Speaking as Bolt, a hilariously energetic and silly kid who can't contain his excitement. ",
    "pip":   "Speaking as Pip, a sweet, gentle, softly-spoken genius who's a little shy. ",
}


def build_expert_voice_map(characters: dict) -> dict:
    """Build a character_id → voice_id map for an episode's characters.
    
    Uses the expert's gender field to pick from the right voice pool.
    Falls back to the combined pool if gender isn't specified.
    """
    voice_map = {}
    female_idx = 0
    male_idx = 0
    fallback_idx = 0

    for char_id, char in characters.items():
        if char_id in GUIDE_VOICES:
            voice_map[char_id] = GUIDE_VOICES[char_id]
        else:
            gender = char.get("gender", "").lower() if isinstance(char, dict) else ""
            if gender == "female":
                voice_map[char_id] = EXPERT_VOICES_FEMALE[female_idx % len(EXPERT_VOICES_FEMALE)]
                female_idx += 1
            elif gender == "male":
                voice_map[char_id] = EXPERT_VOICES_MALE[male_idx % len(EXPERT_VOICES_MALE)]
                male_idx += 1
            else:
                # No gender specified — use combined pool
                voice_map[char_id] = EXPERT_VOICE_POOL[fallback_idx % len(EXPERT_VOICE_POOL)]
                fallback_idx += 1

    return voice_map


def generate_speech(text: str, voice_id: str, emotion: str = "neutral",
                    character: str = "") -> bytes:
    """Generate speech audio via ElevenLabs API with emotional stage directions.

    Args:
        text: The dialogue text to speak
        voice_id: ElevenLabs voice ID
        emotion: Emotion key for voice settings + stage direction
        character: Character ID for character-specific direction (optional)

    Returns:
        MP3 audio bytes
    """
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY not set")

    if not text.strip():
        raise ValueError("Empty text")

    settings = EMOTION_SETTINGS.get(emotion, EMOTION_SETTINGS["neutral"])

    # ElevenLabs speaks ALL text aloud — no hidden stage directions.
    # Expressiveness comes from voice_settings (stability, style, similarity).
    directed_text = text

    url = f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": directed_text,
        "model_id": MODEL_ID,
        "voice_settings": {
            "stability": settings["stability"],
            "similarity_boost": settings["similarity_boost"],
            "style": settings.get("style", 0.0),
            "use_speaker_boost": True,
        },
    }

    log.info(f"TTS: char={character}, emotion={emotion}, {len(text)} chars")
    response = requests.post(url, json=payload, headers=headers, timeout=30)

    if response.status_code != 200:
        error_detail = response.text[:200]
        log.error(f"ElevenLabs API error {response.status_code}: {error_detail}")
        raise RuntimeError(f"ElevenLabs TTS failed: {response.status_code}")

    return response.content
