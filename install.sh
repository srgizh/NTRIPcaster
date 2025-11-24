#!/bin/bash
#
# NTRIP Caster скрипт установки
# Для систем Debian/Ubuntu
# Автор: 2RTK
# Версия: 1.0.0
#

# Определение цветов
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Проверка запуска от root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Ошибка: Запустите скрипт с правами root (sudo ./install.sh)${NC}"
  exit 1
fi

# Приветственное сообщение
echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}       2RTK NTRIP Caster скрипт установки         ${NC}"
echo -e "${BLUE}=================================================${NC}"
echo -e "${GREEN}Этот скрипт автоматически установит 2RTK NTRIP Caster и зависимости, и настроит автозапуск${NC}"
echo ""

# Проверка типа системы
if [ -f /etc/debian_version ]; then
    echo -e "${GREEN}Обнаружена система Debian/Ubuntu, продолжаем установку...${NC}"
else
    echo -e "${RED}Ошибка: Этот скрипт поддерживает только системы Debian/Ubuntu${NC}"
    exit 1
fi

# Настройка директорий установки
INSTALL_DIR="/opt/2rtk"
CONFIG_DIR="/etc/2rtk"
LOG_DIR="/var/log/2rtk"
SERVICE_NAME="2rtk"

# Создание директорий установки
echo -e "${YELLOW}Создание директорий установки...${NC}"
mkdir -p $INSTALL_DIR
mkdir -p $CONFIG_DIR
mkdir -p $LOG_DIR

# Создание поддиректорий для логов
echo -e "${YELLOW}Создание директорий для логов...${NC}"


# Обновление системы и установка зависимостей
echo -e "${YELLOW}Обновление системы и установка зависимостей...${NC}"
apt-get update
apt-get install -y python3 python3-pip python3-venv supervisor nginx git

# Создание Python виртуального окружения
echo -e "${YELLOW}Создание Python виртуального окружения...${NC}"
python3 -m venv $INSTALL_DIR/venv
source $INSTALL_DIR/venv/bin/activate

# Загрузка файлов проекта
echo -e "${YELLOW}Загрузка файлов проекта...${NC}"
cd /tmp
git clone https://github.com/srgizh/NTRIPcaster.git
cp -r NTRIPcaster/* $INSTALL_DIR/

# Копирование и настройка config.ini
echo -e "${YELLOW}Настройка config.ini...${NC}"
if [ -f $INSTALL_DIR/config.ini.example ]; then
    # Резервное копирование оригинального файла конфигурации
    cp $INSTALL_DIR/config.ini.example $CONFIG_DIR/config.ini.original
    
    # Копирование и изменение файла конфигурации
    cp $INSTALL_DIR/config.ini.example $CONFIG_DIR/config.ini
    
    # Обновление путей в файле конфигурации
    sed -i "s|path = /app/data/2rtk.db|path = $INSTALL_DIR/data/2rtk.db|g" $CONFIG_DIR/config.ini
    sed -i "s|main_log = /app/logs/main.log|main_log = $LOG_DIR/main.log|g" $CONFIG_DIR/config.ini
    sed -i "s|ntrip_log = /app/logs/ntrip.log|ntrip_log = $LOG_DIR/ntrip.log|g" $CONFIG_DIR/config.ini
    sed -i "s|error_log = /app/logs/errors.log|error_log = $LOG_DIR/errors.log|g" $CONFIG_DIR/config.ini
    
    # Настройка конфигурации для продакшена
    sed -i "s|debug = true|debug = false|g" $CONFIG_DIR/config.ini
    
    # Генерация случайного ключа
    RANDOM_KEY=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 32 | head -n 1)
    sed -i "s|secret_key = your-secret-key-change-this-in-production|secret_key = $RANDOM_KEY|g" $CONFIG_DIR/config.ini
    
    echo -e "${GREEN}Файл конфигурации обновлен${NC}"
else
    echo -e "${RED}Ошибка: Файл config.ini.example не найден${NC}"
    exit 1
fi

# Установка Python зависимостей
echo -e "${YELLOW}Установка Python зависимостей...${NC}"
$INSTALL_DIR/venv/bin/pip install --upgrade pip
$INSTALL_DIR/venv/bin/pip install -r $INSTALL_DIR/requirements.txt

# Создание файла службы systemd
echo -e "${YELLOW}Создание файла службы systemd...${NC}"
cat > /etc/systemd/system/$SERVICE_NAME.service << EOF
[Unit]
Description=NTRIP Caster Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin"
Environment="NTRIP_CONFIG_FILE=$CONFIG_DIR/config.ini"
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/main.py
Restart=always
RestartSec=5
StandardOutput=append:$LOG_DIR/main.log
StandardError=append:$LOG_DIR/errors.log

[Install]
WantedBy=multi-user.target
EOF

# Создание конфигурации ротации логов
echo -e "${YELLOW}Создание конфигурации ротации логов...${NC}"
cat > /etc/logrotate.d/2rtk << EOF
$LOG_DIR/main.log $LOG_DIR/ntrip.log $LOG_DIR/errors.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 root root
    sharedscripts
    postrotate
        systemctl reload 2rtk.service > /dev/null 2>&1 || true
    endscript
}
EOF

# Установка прав доступа к файлам
echo -e "${YELLOW}Установка прав доступа к файлам...${NC}"
chmod +x $INSTALL_DIR/main.py
chown -R root:root $INSTALL_DIR
chown -R root:root $CONFIG_DIR
chown -R root:root $LOG_DIR

# Установка прав доступа к директориям логов
echo -e "${YELLOW}Установка прав доступа к директориям логов...${NC}"
chmod -R 755 $LOG_DIR
find $LOG_DIR -type d -exec chmod 755 {} \;
find $LOG_DIR -type f -exec chmod 644 {} \;

# Создание директории для базы данных
echo -e "${YELLOW}Создание директории для базы данных...${NC}"
mkdir -p $INSTALL_DIR/data
chmod 755 $INSTALL_DIR/data

# Создание символической ссылки для удобного доступа к файлу конфигурации
ln -sf $CONFIG_DIR/config.ini $INSTALL_DIR/config.ini

# Включение и запуск службы
echo -e "${YELLOW}Включение и запуск службы...${NC}"
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl start $SERVICE_NAME

# Настройка файрвола (если установлен)
echo -e "${YELLOW}Настройка файрвола...${NC}"
if command -v ufw > /dev/null; then
    ufw allow 2101/tcp  # NTRIP порт
    ufw allow 5757/tcp  # Web интерфейс управления порт
    echo -e "${GREEN}Настроены правила файрвола UFW${NC}"
elif command -v firewall-cmd > /dev/null; then
    firewall-cmd --permanent --add-port=2101/tcp
    firewall-cmd --permanent --add-port=5757/tcp
    firewall-cmd --reload
    echo -e "${GREEN}Настроены правила файрвола firewalld${NC}"
else
    echo -e "${YELLOW}Поддерживаемый файрвол не обнаружен, настройте правила файрвола вручную${NC}"
fi

# Создание конфигурации Nginx (опционально, для обратного проксирования Web интерфейса управления)
echo -e "${YELLOW}Создание конфигурации Nginx...${NC}"
cat > /etc/nginx/sites-available/2rtk << EOF
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5757;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF

# Включение конфигурации Nginx
ln -sf /etc/nginx/sites-available/2rtk /etc/nginx/sites-enabled/
systemctl restart nginx

# Проверка состояния службы
echo -e "${YELLOW}Проверка состояния службы...${NC}"
sleep 3
if systemctl is-active --quiet $SERVICE_NAME; then
    echo -e "${GREEN}Служба NTRIP Caster успешно запущена!${NC}"
else
    echo -e "${RED}Служба NTRIP Caster не запустилась, проверьте логи: $LOG_DIR/errors.log${NC}"
fi

# Отображение информации об установке
echo -e "${BLUE}=================================================${NC}"
echo -e "${GREEN}2RTK NTRIP Caster установка завершена!${NC}"
echo -e "${BLUE}------------------------------------------------${NC}"
echo -e "${YELLOW}Директория установки:${NC} $INSTALL_DIR"
echo -e "${YELLOW}Директория конфигурации:${NC} $CONFIG_DIR"
echo -e "${YELLOW}Директория логов:${NC} $LOG_DIR"
echo -e "${YELLOW}NTRIP порт:${NC} 2101"
echo -e "${YELLOW}Web интерфейс управления:${NC} http://IP_СЕРВЕРА:5757"
echo -e "${YELLOW}Nginx прокси:${NC} http://IP_СЕРВЕРА"
echo -e "${BLUE}------------------------------------------------${NC}"
echo -e "${YELLOW}Команды управления службой:${NC}"
echo -e "  Запуск службы: ${GREEN}systemctl start $SERVICE_NAME${NC}"
echo -e "  Остановка службы: ${GREEN}systemctl stop $SERVICE_NAME${NC}"
echo -e "  Перезапуск службы: ${GREEN}systemctl restart $SERVICE_NAME${NC}"
echo -e "  Просмотр состояния: ${GREEN}systemctl status $SERVICE_NAME${NC}"
echo -e "  Просмотр логов: ${GREEN}journalctl -u $SERVICE_NAME${NC}"
echo -e "${BLUE}=================================================${NC}"

# Предупреждение об изменении пароля по умолчанию
echo -e "${RED}Важно для безопасности: Немедленно измените пароль администратора по умолчанию!${NC}"
echo -e "Имя пользователя администратора по умолчанию: admin"
echo -e "Пароль администратора по умолчанию: admin123"

exit 0