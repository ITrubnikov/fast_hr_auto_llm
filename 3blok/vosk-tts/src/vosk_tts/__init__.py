"""
Vosk-TTS сервис для локального синтеза речи
Интегрированный с Vosk TTS Python API с расширенной отладкой
"""

__version__ = "0.9.0"
__author__ = "Vosk-TTS Team"

from .tts import VoskTTSEngine
from .triton_client import TritonTTSClient
from .config import TTSConfig

__all__ = [
    "VoskTTSEngine",
    "TritonTTSClient",
    "TTSConfig"
]
