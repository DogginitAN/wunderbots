"""Wunderbots TTS — Groq Orpheus voice generation"""
import os
import io
import re
import logging
from openai import OpenAI

log = logging.getLogger("wunderbots.tts")

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ.get("GROK_API_KEY"),
)

TTS_MODEL = "canopylabs/orpheus-v1-english"
MAX_CHARS = 200  # Groq Orpheus per-request limit

# ─── VOICE MAPPING ───────────────────────────────────────────────────────────
# Groq Orpheus voices: troy, hannah, austin, tara, leah, jess
# Open-source Orpheus voices: tara, leah, jess, leo, dan, mia, zac, zoe
# Groq subset is troy, hannah, austin + possibly tara, leah, jess

# Guide characters — consistent across all episodes
GUIDE_VOICES = {
    "nova": "tara",      # confident, clear, leader energy
    "bolt": "austin",    # energetic, good for silly delivery
    "pip":  "leah",      # warm, gentle, perfect for shy genius
}

# Expert voice pool — rotated based on expert index
EXPERT_VOICES = ["troy", "hannah", "jess"]

# ─── EMOTION → VOCAL DIRECTION ──────────────────────────────────────────────
EMOTION_DIRECTIONS = {
    "neutral":    "",
    "excited":    "[excited] ",
    "thinking":   "[thoughtful] ",
    "surprised":  "[surprised] ",
    "happy":      "[cheerful] ",
    "explaining": "[warm] ",
    "silly":      "[playful] ",
    "shy":        "[soft] ",
}


def get_voice_for_character(character_id: str, characters: dict, expert_index: int = 0) -> str:
    """Determine which Orpheus voice to use for a character."""
    if character_id in GUIDE_VOICES:
        return GUIDE_VOICES[character_id]
    
    # For experts, rotate through the pool
    return EXPERT_VOICES[expert_index % len(EXPERT_VOICES)]


def build_expert_voice_map(characters: dict) -> dict:
    """Build a character_id → voice mapping for the whole episode."""
    voice_map = dict(GUIDE_VOICES)
    expert_idx = 0
    for char_id, char_data in characters.items():
        if char_id not in voice_map:
            voice_map[char_id] = EXPERT_VOICES[expert_idx % len(EXPERT_VOICES)]
            expert_idx += 1
    return voice_map


def split_text(text: str, max_len: int = MAX_CHARS) -> list[str]:
    """Split text into chunks under max_len at sentence boundaries."""
    if len(text) <= max_len:
        return [text]
    
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break
        
        # Find best split point (sentence boundary) before max_len
        split_at = max_len
        for sep in ['. ', '! ', '? ', '— ', ', ']:
            idx = remaining[:max_len].rfind(sep)
            if idx > 0:
                split_at = idx + len(sep)
                break
        
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    
    return chunks


def generate_speech(text: str, voice: str, emotion: str = "neutral") -> bytes:
    """Generate speech audio for a single text chunk.
    Returns WAV bytes.
    """
    direction = EMOTION_DIRECTIONS.get(emotion, "")
    input_text = f"{direction}{text}" if direction else text
    
    # Split if over limit
    chunks = split_text(input_text)
    
    all_audio = bytearray()
    for chunk in chunks:
        try:
            response = client.audio.speech.create(
                model=TTS_MODEL,
                voice=voice,
                input=chunk,
                response_format="wav",
            )
            all_audio.extend(response.content)
        except Exception as e:
            log.error(f"TTS error for chunk '{chunk[:50]}...': {e}")
            raise
    
    return bytes(all_audio)


def generate_scene_audio(scene: dict, voice_map: dict) -> bytes | None:
    """Generate audio for a single scene. Returns WAV bytes or None if scene has no dialogue."""
    if scene.get("type") not in ("dialogue", "explanation"):
        return None
    
    text = scene.get("text", "")
    if not text:
        return None
    
    character_id = scene.get("character", "")
    voice = voice_map.get(character_id, "troy")
    emotion = scene.get("emotion", "neutral")
    
    return generate_speech(text, voice, emotion)
