# Используем стандартный Python образ
FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    ffmpeg \
    portaudio19-dev \
    libsndfile1-dev \
    libasound2-dev \
    curl \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Обновление pip
RUN pip install --upgrade pip setuptools wheel

# Создание рабочей директории
WORKDIR /app

# Копирование файлов зависимостей
COPY requirements.txt ./

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY interview_system/ ./interview_system/

# Копирование конфигурационных файлов
COPY interview_system/interview_config.json ./
COPY interview_system/pretrained_models/ ./pretrained_models/

# Создание директорий для логов и записей
RUN mkdir -p logs recordings static

# Переменные окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Открытие порта
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Команда запуска
CMD ["python", "interview_system/interview_server.py"]
