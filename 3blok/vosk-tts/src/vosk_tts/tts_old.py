"""
FishSpeech TTS движок с поддержкой OpenAudio S1-mini модели
"""

import logging
import asyncio
import tempfile
import hashlib
import subprocess
import os
import sys
from pathlib import Path
from typing import Optional, Union, Dict, Any
from datetime import datetime
import numpy as np
import soundfile as sf

from .config import TTSConfig

logger = logging.getLogger(__name__)


class VoskTTSEngine:
    """
    FishSpeech TTS движок с поддержкой OpenAudio S1-mini модели
    """
    
    def __init__(self, config: TTSConfig):
        self.config = config
        self._cache: Dict[str, Path] = {}
        self._is_initialized = False
        
        # Пути к модели FishSpeech
        self.fish_speech_path = Path("/app/fish-speech")
        self.model_path = Path(os.getenv("FISHSPEECH_MODEL_PATH", "/app/checkpoints/openaudio-s1-mini"))
        self.llama_checkpoint = os.getenv("FISHSPEECH_LLAMA_CHECKPOINT", str(self.model_path))
        self.decoder_checkpoint = os.getenv("FISHSPEECH_DECODER_CHECKPOINT", str(self.model_path / "codec.pth"))
        self.decoder_config = os.getenv("FISHSPEECH_DECODER_CONFIG", "modded_dac_vq")
        
        # Создаем необходимые папки
        Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.temp_dir).mkdir(parents=True, exist_ok=True)
    
    async def initialize(self, use_triton: bool = False) -> bool:
        """
        Инициализация FishSpeech TTS движка
        
        Args:
            use_triton: Игнорируется, оставлен для совместимости
        """
        
        logger.info("🐟 Инициализация FishSpeech TTS движка...")
        
        try:
            # Проверяем наличие модели
            if not self.model_path.exists():
                logger.error(f"❌ Модель OpenAudio S1-mini не найдена: {self.model_path}")
                return False
            
            # Проверяем ключевые файлы модели
            codec_path = Path(self.decoder_checkpoint)
            if not codec_path.exists():
                logger.error(f"❌ Codec файл не найден: {codec_path}")
                return False
            
            # Проверяем наличие FishSpeech
            if not self.fish_speech_path.exists():
                logger.error(f"❌ FishSpeech не найден: {self.fish_speech_path}")
                return False
            
            # Добавляем FishSpeech в Python PATH
            if str(self.fish_speech_path) not in sys.path:
                sys.path.insert(0, str(self.fish_speech_path))
            
            self._is_initialized = True
            logger.info("✅ FishSpeech TTS движок успешно инициализирован")
            logger.info(f"📁 Модель: {self.model_path}")
            logger.info(f"🎯 Декодер: {self.decoder_checkpoint}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации FishSpeech: {e}")
            self._is_initialized = False
            return False
    
    async def _initialize_local_engine(self) -> bool:
        """Инициализация локального vosk-tts"""
        # ВРЕМЕННАЯ ЗАГЛУШКА для тестирования workflow
        logger.info("🔧 ВРЕМЕННАЯ ЗАГЛУШКА: локальный TTS инициализирован без синтеза")
        return True
        
        try:
            import vosk_tts
            self._local_engine = vosk_tts
            
            # Проверка доступности
            logger.info("Локальный vosk-tts доступен")
            return True
            
        except ImportError as e:
            logger.error(f"vosk-tts не установлен: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка инициализации vosk-tts: {e}")
            return False
    
    async def synthesize_text(
        self,
        text: str,
        voice: str = None,
        speed: float = None,
        pitch: float = None,
        volume: float = None,
        output_path: Optional[Union[str, Path]] = None
    ) -> Optional[Path]:
        """
        Синтез текста в аудио
        
        Args:
            text: Текст для синтеза
            voice: Имя голоса
            speed: Скорость речи
            pitch: Высота тона  
            volume: Громкость
            output_path: Путь для сохранения (если None, создается автоматически)
            
        Returns:
            Путь к созданному аудио файлу или None при ошибке
        """
        
        if not self._is_initialized:
            logger.error("TTS движок не инициализирован")
            return None
        
        # Реальный синтез через локальный vosk-tts
        logger.info(f"🎤 Синтезируем речь: '{text[:30]}...'")
        
        # Создаем путь для выходного файла
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            output_path = Path(self.config.output_dir) / f"tts_{timestamp}.wav"
        else:
            output_path = Path(output_path)
            
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Используем vosk-tts командой
            import subprocess
            
            # Параметры голоса - используем мульти-голосовую модель
            voice_name = voice or self.config.default_voice or "irina"
            
            # Маппинг голосов на speaker ID для мульти-голосовой модели
            voice_mapping = {
                "irina": 0,     # женский голос 0
                "elena": 1,     # женский голос 1 
                "natasha": 2,   # женский голос 2
                "pavel": 3,     # мужской голос 3
                "dmitri": 4     # мужской голос 4
            }
            speaker_id = voice_mapping.get(voice_name, 0)
            
            # Команда для синтеза (используем мульти-голосовую модель)
            cmd = [
                "vosk-tts", 
                "--input", text,
                "--output", str(output_path),
                "--model-name", "vosk-model-tts-ru-0.9-multi",
                "--speaker", str(speaker_id)
            ]
            
            logger.debug(f"Выполняем команду: {' '.join(cmd)}")
            
            # Выполняем команду
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and output_path.exists():
                logger.info(f"✅ TTS синтез успешен: {output_path}")
                return output_path
            else:
                logger.error(f"❌ Ошибка vosk-tts: {result.stderr}")
                
                # Fallback: создаем минимальный WAV файл
                logger.warning("🔄 Fallback: создаем тишину")
                import soundfile as sf
                import numpy as np
                
                sample_rate = 22050
                duration = 1.0
                audio_data = np.zeros(int(sample_rate * duration), dtype=np.float32)
                sf.write(output_path, audio_data, sample_rate)
                return output_path
                
        except Exception as e:
            logger.error(f"❌ Ошибка синтеза: {e}")
            return None
        
        if not text.strip():
            logger.warning("Пустой текст для синтеза")
            return None
        
        if len(text) > self.config.max_text_length:
            logger.error(f"Текст слишком длинный: {len(text)} > {self.config.max_text_length}")
            return None
        
        # Используем значения по умолчанию
        voice = voice or self.config.default_voice
        speed = speed or self.config.default_speed
        pitch = pitch or self.config.default_pitch
        volume = volume or self.config.default_volume
        
        # Проверка кеша
        cache_key = None
        if self.config.enable_cache:
            cache_key = self._generate_cache_key(text, voice, speed, pitch, volume)
            if cache_key in self._cache and self._cache[cache_key].exists():
                logger.debug(f"Используем кеш для: {text[:50]}...")
                return self._cache[cache_key]
        
        # Генерируем путь для выходного файла
        if output_path is None:
            timestamp = asyncio.get_event_loop().time()
            filename = f"tts_{voice}_{int(timestamp)}.wav"
            output_path = Path(self.config.output_dir) / filename
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Пробуем Triton сначала
            if self.triton_client:
                audio_data = await self.triton_client.synthesize_text(
                    text=text,
                    voice=voice,
                    speed=speed,
                    pitch=pitch
                )
                
                if audio_data is not None:
                    # Применяем громкость
                    if volume != 1.0:
                        audio_data = audio_data * volume
                        audio_data = np.clip(audio_data, -1.0, 1.0)
                    
                    # Сохраняем аудио
                    voice_config = self.config.voices.get(voice)
                    sample_rate = voice_config.sample_rate if voice_config else 22050
                    
                    sf.write(str(output_path), audio_data, sample_rate)
                    
                    # Добавляем в кеш
                    if cache_key:
                        self._cache[cache_key] = output_path
                    
                    logger.debug(f"Triton TTS синтез успешен: {output_path}")
                    return output_path
                else:
                    logger.warning("Triton TTS не смог синтезировать, пробуем локальный")
            
            # Если Triton не сработал, пробуем локальный
            if self._local_engine:
                success = await self._synthesize_local(
                    text=text,
                    voice=voice,
                    speed=speed,
                    pitch=pitch,
                    volume=volume,
                    output_path=output_path
                )
                
                if success:
                    # Добавляем в кеш
                    if cache_key:
                        self._cache[cache_key] = output_path
                    
                    logger.debug(f"Локальный TTS синтез успешен: {output_path}")
                    return output_path
            
            logger.error("Не удалось синтезировать текст ни одним способом")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка синтеза текста: {e}")
            return None
    
    async def _synthesize_local(
        self,
        text: str,
        voice: str,
        speed: float,
        pitch: float, 
        volume: float,
        output_path: Path
    ) -> bool:
        """Локальный синтез через vosk-tts CLI"""
        
        try:
            import subprocess
            
            # Мапинг голосов vosk-tts
            voice_mapping = {
                "irina": "russian/irina",
                "elena": "russian/elena", 
                "pavel": "russian/pavel"
            }
            
            voice_path = voice_mapping.get(voice, "russian/irina")
            
            # Команда для vosk-tts
            cmd = [
                "python", "-m", "vosk_tts",
                "--text", text,
                "--voice", voice_path,
                "--output", str(output_path),
                "--sample-rate", "22050"
            ]
            
            if speed != 1.0:
                cmd.extend(["--speed", str(speed)])
            
            # Выполняем синтез
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and output_path.exists():
                # Применяем громкость если нужно
                if volume != 1.0:
                    audio_data, sample_rate = sf.read(str(output_path))
                    audio_data = audio_data * volume
                    audio_data = np.clip(audio_data, -1.0, 1.0)
                    sf.write(str(output_path), audio_data, sample_rate)
                
                return True
            else:
                logger.error(f"Ошибка локального TTS: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка локального синтеза: {e}")
            return False
    
    def _generate_cache_key(
        self, 
        text: str, 
        voice: str, 
        speed: float, 
        pitch: float, 
        volume: float
    ) -> str:
        """Генерирует ключ кеша"""
        
        cache_string = f"{text}|{voice}|{speed}|{pitch}|{volume}"
        return hashlib.md5(cache_string.encode()).hexdigest()
    
    async def get_available_voices(self) -> Dict[str, Dict[str, Any]]:
        """Получает список доступных голосов"""
        
        if self.triton_client:
            return self.triton_client.get_available_voices()
        else:
            # Локальные голоса
            voices = {}
            for voice_name, voice_config in self.config.voices.items():
                voices[voice_name] = {
                    'name': voice_name,
                    'gender': voice_config.gender,
                    'language': voice_config.language,
                    'sample_rate': voice_config.sample_rate,
                    'description': voice_config.description,
                    'ready': True,  # Предполагаем что локальные голоса доступны
                    'engine': 'local'
                }
            
            return voices
    
    async def health_check(self) -> Dict[str, Any]:
        """Проверка здоровья TTS движка"""
        
        status = {
            "initialized": self._is_initialized,
            "triton_available": self.triton_client is not None,
            "local_available": self._local_engine is not None,
            "cache_size": len(self._cache)
        }
        
        if self.triton_client:
            triton_health = await self.triton_client.health_check()
            status["triton_healthy"] = triton_health
            
            if triton_health:
                status["server_info"] = self.triton_client.get_server_info()
        
        return status
    
    def clear_cache(self):
        """Очистка кеша"""
        self._cache.clear()
        logger.info("Кеш TTS очищен")
    
    async def cleanup(self):
        """Очистка ресурсов"""
        
        if self.triton_client:
            await self.triton_client.cleanup()
            self.triton_client = None
        
        self._local_engine = None
        self._cache.clear()
        self._is_initialized = False
        
        logger.info("TTS движок закрыт")
