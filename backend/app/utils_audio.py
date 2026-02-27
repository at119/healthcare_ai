"""Audio utility functions."""
import base64
import io
import wave
from typing import Tuple


def decode_audio_base64(audio_base64: str) -> bytes:
    """Decode base64 encoded audio data."""
    # Remove data URL prefix if present
    if audio_base64.startswith("data:audio"):
        audio_base64 = audio_base64.split(",")[1]
    
    return base64.b64decode(audio_base64)


def validate_audio_format(audio_data: bytes) -> Tuple[bool, str]:
    """Validate audio format (basic check)."""
    try:
        # Try to read as WAV
        audio_io = io.BytesIO(audio_data)
        with wave.open(audio_io, 'rb') as wav_file:
            frames = wav_file.getnframes()
            sample_rate = wav_file.getframerate()
            channels = wav_file.getnchannels()
            
            if sample_rate < 8000 or sample_rate > 48000:
                return False, f"Unsupported sample rate: {sample_rate}"
            if channels not in [1, 2]:
                return False, f"Unsupported channels: {channels}"
            
            return True, f"Valid WAV: {sample_rate}Hz, {channels} channel(s), {frames} frames"
    except Exception as e:
        # If not WAV, assume it's a valid format for Azure Speech
        # Azure Speech supports various formats
        return True, f"Audio format accepted (Azure Speech will handle conversion): {str(e)}"


def get_audio_duration(audio_data: bytes) -> float:
    """Estimate audio duration in seconds."""
    try:
        audio_io = io.BytesIO(audio_data)
        with wave.open(audio_io, 'rb') as wav_file:
            frames = wav_file.getnframes()
            sample_rate = wav_file.getframerate()
            return frames / float(sample_rate)
    except:
        # Rough estimate: assume 16kHz, mono, 16-bit
        return len(audio_data) / 32000.0
