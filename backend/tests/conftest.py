import os
import sys
import uuid
import wave
import math
import struct
import pytest

# Add backend directory to Python path
BACKEND_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


# ============================================================
# Database fixture
# ============================================================

@pytest.fixture
def db():
    """
    Provide a SQLAlchemy database session for tests.
    """

    from app.database.config import SessionLocal

    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


# ============================================================
# Meeting fixture
# ============================================================

@pytest.fixture
def meeting_id(db):
    """
    Create a temporary meeting and return its database ID.
    """

    from app.database.models import Meeting

    meeting = Meeting(
        meeting_id=f"pytest-{uuid.uuid4()}",
        title="Pytest Test Meeting",
        is_active=True,
    )

    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    meeting_db_id = meeting.id

    yield meeting_db_id

    # Cleanup
    try:
        db.delete(meeting)
        db.commit()
    except Exception:
        db.rollback()


# ============================================================
# WebSocket fixture
# ============================================================

@pytest.fixture
def websocket_uri():
    """
    WebSocket endpoint used by audio-processing tests.
    """

    return "ws://localhost:8000/ws/test-client"


# ============================================================
# Audio file fixture
# ============================================================

@pytest.fixture
def audio_file(tmp_path):
    """
    Create a small WAV file for audio-processing tests.
    """

    file_path = tmp_path / "test_audio.wav"

    sample_rate = 16000
    duration = 1.0
    frequency = 440.0

    num_samples = int(sample_rate * duration)

    with wave.open(str(file_path), "wb") as wav_file:

        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)

        frames = bytearray()

        for i in range(num_samples):

            sample = int(
                16000
                * math.sin(
                    2 * math.pi * frequency * i / sample_rate
                )
            )

            frames.extend(
                struct.pack("<h", sample)
            )

        wav_file.writeframes(frames)

    return str(file_path)