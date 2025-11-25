# Скрипт развёртывания NTRIP Caster через Docker (версия PowerShell)
# Используется для управления контейнерами Docker NTRIP Caster в среде Windows

param(
    [Parameter(Position=0)]
    [string]$Command = "help",
    
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Args
)

# Настройка обработки ошибок
$ErrorActionPreference = "Stop"

# Конфигурация проекта
$PROJECT_NAME = "ntrip-caster"
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$ENV_FILE = Join-Path $SCRIPT_DIR ".env"
$ENV_EXAMPLE = Join-Path $SCRIPT_DIR ".env.example"

# Определение цветов
$Colors = @{
    Red = "Red"
    Green = "Green"
    Yellow = "Yellow"
    Blue = "Blue"
    Magenta = "Magenta"
    Cyan = "Cyan"
    White = "White"
}

# Функции логирования
function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "Info"
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    
    switch ($Level) {
        "Info" { Write-Host "[$timestamp] [INFO] $Message" -ForegroundColor $Colors.Blue }
        "Success" { Write-Host "[$timestamp] [SUCCESS] $Message" -ForegroundColor $Colors.Green }
        "Warning" { Write-Host "[$timestamp] [WARNING] $Message" -ForegroundColor $Colors.Yellow }
        "Error" { Write-Host "[$timestamp] [ERROR] $Message" -ForegroundColor $Colors.Red }
        "Step" { Write-Host "[$timestamp] [STEP] $Message" -ForegroundColor $Colors.Magenta }
    }
}

# Отображение баннера
function Show-Banner {
    Write-Host "" -ForegroundColor $Colors.Cyan
    Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor $Colors.Cyan
    Write-Host "║              Скрипт развёртывания NTRIP Caster               ║" -ForegroundColor $Colors.Cyan
    Write-Host "║                    Версия PowerShell                         ║" -ForegroundColor $Colors.Cyan
    Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor $Colors.Cyan
    Write-Host "" -ForegroundColor $Colors.Cyan
}

# Проверка окружения Docker
function Test-DockerEnvironment {
    Write-Log "Проверка окружения Docker..." "Step"
    
    # Проверка Docker
    try {
        $dockerVersion = docker --version
        Write-Log "Версия Docker: $dockerVersion" "Info"
    }
    catch {
        Write-Log "Docker не установлен или не запущен" "Error"
        Write-Log "Установите Docker Desktop: https://www.docker.com/products/docker-desktop" "Info"
        exit 1
    }
    
    # Проверка Docker Compose
    try {
        $composeVersion = docker compose version
        Write-Log "Версия Docker Compose: $composeVersion" "Info"
        $script:DOCKER_COMPOSE_CMD = "docker compose"
    }
    catch {
        try {
            $composeVersion = docker-compose --version
            Write-Log "Версия Docker Compose: $composeVersion" "Info"
            $script:DOCKER_COMPOSE_CMD = "docker-compose"
        }
        catch {
            Write-Log "Docker Compose не установлен" "Error"
            exit 1
        }
    }
    
    # Проверка демона Docker
    try {
        docker info | Out-Null
        Write-Log "Демон Docker работает нормально" "Success"
    }
    catch {
        Write-Log "Демон Docker не запущен, запустите Docker Desktop" "Error"
        exit 1
    }
}

# Загрузка переменных окружения
function Import-EnvironmentVariables {
    if (Test-Path $ENV_FILE) {
        Get-Content $ENV_FILE | ForEach-Object {
            if ($_ -match '^([^#][^=]+)=(.*)$') {
                [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
            }
        }
        Write-Log "Переменные окружения загружены" "Info"
    } else {
        Write-Log "Файл .env не существует, используется конфигурация по умолчанию" "Warning"
    }
}

# Построение команды Docker Compose
function Build-ComposeCommand {
    param([string[]]$ComposeArgs)
    
    $environment = $env:ENVIRONMENT
    if (-not $environment) { $environment = "development" }
    
    $profiles = $env:PROFILES
    if (-not $profiles) { $profiles = "dev" }
    
    $composeFiles = @("-f", "docker-compose.yml")
    
    if ($environment -eq "production") {
        $composeFiles += @("-f", "docker-compose.prod.yml")
    } else {
        $composeFiles += @("-f", "docker-compose.override.yml")
    }
    
    $profileArgs = @()
    if ($profiles) {
        $profileList = $profiles -split ","
        foreach ($profile in $profileList) {
            $profileArgs += @("--profile", $profile.Trim())
        }
    }
    
    $fullCommand = @($script:DOCKER_COMPOSE_CMD) + $composeFiles + $profileArgs + $ComposeArgs
    return $fullCommand -join " "
}

# Выполнение команды Docker Compose
function Invoke-ComposeCommand {
    param([string[]]$ComposeArgs)
    
    $command = Build-ComposeCommand $ComposeArgs
    Write-Log "Выполнение команды: $command" "Info"
    
    try {
        Invoke-Expression $command
        return $LASTEXITCODE
    }
    catch {
        Write-Log "Не удалось выполнить команду: $_" "Error"
        return 1
    }
}

# Создание необходимых директорий
function New-RequiredDirectories {
    Write-Log "Создание необходимых директорий..." "Step"
    
    $directories = @(
        "data",
        "logs",
        "secrets",
        "nginx/logs",
        "redis",
        "monitoring/prometheus/rules",
        "monitoring/grafana/provisioning/datasources",
        "monitoring/grafana/provisioning/dashboards",
        "monitoring/grafana/dashboards",
        "backup"
    )
    
    foreach ($dir in $directories) {
        $fullPath = Join-Path $SCRIPT_DIR $dir
        if (-not (Test-Path $fullPath)) {
            New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
            Write-Log "Создана директория: $dir" "Info"
        }
    }
    
    # Установка прав доступа (эквивалентная операция для Windows)
    try {
        $dataPath = Join-Path $SCRIPT_DIR "data"
        $logsPath = Join-Path $SCRIPT_DIR "logs"
        
        # Убедиться, что текущий пользователь имеет полный контроль
        icacls $dataPath /grant "${env:USERNAME}:(OI)(CI)F" /T | Out-Null
        icacls $logsPath /grant "${env:USERNAME}:(OI)(CI)F" /T | Out-Null
        
        Write-Log "Права доступа к директориям установлены" "Success"
    }
    catch {
        Write-Log "Не удалось установить права доступа, но это не критично" "Warning"
    }
}

# Создание файла окружения
function New-EnvironmentFile {
    Write-Log "Создание конфигурационного файла окружения..." "Step"
    
    if (-not (Test-Path $ENV_FILE)) {
        if (Test-Path $ENV_EXAMPLE) {
            Copy-Item $ENV_EXAMPLE $ENV_FILE
            Write-Log "Файл .env создан" "Success"
        } else {
            Write-Log "Файл .env.example не существует" "Error"
            return
        }
    }
    
    # Обновление переменных окружения
    $content = Get-Content $ENV_FILE
    $environment = $env:ENVIRONMENT
    if (-not $environment) { $environment = "development" }
    
    $content = $content -replace '^ENVIRONMENT=.*', "ENVIRONMENT=$environment"
    $content = $content -replace '^PROJECT_NAME=.*', "PROJECT_NAME=$PROJECT_NAME"
    $content = $content -replace '^TZ=.*', "TZ=Asia/Shanghai"
    
    Set-Content -Path $ENV_FILE -Value $content
    Write-Log "Конфигурационный файл окружения обновлён" "Success"
}

# Проверка здоровья
function Test-ServiceHealth {
    Write-Log "Выполнение проверки здоровья..." "Step"
    
    try {
        if (Test-Path "healthcheck.py") {
            python healthcheck.py
        } else {
            Write-Log "Скрипт проверки здоровья не существует, пропуск проверки" "Warning"
        }
    }
    catch {
        Write-Log "Проверка здоровья не удалась: $_" "Error"
    }
}

# Отображение информации о службах
function Show-ServiceInfo {
    Write-Log "Информация о службах:" "Step"
    
    # Получение IP-адреса локального хоста
    $localIP = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "Ethernet*" | Select-Object -First 1).IPAddress
    if (-not $localIP) {
        $localIP = "localhost"
    }
    
    Write-Host ""
    Write-Host "📡 Служба NTRIP Caster:" -ForegroundColor $Colors.Cyan
    Write-Host "   - NTRIP порт: ntrip://${localIP}:2101" -ForegroundColor $Colors.White
    Write-Host "   - Веб-интерфейс управления: http://${localIP}:5757" -ForegroundColor $Colors.White
    
    $profiles = $env:PROFILES
    if ($profiles -and ($profiles -match "monitoring" -or $profiles -match "full")) {
        Write-Host ""
        Write-Host "📊 Службы мониторинга:" -ForegroundColor $Colors.Cyan
        Write-Host "   - Prometheus: http://${localIP}:9090" -ForegroundColor $Colors.White
        Write-Host "   - Grafana: http://${localIP}:3000 (admin/admin123)" -ForegroundColor $Colors.White
    }
    
    $environment = $env:ENVIRONMENT
    if ($environment -eq "development") {
        Write-Host ""
        Write-Host "🛠️ Инструменты разработки:" -ForegroundColor $Colors.Cyan
        Write-Host "   - Adminer (управление БД): http://${localIP}:8081" -ForegroundColor $Colors.White
        Write-Host "   - Dozzle (просмотр логов): http://${localIP}:8082" -ForegroundColor $Colors.White
        Write-Host "   - cAdvisor (мониторинг контейнеров): http://${localIP}:8083" -ForegroundColor $Colors.White
    }
    
    Write-Host ""
}

# Отображение справки
function Show-Help {
    Write-Host ""
    Write-Host "Скрипт развёртывания NTRIP Caster через Docker (версия PowerShell)" -ForegroundColor $Colors.Cyan
    Write-Host ""
    Write-Host "Использование: .\docker-deploy.ps1 <команда> [опции]" -ForegroundColor $Colors.White
    Write-Host ""
    Write-Host "Основные команды:" -ForegroundColor $Colors.Yellow
    Write-Host "  up              Запустить службы" -ForegroundColor $Colors.White
    Write-Host "  down            Остановить службы" -ForegroundColor $Colors.White
    Write-Host "  restart         Перезапустить службы" -ForegroundColor $Colors.White
    Write-Host "  status          Просмотреть состояние служб" -ForegroundColor $Colors.White
    Write-Host "  logs            Просмотреть логи служб" -ForegroundColor $Colors.White
    Write-Host "  build           Собрать образ" -ForegroundColor $Colors.White
    Write-Host "  pull            Загрузить образ" -ForegroundColor $Colors.White
    Write-Host "  clean           Очистить ресурсы" -ForegroundColor $Colors.White
    Write-Host ""
    Write-Host "Команды управления:" -ForegroundColor $Colors.Yellow
    Write-Host "  health          Проверка здоровья" -ForegroundColor $Colors.White
    Write-Host "  info            Отобразить информацию о службах" -ForegroundColor $Colors.White
    Write-Host "  backup          Резервное копирование данных" -ForegroundColor $Colors.White
    Write-Host "  restore         Восстановление данных" -ForegroundColor $Colors.White
    Write-Host "  update          Обновить службы" -ForegroundColor $Colors.White
    Write-Host ""
    Write-Host "Переменные окружения:" -ForegroundColor $Colors.Yellow
    Write-Host "  ENVIRONMENT     Окружение развёртывания (development|production)" -ForegroundColor $Colors.White
    Write-Host "  PROFILES        Профили конфигурации служб (dev|prod|monitoring|full)" -ForegroundColor $Colors.White
    Write-Host ""
    Write-Host "Примеры:" -ForegroundColor $Colors.Yellow
    Write-Host "  .\docker-deploy.ps1 up -d" -ForegroundColor $Colors.White
    Write-Host "  `$env:ENVIRONMENT='production'; .\docker-deploy.ps1 up" -ForegroundColor $Colors.White
    Write-Host "  `$env:PROFILES='monitoring'; .\docker-deploy.ps1 restart" -ForegroundColor $Colors.White
    Write-Host ""
}

# Главная функция
function Main {
    param([string]$Command, [string[]]$Args)
    
    Show-Banner
    
    # Проверка, что скрипт запущен в правильной директории
    if (-not (Test-Path "docker-compose.yml")) {
        Write-Log "Запустите этот скрипт в корневой директории проекта NTRIP Caster" "Error"
        exit 1
    }
    
    # Проверка окружения Docker
    Test-DockerEnvironment
    
    # Загрузка переменных окружения
    Import-EnvironmentVariables
    
    switch ($Command.ToLower()) {
        "help" {
            Show-Help
        }
        "check" {
            Write-Log "Проверка окружения Docker завершена" "Success"
        }
        "create_directories" {
            New-RequiredDirectories
        }
        "create_env" {
            New-EnvironmentFile
        }
        "up" {
            Write-Log "Запуск служб..." "Step"
            $exitCode = Invoke-ComposeCommand (@("up") + $Args)
            if ($exitCode -eq 0) {
                Start-Sleep -Seconds 5
                Test-ServiceHealth
                Show-ServiceInfo
            }
        }
        "down" {
            Write-Log "Остановка служб..." "Step"
            Invoke-ComposeCommand (@("down") + $Args)
        }
        "restart" {
            Write-Log "Перезапуск служб..." "Step"
            Invoke-ComposeCommand (@("restart") + $Args)
            Start-Sleep -Seconds 5
            Test-ServiceHealth
        }
        "status" {
            Invoke-ComposeCommand @("ps")
        }
        "logs" {
            Invoke-ComposeCommand (@("logs") + $Args)
        }
        "build" {
            Write-Log "Сборка образа..." "Step"
            Invoke-ComposeCommand (@("build") + $Args)
        }
        "pull" {
            Write-Log "Загрузка образа..." "Step"
            Invoke-ComposeCommand (@("pull") + $Args)
        }
        "clean" {
            Write-Log "Очистка ресурсов..." "Step"
            Invoke-ComposeCommand @("down", "--volumes", "--remove-orphans")
            docker system prune -f
        }
        "health" {
            Test-ServiceHealth
        }
        "info" {
            Show-ServiceInfo
        }
        "backup" {
            Write-Log "Резервное копирование данных..." "Step"
            $backupDir = Join-Path $SCRIPT_DIR "backup"
            $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
            $backupFile = Join-Path $backupDir "ntrip_backup_$timestamp.zip"
            
            if (-not (Test-Path $backupDir)) {
                New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
            }
            
            $dataDir = Join-Path $SCRIPT_DIR "data"
            if (Test-Path $dataDir) {
                Compress-Archive -Path $dataDir -DestinationPath $backupFile -Force
                Write-Log "Резервное копирование данных завершено: $backupFile" "Success"
            } else {
                Write-Log "Директория данных не существует" "Warning"
            }
        }
        "restore" {
            Write-Log "Восстановление данных..." "Step"
            if ($Args.Count -gt 0) {
                $backupFile = $Args[0]
                if (Test-Path $backupFile) {
                    $dataDir = Join-Path $SCRIPT_DIR "data"
                    Expand-Archive -Path $backupFile -DestinationPath $dataDir -Force
                    Write-Log "Восстановление данных завершено" "Success"
                } else {
                    Write-Log "Файл резервной копии не существует: $backupFile" "Error"
                }
            } else {
                Write-Log "Укажите путь к файлу резервной копии" "Error"
            }
        }
        "update" {
            Write-Log "Обновление служб..." "Step"
            Invoke-ComposeCommand @("pull")
            Invoke-ComposeCommand @("up", "-d")
            Write-Log "Обновление служб завершено" "Success"
        }
        default {
            Write-Log "Неизвестная команда: $Command" "Error"
            Show-Help
            exit 1
        }
    }
}

# Точка входа скрипта
if ($MyInvocation.InvocationName -ne '.') {
    Main $Command $Args
}