#!/usr/bin/env python3
"""Современный детектор окончания речи на основе Silero VAD."""

import time
import numpy as np
import torch
from typing import Dict, Any, Tuple
from collections import deque


class ModernSpeechDetector:
    """Современный детектор окончания речи с использованием Silero VAD."""
    
    def __init__(self, config: Dict[str, Any], sample_rate: int = 8000, chunk_size: int = 2400):
        self.config = config
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        
        # Параметры из конфигурации
        self.silence_duration = config.get('silence_duration', 1.5)
        self.min_speech_duration = config.get('min_speech_duration', 0.8)
        self.listening_timeout = config.get('listening_timeout', 25)
        self.chunk_timeout = config.get('chunk_timeout', 0.05)
        
        # Параметры Silero VAD
        self.threshold = config.get('threshold', 0.5)
        self.min_silence_duration = config.get('min_silence_duration', 0.5)
        
        # Состояние детектора
        self.speech_detected = False
        self.speech_start_time = None
        self.silence_chunks = 0
        self.speech_chunks = 0
        self.last_speech_time = None
        
        # Адаптивные счетчики
        self.required_silence_chunks = int(self.silence_duration / self.chunk_timeout)
        self.min_speech_chunks = int(self.min_speech_duration / self.chunk_timeout)
        
        # Буферы для анализа
        self.audio_buffer = deque(maxlen=int(3.0 * sample_rate))
        self.speech_probabilities = deque(maxlen=20)
        
        # Инициализация Silero VAD
        self._init_silero_vad()
        
        # Статистика для адаптации
        self.total_speech_time = 0.0
        self.total_silence_time = 0.0
        
        print(f"🔧 Современный детектор речи (Silero VAD):")
        print(f"   - Анализ 3-секундных отрезков на наличие голоса")
        print(f"   - Мин. длительность речи: {self.min_speech_duration}s")
        print(f"   - Порог VAD: {self.threshold}")
        print(f"   - Завершение при отсутствии голоса в последние 3 секунды")
    
    def _init_silero_vad(self):
        """Инициализация Silero VAD модели."""
        try:
            import torch
            from silero_vad import load_silero_vad
            
            # Загружаем модель Silero VAD с правильными параметрами
            self.vad_model, self.utils = load_silero_vad(
                torch.jit.load, 
                'silero_vad.jit'
            )
            
            # Настраиваем модель
            self.vad_model.eval()
            self.vad_model = self.vad_model.to('cpu')
            
            print(f"✅ Silero VAD модель загружена")
        except Exception as e:
            print(f"⚠️ Ошибка загрузки Silero VAD: {e}")
            print(f"⚠️ Пробуем альтернативный способ загрузки...")
            
            try:
                # Альтернативный способ загрузки
                import torch
                from silero_vad import load_silero_vad
                
                self.vad_model, self.utils = load_silero_vad(
                    torch.jit.load, 
                    'silero_vad.jit'
                )
                
                self.vad_model.eval()
                self.vad_model = self.vad_model.to('cpu')
                
                print(f"✅ Silero VAD модель загружена (ONNX режим)")
            except Exception as e2:
                print(f"⚠️ Ошибка альтернативной загрузки Silero VAD: {e2}")
                print(f"⚠️ Используем fallback режим - детекция отключена")
                self.vad_model = None
                self.utils = None
    
    def _calculate_energy(self, audio_chunk: np.ndarray) -> float:
        """Вычислить энергию аудио чанка."""
        if len(audio_chunk) == 0:
            return 0.0
        return np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2))
    
    def _calculate_spectral_centroid(self, audio_chunk: np.ndarray) -> float:
        """Вычислить спектральный центроид."""
        if len(audio_chunk) < 64:
            return 0.0
        
        try:
            fft = np.fft.fft(audio_chunk)
            magnitude = np.abs(fft[:len(fft)//2])
            
            if np.sum(magnitude) == 0:
                return 0.0
            
            freqs = np.linspace(0, self.sample_rate/2, len(magnitude))
            centroid = np.sum(freqs * magnitude) / np.sum(magnitude)
            return centroid
        except:
            return 0.0
    
    def _is_speech_silero_vad(self, audio_chunk: np.ndarray) -> Tuple[bool, float]:
        """Определить наличие речи с помощью Silero VAD."""
        if self.vad_model is None or len(audio_chunk) == 0:
            # Если VAD не загружен - считаем что речи нет
            print(f"🔇 VAD не загружен или пустой чанк - речь: False")
            return False, 0.0
        
        try:
            # Конвертируем в torch tensor
            audio_tensor = torch.from_numpy(audio_chunk.astype(np.float32))
            
            # Нормализуем аудио
            if len(audio_tensor) > 0:
                max_val = torch.max(torch.abs(audio_tensor))
                if max_val > 0:
                    audio_tensor = audio_tensor / max_val
                else:
                    print(f"🔇 Нулевая амплитуда - речь: False")
                    return False, 0.0
            
            # Получаем вероятность речи
            with torch.no_grad():
                speech_prob = self.vad_model(audio_tensor, self.sample_rate).item()
            
            # Более строгий порог для избежания ложных срабатываний
            effective_threshold = self.threshold + 0.2
            is_speech = speech_prob > effective_threshold
            
            # Подробное логирование
            print(f"🎯 Silero VAD: prob={speech_prob:.3f}, threshold={effective_threshold:.3f}, speech={is_speech}")
            
            return is_speech, speech_prob
                
        except Exception as e:
            print(f"⚠️ Ошибка Silero VAD: {e}")
            return False, 0.0
    
    def _is_speech_energy(self, audio_chunk: np.ndarray) -> bool:
        """Определить речь по энергии."""
        energy = self._calculate_energy(audio_chunk)
        self.energy_history.append(energy)
        
        if len(self.energy_history) > 5:
            avg_energy = np.mean(list(self.energy_history)[-5:])
            adaptive_threshold = max(self.energy_threshold, avg_energy * 0.6)
        else:
            adaptive_threshold = self.energy_threshold
        
        return energy > adaptive_threshold
    
    def _analyze_3_second_segment(self) -> bool:
        """Анализировать 3-секундный отрезок на наличие речи."""
        if len(self.audio_buffer) < self.sample_rate * 3:  # Меньше 3 секунд
            print(f"🔍 Анализ 3с: недостаточно данных ({len(self.audio_buffer)}/{self.sample_rate * 3})")
            return False
        
        # Берем последние 3 секунды из буфера
        segment = np.array(list(self.audio_buffer)[-self.sample_rate * 3:])
        
        # Разбиваем на чанки по 0.5 секунды для анализа
        chunk_size = self.sample_rate // 2  # 0.5 секунды
        speech_chunks = 0
        total_chunks = 0
        
        print(f"🔍 Анализ 3-секундного отрезка: {len(segment)} сэмплов, чанки по {chunk_size}")
        
        for i in range(0, len(segment) - chunk_size, chunk_size):
            chunk = segment[i:i + chunk_size]
            is_speech, confidence = self._is_speech_silero_vad(chunk)
            total_chunks += 1
            
            if is_speech:
                speech_chunks += 1
        
        # Если больше 30% чанков содержат речь - считаем что есть голос
        speech_ratio = speech_chunks / max(total_chunks, 1)
        has_speech = speech_ratio > 0.3
        
        print(f"🔍 Результат анализа 3с: {speech_chunks}/{total_chunks} чанков с речью, ratio={speech_ratio:.2f}, has_speech={has_speech}")
        
        return has_speech
    
    def _is_speech_combined(self, audio_chunk: np.ndarray) -> Tuple[bool, float]:
        """Детекция речи на основе Silero VAD модели или fallback на энергию."""
        # Пробуем Silero VAD
        silero_result, confidence = self._is_speech_silero_vad(audio_chunk)
        
        # Если VAD не загружен, используем простую детекцию по энергии
        if self.vad_model is None:
            energy = self._calculate_energy(audio_chunk)
            # Более строгий порог для fallback режима
            energy_threshold = 500.0  # Увеличиваем порог еще больше
            is_speech = energy > energy_threshold
            confidence = min(energy / 2000.0, 1.0)  # Нормализуем энергию
            print(f"🔧 Fallback режим: energy={energy:.1f}, threshold={energy_threshold:.1f}, speech={is_speech}")
            return is_speech, confidence
        
        # Если Silero VAD говорит "речь" - верим ему
        if silero_result:
            return True, confidence
        
        # Если Silero VAD не уверен - считаем тишиной
        return False, confidence
    
    def _should_end_speech(self, current_time: float) -> bool:
        """Определить, следует ли завершить речь на основе анализа 3-секундных отрезков."""
        if not self.speech_detected:
            return False
        
        speech_duration = current_time - self.speech_start_time if self.speech_start_time else 0
        
        if speech_duration < self.min_speech_duration:
            return False
        
        # Основное правило: анализируем 3-секундный отрезок
        # Если в последние 3 секунды нет голоса - завершаем речь
        if len(self.audio_buffer) >= self.sample_rate * 3:
            has_speech_in_3_seconds = self._analyze_3_second_segment()
            if not has_speech_in_3_seconds:
                # Дополнительная проверка: убеждаемся что тишина длится достаточно долго
                time_since_last_speech = current_time - self.last_speech_time if self.last_speech_time else 0
                if time_since_last_speech >= self.silence_duration:
                    print(f"✅ Завершение по анализу 3-секундного отрезка (нет голоса в последние 3 секунды, тишина: {time_since_last_speech:.1f}s)")
                    return True
                else:
                    print(f"🔍 3-секундный анализ показал тишину, но тишина слишком короткая ({time_since_last_speech:.1f}s < {self.silence_duration}s)")
        
        # Защита от зависания (принудительное завершение)
        if speech_duration >= self.listening_timeout:
            print(f"✅ Принудительное завершение (длительность: {speech_duration:.1f}s, лимит: {self.listening_timeout}s)")
            return True
        
        return False
    
    def process_chunk(self, audio_chunk: np.ndarray) -> bool:
        """Обработать чанк аудио и определить, закончилась ли речь."""
        if len(audio_chunk) == 0:
            return False
        
        current_time = time.time()
        self.audio_buffer.extend(audio_chunk)
        
        is_speech, confidence = self._is_speech_combined(audio_chunk)
        self.speech_probabilities.append(confidence)
        
        # Логируем каждый чанк для отладки
        print(f"📊 Чанк: speech={is_speech}, conf={confidence:.3f}, buffer={len(self.audio_buffer)}")
        
        if is_speech:
            if not self.speech_detected:
                self.speech_detected = True
                self.speech_start_time = current_time
                self.silence_chunks = 0
                self.speech_chunks = 0
                self.last_speech_time = current_time
                print(f"�� Речь началась (SpeechBrain, уверенность: {confidence:.2f})")
            else:
                self.speech_chunks += 1
                self.silence_chunks = 0
                self.last_speech_time = current_time
                self.total_speech_time += self.chunk_timeout
                
                if self.speech_chunks % 40 == 0:
                    speech_duration = current_time - self.speech_start_time
                    print(f"🎤 Продолжение речи ({speech_duration:.1f}s, уверенность: {confidence:.2f})")
        else:
            if self.speech_detected:
                self.silence_chunks += 1
                self.total_silence_time += self.chunk_timeout
                
                if self.silence_chunks == 1:
                    print(f"🔇 Начало тишины (SpeechBrain, уверенность: {confidence:.2f})")
                elif self.silence_chunks % 20 == 0:
                    speech_duration = current_time - self.speech_start_time if self.speech_start_time else 0
                    print(f"🔇 Тишина {self.silence_chunks}/{self.required_silence_chunks} (речь: {speech_duration:.1f}s)")
                
                if self._should_end_speech(current_time):
                    speech_duration = current_time - self.speech_start_time if self.speech_start_time else 0
                    print(f"✅ Речь завершена (речь: {speech_duration:.1f}s, тишина: {self.silence_chunks} чанков)")
                    return True
            else:
                self.silence_chunks += 1
                self.total_silence_time += self.chunk_timeout
                if self.silence_chunks % 100 == 0:
                    print(f"🔇 Ожидание речи... ({self.silence_chunks * self.chunk_timeout:.1f}s)")
        
        if self.speech_detected and self.last_speech_time:
            time_since_speech = current_time - self.last_speech_time
            if time_since_speech > self.listening_timeout:
                print(f"⏰ Таймаут прослушивания ({self.listening_timeout}s)")
                return True
        
        return False
    
    def reset(self):
        """Сбросить состояние детектора."""
        self.speech_detected = False
        self.speech_start_time = None
        self.silence_chunks = 0
        self.speech_chunks = 0
        self.last_speech_time = None
        self.audio_buffer.clear()
        self.speech_probabilities.clear()
        self.total_speech_time = 0.0
        self.total_silence_time = 0.0
        print("🔄 Современный детектор сброшен")
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику детектора."""
        return {
            'speech_detected': self.speech_detected,
            'speech_duration': time.time() - self.speech_start_time if self.speech_start_time else 0,
            'silence_chunks': self.silence_chunks,
            'speech_chunks': self.speech_chunks,
            'threshold': self.threshold,
            'speech_ratio': self.total_speech_time / max(self.total_speech_time + self.total_silence_time, 1e-6),
            'avg_speech_prob': np.mean(list(self.speech_probabilities)) if self.speech_probabilities else 0.0
        }
