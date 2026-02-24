"""Wunderbots server — Starlette + Groq"""
import os
import json
import time
import logging
from starlette.applications import Starlette
from starlette.responses import JSONResponse, FileResponse
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from openai import OpenAI
from prompts import STAGE_1_SYSTEM, STAGE_1_USER, STAGE_2_SYSTEM, STAGE_2_USER

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("wunderbots")

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ.get("GROK_API_KEY"),
)
MODEL = os.environ.get("WUNDERBOTS_MODEL", "openai/gpt-oss-120b")


def clean_json(text: str) -> str:
    """Strip markdown fences if present."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return t


def generate_episode(question: str) -> dict:
    """Run the 2-stage prompt chain. Returns episode JSON."""
    t0 = time.time()

    # Stage 1: Research & Outline
    log.info(f"Stage 1: Generating outline for '{question}'...")
    s1 = client.chat.completions.create(
        model=MODEL,
        max_tokens=4096,
        temperature=0.7,
        messages=[
            {"role": "system", "content": STAGE_1_SYSTEM},
            {"role": "user", "content": STAGE_1_USER.format(question=question)},
        ],
    )
    outline_text = clean_json(s1.choices[0].message.content)
    outline = json.loads(outline_text)
    s1_time = time.time() - t0
    log.info(f"Stage 1 done: {s1_time:.1f}s, experts: {[e['name'] for e in outline.get('experts', [])]}")

    # Stage 2: Script Generation
    t1 = time.time()
    log.info("Stage 2: Generating script...")
    s2 = client.chat.completions.create(
        model=MODEL,
        max_tokens=16384,
        temperature=0.7,
        messages=[
            {"role": "system", "content": STAGE_2_SYSTEM},
            {"role": "user", "content": STAGE_2_USER.format(outline=outline_text)},
        ],
    )
    script_text = clean_json(s2.choices[0].message.content)
    script = json.loads(script_text)
    s2_time = time.time() - t1
    total_scenes = sum(len(a["scenes"]) for a in script.get("acts", []))
    log.info(f"Stage 2 done: {s2_time:.1f}s, {total_scenes} scenes")
    log.info(f"Total generation: {time.time() - t0:.1f}s")

    return script


# ─── ROUTES ──────────────────────────────────────────────────────────────────

async def homepage(request):
    return FileResponse(
        os.path.join(os.path.dirname(__file__), "static", "index.html"),
        media_type="text/html",
    )


async def health(request):
    return JSONResponse({"status": "ok", "model": MODEL})


async def api_generate(request):
    try:
        body = await request.json()
        question = body.get("question", "").strip()
        if not question:
            return JSONResponse({"error": "No question provided"}, status_code=400)
        if len(question) > 200:
            return JSONResponse({"error": "Question too long"}, status_code=400)

        episode = generate_episode(question)
        return JSONResponse(episode)

    except json.JSONDecodeError as e:
        log.error(f"JSON parse error from LLM: {e}")
        return JSONResponse(
            {"error": "Failed to generate valid episode. Try again!"},
            status_code=500,
        )
    except Exception as e:
        log.error(f"Generation error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


static_dir = os.path.join(os.path.dirname(__file__), "static")

routes = [
    Route("/", homepage),
    Route("/health", health),
    Route("/api/generate", api_generate, methods=["POST"]),
    Mount("/static", StaticFiles(directory=static_dir), name="static"),
]

app = Starlette(routes=routes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
