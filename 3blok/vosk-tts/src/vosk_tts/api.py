"""
FastAPI интерфейс для Vosk-TTS сервиса с отладкой
"""

import asyncio
import logging
import time
from typing import List, Optional, Dict, Any
from pathlib import Path
import tempfile
import uuid

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Form, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import ServiceConfig, TTSConfig
from .tts import VoskTTSEngine

# Настраиваем логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic модели для API
class SynthesisRequest(BaseModel):
    text: str = Field(..., description="Текст для синтеза", max_length=1000)
    voice: Optional[str] = Field(default=None, description="Имя голоса")
    format: Optional[str] = Field(default="wav", description="Формат аудио")

class SynthesisResponse(BaseModel):
    success: bool
    message: str
    audio_url: Optional[str] = None
    file_id: Optional[str] = None
    duration: Optional[float] = None
    voice_used: Optional[str] = None
    processing_time: Optional[float] = None

class VoiceInfo(BaseModel):
    name: str
    gender: str
    language: str
    sample_rate: int
    description: str
    ready: bool
    engine: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    message: str
    details: Dict[str, Any]
    timestamp: float

# Глобальные переменные
tts_engine: Optional[VoskTTSEngine] = None
service_config: Optional[ServiceConfig] = None

# FastAPI приложение
app = FastAPI(
    title="Vosk-TTS API",
    description="Text-to-Speech сервис на основе Vosk TTS для локального синтеза речи с отладкой",
    version="0.9.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске"""
    global tts_engine, service_config
    
    try:
        logger.info("🚀 Запуск Vosk-TTS API сервиса с отладкой...")
        
        # Загружаем конфигурацию
        service_config = ServiceConfig()
        
        # Создаем TTS движок
        tts_engine = VoskTTSEngine(service_config.tts)
        
        # Инициализируем движок (загрузка модели Vosk)
        success = await tts_engine.initialize()
        
        if not success:
            logger.error("❌ Не удалось инициализировать TTS движок")
            raise Exception("TTS initialization failed")
        
        logger.info("✅ Vosk-TTS API сервис запущен успешно с отладкой!")
        
        # Показываем доступные голоса
        voices = tts_engine.get_available_voices()
        logger.info(f"📢 Доступно голосов: {voices}")
        
    except Exception as e:
        logger.error(f"💥 Ошибка запуска сервиса: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Очистка при завершении"""
    global tts_engine
    
    if tts_engine:
        await tts_engine.cleanup()
        logger.info("🛑 Vosk-TTS API сервис остановлен")

@app.get("/", response_model=Dict[str, Any])
async def root():
    """Главная страница API"""
    return {
        "name": "Vosk-TTS API",
        "version": "0.9.0",
        "description": "Text-to-Speech сервис для локального синтеза речи через Vosk TTS с отладкой",
        "endpoints": {
            "synthesis": "/synthesize",
            "voices": "/voices",
            "health": "/health",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    global tts_engine
    
    if not tts_engine:
        raise HTTPException(status_code=503, detail="TTS движок не инициализирован")
    
    try:
        health_info = tts_engine.health_check()
        
        status = "healthy" if health_info.get("initialized", False) else "unhealthy"
        
        response_data = {
            "status": status,
            "message": "Сервис работает нормально" if status == "healthy" else "Есть проблемы",
            "details": health_info,
            "timestamp": time.time()
        }
        
        return JSONResponse(
            content=response_data,
            media_type="application/json; charset=utf-8"
        )
        
    except Exception as e:
        logger.error(f"Ошибка проверки здоровья: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/voices", response_model=Dict[str, VoiceInfo])
async def get_voices():
    """Получить список доступных голосов"""
    global tts_engine
    
    if not tts_engine:
        raise HTTPException(status_code=503, detail="TTS движок не инициализирован")
    
    try:
        voices_list = tts_engine.get_available_voices()
        
        # Преобразуем список голосов в Pydantic модели
        response = {}
        for voice_name in voices_list:
            response[voice_name] = VoiceInfo(
                name=voice_name,
                gender="female" if voice_name in ["irina", "elena", "natasha"] else "male",
                language="ru",
                sample_rate=22050,
                description=f"Vosk TTS голос: {voice_name}",
                ready=True,
                engine="Vosk TTS (Local)"
            )
        
        return response
        
    except Exception as e:
        logger.error(f"Ошибка получения голосов: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/synthesize", response_model=SynthesisResponse)
async def synthesize_text(request: SynthesisRequest):
    """Синтез текста в речь"""
    global tts_engine
    
    if not tts_engine:
        raise HTTPException(status_code=503, detail="TTS движок не инициализирован")
    
    start_time = time.time()
    
    try:
        # Детальная отладка кодировки
        logger.info(f"🔤 RAW текст: {repr(request.text[:50])}")
        logger.info(f"🔤 UTF-8 bytes: {request.text.encode('utf-8')[:100]}")
        logger.info(f"🔤 Длина текста: {len(request.text)} символов")
        
        # Безопасное логирование для терминала
        safe_text = request.text[:50].encode('ascii', 'replace').decode('ascii')
        logger.info(f"🎤 Синтез текста: {safe_text}...")
        
        # Генерируем уникальный ID файла
        file_id = str(uuid.uuid4())
        
        # Синтезируем аудио
        audio_path = await tts_engine.synthesize_text(
            text=request.text,
            voice=request.voice
        )
        
        if audio_path is None:
            raise HTTPException(status_code=500, detail="Не удалось синтезировать аудио")
        
        processing_time = time.time() - start_time
        
        # Получаем информацию об аудио файле
        file_size = audio_path.stat().st_size
        duration = None  # TODO: вычислить длительность
        
        # Переименовываем файл с file_id
        new_path = audio_path.parent / f"{file_id}.wav"
        audio_path.rename(new_path)
        
        # Формируем URL для скачивания
        audio_url = f"/audio/{file_id}.wav"
        
        logger.info(f"✅ Синтез завершен за {processing_time:.2f}с, размер: {file_size} байт")
        
        return SynthesisResponse(
            success=True,
            message="Синтез завершен успешно",
            audio_url=audio_url,
            file_id=file_id,
            duration=duration,
            voice_used=request.voice or service_config.tts.default_voice,
            processing_time=processing_time
        )
        
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Ошибка синтеза: {e}")
        
        return SynthesisResponse(
            success=False,
            message=f"Ошибка синтеза: {str(e)}",
            processing_time=processing_time
        )

@app.post("/synthesize/form", response_model=SynthesisResponse)
async def synthesize_text_form(
    text: str = Form(..., description="Текст для синтеза"),
    voice: Optional[str] = Form(default=None, description="Имя голоса")
):
    """Синтез текста через форму"""
    request = SynthesisRequest(
        text=text,
        voice=voice
    )
    
    return await synthesize_text(request)

@app.get("/audio/{file_id}")
async def get_audio_file(file_id: str):
    """Получить аудио файл по ID"""
    
    # Проверяем безопасность file_id
    if not file_id.replace("-", "").replace(".", "").isalnum():
        raise HTTPException(status_code=400, detail="Некорректный ID файла")
    
    audio_path = Path(service_config.tts.output_dir) / file_id
    
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Аудио файл не найден")
    
    return FileResponse(
        path=str(audio_path),
        media_type="audio/wav",
        filename=file_id,
        headers={"Content-Disposition": f"attachment; filename={file_id}"}
    )

@app.delete("/audio/{file_id}")
async def delete_audio_file(file_id: str):
    """Удалить аудио файл"""
    
    # Проверяем безопасность file_id
    if not file_id.replace("-", "").replace(".", "").isalnum():
        raise HTTPException(status_code=400, detail="Некорректный ID файла")
    
    audio_path = Path(service_config.tts.output_dir) / file_id
    
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    try:
        audio_path.unlink()
        return {"success": True, "message": "Файл удален"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка удаления: {e}")

@app.post("/cache/clear")
async def clear_cache():
    """Очистка кеша TTS"""
    global tts_engine
    
    if not tts_engine:
        raise HTTPException(status_code=503, detail="TTS движок не инициализирован")
    
    tts_engine.clear_cache()
    return {"success": True, "message": "Кеш очищен"}

@app.get("/stats")
async def get_stats():
    """Получить статистику сервиса"""
    global tts_engine, service_config
    
    if not tts_engine:
        raise HTTPException(status_code=503, detail="TTS движок не инициализирован")
    
    try:
        health_info = tts_engine.health_check()
        voices_list = tts_engine.get_available_voices()
        
        # Подсчет файлов в output папке
        output_dir = Path(service_config.tts.output_dir)
        audio_files_count = len(list(output_dir.glob("*.wav"))) if output_dir.exists() else 0
        
        return {
            "service": {
                "name": "Vosk-TTS API",
                "version": "0.9.0",
                "uptime": time.time()  # TODO: реальное время работы
            },
            "tts_engine": health_info,
            "voices": {
                "total": len(voices_list),
                "ready": len(voices_list),  # Все голоса Vosk считаются готовыми
                "available": voices_list
            },
            "files": {
                "audio_files": audio_files_count,
                "output_dir": str(output_dir)
            }
        }
        
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    
    # Загружаем конфигурацию для запуска
    config = ServiceConfig()
    
    print(f"🚀 Запуск Vosk-TTS API на {config.api.host}:{config.api.port}")
    print(f"📖 Документация: http://{config.api.host}:{config.api.port}/docs")
    
    uvicorn.run(
        "src.vosk_tts.api:app",
        host=config.api.host,
        port=config.api.port,
        workers=config.api.workers,
        log_level=config.log_level.lower(),
        reload=False
    )
