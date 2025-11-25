#!/bin/bash
# Скрипт развёртывания NTRIP Caster через Docker v2.1.8
# Полное решение развёртывания для сред разработки, тестирования и production

set -euo pipefail

# Определение цветов
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Переменные конфигурации
IMAGE_NAME="ntrip-caster"
IMAGE_TAG="2.1.8"
CONTAINER_NAME="ntrip-caster"
NETWORK_NAME="ntrip-network"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENVIRONMENT="development"
PROFILES=""
COMPOSE_FILES="-f docker-compose.yml"

# Определение функций
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

log_debug() {
    if [[ "${DEBUG:-false}" == "true" ]]; then
        echo -e "${PURPLE}[DEBUG]${NC} $1"
    fi
}

log_success() {
    echo -e "${CYAN}[SUCCESS]${NC} $1"
}

# Отображение баннера
show_banner() {
    echo -e "${CYAN}"
    cat << 'EOF'
    ██████╗ ██████╗ ████████╗██╗  ██╗
    ╚════██╗██╔══██╗╚══██╔══╝██║ ██╔╝
     █████╔╝██████╔╝   ██║   █████╔╝ 
    ██╔═══╝ ██╔══██╗   ██║   ██╔═██╗ 
    ███████╗██║  ██║   ██║   ██║  ██╗
    ╚══════╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝
EOF
    echo -e "${NC}"
    echo -e "${GREEN}    Скрипт развёртывания NTRIP Caster через Docker v2.1.8${NC}"
    echo -e "${BLUE}    Окружение: ${ENVIRONMENT} | Файлы конфигурации: ${COMPOSE_FILES}${NC}"
    echo
}

# Парсинг аргументов командной строки
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --env|--environment)
                ENVIRONMENT="$2"
                shift 2
                ;;
            --profile)
                PROFILES="--profile $2 $PROFILES"
                shift 2
                ;;
            --debug)
                DEBUG="true"
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                break
                ;;
        esac
    done
    
    # Настройка compose файлов в зависимости от окружения
    case "$ENVIRONMENT" in
        "production"|"prod")
            COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml"
            ENVIRONMENT="production"
            ;;
        "development"|"dev")
            COMPOSE_FILES="-f docker-compose.yml -f docker-compose.override.yml"
            ENVIRONMENT="development"
            ;;
        "testing"|"test")
            COMPOSE_FILES="-f docker-compose.yml"
            ENVIRONMENT="testing"
            ;;
        *)
            log_warn "Неизвестное окружение: $ENVIRONMENT, используется окружение разработки по умолчанию"
            ENVIRONMENT="development"
            COMPOSE_FILES="-f docker-compose.yml -f docker-compose.override.yml"
            ;;
    esac
    
    log_debug "Окружение: $ENVIRONMENT"
    log_debug "Compose файлы: $COMPOSE_FILES"
    log_debug "Profiles: $PROFILES"
}

# Проверка установки Docker
check_docker() {
    log_step "Проверка окружения Docker..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker не установлен, сначала установите Docker"
        echo "Команды установки:"
        echo "  Ubuntu/Debian: curl -fsSL https://get.docker.com | sh"
        echo "  CentOS/RHEL: curl -fsSL https://get.docker.com | sh"
        echo "  macOS: brew install docker"
        echo "  Windows: скачайте Docker Desktop"
        exit 1
    fi
    
    # Проверка Docker Compose (приоритет плагину docker compose)
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE_CMD="docker compose"
        log_debug "Используется плагин Docker Compose"
    elif command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE_CMD="docker-compose"
        log_debug "Используется отдельный docker-compose"
    else
        log_error "Docker Compose не установлен, сначала установите Docker Compose"
        echo "Команды установки:"
        echo "  Плагин: docker plugin install docker/compose"
        echo "  Отдельная установка: sudo curl -L \"https://github.com/docker/compose/releases/latest/download/docker-compose-\$(uname -s)-\$(uname -m)\" -o /usr/local/bin/docker-compose"
        echo "           sudo chmod +x /usr/local/bin/docker-compose"
        exit 1
    fi
    
    # Проверка запуска демона Docker
    if ! docker info &> /dev/null; then
        log_error "Демон Docker не запущен, запустите службу Docker"
        echo "Команды запуска:"
        echo "  systemd: sudo systemctl start docker"
        echo "  macOS/Windows: запустите Docker Desktop"
        exit 1
    fi
    
    # Отображение информации о версиях
    local docker_version=$(docker --version | cut -d' ' -f3 | cut -d',' -f1)
    local compose_version=$($DOCKER_COMPOSE_CMD version --short 2>/dev/null || echo "unknown")
    
    log_info "Проверка окружения Docker пройдена"
    log_debug "Версия Docker: $docker_version"
    log_debug "Версия Compose: $compose_version"
}

# Создание необходимых директорий
create_directories() {
    log_step "Создание необходимой структуры директорий..."
    
    # Базовые директории
    local dirs=(
        "data"
        "logs"
        "config"
        "secrets"
        "nginx/conf.d"
        "nginx/ssl"
        "nginx/logs"
        "redis"
        "monitoring/prometheus/rules"
        "monitoring/grafana/provisioning/datasources"
        "monitoring/grafana/provisioning/dashboards"
        "monitoring/grafana/dashboards"
        "backup"
    )
    
    for dir in "${dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            log_debug "Создание директории: $dir"
        fi
    done
    
    # Установка прав доступа к директориям
    chmod 755 data logs config
    chmod 700 secrets
    
    # Копирование конфигурационного файла
    if [[ ! -f "config/config.ini" && -f "config.ini" ]]; then
        cp config.ini config/config.ini
        log_info "Конфигурационный файл скопирован в config/config.ini"
    fi
    
    # Создание конфигурационного файла окружения
    if [[ ! -f ".env.${ENVIRONMENT}" ]]; then
        create_env_file
    fi
    
    log_success "Структура директорий создана"
}

# Создание конфигурационного файла окружения
create_env_file() {
    log_step "Создание конфигурационного файла окружения..."
    
    cat > ".env.${ENVIRONMENT}" << EOF
# Конфигурация окружения ${ENVIRONMENT}
COMPOSE_PROJECT_NAME=ntrip-${ENVIRONMENT}
COMPOSE_FILE=${COMPOSE_FILES// /,}
ENVIRONMENT=${ENVIRONMENT}

# Конфигурация приложения
NTRIP_HOST=0.0.0.0
NTRIP_PORT=2101
WEB_HOST=0.0.0.0
WEB_PORT=5757

# Конфигурация логирования
LOG_LEVEL=INFO
LOG_FORMAT=json

# Конфигурация базы данных
DATABASE_PATH=/app/data/2rtk.db

# Конфигурация часового пояса
TZ=Asia/Shanghai
EOF
    
    log_info "Конфигурационный файл окружения создан: .env.${ENVIRONMENT}"
}

# Создание конфигурации Nginx
create_nginx_config() {
    log_step "Создание конфигурации Nginx..."
    
    cat > nginx/nginx.conf << 'EOF'
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
    use epoll;
    multi_accept on;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';
    
    access_log /var/log/nginx/access.log main;
    
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types
        text/plain
        text/css
        text/xml
        text/javascript
        application/json
        application/javascript
        application/xml+rss
        application/atom+xml
        image/svg+xml;
    
    include /etc/nginx/conf.d/*.conf;
}
EOF

    cat > nginx/conf.d/ntrip.conf << 'EOF'
server {
    listen 80;
    server_name _;
    
    # Заголовки безопасности
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;
    
    # Веб-интерфейс управления
    location / {
        proxy_pass http://ntrip-caster:5757;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Поддержка WebSocket
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
    
    # Проверка здоровья
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}

# Прокси службы NTRIP (опционально)
stream {
    upstream ntrip_backend {
        server ntrip-caster:2101;
    }
    
    server {
        listen 2101;
        proxy_pass ntrip_backend;
        proxy_timeout 1s;
        proxy_responses 1;
        error_log /var/log/nginx/ntrip.log;
    }
}
EOF

    log_info "Конфигурация Nginx создана"
}

# Создание конфигурации мониторинга
create_monitoring_config() {
    log_step "Создание конфигурации мониторинга..."
    
    cat > monitoring/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  # - "first_rules.yml"
  # - "second_rules.yml"

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
  
  - job_name: 'ntrip-caster'
    static_configs:
      - targets: ['ntrip-caster:5757']
    metrics_path: '/metrics'
    scrape_interval: 30s
EOF

    mkdir -p monitoring/grafana/provisioning/datasources
    cat > monitoring/grafana/provisioning/datasources/prometheus.yml << 'EOF'
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
EOF

    log_info "Конфигурация мониторинга создана"
}

# Сборка образа
build_image() {
    log_step "Сборка образа Docker..."
    
    if [ -f "Dockerfile" ]; then
        docker build -t $IMAGE_NAME:$IMAGE_TAG .
        docker tag $IMAGE_NAME:$IMAGE_TAG $IMAGE_NAME:latest
        log_success "Образ собран: $IMAGE_NAME:$IMAGE_TAG"
    else
        log_info "Dockerfile не найден, используется сборка через docker-compose..."
        $DOCKER_COMPOSE_CMD $COMPOSE_FILES build
        log_success "Образ собран"
    fi
}

# Запуск служб
start_services() {
    log_step "Запуск служб..."
    
    # Базовые службы
    $DOCKER_COMPOSE_CMD $COMPOSE_FILES $PROFILES up -d ntrip-caster
    
    # Ожидание запуска служб
    log_info "Ожидание запуска служб..."
    sleep 10
    
    # Проверка состояния служб
    if $DOCKER_COMPOSE_CMD $COMPOSE_FILES ps | grep -q "Up"; then
        log_info "Служба NTRIP Caster успешно запущена"
        check_health
    else
        log_error "Не удалось запустить службы"
        $DOCKER_COMPOSE_CMD $COMPOSE_FILES logs ntrip-caster
        exit 1
    fi
}

# Запуск полного стека служб (включая Nginx и мониторинг)
start_full_services() {
    log_step "Запуск полного стека служб..."
    
    $DOCKER_COMPOSE_CMD $COMPOSE_FILES --profile nginx --profile monitoring up -d
    
    # Ожидание запуска служб
    log_info "Ожидание запуска служб..."
    sleep 15
    
    check_health
    show_info
    log_success "Полный стек служб запущен"
}

# Остановка служб
stop_services() {
    log_step "Остановка служб..."
    
    $DOCKER_COMPOSE_CMD $COMPOSE_FILES $PROFILES down
    
    log_success "Службы остановлены"
}

# Очистка ресурсов
clean_resources() {
    log_step "Очистка ресурсов Docker..."
    
    # Остановка и удаление контейнеров
    $DOCKER_COMPOSE_CMD $COMPOSE_FILES down -v --remove-orphans
    
    # Удаление образов
    docker rmi $IMAGE_NAME:$IMAGE_TAG $IMAGE_NAME:latest 2>/dev/null || true
    
    # Очистка неиспользуемых ресурсов
    docker system prune -f
    docker volume prune -f
    
    log_success "Очистка ресурсов завершена"
}

# Просмотр логов
view_logs() {
    $DOCKER_COMPOSE_CMD $COMPOSE_FILES logs -f ntrip-caster
}

# Просмотр состояния
view_status() {
    echo "=== Состояние Docker Compose ==="
    $DOCKER_COMPOSE_CMD $COMPOSE_FILES ps
    echo
    echo "=== Использование ресурсов контейнерами ==="
    docker stats --no-stream
    echo
    echo "=== Состояние здоровья служб ==="
    if docker ps --format "table {{.Names}}\t{{.Status}}" | grep -q "ntrip-caster.*Up"; then
        if $DOCKER_COMPOSE_CMD $COMPOSE_FILES exec -T ntrip-caster curl -f http://localhost:5757/ >/dev/null 2>&1; then
            echo "✓ Веб-служба работает нормально"
        else
            echo "✗ Веб-служба работает некорректно"
        fi
    else
        echo "✗ Служба NTRIP Caster не запущена"
    fi
}

# Отображение справки
show_help() {
    echo "Скрипт развёртывания NTRIP Caster через Docker v2.1.8"
    echo
    echo "Использование: $0 [опции] [команда] [параметры]"
    echo
    echo "Опции:"
    echo "  --env, --environment ENV  Указать окружение (development|testing|production)"
    echo "  --profile PROFILE         Включить указанный compose profile"
    echo "  --debug                   Включить режим отладки"
    echo "  --help, -h               Отобразить справку"
    echo
    echo "Команды:"
    echo "  build     - Собрать образ Docker"
    echo "  start     - Запустить базовые службы"
    echo "  full      - Запустить полный стек служб (включая Nginx и мониторинг)"
    echo "  stop      - Остановить службы"
    echo "  restart   - Перезапустить службы"
    echo "  logs      - Просмотреть логи"
    echo "  status    - Просмотреть состояние"
    echo "  health    - Проверить состояние здоровья служб"
    echo "  info      - Отобразить информацию о службах"
    echo "  backup    - Создать резервную копию данных"
    echo "  restore   - Восстановить данные (требуется указать путь к резервной копии)"
    echo "  update    - Обновить службы"
    echo "  clean     - Очистить ресурсы"
    echo "  help      - Отобразить справку"
    echo
    echo "Примеры:"
    echo "  $0 --env production build && $0 start    # Сборка и запуск в production окружении"
    echo "  $0 --profile nginx --profile monitoring full  # Запуск полного стека служб"
    echo "  $0 --debug logs                          # Просмотр логов в режиме отладки"
    echo "  $0 backup                                # Резервное копирование данных"
    echo "  $0 restore ./backup/20231201_120000     # Восстановление данных"
    echo
    echo "Описание окружений:"
    echo "  development - Окружение разработки, включает инструменты отладки"
    echo "  testing     - Тестовое окружение, базовая конфигурация"
    echo "  production  - Production окружение, оптимизированная конфигурация"
}

# Проверка состояния здоровья служб
check_health() {
    log_info "Проверка состояния здоровья служб..."
    
    local services=("ntrip-caster" "ntrip-nginx" "ntrip-prometheus" "ntrip-grafana")
    local healthy=true
    
    for service in "${services[@]}"; do
        if $DOCKER_COMPOSE_CMD $COMPOSE_FILES $PROFILES ps --format "table {{.Service}}\t{{.Status}}" | grep -q "$service.*healthy"; then
            log_success "✓ $service: здоров"
        elif $DOCKER_COMPOSE_CMD $COMPOSE_FILES $PROFILES ps --format "table {{.Service}}\t{{.Status}}" | grep -q "$service.*Up"; then
            log_warn "⚠ $service: работает, но проверка здоровья не пройдена"
            healthy=false
        else
            log_error "✗ $service: не запущен"
            healthy=false
        fi
    done
    
    if [ "$healthy" = true ]; then
        log_success "Все службы работают нормально"
    else
        log_warn "Некоторые службы имеют проблемы, проверьте логи"
    fi
}

# Отображение информации о службах
show_info() {
    log_info "Информация о службе NTRIP Caster:"
    echo
    echo "${BLUE}Окружение:${NC} $ENVIRONMENT"
    echo "${BLUE}Файлы конфигурации:${NC} $COMPOSE_FILES"
    echo "${BLUE}Имя проекта:${NC} ${CONTAINER_NAME}"
    echo
    echo "${BLUE}Точки доступа служб:${NC}"
    echo "  • NTRIP Caster: http://localhost:2101"
    echo "  • Веб-интерфейс: http://localhost:5757"
    echo "  • Prometheus: http://localhost:9090"
    echo "  • Grafana: http://localhost:3000"
    if [ "$ENVIRONMENT" = "development" ]; then
        echo "  • Adminer: http://localhost:8081"
        echo "  • Dozzle: http://localhost:8082"
        echo "  • cAdvisor: http://localhost:8083"
    fi
    echo
    
    if $DOCKER_COMPOSE_CMD $COMPOSE_FILES ps >/dev/null 2>&1; then
        echo "${BLUE}Состояние служб:${NC}"
        $DOCKER_COMPOSE_CMD $COMPOSE_FILES ps
    fi
}

# Резервное копирование данных
backup_data() {
    log_info "Резервное копирование данных..."
    
    local backup_dir="./backup/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup_dir"
    
    # Резервное копирование конфигурационных файлов
    log_info "Резервное копирование конфигурационных файлов..."
    cp -r config/ "$backup_dir/" 2>/dev/null || true
    cp -r nginx/ "$backup_dir/" 2>/dev/null || true
    cp -r monitoring/ "$backup_dir/" 2>/dev/null || true
    cp .env.* "$backup_dir/" 2>/dev/null || true
    
    # Резервное копирование томов данных
    log_info "Резервное копирование томов данных..."
    if docker volume ls | grep -q "ntrip.*data"; then
        docker run --rm -v "ntrip-data:/data" -v "$(pwd)/$backup_dir:/backup" alpine tar czf /backup/ntrip-data.tar.gz -C /data .
    fi
    
    if docker volume ls | grep -q "prometheus.*data"; then
        docker run --rm -v "prometheus-data:/data" -v "$(pwd)/$backup_dir:/backup" alpine tar czf /backup/prometheus-data.tar.gz -C /data .
    fi
    
    if docker volume ls | grep -q "grafana.*data"; then
        docker run --rm -v "grafana-data:/data" -v "$(pwd)/$backup_dir:/backup" alpine tar czf /backup/grafana-data.tar.gz -C /data .
    fi
    
    log_success "Резервное копирование завершено: $backup_dir"
}

# Восстановление данных
restore_data() {
    local backup_path="$1"
    
    if [ -z "$backup_path" ] || [ ! -d "$backup_path" ]; then
        log_error "Укажите корректный путь к директории резервной копии"
        exit 1
    fi
    
    log_info "Восстановление данных из $backup_path..."
    
    # Остановка служб
    $DOCKER_COMPOSE_CMD $COMPOSE_FILES down
    
    # Восстановление конфигурационных файлов
    if [ -d "$backup_path/config" ]; then
        log_info "Восстановление конфигурационных файлов..."
        cp -r "$backup_path/config/" ./ 2>/dev/null || true
    fi
    
    # Восстановление томов данных
    if [ -f "$backup_path/ntrip-data.tar.gz" ]; then
        log_info "Восстановление данных NTRIP..."
        docker run --rm -v "ntrip-data:/data" -v "$(realpath $backup_path):/backup" alpine tar xzf /backup/ntrip-data.tar.gz -C /data
    fi
    
    if [ -f "$backup_path/prometheus-data.tar.gz" ]; then
        log_info "Восстановление данных Prometheus..."
        docker run --rm -v "prometheus-data:/data" -v "$(realpath $backup_path):/backup" alpine tar xzf /backup/prometheus-data.tar.gz -C /data
    fi
    
    if [ -f "$backup_path/grafana-data.tar.gz" ]; then
        log_info "Восстановление данных Grafana..."
        docker run --rm -v "grafana-data:/data" -v "$(realpath $backup_path):/backup" alpine tar xzf /backup/grafana-data.tar.gz -C /data
    fi
    
    log_success "Восстановление данных завершено"
}

# Обновление служб
update_services() {
    log_info "Обновление служб..."
    
    # Загрузка последних образов
    log_info "Загрузка последних образов..."
    $DOCKER_COMPOSE_CMD $COMPOSE_FILES pull
    
    # Пересборка локальных образов
    log_info "Пересборка локальных образов..."
    $DOCKER_COMPOSE_CMD $COMPOSE_FILES build --no-cache
    
    # Перезапуск служб
    log_info "Перезапуск служб..."
    $DOCKER_COMPOSE_CMD $COMPOSE_FILES up -d
    
    # Очистка старых образов
    log_info "Очистка неиспользуемых образов..."
    docker image prune -f
    
    log_success "Обновление служб завершено"
}

# Главная функция
main() {
    show_banner
    parse_args "$@"
    
    case "$1" in
        build)
            check_docker
            create_directories
            create_nginx_config
            create_monitoring_config
            build_image
            ;;
        start)
            check_docker
            create_directories
            start_services
            ;;
        full)
            check_docker
            create_directories
            create_nginx_config
            create_monitoring_config
            start_full_services
            ;;
        stop)
            check_docker
            stop_services
            ;;
        restart)
            check_docker
            stop_services
            sleep 2
            start_services
            ;;
        logs)
            check_docker
            view_logs
            ;;
        status)
            check_docker
            view_status
            ;;
        health)
            check_docker
            check_health
            ;;
        info)
            show_info
            ;;
        backup)
            check_docker
            backup_data
            ;;
        restore)
            check_docker
            restore_data "$2"
            ;;
        update)
            check_docker
            update_services
            ;;
        clean)
            check_docker
            clean_resources
            ;;
        help|--help|-h)
            show_help
            ;;
        "")
            log_info "Начало автоматического развёртывания..."
            check_docker
            create_directories
            create_nginx_config
            create_monitoring_config
            build_image
            start_services
            
            echo
            echo "==========================================="
            echo "    Развёртывание NTRIP Caster через Docker завершено"
            echo "==========================================="
            echo
            echo "Адреса служб:"
            echo "  - Служба NTRIP: $(hostname -I | awk '{print $1}'):2101"
            echo "  - Веб-управление: http://$(hostname -I | awk '{print $1}'):5757"
            echo
            echo "Команды управления:"
            echo "  - Просмотр состояния: $0 status"
            echo "  - Просмотр логов: $0 logs"
            echo "  - Остановка служб: $0 stop"
            echo "  - Перезапуск служб: $0 restart"
            echo
            ;;
        *)
            log_error "Неизвестная команда: $1"
            show_help
            exit 1
            ;;
    esac
}

# Выполнение главной функции
main "$@"