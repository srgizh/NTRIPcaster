# NTRIP Caster Docker Makefile
# Удобный инструмент для упрощения операций с Docker

# Окружение по умолчанию
ENV ?= development
PROFILE ?= 
DEBUG ?= false

# Конфигурация проекта
PROJECT_NAME := ntrip-caster
IMAGE_NAME := $(PROJECT_NAME)
IMAGE_TAG := latest

# Файлы Docker Compose
COMPOSE_FILE := docker-compose.yml
ifeq ($(ENV),development)
	COMPOSE_FILE += -f docker-compose.override.yml
else ifeq ($(ENV),production)
	COMPOSE_FILE += -f docker-compose.prod.yml
endif

# Команды Docker Compose
DOCKER_COMPOSE := docker compose $(addprefix -f ,$(COMPOSE_FILE))
ifeq ($(PROFILE),)
	DOCKER_COMPOSE_CMD := $(DOCKER_COMPOSE)
else
	DOCKER_COMPOSE_CMD := $(DOCKER_COMPOSE) $(addprefix --profile ,$(PROFILE))
endif

# Определение цветов
RED := \033[31m
GREEN := \033[32m
YELLOW := \033[33m
BLUE := \033[34m
MAGENTA := \033[35m
CYAN := \033[36m
WHITE := \033[37m
RESET := \033[0m

# Цель по умолчанию
.DEFAULT_GOAL := help

# Информация справки
.PHONY: help
help: ## Показать справочную информацию
	@echo "$(CYAN)NTRIP Caster Docker Makefile$(RESET)"
	@echo ""
	@echo "$(YELLOW)Использование:$(RESET)"
	@echo "  make [цель] [переменная=значение]"
	@echo ""
	@echo "$(YELLOW)Переменные:$(RESET)"
	@echo "  ENV=development|testing|production  Указать окружение (по умолчанию: development)"
	@echo "  PROFILE=nginx,monitoring            Указать compose profile"
	@echo "  DEBUG=true|false                    Включить режим отладки (по умолчанию: false)"
	@echo ""
	@echo "$(YELLOW)Цели:$(RESET)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(YELLOW)Примеры:$(RESET)"
	@echo "  make build ENV=production          # Сборка образа production-окружения"
	@echo "  make up PROFILE=nginx,monitoring   # Запуск полного стека сервисов"
	@echo "  make logs SERVICE=ntrip-caster     # Просмотр логов конкретного сервиса"

# Проверка окружения
.PHONY: check-env
check-env: ## Проверить зависимости окружения
	@echo "$(BLUE)Проверка зависимостей окружения...$(RESET)"
	@command -v docker >/dev/null 2>&1 || { echo "$(RED)Ошибка: Docker не установлен$(RESET)"; exit 1; }
	@command -v docker compose >/dev/null 2>&1 || { echo "$(RED)Ошибка: Docker Compose не установлен$(RESET)"; exit 1; }
	@echo "$(GREEN)✓ Проверка окружения Docker пройдена$(RESET)"
	@docker --version
	@docker compose version

# Создание необходимых каталогов
.PHONY: setup
setup: ## Создать необходимые каталоги и файлы
	@echo "$(BLUE)Создание структуры каталогов проекта...$(RESET)"
	@mkdir -p data logs config backup
	@mkdir -p secrets nginx/logs redis
	@mkdir -p monitoring/prometheus/rules
	@mkdir -p monitoring/grafana/provisioning/datasources
	@mkdir -p monitoring/grafana/provisioning/dashboards
	@mkdir -p monitoring/grafana/dashboards
	@echo "$(GREEN)✓ Создание структуры каталогов завершено$(RESET)"

# Сборка образа
.PHONY: build
build: check-env setup ## Собрать Docker-образ
	@echo "$(BLUE)Сборка Docker-образа (окружение: $(ENV))...$(RESET)"
	$(DOCKER_COMPOSE_CMD) build
	@echo "$(GREEN)✓ Сборка образа завершена$(RESET)"

# Загрузка образа
.PHONY: pull
pull: check-env ## Загрузить Docker-образ
	@echo "$(BLUE)Загрузка Docker-образа...$(RESET)"
	$(DOCKER_COMPOSE_CMD) pull
	@echo "$(GREEN)✓ Загрузка образа завершена$(RESET)"

# Запуск сервисов
.PHONY: up
up: check-env setup ## Запустить сервисы
	@echo "$(BLUE)Запуск сервисов (окружение: $(ENV))...$(RESET)"
	$(DOCKER_COMPOSE_CMD) up -d
	@sleep 5
	@$(MAKE) health
	@$(MAKE) info
	@echo "$(GREEN)✓ Запуск сервисов завершён$(RESET)"

# Остановка сервисов
.PHONY: down
down: ## Остановить сервисы
	@echo "$(BLUE)Остановка сервисов...$(RESET)"
	$(DOCKER_COMPOSE_CMD) down
	@echo "$(GREEN)✓ Сервисы остановлены$(RESET)"

# Перезапуск сервисов
.PHONY: restart
restart: ## Перезапустить сервисы
	@echo "$(BLUE)Перезапуск сервисов...$(RESET)"
	$(DOCKER_COMPOSE_CMD) restart
	@sleep 5
	@$(MAKE) health
	@echo "$(GREEN)✓ Перезапуск сервисов завершён$(RESET)"

# Просмотр статуса
.PHONY: status
status: ## Показать статус сервисов
	@echo "$(BLUE)Статус сервисов:$(RESET)"
	$(DOCKER_COMPOSE_CMD) ps

# Просмотр логов
.PHONY: logs
logs: ## Показать логи сервисов (SERVICE=имя_сервиса)
	@echo "$(BLUE)Просмотр логов сервисов...$(RESET)"
ifeq ($(SERVICE),)
	$(DOCKER_COMPOSE_CMD) logs -f
else
	$(DOCKER_COMPOSE_CMD) logs -f $(SERVICE)
endif

# Проверка работоспособности
.PHONY: health
health: ## Проверить состояние работоспособности сервисов
	@echo "$(BLUE)Проверка состояния работоспособности сервисов...$(RESET)"
	@./docker-deploy.sh health 2>/dev/null || echo "$(YELLOW)Используйте './docker-deploy.sh health' для подробной проверки работоспособности$(RESET)"

# Показать информацию о сервисах
.PHONY: info
info: ## Показать информацию о сервисах
	@echo "$(BLUE)Информация о сервисах NTRIP Caster:$(RESET)"
	@echo ""
	@echo "$(CYAN)Окружение:$(RESET) $(ENV)"
	@echo "$(CYAN)Конфигурационные файлы:$(RESET) $(COMPOSE_FILE)"
	@echo "$(CYAN)Название проекта:$(RESET) $(PROJECT_NAME)"
	@echo ""
	@echo "$(CYAN)Конечные точки сервисов:$(RESET)"
	@echo "  • NTRIP Caster: http://localhost:2101"
	@echo "  • Веб-интерфейс: http://localhost:5757"
	@echo "  • Prometheus: http://localhost:9090"
	@echo "  • Grafana: http://localhost:3000"
ifeq ($(ENV),development)
	@echo "  • Adminer: http://localhost:8081"
	@echo "  • Dozzle: http://localhost:8082"
	@echo "  • cAdvisor: http://localhost:8083"
endif
	@echo ""

# Вход в контейнер
.PHONY: shell
shell: ## Войти в shell контейнера (SERVICE=имя_сервиса, по умолчанию ntrip-caster)
	@echo "$(BLUE)Вход в shell контейнера...$(RESET)"
	$(DOCKER_COMPOSE_CMD) exec $(or $(SERVICE),ntrip-caster) /bin/bash

# Выполнение команды
.PHONY: exec
exec: ## Выполнить команду в контейнере (SERVICE=имя_сервиса CMD=команда)
	@echo "$(BLUE)Выполнение команды в контейнере...$(RESET)"
	$(DOCKER_COMPOSE_CMD) exec $(or $(SERVICE),ntrip-caster) $(CMD)

# Резервное копирование данных
.PHONY: backup
backup: ## Создать резервную копию данных
	@echo "$(BLUE)Создание резервной копии данных...$(RESET)"
	@./docker-deploy.sh backup
	@echo "$(GREEN)✓ Резервное копирование данных завершено$(RESET)"

# Восстановление данных
.PHONY: restore
restore: ## Восстановить данные (BACKUP_PATH=путь_к_резервной_копии)
	@echo "$(BLUE)Восстановление данных...$(RESET)"
	@if [ -z "$(BACKUP_PATH)" ]; then \
		echo "$(RED)Ошибка: Укажите путь к резервной копии BACKUP_PATH=<путь>$(RESET)"; \
		exit 1; \
	fi
	@./docker-deploy.sh restore $(BACKUP_PATH)
	@echo "$(GREEN)✓ Восстановление данных завершено$(RESET)"

# Обновление сервисов
.PHONY: update
update: ## Обновить сервисы
	@echo "$(BLUE)Обновление сервисов...$(RESET)"
	@$(MAKE) pull
	@$(MAKE) build
	@$(MAKE) restart
	@echo "$(GREEN)✓ Обновление сервисов завершено$(RESET)"

# Очистка ресурсов
.PHONY: clean
clean: ## Очистить ресурсы Docker
	@echo "$(BLUE)Очистка ресурсов Docker...$(RESET)"
	$(DOCKER_COMPOSE_CMD) down -v --remove-orphans
	docker system prune -f
	docker volume prune -f
	@echo "$(GREEN)✓ Очистка ресурсов завершена$(RESET)"

# Глубокая очистка
.PHONY: clean-all
clean-all: ## Глубокая очистка (включая образы)
	@echo "$(BLUE)Глубокая очистка ресурсов Docker...$(RESET)"
	@$(MAKE) clean
	docker image prune -a -f
	docker builder prune -a -f
	@echo "$(GREEN)✓ Глубокая очистка завершена$(RESET)"

# Ярлык для окружения разработки
.PHONY: dev
dev: ## Запустить окружение разработки
	@$(MAKE) up ENV=development

# Ярлык для production-окружения
.PHONY: prod
prod: ## Запустить production-окружение
	@$(MAKE) up ENV=production PROFILE=nginx,monitoring

# Ярлык для тестового окружения
.PHONY: test
test: ## Запустить тестовое окружение
	@$(MAKE) up ENV=testing

# Сервисы мониторинга
.PHONY: monitoring
monitoring: ## Запустить сервисы мониторинга
	@echo "$(BLUE)Запуск сервисов мониторинга...$(RESET)"
	$(DOCKER_COMPOSE_CMD) --profile monitoring up -d
	@echo "$(GREEN)✓ Сервисы мониторинга запущены$(RESET)"
	@echo "$(CYAN)Prometheus:$(RESET) http://localhost:9090"
	@echo "$(CYAN)Grafana:$(RESET) http://localhost:3000 (admin/admin)"

# Сетевой прокси
.PHONY: proxy
proxy: ## Запустить сетевой прокси
	@echo "$(BLUE)Запуск сетевого прокси...$(RESET)"
	$(DOCKER_COMPOSE_CMD) --profile nginx up -d
	@echo "$(GREEN)✓ Сетевой прокси запущен$(RESET)"

# Тестирование производительности
.PHONY: benchmark
benchmark: ## Запустить тестирование производительности
	@echo "$(BLUE)Запуск тестирования производительности...$(RESET)"
	@echo "$(YELLOW)TODO: Реализовать скрипт тестирования производительности$(RESET)"

# Сканирование безопасности
.PHONY: security-scan
security-scan: ## Запустить сканирование безопасности
	@echo "$(BLUE)Запуск сканирования безопасности...$(RESET)"
	@command -v trivy >/dev/null 2>&1 && trivy image $(IMAGE_NAME):$(IMAGE_TAG) || echo "$(YELLOW)Установите trivy для сканирования безопасности$(RESET)"

# Генерация конфигурации
.PHONY: config
config: ## Сгенерировать конфигурационные файлы
	@echo "$(BLUE)Генерация конфигурационных файлов...$(RESET)"
	$(DOCKER_COMPOSE_CMD) config

# Проверка конфигурации
.PHONY: validate
validate: ## Проверить конфигурационные файлы
	@echo "$(BLUE)Проверка конфигурационных файлов...$(RESET)"
	$(DOCKER_COMPOSE_CMD) config --quiet
	@echo "$(GREEN)✓ Проверка конфигурационных файлов пройдена$(RESET)"

# Показать информацию о версии
.PHONY: version
version: ## Показать информацию о версии
	@echo "$(CYAN)Информация о версии NTRIP Caster Docker:$(RESET)"
	@echo "Проект: $(PROJECT_NAME)"
	@echo "Образ: $(IMAGE_NAME):$(IMAGE_TAG)"
	@echo "Окружение: $(ENV)"
	@docker --version
	@docker compose version

# Очистка кэша сборки
.PHONY: clean-cache
clean-cache: ## Очистить кэш сборки
	@echo "$(BLUE)Очистка кэша сборки...$(RESET)"
	docker builder prune -f
	@echo "$(GREEN)✓ Очистка кэша сборки завершена$(RESET)"

# Экспорт образа
.PHONY: export
export: ## Экспортировать Docker-образ
	@echo "$(BLUE)Экспорт Docker-образа...$(RESET)"
	docker save -o $(PROJECT_NAME)-$(IMAGE_TAG).tar $(IMAGE_NAME):$(IMAGE_TAG)
	@echo "$(GREEN)✓ Экспорт образа завершён: $(PROJECT_NAME)-$(IMAGE_TAG).tar$(RESET)"

# Импорт образа
.PHONY: import
import: ## Импортировать Docker-образ (FILE=файл_образа)
	@echo "$(BLUE)Импорт Docker-образа...$(RESET)"
	@if [ -z "$(FILE)" ]; then \
		echo "$(RED)Ошибка: Укажите файл образа FILE=<путь_к_файлу>$(RESET)"; \
		exit 1; \
	fi
	docker load -i $(FILE)
	@echo "$(GREEN)✓ Импорт образа завершён$(RESET)"

# Показать использование ресурсов
.PHONY: stats
stats: ## Показать использование ресурсов контейнерами
	@echo "$(BLUE)Использование ресурсов контейнерами:$(RESET)"
	docker stats --no-stream

# Показать информацию о сети
.PHONY: network
network: ## Показать информацию о сети
	@echo "$(BLUE)Информация о сети Docker:$(RESET)"
	docker network ls | grep ntrip
	docker network inspect ntrip-network 2>/dev/null || echo "$(YELLOW)Сеть ntrip-network не существует$(RESET)"

# Показать информацию о томах
.PHONY: volumes
volumes: ## Показать информацию о томах
	@echo "$(BLUE)Информация о томах Docker:$(RESET)"
	docker volume ls | grep ntrip

# Быстрая пересборка
.PHONY: rebuild
rebuild: ## Быстро пересобрать сервисы
	@echo "$(BLUE)Быстрая пересборка сервисов...$(RESET)"
	@$(MAKE) down
	@$(MAKE) build
	@$(MAKE) up
	@echo "$(GREEN)✓ Пересборка сервисов завершена$(RESET)"