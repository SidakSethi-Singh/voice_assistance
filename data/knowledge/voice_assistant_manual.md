# Real-Time Voice Assistant Architecture & Features

## Core Pipeline Specs
- **Streaming STT:** Deepgram Nova-2 streaming WebSocket with 16kHz linear PCM audio capture and live VAD events.
- **LLM Intelligence:** Google Gemini with native structured tool calling and low-latency token streaming.
- **Streaming TTS:** ElevenLabs streaming WebSocket for ultra-low latency chunked audio playback.
- **Barge-In Mechanism:** Instant dual-side interruption handling. Backend fires an `asyncio.Event` cancellation to abort active LLM & TTS tasks while emitting `CLEAR_AUDIO` to the client to purge Web Audio buffers instantly without stutter.

## Real Tools Available
1. **Weather System:** Live global weather and multi-day forecasts via Open-Meteo.
2. **Task & Reminder Database:** Persistent SQLite task tracking with create, list, complete, and delete actions.
3. **Local Knowledge RAG Engine:** Fast semantic search over local documentation with vector cosine similarity.
