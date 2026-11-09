# Скрипт для локального тестирования Docker контейнера (Windows)

Write-Host "🐳 Сборка Docker образа..." -ForegroundColor Cyan
docker build -t football-school .

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "🚀 Запуск контейнера..." -ForegroundColor Cyan
    docker run -p 5000:5000 `
      -e PORT=5000 `
      -e SECRET_KEY=test-secret-key-for-local-development `
      -e FLASK_ENV=development `
      football-school

    Write-Host ""
    Write-Host "✅ Приложение доступно на http://localhost:5000" -ForegroundColor Green
} else {
    Write-Host "❌ Ошибка сборки Docker образа" -ForegroundColor Red
}
