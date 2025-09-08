# 🎤 Система технических интервью с ИИ-анализом эмоций

Полноценная система для проведения адаптивных технических интервью с использованием:
- **Whisper** для распознавания речи (русский + английский)
- **wav2vec2-xlsr-53-russian-emotion-recognition** для анализа эмоций
- **LangGraph** для адаптивной генерации вопросов
- **ChatGPT** для оценки ответов и создания новых вопросов
- **WebRTC** веб-интерфейс для проведения интервью

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
# Создаем виртуальное окружение
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# или
venv\Scripts\activate     # Windows

# Устанавливаем зависимости
pip install -r requirements.txt
```

### 2. Настройка конфигурации

Отредактируйте `interview_config.json` и укажите ваш OpenAI API ключ:

```json
{
  "openai_api_key": "ваш-api-ключ-здесь",
  ...
}
```

### 3. Запуск веб-сервера

```bash
# Запускаем сервер
python3 start_server.py
```

Сервер будет доступен по адресу: `http://localhost:8000`

### 4. Создание комнаты интервью

**В новом терминале:**

```bash
# Linux/macOS
./create_room.sh

# Windows/Python
python3 create_room.py
```

### 5. Проведение интервью

1. Откройте ссылку в браузере (например: `http://localhost:8000/room/ABC12345`)
2. Нажмите кнопку **"Начать Интервью"**
3. Разрешите доступ к микрофону
4. Нажмите **"Начать запись"** и говорите в микрофон
5. Нажмите **"Остановить"** когда закончите говорить
6. Нажмите **"Отправить ответ"** для отправки записи на сервер
7. Получайте адаптивные вопросы на основе ваших ответов

## 🎯 Особенности системы

### 🔄 Адаптивные вопросы
- Система автоматически генерирует сложные вопросы на основе ответов
- Поддерживает 7 категорий эмоций (anger, disgust, enthusiasm, fear, happiness, neutral, sadness)
- Использует Whisper для распознавания речи (русский + английский)

### 🎤 Аудио обработка
- **TTS**: OpenAI TTS с отправкой аудио в браузер
- **ASR**: OpenAI Whisper для распознавания речи
- **Browser Recording**: Web Audio API для записи в браузере
- **Emotion Analysis**: wav2vec2-xlsr-53-russian-emotion-recognition

### 🌐 Веб-интерфейс
- Современный HTML5 интерфейс
- WebSocket для реального времени
- Автоматическое переподключение
- Логирование всех событий

## 📡 API Endpoints

### REST API
- `GET /` - Статус сервера
- `POST /api/rooms/create` - Создание комнаты с вопросами
- `GET /api/rooms/{code}/status` - Статус комнаты

### WebSocket
- `WebSocket /ws/{code}` - Подключение к интервью

### Веб-интерфейс
- `GET /room/{code}` - HTML интерфейс для проведения интервью

## 🔧 Конфигурация

Настройки находятся в `interview_config.json`:

```json
{
  "openai_api_key": "ваш-api-ключ",
  "max_depth": 3,
  "min_score_threshold": 7,
  "speech_detection": {
    "silence_duration": 3.0,
    "listening_timeout": 120
  },
  "drivers": {
    "asr": {
      "type": "whisper",
      "config": {
        "model_size": "base",
        "language": "auto"
      }
    },
    "tts": {
      "type": "gtts",
      "config": {
        "language": "ru"
      }
    }
  }
}
```

## 🏗️ Архитектура

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Внешний       │    │   FastAPI        │    │   Пользователь  │
│   сервис        │───▶│   + WebSocket    │◀───│   Браузер       │
│                 │    │   + LangGraph    │    │   + WebRTC      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │   AI Pipeline    │
                       │   Whisper +      │
                       │   Emotion AI +   │
                       │   ChatGPT        │
                       └──────────────────┘
```

## 📁 Структура проекта

```
interview_system/
├── interview_server.py          # Основной веб-сервер
├── langgraph_interview.py       # Логика интервью с LangGraph
├── modern_speech_detector.py    # Детектор окончания речи
├── interview_config.json        # Конфигурация системы
├── technical_questions.json     # Начальные вопросы
├── create_room.sh              # Скрипт создания комнаты (Linux/macOS)
├── create_room.py              # Скрипт создания комнаты (Python)
├── start_server.py             # Запуск сервера
├── requirements.txt            # Зависимости
└── interview_system_package/   # Пакет драйверов
    └── interview_system/
        └── drivers/
            ├── whisper_asr.py      # Whisper ASR драйвер
            ├── emotion_analyzer.py # Анализатор эмоций
            └── ...
```

## 🛠️ Развертывание

### Локальная разработка
```bash
python3 start_server.py
```

### Продакшн (с Gunicorn)
```bash
gunicorn interview_server:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Docker
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python3", "start_server.py"]
```

## 📊 Мониторинг

- **Логи сервера**: консольный вывод + `server.log`
- **WebSocket соединения**: автоматическое управление
- **Статус комнат**: API endpoint `/api/rooms/{room_code}/status`
- **Отчеты интервью**: автоматическое сохранение в `technical_interview_report.json`

## 🔍 Пример использования

### 1. Создание комнаты через API

```bash
curl -X POST "http://localhost:8000/api/rooms/create" \
  -H "Content-Type: application/json" \
  -d '{
    "questions": {
      "Java Backend": {
        "id": "java_start",
        "text": "Скажите вы разработчик, четкий ответ да/нет?"
      }
    }
  }'
```

### 2. WebSocket сообщения

**От клиента:**
```json
{"type": "start_interview"}
{"type": "audio_data", "audio_data": "base64..."}
{"type": "end_interview"}
```

**От сервера:**
```json
{"type": "question", "question": "Вопрос", "topic": "Java", "difficulty": 1}
{"type": "answer", "answer": "Ответ пользователя"}
{"type": "interview_completed"}
```

## 🆘 Решение проблем

### Сервер не запускается
```bash
# Проверьте зависимости
pip install -r requirements.txt

# Проверьте порт
lsof -ti:8000
kill -9 $(lsof -ti:8000)
```

### Не работает микрофон
- Проверьте разрешения браузера на доступ к микрофону
- Убедитесь что микрофон не используется другими приложениями

### Ошибки распознавания
- Проверьте что Whisper и модели эмоций загружены
- Проверьте качество аудио (частота дискретизации 16kHz)

### Проблемы с WebSocket
- Проверьте что сервер запущен
- Убедитесь что нет проблем с сетью
- Проверьте логи сервера

## 📈 Производительность

- **Whisper**: ~2-3 секунды на обработку ответа
- **Emotion Analysis**: ~1-2 секунды на анализ эмоций
- **ChatGPT**: ~3-5 секунд на генерацию вопроса
- **Общее время**: ~6-10 секунд на цикл вопрос-ответ

## 🎉 Готово!

Система готова к использованию! Создавайте комнаты, подключайтесь через браузер и проводите технические интервью с ИИ-анализом эмоций.

### 📞 Поддержка

При возникновении проблем:
1. Проверьте логи сервера в `server.log`
2. Убедитесь что все зависимости установлены
3. Проверьте конфигурацию в `interview_config.json`
4. Убедитесь что OpenAI API ключ корректный
