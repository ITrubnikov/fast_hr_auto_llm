#!/bin/bash
# Скрипт для запуска/перезапуска сервера интервью с новым кодом

echo "🚀 Перезапуск сервера интервью..."

# Переходим в директорию проекта
cd "$(dirname "$0")"

# Проверяем, запущен ли сервер
if pgrep -f "interview_server.py" > /dev/null; then
    echo "🛑 Останавливаем существующий сервер..."
    pkill -f "interview_server.py"
    sleep 2
    
    # Проверяем, что сервер действительно остановлен
    if pgrep -f "interview_server.py" > /dev/null; then
        echo "⚠️ Принудительная остановка сервера..."
        pkill -9 -f "interview_server.py"
        sleep 1
    fi
    echo "✅ Сервер остановлен"
else
    echo "ℹ️ Сервер не был запущен"
fi

# Проверяем наличие виртуального окружения
if [ ! -d "venv" ]; then
    echo "❌ Виртуальное окружение не найдено!"
    echo "Создайте виртуальное окружение:"
    echo "   python3 -m venv venv"
    echo "   source venv/bin/activate"
    echo "   pip install -r requirements.txt"
    exit 1
fi

# Активируем виртуальное окружение
echo "🔧 Активация виртуального окружения..."
source venv/bin/activate

# Проверяем зависимости
echo "📦 Проверка зависимостей..."
if ! python -c "import fastapi, uvicorn, websockets" 2>/dev/null; then
    echo "⚠️ Некоторые зависимости отсутствуют. Устанавливаем..."
    pip install -r requirements.txt
fi

# Очищаем логи
echo "🧹 Очистка старых логов..."
rm -f server.log nohup.out

# Запускаем сервер в фоновом режиме
echo "🚀 Запуск сервера..."
nohup python start_server.py > server.log 2>&1 &
SERVER_PID=$!

# Ждем немного, чтобы сервер запустился
sleep 3

# Проверяем, что сервер запустился
if pgrep -f "interview_server.py" > /dev/null; then
    echo "✅ Сервер успешно запущен (PID: $SERVER_PID)"
    echo "📋 Логи: tail -f server.log"
    echo "🌐 URL: http://localhost:8000"
    echo ""
    echo "💡 Для остановки сервера:"
    echo "   pkill -f interview_server.py"
    echo ""
    echo "📊 Статус сервера:"
    curl -s http://localhost:8000/ > /dev/null && echo "✅ Сервер отвечает" || echo "❌ Сервер не отвечает"
else
    echo "❌ Ошибка запуска сервера!"
    echo "📋 Проверьте логи:"
    echo "   cat server.log"
    exit 1
fi
