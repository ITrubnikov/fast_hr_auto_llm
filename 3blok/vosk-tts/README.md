# Vosk-TTS Docker Блок

**Text-to-Speech сервис на основе Vosk-TTS с поддержкой Triton Inference Server**

Блок аналогичный onnx-asr, но для синтеза речи. Поддерживает 3 русских голоса через Triton Server и Docker.

## 🎯 Особенности

- 🐳 **Docker-ready** - полная контейнеризация
- ⚡ **Triton Inference Server** - масштабируемый ML сервинг  
- 🎤 **3 русских голоса** - Ирина, Елена, Павел
- 📊 **Мониторинг** - Prometheus метрики
- 🔄 **Fallback** - автоматический переход на локальный vosk-tts
- 🌐 **REST API** - простая интеграция

## 🏗 Архитектура

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   FastAPI       │────│  TritonTTSClient │────│ Triton Server   │
│   (Port 8200)   │    │                  │    │   (Port 8100)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                                               │
         │              ┌──────────────────┐             │
         └──────────────│  VoskTTSEngine   │─────────────┘
                        │   (Fallback)     │
                        └──────────────────┘
```

## 🚀 Быстрый старт

### 1. Запуск через Docker Compose

```bash
# Клонируйте и перейдите в папку
cd vosk-tts

# Запустите все сервисы
docker-compose up -d

# Проверьте статус
curl http://localhost:8200/health
```

### 2. Использование API

**Синтез текста:**
```bash
curl -X POST "http://localhost:8200/synthesize" \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Привет! Это тест синтеза речи.",
       "voice": "irina",
       "speed": 1.0
     }'
```

**Список голосов:**
```bash
curl http://localhost:8200/voices
```

### 3. Swagger UI
Откройте в браузере: `http://localhost:8200/docs`

## 🎭 Доступные голоса

| Голос | Пол | Описание | Модель |
|-------|-----|----------|--------|
| **irina** | Женский | Нейтральный, четкий | vosk-tts-irina |
| **elena** | Женский | Мягкий, приятный | vosk-tts-elena |
| **pavel** | Мужской | Уверенный, спокойный | vosk-tts-pavel |

## 🔧 Конфигурация

### Docker Compose порты:
- **8100** - Triton HTTP
- **8101** - Triton GRPC
- **8102** - Triton Metrics  
- **8200** - TTS API
- **9091** - Prometheus

### Переменные окружения:
```bash
# Triton сервер
TRITON_URL=triton-tts:8000

# Логирование
LOG_LEVEL=INFO

# API настройки
API_HOST=0.0.0.0
API_PORT=8080
```

## 📂 Структура проекта

```
vosk-tts/
├── docker-compose.yml          # Оркестрация сервисов
├── Dockerfile                  # API контейнер
├── requirements.txt            # Python зависимости
├── src/vosk_tts/              # Основной код
│   ├── __init__.py            # Экспорты модуля
│   ├── config.py              # Конфигурация
│   ├── tts.py                 # TTS движок
│   ├── triton_client.py       # Triton клиент
│   └── api.py                 # FastAPI интерфейс
├── triton_model_repository/   # Модели Triton
│   ├── vosk-tts-irina/       # Модель Ирина
│   ├── vosk-tts-elena/       # Модель Елена
│   └── vosk-tts-pavel/       # Модель Павел
└── monitoring/
    └── prometheus.yml         # Конфигурация мониторинга
```

## 🔌 API Endpoints

### Основные

- `GET /` - Информация о сервисе
- `GET /health` - Проверка здоровья
- `GET /voices` - Список голосов
- `GET /stats` - Статистика сервиса

### TTS

- `POST /synthesize` - Синтез текста (JSON)
- `POST /synthesize/form` - Синтез текста (Form)
- `GET /audio/{file_id}` - Скачать аудио файл
- `DELETE /audio/{file_id}` - Удалить аудио файл

### Управление

- `POST /cache/clear` - Очистить кеш

## 🛠 Разработка

### Локальная разработка

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск API (без Triton)
python -m uvicorn src.vosk_tts.api:app --reload --port 8200

# Или только с vosk-tts
python src/vosk_tts/api.py
```

### Тестирование

```bash
# Проверка TTS
curl -X POST "http://localhost:8200/synthesize" \
     -H "Content-Type: application/json" \
     -d '{"text": "Тест", "voice": "irina"}'

# Проверка здоровья
curl http://localhost:8200/health
```

## 🔧 Настройка Triton моделей

Каждая модель имеет структуру:
```
vosk-tts-{voice}/
├── config.pbtxt      # Конфигурация Triton
└── 1/
    └── model.py      # Python backend
```

### Добавление нового голоса:

1. Создайте папку модели:
   ```bash
   mkdir -p triton_model_repository/vosk-tts-newvoice/1
   ```

2. Скопируйте config.pbtxt и model.py
3. Измените voice_path в model.py
4. Добавьте голос в config.py

## 📊 Мониторинг

### Prometheus метрики:
- Triton Server: `http://localhost:8102/metrics`
- Prometheus UI: `http://localhost:9091`

### Health checks:
```bash
# Общее здоровье
curl http://localhost:8200/health

# Triton статус  
curl http://localhost:8100/v2/health/ready
```

## 🐛 Troubleshooting

### Triton не запускается:
```bash
# Проверьте логи
docker-compose logs triton-tts

# Убедитесь что vosk-tts установлен
docker-compose exec triton-tts pip list | grep vosk
```

### Модель не загружается:
```bash
# Проверьте модели в Triton
curl http://localhost:8100/v2/models

# Логи конкретной модели
curl http://localhost:8100/v2/models/vosk-tts-irina
```

### API недоступен:
```bash
# Проверьте контейнер
docker-compose ps

# Логи API
docker-compose logs vosk-tts-api
```

## 🚦 Production

### С GPU поддержкой:
1. Раскомментируйте GPU настройки в docker-compose.yml
2. Установите nvidia-container-runtime
3. Измените instance_group в config.pbtxt на KIND_GPU

### Масштабирование:
```bash
# Увеличьте количество реплик API
docker-compose up -d --scale vosk-tts-api=3

# Или увеличьте instance_count в Triton конфигах
```

### Безопасность:
- Включите API ключи в config.py
- Настройте CORS origins
- Используйте HTTPS reverse proxy

## 🔗 Интеграция с voice-dialog

Этот блок интегрируется с voice-dialog системой:

```python
# В voice-dialog/src/voice_dialog/tts.py
class VoskTTSEngine:
    def __init__(self, config: TTSConfig):
        # Используйте этот Docker сервис
        self.triton_url = "localhost:8100"  # Triton
        self.api_url = "localhost:8200"     # API
```

## 📄 Лицензия

Аналогично основному проекту. Vosk-TTS имеет Apache 2.0 лицензию.

---

**Версия**: 0.1.0  
**Совместимость**: onnx-asr v0.1.0, voice-dialog v0.1.0
