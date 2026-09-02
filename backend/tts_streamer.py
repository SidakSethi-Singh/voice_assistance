import json
import base64
import asyncio
import logging
import websockets
from typing import AsyncGenerator, Optional, Callable
from backend.config import settings

logger = logging.getLogger("voice_assistant.tts")

class ElevenLabsTTSStreamer:
    """
    Streams text to ElevenLabs WebSocket API and yields streaming MP3 audio chunks
    as fast as text sentences/phrases become available from the LLM.
    """
    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None
    ):
        self._api_key = api_key
        self._voice_id = voice_id
        self._model_id = model_id

    @property
    def api_key(self) -> str:
        return self._api_key or settings.ELEVENLABS_API_KEY

    @api_key.setter
    def api_key(self, val: str):
        self._api_key = val

    @property
    def voice_id(self) -> str:
        return self._voice_id or settings.ELEVENLABS_VOICE_ID or "21m00Tcm4TlvDq8ikWAM"

    @property
    def model_id(self) -> str:
        return self._model_id or settings.ELEVENLABS_MODEL_ID or "eleven_turbo_v2_5"

    async def stream_audio_from_text_generator(
        self,
        text_stream: AsyncGenerator[str, None],
        cancel_event: Optional[asyncio.Event] = None
    ) -> AsyncGenerator[bytes, None]:
        """
        Takes an async stream of text tokens/sentences, connects to ElevenLabs WebSocket,
        pipes text into the socket, and yields binary audio chunks progressively.
        """
        if not self.api_key:
            logger.warning("ElevenLabs API key is missing. Skipping live TTS audio streaming.")
            return

        ws_url = (
            f"wss://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream-input?"
            f"model_id={self.model_id}&output_format=mp3_44100_128"
        )
        headers = {
            "xi-api-key": self.api_key
        }

        audio_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()

        async def receive_audio_task(ws):
            try:
                while True:
                    if cancel_event and cancel_event.is_set():
                        break
                    message = await ws.recv()
                    data = json.loads(message)

                    # ElevenLabs returns base64 encoded audio in the "audio" key
                    audio_b64 = data.get("audio")
                    if audio_b64:
                        audio_bytes = base64.b64decode(audio_b64)
                        await audio_queue.put(audio_bytes)

                    if data.get("isFinal", False):
                        break
            except websockets.ConnectionClosed:
                pass
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error receiving audio from ElevenLabs: {e}")
            finally:
                await audio_queue.put(None)

        try:
            async with websockets.connect(ws_url, extra_headers=headers) as ws:
                # 1. Send BOS (Beginning of Stream) payload
                bos_message = {
                    "text": " ",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.8
                    },
                    "generation_config": {
                        "chunk_length_schedule": [120, 160, 250, 290]
                    },
                    "xi_api_key": self.api_key
                }
                await ws.send(json.dumps(bos_message))

                receiver = asyncio.create_task(receive_audio_task(ws))

                # 2. Feed text from LLM stream into ElevenLabs
                buffer = ""
                async for token in text_stream:
                    if cancel_event and cancel_event.is_set():
                        logger.info("TTS streaming cancelled by barge-in.")
                        break

                    buffer += token
                    # If we reach punctuation or a sentence break, send it immediately
                    if any(p in token for p in [".", "!", "?", "\n", ",", ";", ":"]) or len(buffer) > 40:
                        send_payload = {
                            "text": buffer + " ",
                            "try_trigger_generation": True
                        }
                        await ws.send(json.dumps(send_payload))
                        buffer = ""

                # Send remaining text
                if buffer.strip() and not (cancel_event and cancel_event.is_set()):
                    await ws.send(json.dumps({"text": buffer + " ", "try_trigger_generation": True}))

                # Send EOS (End of Stream)
                if not (cancel_event and cancel_event.is_set()):
                    await ws.send(json.dumps({"text": ""}))

                # 3. Yield audio chunks from the receiver queue
                while True:
                    if cancel_event and cancel_event.is_set():
                        break
                    try:
                        chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.1)
                        if chunk is None:
                            break
                        yield chunk
                    except asyncio.TimeoutError:
                        if receiver.done() and audio_queue.empty():
                            break
                        continue

                if not receiver.done():
                    receiver.cancel()

        except asyncio.CancelledError:
            logger.info("TTS task cancelled.")
        except Exception as e:
            logger.error(f"ElevenLabs TTS WebSocket error: {e}")
