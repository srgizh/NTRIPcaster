@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM Скрипт развёртывания NTRIP Caster через Docker (версия Batch)
REM Используется для управления контейнерами Docker NTRIP Caster в среде Windows

REM Конфигурация проекта
set "PROJECT_NAME=ntrip-caster"
set "SCRIPT_DIR=%~dp0"
set "ENV_FILE=%SCRIPT_DIR%.env"

REM Определение цветов (Windows 10+ поддерживает ANSI цвета)
set "RED=[31m"
set "GREEN=[32m"
set "YELLOW=[33m"
set "BLUE=[34m"
set "PURPLE=[35m"
set "CYAN=[36m"
set "NC=[0m"

REM Включение поддержки ANSI цветов
reg add HKCU\Console /v VirtualTerminalLevel /t REG_DWORD /d 1 /f >nul 2>&1

REM Получение параметров команды
set "COMMAND=%1"
if "%COMMAND%"=="" set "COMMAND=help"

REM Функции логирования
:log_info
echo %BLUE%[INFO]%NC% %~1
goto :eof

:log_success
echo %GREEN%[SUCCESS]%NC% %~1
goto :eof

:log_warning
echo %YELLOW%[WARNING]%NC% %~1
goto :eof

:log_error
echo %RED%[ERROR]%NC% %~1
goto :eof

:log_step
echo %PURPLE%[STEP]%NC% %~1
goto :eof

REM Отображение баннера
:show_banner
echo %CYAN%
echo ╔══════════════════════════════════════════════════════════════╗
echo ║              Скрипт развёртывания NTRIP Caster               ║
echo ║                    Версия Batch                              ║
echo ╚══════════════════════════════════════════════════════════════╝
echo %NC%
goto :eof

REM Проверка окружения Docker
:check_docker
call :log_step "Проверка окружения Docker..."

REM Проверка Docker
docker --version >nul 2>&1
if errorlevel 1 (
    call :log_error "Docker не установлен, сначала установите Docker Desktop"
    echo Адрес загрузки: https://www.docker.com/products/docker-desktop
    exit /b 1
)

REM Проверка Docker Compose
docker compose version >nul 2>&1
if errorlevel 1 (
    docker-compose --version >nul 2>&1
    if errorlevel 1 (
        call :log_error "Docker Compose не установлен"
        exit /b 1
    ) else (
        set "DOCKER_COMPOSE_CMD=docker-compose"
    )
) else (
    set "DOCKER_COMPOSE_CMD=docker compose"
)

REM Проверка состояния службы Docker
docker info >nul 2>&1
if errorlevel 1 (
    call :log_error "Служба Docker не запущена, запустите Docker Desktop"
    exit /b 1
)

call :log_success "Проверка окружения Docker завершена"
goto :eof

REM Загрузка переменных окружения
:load_env
if exist "%ENV_FILE%" (
    for /f "usebackq tokens=1,2 delims==" %%a in ("%ENV_FILE%") do (
        if not "%%a"=="" if not "%%a:~0,1"=="#" (
            set "%%a=%%b"
        )
    )
    call :log_info "Переменные окружения загружены"
) else (
    call :log_warning "Файл .env не существует, используется конфигурация по умолчанию"
)
goto :eof

REM Построение команды Docker Compose
:build_compose_cmd
if "%ENVIRONMENT%"=="" set "ENVIRONMENT=development"
if "%PROFILES%"=="" set "PROFILES=dev"

set "COMPOSE_FILES=-f docker-compose.yml"

if "%ENVIRONMENT%"=="production" (
    set "COMPOSE_FILES=%COMPOSE_FILES% -f docker-compose.prod.yml"
) else (
    set "COMPOSE_FILES=%COMPOSE_FILES% -f docker-compose.override.yml"
)

set "PROFILE_ARGS="
for %%p in (%PROFILES:,= %) do (
    set "PROFILE_ARGS=!PROFILE_ARGS! --profile %%p"
)

set "FULL_COMPOSE_CMD=%DOCKER_COMPOSE_CMD% %COMPOSE_FILES% %PROFILE_ARGS%"
goto :eof

REM Выполнение команды Docker Compose
:run_compose
call :build_compose_cmd
set "FULL_CMD=%FULL_COMPOSE_CMD% %*"
call :log_info "Выполнение команды: %FULL_CMD%"
%FULL_CMD%
goto :eof

REM Создание необходимых директорий
:create_directories
call :log_step "Создание необходимых директорий..."

set "DIRS=data logs secrets nginx\logs redis monitoring\prometheus\rules monitoring\grafana\provisioning\datasources monitoring\grafana\provisioning\dashboards monitoring\grafana\dashboards backup"

for %%d in (%DIRS%) do (
    if not exist "%%d" (
        mkdir "%%d" 2>nul
        call :log_info "Создана директория: %%d"
    )
)

call :log_success "Создание директорий завершено"
goto :eof

REM Проверка здоровья
:health_check
call :log_step "Выполнение проверки здоровья..."

if exist "healthcheck.py" (
    python healthcheck.py
) else (
    call :log_warning "Скрипт проверки здоровья не существует, пропуск проверки"
)
goto :eof

REM Отображение информации о службах
:show_info
call :log_step "Информация о службах:"

REM Получение IP-адреса локального хоста
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    for /f "tokens=1" %%b in ("%%a") do (
        set "LOCAL_IP=%%b"
        goto :ip_found
    )
)
set "LOCAL_IP=localhost"

:ip_found
echo.
echo 📡 Служба NTRIP Caster:
echo    - NTRIP порт: ntrip://%LOCAL_IP%:2101
echo    - Веб-интерфейс управления: http://%LOCAL_IP%:5757

echo %PROFILES% | findstr /c:"monitoring" >nul
if not errorlevel 1 (
    echo.
    echo 📊 Службы мониторинга:
    echo    - Prometheus: http://%LOCAL_IP%:9090
    echo    - Grafana: http://%LOCAL_IP%:3000 ^(admin/admin123^)
)

if "%ENVIRONMENT%"=="development" (
    echo.
    echo 🛠️ Инструменты разработки:
    echo    - Adminer ^(управление БД^): http://%LOCAL_IP%:8081
    echo    - Dozzle ^(просмотр логов^): http://%LOCAL_IP%:8082
    echo    - cAdvisor ^(мониторинг контейнеров^): http://%LOCAL_IP%:8083
)

echo.
goto :eof

REM Отображение справки
:show_help
echo.
echo Скрипт развёртывания NTRIP Caster через Docker ^(версия Batch^)
echo.
echo Использование: docker-deploy.bat ^<команда^> [опции]
echo.
echo Основные команды:
echo   up              Запустить службы
echo   down            Остановить службы
echo   restart         Перезапустить службы
echo   status          Просмотреть состояние служб
echo   logs            Просмотреть логи служб
echo   build           Собрать образ
echo   pull            Загрузить образ
echo   clean           Очистить ресурсы
echo.
echo Команды управления:
echo   health          Проверка здоровья
echo   info            Отобразить информацию о службах
echo   backup          Резервное копирование данных
echo   create_dirs     Создать необходимые директории
echo.
echo Переменные окружения:
echo   ENVIRONMENT     Окружение развёртывания ^(development^|production^)
echo   PROFILES        Профили конфигурации служб ^(dev^|prod^|monitoring^|full^)
echo.
echo Примеры:
echo   docker-deploy.bat up -d
echo   set ENVIRONMENT=production ^&^& docker-deploy.bat up
echo   set PROFILES=monitoring ^&^& docker-deploy.bat restart
echo.
goto :eof

REM Главная функция
:main
call :show_banner

REM Проверка, что скрипт запущен в правильной директории
if not exist "docker-compose.yml" (
    call :log_error "Запустите этот скрипт в корневой директории проекта NTRIP Caster"
    pause
    exit /b 1
)

REM Проверка окружения Docker
call :check_docker
if errorlevel 1 exit /b 1

REM Загрузка переменных окружения
call :load_env

REM Выполнение команды
if "%COMMAND%"=="help" goto :show_help
if "%COMMAND%"=="check" (
    call :log_success "Проверка окружения Docker завершена"
    goto :end
)
if "%COMMAND%"=="create_dirs" (
    call :create_directories
    goto :end
)
if "%COMMAND%"=="up" (
    call :log_step "Запуск служб..."
    call :run_compose up %2 %3 %4 %5 %6 %7 %8 %9
    if not errorlevel 1 (
        timeout /t 5 /nobreak >nul
        call :health_check
        call :show_info
    )
    goto :end
)
if "%COMMAND%"=="down" (
    call :log_step "Остановка служб..."
    call :run_compose down %2 %3 %4 %5 %6 %7 %8 %9
    goto :end
)
if "%COMMAND%"=="restart" (
    call :log_step "Перезапуск служб..."
    call :run_compose restart %2 %3 %4 %5 %6 %7 %8 %9
    timeout /t 5 /nobreak >nul
    call :health_check
    goto :end
)
if "%COMMAND%"=="status" (
    call :run_compose ps
    goto :end
)
if "%COMMAND%"=="logs" (
    call :run_compose logs %2 %3 %4 %5 %6 %7 %8 %9
    goto :end
)
if "%COMMAND%"=="build" (
    call :log_step "Сборка образа..."
    call :run_compose build %2 %3 %4 %5 %6 %7 %8 %9
    goto :end
)
if "%COMMAND%"=="pull" (
    call :log_step "Загрузка образа..."
    call :run_compose pull %2 %3 %4 %5 %6 %7 %8 %9
    goto :end
)
if "%COMMAND%"=="clean" (
    call :log_step "Очистка ресурсов..."
    call :run_compose down --volumes --remove-orphans
    docker system prune -f
    goto :end
)
if "%COMMAND%"=="health" (
    call :health_check
    goto :end
)
if "%COMMAND%"=="info" (
    call :show_info
    goto :end
)
if "%COMMAND%"=="backup" (
    call :log_step "Резервное копирование данных..."
    if not exist "backup" mkdir "backup"
    for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "dt=%%a"
    set "timestamp=!dt:~0,8!_!dt:~8,6!"
    if exist "data" (
        powershell -Command "Compress-Archive -Path 'data' -DestinationPath 'backup\ntrip_backup_!timestamp!.zip' -Force"
        call :log_success "Резервное копирование данных завершено: backup\ntrip_backup_!timestamp!.zip"
    ) else (
        call :log_warning "Директория данных не существует"
    )
    goto :end
)

REM Неизвестная команда
call :log_error "Неизвестная команда: %COMMAND%"
call :show_help

:end
goto :eof

REM Точка входа скрипта
call :main %*