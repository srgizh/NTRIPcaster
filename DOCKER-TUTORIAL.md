# Руководство по установке и использованию NTRIP Caster в Docker

Данное руководство поможет вам быстро развернуть и запустить NTRIP Caster v2.2.0 с помощью Docker.

## Содержание
- [Предварительные требования](#предварительные-требования)
- [Быстрый старт](#быстрый-старт)
- [Подробные шаги установки](#подробные-шаги-установки)
- [Описание конфигурации](#описание-конфигурации)
- [Способы использования](#способы-использования)
- [Часто задаваемые вопросы](#часто-задаваемые-вопросы)
- [Расширенная конфигурация](#расширенная-конфигурация)

## Предварительные требования

### 1. Установка Docker

#### Система Windows
1. Скачать и установить [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
2. Запустить Docker Desktop
3. Проверить установку:
   ```cmd
   docker --version
   docker-compose --version
   ```

#### Система Linux (Ubuntu/Debian)
```bash
# Обновление индекса пакетов
sudo apt update

# Установка необходимых пакетов
sudo apt install apt-transport-https ca-certificates curl gnupg lsb-release

# Добавление официального GPG-ключа Docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Добавление репозитория Docker
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Установка Docker Engine
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Запуск службы Docker
sudo systemctl start docker
sudo systemctl enable docker

# Добавление текущего пользователя в группу docker (опционально)
sudo usermod -aG docker $USER
```

#### Система CentOS/RHEL
```bash
# Установка Docker
sudo yum install -y yum-utils
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo yum install docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Запуск службы Docker
sudo systemctl start docker
sudo systemctl enable docker
```

## Быстрый старт

### Способ 1: Одноразовый запуск (самый простой)

```bash
# Загрузка и прямой запуск, образ автоматически создаст необходимые каталоги и конфигурационные файлы
docker run -d \
  --name ntrip-caster \
  -p 2101:2101 \
  -p 5757:5757 \
  2rtk/ntripcaster:latest
```

> **Примечание:** Образ содержит встроенный скрипт запуска, который автоматически создаст необходимые каталоги (logs, data, config) и инициализирует конфигурационный файл по умолчанию. Данные будут храниться внутри контейнера, и пока контейнер не будет удален, данные будут сохранены. Подходит для быстрого тестирования, проверки и легкого развертывания.
>
> **Сохранение данных:** Пока контейнер не удален (`docker rm`), все данные (логи, база данных, конфигурация) будут сохранены. Перезапуск контейнера (`docker restart ntrip-caster`) не приведет к потере данных.

### Способ 2: Сохранение данных на хосте (рекомендуется для production)

> **Сценарий использования:** Данные хранятся в каталоге хоста, что облегчает миграцию сервера, обновление версий, резервное копирование данных и управление конфигурацией. Особенно подходит для сценариев, требующих частого обслуживания или развертывания в нескольких средах.

```bash
# 1. Загрузка последнего образа
docker pull 2rtk/ntripcaster:latest

# 2. Создание каталога данных
mkdir -p ./ntrip-data/{logs,data,config}

# 3. Копирование шаблона конфигурационного файла
docker run --rm 2rtk/ntripcaster:latest cat /app/config.ini.example > ./ntrip-data/config/config.ini

# 4. Запуск контейнера
docker run -d \
  --name ntrip-caster \
  -p 2101:2101 \
  -p 5757:5757 \
  -v $(pwd)/ntrip-data/logs:/app/logs \
  -v $(pwd)/ntrip-data/data:/app/data \
  -v $(pwd)/ntrip-data/config:/app/config \
  2rtk/ntripcaster:latest
```

### Способ 3: Использование Docker Compose (рекомендуется для production)

1. Загрузка файлов проекта:
```bash
git clone https://github.com/srgizh/NTRIPcaster.git
cd NTRIPcaster
```

2. Запуск службы:
```bash
# Среда разработки
docker-compose up -d

# Production-среда
docker-compose -f docker-compose.prod.yml up -d
```

## Подробные шаги установки

### 1. Подготовка рабочего каталога

```bash
# Создание каталога проекта
mkdir ntrip-caster && cd ntrip-caster

# Создание структуры каталогов данных
mkdir -p data/{logs,data,config}
```

### 2. Подготовка конфигурационного файла

```bash
# Получение шаблона конфигурационного файла
docker run --rm 2rtk/ntripcaster:latest cat /app/config.ini.example > data/config/config.ini
```

### 3. Редактирование конфигурационного файла

Редактирование файла `data/config/config.ini`, основные параметры конфигурации:

```ini

[network]
host = 0.0.0.0
ntrip_port = 2101
web_port = 5757

[database]
path = data/2rtk.db

[logging]
log_dir = logs
log_level = INFO

[security]
secret_key = your-secret-key-here   # В production-среде обязательно изменить ключ по умолчанию
password_hash_rounds = 12
```

### 4. Запуск контейнера

#### Базовый запуск
```bash
docker run -d \
  --name ntrip-caster \
  --restart unless-stopped \
  -p 2101:2101 \
  -p 5757:5757 \
  -v $(pwd)/data/logs:/app/logs \
  -v $(pwd)/data/data:/app/data \
  -v $(pwd)/data/config:/app/config \
  2rtk/ntripcaster:latest
```

#### Запуск с переменными окружения
```bash
docker run -d \
  --name ntrip-caster \
  --restart unless-stopped \
  -p 2101:2101 \
  -p 5757:5757 \
  -e NTRIP_PORT=2101 \
  -e WEB_PORT=5757 \
  -e DEBUG_MODE=false \
  -v $(pwd)/data/logs:/app/logs \
  -v $(pwd)/data/data:/app/data \
  -v $(pwd)/data/config:/app/config \
  2rtk/ntripcaster:latest
```

## Описание конфигурации

### Описание портов
- **2101**: Порт службы NTRIP (стандартный порт NTRIP)
- **5757**: Порт веб-интерфейса управления

### Описание томов данных
- `/app/logs`: Каталог файлов логов
- `/app/data`: Каталог базы данных и файлов данных
- `/app/config`: Каталог конфигурационных файлов

### Переменные окружения
- `NTRIP_PORT`: Порт службы NTRIP (по умолчанию: 2101)
- `WEB_PORT`: Порт веб-службы (по умолчанию: 5757)
- `DEBUG_MODE`: Режим отладки (по умолчанию: false)
- `DATABASE_PATH`: Путь к базе данных (по умолчанию: data/2rtk.db)
- `SECRET_KEY`: Ключ приложения

## Способы использования

### 1. Доступ к веб-интерфейсу управления

Открыть браузер и перейти по адресу: `http://localhost:5757`

Учетные данные администратора по умолчанию:
- Имя пользователя: `admin`
- Пароль: `admin123`

### 2. Добавление точки монтирования

В веб-интерфейсе:
1. Войти в интерфейс управления
2. Нажать "Добавить точку монтирования"
3. Заполнить информацию о точке монтирования:
   - Имя точки монтирования: например, `RTCM3`
   - Описание: описание точки монтирования
   - Формат: выбрать формат данных

### 3. Подключение NTRIP-клиента

Использование NTRIP-клиента для подключения:
- Сервер: `your-server-ip`
- Порт: `2101`
- Точка монтирования: имя созданной точки монтирования
- Имя пользователя/пароль: настраиваются в интерфейсе управления

### 4. Просмотр логов

```bash
# Просмотр логов контейнера
docker logs ntrip-caster

# Просмотр логов в реальном времени
docker logs -f ntrip-caster

# Просмотр файла логов приложения
tail -f data/logs/main.log
```

## Часто задаваемые вопросы

### Q1: Ошибка запуска контейнера - проблема с правами доступа

**Описание проблемы:**
При ошибке `PermissionError: [Errno 13] Permission denied: '/app/logs/main.log'` причина - проблема с правами доступа к томам Docker.

**Решение:**
```bash
# 1. Остановка и удаление существующего контейнера
docker-compose down
docker rm ntrip-caster

# 2. Удаление существующих томов данных (внимание: это удалит все данные)
docker volume rm ntripcaster_ntrip-logs ntripcaster_ntrip-data ntripcaster_ntrip-config

# 3. Пересборка образа (если используется последняя версия)
docker-compose build --no-cache

# 4. Перезапуск службы
docker-compose up -d
```

**Проверка других проблем запуска:**
```bash
# Проверка статуса контейнера
docker ps -a

# Просмотр логов ошибок
docker logs ntrip-caster

# Проверка использования портов
netstat -tlnp | grep :2101
netstat -tlnp | grep :5757
```

### Q2: Нет доступа к веб-интерфейсу

**Проверка:**
1. Убедиться, что контейнер запущен: `docker ps`
2. Убедиться, что маппинг портов правильный: `docker port ntrip-caster`
3. Проверить настройки файрвола
4. Убедиться в настройках портов в конфигурационном файле

### Q3: NTRIP-клиент не может подключиться

**Проверка:**
1. Убедиться, что порт NTRIP 2101 открыт
2. Проверить, правильно ли создана точка монтирования
3. Проверить имя пользователя и пароль
4. Просмотреть логи сервера

### Q4: Проблемы с сохранением данных

**Решение:**
```bash
# Убедиться, что том данных правильно подключен
docker inspect ntrip-caster | grep Mounts -A 20

# Проверить права доступа к каталогу
ls -la data/
sudo chown -R 1000:1000 data/
```

## Расширенная конфигурация

### 1. Использование Docker Compose

Создание файла `docker-compose.yml`:

```yaml
version: '3.8'

services:
  ntrip-caster:
    image: 2rtk/ntripcaster:latest
    container_name: ntrip-caster
    restart: unless-stopped
    ports:
      - "2101:2101"
      - "5757:5757"
    volumes:
      - ./data/logs:/app/logs
      - ./data/data:/app/data
      - ./data/config:/app/config
    environment:
      - NTRIP_PORT=2101
      - WEB_PORT=5757
      - DEBUG_MODE=false
    healthcheck:
      test: ["CMD", "python", "/app/healthcheck.py"]
      interval: 30s
      timeout: 15s
      retries: 3
      start_period: 90s

  # Опционально: добавление обратного прокси Nginx
  nginx:
    image: nginx:alpine
    container_name: ntrip-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./nginx/ssl:/etc/nginx/ssl
    depends_on:
      - ntrip-caster
```

Запуск службы:
```bash
docker-compose up -d
```

### 2. Развертывание в production-среде

#### Использование SSL/TLS

1. Подготовка SSL-сертификата
2. Настройка обратного прокси Nginx
3. Обновление правил файрвола

#### Мониторинг и логирование

```bash
# Настройка ротации логов
docker run -d \
  --name ntrip-caster \
  --log-driver json-file \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  # ... другие параметры
```

### 3. Резервное копирование и восстановление

#### Резервное копирование данных
```bash
# Резервное копирование каталога данных
tar -czf ntrip-backup-$(date +%Y%m%d).tar.gz data/

# Резервное копирование базы данных
docker exec ntrip-caster sqlite3 /app/data/2rtk.db ".backup /app/data/backup.db"
```

#### Восстановление данных
```bash
# Остановка контейнера
docker stop ntrip-caster

# Восстановление данных
tar -xzf ntrip-backup-20231201.tar.gz

# Перезапуск контейнера
docker start ntrip-caster
```

### 4. Оптимизация производительности

#### Ограничение ресурсов
```bash
docker run -d \
  --name ntrip-caster \
  --memory=512m \
  --cpus=1.0 \
  # ... другие параметры
```

#### Оптимизация сети
```bash
# Создание пользовательской сети
docker network create ntrip-network

# Использование пользовательской сети
docker run -d \
  --name ntrip-caster \
  --network ntrip-network \
  # ... другие параметры
```

## Обновление и обслуживание

### Обновление до новой версии

```bash
# 1. Резервное копирование данных
tar -czf backup-$(date +%Y%m%d).tar.gz data/

# 2. Остановка и удаление старого контейнера
docker stop ntrip-caster
docker rm ntrip-caster

# 3. Загрузка нового образа
docker pull 2rtk/ntripcaster:latest

# 4. Запуск нового контейнера
docker run -d \
  --name ntrip-caster \
  --restart unless-stopped \
  -p 2101:2101 \
  -p 5757:5757 \
  -v $(pwd)/data/logs:/app/logs \
  -v $(pwd)/data/data:/app/data \
  -v $(pwd)/data/config:/app/config \
  2rtk/ntripcaster:latest
```

### Проверка работоспособности

```bash
# Проверка состояния работоспособности контейнера
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Ручное выполнение проверки работоспособности
docker exec ntrip-caster python /app/healthcheck.py
```

## Техническая поддержка

Если при использовании возникли проблемы, можно:

1. Просмотреть документацию проекта: [Репозиторий GitHub](https://github.com/srgizh/NTRIPcaster)
2. Сообщить о проблеме: [Проблемы GitHub](https://github.com/srgizh/NTRIPcaster/issues)
3. Связаться с автором: i@jia.by
4. Посетить официальный сайт: https://2rtk.com

---

**Информация о версии:** NTRIP Caster v2.2.0  
**Дата обновления:** Август 2025  
**Автор:** i@jia.by