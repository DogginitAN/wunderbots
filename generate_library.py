"""Batch generate episodes for the Wunderbots library.
Run from Nash with: python3 generate_library.py

Generates episode JSON + TTS audio for each scene, saves to library/.
The resulting JSON files ship with the repo — zero API calls on replay.
"""
import os, sys, json, re, time, base64

from prompts import STAGE_1_SYSTEM as STAGE1_SYSTEM, STAGE_1_USER as STAGE1_USER, STAGE_2_SYSTEM as STAGE2_SYSTEM, STAGE_2_USER as STAGE2_USER
from tts import build_expert_voice_map, generate_speech, EMOTION_DIRECTIONS
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get("GROK_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)
MODEL = os.environ.get("WUNDERBOTS_MODEL", "openai/gpt-oss-120b")
LIBRARY_DIR = os.path.join(os.path.dirname(__file__), "library")
os.makedirs(LIBRARY_DIR, exist_ok=True)

def slugify(text):
    t = text.lower().strip()
    t = re.sub(r'[^\w\s-]', '', t)
    t = re.sub(r'[\s_-]+', '-', t)
    return t[:60].strip('-')

def generate_episode_json(question):
    """Run the 2-stage prompt chain to generate episode JSON."""
    slug = slugify(question)
    path = os.path.join(LIBRARY_DIR, f"{slug}.json")
    
    # Check if JSON already exists (without audio)
    if os.path.exists(path):
        with open(path) as f:
            ep = json.load(f)
        if ep.get("acts"):
            print(f"  📄 JSON exists: {slug}")
            return ep, slug, path
    
    # Stage 1: Research & Outline
    print(f"  📝 Stage 1: Research & Outline...")
    t0 = time.time()
    r1 = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": STAGE1_SYSTEM},
            {"role": "user", "content": STAGE1_USER.format(question=question)},
        ],
        temperature=0.7,
        max_tokens=4096,
    )
    outline_text = r1.choices[0].message.content.strip()
    if "```json" in outline_text:
        outline_text = outline_text.split("```json")[1].split("```")[0].strip()
    elif "```" in outline_text:
        outline_text = outline_text.split("```")[1].split("```")[0].strip()
    outline = json.loads(outline_text)
    print(f"     Done ({time.time()-t0:.1f}s)")
    
    # Stage 2: Script Generation
    print(f"  🎬 Stage 2: Script Generation...")
    t1 = time.time()
    r2 = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": STAGE2_SYSTEM},
            {"role": "user", "content": STAGE2_USER.format(outline=json.dumps(outline, indent=2))},
        ],
        temperature=0.7,
        max_tokens=16384,
    )
    script_text = r2.choices[0].message.content.strip()
    if "```json" in script_text:
        script_text = script_text.split("```json")[1].split("```")[0].strip()
    elif "```" in script_text:
        script_text = script_text.split("```")[1].split("```")[0].strip()
    episode = json.loads(script_text)
    print(f"     Done ({time.time()-t1:.1f}s)")
    
    # Add voice map
    episode["voice_map"] = build_expert_voice_map(episode.get("characters", {}))
    
    # Save JSON (without audio yet)
    with open(path, "w") as f:
        json.dump(episode, f, indent=2)
    print(f"  💾 Saved: {path}")
    
    return episode, slug, path


def generate_audio_for_episode(episode, slug, path):
    """Generate TTS audio for all dialogue scenes and embed in the JSON."""
    voice_map = episode.get("voice_map", {})
    audio_cache = episode.get("audio_cache", {})
    
    total_scenes = 0
    cached_scenes = 0
    generated_scenes = 0
    
    for aI, act in enumerate(episode.get("acts", [])):
        for sI, scene in enumerate(act.get("scenes", [])):
            if scene.get("type") not in ("dialogue", "explanation"):
                continue
            if not scene.get("text"):
                continue
            
            total_scenes += 1
            key = f"{aI}-{sI}"
            
            if key in audio_cache:
                cached_scenes += 1
                continue
            
            voice = voice_map.get(scene.get("character", ""), "troy")
            emotion = scene.get("emotion", "neutral")
            text = scene["text"]
            
            try:
                audio_bytes = generate_speech(text, voice, emotion)
                audio_cache[key] = base64.b64encode(audio_bytes).decode("ascii")
                generated_scenes += 1
                
                # Rate limit — Groq free tier is tight
                time.sleep(0.5)
                
            except Exception as e:
                print(f"    ⚠️  TTS failed for {key}: {e}")
                # If we hit rate limits, stop TTS generation
                if "rate" in str(e).lower() or "limit" in str(e).lower():
                    print("    🛑 Rate limited — stopping TTS generation")
                    break
        else:
            continue
        break  # break outer loop if inner loop broke
    
    episode["audio_cache"] = audio_cache
    
    # Save updated JSON with audio
    with open(path, "w") as f:
        json.dump(episode, f)
    
    filesize = os.path.getsize(path)
    print(f"  🔊 Audio: {generated_scenes} generated, {cached_scenes} cached, {total_scenes} total")
    print(f"  📦 File size: {filesize / 1024:.0f} KB")
    return generated_scenes


if __name__ == "__main__":
    QUESTIONS = [
        "Why is the sky blue?",
        "Why do volcanoes erupt?",
        "How do airplanes fly?",
        "Why do we dream?",
        "How do rainbows form?",
    ]
    
    # Allow filtering from command line
    if len(sys.argv) > 1:
        if sys.argv[1] == "--text-only":
            # Generate just the episode JSON, no audio
            for q in QUESTIONS:
                print(f"\n{'='*60}")
                print(f"📚 {q}")
                try:
                    ep, slug, path = generate_episode_json(q)
                    scenes = sum(len(a['scenes']) for a in ep.get('acts', []))
                    print(f"  ✅ {scenes} scenes, {len(ep.get('characters', {}))} characters")
                except Exception as e:
                    print(f"  ❌ Error: {e}")
            print(f"\n{'='*60}")
            print("Done! Run without --text-only to add audio.")
            sys.exit(0)
        else:
            QUESTIONS = [" ".join(sys.argv[1:])]
    
    for q in QUESTIONS:
        print(f"\n{'='*60}")
        print(f"📚 {q}")
        try:
            ep, slug, path = generate_episode_json(q)
            scenes = sum(len(a['scenes']) for a in ep.get('acts', []))
            print(f"  ✅ {scenes} scenes, {len(ep.get('characters', {}))} characters")
            
            print(f"  🎙️ Generating audio...")
            generate_audio_for_episode(ep, slug, path)
        except Exception as e:
            print(f"  ❌ Error: {e}")
            import traceback; traceback.print_exc()
    
    print(f"\n{'='*60}")
    print("Library generation complete!")
    print(f"Episodes in library: {len(os.listdir(LIBRARY_DIR))}")
