import os
import sys
import subprocess
import urllib.request

# URL for dlib wheel (Python 3.11, Windows 64-bit)
# Используем проверенный репозиторий с готовыми файлами
DLIB_URL = "https://github.com/z-mahmud22/Dlib_Windows_Python3.x/raw/main/dlib-19.24.1-cp311-cp311-win_amd64.whl"
DLIB_FILE = "dlib-19.24.1-cp311-cp311-win_amd64.whl"

def install_package(args):
    """Run pip install with arguments"""
    cmd = [sys.executable, "-m", "pip", "install"] + args
    print(f"Running: {' '.join(cmd)}")
    subprocess.check_call(cmd)

def main():
    print("🚀 Начинаем автоматическое исправление установки...")
    
    # 1. Скачивание dlib
    if not os.path.exists(DLIB_FILE):
        print(f"📥 Скачиваю dlib (это может занять время)...")
        try:
            urllib.request.urlretrieve(DLIB_URL, DLIB_FILE)
            print("✅ Скачивание завершено.")
        except Exception as e:
            print(f"❌ Ошибка при скачивании: {e}")
            print("Попробуйте скачать файл вручную по ссылке:")
            print(DLIB_URL)
            return
    else:
        print("ℹ️ Файл dlib уже существует, используем его.")

    # 2. Установка dlib
    try:
        print("🛠 Устанавливаю dlib...")
        install_package([DLIB_FILE])
        print("✅ dlib успешно установлен!")
    except Exception as e:
        print(f"❌ Ошибка установки dlib: {e}")
        return

    # 3. Установка остальных зависимостей
    if os.path.exists("requirements.txt"):
        print("📦 Устанавливаю остальные библиотеки (Flask, etc)...")
        try:
            install_package(["-r", "requirements.txt"])
            print("✅ Все библиотеки установлены!")
        except Exception as e:
            print(f"❌ Ошибка установки зависимостей: {e}")
    else:
        print("⚠️ Файл requirements.txt не найден!")

    print("\n-------------------------------------------")
    print("🎉 ГОТОВО! Теперь запустите: run.bat")
    print("-------------------------------------------")
    
    # Удаляем скачанный файл, чтобы не мусорить (по желанию)
    # os.remove(DLIB_FILE)

if __name__ == "__main__":
    main()
