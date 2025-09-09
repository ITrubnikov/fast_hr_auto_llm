# Dockerfile для Vosk TTS API сервера
FROM python:3.9-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    build-essential \
    libsndfile1 \
    ffmpeg \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем requirements
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Создаем директории для моделей и выходных файлов
RUN mkdir -p /app/models /app/output

# Копируем исходный код
COPY src/ src/

# Создаем дополнительные директории
RUN mkdir -p logs

# Переменные окружения
ENV PYTHONPATH=/app

EXPOSE 8080

# Проверка здоровья
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Запуск API сервера
CMD ["python", "-m", "uvicorn", "src.vosk_tts.api:app", "--host", "0.0.0.0", "--port", "8080"]