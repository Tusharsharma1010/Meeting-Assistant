import asyncio
import logging
import json
import queue
import threading
import time
from typing import Dict, Optional, Callable, Any
from datetime import datetime

import numpy as np
from faster_whisper import WhisperModel

from .stream_manager import StreamManager


logger = logging.getLogger(__name__)


class EnhancedAudioProcessor:
    """
    Local audio processor using faster-whisper.

    Audio flow:

        WebSocket
            ↓
        PCM int16 chunks
            ↓
        StreamManager
            ↓
        Local audio buffer
            ↓
        faster-whisper
            ↓
        Transcript
    """

    def __init__(
        self,
        websocket: Any,
        client_id: str,
        on_transcript: Callable[[dict], None],
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self.websocket = websocket
        self.client_id = client_id
        self.on_transcript = on_transcript
        self.loop = loop or asyncio.get_event_loop()

        # ----------------------------------------------------
        # Audio state
        # ----------------------------------------------------

        self.current_audio_type = None
        self.current_chunk_audio_type = None
        self.current_sample_rate = 16000

        self.stream_manager = StreamManager()

        self.audio_queue = queue.Queue()

        self.is_running = True
        self.processing_thread = None

        self.last_audio_timestamp = time.time()

        self.silence_threshold = 0.01
        self.TIMEOUT_SECONDS = 60

        # ----------------------------------------------------
        # Whisper configuration
        # ----------------------------------------------------

        self.whisper_model_name = "base"

        logger.info(
            f"Loading local Whisper model: "
            f"{self.whisper_model_name}"
        )

        try:
            self.whisper_model = WhisperModel(
                self.whisper_model_name,
                device="cpu",
                compute_type="int8",
            )

            logger.info(
                "Local Whisper model loaded successfully."
            )

        except Exception as e:
            logger.error(
                f"Failed to load Whisper model: {e}",
                exc_info=True,
            )
            raise

        # ----------------------------------------------------
        # Transcription buffering
        # ----------------------------------------------------

        # Keep separate buffers for microphone and system audio.
        self.audio_buffers: Dict[str, bytearray] = {
            "microphone": bytearray(),
            "system": bytearray(),
        }

        # Transcribe approximately every 3 seconds.
        self.transcription_interval_seconds = 3

        self.last_transcription_time: Dict[str, float] = {
            "microphone": time.time(),
            "system": time.time(),
        }

        logger.info(
            f"EnhancedAudioProcessor initialized for "
            f"client: {self.client_id}"
        )

    # ========================================================
    # WebSocket message handling
    # ========================================================

    async def handle_message(self, message):
        """
        Handle incoming WebSocket messages.

        Supports:

        1. JSON audio metadata
        2. Binary PCM audio
        """

        try:

            # ------------------------------------------------
            # JSON message
            # ------------------------------------------------

            if isinstance(message, str):

                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    logger.error(
                        "Failed to parse WebSocket JSON message."
                    )
                    return

                if data.get("type") == "audio_meta":

                    audio_type = data.get("audioType")

                    if audio_type not in [
                        "microphone",
                        "system",
                    ]:
                        logger.error(
                            f"Invalid audio type received: "
                            f"{audio_type}"
                        )
                        return

                    self.current_chunk_audio_type = audio_type
                    self.current_audio_type = audio_type

                    self.current_sample_rate = int(
                        data.get("sampleRate", 16000)
                    )

                    logger.debug(
                        "Audio metadata received - "
                        f"type={audio_type}, "
                        f"sample_rate={self.current_sample_rate}"
                    )

                    return

            # ------------------------------------------------
            # Binary audio
            # ------------------------------------------------

            if isinstance(message, bytes):

                audio_type = (
                    self.current_chunk_audio_type
                    or self.current_audio_type
                    or "microphone"
                )

                if audio_type not in [
                    "microphone",
                    "system",
                ]:
                    logger.error(
                        f"Invalid audio type: {audio_type}"
                    )
                    return

                await self.process_chunk(
                    message,
                    audio_type,
                )

        except Exception as e:

            logger.error(
                f"Error handling WebSocket message: {e}",
                exc_info=True,
            )

    # ========================================================
    # Audio chunk processing
    # ========================================================

    async def process_chunk(
        self,
        audio_data: bytes,
        audio_type: str = "microphone",
    ):
        """
        Process a new PCM audio chunk.
        """

        try:

            if not self.is_running:
                return False

            if audio_type not in [
                "microphone",
                "system",
            ]:
                logger.error(
                    f"Invalid audio type: {audio_type}"
                )
                return False

            if not audio_data:
                return False

            # ------------------------------------------------
            # Convert PCM to numpy
            # ------------------------------------------------

            data = np.frombuffer(
                audio_data,
                dtype=np.int16,
            )

            if data.size == 0:
                return False

            # ------------------------------------------------
            # Audio level detection
            # ------------------------------------------------

            max_level = (
                np.max(np.abs(data)) / 32768.0
            )

            if max_level <= self.silence_threshold:

                logger.debug(
                    f"Ignoring silent {audio_type} audio chunk."
                )

                return True

            self.last_audio_timestamp = time.time()

            # ------------------------------------------------
            # Store in StreamManager
            # ------------------------------------------------

            await self.stream_manager.process_audio_chunk(
                client_id=self.client_id,
                audio_data=audio_data,
                audio_type=audio_type,
            )

            # ------------------------------------------------
            # Store in local Whisper buffer
            # ------------------------------------------------

            self.audio_buffers[audio_type].extend(
                audio_data
            )

            logger.debug(
                f"Buffered {len(audio_data)} bytes "
                f"of {audio_type} audio."
            )

            # ------------------------------------------------
            # Check whether enough audio exists
            # ------------------------------------------------

            sample_rate = self.current_sample_rate or 16000

            bytes_per_sample = 2

            required_bytes = int(
                self.transcription_interval_seconds
                * sample_rate
                * bytes_per_sample
            )

            current_buffer_size = len(
                self.audio_buffers[audio_type]
            )

            if current_buffer_size >= required_bytes:

                # Copy the audio from the buffer.
                audio_to_transcribe = bytes(
                    self.audio_buffers[audio_type]
                )

                # Clear the buffer.
                self.audio_buffers[audio_type].clear()

                # Transcribe asynchronously.
                asyncio.create_task(
                    self._transcribe_audio(
                        audio_to_transcribe,
                        audio_type,
                        sample_rate,
                    )
                )

            return True

        except Exception as e:

            logger.error(
                f"Error processing audio chunk: {e}",
                exc_info=True,
            )

            return False

    # ========================================================
    # Whisper transcription
    # ========================================================

    async def _transcribe_audio(
        self,
        audio_data: bytes,
        audio_type: str,
        sample_rate: int = 16000,
    ):
        """
        Transcribe PCM audio using local faster-whisper.
        """

        try:

            if not audio_data:
                return

            # ------------------------------------------------
            # Convert PCM int16 → float32
            # ------------------------------------------------

            audio_array = np.frombuffer(
                audio_data,
                dtype=np.int16,
            ).astype(np.float32)

            if audio_array.size == 0:
                return

            audio_array /= 32768.0

            # ------------------------------------------------
            # Whisper expects approximately 16 kHz audio.
            # ------------------------------------------------

            if sample_rate != 16000:

                logger.warning(
                    f"Received sample rate {sample_rate}. "
                    f"Whisper pipeline expects 16000 Hz."
                )

            # ------------------------------------------------
            # Run Whisper in a background thread.
            # ------------------------------------------------

            segments, info = await asyncio.to_thread(
                self.whisper_model.transcribe,
                audio_array,
                language="en",
                beam_size=5,
                vad_filter=True,
            )

            # ------------------------------------------------
            # Collect transcript
            # ------------------------------------------------

            transcript_parts = []

            for segment in segments:

                text = segment.text.strip()

                if text:
                    transcript_parts.append(text)

            transcript = " ".join(
                transcript_parts
            ).strip()

            if not transcript:
                logger.debug(
                    "Whisper returned no transcript."
                )
                return

            # ------------------------------------------------
            # Create transcript message
            # ------------------------------------------------

            message = {
                "type": "transcript",
                "text": transcript,
                "is_final": True,
                "confidence": None,
                "audioType": audio_type,
                "timestamp": datetime.now().isoformat(),
            }

            logger.info(
                f"Generated local Whisper transcript "
                f"for {self.client_id}: "
                f"{transcript[:100]}"
            )

            # ------------------------------------------------
            # Send transcript to WebSocket
            # ------------------------------------------------

            try:

                await self.send_websocket_message(
                    message
                )

            except Exception as ws_error:

                logger.error(
                    f"WebSocket transcript send error: "
                    f"{ws_error}"
                )

            # ------------------------------------------------
            # Send transcript to application callback
            # ------------------------------------------------

            try:

                result = self.on_transcript(
                    message
                )

                if asyncio.iscoroutine(result):
                    await result

            except Exception as callback_error:

                logger.error(
                    f"Transcript callback error: "
                    f"{callback_error}",
                    exc_info=True,
                )

        except Exception as e:

            logger.error(
                f"Whisper transcription error: {e}",
                exc_info=True,
            )

    # ========================================================
    # Legacy-compatible processing loop
    # ========================================================

    def _process_audio(self):
        """
        Background audio processing loop.

        Audio is primarily processed by process_chunk().
        This loop remains available for compatibility with
        the existing processor lifecycle.
        """

        logger.info(
            f"Audio processing loop started for "
            f"client: {self.client_id}"
        )

        try:

            while self.is_running:

                try:

                    audio_type, chunk = (
                        self.audio_queue.get(
                            timeout=0.1
                        )
                    )

                except queue.Empty:

                    if (
                        time.time()
                        - self.last_audio_timestamp
                        > self.TIMEOUT_SECONDS
                    ):

                        logger.warning(
                            "Audio timeout detected."
                        )

                    continue

                if not chunk:
                    continue

                # Schedule normal processing on the
                # asyncio event loop.
                try:

                    future = (
                        asyncio.run_coroutine_threadsafe(
                            self.process_chunk(
                                chunk,
                                audio_type,
                            ),
                            self.loop,
                        )
                    )

                    future.result(timeout=5)

                except Exception as e:

                    logger.error(
                        f"Error processing queued audio: {e}",
                        exc_info=True,
                    )

        except Exception as e:

            logger.error(
                f"Fatal error in audio processing loop: {e}",
                exc_info=True,
            )

        finally:

            logger.info(
                "Audio processing loop ended."
            )

    # ========================================================
    # WebSocket sending
    # ========================================================

    async def send_websocket_message(
        self,
        message: dict,
    ):
        """
        Send a JSON message through WebSocket.
        """

        try:

            if not self.is_running:
                return

            if self.websocket is None:
                return

            if message.get("type") == "transcript":

                audio_type = message.get(
                    "audioType"
                )

                if audio_type not in [
                    "microphone",
                    "system",
                    "unknown",
                ]:
                    logger.error(
                        f"Invalid transcript audio type: "
                        f"{audio_type}"
                    )
                    return

            await self.websocket.send_json(
                message
            )

        except Exception as e:

            logger.error(
                f"Error sending WebSocket message: {e}",
                exc_info=True,
            )

    # ========================================================
    # Start
    # ========================================================

    async def start(self):
        """
        Start the audio processing pipeline.
        """

        try:

            # ------------------------------------------------
            # Register audio streams
            # ------------------------------------------------

            await self.stream_manager.add_stream(
                self.client_id,
                "microphone",
            )

            await self.stream_manager.add_stream(
                self.client_id,
                "system",
            )

            # ------------------------------------------------
            # Start compatibility processing thread
            # ------------------------------------------------

            self.processing_thread = threading.Thread(
                target=self._process_audio,
                daemon=True,
            )

            self.processing_thread.start()

            logger.info(
                f"Started enhanced audio processor "
                f"for client: {self.client_id}"
            )

            return True

        except Exception as e:

            logger.error(
                f"Error starting audio processor: {e}",
                exc_info=True,
            )

            return False

    # ========================================================
    # Stop
    # ========================================================

    async def stop(self):
        """
        Stop the audio processing pipeline.
        """

        try:

            self.is_running = False

            # ------------------------------------------------
            # Stop background thread
            # ------------------------------------------------

            if (
                self.processing_thread
                and self.processing_thread.is_alive()
            ):

                self.processing_thread.join(
                    timeout=2
                )

            # ------------------------------------------------
            # Clean up streams
            # ------------------------------------------------

            await self.stream_manager.remove_stream(
                self.client_id,
                "microphone",
            )

            await self.stream_manager.remove_stream(
                self.client_id,
                "system",
            )

            logger.info(
                f"Stopped enhanced audio processor "
                f"for client: {self.client_id}"
            )

            return True

        except Exception as e:

            logger.error(
                f"Error stopping audio processor: {e}",
                exc_info=True,
            )

            return False

    # ========================================================
    # Status
    # ========================================================

    def get_status(self) -> dict:
        """
        Get current processor status.
        """

        return {
            "client_id": self.client_id,
            "is_running": self.is_running,
            "current_audio_type": self.current_audio_type,
            "sample_rate": self.current_sample_rate,
            "streams": (
                self.stream_manager
                .get_all_stream_statuses()
            ),
            "whisper_model": self.whisper_model_name,
            "transcription_mode": "local",
        }