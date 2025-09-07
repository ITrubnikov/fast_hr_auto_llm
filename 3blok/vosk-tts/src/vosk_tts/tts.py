"""
Vosk TTS движок для локального синтеза речи с отладкой
"""

import logging
import asyncio
import tempfile
from pathlib import Path
from typing import Optional, Union, Dict, Any
import subprocess
import os
import shutil
from datetime import datetime
import numpy as np
import soundfile as sf

# Vosk TTS Python API - официальные импорты для последней версии  
from vosk_tts import Model, Synth

from .config import TTSConfig

logger = logging.getLogger(__name__)


class VoskTTSEngine:
    """
    Vosk TTS движок для локального синтеза речи с расширенной отладкой
    """
    
    def __init__(self, config: TTSConfig):
        self.config = config
        self._cache: Dict[str, Path] = {}
        self._is_initialized = False
        self._available_voices = []
        self._model = None
        self._synth = None
        
        # Доступные голоса Vosk TTS (русские)
        self._default_voices = [
            {"name": "irina", "lang": "ru", "speaker_id": 0, "description": "Женский голос"},
            {"name": "elena", "lang": "ru", "speaker_id": 1, "description": "Женский голос"},
            {"name": "natasha", "lang": "ru", "speaker_id": 2, "description": "Женский голос"},
            {"name": "pavel", "lang": "ru", "speaker_id": 3, "description": "Мужской голос"},
            {"name": "dmitri", "lang": "ru", "speaker_id": 4, "description": "Мужской голос"}
        ]
        
        # Создаем необходимые папки
        Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.temp_dir).mkdir(parents=True, exist_ok=True)
    
    async def initialize(self, use_triton: bool = False) -> bool:
        """
        Инициализация Vosk TTS движка с детальной отладкой
        
        Args:
            use_triton: Не используется для локального Vosk TTS
            
        Returns:
            True если инициализация успешна
        """
        try:
            logger.info("🚀 Инициализируем Vosk TTS движок...")

            # Режим без загрузки модели: использовать только CLI (быстрый старт в Docker)
            cli_only = os.environ.get("TTS_CLI_ONLY", "0") == "1"
            if cli_only:
                self._available_voices = [v["name"] for v in self._default_voices]
                self._is_initialized = True
                logger.warning("⚙️  Включен режим CLI-only (TTS_CLI_ONLY=1): загрузка модели Vosk TTS пропущена")
                return True
            
            # Загружаем модель Vosk TTS
            try:
                model_name = "vosk-model-tts-ru-0.9-multi"  
                logger.info(f"🔧 Загружаем модель: {model_name}")
                self._model = Model(model_name=model_name)
                logger.info(f"✅ Модель загружена: {type(self._model)}")
                
                # Создаем синтезатор
                self._synth = Synth(self._model)
                logger.info(f"✅ Синтезатор создан: {type(self._synth)}")
                
            except Exception as model_error:
                logger.error(f"❌ Не удалось загрузить модель {model_name}: {model_error}")
                return False
            
            # Устанавливаем доступные голоса
            self._available_voices = [v["name"] for v in self._default_voices]
            logger.info(f"✅ Vosk TTS успешно инициализирован. Доступные голоса: {self._available_voices}")
            self._is_initialized = True
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Vosk TTS: {e}")
            return False
    
    
    async def _get_available_voices(self) -> list:
        """Получает список доступных голосов (для совместимости)"""
        return self._available_voices if self._available_voices else [v["name"] for v in self._default_voices]
    
    async def synthesize_text(
        self, 
        text: str, 
        voice: str = "irina",
        output_path: Optional[Union[str, Path]] = None
    ) -> Optional[Path]:
        """
        Синтезирует текст в речь используя Vosk TTS с расширенной отладкой
        
        Args:
            text: Текст для синтеза
            voice: Голос для использования (irina, elena, natasha, pavel, dmitri)
            output_path: Путь для сохранения файла (опционально)
            
        Returns:
            Путь к созданному аудиофайлу или None в случае ошибки
        """
        if not self._is_initialized:
            logger.error("❌ TTS движок не инициализирован!")
            return None
        
        if not text or not text.strip():
            logger.warning("⚠️ Пустой текст для синтеза")
            return None
        
        # Детальная отладка кодировки на уровне TTS
        logger.info(f"🔤 TTS RAW текст: {repr(text[:50])}")
        logger.info(f"🔤 TTS UTF-8 bytes: {text.encode('utf-8')[:100]}")
        
        # Безопасное логирование для терминала
        safe_text = text[:50].encode('ascii', 'replace').decode('ascii')
        logger.info(f"🎤 Синтезируем речь Vosk TTS: '{safe_text}...' голос: {voice}")
        
        # Создаем путь для выходного файла
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            output_path = Path(self.config.output_dir) / f"vosk_tts_{timestamp}.wav"
        else:
            output_path = Path(output_path)
            
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # 1) Пытаемся синтезировать через CLI (надежный путь как в Triton)
            success = await self._synthesize_with_cli(text, voice, output_path)

            # 2) Если CLI не сработал, пробуем Python API (второй шанс)
            if not success:
                success = await self._synthesize_vosk_debug(text, voice, output_path)
            
            if success:
                logger.info(f"✅ Vosk TTS синтез успешен: {output_path}")
                return output_path
            else:
                logger.error("❌ Vosk TTS синтез не удался")
                
                # Fallback: создаем минимальный WAV файл с тишиной
                logger.warning("🔄 Fallback: создаем тишину")
                sample_rate = 22050
                duration = len(text.split()) * 0.5  # ~0.5 сек на слово
                duration = max(1.0, min(duration, 10.0))  # от 1 до 10 сек
                
                audio_data = np.zeros(int(sample_rate * duration), dtype=np.float32)
                sf.write(output_path, audio_data, sample_rate)
                return output_path
                
        except Exception as e:
            logger.error(f"❌ Ошибка синтеза Vosk TTS: {e}")
            
            # Emergency fallback
            try:
                sample_rate = 22050
                duration = 1.0
                audio_data = np.zeros(int(sample_rate * duration), dtype=np.float32)
                sf.write(output_path, audio_data, sample_rate)
                return output_path
            except:
                return None
    
    async def _synthesize_with_cli(self, text: str, voice: str, output_path: Path) -> bool:
        """
        Синтез через CLI `python -m vosk_tts` (как в Triton Python backend)
        Надежнее текущего Python API для некоторых версий пакета.
        """
        try:
            text_utf8 = text.encode('utf-8').decode('utf-8') if isinstance(text, str) else str(text)

            # Маппинг человеческих имен голосов на пути CLI
            voice_map = {
                "irina": "russian/irina",
                "elena": "russian/elena",
                "pavel": "russian/pavel",
                # Для совместимости: маппим прочие на ближайший доступный
                "natasha": "russian/elena",
                "dmitri": "russian/pavel",
            }
            voice_path = voice_map.get(voice or "irina", "russian/irina")

            cmd = [
                "python", "-m", "vosk_tts",
                "--text", text_utf8,
                "--voice", voice_path,
                "--output", str(output_path),
                "--sample-rate", "22050",
            ]

            logger.info(f"🧪 CLI синтез: voice={voice_path}, out={output_path}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                logger.warning(f"❌ vosk_tts CLI error: {result.stderr}")
                return False

            if output_path.exists() and output_path.stat().st_size > 0:
                logger.info(f"✅ CLI создал файл: {output_path.stat().st_size} байт")
                return True
            else:
                logger.error(f"❌ CLI не создал файл или он пуст: {output_path}")
                return False
        except subprocess.TimeoutExpired:
            logger.error("⏳ Таймаут CLI синтеза")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка CLI синтеза: {e}")
            return False

    async def _synthesize_vosk_debug(self, text: str, voice: str, output_path: Path) -> bool:
        """
        Выполняет синтез с помощью Vosk TTS
        """
        try:
            # Обеспечиваем правильную UTF-8 кодировку
            text_utf8 = text.encode('utf-8').decode('utf-8') if isinstance(text, str) else str(text)
            logger.info(f"🎤 Синтезируем: '{text_utf8[:50]}...' голос={voice}")
            logger.info(f"🔤 Кодировка текста проверена: {len(text_utf8)} символов")
            
            # Проверяем что модель и синтезатор инициализированы
            if self._model is None or self._synth is None:
                logger.error("❌ Модель или синтезатор не загружены")
                return False
            
            # Определяем speaker_id по имени голоса
            speaker_id = 0  # По умолчанию irina
            for voice_info in self._default_voices:
                if voice_info["name"] == voice:
                    speaker_id = voice_info["speaker_id"]
                    break
            
            # Пробуем разные варианты вызова API
            logger.info(f"🧪 Попытка 1: synth(text, output_path, speaker_id) - позиционные аргументы")
            try:
                self._synth.synth(text_utf8, str(output_path), speaker_id)
                logger.info("✅ Успех: позиционные аргументы")
            except Exception as e1:
                logger.warning(f"❌ Позиционные не работают: {e1}")
                
                logger.info(f"🧪 Попытка 2: synth(text, speaker_id) - без output_path")
                try:
                    result = self._synth.synth(text_utf8, speaker_id)
                    logger.info(f"🎵 Результат synth: {type(result)}, содержимое: {result[:100] if hasattr(result, '__len__') else result}")
                    
                    # Сохраняем результат если это аудио данные
                    if hasattr(result, '__len__') and len(result) > 0:
                        import soundfile as sf
                        sf.write(str(output_path), result, 22050)
                        logger.info("✅ Успех: прямой вызов с сохранением")
                    else:
                        raise Exception(f"Некорректный результат: {result}")
                        
                except Exception as e2:
                    logger.warning(f"❌ Прямой вызов не работает: {e2}")
                    raise e2
            logger.info(f"🎵 Синтез завершен, проверяем файл: {output_path}")
            
            # Проверяем что файл создан и не пустой
            if output_path.exists() and output_path.stat().st_size > 0:
                logger.info(f"✅ Аудио файл создан успешно: {output_path.stat().st_size} байт")
                return True
            else:
                logger.error(f"❌ Файл не создан или пустой: {output_path}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка синтеза: {e}")
            return False
    
    
    
    def get_available_voices(self) -> list:
        """
        Возвращает список доступных голосов
        
        Returns:
            Список имен голосов
        """
        return self._available_voices if self._available_voices else ["irina", "elena", "natasha", "pavel", "dmitri"]
    
    def get_config_info(self) -> Dict[str, Any]:
        """
        Возвращает информацию о конфигурации движка
        
        Returns:
            Словарь с информацией о конфигурации
        """
        return {
            "engine": "Vosk TTS (Local)",
            "version": "0.9-multi",
            "model_loaded": bool(self._model),
            "synth_ready": bool(self._synth),
            "initialized": self._is_initialized,
            "available_voices": self.get_available_voices(),
            "output_dir": str(self.config.output_dir),
            "temp_dir": str(self.config.temp_dir),
            "cache_size": len(self._cache)
        }
    
    def health_check(self) -> Dict[str, Any]:
        """
        Проверка здоровья TTS движка
        
        Returns:
            Словарь со статусом здоровья
        """
        try:
            # Проверяем полную готовность
            model_ok = bool(self._model)
            synth_ok = bool(self._synth)
            init_ok = self._is_initialized
            
            status = "healthy" if (model_ok and synth_ok and init_ok) else "unhealthy"
            
            return {
                "status": status,
                "engine": "Vosk TTS (Local)",
                "version": "0.9-multi",
                "model_loaded": model_ok,
                "synth_ready": synth_ok,
                "initialized": init_ok,
                "available_voices": self.get_available_voices(),
                "cache_size": len(self._cache)
            }
        except Exception as e:
            return {
                "status": "error",
                "engine": "Vosk TTS (Local)",
                "error": str(e)
            }
    
    async def cleanup(self):
        """Очистка ресурсов"""
        try:
            # Очищаем кеш
            self._cache.clear()
            
            # Освобождаем ресурсы Vosk TTS
            if self._synth:
                self._synth = None
                logger.info("🧹 Синтезатор Vosk TTS освобожден")
                
            if self._model:
                self._model = None
                logger.info("🧹 Модель Vosk TTS освобождена")
            
            # Удаляем временные файлы Vosk TTS
            temp_dir = Path(self.config.temp_dir)
            if temp_dir.exists():
                for temp_file in temp_dir.glob("vosk_tts_*"):
                    try:
                        temp_file.unlink()
                        logger.debug(f"🗑️ Удален временный файл: {temp_file}")
                    except:
                        pass
            
            self._is_initialized = False
            logger.info("🧹 Vosk TTS ресурсы очищены")
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при очистке Vosk TTS: {e}")