"""
Конфигурация для Vosk-TTS сервиса
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class VoiceConfig(BaseModel):
    """Конфигурация голоса"""
    name: str = Field(description="Имя голоса")
    model_name: str = Field(description="Имя модели в Triton")
    language: str = Field(default="ru", description="Язык")
    sample_rate: int = Field(default=22050, description="Частота дискретизации")
    gender: str = Field(description="Пол голоса (male/female)")
    description: str = Field(default="", description="Описание голоса")


class TTSConfig(BaseModel):
    """Основная конфигурация TTS"""
    
    # Triton настройки
    triton_url: str = Field(default="localhost:8000", description="URL Triton сервера")
    triton_timeout: int = Field(default=60, description="Таймаут Triton запросов в секундах")
    
    # Доступные голоса
    voices: Dict[str, VoiceConfig] = Field(
        default={
            "irina": VoiceConfig(
                name="irina",
                model_name="vosk-tts-irina",
                gender="female",
                description="Женский голос, нейтральный"
            ),
            "elena": VoiceConfig(
                name="elena", 
                model_name="vosk-tts-elena",
                gender="female",
                description="Женский голос, мягкий"
            ),
            "pavel": VoiceConfig(
                name="pavel",
                model_name="vosk-tts-pavel", 
                gender="male",
                description="Мужской голос, уверенный"
            )
        }
    )
    
    # Настройки синтеза
    default_voice: str = Field(default="irina", description="Голос по умолчанию")
    default_speed: float = Field(default=1.0, description="Скорость по умолчанию")
    default_pitch: float = Field(default=1.0, description="Тональность по умолчанию") 
    default_volume: float = Field(default=0.8, description="Громкость по умолчанию")
    
    # Ограничения
    max_text_length: int = Field(default=1000, description="Максимальная длина текста")
    max_concurrent_requests: int = Field(default=10, description="Максимум одновременных запросов")
    
    # Кеширование
    enable_cache: bool = Field(default=True, description="Включить кеширование")
    cache_ttl_seconds: int = Field(default=3600, description="Время жизни кеша")
    
    # Пути
    output_dir: str = Field(default="/app/output", description="Папка для аудио файлов")
    temp_dir: str = Field(default="/tmp/vosk-tts", description="Временная папка")


class APIConfig(BaseModel):
    """Конфигурация API"""
    host: str = Field(default="0.0.0.0", description="Хост API")
    port: int = Field(default=8080, description="Порт API")
    workers: int = Field(default=1, description="Количество worker процессов")
    
    # Безопасность
    api_key_required: bool = Field(default=False, description="Требовать API ключ")
    allowed_origins: List[str] = Field(default=["*"], description="Разрешенные CORS origins")
    
    # Лимиты
    max_request_size: int = Field(default=1000000, description="Максимальный размер запроса в байтах")
    request_timeout: int = Field(default=30, description="Таймаут запроса в секундах")


class ServiceConfig(BaseSettings):
    """Общая конфигурация сервиса"""
    
    tts: TTSConfig = Field(default_factory=TTSConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    
    # Логирование
    log_level: str = Field(default="INFO", description="Уровень логирования")
    log_format: str = Field(default="json", description="Формат логов (json/text)")
    
    # Метрики
    enable_metrics: bool = Field(default=True, description="Включить метрики")
    metrics_port: int = Field(default=8081, description="Порт для метрик")
    
    class Config:
        env_file = ".env"
        env_nested_delimiter = "__"
        
        # Примеры переменных окружения:
        # TTS__TRITON_URL=localhost:8000
        # TTS__DEFAULT_VOICE=elena
        # API__PORT=8080
        # LOG_LEVEL=DEBUG
