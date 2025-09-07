
import sys
import os
import time
import numpy as np
from pathlib import Path

# Добавляем путь к нашему модулю
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def create_test_audio(duration: float = 2.0, sample_rate: int = 16000, frequency: float = 440.0) -> np.ndarray:
    """
    Создает тестовый аудио сигнал (синусоида)
    
    Args:
        duration: Длительность в секундах
        sample_rate: Частота дискретизации
        frequency: Частота тона в Герцах
    
    Returns:
        Аудио сигнал как numpy array
    """
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    # Создаем синусоидальный сигнал с затуханием в начале и конце
    audio = np.sin(2 * np.pi * frequency * t)
    
    # Добавляем огибающую для более естественного звучания
    fade_samples = int(0.1 * sample_rate)  # 0.1 секунды затухания
    fade_in = np.linspace(0, 1, fade_samples)
    fade_out = np.linspace(1, 0, fade_samples)
    
    audio[:fade_samples] *= fade_in
    audio[-fade_samples:] *= fade_out
    
    return audio.astype(np.float32)

def create_noisy_audio(duration: float = 3.0, sample_rate: int = 16000) -> np.ndarray:
    """
    Создает аудио с речью и паузами (имитация)
    
    Args:
        duration: Длительность в секундах
        sample_rate: Частота дискретизации
    
    Returns:
        Аудио сигнал с "речью" и паузами
    """
    samples = int(sample_rate * duration)
    audio = np.zeros(samples, dtype=np.float32)
    
    # Добавляем несколько "слов" (тональные сигналы разной частоты)
    word_segments = [
        (0.2, 0.8, 300),   # "слово" 1: 300 Hz
        (1.0, 1.4, 450),   # "слово" 2: 450 Hz  
        (1.8, 2.5, 350),   # "слово" 3: 350 Hz
    ]
    
    for start, end, freq in word_segments:
        start_idx = int(start * sample_rate)
        end_idx = int(end * sample_rate)
        
        if end_idx > samples:
            end_idx = samples
            
        segment_duration = (end_idx - start_idx) / sample_rate
        t = np.linspace(0, segment_duration, end_idx - start_idx, endpoint=False)
        
        # Создаем тональный сигнал
        tone = np.sin(2 * np.pi * freq * t) * 0.7
        
        # Добавляем немного шума для реалистичности
        noise = np.random.normal(0, 0.1, len(tone))
        segment = tone + noise
        
        audio[start_idx:end_idx] = segment.astype(np.float32)
    
    # Добавляем фоновый шум
    background_noise = np.random.normal(0, 0.05, samples)
    audio += background_noise.astype(np.float32)
    
    return audio

def test_triton_connection():
    """Проверка подключения к Triton серверу"""
    print("🔍 Проверка подключения к Triton серверу...")
    
    try:
        import requests
        
        # Проверяем основную готовность сервера
        response = requests.get("http://localhost:8000/v2/health/ready", timeout=5)
        if response.status_code != 200:
            print(f"❌ Triton сервер недоступен (код: {response.status_code})")
            return False
            
        print("✅ Triton сервер доступен")
        
        # Проверяем доступность нужных моделей
        models_to_check = ["gigaam_preprocessor", "gigaam-v2-ctc", "pyannote-vad"]
        
        for model in models_to_check:
            try:
                model_response = requests.get(f"http://localhost:8000/v2/models/{model}/ready", timeout=3)
                if model_response.status_code == 200:
                    print(f"✅ Модель {model} готова")
                else:
                    print(f"⚠️  Модель {model} не готова (код: {model_response.status_code})")
            except Exception as e:
                print(f"⚠️  Не удается проверить модель {model}: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Не удается подключиться к Triton серверу: {e}")
        return False

def test_asr_without_vad():
    """Тест ASR без VAD"""
    print("\n" + "="*60)
    print("🎤 ТЕСТ ASR БЕЗ VAD")
    print("="*60)
    
    try:
        import onnx_asr
        
        print("📥 Загрузка модели ASR...")
        try:
            asr = onnx_asr.load_model(
                model="gigaam-v2-ctc",
                triton_url="localhost:8000",
                cpu_preprocessing=True,
                path="."  # Путь к vocab файлу
            )
            vad = onnx_asr.load_vad("pyannote")
            asr = asr.with_vad(vad)

            print("✅ Модель ASR загружена")
        except Exception as e:
            print(f"❌ Ошибка загрузки модели ASR: {e}")
            print("💡 Убедитесь что:")
            print("  - Файл v2_vocab.txt находится в текущей директории")
            print("  - Модель gigaam-v2-ctc загружена в Triton")
            print("  - Модель gigaam_preprocessor загружена в Triton")
            return False
        
        # Тест 1: Реальный WAV файл  
        print("\n🔄 Тест 1: Тестовый WAV файл")
        try:
            start_time = time.time()
            result = asr.recognize("test.wav", sample_rate=16000)
            processing_time = time.time() - start_time
            
            print(f"  Результат: '{result}'")
            print(f"  Время обработки: {processing_time:.3f} сек")
        except Exception as e:
            print(f"  ❌ Ошибка распознавания WAV файла: {e}")
            print(f"  💡 Убедитесь что файл test.wav существует")
            return False
        
        # Тест 2: Короткий синтетический сигнал
        print("\n🔄 Тест 2: Короткий синусоидальный сигнал")
        short_audio = create_test_audio(duration=1.0, frequency=440)
        print(f"  Аудио: {len(short_audio)} сэмплов, {len(short_audio)/16000:.1f} сек")
        
        try:
            start_time = time.time()
            result = asr.recognize(short_audio, sample_rate=16000)
            processing_time = time.time() - start_time
            
            print(f"  Результат: '{result}'")
            print(f"  Время обработки: {processing_time:.3f} сек")
        except Exception as e:
            print(f"  ❌ Ошибка распознавания: {e}")
            print(f"  💡 Проверьте логи Triton сервера для деталей")
            return False
        
        # Тест 3: Более длинный сигнал
        print("\n🔄 Тест 3: Длинный аудио сигнал")
        long_audio = create_test_audio(duration=3.0, frequency=350)
        print(f"  Аудио: {len(long_audio)} сэмплов, {len(long_audio)/16000:.1f} сек")
        
        try:
            start_time = time.time()
            result = asr.recognize(long_audio, sample_rate=16000)
            processing_time = time.time() - start_time
            
            print(f"  Результат: '{result}'")
            print(f"  Время обработки: {processing_time:.3f} сек")
        except Exception as e:
            print(f"  ❌ Ошибка распознавания длинного аудио: {e}")
            return False
        
        # Тест 4: Батч обработка
        print("\n🔄 Тест 4: Батч обработка")
        audio_batch = [
            create_test_audio(duration=0.8, frequency=300),
            create_test_audio(duration=1.2, frequency=500),
            create_test_audio(duration=0.5, frequency=400)
        ]
        
        print(f"  Батч: {len(audio_batch)} аудио файлов")
        
        try:
            start_time = time.time()
            # Приводим к правильным типам
            audio_batch_typed = [np.array(audio, dtype=np.float32) for audio in audio_batch]
            results = asr.recognize(audio_batch_typed, sample_rate=16000)  # type: ignore
            processing_time = time.time() - start_time
            
            print(f"  Результаты:")
            for i, result in enumerate(results):
                print(f"    {i+1}: '{result}'")
            print(f"  Время обработки батча: {processing_time:.3f} сек")
        except Exception as e:
            print(f"  ❌ Ошибка батч обработки: {e}")
            return False
        
        print("\n✅ ASR без VAD работает корректно!")
        return True
        
    except Exception as e:
        print(f"\n❌ Ошибка в ASR без VAD: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_asr_with_vad():
    """Тест ASR с VAD"""
    print("\n" + "="*60)
    print("🎤🔇 ТЕСТ ASR С VAD")
    print("="*60)
    
    try:
        import onnx_asr
        
        print("📥 Загрузка модели ASR...")
        asr = onnx_asr.load_model(
            model="gigaam-v2-ctc",
            triton_url="localhost:8000",
            cpu_preprocessing=True,
            path="."
        )
        
        print("📥 Загрузка модели VAD...")
        vad = onnx_asr.load_vad(
            model="pyannote",
            triton_url="localhost:8000"
        )
        
        # Создаем ASR с VAD
        asr_with_vad = asr.with_vad(vad)
        print("✅ ASR с VAD настроен")
        
        # Тест 1: Реальный WAV файл
        print("\n🔄 Тест 1: Тестовый WAV файл с речевыми сегментами")
        test_audio_path = "test.wav"
        print(f"  Используем файл: {test_audio_path}")
        
        try:
            start_time = time.time()
            segments = list(asr_with_vad.recognize(test_audio_path, sample_rate=16000))
            processing_time = time.time() - start_time
        except Exception as e:
            print(f"  ❌ Ошибка обработки WAV файла: {e}")
            return False
        
        print(f"  Найдено сегментов: {len(segments)}")
        for i, segment in enumerate(segments):
            print(f"    Сегмент {i+1}: '{segment.text}' [{segment.start:.2f}s - {segment.end:.2f}s]")
        print(f"  Время обработки: {processing_time:.3f} сек")
        
        # Тест 2: Тихое аудио (должно не найти речи)
        print("\n🔄 Тест 2: Тихое аудио (фоновый шум)")
        quiet_audio = np.random.normal(0, 0.02, int(16000 * 2)).astype(np.float32)
        print(f"  Аудио: {len(quiet_audio)} сэмплов, {len(quiet_audio)/16000:.1f} сек (только шум)")
        
        start_time = time.time()
        segments = list(asr_with_vad.recognize(quiet_audio, sample_rate=16000))
        processing_time = time.time() - start_time
        
        print(f"  Найдено сегментов: {len(segments)}")
        if segments:
            for i, segment in enumerate(segments):
                print(f"    Сегмент {i+1}: '{segment.text}' [{segment.start:.2f}s - {segment.end:.2f}s]")
        else:
            print("    (речь не обнаружена - это ожидаемо)")
        print(f"  Время обработки: {processing_time:.3f} сек")
        
        # Тест 3: Сравнение с и без VAD
        print("\n🔄 Тест 3: Сравнение ASR с VAD и без VAD")
        test_audio = create_noisy_audio(duration=2.5)
        
        # Без VAD
        start_time = time.time()
        result_no_vad = asr.recognize(test_audio, sample_rate=16000)
        time_no_vad = time.time() - start_time
        
        # С VAD
        start_time = time.time()
        segments_with_vad = list(asr_with_vad.recognize(test_audio, sample_rate=16000))
        time_with_vad = time.time() - start_time
        
        print(f"  Без VAD: '{result_no_vad}' (время: {time_no_vad:.3f}s)")
        print(f"  С VAD: {len(segments_with_vad)} сегментов (время: {time_with_vad:.3f}s)")
        for i, segment in enumerate(segments_with_vad):
            print(f"    Сегмент {i+1}: '{segment.text}' [{segment.start:.2f}s - {segment.end:.2f}s]")
        
        print("\n✅ ASR с VAD работает корректно!")
        return True
        
    except Exception as e:
        print(f"\n❌ Ошибка в ASR с VAD: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_different_sample_rates():
    """Тест работы с разными частотами дискретизации"""
    print("\n" + "="*60)
    print("📊 ТЕСТ РАЗНЫХ ЧАСТОТ ДИСКРЕТИЗАЦИИ")
    print("="*60)
    
    try:
        import onnx_asr
        
        asr = onnx_asr.load_model(
            model="gigaam-v2-ctc",
            triton_url="localhost:8000",
            cpu_preprocessing=True,
            path="."
        )
        
        # Тестируем разные частоты (только поддерживаемые)
        from onnx_asr.utils import SampleRates
        from typing import get_args
        
        supported_rates = get_args(SampleRates)
        sample_rates = [sr for sr in [8000, 22050, 44100, 48000] if sr in supported_rates]
        
        for sr in sample_rates:
            print(f"\n🔄 Тест частоты {sr} Hz")
            
            # Создаем аудио с соответствующей частотой
            duration = 1.0
            samples = int(sr * duration)
            t = np.linspace(0, duration, samples, endpoint=False)
            audio = np.sin(2 * np.pi * 440 * t).astype(np.float32)
            
            print(f"  Аудио: {len(audio)} сэмплов при {sr} Hz")
            
            try:
                start_time = time.time()
                # Приводим sr к правильному типу SampleRates
                result = asr.recognize(audio, sample_rate=sr)  # type: ignore
                processing_time = time.time() - start_time
                
                print(f"  ✅ Результат: '{result}' (время: {processing_time:.3f}s)")
            except Exception as e:
                print(f"  ❌ Ошибка: {e}")
        
        print("\n✅ Тест частот дискретизации завершен!")
        return True
        
    except Exception as e:
        print(f"\n❌ Ошибка в тесте частот: {e}")
        return False

def test_performance_benchmark():
    """Бенчмарк производительности"""
    print("\n" + "="*60)
    print("⚡ БЕНЧМАРК ПРОИЗВОДИТЕЛЬНОСТИ")
    print("="*60)
    
    try:
        import onnx_asr
        
        asr = onnx_asr.load_model(
            model="gigaam-v2-ctc",
            triton_url="localhost:8000",
            cpu_preprocessing=True,
            path="."
        )
        
        # Тест производительности для разных длин аудио
        durations = [0.5, 1.0, 2.0, 5.0, 10.0]
        
        print("Длительность | Время обработки | Real-time фактор")
        print("-" * 50)
        
        for duration in durations:
            audio = create_test_audio(duration=duration, frequency=400)
            
            # Прогрев
            asr.recognize(audio[:int(16000 * 0.1)], sample_rate=16000)
            
            # Измерение
            start_time = time.time()
            result = asr.recognize(audio, sample_rate=16000)
            processing_time = time.time() - start_time
            
            real_time_factor = processing_time / duration
            
            print(f"{duration:8.1f}s   | {processing_time:12.3f}s    | {real_time_factor:12.3f}x")
        
        print("\n📊 Real-time фактор < 1.0 означает обработку быстрее реального времени")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Ошибка в бенчмарке: {e}")
        return False

def check_dependencies():
    """Проверка необходимых зависимостей"""
    print("🔍 Проверка зависимостей...")
    
    missing_deps = []
    
    try:
        import requests
        print("✅ requests")
    except ImportError:
        missing_deps.append("requests")
        print("❌ requests")
    
    try:
        import scipy
        print("✅ scipy")
    except ImportError:
        missing_deps.append("scipy")
        print("❌ scipy")
    
    try:
        import tritonclient
        print("✅ tritonclient")
    except ImportError:
        missing_deps.append("tritonclient[all]")
        print("❌ tritonclient")
    
    if missing_deps:
        print(f"\n❌ Отсутствуют зависимости: {', '.join(missing_deps)}")
        print("Установите их командой:")
        print(f"pip install {' '.join(missing_deps)}")
        return False
    
    print("✅ Все зависимости установлены")
    return True

def main():
    """Основная функция тестирования"""
    print("🚀 ТЕСТИРОВАНИЕ СЕРВИСА ASR")
    print("=" * 80)
    print("Тестируем Triton-based ASR сервис с поддержкой VAD")
    print("=" * 80)
    
    # Проверяем зависимости
    if not check_dependencies():
        return
    
    # Проверяем подключение к Triton
    if not test_triton_connection():
        print("\n❌ Triton сервер недоступен. Убедитесь что:")
        print("1. Docker контейнер с Triton запущен")
        print("2. Сервер доступен на localhost:8000") 
        print("3. Модели загружены в Triton:")
        print("   - gigaam_preprocessor")
        print("   - gigaam-v2-ctc") 
        print("   - pyannote-vad")
        return
    
    # Список тестов
    tests = [
        ("ASR без VAD", test_asr_without_vad),
        ("ASR с VAD", test_asr_with_vad),
        ("Разные частоты дискретизации", test_different_sample_rates),
        ("Бенчмарк производительности", test_performance_benchmark),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            print(f"\n🔄 Запуск теста: {test_name}")
            success = test_func()
            results.append((test_name, success))
        except KeyboardInterrupt:
            print(f"\n⚠️ Тест '{test_name}' прерван пользователем")
            results.append((test_name, False))
            break
        except Exception as e:
            print(f"\n❌ Неожиданная ошибка в тесте '{test_name}': {e}")
            results.append((test_name, False))
    
    # Итоги
    print("\n" + "="*80)
    print("📋 ИТОГИ ТЕСТИРОВАНИЯ")
    print("="*80)
    
    passed = 0
    for test_name, success in results:
        status = "✅ ПРОШЕЛ" if success else "❌ НЕ ПРОШЕЛ"
        print(f"{test_name:<35} | {status}")
        if success:
            passed += 1
    
    total = len(results)
    print("-" * 80)
    print(f"ИТОГО: {passed}/{total} тестов прошли успешно")
    
    if passed == total:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОШЛИ! Сервис работает корректно.")
    else:
        print(f"\n⚠️ {total - passed} тестов не прошли. Проверьте настройки Triton и моделей.")
    
    print("\n💡 Для устранения проблем:")
    print("- Проверьте логи Triton сервера")
    print("- Убедитесь что модели загружены: curl localhost:8000/v2/models")
    print("- Проверьте конфигурацию моделей в triton_model_repository/")

if __name__ == "__main__":
    main()
