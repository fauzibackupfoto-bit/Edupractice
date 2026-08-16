"""
TTS backend for NUR-AI / TOEFL ITP app.

Wraps Microsoft Edge's neural voices (via the edge-tts library) behind a
simple HTTP endpoint so a static HTML/JS frontend can request MP3 audio
without needing to speak the (unofficial) websocket protocol itself.

Run locally:
    pip install -r requirements.txt
    uvicorn server:app --host 0.0.0.0 --port 8000

Then in the browser, GET requests like:
    http://localhost:8000/tts?text=Hello%20there&voice=female

Deploy for free on Render / Railway / Fly.io (any host that allows
outbound network access) since GitHub Pages / static hosting can't run this.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import edge_tts
import hashlib
import io
import os

app = FastAPI(title="NUR-AI TTS backend")

# Allow the static HTML app (served from any origin) to call this backend.
# Lock this down to your real domain once you deploy, e.g. ["https://your-app.com"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Map our simple gender labels -> specific Edge neural voices.
# Full voice list: `edge-tts --list-voices`
VOICE_MAP = {
    "female": "en-US-AriaNeural",
    "male": "en-US-GuyNeural",
    # Indonesian voices, in case you want native-language narration too:
    "female-id": "id-ID-GadisNeural",
    "male-id": "id-ID-ArdiNeural",
}

# Simple on-disk cache so repeated lines (same text + voice) aren't
# re-synthesized every time — saves latency and bandwidth.
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def cache_path(text: str, voice: str) -> str:
    key = hashlib.sha256(f"{voice}|{text}".encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{key}.mp3")


@app.get("/tts")
async def tts(
    text: str = Query(..., min_length=1, max_length=2000),
    voice: str = Query("female", description="one of: " + ", ".join(VOICE_MAP)),
    rate: str = Query("-5%", description="edge-tts rate offset, e.g. '-5%', '+10%'"),
):
    edge_voice = VOICE_MAP.get(voice)
    if not edge_voice:
        raise HTTPException(400, f"Unknown voice '{voice}'. Options: {list(VOICE_MAP)}")

    path = cache_path(text, edge_voice + rate)
    if not os.path.exists(path):
        communicate = edge_tts.Communicate(text, edge_voice, rate=rate)
        with open(path, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])

    with open(path, "rb") as f:
        audio_bytes = f.read()

    return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/mpeg")


@app.get("/health")
def health():
    return {"status": "ok"}
