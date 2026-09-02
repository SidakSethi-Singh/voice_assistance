import os
import sys
from pathlib import Path

# Ensure project root is in sys.path for direct python backend/main.py execution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.pipeline_manager import SessionPipeline
from backend.tools.rag_tool import rag_engine

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.DEBUG else logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("voice_assistant.main")

app = FastAPI(title="Real-Time Voice Assistant API", version="1.0.0")

# CORS middleware for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

@app.get("/api/health")
async def health_check():
    """Health status and configuration check."""
    return {
        "status": "online",
        "stt_configured": bool(settings.DEEPGRAM_API_KEY),
        "llm_configured": bool(settings.GEMINI_API_KEY),
        "tts_configured": bool(settings.ELEVENLABS_API_KEY),
        "gemini_model": settings.GEMINI_MODEL,
        "knowledge_chunks": len(rag_engine.chunks)
    }

@app.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket):
    """
    Full-duplex WebSocket endpoint for real-time voice streaming:
    Client sends PCM audio chunks or control messages;
    Server sends live STT transcripts, tool execution updates, TTS audio chunks, and barge-in signals.
    """
    await websocket.accept()
    logger.info("Client connected to voice WebSocket.")
    pipeline = SessionPipeline(websocket)
    try:
        await pipeline.start()
    except WebSocketDisconnect:
        logger.info("Client disconnected normally.")
    except Exception as e:
        logger.error(f"WebSocket session error: {e}")
    finally:
        logger.info("Cleaned up voice session pipeline.")

# Mount frontend static assets
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/")
async def serve_index():
    """Serve the single-page voice assistant Web UI."""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse({"message": "Frontend not found. Please check frontend/index.html"}, status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
