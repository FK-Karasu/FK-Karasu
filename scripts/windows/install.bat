@echo off
rem Запускать из любой папки: переходим в корень проекта (на 2 уровня выше).
cd /d "%~dp0..\.."
echo ===================================================
echo   Установка Системы Футбольной Школы
echo ===================================================
echo.

echo 1. Создание виртуального окружения (python venv)...
python -m venv venv
if %errorlevel% neq 0 (
    echo ОШИБКА: Не удалось создать venv. Проверьте, установлен ли Python 3.11 и добавлен ли он в PATH.
    pause
    exit /b
)

echo.
echo 2. Активация окружения...
call venv\Scripts\activate

echo.
echo 3. Обновление pip...
python -m pip install --upgrade pip

echo.
echo 4. Установка CMake (нужен для dlib)...
pip install cmake

echo.
echo 5. Установка зависимостей (это может занять 5-10 минут)...
echo    Устанавливаем dlib и библиотеки для распознавания лиц...
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo ОШИБКА: Не удалось установить библиотеки.
    echo Возможные причины:
    echo  - Не установлен Visual Studio C++ Build Tools
    echo  - Нет интернета
    pause
    exit /b
)

echo.
echo ===================================================
echo   Установка успешно завершена!
echo   Теперь запустите файл run.bat для старта системы.
echo ===================================================
pause
