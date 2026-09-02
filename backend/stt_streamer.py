import json
import asyncio
import logging
import websockets
from typing import AsyncGenerator, Optional, Callable, Dict, Any

logger = logging.getLogger("voice_assistant.stt")

class DeepgramSTTStreamer:
    """
    Manages a live bidirectional WebSocket session with Deepgram STT.
    Accepts 16kHz 16-bit linear PCM audio chunks and yields real-time interim & final transcripts.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._is_running = False
        self._receive_task: Optional[asyncio.Task] = None
        self._event_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

    async def start(self) -> bool:
        """Connect to Deepgram streaming WebSocket."""
        if not self.api_key:
            logger.warning("Deepgram API Key is missing. STT will operate in offline/mock mode.")
            return False

        url = (
            "wss://api.deepgram.com/v1/listen?"
            "encoding=linear16&"
            "sample_rate=16000&"
            "channels=1&"
            "interim_results=true&"
            "smart_format=true&"
            "endpointing=300&"
            "vad_events=true"
        )
        headers = {
            "Authorization": f"Token {self.api_key}"
        }

        try:
            self.ws = await websockets.connect(url, extra_headers=headers)
            self._is_running = True
            self._receive_task = asyncio.create_task(self._listen_loop())
            logger.info("Successfully connected to Deepgram Streaming STT WebSocket.")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Deepgram STT: {e}")
            self._is_running = False
            return False

    async def send_audio_chunk(self, pcm_data: bytes):
        """Send raw PCM audio bytes to Deepgram."""
        if self._is_running and self.ws:
            try:
                await self.ws.send(pcm_data)
            except Exception as e:
                logger.error(f"Error sending audio chunk to Deepgram: {e}")

    async def _listen_loop(self):
        """Receive transcript & VAD messages from Deepgram."""
        try:
            while self._is_running and self.ws:
                message = await self.ws.recv()
                data = json.loads(message)

                msg_type = data.get("type")
                if msg_type == "SpeechStarted":
                    await self._event_queue.put({
                        "type": "speech_started",
                        "timestamp": data.get("timestamp", 0)
                    })
                    continue

                if "channel" in data:
                    channel = data["channel"]
                    alternatives = channel.get("alternatives", [])
                    if alternatives:
                        transcript = alternatives[0].get("transcript", "")
                        is_final = data.get("is_final", False)
                        speech_final = data.get("speech_final", False)

                        if transcript.strip():
                            await self._event_queue.put({
                                "type": "transcript",
                                "text": transcript.strip(),
                                "is_final": is_final,
                                "speech_final": speech_final,
                                "confidence": alternatives[0].get("confidence", 0.0)
                            })
        except websockets.ConnectionClosed:
            logger.info("Deepgram STT connection closed.")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in Deepgram STT receive loop: {e}")
        finally:
            self._is_running = False

    async def events(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Yield parsed transcript and speech events."""
        while self._is_running or not self._event_queue.empty():
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=0.1)
                yield event
            except asyncio.TimeoutError:
                if not self._is_running and self._event_queue.empty():
                    break
                continue

    async def close(self):
        """Cleanly close the STT stream."""
        self._is_running = False
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
        if self.ws:
            try:
                # Send close stream message to Deepgram
                await self.ws.send(json.dumps({"type": "CloseStream"}))
                await self.ws.close()
            except Exception:
                pass
            self.ws = None
