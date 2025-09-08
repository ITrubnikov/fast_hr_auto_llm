FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Создание рабочей директории
WORKDIR /app

# Копирование файлов зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование приложения
COPY . .

# Создание директории для конфигурации Streamlit
RUN mkdir -p ~/.streamlit

# Конфигурация Streamlit
RUN echo "\
[general]\n\
email = \"\"\n\
" > ~/.streamlit/credentials.toml

RUN echo "\
[server]\n\
headless = true\n\
enableCORS=false\n\
port = 8504\n\
" > ~/.streamlit/config.toml

# Экспонирование порта
EXPOSE 8504

# Команда запуска
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8504"]
