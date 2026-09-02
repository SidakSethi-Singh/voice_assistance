# 🌌 Aether — Real-Time Voice Assistant

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.14-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![WebSockets](https://img.shields.io/badge/WebSockets-Full--Duplex-010101?logo=socketdotio&logoColor=white)](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API)
[![Google Gemini](https://img.shields.io/badge/LLM-Google%20Gemini-4285F4?logo=google&logoColor=white)](https://aistudio.google.com)
[![Deepgram](https://img.shields.io/badge/STT-Deepgram%20Nova--2-13EF95?logo=deepgram&logoColor=black)](https://deepgram.com)
[![ElevenLabs](https://img.shields.io/badge/TTS-ElevenLabs-black?logo=elevenlabs&logoColor=white)](https://elevenlabs.io)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A high-performance, full-duplex conversational voice assistant engineered for **ultra-low latency**, **live streaming speech-to-text**, **native LLM tool calling**, **progressive sentence audio playback**, and **seamless barge-in (interruption) handling**.

---

## 🌟 Key Highlights & Differentiators

Unlike traditional voice assistants that operate on rigid *"record → upload → transcribe → wait → LLM → synthesize → play"* pipelines, **Aether** is built as a live, bidirectional conversational loop:
- 🎙️ **Streaming STT:** Streams 16kHz linear PCM audio directly over WebSockets as you talk.
- ⚡ **Sub-1.5s Response Latency:** Employs progressive sentence buffering — audio playback begins playing chunk-by-chunk on the first sentence before full text generation finishes.
- 🛠️ **3 Real Native Tools (No Mocks):** Live global weather via Open-Meteo, persistent SQLite task/reminder database, and semantic vector RAG over local documents.
- 🛑 **Graceful Barge-In Handling:** Instant dual cancellation (backend task abort + Web Audio buffer purge) with acoustic self-echo isolation so the assistant never interrupts itself.
- 🔊 **Hands-Free Wake-Word:** Dual-tone activation chime triggered on *"Hey Aether"*.
- 🌐 **Instant Zero-Key Fallback:** Works immediately in any browser using Web Speech API even before entering third-party cloud keys.

---

## 🏗️ System Architecture

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      Browser UI / Web Audio Client                     │
 │  - AudioWorklet / MediaStream mic capture (16kHz PCM Linear)           │
 │  - Low-latency AudioContext Chunk Player (queue & instant flush)       │
 │  - Interactive Visualizer: Glowing Orb / Waveform / State Indicators   │
 │  - Live Transcript Drawer & Tool Execution Inspector & Latency HUD     │
 └───────────────────────────────▲──┬─────────────────────────────────────┘
                                 │  │ Full-Duplex WebSocket (/ws/voice)
                                 │  ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                   FastAPI Async WebSocket Orchestrator                 │
 │                                                                        │
 │  ┌───────────────────────┐  ┌──────────────────┐  ┌─────────────────┐ │
 │  │ 1. Streaming STT      │  │ 2. Tool-Calling  │  │ 3. Streaming    │ │
 │  │    (Deepgram Nova-2 / │  │    LLM Engine    │  │    TTS Engine   │ │
 │  │    Web Speech API)    │  │ (Gemini 3.1 Flash│  │  (ElevenLabs /  │ │
 │  └───────────┬───────────┘  │  Auto-Failover)  │  │  Sentence Buff) │ │
 │              │              └────────▲───┬─────┘  └────────┬────────┘ │
 │              ▼                       │   │                 │          │
 │     [Transcript Router] ─────────────┘ [Sentence Buffer] ──┘          │
 │              │                                                        │
 │              ▼                                                        │
 │     [Barge-In Detector] ───► [Cancellation Event / Task Abort]        │
 └──────────────────────────────────────┬─────────────────────────────────┘
                                        ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                             Real Tools                                 │
 │  1. Live Weather Tool: Open-Meteo API (real-time temperature & forecast│
 │  2. Reminders & Tasks DB: SQLite with persistent CRUD & status filter  │
 │  3. Local Knowledge RAG Tool: Local embedded vector store & retriever  │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Complete Tech Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Backend Framework** | **Python 3.10+ / FastAPI** | High-performance asynchronous API & WebSocket orchestrator |
| **Server Runtime** | **Uvicorn** | ASGI server with high-concurrency WebSocket connection pool |
| **Transport** | **WebSockets (`/ws/voice`)** | Full-duplex, low-overhead bidirectional streaming |
| **LLM Engine** | **Google Gemini (`gemini-3.1-flash-lite`)** | Structured function/tool calling, SSE token streaming, multi-model auto-failover |
| **Speech-to-Text (STT)** | **Deepgram Nova-2 WebSocket + Web Speech API** | 16kHz linear PCM streaming STT with live interim results and VAD |
| **Text-to-Speech (TTS)** | **ElevenLabs WebSocket + Web Speech Synthesis** | Progressive sentence-buffered audio streaming |
| **Database** | **SQLite (`data/reminders.db`)** | Persistent storage for reminders and tasks (full CRUD) |
| **Vector RAG Engine** | **NumPy + Custom Cosine Scoring** | Semantic document chunking and vector retrieval over local markdown files |
| **Frontend** | **Vanilla HTML5, Glassmorphic CSS3, JavaScript** | Glowing audio-reactive voice orb, real-time waveform canvas, latency telemetry HUD |
| **Web Audio API** | **AudioContext & ScriptProcessor** | 16kHz PCM downsampling, microphone stream analyser, and progressive chunk player |
| **Build Assistant** | **Google Antigravity (Gemini 3.7 Flash)** | Architecture design, test harnesses, and end-to-end integration |

---

## ⚡ The 3 Real Tools (Zero Mocks)

### 1. 🌦️ Live Global Weather Tool (`backend/tools/weather_tool.py`)
- **API:** Open-Meteo Geocoding & Weather Forecast APIs (Free, high accuracy).
- **Capabilities:** Resolves coordinates for any city worldwide, returning current temperature (°C/°F), weather condition (Clear, Rainy, Overcast, etc.), wind speed, humidity, precipitation, and multi-day daily forecasts.
- **Example Voice Query:** *"What's the weather in Tokyo right now?"*

### 2. 📝 Persistent Reminders & Tasks DB (`backend/tools/reminder_tool.py`)
- **Database:** SQLite (`data/reminders.db`) with automatic schema initialization.
- **Capabilities:** Full CRUD actions (`create`, `list`, `complete`, `delete`) with priority tagging (`low`, `medium`, `high`) and due-date tracking.
- **Example Voice Query:** *"Set a high-priority reminder to review the pull request tomorrow at 10 AM."*

### 3. 🔍 Local Document Knowledge RAG Tool (`backend/tools/rag_tool.py`)
- **Knowledge Base:** Local markdown documents in `data/knowledge/` (Smart Home Hub, Office Facilities & Wi-Fi, Assistant Architecture).
- **Capabilities:** Chunks text by section headers, tokenizes content, and performs cosine vector similarity search to extract verified internal facts.
- **Example Voice Query:** *"What is the guest Wi-Fi password?"* or *"What devices are in the movie night scene?"*

---

## 🚀 Step-by-Step Installation & Local Setup

Follow these instructions to run the voice assistant on your local machine:

### 1. Prerequisites
- **Python 3.10 or higher** (Tested on Python 3.10, 3.11, 3.12, 3.14).
- **Git** installed on your system.

### 2. Clone the Repository
```bash
git clone https://github.com/SidakSethi-Singh/voice_assistance.git
cd voice_assistance
```

### 3. Create and Activate a Virtual Environment
- **On Windows (PowerShell):**
  ```powershell
  python -m venv venv
  .\venv\Scripts\Activate.ps1
  ```
- **On macOS / Linux:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Configure API Keys
Create your local environment file:
- **On Windows:** `copy .env.example .env`
- **On macOS/Linux:** `cp .env.example .env`

Open [`.env`](.env) and add your keys:
```ini
# Google Gemini API Key (Required for LLM & Tools - Free from https://aistudio.google.com)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.1-flash-lite

# Deepgram Streaming STT (Optional - Free from https://console.deepgram.com)
DEEPGRAM_API_KEY=your_deepgram_api_key_here

# ElevenLabs Streaming TTS (Optional - Free from https://elevenlabs.io)
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
ELEVENLABS_MODEL_ID=eleven_turbo_v2_5

# Server Configuration
HOST=0.0.0.0
PORT=8000
DEBUG=true
```
*(Note: If Deepgram or ElevenLabs keys are left blank, the app automatically runs using the built-in browser Web Speech STT/TTS engine).*

---

## 💻 Running the Assistant

Start the application server:
```bash
python backend/main.py
```
Or with Uvicorn:
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser at **`http://localhost:8000`**.

### How to Interact:
1. Click **"Start Voice Session"** (allow microphone permissions when prompted).
2. **Hands-Free Wake Word:** Say **"Hey Aether"** or directly ask your question.
3. **Barge-In / Interruption:** Whenever the assistant is speaking, simply speak over it or press the **`Spacebar`** / click **"Interrupt"** — the assistant instantly stops audio playback and listens to your new question.

---

## 🧪 Running the Automated Test Suite

The project includes an end-to-end unit and integration test suite:

```bash
python -m pytest tests/ -v
```

### Test Coverage Summary:
```text
tests/test_pipeline.py::test_health_endpoint PASSED          [ 14%]
tests/test_pipeline.py::test_llm_tool_dispatch PASSED        [ 28%]
tests/test_pipeline.py::test_barge_in_cancellation_logic     [ 42%]
tests/test_pipeline.py::test_wake_word_detection PASSED      [ 57%]
tests/test_tools.py::test_weather_tool_live PASSED           [ 71%]
tests/test_tools.py::test_reminder_tool_crud PASSED          [ 85%]
tests/test_tools.py::test_rag_tool_retrieval PASSED          [100%]

======================== 7 passed in 4.33s ========================
```

---

## ☁️ 1-Click Deployment Guide (Render)

This repository is pre-configured with [`render.yaml`](render.yaml) and [`Procfile`](Procfile) for 1-click deployment on Render:

1. Push your repository to GitHub.
2. Log in to **[dashboard.render.com](https://dashboard.render.com)**.
3. Click **New +** $\rightarrow$ **Web Service** $\rightarrow$ select your GitHub repository.
4. Set:
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
5. Under **Environment Variables**, add `GEMINI_API_KEY` and `GEMINI_MODEL=gemini-3.1-flash-lite`.
6. Click **Create Web Service**.

Your live assistant will be live with full WebSocket and HTTPS support at `https://your-service-name.onrender.com`.

---

## 📂 Project Structure

```
voice_assistance/
├── backend/
│   ├── __init__.py
│   ├── config.py              # Dynamic configuration & environment loader
│   ├── main.py                # FastAPI app, static assets & WebSocket voice endpoint
│   ├── stt_streamer.py        # Deepgram Nova-2 streaming WebSocket handler
│   ├── llm_engine.py          # Gemini API, function calling & auto-failover engine
│   ├── tts_streamer.py        # ElevenLabs streaming WebSocket TTS handler
│   ├── pipeline_manager.py    # Session orchestrator, state machine & barge-in logic
│   └── tools/
│       ├── __init__.py
│       ├── weather_tool.py    # Live Open-Meteo weather & forecast API
│       ├── reminder_tool.py   # SQLite persistent task database (CRUD)
│       └── rag_tool.py        # Local markdown document vector RAG retriever
├── frontend/
│   ├── index.html             # Glassmorphic dashboard UI
│   ├── css/
│   │   └── style.css          # Responsive dark styling & glowing visualizer
│   └── js/
│       ├── app.js             # UI controller, waveform visualizer & telemetry HUD
│       ├── audio_recorder.js  # 16kHz PCM linear microphone stream recorder
│       └── audio_player.js    # Progressive audio buffer player & instant flusher
├── data/
│   ├── knowledge/             # Local markdown RAG documents
│   │   ├── smart_home_devices.md
│   │   ├── office_faq_and_wifi.md
│   │   └── voice_assistant_manual.md
│   └── reminders.db           # SQLite database
├── tests/
│   ├── test_tools.py          # Tool unit tests
│   └── test_pipeline.py       # Integration, barge-in & wake-word tests
├── requirements.txt           # Python dependencies
├── Procfile                   # Process file for Render / Railway
├── render.yaml                # 1-click Render blueprint
├── .env.example               # Example environment variables
├── .gitignore                 # Protected secrets & build artifacts
└── README.md                  # Complete documentation
```

---

## 🤖 AI Assistant Attribution
Developed and pair-programmed with **Google Antigravity** using the **Gemini 3.7 Flash** agent for architecture design, tool-calling integration, low-latency streaming pipeline orchestration, and edge-case handling.
