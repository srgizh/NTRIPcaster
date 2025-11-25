#!/bin/bash
#
# Скрипт автоматической деинсталляции NTRIP Caster
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
  echo -e "${RED}Ошибка: запустите скрипт с правами root (sudo ./uninstall.sh)${NC}"
  exit 1
fi

# Отображение приветственного сообщения
echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}       Скрипт автоматической деинсталляции       ${NC}"
echo -e "${BLUE}           2RTK NTRIP Caster                     ${NC}"
echo -e "${BLUE}=================================================${NC}"
echo -e "${RED}Внимание: этот скрипт полностью удалит 2RTK NTRIP Caster и все данные${NC}"
echo ""

# Подтверждение деинсталляции
read -p "Вы уверены, что хотите удалить 2RTK NTRIP Caster? (y/n): " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
  echo -e "${GREEN}Деинсталляция отменена${NC}"
  exit 0
fi

# Установка путей установки (таких же, как в скрипте установки)
INSTALL_DIR="/opt/2rtk"
CONFIG_DIR="/etc/2rtk"
LOG_DIR="/var/log/2rtk"
SERVICE_NAME="2rtk"

# Остановка и отключение службы
echo -e "${YELLOW}Остановка и отключение службы...${NC}"
systemctl stop $SERVICE_NAME
systemctl disable $SERVICE_NAME
systemctl daemon-reload

# Удаление файла службы systemd
echo -e "${YELLOW}Удаление файла службы systemd...${NC}"
rm -f /etc/systemd/system/$SERVICE_NAME.service

# Удаление конфигурации Nginx
echo -e "${YELLOW}Удаление конфигурации Nginx...${NC}"
rm -f /etc/nginx/sites-enabled/2rtk
rm -f /etc/nginx/sites-available/2rtk
systemctl restart nginx

# Удаление конфигурации ротации логов
echo -e "${YELLOW}Удаление конфигурации ротации логов...${NC}"
rm -f /etc/logrotate.d/2rtk

# Удаление правил файрвола (если существуют)
echo -e "${YELLOW}Удаление правил файрвола...${NC}"
if command -v ufw > /dev/null; then
    ufw delete allow 2101/tcp
    ufw delete allow 5757/tcp
    echo -e "${GREEN}Правила файрвола UFW удалены${NC}"
elif command -v firewall-cmd > /dev/null; then
    firewall-cmd --permanent --remove-port=2101/tcp
    firewall-cmd --permanent --remove-port=5757/tcp
    firewall-cmd --reload
    echo -e "${GREEN}Правила файрвола firewalld удалены${NC}"
else
    echo -e "${YELLOW}Поддерживаемый файрвол не обнаружен, удалите правила файрвола вручную${NC}"
fi

# Резервное копирование данных (опционально)
echo -e "${YELLOW}Нужно ли создать резервную копию данных? (y/n): ${NC}"
read backup_choice
if [[ "$backup_choice" == "y" || "$backup_choice" == "Y" ]]; then
    BACKUP_DIR="/root/2rtk_backup_$(date +%Y%m%d_%H%M%S)"
    echo -e "${YELLOW}Создание директории резервного копирования: $BACKUP_DIR${NC}"
    mkdir -p $BACKUP_DIR
    
    # Резервное копирование конфигурационных файлов
    if [ -d "$CONFIG_DIR" ]; then
        cp -r $CONFIG_DIR $BACKUP_DIR/
        echo -e "${GREEN}Конфигурационные файлы скопированы в $BACKUP_DIR/$(basename $CONFIG_DIR)${NC}"
    fi
    
    # Резервное копирование базы данных
    if [ -f "$INSTALL_DIR/2rtk.db" ]; then
        cp $INSTALL_DIR/2rtk.db $BACKUP_DIR/
        echo -e "${GREEN}База данных скопирована в $BACKUP_DIR/2rtk.db${NC}"
    fi
    
    # Резервное копирование логов
    if [ -d "$LOG_DIR" ]; then
        cp -r $LOG_DIR $BACKUP_DIR/
        echo -e "${GREEN}Файлы логов скопированы в $BACKUP_DIR/$(basename $LOG_DIR)${NC}"
    fi
    
    echo -e "${GREEN}Резервное копирование данных завершено: $BACKUP_DIR${NC}"
fi

# Удаление директории установки
echo -e "${YELLOW}Удаление директории установки...${NC}"
rm -rf $INSTALL_DIR

# Удаление директории конфигурации
echo -e "${YELLOW}Удаление директории конфигурации...${NC}"
rm -rf $CONFIG_DIR

# Удаление директории логов
echo -e "${YELLOW}Удаление директории логов...${NC}"
rm -rf $LOG_DIR

# Запрос об удалении зависимостей
echo -e "${YELLOW}Удалить установленные зависимости? (y/n): ${NC}"
read deps_choice
if [[ "$deps_choice" == "y" || "$deps_choice" == "Y" ]]; then
    echo -e "${YELLOW}Удаление зависимостей...${NC}"
    # Примечание: здесь удаляются только явно установленные скриптом пакеты, без их зависимостей
    apt-get remove -y supervisor nginx
    echo -e "${GREEN}Зависимости удалены${NC}"
else
    echo -e "${YELLOW}Зависимости сохранены${NC}"
fi

# Отображение информации о завершении деинсталляции
echo -e "${BLUE}=================================================${NC}"
echo -e "${GREEN}Деинсталляция 2RTK NTRIP Caster завершена!${NC}"
echo -e "${BLUE}------------------------------------------------${NC}"
echo -e "${YELLOW}Удалено следующее:${NC}"
echo -e "  - Файл службы: /etc/systemd/system/$SERVICE_NAME.service"
echo -e "  - Директория установки: $INSTALL_DIR"
echo -e "  - Директория конфигурации: $CONFIG_DIR"
echo -e "  - Директория логов: $LOG_DIR"
echo -e "  - Конфигурация Nginx: /etc/nginx/sites-available/2rtk"
echo -e "  - Конфигурация ротации логов: /etc/logrotate.d/2rtk"

if [[ "$backup_choice" == "y" || "$backup_choice" == "Y" ]]; then
    echo -e "${BLUE}------------------------------------------------${NC}"
    echo -e "${GREEN}Резервная копия данных создана в: $BACKUP_DIR${NC}"
fi

echo -e "${BLUE}=================================================${NC}"

exit 0
