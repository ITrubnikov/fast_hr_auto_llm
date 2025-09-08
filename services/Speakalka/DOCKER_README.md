# 🐳 Контейнеризация системы интервью Speakalka

Этот документ описывает, как запустить систему технических интервью в Docker контейнере.

## 📋 Требования

- Docker 20.10+
- Docker Compose 2.0+
- Минимум 4GB RAM
- Минимум 2 CPU cores

## 🚀 Быстрый старт

### 1. Клонирование и подготовка

```bash
git clone <repository-url>
cd Speakalka
```

### 2. Настройка переменных окружения

Создайте файл `.env` в корне проекта:

```bash
# OpenAI API ключ
OPENAI_API_KEY=your_openai_api_key_here
```

### 3. Запуск с помощью скрипта

```bash
# Сборка и запуск
./deploy.sh build
./deploy.sh start

# Или все сразу
./deploy.sh build && ./deploy.sh start
```

### 4. Доступ к приложению

- **Веб-интерфейс**: http://localhost:8000
- **API документация**: http://localhost:8000/docs
- **API endpoint**: http://localhost:8000/api

## 🛠️ Управление контейнером

### Доступные команды

```bash
./deploy.sh build      # Собрать Docker образ
./deploy.sh start      # Запустить сервисы
./deploy.sh stop       # Остановить сервисы
./deploy.sh restart    # Перезапустить сервисы
./deploy.sh logs       # Просмотреть логи
./deploy.sh status     # Проверить статус
./deploy.sh clean      # Очистить Docker ресурсы
./deploy.sh help       # Показать справку
```

### Ручное управление Docker Compose

```bash
# Запуск
docker-compose up -d

# Остановка
docker-compose down

# Просмотр логов
docker-compose logs -f

# Перезапуск
docker-compose restart
```

## 📁 Структура проекта

```
Speakalka/
├── Dockerfile                 # Docker образ
├── docker-compose.yml        # Docker Compose конфигурация
├── requirements.txt          # Python зависимости
├── .dockerignore            # Исключения для Docker
├── deploy.sh                # Скрипт управления
├── interview_system/        # Основное приложение
│   ├── interview_server.py  # FastAPI сервер
│   ├── requirements.txt     # Зависимости приложения
│   └── ...
└── T-one/                   # ASR модуль
    ├── pyproject.toml       # Конфигурация пакета
    └── ...
```

## 🔧 Конфигурация

### Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `OPENAI_API_KEY` | API ключ OpenAI | - |
| `PYTHONPATH` | Путь к Python модулям | `/app` |
| `PYTHONUNBUFFERED` | Небуферизованный вывод | `1` |

### Порты

- **8000**: HTTP API и веб-интерфейс

### Тома

- `./logs:/app/logs` - Логи приложения
- `./recordings:/app/recordings` - Записи интервью
- `./static:/app/static` - Статические файлы

## 🐛 Отладка

### Просмотр логов

```bash
# Все логи
./deploy.sh logs

# Только ошибки
docker-compose logs interview-system | grep ERROR

# Последние 100 строк
docker-compose logs --tail=100 interview-system
```

### Вход в контейнер

```bash
docker-compose exec interview-system bash
```

### Проверка здоровья

```bash
# Статус контейнеров
./deploy.sh status

# Проверка API
curl http://localhost:8000/

# Health check
curl http://localhost:8000/health
```

## 🔄 Обновление

### Обновление кода

```bash
# Остановка
./deploy.sh stop

# Обновление кода (git pull, etc.)

# Пересборка и запуск
./deploy.sh build
./deploy.sh start
```

### Обновление зависимостей

1. Обновите `requirements.txt`
2. Пересоберите образ: `./deploy.sh build`

## 🚨 Устранение неполадок

### Проблемы с памятью

Если контейнер падает из-за нехватки памяти:

```bash
# Увеличьте лимиты в docker-compose.yml
deploy:
  resources:
    limits:
      memory: 8G  # Увеличьте до 8GB
```

### Проблемы с аудио

Если есть проблемы с аудио устройствами:

```bash
# Добавьте в docker-compose.yml
devices:
  - /dev/snd:/dev/snd
```

### Проблемы с GPU

Для использования GPU (если нужно):

```bash
# Добавьте в docker-compose.yml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

## 📊 Мониторинг

### Метрики контейнера

```bash
# Использование ресурсов
docker stats speakalka-interview

# Детальная информация
docker inspect speakalka-interview
```

### Логи приложения

Логи сохраняются в директории `./logs/` и доступны в контейнере по пути `/app/logs/`.

## 🔒 Безопасность

- Контейнер запускается от непривилегированного пользователя
- API ключи передаются через переменные окружения
- Внешние порты ограничены только необходимыми

## 📝 Примечания

- Первый запуск может занять несколько минут из-за загрузки ML моделей
- Убедитесь, что порт 8000 свободен
- Для production использования рекомендуется настроить reverse proxy (nginx)
