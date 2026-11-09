#!/bin/bash
# Скрипт для локального тестирования Docker контейнера

echo "🐳 Сборка Docker образа..."
docker build -t football-school .

echo ""
echo "🚀 Запуск контейнера..."
docker run -p 5000:5000 \
  -e PORT=5000 \
  -e SECRET_KEY=test-secret-key-for-local-development \
  -e FLASK_ENV=development \
  football-school

echo ""
echo "✅ Приложение доступно на http://localhost:5000"
