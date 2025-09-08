# 🚀 Настройка Kafka для системы интервью

## 📋 Обзор

Система интервью теперь интегрирована с Apache Kafka для отправки отчетов в топик `step3`. Отчеты больше не сохраняются в файлы, а отправляются в Kafka для дальнейшей обработки.

## 🔧 Настройка Kafka

### 1. Запуск Kafka в Docker

Kafka уже настроена в проекте `/Users/margo/fast_hr_auto_llm`. Убедитесь, что Kafka запущена:

```bash
cd /Users/margo/fast_hr_auto_llm/kafka-secure
docker-compose up -d
```

### 2. Проверка статуса Kafka

```bash
# Проверить что контейнеры запущены
docker ps | grep kafka

# Проверить логи
docker logs kafka1
docker logs kafka2  
docker logs kafka3
```

### 3. Создание топика step3

```bash
# Подключиться к одному из Kafka контейнеров
docker exec -it kafka1 bash

# Создать топик step3
kafka-topics --create \
  --topic step3 \
  --bootstrap-server localhost:9092 \
  --partitions 3 \
  --replication-factor 3

# Проверить что топик создан
kafka-topics --list --bootstrap-server localhost:9092
```

## 🐳 Настройка Docker Compose

Система интервью уже настроена для подключения к Kafka:

- **Сеть**: `kafka-secure_default`
- **Bootstrap Servers**: `kafka1:19092,kafka2:19093,kafka3:19094`
- **Топик**: `step3`

## 📊 Формат отчетов

Отчеты отправляются в JSON формате со следующей структурой:

```json
{
  "timestamp": 1703123456.789,
  "source": "interview_system",
  "topic": "step3",
  "report": {
    "candidate_name": "Имя Кандидата",
    "interview_id": "interview_1703123456",
    "completion_time": "2023-12-21 10:30:45",
    "total_questions": 5,
    "topics_covered": ["Python", "Алгоритмы", "Базы данных"],
    "average_score": 7.5,
    "emotion_analysis": {
      "most_common_emotion": "neutral",
      "emotion_distribution": {"neutral": 0.6, "happiness": 0.4},
      "average_confidence": 0.85,
      "total_analyses": 5
    },
    "answers": [
      {
        "question_id": "q1",
        "question_text": "Вопрос",
        "topic": "Python",
        "difficulty": 1,
        "answer_text": "Ответ кандидата",
        "score": 8,
        "evaluation": "Оценка ответа",
        "timestamp": "2023-12-21 10:25:30",
        "emotion_analysis": {
          "primary_emotion": "neutral",
          "confidence": 0.9,
          "emotions": {"neutral": 0.9, "happiness": 0.1}
        }
      }
    ]
  }
}
```

## 🧪 Тестирование

### Запуск тестового скрипта

```bash
# Установить переменные окружения
export KAFKA_BOOTSTRAP_SERVERS="kafka1:19092,kafka2:19093,kafka3:19094"
export KAFKA_TOPIC="step3"

# Запустить тест
python3 test_kafka_integration.py
```

### Проверка сообщений в топике

```bash
# Подключиться к Kafka контейнеру
docker exec -it kafka1 bash

# Читать сообщения из топика step3
kafka-console-consumer \
  --topic step3 \
  --bootstrap-server localhost:9092 \
  --from-beginning
```

## 🔄 Fallback механизм

Если Kafka недоступна, система автоматически сохраняет отчеты в файлы:

- `interview_report_{room_id}.json` - для комнатных интервью
- `technical_interview_report.json` - для LangGraph интервью

## 🚀 Запуск системы

```bash
# Запустить систему интервью
docker-compose up -d

# Проверить логи
docker logs speakalka-interview
```

## 🔍 Мониторинг

### Kafka UI

Kafka UI доступна по адресу: `http://localhost:8080`

- Логин: `admin`
- Пароль: `admin`

### Проверка логов

```bash
# Логи системы интервью
docker logs -f speakalka-interview

# Логи Kafka
docker logs -f kafka1
```

## ⚠️ Устранение неполадок

### Kafka недоступна

1. Проверить что Kafka запущена:
   ```bash
   docker ps | grep kafka
   ```

2. Проверить сеть:
   ```bash
   docker network ls | grep kafka
   ```

3. Проверить подключение из контейнера:
   ```bash
   docker exec -it speakalka-interview ping kafka1
   ```

### Топик не существует

```bash
# Создать топик
docker exec -it kafka1 kafka-topics --create \
  --topic step3 \
  --bootstrap-server localhost:9092 \
  --partitions 3 \
  --replication-factor 3
```

### Проблемы с сетью

```bash
# Пересоздать сеть
docker network rm kafka-secure_default
cd /Users/margo/fast_hr_auto_llm/kafka-secure
docker-compose down
docker-compose up -d
```

## 📝 Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `KAFKA_BOOTSTRAP_SERVERS` | Адреса Kafka брокеров | `kafka1:19092,kafka2:19093,kafka3:19094` |
| `KAFKA_TOPIC` | Название топика | `step3` |
| `KAFKA_CONNECT_MAX_RETRIES` | Максимум попыток подключения | `8` |
| `KAFKA_CONNECT_BACKOFF_SECONDS` | Задержка между попытками | `2` |
