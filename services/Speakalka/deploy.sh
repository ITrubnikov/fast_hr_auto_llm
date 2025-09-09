#!/bin/bash

# Скрипт для развертывания системы интервью в контейнере
# Использование: ./deploy.sh [build|start|stop|restart|logs|clean]

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для вывода сообщений
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Проверка наличия Docker
check_docker() {
    if ! command -v docker &> /dev/null; then
        error "Docker не установлен. Установите Docker и попробуйте снова."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        error "Docker Compose не установлен. Установите Docker Compose и попробуйте снова."
        exit 1
    fi
}

# Обеспечить окружение по умолчанию (без .env)
prepare_env_defaults() {
    export OPENAI_API_KEY="${OPENAI_API_KEY:-dummy-key}"
    export KAFKA_BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS:-kafka1:19092,kafka2:19093}"
    export KAFKA_TOPIC="${KAFKA_TOPIC:-step3}"
}

# Обеспечить внешнюю сеть для Kafka
ensure_network() {
    local net="margo_default"
    if ! docker network inspect "$net" >/dev/null 2>&1; then
        log "Создаю сеть $net"
        docker network create "$net" || true
    fi
}

# Создать необходимые директории
ensure_dirs() {
    mkdir -p logs recordings static || true
}

# Сборка образа
build_image() {
    prepare_env_defaults
    ensure_network
    ensure_dirs
    log "Сборка Docker образа..."
    docker-compose build --no-cache
    success "Образ успешно собран"
}

# Запуск сервисов
start_services() {
    prepare_env_defaults
    ensure_network
    ensure_dirs
    log "Запуск сервисов..."
    docker-compose up -d
    success "Сервисы запущены"
    log "Система интервью доступна по адресу: http://localhost:8000"
    log "API документация: http://localhost:8000/docs"
}

# Остановка сервисов
stop_services() {
    log "Остановка сервисов..."
    docker-compose down
    success "Сервисы остановлены"
}

# Перезапуск сервисов
restart_services() {
    log "Перезапуск сервисов..."
    docker-compose restart
    success "Сервисы перезапущены"
}

# Просмотр логов
view_logs() {
    log "Просмотр логов..."
    docker-compose logs -f interview-system
}

# Очистка
clean_up() {
    log "Очистка Docker ресурсов..."
    docker-compose down -v
    docker system prune -f
    success "Очистка завершена"
}

# Проверка статуса
check_status() {
    log "Проверка статуса сервисов..."
    docker-compose ps
}

# Основная логика
main() {
    check_docker
    
    case "${1:-start}" in
        "build")
            build_image
            ;;
        "start")
            start_services
            ;;
        "stop")
            stop_services
            ;;
        "restart")
            restart_services
            ;;
        "logs")
            view_logs
            ;;
        "status")
            check_status
            ;;
        "clean")
            clean_up
            ;;
        "help"|"-h"|"--help")
            echo "Использование: $0 [команда]"
            echo ""
            echo "Команды:"
            echo "  build     - Собрать Docker образ"
            echo "  start     - Запустить сервисы (по умолчанию)"
            echo "  stop      - Остановить сервисы"
            echo "  restart   - Перезапустить сервисы"
            echo "  logs      - Просмотреть логи"
            echo "  status    - Проверить статус сервисов"
            echo "  clean     - Очистить Docker ресурсы"
            echo "  help      - Показать эту справку"
            ;;
        *)
            error "Неизвестная команда: $1"
            echo "Используйте '$0 help' для просмотра доступных команд"
            exit 1
            ;;
    esac
}

# Запуск
main "$@"
