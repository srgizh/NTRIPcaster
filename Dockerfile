# Образ Docker NTRIP Caster v2.2.0
# Используется многоэтапная сборка для оптимизации размера образа
FROM python:3.11-slim AS builder

# Установка переменных окружения на этапе сборки
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Установка зависимостей для сборки
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Создание виртуального окружения
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Копирование и установка зависимостей Python
COPY requirements.txt .
# Сначала обновление setuptools до безопасной версии для исправления CVE-2025-47273 и CVE-2024-6345
RUN pip install --upgrade pip setuptools>=78.1.1 wheel && \
    pip install --no-cache-dir -r requirements.txt

# Образ production
FROM python:3.11-slim AS production

# Установка меток
LABEL maintainer="2rtk <i@jia.by>" \
      version="2.2.0" \
      description="High-performance NTRIP Caster with RTCM parsing" \
      org.opencontainers.image.title="NTRIP Caster" \
      org.opencontainers.image.description="High-performance NTRIP Caster with RTCM parsing" \
      org.opencontainers.image.version="2.2.0" \
      org.opencontainers.image.vendor="2RTK" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/Rampump/NTRIPcaster"

# Установка переменных окружения
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:$PATH" \
    DEBIAN_FRONTEND=noninteractive \
    TZ=UTC

# Установка зависимостей времени выполнения
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    curl \
    ca-certificates \
    tzdata \
    tini \
    gosu \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Создание пользователя и группы (не root)
RUN groupadd -r -g 1000 ntrip && \
    useradd -r -u 1000 -g ntrip -d /app -s /bin/bash ntrip

# Установка рабочей директории
WORKDIR /app

# Копирование виртуального окружения из этапа сборки
COPY --from=builder /opt/venv /opt/venv

# Обеспечение использования безопасной версии setuptools в production окружении
RUN pip install --upgrade setuptools>=78.1.1

# Копирование кода приложения (селективное копирование, избегание копирования ненужных файлов)
COPY --chown=ntrip:ntrip main.py healthcheck.py config.ini.example ./
COPY --chown=ntrip:ntrip src/ ./src/
COPY --chown=ntrip:ntrip pyrtcm/ ./pyrtcm/
COPY --chown=ntrip:ntrip static/ ./static/
COPY --chown=ntrip:ntrip templates/ ./templates/

# Создание необходимых директорий и установка прав доступа
RUN mkdir -p /app/logs /app/data /app/config && \
    chown -R ntrip:ntrip /app && \
    chmod -R 755 /app && \
    chmod +x /app/main.py /app/healthcheck.py

# Создание точек монтирования томов данных
VOLUME ["/app/logs", "/app/data", "/app/config"]

# Открытие портов
EXPOSE 2101 5757

# Проверка здоровья
HEALTHCHECK --interval=30s --timeout=15s --start-period=90s --retries=3 \
    CMD python /app/healthcheck.py || exit 1

# Создание скрипта запуска
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Обеспечение существования директорий и установка правильных прав доступа\n\
echo "Установка прав доступа к директориям..."\n\
mkdir -p /app/logs /app/data /app/config\n\
chown -R ntrip:ntrip /app/logs /app/data /app/config\n\
chmod -R 755 /app/logs /app/data /app/config\n\
\n\
# Инициализация конфигурационного файла (если не существует)\n\
if [ ! -f "/app/config/config.ini" ]; then\n\
    echo "Инициализация конфигурационного файла..."\n\
    cp /app/config.ini.example /app/config/config.ini\n\
    chown ntrip:ntrip /app/config/config.ini\n\
fi\n\
\n\
# Установка пути к конфигурационному файлу\n\
export NTRIP_CONFIG_FILE="/app/config/config.ini"\n\
\n\
# Переключение на пользователя ntrip и запуск приложения\n\
echo "Запуск NTRIP Caster..."\n\
exec gosu ntrip python /app/main.py' > /app/entrypoint.sh && \
    chmod +x /app/entrypoint.sh && \
    chown ntrip:ntrip /app/entrypoint.sh

# Использование tini в качестве процесса init
ENTRYPOINT ["/usr/bin/tini", "--"]

# Команда запуска
CMD ["/app/entrypoint.sh"]