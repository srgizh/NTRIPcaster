#!/bin/bash

# Скрипт быстрого запуска NTRIP Caster
# Используется для быстрого развёртывания и управления службой NTRIP Caster

set -e

# Определение цветов
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Конфигурация проекта
PROJECT_NAME="ntrip-caster"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
ENV_EXAMPLE="${SCRIPT_DIR}/.env.example"

# Функции логирования
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${PURPLE}[STEP]${NC} $1"
}

# Отображение баннера
show_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                 Быстрый запуск NTRIP Caster                  ║"
    echo "║                  Развёртывание через Docker                  ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Проверка зависимостей
check_dependencies() {
    log_step "Проверка системных зависимостей..."
    
    # Проверка Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker не установлен, сначала установите Docker"
        echo "Руководство по установке: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    # Проверка Docker Compose
    if ! docker compose version &> /dev/null && ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose не установлен, сначала установите Docker Compose"
        echo "Руководство по установке: https://docs.docker.com/compose/install/"
        exit 1
    fi
    
    # Проверка состояния службы Docker
    if ! docker info &> /dev/null; then
        log_error "Служба Docker не запущена, запустите службу Docker"
        exit 1
    fi
    
    log_success "Проверка системных зависимостей завершена"
}

# Инициализация окружения
init_environment() {
    log_step "Инициализация конфигурации окружения..."
    
    # Создание файла .env
    if [[ ! -f "$ENV_FILE" ]]; then
        if [[ -f "$ENV_EXAMPLE" ]]; then
            cp "$ENV_EXAMPLE" "$ENV_FILE"
            log_success "Создан файл конфигурации .env"
        else
            log_error "Файл .env.example не существует"
            exit 1
        fi
    else
        log_info "Файл .env уже существует, пропуск создания"
    fi
    
    # Создание необходимых директорий
    log_info "Создание необходимых директорий..."
    ./docker-deploy.sh create_directories
    
    log_success "Инициализация окружения завершена"
}

# Выбор режима развёртывания
select_deployment_mode() {
    echo
    log_step "Выбор режима развёртывания:"
    echo "1) Режим разработки (development) - включает инструменты разработки и функции отладки"
    echo "2) Режим production (production) - оптимизированная производительность, только основные службы"
    echo "3) Полный режим (full) - включает все службы и мониторинг"
    echo "4) Минимальный режим (minimal) - только основная служба NTRIP Caster"
    echo
    
    while true; do
        read -p "Выберите режим развёртывания [1-4]: " choice
        case $choice in
            1)
                ENVIRONMENT="development"
                PROFILES="dev,monitoring"
                break
                ;;
            2)
                ENVIRONMENT="production"
                PROFILES="prod,monitoring"
                break
                ;;
            3)
                ENVIRONMENT="production"
                PROFILES="full"
                break
                ;;
            4)
                ENVIRONMENT="production"
                PROFILES="minimal"
                break
                ;;
            *)
                log_warning "Неверный выбор, введите 1-4"
                ;;
        esac
    done
    
    # Обновление файла .env
    sed -i "s/^ENVIRONMENT=.*/ENVIRONMENT=$ENVIRONMENT/" "$ENV_FILE"
    
    log_success "Выбран режим $ENVIRONMENT, профили конфигурации: $PROFILES"
}

# Сборка и запуск служб
deploy_services() {
    log_step "Сборка и запуск служб..."
    
    # Загрузка последних образов
    log_info "Загрузка образов Docker..."
    ENVIRONMENT="$ENVIRONMENT" PROFILES="$PROFILES" ./docker-deploy.sh pull
    
    # Сборка пользовательских образов
    log_info "Сборка образов приложения..."
    ENVIRONMENT="$ENVIRONMENT" PROFILES="$PROFILES" ./docker-deploy.sh build
    
    # Запуск служб
    log_info "Запуск служб..."
    ENVIRONMENT="$ENVIRONMENT" PROFILES="$PROFILES" ./docker-deploy.sh up -d
    
    # Ожидание запуска служб
    log_info "Ожидание запуска служб..."
    sleep 10
    
    # Проверка здоровья
    log_info "Выполнение проверки здоровья..."
    ENVIRONMENT="$ENVIRONMENT" PROFILES="$PROFILES" ./docker-deploy.sh health
    
    log_success "Развёртывание служб завершено"
}

# Отображение информации о службах
show_service_info() {
    log_step "Информация о службах:"
    
    # Отображение состояния служб
    ENVIRONMENT="$ENVIRONMENT" PROFILES="$PROFILES" ./docker-deploy.sh status
    
    echo
    log_step "Точки доступа служб:"
    
    # Получение IP-адреса локального хоста
    LOCAL_IP=$(hostname -I | awk '{print $1}' 2>/dev/null || echo "localhost")
    
    echo "📡 Служба NTRIP Caster:"
    echo "   - NTRIP порт: ntrip://$LOCAL_IP:2101"
    echo "   - Веб-интерфейс управления: http://$LOCAL_IP:5757"
    
    if [[ "$PROFILES" == *"monitoring"* ]] || [[ "$PROFILES" == *"full"* ]]; then
        echo
        echo "📊 Службы мониторинга:"
        echo "   - Prometheus: http://$LOCAL_IP:9090"
        echo "   - Grafana: http://$LOCAL_IP:3000 (admin/admin123)"
    fi
    
    if [[ "$ENVIRONMENT" == "development" ]]; then
        echo
        echo "🛠️ Инструменты разработки:"
        echo "   - Adminer (управление БД): http://$LOCAL_IP:8081"
        echo "   - Dozzle (просмотр логов): http://$LOCAL_IP:8082"
        echo "   - cAdvisor (мониторинг контейнеров): http://$LOCAL_IP:8083"
    fi
    
    if [[ -f "$ENV_FILE" ]]; then
        NGINX_PORT=$(grep "^NGINX_HTTP_PORT=" "$ENV_FILE" | cut -d'=' -f2 || echo "80")
        if [[ "$NGINX_PORT" != "80" ]]; then
            echo
            echo "🌐 Прокси Nginx:"
            echo "   - HTTP: http://$LOCAL_IP:$NGINX_PORT"
        fi
    fi
    
    echo
    log_success "Развёртывание завершено! Используйте указанные выше точки доступа для доступа к службам"
}

# Отображение команд управления
show_management_commands() {
    echo
    log_step "Часто используемые команды управления:"
    echo "Просмотр логов:     ./docker-deploy.sh logs"
    echo "Просмотр состояния: ./docker-deploy.sh status"
    echo "Перезапуск служб:   ./docker-deploy.sh restart"
    echo "Остановка служб:    ./docker-deploy.sh down"
    echo "Очистка ресурсов:   ./docker-deploy.sh clean"
    echo "Проверка здоровья:  ./docker-deploy.sh health"
    echo "Резервное копирование: ./docker-deploy.sh backup"
    echo "Обновление служб:   ./docker-deploy.sh update"
    echo
    echo "Использование Makefile (рекомендуется):"
    echo "make up          # Запустить службы"
    echo "make down        # Остановить службы"
    echo "make logs        # Просмотр логов"
    echo "make status      # Просмотр состояния"
    echo "make health      # Проверка здоровья"
    echo "make clean       # Очистка ресурсов"
}

# Главная функция
main() {
    show_banner
    
    # Проверка, что скрипт запущен в правильной директории
    if [[ ! -f "docker-compose.yml" ]]; then
        log_error "Запустите этот скрипт в корневой директории проекта NTRIP Caster"
        exit 1
    fi
    
    # Проверка зависимостей
    check_dependencies
    
    # Инициализация окружения
    init_environment
    
    # Выбор режима развёртывания
    select_deployment_mode
    
    # Подтверждение развёртывания
    echo
    read -p "Подтвердите начало развёртывания? [y/N]: " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        log_info "Развёртывание отменено"
        exit 0
    fi
    
    # Развёртывание служб
    deploy_services
    
    # Отображение информации о службах
    show_service_info
    
    # Отображение команд управления
    show_management_commands
    
    echo
    log_success "🎉 Быстрый запуск NTRIP Caster завершён!"
}

# Точка входа скрипта
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
