#!/bin/bash
# Скрипт для создания комнаты интервью через Kafka

echo "🚀 Создание комнаты интервью через Kafka..."

# Переходим в директорию проекта
cd "$(dirname "$0")"

# Проверяем что сервер запущен
echo "🔍 Проверка статуса сервера..."
if ! curl -s http://localhost:8000/ > /dev/null 2>&1; then
    echo "❌ Сервер не запущен!"
    echo ""
    echo "💡 Запустите сервер командой:"
    echo "   docker-compose up -d"
    echo ""
    echo "Или вручную:"
    echo "   source venv/bin/activate"
    echo "   python start_server.py"
    exit 1
fi

echo "✅ Сервер запущен и отвечает"

# Генерируем уникальный candidate ID
CANDIDATE_ID="cv_$(date +%s)_$((RANDOM % 9000 + 1000))"
CANDIDATE_NAME="Тестовый Кандидат"
VACANCY_TITLE="Разработчик"

echo "📝 Отправляем сообщение в Kafka топик step1..."
echo "👤 Кандидат: $CANDIDATE_NAME"
echo "🆔 Candidate ID: $CANDIDATE_ID"
echo "💼 Вакансия: $VACANCY_TITLE"

# Создаем Python скрипт для отправки сообщения в Kafka
cat > /tmp/send_kafka_message.py << 'EOF'
#!/usr/bin/env python3
import json
import sys
from kafka import KafkaProducer

def send_message():
    # Данные из аргументов командной строки
    candidate_id = sys.argv[1]
    candidate_name = sys.argv[2]
    vacancy_title = sys.argv[3]
    
    # Тестовое сообщение
    message = {
        "candidateId": candidate_id,
        "requestId": f"req_{candidate_id}",
        "vacancyTitle": vacancy_title,
        "vacancy": f"Описание вакансии: {vacancy_title}",
        "candidateName": candidate_name,
        "cvText": f"Резюме кандидата: {candidate_name}",
        "suitabilityConclusion": "Высокая пригодность",
        "score": 8,
        "email": "test@example.com",
        "preferredContact": "📧 test@example.com",
        "questionsForApplicant": [
            "Расскажите о вашем опыте работы",
            "Какие технологии вы используете?",
            "Почему вы хотите работать в нашей компании?",
            "Какие у вас планы на развитие?",
            "Готовы ли вы к удаленной работе?"
        ]
    }
    
    # Настройки Kafka
    bootstrap_servers = ["kafka1:19092", "kafka2:19093", "kafka3:19094"]
    topic = "step1"
    
    try:
        # Создаем producer
        producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            acks='all',
            retries=3
        )
        
        # Отправляем сообщение
        future = producer.send(
            topic,
            value=message,
            key=candidate_id
        )
        
        # Ждем подтверждения
        record_metadata = future.get(timeout=10)
        
        print(f"SUCCESS:{record_metadata.partition}:{record_metadata.offset}")
        producer.close()
        
    except Exception as e:
        print(f"ERROR:{str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    send_message()
EOF

# Запускаем Python скрипт через Docker
RESULT=$(docker exec speakalka-interview python3 /tmp/send_kafka_message.py "$CANDIDATE_ID" "$CANDIDATE_NAME" "$VACANCY_TITLE" 2>&1)

# Проверяем результат
if echo "$RESULT" | grep -q "SUCCESS:"; then
    echo "✅ Сообщение отправлено в Kafka успешно!"
    
    # Извлекаем partition и offset
    PARTITION=$(echo "$RESULT" | cut -d':' -f2)
    OFFSET=$(echo "$RESULT" | cut -d':' -f3)
    
    echo "📊 Partition: $PARTITION, Offset: $OFFSET"
    echo ""
    echo "🏠 Candidate ID: $CANDIDATE_ID"
    echo "🌐 Веб-URL: http://localhost:8000/room/$CANDIDATE_ID"
    echo ""
    echo "📋 Откройте браузер и перейдите по ссылке:"
    echo "   http://localhost:8000/room/$CANDIDATE_ID"
    echo ""
    
    # Пытаемся открыть в браузере (если возможно)
    if command -v open >/dev/null 2>&1; then
        echo "💡 Открыть в браузере? (y/n): "
        read -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            open "http://localhost:8000/room/$CANDIDATE_ID"
        fi
    fi
    
    echo ""
    echo "🎯 Комната будет создана автоматически после обработки сообщения!"
    echo "📊 Для мониторинга логов: docker logs -f speakalka-interview"
    
else
    echo "❌ Ошибка отправки сообщения в Kafka:"
    echo "$RESPONSE"
    echo ""
    echo "💡 Возможные причины:"
    echo "   - Kafka недоступна"
    echo "   - Проблемы с сетью Docker"
    echo "   - Топик step1 не существует"
    echo ""
    echo "🔍 Проверьте статус Kafka:"
    echo "   docker ps | grep kafka"
    echo "   docker logs speakalka-interview"
    exit 1
fi

# Удаляем временный файл
rm -f /tmp/send_kafka_message.py