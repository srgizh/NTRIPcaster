#!/bin/bash
# Скрипт сборки и развёртывания защищённой версии NTRIP Caster
# Используется для сборки защищённого образа Docker и отправки в репозиторий

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
IMAGE_NAME="ntripcaster"
IMAGE_TAG="2.2.0"
REGISTRY_URL="2rtk"  # Имя пользователя/организации Docker Hub
REGISTRY_NAMESPACE=""  # Docker Hub не требует дополнительного пространства имён
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

log_success() {
    echo -e "${CYAN}[SUCCESS]${NC} $1"
}

# Отображение баннера
show_banner() {
    echo -e "${CYAN}"
    cat << 'EOF'
    ███╗   ██╗████████╗██████╗ ██╗██████╗ 
    ████╗  ██║╚══██╔══╝██╔══██╗██║██╔══██╗
    ██╔██╗ ██║   ██║   ██████╔╝██║██████╔╝
    ██║╚██╗██║   ██║   ██╔══██╗██║██╔═══╝ 
    ██║ ╚████║   ██║   ██║  ██║██║██║     
    ╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝     
EOF
    echo -e "${NC}"
    echo -e "${GREEN}    Инструмент сборки и развёртывания защищённой версии NTRIP Caster${NC}"
    echo -e "${BLUE}    Версия: ${IMAGE_TAG}${NC}"
    echo
}

# Проверка зависимостей
check_dependencies() {
    log_step "Проверка зависимостей для сборки..."
    
    local deps=("python3" "docker" "git")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            log_error "Отсутствует зависимость: $dep"
            exit 1
        fi
    done
    
    # Проверка запуска Docker
    if ! docker info &> /dev/null; then
        log_error "Docker не запущен или нет доступа"
        exit 1
    fi
    
    log_info "Проверка зависимостей пройдена"
}

# Сборка защищённой версии бинарного файла
build_protected_binary() {
    log_step "Сборка защищённого бинарного файла..."
    
    cd "$SCRIPT_DIR"
    
    # Запуск скрипта защищённой сборки
    if [ -f "build_protected.py" ]; then
        python3 build_protected.py
    else
        log_error "Скрипт build_protected.py не найден"
        exit 1
    fi
    
    # Проверка результата сборки
    if [ ! -d "dist_protected/ntrip-caster" ]; then
        log_error "Не удалось собрать бинарный файл"
        exit 1
    fi
    
    log_success "Бинарный файл собран"
}

# Сборка образа Docker
build_docker_image() {
    log_step "Сборка образа Docker..."
    
    cd "$SCRIPT_DIR"
    
    # Сборка образа
    local full_image_name="${IMAGE_NAME}:${IMAGE_TAG}"
    
    docker build \
        -f Dockerfile \
        -t "$full_image_name" \
        -t "${IMAGE_NAME}:latest" \
        --build-arg BUILD_DATE="$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        --build-arg VCS_REF="$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')" \
        .
    
    log_success "Образ Docker собран: $full_image_name"
}

# Тестирование образа
test_image() {
    log_step "Тестирование образа Docker..."
    
    local test_container="ntrip-test-$(date +%s)"
    
    # Запуск тестового контейнера
    docker run -d \
        --name "$test_container" \
        -p 12101:2101 \
        -p 15757:5757 \
        "${IMAGE_NAME}:${IMAGE_TAG}"
    
    # Ожидание запуска контейнера
    sleep 10
    
    # Проверка состояния контейнера
    if docker ps | grep -q "$test_container"; then
        log_info "Контейнер успешно запущен, выполняется проверка здоровья..."
        
        # Ожидание проверки здоровья
        local max_attempts=30
        local attempt=0
        
        while [ $attempt -lt $max_attempts ]; do
            if docker exec "$test_container" python3 /app/healthcheck.py &>/dev/null; then
                log_success "Проверка здоровья пройдена"
                break
            fi
            
            attempt=$((attempt + 1))
            sleep 2
        done
        
        if [ $attempt -eq $max_attempts ]; then
            log_warn "Истёк таймаут проверки здоровья, но контейнер всё ещё работает"
        fi
    else
        log_error "Не удалось запустить контейнер"
        docker logs "$test_container"
        docker rm -f "$test_container" 2>/dev/null || true
        exit 1
    fi
    
    # Очистка тестового контейнера
    docker rm -f "$test_container" 2>/dev/null || true
    log_success "Тестирование образа завершено"
}

# Отправка в репозиторий
push_to_registry() {
    if [ -z "$REGISTRY_URL" ]; then
        log_warn "Адрес репозитория не установлен, пропуск шага отправки"
        log_info "Для отправки установите переменные REGISTRY_URL и REGISTRY_NAMESPACE"
        return
    fi
    
    log_step "Отправка образа в репозиторий..."
    
    local registry_image
    if [ -n "$REGISTRY_NAMESPACE" ]; then
        registry_image="${REGISTRY_URL}/${REGISTRY_NAMESPACE}/${IMAGE_NAME}"
    else
        registry_image="${REGISTRY_URL}/${IMAGE_NAME}"
    fi
    
    # Тегирование образа
    docker tag "${IMAGE_NAME}:${IMAGE_TAG}" "${registry_image}:${IMAGE_TAG}"
    docker tag "${IMAGE_NAME}:latest" "${registry_image}:latest"
    
    # Отправка образа
    docker push "${registry_image}:${IMAGE_TAG}"
    docker push "${registry_image}:latest"
    
    log_success "Образ отправлен: ${registry_image}:${IMAGE_TAG}"
}

# Генерация документации по развёртыванию
generate_deployment_docs() {
    log_step "Генерация документации по развёртыванию..."
    
    local docs_dir="deployment_docs"
    mkdir -p "$docs_dir"
    
    # Генерация docker-compose.yml
    cat > "${docs_dir}/docker-compose.yml" << EOF
# Конфигурация развёртывания защищённой версии NTRIP Caster
# Использование: docker-compose up -d

version: '3.8'

services:
  ntrip-caster:
    image: ${REGISTRY_URL:+${REGISTRY_URL}/}${REGISTRY_NAMESPACE:+${REGISTRY_NAMESPACE}/}${IMAGE_NAME}:${IMAGE_TAG}
    container_name: ntrip-caster
    hostname: ntrip-caster
    restart: unless-stopped
    ports:
      - "2101:2101"  # Порт службы NTRIP
      - "5757:5757"  # Порт веб-управления
    volumes:
      - ntrip-data:/app/data          # Постоянное хранение данных
      - ntrip-logs:/app/logs          # Постоянное хранение логов
      - ntrip-config:/app/config      # Файлы конфигурации
      - /etc/localtime:/etc/localtime:ro  # Синхронизация часового пояса
    environment:
      - TZ=Asia/Shanghai
      - NTRIP_CONFIG_FILE=/app/config/config.ini
    networks:
      - ntrip-network
    healthcheck:
      test: ["CMD", "python", "/app/healthcheck.py"]
      interval: 30s
      timeout: 15s
      retries: 3
      start_period: 90s
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"
        compress: "true"
    security_opt:
      - no-new-privileges:true
    ulimits:
      nofile:
        soft: 65536
        hard: 65536

volumes:
  ntrip-data:
    driver: local
  ntrip-logs:
    driver: local
  ntrip-config:
    driver: local

networks:
  ntrip-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
EOF

    # Генерация скрипта развёртывания
    cat > "${docs_dir}/deploy.sh" << 'EOF'
#!/bin/bash
# Скрипт автоматического развёртывания NTRIP Caster

set -e

echo "Начало развёртывания NTRIP Caster..."

# Проверка Docker и docker-compose
if ! command -v docker &> /dev/null; then
    echo "Ошибка: Docker не установлен"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "Ошибка: docker-compose не установлен"
    exit 1
fi

# Загрузка последних образов
echo "Загрузка последних образов..."
docker-compose pull

# Запуск служб
echo "Запуск служб..."
docker-compose up -d

# Ожидание запуска служб
echo "Ожидание запуска служб..."
sleep 30

# Проверка состояния служб
echo "Проверка состояния служб..."
docker-compose ps

echo "Развёртывание завершено!"
echo "Адрес службы NTRIP: http://localhost:2101"
echo "Веб-интерфейс управления: http://localhost:5757"
echo "Учётная запись администратора по умолчанию: admin/admin123"
echo ""
echo "Часто используемые команды:"
echo "  Просмотр логов: docker-compose logs -f"
echo "  Остановка служб: docker-compose down"
echo "  Перезапуск служб: docker-compose restart"
EOF

    chmod +x "${docs_dir}/deploy.sh"
    
    # Генерация README
    cat > "${docs_dir}/README.md" << EOF
# Руководство по развёртыванию NTRIP Caster

## Быстрое развёртывание

1. Убедитесь, что установлены Docker и docker-compose
2. Запустите скрипт развёртывания:
   \`\`\`bash
   ./deploy.sh
   \`\`\`

## Ручное развёртывание

1. Загрузите образ:
   \`\`\`bash
   docker-compose pull
   \`\`\`

2. Запустите службы:
   \`\`\`bash
   docker-compose up -d
   \`\`\`

## Доступ к службам

- Служба NTRIP: http://localhost:2101
- Веб-интерфейс управления: http://localhost:5757
- Учётная запись администратора по умолчанию: admin/admin123

## Описание конфигурации

Файл конфигурации находится внутри контейнера по пути \`/app/config/config.ini\`, может быть сохранён через том данных.

## Постоянное хранение данных

- Директория данных: том \`ntrip-data\`
- Директория логов: том \`ntrip-logs\`  
- Директория конфигурации: том \`ntrip-config\`

## Часто используемые команды

\`\`\`bash
# Просмотр состояния служб
docker-compose ps

# Просмотр логов
docker-compose logs -f

# Перезапуск служб
docker-compose restart

# Остановка служб
docker-compose down

# Обновление служб
docker-compose pull && docker-compose up -d
\`\`\`

## Устранение неполадок

1. Проверьте, не заняты ли порты
2. Проверьте, что служба Docker работает нормально
3. Просмотрите логи контейнера для диагностики проблем

EOF

    log_success "Документация по развёртыванию сгенерирована: $docs_dir/"
}

# Очистка файлов сборки
cleanup_build_files() {
    log_step "Очистка файлов сборки..."
    
    # Опциональная очистка, сохранить важные файлы
    if [ -d "build_protected" ]; then
        rm -rf build_protected/work build_protected/obfuscated
    fi
    
    log_info "Очистка файлов сборки завершена"
}

# Отображение справки по использованию
show_help() {
    cat << EOF
Инструмент сборки и развёртывания защищённой версии NTRIP Caster

Использование: $0 [опции]

Опции:
  --registry-url URL        Установить адрес репозитория Docker
  --registry-namespace NS   Установить пространство имён репозитория
  --skip-test              Пропустить тестирование образа
  --skip-push              Пропустить отправку в репозиторий
  --cleanup                Очистить временные файлы после сборки
  --help, -h               Отобразить эту справку

Примеры:
  $0 --registry-url registry.example.com --registry-namespace mycompany
  $0 --skip-test --skip-push

EOF
}

# Парсинг аргументов командной строки
parse_args() {
    SKIP_TEST=false
    SKIP_PUSH=false
    CLEANUP=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --registry-url)
                REGISTRY_URL="$2"
                shift 2
                ;;
            --registry-namespace)
                REGISTRY_NAMESPACE="$2"
                shift 2
                ;;
            --skip-test)
                SKIP_TEST=true
                shift
                ;;
            --skip-push)
                SKIP_PUSH=true
                shift
                ;;
            --cleanup)
                CLEANUP=true
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "Неизвестный параметр: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

# Главная функция
main() {
    # Парсинг параметров
    parse_args "$@"
    
    # Отображение баннера
    show_banner
    
    # Отображение информации о конфигурации
    log_info "Конфигурация сборки:"
    echo "  Имя образа: ${IMAGE_NAME}:${IMAGE_TAG}"
    echo "  Адрес репозитория: ${REGISTRY_URL:-'не установлен'}"
    echo "  Пространство имён: ${REGISTRY_NAMESPACE:-'не установлено'}"
    echo "  Пропустить тест: ${SKIP_TEST}"
    echo "  Пропустить отправку: ${SKIP_PUSH}"
    echo
    
    try {
        # 1. Проверка зависимостей
        check_dependencies
        
        # 2. Сборка защищённой версии бинарного файла
        build_protected_binary
        
        # 3. Сборка образа Docker
        build_docker_image
        
        # 4. Тестирование образа (опционально)
        if [ "$SKIP_TEST" = false ]; then
            test_image
        fi
        
        # 5. Отправка в репозиторий (опционально)
        if [ "$SKIP_PUSH" = false ]; then
            push_to_registry
        fi
        
        # 6. Генерация документации по развёртыванию
        generate_deployment_docs
        
        # 7. Очистка файлов сборки (опционально)
        if [ "$CLEANUP" = true ]; then
            cleanup_build_files
        fi
        
        echo
        log_success "Сборка и развёртывание завершены!"
        echo
        log_info "Следующие шаги:"
        echo "  1. Просмотреть документацию по развёртыванию: deployment_docs/README.md"
        echo "  2. Использовать скрипт развёртывания: cd deployment_docs && ./deploy.sh"
        if [ -n "$REGISTRY_URL" ]; then
            echo "  3. Распространить образ: ${REGISTRY_URL}/${REGISTRY_NAMESPACE:+${REGISTRY_NAMESPACE}/}${IMAGE_NAME}:${IMAGE_TAG}"
        fi
        echo
        
    } catch {
        log_error "Сборка не удалась: $1"
        exit 1
    }
}

# Функции обработки ошибок Bash
try() {
    "$@"
}

catch() {
    case $? in
        0) ;; # Успех, ничего не делать
        *) "$@" ;; # Неудача, выполнить блок catch
    esac
}

# Точка входа скрипта
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi