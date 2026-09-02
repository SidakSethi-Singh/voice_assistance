import time
import json
import asyncio
import logging
from typing import Optional, Dict, Any
from fastapi import WebSocket

from backend.config import settings
from backend.stt_streamer import DeepgramSTTStreamer
from backend.llm_engine import GeminiLLMEngine
from backend.tts_streamer import ElevenLabsTTSStreamer

logger = logging.getLogger("voice_assistant.pipeline")

class SessionPipeline:
    """
    Coordinates full-duplex streaming conversational loop for a single WebSocket client.
    Handles STT -> Gemini Tool Calling -> Streaming TTS -> Barge-In interruption.
    """
    def __init__(self, client_ws: WebSocket):
        self.client_ws = client_ws
        self.stt: Optional[DeepgramSTTStreamer] = None
        self.llm = GeminiLLMEngine()
        self.tts = ElevenLabsTTSStreamer()

        self.state = "IDLE"  # IDLE, LISTENING, PROCESSING, SPEAKING, INTERRUPTED
        self.cancel_event = asyncio.Event()
        self.active_turn_task: Optional[asyncio.Task] = None

        self.speech_start_time: float = 0.0
        self.stt_final_time: float = 0.0

    async def send_client_json(self, data: Dict[str, Any]):
        """Send JSON message to client browser."""
        try:
            await self.client_ws.send_text(json.dumps(data))
        except Exception as e:
            logger.debug(f"Error sending message to client: {e}")

    async def send_client_bytes(self, data: bytes):
        """Send raw audio bytes to client browser."""
        try:
            await self.client_ws.send_bytes(data)
        except Exception as e:
            logger.debug(f"Error sending audio bytes to client: {e}")

    async def update_state(self, new_state: str):
        """Update and broadcast session state."""
        self.state = new_state
        await self.send_client_json({"type": "state_change", "state": self.state})

    async def trigger_barge_in(self, reason: str = "user_speech"):
        """
        Instantly interrupts current assistant response.
        Cancels in-flight LLM & TTS tasks and signals client to purge audio buffers.
        """
        if self.state in ["PROCESSING", "SPEAKING"]:
            logger.info(f"Barge-in triggered ({reason}). Interrupting assistant response.")
            self.cancel_event.set()

            # Tell client to immediately flush audio playback
            await self.send_client_json({
                "type": "barge_in",
                "message": "Assistant interrupted by user speech."
            })
            await self.update_state("INTERRUPTED")

            if self.active_turn_task and not self.active_turn_task.done():
                self.active_turn_task.cancel()

            # Short pause then return to listening
            await asyncio.sleep(0.05)
            self.cancel_event.clear()
            await self.update_state("LISTENING")

    async def handle_user_transcript(self, transcript: str):
        """Called when STT produces a final user utterance."""
        if not transcript.strip():
            return

        # Cancel any previous incomplete response
        if self.active_turn_task and not self.active_turn_task.done():
            self.cancel_event.set()
            self.active_turn_task.cancel()
            await asyncio.sleep(0.02)

        self.cancel_event.clear()
        self.active_turn_task = asyncio.create_task(self._process_turn(transcript))

    async def _process_turn(self, user_text: str):
        """Execute the turn: Send to LLM -> Stream tokens -> Stream TTS -> Send audio chunks."""
        t_start = time.perf_counter()
        metrics = {
            "stt_final_ms": round((time.perf_counter() - self.stt_final_time) * 1000, 1) if self.stt_final_time else 0,
            "llm_ttft_ms": 0,
            "tool_execution_ms": 0,
            "tts_ttfb_ms": 0,
            "total_turn_ms": 0
        }

        try:
            await self.update_state("PROCESSING")
            await self.send_client_json({
                "type": "processing_started",
                "user_text": user_text
            })

            first_token_received = False
            token_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

            # Callback when tool execution occurs
            def on_tool_call(tool_name: str, args: Dict[str, Any], result: Dict[str, Any]):
                asyncio.create_task(self.send_client_json({
                    "type": "tool_executed",
                    "tool_name": tool_name,
                    "args": args,
                    "result": result
                }))

            async def text_producer():
                nonlocal first_token_received
                try:
                    async for token in self.llm.stream_chat(
                        user_message=user_text,
                        cancel_event=self.cancel_event,
                        on_tool_call=on_tool_call
                    ):
                        if not first_token_received:
                            first_token_received = True
                            metrics["llm_ttft_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
                            await self.send_client_json({
                                "type": "metrics_update",
                                "metrics": metrics
                            })

                        # Stream partial text response to frontend
                        await self.send_client_json({
                            "type": "assistant_chunk",
                            "text": token
                        })
                        await token_queue.put(token)
                finally:
                    await token_queue.put(None)

            # Start LLM stream in background task
            producer_task = asyncio.create_task(text_producer())

            # Async generator reading from token_queue for TTS
            async def text_stream_gen():
                while True:
                    if self.cancel_event.is_set():
                        break
                    tok = await token_queue.get()
                    if tok is None:
                        break
                    yield tok

            # Stream audio progressively to frontend
            first_audio_chunk = False
            async for audio_chunk in self.tts.stream_audio_from_text_generator(
                text_stream_gen(),
                cancel_event=self.cancel_event
            ):
                if self.cancel_event.is_set():
                    break

                if not first_audio_chunk:
                    first_audio_chunk = True
                    metrics["tts_ttfb_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
                    await self.update_state("SPEAKING")

                await self.send_client_bytes(audio_chunk)

            await producer_task

            if not self.cancel_event.is_set():
                metrics["total_turn_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
                await self.send_client_json({
                    "type": "turn_completed",
                    "metrics": metrics
                })
                await self.update_state("LISTENING")

        except asyncio.CancelledError:
            logger.info("Turn processing was cancelled (barge-in).")
        except Exception as e:
            logger.error(f"Error in turn processing: {e}")
            await self.send_client_json({"type": "error", "message": str(e)})
            await self.update_state("LISTENING")

    async def start(self):
        """Initialize STT and start listening for audio stream from client."""
        await self.update_state("LISTENING")

        # Initialize STT streamer
        self.stt = DeepgramSTTStreamer(api_key=settings.DEEPGRAM_API_KEY)
        stt_connected = await self.stt.start()

        if not stt_connected:
            await self.send_client_json({
                "type": "warning",
                "message": "Deepgram STT is running in simulated/mock mode (add DEEPGRAM_API_KEY to .env for live speech)."
            })

        # Background task for consuming STT events
        async def stt_event_consumer():
            if not self.stt:
                return
            async for event in self.stt.events():
                ev_type = event.get("type")

                if ev_type == "speech_started":
                    # Instant barge-in trigger when user starts talking
                    if self.state in ["PROCESSING", "SPEAKING"]:
                        await self.trigger_barge_in(reason="speech_started")

                elif ev_type == "transcript":
                    text = event.get("text", "")
                    is_final = event.get("is_final", False)
                    speech_final = event.get("speech_final", False)

                    # Also trigger barge-in if we see interim speech while assistant is talking
                    if text and self.state in ["PROCESSING", "SPEAKING"]:
                        await self.trigger_barge_in(reason="interim_transcript")

                    # Emit transcript update to client
                    await self.send_client_json({
                        "type": "stt_transcript",
                        "text": text,
                        "is_final": is_final,
                        "speech_final": speech_final
                    })

                    if is_final or speech_final:
                        self.stt_final_time = time.perf_counter()
                        await self.handle_user_transcript(text)

        consumer_task = asyncio.create_task(stt_event_consumer())

        try:
            while True:
                # Receive messages from client browser
                message = await self.client_ws.receive()

                if "bytes" in message and message["bytes"]:
                    # Forward PCM audio chunk to STT
                    pcm_bytes = message["bytes"]
                    if self.stt:
                        await self.stt.send_audio_chunk(pcm_bytes)

                elif "text" in message and message["text"]:
                    data = json.loads(message["text"])
                    action = data.get("action")

                    if action == "manual_interrupt":
                        await self.trigger_barge_in(reason="manual_button")

                    elif action == "text_prompt":
                        # Support typed prompts as well for testing
                        prompt_text = data.get("text", "")
                        self.stt_final_time = time.perf_counter()
                        await self.handle_user_transcript(prompt_text)

                    elif action == "update_config":
                        # Allow dynamic API key updates from frontend settings modal
                        if "gemini_api_key" in data and data["gemini_api_key"]:
                            self.llm.api_key = data["gemini_api_key"]
                        if "elevenlabs_api_key" in data and data["elevenlabs_api_key"]:
                            self.tts.api_key = data["elevenlabs_api_key"]
                        if "deepgram_api_key" in data and data["deepgram_api_key"]:
                            if self.stt:
                                await self.stt.close()
                            self.stt = DeepgramSTTStreamer(api_key=data["deepgram_api_key"])
                            await self.stt.start()
                        await self.send_client_json({"type": "config_updated", "status": "ok"})

        except Exception as e:
            logger.info(f"WebSocket session ended: {e}")
        finally:
            if consumer_task and not consumer_task.done():
                consumer_task.cancel()
            if self.active_turn_task and not self.active_turn_task.done():
                self.active_turn_task.cancel()
            if self.stt:
                await self.stt.close()
