"""
Telegram бот для уведомлений учеников
Запускается отдельным процессом

Установка зависимостей:
pip install python-telegram-bot

Запуск:
python telegram_bot.py
"""
import os
import requests
import time
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# URL вашего приложения
# Для локальной разработки или внутри контейнера:
port = os.environ.get('PORT', '5000')
APP_URL = os.environ.get('APP_URL', f'http://127.0.0.1:{port}')

# Получить токен бота из настроек через API
def get_bot_token():
    """Получить токен бота из настроек приложения"""
    # Сначала пробуем получить из переменной окружения
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    
    if token:
        print("✓ Токен получен из переменной окружения")
        return token

    # Если нет в переменной окружения, пробуем получить из настроек через API с повторами
    print(f"⏳ Ожидание запуска API по адресу {APP_URL}...")
    max_retries = 30  # Пробовать 30 раз (около 2-3 минут)
    for i in range(max_retries):
        try:
            response = requests.get(f'{APP_URL}/api/club-settings/public', timeout=5)
            if response.status_code == 200:
                data = response.json()
                token = data.get('telegram_bot_token')
                if token:
                    print("✓ Токен получен из настроек приложения")
                    return token
                else:
                    print("⚠️ Токен не задан в настройках приложения. Повтор...")
            else:
                 print(f"⚠️ API вернул статус {response.status_code}. Повтор...")
        except requests.exceptions.ConnectionError:
            print("⚠️ Сервер еще не доступен. Повтор...")
        except Exception as e:
            print(f"⚠️ Ошибка получения токена: {e}")
        
        time.sleep(5) # Ждем 5 секунд перед повтором

    print("❌ Не удалось получить токен после всех попыток.")
    return None


# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    
    # Клавиатура: Отправить номер + Кнопка Web App
    contact_keyboard = ReplyKeyboardMarkup(
        [
            [KeyboardButton("📱 Отправить мой номер", request_contact=True)],
            [KeyboardButton("🌐 Открыть приложение", web_app=WebAppInfo(url="https://karasu.uz/portal/login"))]
        ],
        resize_keyboard=True
    )
    
    await update.message.reply_text(
        "👋 Привет! Я бот для уведомлений футбольной школы.\n\n"
        "Для регистрации нажми «Отправить номер», или нажми «Открыть приложение» для входа в кабинет 👇",
        reply_markup=contact_keyboard
    )


# Обработчик контакта
async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик полученного контакта"""
    contact = update.message.contact
    chat_id = update.message.chat_id
    phone_number = contact.phone_number
    
    # Отправляем на сервер для проверки
    try:
        response = requests.post(
            f'{APP_URL}/api/telegram/register-by-phone',
            json={
                'chat_id': chat_id,
                'phone': phone_number
            },
            timeout=10
        )
        
        result = response.json()
        
        if result.get('success'):
            if result.get('is_staff'):
                roles = result.get('roles', [])
                
                # Постоянное меню для сотрудников
                staff_keyboard = ReplyKeyboardMarkup(
                    [
                        [KeyboardButton("📊 Отчет по посещаемости")],
                        [KeyboardButton("🌐 Открыть приложение", web_app=WebAppInfo(url="https://karasu.uz/portal/login"))]
                    ],
                    resize_keyboard=True
                )
                
                await update.message.reply_text(
                    f"✅ <b>Доступ разрешен: {', '.join(roles)}</b>\n\n"
                    f"Вы успешно авторизованы как сотрудник Командного центра школы.\n"
                    f"Теперь сюда будут приходить уведомления об оплатах и ежедневные отчеты.\n\n"
                    f"Используйте кнопки меню для управления.",
                    parse_mode='HTML',
                    reply_markup=staff_keyboard
                )
                return

            student = result.get('student', {})
            student_name = student.get('full_name', 'ученик')
            code = student.get('code', '----')
            
            # Формируем сообщение с данными для входа
            login = phone_number
            if not login.startswith('+'):
                login = '+' + login

            await update.message.reply_text(
                f"✅ Ура! Я нашел тебя, {student_name}!\n\n"
                f"🔐 <b>Твой доступ к порталу:</b>\n"
                f"🔗 Ссылка: https://karasu.uz/portal\n"
                f"👤 Логин: <code>{login}</code>\n"
                f"🔑 Пароль (код): <code>{code}</code>\n\n"
                f"Теперь я буду присылать сюда уведомления о занятиях!",
                parse_mode='HTML',
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            await update.message.reply_text(
                f"❌ {result.get('message', 'Ошибка')}\n"
                "Попробуй обратиться к администратору, если уверен, что твой номер есть в базе.",
                reply_markup=ReplyKeyboardRemove()
            )
            
    except Exception as e:
        await update.message.reply_text("❌ Ошибка соединения с сервером. Попробуй позже.")
        print(f"Error handling contact: {e}")


# Обработчик текстовых сообщений (старый способ по коду, оставим на всякий случай)
async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кода привязки (резервный вариант)"""
    chat_id = update.message.chat_id
    code = update.message.text.strip().upper()
    
    # Проверка формата кода
    if len(code) != 4 or not (code[0].isalpha() and code[1:].isdigit()):
        await update.message.reply_text(
            "❌ Неверный формат кода.\n\n"
            "Код должен состоять из буквы и трех цифр.\n"
            "Проверь правильность кода и попробуй еще раз:"
        )
        return
    
    # Отправить код на сервер для регистрации
    try:
        response = requests.post(
            f'{APP_URL}/api/telegram/register',
            json={
                'chat_id': chat_id,
                'code': code
            },
            timeout=10
        )
        
        result = response.json()
        
        if result.get('success'):
            student = result.get('student', {})
            student_name = student.get('full_name', 'ученик')
            group_name = student.get('group_name', 'группа')
            
            await update.message.reply_text(
                f"✅ {result.get('message', 'Регистрация успешна!')}\n\n"
                f"Теперь ты будешь получать уведомления о занятиях группы '{group_name}'."
            )
        else:
            await update.message.reply_text(
                f"❌ {result.get('message', 'Ошибка регистрации')}\n\n"
                "Проверь правильность кода и попробуй еще раз:"
            )
    except requests.exceptions.RequestException as e:
        await update.message.reply_text(
            "❌ Ошибка соединения с сервером. Попробуй позже."
        )
        print(f"Ошибка запроса к API: {e}")


# Обработчик команды /app
async def handle_app(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка кнопки для открытия Web App"""
    keyboard = [[InlineKeyboardButton("🚀 Открыть приложение", web_app=WebAppInfo(url="https://karasu.uz/portal/login"))]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Нажмите кнопку ниже, чтобы открыть приложение школы:", reply_markup=reply_markup)

# Обработчик кнопки отчета
async def handle_staff_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Предложение выбрать дату для отчета"""
    keyboard = [
        [
            InlineKeyboardButton("Сегодня", callback_data="report_today"),
            InlineKeyboardButton("Вчера", callback_data="report_yesterday"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите период для отчета:", reply_markup=reply_markup)

# Обработчик инлайн-кнопок
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора даты"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    target_date = datetime.now()

    if data == "report_yesterday":
        target_date = target_date - timedelta(days=1)
    
    date_str = target_date.strftime('%Y-%m-%d')
    
    try:
        response = requests.get(
            f"{APP_URL}/api/telegram/attendance-report",
            params={'date': date_str},
            timeout=10
        )
        result = response.json()
        
        if result.get('success'):
            await query.edit_message_text(
                result.get('text', 'Ошибка формирования текста'),
                parse_mode='HTML'
            )
        else:
            await query.edit_message_text(f"❌ Ошибка: {result.get('message', 'Неизвестная ошибка')}")
    except Exception as e:
        print(f"Error getting report: {e}")
        await query.edit_message_text("❌ Ошибка соединения с сервером.")


# Обработчик неизвестных команд
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик неизвестных команд"""
    if update.message.text == "📊 Отчет по посещаемости":
        await handle_staff_report(update, context)
        return
        
    await update.message.reply_text(
        "Не понимаю эту команду.\n\n"
        "Используй /start для начала работы."
    )


def main():
    """Запуск бота"""
    # Получить токен
    token = get_bot_token()
    
    if not token:
        print("❌ Ошибка: Токен бота не найден!")
        print("Установите переменную окружения TELEGRAM_BOT_TOKEN")
        print("Или добавьте токен в настройки приложения")
        return
    
    print(f"🤖 Запуск Telegram бота...")
    print(f"📡 Подключение к приложению: {APP_URL}")
    
    # Создать приложение
    application = Application.builder().token(token).build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("report", handle_staff_report))
    application.add_handler(CommandHandler("app", handle_app))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.Regex("^📊 Отчет по посещаемости$"), handle_staff_report))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code))
    application.add_handler(MessageHandler(filters.COMMAND, unknown))
    
    # Запустить бота с защитой от конфликтов (при обновлении контейнеров)
    print("✅ Бот запущен и готов к работе!")
    print("Нажмите Ctrl+C для остановки")

    while True:
        try:
            application.run_polling(allowed_updates=Update.ALL_TYPES)
            # Если run_polling вернулся сам (например, при остановке), выходим
            break
        except Exception as e:
            # Если словили Конфликт (Conflict), значит старый контейнер еще жив.
            # Ждем и пробуем снова.
            if "Conflict" in str(e):
                print("⚠️ Обнаружен конфликт сессий (старый контейнер еще работает). Ждем 10 сек...")
                time.sleep(10)
            else:
                print(f"⚠️ Критическая ошибка бота: {e}. Перезапуск через 5 сек...")
                time.sleep(5)


if __name__ == '__main__':
    main()
