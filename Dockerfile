FROM python:3.11-slim

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
