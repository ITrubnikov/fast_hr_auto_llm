#!/usr/bin/env python3
"""
Фабрика драйверов для системы интервью
"""

import json
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod


class BaseDriver(ABC):
    """Базовый класс для всех драйверов."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.initialized = False
    
    @abstractmethod
    def initialize(self):
        """Инициализация драйвера."""
        pass
    
    @abstractmethod
    def cleanup(self):
        """Очистка ресурсов драйвера."""
        pass


class AudioInputDriver(BaseDriver):
    """Драйвер для ввода аудио."""
    
    def initialize(self):
        """Инициализация драйвера ввода аудио."""
        print("🎤 Инициализация драйвера ввода аудио...")
        self.initialized = True
    
    def cleanup(self):
        """Очистка ресурсов драйвера ввода аудио."""
        print("🧹 Очистка драйвера ввода аудио...")


class AudioOutputDriver(BaseDriver):
    """Драйвер для вывода аудио."""
    
    def initialize(self):
        """Инициализация драйвера вывода аудио."""
        print("🔊 Инициализация драйвера вывода аудио...")
        self.initialized = True
    
    def cleanup(self):
        """Очистка ресурсов драйвера вывода аудио."""
        print("🧹 Очистка драйвера вывода аудио...")


class TTSDriver(BaseDriver):
    """OpenAI TTS драйвер с отправкой аудио в браузер."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.websocket = None
        self.client = None
    
    def initialize(self):
        """Инициализация OpenAI TTS драйвера."""
        print("🗣️ Инициализация OpenAI TTS драйвера...")
        try:
            from openai import OpenAI
            api_key = self.config.get('api_key')
            if api_key:
                self.client = OpenAI(api_key=api_key)
                print("✅ OpenAI TTS клиент инициализирован")
            else:
                print("❌ API ключ не найден для OpenAI TTS")
                self.initialized = False
                return
            self.initialized = True
        except Exception as e:
            print(f"❌ Ошибка инициализации OpenAI TTS: {e}")
            self.initialized = False
    
    def cleanup(self):
        """Очистка ресурсов драйвера TTS."""
        print("🧹 Очистка OpenAI TTS драйвера...")
        self.client = None
    
    def synthesize(self, text: str) -> bytes:
        """Синтез речи через OpenAI TTS."""
        print(f"🗣️ OpenAI TTS синтез: {text[:50]}...")
        if self.client:
            try:
                response = self.client.audio.speech.create(
                    model="tts-1",
                    voice=self.config.get('voice', 'alloy'),
                    input=text
                )
                return response.content
            except Exception as e:
                print(f"❌ Ошибка OpenAI TTS синтеза: {e}")
                return b""
        return b""
    
    def set_websocket(self, websocket):
        """Установить WebSocket для отправки аудио в браузер."""
        self.websocket = websocket
    
    async def synthesize_to_browser(self, text: str):
        """Синтез речи через OpenAI TTS с отправкой в браузер."""
        print(f"🗣️ OpenAI TTS синтез для браузера: {text[:50]}...")
        if self.client and self.websocket:
            try:
                # Синтезируем речь через OpenAI
                response = self.client.audio.speech.create(
                    model="tts-1",
                    voice=self.config.get('voice', 'alloy'),
                    input=text
                )
                audio_data = response.content
                
                # Отправляем аудио в браузер
                import base64
                audio_b64 = base64.b64encode(audio_data).decode('utf-8')
                
                await self.websocket.send_text(json.dumps({
                    "type": "audio_data",
                    "audio_data": audio_b64,
                    "format": "mp3"
                }))
                print("✅ OpenAI TTS аудио отправлено в браузер")
            except Exception as e:
                print(f"❌ Ошибка OpenAI TTS для браузера: {e}")
        else:
            print("⚠️ OpenAI TTS клиент или WebSocket не инициализирован")


class ASRDriver(BaseDriver):
    """Драйвер для распознавания речи (ASR)."""
    
    def initialize(self):
        """Инициализация драйвера ASR."""
        print("👂 Инициализация драйвера ASR...")
        self.initialized = True
    
    def cleanup(self):
        """Очистка ресурсов драйвера ASR."""
        print("🧹 Очистка драйвера ASR...")
    
    def transcribe(self, audio_data: bytes) -> str:
        """Распознавание речи из аудио данных."""
        print("👂 Распознавание речи...")
        # Заглушка - в реальной реализации здесь будет распознавание речи
        return "Распознанный текст"


class DriverFactory:
    """Фабрика для создания драйверов."""
    
    DRIVER_TYPES = {
        'audio_input': AudioInputDriver,
        'audio_output': AudioOutputDriver,
        'tts': TTSDriver,
        'asr': ASRDriver,
        # Поддержка типов из конфигурации
        'microphone': AudioInputDriver,
        'speaker': AudioOutputDriver,
        'browser': TTSDriver,
        'whisper': ASRDriver
    }
    
    @classmethod
    def create_driver(cls, driver_type: str, config: Dict[str, Any]) -> BaseDriver:
        """Создать драйвер указанного типа."""
        if driver_type not in cls.DRIVER_TYPES:
            raise ValueError(f"Неизвестный тип драйвера: {driver_type}")
        
        driver_class = cls.DRIVER_TYPES[driver_type]
        return driver_class(config)
    
    @classmethod
    def get_available_drivers(cls) -> list:
        """Получить список доступных типов драйверов."""
        return list(cls.DRIVER_TYPES.keys())


def create_drivers_from_config(config: Dict[str, Any]) -> Dict[str, BaseDriver]:
    """Создать драйверы из конфигурации."""
    drivers = {}
    
    for driver_name, driver_config in config.items():
        if isinstance(driver_config, dict) and 'type' in driver_config:
            driver_type = driver_config['type']
            driver_config_dict = driver_config.get('config', {})
            
            try:
                driver = DriverFactory.create_driver(driver_type, driver_config_dict)
                drivers[driver_name] = driver
                print(f"✅ Создан драйвер {driver_name} типа {driver_type}")
            except Exception as e:
                print(f"❌ Ошибка создания драйвера {driver_name}: {e}")
        else:
            print(f"⚠️ Пропущен драйвер {driver_name}: некорректная конфигурация")
    
    return drivers
