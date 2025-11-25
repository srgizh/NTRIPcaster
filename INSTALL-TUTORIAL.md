# Руководство по установке NTRIP Caster в Linux

Прямая установка и развертывание NTRIP Caster v2.2.0 в Linux, поддерживаются основные дистрибутивы: Debian, Ubuntu, CentOS, RHEL и другие.

## Содержание
- [Системные требования](#системные-требования)
- [Быстрая установка](#быстрая-установка)
- [Скрипт автоматической установки](#скрипт-автоматической-установки)
- [Подробные шаги установки](#подробные-шаги-установки)
- [Описание конфигурации](#описание-конфигурации)
- [Управление службой](#управление-службой)
- [Часто задаваемые вопросы](#часто-задаваемые-вопросы)
- [Оптимизация производительности](#оптимизация-производительности)
- [Настройка безопасности](#настройка-безопасности)

## Системные требования

### Минимальные требования
- **Операционная система**: Linux (Debian 10+, Ubuntu 18.04+, CentOS 7+, RHEL 7+)
- **CPU**: 1 ядро
- **Память**: 512MB RAM
- **Хранилище**: 1GB свободного места
- **Python**: 3.8+ (рекомендуется 3.11)

### Рекомендуемая конфигурация
- **CPU**: 2+ ядра
- **Память**: 2GB+ RAM
- **Хранилище**: 10GB+ свободного места
- **Сеть**: стабильное сетевое соединение

### Поддерживаемые дистрибутивы
- Debian 10/11/12 (Buster/Bullseye/Bookworm)
- Ubuntu 18.04/20.04/22.04/24.04 LTS
- CentOS 7/8/9
- RHEL 7/8/9
- Rocky Linux 8/9
- AlmaLinux 8/9
- openSUSE Leap 15.x
- Fedora 35+

### Быстрая ручная установка

```bash
# 1. Клонирование проекта
git clone https://github.com/srgizh/NTRIPcaster.git
cd NTRIPcaster

# 2. Запуск скрипта установки
sudo chmod +x install.sh
sudo ./install.sh

# 3. Запуск службы
sudo systemctl start ntripcaster
sudo systemctl enable ntripcaster
```

## Скрипт автоматической установки

### Автоматический скрипт установки

Предоставляется автоматический скрипт установки, который может установить NTRIP Caster одним кликом в большинстве дистрибутивов Linux.

#### Способы использования

**Способ 1: Прямая загрузка и выполнение (рекомендуется)**
```bash
# Загрузка и запуск скрипта установки
wget -O - https://raw.githubusercontent.com/srgizh/NTRIPcaster/main/install.sh | sudo bash
```

**Способ 2: Загрузка и последующее выполнение**
```bash
# Загрузка скрипта в локальную систему
wget https://raw.githubusercontent.com/srgizh/NTRIPcaster/main/install.sh
chmod +x install.sh
sudo ./install.sh
```

> **Примечание**: Скрипт автоматически загрузит последние файлы проекта с GitHub, нет необходимости вручную клонировать репозиторий.

#### Функции скрипта

Скрипт установки автоматически выполнит следующие операции:

1. **Проверка системного окружения**
   - Автоматическое определение дистрибутива Linux (Debian/Ubuntu/CentOS/RHEL/openSUSE и т.д.)
   - Проверка версии системы и архитектуры
   - Проверка необходимых системных прав

2. **Установка системных зависимостей**
   - Обновление менеджера пакетов системы
   - Установка Python 3.8+ и связанных инструментов разработки
   - Установка необходимых компонентов (Git, SQLite, Nginx и т.д.)
   - Настройка правил файрвола

3. **Создание системного пользователя и каталогов**
   - Создание выделенного системного пользователя `ntripcaster`
   - Создание структуры каталогов приложения (`/opt/ntripcaster`)
   - Настройка каталога логов (`/var/log/ntripcaster`)
   - Настройка соответствующих прав доступа к файлам

4. **Загрузка и настройка приложения**
   - Автоматическое клонирование последнего исходного кода с GitHub (не требуется ручная загрузка)
   - Создание виртуального окружения Python
   - Установка зависимостей Python
   - Генерация конфигурационного файла по умолчанию

5. **Настройка системной службы**
   - Создание файла службы systemd
   - Включение автозапуска при загрузке
   - Запуск службы NTRIP Caster
   - Настройка ротации логов

6. **Настройка сети**
   - Открытие необходимых портов (2101, 5757)
   - Настройка правил файрвола
   - Опциональная настройка обратного прокси Nginx

#### Параметры установки

Скрипт поддерживает следующие переменные окружения для настройки установки:

```bash
# Указание каталога установки
export INSTALL_DIR="/opt/ntripcaster"

# Указание имени пользователя
export NTRIP_USER="ntripcaster"

# Указание портов
export NTRIP_PORT="2101"
export WEB_PORT="5757"

# Установка обратного прокси Nginx
export INSTALL_NGINX="true"

# Включение SSL
export ENABLE_SSL="false"

# Запуск скрипта установки
sudo -E ./install.sh
```

#### Проверка установки

После завершения установки скрипт автоматически проверит результат установки:

```bash
# Проверка статуса службы
sudo systemctl status ntripcaster

# Проверка прослушивания портов
sudo netstat -tlnp | grep :2101
sudo netstat -tlnp | grep :5757

# Доступ к веб-интерфейсу
curl -I http://localhost:5757
```

#### Удаление

Для удаления можно использовать скрипт удаления:

```bash
# Загрузка и запуск скрипта удаления
wget -O - https://raw.githubusercontent.com/srgizh/NTRIPcaster/main/uninstall.sh | sudo bash
```

### Быстрая проверка

После завершения установки вы можете быстро проверить следующим образом:

1. **Проверка статуса службы**:
   ```bash
   sudo systemctl status ntripcaster
   ```

2. **Доступ к веб-интерфейсу управления**:
   Откройте браузер и перейдите по адресу `http://your-server-ip:5757`
   
   Учетные данные по умолчанию:
   - Имя пользователя: `admin`
   - Пароль: `admin123`

3. **Тестирование NTRIP-подключения**:
   ```bash
   telnet localhost 2101
   ```

## Подробные шаги установки

### 1. Подготовка системы

#### Системы Debian/Ubuntu

```bash
# Обновление системных пакетов
sudo apt update && sudo apt upgrade -y

# Установка необходимых системных пакетов
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    wget \
    curl \
    sqlite3 \
    build-essential \
    python3-dev \
    libssl-dev \
    libffi-dev \
    supervisor \
    nginx

# Установка пакетов разработки systemd (при необходимости)
sudo apt install -y libsystemd-dev
```

#### Системы CentOS/RHEL

```bash
# CentOS 7
sudo yum update -y
sudo yum install -y epel-release
sudo yum install -y \
    python3 \
    python3-pip \
    git \
    wget \
    curl \
    sqlite \
    gcc \
    python3-devel \
    openssl-devel \
    libffi-devel \
    supervisor \
    nginx

# CentOS 8/9 или RHEL 8/9
sudo dnf update -y
sudo dnf install -y epel-release
sudo dnf install -y \
    python3 \
    python3-pip \
    git \
    wget \
    curl \
    sqlite \
    gcc \
    python3-devel \
    openssl-devel \
    libffi-devel \
    supervisor \
    nginx
```

#### Системы openSUSE

```bash
# Обновление системы
sudo zypper refresh && sudo zypper update -y

# Установка необходимых пакетов
sudo zypper install -y \
    python3 \
    python3-pip \
    git \
    wget \
    curl \
    sqlite3 \
    gcc \
    python3-devel \
    libopenssl-devel \
    libffi-devel \
    supervisor \
    nginx
```

### 2. Создание системного пользователя

```bash
# Создание выделенного пользователя
sudo useradd -r -s /bin/false -d /opt/ntripcaster ntripcaster

# Создание каталогов приложения
sudo mkdir -p /opt/ntripcaster
sudo mkdir -p /var/log/ntripcaster
sudo mkdir -p /etc/ntripcaster

# Установка прав доступа к каталогам
sudo chown -R ntripcaster:ntripcaster /opt/ntripcaster
sudo chown -R ntripcaster:ntripcaster /var/log/ntripcaster
sudo chown -R ntripcaster:ntripcaster /etc/ntripcaster
```

### 3. Загрузка и установка приложения

```bash
# Переход в каталог приложения
cd /opt/ntripcaster

# Загрузка исходного кода
sudo -u ntripcaster git clone https://github.com/srgizh/NTRIPcaster.git 

# Создание виртуального окружения Python
sudo -u ntripcaster python3 -m venv venv

# Активация виртуального окружения и установка зависимостей
sudo -u ntripcaster bash -c '
    source venv/bin/activate
    pip install --upgrade pip setuptools wheel
    pip install -r requirements.txt
'
```

### 4. Настройка приложения

```bash
# Копирование конфигурационного файла
sudo -u ntripcaster cp config.ini.example /etc/ntripcaster/config.ini

# Редактирование конфигурационного файла
sudo nano /etc/ntripcaster/config.ini
```

#### Основные параметры конфигурации:

```ini
[app]
name = 2RTK Ntrip Caster
version = 2.1.9
description = Ntrip Caster
author = 2rtk
contact = your-email@example.com
website = https://your-domain.com

[network]
host = 0.0.0.0
ntrip_port = 2101
web_port = 5757

[database]
path = /opt/ntripcaster/data/2rtk.db

[logging]
log_dir = /var/log/ntripcaster
log_level = INFO
log_file = main.log
log_format = %(asctime)s - %(name)s - %(levelname)s - %(message)s
log_max_size = 10485760
log_backup_count = 5

[security]
secret_key = $(openssl rand -hex 32)
password_hash_rounds = 12
session_timeout = 3600
```

### 5. Генерация ключа и инициализация базы данных

```bash
# Генерация безопасного ключа
SECRET_KEY=$(openssl rand -hex 32)
sudo sed -i "s/your-secret-key-here/$SECRET_KEY/g" /etc/ntripcaster/config.ini

# Создание каталога данных
sudo -u ntripcaster mkdir -p /opt/ntripcaster/data

# Инициализация базы данных (если приложение поддерживает)
sudo -u ntripcaster bash -c '
    cd /opt/ntripcaster
    source venv/bin/activate
    python -c "from src.database import init_db; init_db()"
'
```

### 6. Создание службы systemd

```bash
# Создание файла службы
sudo tee /etc/systemd/system/ntripcaster.service > /dev/null <<EOF
[Unit]
Description=NTRIP Caster Service
After=network.target
Wants=network.target

[Service]
Type=simple
User=ntripcaster
Group=ntripcaster
WorkingDirectory=/opt/ntripcaster
Environment=NTRIP_CONFIG_FILE=/etc/ntripcaster/config.ini
Environment=PYTHONPATH=/opt/ntripcaster
ExecStart=/opt/ntripcaster/venv/bin/python /opt/ntripcaster/main.py
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10
KillMode=mixed
TimeoutStopSec=30

# Настройки безопасности
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/ntripcaster/data /var/log/ntripcaster /etc/ntripcaster

# Ограничения ресурсов
LimitNOFILE=65536
LimitNPROC=4096

[Install]
WantedBy=multi-user.target
EOF

# Перезагрузка конфигурации systemd
sudo systemctl daemon-reload
```

### 7. Настройка файрвола

#### UFW (Ubuntu/Debian)

```bash
# Включение UFW
sudo ufw enable

# Открытие необходимых портов
sudo ufw allow 2101/tcp comment 'NTRIP Service'
sudo ufw allow 5757/tcp comment 'NTRIP Web Interface'
sudo ufw allow ssh

# Просмотр статуса
sudo ufw status
```

#### firewalld (CentOS/RHEL)

```bash
# Запуск firewalld
sudo systemctl start firewalld
sudo systemctl enable firewalld

# Открытие портов
sudo firewall-cmd --permanent --add-port=2101/tcp
sudo firewall-cmd --permanent --add-port=5757/tcp
sudo firewall-cmd --reload

# Просмотр статуса
sudo firewall-cmd --list-all
```

#### iptables (универсально)

```bash
# Открытие портов
sudo iptables -A INPUT -p tcp --dport 2101 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 5757 -j ACCEPT

# Сохранение правил (Debian/Ubuntu)
sudo iptables-save > /etc/iptables/rules.v4

# Сохранение правил (CentOS/RHEL)
sudo service iptables save
```

## Описание конфигурации

### Переменные окружения

Можно переопределить настройки конфигурационного файла через переменные окружения:

```bash
# Добавить в /etc/systemd/system/ntripcaster.service
Environment=NTRIP_PORT=2101
Environment=WEB_PORT=5757
Environment=DEBUG_MODE=false
Environment=DATABASE_PATH=/opt/ntripcaster/data/2rtk.db
Environment=LOG_LEVEL=INFO
```

### Конфигурация логирования

```bash
# Настройка logrotate
sudo tee /etc/logrotate.d/ntripcaster > /dev/null <<EOF
/var/log/ntripcaster/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 ntripcaster ntripcaster
    postrotate
        systemctl reload ntripcaster
    endscript
}
EOF
```

## Управление службой

### Основные операции

```bash
# Запуск службы
sudo systemctl start ntripcaster

# Остановка службы
sudo systemctl stop ntripcaster

# Перезапуск службы
sudo systemctl restart ntripcaster

# Перезагрузка конфигурации
sudo systemctl reload ntripcaster

# Просмотр статуса службы
sudo systemctl status ntripcaster

# Включение автозапуска при загрузке
sudo systemctl enable ntripcaster

# Отключение автозапуска при загрузке
sudo systemctl disable ntripcaster
```

### Просмотр логов

```bash
# Просмотр логов службы
sudo journalctl -u ntripcaster

# Просмотр логов в реальном времени
sudo journalctl -u ntripcaster -f

# Просмотр логов приложения
sudo tail -f /var/log/ntripcaster/main.log

# Просмотр логов ошибок
sudo grep ERROR /var/log/ntripcaster/main.log
```

### Мониторинг службы

```bash
# Проверка, запущена ли служба
sudo systemctl is-active ntripcaster

# Проверка прослушивания портов
sudo netstat -tlnp | grep -E ':(2101|5757)'
# или использовать ss
sudo ss -tlnp | grep -E ':(2101|5757)'

# Проверка процессов
sudo ps aux | grep ntripcaster
```

## Часто задаваемые вопросы

### Q1: Служба не запускается

**Шаги диагностики:**

```bash
# Просмотр подробной информации об ошибке
sudo journalctl -u ntripcaster -n 50

# Проверка синтаксиса конфигурационного файла
sudo -u ntripcaster bash -c '
    cd /opt/ntripcaster
    source venv/bin/activate
    python -c "import configparser; c=configparser.ConfigParser(); c.read("/etc/ntripcaster/config.ini")"
'

# Проверка прав доступа к файлам
sudo ls -la /opt/ntripcaster/
sudo ls -la /etc/ntripcaster/
sudo ls -la /var/log/ntripcaster/

# Ручной тестовый запуск
sudo -u ntripcaster bash -c '
    cd /opt/ntripcaster
    source venv/bin/activate
    NTRIP_CONFIG_FILE=/etc/ntripcaster/config.ini python main.py
'
```

### Q2: Порт занят

```bash
# Просмотр использования порта
sudo lsof -i :2101
sudo lsof -i :5757

# Убить процесс, занимающий порт
sudo kill -9 <PID>

# Или изменить порт в конфигурационном файле
sudo nano /etc/ntripcaster/config.ini
```

### Q3: Проблемы с правами доступа

```bash
# Повторная установка прав доступа
sudo chown -R ntripcaster:ntripcaster /opt/ntripcaster
sudo chown -R ntripcaster:ntripcaster /var/log/ntripcaster
sudo chown -R ntripcaster:ntripcaster /etc/ntripcaster

# Проверка SELinux (CentOS/RHEL)
sudo getenforce
sudo setsebool -P httpd_can_network_connect 1
```

### Q4: Проблемы с зависимостями Python

```bash
# Переустановка зависимостей
sudo -u ntripcaster bash -c '
    cd /opt/ntripcaster
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt --force-reinstall
'

# Проверка версии Python
python3 --version

# Если версия Python слишком старая, установить новую версию
# Ubuntu/Debian
sudo apt install software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev
```

### Q5: Проблемы с базой данных

```bash
# Проверка файла базы данных
sudo ls -la /opt/ntripcaster/data/

# Повторная инициализация базы данных
sudo -u ntripcaster bash -c '
    cd /opt/ntripcaster
    source venv/bin/activate
    rm -f data/2rtk.db
    python -c "from src.database import init_db; init_db()"
'

# Проверка целостности базы данных
sudo -u ntripcaster sqlite3 /opt/ntripcaster/data/2rtk.db "PRAGMA integrity_check;"
```

## Оптимизация производительности

### 1. Оптимизация системы

```bash
# Оптимизация ограничений файловых дескрипторов
sudo tee -a /etc/security/limits.conf > /dev/null <<EOF
ntripcaster soft nofile 65536
ntripcaster hard nofile 65536
ntripcaster soft nproc 4096
ntripcaster hard nproc 4096
EOF

# Оптимизация сетевых параметров
sudo tee -a /etc/sysctl.conf > /dev/null <<EOF
# Сетевая оптимизация NTRIP Caster
net.core.somaxconn = 1024
net.core.netdev_max_backlog = 5000
net.ipv4.tcp_max_syn_backlog = 1024
net.ipv4.tcp_keepalive_time = 600
net.ipv4.tcp_keepalive_intvl = 60
net.ipv4.tcp_keepalive_probes = 3
EOF

# Применение системных параметров
sudo sysctl -p
```

### 2. Оптимизация приложения

Редактирование конфигурационного файла `/etc/ntripcaster/config.ini`:

```ini
[performance]
# Размер пула потоков
thread_pool_size = 10

# Максимальное количество рабочих потоков
max_workers = 20

# Размер очереди подключений
connection_queue_size = 100

# Максимальное использование памяти (MB)
max_memory_usage = 512

# Порог предупреждения использования CPU (%)
cpu_warning_threshold = 80

# Порог предупреждения использования памяти (%)
memory_warning_threshold = 85

[network]
# Максимальное количество подключений
max_connections = 1000

# Размер буфера
buffer_size = 8192

[tcp]
# Настройки TCP Keep-Alive
keepalive_enable = true
keepalive_idle = 600
keepalive_interval = 60
keepalive_count = 3

# Таймаут Socket
socket_timeout = 30
connection_timeout = 10
```

### 3. Скрипт мониторинга

Создание скрипта мониторинга `/opt/ntripcaster/monitor.sh`:

```bash
#!/bin/bash

# Скрипт мониторинга NTRIP Caster

LOG_FILE="/var/log/ntripcaster/monitor.log"
PID_FILE="/var/run/ntripcaster.pid"

# Проверка статуса службы
check_service() {
    if ! systemctl is-active --quiet ntripcaster; then
        echo "$(date): Служба NTRIP Caster не запущена, попытка перезапуска..." >> $LOG_FILE
        systemctl start ntripcaster
        sleep 5
        if systemctl is-active --quiet ntripcaster; then
            echo "$(date): Служба NTRIP Caster успешно перезапущена" >> $LOG_FILE
        else
            echo "$(date): Не удалось перезапустить службу NTRIP Caster" >> $LOG_FILE
        fi
    fi
}

# Проверка портов
check_ports() {
    if ! netstat -tlnp | grep -q ":2101"; then
        echo "$(date): Порт NTRIP 2101 не прослушивается" >> $LOG_FILE
    fi
    
    if ! netstat -tlnp | grep -q ":5757"; then
        echo "$(date): Веб-порт 5757 не прослушивается" >> $LOG_FILE
    fi
}

# Проверка использования памяти
check_memory() {
    MEMORY_USAGE=$(ps -o pid,ppid,cmd,%mem --sort=-%mem -C python3 | grep ntripcaster | awk '{print $4}' | head -1)
    if [ ! -z "$MEMORY_USAGE" ] && (( $(echo "$MEMORY_USAGE > 80" | bc -l) )); then
        echo "$(date): Обнаружено высокое использование памяти: ${MEMORY_USAGE}%" >> $LOG_FILE
    fi
}

# Выполнение проверок
check_service
check_ports
check_memory

echo "$(date): Проверка мониторинга завершена" >> $LOG_FILE
```

Настройка задания cron:

```bash
# Установка права на выполнение
sudo chmod +x /opt/ntripcaster/monitor.sh

# Добавление в crontab
sudo crontab -e
# Добавить следующую строку (проверка каждые 5 минут)
*/5 * * * * /opt/ntripcaster/monitor.sh
```

## Настройка безопасности

### 1. Конфигурация SSL/TLS

#### Генерация самоподписанного сертификата

```bash
# Создание каталога сертификатов
sudo mkdir -p /etc/ntripcaster/ssl

# Генерация закрытого ключа
sudo openssl genrsa -out /etc/ntripcaster/ssl/server.key 2048

# Генерация запроса на подпись сертификата
sudo openssl req -new -key /etc/ntripcaster/ssl/server.key -out /etc/ntripcaster/ssl/server.csr

# Генерация самоподписанного сертификата
sudo openssl x509 -req -days 365 -in /etc/ntripcaster/ssl/server.csr -signkey /etc/ntripcaster/ssl/server.key -out /etc/ntripcaster/ssl/server.crt

# Установка прав доступа
sudo chown -R ntripcaster:ntripcaster /etc/ntripcaster/ssl
sudo chmod 600 /etc/ntripcaster/ssl/server.key
sudo chmod 644 /etc/ntripcaster/ssl/server.crt
```

#### Настройка обратного прокси Nginx

```bash
# Создание конфигурации Nginx
sudo tee /etc/nginx/sites-available/ntripcaster > /dev/null <<EOF
server {
    listen 80;
    listen 443 ssl http2;
    server_name your-domain.com;

    # Конфигурация SSL
    ssl_certificate /etc/ntripcaster/ssl/server.crt;
    ssl_certificate_key /etc/ntripcaster/ssl/server.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Перенаправление HTTP на HTTPS
    if (\$scheme != "https") {
        return 301 https://\$host\$request_uri;
    }

    # Прокси веб-интерфейса
    location / {
        proxy_pass http://127.0.0.1:5757;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Прокси службы NTRIP
    location /ntrip {
        proxy_pass http://127.0.0.1:2101;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF

# Включение сайта
sudo ln -s /etc/nginx/sites-available/ntripcaster /etc/nginx/sites-enabled/

# Проверка конфигурации
sudo nginx -t

# Перезапуск Nginx
sudo systemctl restart nginx
```

### 2. Контроль доступа

```bash
# Настройка fail2ban
sudo apt install fail2ban  # Debian/Ubuntu
sudo yum install fail2ban  # CentOS/RHEL

# Создание конфигурации fail2ban
sudo tee /etc/fail2ban/jail.d/ntripcaster.conf > /dev/null <<EOF
[ntripcaster]
enabled = true
port = 2101,5757
filter = ntripcaster
logpath = /var/log/ntripcaster/main.log
maxretry = 5
bantime = 3600
findtime = 600
EOF

# Создание правил фильтрации
sudo tee /etc/fail2ban/filter.d/ntripcaster.conf > /dev/null <<EOF
[Definition]
failregex = ^.*Authentication failed.*from <HOST>.*$
            ^.*Invalid credentials.*from <HOST>.*$
            ^.*Connection refused.*from <HOST>.*$
ignoreregex =
EOF

# Перезапуск fail2ban
sudo systemctl restart fail2ban
```

### 3. Регулярное резервное копирование

Создание скрипта резервного копирования `/opt/ntripcaster/backup.sh`:

```bash
#!/bin/bash

# Скрипт резервного копирования NTRIP Caster

BACKUP_DIR="/opt/backups/ntripcaster"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="ntripcaster_backup_$DATE.tar.gz"

# Создание каталога резервных копий
mkdir -p $BACKUP_DIR

# Остановка службы
systemctl stop ntripcaster

# Создание резервной копии
tar -czf $BACKUP_DIR/$BACKUP_FILE \
    /opt/ntripcaster \
    /etc/ntripcaster \
    /var/log/ntripcaster

# Запуск службы
systemctl start ntripcaster

# Удаление резервных копий старше 30 дней
find $BACKUP_DIR -name "ntripcaster_backup_*.tar.gz" -mtime +30 -delete

echo "Резервное копирование завершено: $BACKUP_DIR/$BACKUP_FILE"
```

Настройка регулярного резервного копирования:

```bash
# Установка права на выполнение
sudo chmod +x /opt/ntripcaster/backup.sh

# Добавление в crontab (резервное копирование каждый день в 2:00 ночи)
sudo crontab -e
# Добавить следующую строку
0 2 * * * /opt/ntripcaster/backup.sh
```

## Удаление

Если требуется полностью удалить NTRIP Caster:

```bash
# Остановка и отключение службы
sudo systemctl stop ntripcaster
sudo systemctl disable ntripcaster

# Удаление файла службы
sudo rm /etc/systemd/system/ntripcaster.service
sudo systemctl daemon-reload

# Удаление файлов приложения
sudo rm -rf /opt/ntripcaster
sudo rm -rf /etc/ntripcaster
sudo rm -rf /var/log/ntripcaster

# Удаление пользователя
sudo userdel ntripcaster

# Удаление конфигурации Nginx (если была настроена)
sudo rm /etc/nginx/sites-enabled/ntripcaster
sudo rm /etc/nginx/sites-available/ntripcaster
sudo systemctl restart nginx

# Удаление правил файрвола
sudo ufw delete allow 2101/tcp
sudo ufw delete allow 5757/tcp
```

## Техническая поддержка

Если при установке или использовании возникли проблемы, можно:

1. **Просмотр логов**: `sudo journalctl -u ntripcaster -f`
2. **Проверка статуса**: `sudo systemctl status ntripcaster`
3. **Просмотр документации**: [Репозиторий GitHub](https://github.com/srgizh/NTRIPcaster)
4. **Сообщить о проблеме**: [Проблемы GitHub](https://github.com/srgizh/NTRIPcaster/issues)
5. **Связаться с автором**: i@jia.by
6. **Посетить официальный сайт**: https://2rtk.com

## История обновлений

- **v2.2.0**: Последняя версия, поддержка большего количества дистрибутивов Linux
- **v2.1.8**: Оптимизация производительности и улучшение безопасности
- **v2.1.7**: Добавление функций мониторинга и логирования

---

**Информация о версии:** NTRIP Caster v2.2.0  
**Дата обновления:** Декабрь 2024  
**Автор:** Команда 2RTK  
**Лицензия:** Apache 2.0