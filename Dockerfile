FROM python:3.11-slim

# Зеркала пакетов. У провайдера сервера до deb.debian.org и pypi.org (CDN Fastly)
# всего ~70 КБ/с, и полная сборка не укладывалась в таймаут. Зеркала Huawei отдают
# 1,5–2 МБ/с. Другое зеркало: --build-arg APT_MIRROR=... / PIP_INDEX=...
ARG APT_MIRROR=https://repo.huaweicloud.com
ARG PIP_INDEX=https://repo.huaweicloud.com/repository/pypi/simple
ENV PIP_INDEX_URL=${PIP_INDEX} \
    PIP_DEFAULT_TIMEOUT=60 \
    PIP_RETRIES=10
RUN sed -i "s|http://deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources

# Системные библиотеки и компилятор для CPU InsightFace
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Явное копирование ассетов в defaults (пробивает кеш Docker)
COPY frontend/static/uploads/ /app/defaults/

RUN mkdir -p database frontend/static/uploads

ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py

EXPOSE 5000

# Исправляем окончания строк (CRLF -> LF) для Windows-файлов и делаем скрипт исполняемым
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh

CMD ["./start.sh"]
# Force rebuild trigger 2
