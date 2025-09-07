"""
Triton Inference Server клиент для Vosk-TTS
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List
import numpy as np

try:
    import tritonclient.http as httpclient
    import tritonclient.grpc as grpcclient
    from tritonclient.utils import np_to_triton_dtype
    TRITON_AVAILABLE = True
except ImportError:
    logging.warning("Triton client не установлен. Установите: pip install tritonclient[all]")
    TRITON_AVAILABLE = False

from .config import TTSConfig

logger = logging.getLogger(__name__)


class TritonTTSClient:
    """
    Клиент для взаимодействия с Triton Inference Server для TTS
    """
    
    def __init__(self, config: TTSConfig):
        self.config = config
        self.http_client: Optional[httpclient.InferenceServerClient] = None
        self.grpc_client: Optional[grpcclient.InferenceServerClient] = None
        self._available_models: Dict[str, Dict[str, Any]] = {}
        self._is_initialized = False
        
    async def initialize(self) -> bool:
        """Инициализация клиента"""
        
        if not TRITON_AVAILABLE:
            logger.error("Triton client недоступен")
            return False
            
        try:
            # Парсим URL
            if ":" in self.config.triton_url:
                host, port = self.config.triton_url.split(":", 1)
                port = int(port)
            else:
                host = self.config.triton_url
                port = 8000
            
            # Создаем HTTP клиент
            self.http_client = httpclient.InferenceServerClient(
                url=f"{host}:{port}",
                verbose=False
            )
            
            # Проверяем доступность сервера
            if not self.http_client.is_server_live():
                logger.error("Triton сервер недоступен")
                return False
                
            if not self.http_client.is_server_ready():
                logger.error("Triton сервер не готов")
                return False
            
            # Получаем список доступных моделей
            models = self.http_client.get_model_repository_index()
            
            for model in models:
                model_name = model['name']
                
                # Проверяем что модель загружена
                if model['state'] == 'READY':
                    try:
                        model_metadata = self.http_client.get_model_metadata(model_name)
                        model_config = self.http_client.get_model_config(model_name)
                        
                        self._available_models[model_name] = {
                            'name': model_name,
                            'state': model['state'],
                            'metadata': model_metadata,
                            'config': model_config
                        }
                        
                        logger.info(f"TTS модель загружена: {model_name}")
                        
                    except Exception as e:
                        logger.warning(f"Не удалось загрузить метаданные модели {model_name}: {e}")
            
            logger.info(f"Triton TTS клиент инициализирован. Доступно моделей: {len(self._available_models)}")
            self._is_initialized = True
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации Triton клиента: {e}")
            return False
    
    async def synthesize_text(
        self, 
        text: str, 
        voice: str = None,
        speed: float = None,
        pitch: float = None
    ) -> Optional[np.ndarray]:
        """
        Синтез текста в аудио через Triton
        
        Args:
            text: Текст для синтеза
            voice: Имя голоса
            speed: Скорость речи 
            pitch: Высота тона
            
        Returns:
            Аудио массив или None при ошибке
        """
        
        if not self._is_initialized:
            logger.error("Triton клиент не инициализирован")
            return None
            
        if not text.strip():
            logger.warning("Пустой текст для синтеза")
            return None
        
        # Используем голос по умолчанию если не указан
        if voice is None:
            voice = self.config.default_voice
        
        # Получаем конфигурацию голоса
        if voice not in self.config.voices:
            logger.error(f"Неизвестный голос: {voice}")
            return None
            
        voice_config = self.config.voices[voice]
        model_name = voice_config.model_name
        
        # Проверяем доступность модели
        if model_name not in self._available_models:
            logger.error(f"TTS модель недоступна: {model_name}")
            return None
        
        try:
            # Подготавливаем входные данные
            inputs = []
            outputs = []
            
            # Текст как строка
            text_data = np.array([text.encode('utf-8')], dtype=object)
            text_input = httpclient.InferInput("text", text_data.shape, np_to_triton_dtype(text_data.dtype))
            text_input.set_data_from_numpy(text_data)
            inputs.append(text_input)
            
            # Параметры синтеза
            params = {
                'speed': speed or self.config.default_speed,
                'pitch': pitch or self.config.default_pitch,
                'sample_rate': voice_config.sample_rate
            }
            
            for param_name, param_value in params.items():
                param_data = np.array([param_value], dtype=np.float32)
                param_input = httpclient.InferInput(param_name, param_data.shape, np_to_triton_dtype(param_data.dtype))
                param_input.set_data_from_numpy(param_data)
                inputs.append(param_input)
            
            # Выходные данные
            outputs.append(httpclient.InferRequestedOutput("audio"))
            
            # Выполняем инференс
            response = self.http_client.infer(
                model_name=model_name,
                inputs=inputs,
                outputs=outputs,
                timeout=self.config.triton_timeout
            )
            
            # Получаем результат
            audio_output = response.as_numpy("audio")
            
            if audio_output is not None and len(audio_output) > 0:
                logger.debug(f"TTS синтез успешен: {len(audio_output)} сэмплов")
                return audio_output
            else:
                logger.error("Пустой результат от TTS модели")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка TTS синтеза: {e}")
            return None
    
    def get_available_voices(self) -> Dict[str, Dict[str, Any]]:
        """Получает список доступных голосов"""
        
        available_voices = {}
        
        for voice_name, voice_config in self.config.voices.items():
            model_name = voice_config.model_name
            is_ready = model_name in self._available_models
            
            available_voices[voice_name] = {
                'name': voice_name,
                'model_name': model_name,
                'gender': voice_config.gender,
                'language': voice_config.language,
                'sample_rate': voice_config.sample_rate,
                'description': voice_config.description,
                'ready': is_ready
            }
        
        return available_voices
    
    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Получает информацию о модели"""
        return self._available_models.get(model_name)
    
    def is_model_ready(self, model_name: str) -> bool:
        """Проверяет готовность модели"""
        return model_name in self._available_models
    
    def get_server_info(self) -> Dict[str, Any]:
        """Получает информацию о сервере"""
        
        if not self._is_initialized:
            return {"status": "not_initialized"}
        
        try:
            metadata = self.http_client.get_server_metadata()
            return {
                "status": "ready",
                "name": metadata.get('name', 'unknown'),
                "version": metadata.get('version', 'unknown'),
                "models_count": len(self._available_models),
                "available_models": list(self._available_models.keys())
            }
        except Exception as e:
            logger.error(f"Ошибка получения информации сервера: {e}")
            return {"status": "error", "error": str(e)}
    
    async def health_check(self) -> bool:
        """Проверка здоровья сервиса"""
        
        if not self._is_initialized:
            return False
            
        try:
            return (
                self.http_client.is_server_live() and 
                self.http_client.is_server_ready()
            )
        except Exception:
            return False
    
    async def cleanup(self):
        """Очистка ресурсов"""
        
        if self.http_client:
            self.http_client.close()
            self.http_client = None
            
        if self.grpc_client:
            self.grpc_client.close()
            self.grpc_client = None
        
        self._available_models.clear()
        self._is_initialized = False
        
        logger.info("Triton TTS клиент закрыт")
