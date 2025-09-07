"""
Triton Python Backend для vosk-tts модели Pavel
"""

import json
import logging
import numpy as np
import subprocess
import tempfile
import os
import soundfile as sf
from pathlib import Path

import triton_python_backend_utils as pb_utils

logger = logging.getLogger(__name__)


class TritonPythonModel:
    """Triton Python модель для vosk-tts Pavel"""
    
    def initialize(self, args):
        """Инициализация модели"""
        
        self.model_config = model_config = json.loads(args['model_config'])
        self.model_name = "vosk-tts-pavel"
        self.voice_path = "russian/pavel"
        
        # Проверяем доступность vosk-tts
        try:
            result = subprocess.run(
                ["python", "-m", "vosk_tts", "--help"], 
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                raise Exception("vosk-tts CLI недоступен")
                
            logger.info(f"✅ {self.model_name} модель инициализирована")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации {self.model_name}: {e}")
            raise
    
    def execute(self, requests):
        """Выполнение инференса"""
        
        responses = []
        
        for request in requests:
            try:
                # Извлекаем входные данные
                text_tensor = pb_utils.get_input_tensor_by_name(request, "text")
                text = text_tensor.as_numpy()[0].decode('utf-8')
                
                # Опциональные параметры
                speed = 1.0
                pitch = 1.0
                sample_rate = 22050
                
                speed_tensor = pb_utils.get_input_tensor_by_name(request, "speed")
                if speed_tensor is not None:
                    speed = float(speed_tensor.as_numpy()[0])
                
                pitch_tensor = pb_utils.get_input_tensor_by_name(request, "pitch") 
                if pitch_tensor is not None:
                    pitch = float(pitch_tensor.as_numpy()[0])
                
                sample_rate_tensor = pb_utils.get_input_tensor_by_name(request, "sample_rate")
                if sample_rate_tensor is not None:
                    sample_rate = int(sample_rate_tensor.as_numpy()[0])
                
                # Синтез аудио
                audio_data = self._synthesize_audio(text, speed, pitch, sample_rate)
                
                if audio_data is None:
                    raise Exception("Не удалось синтезировать аудио")
                
                # Подготовка выходных тензоров
                audio_tensor = pb_utils.Tensor("audio", audio_data.astype(np.float32))
                sample_rate_tensor = pb_utils.Tensor("sample_rate_out", np.array([sample_rate], dtype=np.float32))
                
                response = pb_utils.InferenceResponse(
                    output_tensors=[audio_tensor, sample_rate_tensor]
                )
                
                responses.append(response)
                
                logger.debug(f"TTS синтез успешен: {len(audio_data)} сэмплов")
                
            except Exception as e:
                logger.error(f"Ошибка TTS синтеза: {e}")
                
                error_response = pb_utils.InferenceResponse(
                    error=pb_utils.TritonError(f"TTS Error: {str(e)}")
                )
                responses.append(error_response)
        
        return responses
    
    def _synthesize_audio(self, text: str, speed: float, pitch: float, sample_rate: int) -> np.ndarray:
        """Синтез аудио через vosk-tts CLI"""
        
        try:
            # Создаем временный файл для аудио
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
            
            # Команда для vosk-tts
            cmd = [
                "python", "-m", "vosk_tts",
                "--text", text,
                "--voice", self.voice_path,
                "--output", temp_path,
                "--sample-rate", str(sample_rate)
            ]
            
            if speed != 1.0:
                cmd.extend(["--speed", str(speed)])
            
            # Выполняем синтез
            result = subprocess.run(
                cmd, 
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"vosk-tts error: {result.stderr}")
                return None
            
            # Читаем результат
            if os.path.exists(temp_path):
                audio_data, _ = sf.read(temp_path)
                
                # Очищаем временный файл
                os.unlink(temp_path)
                
                return audio_data
            else:
                logger.error("Аудио файл не был создан")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error("Таймаут TTS синтеза")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка TTS: {e}")
            return None
    
    def finalize(self):
        """Финализация модели"""
        logger.info(f"🛑 {self.model_name} модель завершена")
