# Kafka REST Producer

REST сервис, публикующий произвольный JSON в Kafka топик `step1`.

## Сборка

```bash
cd services/kafka-rest-producer
mvn -q -DskipTests package
```

## Запуск локально

```bash
java -jar target/kafka-rest-producer-0.0.1-SNAPSHOT.jar
```

Конфигурация: `src/main/resources/application.yml`
- Kafka bootstrap servers: `localhost:9092,localhost:9093,localhost:9094`
- HTTP порт: `8090`

## Запуск в Docker

```bash
# Сначала собрать jar
mvn -q -DskipTests package
# Собрать образ
docker build -t kafka-rest-producer:local .
# Запустить контейнер
docker run --rm -p 8090:8090 \
  kafka-rest-producer:local
```

## API

- POST `/api/publish`
  - Тело: любой JSON (передаётся как строка)
  - Ответ: 202 Accepted, тело "queued"

Пример запроса:

```bash
curl -X POST http://localhost:8090/api/publish \
  -H "Content-Type: application/json" \
  -d '{"hello":"world"}'
```
