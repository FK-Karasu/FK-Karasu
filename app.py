import os
import io
import json
import base64
import shutil
import threading
import time
import queue
import re
import math
import calendar
import uuid
import requests
import hashlib
import smtplib
import secrets
import random
import cv2
import numpy as np
from datetime import datetime, timedelta, date, timezone
from datetime import time as dt_time
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory, send_file, session, Response
from flask_compress import Compress
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
import urllib.parse
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload, defer
import pytz
from email.message import EmailMessage
from urllib.parse import urlencode
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
import psutil
try:
    import pynvml
    pynvml.nvmlInit()
    NVML_ENABLED = True
except Exception:
    NVML_ENABLED = False

if os.name == 'nt':
    paths_to_add = [
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4\bin",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4\libnvvp",
        r"C:\Program Files\NVIDIA\CUDNN\v9.18\bin\12.9\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.18\bin",
        r"C:\Program Files\NVIDIA\CUDNN\v9.1\bin",
        r"C:\NVIDIA\CUDNN\v9.18\bin\12.9\x64", # На всякий случай
        os.environ.get('CUDA_PATH_V12_4', ''),
        os.environ.get('CUDA_PATH', '')
    ]
    for p in paths_to_add:
        if p and os.path.exists(p):
            try:
                os.add_dll_directory(p)
                os.environ['PATH'] = p + os.pathsep + os.environ.get('PATH', '')
                print(f"✅ Путь добавлен: {p}")
            except Exception: pass

# Отключаем лишние логи OpenCV и FFmpeg (убираем ошибки HEVC)
os.environ['OPENCV_LOG_LEVEL'] = 'ERROR'
os.environ['FFMPEG_LOG_LEVEL'] = 'quiet'
# Форсируем использование CUDA/TensorRT в ONNX
os.environ['ORT_TENSORRT_FP16_ENABLE'] = '1'

from backend.models.models import db, User, Student, Payment, Attendance, AccessLog, Expense, Group, GroupTrainer, Tariff, ClubSettings, RewardType, StudentReward, CashTransfer, Role, RolePermission, CardType, StudentCard, Tournament, TournamentTeamCatalog, TournamentTeamMember, TournamentStadium, TournamentTeamShareLink, TournamentEntry, TournamentGroup, TournamentMatch, TournamentMatchAppearance, TournamentMatchEvent, TournamentAward, DeviceCommand, BridgeStatus, TerminalFaceState, StudentLog
# Live camera recognition stays disabled; access-log verification is separate.
USE_FACE = False
from backend.services.face_stub import DummyFaceService as FaceService
from backend.services.access_face_verifier import AccessFaceVerifier
from backend.data.locations import get_cities, get_districts
from backend.utils.student_utils import (
    generate_telegram_link_code,
    get_next_available_student_number,
    validate_student_number,
    ensure_student_has_telegram_code
)
from backend.services.telegram_service import (
    send_group_notification,
    register_student_by_code,
    send_reward_notification,
    send_card_notification,
    send_payment_notification,
    send_monthly_payment_reminders
)

# Часовой пояс Ташкента (UTC+5)
TASHKENT_TZ = pytz.timezone('Asia/Tashkent')

def get_local_time():
    """Получить текущее локальное время Ташкента"""
    return datetime.now(TASHKENT_TZ)

def get_local_date():
    """Получить текущую локальную дату Ташкента"""
    return get_local_time().date()

def get_local_datetime():
    """Получить текущий локальный datetime Ташкента (без timezone для совместимости с БД)"""
    return get_local_time().replace(tzinfo=None)

# Получить абсолютный путь к папке проекта
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__, 
            template_folder='frontend/templates',
            static_folder='frontend/static')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Конфигурация для production/development
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')

# PostgreSQL URL для Railway (автоматически устанавливается)
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # Railway отдаёт postgres://. SQLAlchemy 2 по схеме postgresql://
    # берёт драйвер psycopg 3, которого в образе нет: стоит psycopg2.
    if database_url.startswith('postgres://'):
        database_url = 'postgresql+psycopg2://' + database_url[len('postgres://'):]
    elif database_url.startswith('postgresql+psycopg://'):
        database_url = 'postgresql+psycopg2://' + database_url[len('postgresql+psycopg://'):]
    elif database_url.startswith('postgresql://'):
        database_url = 'postgresql+psycopg2://' + database_url[len('postgresql://'):]
    elif database_url.startswith('sqlite:///') and not database_url.startswith('sqlite:////'):
        sqlite_path = database_url.replace('sqlite:///', '', 1)
        if not os.path.isabs(sqlite_path):
            sqlite_path = os.path.join(basedir, sqlite_path)
        database_url = 'sqlite:///' + sqlite_path.replace('\\', '/')
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    db_label = 'POSTGRESQL' if database_url.startswith('postgresql') else 'SQLITE'
    print(f"✅ ИСПОЛЬЗУЕТСЯ {db_label}: {database_url.split('@')[-1]}") # Логируем (без пароля)
else:
    # Локальная разработка - SQLite
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database', 'football_school.db')
    print("⚠️ ИСПОЛЬЗУЕТСЯ SQLITE (Локальный режим или нет DATABASE_URL)")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'frontend', 'static', 'uploads')

UPLOAD_FOLDER = app.config['UPLOAD_FOLDER']

GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '').strip()
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '').strip()
GOOGLE_OAUTH_AUTHORIZE_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_OAUTH_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_OAUTH_USERINFO_URL = 'https://www.googleapis.com/oauth2/v3/userinfo'
PASSWORD_RESET_TOKEN_TTL_HOURS = int(os.environ.get('PASSWORD_RESET_TOKEN_TTL_HOURS', '2') or 2)

db.init_app(app)
app.config['COMPRESS_MIN_SIZE'] = 1000
app.config['COMPRESS_MIMETYPES'] = [
    'text/html', 'text/css', 'application/javascript', 'application/json',
    'image/svg+xml'
]
Compress(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


@app.after_request
def add_asset_cache_headers(response):
    """Avoid downloading the same shared CSS, JS and media on every tab change."""
    if request.path.startswith('/static/') and response.status_code in {200, 206, 304}:
        extension = os.path.splitext(request.path.lower())[1]
        max_age = 3600 if extension in {'.css', '.js'} else (
            2592000 if extension in {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg', '.mp4', '.woff', '.woff2'}
            else 86400
        )
        response.cache_control.public = True
        response.cache_control.max_age = max_age
        response.cache_control.no_cache = None
    return response

# --- БЛОК АВТОМАТИЧЕСКОЙ ИНИЦИАЛИЗАЦИИ ПЕРЕНЕСЕН В КОНЕЦ ФАЙЛА ---
# (чтобы все функции были объявлены до их вызова)
# ---------------------------------------------

face_service = FaceService()
access_face_verifier = AccessFaceVerifier(basedir)
access_face_verify_queue = queue.Queue()
access_face_verify_queued = set()
access_face_verify_lock = threading.Lock()
access_face_verify_worker_started = False
access_face_index_prewarm_started = False
ACCESS_FACE_IDENTIFICATION_VERSION = 2
photo_thumbnail_lock = threading.Lock()

# RTSP Настройки камеры Ezviz (Замените ВАШ_ПАРОЛЬ на реальный пароль от камеры)
RTSP_URL = "rtsp://admin:UNZKZK@192.168.100.3:554/h264_stream"

# Глобальный объект для управления источником камеры (None = из настроек БД)
CAMERA_OVERRIDE_SOURCE = None

# Глобальный кеш шрифта
GLOBAL_FONT = None

def get_cached_font():
    global GLOBAL_FONT
    if GLOBAL_FONT is not None:
        return GLOBAL_FONT
    
    font_candidates = ["arial.ttf", "C:\\Windows\\Fonts\\arial.ttf", "C:\\Windows\\Fonts\\tahoma.ttf", "tahoma.ttf"]
    for path in font_candidates:
        try:
            GLOBAL_FONT = ImageFont.truetype(path, 40)
            return GLOBAL_FONT
        except: continue
    GLOBAL_FONT = ImageFont.load_default()
    return GLOBAL_FONT


def normalize_email(value):
    return (value or '').strip().lower()


def token_hash(value):
    return hashlib.sha256((value or '').encode('utf-8')).hexdigest()


def absolute_url(endpoint, **values):
    return url_for(endpoint, _external=True, **values)


def get_google_redirect_uri():
    return absolute_url('google_callback')


def smtp_configured():
    required = ['SMTP_HOST', 'SMTP_PORT', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'MAIL_FROM']
    return all((os.environ.get(key) or '').strip() for key in required)


def send_email_message(to_email, subject, body):
    if not smtp_configured():
        raise RuntimeError('SMTP не настроен. Укажите SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD и MAIL_FROM.')

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = os.environ.get('MAIL_FROM')
    msg['To'] = to_email
    msg.set_content(body)

    host = os.environ.get('SMTP_HOST')
    port = int(os.environ.get('SMTP_PORT', '587') or 587)
    username = os.environ.get('SMTP_USERNAME')
    password = os.environ.get('SMTP_PASSWORD')
    use_ssl = (os.environ.get('SMTP_USE_SSL') or '').strip().lower() in ('1', 'true', 'yes')

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=20) as server:
            server.login(username, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(msg)


def redirect_after_login(user):
    if user.role == 'payment_admin':
        return '/mobile-payments'
    if user.role == 'teacher':
        return '/teacher-attendance'
    return '/dashboard'


def get_public_payment_methods(settings=None):
    settings = settings or get_club_settings_instance()
    methods = [
        {
            'key': 'click',
            'name': 'Click',
            'enabled': bool(getattr(settings, 'payment_click_enabled', False)),
            'qr_url': getattr(settings, 'payment_click_qr_url', None),
            'logo_url': url_for('static', filename='uploads/click.png'),
        },
        {
            'key': 'payme',
            'name': 'Payme',
            'enabled': bool(getattr(settings, 'payment_payme_enabled', False)),
            'qr_url': getattr(settings, 'payment_payme_qr_url', None),
            'logo_url': url_for('static', filename='uploads/payme.png'),
        },
        {
            'key': 'uzum',
            'name': 'Uzum',
            'enabled': bool(getattr(settings, 'payment_uzum_enabled', False)),
            'qr_url': getattr(settings, 'payment_uzum_qr_url', None),
            'logo_url': url_for('static', filename='uploads/uzum.png'),
        },
        {
            'key': 'paynet',
            'name': 'Paynet',
            'enabled': bool(getattr(settings, 'payment_paynet_enabled', False)),
            'qr_url': getattr(settings, 'payment_paynet_qr_url', None),
            'logo_url': url_for('static', filename='uploads/paynet.png'),
        },
        {
            'key': 'multicard',
            'name': 'Multicard',
            'enabled': bool(getattr(settings, 'payment_multicard_enabled', False)),
            'qr_url': getattr(settings, 'payment_multicard_qr_url', None),
            'logo_url': url_for('static', filename='uploads/multicard.png'),
        },
        {
            'key': 'oson',
            'name': 'Oson',
            'enabled': bool(getattr(settings, 'payment_oson_enabled', False)),
            'qr_url': getattr(settings, 'payment_oson_qr_url', None),
            'logo_url': url_for('static', filename='uploads/oson.jpeg'),
        },
    ]
    return methods

class VideoCamera(object):
    def __init__(self, url):
        # Если url похож на индекс камеры (0, 1...), превращаем в int
        try:
            if isinstance(url, str) and (url.isdigit() or (url.startswith('-') and url[1:].isdigit())):
                camera_id = int(url)
            else:
                camera_id = url
        except Exception:
            camera_id = url

        self.camera_id = camera_id
        self.video = None
        self.last_frame = None
        self.lock = threading.Lock()
        self.is_running = True
        self.error_count = 0
        
        # Настройки вывода
        self.output_settings = {
            'resolution': '720p',
            'quality': 70
        }
        
        # Запуск системы анализа лиц
        face_service.start()
        
        # Поток для захвата (выделяем VideoCapture сюда, чтобы не вешать главный поток)
        self.thread = threading.Thread(target=self._update, args=())
        self.thread.daemon = True
        self.thread.start()

    def _update(self):
        # Инициализация камеры внутри потока
        print(f"⚙️ Поток захвата ({self.camera_id}) запущен")
        while self.is_running:
            try:
                if self.video and self.video.isOpened():
                    # Для RTSP важно вычитывать буфер постоянно
                    ret, frame = self.video.read()
                    if ret:
                        with self.lock:
                            self.last_frame = frame
                        # Ограничиваем очередь ИИ, чтобы он не захлебнулся
                        face_service.process_frame(frame)
                        self.error_count = 0
                    else:
                        self.error_count += 1
                        if self.error_count > 10:
                            self.video.release()
                            self.video = None
                else:
                    self._open_capture()
                    time.sleep(0.5)
            except Exception as e:
                print(f"❌ Ошибка в цикле камеры {self.camera_id}: {e}")
                time.sleep(1)
            time.sleep(0.01)
            
        # Конец цикла - освобождаем ресурсы
        if self.video:
            self.video.release()
            self.video = None
        print(f"🛑 Поток захвата ({self.camera_id}) полностью остановлен")

    def _open_capture(self):
        """Внутренний метод открытия видеозахвата"""
        try:
            print(f"🔄 Открытие видео-захвата: {self.camera_id}")
            # Оптимизация для RTSP / EZVIZ
            if isinstance(self.camera_id, str) and "rtsp" in self.camera_id:
                # Настройки устанавливаются ДО открытия Capture
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp|reorder_queue_size;100|max_delay;500000"
                self.video = cv2.VideoCapture(self.camera_id, cv2.CAP_FFMPEG)
                self.video.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            else:
                # Для Windows DirectShow часто лучше для веб-камер
                if isinstance(self.camera_id, int) and os.name == 'nt':
                    self.video = cv2.VideoCapture(self.camera_id, cv2.CAP_DSHOW)
                else:
                    self.video = cv2.VideoCapture(self.camera_id)

            if self.video and self.video.isOpened():
                print(f"✅ Камера {self.camera_id} успешно открыта")
                if isinstance(self.camera_id, int):
                    self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                    self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                    self.video.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            else:
                print(f"❌ Не удалось открыть камеру {self.camera_id}")
                self.video = None
        except Exception as e:
            print(f"❌ Критическая ошибка открытия камеры: {e}")
            self.video = None

    def get_frame(self, draw_faces=True):
        frame = None
        with self.lock:
            if self.last_frame is not None:
                frame = self.last_frame.copy()
        
        provider_name = "CPU (Slow)"
        try:
            if face_service.gpu_active:
                if 'TensorrtExecutionProvider' in face_service.providers:
                    provider_name = "TensorRT (Super Rocket!)"
                else:
                    provider_name = "CUDA (Rocket!)"
        except: pass

        if frame is None:
            black_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            cv2.putText(black_frame, "Loading camera...", (450, 340), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 2)
            cv2.putText(black_frame, f"Engine: {provider_name}", (450, 400), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 1)
            ret, jpeg = cv2.imencode('.jpg', black_frame)
            return jpeg.tobytes() if ret else None, None

        faces, fps = face_service.get_latest_results()
        
        if draw_faces and faces:
            # Отрисовка с кешированным шрифтом
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(frame_rgb)
            draw = ImageDraw.Draw(img_pil)
            font = get_cached_font()

            for face in faces:
                bbox = face['bbox']
                name = face['name']
                color_pil = (0, 255, 0) if face['is_recognized'] else (255, 0, 0)
                
                draw.rectangle([bbox[0], bbox[1], bbox[2], bbox[3]], outline=color_pil, width=4)
                text_bbox = draw.textbbox((bbox[0], bbox[1]-55), name, font=font)
                draw.rectangle([text_bbox[0]-5, text_bbox[1]-5, text_bbox[2]+10, text_bbox[3]+5], fill=color_pil)
                draw.text((bbox[0], bbox[1]-55), name, font=font, fill=(255, 255, 255))
            
            frame = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

        cv2.putText(frame, f"AI FPS: {fps:.1f}", (20, 50), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
        cv2.putText(frame, f"Engine: {provider_name}", (20, 100), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 0), 2)

        target_width = 1280
        if self.output_settings['resolution'] == '1080p': target_width = 1920
        elif self.output_settings['resolution'] == '2k': target_width = 2560
        
        h, w = frame.shape[:2]
        if w != target_width:
            scale = target_width / w
            frame = cv2.resize(frame, (target_width, int(h * scale)))

        ret, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, self.output_settings['quality']])
        return (jpeg.tobytes(), frame) if ret else (None, None)

    def _mark_attendance_optimized(self, student_id, name):
        """
        Удалено в пользу отметки через JS.
        Теперь отметка происходит в фоне только если JS неактивен (опционально)
        Для чистоты интерфейса оставляем управление браузеру.
        """
        pass

    def stop(self):
        print(f"⏳ Запрос на остановку камеры {self.camera_id}...")
        self.is_running = False
        # Освобождаем видео сразу, чтобы разблокировать .read() если он завис
        if self.video:
            self.video.release()
            self.video = None


# Глобальный объект камеры
global_camera = None
camera_lock = threading.Lock()

def get_camera():
    global global_camera, CAMERA_OVERRIDE_SOURCE
    with camera_lock:
        # Определяем URL/ID камеры
        if CAMERA_OVERRIDE_SOURCE is not None:
            db_url = CAMERA_OVERRIDE_SOURCE
        else:
            try:
                settings = get_club_settings_instance()
                db_url = settings.rtsp_url if settings.rtsp_url else RTSP_URL
            except Exception:
                db_url = RTSP_URL

        if global_camera is None:
            global_camera = VideoCamera(db_url)
        elif str(global_camera.camera_id) != str(db_url):
            print(f"🔄 Смена источника: {global_camera.camera_id} -> {db_url}")
            global_camera.stop()
            time.sleep(1.5) # Даем время на освобождение устройства
            global_camera = VideoCamera(db_url)
            
        return global_camera

def gen_frames(camera):
    while camera.is_running:
        frame_bytes, _ = camera.get_frame(draw_faces=True)
        if frame_bytes:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n\r\n')
        else:
            time.sleep(0.5) # Ждем дольше, если кадров нет совсем
            continue
        # Минимальная задержка для отзывчивости
        time.sleep(0.03) # ~30 FPS

@app.route('/video_feed')
def video_feed():
    """MJPEG поток видео с RTSP камеры"""
    try:
        return Response(gen_frames(get_camera()),
                        mimetype='multipart/x-mixed-replace; boundary=frame')
    except Exception as e:
        print(f"❌ Ошибка видео-фида: {e}")
        return "Video feed error", 500

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


DAY_LABELS = {
    1: 'Пн', 2: 'Вт', 3: 'Ср', 4: 'Чт', 5: 'Пт', 6: 'Сб', 7: 'Вс'
}

SERVICE_PRIMARY_KEY = os.environ.get('SERVICE_PRIMARY_KEY', 'football_club')
SERVICE_SUPPORT_PHONE_DEFAULT = os.environ.get('SERVICE_SUPPORT_PHONE', '+998994067406')
SERVICE_STATE_CACHE_TTL_SECONDS = float(os.environ.get('SERVICE_STATE_CACHE_TTL_SECONDS', '5'))
SERVICE_STATE_CACHE = {'payload': None, 'expires_at': 0.0}
SERVICE_STATE_CACHE_LOCK = threading.Lock()
SERVICE_LABELS = {
    'football_club': 'Футбольный клуб'
}
RU_MONTHS = {
    1: 'январь',
    2: 'февраль',
    3: 'март',
    4: 'апрель',
    5: 'май',
    6: 'июнь',
    7: 'июль',
    8: 'август',
    9: 'сентябрь',
    10: 'октябрь',
    11: 'ноябрь',
    12: 'декабрь'
}


def ensure_payment_type_column():
    """Проверяет служебные колонки таблицы payments."""
    try:
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        
        if 'payments' not in tables:
            db.create_all()
            return
        
        columns = {col['name'] for col in inspector.get_columns('payments')}
        
        if 'payment_type' not in columns:
            try:
                db.session.execute(db.text("ALTER TABLE payments ADD COLUMN payment_type VARCHAR(20) DEFAULT 'cash'"))
                # Обновить существующие записи
                db.session.execute(db.text("UPDATE payments SET payment_type = 'cash' WHERE payment_type IS NULL"))
                db.session.commit()
                print("✓ Добавлена колонка payment_type в таблицу payments")
            except Exception as e:
                db.session.rollback()
                if "duplicate column" not in str(e).lower() and "already exists" not in str(e).lower():
                    print(f"Ошибка при добавлении payment_type: {e}")

        # Старые платежи нельзя достоверно датировать задним числом, поэтому
        # оставляем created_at у них NULL. Новые записи заполняются моделью.
        if 'created_at' not in columns:
            try:
                db.session.execute(db.text("ALTER TABLE payments ADD COLUMN created_at TIMESTAMP NULL"))
                db.session.execute(db.text("CREATE INDEX IF NOT EXISTS idx_payments_created_at ON payments (created_at)"))
                db.session.commit()
                print("✓ Добавлена фактическая дата создания платежа")
            except Exception as e:
                db.session.rollback()
                if "duplicate column" not in str(e).lower() and "already exists" not in str(e).lower():
                    print(f"Ошибка при добавлении payments.created_at: {e}")
    except Exception as e:
        print(f"Ошибка при проверке колонки payment_type: {e}")


def get_club_settings_instance():
    """Получить настройки клуба (теперь без лишних проверок БД)"""
    try:
        settings = ClubSettings.query.first()
    except Exception:
        db.session.rollback()
        ensure_club_settings_columns()
        db.session.rollback()
        settings = ClubSettings.query.first()
    if not settings:
        settings = ClubSettings(system_name='FK QORASUV')
        db.session.add(settings)
        db.session.commit()
    return settings


def get_bridge_key(settings=None):
    settings = settings or get_club_settings_instance()
    configured = (getattr(settings, 'hikvision_device_key', '') or '').strip()
    return configured or (os.environ.get('DEVICE_INGEST_KEY') or '').strip()


def default_hikvision_devices():
    return [
        {'name': 'entry', 'ip': '192.168.68.107', 'protocol': 'https', 'port': 443, 'doorNo': 1},
        {'name': 'exit', 'ip': '192.168.68.104', 'protocol': 'https', 'port': 443, 'doorNo': 1},
    ]


def check_bridge_auth():
    expected = get_bridge_key()
    provided = (
        request.headers.get('x-device-key')
        or request.headers.get('X-Device-Key')
        or request.args.get('key')
        or ''
    ).strip()
    return bool(expected and provided and provided == expected)


def queue_hikvision_sync(reason='change'):
    """Попросить локальный bridge выполнить синхронизацию без ожидания интервала."""
    try:
        ensure_device_commands_table()

        now = get_local_datetime()
        stale_before = now - timedelta(minutes=30)

        stale_processing = DeviceCommand.query.filter(
            DeviceCommand.command == 'HIKVISION_SYNC',
            DeviceCommand.status == 'processing',
            DeviceCommand.picked_at < stale_before
        ).all()
        for old_cmd in stale_processing:
            old_cmd.status = 'failed'
            old_cmd.result = 'Команда зависла и была закрыта перед постановкой новой синхронизации.'
            old_cmd.finished_at = now

        pending_cmd = DeviceCommand.query.filter(
            DeviceCommand.command == 'HIKVISION_SYNC',
            DeviceCommand.status == 'pending'
        ).order_by(DeviceCommand.created_at.desc()).first()
        if pending_cmd:
            pending_cmd.set_payload({'reason': reason, 'merged': True})
            pending_cmd.result = f'Объединено с более новой причиной: {reason}'
            pending_cmd.created_at = now
            return

        cmd = DeviceCommand(command='HIKVISION_SYNC')
        cmd.set_payload({'reason': reason})
        db.session.add(cmd)
    except Exception as e:
        print(f"Не удалось поставить команду синхронизации Hikvision: {e}")


def queue_hikvision_person(person_type, person_id=None, reason='change', action='upsert', employee_no=None):
    """Поставить точечную команду bridge для одного ученика или сотрудника."""
    try:
        ensure_device_commands_table()

        payload = {
            'reason': reason,
            'action': action,
            'person_type': person_type,
        }
        if person_id is not None:
            payload['person_id'] = int(person_id)
        if employee_no:
            payload['employeeNo'] = str(employee_no)

        now = get_local_datetime()
        stale_before = now - timedelta(minutes=30)

        stale_processing = DeviceCommand.query.filter(
            DeviceCommand.command == 'HIKVISION_PERSON',
            DeviceCommand.status == 'processing',
            DeviceCommand.picked_at < stale_before
        ).all()
        for old_cmd in stale_processing:
            old_cmd.status = 'failed'
            old_cmd.result = 'Точечная команда зависла и была закрыта перед постановкой новой команды.'
            old_cmd.finished_at = now

        pending_commands = DeviceCommand.query.filter(
            DeviceCommand.command == 'HIKVISION_PERSON',
            DeviceCommand.status == 'pending'
        ).all()
        for pending in pending_commands:
            pending_payload = pending.get_payload()
            same_person = (
                pending_payload.get('person_type') == person_type and
                (
                    (person_id is not None and pending_payload.get('person_id') == int(person_id)) or
                    (employee_no and str(pending_payload.get('employeeNo')) == str(employee_no))
                )
            )
            if same_person:
                pending.set_payload(payload)
                pending.result = f'Обновлено более новой точечной командой: {reason}'
                pending.created_at = now
                return

        cmd = DeviceCommand(command='HIKVISION_PERSON')
        cmd.set_payload(payload)
        db.session.add(cmd)
    except Exception as e:
        print(f"Не удалось поставить точечную команду Hikvision: {e}")


def queue_hikvision_door_open(device_name):
    """Поставить срочную команду bridge на открытие двери терминала."""
    try:
        ensure_device_commands_table()
        device_name = (device_name or '').strip()
        if device_name not in {'entry', 'exit'}:
            raise ValueError('Unknown Hikvision device')

        cmd = DeviceCommand(command='HIKVISION_DOOR_OPEN')
        cmd.set_payload({
            'device_name': device_name,
            'reason': 'manual_door_open',
            'requested_at': get_local_datetime().isoformat(),
        })
        db.session.add(cmd)
    except Exception as e:
        print(f"Не удалось поставить команду открытия турникета Hikvision: {e}")
        raise


def queue_hikvision_clear_device(device_name):
    """Поставить команду bridge на полную очистку памяти выбранного терминала."""
    try:
        ensure_device_commands_table()
        device_name = (device_name or '').strip()
        if device_name not in {'entry', 'exit'}:
            raise ValueError('Unknown Hikvision device')

        cmd = DeviceCommand(command='HIKVISION_CLEAR_DEVICE')
        cmd.set_payload({
            'device_name': device_name,
            'reason': 'manual_device_clear',
            'requested_at': get_local_datetime().isoformat(),
        })
        db.session.add(cmd)
    except Exception as e:
        print(f"Не удалось поставить команду очистки терминала Hikvision: {e}")
        raise


def queue_hikvision_control(action):
    """Поставить срочную команду управления текущей работой bridge."""
    try:
        ensure_device_commands_table()
        action = (action or '').strip()
        if action not in {'pause', 'resume', 'stop', 'restart', 'update'}:
            raise ValueError('Unknown bridge control action')

        cmd = DeviceCommand(command='HIKVISION_CONTROL')
        cmd.set_payload({
            'action': action,
            'reason': f'bridge_{action}',
            'requested_at': get_local_datetime().isoformat(),
        })
        db.session.add(cmd)
    except Exception as e:
        print(f"Не удалось поставить команду управления Hikvision bridge: {e}")
        raise


def get_month_paid_map(year, month):
    rows = db.session.query(
        Payment.student_id,
        func.coalesce(func.sum(Payment.amount_paid), 0)
    ).filter(
        Payment.payment_year == year,
        Payment.payment_month == month
    ).group_by(Payment.student_id).all()
    return {student_id: float(total or 0) for student_id, total in rows}


def get_payment_date_paid_map(year, month):
    start_dt = datetime(year, month, 1)
    end_dt = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    rows = db.session.query(
        Payment.student_id,
        func.coalesce(func.sum(Payment.amount_paid), 0)
    ).filter(
        Payment.payment_date >= start_dt,
        Payment.payment_date < end_dt
    ).group_by(Payment.student_id).all()
    return {student_id: float(total or 0) for student_id, total in rows}


def get_access_payment_policy(settings):
    policy = (getattr(settings, 'access_payment_policy', None) or 'partial_current_month').strip()
    allowed = {'full_current_month', 'partial_current_month', 'any_payment_this_month'}
    return policy if policy in allowed else 'partial_current_month'


def get_hikvision_daily_sync_time(settings):
    value = (getattr(settings, 'hikvision_daily_sync_time', None) or '03:00').strip()
    if re.match(r'^\d{2}:\d{2}$', value):
        hour, minute = map(int, value.split(':'))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return value
    return '03:00'


def should_check_access_debt(settings, today=None):
    today = today or get_local_date()
    block_day = int(getattr(settings, 'access_block_day', 10) or 10)
    block_day = max(1, min(31, block_day))
    start_year = getattr(settings, 'access_debt_start_year', None)
    start_month = getattr(settings, 'access_debt_start_month', None)
    if start_year and start_month and (today.year, today.month) < (int(start_year), int(start_month)):
        return False
    return today.day >= block_day


def get_access_max_debt_months(settings):
    try:
        value = int(getattr(settings, 'access_max_debt_months', 0) or 0)
    except (TypeError, ValueError):
        value = 0
    return max(0, min(36, value))


def get_effective_access_max_debt_months(settings):
    value = get_access_max_debt_months(settings)
    if get_access_payment_policy(settings) == 'any_payment_this_month':
        return max(1, value)
    return 0


def normalize_month_pair(year, month):
    if not year or not month:
        return None
    try:
        year = int(year)
        month = int(month)
    except (TypeError, ValueError):
        return None
    if month < 1 or month > 12:
        return None
    return year, month


def iter_month_pairs(start_year, start_month, end_year, end_month):
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        yield year, month
        month += 1
        if month > 12:
            month = 1
            year += 1


MIN_LESSONS_FOR_DEBT_DEFAULT = 4


def get_access_open_until(settings=None):
    """До какой даты включительно пускаем всех без проверки оплаты."""
    settings = settings or get_club_settings_instance()
    value = getattr(settings, 'access_open_until', None)
    if isinstance(value, datetime):
        return value.date()
    return value


def is_access_open_day(settings=None, today=None):
    """Сегодня действует режим "пропустить всех"?"""
    open_until = get_access_open_until(settings)
    if not open_until:
        return False
    return (today or get_local_date()) <= open_until


def get_min_lessons_for_debt(settings=None):
    """Со скольких посещений месяц вообще считается долговым."""
    settings = settings or get_club_settings_instance()
    value = getattr(settings, 'min_lessons_for_debt', None)
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = MIN_LESSONS_FOR_DEBT_DEFAULT
    return max(0, value)


def get_attendance_counts_by_month(student_ids, year_from=None):
    """(student_id, year, month) -> сколько занятий посетил."""
    ids = [int(value) for value in student_ids if value is not None]
    if not ids:
        return {}
    query = db.session.query(
        Attendance.student_id,
        func.extract('year', Attendance.date),
        func.extract('month', Attendance.date),
        func.count(func.distinct(Attendance.date))
    ).filter(Attendance.student_id.in_(ids), Attendance.date.isnot(None))
    if year_from:
        query = query.filter(func.extract('year', Attendance.date) >= int(year_from))
    rows = query.group_by(
        Attendance.student_id,
        func.extract('year', Attendance.date),
        func.extract('month', Attendance.date)
    ).all()
    return {
        (int(student_id), int(year), int(month)): int(count or 0)
        for student_id, year, month, count in rows
    }


def month_is_chargeable(student_id, year, month, attendance_counts, min_lessons):
    """Месяц без занятий долгом не считаем: ученик просто не ходил."""
    if min_lessons <= 0:
        return True
    visits = attendance_counts.get((int(student_id), int(year), int(month)), 0)
    return visits >= min_lessons


def get_discount_months(student_ids, year_from=None):
    """Месяцы, закрытые скидкой: {(student_id, year, month)}.

    Если за месяц есть хотя бы одна оплата с отметкой скидки, остаток
    по этому месяцу долгом не считается — так закрываются приход в
    середине месяца, разовые договоренности и прощенные хвосты.
    """
    ids = [int(value) for value in student_ids if value is not None]
    if not ids or not ensure_payment_columns():
        return set()
    try:
        query = db.session.query(
            Payment.student_id, Payment.payment_year, Payment.payment_month
        ).filter(
            Payment.student_id.in_(ids),
            Payment.is_discount.is_(True),
            Payment.payment_year.isnot(None),
            Payment.payment_month.isnot(None),
        )
        if year_from:
            query = query.filter(Payment.payment_year >= int(year_from))
        return {
            (int(student_id), int(year), int(month))
            for student_id, year, month in query.all()
        }
    except Exception as exc:
        print(f'get_discount_months failed: {type(exc).__name__}: {exc}')
        return set()


def get_student_month_due(student, year, month, tariff_price=None):
    """Сколько ученик должен за конкретный месяц по тарифу.

    Скидки сюда не входят: они привязаны к оплате и применяются там,
    где считается долг, — см. get_discount_months.
    """
    if tariff_price is None:
        tariff_price = float(student.tariff.price or 0) if student.tariff else 0
    return float(tariff_price)


def get_students_month_dues(students, year, month, settings=None, apply_attendance_rule=True):
    """Сколько ждем от каждого ученика за конкретный месяц.

    Единая точка для всей статистики, чтобы цифры совпадали с тем,
    что показывает карточка ученика и правила турникета:
      - за месяц поступления берем согласованную сумму, а не полный тариф;
      - месяц, в котором ученик почти не появлялся, оплаты не ждет;
      - архивные и неактивные сюда не попадают: их отсеивают запросы выше.
    """
    settings = settings or get_club_settings_instance()
    students = [student for student in students if student is not None]
    if not students:
        return {}

    student_ids = [student.id for student in students]
    min_lessons = get_min_lessons_for_debt(settings) if apply_attendance_rule else 0
    attendance_counts = (
        get_attendance_counts_by_month(student_ids, year) if min_lessons else {}
    )
    discount_months = get_discount_months(student_ids, year)
    paid_rows = db.session.query(
        Payment.student_id, func.coalesce(func.sum(Payment.amount_paid), 0)
    ).filter(
        Payment.student_id.in_(student_ids),
        Payment.payment_year == year,
        Payment.payment_month == month,
    ).group_by(Payment.student_id).all() if student_ids else []
    paid_by_student = {int(sid): float(total or 0) for sid, total in paid_rows}

    dues = {}
    for student in students:
        if student.club_funded or not student.tariff:
            dues[student.id] = 0.0
            continue
        if min_lessons and not month_is_chargeable(student.id, year, month, attendance_counts, min_lessons):
            dues[student.id] = 0.0
            continue
        if (student.id, year, month) in discount_months:
            # Со скидкой ждем ровно столько, сколько уже внесли
            dues[student.id] = paid_by_student.get(student.id, 0.0)
            continue
        dues[student.id] = float(get_student_month_due(student, year, month))
    return dues


def get_student_debt_start_pair(student, settings, today=None):
    today = today or get_local_date()
    candidates = []

    global_start = normalize_month_pair(
        getattr(settings, 'access_debt_start_year', None),
        getattr(settings, 'access_debt_start_month', None)
    )
    if global_start:
        candidates.append(global_start)

    if getattr(student, 'admission_date', None):
        candidates.append((student.admission_date.year, student.admission_date.month))
    else:
        candidates.append((today.year, 1))

    return max(candidates)


def get_debt_month_counts(students, settings=None, today=None, include_current=True):
    settings = settings or get_club_settings_instance()
    today = today or get_local_date()
    students = [student for student in students if student and student.tariff and not student.club_funded]
    if not students:
        return {}

    start_pairs = {
        student.id: get_student_debt_start_pair(student, settings, today)
        for student in students
    }
    min_start_year = min(pair[0] for pair in start_pairs.values())
    student_ids = [student.id for student in students]
    min_lessons = get_min_lessons_for_debt(settings)
    attendance_counts = get_attendance_counts_by_month(student_ids, min_start_year) if min_lessons else {}
    discount_months = get_discount_months(student_ids, min_start_year)

    paid_rows = db.session.query(
        Payment.student_id,
        Payment.payment_year,
        Payment.payment_month,
        func.coalesce(func.sum(Payment.amount_paid), 0)
    ).filter(
        Payment.student_id.in_(student_ids),
        Payment.payment_year.isnot(None),
        Payment.payment_month.isnot(None),
        Payment.payment_year >= min_start_year,
        Payment.payment_year <= today.year
    ).group_by(
        Payment.student_id,
        Payment.payment_year,
        Payment.payment_month
    ).all()
    paid_by_month = {
        (student_id, year, month): float(total or 0)
        for student_id, year, month, total in paid_rows
    }

    counts = {}
    for student in students:
        start_year, start_month = start_pairs[student.id]
        if (start_year, start_month) > (today.year, today.month):
            counts[student.id] = 0
            continue

        tariff_price = float(student.tariff.price or 0)
        count = 0
        end_year, end_month = today.year, today.month
        if not include_current:
            end_month -= 1
            if end_month < 1:
                end_month = 12
                end_year -= 1
        if (start_year, start_month) > (end_year, end_month):
            counts[student.id] = 0
            continue

        for year, month in iter_month_pairs(start_year, start_month, end_year, end_month):
            paid = paid_by_month.get((student.id, year, month), 0)
            due = get_student_month_due(student, year, month, tariff_price)
            if not month_is_chargeable(student.id, year, month, attendance_counts, min_lessons):
                continue
            if (student.id, year, month) in discount_months:
                continue
            if max(0, due - paid) > 0:
                count += 1
        counts[student.id] = count

    return counts


def student_access_state(student, settings=None, paid_map=None, payment_date_paid_map=None, today=None,
                         debt_month_count=None, discount_months=None, attendance_counts=None):
    settings = settings or get_club_settings_instance()
    today = today or get_local_date()
    paid_map = paid_map or {}
    payment_date_paid_map = payment_date_paid_map or {}

    if student.status != 'active':
        return False, 'inactive', 0
    # Режим "пропустить всех": действует до указанной даты включительно
    if is_access_open_day(settings, today):
        return True, 'open_day', 0
    if student.club_funded:
        return True, 'club_funded', 0
    if not student.tariff:
        return True, 'no_tariff', 0
    if not should_check_access_debt(settings, today):
        return True, 'grace_period', 0

    # Месяц без занятий долгом не считаем: ученик просто не приходил
    min_lessons = get_min_lessons_for_debt(settings)
    if min_lessons:
        if attendance_counts is None:
            attendance_counts = get_attendance_counts_by_month([student.id], today.year)
        visits = attendance_counts.get((student.id, today.year, today.month), 0)
        if visits < min_lessons and not float(paid_map.get(student.id, 0) or 0):
            if debt_month_count is None:
                debt_month_count = get_debt_month_counts(
                    [student], settings, today, include_current=False
                ).get(student.id, 0)
            if debt_month_count <= get_access_max_debt_months(settings):
                return True, 'no_lessons_this_month', 0

    # Месяц, закрытый скидкой, долгом не считаем
    if discount_months is None:
        discount_months = get_discount_months([student.id], today.year)
    if (student.id, today.year, today.month) in discount_months:
        if debt_month_count is None:
            debt_month_count = get_debt_month_counts(
                [student], settings, today, include_current=False
            ).get(student.id, 0)
        if debt_month_count <= get_access_max_debt_months(settings):
            return True, 'month_discounted', 0

    tariff_price = get_student_month_due(student, today.year, today.month)
    paid = float(paid_map.get(student.id, 0) or 0)
    paid_by_date = float(payment_date_paid_map.get(student.id, 0) or 0)
    debt = max(0, tariff_price - paid)
    policy = get_access_payment_policy(settings)
    max_debt_months = get_access_max_debt_months(settings)

    if policy == 'partial_current_month':
        if debt_month_count is None:
            debt_month_count = get_debt_month_counts([student], settings, today, include_current=False).get(student.id, 0)
        if debt_month_count > 0:
            return False, 'too_many_debt_months', debt

    if policy == 'full_current_month':
        if debt > 0:
            return False, 'current_month_debt', debt
        return True, 'paid_full_current_month', 0

    if policy == 'any_payment_this_month':
        max_debt_months = max(1, max_debt_months)
        if debt_month_count is None:
            debt_month_count = get_debt_month_counts([student], settings, today, include_current=False).get(student.id, 0)
        if debt_month_count > max_debt_months:
            return False, 'too_many_debt_months', debt
        if paid > 0 or paid_by_date > 0:
            return True, 'any_payment_this_month', debt
        return False, 'no_payment_this_month', debt

    if paid > 0:
        return True, 'partial_current_month', debt
    return False, 'no_current_month_payment', debt


ACCESS_REASON_LABELS = {
    'allowed': 'Допуск разрешен',
    'inactive': 'Ученик не активен',
    'blacklist': 'Ученик в черном списке',
    'club_funded': 'Клубное финансирование',
    'no_tariff': 'Тариф не указан, блокировка по оплате не применяется',
    'grace_period': 'Льготный период до дня блокировки',
    'current_month_debt': 'Есть долг за текущий месяц',
    'paid_full_current_month': 'Месяц оплачен полностью',
    'any_payment_this_month': 'Есть оплата в этом месяце',
    'no_payment_this_month': 'Нет оплаты в этом месяце',
    'partial_current_month': 'Есть оплата за этот месяц',
    'no_current_month_payment': 'Нет оплаты за текущий месяц',
    'no_lessons_this_month': 'В этом месяце занятий не было',
    'month_discounted': 'Месяц закрыт скидкой',
    'open_day': 'Открытый день: пускаем всех',
    'too_many_debt_months': 'Долг больше разрешенного срока',
    'no_photo': 'Нет фото для Face ID',
    'staff_active': 'Сотрудник активен',
    'staff_inactive': 'Сотрудник неактивен',
}


def build_student_access_payload(student, settings=None, paid_map=None, payment_date_paid_map=None, today=None,
                                 debt_month_count=None, discount_months=None, attendance_counts=None):
    settings = settings or get_club_settings_instance()
    today = today or get_local_date()
    paid_map = paid_map or {}
    payment_date_paid_map = payment_date_paid_map or {}
    policy = get_access_payment_policy(settings)
    if debt_month_count is None and policy in {'partial_current_month', 'any_payment_this_month'} and not student.club_funded:
        debt_month_count = get_debt_month_counts([student], settings, today, include_current=False).get(student.id, 0)
    allowed, reason, debt = student_access_state(
        student,
        settings,
        paid_map,
        payment_date_paid_map,
        today,
        debt_month_count=debt_month_count,
        discount_months=discount_months,
        attendance_counts=attendance_counts
    )
    photo_url = build_photo_url(student.photo_path)
    can_sync_to_turnstile = bool(allowed and photo_url)
    final_reason = reason if allowed else reason
    if allowed and not photo_url:
        final_reason = 'no_photo'

    tariff_price = float(student.tariff.price or 0) if student.tariff else 0
    current_month_paid = float(paid_map.get(student.id, 0) or 0)
    paid_this_calendar_month = float(payment_date_paid_map.get(student.id, 0) or 0)

    return {
        'allowed': bool(allowed),
        'can_sync_to_turnstile': can_sync_to_turnstile,
        'will_pass': can_sync_to_turnstile,
        'reason': final_reason,
        'reason_label': ACCESS_REASON_LABELS.get(final_reason, final_reason),
        'policy_reason': reason,
        'access_exempt_from_payment': bool(reason == 'club_funded'),
        'debt': float(debt or 0),
        'current_month_paid': current_month_paid,
        'paid_this_calendar_month': paid_this_calendar_month,
        'tariff_price': tariff_price,
        'has_photo': bool(photo_url),
        'block_day': int(getattr(settings, 'access_block_day', 10) or 10),
        'payment_policy': policy,
        'max_debt_months': get_effective_access_max_debt_months(settings),
        'debt_month_count': int(debt_month_count or 0),
        'month': today.month,
        'year': today.year,
    }


def build_hikvision_person_payload(person_type, person_id, settings=None, today=None, paid_map=None, payment_date_paid_map=None, debt_month_counts=None):
    """Собрать одну запись в формате локального Hikvision bridge."""
    settings = settings or get_club_settings_instance()
    today = today or get_local_date()
    base_url = request.host_url.rstrip('/')

    if person_type == 'staff':
        user = db.session.get(User, int(person_id))
        if not user:
            return None
        photo_url = build_photo_url(user.photo_path)
        if photo_url and photo_url.startswith('/'):
            photo_url = f"{base_url}{photo_url}"
        allowed = bool(user.is_active)
        reason = 'staff_active' if allowed else 'staff_inactive'
        final_reason = 'no_photo' if allowed and not photo_url else reason
        face_photo_url = (
            f"{base_url}/api/hikvision/face-photo?person_type=staff&person_id={user.id}"
            if photo_url else None
        )
        return {
            'student_id': None,
            'user_id': user.id,
            'person_type': 'staff',
            'employeeNo': f"900000{user.id}",
            'fullName': user.full_name or user.username,
            'group': 'Сотрудники клуба',
            'photoUrl': photo_url,
            'facePhotoUrl': face_photo_url,
            'photoHash': photo_signature(user.photo_path),
            'enabled': bool(allowed and photo_url),
            'access_allowed': allowed,
            'access_reason': final_reason,
            'access_reason_label': ACCESS_REASON_LABELS.get(final_reason, final_reason),
            'current_month_debt': 0,
            'current_month_paid': 0,
            'paid_this_calendar_month': 0,
            'has_photo': bool(photo_url),
            'status': 'active' if user.is_active else 'inactive',
            'student_number': None,
        }

    student = Student.query.options(
        joinedload(Student.tariff),
        joinedload(Student.group)
    ).filter(Student.id == int(person_id)).first()
    if not student:
        return None

    paid_map = paid_map if paid_map is not None else get_month_paid_map(today.year, today.month)
    payment_date_paid_map = payment_date_paid_map if payment_date_paid_map is not None else get_payment_date_paid_map(today.year, today.month)
    debt_month_count = None
    if isinstance(debt_month_counts, dict):
        debt_month_count = debt_month_counts.get(student.id)
    access_payload = build_student_access_payload(
        student,
        settings,
        paid_map,
        payment_date_paid_map,
        today,
        debt_month_count=debt_month_count
    )
    photo_url = build_photo_url(student.photo_path)
    if photo_url and photo_url.startswith('/'):
        photo_url = f"{base_url}{photo_url}"
    return {
        'student_id': student.id,
        'person_type': 'student',
        'employeeNo': str(student.id),
        'fullName': student.full_name,
        'group': student.group.name if student.group else None,
        'photoUrl': photo_url,
        'facePhotoUrl': (
            f"{base_url}/api/hikvision/face-photo?person_type=student&person_id={student.id}"
            if photo_url else None
        ),
        'photoHash': photo_signature(student.photo_path),
        'enabled': bool(access_payload['can_sync_to_turnstile']),
        'access_allowed': bool(access_payload['allowed']),
        'access_reason': access_payload['reason'],
        'access_reason_label': access_payload['reason_label'],
        'access_exempt_from_payment': access_payload['access_exempt_from_payment'],
        'current_month_debt': access_payload['debt'],
        'current_month_paid': access_payload['current_month_paid'],
        'paid_this_calendar_month': access_payload['paid_this_calendar_month'],
        'has_photo': bool(access_payload['has_photo']),
        'status': student.status,
        'student_number': student.student_number,
    }


def dedupe_hikvision_payload(items):
    """Не отправлять в терминалы явные дубли одного лица с разными ID."""
    seen = {}
    clean = []
    skipped = []
    for item in items:
        if not item.get('enabled') or not item.get('photoUrl'):
            clean.append(item)
            continue

        key = (
            item.get('person_type') or '',
            (item.get('fullName') or '').strip().lower(),
            item.get('photoUrl') or '',
        )
        if key[1] and key[2] and key in seen:
            skipped.append({
                'kept_employeeNo': seen[key].get('employeeNo'),
                'skipped_employeeNo': item.get('employeeNo'),
                'fullName': item.get('fullName'),
            })
            continue

        seen[key] = item
        clean.append(item)
    return clean, skipped


def get_default_service_controls():
    return {
        'football_club': {
            'name': SERVICE_LABELS['football_club'],
            'enabled': True,
            'support_phone': SERVICE_SUPPORT_PHONE_DEFAULT,
            'disabled_reason': 'За {month} из-за неоплаты система автоматически отключена.',
            'updated_at': None,
            'updated_by': None
        }
    }


def load_service_controls(settings):
    controls = {}
    raw_controls = getattr(settings, 'service_controls', None)
    if raw_controls:
        try:
            parsed = json.loads(raw_controls)
            if isinstance(parsed, dict):
                controls = parsed
        except Exception:
            controls = {}

    defaults = get_default_service_controls()
    merged_controls = {}
    for service_key, default_cfg in defaults.items():
        current_cfg = controls.get(service_key, {})
        if not isinstance(current_cfg, dict):
            current_cfg = {}

        merged = dict(default_cfg)
        merged.update(current_cfg)
        merged['name'] = default_cfg['name']
        merged['enabled'] = bool(merged.get('enabled', True))
        merged['support_phone'] = (merged.get('support_phone') or SERVICE_SUPPORT_PHONE_DEFAULT).strip()
        merged['disabled_reason'] = (merged.get('disabled_reason') or default_cfg['disabled_reason']).strip()
        merged_controls[service_key] = merged

    return merged_controls


def save_service_controls(settings, controls):
    settings.service_controls = json.dumps(controls, ensure_ascii=False)
    reset_service_state_cache()


def get_current_month_label():
    now = get_local_time()
    month_name = RU_MONTHS.get(now.month, str(now.month))
    return f"{month_name} {now.year}"


def build_service_state_payload(service_key=None):
    selected_key = service_key or SERVICE_PRIMARY_KEY
    settings = get_club_settings_instance()
    controls = load_service_controls(settings)
    service_cfg = controls.get(selected_key)
    if not service_cfg:
        return {
            'success': False,
            'service': selected_key,
            'message': 'Сервис не найден'
        }

    month_label = get_current_month_label()
    reason_template = service_cfg.get('disabled_reason') or 'За {month} из-за неоплаты система автоматически отключена.'
    try:
        lock_message = reason_template.format(month=month_label)
    except Exception:
        lock_message = reason_template

    enabled = bool(service_cfg.get('enabled', True))
    return {
        'success': True,
        'service': selected_key,
        'service_name': service_cfg.get('name') or SERVICE_LABELS.get(selected_key, selected_key),
        'enabled': enabled,
        'lock_active': not enabled,
        'month_label': month_label,
        'title': 'Система временно отключена',
        'message': lock_message,
        'support_phone': service_cfg.get('support_phone') or SERVICE_SUPPORT_PHONE_DEFAULT,
        'updated_at': service_cfg.get('updated_at'),
        'updated_by': service_cfg.get('updated_by')
    }


def reset_service_state_cache():
    with SERVICE_STATE_CACHE_LOCK:
        SERVICE_STATE_CACHE['payload'] = None
        SERVICE_STATE_CACHE['expires_at'] = 0.0


def get_cached_service_state_payload():
    now = time.monotonic()
    with SERVICE_STATE_CACHE_LOCK:
        if SERVICE_STATE_CACHE['payload'] is not None and now < SERVICE_STATE_CACHE['expires_at']:
            return SERVICE_STATE_CACHE['payload']
        payload = build_service_state_payload(SERVICE_PRIMARY_KEY)
        SERVICE_STATE_CACHE['payload'] = payload
        SERVICE_STATE_CACHE['expires_at'] = now + max(1.0, SERVICE_STATE_CACHE_TTL_SECONDS)
        return payload


def is_management_chat_id(chat_id, settings=None):
    chat_id_str = str(chat_id or '').strip()
    if not chat_id_str:
        return False

    st = settings or get_club_settings_instance()
    allowed_chat_ids = {
        str(getattr(st, 'director_chat_id', '') or '').strip(),
        str(getattr(st, 'founder_chat_id', '') or '').strip(),
        str(getattr(st, 'cashier_chat_id', '') or '').strip()
    }
    allowed_chat_ids.discard('')
    return chat_id_str in allowed_chat_ids


def get_owner_allowed_chat_ids():
    raw_value = (os.environ.get('OWNER_BOT_ALLOWED_CHAT_IDS') or '').strip()
    if not raw_value:
        return set()

    values = set()
    for part in raw_value.split(','):
        candidate = part.strip()
        if candidate:
            values.add(candidate)
    return values


def is_owner_chat_id(chat_id):
    chat_id_str = str(chat_id or '').strip()
    if not chat_id_str:
        return False
    return chat_id_str in get_owner_allowed_chat_ids()


def can_manage_service_from_telegram(chat_id, settings=None):
    return is_management_chat_id(chat_id, settings) or is_owner_chat_id(chat_id)


def ensure_users_table_columns():
    """Проверяет и добавляет отсутствующие колонки в таблицу users"""
    try:
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        
        if 'users' not in tables:
            db.create_all()
            return
        
        columns = {col['name'] for col in inspector.get_columns('users')}
        
        # Добавляем отсутствующие колонки
        if 'role_id' not in columns:
            try:
                db.session.execute(db.text("ALTER TABLE users ADD COLUMN role_id INTEGER"))
                db.session.commit()
                print("✓ Добавлена колонка role_id в таблицу users")
            except Exception as e:
                db.session.rollback()
                if "duplicate column" not in str(e).lower():
                    print(f"Ошибка при добавлении role_id: {e}")
        
        if 'full_name' not in columns:
            try:
                db.session.execute(db.text("ALTER TABLE users ADD COLUMN full_name VARCHAR(200)"))
                db.session.commit()
                print("✓ Добавлена колонка full_name в таблицу users")
            except Exception as e:
                db.session.rollback()
                if "duplicate column" not in str(e).lower():
                    print(f"Ошибка при добавлении full_name: {e}")

        extra_columns = {
            'phone': "ALTER TABLE users ADD COLUMN phone VARCHAR(30)",
            'email': "ALTER TABLE users ADD COLUMN email VARCHAR(255)",
            'google_sub': "ALTER TABLE users ADD COLUMN google_sub VARCHAR(255)",
            'password_reset_token_hash': "ALTER TABLE users ADD COLUMN password_reset_token_hash VARCHAR(128)",
            'password_reset_expires_at': "ALTER TABLE users ADD COLUMN password_reset_expires_at TIMESTAMP",
        }
        for column_name, statement in extra_columns.items():
            if column_name not in columns:
                try:
                    db.session.execute(db.text(statement))
                    db.session.commit()
                    print(f"✓ Добавлена колонка {column_name} в таблицу users")
                except Exception as e:
                    db.session.rollback()
                    err_text = str(e).lower()
                    if "duplicate column" not in err_text and "duplicatecolumn" not in err_text:
                        print(f"Ошибка при добавлении {column_name}: {e}")

        try:
            db.session.execute(db.text("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users (email)"))
            db.session.execute(db.text("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub ON users (google_sub)"))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Ошибка при создании индексов users: {e}")

        if 'photo_path' not in columns:
            try:
                db.session.execute(db.text("ALTER TABLE users ADD COLUMN photo_path VARCHAR(300)"))
                db.session.commit()
                print("✓ Добавлена колонка photo_path в таблицу users")
            except Exception as e:
                db.session.rollback()
                err_text = str(e).lower()
                if "duplicate column" not in err_text and "duplicatecolumn" not in err_text:
                    print(f"Ошибка при добавлении photo_path: {e}")

        if 'salary_type' not in columns:
            try:
                db.session.execute(db.text("ALTER TABLE users ADD COLUMN salary_type VARCHAR(20) DEFAULT 'fixed'"))
                db.session.commit()
                print("✓ Добавлена колонка salary_type в таблицу users")
            except Exception as e:
                db.session.rollback()
                if "duplicate column" not in str(e).lower():
                    print(f"Ошибка при добавлении salary_type: {e}")

        if 'fixed_salary' not in columns:
            try:
                db.session.execute(db.text("ALTER TABLE users ADD COLUMN fixed_salary FLOAT"))
                db.session.commit()
                print("✓ Добавлена колонка fixed_salary в таблицу users")
            except Exception as e:
                db.session.rollback()
                if "duplicate column" not in str(e).lower():
                    print(f"Ошибка при добавлении fixed_salary: {e}")
        
        if 'is_active' not in columns:
            try:
                db.session.execute(db.text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1"))
                db.session.commit()
                # Обновляем существующие записи
                db.session.execute(db.text("UPDATE users SET is_active = 1 WHERE is_active IS NULL"))
                db.session.commit()
                print("✓ Добавлена колонка is_active в таблицу users")
            except Exception as e:
                db.session.rollback()
                if "duplicate column" not in str(e).lower():
                    print(f"Ошибка при добавлении is_active: {e}")
                    
    except Exception as e:
        print(f"Ошибка при обновлении таблицы users: {e}")


def ensure_roles_tables():
    """Проверяет и создает таблицы для системы ролей"""
    try:
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        
        if 'roles' not in tables or 'role_permissions' not in tables:
            db.create_all()
        create_default_roles()
    except Exception as e:
        print(f"Ошибка при проверке таблиц ролей: {e}")


def ensure_group_trainers_table():
    """Проверяет и создает таблицу закрепления тренеров за группами"""
    try:
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        if 'group_trainers' not in tables:
            db.create_all()
            print("✓ Создана таблица group_trainers")
    except Exception as e:
        print(f"Ошибка при проверке таблицы group_trainers: {e}")


def ensure_tournament_tables():
    """Создает и аккуратно расширяет таблицы турниров, команд и стадионов."""
    try:
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        required = {
            'tournaments',
            'tournament_team_catalog',
            'tournament_team_members',
            'tournament_stadiums',
            'tournament_team_share_links',
            'tournament_entries',
            'tournament_groups',
            'tournament_fixtures',
            'tournament_match_appearances',
            'tournament_match_events',
            'tournament_awards',
        }
        if not required.issubset(set(tables)):
            db.create_all()
            print("✓ Созданы таблицы турниров")
            inspector = db.inspect(db.engine)
        tournament_columns = {col['name'] for col in inspector.get_columns('tournaments')}
        team_columns = {col['name'] for col in inspector.get_columns('tournament_team_catalog')}
        stadium_columns = {col['name'] for col in inspector.get_columns('tournament_stadiums')}
        member_columns = {col['name'] for col in inspector.get_columns('tournament_team_members')}
        entry_columns = {col['name'] for col in inspector.get_columns('tournament_entries')}
        fixture_columns = {col['name'] for col in inspector.get_columns('tournament_fixtures')}
        team_column_definitions = {
            'trainer_name': 'VARCHAR(200)',
            'trainer_photo_path': 'VARCHAR(300)',
            'administration_phone': 'VARCHAR(50)',
            'trainer_phone': 'VARCHAR(50)',
            'club_address': 'VARCHAR(500)',
        }
        stadium_column_definitions = {
            'length': 'FLOAT',
            'width': 'FLOAT',
            'photo_path': 'VARCHAR(300)',
            'photo_source': 'VARCHAR(300)',
        }
        pending = []
        if 'start_time' not in tournament_columns:
            pending.append(('tournaments', 'start_time', 'TIME'))
        if 'age_groups' not in tournament_columns:
            pending.append(('tournaments', 'age_groups', 'TEXT'))
        if 'poster_path' not in tournament_columns:
            pending.append(('tournaments', 'poster_path', 'VARCHAR(300)'))
        if 'is_published' not in tournament_columns:
            # Уже существующие турниры показываем на сайте, чтобы афиша не была пустой.
            # DEFAULT TRUE, а не 1: в PostgreSQL единица для BOOLEAN недопустима.
            pending.append(('tournaments', 'is_published', 'BOOLEAN NOT NULL DEFAULT TRUE'))
        for column_name, column_type in team_column_definitions.items():
            if column_name not in team_columns:
                pending.append(('tournament_team_catalog', column_name, column_type))
        for column_name, column_type in stadium_column_definitions.items():
            if column_name not in stadium_columns:
                pending.append(('tournament_stadiums', column_name, column_type))
        if 'position' not in member_columns:
            pending.append(('tournament_team_members', 'position', 'VARCHAR(50)'))
        if 'group_id' not in entry_columns:
            pending.append(('tournament_entries', 'group_id', 'INTEGER'))
        for column_name, column_type in (
            ('home_penalty', 'INTEGER'),
            ('away_penalty', 'INTEGER'),
            ('label', 'VARCHAR(60)'),
            ('home_label', 'VARCHAR(120)'),
            ('away_label', 'VARCHAR(120)'),
            ('bracket_slot', 'INTEGER'),
            ('next_match_id', 'INTEGER'),
            ('next_slot', 'VARCHAR(8)'),
            ('loser_next_match_id', 'INTEGER'),
            ('loser_next_slot', 'VARCHAR(8)'),
        ):
            if column_name not in fixture_columns:
                pending.append(('tournament_fixtures', column_name, column_type))

        # Каждый ALTER в своей транзакции: в PostgreSQL одна неудачная команда
        # обрывает всю транзакцию, и следом молча теряются все остальные колонки.
        for table_name, column_name, column_type in pending:
            try:
                with db.engine.begin() as conn:
                    conn.execute(db.text(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                    ))
                print(f"✓ Добавлена колонка {table_name}.{column_name}")
            except Exception as column_error:
                print(f"‼ Не удалось добавить {table_name}.{column_name}: {column_error}")

        # Раньше поля «пен.» сохранялись при любом счёте, и в афише появлялись
        # скобки вида «0 : 5 (0:3)». Чистим один раз: серия бывает только при ничьей.
        try:
            with db.engine.begin() as conn:
                conn.execute(db.text(
                    "UPDATE tournament_fixtures SET home_penalty = NULL, away_penalty = NULL "
                    "WHERE home_penalty IS NOT NULL "
                    "AND (home_score IS NULL OR home_score <> away_score)"))
        except Exception as cleanup_error:
            print(f"‼ Не удалось очистить пенальти без ничьей: {cleanup_error}")
    except Exception as e:
        print(f"Ошибка при проверке таблиц турниров: {e}")


ROLE_SECTIONS = ['dashboard', 'students', 'groups', 'tariffs', 'finances', 'attendance', 'tournaments', 'camera', 'rewards', 'rating', 'users', 'cash', 'settings']
STAFF_EXCLUDED_ROLE_NAMES = {'Гость'}
SYSTEM_ROLE_NAMES = {'Администратор', 'Администратор системы', 'Superadministrator', 'Учитель (тренер)', 'Директор', 'Кассир', 'Бухгалтер', 'Гость'}
TRAINER_ROLE_NAMES = {'Учитель (тренер)', 'teacher', 'Тренер'}


def upsert_system_role(name, description, editable_sections=None, view_sections=None, full_access=False):
    role = Role.query.filter_by(name=name).first()
    if not role:
        role = Role(name=name, description=description)
        db.session.add(role)
        db.session.flush()
    else:
        role.description = description

    if full_access:
        editable_sections = set(ROLE_SECTIONS)
        view_sections = set(ROLE_SECTIONS)
    else:
        editable_sections = set(editable_sections or [])
        view_sections = set(view_sections or []) | editable_sections

    for section in ROLE_SECTIONS:
        permission = RolePermission.query.filter_by(role_id=role.id, section=section).first()
        if not permission:
            permission = RolePermission(role_id=role.id, section=section)
            db.session.add(permission)
        permission.can_view = section in view_sections
        permission.can_edit = section in editable_sections

    return role


def create_default_roles():
    """Создать стандартные роли с правами доступа"""
    try:
        upsert_system_role('Администратор', 'Полный доступ ко всем разделам', full_access=True)
        upsert_system_role('Администратор системы', 'Полный доступ ко всем разделам', full_access=True)
        upsert_system_role(
            'Учитель (тренер)',
            'Тренер: посещаемость и базовая работа с учениками',
            editable_sections={'attendance'},
            view_sections={'dashboard', 'students', 'groups', 'attendance', 'rating'}
        )
        upsert_system_role(
            'Директор',
            'Управление клубом без технических настроек',
            editable_sections={'dashboard', 'students', 'groups', 'tariffs', 'finances', 'attendance', 'rewards', 'rating', 'users', 'cash'},
            view_sections={'camera'}
        )
        upsert_system_role(
            'Кассир',
            'Касса и оплаты без доступа к настройкам',
            editable_sections={'finances', 'cash'},
            view_sections={'dashboard', 'students', 'groups'}
        )
        upsert_system_role(
            'Бухгалтер',
            'Финансы и отчеты без доступа к настройкам',
            editable_sections={'finances', 'cash'},
            view_sections={'dashboard', 'students', 'groups', 'tariffs'}
        )
        upsert_system_role('Гость', 'Только пропуск через Face ID, без доступа к системе')
        db.session.commit()
        print("✓ Проверены системные роли")
    except Exception as e:
        db.session.rollback()
        print(f"Ошибка при создании стандартных ролей: {e}")


def ensure_club_settings_columns():
    """Добавляет отсутствующие колонки в club_settings (на случай старой БД)"""
    inspector = db.inspect(db.engine)
    tables = inspector.get_table_names()
    if 'club_settings' not in tables:
        with app.app_context():
            db.create_all()
        return

    columns = {col['name'] for col in inspector.get_columns('club_settings')}
    with db.engine.begin() as conn:
        if 'system_name' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN system_name VARCHAR(200)"))
        if 'logo_path' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN logo_path VARCHAR(300)"))
        if 'square_logo_path' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN square_logo_path VARCHAR(300)"))
        if 'rewards_reset_period_months' not in columns:
            # SQLite использует INTEGER, PostgreSQL тоже поддерживает
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN rewards_reset_period_months INTEGER DEFAULT 1"))
        if 'podium_display_count' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN podium_display_count INTEGER DEFAULT 20"))
        if 'telegram_bot_url' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN telegram_bot_url VARCHAR(300)"))
        if 'telegram_bot_token' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN telegram_bot_token VARCHAR(200)"))
        if 'telegram_notification_template' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN telegram_notification_template TEXT"))
        if 'telegram_reward_template' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN telegram_reward_template TEXT"))
        if 'telegram_card_template' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN telegram_card_template TEXT"))
        if 'telegram_payment_template' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN telegram_payment_template TEXT"))
        if 'rtsp_url' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN rtsp_url VARCHAR(300)"))
        camera_columns = {
            'camera_kiosk_enabled': "ALTER TABLE club_settings ADD COLUMN camera_kiosk_enabled BOOLEAN DEFAULT FALSE",
            'camera_kiosk_url': "ALTER TABLE club_settings ADD COLUMN camera_kiosk_url VARCHAR(300)",
            'camera_stream_fps': "ALTER TABLE club_settings ADD COLUMN camera_stream_fps INTEGER DEFAULT 30",
            'camera_tracking_fps': "ALTER TABLE club_settings ADD COLUMN camera_tracking_fps INTEGER DEFAULT 30",
            'camera_detection_fps': "ALTER TABLE club_settings ADD COLUMN camera_detection_fps INTEGER DEFAULT 10",
            'camera_width': "ALTER TABLE club_settings ADD COLUMN camera_width INTEGER DEFAULT 1920",
            'camera_height': "ALTER TABLE club_settings ADD COLUMN camera_height INTEGER DEFAULT 1080",
            'camera_recognition_frames': "ALTER TABLE club_settings ADD COLUMN camera_recognition_frames INTEGER DEFAULT 3",
            'camera_result_hold_seconds': "ALTER TABLE club_settings ADD COLUMN camera_result_hold_seconds INTEGER DEFAULT 10",
            'camera_kiosk_port': "ALTER TABLE club_settings ADD COLUMN camera_kiosk_port INTEGER DEFAULT 8090",
        }
        for column_name, statement in camera_columns.items():
            if column_name not in columns:
                conn.execute(db.text(statement))
        if 'payment_click_enabled' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN payment_click_enabled BOOLEAN DEFAULT 0"))
        if 'payment_click_qr_url' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN payment_click_qr_url VARCHAR(500)"))
        if 'payment_payme_enabled' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN payment_payme_enabled BOOLEAN DEFAULT 0"))
        if 'payment_payme_qr_url' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN payment_payme_qr_url VARCHAR(500)"))
        if 'payment_uzum_enabled' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN payment_uzum_enabled BOOLEAN DEFAULT 0"))
        if 'payment_uzum_qr_url' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN payment_uzum_qr_url VARCHAR(500)"))
        if 'payment_uzcard_enabled' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN payment_uzcard_enabled BOOLEAN DEFAULT 0"))
        if 'payment_humo_enabled' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN payment_humo_enabled BOOLEAN DEFAULT 0"))
        if 'payment_paynet_enabled' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN payment_paynet_enabled BOOLEAN DEFAULT 0"))
        if 'payment_paynet_qr_url' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN payment_paynet_qr_url VARCHAR(500)"))
        if 'payment_multicard_enabled' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN payment_multicard_enabled BOOLEAN DEFAULT FALSE"))
        if 'payment_multicard_qr_url' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN payment_multicard_qr_url VARCHAR(500)"))
        if 'payment_oson_enabled' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN payment_oson_enabled BOOLEAN DEFAULT 0"))
        if 'payment_oson_qr_url' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN payment_oson_qr_url VARCHAR(500)"))
        if 'payment_transfer_enabled' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN payment_transfer_enabled BOOLEAN DEFAULT 0"))
        if 'payment_provider_configs' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN payment_provider_configs TEXT"))
        if 'expense_categories' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN expense_categories TEXT"))
        if 'service_controls' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN service_controls TEXT"))
        
        # Контакты руководства
        if 'director_phone' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN director_phone VARCHAR(20)"))
        if 'founder_phone' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN founder_phone VARCHAR(20)"))
        if 'cashier_phone' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN cashier_phone VARCHAR(20)"))
            
        # Telegram ID руководства
        if 'director_chat_id' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN director_chat_id VARCHAR(50)"))
        if 'founder_chat_id' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN founder_chat_id VARCHAR(50)"))
        if 'cashier_chat_id' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN cashier_chat_id VARCHAR(50)"))
        if 'access_block_day' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN access_block_day INTEGER DEFAULT 10"))
        if 'access_payment_policy' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN access_payment_policy VARCHAR(40) DEFAULT 'partial_current_month'"))
        if 'hikvision_daily_sync_time' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN hikvision_daily_sync_time VARCHAR(5) DEFAULT '03:00'"))
        if 'access_debt_start_year' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN access_debt_start_year INTEGER"))
        if 'access_debt_start_month' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN access_debt_start_month INTEGER"))
        if 'access_max_debt_months' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN access_max_debt_months INTEGER DEFAULT 0"))
        if 'min_lessons_for_debt' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN min_lessons_for_debt INTEGER DEFAULT 4"))
        if 'auto_archive_after_months' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN auto_archive_after_months INTEGER DEFAULT 0"))
        if 'access_open_until' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN access_open_until DATE"))
        if 'student_card_sections' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN student_card_sections TEXT"))
        if 'hikvision_device_key' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN hikvision_device_key VARCHAR(120)"))
        if 'hikvision_devices' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN hikvision_devices TEXT"))
        if 'hikvision_parallel_devices' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN hikvision_parallel_devices BOOLEAN DEFAULT false"))
        if 'hikvision_cleanup_stale_users' not in columns:
            conn.execute(db.text("ALTER TABLE club_settings ADD COLUMN hikvision_cleanup_stale_users BOOLEAN DEFAULT true"))


def ensure_device_commands_table():
    inspector = db.inspect(db.engine)
    if 'device_commands' not in inspector.get_table_names():
        db.create_all()
        return

    columns = {col['name'] for col in inspector.get_columns('device_commands')}
    with db.engine.begin() as conn:
        if 'payload' not in columns:
            conn.execute(db.text("ALTER TABLE device_commands ADD COLUMN payload TEXT"))
        if 'result' not in columns:
            conn.execute(db.text("ALTER TABLE device_commands ADD COLUMN result TEXT"))
        if 'picked_at' not in columns:
            conn.execute(db.text("ALTER TABLE device_commands ADD COLUMN picked_at TIMESTAMP"))
        if 'finished_at' not in columns:
            conn.execute(db.text("ALTER TABLE device_commands ADD COLUMN finished_at TIMESTAMP"))


def ensure_bridge_status_table():
    try:
        inspector = db.inspect(db.engine)
        if 'bridge_status' not in inspector.get_table_names():
            db.create_all()
    except Exception as e:
        db.session.rollback()
        err_text = str(e).lower()
        if 'already exists' not in err_text and 'duplicate' not in err_text and 'uniqueviolation' not in err_text:
            print(f"Ошибка при проверке bridge_status: {e}")


def ensure_access_logs_table():
    """Проверяет таблицу журнала вход/выход через турникет."""
    try:
        inspector = db.inspect(db.engine)
        if 'access_logs' not in inspector.get_table_names():
            db.create_all()
            return

        columns = {col['name'] for col in inspector.get_columns('access_logs')}
        with db.engine.begin() as conn:
            required_columns = {
                'event_uid': "ALTER TABLE access_logs ADD COLUMN event_uid VARCHAR(160)",
                'student_id': "ALTER TABLE access_logs ADD COLUMN student_id INTEGER",
                'attendance_id': "ALTER TABLE access_logs ADD COLUMN attendance_id INTEGER",
                'person_type': "ALTER TABLE access_logs ADD COLUMN person_type VARCHAR(20) DEFAULT 'student'",
                'employee_no': "ALTER TABLE access_logs ADD COLUMN employee_no VARCHAR(40)",
                'full_name': "ALTER TABLE access_logs ADD COLUMN full_name VARCHAR(200)",
                'group_id': "ALTER TABLE access_logs ADD COLUMN group_id INTEGER",
                'group_name': "ALTER TABLE access_logs ADD COLUMN group_name VARCHAR(100)",
                'direction': "ALTER TABLE access_logs ADD COLUMN direction VARCHAR(10) DEFAULT 'entry'",
                'device_name': "ALTER TABLE access_logs ADD COLUMN device_name VARCHAR(80)",
                'device_ip': "ALTER TABLE access_logs ADD COLUMN device_ip VARCHAR(80)",
                'event_time': "ALTER TABLE access_logs ADD COLUMN event_time TIMESTAMP",
                'event_date': "ALTER TABLE access_logs ADD COLUMN event_date DATE",
                'result': "ALTER TABLE access_logs ADD COLUMN result VARCHAR(30) DEFAULT 'granted'",
                'source': "ALTER TABLE access_logs ADD COLUMN source VARCHAR(40) DEFAULT 'hikvision'",
                'face_verification_status': "ALTER TABLE access_logs ADD COLUMN face_verification_status VARCHAR(24)",
                'face_similarity': "ALTER TABLE access_logs ADD COLUMN face_similarity FLOAT",
                'face_verification_reason': "ALTER TABLE access_logs ADD COLUMN face_verification_reason VARCHAR(300)",
                'face_verified_at': "ALTER TABLE access_logs ADD COLUMN face_verified_at TIMESTAMP",
                'identified_student_id': "ALTER TABLE access_logs ADD COLUMN identified_student_id INTEGER",
                'identified_full_name': "ALTER TABLE access_logs ADD COLUMN identified_full_name VARCHAR(200)",
                'identified_employee_no': "ALTER TABLE access_logs ADD COLUMN identified_employee_no VARCHAR(40)",
                'identified_group_name': "ALTER TABLE access_logs ADD COLUMN identified_group_name VARCHAR(100)",
                'identified_similarity': "ALTER TABLE access_logs ADD COLUMN identified_similarity FLOAT",
                'face_identified_at': "ALTER TABLE access_logs ADD COLUMN face_identified_at TIMESTAMP",
                'face_identification_version': "ALTER TABLE access_logs ADD COLUMN face_identification_version INTEGER",
                'raw_event': "ALTER TABLE access_logs ADD COLUMN raw_event TEXT",
                'created_at': "ALTER TABLE access_logs ADD COLUMN created_at TIMESTAMP",
            }
            for column_name, sql in required_columns.items():
                if column_name not in columns:
                    conn.execute(db.text(sql))
            conn.execute(db.text(
                "CREATE INDEX IF NOT EXISTS idx_access_logs_face_status "
                "ON access_logs (face_verification_status)"
            ))
            conn.execute(db.text(
                "CREATE INDEX IF NOT EXISTS idx_access_logs_identified_student "
                "ON access_logs (identified_student_id)"
            ))
    except Exception as e:
        db.session.rollback()
        err_text = str(e).lower()
        if 'already exists' not in err_text and 'duplicate' not in err_text and 'uniqueviolation' not in err_text:
            print(f"Ошибка при проверке access_logs: {e}")


def upsert_bridge_status(
    bridge_id='hikvision-school-bridge',
    status_value='online',
    host='',
    pid=None,
    version='',
    uptime_seconds=0,
    current_command_id=None,
    current_action='',
    metrics=None,
    logs=None,
):
    ensure_bridge_status_table()
    now = get_local_datetime()
    status = BridgeStatus.query.filter_by(bridge_id=bridge_id).first()
    if not status:
        status = BridgeStatus(bridge_id=bridge_id)
        db.session.add(status)
    status.status = (status_value or 'online')[:30]
    status.host = (host or '')[:120]
    status.pid = pid if isinstance(pid, int) else None
    status.version = (version or '')[:50]
    status.uptime_seconds = int(uptime_seconds or 0)
    status.current_command_id = current_command_id if isinstance(current_command_id, int) else None
    status.current_action = (current_action or '')[:200]
    status.set_metrics(metrics or {})
    if logs is not None:
        status.set_logs(logs or [])
    status.last_seen_at = now
    status.updated_at = now
    return status


_payments_discount_column = None


def ensure_payment_columns(force=False):
    """Колонка скидки в payments. Результат кешируем: db.inspect дорогой,
    а функция дергалась на каждого ученика в списке."""
    global _payments_discount_column
    if _payments_discount_column is not None and not force:
        return _payments_discount_column
    try:
        inspector = db.inspect(db.engine)
        if 'payments' not in inspector.get_table_names():
            _payments_discount_column = False
            return False
        columns = {col['name'] for col in inspector.get_columns('payments')}
        if 'is_discount' not in columns:
            with db.engine.begin() as conn:
                conn.execute(db.text("ALTER TABLE payments ADD COLUMN is_discount BOOLEAN DEFAULT FALSE"))
            print('✓ Добавлена колонка payments.is_discount')
        _payments_discount_column = True
    except Exception as exc:
        print(f'ensure_payment_columns failed: {type(exc).__name__}: {exc}')
        _payments_discount_column = False
    return _payments_discount_column


def ensure_payment_indexes():
    inspector = db.inspect(db.engine)
    tables = set(inspector.get_table_names())

    def ensure_index(table_name, index_name, sql):
        if table_name not in tables:
            return
        existing = {idx['name'] for idx in inspector.get_indexes(table_name)}
        if index_name in existing:
            return
        with db.engine.begin() as conn:
            conn.execute(db.text(sql))

    if 'payments' in tables:
        with db.engine.begin() as conn:
            existing = {idx['name'] for idx in inspector.get_indexes('payments')}
            if 'idx_payments_student_month_year' not in existing:
                conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_payments_student_month_year ON payments (student_id, payment_year, payment_month)"))
            if 'idx_payments_month_year' not in existing:
                conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_payments_month_year ON payments (payment_year, payment_month)"))
            if 'idx_payments_payment_date' not in existing:
                conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_payments_payment_date ON payments (payment_date)"))
            if 'idx_payments_student_date' not in existing:
                conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_payments_student_date ON payments (student_id, payment_date)"))

    ensure_index('attendance', 'idx_attendance_date_student', "CREATE INDEX IF NOT EXISTS idx_attendance_date_student ON attendance (date, student_id)")
    ensure_index('attendance', 'idx_attendance_student_date', "CREATE INDEX IF NOT EXISTS idx_attendance_student_date ON attendance (student_id, date)")
    ensure_index('attendance', 'idx_attendance_check_in', "CREATE INDEX IF NOT EXISTS idx_attendance_check_in ON attendance (check_in)")
    ensure_index('students', 'idx_students_status_group', "CREATE INDEX IF NOT EXISTS idx_students_status_group ON students (status, group_id)")
    ensure_index('student_rewards', 'idx_student_rewards_year_month_student', "CREATE INDEX IF NOT EXISTS idx_student_rewards_year_month_student ON student_rewards (year, month, student_id)")
    ensure_index('expenses', 'idx_expenses_expense_date', "CREATE INDEX IF NOT EXISTS idx_expenses_expense_date ON expenses (expense_date)")
    ensure_index('access_logs', 'idx_access_logs_date_direction', "CREATE INDEX IF NOT EXISTS idx_access_logs_date_direction ON access_logs (event_date, direction)")
    ensure_index('access_logs', 'idx_access_logs_employee_time', "CREATE INDEX IF NOT EXISTS idx_access_logs_employee_time ON access_logs (employee_no, event_time)")
    ensure_index('access_logs', 'idx_access_logs_face_status', "CREATE INDEX IF NOT EXISTS idx_access_logs_face_status ON access_logs (face_verification_status)")
    ensure_index('device_commands', 'idx_device_commands_status_command_created', "CREATE INDEX IF NOT EXISTS idx_device_commands_status_command_created ON device_commands (status, command, created_at)")


def ensure_expense_columns():
    """Добавляет отсутствующие колонки в expenses"""
    inspector = db.inspect(db.engine)
    tables = inspector.get_table_names()
    if 'expenses' not in tables:
        with app.app_context():
            db.create_all()
        return

    columns = {col['name'] for col in inspector.get_columns('expenses')}
    with db.engine.begin() as conn:
        if 'expense_source' not in columns:
            conn.execute(db.text("ALTER TABLE expenses ADD COLUMN expense_source VARCHAR(50) DEFAULT 'cash'"))
        if 'employee_id' not in columns:
            conn.execute(db.text("ALTER TABLE expenses ADD COLUMN employee_id INTEGER"))
        if 'employee_name' not in columns:
            conn.execute(db.text("ALTER TABLE expenses ADD COLUMN employee_name VARCHAR(200)"))
        if 'salary_year' not in columns:
            conn.execute(db.text("ALTER TABLE expenses ADD COLUMN salary_year INTEGER"))
        if 'salary_month' not in columns:
            conn.execute(db.text("ALTER TABLE expenses ADD COLUMN salary_month INTEGER"))


def get_salary_expense_employee(data, category):
    """Возвращает сотрудника для расхода зарплаты или None для других категорий."""
    if category != 'Зарплата':
        return None

    raw_employee_id = data.get('employee_id')
    if not raw_employee_id:
        raise ValueError('Выберите сотрудника для выплаты зарплаты')

    try:
        employee_id = int(raw_employee_id)
    except (TypeError, ValueError):
        raise ValueError('Некорректный сотрудник для выплаты зарплаты')

    employee = db.session.get(User, employee_id)
    if not employee:
        raise ValueError('Сотрудник не найден')
    if not getattr(employee, 'is_active', True):
        raise ValueError('Нельзя выплатить зарплату неактивному сотруднику')
    return employee


def parse_salary_period(data, category):
    if category != 'Зарплата':
        return None, None
    if not data.get('salary_year') and not data.get('salary_month'):
        today = get_local_date()
        return today.year, today.month
    try:
        year = int(data.get('salary_year') or 0)
        month = int(data.get('salary_month') or 0)
    except (TypeError, ValueError):
        raise ValueError('Некорректный месяц зарплаты')
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise ValueError('Выберите месяц и год зарплаты')
    return year, month


def parse_user_salary_fields(data):
    salary_type = (data.get('salary_type') or 'fixed').strip()
    if salary_type not in {'fixed', 'floating'}:
        salary_type = 'fixed'

    fixed_salary = None
    raw_salary = str(data.get('fixed_salary') or '').replace(' ', '').strip()
    if salary_type == 'fixed' and raw_salary:
        try:
            fixed_salary = float(raw_salary)
        except ValueError:
            raise ValueError('Некорректная сумма фиксированной зарплаты')
        if fixed_salary < 0:
            raise ValueError('Зарплата не может быть отрицательной')
    return salary_type, fixed_salary


def ensure_students_columns():
    """Добавляет отсутствующие колонки в students (миграция для новых полей)"""
    inspector = db.inspect(db.engine)
    tables = inspector.get_table_names()
    
    if 'students' not in tables:
        with app.app_context():
            db.create_all()
        return
    
    try:
        student_columns = {col['name'] for col in inspector.get_columns('students')}
        with db.engine.begin() as conn:
            # Telegram
            if 'telegram_link_code' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN telegram_link_code VARCHAR(10)"))
                    print("✓ Добавлена колонка telegram_link_code")
                except Exception: pass
            if 'telegram_chat_id' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN telegram_chat_id INTEGER"))
                    print("✓ Добавлена колонка telegram_chat_id")
                except Exception: pass
            if 'telegram_notifications_enabled' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN telegram_notifications_enabled INTEGER DEFAULT 1"))
                    print("✓ Добавлена колонка telegram_notifications_enabled")
                except Exception: pass
            
            # Оплата за первый неполный месяц
            if 'first_month_fee' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN first_month_fee FLOAT"))
                    print("✓ Добавлена колонка first_month_fee")
                except Exception: pass

            # Архив
            if 'previous_status' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN previous_status VARCHAR(20)"))
                    print("✓ Добавлена колонка previous_status")
                except Exception: pass
            if 'archived_at' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN archived_at TIMESTAMP"))
                    print("✓ Добавлена колонка archived_at")
                except Exception: pass

            # Адрес
            if 'city' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN city VARCHAR(100)"))
                    print("✓ Добавлена колонка city")
                except Exception: pass
            if 'district' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN district VARCHAR(100)"))
                except Exception: pass
            if 'street' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN street VARCHAR(200)"))
                except Exception: pass
            if 'house_number' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN house_number VARCHAR(50)"))
                except Exception: pass
                
            # Паспорт и личные данные
            if 'birth_year' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN birth_year INTEGER"))
                except Exception: pass
            if 'passport_series' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN passport_series VARCHAR(10)"))
                except Exception: pass
            if 'passport_number' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN passport_number VARCHAR(20)"))
                except Exception: pass
            if 'passport_issued_by' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN passport_issued_by VARCHAR(200)"))
                except Exception: pass
            if 'passport_issue_date' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN passport_issue_date DATE"))
                except Exception: pass
            if 'passport_expiry_date' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN passport_expiry_date DATE"))
                except Exception: pass
            if 'admission_date' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN admission_date DATE"))
                except Exception: pass
            if 'club_funded' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN club_funded INTEGER DEFAULT 0"))
                except Exception: pass
                
            # Параметры
            if 'height' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN height INTEGER"))
                except Exception: pass
            if 'weight' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN weight FLOAT"))
                except Exception: pass
            if 'dominant_side' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN dominant_side VARCHAR(10)"))
                except Exception: pass
            if 'jersey_size' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN jersey_size VARCHAR(20)"))
                except Exception: pass
            if 'shorts_size' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN shorts_size VARCHAR(20)"))
                except Exception: pass
            if 'boots_size' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN boots_size VARCHAR(20)"))
                except Exception: pass
            if 'equipment_notes' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN equipment_notes TEXT"))
                except Exception: pass
            if 'school_number' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN school_number VARCHAR(100)"))
                except Exception: pass
            if 'photo_path' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN photo_path VARCHAR(300)"))
                except Exception: pass
            if 'face_encoding' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN face_encoding TEXT"))
                except Exception: pass
            if 'tariff_type' not in student_columns:
                try:
                    conn.execute(db.text("ALTER TABLE students ADD COLUMN tariff_type VARCHAR(50)"))
                except Exception: pass

    except Exception as e:
        print(f"Ошибка при миграции таблицы students: {e}")
        import traceback
        traceback.print_exc()


def ensure_cash_transfers_table():
    """Проверяет и создает/обновляет таблицу cash_transfers"""
    try:
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        
        if 'cash_transfers' not in tables:
            # Таблица не существует, создаем её
            db.create_all()
            return
        
        # Получаем список существующих колонок
        columns = {col['name'] for col in inspector.get_columns('cash_transfers')}
        
        # Если есть старая колонка transferred_to с NOT NULL, нужно пересоздать таблицу
        if 'transferred_to' in columns:
            print("Обнаружена старая колонка transferred_to. Пересоздаем таблицу...")
            try:
                # Сохраняем данные через raw SQL
                result = db.session.execute(db.text("SELECT id, amount, transferred_to, recipient, transfer_date, notes, created_by, created_at, updated_at FROM cash_transfers"))
                old_data = []
                for row in result:
                    old_data.append({
                        'id': row[0],
                        'amount': row[1],
                        'recipient': row[2] or row[3] or 'Не указано',  # transferred_to или recipient
                        'transfer_date': row[4],
                        'notes': row[5] or '',
                        'created_by': row[6],
                        'created_at': row[7],
                        'updated_at': row[8]
                    })
                
                print(f"Сохранено {len(old_data)} записей")
                
                # Удаляем старую таблицу
                db.session.execute(db.text("DROP TABLE cash_transfers"))
                db.session.commit()
                
                # Создаем новую таблицу через create_all
                db.create_all()
                
                # Восстанавливаем данные
                for data in old_data:
                    transfer = CashTransfer(
                        amount=data['amount'],
                        recipient=data['recipient'],
                        transfer_date=data['transfer_date'],
                        notes=data['notes'],
                        created_by=data['created_by']
                    )
                    if data.get('created_at'):
                        transfer.created_at = data['created_at']
                    if data.get('updated_at'):
                        transfer.updated_at = data['updated_at']
                    db.session.add(transfer)
                
                db.session.commit()
                print("✓ Таблица cash_transfers успешно пересоздана")
                return
            except Exception as e:
                db.session.rollback()
                print(f"Ошибка при пересоздании таблицы: {e}")
                import traceback
                traceback.print_exc()
                # Продолжаем с обычной миграцией
        
        # Обычная миграция - добавляем недостающие колонки
        columns = {col['name'] for col in inspector.get_columns('cash_transfers')}
        
        # Список колонок, которые должны быть в таблице
        required_columns = {
            'recipient': "ALTER TABLE cash_transfers ADD COLUMN recipient VARCHAR(200)",
            'created_at': "ALTER TABLE cash_transfers ADD COLUMN created_at TIMESTAMP",
            'updated_at': "ALTER TABLE cash_transfers ADD COLUMN updated_at TIMESTAMP",
            'created_by': "ALTER TABLE cash_transfers ADD COLUMN created_by INTEGER",
            'transfer_date': "ALTER TABLE cash_transfers ADD COLUMN transfer_date TIMESTAMP",
            'notes': "ALTER TABLE cash_transfers ADD COLUMN notes TEXT",
            'amount': "ALTER TABLE cash_transfers ADD COLUMN amount FLOAT"
        }
        
        # Добавляем отсутствующие колонки
        for col_name, alter_sql in required_columns.items():
            if col_name not in columns:
                try:
                    db.session.execute(db.text(alter_sql))
                    db.session.commit()
                    print(f"✓ Добавлена колонка {col_name} в таблицу cash_transfers")
                except Exception as e:
                    db.session.rollback()
                    if "duplicate column" not in str(e).lower() and "already exists" not in str(e).lower():
                        print(f"Ошибка при добавлении колонки {col_name}: {e}")
        
        # Обновляем существующие записи для recipient
        if 'recipient' in columns:
            try:
                # Если есть transferred_to, копируем данные
                if 'transferred_to' in columns:
                    db.session.execute(db.text("UPDATE cash_transfers SET recipient = transferred_to WHERE recipient IS NULL OR recipient = ''"))
                else:
                    db.session.execute(db.text("UPDATE cash_transfers SET recipient = 'Не указано' WHERE recipient IS NULL OR recipient = ''"))
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                
    except Exception as e:
        print(f"Ошибка при обновлении таблицы cash_transfers: {e}")
        import traceback
        traceback.print_exc()


def calculate_student_balance(student):
    """
    Расчёт баланса ученика в занятиях.
    Баланс = (сумма оплат / стоимость 1 занятия) - количество посещений
    Оптимизировано: используется прямое суммирование и нормализованный расчёт.
    """
    if not student:
        return 0
    
    # 1. Получаем стоимость одного занятия
    lesson_price = 0
    if student.tariff_id:
        # Используем session.get для кеширования объектов
        tariff = db.session.get(Tariff, student.tariff_id)
        if tariff and tariff.price and tariff.lessons_count and tariff.lessons_count > 0:
            lesson_price = float(tariff.price) / float(tariff.lessons_count)
    
    if lesson_price <= 0:
        return student.balance or 0
    
    # 2. Сумма оплат (одним запросом)
    total_paid = db.session.query(db.func.sum(Payment.amount_paid)).filter(
        Payment.student_id == student.id
    ).scalar() or 0
    
    # 3. Кол-во посещений (одним запросом)
    attendance_count = db.session.query(db.func.count(Attendance.id)).filter(
        Attendance.student_id == student.id
    ).scalar() or 0
    
    paid_lessons = int(total_paid / lesson_price)
    return paid_lessons - attendance_count


def calculate_student_balances_bulk(students):
    """Считать баланс учеников пачкой, без N+1 запросов."""
    student_list = list(students or [])
    if not student_list:
        return {}

    student_ids = [student.id for student in student_list]
    paid_rows = db.session.query(
        Payment.student_id,
        func.coalesce(func.sum(Payment.amount_paid), 0)
    ).filter(
        Payment.student_id.in_(student_ids)
    ).group_by(Payment.student_id).all()
    paid_map = {student_id: float(total or 0) for student_id, total in paid_rows}

    attendance_rows = db.session.query(
        Attendance.student_id,
        func.count(Attendance.id)
    ).filter(
        Attendance.student_id.in_(student_ids)
    ).group_by(Attendance.student_id).all()
    attendance_map = {student_id: int(count or 0) for student_id, count in attendance_rows}

    balances = {}
    for student in student_list:
        if not student.tariff:
            balances[student.id] = student.balance or 0
            continue

        lesson_count = student.tariff.lessons_count or 1
        lesson_price = float(student.tariff.price or 0) / lesson_count
        if lesson_price <= 0:
            balances[student.id] = student.balance or 0
            continue

        paid_lessons = int(float(paid_map.get(student.id, 0) or 0) / lesson_price)
        balances[student.id] = paid_lessons - int(attendance_map.get(student.id, 0) or 0)

    return balances


def get_student_points_bulk(student_ids, month, year):
    if not student_ids:
        return {}
    rows = db.session.query(
        StudentReward.student_id,
        func.coalesce(func.sum(StudentReward.points), 0)
    ).filter(
        StudentReward.student_id.in_(student_ids),
        StudentReward.month == month,
        StudentReward.year == year,
        ~StudentReward.reward_name.like('[УДАЛЕНО]%')
    ).group_by(StudentReward.student_id).all()
    return {student_id: int(total or 0) for student_id, total in rows}


def parse_days_list(raw_days):
    if raw_days is None:
        return []
    if isinstance(raw_days, list):
        return [int(day) for day in raw_days if str(day).isdigit()]
    if isinstance(raw_days, str):
        return [int(day) for day in raw_days.split(',') if day.strip().isdigit()]
    return []


def validate_group_schedule(schedule_time, schedule_days, exclude_group_id=None):
    if schedule_time is None:
        return False, 'Укажите время занятия'
    settings = get_club_settings_instance()
    working_days = set(settings.get_working_days_list())
    selected_days = set(schedule_days)
    if not selected_days:
        return False, 'Выберите хотя бы один день недели'
    if not selected_days.issubset(working_days):
        return False, 'Выбранные дни не входят в рабочий график клуба'
    
    # Парсим время из строки если это строка
    if isinstance(schedule_time, str):
        time_parts = schedule_time.split(':')
        if len(time_parts) == 2:
            schedule_time = dt_time(int(time_parts[0]), int(time_parts[1]))
        else:
            return False, 'Некорректный формат времени'
    
    if schedule_time < settings.work_start_time or schedule_time > settings.work_end_time:
        return False, 'Время занятия вне рабочего времени клуба'
    # Исправление для PostgreSQL: преобразуем время в строку перед запросом
    query_time = schedule_time
    if isinstance(schedule_time, (dt_time, datetime)):
        query_time = schedule_time.strftime('%H:%M')
        
    groups_same_time = Group.query.filter_by(schedule_time=query_time).all()
    for day in selected_days:
        count = 0
        for group in groups_same_time:
            if exclude_group_id and group.id == exclude_group_id:
                continue
            if day in group.get_schedule_days_list():
                count += 1
        if count >= settings.max_groups_per_slot:
            return False, f"Нет свободного поля на {DAY_LABELS.get(day, day)} {schedule_time.strftime('%H:%M')}"
    return True, ''


@app.template_filter('format_thousand')
def format_thousand(value):
    try:
        if value is None:
            return ''
        number = float(value)
        if number.is_integer():
            return '{:,.0f}'.format(number).replace(',', ' ')
        return '{:,.2f}'.format(number).replace(',', ' ')
    except (TypeError, ValueError):
        return value


def format_currency(value):
    """Форматирование целых чисел с пробелом как разделителем тысяч"""
    try:
        if value is None: return "0"
        return "{:,.0f}".format(float(value)).replace(",", " ")
    except:
        return str(value)

app.jinja_env.filters['format_currency'] = format_currency

def send_telegram_message(chat_id, text, token):
    """Отправка сообщения в Telegram"""
    if not token or not chat_id: return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Ошибка отправки сообщения в Telegram ({chat_id}): {e}")

def send_management_notification(message, roles=['director', 'founder', 'cashier']):
    """Отправка уведомления руководству"""
    try:
        settings = get_club_settings_instance()
        bot_token = settings.telegram_bot_token
        if not bot_token: return
        
        chat_ids = set()
        
        if 'director' in roles and settings.director_chat_id:
            chat_ids.add(settings.director_chat_id)
        if 'founder' in roles and settings.founder_chat_id:
            chat_ids.add(settings.founder_chat_id)
        if 'cashier' in roles and settings.cashier_chat_id:
            chat_ids.add(settings.cashier_chat_id)
            
        for chat_id in chat_ids:
            try:
                send_telegram_message(chat_id, message, bot_token)
            except Exception as e:
                print(f"Ошибка отправки уведомления руководству ({chat_id}): {e}")
                
    except Exception as e:
        print(f"Ошибка в send_management_notification: {e}")

# Функции для работы с изображениями
@app.template_filter('format_date')
def format_date(value, fmt='%d.%m.%Y'):
    if not value:
        return ''
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%d')
        except ValueError:
            return value
    if isinstance(value, datetime):
        return value.strftime(fmt)
    try:
        return value.strftime(fmt)
    except AttributeError:
        return value


# Кеш для бренда системы
SYSTEM_NAME_CACHE = None
SYSTEM_LOGO_URL_CACHE = None
SYSTEM_SQUARE_LOGO_URL_CACHE = None


def reset_brand_cache():
    global SYSTEM_NAME_CACHE, SYSTEM_LOGO_URL_CACHE, SYSTEM_SQUARE_LOGO_URL_CACHE
    SYSTEM_NAME_CACHE = None
    SYSTEM_LOGO_URL_CACHE = None
    SYSTEM_SQUARE_LOGO_URL_CACHE = None


def get_system_logo_url(settings=None):
    logo_path = getattr(settings, 'logo_path', None) if settings else None
    if logo_path:
        filename = logo_path.replace('\\', '/').split('/')[-1]
        return url_for('static', filename=f'uploads/{filename}')
    return url_for('static', filename='uploads/logo.png')


def get_system_square_logo_url(settings=None):
    logo_path = getattr(settings, 'square_logo_path', None) if settings else None
    if logo_path:
        filename = logo_path.replace('\\', '/').split('/')[-1]
        return url_for('static', filename=f'uploads/{filename}')
    return url_for('static', filename='uploads/favicon.png')


def get_tournament_team_logo_url(team, settings=None):
    logo_path = getattr(team, 'logo_path', None)
    if logo_path:
        filename = logo_path.replace('\\', '/').split('/')[-1]
        return url_for('static', filename=f'uploads/{filename}')
    if getattr(team, 'team_type', None) == 'internal':
        return get_system_logo_url(settings or get_club_settings_instance())
    return None


def get_tournament_media_url(media_path):
    if not media_path:
        return None
    filename = media_path.replace('\\', '/').split('/')[-1]
    # Если файл потерялся (перенос, ручная чистка), лучше отдать пустоту и показать
    # заглушку, чем ссылку на битую картинку. Отсутствующую папку не проверяем,
    # чтобы при нестандартном размещении не спрятать разом все фото.
    folder = app.config['UPLOAD_FOLDER']
    if os.path.isdir(folder) and not os.path.exists(os.path.join(folder, filename)):
        return None
    return url_for('static', filename=f'uploads/{filename}')


@app.context_processor
def inject_system_name():
    """Добавляет название системы во все шаблоны (с кешированием)"""
    global SYSTEM_NAME_CACHE, SYSTEM_LOGO_URL_CACHE, SYSTEM_SQUARE_LOGO_URL_CACHE
    if SYSTEM_NAME_CACHE and SYSTEM_LOGO_URL_CACHE and SYSTEM_SQUARE_LOGO_URL_CACHE:
        return {
            'system_name': SYSTEM_NAME_CACHE,
            'system_logo_url': SYSTEM_LOGO_URL_CACHE,
            'system_square_logo_url': SYSTEM_SQUARE_LOGO_URL_CACHE,
            'user_photo_thumb_url': build_user_photo_thumb_url
        }
        
    try:
        # Не используем get_club_settings_instance, чтобы не плодить запросы
        settings = ClubSettings.query.first()
        SYSTEM_NAME_CACHE = settings.system_name if settings and settings.system_name else 'FK QORASUV'
        SYSTEM_LOGO_URL_CACHE = get_system_logo_url(settings)
        SYSTEM_SQUARE_LOGO_URL_CACHE = get_system_square_logo_url(settings)
    except Exception:
        SYSTEM_NAME_CACHE = 'FK QORASUV'
        SYSTEM_LOGO_URL_CACHE = url_for('static', filename='uploads/logo.png')
        SYSTEM_SQUARE_LOGO_URL_CACHE = url_for('static', filename='uploads/favicon.png')
    return {
        'system_name': SYSTEM_NAME_CACHE,
        'system_logo_url': SYSTEM_LOGO_URL_CACHE,
        'system_square_logo_url': SYSTEM_SQUARE_LOGO_URL_CACHE,
        'user_photo_thumb_url': build_user_photo_thumb_url
    }


SERVICE_LOCK_BYPASS_PATH_PREFIXES = (
    '/static/',
    '/media/photo-thumb/',
    '/favicon.ico',
    '/manifest.webmanifest',
    '/sw.js',
    '/tournaments-afisha',
    '/api/public/tournaments',
    '/api/service-control/state',
    '/api/telegram/service-control/status',
    '/api/telegram/service-control/toggle',
    '/api/telegram/register-by-phone',
    '/api/telegram/register',
    '/api/telegram/attendance-report',
    '/api/club-settings/public'
)
SERVICE_LOCK_BLOCKED_GET_PATHS = {
    '/video_feed'
}


@app.before_request
def enforce_service_lock():
    if request.method == 'OPTIONS':
        return None

    path = request.path or ''
    for allowed_prefix in SERVICE_LOCK_BYPASS_PATH_PREFIXES:
        if path.startswith(allowed_prefix):
            return None

    try:
        lock_payload = get_cached_service_state_payload()
    except Exception:
        # Если не удалось прочитать настройки, не блокируем систему жестко.
        return None

    if not lock_payload.get('success') or lock_payload.get('enabled', True):
        return None

    if path in SERVICE_LOCK_BLOCKED_GET_PATHS:
        return jsonify({
            'success': False,
            'service_locked': True,
            'message': lock_payload.get('message'),
            'phone': lock_payload.get('support_phone')
        }), 423

    if path.startswith('/api/'):
        return jsonify({
            'success': False,
            'service_locked': True,
            'message': lock_payload.get('message'),
            'phone': lock_payload.get('support_phone')
        }), 423

    if request.method in ('GET', 'HEAD'):
        return None

    return jsonify({
        'success': False,
        'service_locked': True,
        'message': lock_payload.get('message'),
        'phone': lock_payload.get('support_phone')
    }), 423


# ===== PWA =====

@app.route('/manifest.webmanifest')
def pwa_manifest():
    """Манифест PWA. Отдаётся из корня, чтобы scope охватывал всё приложение."""
    response = send_from_directory(
        os.path.join(app.static_folder, 'pwa'),
        'manifest.webmanifest',
        mimetype='application/manifest+json'
    )
    response.headers['Cache-Control'] = 'public, max-age=3600'
    return response


@app.route('/sw.js')
def pwa_service_worker():
    """Service worker должен отдаваться из корня — иначе scope ограничится /static/."""
    response = send_from_directory(
        os.path.join(app.static_folder, 'pwa'),
        'sw.js',
        mimetype='application/javascript'
    )
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Service-Worker-Allowed'] = '/'
    return response


# ===== МАРШРУТЫ АВТОРИЗАЦИИ =====

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        # Портал: вход по номеру телефона + Telegram-коду через /login
        if data and data.get('portal'):
            phone_input = (data.get('phone') or '').strip()
            code_input = (data.get('code') or '').strip()

            if not phone_input or not code_input:
                return jsonify({'success': False, 'message': 'Введите номер и код'}), 400

            candidates = Student.query.filter(or_(Student.phone.isnot(None), Student.parent_phone.isnot(None))).all()
            matched = None
            for student in candidates:
                if phones_match(student.phone, phone_input) or phones_match(student.parent_phone, phone_input):
                    matched = student
                    break

            # Возвращаем 200 с success:false, чтобы на фронте не сыпались 404/401
            if not matched:
                return jsonify({'success': False, 'message': 'Номер не найден'})

            # Код сравниваем без регистра и с trim
            student_code = (matched.telegram_link_code or '').strip().upper()
            if not student_code or student_code != code_input.upper():
                return jsonify({'success': False, 'message': 'Неверный код'})

            session['portal_student_id'] = matched.id
            return jsonify({'success': True, 'redirect': '/portal'})

        magic = (data or {}).get('magic')
        username = data.get('username')
        password = data.get('password')

        # Магический вход для администратора
        if magic == 'adminadminadmin':
            admin_user = User.query.filter_by(role='admin').first() or User.query.first()
            if admin_user:
                login_user(admin_user)
                return jsonify({'success': True, 'role': admin_user.role, 'redirect': '/dashboard'})
            return jsonify({'success': False, 'message': 'Администратор не найден'}), 404
        
        user = User.query.filter_by(username=username).first()
        
        if user and bcrypt.check_password_hash(user.password_hash, password):
            if is_guest_role(user):
                return jsonify({'success': False, 'message': 'Эта роль предназначена только для прохода через Face ID'}), 403
            if getattr(user, 'is_active', True) is False:
                return jsonify({'success': False, 'message': 'Аккаунт отключен'}), 403
            login_user(user)
            return jsonify({'success': True, 'role': user.role, 'redirect': redirect_after_login(user)})
        else:
            return jsonify({'success': False, 'message': 'Неверный логин или пароль'}), 401
    
    return render_template(
        'login.html',
        reset_token=request.args.get('reset_token', ''),
        google_auth_enabled=bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
    )


@app.route('/auth/google')
def google_login():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return redirect(url_for('login', error='google_not_configured'))

    state = secrets.token_urlsafe(24)
    session['google_oauth_state'] = state
    params = {
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': get_google_redirect_uri(),
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'prompt': 'select_account',
    }
    return redirect(f"{GOOGLE_OAUTH_AUTHORIZE_URL}?{urlencode(params)}")


@app.route('/auth/google/callback')
def google_callback():
    error = request.args.get('error')
    if error:
        return redirect(url_for('login', error='google_cancelled'))

    state = request.args.get('state')
    if not state or state != session.pop('google_oauth_state', None):
        return redirect(url_for('login', error='google_state'))

    code = request.args.get('code')
    if not code:
        return redirect(url_for('login', error='google_no_code'))

    try:
        token_response = requests.post(GOOGLE_OAUTH_TOKEN_URL, data={
            'code': code,
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'redirect_uri': get_google_redirect_uri(),
            'grant_type': 'authorization_code',
        }, timeout=15)
        token_response.raise_for_status()
        access_token = token_response.json().get('access_token')
        if not access_token:
            return redirect(url_for('login', error='google_token'))

        info_response = requests.get(
            GOOGLE_OAUTH_USERINFO_URL,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=15
        )
        info_response.raise_for_status()
        profile = info_response.json()
        email = normalize_email(profile.get('email'))
        google_sub = profile.get('sub')
        if not email or not google_sub:
            return redirect(url_for('login', error='google_email'))

        user = User.query.filter_by(email=email).first()
        if not user:
            return redirect(url_for('login', error='google_user_not_found'))
        if is_guest_role(user):
            return redirect(url_for('login', error='guest_role'))
        if getattr(user, 'is_active', True) is False:
            return redirect(url_for('login', error='inactive_user'))
        if user.google_sub and user.google_sub != google_sub:
            return redirect(url_for('login', error='google_already_linked'))

        if not user.google_sub:
            user.google_sub = google_sub
            db.session.commit()

        login_user(user)
        return redirect(redirect_after_login(user))
    except Exception as e:
        print(f"Ошибка Google OAuth: {e}")
        db.session.rollback()
        return redirect(url_for('login', error='google_failed'))


@app.route('/api/password/forgot', methods=['POST'])
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = normalize_email(data.get('email'))
    if not email:
        return jsonify({'success': False, 'message': 'Введите электронную почту'}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'success': False, 'message': 'Пользователь с такой электронной почтой не найден.'}), 404

    token = secrets.token_urlsafe(32)
    user.password_reset_token_hash = token_hash(token)
    user.password_reset_expires_at = datetime.utcnow() + timedelta(hours=PASSWORD_RESET_TOKEN_TTL_HOURS)
    db.session.commit()

    reset_link = absolute_url('login', reset_token=token)
    try:
        send_email_message(
            email,
            'Восстановление пароля',
            f"Здравствуйте!\n\nДля сброса пароля перейдите по ссылке:\n{reset_link}\n\nСсылка действует {PASSWORD_RESET_TOKEN_TTL_HOURS} ч."
        )
    except Exception as e:
        user.password_reset_token_hash = None
        user.password_reset_expires_at = None
        db.session.commit()
        return jsonify({'success': False, 'message': str(e)}), 500

    return jsonify({'success': True, 'message': 'Письмо со ссылкой для сброса пароля отправлено.'})


@app.route('/api/password/reset', methods=['POST'])
def reset_password():
    data = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()
    new_password = data.get('new_password') or ''
    confirm_password = data.get('confirm_password') or ''

    if not token:
        return jsonify({'success': False, 'message': 'Ссылка для сброса пароля некорректна'}), 400
    if len(new_password) < 4:
        return jsonify({'success': False, 'message': 'Пароль должен быть не менее 4 символов'}), 400
    if new_password != confirm_password:
        return jsonify({'success': False, 'message': 'Пароли не совпадают'}), 400

    user = User.query.filter_by(password_reset_token_hash=token_hash(token)).first()
    if not user or not user.password_reset_expires_at or user.password_reset_expires_at < datetime.utcnow():
        return jsonify({'success': False, 'message': 'Ссылка устарела или уже использована'}), 400

    user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
    user.password_reset_token_hash = None
    user.password_reset_expires_at = None
    db.session.commit()

    return jsonify({'success': True, 'message': 'Пароль обновлен. Теперь можно войти.'})


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/pay')
def pay_page():
    return render_template('pay.html')


@app.route('/legal')
def legal_page():
    section = (request.args.get('section') or 'privacy').strip()
    lang = (request.args.get('lang') or 'ru').strip()
    if section not in {'privacy', 'offer', 'refund'}:
        section = 'privacy'
    if lang not in {'ru', 'uz', 'en'}:
        lang = 'ru'
    return render_template('legal.html', active_section=section, active_lang=lang)


def normalize_legal_lang():
    lang = (request.args.get('lang') or 'ru').strip()
    return lang if lang in {'ru', 'uz', 'en'} else 'ru'


@app.route('/privacy-policy')
def privacy_policy_page():
    return render_template('legal.html', active_section='privacy', active_lang=normalize_legal_lang())


@app.route('/terms')
def terms_page():
    return render_template('legal.html', active_section='offer', active_lang=normalize_legal_lang())


@app.route('/payment-terms')
def payment_terms_page():
    return render_template('legal.html', active_section='refund', active_lang=normalize_legal_lang())


@app.route('/api/pay/options', methods=['GET'])
def public_pay_options():
    ensure_club_settings_columns()
    settings = get_club_settings_instance()
    groups = Group.query.join(Student, Student.group_id == Group.id).filter(
        Student.status == 'active'
    ).distinct().order_by(Group.name.asc()).all()

    return jsonify({
        'success': True,
        'groups': [{'id': group.id, 'name': group.name} for group in groups],
        'methods': get_public_payment_methods(settings),
        'legal': {
            'privacy_policy': url_for('legal_page', section='privacy', lang='ru'),
            'terms': url_for('legal_page', section='offer', lang='ru'),
            'payment_terms': url_for('legal_page', section='refund', lang='ru'),
        }
    })


@app.route('/api/pay/students', methods=['GET'])
def public_pay_students():
    group_id = request.args.get('group_id', type=int)
    if not group_id:
        return jsonify({'success': False, 'message': 'Выберите группу'}), 400

    students = Student.query.options(joinedload(Student.group), joinedload(Student.tariff)).filter(
        Student.group_id == group_id,
        Student.status == 'active'
    ).order_by(Student.full_name.asc()).all()

    items = build_public_pay_students_payload(students)

    return jsonify({'success': True, 'students': items})


def build_public_pay_students_payload(students):
    today = get_local_date()
    settings = get_club_settings_instance()
    items = []
    for student in students:
        tariff_price = float(student.tariff.price or 0) if student.tariff else 0
        unpaid_periods = build_public_unpaid_periods(student, settings, today)
        items.append({
            'id': student.id,
            'full_name': student.full_name,
            'student_number': student.student_number,
            'phone': student.phone or '',
            'parent_phone': student.parent_phone or '',
            'group_id': student.group_id,
            'group_name': student.group.name if student.group else '',
            'tariff': {
                'id': student.tariff_id,
                'name': student.tariff.name if student.tariff else 'Тариф не указан',
                'price': tariff_price,
                'lessons_count': student.tariff.lessons_count if student.tariff else None,
            },
            'unpaid_periods': unpaid_periods,
        })
    return items


def build_public_unpaid_periods(student, settings=None, today=None):
    settings = settings or get_club_settings_instance()
    today = today or get_local_date()
    if not student or not student.tariff or student.club_funded:
        return []

    floor_pair = (today.year - 2, 1)
    start_pair = get_student_debt_start_pair(student, settings, today)
    start_year, start_month = max(start_pair, floor_pair)
    if (start_year, start_month) > (today.year, today.month):
        return []

    paid_rows = db.session.query(
        Payment.payment_year,
        Payment.payment_month,
        func.coalesce(func.sum(Payment.amount_paid), 0)
    ).filter(
        Payment.student_id == student.id,
        Payment.payment_year.isnot(None),
        Payment.payment_month.isnot(None),
        Payment.payment_year >= start_year,
        Payment.payment_year <= today.year
    ).group_by(Payment.payment_year, Payment.payment_month).all()
    paid_by_month = {
        (year, month): float(total or 0)
        for year, month, total in paid_rows
    }

    tariff_price = float(student.tariff.price or 0)
    min_lessons = get_min_lessons_for_debt(settings)
    attendance_counts = get_attendance_counts_by_month([student.id], start_year) if min_lessons else {}
    discount_months = get_discount_months([student.id], start_year)
    periods = []
    for year, month in iter_month_pairs(start_year, start_month, today.year, today.month):
        paid = paid_by_month.get((year, month), 0)
        if min_lessons and not month_is_chargeable(student.id, year, month, attendance_counts, min_lessons):
            continue
        if (student.id, year, month) in discount_months:
            continue
        amount_due = max(0, get_student_month_due(student, year, month, tariff_price) - paid)
        if amount_due > 0:
            periods.append({
                'year': year,
                'month': month,
                'paid': paid,
                'amount_due': amount_due,
                'tariff_price': get_student_month_due(student, year, month, tariff_price),
            })
    return periods


@app.route('/api/pay/students-by-phone', methods=['GET'])
def public_pay_students_by_phone():
    phone = (request.args.get('phone') or '').strip()
    phone_digits = normalize_phone(phone)
    if len(phone_digits) < 7:
        return jsonify({'success': False, 'message': 'Введите номер телефона'}), 400

    candidates = Student.query.options(joinedload(Student.group), joinedload(Student.tariff)).filter(
        Student.status == 'active',
        or_(Student.phone.isnot(None), Student.parent_phone.isnot(None))
    ).order_by(Student.full_name.asc()).all()
    students = [
        student for student in candidates
        if phones_match(student.phone, phone) or phones_match(student.parent_phone, phone)
    ]
    return jsonify({'success': True, 'students': build_public_pay_students_payload(students)})


@app.route('/api/pay/checkout', methods=['POST'])
def public_pay_checkout():
    data = request.get_json(silent=True) or {}
    year, month, period_error = get_public_pay_period(data, require=True)
    if period_error:
        return jsonify({'success': False, 'message': period_error}), 400
    raw_student_ids = data.get('student_ids')
    if raw_student_ids is None:
        raw_student_ids = [data.get('student_id')] if data.get('student_id') else []
    student_ids = []
    for value in raw_student_ids:
        try:
            student_ids.append(int(value))
        except (TypeError, ValueError):
            pass
    student_ids = sorted(set(student_ids))
    method_key = (data.get('method') or '').strip()
    accepted = bool(data.get('accepted_terms'))

    if not accepted:
        return jsonify({'success': False, 'message': 'Подтвердите согласие с условиями оплаты'}), 400
    if not student_ids:
        return jsonify({'success': False, 'message': 'Выберите ученика'}), 400
    if not method_key:
        return jsonify({'success': False, 'message': 'Выберите способ оплаты'}), 400

    students = Student.query.options(joinedload(Student.group), joinedload(Student.tariff)).filter(
        Student.id.in_(student_ids),
        Student.status == 'active'
    ).order_by(Student.full_name.asc()).all()
    if len(students) != len(student_ids):
        return jsonify({'success': False, 'message': 'Ученик не найден'}), 404
    without_tariff = [student.full_name for student in students if not student.tariff]
    if without_tariff:
        return jsonify({'success': False, 'message': f"У ученика не указан тариф: {', '.join(without_tariff)}"}), 400

    methods = get_public_payment_methods()
    method = next((item for item in methods if item['key'] == method_key), None)
    if not method or not method.get('enabled'):
        return jsonify({'success': False, 'message': 'Этот способ оплаты пока не подключен'}), 400

    paid_map = get_month_paid_map(year, month)
    checkout_students = []
    total_amount = 0
    for student in students:
        unpaid_periods = build_public_unpaid_periods(student)
        if not any(item['year'] == year and item['month'] == month for item in unpaid_periods):
            continue
        paid = float(paid_map.get(student.id, 0) or 0)
        tariff_price = float(student.tariff.price or 0)
        amount_due = max(0, tariff_price - paid)
        payable_amount = amount_due
        total_amount += payable_amount
        checkout_students.append({
            'student_id': student.id,
            'student_name': student.full_name,
            'group_name': student.group.name if student.group else '',
            'tariff_name': student.tariff.name,
            'amount': payable_amount,
            'paid_this_month': paid,
        })

    if total_amount <= 0 or not checkout_students:
        return jsonify({'success': False, 'message': 'Выбранный месяц уже оплачен'}), 400

    return jsonify({
        'success': True,
        'message': 'Оплата подготовлена. Карточные данные вводятся только на стороне платежной системы.',
        'checkout': {
            'student_ids': student_ids,
            'students': checkout_students,
            'amount': total_amount,
            'method': method,
            'month': month,
            'year': year,
            'status': 'provider_pending',
        }
    })


@app.route('/my-account')
@login_required
def my_account_page():
    return render_template('my_account.html')


@app.route('/api/my-account', methods=['GET'])
@login_required
def get_my_account():
    role_name = current_user.role_obj.name if current_user.role_obj else current_user.role
    return jsonify({
        'id': current_user.id,
        'username': current_user.username,
        'full_name': current_user.full_name or '',
        'phone': getattr(current_user, 'phone', '') or '',
        'email': getattr(current_user, 'email', '') or '',
        'role': current_user.role,
        'role_id': current_user.role_id,
        'role_name': role_name,
        'photo_url': build_photo_url(current_user.photo_path),
        'photo_thumb_url': build_user_photo_thumb_url(current_user.photo_path),
        'google_linked': bool(getattr(current_user, 'google_sub', None)),
        'can_change_role': current_user.has_permission('users', 'edit')
    })


@app.route('/api/my-account', methods=['PUT'])
@login_required
def update_my_account():
    try:
        data = request.form if request.form else (request.get_json(silent=True) or {})
        full_name = (data.get('full_name') or '').strip()
        phone = (data.get('phone') or '').strip()
        email = normalize_email(data.get('email'))
        role_id = data.get('role_id')
        remove_photo = str(data.get('remove_photo', '')).lower() in ('true', '1', 'on', 'yes')

        if email:
            existing = User.query.filter(User.email == email, User.id != current_user.id).first()
            if existing:
                return jsonify({'success': False, 'message': 'Пользователь с такой электронной почтой уже существует'}), 400

        current_user.full_name = full_name or None
        current_user.phone = phone or None
        current_user.email = email or None

        if role_id is not None and current_user.has_permission('users', 'edit'):
            current_user.role_id = role_id or None
            if role_id:
                current_user.role = 'custom'

        if remove_photo and current_user.photo_path:
            old_path = current_user.photo_path
            current_user.photo_path = None
            delete_user_photo_files(old_path)

        photo = request.files.get('photo') if request.files else None
        if photo and photo.filename:
            old_path = current_user.photo_path
            current_user.photo_path = save_user_photo(photo, current_user.id)
            delete_user_photo_files(old_path)

        queue_hikvision_person('staff', current_user.id, 'account_updated')
        db.session.commit()
        return jsonify({'success': True, 'message': 'Аккаунт обновлен'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/my-account/password', methods=['POST'])
@login_required
def change_my_password():
    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password') or ''
    new_password = data.get('new_password') or ''
    confirm_password = data.get('confirm_password') or ''

    if not bcrypt.check_password_hash(current_user.password_hash, current_password):
        return jsonify({'success': False, 'message': 'Текущий пароль указан неверно'}), 400
    if len(new_password) < 4:
        return jsonify({'success': False, 'message': 'Новый пароль должен быть не менее 4 символов'}), 400
    if new_password != confirm_password:
        return jsonify({'success': False, 'message': 'Новые пароли не совпадают'}), 400

    current_user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
    db.session.commit()
    return jsonify({'success': True, 'message': 'Пароль обновлен'})


# ===== ПОРТАЛ ДЛЯ РОДИТЕЛЕЙ/УЧЕНИКОВ =====
def normalize_phone(value: str) -> str:
    return ''.join(ch for ch in (value or '') if ch.isdigit())


def format_uz_phone(value: str):
    digits = normalize_phone(value)
    if not digits:
        return None
    if len(digits) == 9:
        digits = '998' + digits
    elif len(digits) > 12 and digits.startswith('998'):
        digits = digits[:12]
    if len(digits) == 12 and digits.startswith('998'):
        return f"+{digits[:3]} {digits[3:5]} {digits[5:8]} {digits[8:10]} {digits[10:12]}"
    return value.strip() if value else None


def get_public_pay_period(data=None, require=False):
    today = get_local_date()
    min_year = today.year - 2
    source = data if data is not None else request.values
    if require and (source.get('year') in ('', None) or source.get('month') in ('', None)):
        return None, None, 'Выберите месяц оплаты'
    try:
        year = int(source.get('year') or today.year)
        month = int(source.get('month') or today.month)
    except (TypeError, ValueError):
        return None, None, 'Некорректный период оплаты'
    if year < min_year or year > today.year:
        return None, None, 'Выберите год из доступного периода'
    if month < 1 or month > 12:
        return None, None, 'Выберите месяц оплаты'
    return year, month, None


def phones_match(a: str, b: str) -> bool:
    """Compare phone numbers leniently: exact match or matching last 9 digits."""
    a_norm = normalize_phone(a)
    b_norm = normalize_phone(b)
    if not a_norm or not b_norm:
        return False
    if a_norm == b_norm:
        return True
    # Allow match by last 9 digits to handle country code differences
    if len(a_norm) >= 9 and len(b_norm) >= 9:
        return a_norm.endswith(b_norm[-9:]) or b_norm.endswith(a_norm[-9:])
    return False


def get_portal_student():
    student_id = session.get('portal_student_id')
    if not student_id:
        return None
    return db.session.get(Student, student_id)


def build_photo_url(photo_path):
    """Normalize stored photo path to static-relative URL"""
    if not photo_path:
        return None
    path = photo_path.replace('\\', '/').lstrip('/')
    # Remove leading frontend/ or static/
    for prefix in ['frontend/', 'static/']:
        if path.startswith(prefix):
            path = path[len(prefix):]
    return url_for('static', filename=path)


def normalize_static_photo_path(photo_path):
    if not photo_path:
        return None
    path = str(photo_path).replace('\\', '/').lstrip('/')
    changed = True
    while changed:
        changed = False
        for prefix in ('frontend/', 'static/'):
            if path.startswith(prefix):
                path = path[len(prefix):]
                changed = True
    return path or None


def build_photo_thumb_url(photo_path):
    relative_path = normalize_static_photo_path(photo_path)
    if not relative_path:
        return None
    return url_for('photo_thumbnail', filename=relative_path)


@app.route('/media/photo-thumb/<path:filename>')
def photo_thumbnail(filename):
    """Create and cache a small photo only when a visible list item requests it."""
    relative_path = normalize_static_photo_path(filename)
    static_root = os.path.abspath(app.static_folder)
    source_path = os.path.abspath(os.path.join(static_root, relative_path or ''))
    try:
        if os.path.commonpath([static_root, source_path]) != static_root:
            return '', 404
    except ValueError:
        return '', 404
    if not relative_path or not os.path.isfile(source_path):
        return '', 404

    try:
        stat = os.stat(source_path)
        cache_key = hashlib.sha1(
            f'{relative_path}:{stat.st_mtime_ns}:{stat.st_size}'.encode('utf-8')
        ).hexdigest()[:24]
        cache_dir = os.path.join(app.config['UPLOAD_FOLDER'], '.thumb_cache')
        cache_path = os.path.join(cache_dir, f'{cache_key}.jpg')
        if not os.path.isfile(cache_path):
            with photo_thumbnail_lock:
                if not os.path.isfile(cache_path):
                    os.makedirs(cache_dir, exist_ok=True)
                    with Image.open(source_path) as image:
                        image = ImageOps.exif_transpose(image).convert('RGB')
                        image = ImageOps.fit(
                            image,
                            (192, 192),
                            method=Image.Resampling.LANCZOS,
                            centering=(0.5, 0.38),
                        )
                        image.save(cache_path, 'JPEG', quality=78, optimize=True, progressive=True)
        response = send_file(cache_path, mimetype='image/jpeg', conditional=True, max_age=2592000)
        response.cache_control.public = False
        response.cache_control.private = True
        return response
    except Exception as exc:
        print(f'Photo thumbnail failed for {relative_path}: {type(exc).__name__}: {exc}')
        return '', 404


# --- Нормализация фото для терминалов Hikvision -------------------------------
# Терминалы принимают только JPEG, отклоняют CMYK/градации серого/альфа-канал,
# слишком маленькие и слишком тяжелые файлы (ISAPI statusCode 6 "Invalid Content").
HIK_FACE_MIN_SIDE = 480
HIK_FACE_MAX_SIDE = 1200
HIK_FACE_MAX_BYTES = 190 * 1024
HIK_FACE_MIN_BYTES = 12 * 1024


def resolve_static_photo_file(photo_path):
    """Абсолютный путь к файлу фото внутри static, либо None."""
    relative_path = normalize_static_photo_path(photo_path)
    if not relative_path:
        return None
    static_root = os.path.abspath(app.static_folder)
    source_path = os.path.abspath(os.path.join(static_root, relative_path))
    try:
        if os.path.commonpath([static_root, source_path]) != static_root:
            return None
    except ValueError:
        return None
    return source_path if os.path.isfile(source_path) else None


def build_hikvision_face_jpeg(photo_path):
    """Привести фото к виду, который терминал точно примет.

    Возвращает (jpeg_bytes, info) или (None, info) с причиной отказа.
    """
    info = {'ok': False, 'reason': None, 'width': 0, 'height': 0, 'bytes': 0, 'source_format': None}
    source_path = resolve_static_photo_file(photo_path)
    if not source_path:
        info['reason'] = 'Файл фото не найден на сервере'
        return None, info

    try:
        with Image.open(source_path) as raw:
            info['source_format'] = (raw.format or '').upper()
            image = ImageOps.exif_transpose(raw)
            if image.mode in ('RGBA', 'LA', 'P'):
                image = image.convert('RGBA')
                flat = Image.new('RGB', image.size, (255, 255, 255))
                flat.paste(image, mask=image.split()[-1])
                image = flat
            else:
                image = image.convert('RGB')

            width, height = image.size
            if width < 20 or height < 20:
                info['reason'] = f'Фото слишком маленькое ({width}x{height})'
                return None, info

            # Апскейл, если терминалу не хватит пикселей на лицо
            scale_up = max(HIK_FACE_MIN_SIDE / width, HIK_FACE_MIN_SIDE / height, 1.0)
            # Даунскейл, если картинка огромная
            scale_down = min(HIK_FACE_MAX_SIDE / width, HIK_FACE_MAX_SIDE / height, 1.0)
            scale = scale_up if scale_up > 1.0 else scale_down
            if abs(scale - 1.0) > 0.01:
                image = image.resize(
                    (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
                    Image.Resampling.LANCZOS
                )

            info['width'], info['height'] = image.size

            data = None
            for quality in (92, 88, 82, 76, 70, 64, 58, 50):
                buffer = io.BytesIO()
                image.save(buffer, 'JPEG', quality=quality, optimize=True, subsampling=0)
                data = buffer.getvalue()
                if len(data) <= HIK_FACE_MAX_BYTES:
                    break

            if data and len(data) > HIK_FACE_MAX_BYTES:
                # Последняя попытка: уменьшить сторону и пережать
                shrunk = image.copy()
                shrunk.thumbnail((HIK_FACE_MIN_SIDE, HIK_FACE_MIN_SIDE), Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                shrunk.save(buffer, 'JPEG', quality=72, optimize=True, subsampling=0)
                data = buffer.getvalue()
                info['width'], info['height'] = shrunk.size

            if not data:
                info['reason'] = 'Не удалось пережать фото в JPEG'
                return None, info
            if len(data) > HIK_FACE_MAX_BYTES:
                info['reason'] = f'Фото не сжимается до {HIK_FACE_MAX_BYTES // 1024} КБ'
                return None, info

            info['bytes'] = len(data)
            info['ok'] = True
            if len(data) < HIK_FACE_MIN_BYTES:
                info['warning'] = 'Фото очень низкого качества, терминал может его отклонить'
            return data, info
    except Exception as exc:
        info['reason'] = f'Фото повреждено или неподдерживаемый формат ({type(exc).__name__})'
        return None, info


def photo_signature(photo_path):
    """Короткая подпись файла фото: меняется, как только фото заменили.

    Нужна bridge, чтобы понять, что в терминале лежит устаревшее лицо.
    """
    source_path = resolve_static_photo_file(photo_path)
    if not source_path:
        return ''
    try:
        stat = os.stat(source_path)
        return hashlib.sha1(
            f'{stat.st_mtime_ns}:{stat.st_size}'.encode('utf-8')
        ).hexdigest()[:16]
    except OSError:
        return ''


def resolve_person_photo_path(person_type, person_id):
    if person_type == 'staff':
        user = db.session.get(User, int(person_id))
        return user.photo_path if user else None
    student = db.session.get(Student, int(person_id))
    return student.photo_path if student else None


@app.route('/api/hikvision/face-photo', methods=['GET'])
def hikvision_face_photo():
    """Готовый к записи в терминал JPEG. Забирает локальный bridge."""
    if not check_bridge_auth():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    person_type = (request.args.get('person_type') or 'student').strip()
    person_id = request.args.get('person_id')
    if person_type not in {'student', 'staff'} or not person_id:
        return jsonify({'success': False, 'message': 'Invalid person request'}), 400

    try:
        photo_path = resolve_person_photo_path(person_type, person_id)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Invalid person id'}), 400
    if not photo_path:
        return jsonify({'success': False, 'message': 'Нет фото для Face ID'}), 404

    # Кэш: одно и то же фото пережимаем один раз, дальше отдаем с диска.
    cache_path = None
    source_path = resolve_static_photo_file(photo_path)
    if source_path:
        try:
            stat = os.stat(source_path)
            cache_key = hashlib.sha1(
                f'hikface:{source_path}:{stat.st_mtime_ns}:{stat.st_size}'.encode('utf-8')
            ).hexdigest()[:24]
            cache_dir = os.path.join(app.config['UPLOAD_FOLDER'], '.hik_face_cache')
            cache_path = os.path.join(cache_dir, f'{cache_key}.jpg')
            if os.path.isfile(cache_path):
                response = send_file(cache_path, mimetype='image/jpeg', conditional=False)
                response.cache_control.no_store = True
                return response
        except OSError:
            cache_path = None

    data, info = build_hikvision_face_jpeg(photo_path)
    if not data:
        return jsonify({'success': False, 'message': info.get('reason') or 'Фото не подходит'}), 422

    if cache_path:
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            temp_path = f'{cache_path}.tmp'
            with open(temp_path, 'wb') as handle:
                handle.write(data)
            os.replace(temp_path, cache_path)
        except OSError as exc:
            print(f'hikvision face cache write failed: {type(exc).__name__}: {exc}')

    response = Response(data, mimetype='image/jpeg')
    response.headers['Content-Length'] = str(len(data))
    response.headers['X-Face-Width'] = str(info['width'])
    response.headers['X-Face-Height'] = str(info['height'])
    response.cache_control.no_store = True
    return response


def get_user_photo_thumb_path(photo_path):
    if not photo_path:
        return None
    directory, filename = os.path.split(photo_path)
    name, ext = os.path.splitext(filename)
    if not name:
        return None
    return os.path.join(directory, f"{name}_thumb{ext or '.jpg'}")


def build_user_photo_thumb_url(photo_path):
    if not photo_path:
        return url_for('static', filename='uploads/avatar_ccount_thumb.png')
    thumb_path = get_user_photo_thumb_path(photo_path)
    if thumb_path and os.path.exists(thumb_path):
        return build_photo_url(thumb_path)
    return build_photo_thumb_url(photo_path) or url_for('static', filename='uploads/avatar_ccount_thumb.png')


def delete_user_photo_files(photo_path):
    if not photo_path:
        return
    for path in {photo_path, get_user_photo_thumb_path(photo_path)}:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception as photo_error:
            print(f"Ошибка при удалении фото сотрудника: {photo_error}")


def detect_upload_image_extension(image_file):
    """Расширение файла по его содержимому, а не по имени.

    Имя доверять нельзя: secure_filename срезает кириллицу вместе с точкой
    ('логотип.png' -> 'png'), а браузеры и телефоны присылают .jfif, .HEIC
    и расширения в верхнем регистре. Раньше такие файлы отклонялись
    с сообщением «Поддерживаются PNG, JPG, WEBP».
    """
    try:
        image_file.stream.seek(0)
        with Image.open(image_file.stream) as image:
            image_format = (image.format or '').upper()
            has_alpha = 'A' in image.getbands()
    except Exception:
        raise ValueError('Не удалось прочитать изображение. Загрузите PNG, JPG или WEBP')
    finally:
        try:
            image_file.stream.seek(0)
        except Exception:
            pass

    if image_format == 'PNG':
        return '.png'
    if image_format == 'JPEG':
        return '.jpg'
    if image_format == 'WEBP':
        return '.webp'
    # Остальные читаемые форматы (GIF, BMP, TIFF) конвертируем при сохранении.
    return '.png' if has_alpha else '.jpg'


def save_optimized_logo_upload(logo_file, filepath, max_size):
    """Keep uploaded branding visually intact while preventing multi-megabyte originals."""
    extension = os.path.splitext(filepath)[1].lower()
    with Image.open(logo_file.stream) as image:
        image = ImageOps.exif_transpose(image)
        if image.width * image.height > 40_000_000:
            raise ValueError('Изображение слишком большое')
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        if extension == '.png':
            image.convert('RGBA' if 'A' in image.getbands() else 'RGB').save(
                filepath, 'PNG', optimize=True, compress_level=9
            )
        elif extension in {'.jpg', '.jpeg'}:
            image.convert('RGB').save(filepath, 'JPEG', quality=88, optimize=True, progressive=True)
        else:
            image.save(filepath, 'WEBP', quality=86, method=6)


def save_tournament_team_logo(logo_file, old_logo_path=None):
    if not logo_file or not logo_file.filename:
        return old_logo_path
    ext = detect_upload_image_extension(logo_file)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    filename = f"tournament_team_logo_{int(time.time())}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    save_optimized_logo_upload(logo_file, filepath, (640, 640))

    if old_logo_path:
        old_filename = old_logo_path.replace('\\', '/').split('/')[-1]
        if old_filename.startswith('tournament_team_logo_'):
            old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_filename)
            try:
                if os.path.exists(old_path):
                    os.remove(old_path)
            except OSError:
                pass
    return os.path.join('frontend', 'static', 'uploads', filename)


def save_tournament_catalog_photo(photo_file, prefix, old_photo_path=None):
    if not photo_file or not photo_file.filename:
        return old_photo_path
    ext = detect_upload_image_extension(photo_file)

    safe_prefix = re.sub(r'[^a-z0-9_]+', '_', str(prefix).lower()).strip('_')
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    filename = f"{safe_prefix}_{int(time.time())}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    save_optimized_logo_upload(photo_file, filepath, (1200, 1200))
    delete_tournament_catalog_media(old_photo_path, (f'{safe_prefix}_',))
    return os.path.join('frontend', 'static', 'uploads', filename)


def delete_tournament_catalog_media(media_path, allowed_prefixes=(
    'tournament_poster_',
    'tournament_team_logo_',
    'tournament_trainer_',
    'tournament_member_',
)):
    if not media_path:
        return
    filename = media_path.replace('\\', '/').split('/')[-1]
    if not any(filename.startswith(prefix) for prefix in allowed_prefixes):
        return
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            os.remove(filepath)
    except OSError:
        pass


def delete_tournament_team_logo(logo_path):
    delete_tournament_catalog_media(logo_path, ('tournament_team_logo_',))


def save_user_photo(photo_file, user_id):
    if not photo_file or not photo_file.filename:
        return None
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    try:
        ext = detect_upload_image_extension(photo_file)
    except ValueError:
        ext = '.jpg'
    filename = f"user_{user_id}_{int(time.time())}{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    photo_file.save(filepath)
    try:
        with Image.open(filepath) as image:
            image = image.convert('RGB')
            image.thumbnail((160, 160), Image.LANCZOS)
            thumb_path = get_user_photo_thumb_path(filepath)
            image.save(thumb_path, quality=82, optimize=True)
    except Exception as thumb_error:
        print(f"Ошибка при создании миниатюры сотрудника: {thumb_error}")
    return os.path.join('frontend', 'static', 'uploads', filename)


@app.route('/portal/login', methods=['GET', 'POST'])
def portal_login():
    if request.method == 'POST':
        data = request.get_json() or {}
        phone_input = (data.get('phone') or '').strip()
        code_input = (data.get('code') or '').strip()

        if not phone_input or not code_input:
            return jsonify({'success': False, 'message': 'Введите номер и код'}), 400

        candidates = Student.query.filter(or_(Student.phone.isnot(None), Student.parent_phone.isnot(None))).all()
        matched = None
        for student in candidates:
            if phones_match(student.phone, phone_input) or phones_match(student.parent_phone, phone_input):
                matched = student
                break

        # Возвращаем 200 с success:false, чтобы на фронте не сыпались 404/401
        if not matched:
            return jsonify({'success': False, 'message': 'Номер не найден'})

        # Код сравниваем без регистра и с trim
        student_code = (matched.telegram_link_code or '').strip().upper()
        if not student_code or student_code != code_input.upper():
            return jsonify({'success': False, 'message': 'Неверный код'})

        session['portal_student_id'] = matched.id
        return jsonify({'success': True, 'redirect': '/portal'})

    return render_template('portal_login.html')


@app.route('/portal/logout')
def portal_logout():
    session.pop('portal_student_id', None)
    return redirect(url_for('portal_login'))


@app.route('/portal')
def portal_home():
    student = get_portal_student()
    if not student:
        return redirect(url_for('portal_login'))
    return render_template('portal.html')


@app.route('/api/portal/me')
def portal_me():
    student = get_portal_student()
    if not student:
        return jsonify({'success': False, 'message': 'Not authorized'}), 401

    settings = get_club_settings_instance()
    telegram_bot_url = getattr(settings, 'telegram_bot_url', '') or ''

    # Информация о группе
    group_info = None
    days_list = []
    if student.group:
        try:
            days_list = student.group.get_schedule_days_list() if hasattr(student.group, 'get_schedule_days_list') else []
            days_names = [DAY_LABELS.get(d, str(d)) for d in days_list] if days_list else []
            
            # schedule_time теперь может быть строкой "HH:MM" или JSON
            schedule_time_str = '—'
            if student.group.schedule_time:
                try:
                    # Пробуем распарсить как JSON
                    time_map = json.loads(student.group.schedule_time)
                    if isinstance(time_map, dict):
                        # Показываем времена для каждого дня
                        time_strs = []
                        for day in days_list:
                            day_time = time_map.get(str(day))
                            if day_time:
                                time_strs.append(f"{DAY_LABELS.get(day, str(day))} {day_time}")
                        schedule_time_str = ', '.join(time_strs) if time_strs else '—'
                except (json.JSONDecodeError, ValueError):
                    # Обычная строка HH:MM
                    schedule_time_str = student.group.schedule_time
            
            group_info = {
                'name': student.group.name,
                'schedule_days': ', '.join(days_names) if days_names else '—',
                'schedule_days_list': days_list,
                'schedule_time': schedule_time_str,
                'schedule_time_map': student.group.get_schedule_time_map()  # Для фронтенда
            }
        except Exception as e:
            print(f"Error getting group info: {e}")
            group_info = {
                'name': student.group.name,
                'schedule_days': '—',
                'schedule_days_list': [],
                'schedule_time': '—',
                'schedule_time_map': None
            }
    
    # Информация о тарифе
    tariff_info = None
    try:
        if student.tariff:
            tariff_info = {
                'name': student.tariff.name,
                'price': student.tariff.price,
                'lessons_count': student.tariff.lessons_count
            }
        elif student.tariff_type:
            tariff_info = {'name': student.tariff_type, 'price': None, 'lessons_count': None}
    except Exception as e:
        print(f"Error getting tariff info: {e}")
        tariff_info = {'name': student.tariff_type or 'Не указан', 'price': None, 'lessons_count': None}

    rewards = StudentReward.query.filter_by(student_id=student.id).order_by(StudentReward.issued_at.desc()).limit(10).all()
    cards = StudentCard.query.filter_by(student_id=student.id).order_by(StudentCard.issued_at.desc()).limit(10).all()

    # Посещаемость за текущий месяц
    today_local = get_local_date()
    first_day = today_local.replace(day=1)
    next_month = (first_day + timedelta(days=32)).replace(day=1)
    last_day = next_month - timedelta(days=1)

    # Считаем посещения по уникальным датам (а не по количеству записей, т.к. может быть несколько чек-инов в день)
    attendance_done = db.session.query(Attendance.date).filter(
        Attendance.student_id == student.id,
        Attendance.date >= first_day,
        Attendance.date <= last_day
    ).distinct().count()

    schedule_days_for_calc = days_list or []
    attendance_plan = 0
    if schedule_days_for_calc:
        current_day = first_day
        while current_day <= last_day:
            if current_day.isoweekday() in schedule_days_for_calc:
                attendance_plan += 1
            current_day += timedelta(days=1)

    rewards_payload = [
        {
            'name': r.reward_name,
            'points': r.points,
            'issued_at': r.issued_at.isoformat() if r.issued_at else None
        }
        for r in rewards
    ]

    cards_payload = [
        {
            'name': c.card_type.name if (c.card_type and hasattr(c.card_type, 'name')) else 'Карточка',
            'card_type': c.card_type.name if (c.card_type and hasattr(c.card_type, 'name')) else (c.card_type.color if (c.card_type and hasattr(c.card_type, 'color')) else 'yellow'),
            'color': c.card_type.color if (c.card_type and hasattr(c.card_type, 'color')) else None,
            'reason': c.reason,
            'issued_at': c.issued_at.isoformat() if c.issued_at else None,
            'is_active': c.is_active
        }
        for c in cards
    ]

    # Генерируем даты тренировок для текущего и следующего месяца
    training_dates = []
    if schedule_days_for_calc and student.group:
        # Берем данные за 2 месяца (текущий и следующий)
        start_date = first_day
        end_date = last_day + timedelta(days=31)  # +месяц вперед
        
        # Получаем все посещения студента
        attended_dates = {
            att.date.isoformat(): {
                'attended': True,
                'is_late': att.is_late,
                'late_minutes': att.late_minutes
            }
            for att in Attendance.query.filter(
                Attendance.student_id == student.id,
                Attendance.date >= start_date,
                Attendance.date <= end_date
            ).all()
        }
        
        # Генерируем даты тренировок
        current_day = start_date
        schedule_time_map = student.group.get_schedule_time_map()
        
        while current_day <= end_date:
            weekday = current_day.isoweekday()
            if weekday in schedule_days_for_calc:
                date_str = current_day.isoformat()
                attendance_info = attended_dates.get(date_str)
                
                # Определяем время тренировки для этого дня
                training_time = None
                if schedule_time_map:
                    training_time = schedule_time_map.get(weekday)
                else:
                    # Простое время для всех дней
                    training_time = student.group.schedule_time
                
                training_dates.append({
                    'date': date_str,
                    'weekday': weekday,
                    'time': training_time if training_time else '—',
                    'attended': attendance_info is not None,
                    'is_late': attendance_info['is_late'] if attendance_info else False,
                    'late_minutes': attendance_info['late_minutes'] if attendance_info else 0
                })
            current_day += timedelta(days=1)

    return jsonify({
        'success': True,
        'telegram_bot_url': telegram_bot_url,
        'student': {
            'id': student.id,
            'full_name': student.full_name,
            'group': group_info,
            'tariff': tariff_info,
            'balance': student.balance,
            'phone': student.phone,
            'parent_phone': student.parent_phone,
            'status': student.status,
            'photo_url': build_photo_url(student.photo_path),
            'city': student.city,
            'district': student.district,
            'street': student.street,
            'house_number': student.house_number,
            'admission_date': student.admission_date.isoformat() if student.admission_date else None,
            'birth_year': student.birth_year,
            'passport_series': student.passport_series,
            'passport_number': student.passport_number,
            'passport_issued_by': student.passport_issued_by,
            'passport_issue_date': student.passport_issue_date.isoformat() if student.passport_issue_date else None,
            'passport_expiry_date': student.passport_expiry_date.isoformat() if student.passport_expiry_date else None,
            'height': student.height,
            'weight': student.weight,
            'dominant_side': getattr(student, 'dominant_side', None),
            'jersey_size': student.jersey_size,
            'shorts_size': student.shorts_size,
            'boots_size': student.boots_size,
            'equipment_notes': student.equipment_notes
        },
        'rewards': rewards_payload,
        'cards': cards_payload,
        'attendance_month_done': attendance_done,
        'attendance_month_total': attendance_plan,
        'training_dates': training_dates  # Даты тренировок с информацией о посещении
    })


@app.route('/api/portal/attendance')
def portal_attendance():
    student = get_portal_student()
    if not student:
        return jsonify({'success': False, 'message': 'Not authorized'}), 401

    records = Attendance.query.filter_by(student_id=student.id).order_by(Attendance.date.desc()).limit(60).all()
    data = [
        {
            'date': r.date.isoformat() if r.date else None,
            'is_late': r.is_late,
            'late_minutes': r.late_minutes,
            'lesson_deducted': r.lesson_deducted
        }
        for r in records
    ]
    print(f"📊 Portal attendance for student {student.id}: {len(records)} records")
    for r in records[:5]:
        print(f"   - {r.date} (ID: {r.id})")
    return jsonify({'success': True, 'attendance': data})


@app.route('/api/portal/payments')
def portal_payments():
    student = get_portal_student()
    if not student:
        return jsonify({'success': False, 'message': 'Not authorized'}), 401

    payments = Payment.query.filter_by(student_id=student.id).order_by(Payment.payment_date.desc()).limit(60).all()
    data = [
        {
            'amount_paid': p.amount_paid,
            'amount_due': p.amount_due,
            'payment_date': p.payment_date.isoformat() if p.payment_date else None,
            'payment_type': p.payment_type,
            'notes': p.notes,
            'tariff_name': p.tariff_name
        }
        for p in payments
    ]
    return jsonify({'success': True, 'payments': data})


# ===== ГЛАВНАЯ ПАНЕЛЬ =====

@app.route('/dashboard')
@login_required
def dashboard():
    # Статистика
    total_students = Student.query.filter_by(status='active').count()
    # Пакетный расчет баланса вместо отдельных запросов на каждого ученика.
    active_students = Student.query.options(joinedload(Student.tariff)).filter_by(status='active').all()
    balances = calculate_student_balances_bulk(active_students)
    students_low_balance = sum(1 for student in active_students if balances.get(student.id, 0) <= 2)
    
    today = get_local_date()
    today_attendance = Attendance.query.filter_by(date=today).count()
    
    # Доходы за месяц
    month_start = get_local_datetime().replace(day=1)
    month_income = db.session.query(db.func.sum(Payment.amount_paid)).filter(
        Payment.payment_date >= month_start
    ).scalar() or 0
    
    # Расходы за месяц
    month_expenses = db.session.query(db.func.sum(Expense.amount)).filter(
        Expense.expense_date >= month_start
    ).scalar() or 0
    
    return render_template('dashboard.html',
                         total_students=total_students,
                         students_low_balance=students_low_balance,
                         today_attendance=today_attendance,
                         month_income=month_income,
                         month_expenses=month_expenses,
                         profit=month_income - month_expenses)


# ===== УЧЕНИКИ =====

@app.route('/students')
@login_required
def students():
    all_students = []
    return render_template('students.html',
                         student_card_sections=get_student_card_sections(),
                           students=all_students,
                           payment_info={},
                           balances={},
                           student_points={},
                           access_info={})


@app.route('/groups')
@login_required
def groups_page():
    return render_template('groups.html')


@app.route('/api/students', methods=['GET'])
@login_required
def get_students_list():
    """Возвращает всех учеников для фильтров"""
    list_view = request.args.get('view') == 'list'
    if list_view:
        page = max(request.args.get('page', 1, type=int) or 1, 1)
        per_page = min(max(request.args.get('per_page', 80, type=int) or 80, 1), 200)
        group_id = request.args.get('group_id', type=int)
        search = (request.args.get('q') or '').strip()
        status = (request.args.get('status') or '').strip()

        query = Student.query.options(
            joinedload(Student.group),
            joinedload(Student.tariff)
        ).outerjoin(Group)

        if group_id:
            query = query.filter(Student.group_id == group_id)
        if status:
            query = query.filter(Student.status == status)
        if search:
            like = f"%{search.lower()}%"
            query = query.filter(or_(
                func.lower(Student.full_name).like(like),
                func.lower(func.coalesce(Student.student_number, '')).like(like),
                func.lower(func.coalesce(Student.phone, '')).like(like),
                func.lower(func.coalesce(Student.parent_phone, '')).like(like),
                func.lower(func.coalesce(Group.name, '')).like(like),
            ))

        pagination = query.order_by(Group.name.asc(), Student.full_name.asc()).paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        students = pagination.items
        balances = calculate_student_balances_bulk(students)
        today = get_local_date()
        points = get_student_points_bulk([student.id for student in students], today.month, today.year)

        settings = get_club_settings_instance()
        paid_map = get_month_paid_map(today.year, today.month)
        payment_date_paid_map = get_payment_date_paid_map(today.year, today.month)
        access_policy = get_access_payment_policy(settings)
        debt_month_counts = (
            get_debt_month_counts(students, settings, today, include_current=False)
            if access_policy in {'partial_current_month', 'any_payment_this_month'}
            else {}
        )
        face_states = get_terminal_face_state_bulk([str(student.id) for student in students])
        # Один запрос на всю страницу вместо запроса на каждого ученика
        student_ids_page = [student.id for student in students]
        discount_months = get_discount_months(student_ids_page, today.year)
        attendance_counts = (
            get_attendance_counts_by_month(student_ids_page, today.year)
            if get_min_lessons_for_debt(settings) else {}
        )

        items = []
        for student in students:
            balance = balances.get(student.id, 0)
            access = build_student_access_payload(
                student,
                settings,
                paid_map,
                payment_date_paid_map,
                today,
                debt_month_count=debt_month_counts.get(student.id),
                discount_months=discount_months,
                attendance_counts=attendance_counts
            )
            group_name = student.group.name if student.group else 'Без группы'
            photo_url = build_photo_thumb_url(student.photo_path)
            search_text = ' '.join(filter(None, [
                student.full_name,
                student.student_number,
                student.phone,
                student.parent_phone,
                group_name,
            ])).lower()
            items.append({
                'id': student.id,
                'full_name': student.full_name,
                'student_number': student.student_number,
                'group_id': student.group_id,
                'group_name': group_name,
                'status': student.status,
                'birth_year': student.birth_year,
                'club_funded': bool(student.club_funded),
                'balance': balance,
                'points': points.get(student.id, 0),
                'photo_url': photo_url,
                'search': search_text,
                'status_label': student_status_label(student.status),
                'is_archived': student.status == 'archived',
                'will_pass': bool(access['can_sync_to_turnstile']),
                'access_reason': access['reason'],
                'access_reason_label': access['reason_label'],
                'has_photo': bool(access['has_photo']),
                'terminals': face_states.get(str(student.id), []),
            })

        return jsonify({
            'items': items,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev,
        })

    options_view = request.args.get('view') == 'options'
    if options_view:
        group_id = request.args.get('group_id', type=int)
        active_only = request.args.get('active_only') in {'1', 'true', 'yes'}

        query = Student.query.options(
            joinedload(Student.group),
            joinedload(Student.tariff)
        )
        if group_id:
            query = query.filter(Student.group_id == group_id)
        if active_only:
            query = query.filter(Student.status == 'active')

        students = query.order_by(Student.full_name.asc()).all()
        return jsonify([
            {
                'id': student.id,
                'full_name': student.full_name,
                'student_number': student.student_number,
                'group_id': student.group_id,
                'group_name': student.group.name if student.group else None,
                'status': student.status,
                'photo_path': student.photo_path,
                'photo_url': build_photo_thumb_url(student.photo_path),
                'tariff_id': student.tariff_id,
                'tariff_name': student.tariff.name if student.tariff else None,
                'tariff_price': student.tariff.price if student.tariff else 0,
            }
            for student in students
        ])

    ensure_club_settings_columns()
    settings = get_club_settings_instance()
    today = get_local_date()
    paid_map = get_month_paid_map(today.year, today.month)
    payment_date_paid_map = get_payment_date_paid_map(today.year, today.month)
    students = Student.query.options(
        joinedload(Student.group),
        joinedload(Student.tariff)
    ).order_by(Student.full_name.asc()).all()
    result = []
    for student in students:
        access_payload = build_student_access_payload(student, settings, paid_map, payment_date_paid_map, today)
        result.append({
            'id': student.id,
            'full_name': student.full_name,
            'student_number': student.student_number,
            'group_id': student.group_id,
            'group_name': student.group.name if student.group else None,
            'status': student.status,
            'photo_path': student.photo_path,
            'admission_date': student.admission_date.isoformat() if student.admission_date else None,
            'turnstile_access': access_payload
        })
    return jsonify(result)


@app.route('/api/students/add', methods=['POST'])
@login_required
def add_student():
    try:
        full_name = request.form.get('full_name')
        phone = format_uz_phone(request.form.get('phone'))
        parent_phone = format_uz_phone(request.form.get('parent_phone'))
        photo = request.files.get('photo')
        
        # Новые поля
        group_id = request.form.get('group_id')
        tariff_id = request.form.get('tariff_id')
        school_number = request.form.get('school_number')
        city = request.form.get('city')
        district = request.form.get('district')
        street = request.form.get('street')
        house_number = request.form.get('house_number')
        
        birth_year = request.form.get('birth_year')
        passport_series = request.form.get('passport_series')
        passport_number = request.form.get('passport_number')
        passport_issued_by = request.form.get('passport_issued_by')
        passport_issue_date = request.form.get('passport_issue_date')
        passport_expiry_date = request.form.get('passport_expiry_date')
        admission_date_raw = request.form.get('admission_date')
        
        club_funded = request.form.get('club_funded') == 'true'
        first_month_fee_raw = (request.form.get('first_month_fee') or '').replace(' ', '').strip()
        first_month_fee = safe_float(first_month_fee_raw) if first_month_fee_raw else None
        status = request.form.get('status', 'active')
        blacklist_reason = request.form.get('blacklist_reason')
        student_number = (request.form.get('student_number') or '').strip()
        group_id_int = int(group_id) if group_id else None
        
        # Если номер не указан, автогенерируем последовательно (1, 2, 3...)
        if not student_number:
            student_number = get_next_available_student_number(group_id_int)

        if not student_number:
            return jsonify({
                'success': False,
                'message': 'Свободные номера в группе закончились (0-99)'
            }), 400
        
        # Валидация номера
        is_valid, error_msg = validate_student_number(student_number, group_id_int)
        if not is_valid:
            return jsonify({'success': False, 'message': error_msg}), 400
        
        # Проверить, не переполнена ли группа
        if group_id:
            group = db.session.get(Group, int(group_id))
            if group and group.is_full():
                current_count = group.get_current_students_count()
                return jsonify({
                    'success': False, 
                    'message': f'Группа "{group.name}" заполнена ({current_count}/{group.max_students})'
                }), 400
        
        if admission_date_raw:
            try:
                admission_date = datetime.strptime(admission_date_raw, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'message': 'Некорректная дата принятия'}), 400
        else:
            admission_date = get_local_date()

        # Параметры ученика
        height = request.form.get('height')
        weight = request.form.get('weight')
        dominant_side = request.form.get('dominant_side') if request.form.get('dominant_side') in {'left', 'right'} else None
        jersey_size = request.form.get('jersey_size')
        shorts_size = request.form.get('shorts_size')
        boots_size = request.form.get('boots_size')
        equipment_notes = request.form.get('equipment_notes')
        
        # Helper for safe int/float conversion
        def safe_int(val, default=None):
            try: return int(val) if val else default
            except (ValueError, TypeError): return default

        def safe_float(val, default=None):
            try: return float(val) if val else default
            except (ValueError, TypeError): return default

        # Создать ученика
        student = Student(
            student_number=student_number,
            school_number=school_number,
            full_name=full_name,
            phone=phone,
            parent_phone=parent_phone,
            balance=0,
            status=status,
            blacklist_reason=blacklist_reason if status == 'blacklist' else None,
            group_id=group_id_int,
            tariff_id=safe_int(tariff_id),
            telegram_link_code=generate_telegram_link_code(),
            city=city,
            district=district,
            street=street,
            house_number=house_number,
            birth_year=safe_int(birth_year),
            passport_series=passport_series,
            passport_number=passport_number,
            passport_issued_by=passport_issued_by,
            passport_issue_date=datetime.strptime(passport_issue_date, '%Y-%m-%d').date() if (passport_issue_date and passport_issue_date.strip()) else None,
            passport_expiry_date=datetime.strptime(passport_expiry_date, '%Y-%m-%d').date() if (passport_expiry_date and passport_expiry_date.strip()) else None,
            admission_date=admission_date,
            club_funded=club_funded,
            first_month_fee=first_month_fee,
            height=safe_int(height),
            weight=safe_float(weight),
            dominant_side=dominant_side,
            jersey_size=jersey_size,
            shorts_size=shorts_size,
            boots_size=boots_size,
            equipment_notes=equipment_notes
        )
        db.session.add(student)
        db.session.flush()
        
        # Сохранить фото и извлечь face encoding
        encoding_updated = False
        if photo:
            photo_path = face_service.save_student_photo(photo, student.id)
            student.photo_path = photo_path
            access_face_verifier.invalidate_candidate_index()
            
            encoding = face_service.extract_embedding(photo_path)
            if encoding is not None:
                student.set_face_encoding(encoding)
                encoding_updated = True
            else:
                # Если лицо не найдено, не блокируем создание, просто нет вектора
                print(f"⚠️ Лицо не обнаружено для студента {student.id}, пропускаем создание вектора")
        
        queue_hikvision_person('student', student.id, 'student_created')
        db.session.commit()

        if encoding_updated:
            reload_face_encodings()
        
        return jsonify({'success': True, 'student_id': student.id, 'student_number': student_number})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/students/<int:student_id>', methods=['GET'])
@login_required
def get_student(student_id):
    student = Student.query.options(
        joinedload(Student.group),
        joinedload(Student.tariff)
    ).filter(Student.id == student_id).first_or_404()
    ensure_club_settings_columns()
    settings = get_club_settings_instance()
    today = get_local_date()
    paid_map = get_month_paid_map(today.year, today.month)
    payment_date_paid_map = get_payment_date_paid_map(today.year, today.month)
    access_payload = build_student_access_payload(student, settings, paid_map, payment_date_paid_map, today)
    current_points = get_student_points_sum(student.id, today.month, today.year)
    
    # Явно загружаем тариф, если он есть
    tariff_name = None
    tariff_price = 500000  # Дефолтная цена
    if student.tariff_id:
        tariff = db.session.get(Tariff, student.tariff_id)
        if tariff:
            tariff_name = tariff.name
            tariff_price = float(tariff.price) if tariff.price else 500000
    elif student.tariff:
        # Если тариф загружен через relationship
        tariff_name = student.tariff.name if student.tariff.name else None
        tariff_price = float(student.tariff.price) if student.tariff.price else 500000
    
    # Получить информацию о группе и расписании
    group_schedule_days = []
    group_schedule_time = None
    if student.group_id:
        # Явно загружаем группу
        group = db.session.get(Group, student.group_id)
        if group:
            group_schedule_days = group.get_schedule_days_list()
            group_schedule_time = group.schedule_time if group.schedule_time else None
    
    photo_url = None
    if student.photo_path:
        photo_url = url_for(
            'static',
            filename=student.photo_path.replace('frontend/static/', '').replace('\\', '/').lstrip('/')
        )

    return jsonify({
        'id': student.id,
        'student_number': student.student_number,
        'school_number': student.school_number,
        'full_name': student.full_name,
        'phone': student.phone,
        'parent_phone': student.parent_phone,
        'balance': calculate_student_balance(student),
        'points': current_points,
        'status': student.status,
        'blacklist_reason': student.blacklist_reason,
        'group_id': student.group_id,
        'group_name': student.group.name if student.group else None,
        'tariff_id': student.tariff_id,
        'tariff_name': tariff_name,
        'tariff_price': tariff_price,
        'city': student.city,
        'district': student.district,
        'street': student.street,
        'house_number': student.house_number,
        'birth_year': student.birth_year,
        'passport_series': student.passport_series,
        'passport_number': student.passport_number,
        'passport_issued_by': student.passport_issued_by,
        'passport_issue_date': student.passport_issue_date.isoformat() if student.passport_issue_date else None,
        'passport_expiry_date': student.passport_expiry_date.isoformat() if student.passport_expiry_date else None,
        'admission_date': student.admission_date.isoformat() if student.admission_date else None,
        'club_funded': student.club_funded,
        'telegram_link_code': student.telegram_link_code,
        'telegram_chat_id': student.telegram_chat_id,
        'telegram_notifications_enabled': student.telegram_notifications_enabled,
        'telegram_link_code': student.telegram_link_code,
        'telegram_chat_id': student.telegram_chat_id,
        'telegram_notifications_enabled': student.telegram_notifications_enabled,
        'photo_path': student.photo_path,
        'photo_url': photo_url,
        'height': student.height,
        'weight': student.weight,
        'dominant_side': getattr(student, 'dominant_side', None),
        'jersey_size': student.jersey_size,
        'shorts_size': student.shorts_size,
        'boots_size': student.boots_size,
        'equipment_notes': student.equipment_notes,
        'group_schedule_days': group_schedule_days,  # Дни недели занятий (1=Пн, 7=Вс)
        'group_schedule_time': group_schedule_time,  # Время начала занятия (HH:MM)
        'turnstile_access': access_payload,
        'first_month_fee': student.first_month_fee,
        'status_label': student_status_label(student.status),
        'terminals': get_student_terminal_face_state(student.id)
    })


@app.route('/api/students/<int:student_id>', methods=['PUT'])
@login_required
def update_student(student_id):
    try:
        student = Student.query.get_or_404(student_id)
        
        # Определить группу для валидации
        current_group_id = student.group_id
        if 'group_id' in request.form:
            new_group_id = int(request.form['group_id']) if request.form['group_id'] else None
            # Если группа меняется, нужно проверить номер в новой группе
            if new_group_id != current_group_id:
                current_group_id = new_group_id
        
        if 'student_number' in request.form:
            new_student_number = request.form['student_number'].strip()
            if not new_student_number:
                return jsonify({'success': False, 'message': 'Номер ученика не может быть пустым'}), 400
            
            # Валидация номера
            is_valid, error_msg = validate_student_number(new_student_number, current_group_id, exclude_student_id=student.id)
            if not is_valid:
                return jsonify({'success': False, 'message': error_msg}), 400
            
            student.student_number = new_student_number

        # Обновить поля из формы
        if 'full_name' in request.form:
            student.full_name = request.form['full_name']
        if 'school_number' in request.form:
            student.school_number = request.form['school_number'] or None
        if 'phone' in request.form:
            student.phone = format_uz_phone(request.form['phone'])
        if 'parent_phone' in request.form:
            student.parent_phone = format_uz_phone(request.form['parent_phone'])
        if 'status' in request.form:
            student.status = request.form['status']
            if request.form['status'] != 'blacklist':
                student.blacklist_reason = None
        if 'blacklist_reason' in request.form:
            student.blacklist_reason = request.form['blacklist_reason'] or None
        if 'group_id' in request.form:
            new_group_id = int(request.form['group_id']) if request.form['group_id'] else None
            old_group_id = student.group_id
            
            # Проверить, не переполнена ли новая группа (если группа меняется)
            if new_group_id and new_group_id != old_group_id:
                new_group = db.session.get(Group, new_group_id)
                if new_group and new_group.is_full():
                    current_count = new_group.get_current_students_count()
                    return jsonify({
                        'success': False, 
                        'message': f'Группа "{new_group.name}" заполнена ({current_count}/{new_group.max_students})'
                    }), 400
                
                # Если группа меняется, проверить номер в новой группе
                # Если номер занят в новой группе, предложить свободный
                is_valid, error_msg = validate_student_number(student.student_number, new_group_id, exclude_student_id=student.id)
                if not is_valid:
                    # Автоматически назначить свободный номер
                    free_number = get_next_available_student_number(new_group_id, exclude_student_id=student.id)
                    if not free_number:
                        return jsonify({
                            'success': False,
                            'message': f'Свободные номера в группе "{new_group.name if new_group else new_group_id}" закончились (0-99)'
                        }), 400
                    student.student_number = free_number
            
            student.group_id = new_group_id
        # Helper for safe int/float conversion
        def safe_int(val, default=None):
            try: return int(val) if val else default
            except (ValueError, TypeError): return default

        def safe_float(val, default=None):
            try: return float(val) if val else default
            except (ValueError, TypeError): return default

        if 'tariff_id' in request.form:
            student.tariff_id = safe_int(request.form['tariff_id'])
        if 'city' in request.form:
            student.city = request.form['city'] or None
        if 'district' in request.form:
            student.district = request.form['district'] or None
        if 'street' in request.form:
            student.street = request.form['street'] or None
        if 'house_number' in request.form:
            student.house_number = request.form['house_number'] or None
        if 'birth_year' in request.form:
            student.birth_year = safe_int(request.form['birth_year'])
        if 'passport_series' in request.form:
            student.passport_series = request.form['passport_series'] or None
        if 'passport_number' in request.form:
            student.passport_number = request.form['passport_number'] or None
        if 'passport_issued_by' in request.form:
            student.passport_issued_by = request.form['passport_issued_by'] or None
        if 'passport_issue_date' in request.form and request.form['passport_issue_date']:
            try:
                student.passport_issue_date = datetime.strptime(request.form['passport_issue_date'], '%Y-%m-%d').date()
            except ValueError: pass
        if 'passport_expiry_date' in request.form and request.form['passport_expiry_date']:
            try:
                student.passport_expiry_date = datetime.strptime(request.form['passport_expiry_date'], '%Y-%m-%d').date()
            except ValueError: pass
        if 'admission_date' in request.form:
            if request.form['admission_date'] and request.form['admission_date'].strip():
                try:
                    student.admission_date = datetime.strptime(request.form['admission_date'], '%Y-%m-%d').date()
                except ValueError:
                    return jsonify({'success': False, 'message': 'Некорректная дата принятия'}), 400
            else:
                student.admission_date = None
        
        # Обработать чекбокс club_funded
        student.club_funded = 'club_funded' in request.form and request.form['club_funded'] == 'true'

        if 'first_month_fee' in request.form:
            raw = (request.form.get('first_month_fee') or '').replace(' ', '').strip()
            student.first_month_fee = safe_float(raw) if raw else None
        
        # Параметры ученика
        if 'height' in request.form:
            student.height = safe_int(request.form['height'])
        if 'weight' in request.form:
            student.weight = safe_float(request.form['weight'])
        if 'dominant_side' in request.form:
            student.dominant_side = request.form['dominant_side'] if request.form['dominant_side'] in {'left', 'right'} else None
        if 'jersey_size' in request.form:
            student.jersey_size = request.form['jersey_size'] or None
        if 'shorts_size' in request.form:
            student.shorts_size = request.form['shorts_size'] or None
        if 'boots_size' in request.form:
            student.boots_size = request.form['boots_size'] or None
        if 'equipment_notes' in request.form:
            student.equipment_notes = request.form['equipment_notes'] or None
        
        # Обработать новое фото (если загружено)
        if 'photo' in request.files:
            photo = request.files['photo']
            if photo and photo.filename:
                # Удалить старое фото
                if student.photo_path and os.path.exists(student.photo_path):
                    os.remove(student.photo_path)
                
                # Сохранить новое фото
                # Сохранить новое фото через сервис (возвращает корректный относительный путь)
                photo_path = face_service.save_student_photo(photo, student.id)
                student.photo_path = photo_path
                access_face_verifier.invalidate_candidate_index()
                # The previous ArcFace vector belongs to the replaced photo.
                student.face_encoding = None
                
                # Создать новый face encoding через ArcFace
                try:
                    encoding = face_service.extract_embedding(photo_path)
                    if encoding is not None:
                        student.set_face_encoding(encoding)
                        reload_face_encodings()
                except Exception as e:
                    print(f"Ошибка обработки фото: {e}")
        
        # Убедиться, что у ученика есть код для Telegram
        ensure_student_has_telegram_code(student)
        
        queue_hikvision_person('student', student.id, 'student_updated')
        db.session.commit()
        return jsonify({'success': True})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/students/<int:student_id>', methods=['DELETE'])
@login_required
def delete_student(student_id):
    try:
        student = Student.query.get_or_404(student_id)
        student_name = student.full_name
        
        # Удалить все связанные записи перед удалением ученика
        # 1. Удалить карточки ученика
        StudentCard.query.filter_by(student_id=student_id).delete()
        
        # 2. Удалить вознаграждения ученика
        StudentReward.query.filter_by(student_id=student_id).delete()
        
        # 3. Удалить посещаемость ученика
        Attendance.query.filter_by(student_id=student_id).delete()
        
        # 4. Удалить платежи ученика
        Payment.query.filter_by(student_id=student_id).delete()
        
        # 5. Удалить фото ученика, если оно есть
        if student.photo_path and os.path.exists(student.photo_path):
            try:
                os.remove(student.photo_path)
            except Exception as photo_error:
                print(f"Ошибка при удалении фото: {photo_error}")
        
        # 6. Теперь можно безопасно удалить самого ученика
        db.session.delete(student)
        queue_hikvision_person('student', student_id, 'student_deleted', action='delete', employee_no=str(student_id))
        db.session.commit()
        
        # Перезагрузить encodings
        reload_face_encodings()
        
        return jsonify({'success': True, 'message': f'Ученик {student_name} удалён'})
    
    except Exception as e:
        db.session.rollback()
        print(f"Ошибка при удалении ученика {student_id}: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ===== ПЛАТЕЖИ =====

@app.route('/api/payments/add', methods=['POST'])
@login_required
def add_payment():
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        tariff_id = data.get('tariff_id')
        amount_paid = float(data.get('amount_paid'))
        amount_due = float(data.get('amount_due', 0))
        lessons_added = int(data.get('lessons_added', 0))
        is_full_payment = data.get('is_full_payment', True)
        notes = data.get('notes', '')
        
        student = Student.query.get_or_404(student_id)
        tariff = db.session.get(Tariff, tariff_id) if tariff_id else None
        
        # Создать платёж
        payment = Payment(
            student_id=student_id,
            tariff_id=tariff_id,
            amount_paid=amount_paid,
            amount_due=amount_due,
            lessons_added=lessons_added,
            is_full_payment=is_full_payment,
            tariff_name=tariff.name if tariff else None,
            notes=notes,
            created_by=current_user.id
        )
        db.session.add(payment)
        
        # Обновить тип тарифа при полной оплате
        if is_full_payment:
            student.tariff_type = tariff.name if tariff else None

        queue_hikvision_person('student', student.id, 'payment_added')
        db.session.commit()
        
        # Отправить уведомление в Telegram (для старого метода)
        try:
            from datetime import date
            payment_date = payment.payment_date or date.today()
            payment_month = payment.payment_month if hasattr(payment, 'payment_month') and payment.payment_month else payment_date.month
            payment_year = payment.payment_year if hasattr(payment, 'payment_year') and payment.payment_year else payment_date.year
            month_label = f"{payment_month}/{payment_year}"
            payment_type = getattr(payment, 'payment_type', 'cash') or 'cash'
            
            send_payment_notification(
                student_id=student_id,
                payment_date=payment_date,
                month=month_label,
                payment_type=payment_type,
                amount_paid=amount_paid,
                debt=amount_due if amount_due > 0 else None
            )
            
            # --- УВЕДОМЛЕНИЕ ДЛЯ РУКОВОДСТВА ---
            msg_mgmt = (
                f"💰 <b>Новая оплата!</b>\n"
                f"👤 Ученик: <b>{student.full_name}</b>\n"
                f"💵 Сумма: {format_currency(amount_paid)} сум\n"
                f"📦 Тариф: {tariff.name if tariff else 'Без тарифа'}\n"
                f"🗓 Дата: {payment_date.strftime('%d.%m.%Y')}\n"
            )
            if amount_due > 0:
                msg_mgmt += f"⚠️ Долг: {format_currency(amount_due)} сум\n"
             
            send_management_notification(msg_mgmt, roles=['director', 'founder', 'cashier'])
            
        except Exception as e:
            print(f"Ошибка отправки уведомления об оплате: {e}")
            # Не прерываем выполнение, если уведомление не отправилось
        
        return jsonify({
            'success': True, 
            'new_balance': calculate_student_balance(student),
            'is_full_payment': is_full_payment,
            'amount_due': amount_due
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# ===== ПОСЕЩАЕМОСТЬ =====

@app.route('/attendance')
@login_required
def attendance_page():
    return render_template('attendance.html')


@app.route('/access-log')
@login_required
def access_log_page():
    if not current_user.has_permission('attendance', 'view'):
        return redirect(url_for('dashboard'))
    return render_template('access_log.html')


@app.route('/staff-timesheet')
@login_required
def staff_timesheet_page():
    if not current_user.has_permission('attendance', 'view'):
        return redirect(url_for('dashboard'))
    return render_template('staff_timesheet.html')


def has_tournament_permission(permission='view'):
    return (
        current_user.has_permission('tournaments', permission)
        or current_user.has_permission('attendance', permission)
        or current_user.role == 'admin'
    )


def parse_date_value(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).date()
    except Exception:
        try:
            return datetime.strptime(str(value), '%Y-%m-%d').date()
        except Exception:
            try:
                return datetime.strptime(str(value).strip(), '%d.%m.%Y').date()
            except Exception:
                return None


def parse_time_value(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), '%H:%M').time()
    except Exception:
        return None


def parse_bool_field(value, default=False):
    """FormData присылает булевы значения строками, JSON — настоящим bool."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'on', 'yes', 'да'}


def normalize_age_groups(value):
    if isinstance(value, str):
        value = re.split(r'[,;\n]+', value)
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        label = str(item or '').strip()
        if label and label not in result:
            result.append(label)
    return result


def serialize_tournament(tournament):
    try:
        age_groups = json.loads(tournament.age_groups or '[]')
    except Exception:
        age_groups = normalize_age_groups(tournament.age_groups)
    payload = {
        'id': tournament.id,
        'name': tournament.name,
        'location': tournament.location,
        'start_date': tournament.start_date.isoformat() if tournament.start_date else None,
        'start_time': tournament.start_time.strftime('%H:%M') if tournament.start_time else None,
        'end_date': tournament.end_date.isoformat() if tournament.end_date else None,
        'age_groups': age_groups,
        'poster_url': get_tournament_media_url(tournament.poster_path),
        'is_published': bool(tournament.is_published),
        'created_at': tournament.created_at.isoformat() if tournament.created_at else None,
    }
    return payload


def serialize_tournament_team_catalog(team):
    return {
        'id': team.id,
        'name': team.name,
        'logo_url': get_tournament_team_logo_url(team),
        'trainer_name': team.trainer_name,
        'trainer_photo_url': get_tournament_media_url(team.trainer_photo_path),
        'administration_phone': team.administration_phone,
        'trainer_phone': team.trainer_phone,
        'club_address': team.club_address,
        'member_count': len(team.members),
        'created_at': team.created_at.isoformat() if team.created_at else None,
    }


PLAYER_POSITIONS = ('Вратарь', 'Защитник', 'Полузащитник', 'Нападающий')


def normalize_player_position(value):
    label = (value or '').strip()
    return label if label in PLAYER_POSITIONS else None


def serialize_tournament_team_member(member):
    return {
        'id': member.id,
        'team_id': member.team_id,
        'photo_url': get_tournament_media_url(member.photo_path),
        'last_name': member.last_name,
        'first_name': member.first_name,
        'middle_name': member.middle_name,
        'full_name': member.full_name,
        'birth_date': member.birth_date.isoformat() if member.birth_date else None,
        'passport_series': member.passport_series,
        'address': member.address,
        'phone_primary': member.phone_primary,
        'phone_secondary': member.phone_secondary,
        'team_number': member.team_number,
        'position': member.position,
        'created_at': member.created_at.isoformat() if member.created_at else None,
    }


def serialize_tournament_stadium(stadium):
    return {
        'id': stadium.id,
        'name': stadium.name,
        'photo_source': stadium.photo_source,
        'owner_phone': stadium.owner_phone,
        'length': stadium.length,
        'width': stadium.width,
        'photo_url': get_tournament_media_url(stadium.photo_path),
        'latitude': stadium.latitude,
        'longitude': stadium.longitude,
        'created_at': stadium.created_at.isoformat() if stadium.created_at else None,
    }


def parse_optional_stadium_size(value, label):
    raw = str(value or '').strip().replace(',', '.')
    if not raw:
        return None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f'{label} должна быть числом')
    if number <= 0:
        raise ValueError(f'{label} должна быть больше нуля')
    return number


def apply_tournament_team_form(team):
    team.name = (request.form.get('name') or '').strip()
    team.trainer_name = (request.form.get('trainer_name') or '').strip() or None
    team.administration_phone = (request.form.get('administration_phone') or '').strip() or None
    team.trainer_phone = (request.form.get('trainer_phone') or '').strip() or None
    team.club_address = (request.form.get('club_address') or '').strip() or None


def apply_tournament_member_form(member):
    member.last_name = (request.form.get('last_name') or '').strip()
    member.first_name = (request.form.get('first_name') or '').strip()
    member.middle_name = (request.form.get('middle_name') or '').strip() or None
    member.birth_date = parse_date_value(request.form.get('birth_date'))
    member.passport_series = (request.form.get('passport_series') or '').strip() or None
    member.address = (request.form.get('address') or '').strip() or None
    member.phone_primary = (request.form.get('phone_primary') or '').strip() or None
    member.phone_secondary = (request.form.get('phone_secondary') or '').strip() or None
    member.team_number = (request.form.get('team_number') or '').strip() or None
    member.position = normalize_player_position(request.form.get('position'))


@app.route('/tournaments')
@login_required
def tournaments_page():
    if not has_tournament_permission('view'):
        return redirect(url_for('dashboard'))
    return render_template('tournaments.html')


@app.route('/api/tournaments', methods=['GET', 'POST'])
@login_required
def tournaments_api():
    ensure_tournament_tables()
    if request.method == 'GET':
        if not has_tournament_permission('view'):
            return jsonify({'success': False, 'message': 'Нет доступа'}), 403
        tournaments = Tournament.query.filter(
            Tournament.start_time.isnot(None),
            Tournament.age_groups.isnot(None),
        ).order_by(
            Tournament.start_date.desc().nullslast(),
            Tournament.created_at.desc()
        ).all()
        return jsonify({'success': True, 'tournaments': [serialize_tournament(item) for item in tournaments]})

    if not has_tournament_permission('edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403
    # Форма отправляет FormData из-за файла афиши; JSON оставлен для совместимости.
    data = request.form if request.form else (request.get_json() or {})
    name = (data.get('name') or '').strip()
    location = (data.get('location') or '').strip()
    start_date = parse_date_value(data.get('start_date'))
    start_time = parse_time_value(data.get('start_time'))
    end_date = parse_date_value(data.get('end_date'))
    age_groups = normalize_age_groups(data.get('age_groups'))
    is_published = parse_bool_field(data.get('is_published'), default=True)
    if not all([name, location, start_date, start_time, end_date]) or not age_groups:
        return jsonify({'success': False, 'message': 'Заполните все поля турнира'}), 400
    if end_date < start_date:
        return jsonify({'success': False, 'message': 'Дата окончания не может быть раньше даты проведения'}), 400
    tournament = Tournament(
        name=name,
        location=location,
        start_date=start_date,
        start_time=start_time,
        end_date=end_date,
        age_groups=json.dumps(age_groups, ensure_ascii=False),
        is_published=is_published,
        created_by=current_user.id,
    )
    poster_file = request.files.get('poster')
    if poster_file and poster_file.filename:
        try:
            tournament.poster_path = save_tournament_catalog_photo(poster_file, 'tournament_poster')
        except ValueError as exc:
            return jsonify({'success': False, 'message': str(exc)}), 400
    db.session.add(tournament)
    db.session.commit()
    return jsonify({'success': True, 'tournament': serialize_tournament(tournament)}), 201


@app.route('/api/tournaments/<int:tournament_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def tournament_detail_api(tournament_id):
    ensure_tournament_tables()
    tournament = Tournament.query.filter_by(id=tournament_id).first_or_404()

    if request.method == 'GET':
        if not has_tournament_permission('view'):
            return jsonify({'success': False, 'message': 'Нет доступа'}), 403
        return jsonify({'success': True, 'tournament': serialize_tournament(tournament)})

    if not has_tournament_permission('edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403

    if request.method == 'DELETE':
        poster_path = tournament.poster_path
        db.session.delete(tournament)
        db.session.commit()
        delete_tournament_catalog_media(poster_path, ('tournament_poster_',))
        return jsonify({'success': True})

    # Форма отправляет FormData из-за файла афиши; JSON оставлен для совместимости.
    data = request.form if request.form else (request.get_json() or {})
    name = (data.get('name') or '').strip()
    location = (data.get('location') or '').strip()
    start_date = parse_date_value(data.get('start_date'))
    start_time = parse_time_value(data.get('start_time'))
    end_date = parse_date_value(data.get('end_date'))
    age_groups = normalize_age_groups(data.get('age_groups'))
    is_published = parse_bool_field(data.get('is_published'), default=True)
    if not all([name, location, start_date, start_time, end_date]) or not age_groups:
        return jsonify({'success': False, 'message': 'Заполните все поля турнира'}), 400
    if end_date < start_date:
        return jsonify({'success': False, 'message': 'Дата окончания не может быть раньше даты проведения'}), 400
    tournament.name = name
    tournament.location = location
    tournament.start_date = start_date
    tournament.start_time = start_time
    tournament.end_date = end_date
    tournament.age_groups = json.dumps(age_groups, ensure_ascii=False)
    tournament.is_published = is_published

    poster_file = request.files.get('poster')
    if poster_file and poster_file.filename:
        try:
            tournament.poster_path = save_tournament_catalog_photo(
                poster_file, 'tournament_poster', tournament.poster_path,
            )
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(exc)}), 400
    elif parse_bool_field(data.get('remove_poster'), default=False):
        removed = tournament.poster_path
        tournament.poster_path = None
        delete_tournament_catalog_media(removed, ('tournament_poster_',))

    db.session.commit()
    return jsonify({'success': True, 'tournament': serialize_tournament(tournament)})


@app.route('/api/tournament-team-catalog', methods=['GET', 'POST'])
@login_required
def tournament_team_catalog_api():
    ensure_tournament_tables()
    if request.method == 'GET':
        if not has_tournament_permission('view'):
            return jsonify({'success': False, 'message': 'Нет доступа'}), 403
        teams = TournamentTeamCatalog.query.order_by(TournamentTeamCatalog.name.asc()).all()
        return jsonify({'success': True, 'teams': [serialize_tournament_team_catalog(team) for team in teams]})

    if not has_tournament_permission('edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403
    name = (request.form.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'Укажите название команды'}), 400
    if TournamentTeamCatalog.query.filter(func.lower(TournamentTeamCatalog.name) == name.lower()).first():
        return jsonify({'success': False, 'message': 'Команда с таким названием уже существует'}), 400
    logo_file = request.files.get('logo')
    if not logo_file or not logo_file.filename:
        return jsonify({'success': False, 'message': 'Добавьте логотип команды'}), 400
    team = TournamentTeamCatalog(name=name, created_by=current_user.id)
    apply_tournament_team_form(team)
    try:
        team.logo_path = save_tournament_team_logo(logo_file)
        if request.files.get('trainer_photo'):
            team.trainer_photo_path = save_tournament_catalog_photo(
                request.files.get('trainer_photo'),
                'tournament_trainer',
            )
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    db.session.add(team)
    db.session.commit()
    return jsonify({'success': True, 'team': serialize_tournament_team_catalog(team)}), 201


@app.route('/api/tournament-team-catalog/<int:team_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def tournament_team_catalog_detail_api(team_id):
    ensure_tournament_tables()
    team = db.session.get(TournamentTeamCatalog, team_id)
    if not team:
        return jsonify({'success': False, 'message': 'Команда не найдена'}), 404
    if request.method == 'GET':
        if not has_tournament_permission('view'):
            return jsonify({'success': False, 'message': 'Нет доступа'}), 403
        payload = serialize_tournament_team_catalog(team)
        payload['members'] = [
            serialize_tournament_team_member(member)
            for member in sorted(team.members, key=lambda item: (
                item.last_name.lower(),
                item.first_name.lower(),
                item.id,
            ))
        ]
        return jsonify({'success': True, 'team': payload})

    if not has_tournament_permission('edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403
    old_logo = team.logo_path
    if request.method == 'DELETE':
        trainer_photo = team.trainer_photo_path
        member_photos = [member.photo_path for member in team.members if member.photo_path]
        db.session.delete(team)
        db.session.commit()
        delete_tournament_team_logo(old_logo)
        delete_tournament_catalog_media(trainer_photo)
        for photo_path in member_photos:
            delete_tournament_catalog_media(photo_path)
        return jsonify({'success': True})

    name = (request.form.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'Укажите название команды'}), 400
    duplicate = TournamentTeamCatalog.query.filter(
        func.lower(TournamentTeamCatalog.name) == name.lower(),
        TournamentTeamCatalog.id != team.id,
    ).first()
    if duplicate:
        return jsonify({'success': False, 'message': 'Команда с таким названием уже существует'}), 400
    apply_tournament_team_form(team)
    if request.files.get('logo'):
        try:
            team.logo_path = save_tournament_team_logo(request.files.get('logo'), team.logo_path)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(exc)}), 400
    if request.files.get('trainer_photo'):
        try:
            team.trainer_photo_path = save_tournament_catalog_photo(
                request.files.get('trainer_photo'),
                'tournament_trainer',
                team.trainer_photo_path,
            )
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(exc)}), 400
    db.session.commit()
    return jsonify({'success': True, 'team': serialize_tournament_team_catalog(team)})


@app.route('/api/tournament-team-catalog/<int:team_id>/members', methods=['GET', 'POST'])
@login_required
def tournament_team_members_api(team_id):
    ensure_tournament_tables()
    team = db.session.get(TournamentTeamCatalog, team_id)
    if not team:
        return jsonify({'success': False, 'message': 'Команда не найдена'}), 404
    if request.method == 'GET':
        if not has_tournament_permission('view'):
            return jsonify({'success': False, 'message': 'Нет доступа'}), 403
        members = TournamentTeamMember.query.filter_by(team_id=team_id).order_by(
            TournamentTeamMember.last_name.asc(),
            TournamentTeamMember.first_name.asc(),
        ).all()
        return jsonify({
            'success': True,
            'members': [serialize_tournament_team_member(member) for member in members],
        })

    if not has_tournament_permission('edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403
    member = TournamentTeamMember(team_id=team_id, last_name='', first_name='')
    apply_tournament_member_form(member)
    if not member.last_name or not member.first_name:
        return jsonify({'success': False, 'message': 'Укажите фамилию и имя участника'}), 400
    birth_value = (request.form.get('birth_date') or '').strip()
    if birth_value and not member.birth_date:
        return jsonify({'success': False, 'message': 'Дата рождения должна быть в формате дд.мм.гггг'}), 400
    photo_file = request.files.get('photo')
    try:
        if photo_file and photo_file.filename:
            member.photo_path = save_tournament_catalog_photo(photo_file, 'tournament_member')
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    db.session.add(member)
    db.session.commit()
    return jsonify({'success': True, 'member': serialize_tournament_team_member(member)}), 201


@app.route('/api/tournament-team-members/<int:member_id>', methods=['PUT', 'DELETE'])
@login_required
def tournament_team_member_detail_api(member_id):
    ensure_tournament_tables()
    if not has_tournament_permission('edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403
    member = db.session.get(TournamentTeamMember, member_id)
    if not member:
        return jsonify({'success': False, 'message': 'Участник не найден'}), 404
    if request.method == 'DELETE':
        photo_path = member.photo_path
        db.session.delete(member)
        db.session.commit()
        delete_tournament_catalog_media(photo_path)
        return jsonify({'success': True})

    apply_tournament_member_form(member)
    if not member.last_name or not member.first_name:
        return jsonify({'success': False, 'message': 'Укажите фамилию и имя участника'}), 400
    birth_value = (request.form.get('birth_date') or '').strip()
    if birth_value and not member.birth_date:
        return jsonify({'success': False, 'message': 'Дата рождения должна быть в формате дд.мм.гггг'}), 400
    if request.files.get('photo'):
        try:
            member.photo_path = save_tournament_catalog_photo(
                request.files.get('photo'),
                'tournament_member',
                member.photo_path,
            )
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(exc)}), 400
    db.session.commit()
    return jsonify({'success': True, 'member': serialize_tournament_team_member(member)})


# ===== УЧАСТНИКИ ТУРНИРА (ЗАЯВКИ) =====

ENTRY_STATUSES = {
    TournamentEntry.STATUS_INVITED: 'Приглашена',
    TournamentEntry.STATUS_CONFIRMED: 'Подтвердила',
    TournamentEntry.STATUS_DECLINED: 'Отказалась',
}


def tournament_age_group_labels(tournament):
    """Категории турнира так, как их задал организатор: «2015» или «U-12»."""
    try:
        labels = json.loads(tournament.age_groups or '[]')
    except Exception:
        labels = normalize_age_groups(tournament.age_groups)
    return [str(label).strip() for label in (labels or []) if str(label).strip()]


def serialize_tournament_entry(entry):
    team = entry.team
    members = TournamentTeamMember.query.filter_by(team_id=entry.team_id).count() if team else 0
    return {
        'id': entry.id,
        'tournament_id': entry.tournament_id,
        'team_id': entry.team_id,
        'team_name': team.name if team else '—',
        'team_logo_url': get_tournament_media_url(team.logo_path) if team else None,
        'trainer_name': team.trainer_name if team else None,
        'trainer_phone': (team.trainer_phone or team.administration_phone) if team else None,
        'age_group': entry.age_group,
        'status': entry.status,
        'status_label': ENTRY_STATUSES.get(entry.status, entry.status),
        'group_id': entry.group_id,
        'note': entry.note,
        'member_count': members,
        'created_at': entry.created_at.isoformat() if entry.created_at else None,
    }


@app.route('/api/tournaments/<int:tournament_id>/entries', methods=['GET', 'POST'])
@login_required
def tournament_entries_api(tournament_id):
    ensure_tournament_tables()
    tournament = Tournament.query.filter_by(id=tournament_id).first_or_404()

    if request.method == 'GET':
        if not has_tournament_permission('view'):
            return jsonify({'success': False, 'message': 'Нет доступа'}), 403
        entries = TournamentEntry.query.filter_by(tournament_id=tournament_id).all()
        # Сортируем по категории, затем по названию команды — так удобнее читать список.
        entries.sort(key=lambda item: (item.age_group, (item.team.name if item.team else '')))
        return jsonify({
            'success': True,
            'age_groups': tournament_age_group_labels(tournament),
            'entries': [serialize_tournament_entry(entry) for entry in entries],
        })

    if not has_tournament_permission('edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403

    data = request.get_json() or {}
    age_group = (data.get('age_group') or '').strip()

    # Команд может прийти сразу несколько: заявлять по одной неудобно.
    raw_ids = data.get('team_ids')
    if not isinstance(raw_ids, list):
        raw_ids = [data.get('team_id')]
    team_ids = []
    for value in raw_ids:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number not in team_ids:
            team_ids.append(number)
    if not team_ids:
        return jsonify({'success': False, 'message': 'Выберите команду'}), 400

    allowed = tournament_age_group_labels(tournament)
    if not age_group:
        return jsonify({'success': False, 'message': 'Выберите возрастную категорию'}), 400
    if allowed and age_group not in allowed:
        return jsonify({'success': False, 'message': 'Выберите возрастную категорию турнира'}), 400

    status = data.get('status') if data.get('status') in ENTRY_STATUSES else TournamentEntry.STATUS_INVITED
    note = (data.get('note') or '').strip() or None
    already = {
        entry.team_id for entry in TournamentEntry.query.filter_by(
            tournament_id=tournament_id, age_group=age_group,
        ).all()
    }

    added, skipped, missing = [], [], 0
    for team_id in team_ids:
        team = db.session.get(TournamentTeamCatalog, team_id)
        if not team:
            missing += 1
            continue
        if team.id in already:
            skipped.append(team.name)
            continue
        db.session.add(TournamentEntry(
            tournament_id=tournament_id,
            team_id=team.id,
            age_group=age_group,
            status=status,
            note=note,
            created_by=current_user.id,
        ))
        already.add(team.id)
        added.append(team.name)

    if not added:
        if skipped:
            names = ', '.join(f'«{name}»' for name in skipped)
            return jsonify({
                'success': False,
                'message': f'{names} уже заявлены в категории {age_group}',
            }), 400
        return jsonify({'success': False, 'message': 'Команда не найдена'}), 400

    db.session.commit()
    return jsonify({'success': True, 'added': added, 'skipped': skipped, 'missing': missing}), 201


@app.route('/api/tournament-entries/<int:entry_id>', methods=['PUT', 'DELETE'])
@login_required
def tournament_entry_detail_api(entry_id):
    ensure_tournament_tables()
    if not has_tournament_permission('edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403
    entry = db.session.get(TournamentEntry, entry_id)
    if not entry:
        return jsonify({'success': False, 'message': 'Заявка не найдена'}), 404

    if request.method == 'DELETE':
        db.session.delete(entry)
        db.session.commit()
        return jsonify({'success': True})

    data = request.get_json() or {}

    if 'group_id' in data:
        group_id = data.get('group_id')
        if group_id in (None, '', 0):
            entry.group_id = None
        else:
            group = db.session.get(TournamentGroup, int(group_id))
            # Группа должна быть из этого турнира и этой же категории.
            if (not group or group.tournament_id != entry.tournament_id
                    or group.age_group != entry.age_group):
                return jsonify({'success': False, 'message': 'Группа не подходит этой заявке'}), 400
            entry.group_id = group.id
        if 'status' not in data:
            db.session.commit()
            return jsonify({'success': True, 'entry': serialize_tournament_entry(entry)})

    status = data.get('status')
    if status not in ENTRY_STATUSES:
        return jsonify({'success': False, 'message': 'Неизвестный статус заявки'}), 400
    entry.status = status
    # Отказавшаяся команда не может оставаться в группе.
    if status != TournamentEntry.STATUS_CONFIRMED:
        entry.group_id = None
    if 'note' in data:
        entry.note = (data.get('note') or '').strip() or None
    db.session.commit()
    return jsonify({'success': True, 'entry': serialize_tournament_entry(entry)})


# ===== ГРУППЫ ТУРНИРА =====

GROUP_NAMES = 'ABCDEFGHIJKLMNOP'


def serialize_tournament_group(group):
    return {
        'id': group.id,
        'name': group.name,
        'age_group': group.age_group,
        'sort_order': group.sort_order,
    }


def ensure_tournament_groups(tournament_id, age_group, count):
    """Доводит число групп категории до нужного: лишние пустые убираем."""
    count = max(0, min(int(count), len(GROUP_NAMES)))
    groups = TournamentGroup.query.filter_by(
        tournament_id=tournament_id, age_group=age_group,
    ).order_by(TournamentGroup.sort_order.asc()).all()

    for index in range(len(groups), count):
        groups.append(TournamentGroup(
            tournament_id=tournament_id,
            age_group=age_group,
            name=GROUP_NAMES[index],
            sort_order=index,
        ))
        db.session.add(groups[-1])

    for extra in groups[count:]:
        # Команды из удаляемой группы возвращаются в «без группы», а не пропадают.
        TournamentEntry.query.filter_by(group_id=extra.id).update({'group_id': None})
        db.session.delete(extra)

    db.session.flush()
    return groups[:count]


@app.route('/api/tournaments/<int:tournament_id>/groups', methods=['GET', 'POST'])
@login_required
def tournament_groups_api(tournament_id):
    ensure_tournament_tables()
    tournament = Tournament.query.filter_by(id=tournament_id).first_or_404()

    if request.method == 'GET':
        if not has_tournament_permission('view'):
            return jsonify({'success': False, 'message': 'Нет доступа'}), 403
        groups = TournamentGroup.query.filter_by(tournament_id=tournament_id).order_by(
            TournamentGroup.age_group.asc(), TournamentGroup.sort_order.asc(),
        ).all()
        entries = TournamentEntry.query.filter_by(
            tournament_id=tournament_id, status=TournamentEntry.STATUS_CONFIRMED,
        ).all()
        entries.sort(key=lambda item: (item.team.name if item.team else ''))
        return jsonify({
            'success': True,
            'age_groups': tournament_age_group_labels(tournament),
            'groups': [serialize_tournament_group(group) for group in groups],
            'entries': [serialize_tournament_entry(entry) for entry in entries],
        })

    if not has_tournament_permission('edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403

    data = request.get_json() or {}
    age_group = (data.get('age_group') or '').strip()
    allowed = tournament_age_group_labels(tournament)
    if allowed and age_group not in allowed:
        return jsonify({'success': False, 'message': 'Выберите возрастную категорию турнира'}), 400
    try:
        count = int(data.get('count'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Укажите количество групп'}), 400
    if count < 1 or count > len(GROUP_NAMES):
        return jsonify({'success': False, 'message': f'Групп может быть от 1 до {len(GROUP_NAMES)}'}), 400

    groups = ensure_tournament_groups(tournament_id, age_group, count)

    if data.get('draw'):
        entries = TournamentEntry.query.filter_by(
            tournament_id=tournament_id,
            age_group=age_group,
            status=TournamentEntry.STATUS_CONFIRMED,
        ).all()
        if not entries:
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': 'В этой категории нет подтверждённых команд',
            }), 400
        # Змейкой по группам, порядок случайный — так составы получаются ровными.
        random.shuffle(entries)
        for index, entry in enumerate(entries):
            entry.group_id = groups[index % len(groups)].id

    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/tournament-groups/<int:group_id>', methods=['DELETE'])
@login_required
def tournament_group_detail_api(group_id):
    ensure_tournament_tables()
    if not has_tournament_permission('edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403
    group = db.session.get(TournamentGroup, group_id)
    if not group:
        return jsonify({'success': False, 'message': 'Группа не найдена'}), 404
    TournamentEntry.query.filter_by(group_id=group.id).update({'group_id': None})
    db.session.delete(group)
    db.session.commit()
    return jsonify({'success': True})


# ===== МАТЧИ И ТАБЛИЦА =====

WIN_POINTS = 3
DRAW_POINTS = 1


def round_robin_rounds(items):
    """Круговая система в один круг: каждый играет с каждым по разу.

    Классический круговой метод: один участник фиксирован, остальные сдвигаются.
    При нечётном числе добавляем «пустого» — его соперник в этом туре отдыхает.
    """
    players = list(items)
    if len(players) < 2:
        return []
    if len(players) % 2:
        players.append(None)

    half = len(players) // 2
    rounds = []
    for _ in range(len(players) - 1):
        pairs = []
        for index in range(half):
            home, away = players[index], players[-1 - index]
            if home is not None and away is not None:
                # Чередуем хозяев, чтобы поля распределялись ровнее.
                pairs.append((home, away) if len(rounds) % 2 == 0 else (away, home))
        rounds.append(pairs)
        players = [players[0]] + [players[-1]] + players[1:-1]
    return rounds


def serialize_match(match):
    def side(entry, placeholder=None):
        if not entry:
            return {'entry_id': None, 'team_name': placeholder or '—', 'team_logo_url': None}
        team = entry.team
        return {
            'entry_id': entry.id,
            'team_name': team.name if team else '—',
            'team_logo_url': get_tournament_media_url(team.logo_path) if team else None,
        }

    return {
        'id': match.id,
        'age_group': match.age_group,
        'group_id': match.group_id,
        'group_name': match.group.name if match.group else None,
        'round_no': match.round_no,
        'home': side(match.home_entry, match.home_label),
        'away': side(match.away_entry, match.away_label),
        'home_score': match.home_score,
        'away_score': match.away_score,
        'is_played': match.is_played,
        'stage': match.stage,
        'label': match.label,
        'bracket_slot': match.bracket_slot,
        'home_penalty': match.home_penalty,
        'away_penalty': match.away_penalty,
        'winner_entry_id': match.winner_entry_id,
        'stadium_id': match.stadium_id,
        'stadium_name': match.stadium.name if match.stadium else None,
        'kickoff_at': match.kickoff_at.isoformat(timespec='minutes') if match.kickoff_at else None,
    }


def build_standings(entries, matches):
    """Таблица считается из матчей и нигде не хранится — иначе разъедется."""
    rows = {}
    for entry in entries:
        rows[entry.id] = {
            'entry_id': entry.id,
            'team_name': entry.team.name if entry.team else '—',
            'team_logo_url': get_tournament_media_url(entry.team.logo_path) if entry.team else None,
            'played': 0, 'won': 0, 'drawn': 0, 'lost': 0,
            'goals_for': 0, 'goals_against': 0, 'diff': 0, 'points': 0,
        }

    played = [m for m in matches if m.is_played
              and m.home_entry_id in rows and m.away_entry_id in rows]
    for match in played:
        home, away = rows[match.home_entry_id], rows[match.away_entry_id]
        home['played'] += 1
        away['played'] += 1
        home['goals_for'] += match.home_score
        home['goals_against'] += match.away_score
        away['goals_for'] += match.away_score
        away['goals_against'] += match.home_score
        if match.home_score > match.away_score:
            home['won'] += 1
            away['lost'] += 1
            home['points'] += WIN_POINTS
        elif match.home_score < match.away_score:
            away['won'] += 1
            home['lost'] += 1
            away['points'] += WIN_POINTS
        else:
            home['drawn'] += 1
            away['drawn'] += 1
            home['points'] += DRAW_POINTS
            away['points'] += DRAW_POINTS

    for row in rows.values():
        row['diff'] = row['goals_for'] - row['goals_against']

    table = sorted(
        rows.values(),
        key=lambda row: (-row['points'], -row['diff'], -row['goals_for'], row['team_name']),
    )

    # Личная встреча решает только чистую пару: при тройном равенстве она
    # зацикливается, и общепринятого простого правила там нет.
    for index in range(len(table) - 1):
        first, second = table[index], table[index + 1]
        same = (first['points'], first['diff'], first['goals_for']) == \
               (second['points'], second['diff'], second['goals_for'])
        if not same:
            continue
        neighbours = [row for row in table
                      if (row['points'], row['diff'], row['goals_for'])
                      == (first['points'], first['diff'], first['goals_for'])]
        if len(neighbours) != 2:
            continue
        for match in played:
            pair = {match.home_entry_id, match.away_entry_id}
            if pair != {first['entry_id'], second['entry_id']}:
                continue
            winner = None
            if match.home_score > match.away_score:
                winner = match.home_entry_id
            elif match.away_score > match.home_score:
                winner = match.away_entry_id
            if winner == second['entry_id']:
                table[index], table[index + 1] = second, first

    for place, row in enumerate(table, start=1):
        row['place'] = place
    return table


@app.route('/api/tournaments/<int:tournament_id>/matches', methods=['GET', 'POST'])
@login_required
def tournament_matches_api(tournament_id):
    ensure_tournament_tables()
    tournament = Tournament.query.filter_by(id=tournament_id).first_or_404()

    if request.method == 'GET':
        if not has_tournament_permission('view'):
            return jsonify({'success': False, 'message': 'Нет доступа'}), 403
        age_group = (request.args.get('age_group') or '').strip()
        groups = TournamentGroup.query.filter_by(
            tournament_id=tournament_id, age_group=age_group,
        ).order_by(TournamentGroup.sort_order.asc()).all()
        matches = TournamentMatch.query.filter_by(
            tournament_id=tournament_id, age_group=age_group,
            stage=TournamentMatch.STAGE_GROUP,
        ).order_by(TournamentMatch.round_no.asc(), TournamentMatch.id.asc()).all()
        playoff = TournamentMatch.query.filter_by(
            tournament_id=tournament_id, age_group=age_group,
            stage=TournamentMatch.STAGE_PLAYOFF,
        ).order_by(TournamentMatch.round_no.asc(), TournamentMatch.bracket_slot.asc()).all()
        entries = TournamentEntry.query.filter_by(
            tournament_id=tournament_id, age_group=age_group,
            status=TournamentEntry.STATUS_CONFIRMED,
        ).all()

        blocks = []
        for group in groups:
            group_entries = [e for e in entries if e.group_id == group.id]
            group_matches = [m for m in matches if m.group_id == group.id]
            blocks.append({
                'group': serialize_tournament_group(group),
                'standings': build_standings(group_entries, group_matches),
                'matches': [serialize_match(m) for m in group_matches],
            })
        return jsonify({
            'success': True,
            'blocks': blocks,
            'playoff': [serialize_match(m) for m in playoff],
            'results': playoff_results(playoff),
            'stadiums': [{'id': s.id, 'name': s.name}
                         for s in TournamentStadium.query.order_by(TournamentStadium.name.asc()).all()],
        })

    if not has_tournament_permission('edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403

    data = request.get_json() or {}
    age_group = (data.get('age_group') or '').strip()
    groups = TournamentGroup.query.filter_by(
        tournament_id=tournament_id, age_group=age_group,
    ).order_by(TournamentGroup.sort_order.asc()).all()
    if not groups:
        return jsonify({'success': False, 'message': 'Сначала создайте группы этой категории'}), 400

    entries = TournamentEntry.query.filter_by(
        tournament_id=tournament_id, age_group=age_group,
        status=TournamentEntry.STATUS_CONFIRMED,
    ).all()

    created = 0
    for group in groups:
        group_entries = [e for e in entries if e.group_id == group.id]
        # Пересоздаём календарь группы целиком: частичная досборка запутала бы туры.
        TournamentMatch.query.filter_by(
            tournament_id=tournament_id, group_id=group.id,
        ).delete(synchronize_session=False)
        for round_index, pairs in enumerate(round_robin_rounds(group_entries), start=1):
            for home, away in pairs:
                db.session.add(TournamentMatch(
                    tournament_id=tournament_id,
                    age_group=age_group,
                    group_id=group.id,
                    round_no=round_index,
                    home_entry_id=home.id,
                    away_entry_id=away.id,
                ))
                created += 1

    if not created:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'В группах меньше двух команд — играть некому',
        }), 400

    db.session.commit()
    return jsonify({'success': True, 'created': created})


def match_teams(match):
    return {match.home_entry_id, match.away_entry_id} - {None}


# ===== ПЛЕЙ-ОФФ =====

ROUND_NAMES = {1: 'Финал', 2: 'Полуфинал', 4: 'Четвертьфинал', 8: '1/8 финала', 16: '1/16 финала'}


def playoff_round_name(matches_in_round):
    return ROUND_NAMES.get(matches_in_round, f'Раунд на {matches_in_round} матчей')


def propagate_playoff(match):
    """Переносит победителя (и проигравшего) в следующий матч сетки."""
    if match.stage != TournamentMatch.STAGE_PLAYOFF:
        return
    for target_id, slot, entry_id in (
        (match.next_match_id, match.next_slot, match.winner_entry_id),
        (match.loser_next_match_id, match.loser_next_slot, match.loser_entry_id),
    ):
        if not target_id or not slot:
            continue
        target = db.session.get(TournamentMatch, target_id)
        if not target:
            continue
        if slot == 'home':
            target.home_entry_id = entry_id
        else:
            target.away_entry_id = entry_id


def qualified_slot_labels(groups, advance):
    """Плейсхолдеры вида «1 место группы A» до того, как группы доиграны."""
    labels = []
    for place in range(1, advance + 1):
        for group in groups:
            labels.append((group.id, place, f'{place} место группы {group.name}'))
    return labels


def resolve_qualified(tournament_id, age_group, groups, advance):
    """Возвращает пары (entry_id | None, подпись) в порядке посева."""
    entries = TournamentEntry.query.filter_by(
        tournament_id=tournament_id, age_group=age_group,
        status=TournamentEntry.STATUS_CONFIRMED,
    ).all()
    matches = TournamentMatch.query.filter_by(
        tournament_id=tournament_id, age_group=age_group,
        stage=TournamentMatch.STAGE_GROUP,
    ).all()

    tables = {}
    for group in groups:
        group_entries = [e for e in entries if e.group_id == group.id]
        group_matches = [m for m in matches if m.group_id == group.id]
        tables[group.id] = build_standings(group_entries, group_matches)

    seeds = []
    for group_id, place, label in qualified_slot_labels(groups, advance):
        table = tables.get(group_id) or []
        # Место засчитываем только когда все матчи группы сыграны — иначе
        # в сетку попадёт лидер по ходу турнира, а не по итогу.
        finished = all(m.is_played for m in matches if m.group_id == group_id) and table
        entry_id = table[place - 1]['entry_id'] if finished and len(table) >= place else None
        seeds.append((entry_id, label))
    return seeds


def playoff_results(matches):
    """Итоговые места. Финал разводит первое и второе, матч за 3 место — третье и четвёртое."""
    final = next((m for m in matches if m.label == 'Финал'), None)
    bronze = next((m for m in matches if m.label == 'За 3 место'), None)

    places = []

    def add(place, entry_id):
        if not entry_id:
            return
        entry = db.session.get(TournamentEntry, entry_id)
        team = entry.team if entry else None
        places.append({
            'place': place,
            'team_name': team.name if team else '—',
            'team_logo_url': get_tournament_media_url(team.logo_path) if team else None,
        })

    if final and final.winner_entry_id:
        add(1, final.winner_entry_id)
        add(2, final.loser_entry_id)
    if bronze and bronze.winner_entry_id:
        add(3, bronze.winner_entry_id)
        add(4, bronze.loser_entry_id)
    return places


@app.route('/api/tournaments/<int:tournament_id>/playoff', methods=['POST'])
@login_required
def tournament_playoff_api(tournament_id):
    ensure_tournament_tables()
    if not has_tournament_permission('edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403
    tournament = Tournament.query.filter_by(id=tournament_id).first_or_404()

    data = request.get_json() or {}
    age_group = (data.get('age_group') or '').strip()
    try:
        advance = int(data.get('advance') or 2)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Проверьте количество выходящих команд'}), 400
    if advance < 1 or advance > 4:
        return jsonify({'success': False, 'message': 'Из группы могут выходить от 1 до 4 команд'}), 400
    third_place = bool(data.get('third_place', True))

    groups = TournamentGroup.query.filter_by(
        tournament_id=tournament_id, age_group=age_group,
    ).order_by(TournamentGroup.sort_order.asc()).all()
    if not groups:
        return jsonify({'success': False, 'message': 'Сначала создайте группы этой категории'}), 400

    seeds = resolve_qualified(tournament_id, age_group, groups, advance)
    if len(seeds) < 2:
        return jsonify({'success': False, 'message': 'Для сетки нужно минимум две команды'}), 400

    size = 1
    while size < len(seeds):
        size *= 2
    # Свободные места в сетке: их соперник проходит дальше автоматически.
    seeds += [(None, None)] * (size - len(seeds))

    TournamentMatch.query.filter_by(
        tournament_id=tournament_id, age_group=age_group,
        stage=TournamentMatch.STAGE_PLAYOFF,
    ).delete(synchronize_session=False)
    db.session.flush()

    rounds = []
    round_no = 1
    pairs = [(seeds[i], seeds[size - 1 - i]) for i in range(size // 2)]
    current = []
    for slot, (home, away) in enumerate(pairs, start=1):
        match = TournamentMatch(
            tournament_id=tournament_id,
            age_group=age_group,
            stage=TournamentMatch.STAGE_PLAYOFF,
            round_no=round_no,
            bracket_slot=slot,
            label=playoff_round_name(len(pairs)),
            home_entry_id=home[0],
            away_entry_id=away[0],
            home_label=home[1],
            away_label=away[1],
        )
        db.session.add(match)
        current.append(match)
    db.session.flush()
    rounds.append(current)

    while len(current) > 1:
        round_no += 1
        nxt = []
        for slot, index in enumerate(range(0, len(current), 2), start=1):
            match = TournamentMatch(
                tournament_id=tournament_id,
                age_group=age_group,
                stage=TournamentMatch.STAGE_PLAYOFF,
                round_no=round_no,
                bracket_slot=slot,
                label=playoff_round_name(len(current) // 2),
            )
            db.session.add(match)
            nxt.append(match)
        db.session.flush()
        for index, parent in enumerate(current):
            target = nxt[index // 2]
            parent.next_match_id = target.id
            parent.next_slot = 'home' if index % 2 == 0 else 'away'
        current = nxt
        rounds.append(current)

    if third_place and len(rounds) >= 2:
        semis = rounds[-2]
        if len(semis) == 2:
            bronze = TournamentMatch(
                tournament_id=tournament_id,
                age_group=age_group,
                stage=TournamentMatch.STAGE_PLAYOFF,
                round_no=round_no,
                bracket_slot=2,
                label='За 3 место',
                home_label='Проигравший полуфинала 1',
                away_label='Проигравший полуфинала 2',
            )
            db.session.add(bronze)
            db.session.flush()
            for index, semi in enumerate(semis):
                semi.loser_next_match_id = bronze.id
                semi.loser_next_slot = 'home' if index == 0 else 'away'

    numbers = {}
    position = 0
    for round_matches in rounds:
        for match in round_matches:
            position += 1
            numbers[match.id] = position
    for round_matches in rounds:
        for match in round_matches:
            if not match.next_match_id:
                continue
            target = db.session.get(TournamentMatch, match.next_match_id)
            if not target:
                continue
            text = f'Победитель матча {numbers[match.id]}'
            if match.next_slot == 'home':
                target.home_label = text
            else:
                target.away_label = text

    # Свободные места: соперник проходит сразу, иначе сетка встанет.
    for match in rounds[0]:
        if match.home_entry_id and match.away_label is None and match.away_entry_id is None:
            propagate_playoff(match)
        elif match.away_entry_id and match.home_label is None and match.home_entry_id is None:
            propagate_playoff(match)

    db.session.commit()
    return jsonify({'success': True, 'rounds': len(rounds)})


@app.route('/api/tournaments/<int:tournament_id>/matches/schedule', methods=['POST'])
@login_required
def tournament_schedule_api(tournament_id):
    """Расставляет матчи по дням и слотам времени."""
    ensure_tournament_tables()
    if not has_tournament_permission('edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403
    tournament = Tournament.query.filter_by(id=tournament_id).first_or_404()

    data = request.get_json() or {}
    try:
        duration = int(data.get('duration') or 30)
        gap = int(data.get('gap') or 10)
        pitches = int(data.get('pitches') or 1)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Проверьте числовые параметры'}), 400
    if duration < 5 or duration > 240:
        return jsonify({'success': False, 'message': 'Длительность матча — от 5 до 240 минут'}), 400
    if gap < 0 or gap > 240:
        return jsonify({'success': False, 'message': 'Перерыв — от 0 до 240 минут'}), 400
    if pitches < 1 or pitches > 10:
        return jsonify({'success': False, 'message': 'Полей может быть от 1 до 10'}), 400

    start_date = parse_date_value(data.get('start_date')) or tournament.start_date
    start_time = parse_time_value(data.get('start_time')) or tournament.start_time or dt_time(10, 0)
    end_time = parse_time_value(data.get('end_time')) or dt_time(18, 0)
    if not start_date:
        return jsonify({'success': False, 'message': 'Укажите дату начала'}), 400
    if end_time <= start_time:
        return jsonify({'success': False, 'message': 'Конец дня должен быть позже начала'}), 400

    overwrite = bool(data.get('overwrite'))
    age_group = (data.get('age_group') or '').strip()
    only_current = bool(data.get('only_current')) and age_group

    stadium_id = data.get('stadium_id')
    stadium_id = int(stadium_id) if stadium_id else None

    query = TournamentMatch.query.filter_by(tournament_id=tournament_id)
    if only_current:
        query = query.filter_by(age_group=age_group)
    all_matches = query.all()

    # Порядок расстановки — по турам: внутри тура команда играет не больше
    # одного раза, поэтому такие матчи можно ставить параллельно без коллизий.
    def order_key(match):
        return (match.round_no, match.age_group, match.group.sort_order if match.group else 0, match.id)

    pending = sorted([m for m in all_matches if overwrite or not m.kickoff_at], key=order_key)
    if not pending:
        return jsonify({'success': False, 'message': 'Все матчи уже расставлены по времени'}), 400

    # Слоты, занятые матчами, которые мы не трогаем, — их нельзя занимать повторно.
    busy = {}
    if not overwrite:
        fixed = TournamentMatch.query.filter(
            TournamentMatch.tournament_id == tournament_id,
            TournamentMatch.kickoff_at.isnot(None),
        ).all()
        for match in fixed:
            busy.setdefault(match.kickoff_at, []).append(match)

    slot = datetime.combine(start_date, start_time)
    day_end = datetime.combine(start_date, end_time)
    scheduled = 0
    days = set()

    for match in pending:
        placed = False
        while not placed:
            if slot + timedelta(minutes=duration) > day_end:
                next_day = (slot.date() + timedelta(days=1))
                slot = datetime.combine(next_day, start_time)
                day_end = datetime.combine(next_day, end_time)
                continue

            taken = busy.get(slot, [])
            busy_teams = set()
            for other in taken:
                busy_teams |= match_teams(other)
            # Одна команда не может играть два матча в одно время — даже если
            # свободное поле есть (например, клуб заявлен в двух категориях).
            if len(taken) >= pitches or (match_teams(match) & busy_teams):
                slot += timedelta(minutes=duration + gap)
                continue

            match.kickoff_at = slot
            if stadium_id:
                match.stadium_id = stadium_id
            busy.setdefault(slot, []).append(match)
            days.add(slot.date())
            scheduled += 1
            placed = True

    db.session.commit()
    return jsonify({
        'success': True,
        'scheduled': scheduled,
        'days': len(days),
        'first': min(days).isoformat() if days else None,
        'last': max(days).isoformat() if days else None,
    })


@app.route('/api/tournament-matches/<int:match_id>', methods=['PUT'])
@login_required
def tournament_match_detail_api(match_id):
    ensure_tournament_tables()
    if not has_tournament_permission('edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403
    match = db.session.get(TournamentMatch, match_id)
    if not match:
        return jsonify({'success': False, 'message': 'Матч не найден'}), 404

    data = request.get_json() or {}

    if 'home_score' in data or 'away_score' in data:
        def parse_score(value):
            if value in (None, ''):
                return None
            number = int(value)
            if number < 0 or number > 99:
                raise ValueError
            return number
        try:
            home = parse_score(data.get('home_score'))
            away = parse_score(data.get('away_score'))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Счёт должен быть числом от 0 до 99'}), 400
        # Счёт либо есть целиком, либо матч считается несыгранным.
        if (home is None) != (away is None):
            return jsonify({'success': False, 'message': 'Укажите счёт обеих команд'}), 400
        match.home_score = home
        match.away_score = away
        if home is None:
            match.home_penalty = None
            match.away_penalty = None

    if 'stadium_id' in data:
        stadium_id = data.get('stadium_id')
        match.stadium_id = int(stadium_id) if stadium_id else None

    if 'home_penalty' in data or 'away_penalty' in data:
        def parse_penalty(value):
            if value in (None, ''):
                return None
            number = int(value)
            if number < 0 or number > 99:
                raise ValueError
            return number
        try:
            match.home_penalty = parse_penalty(data.get('home_penalty'))
            match.away_penalty = parse_penalty(data.get('away_penalty'))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Пенальти — число от 0 до 99'}), 400

    if 'kickoff_at' in data:
        value = (data.get('kickoff_at') or '').strip()
        if not value:
            match.kickoff_at = None
        else:
            try:
                match.kickoff_at = datetime.fromisoformat(value)
            except ValueError:
                return jsonify({'success': False, 'message': 'Некорректные дата и время'}), 400

    # Серия пенальти бывает только при ничьей: при любом другом счёте
    # оставшиеся в форме числа — мусор, и хранить их нельзя.
    if match.home_score is None or match.home_score != match.away_score:
        match.home_penalty = None
        match.away_penalty = None

    propagate_playoff(match)
    db.session.commit()
    return jsonify({'success': True, 'match': serialize_match(match)})


# ===== ПРОТОКОЛ МАТЧА И СТАТИСТИКА ИГРОКОВ =====

AWARD_CODES = {
    'top_scorer': 'Лучший бомбардир',
    'best_goalkeeper': 'Лучший вратарь',
    'best_player': 'Лучший игрок',
    'best_defender': 'Лучший защитник',
    'best_midfielder': 'Лучший полузащитник',
    'fair_play': 'Fair Play',
}
# Расчётные призы система предлагает сама, остальные присуждают люди.
COMPUTED_AWARDS = {'top_scorer', 'best_goalkeeper', 'fair_play'}


def member_card(member):
    if not member:
        return None
    return {
        'id': member.id,
        'name': member.full_name,
        'short_name': ' '.join(filter(None, [
            member.last_name,
            f'{member.first_name[0]}.' if member.first_name else None,
        ])),
        'number': member.team_number,
        'position': member.position,
        'photo_url': get_tournament_media_url(member.photo_path),
    }


def serialize_protocol(match):
    """Протокол матча: составы обеих команд и события."""
    appearances = TournamentMatchAppearance.query.filter_by(match_id=match.id).all()
    events = TournamentMatchEvent.query.filter_by(match_id=match.id).order_by(
        TournamentMatchEvent.minute.is_(None), TournamentMatchEvent.minute, TournamentMatchEvent.id).all()

    def team_block(entry):
        if not entry or not entry.team:
            return None
        squad = [member_card(m) for m in entry.team.members]
        mine = [a for a in appearances if a.entry_id == entry.id]
        return {
            'entry_id': entry.id,
            'team_name': entry.team.name,
            'team_logo_url': get_tournament_media_url(entry.team.logo_path),
            'squad': squad,
            'lineup': [{
                'member_id': a.member_id,
                'is_starting': bool(a.is_starting),
                'is_goalkeeper': bool(a.is_goalkeeper),
                'minutes': a.minutes,
            } for a in mine],
        }

    return {
        'match_id': match.id,
        'home_score': match.home_score,
        'away_score': match.away_score,
        'home': team_block(match.home_entry),
        'away': team_block(match.away_entry),
        'events': [{
            'id': e.id,
            'entry_id': e.entry_id,
            'kind': e.kind,
            'member_id': e.member_id,
            'member_name': e.member.full_name if e.member else None,
            'minute': e.minute,
            'is_own_goal': bool(e.is_own_goal),
            'is_penalty': bool(e.is_penalty),
            'assist_member_id': e.assist_member_id,
            'assist_name': e.assist_member.full_name if e.assist_member else None,
            'card': e.card,
        } for e in events],
    }


@app.route('/api/tournament-matches/<int:match_id>/protocol', methods=['GET', 'PUT'])
@login_required
def tournament_match_protocol_api(match_id):
    match = db.session.get(TournamentMatch, match_id)
    if not match:
        return jsonify({'success': False, 'message': 'Матч не найден'}), 404

    if request.method == 'GET':
        return jsonify({'success': True, 'protocol': serialize_protocol(match)})

    if not match.home_entry_id or not match.away_entry_id:
        return jsonify({'success': False, 'message': 'В матче ещё не определены обе команды'}), 400

    data = request.get_json() or {}
    sides = {'home': match.home_entry_id, 'away': match.away_entry_id}

    # Игрок может попасть в протокол только из состава своей команды.
    allowed = {}
    for side, entry_id in sides.items():
        entry = db.session.get(TournamentEntry, entry_id)
        allowed[side] = {m.id for m in entry.team.members} if entry and entry.team else set()

    def parse_minute(value):
        if value in (None, ''):
            return None
        number = int(value)
        if number < 0 or number > 200:
            raise ValueError
        return number

    lineups = data.get('lineups') or {}
    events = data.get('events') or []

    try:
        goal_count = {'home': 0, 'away': 0}
        for event in events:
            side = event.get('side')
            if side not in sides:
                raise ValueError('Неизвестная команда в событии')
            if event.get('kind') == TournamentMatchEvent.KIND_GOAL:
                goal_count[side] += 1

        # Протокол обязан сходиться со счётом, иначе таблица бомбардиров врёт.
        if match.is_played:
            if goal_count['home'] != match.home_score or goal_count['away'] != match.away_score:
                return jsonify({'success': False, 'message':
                                f"Голов в протоколе {goal_count['home']}:{goal_count['away']}, "
                                f'а счёт матча {match.home_score}:{match.away_score}'}), 400
        elif goal_count['home'] or goal_count['away']:
            return jsonify({'success': False, 'message': 'Сначала укажите счёт матча'}), 400

        TournamentMatchAppearance.query.filter_by(match_id=match.id).delete()
        TournamentMatchEvent.query.filter_by(match_id=match.id).delete()

        for side, entry_id in sides.items():
            keepers = 0
            for row in (lineups.get(side) or []):
                member_id = int(row.get('member_id'))
                if member_id not in allowed[side]:
                    raise ValueError('Игрок не из состава этой команды')
                is_keeper = bool(row.get('is_goalkeeper'))
                keepers += 1 if is_keeper else 0
                db.session.add(TournamentMatchAppearance(
                    match_id=match.id,
                    entry_id=entry_id,
                    member_id=member_id,
                    is_starting=bool(row.get('is_starting', True)),
                    is_goalkeeper=is_keeper,
                    minutes=parse_minute(row.get('minutes')),
                ))
            if keepers > 1:
                raise ValueError('В одной команде отмечено несколько вратарей')

        for event in events:
            side = event.get('side')
            entry_id = sides[side]
            kind = event.get('kind') or TournamentMatchEvent.KIND_GOAL
            member_id = event.get('member_id')
            member_id = int(member_id) if member_id else None
            # Автогол забивает игрок соперника, поэтому его проверяем по чужому составу.
            own_goal = bool(event.get('is_own_goal'))
            other = 'away' if side == 'home' else 'home'
            if member_id and member_id not in allowed[other if own_goal else side]:
                raise ValueError('Автор события не из состава своей команды')
            assist_id = event.get('assist_member_id')
            assist_id = int(assist_id) if assist_id else None
            if assist_id and assist_id not in allowed[side]:
                raise ValueError('Ассистент не из состава этой команды')
            if kind == TournamentMatchEvent.KIND_CARD and event.get('card') not in (
                    TournamentMatchEvent.CARD_YELLOW, TournamentMatchEvent.CARD_RED):
                raise ValueError('Не указан цвет карточки')
            db.session.add(TournamentMatchEvent(
                match_id=match.id,
                entry_id=entry_id,
                member_id=member_id,
                kind=kind,
                minute=parse_minute(event.get('minute')),
                is_own_goal=own_goal,
                is_penalty=bool(event.get('is_penalty')),
                assist_member_id=assist_id if kind == TournamentMatchEvent.KIND_GOAL else None,
                card=event.get('card') if kind == TournamentMatchEvent.KIND_CARD else None,
            ))
    except ValueError as error:
        db.session.rollback()
        message = str(error) if str(error) else 'Минута — число от 0 до 200'
        return jsonify({'success': False, 'message': message}), 400

    db.session.commit()
    return jsonify({'success': True, 'protocol': serialize_protocol(match)})


def collect_player_stats(tournament, age_group):
    """Личная статистика по категории: бомбардиры, вратари, карточки, Fair Play."""
    matches = TournamentMatch.query.filter_by(
        tournament_id=tournament.id, age_group=age_group).all()
    match_by_id = {m.id: m for m in matches}
    if not match_by_id:
        return {'scorers': [], 'goalkeepers': [], 'cards': [], 'fair_play': []}

    ids = list(match_by_id.keys())
    appearances = TournamentMatchAppearance.query.filter(
        TournamentMatchAppearance.match_id.in_(ids)).all()
    events = TournamentMatchEvent.query.filter(
        TournamentMatchEvent.match_id.in_(ids)).all()

    entries = {e.id: e for e in TournamentEntry.query.filter_by(
        tournament_id=tournament.id, age_group=age_group).all()}

    def team_of(entry_id):
        entry = entries.get(entry_id)
        return entry.team if entry else None

    def base_row(member, entry_id):
        team = team_of(entry_id)
        return {
            'member_id': member.id,
            'name': member.full_name,
            'number': member.team_number,
            'position': member.position,
            'photo_url': get_tournament_media_url(member.photo_path),
            'team_name': team.name if team else '—',
            'team_logo_url': get_tournament_media_url(team.logo_path) if team else None,
        }

    played = {mid for mid, m in match_by_id.items() if m.is_played}

    # --- бомбардиры ---
    scorers = {}
    for event in events:
        if event.kind != TournamentMatchEvent.KIND_GOAL or event.is_own_goal or not event.member:
            continue
        row = scorers.setdefault(event.member_id, {
            **base_row(event.member, event.entry_id),
            'goals': 0, 'penalty_goals': 0, 'assists': 0, 'matches': 0,
        })
        row['goals'] += 1
        if event.is_penalty:
            row['penalty_goals'] += 1

    assists = {}
    for event in events:
        if event.kind != TournamentMatchEvent.KIND_GOAL or not event.assist_member_id:
            continue
        assists[event.assist_member_id] = assists.get(event.assist_member_id, 0) + 1
        if event.assist_member_id not in scorers and event.assist_member:
            scorers[event.assist_member_id] = {
                **base_row(event.assist_member, event.entry_id),
                'goals': 0, 'penalty_goals': 0, 'assists': 0, 'matches': 0,
            }

    member_matches = {}
    for appearance in appearances:
        if appearance.match_id not in played:
            continue
        member_matches.setdefault(appearance.member_id, set()).add(appearance.match_id)

    for member_id, row in scorers.items():
        row['assists'] = assists.get(member_id, 0)
        row['matches'] = len(member_matches.get(member_id, ()))
    # Больше голов; при равенстве выше тот, кто забил за меньшее число матчей.
    scorer_rows = sorted(scorers.values(), key=lambda r: (
        -r['goals'], -r['assists'], r['matches'] or 99, r['name']))

    # --- вратари ---
    conceded = {}
    for event in events:
        if event.kind != TournamentMatchEvent.KIND_GOAL:
            continue
        conceded[(event.match_id, event.entry_id)] = conceded.get(
            (event.match_id, event.entry_id), 0) + 1

    keepers = {}
    for appearance in appearances:
        if not appearance.is_goalkeeper or appearance.match_id not in played:
            continue
        match = match_by_id[appearance.match_id]
        against = match.away_entry_id if appearance.entry_id == match.home_entry_id else match.home_entry_id
        # Мячи, забитые сопернику, — это пропущенные нашим вратарём.
        goals_against = conceded.get((match.id, against), 0)
        row = keepers.setdefault(appearance.member_id, {
            **base_row(appearance.member, appearance.entry_id),
            'matches': 0, 'conceded': 0, 'clean_sheets': 0,
        })
        row['matches'] += 1
        row['conceded'] += goals_against
        if goals_against == 0:
            row['clean_sheets'] += 1

    team_match_count = {}
    for match in matches:
        if not match.is_played:
            continue
        for entry_id in (match.home_entry_id, match.away_entry_id):
            if entry_id:
                team_match_count[entry_id] = team_match_count.get(entry_id, 0) + 1

    keeper_rows = []
    for member_id, row in keepers.items():
        row['avg_conceded'] = round(row['conceded'] / row['matches'], 2) if row['matches'] else None
        # Ценз: иначе вратарь одного матча 0:0 обходит того, кто отыграл весь турнир.
        entry_id = next((a.entry_id for a in appearances if a.member_id == member_id), None)
        need = team_match_count.get(entry_id, 0)
        row['qualified'] = row['matches'] * 2 >= need if need else False
        keeper_rows.append(row)
    keeper_rows.sort(key=lambda r: (
        not r['qualified'], -r['clean_sheets'], r['avg_conceded'] if r['avg_conceded'] is not None else 99,
        -r['matches'], r['name']))

    # --- карточки и Fair Play ---
    cards = {}
    team_penalty = {}
    for event in events:
        if event.kind != TournamentMatchEvent.KIND_CARD:
            continue
        weight = 3 if event.card == TournamentMatchEvent.CARD_RED else 1
        team_penalty[event.entry_id] = team_penalty.get(event.entry_id, 0) + weight
        if not event.member:
            continue
        row = cards.setdefault(event.member_id, {
            **base_row(event.member, event.entry_id), 'yellow': 0, 'red': 0,
        })
        if event.card == TournamentMatchEvent.CARD_RED:
            row['red'] += 1
        else:
            row['yellow'] += 1
    card_rows = sorted(cards.values(), key=lambda r: (-r['red'], -r['yellow'], r['name']))

    fair_play = []
    for entry_id, entry in entries.items():
        if not entry.team or not team_match_count.get(entry_id):
            continue
        team = entry.team
        fair_play.append({
            'entry_id': entry_id,
            'team_name': team.name,
            'team_logo_url': get_tournament_media_url(team.logo_path),
            'penalty': team_penalty.get(entry_id, 0),
            'matches': team_match_count.get(entry_id, 0),
        })
    fair_play.sort(key=lambda r: (r['penalty'], r['team_name']))

    return {
        'scorers': scorer_rows,
        'goalkeepers': keeper_rows,
        'cards': card_rows,
        'fair_play': fair_play,
    }


def suggested_awards(stats):
    """Кого система предлагает наградить по расчётным призам."""
    out = {}
    if stats['scorers'] and stats['scorers'][0]['goals']:
        out['top_scorer'] = stats['scorers'][0]
    qualified = [k for k in stats['goalkeepers'] if k['qualified']]
    if qualified:
        out['best_goalkeeper'] = qualified[0]
    if stats['fair_play']:
        out['fair_play'] = stats['fair_play'][0]
    return out


def serialize_awards(tournament, age_group, stats):
    stored = {a.code: a for a in TournamentAward.query.filter_by(
        tournament_id=tournament.id, age_group=age_group).all()}
    suggested = suggested_awards(stats)
    rows = []
    for code, title in AWARD_CODES.items():
        award = stored.get(code)
        winner = None
        if award and award.member:
            team = award.member.team
            winner = {
                'member_id': award.member.id,
                'name': award.member.full_name,
                'number': award.member.team_number,
                'photo_url': get_tournament_media_url(award.member.photo_path),
                'team_name': team.name if team else '—',
                'team_logo_url': get_tournament_media_url(team.logo_path) if team else None,
            }
        elif award and award.entry and award.entry.team:
            team = award.entry.team
            winner = {
                'member_id': None,
                'name': team.name,
                'number': None,
                'photo_url': None,
                'team_name': team.name,
                'team_logo_url': get_tournament_media_url(team.logo_path),
            }
        rows.append({
            'code': code,
            'title': title,
            'computed': code in COMPUTED_AWARDS,
            'winner': winner,
            'note': award.note if award else None,
            'suggested': suggested.get(code),
        })
    return rows


@app.route('/api/tournaments/<int:tournament_id>/players', methods=['GET'])
@login_required
def tournament_players_api(tournament_id):
    tournament = db.session.get(Tournament, tournament_id)
    if not tournament:
        return jsonify({'success': False, 'message': 'Турнир не найден'}), 404
    age_group = (request.args.get('age_group') or '').strip()
    labels = tournament_age_group_labels(tournament)
    if not age_group and labels:
        age_group = labels[0]
    stats = collect_player_stats(tournament, age_group)
    return jsonify({
        'success': True,
        'age_group': age_group,
        'stats': stats,
        'awards': serialize_awards(tournament, age_group, stats),
    })


@app.route('/api/tournaments/<int:tournament_id>/awards', methods=['PUT'])
@login_required
def tournament_awards_api(tournament_id):
    tournament = db.session.get(Tournament, tournament_id)
    if not tournament:
        return jsonify({'success': False, 'message': 'Турнир не найден'}), 404
    data = request.get_json() or {}
    age_group = (data.get('age_group') or '').strip()
    code = (data.get('code') or '').strip()
    if code not in AWARD_CODES:
        return jsonify({'success': False, 'message': 'Неизвестная награда'}), 400

    award = TournamentAward.query.filter_by(
        tournament_id=tournament.id, age_group=age_group, code=code).first()
    member_id = data.get('member_id')
    entry_id = data.get('entry_id')

    if not member_id and not entry_id:
        if award:
            db.session.delete(award)
            db.session.commit()
        return jsonify({'success': True})

    if not award:
        award = TournamentAward(tournament_id=tournament.id, age_group=age_group, code=code)
        db.session.add(award)
    award.member_id = int(member_id) if member_id else None
    award.entry_id = int(entry_id) if entry_id else None
    award.note = (data.get('note') or '').strip() or None
    db.session.commit()

    stats = collect_player_stats(tournament, age_group)
    return jsonify({'success': True, 'awards': serialize_awards(tournament, age_group, stats)})


# ===== ПУБЛИЧНАЯ АФИША ТУРНИРОВ =====

def public_tournament_payload(tournament, stadium_by_name):
    """Карточка для афиши: только турнир и площадка, без персональных данных."""
    try:
        age_groups = json.loads(tournament.age_groups or '[]')
    except Exception:
        age_groups = normalize_age_groups(tournament.age_groups)

    stadium = stadium_by_name.get((tournament.location or '').strip().lower())
    return {
        'id': tournament.id,
        'name': tournament.name,
        'poster_url': get_tournament_media_url(tournament.poster_path),
        'location': tournament.location,
        'start_date': tournament.start_date.isoformat() if tournament.start_date else None,
        'start_time': tournament.start_time.strftime('%H:%M') if tournament.start_time else None,
        'end_date': tournament.end_date.isoformat() if tournament.end_date else None,
        'age_groups': age_groups,
        'teams_count': TournamentEntry.query.filter_by(
            tournament_id=tournament.id,
            status=TournamentEntry.STATUS_CONFIRMED,
        ).count(),
        'stadium': {
            'photo_url': get_tournament_media_url(stadium.photo_path),
            'photo_source': stadium.photo_source,
            'latitude': stadium.latitude,
            'longitude': stadium.longitude,
        } if stadium else None,
    }


def public_player_stats(tournament, age_group):
    """Личная статистика для афиши: без дат рождения, телефонов и адресов."""
    stats = collect_player_stats(tournament, age_group)
    keep = ('member_id', 'name', 'number', 'position', 'photo_url',
            'team_name', 'team_logo_url')

    def trim(row, extra):
        out = {key: row.get(key) for key in keep}
        out.update({key: row.get(key) for key in extra})
        return out

    awards = [a for a in serialize_awards(tournament, age_group, stats) if a['winner']]
    return {
        'scorers': [trim(r, ('goals', 'penalty_goals', 'assists', 'matches'))
                    for r in stats['scorers'][:10]],
        'goalkeepers': [trim(r, ('matches', 'conceded', 'clean_sheets', 'avg_conceded'))
                        for r in stats['goalkeepers'][:10] if r['qualified']],
        'cards': [trim(r, ('yellow', 'red')) for r in stats['cards'][:10]],
        'fair_play': stats['fair_play'][:10],
        'awards': [{'code': a['code'], 'title': a['title'], 'winner': a['winner'],
                    'note': a['note']} for a in awards],
    }


@app.route('/api/public/tournaments/<int:tournament_id>')
def public_tournament_detail_api(tournament_id):
    """Карточка турнира для гостя: сам турнир и команды, но без персональных данных."""
    ensure_tournament_tables()
    tournament = Tournament.query.filter_by(id=tournament_id).first()
    if not tournament or not tournament.is_published:
        return jsonify({'success': False, 'message': 'Турнир не найден'}), 404

    stadium_by_name = {
        (item.name or '').strip().lower(): item
        for item in TournamentStadium.query.all()
    }
    payload = public_tournament_payload(tournament, stadium_by_name)

    entries = TournamentEntry.query.filter_by(
        tournament_id=tournament.id,
        status=TournamentEntry.STATUS_CONFIRMED,
    ).all()
    entries.sort(key=lambda item: (item.age_group, (item.team.name if item.team else '')))

    groups = TournamentGroup.query.filter_by(tournament_id=tournament.id).order_by(
        TournamentGroup.age_group.asc(), TournamentGroup.sort_order.asc(),
    ).all()
    matches = TournamentMatch.query.filter_by(tournament_id=tournament.id).order_by(
        TournamentMatch.round_no.asc(), TournamentMatch.id.asc(),
    ).all()

    def public_team(entry):
        # Наружу отдаём только название и логотип: телефоны тренеров и составы
        # остаются внутри системы.
        return {
            'name': entry.team.name if entry.team else '—',
            'logo_url': get_tournament_media_url(entry.team.logo_path) if entry.team else None,
        }

    def public_match(match):
        data = serialize_match(match)
        return {
            'round_no': data['round_no'],
            'home': data['home']['team_name'],
            'home_id': data['home']['entry_id'],
            'home_logo_url': data['home']['team_logo_url'],
            'away': data['away']['team_name'],
            'away_id': data['away']['entry_id'],
            'away_logo_url': data['away']['team_logo_url'],
            'home_score': data['home_score'],
            'away_score': data['away_score'],
            'home_penalty': data['home_penalty'],
            'away_penalty': data['away_penalty'],
            'is_played': data['is_played'],
            'kickoff_at': data['kickoff_at'],
            'stadium_name': data['stadium_name'],
        }

    categories = []
    for age_group in tournament_age_group_labels(tournament):
        age_entries = [e for e in entries if e.age_group == age_group and e.team]
        age_groups = [g for g in groups if g.age_group == age_group]
        blocks = []
        for group in age_groups:
            group_entries = [e for e in age_entries if e.group_id == group.id]
            group_matches = [m for m in matches if m.group_id == group.id
                             and m.stage == TournamentMatch.STAGE_GROUP]
            blocks.append({
                'name': group.name,
                'standings': build_standings(group_entries, group_matches),
                'matches': [public_match(m) for m in group_matches],
            })
        age_playoff = [m for m in matches
                       if m.age_group == age_group
                       and m.stage == TournamentMatch.STAGE_PLAYOFF]
        age_playoff.sort(key=lambda m: (m.round_no, m.bracket_slot or 0))
        categories.append({
            'age_group': age_group,
            'teams': [public_team(e) for e in age_entries],
            'groups': blocks,
            'playoff': [dict(public_match(m), label=m.label) for m in age_playoff],
            'results': playoff_results(age_playoff),
            'players': public_player_stats(tournament, age_group),
        })

    # Категории без единой заявки на афише не нужны.
    payload['categories'] = [c for c in categories if c['teams']]
    return jsonify({'success': True, 'tournament': payload})


@app.route('/tournaments-afisha')
def public_tournaments_page():
    return render_template('public_tournaments.html')


# ===== ОБЛОЖКА НАГРАДЫ =====

COVER_FONT_PATH = os.path.join(basedir, 'frontend', 'static', 'vendor',
                               'onest-ttf', 'Onest-VariableFont_wght.ttf')
COVER_SIZE = (1080, 1350)
COVER_BG = (23, 25, 31)
COVER_ACCENT = (255, 154, 43)


def plural_ru(number, one, few, many):
    if 11 <= number % 100 <= 14:
        return many
    tail = number % 10
    if tail == 1:
        return one
    if 2 <= tail <= 4:
        return few
    return many


def cover_font(size, weight=400):
    """Шрифт обложки. Файл вариативный, поэтому вес задаётся осью, а не отдельным файлом."""
    font = ImageFont.truetype(COVER_FONT_PATH, size)
    try:
        font.set_variation_by_axes([weight])
    except Exception:
        pass
    return font


def cover_circle(image, size):
    """Кадрирует картинку в круг заданного диаметра."""
    if image.mode in ('RGBA', 'LA', 'P'):
        source = image.convert('RGBA')
        plate = Image.new('RGBA', source.size, (255, 255, 255, 255))
        source = Image.alpha_composite(plate, source).convert('RGB')
    else:
        source = image.convert('RGB')
    width, height = source.size
    side = min(width, height)
    source = source.crop(((width - side) // 2, (height - side) // 2,
                          (width + side) // 2, (height + side) // 2)).resize((size, size), Image.LANCZOS)
    mask = Image.new('L', (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    source.putalpha(mask.resize((size, size), Image.LANCZOS))
    return source


def cover_local_image(media_path):
    if not media_path:
        return None
    filename = media_path.replace('\\', '/').split('/')[-1]
    full = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(full):
        return None
    try:
        return Image.open(full)
    except Exception:
        return None


def draw_centered(draw, y, text, font, fill):
    width = draw.textlength(text, font=font)
    draw.text(((COVER_SIZE[0] - width) / 2, y), text, font=font, fill=fill)
    return width


def fit_font(draw, text, max_width, start_size, weight=750):
    """Подбирает кегль, чтобы длинная фамилия не выехала за поля."""
    size = start_size
    while size > 24:
        font = cover_font(size, weight)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 4
    return cover_font(24, weight)


def build_award_cover(tournament, age_group, title, winner, value_line):
    canvas = Image.new('RGB', COVER_SIZE, COVER_BG)
    draw = ImageDraw.Draw(canvas)
    margin = 70
    inner = COVER_SIZE[0] - margin * 2

    # Подложка: постер турнира, приглушённый, чтобы текст читался.
    poster = cover_local_image(tournament.poster_path)
    if poster:
        poster = poster.convert('RGB')
        ratio = max(COVER_SIZE[0] / poster.width, COVER_SIZE[1] / poster.height)
        poster = poster.resize((int(poster.width * ratio) + 1, int(poster.height * ratio) + 1), Image.LANCZOS)
        left = (poster.width - COVER_SIZE[0]) // 2
        top = (poster.height - COVER_SIZE[1]) // 2
        poster = poster.crop((left, top, left + COVER_SIZE[0], top + COVER_SIZE[1]))
        poster = poster.filter(ImageFilter.GaussianBlur(18))
        canvas.paste(poster, (0, 0))
        canvas = Image.blend(canvas, Image.new('RGB', COVER_SIZE, COVER_BG), 0.62)
        draw = ImageDraw.Draw(canvas)

    draw.text((margin, margin), tournament.name.upper(), font=cover_font(30, 700), fill=(255, 255, 255))
    subtitle = ' · '.join(filter(None, [
        age_group,
        tournament.start_date.strftime('%d.%m.%Y') if tournament.start_date else None,
    ]))
    draw.text((margin, margin + 42), subtitle, font=cover_font(26, 400), fill=(170, 175, 185))

    photo = cover_local_image(winner.get('photo_path'))
    if photo is None and winner.get('team_award'):
        photo = cover_local_image(winner.get('logo_path'))
    face_size = 460
    face_top = 250
    ring = 8
    draw.ellipse((COVER_SIZE[0] / 2 - face_size / 2 - ring, face_top - ring,
                  COVER_SIZE[0] / 2 + face_size / 2 + ring, face_top + face_size + ring),
                 fill=COVER_ACCENT)
    if photo:
        circle = cover_circle(photo, face_size)
        canvas.paste(circle, (int(COVER_SIZE[0] / 2 - face_size / 2), face_top), circle)
    else:
        draw.ellipse((COVER_SIZE[0] / 2 - face_size / 2, face_top,
                      COVER_SIZE[0] / 2 + face_size / 2, face_top + face_size), fill=(44, 47, 56))
        initials = (winner.get('name') or '?')[:2].upper()
        font = cover_font(150, 750)
        draw_centered(draw, face_top + face_size / 2 - 100, initials, font, (120, 125, 135))

    y = face_top + face_size + 70
    draw_centered(draw, y, title.upper(), cover_font(34, 700), COVER_ACCENT)

    y += 70
    name_font = fit_font(draw, winner.get('name') or '', inner, 88)
    draw_centered(draw, y, winner.get('name') or '', name_font, (255, 255, 255))

    y += 110
    draw_centered(draw, y, winner.get('team_name') or '', cover_font(34, 400), (170, 175, 185))

    if value_line:
        y += 80
        draw_centered(draw, y, value_line, cover_font(64, 750), (255, 255, 255))

    settings = ClubSettings.query.first()
    club = (settings.system_name if settings and settings.system_name else 'FK KARASU')
    draw_centered(draw, COVER_SIZE[1] - 110, club, cover_font(28, 700), (120, 125, 135))
    return canvas


@app.route('/api/tournaments/<int:tournament_id>/awards/<code>/cover.png')
@login_required
def tournament_award_cover(tournament_id, code):
    tournament = db.session.get(Tournament, tournament_id)
    if not tournament or code not in AWARD_CODES:
        return jsonify({'success': False, 'message': 'Награда не найдена'}), 404
    age_group = (request.args.get('age_group') or '').strip()
    award = TournamentAward.query.filter_by(
        tournament_id=tournament.id, age_group=age_group, code=code).first()
    if not award or not (award.member_id or award.entry_id):
        return jsonify({'success': False, 'message': 'Награда ещё не присуждена'}), 404

    stats = collect_player_stats(tournament, age_group)
    value_line = ''
    if award.member:
        team = award.member.team
        winner = {
            'name': award.member.full_name,
            'team_name': team.name if team else '',
            'photo_path': award.member.photo_path,
            'logo_path': team.logo_path if team else None,
        }
        row = next((r for r in stats['scorers'] if r['member_id'] == award.member_id), None)
        keeper = next((r for r in stats['goalkeepers'] if r['member_id'] == award.member_id), None)
        if code == 'top_scorer' and row:
            value_line = f"{row['goals']} " + plural_ru(row['goals'], 'гол', 'гола', 'голов')
        elif code == 'best_goalkeeper' and keeper:
            value_line = f"{keeper['clean_sheets']} " + plural_ru(
                keeper['clean_sheets'], 'сухой матч', 'сухих матча', 'сухих матчей')
    else:
        team = award.entry.team if award.entry else None
        winner = {
            'name': team.name if team else '',
            'team_name': age_group,
            'photo_path': None,
            'logo_path': team.logo_path if team else None,
            'team_award': True,
        }

    image = build_award_cover(tournament, age_group, AWARD_CODES[code], winner, value_line)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    buffer.seek(0)
    name = f'{code}-{age_group or "all"}.png'
    return send_file(buffer, mimetype='image/png', as_attachment=False, download_name=name)


# ===== СТУДИЯ ПУБЛИКАЦИЙ =====
# Картинку рисует только сервер: предпросмотр в браузере — это тот же PNG,
# что уйдёт в Telegram. Иначе превью и файл неизбежно разъезжаются.

POST_FONT_DIR = os.path.join(basedir, 'frontend', 'static', 'vendor', 'onest-ttf')
POST_FONTS = {
    'onest': ('Onest-VariableFont_wght.ttf', 'Onest — нейтральный'),
    'unbounded': ('Unbounded.ttf', 'Unbounded — плакатный'),
    'manrope': ('Manrope.ttf', 'Manrope — округлый'),
}
POST_FORMATS = {
    'post': (1080, 1350, 'Instagram — пост'),
    'square': (1080, 1080, 'Квадрат'),
    'story': (1080, 1920, 'Сторис'),
    'wide': (1200, 675, 'Telegram — широкий'),
}
POST_THEMES = {
    'dark': ('Тёмная', (18, 20, 26), (255, 255, 255), (156, 163, 175)),
    'light': ('Светлая', (247, 245, 243), (23, 25, 31), (110, 116, 126)),
    'grass': ('Травяная', (12, 46, 32), (255, 255, 255), (168, 200, 182)),
    'night': ('Полуночная', (17, 24, 51), (255, 255, 255), (160, 172, 210)),
}
POST_TEMPLATES = {
    'announce': 'Анонс турнира',
    'match': 'Результат матча',
    'standings': 'Таблица группы',
    'results': 'Итоги турнира',
    'award': 'Награда',
}
POST_ACCENTS = ['#ff9a2b', '#e63946', '#2a9d8f', '#4361ee', '#f4a261', '#111827']


def post_font(key, size, weight=400):
    filename = POST_FONTS.get(key, POST_FONTS['onest'])[0]
    font = ImageFont.truetype(os.path.join(POST_FONT_DIR, filename), size)
    try:
        font.set_variation_by_axes([weight])
    except Exception:
        pass
    return font


def hex_to_rgb(value, fallback=(255, 154, 43)):
    value = (value or '').strip().lstrip('#')
    if len(value) != 6:
        return fallback
    try:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return fallback


def wrap_text(draw, text, font, max_width):
    words = (text or '').split()
    lines, current = [], ''
    for word in words:
        probe = f'{current} {word}'.strip()
        if draw.textlength(probe, font=font) <= max_width or not current:
            current = probe
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def fit_text_font(draw, text, max_width, start, key, weight):
    size = start
    while size > 20:
        font = post_font(key, size, weight)
        if draw.textlength(text or '', font=font) <= max_width:
            return font
        size -= 4
    return post_font(key, 20, weight)


def paste_cover(canvas, image, box):
    """Вписывает картинку в прямоугольник по короткой стороне."""
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    source = image.convert('RGB')
    ratio = max(width / source.width, height / source.height)
    source = source.resize((int(source.width * ratio) + 1, int(source.height * ratio) + 1), Image.LANCZOS)
    x = (source.width - width) // 2
    y = (source.height - height) // 2
    canvas.paste(source.crop((x, y, x + width, y + height)), (left, top))


def post_logo(canvas, media_path, center, size, plate):
    """Логотип команды в круге. Прозрачный PNG кладём на светлую подложку."""
    draw = ImageDraw.Draw(canvas)
    cx, cy = center
    draw.ellipse((cx - size // 2, cy - size // 2, cx + size // 2, cy + size // 2), fill=plate)
    image = cover_local_image(media_path)
    if not image:
        return
    circle = cover_circle(image, size - 8)
    canvas.paste(circle, (cx - (size - 8) // 2, cy - (size - 8) // 2), circle)


def post_background(canvas, params, theme_bg):
    """Фон: заливка темы, постер турнира или загруженная картинка."""
    background = params.get('background')
    image = None
    if background == 'poster':
        image = cover_local_image(params['tournament'].poster_path)
    elif background == 'custom':
        image = cover_local_image(params.get('background_path'))
    if image is None:
        return canvas
    paste_cover(canvas, image, (0, 0, canvas.width, canvas.height))
    if params.get('blur'):
        canvas = canvas.filter(ImageFilter.GaussianBlur(14))
    shade = int(params.get('shade', 70))
    plate = Image.new('RGB', canvas.size, theme_bg)
    return Image.blend(canvas, plate, max(0, min(95, shade)) / 100)


def post_header(canvas, params, margin):
    draw = ImageDraw.Draw(canvas)
    tournament = params['tournament']
    draw.text((margin, margin), (params.get('eyebrow') or tournament.name).upper(),
              font=post_font(params['font'], 30, 700), fill=params['accent'])
    line = params.get('caption') or ' · '.join(filter(None, [
        params.get('age_group'),
        tournament.start_date.strftime('%d.%m.%Y') if tournament.start_date else None,
        tournament.location,
    ]))
    if line:
        draw.text((margin, margin + 44), line, font=post_font(params['font'], 26, 400), fill=params['muted'])


def post_footer(canvas, params, margin):
    draw = ImageDraw.Draw(canvas)
    settings = ClubSettings.query.first()
    club = (settings.system_name if settings and settings.system_name else 'FK KARASU')
    draw.text((margin, canvas.height - margin - 30), club,
              font=post_font(params['font'], 26, 700), fill=params['muted'])


def render_announce(canvas, params, margin):
    draw = ImageDraw.Draw(canvas)
    tournament = params['tournament']
    inner = canvas.width - margin * 2
    y = int(canvas.height * 0.3)
    title = params.get('title') or tournament.name
    font = post_font(params['font'], 96 if canvas.width >= 1080 else 64, 750)
    for line in wrap_text(draw, title, font, inner)[:3]:
        draw.text((margin, y), line, font=font, fill=params['ink'])
        y += int(font.size * 1.12)

    subtitle = params.get('subtitle')
    if subtitle is None:
        subtitle = ' · '.join(filter(None, [
            tournament.location,
            tournament_age_group_labels(tournament) and ', '.join(
                tournament_age_group_labels(tournament)) or None,
        ]))
    if subtitle:
        y += 24
        font = post_font(params['font'], 38, 400)
        for line in wrap_text(draw, subtitle, font, inner)[:3]:
            draw.text((margin, y), line, font=font, fill=params['muted'])
            y += int(font.size * 1.3)

    note = params.get('note')
    if note:
        y += 34
        pill = post_font(params['font'], 34, 700)
        width = draw.textlength(note, font=pill)
        draw.rounded_rectangle((margin, y, margin + width + 56, y + 74), radius=37, fill=params['accent'])
        draw.text((margin + 28, y + 16), note, font=pill, fill=params['on_accent'])


def render_match(canvas, params, margin):
    draw = ImageDraw.Draw(canvas)
    match = params.get('match')
    if not match:
        return render_announce(canvas, params, margin)
    center = canvas.width // 2
    top = int(canvas.height * 0.28)
    logo = 190 if canvas.height > 900 else 130
    gap = int(canvas.width * 0.24)

    for side, offset in (('home', -gap), ('away', gap)):
        entry = match.home_entry if side == 'home' else match.away_entry
        team = entry.team if entry else None
        post_logo(canvas, team.logo_path if team else None, (center + offset, top + logo // 2),
                  logo, params['plate'])
        name = team.name if team else '—'
        font = fit_text_font(draw, name, gap * 1.5, 40, params['font'], 700)
        width = draw.textlength(name, font=font)
        draw.text((center + offset - width / 2, top + logo + 26), name, font=font, fill=params['ink'])

    score = f'{match.home_score} : {match.away_score}' if match.is_played else '— : —'
    font = post_font(params['font'], 92, 750)
    width = draw.textlength(score, font=font)
    draw.text((center - width / 2, top + logo // 2 - font.size * 0.62), score, font=font, fill=params['ink'])

    if match.home_penalty is not None and match.home_score == match.away_score:
        pen = f'по пенальти {match.home_penalty}:{match.away_penalty}'
        font = post_font(params['font'], 30, 400)
        width = draw.textlength(pen, font=font)
        draw.text((center - width / 2, top + logo // 2 + 44), pen, font=font, fill=params['muted'])

    stage = params.get('title') or (match.label or (
        f'Группа {match.group.name}' if match.group else 'Матч турнира'))
    font = post_font(params['font'], 40, 700)
    width = draw.textlength(stage, font=font)
    draw.text((center - width / 2, top + logo + 130), stage, font=font, fill=params['accent'])

    when = params.get('subtitle')
    if when is None and match.kickoff_at:
        when = match.kickoff_at.strftime('%d.%m.%Y, %H:%M')
    if when:
        font = post_font(params['font'], 30, 400)
        width = draw.textlength(when, font=font)
        draw.text((center - width / 2, top + logo + 190), when, font=font, fill=params['muted'])


def render_rows(canvas, params, margin, heading, rows):
    """Общая отрисовка списка: таблица группы и итоги устроены одинаково."""
    draw = ImageDraw.Draw(canvas)
    y = int(canvas.height * 0.24)
    if heading:
        font = post_font(params['font'], 56, 750)
        draw.text((margin, y), heading, font=font, fill=params['ink'])
        y += 96

    space = canvas.height - y - margin - 60
    step = max(84, min(150, int(space / max(len(rows), 1))))
    for index, row in enumerate(rows):
        cy = y + step // 2
        badge = post_font(params['font'], 30, 750)
        number = str(row.get('rank') or index + 1)
        draw.ellipse((margin, cy - 24, margin + 48, cy + 24),
                     fill=params['accent'] if index == 0 else params['plate'])
        width = draw.textlength(number, font=badge)
        draw.text((margin + 24 - width / 2, cy - 18), number, font=badge,
                  fill=params['on_accent'] if index == 0 else params['muted'])

        post_logo(canvas, row.get('logo_path'), (margin + 48 + 26 + 26, cy), 52, params['plate'])

        name_font = post_font(params['font'], 38, 700)
        value_font = post_font(params['font'], 38, 750)
        value = str(row.get('value') or '')
        value_width = draw.textlength(value, font=value_font)
        name_left = margin + 48 + 26 + 52 + 26
        name_max = canvas.width - margin - value_width - 30 - name_left
        name = row.get('name') or ''
        name_font = fit_text_font(draw, name, name_max, 38, params['font'], 700)
        note = row.get('note')
        name_top = cy - name_font.size * (1.05 if note else 0.62)
        draw.text((name_left, name_top), name, font=name_font, fill=params['ink'])
        if note:
            draw.text((name_left, cy + 6), note,
                      font=post_font(params['font'], 24, 400), fill=params['muted'])
        if value:
            draw.text((canvas.width - margin - value_width, cy - value_font.size * 0.62),
                      value, font=value_font, fill=params['accent'])
        if index < len(rows) - 1:
            draw.line((margin, y + step - 1, canvas.width - margin, y + step - 1),
                      fill=params['plate'], width=1)
        y += step


def render_standings(canvas, params, margin):
    group = params.get('group')
    if not group:
        return render_announce(canvas, params, margin)
    entries = TournamentEntry.query.filter_by(group_id=group.id).all()
    matches = TournamentMatch.query.filter_by(
        group_id=group.id, stage=TournamentMatch.STAGE_GROUP).all()
    rows = []
    for row in build_standings(entries, matches)[:7]:
        entry = next((e for e in entries if e.team and e.team.name == row['team_name']), None)
        rows.append({
            'rank': row['place'],
            'name': row['team_name'],
            'note': f"{row['played']} и · {row['goals_for']}–{row['goals_against']}",
            'value': str(row['points']),
            'logo_path': entry.team.logo_path if entry and entry.team else None,
        })
    render_rows(canvas, params, margin, params.get('title') or f'Группа {group.name}', rows)


def render_results(canvas, params, margin):
    matches = TournamentMatch.query.filter_by(
        tournament_id=params['tournament'].id, age_group=params.get('age_group') or '',
        stage=TournamentMatch.STAGE_PLAYOFF).all()
    places = playoff_results(matches)
    titles = {1: 'Победитель', 2: 'Второе место', 3: 'Третье место', 4: 'Четвёртое место'}
    rows = []
    for row in places:
        entry = TournamentEntry.query.filter_by(
            tournament_id=params['tournament'].id, age_group=params.get('age_group') or '').all()
        team = next((e.team for e in entry if e.team and e.team.name == row['team_name']), None)
        rows.append({
            'rank': row['place'],
            'name': row['team_name'],
            'note': titles.get(row['place'], ''),
            'value': '',
            'logo_path': team.logo_path if team else None,
        })
    render_rows(canvas, params, margin, params.get('title') or 'Итоги турнира', rows)


def render_award(canvas, params, margin):
    draw = ImageDraw.Draw(canvas)
    award = params.get('award')
    if not award:
        return render_announce(canvas, params, margin)
    center = canvas.width // 2
    face = 440 if canvas.height > 1100 else 320
    top = int(canvas.height * 0.22)
    draw.ellipse((center - face // 2 - 8, top - 8, center + face // 2 + 8, top + face + 8),
                 fill=params['accent'])
    member = award.member
    team = member.team if member else (award.entry.team if award.entry else None)
    photo = cover_local_image(member.photo_path) if member else None
    if photo is None and not member:
        photo = cover_local_image(team.logo_path if team else None)
    if photo:
        circle = cover_circle(photo, face)
        canvas.paste(circle, (center - face // 2, top), circle)
    else:
        draw.ellipse((center - face // 2, top, center + face // 2, top + face), fill=params['plate'])

    y = top + face + 60
    title = params.get('title') or AWARD_CODES.get(award.code, '')
    font = post_font(params['font'], 38, 700)
    width = draw.textlength(title.upper(), font=font)
    draw.text((center - width / 2, y), title.upper(), font=font, fill=params['accent'])

    y += 70
    name = params.get('subtitle') or (member.full_name if member else (team.name if team else ''))
    font = fit_text_font(draw, name, canvas.width - margin * 2, 84, params['font'], 750)
    width = draw.textlength(name, font=font)
    draw.text((center - width / 2, y), name, font=font, fill=params['ink'])

    y += int(font.size * 1.35)
    note = params.get('note')
    if note is None:
        note = team.name if (member and team) else ''
    if note:
        font = post_font(params['font'], 34, 400)
        width = draw.textlength(note, font=font)
        draw.text((center - width / 2, y), note, font=font, fill=params['muted'])


POST_RENDERERS = {
    'announce': render_announce,
    'match': render_match,
    'standings': render_standings,
    'results': render_results,
    'award': render_award,
}


def build_post_image(tournament, data):
    template = data.get('template') if data.get('template') in POST_RENDERERS else 'announce'
    width, height, _ = POST_FORMATS.get(data.get('format'), POST_FORMATS['post'])
    theme_name, theme_bg, theme_ink, theme_muted = POST_THEMES.get(
        data.get('theme'), POST_THEMES['dark'])
    accent = hex_to_rgb(data.get('accent'))
    light_theme = data.get('theme') == 'light'

    canvas = Image.new('RGB', (width, height), theme_bg)
    params = {
        'tournament': tournament,
        'font': data.get('font') if data.get('font') in POST_FONTS else 'onest',
        'accent': accent,
        'ink': theme_ink,
        'muted': theme_muted,
        'plate': (240, 237, 233) if light_theme else (44, 48, 58),
        'on_accent': (23, 25, 31),
        'background': data.get('background'),
        'background_path': data.get('background_path'),
        'shade': data.get('shade', 70),
        'blur': data.get('blur'),
        'age_group': data.get('age_group'),
        'title': data.get('title') or None,
        'subtitle': data.get('subtitle') if data.get('subtitle') != '' else None,
        'note': data.get('note') or None,
        'eyebrow': data.get('eyebrow') or None,
        'caption': data.get('caption') or None,
    }
    canvas = post_background(canvas, params, theme_bg)

    if data.get('match_id'):
        params['match'] = db.session.get(TournamentMatch, int(data['match_id']))
    if data.get('group_id'):
        params['group'] = db.session.get(TournamentGroup, int(data['group_id']))
    if data.get('award_code'):
        params['award'] = TournamentAward.query.filter_by(
            tournament_id=tournament.id, age_group=data.get('age_group') or '',
            code=data['award_code']).first()

    margin = 80 if width >= 1080 else 60
    post_header(canvas, params, margin)
    POST_RENDERERS[template](canvas, params, margin)
    post_footer(canvas, params, margin)
    return canvas


@app.route('/api/tournaments/<int:tournament_id>/post-options')
@login_required
def tournament_post_options_api(tournament_id):
    tournament = db.session.get(Tournament, tournament_id)
    if not tournament:
        return jsonify({'success': False, 'message': 'Турнир не найден'}), 404
    age_groups = tournament_age_group_labels(tournament)
    matches = TournamentMatch.query.filter_by(tournament_id=tournament.id).all()
    groups = TournamentGroup.query.filter_by(tournament_id=tournament.id).order_by(
        TournamentGroup.age_group, TournamentGroup.sort_order).all()

    def match_label(match):
        home = match.home_entry.team.name if match.home_entry and match.home_entry.team else '—'
        away = match.away_entry.team.name if match.away_entry and match.away_entry.team else '—'
        score = f'{match.home_score}:{match.away_score}' if match.is_played else '—:—'
        return f'{home} {score} {away}'

    awards = []
    for age_group in age_groups:
        for row in TournamentAward.query.filter_by(
                tournament_id=tournament.id, age_group=age_group).all():
            if row.member_id or row.entry_id:
                awards.append({'code': row.code, 'age_group': age_group,
                               'title': AWARD_CODES.get(row.code, row.code)})

    return jsonify({
        'success': True,
        'templates': [{'key': key, 'title': title} for key, title in POST_TEMPLATES.items()],
        'formats': [{'key': key, 'title': value[2], 'width': value[0], 'height': value[1]}
                    for key, value in POST_FORMATS.items()],
        'themes': [{'key': key, 'title': value[0]} for key, value in POST_THEMES.items()],
        'fonts': [{'key': key, 'title': value[1]} for key, value in POST_FONTS.items()],
        'accents': POST_ACCENTS,
        'age_groups': age_groups,
        'has_poster': bool(get_tournament_media_url(tournament.poster_path)),
        'matches': [{'id': m.id, 'age_group': m.age_group, 'label': match_label(m),
                     'stage': m.stage} for m in matches
                    if m.home_entry_id and m.away_entry_id],
        'groups': [{'id': g.id, 'age_group': g.age_group, 'name': g.name} for g in groups],
        'awards': awards,
    })


@app.route('/api/tournament-post-background', methods=['POST'])
@login_required
def tournament_post_background_api():
    """Свой фон: сохраняем один раз, дальше рисуем по имени файла."""
    image_file = request.files.get('background')
    if not image_file:
        return jsonify({'success': False, 'message': 'Файл не выбран'}), 400
    extension = detect_upload_image_extension(image_file)
    if not extension:
        return jsonify({'success': False, 'message': 'Поддерживаются PNG, JPG, WEBP'}), 400
    filename = f'post-bg-{uuid.uuid4().hex}.{extension}'
    image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return jsonify({'success': True, 'background_path': filename})


@app.route('/api/tournaments/<int:tournament_id>/post.png', methods=['POST'])
@login_required
def tournament_post_render_api(tournament_id):
    tournament = db.session.get(Tournament, tournament_id)
    if not tournament:
        return jsonify({'success': False, 'message': 'Турнир не найден'}), 404
    data = request.get_json() or {}
    try:
        image = build_post_image(tournament, data)
    except Exception as error:
        return jsonify({'success': False, 'message': f'Не удалось собрать публикацию: {error}'}), 400
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    buffer.seek(0)
    return send_file(buffer, mimetype='image/png', download_name='post.png')


@app.route('/tournaments-afisha/<int:tournament_id>/screen')
def public_tournament_screen_page(tournament_id):
    """Табло для телевизора на стадионе: листает таблицы, сетку и награды."""
    tournament = Tournament.query.filter_by(id=tournament_id, is_published=True).first()
    if not tournament:
        return redirect(url_for('public_tournaments_page'))
    return render_template('public_tournament_screen.html', tournament=tournament)


@app.route('/api/public/tournaments')
def public_tournaments_api():
    ensure_tournament_tables()
    tournaments = Tournament.query.filter(
        Tournament.is_published.is_(True),
        Tournament.start_date.isnot(None),
    ).order_by(Tournament.start_date.desc()).all()

    stadium_by_name = {
        (item.name or '').strip().lower(): item
        for item in TournamentStadium.query.all()
    }

    today = get_local_datetime().date()
    upcoming, past = [], []
    for tournament in tournaments:
        # Турнир считается идущим до конца последнего дня.
        finish = tournament.end_date or tournament.start_date
        payload = public_tournament_payload(tournament, stadium_by_name)
        (upcoming if finish >= today else past).append(payload)

    upcoming.sort(key=lambda item: item['start_date'])
    return jsonify({'success': True, 'upcoming': upcoming, 'past': past})


# ===== ССЫЛКА ДЛЯ ЗАПОЛНЕНИЯ СОСТАВА ТРЕНЕРОМ =====

def tournament_start_moment(tournament):
    """Момент начала турнира — до него тренер может править состав."""
    if not tournament or not tournament.start_date:
        return None
    start_time = tournament.start_time or dt_time(0, 0)
    return datetime.combine(tournament.start_date, start_time)


def tournament_allowed_birth_years(tournament):
    """Годы рождения, разрешённые возрастными группами турнира.

    Считаем только метки-годы («2015», «2015 г.р.»); произвольные вроде «U-12»
    ограничений не задают. Пустой список означает «без ограничений».
    """
    if not tournament:
        return []
    try:
        labels = json.loads(tournament.age_groups or '[]')
    except Exception:
        labels = normalize_age_groups(tournament.age_groups)
    years = set()
    for label in labels or []:
        match = re.fullmatch(r"\s*(\d{4})\s*(?:г\.?\s*р\.?)?\s*", str(label or ''), re.IGNORECASE)
        if match:
            year = int(match.group(1))
            if 1900 <= year <= 2100:
                years.add(year)
    return sorted(years)


def share_link_is_open(link):
    """Ссылка принимает правки, пока не отозвана и турнир не начался."""
    if not link or link.revoked_at:
        return False
    deadline = tournament_start_moment(link.tournament)
    if not deadline:
        return False
    return get_local_datetime() < deadline


def serialize_team_share_link(link):
    deadline = tournament_start_moment(link.tournament)
    return {
        'token': link.token,
        'url': url_for('team_share_form', token=link.token, _external=True),
        'team_id': link.team_id,
        'tournament_id': link.tournament_id,
        'tournament_name': link.tournament.name if link.tournament else None,
        'deadline': deadline.isoformat() if deadline else None,
        'is_open': share_link_is_open(link),
        'revoked': bool(link.revoked_at),
        'created_at': link.created_at.isoformat() if link.created_at else None,
        'last_opened_at': link.last_opened_at.isoformat() if link.last_opened_at else None,
    }


def get_active_share_link(team_id):
    return TournamentTeamShareLink.query.filter_by(
        team_id=team_id,
        revoked_at=None,
    ).order_by(TournamentTeamShareLink.created_at.desc()).first()


@app.route('/api/tournament-team-catalog/<int:team_id>/share', methods=['GET', 'POST', 'DELETE'])
@login_required
def tournament_team_share_api(team_id):
    ensure_tournament_tables()
    team = db.session.get(TournamentTeamCatalog, team_id)
    if not team:
        return jsonify({'success': False, 'message': 'Команда не найдена'}), 404

    if request.method == 'GET':
        if not has_tournament_permission('view'):
            return jsonify({'success': False, 'message': 'Нет доступа'}), 403
        link = get_active_share_link(team_id)
        return jsonify({'success': True, 'link': serialize_team_share_link(link) if link else None})

    if not has_tournament_permission('edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403

    if request.method == 'DELETE':
        link = get_active_share_link(team_id)
        if link:
            link.revoked_at = get_local_datetime()
            db.session.commit()
        return jsonify({'success': True, 'link': None})

    data = request.get_json() or {}
    tournament_id = data.get('tournament_id')
    tournament = db.session.get(Tournament, int(tournament_id)) if tournament_id else None
    if not tournament:
        return jsonify({'success': False, 'message': 'Выберите турнир'}), 400
    if not tournament_start_moment(tournament):
        return jsonify({'success': False, 'message': 'У турнира не заполнена дата начала'}), 400

    # Ссылка на команду одна и не меняется: при смене турнира правим срок,
    # а адрес остаётся прежним, чтобы тренеру не пришлось рассылать новый.
    link = get_active_share_link(team_id)
    if link:
        link.tournament_id = tournament.id
        db.session.commit()
        return jsonify({'success': True, 'link': serialize_team_share_link(link)})

    link = TournamentTeamShareLink(
        team_id=team_id,
        tournament_id=tournament.id,
        token=secrets.token_urlsafe(32),
        created_by=current_user.id,
    )
    db.session.add(link)
    db.session.commit()
    return jsonify({'success': True, 'link': serialize_team_share_link(link)}), 201


def resolve_share_link(token):
    ensure_tournament_tables()
    return TournamentTeamShareLink.query.filter_by(token=token, revoked_at=None).first()


def public_member_payload(member):
    """Публичной форме отдаём только то, что она сама и заполняет."""
    return {
        'id': member.id,
        'last_name': member.last_name,
        'first_name': member.first_name,
        'middle_name': member.middle_name,
        'full_name': member.full_name,
        'birth_date': member.birth_date.isoformat() if member.birth_date else None,
        'team_number': member.team_number,
        'position': member.position,
        'phone_primary': member.phone_primary,
        'photo_url': get_tournament_media_url(member.photo_path),
    }


def share_form_payload(link):
    members = TournamentTeamMember.query.filter_by(team_id=link.team_id).order_by(
        TournamentTeamMember.last_name.asc(),
        TournamentTeamMember.first_name.asc(),
    ).all()
    deadline = tournament_start_moment(link.tournament)
    return {
        'success': True,
        'team': {
            'id': link.team.id,
            'name': link.team.name,
            'logo_url': get_tournament_media_url(link.team.logo_path),
            'trainer_name': link.team.trainer_name,
        },
        'tournament': {
            'name': link.tournament.name if link.tournament else None,
            'location': link.tournament.location if link.tournament else None,
            'start_date': link.tournament.start_date.isoformat()
                if link.tournament and link.tournament.start_date else None,
        },
        'deadline': deadline.isoformat() if deadline else None,
        'editable': share_link_is_open(link),
        'allowed_birth_years': tournament_allowed_birth_years(link.tournament),
        'members': [public_member_payload(member) for member in members],
    }


@app.route('/team-form/<token>')
def team_share_form(token):
    link = resolve_share_link(token)
    if not link:
        return render_template('team_share_form.html', link_valid=False), 404
    link.last_opened_at = get_local_datetime()
    db.session.commit()
    return render_template(
        'team_share_form.html',
        link_valid=True,
        share_token=token,
        player_positions=list(PLAYER_POSITIONS),
    )


@app.route('/api/team-form/<token>')
def team_share_form_api(token):
    link = resolve_share_link(token)
    if not link:
        return jsonify({'success': False, 'message': 'Ссылка недействительна'}), 404
    return jsonify(share_form_payload(link))


def apply_public_member_form(member, allowed_birth_years=()):
    """Упрощённая форма тренера: обязательны только фамилия, имя и дата рождения."""
    member.last_name = (request.form.get('last_name') or '').strip()
    member.first_name = (request.form.get('first_name') or '').strip()
    member.middle_name = (request.form.get('middle_name') or '').strip() or None
    member.birth_date = parse_date_value(request.form.get('birth_date'))
    member.team_number = (request.form.get('team_number') or '').strip() or None
    member.position = normalize_player_position(request.form.get('position'))
    member.phone_primary = (request.form.get('phone_primary') or '').strip() or None
    if not member.last_name or not member.first_name:
        raise ValueError('Укажите фамилию и имя участника')
    if not member.birth_date:
        raise ValueError('Укажите дату рождения в формате дд.мм.гггг')
    if allowed_birth_years and member.birth_date.year not in allowed_birth_years:
        years = ', '.join(str(year) for year in allowed_birth_years)
        raise ValueError(f'Турнир проводится для {years} г.р. — год рождения не подходит')


@app.route('/api/team-form/<token>/members', methods=['POST'])
def team_share_form_add_member(token):
    link = resolve_share_link(token)
    if not link:
        return jsonify({'success': False, 'message': 'Ссылка недействительна'}), 404
    if not share_link_is_open(link):
        return jsonify({'success': False, 'message': 'Турнир уже начался — состав больше не редактируется'}), 403
    member = TournamentTeamMember(team_id=link.team_id, last_name='', first_name='')
    try:
        apply_public_member_form(member, tournament_allowed_birth_years(link.tournament))
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    photo_file = request.files.get('photo')
    if photo_file and photo_file.filename:
        try:
            member.photo_path = save_tournament_catalog_photo(photo_file, 'tournament_member')
        except ValueError as exc:
            return jsonify({'success': False, 'message': str(exc)}), 400
    db.session.add(member)
    db.session.commit()
    return jsonify({'success': True, 'member': public_member_payload(member)}), 201


@app.route('/api/team-form/<token>/members/<int:member_id>', methods=['PUT', 'DELETE'])
def team_share_form_member_detail(token, member_id):
    link = resolve_share_link(token)
    if not link:
        return jsonify({'success': False, 'message': 'Ссылка недействительна'}), 404
    if not share_link_is_open(link):
        return jsonify({'success': False, 'message': 'Турнир уже начался — состав больше не редактируется'}), 403
    member = db.session.get(TournamentTeamMember, member_id)
    # Токен даёт доступ только к своей команде.
    if not member or member.team_id != link.team_id:
        return jsonify({'success': False, 'message': 'Участник не найден'}), 404

    if request.method == 'DELETE':
        photo_path = member.photo_path
        db.session.delete(member)
        db.session.commit()
        delete_tournament_catalog_media(photo_path)
        return jsonify({'success': True})

    try:
        apply_public_member_form(member, tournament_allowed_birth_years(link.tournament))
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(exc)}), 400
    photo_file = request.files.get('photo')
    if photo_file and photo_file.filename:
        try:
            member.photo_path = save_tournament_catalog_photo(
                photo_file, 'tournament_member', member.photo_path,
            )
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(exc)}), 400
    db.session.commit()
    return jsonify({'success': True, 'member': public_member_payload(member)})


@app.route('/api/tournament-stadiums', methods=['GET', 'POST'])
@login_required
def tournament_stadiums_api():
    ensure_tournament_tables()
    if request.method == 'GET':
        if not has_tournament_permission('view'):
            return jsonify({'success': False, 'message': 'Нет доступа'}), 403
        stadiums = TournamentStadium.query.order_by(TournamentStadium.name.asc()).all()
        return jsonify({
            'success': True,
            'stadiums': [serialize_tournament_stadium(stadium) for stadium in stadiums],
        })

    if not has_tournament_permission('edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403
    data = request.form if request.form else (request.get_json() or {})
    name = (data.get('name') or '').strip()
    try:
        latitude = float(data.get('latitude'))
        longitude = float(data.get('longitude'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Выберите локацию стадиона на карте'}), 400
    try:
        stadium_length = parse_optional_stadium_size(data.get('length'), 'Длина')
        stadium_width = parse_optional_stadium_size(data.get('width'), 'Ширина')
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    if not name:
        return jsonify({'success': False, 'message': 'Укажите название стадиона'}), 400
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return jsonify({'success': False, 'message': 'Некорректные координаты стадиона'}), 400
    stadium = TournamentStadium(
        name=name,
        owner_phone=(data.get('owner_phone') or '').strip() or None,
        length=stadium_length,
        width=stadium_width,
        latitude=latitude,
        longitude=longitude,
        created_by=current_user.id,
    )
    if request.files.get('photo'):
        try:
            stadium.photo_path = save_tournament_catalog_photo(
                request.files.get('photo'),
                'tournament_stadium',
            )
        except ValueError as exc:
            return jsonify({'success': False, 'message': str(exc)}), 400
    db.session.add(stadium)
    db.session.commit()
    return jsonify({'success': True, 'stadium': serialize_tournament_stadium(stadium)}), 201


# ===== ИМПОРТ СТАДИОНОВ ИЗ OPENSTREETMAP =====

OSM_USER_AGENT = 'FK Karasu stadium import'

# Основной сервер и зеркало: у Overpass жёсткие лимиты на IP.
OSM_OVERPASS_URLS = (
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
)

# Границы городов, по которым забираем футбольные объекты (юг, запад, север, восток).
OSM_IMPORT_AREAS = {
    'tashkent': ('Ташкент', 41.15, 69.10, 41.42, 69.45),
    'samarkand': ('Самарканд', 39.58, 66.85, 39.72, 67.05),
    'namangan': ('Наманган', 40.94, 71.53, 41.05, 71.72),
    'andijan': ('Андижан', 40.72, 72.24, 40.83, 72.42),
    'fergana': ('Фергана', 40.32, 71.71, 40.43, 71.85),
    'bukhara': ('Бухара', 39.71, 64.36, 39.83, 64.51),
}

# Виды спорта, которые точно не про футбол — такие объекты пропускаем.
OSM_NON_FOOTBALL_SPORTS = {
    'swimming', 'tennis', 'basketball', 'volleyball', 'ice_hockey', 'ice_skating',
    'cycling', 'equestrian', 'climbing', 'chess', 'shooting', 'karting', 'judo',
    'sambo', 'boxing', 'gymnastics', 'athletics', 'fitness', 'gym', 'yoga',
    '10pin', 'baseball', 'skateboard', 'table_tennis', 'handball', 'running',
}


def osm_venue_name(tags):
    for key in ('name:ru', 'name', 'name:uz', 'name:en'):
        value = (tags.get(key) or '').strip()
        if value:
            return value[:200]
    return ''


def osm_is_football_venue(tags):
    """Стадионы берём все, кроме явно нефутбольных; поля и комплексы — только футбольные."""
    leisure = tags.get('leisure')
    sports = {part.strip().lower() for part in (tags.get('sport') or '').split(';') if part.strip()}
    if sports & {'soccer', 'football', 'multi'}:
        return True
    if leisure == 'stadium':
        return not (sports & OSM_NON_FOOTBALL_SPORTS)
    return False


def fetch_osm_football_venues(area_key):
    """Забирает из OpenStreetMap названные футбольные объекты выбранного города."""
    area = OSM_IMPORT_AREAS.get(area_key)
    if not area:
        raise ValueError('Неизвестный город')
    _, south, west, north, east = area
    query = f"""[out:json][timeout:90][bbox:{south},{west},{north},{east}];
(
  way["leisure"="stadium"];
  relation["leisure"="stadium"];
  way["leisure"="pitch"]["sport"~"soccer|football"];
  nwr["leisure"="sports_centre"]["sport"~"soccer|football|multi"];
);
out tags center;"""
    elements = None
    last_status = None
    for url in OSM_OVERPASS_URLS:
        try:
            response = requests.post(
                url,
                data={'data': query},
                timeout=120,
                headers={'User-Agent': OSM_USER_AGENT},
            )
        except requests.RequestException:
            last_status = None
            continue
        last_status = response.status_code
        if response.status_code != 200:
            continue
        try:
            elements = response.json().get('elements', [])
        except ValueError:
            continue
        break

    if elements is None:
        if last_status == 429:
            raise ValueError('OpenStreetMap ограничил частоту запросов. Повторите через минуту')
        if last_status == 504:
            raise ValueError('OpenStreetMap не успел обработать запрос. Повторите попытку')
        raise ValueError('OpenStreetMap недоступен, попробуйте позже')

    venues = []
    for element in elements:
        tags = element.get('tags') or {}
        name = osm_venue_name(tags)
        if not name or not osm_is_football_venue(tags):
            continue
        center = element.get('center') or {}
        latitude = center.get('lat', element.get('lat'))
        longitude = center.get('lon', element.get('lon'))
        if latitude is None or longitude is None:
            continue
        venues.append({
            'name': name,
            'latitude': float(latitude),
            'longitude': float(longitude),
            'wikidata': (tags.get('wikidata') or '').strip() or None,
        })
    return venues


def fetch_wikidata_images(wikidata_ids):
    """Свойство P18 в Wikidata — заглавное фото объекта в Wikimedia Commons."""
    images = {}
    ids = [item for item in wikidata_ids if item]
    for start in range(0, len(ids), 40):
        chunk = ids[start:start + 40]
        try:
            response = requests.get(
                'https://www.wikidata.org/w/api.php',
                params={'action': 'wbgetentities', 'ids': '|'.join(chunk),
                        'props': 'claims', 'format': 'json'},
                timeout=45,
                headers={'User-Agent': OSM_USER_AGENT},
            )
            entities = response.json().get('entities', {})
        except Exception:
            continue
        for qid, entity in entities.items():
            claims = (entity or {}).get('claims', {}).get('P18') or []
            if not claims:
                continue
            try:
                images[qid] = claims[0]['mainsnak']['datavalue']['value']
            except (KeyError, TypeError, IndexError):
                continue
    return images


def fetch_commons_credit(file_name):
    """Автор и лицензия — снимки Commons чаще всего CC BY-SA, их нужно указывать."""
    try:
        response = requests.get(
            'https://commons.wikimedia.org/w/api.php',
            params={'action': 'query', 'titles': f'File:{file_name}',
                    'prop': 'imageinfo', 'iiprop': 'extmetadata', 'format': 'json'},
            timeout=45,
            headers={'User-Agent': OSM_USER_AGENT},
        )
        pages = response.json().get('query', {}).get('pages', {})
    except Exception:
        return 'Wikimedia Commons'
    for page in pages.values():
        info = (page.get('imageinfo') or [{}])[0]
        meta = info.get('extmetadata', {})
        artist = re.sub(r'<[^>]+>', '', meta.get('Artist', {}).get('value', '') or '').strip()
        license_name = (meta.get('LicenseShortName', {}).get('value') or '').strip()
        parts = ['Wikimedia Commons']
        if artist:
            parts.append(artist[:120])
        if license_name:
            parts.append(license_name)
        return ' · '.join(parts)[:300]
    return 'Wikimedia Commons'


def download_commons_photo(file_name):
    """Скачивает фото из Commons и кладёт его как обычное фото стадиона."""
    url = ('https://commons.wikimedia.org/wiki/Special:FilePath/'
           + urllib.parse.quote(file_name.replace(' ', '_')) + '?width=1600')
    try:
        response = requests.get(url, timeout=90, headers={'User-Agent': OSM_USER_AGENT})
    except requests.RequestException:
        return None
    if response.status_code != 200 or not response.content:
        return None

    stream = io.BytesIO(response.content)
    upload = FileStorage(stream=stream, filename=file_name)
    try:
        return save_tournament_catalog_photo(upload, 'tournament_stadium')
    except ValueError:
        return None


def stadium_import_key(name):
    return re.sub(r'[^a-zа-я0-9]+', '', (name or '').lower())


def stadiums_are_close(first_lat, first_lon, second_lat, second_lon, meters=150):
    """Грубая проверка расстояния — для отсечения дублей этого достаточно."""
    lat_delta = (first_lat - second_lat) * 111_320
    lon_delta = (first_lon - second_lon) * 111_320 * math.cos(math.radians(first_lat))
    return (lat_delta ** 2 + lon_delta ** 2) ** 0.5 <= meters


@app.route('/api/tournament-stadiums/import-osm', methods=['POST'])
@login_required
def tournament_stadiums_import_osm():
    ensure_tournament_tables()
    if not has_tournament_permission('edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403

    data = request.get_json() or {}
    area_key = (data.get('area') or 'tashkent').strip().lower()
    try:
        venues = fetch_osm_football_venues(area_key)
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400

    photo_files = fetch_wikidata_images([venue.get('wikidata') for venue in venues])

    existing = TournamentStadium.query.all()
    by_key = {stadium_import_key(item.name): item for item in existing if item.name}
    with_point = [item for item in existing
                  if item.latitude is not None and item.longitude is not None]

    venues.sort(key=lambda item: 0 if photo_files.get(item.get('wikidata')) else 1)

    def attach_photo(stadium, file_name):
        """Скачивает снимок из Commons и прикрепляет к стадиону."""
        time.sleep(0.6)
        photo_path = download_commons_photo(file_name)
        if not photo_path:
            return False
        stadium.photo_path = photo_path
        stadium.photo_source = fetch_commons_credit(file_name)
        return True

    added = 0
    skipped = 0
    with_photo = 0
    enriched = 0
    for venue in venues:
        key = stadium_import_key(venue['name'])
        match = by_key.get(key) if key else None
        if match is None:
            match = next((item for item in with_point
                          if stadiums_are_close(venue['latitude'], venue['longitude'],
                                                item.latitude, item.longitude)), None)

        file_name = photo_files.get(venue.get('wikidata'))
        if match is not None:
            # Стадион уже заведён: не дублируем, но дозаполняем фото, если его нет.
            skipped += 1
            if file_name and not get_tournament_media_url(match.photo_path)                     and attach_photo(match, file_name):
                enriched += 1
            continue

        stadium = TournamentStadium(
            name=venue['name'],
            latitude=venue['latitude'],
            longitude=venue['longitude'],
            created_by=current_user.id,
        )
        if file_name and attach_photo(stadium, file_name):
            with_photo += 1
        db.session.add(stadium)
        by_key[key] = stadium
        with_point.append(stadium)
        added += 1

    if added or enriched:
        db.session.commit()
    return jsonify({
        'success': True,
        'area': OSM_IMPORT_AREAS[area_key][0],
        'found': len(venues),
        'added': added,
        'skipped': skipped,
        'with_photo': with_photo,
        'enriched': enriched,
    })


@app.route('/api/tournament-stadiums/<int:stadium_id>', methods=['PUT', 'DELETE'])
@login_required
def tournament_stadium_detail_api(stadium_id):
    ensure_tournament_tables()
    if not has_tournament_permission('edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403
    stadium = db.session.get(TournamentStadium, stadium_id)
    if not stadium:
        return jsonify({'success': False, 'message': 'Стадион не найден'}), 404
    if request.method == 'DELETE':
        photo_path = stadium.photo_path
        db.session.delete(stadium)
        db.session.commit()
        delete_tournament_catalog_media(photo_path, ('tournament_stadium_',))
        return jsonify({'success': True})
    data = request.form if request.form else (request.get_json() or {})
    name = (data.get('name') or '').strip()
    try:
        latitude = float(data.get('latitude'))
        longitude = float(data.get('longitude'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Выберите локацию стадиона на карте'}), 400
    try:
        stadium_length = parse_optional_stadium_size(data.get('length'), 'Длина')
        stadium_width = parse_optional_stadium_size(data.get('width'), 'Ширина')
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    if not name:
        return jsonify({'success': False, 'message': 'Укажите название стадиона'}), 400
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return jsonify({'success': False, 'message': 'Некорректные координаты стадиона'}), 400
    stadium.name = name
    stadium.owner_phone = (data.get('owner_phone') or '').strip() or None
    stadium.length = stadium_length
    stadium.width = stadium_width
    stadium.latitude = latitude
    stadium.longitude = longitude
    if request.files.get('photo'):
        try:
            stadium.photo_path = save_tournament_catalog_photo(
                request.files.get('photo'),
                'tournament_stadium',
                stadium.photo_path,
            )
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(exc)}), 400
    db.session.commit()
    return jsonify({'success': True, 'stadium': serialize_tournament_stadium(stadium)})


def parse_access_event_time(value):
    if not value:
        return get_local_datetime()
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        try:
            dt = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        except Exception:
            return get_local_datetime()
    if dt.tzinfo:
        return dt.astimezone(TASHKENT_TZ).replace(tzinfo=None)
    return dt


def calculate_attendance_late(student, attendance_date, check_in_dt):
    is_late = False
    late_minutes = 0
    if student.group_id:
        group = db.session.get(Group, student.group_id)
        if group and group.schedule_time:
            schedule_time_str = group.get_schedule_time_for_day(attendance_date.weekday() + 1)
            if schedule_time_str:
                parts = str(schedule_time_str).split(':')
                if len(parts) >= 2:
                    try:
                        schedule_time = dt_time(int(parts[0]), int(parts[1]))
                        scheduled_dt = datetime.combine(attendance_date, schedule_time)
                        diff_minutes = (check_in_dt - scheduled_dt).total_seconds() / 60
                        if diff_minutes > (group.late_threshold or 0):
                            is_late = True
                            late_minutes = int(diff_minutes)
                    except Exception:
                        pass
    return is_late, late_minutes


def create_or_update_attendance_from_access(student, direction, event_dt):
    attendance_date = event_dt.date()
    attendance = Attendance.query.filter_by(student_id=student.id, date=attendance_date).first()
    created = False

    if direction == 'entry':
        if not attendance:
            is_late, late_minutes = calculate_attendance_late(student, attendance_date, event_dt)
            attendance = Attendance(
                student_id=student.id,
                date=attendance_date,
                check_in=event_dt,
                lesson_deducted=not student.club_funded,
                is_late=is_late,
                late_minutes=late_minutes,
            )
            db.session.add(attendance)
            db.session.flush()
            created = True
        elif not attendance.check_in or event_dt < attendance.check_in:
            attendance.check_in = event_dt
    elif direction == 'exit':
        if not attendance:
            attendance = Attendance(
                student_id=student.id,
                date=attendance_date,
                check_in=None,
                check_out=event_dt,
                lesson_deducted=not student.club_funded,
                is_late=False,
                late_minutes=0,
            )
            db.session.add(attendance)
            db.session.flush()
            created = True
        elif not attendance.check_out or event_dt > attendance.check_out:
            attendance.check_out = event_dt

    return attendance, created


def apply_attendance_to_access_log(log):
    if not log or log.person_type == 'staff' or log.result != 'granted':
        return None, False

    student = log.student or (db.session.get(Student, log.student_id) if log.student_id else None)
    if not student:
        employee_no = str(log.employee_no or '').strip()
        if employee_no.isdigit():
            student = db.session.get(Student, int(employee_no))

    if not student:
        return None, False

    event_dt = log.event_time or get_local_datetime()
    attendance, created = create_or_update_attendance_from_access(student, log.direction, event_dt)
    if attendance:
        log.student_id = student.id
        log.attendance_id = attendance.id
        log.person_type = 'student'
        log.full_name = student.full_name
        log.group_id = student.group_id
        log.group_name = student.group.name if student.group else None
    return attendance, created


def find_access_photo_value(value, depth=0):
    if not value or depth > 5:
        return None
    if isinstance(value, str):
        raw = value.strip()
        if raw.startswith('data:image/') or raw.startswith(('http://', 'https://', '/ISAPI/', '/doc/', '/pic/', '/picture/', '/Streaming/')):
            return raw
        if raw.startswith('/9j/') and len(raw) > 200:
            return f"data:image/jpeg;base64,{raw}"
        return None
    if isinstance(value, list):
        for item in value:
            found = find_access_photo_value(item, depth + 1)
            if found:
                return found
        return None
    if not isinstance(value, dict):
        return None

    preferred_keys = [
        'access_photo_data_url', 'access_photo_url', 'pictureURL', 'pictureUrl', 'picUrl', 'picURL',
        'capturePicUrl', 'capturePicURL', 'snapPicUrl', 'snapPicURL', 'facePicUrl', 'facePicURL',
        'imageUrl', 'imageURL', 'photoUrl', 'photoURL', 'pictureData', 'pictureBase64',
        'picData', 'picBase64', 'capturePicData', 'capturePicBase64', 'facePicData',
        'facePicBase64', 'imageData', 'imageBase64', 'picture', 'capturePic', 'facePic', 'pic',
    ]
    for key in preferred_keys:
        if key in value:
            found = find_access_photo_value(value.get(key), depth + 1)
            if found:
                return found
    for item in value.values():
        found = find_access_photo_value(item, depth + 1)
        if found:
            return found
    return None


def access_log_photo_url(log):
    access_photo_url = find_access_photo_value(log.get_raw_event())
    if access_photo_url and not access_photo_url.startswith('data:image/'):
        access_photo_url = None
    return access_photo_url


def access_log_person_photo_url(log):
    if log.person_type == 'student':
        student = log.student or (db.session.get(Student, log.student_id) if log.student_id else None)
        return build_photo_url(student.photo_path) if student else None
    if log.person_type == 'staff':
        user_id = parse_staff_user_id(log.employee_no)
        user = db.session.get(User, user_id) if user_id else None
        return build_user_photo_thumb_url(user.photo_path) if user else None
    return None


def access_log_to_dict(log, photo_available=None):
    if photo_available is None:
        photo_available = bool(access_log_photo_url(log))
    access_photo_url = url_for('access_log_photo_file', log_id=log.id) if photo_available and log.id else None
    access_photo_thumb_url = (
        url_for('access_log_photo_file', log_id=log.id, thumb=1)
        if photo_available and log.id else None
    )
    person_photo_url = access_log_person_photo_url(log)
    identified_student = log.identified_student if log.identified_student_id else None
    return {
        'id': log.id,
        'event_uid': log.event_uid,
        'student_id': log.student_id,
        'attendance_id': log.attendance_id,
        'person_type': log.person_type,
        'employee_no': log.employee_no,
        'full_name': log.full_name,
        'group_name': log.group_name,
        'direction': log.direction,
        'device_name': log.device_name,
        'device_ip': log.device_ip,
        'event_time': log.event_time.isoformat() if log.event_time else None,
        'event_date': log.event_date.isoformat() if log.event_date else None,
        'result': log.result,
        'source': log.source,
        'access_photo_url': access_photo_url,
        'access_photo_thumb_url': access_photo_thumb_url,
        'person_photo_url': person_photo_url,
        'identified_student_id': log.identified_student_id,
        'identified_full_name': log.identified_full_name,
        'identified_employee_no': log.identified_employee_no,
        'identified_group_name': log.identified_group_name,
        'identified_photo_url': build_photo_url(identified_student.photo_path) if identified_student else None,
        'identified_similarity': round(max(0.0, min(1.0, float(log.identified_similarity))) * 100, 1) if log.identified_similarity is not None else None,
        'identified_tentative': bool(
            log.identified_student_id
            and log.identified_similarity is not None
            and float(log.identified_similarity) < access_face_verifier.confirm_threshold
        ),
        'face_identified_at': log.face_identified_at.isoformat() if log.face_identified_at else None,
        'face_identification_version': log.face_identification_version,
        'face_verification_status': log.face_verification_status,
        'face_similarity': round(max(0.0, min(1.0, float(log.face_similarity))) * 100, 1) if log.face_similarity is not None else None,
        'face_verification_reason': log.face_verification_reason,
        'face_verified_at': log.face_verified_at.isoformat() if log.face_verified_at else None,
    }


def access_log_status_to_dict(log):
    return {
        'id': log.id,
        'person_type': log.person_type,
        'full_name': log.full_name,
        'identified_student_id': log.identified_student_id,
        'identified_full_name': log.identified_full_name,
        'identified_employee_no': log.identified_employee_no,
        'identified_group_name': log.identified_group_name,
        'identified_similarity': round(max(0.0, min(1.0, float(log.identified_similarity))) * 100, 1) if log.identified_similarity is not None else None,
        'identified_tentative': bool(
            log.identified_student_id
            and log.identified_similarity is not None
            and float(log.identified_similarity) < access_face_verifier.confirm_threshold
        ),
        'face_identified_at': log.face_identified_at.isoformat() if log.face_identified_at else None,
        'face_verification_status': log.face_verification_status,
        'face_similarity': round(max(0.0, min(1.0, float(log.face_similarity))) * 100, 1) if log.face_similarity is not None else None,
        'face_verification_reason': log.face_verification_reason,
        'face_verified_at': log.face_verified_at.isoformat() if log.face_verified_at else None,
    }


def merge_access_photo_payload(log, data):
    if not log or not isinstance(data, dict):
        return False

    raw_event = log.get_raw_event()
    changed = False
    incoming_raw = data.get('raw_event') if isinstance(data.get('raw_event'), dict) else {}
    for key in (
        'access_photo_data_url', 'access_photo_url', 'access_photo_error',
        'pictureData', 'pictureBase64', 'picData', 'picBase64',
        'capturePicData', 'capturePicBase64', 'facePicData', 'facePicBase64',
        'imageData', 'imageBase64', 'pictureURL', 'pictureUrl',
    ):
        value = data.get(key) or incoming_raw.get(key)
        if value and raw_event.get(key) != value:
            raw_event[key] = value
            changed = True

    if changed:
        log.set_raw_event(raw_event)
    return changed


def resolve_student_photo_path(photo_path):
    if not photo_path:
        return None
    normalized = str(photo_path).replace('\\', '/').lstrip('/')
    candidates = []
    if os.path.isabs(str(photo_path)):
        candidates.append(str(photo_path))
    candidates.append(os.path.join(basedir, normalized))
    static_relative = normalized
    for prefix in ('frontend/static/', 'frontend/', 'static/'):
        if static_relative.startswith(prefix):
            static_relative = static_relative[len(prefix):]
            break
    candidates.append(os.path.join(app.static_folder, static_relative))
    return next((path for path in candidates if os.path.isfile(path)), None)


def stored_student_face_embedding(student):
    try:
        embedding = student.get_face_encoding()
        if embedding is not None and len(embedding) == 512:
            return embedding
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return None


def build_access_face_candidates():
    students = Student.query.filter(
        Student.photo_path.isnot(None),
        Student.photo_path != '',
    ).all()
    group_ids = {item.group_id for item in students if item.group_id}
    group_names = {
        item.id: item.name for item in Group.query.filter(Group.id.in_(group_ids)).all()
    } if group_ids else {}
    candidates = [{
        'id': item.id,
        'full_name': item.full_name,
        'employee_no': str(item.id),
        'group_name': group_names.get(item.group_id),
        'photo_path': resolve_student_photo_path(item.photo_path),
        'embedding': stored_student_face_embedding(item),
    } for item in students]
    return students, candidates


def persist_computed_face_embeddings(students, candidates):
    students_by_id = {item.id: item for item in students}
    changed = False
    for candidate in candidates:
        computed = candidate.get('computed_embedding')
        target = students_by_id.get(candidate.get('id'))
        if computed is not None and target is not None:
            target.set_face_encoding(np.asarray(computed, dtype=np.float32))
            changed = True
    if changed:
        db.session.commit()


def prewarm_access_face_index():
    """Load the model/index in background so the first terminal event does not pay cold-start cost."""
    try:
        with app.app_context():
            students, candidates = build_access_face_candidates()
            access_face_verifier.prepare_candidate_index(candidates)
            persist_computed_face_embeddings(students, candidates)
            print(f'✅ Индекс распознавания лиц подготовлен: {len(candidates)} учеников')
    except Exception as exc:
        print(f'⚠️ Предварительная загрузка распознавания не выполнена: {type(exc).__name__}: {exc}')


def start_access_face_index_prewarm():
    global access_face_index_prewarm_started
    if os.environ.get('FACE_VERIFY_PREWARM', '1').strip().lower() in {'0', 'false', 'no'}:
        return
    with access_face_verify_lock:
        if access_face_index_prewarm_started:
            return
        access_face_index_prewarm_started = True
    threading.Thread(
        target=prewarm_access_face_index,
        daemon=True,
        name='access-face-index-prewarm',
    ).start()


def run_access_face_verify_worker():
    while True:
        log_id = access_face_verify_queue.get()
        try:
            with app.app_context():
                log = db.session.get(AccessLog, log_id)
                if not log or (log.face_identified_at and log.face_identification_version == ACCESS_FACE_IDENTIFICATION_VERSION):
                    continue
                stale_before = get_local_datetime() - timedelta(minutes=10)
                if (
                    log.face_verification_status == 'processing'
                    and log.face_verified_at
                    and log.face_verified_at > stale_before
                ):
                    continue
                log.face_verification_status = 'processing'
                log.face_verification_reason = 'Сервер индексирует и сравнивает лица'
                log.face_verified_at = get_local_datetime()
                log.identified_student_id = None
                log.identified_full_name = None
                log.identified_employee_no = None
                log.identified_group_name = None
                log.identified_similarity = None
                log.face_identified_at = None
                db.session.commit()
                if log.person_type != 'student' or not log.student_id:
                    log.face_verification_status = 'not_applicable'
                    log.face_verification_reason = 'Проверка выполняется только для учеников'
                    log.face_verified_at = get_local_datetime()
                    log.face_identified_at = get_local_datetime()
                    log.face_identification_version = ACCESS_FACE_IDENTIFICATION_VERSION
                    db.session.commit()
                    continue

                students, candidates = build_access_face_candidates()
                result = access_face_verifier.identify_and_verify(
                    access_log_photo_url(log), candidates, log.student_id,
                )
                log.face_verification_status = result.get('status') or 'unavailable'
                log.face_similarity = result.get('similarity')
                log.face_verification_reason = str(result.get('reason') or '')[:300] or None
                log.face_verified_at = get_local_datetime()
                identified = result.get('identified') or {}
                log.identified_student_id = identified.get('id')
                log.identified_full_name = identified.get('full_name')
                log.identified_employee_no = identified.get('employee_no')
                log.identified_group_name = identified.get('group_name')
                log.identified_similarity = result.get('identified_similarity')
                log.face_identified_at = get_local_datetime()
                log.face_identification_version = ACCESS_FACE_IDENTIFICATION_VERSION
                db.session.commit()
                persist_computed_face_embeddings(students, candidates)
        except Exception as exc:
            print(f'Access face verification failed for log {log_id}: {type(exc).__name__}: {exc}')
            try:
                with app.app_context():
                    failed_log = db.session.get(AccessLog, log_id)
                    if failed_log and not failed_log.face_identified_at:
                        failed_log.face_verification_status = 'unavailable'
                        failed_log.face_verification_reason = f'Ошибка серверной сверки: {type(exc).__name__}'[:300]
                        failed_log.face_verified_at = get_local_datetime()
                        failed_log.face_identified_at = get_local_datetime()
                        failed_log.face_identification_version = ACCESS_FACE_IDENTIFICATION_VERSION
                        db.session.commit()
            except Exception as save_exc:
                print(f'Could not save face verification error for log {log_id}: {save_exc}')
        finally:
            with access_face_verify_lock:
                access_face_verify_queued.discard(log_id)
            access_face_verify_queue.task_done()


def schedule_access_face_verification(log_id):
    global access_face_verify_worker_started
    if not log_id:
        return
    with access_face_verify_lock:
        if log_id in access_face_verify_queued:
            return
        access_face_verify_queued.add(log_id)
        if not access_face_verify_worker_started:
            try:
                worker_count = int(os.environ.get('FACE_VERIFY_WORKERS', '2') or 2)
            except (TypeError, ValueError):
                worker_count = 2
            worker_count = min(4, max(1, worker_count))
            for worker_index in range(worker_count):
                threading.Thread(
                    target=run_access_face_verify_worker,
                    daemon=True,
                    name=f'access-face-verifier-{worker_index + 1}',
                ).start()
            access_face_verify_worker_started = True
    access_face_verify_queue.put(log_id)


def staff_employee_no(user_id):
    return f"900000{user_id}"


def parse_staff_user_id(employee_no):
    raw = str(employee_no or '').strip()
    if raw.startswith('900000') and raw[6:].isdigit():
        return int(raw[6:])
    return None


def format_minutes(minutes):
    if not minutes or minutes <= 0:
        return ''
    hours = minutes // 60
    rest = minutes % 60
    if hours and rest:
        return f"{hours} ч {rest} мин"
    if hours:
        return f"{hours} ч"
    return f"{rest} мин"


def user_role_name(user):
    return user.role_obj.name if getattr(user, 'role_obj', None) else user.role


def is_trainer_role(user):
    return user_role_name(user) in TRAINER_ROLE_NAMES


def is_guest_role(user):
    return user_role_name(user) in STAFF_EXCLUDED_ROLE_NAMES


def is_guest_role_id(role_id):
    if not role_id:
        return False
    role = db.session.get(Role, int(role_id))
    return bool(role and role.name in STAFF_EXCLUDED_ROLE_NAMES)


def is_trainer_role_id(role_id):
    if not role_id:
        return False
    role = db.session.get(Role, int(role_id))
    return bool(role and role.name in TRAINER_ROLE_NAMES)


def parse_int_list_payload(data, key):
    if hasattr(data, 'getlist'):
        raw_values = data.getlist(key)
        if not raw_values and data.get(key):
            raw_values = [data.get(key)]
    else:
        raw_values = data.get(key, []) if isinstance(data, dict) else []

    if raw_values in (None, ''):
        return []
    if isinstance(raw_values, str):
        try:
            decoded = json.loads(raw_values)
            raw_values = decoded if isinstance(decoded, list) else raw_values.split(',')
        except Exception:
            raw_values = raw_values.split(',')
    if not isinstance(raw_values, (list, tuple, set)):
        raw_values = [raw_values]

    ids = []
    for value in raw_values:
        try:
            parsed = int(value)
            if parsed > 0 and parsed not in ids:
                ids.append(parsed)
        except (TypeError, ValueError):
            continue
    return ids


def serialize_group_trainer_link(link):
    user = link.user
    if not user:
        return None
    display_name = user.full_name or user.username
    initials = ''.join(part[:1] for part in display_name.split()[:2]).upper() or 'T'
    return {
        'id': user.id,
        'username': user.username,
        'full_name': display_name,
        'role': link.role,
        'photo_url': build_user_photo_thumb_url(user.photo_path),
        'initials': initials
    }


def group_trainer_payload(group):
    links = sorted(group.trainer_links, key=lambda link: ((link.role != 'primary'), (link.user.full_name or link.user.username) if link.user else ''))
    primary = [serialize_group_trainer_link(link) for link in links if link.role == 'primary']
    assistants = [serialize_group_trainer_link(link) for link in links if link.role == 'assistant']
    primary = [item for item in primary if item]
    assistants = [item for item in assistants if item]
    return {
        'trainers': primary,
        'assistants': assistants,
        'trainer_ids': [item['id'] for item in primary],
        'assistant_ids': [item['id'] for item in assistants]
    }


def sync_group_trainers(group_id, trainer_ids=None, assistant_ids=None):
    ensure_group_trainers_table()
    trainer_ids = trainer_ids or []
    assistant_ids = [user_id for user_id in (assistant_ids or []) if user_id not in trainer_ids]

    GroupTrainer.query.filter_by(group_id=group_id).delete()
    for user_id in trainer_ids:
        db.session.add(GroupTrainer(group_id=group_id, user_id=user_id, role='primary'))
    for user_id in assistant_ids:
        db.session.add(GroupTrainer(group_id=group_id, user_id=user_id, role='assistant'))


def sync_user_primary_trainer_groups(user, group_ids):
    ensure_group_trainers_table()
    GroupTrainer.query.filter_by(user_id=user.id, role='primary').delete()
    if is_trainer_role_id(user.role_id) or user.role in TRAINER_ROLE_NAMES:
        for group_id in group_ids:
            existing = GroupTrainer.query.filter_by(group_id=group_id, user_id=user.id).first()
            if existing:
                existing.role = 'primary'
            else:
                db.session.add(GroupTrainer(group_id=group_id, user_id=user.id, role='primary'))


def clear_user_trainer_groups(user):
    ensure_group_trainers_table()
    GroupTrainer.query.filter_by(user_id=user.id).delete()


@app.route('/api/staff-timesheet', methods=['GET'])
@login_required
def staff_timesheet_data():
    if not current_user.has_permission('attendance', 'view'):
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    ensure_users_table_columns()
    ensure_group_trainers_table()
    ensure_access_logs_table()
    ensure_expense_columns()

    today = get_local_date()
    year = request.args.get('year', default=today.year, type=int) or today.year
    month = request.args.get('month', default=today.month, type=int) or today.month
    search = (request.args.get('search') or '').strip().lower()
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        return jsonify({'success': False, 'message': 'Некорректный период'}), 400

    _, days_in_month = calendar.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, days_in_month)
    start_dt = datetime.combine(start_date, dt_time.min)
    end_dt = datetime.combine(end_date + timedelta(days=1), dt_time.min)

    users = [
        user for user in User.query.order_by(User.full_name.asc(), User.username.asc()).all()
        if not is_guest_role(user)
    ]
    if search:
        users = [
            user for user in users
            if search in (user.full_name or '').lower() or search in (user.username or '').lower()
        ]
    user_by_id = {user.id: user for user in users}
    employee_nos = {staff_employee_no(user.id) for user in users}

    logs = AccessLog.query.filter(
        AccessLog.event_time >= start_dt,
        AccessLog.event_time < end_dt,
        AccessLog.result == 'granted',
        db.or_(
            AccessLog.person_type == 'staff',
            AccessLog.employee_no.in_(employee_nos)
        )
    ).order_by(AccessLog.event_time.asc()).all()

    day_map = {user.id: {day: {'entries': [], 'exits': [], 'all': []} for day in range(1, days_in_month + 1)} for user in users}
    for log in logs:
        user_id = parse_staff_user_id(log.employee_no)
        if user_id not in user_by_id or str(log.employee_no) not in employee_nos:
            continue
        day = log.event_date.day if log.event_date else log.event_time.day
        if day < 1 or day > days_in_month:
            continue
        bucket = day_map[user_id][day]
        bucket['all'].append(log.event_time)
        if log.direction == 'exit':
            bucket['exits'].append(log.event_time)
        else:
            bucket['entries'].append(log.event_time)

    salary_rows = Expense.query.filter(
        Expense.category == 'Зарплата',
        Expense.salary_year == year,
        Expense.salary_month == month,
        Expense.employee_id.isnot(None)
    ).all()
    paid_map = {}
    for expense in salary_rows:
        paid_map[expense.employee_id] = paid_map.get(expense.employee_id, 0) + float(expense.amount or 0)

    days_meta = []
    weekday_labels = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    for day in range(1, days_in_month + 1):
        current = date(year, month, day)
        days_meta.append({
            'day': day,
            'weekday': weekday_labels[current.weekday()],
            'weekend': current.weekday() >= 5
        })

    rows = []
    for index, user in enumerate(users, start=1):
        total_minutes = 0
        cells = []
        for day in range(1, days_in_month + 1):
            bucket = day_map[user.id][day]
            entry_time = min(bucket['entries']) if bucket['entries'] else None
            exit_time = max(bucket['exits']) if bucket['exits'] else None
            single_time = None
            minutes = 0
            if entry_time and exit_time and exit_time > entry_time:
                minutes = int((exit_time - entry_time).total_seconds() // 60)
                total_minutes += minutes
            elif bucket['all']:
                single_time = min(bucket['all'])

            cells.append({
                'day': day,
                'entry': entry_time.strftime('%H:%M') if entry_time else '',
                'exit': exit_time.strftime('%H:%M') if exit_time else '',
                'single': single_time.strftime('%H:%M') if single_time and not (entry_time or exit_time) else '',
                'minutes': minutes,
                'hours_label': format_minutes(minutes),
                'has_data': bool(bucket['all'])
            })

        salary_paid = paid_map.get(user.id, 0)
        rows.append({
            'index': index,
            'id': user.id,
            'employee_no': staff_employee_no(user.id),
            'full_name': user.full_name or user.username,
            'username': user.username,
            'role': user_role_name(user),
            'photo_url': build_user_photo_thumb_url(user.photo_path),
            'salary_type': getattr(user, 'salary_type', 'fixed') or 'fixed',
            'fixed_salary': float(user.fixed_salary or 0) if getattr(user, 'fixed_salary', None) is not None else None,
            'salary_paid': salary_paid,
            'salary_paid_label': f"{salary_paid:,.0f}".replace(',', ' ') + ' сум' if salary_paid else 'Не получил',
            'total_minutes': total_minutes,
            'total_hours_label': format_minutes(total_minutes) or '0 мин',
            'days': cells
        })

    return jsonify({
        'success': True,
        'year': year,
        'month': month,
        'days': days_meta,
        'rows': rows
    })


@app.route('/api/access-log', methods=['GET'])
@login_required
def access_log_list():
    if not current_user.has_permission('attendance', 'view'):
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    ensure_access_logs_table()
    query = AccessLog.query
    selected_date = request.args.get('date')
    start_date = request.args.get('start_date') or selected_date
    end_date = request.args.get('end_date') or selected_date
    direction = (request.args.get('direction') or '').strip()
    result_filter = (request.args.get('result') or '').strip()
    face_status_filter = (request.args.get('face_status') or '').strip()
    search = (request.args.get('search') or '').strip()
    page = max(1, request.args.get('page', default=1, type=int) or 1)
    per_page = request.args.get('per_page', default=50, type=int) or 50
    per_page = min(100, max(10, per_page))

    if start_date or end_date:
        try:
            if start_date:
                query = query.filter(AccessLog.event_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
            if end_date:
                query = query.filter(AccessLog.event_date <= datetime.strptime(end_date, '%Y-%m-%d').date())
        except ValueError:
            return jsonify({'success': False, 'message': 'Некорректный период'}), 400
    if direction in {'entry', 'exit'}:
        query = query.filter(AccessLog.direction == direction)
    if result_filter in {'granted', 'denied', 'error'}:
        query = query.filter(AccessLog.result == result_filter)
    if face_status_filter in {'confirmed', 'suspicious', 'mismatch', 'unavailable'}:
        query = query.filter(AccessLog.face_verification_status == face_status_filter)
    elif face_status_filter == 'pending':
        query = query.filter(or_(
            AccessLog.face_verification_status.is_(None),
            AccessLog.face_verification_status.in_(['pending', 'processing']),
        ))
    if search:
        like = f"%{search}%"
        query = query.filter(or_(
            AccessLog.full_name.ilike(like),
            AccessLog.employee_no.ilike(like),
            AccessLog.group_name.ilike(like),
            AccessLog.identified_full_name.ilike(like),
            AccessLog.identified_employee_no.ilike(like),
            AccessLog.identified_group_name.ilike(like),
        ))

    total = query.count()
    pages = max(1, (total + per_page - 1) // per_page)
    if page > pages:
        page = pages

    logs = query.options(
        joinedload(AccessLog.student),
        joinedload(AccessLog.identified_student),
        defer(AccessLog.raw_event),
    ).order_by(AccessLog.event_time.desc())\
        .offset((page - 1) * per_page)\
        .limit(per_page)\
        .all()

    repaired = False
    for log in logs:
        if log.person_type != 'staff' and not log.attendance_id and log.result == 'granted':
            attendance, _ = apply_attendance_to_access_log(log)
            if attendance:
                repaired = True
    if repaired:
        db.session.commit()

    for log in logs:
        if log.person_type == 'student' and log.face_identification_version != ACCESS_FACE_IDENTIFICATION_VERSION:
            if log.face_verification_status != 'processing':
                log.face_verification_status = 'pending'
            schedule_access_face_verification(log.id)

    log_ids = [log.id for log in logs]
    photo_log_ids = set()
    if log_ids:
        photo_log_ids = {
            log_id for (log_id,) in db.session.query(AccessLog.id).filter(
                AccessLog.id.in_(log_ids),
                or_(
                    AccessLog.raw_event.ilike('%data:image/%'),
                    AccessLog.raw_event.ilike('%/9j/%'),
                ),
            ).all()
        }

    return jsonify({
        'success': True,
        'logs': [access_log_to_dict(log, log.id in photo_log_ids) for log in logs],
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': pages,
        }
    })


@app.route('/api/access-log/<int:log_id>/photo', methods=['GET'])
@login_required
def access_log_photo_file(log_id):
    if not current_user.has_permission('attendance', 'view'):
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    log = db.session.get(AccessLog, log_id)
    if not log:
        return '', 404
    data_url = access_log_photo_url(log)
    if not data_url or ',' not in data_url:
        return '', 404
    try:
        header, encoded = data_url.split(',', 1)
        mime_type = header[5:].split(';', 1)[0].lower()
        if mime_type not in {'image/jpeg', 'image/png', 'image/webp'}:
            return '', 415
        image_bytes = base64.b64decode(encoded, validate=False)
        if not image_bytes or len(image_bytes) > 700_000:
            return '', 404
    except Exception:
        return '', 404

    if request.args.get('thumb') == '1':
        try:
            cache_key = hashlib.sha1(image_bytes).hexdigest()[:24]
            cache_dir = os.path.join(app.config['UPLOAD_FOLDER'], '.thumb_cache')
            cache_path = os.path.join(cache_dir, f'access_{log_id}_{cache_key}.jpg')
            if not os.path.isfile(cache_path):
                with photo_thumbnail_lock:
                    if not os.path.isfile(cache_path):
                        os.makedirs(cache_dir, exist_ok=True)
                        with Image.open(io.BytesIO(image_bytes)) as image:
                            image = ImageOps.exif_transpose(image).convert('RGB')
                            image = ImageOps.fit(
                                image,
                                (160, 160),
                                method=Image.Resampling.LANCZOS,
                                centering=(0.5, 0.38),
                            )
                            image.save(cache_path, 'JPEG', quality=75, optimize=True, progressive=True)
            response = send_file(cache_path, mimetype='image/jpeg', conditional=True, max_age=2592000)
            response.cache_control.public = False
            response.cache_control.private = True
            return response
        except Exception:
            return '', 404

    response = Response(image_bytes, mimetype=mime_type)
    response.cache_control.private = True
    response.cache_control.max_age = 300
    return response


@app.route('/api/access-log/status', methods=['GET'])
@login_required
def access_log_statuses():
    """Return only mutable face-check fields for rows currently visible in the journal."""
    if not current_user.has_permission('attendance', 'view'):
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    raw_ids = (request.args.get('ids') or '').split(',')
    log_ids = []
    for value in raw_ids[:100]:
        try:
            log_id = int(value)
        except (TypeError, ValueError):
            continue
        if log_id > 0:
            log_ids.append(log_id)
    if not log_ids:
        return jsonify({'success': True, 'logs': []})
    logs = AccessLog.query.filter(AccessLog.id.in_(set(log_ids))).all()
    return jsonify({'success': True, 'logs': [access_log_status_to_dict(log) for log in logs]})


@app.route('/api/hikvision/access-event', methods=['POST'])
def hikvision_access_event():
    """Прием события прохода от локального bridge."""
    if not check_bridge_auth():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    ensure_access_logs_table()
    data = request.get_json(silent=True) or {}
    event_uid = str(data.get('event_uid') or data.get('event_id') or '').strip()[:160] or None
    if event_uid:
        existing = AccessLog.query.filter_by(event_uid=event_uid).first()
        if existing:
            attendance_created = False
            attendance = existing.attendance
            raw_updated = merge_access_photo_payload(existing, data)
            if raw_updated and existing.person_type == 'student':
                existing.face_verification_status = 'pending'
                existing.face_similarity = None
                existing.face_verification_reason = None
                existing.face_verified_at = None
                existing.identified_student_id = None
                existing.identified_full_name = None
                existing.identified_employee_no = None
                existing.identified_group_name = None
                existing.identified_similarity = None
                existing.face_identified_at = None
                existing.face_identification_version = None
            if existing.person_type != 'staff' and not existing.attendance_id and existing.result == 'granted':
                attendance, attendance_created = apply_attendance_to_access_log(existing)
                if attendance:
                    raw_updated = True
            if raw_updated:
                db.session.commit()
            if existing.person_type == 'student' and not existing.face_identified_at:
                schedule_access_face_verification(existing.id)
            return jsonify({
                'success': True,
                'duplicate': True,
                'raw_event_updated': raw_updated,
                'log': access_log_to_dict(existing),
                'attendance_created': attendance_created,
                'attendance_id': attendance.id if attendance else None,
            })

    employee_no = str(data.get('employee_no') or data.get('employeeNo') or data.get('employeeNoString') or '').strip()
    direction = (data.get('direction') or data.get('device_name') or '').strip().lower()
    direction = 'exit' if direction in {'exit', 'выход', 'out'} else 'entry'
    result_value = str(data.get('result') or 'granted').strip().lower()
    result_value = result_value if result_value in {'granted', 'denied', 'error'} else 'granted'
    event_dt = parse_access_event_time(data.get('event_time') or data.get('time'))

    person_type = 'unknown'
    student = None
    full_name = (data.get('full_name') or data.get('name') or '').strip()[:200]
    group_id = None
    group_name = None
    attendance = None
    attendance_created = False

    if employee_no.startswith('900000'):
        person_type = 'staff'
    elif employee_no.isdigit():
        student = db.session.get(Student, int(employee_no))
        if student:
            person_type = 'student'
            full_name = student.full_name
            group_id = student.group_id
            group_name = student.group.name if student.group else None
            if result_value == 'granted':
                attendance, attendance_created = create_or_update_attendance_from_access(student, direction, event_dt)

    log = AccessLog(
        event_uid=event_uid,
        student_id=student.id if student else None,
        attendance_id=attendance.id if attendance else None,
        person_type=person_type,
        employee_no=employee_no[:40] if employee_no else None,
        full_name=full_name or None,
        group_id=group_id,
        group_name=group_name,
        direction=direction,
        device_name=str(data.get('device_name') or data.get('device') or '')[:80],
        device_ip=str(data.get('device_ip') or '')[:80],
        event_time=event_dt,
        event_date=event_dt.date(),
        result=result_value,
        source=str(data.get('source') or 'hikvision')[:40],
        face_verification_status='pending' if student else 'not_applicable',
    )
    raw_event = data.get('raw_event') if isinstance(data.get('raw_event'), dict) else {}
    stored_event = {**raw_event}
    for key in ('access_photo_data_url', 'access_photo_url', 'access_photo_error'):
        if data.get(key):
            stored_event[key] = data.get(key)
    log.set_raw_event(stored_event or data)
    db.session.add(log)
    if attendance and not log.attendance_id:
        db.session.flush()
        log.attendance_id = attendance.id
    db.session.commit()
    if student:
        schedule_access_face_verification(log.id)

    return jsonify({
        'success': True,
        'log': access_log_to_dict(log),
        'attendance_created': attendance_created,
        'attendance_id': attendance.id if attendance else None,
    })


@app.route('/api/attendance/checkin', methods=['POST'])
def attendance_checkin():
    """Отметить вход ученика (вызывается из камеры)"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        
        student = Student.query.get_or_404(student_id)
        today = get_local_date()
        now = get_local_datetime()
        
        # Проверить, был ли уже чекин сегодня
        existing = Attendance.query.filter_by(
            student_id=student_id,
            date=today
        ).first()
        
        if existing:
            return jsonify({'success': False, 'message': 'Уже отмечен сегодня'})
        
        # Проверка баланса: пропускаем даже при нуле/минусе, админ решает
        current_balance = calculate_student_balance(student)
        low_balance = (not student.club_funded and current_balance <= 0)
        
        # Определить опоздание
        is_late = False
        late_minutes = 0
        
        if student.group_id:
            group = db.session.get(Group, student.group_id)
            if group and group.schedule_time:
                # Получить время для сегодняшнего дня недели
                weekday = today.weekday()
                schedule_time_str = group.get_schedule_time_for_day(weekday)
                
                if schedule_time_str:
                    # Парсим время из строки HH:MM
                    time_parts = schedule_time_str.split(':')
                    if len(time_parts) == 2:
                        schedule_time = dt_time(int(time_parts[0]), int(time_parts[1]))
                        scheduled_time = datetime.combine(today, schedule_time)
                        time_diff = (now - scheduled_time).total_seconds() / 60
                        
                        if time_diff > group.late_threshold:
                            is_late = True
                            late_minutes = int(time_diff)
        
        # Создать запись посещения
        attendance = Attendance(
            student_id=student_id,
            date=today,
            lesson_deducted=not student.club_funded,
            is_late=is_late,
            late_minutes=late_minutes
        )
        db.session.add(attendance)
        
        # Баланс теперь рассчитывается динамически (оплачено занятий - посещено)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'student_name': student.full_name,
            'remaining_balance': calculate_student_balance(student),
            'is_late': is_late,
            'late_minutes': late_minutes,
            'club_funded': student.club_funded,
            'low_balance': low_balance
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/attendance/manual-checkin', methods=['POST'])
@login_required
def manual_checkin():
    """Ручная фиксация посещения ученика (если камера сломалась)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Нет данных в запросе'}), 400
            
        student_id = data.get('student_id')
        year = data.get('year')
        month = data.get('month')
        day = data.get('day')
        
        # Валидация параметров
        if not student_id:
            return jsonify({'success': False, 'message': 'Не указан ID ученика'}), 400
        if not year or not month or not day:
            return jsonify({'success': False, 'message': 'Не указана дата (год, месяц, день)'}), 400
        
        try:
            student_id = int(student_id)
            year = int(year)
            month = int(month)
            day = int(day)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'Некорректные параметры (должны быть числа)'}), 400
        
        student = Student.query.get_or_404(student_id)
        
        # Создать дату из параметров с валидацией
        try:
            attendance_date = date(year, month, day)
            print(f"📅 Manual checkin: student_id={student_id}, year={year}, month={month}, day={day} => attendance_date={attendance_date}")
        except ValueError as ve:
            return jsonify({'success': False, 'message': f'Некорректная дата: {str(ve)}'}), 400
            
        now = get_local_datetime()
        
        # Проверить, была ли уже фиксация в этот день
        existing = Attendance.query.filter_by(
            student_id=student_id,
            date=attendance_date
        ).first()
        
        if existing:
            return jsonify({'success': False, 'message': 'Уже отмечен в этот день'})
        
        # Определить опоздание (сравниваем с временем начала занятия в указанный день)
        is_late = False
        late_minutes = 0
        
        if student.group_id:
            group = db.session.get(Group, student.group_id)
            if group and group.schedule_time:
                # Получить время для конкретного дня недели (для JSON) или одно время
                weekday = attendance_date.weekday()
                schedule_time_str = group.get_schedule_time_for_day(weekday)
                
                if schedule_time_str:
                    # Парсим время из строки HH:MM
                    time_parts = schedule_time_str.split(':')
                    if len(time_parts) == 2:
                        schedule_time = dt_time(int(time_parts[0]), int(time_parts[1]))
                        
                        # Время начала занятия в указанный день
                        scheduled_time = datetime.combine(attendance_date, schedule_time)
                        # Текущее время для сравнения
                        current_time = now
                        
                        # Если это прошедший день, считаем что опоздание уже не актуально
                        # Но если это сегодня или будущий день, проверяем опоздание
                        if attendance_date <= get_local_date():
                            time_diff = (current_time - scheduled_time).total_seconds() / 60
                            
                            if time_diff > group.late_threshold:
                                is_late = True
                                late_minutes = int(time_diff)
        
        # Создать запись посещения
        attendance = Attendance(
            student_id=student_id,
            date=attendance_date,
            lesson_deducted=not student.club_funded,
            is_late=is_late,
            late_minutes=late_minutes
        )
        db.session.add(attendance)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Посещение {student.full_name} зафиксировано',
            'attendance_id': attendance.id,
            'check_in_time': now.isoformat(),
            'is_late': is_late,
            'late_minutes': late_minutes
        })
    
    except Exception as e:
        db.session.rollback()
        import traceback
        error_trace = traceback.format_exc()
        print(f"Ошибка ручной фиксации посещения: {error_trace}")
        return jsonify({'success': False, 'message': f'Ошибка: {str(e)}'}), 500


@app.route('/api/attendance/today')
@login_required
def today_attendance():
    """Список присутствующих сегодня"""
    try:
        today = get_local_date()
        records = Attendance.query.options(
            joinedload(Attendance.student).joinedload(Student.group),
            joinedload(Attendance.student).joinedload(Student.tariff),
        ).filter_by(date=today).all()
        balances = calculate_student_balances_bulk([
            record.student for record in records if record.student
        ])
        
        result = []
        for record in records:
            if not record.student:
                continue
                
            photo_url = build_photo_thumb_url(record.student.photo_path)
            
            group_name = record.student.group.name if record.student.group else 'Без группы'
            student_balance = balances.get(record.student.id, 0)
            low_balance = (not record.student.club_funded) and (student_balance <= 0)
            
            # Безопасное получение времени
            check_in_str = "--:--"
            if record.check_in:
                # Конвертируем в локальное время, если вдруг в БД попало UTC
                c_time = record.check_in
                if c_time.tzinfo is None:
                    # Допустим это UTC, переводим в Ташкент
                    check_in_str = (c_time + timedelta(hours=5)).strftime('%H:%M')
                else:
                    check_in_str = c_time.astimezone(TASHKENT_TZ).strftime('%H:%M')
            elif hasattr(record, 'check_in_time') and record.check_in_time:
                check_in_str = record.check_in_time.strftime('%H:%M')

            result.append({
                'id': record.id,
                'student_name': record.student.full_name,
                'photo_url': photo_url,
                'group_name': group_name,
                'check_in': check_in_str,
                'balance': student_balance,
                'low_balance': low_balance
            })
        
        return jsonify(result)
    except Exception as e:
        print(f"❌ Ошибка в today_attendance: {e}")
        import traceback
        traceback.print_exc()
        return jsonify([])


@app.route('/api/attendance/years')
@login_required
def attendance_years():
    """Возвращает список годов, в которых есть записи посещаемости"""
    from sqlalchemy import extract
    years_query = db.session.query(extract('year', Attendance.check_in).label('year')) \
        .distinct() \
        .order_by(extract('year', Attendance.check_in).desc()) \
        .all()
    years = []
    for item in years_query:
        raw_value = item.year if hasattr(item, 'year') else item[0]
        if raw_value is None:
            continue
        years.append(int(raw_value))
    current_year = get_local_datetime().year
    return jsonify({'years': years, 'current_year': current_year})


@app.route('/api/attendance/all')
@login_required
def all_attendance():
    """Список посещаемости с фильтрами"""
    from sqlalchemy import extract
    
    # Получение параметров фильтров
    year = request.args.get('year')
    month = request.args.get('month')
    group_id = request.args.get('group_id')
    student_id = request.args.get('student_id')
    
    # Базовый запрос
    query = db.session.query(Attendance).options(
        joinedload(Attendance.student).joinedload(Student.group),
        joinedload(Attendance.student).joinedload(Student.tariff),
    ).join(Student)
    
    # Применение фильтров
    if year:
        query = query.filter(extract('year', Attendance.check_in) == int(year))
    
    if month:
        query = query.filter(extract('month', Attendance.check_in) == int(month))
    
    if student_id:
        query = query.filter(Attendance.student_id == int(student_id))
    
    if group_id:
        query = query.filter(Student.group_id == int(group_id))
    
    # Сортировка по дате (сначала новые)
    records = query.order_by(Attendance.check_in.desc()).all()
    balances = calculate_student_balances_bulk([
        record.student for record in records if record.student
    ])
    
    result = []
    for record in records:
        result.append({
            'id': record.id,
            'student_id': record.student_id,
            'student_name': record.student.full_name,
            'group_name': record.student.group.name if record.student.group else None,
            'check_in_time': record.check_in.isoformat(),
            'balance': balances.get(record.student_id, 0)
        })
    
    return jsonify(result)


@app.route('/api/attendance/analytics', methods=['GET'])
@login_required
def get_attendance_analytics():
    """Аналитика посещаемости"""
    from sqlalchemy import func, extract
    from datetime import date
    
    year = request.args.get('year', type=int)
    if not year:
        year = date.today().year
    
    # Одна агрегация вместо 12 отдельных запросов по месяцам.
    monthly_rows = db.session.query(
        extract('month', Attendance.check_in).label('month'),
        func.count(Attendance.id).label('count'),
    ).filter(
        extract('year', Attendance.check_in) == year
    ).group_by(extract('month', Attendance.check_in)).all()
    monthly_counts = {int(row.month): int(row.count or 0) for row in monthly_rows if row.month}
    month_names = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
                   'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
    monthly_data = [{
        'month': month,
        'month_name': month_names[month - 1],
        'count': monthly_counts.get(month, 0),
    } for month in range(1, 13)]
    
    # Посещаемость по дням недели (1=Пн, 7=Вс)
    # Получаем все записи за год и группируем по дням недели в Python
    attendance_times = db.session.query(Attendance.check_in).filter(
        extract('year', Attendance.check_in) == year
    ).all()
    
    weekday_counts = {i: 0 for i in range(1, 8)}  # 1=Пн, 7=Вс
    for (check_in,) in attendance_times:
        if check_in:
            # weekday() возвращает 0=Пн, 6=Вс, конвертируем в 1-7
            weekday = check_in.weekday() + 1
            weekday_counts[weekday] = weekday_counts.get(weekday, 0) + 1
    
    weekday_data = [{
        'weekday': weekday,
        'count': weekday_counts[weekday]
    } for weekday in range(1, 8)]
    
    # Посещаемость по группам
    group_stats = db.session.query(
        Group.name.label('group_name'),
        func.count(Attendance.id).label('count')
    ).join(Student, Group.id == Student.group_id)\
     .join(Attendance, Student.id == Attendance.student_id)\
     .filter(extract('year', Attendance.check_in) == year)\
     .group_by(Group.id, Group.name)\
     .all()
    
    groups_data = [{
        'group_name': g.group_name,
        'count': g.count
    } for g in group_stats]
    
    # Статистика опозданий
    total_attendance = sum(monthly_counts.values())
    total_late, avg_late = db.session.query(
        func.count(Attendance.id),
        func.avg(Attendance.late_minutes),
    ).filter(
        extract('year', Attendance.check_in) == year,
        Attendance.is_late == True,
        Attendance.late_minutes.isnot(None)
    ).one()
    total_late = total_late or 0
    avg_late = avg_late or 0
    
    late_percentage = round((total_late / total_attendance * 100) if total_attendance > 0 else 0, 1)
    
    return jsonify({
        'monthly': monthly_data,
        'weekdays': weekday_data,
        'groups': groups_data,
        'late_stats': {
            'total_late': total_late,
            'late_percentage': late_percentage,
            'avg_late_minutes': round(avg_late, 1) if avg_late else 0
        }
    })


@app.route('/api/attendance/groups-statistics', methods=['GET'])
@login_required
def get_groups_attendance_statistics():
    """Статистика посещаемости по группам на выбранную дату"""
    from datetime import date, datetime
    
    # Получаем параметры фильтра
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    day = request.args.get('day', type=int)
    
    # Если дата не указана, используем сегодняшнюю
    if not year or not month or not day:
        today = date.today()
        year = year or today.year
        month = month or today.month
        day = day or today.day
    
    selected_date = date(year, month, day)
    weekday = selected_date.weekday() + 1  # 1=Пн, 7=Вс
    
    # Получаем группы, учеников и посещения пачками, без N+1 запросов.
    groups_with_lessons = [
        group for group in Group.query.order_by(Group.name.asc()).all()
        if weekday in group.get_schedule_days_list()
    ]
    group_ids = [group.id for group in groups_with_lessons]
    students_by_group = {group_id: [] for group_id in group_ids}
    attendance_by_group = {group_id: {} for group_id in group_ids}

    if group_ids:
        students = Student.query.options(joinedload(Student.group)).filter(
            Student.group_id.in_(group_ids),
            Student.status == 'active'
        ).order_by(Student.full_name.asc()).all()
        for student in students:
            students_by_group.setdefault(student.group_id, []).append(student)

        attendances = Attendance.query.join(Student).filter(
            Attendance.date == selected_date,
            Student.group_id.in_(group_ids)
        ).all()
        for att in attendances:
            if att.student and att.student.group_id:
                attendance_by_group.setdefault(att.student.group_id, {})[att.student_id] = att

    result = []
    
    for group in groups_with_lessons:
        students = students_by_group.get(group.id, [])
        attendance_records = attendance_by_group.get(group.id, {})
        
        # Формируем список учеников с информацией о посещаемости
        students_list = []
        for student in students:
            att = attendance_records.get(student.id)
            
            # Разделяем имя и фамилию
            name_parts = student.full_name.split(' ', 1)
            first_name = name_parts[0] if name_parts else ''
            last_name = name_parts[1] if len(name_parts) > 1 else ''
            
            check_in_time = None
            check_in_datetime = None
            is_late = False
            late_minutes = 0
            attendance_id = None
            if att:
                attendance_id = att.id
                if att.check_in:
                    check_in_time = att.check_in.isoformat()
                    check_in_datetime = att.check_in.isoformat()
                elif att.date:
                    check_in_datetime = datetime.combine(att.date, dt_time.min).isoformat()
                    check_in_time = check_in_datetime
                is_late = bool(att.is_late)
                late_minutes = att.late_minutes or 0
            
            students_list.append({
                'id': student.id,
                'first_name': first_name,
                'last_name': last_name,
                'full_name': student.full_name,
                'photo_path': student.photo_path,
                'photo_url': build_photo_thumb_url(student.photo_path),
                'has_attended': att is not None,
                'check_in_time': check_in_time,
                'check_in_datetime': check_in_datetime,
                'is_late': is_late,
                'late_minutes': late_minutes,
                'attendance_id': attendance_id  # ID записи посещения для удаления
            })
        
        # Сортируем: сначала те, кто пришел (по времени входа), потом те, кто не пришел
        students_list.sort(key=lambda x: (
            not x['has_attended'],  # False (пришел) идет раньше True (не пришел)
            x['check_in_datetime'] if x['check_in_datetime'] else ''  # По времени входа
        ))
        
        result.append({
            'group_id': group.id,
            'group_name': group.name,
            'schedule_time': group.schedule_time if group.schedule_time else None,
            'total_students': len(students_list),
            'attended_count': sum(1 for s in students_list if s['has_attended']),
            **group_trainer_payload(group),
            'students': students_list
        })
    
    # Сортируем группы по времени занятий
    result.sort(key=lambda x: x['schedule_time'] or '')
    
    return jsonify({
        'date': selected_date.isoformat(),
        'weekday': weekday,
        'groups': result
    })


@app.route('/api/attendance/delete/<int:attendance_id>', methods=['DELETE'])
@login_required
def delete_attendance(attendance_id):
    """Удалить запись посещаемости"""
    record = db.session.get(Attendance, attendance_id)
    
    if not record:
        return jsonify({'success': False, 'message': 'Запись не найдена'}), 404
    
    student = record.student
    
    db.session.delete(record)
    db.session.commit()
    
    # Баланс пересчитывается автоматически после удаления посещения
    return jsonify({
        'success': True,
        'message': f'Запись удалена, баланс {student.full_name}: {calculate_student_balance(student)}'
    })


# ===== РАСХОДЫ =====

@app.route('/expenses')
@login_required
def expenses_page():
    if not current_user.has_permission('finances', 'view'):
        return redirect(url_for('dashboard'))

    ensure_expense_columns()
    expenses = Expense.query.order_by(Expense.expense_date.desc()).limit(50).all()
    employees = User.query.order_by(User.full_name.asc(), User.username.asc()).all()
    return render_template('expenses.html', expenses=expenses, employees=employees)


@app.route('/api/expenses/add', methods=['POST'])
@login_required
def add_expense():
    if not current_user.has_permission('finances', 'edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403

    ensure_expense_columns()
    try:
        data = request.get_json()
        category = (data.get('category') or '').strip()
        incasso_labels = {'инкасация', 'инкассация'}
        is_incasso = category.lower() in incasso_labels
        if is_incasso:
            category = 'Encashment'  # Храним на английском для SQLite
        source = (data.get('expense_source') or 'cash').strip()
        if source not in ['cash', 'bank']:
            source = 'cash'
        # Инкасация всегда идёт из кассы (нал)
        if is_incasso:
            source = 'cash'
        amount = float(data.get('amount'))
        employee = get_salary_expense_employee(data, category)
        salary_year, salary_month = parse_salary_period(data, category)
        expense = Expense(
            category=category,
            amount=amount,
            description=data.get('description'),
            expense_source=source,
            employee_id=employee.id if employee else None,
            employee_name=(employee.full_name or employee.username) if employee else None,
            salary_year=salary_year,
            salary_month=salary_month,
            created_by=current_user.id
        )
        db.session.add(expense)
        db.session.flush()  # Получить ID расхода
        
        # Для инкассации создаём скрытый приход в Р/с
        if is_incasso:
            # Получить первого студента для системных платежей
            system_student = Student.query.first()
            payment = Payment(
                student_id=system_student.id if system_student else 1,
                tariff_id=None,
                amount_paid=amount,
                amount_due=0,
                payment_type='transfer',
                notes=f'Инкассация (Расход #{expense.id})',
                lessons_added=0,
                created_by=current_user.id
            )
            db.session.add(payment)
        
        db.session.commit()
        return jsonify({'success': True})
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/expenses/<int:expense_id>', methods=['PUT'])
@login_required
def update_expense(expense_id):
    if not current_user.has_permission('finances', 'edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403

    ensure_expense_columns()
    try:
        data = request.get_json() or {}
        expense = db.session.get(Expense, expense_id)
        if not expense:
            return jsonify({'success': False, 'message': 'Расход не найден'}), 404

        if 'category' in data:
            category = (data.get('category') or '').strip()
            incasso_labels = {'инкасация', 'инкассация'}
            if category.lower() in incasso_labels:
                category = 'Encashment'  # Храним на английском для SQLite
            expense.category = category
        old_amount = expense.amount
        new_amount = float(data.get('amount')) if 'amount' in data else old_amount
        
        if 'amount' in data:
            expense.amount = new_amount
        if 'description' in data:
            expense.description = data.get('description')
        if 'expense_source' in data:
            source = (data.get('expense_source') or 'cash').strip()
            # Проверяем уже обновлённую категорию или старую
            if expense.category == 'Encashment':
                source = 'cash'
            if source in ['cash', 'bank']:
                expense.expense_source = source

        employee = get_salary_expense_employee(data, expense.category)
        if employee:
            expense.employee_id = employee.id
            expense.employee_name = employee.full_name or employee.username
            salary_year, salary_month = parse_salary_period(data, expense.category)
            expense.salary_year = salary_year
            expense.salary_month = salary_month
        elif expense.category != 'Зарплата':
            expense.employee_id = None
            expense.employee_name = None
            expense.salary_year = None
            expense.salary_month = None
        
        # Обновить связанный платёж инкассации, если сумма изменилась
        if expense.category == 'Encashment' and new_amount != old_amount:
            related_payment = Payment.query.filter(
                Payment.notes.like(f'Инкассация (Расход #{expense_id})')
            ).first()
            if related_payment:
                related_payment.amount_paid = new_amount

        db.session.commit()
        return jsonify({'success': True})
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/expenses/<int:expense_id>', methods=['DELETE'])
@login_required
def delete_expense(expense_id):
    """Удалить расход"""
    if not current_user.has_permission('finances', 'edit'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403

    try:
        expense = db.session.get(Expense, expense_id)
        if not expense:
            return jsonify({'success': False, 'message': 'Расход не найден'}), 404
        
        # Удалить связанный платёж инкассации
        if expense.category == 'Encashment':
            related_payment = Payment.query.filter(
                Payment.notes.like(f'Инкассация (Расход #{expense_id})')
            ).first()
            if related_payment:
                db.session.delete(related_payment)

        db.session.delete(expense)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Расход удалён'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# ===== ФИНАНСЫ =====

@app.route('/finances')
@login_required
def finances_page():
    """Страница финансов"""
    return render_template('finances.html')


@app.route('/settings')
@login_required
def club_settings_page():
    """Страница настроек клуба"""
    if not current_user.has_permission('settings', 'view'):
        return redirect(url_for('dashboard'))
    ensure_club_settings_columns()
    return render_template('settings.html')


# ===== МОБИЛЬНАЯ ВЕРСИЯ ДЛЯ ОПЛАТ =====

@app.route('/mobile-payments')
@login_required
def mobile_payments():
    """Мобильная страница для добавления оплат"""
    if current_user.role not in ['payment_admin', 'admin']:
        return redirect(url_for('dashboard'))
    return render_template('mobile_payment.html')


@app.route('/mobile-payment-history')
@login_required
def mobile_payment_history():
    """История оплат для мобильной версии"""
    if current_user.role not in ['payment_admin', 'admin']:
        return redirect(url_for('dashboard'))
    return render_template('mobile_payment_history.html')


@app.route('/api/mobile/payment-history', methods=['GET'])
@login_required
def get_mobile_payment_history():
    """Получить историю оплат для мобильной версии"""
    if current_user.role not in ['payment_admin', 'admin']:
        return jsonify({'error': 'Доступ запрещен'}), 403
    
    # Получить все оплаты, отсортированные по дате
    payments = db.session.query(
        Payment.id,
        Payment.student_id,
        Payment.amount_paid,
        Payment.payment_date,
        Payment.payment_month,
        Payment.payment_year,
        Payment.notes,
        Payment.created_by,
        Student.full_name.label('student_name')
    ).join(Student).order_by(Payment.payment_date.desc()).limit(100).all()
    
    result = []
    for p in payments:
        result.append({
            'id': p.id,
            'student_id': p.student_id,
            'student_name': p.student_name,
            'amount_paid': p.amount_paid,
            'payment_date': p.payment_date.isoformat(),
            'payment_month': p.payment_month,
            'payment_year': p.payment_year,
            'notes': p.notes,
            'created_by': p.created_by
        })
    
    return jsonify(result)


# ===== МОБИЛЬНАЯ ВЕРСИЯ ДЛЯ УЧИТЕЛЯ =====

@app.route('/teacher-attendance')
@login_required
def teacher_attendance():
    """Мобильная страница переклички для учителя"""
    if current_user.role not in ['teacher', 'admin']:
        return redirect(url_for('dashboard'))
    return render_template('teacher_attendance.html')


@app.route('/api/teacher/mark-attendance', methods=['POST'])
@login_required
def teacher_mark_attendance():
    """Отметить посещаемость ученика"""
    if current_user.role not in ['teacher', 'admin']:
        return jsonify({'error': 'Доступ запрещен'}), 403
    
    try:
        data = request.json
        student_id = data.get('student_id')
        status = data.get('status')  # 'present', 'absent', 'late'
        date_str = data.get('date')
        
        if not all([student_id, status, date_str]):
            return jsonify({'error': 'Недостаточно данных'}), 400
        
        # Проверить, существует ли уже запись на сегодня
        attendance_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        existing = Attendance.query.filter_by(
            student_id=student_id,
            date=attendance_date
        ).first()
        
        if existing:
            # Обновить существующую запись
            existing.status = status
            existing.check_in_time = datetime.now().time() if status == 'present' else None
        else:
            # Создать новую запись
            attendance = Attendance(
                student_id=student_id,
                date=attendance_date,
                status=status,
                check_in_time=datetime.now().time() if status == 'present' else None
            )
            db.session.add(attendance)
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Статус сохранен'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/teacher/today-attendance', methods=['GET'])
@login_required
def teacher_today_attendance():
    """Получить сегодняшнюю посещаемость для группы учителя"""
    if current_user.role not in ['teacher', 'admin']:
        return jsonify({'error': 'Доступ запрещен'}), 403
    
    # Получить group_id учителя
    group_id = current_user.group_id if current_user.role == 'teacher' else request.args.get('group_id', type=int)
    
    if not group_id:
        return jsonify({'error': 'Группа не указана'}), 400
    
    today = date.today()
    
    # Получить сегодняшнюю посещаемость
    attendance_records = Attendance.query.filter_by(date=today).all()
    
    result = {}
    for record in attendance_records:
        if record.student and record.student.group_id == group_id:
            result[record.student_id] = {
                'status': record.status,
                'check_in_time': record.check_in_time.strftime('%H:%M') if record.check_in_time else None
            }
    
    return jsonify(result)


@app.route('/api/finances/income', methods=['GET'])
@login_required
def get_income_stats():
    """Статистика прихода"""
    from datetime import date
    from sqlalchemy import func, extract
    
    today = date.today()
    
    # Сегодня
    income_today = db.session.query(func.sum(Payment.amount_paid)).filter(
        func.date(Payment.payment_date) == today
    ).scalar() or 0
    
    # Этот месяц
    income_month = db.session.query(func.sum(Payment.amount_paid)).filter(
        extract('year', Payment.payment_date) == today.year,
        extract('month', Payment.payment_date) == today.month
    ).scalar() or 0
    
    # Всего
    income_total = db.session.query(func.sum(Payment.amount_paid)).scalar() or 0
    
    # Последние платежи
    payments = db.session.query(
        Payment,
        Student.full_name.label('student_name'),
        Student.group_id.label('group_id'),
        Student.tariff_id.label('student_tariff_id'),
        Group.name.label('group_name'),
        Tariff.name.label('student_tariff_name')
    ).join(Student, Payment.student_id == Student.id, isouter=True) \
     .join(Group, Student.group_id == Group.id, isouter=True) \
     .join(Tariff, Student.tariff_id == Tariff.id, isouter=True) \
     .order_by(Payment.payment_date.desc()).limit(50).all()
    
    payments_list = [{
        'id': p.Payment.id,
        'payment_date': p.Payment.payment_date.isoformat(),
        # В БД локальное время Ташкента хранится без offset; передаём его явно,
        # чтобы браузер в любом часовом поясе показал правильный момент.
        'created_at': f"{p.Payment.created_at.isoformat()}+05:00" if p.Payment.created_at else None,
        'student_id': p.Payment.student_id,
        'student_name': p.student_name,
        'group_id': p.group_id,
        'group_name': p.group_name,
        'tariff_name': p.Payment.tariff_name or p.student_tariff_name or '-',
        'amount_paid': p.Payment.amount_paid,
        'amount_due': p.Payment.amount_due,
        'is_full_payment': p.Payment.is_full_payment,
        'payment_type': getattr(p.Payment, 'payment_type', 'cash') or 'cash',
        'notes': p.Payment.notes
    } for p in payments]
    
    return jsonify({
        'today': income_today,
        'month': income_month,
        'total': income_total,
        'payments': payments_list
    })


@app.route('/api/finances/balance', methods=['GET'])
@login_required
def get_balance_breakdown():
    """Агрегация баланса по наличным и р/с"""
    # Включаем все безналичные типы, в т.ч. alias transfer/перечисление
    bank_methods = {
        'paynet', 'multicard', 'oson', 'click', 'payme', 'перечисление', 'transfer', 'uzum', 'uzcard', 'humo', 'card'
    }

    # Приходы (теперь transfer payments от инкассации автоматически попадут в bank_income)
    total_income = db.session.query(func.sum(Payment.amount_paid)).scalar() or 0
    bank_income = db.session.query(func.sum(Payment.amount_paid)).filter(
        func.lower(func.trim(func.coalesce(Payment.payment_type, 'cash'))).in_(bank_methods)
    ).scalar() or 0
    cash_income = total_income - bank_income

    # Расходы (все расходы считаем нормально, инкассация уже не особый случай)
    bank_expense = db.session.query(func.sum(Expense.amount)).filter(
        func.lower(func.trim(func.coalesce(Expense.expense_source, ''))) == 'bank'
    ).scalar() or 0

    cash_expense = db.session.query(func.sum(Expense.amount)).filter(
        func.lower(func.trim(func.coalesce(Expense.expense_source, ''))) != 'bank'
    ).scalar() or 0

    total_expense = bank_expense + cash_expense

    cash_balance = cash_income - cash_expense
    bank_balance = bank_income - bank_expense
    total_balance = cash_balance + bank_balance

    return jsonify({
        'cash_income': cash_income,
        'bank_income': bank_income,
        'cash_expense': cash_expense,
        'bank_expense': bank_expense,
        'cash_balance': cash_balance,
        'bank_balance': bank_balance,
        'total_income': total_income,
        'total_expense': total_expense,
        'total_balance': total_balance
    })


def calculate_month_debt_total(year, month):
    """Сумма долга активных учеников за конкретный месяц."""
    from calendar import monthrange
    from datetime import date

    today = get_local_date()
    if (year, month) > (today.year, today.month):
        return 0
    settings = get_club_settings_instance()
    global_start = normalize_month_pair(
        getattr(settings, 'access_debt_start_year', None),
        getattr(settings, 'access_debt_start_month', None)
    )
    if global_start and (year, month) < global_start:
        return 0

    month_end = date(year, month, monthrange(year, month)[1])

    students = Student.query.filter(
        Student.status == 'active',
        Student.tariff_id.isnot(None),
        db.or_(Student.club_funded == False, Student.club_funded.is_(None)),
        db.or_(Student.admission_date.is_(None), Student.admission_date <= month_end)
    ).options(joinedload(Student.tariff)).all()

    if not students:
        return 0

    paid_rows = db.session.query(
        Payment.student_id,
        func.coalesce(func.sum(Payment.amount_paid), 0)
    ).filter(
        Payment.payment_year == year,
        Payment.payment_month == month
    ).group_by(Payment.student_id).all()
    paid_by_student = {student_id: float(total or 0) for student_id, total in paid_rows}

    total_debt = 0
    for student in students:
        if not student.tariff or not student.tariff.price:
            continue
        tariff_price = float(student.tariff.price or 0)
        total_debt += max(0, tariff_price - paid_by_student.get(student.id, 0))

    return total_debt


def calculate_month_student_expectation(year, month):
    """Ожидаемая сумма от родителей и численность учеников на конец месяца."""
    from calendar import monthrange
    from datetime import date

    month_start = date(year, month, 1)
    month_end = date(year, month, monthrange(year, month)[1])

    active_students = Student.query.filter(
        Student.status == 'active',
        db.or_(Student.admission_date.is_(None), Student.admission_date <= month_end)
    ).options(joinedload(Student.tariff)).all()

    # Ждем ровно столько, сколько ученик реально должен за этот месяц
    dues = get_students_month_dues(active_students, year, month)

    expected = 0
    student_count = 0
    club_funded_count = 0
    club_expected = 0
    for student in active_students:
        student_count += 1
        tariff_price = float(student.tariff.price or 0) if student.tariff and student.tariff.price else 0
        if student.club_funded:
            club_funded_count += 1
            club_expected += tariff_price
            continue
        expected += dues.get(student.id, 0.0)

    new_student_count = Student.query.filter(
        Student.status == 'active',
        Student.admission_date.isnot(None),
        Student.admission_date >= month_start,
        Student.admission_date <= month_end
    ).count()

    return {
        'expected': float(expected),
        'student_count': int(student_count),
        'club_funded_count': int(club_funded_count),
        'club_expected': float(club_expected),
        'new_student_count': int(new_student_count),
    }


@app.route('/api/finances/debtors', methods=['GET'])
@login_required
def get_debtors():
    """Список должников с помесячной детализацией"""
    settings = get_club_settings_instance()
    today = get_local_date()
    global_start = normalize_month_pair(
        getattr(settings, 'access_debt_start_year', None),
        getattr(settings, 'access_debt_start_month', None)
    )

    students = Student.query.filter(
        Student.status == 'active',
        Student.tariff_id.isnot(None),
        db.or_(Student.club_funded == False, Student.club_funded.is_(None))
    ).options(joinedload(Student.tariff)).all()

    current_year = today.year
    current_month = today.month

    paid_rows = db.session.query(
        Payment.student_id,
        Payment.payment_year,
        Payment.payment_month,
        func.coalesce(func.sum(Payment.amount_paid), 0)
    ).filter(
        Payment.payment_year.isnot(None),
        Payment.payment_month.isnot(None)
    ).group_by(
        Payment.student_id,
        Payment.payment_year,
        Payment.payment_month
    ).all()
    paid_by_month = {
        (student_id, year, month): float(total or 0)
        for student_id, year, month, total in paid_rows
    }
    
    debtors_list = []
    total_debt = 0
    
    for student in students:
        if not student.tariff:
            continue
            
        tariff_price = float(student.tariff.price)
        
        if student.admission_date:
            start_year = student.admission_date.year
            start_month = student.admission_date.month
        else:
            start_year = current_year
            start_month = 1
        if global_start and (start_year, start_month) < global_start:
            start_year, start_month = global_start
        if (start_year, start_month) > (current_year, current_month):
            continue
        
        # Проверить каждый месяц от даты принятия до текущего месяца
        year = start_year
        month = start_month
        
        while (year < current_year) or (year == current_year and month <= current_month):
            month_key = f"{year}-{str(month).zfill(2)}"
            
            total_paid = paid_by_month.get((student.id, year, month), 0)
            debt = max(0, tariff_price - total_paid)
            
            if debt > 0:
                total_debt += debt
                debtors_list.append({
                    'student_id': student.id,
                    'student_name': student.full_name,
                    'student_phone': student.phone or student.parent_phone or '-',
                    'tariff_name': student.tariff.name,
                    'tariff_price': tariff_price,
                    'amount_paid': total_paid,
                    'amount_due': debt,
                    'month': month,
                    'year': year,
                    'month_label': f"{month}/{year}"
                })
            
            # Следующий месяц
            month += 1
            if month > 12:
                month = 1
                year += 1
    
    unique_debtors = len({d['student_id'] for d in debtors_list})

    return jsonify({
        'total_debt': total_debt,
        'count': unique_debtors,
        'debtors': debtors_list
    })


@app.route('/api/hikvision/students', methods=['GET'])
def hikvision_students():
    """Список учеников для локального bridge Hikvision."""
    if not check_bridge_auth():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    ensure_club_settings_columns()
    settings = get_club_settings_instance()
    today = get_local_date()
    paid_map = get_month_paid_map(today.year, today.month)
    payment_date_paid_map = get_payment_date_paid_map(today.year, today.month)
    students = Student.query.options(
        joinedload(Student.tariff),
        joinedload(Student.group)
    ).order_by(Student.id.asc()).all()
    staff_users = User.query.order_by(User.id.asc()).all()
    access_policy = get_access_payment_policy(settings)
    debt_month_counts = (
        get_debt_month_counts(students, settings, today, include_current=False)
        if access_policy in {'partial_current_month', 'any_payment_this_month'}
        else {}
    )

    base_url = request.host_url.rstrip('/')
    payload = []
    for student in students:
        item = build_hikvision_person_payload(
            'student',
            student.id,
            settings,
            today,
            paid_map,
            payment_date_paid_map,
            debt_month_counts
        )
        if item:
            payload.append(item)

    for user in staff_users:
        item = build_hikvision_person_payload('staff', user.id, settings, today)
        if item:
            payload.append(item)
    payload, duplicates_skipped = dedupe_hikvision_payload(payload)

    return jsonify({
        'success': True,
        'month': today.month,
        'year': today.year,
        'access_block_day': int(getattr(settings, 'access_block_day', 10) or 10),
        'access_payment_policy': access_policy,
        'access_max_debt_months': get_effective_access_max_debt_months(settings),
        'duplicates_skipped': duplicates_skipped,
        'students': payload
    })


@app.route('/api/hikvision/person', methods=['GET'])
def hikvision_person():
    """Одна запись для точечного обновления локальным bridge."""
    if not check_bridge_auth():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    person_type = (request.args.get('person_type') or request.args.get('type') or 'student').strip()
    person_id = request.args.get('person_id') or request.args.get('id')
    if person_type not in {'student', 'staff'} or not person_id:
        return jsonify({'success': False, 'message': 'Invalid person request'}), 400

    ensure_club_settings_columns()
    settings = get_club_settings_instance()
    today = get_local_date()
    payload = build_hikvision_person_payload(person_type, person_id, settings, today)
    if not payload:
        return jsonify({'success': False, 'message': 'Person not found'}), 404

    return jsonify({
        'success': True,
        'person': payload,
        'month': today.month,
        'year': today.year,
        'access_block_day': int(getattr(settings, 'access_block_day', 10) or 10),
        'access_payment_policy': get_access_payment_policy(settings),
        'access_max_debt_months': get_effective_access_max_debt_months(settings),
    })


@app.route('/api/hikvision/config', methods=['GET'])
def hikvision_config():
    if not check_bridge_auth():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    ensure_club_settings_columns()
    settings = get_club_settings_instance()
    devices = settings.get_hikvision_devices() or default_hikvision_devices()
    return jsonify({
        'success': True,
        'devices': devices,
        'daily_sync_time': get_hikvision_daily_sync_time(settings),
        'parallel_devices': bool(getattr(settings, 'hikvision_parallel_devices', False)),
        'cleanup_stale_users': bool(getattr(settings, 'hikvision_cleanup_stale_users', True)),
        'max_debt_months': get_effective_access_max_debt_months(settings),
        'camera': {
            'enabled': bool(getattr(settings, 'camera_kiosk_enabled', False)),
            'rtsp_url': getattr(settings, 'rtsp_url', '') or '',
            'kiosk_url': getattr(settings, 'camera_kiosk_url', '') or '',
            'stream_fps': int(getattr(settings, 'camera_stream_fps', 30) or 30),
            'tracking_fps': int(getattr(settings, 'camera_tracking_fps', 30) or 30),
            'detection_fps': int(getattr(settings, 'camera_detection_fps', 10) or 10),
            'width': int(getattr(settings, 'camera_width', 1920) or 1920),
            'height': int(getattr(settings, 'camera_height', 1080) or 1080),
            'recognition_frames': int(getattr(settings, 'camera_recognition_frames', 3) or 3),
            'result_hold_seconds': int(getattr(settings, 'camera_result_hold_seconds', 10) or 10),
            'kiosk_port': int(getattr(settings, 'camera_kiosk_port', 8090) or 8090),
        },
        'timezone': 'Asia/Tashkent',
    })


@app.route('/api/camera-kiosk/recognize', methods=['POST'])
def camera_kiosk_recognize():
    """Read-only face decision for the local camera kiosk on bridge."""
    if not check_bridge_auth():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    ensure_club_settings_columns()
    settings = get_club_settings_instance()
    if not bool(getattr(settings, 'camera_kiosk_enabled', False)):
        return jsonify({'success': False, 'message': 'Camera-kiosk выключен'}), 503

    data = request.get_json(silent=True) or {}
    track_id = str(data.get('track_id') or '')[:80]
    image_data_url = data.get('image_data_url') or data.get('frame') or ''
    if not str(image_data_url).startswith('data:image/'):
        return jsonify({'success': False, 'track_id': track_id, 'message': 'Изображение не передано'}), 400

    students, candidates = build_access_face_candidates()
    result = access_face_verifier.identify(image_data_url, candidates)
    persist_computed_face_embeddings(students, candidates)
    identified = result.get('identified') or {}
    response = {
        'success': True,
        'track_id': track_id,
        'status': result.get('status') or 'unknown',
        'reason': result.get('reason') or '',
        'similarity': round(float(result.get('similarity') or 0) * 100, 1),
        'color': 'yellow',
        'student': None,
    }
    student_id = identified.get('id')
    if not student_id:
        return jsonify(response)

    student = db.session.get(Student, student_id)
    if not student:
        return jsonify(response)
    today = get_local_date()
    paid_map = get_month_paid_map(today.year, today.month)
    payment_date_paid_map = get_payment_date_paid_map(today.year, today.month)
    allowed, reason, debt = student_access_state(
        student,
        settings,
        paid_map,
        payment_date_paid_map,
        today,
    )
    response.update({
        'color': 'green' if allowed else 'red',
        'access_allowed': bool(allowed),
        'access_reason': reason,
        'student': {
            'id': student.id,
            'full_name': student.full_name,
            'group_name': student.group.name if student.group else None,
            'photo_url': build_photo_url(student.photo_path),
            'debt': float(debt or 0),
        },
    })
    return jsonify(response)


@app.route('/api/hikvision/open-day', methods=['GET'])
@login_required
def get_open_day_state():
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    settings = get_club_settings_instance()
    open_until = get_access_open_until(settings)
    return jsonify({
        'success': True,
        'active': is_access_open_day(settings),
        'open_until': open_until.isoformat() if open_until else None,
    })


@app.route('/api/hikvision/open-day', methods=['POST'])
@login_required
def set_open_day():
    """Пропустить всех: включаем на сегодня и сразу выгружаем список в терминалы."""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    ensure_club_settings_columns()
    data = request.get_json(silent=True) or {}
    enable = data.get('enable', True)
    settings = get_club_settings_instance()
    today = get_local_date()

    if not enable:
        settings.access_open_until = None
        db.session.commit()
        queue_hikvision_sync('open_day_off')
        db.session.commit()
        return jsonify({
            'success': True,
            'active': False,
            'message': 'Открытый день выключен. Терминалы вернутся к обычным правилам после синхронизации.'
        })

    # Дату можно задать явно, по умолчанию только сегодня
    raw_date = (data.get('until') or '').strip()
    until = today
    if raw_date:
        try:
            until = datetime.strptime(raw_date, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'message': 'Неверная дата'}), 400
        if until < today:
            return jsonify({'success': False, 'message': 'Дата уже прошла'}), 400

    settings.access_open_until = until
    db.session.commit()
    queue_hikvision_sync('open_day_on')
    db.session.commit()

    total = Student.query.filter(Student.status == 'active').count()
    return jsonify({
        'success': True,
        'active': True,
        'open_until': until.isoformat(),
        'message': (
            f'Открытый день включен до {until.strftime("%d.%m.%Y")} включительно. '
            f'Запущена синхронизация: в терминалы уйдут все активные ученики ({total}) с фото. '
            'На следующий день правила вернутся сами.'
        )
    })


@app.route('/api/hikvision/sync', methods=['POST'])
@login_required
def request_hikvision_sync():
    ensure_club_settings_columns()
    queue_hikvision_sync('manual')
    db.session.commit()
    return jsonify({'success': True, 'message': 'Команда синхронизации отправлена'})


@app.route('/api/hikvision/open-door', methods=['POST'])
@login_required
def request_hikvision_open_door():
    if current_user.role not in ['admin']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    data = request.get_json(silent=True) or {}
    device_name = (data.get('device_name') or data.get('device') or '').strip()
    if device_name not in {'entry', 'exit'}:
        return jsonify({'success': False, 'message': 'Выберите терминал входа или выхода'}), 400

    ensure_club_settings_columns()
    queue_hikvision_door_open(device_name)
    db.session.commit()
    label = 'вход' if device_name == 'entry' else 'выход'
    return jsonify({'success': True, 'message': f'Команда открыть {label} отправлена bridge'})


@app.route('/api/hikvision/clear-device', methods=['POST'])
@login_required
def request_hikvision_clear_device():
    if current_user.role not in ['admin']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    data = request.get_json(silent=True) or {}
    device_name = (data.get('device_name') or data.get('device') or '').strip()
    if device_name not in {'entry', 'exit'}:
        return jsonify({'success': False, 'message': 'Выберите терминал входа или выхода'}), 400

    queue_hikvision_clear_device(device_name)
    db.session.commit()
    label = 'вход' if device_name == 'entry' else 'выход'
    return jsonify({'success': True, 'message': f'Команда очистить терминал {label} отправлена bridge'})


@app.route('/api/hikvision/bridge/control', methods=['POST'])
@login_required
def request_hikvision_bridge_control():
    if current_user.role not in ['admin']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    data = request.get_json(silent=True) or {}
    action = (data.get('action') or '').strip()
    labels = {
        'pause': 'Пауза отправлена bridge',
        'resume': 'Продолжение отправлено bridge',
        'stop': 'Полная остановка отправлена bridge',
        'restart': 'Перезапуск отправлен bridge',
        'update': 'Обновление кода и перезапуск отправлены bridge',
    }
    if action not in labels:
        return jsonify({'success': False, 'message': 'Неизвестная команда управления'}), 400

    queue_hikvision_control(action)
    db.session.commit()
    return jsonify({'success': True, 'message': labels[action]})


@app.route('/api/hikvision/bridge/status', methods=['POST'])
def update_hikvision_bridge_status():
    if not check_bridge_auth():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    ensure_bridge_status_table()
    data = request.get_json(silent=True) or {}
    bridge_id = (data.get('bridge_id') or 'hikvision-school-bridge').strip()[:80]
    upsert_bridge_status(
        bridge_id=bridge_id,
        status_value=data.get('status') or 'online',
        host=data.get('host') or '',
        pid=data.get('pid'),
        version=data.get('version') or '',
        uptime_seconds=data.get('uptime_seconds') or 0,
        current_command_id=data.get('current_command_id'),
        current_action=data.get('current_action') or '',
        metrics=data.get('metrics') or {},
        logs=data.get('logs') or [],
    )
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/hikvision/bridge/status', methods=['GET'])
@login_required
def get_hikvision_bridge_status():
    if current_user.role not in ['admin']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    ensure_bridge_status_table()
    ensure_device_commands_table()
    now = get_local_datetime()
    status = BridgeStatus.query.order_by(BridgeStatus.last_seen_at.desc()).first()
    pending_count = DeviceCommand.query.filter_by(command='HIKVISION_SYNC', status='pending').count()
    processing = DeviceCommand.query.filter_by(command='HIKVISION_SYNC', status='processing')\
        .order_by(DeviceCommand.picked_at.desc()).first()

    online = False
    payload = None
    if status:
        seconds_since_seen = None
        if status.last_seen_at:
            seconds_since_seen = max(0, int((now - status.last_seen_at).total_seconds()))
            online = seconds_since_seen <= 20
        payload = {
            'bridge_id': status.bridge_id,
            'status': 'online' if online else 'offline',
            'reported_status': status.status,
            'host': status.host,
            'pid': status.pid,
            'version': status.version,
            'uptime_seconds': status.uptime_seconds,
            'current_command_id': status.current_command_id,
            'current_action': status.current_action,
            'metrics': status.get_metrics(),
            'logs': status.get_logs(),
            'last_seen_at': status.last_seen_at.isoformat() if status.last_seen_at else None,
            'seconds_since_seen': seconds_since_seen,
        }

    return jsonify({
        'success': True,
        'online': online,
        'bridge': payload,
        'queue': {
            'pending': pending_count,
            'processing': {
                'id': processing.id,
                'payload': processing.get_payload(),
                'picked_at': processing.picked_at.isoformat() if processing.picked_at else None,
            } if processing else None
        }
    })


def get_last_payment_map():
    """student_id -> данные последней по дате оплаты."""
    rows = db.session.query(
        Payment.student_id,
        Payment.payment_date,
        Payment.amount_paid,
        Payment.payment_month,
        Payment.payment_year,
        Payment.payment_type,
        Payment.tariff_name,
        Payment.id
    ).order_by(Payment.student_id.asc(), Payment.payment_date.asc(), Payment.id.asc()).all()

    latest = {}
    for student_id, paid_at, amount, month, year, pay_type, tariff_name, payment_id in rows:
        # Строки идут по возрастанию, поэтому последняя запись и есть свежая оплата.
        latest[student_id] = {
            'date': paid_at,
            'amount': float(amount or 0),
            'month': month,
            'year': year,
            'type': pay_type or '',
            'tariff_name': tariff_name or '',
            'payment_id': payment_id,
        }
    return latest


HIK_MISSING_CATEGORY_LABELS = {
    'no_photo': 'Нет фото для Face ID',
    'photo_broken': 'Фото есть, но терминал его не примет',
    'inactive': 'Ученик не активен или в черном списке',
    'payment': 'Оплата',
    'sync_error': 'Ошибка записи в терминал',
}

HIK_MISSING_PAYMENT_REASONS = {
    'no_current_month_payment',
    'too_many_debt_months',
    'current_month_debt',
    'no_payment_this_month',
}


def check_photo_readable(photo_path):
    """Быстрая проверка фото по заголовку файла, без полного декодирования."""
    source_path = resolve_static_photo_file(photo_path)
    if not source_path:
        return False, 'Файл фото не найден на сервере'
    try:
        with Image.open(source_path) as image:
            width, height = image.size
            if width < 20 or height < 20:
                return False, f'Фото слишком маленькое ({width}x{height})'
        return True, None
    except Exception as exc:
        return False, f'Фото повреждено или неподдерживаемый формат ({type(exc).__name__})'


def collect_last_sync_failures():
    """Ошибки последней синхронизации из отчета bridge: employeeNo -> текст."""
    failures = {}
    try:
        ensure_bridge_status_table()
        status = BridgeStatus.query.order_by(BridgeStatus.last_seen_at.desc()).first()
        if not status:
            return failures
        metrics = status.get_metrics() or {}
        progress = metrics.get('progress') or {}
        for device in (progress.get('devices') or {}).values():
            device_label = device.get('label') or device.get('name') or 'Терминал'
            for item in ((device.get('results') or {}).get('errors') or []):
                employee_no = str(item.get('employeeNo') or '').strip()
                if not employee_no:
                    continue
                failures[employee_no] = f"{device_label}: {item.get('reason') or 'ошибка записи'}"
    except Exception as exc:
        print(f'collect_last_sync_failures failed: {type(exc).__name__}: {exc}')
    return failures


@app.route('/api/hikvision/terminal-missing', methods=['GET'])
@login_required
def hikvision_terminal_missing():
    """Кто сейчас НЕ записан в терминалы и почему."""
    if current_user.role not in ['admin']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    ensure_club_settings_columns()
    settings = get_club_settings_instance()
    today = get_local_date()
    paid_map = get_month_paid_map(today.year, today.month)
    payment_date_paid_map = get_payment_date_paid_map(today.year, today.month)
    students = Student.query.options(
        joinedload(Student.tariff),
        joinedload(Student.group)
    ).filter(Student.status != 'archived').order_by(Student.full_name.asc()).all()
    access_policy = get_access_payment_policy(settings)
    debt_month_counts = (
        get_debt_month_counts(students, settings, today, include_current=False)
        if access_policy in {'partial_current_month', 'any_payment_this_month'}
        else {}
    )
    sync_failures = collect_last_sync_failures()
    last_payments = get_last_payment_map()
    student_ids_all = [student.id for student in students]
    discount_months = get_discount_months(student_ids_all, today.year)
    attendance_counts = (
        get_attendance_counts_by_month(student_ids_all, today.year)
        if get_min_lessons_for_debt(settings) else {}
    )
    check_photos = request.args.get('check_photos', '1') not in {'0', 'false', 'no'}

    items = []
    counters = {'in_terminal': 0, 'total_people': 0}

    def push(person_type, person_id, employee_no, full_name, group, status_value,
             reason, reason_label, category, has_photo, photo_path, detail='', debt_amount=0,
             tariff_id=None, tariff_name=''):
        payment = last_payments.get(person_id) if person_type == 'student' else None
        items.append({
            'last_payment_date': payment['date'].strftime('%d.%m.%Y') if payment and payment['date'] else '',
            'last_payment_amount': payment['amount'] if payment else None,
            'last_payment_period': (
                '{:02d}.{}'.format(payment['month'], payment['year'])
                if payment and payment.get('month') and payment.get('year') else ''
            ),
            'last_payment_type': payment['type'] if payment else '',
            'person_type': person_type,
            'person_id': person_id,
            'employee_no': str(employee_no),
            'full_name': full_name or '',
            'group': group or '',
            'status': status_value or '',
            'reason': reason,
            'reason_label': reason_label,
            'category': category,
            'category_label': HIK_MISSING_CATEGORY_LABELS.get(category, category),
            'has_photo': bool(has_photo),
            'photo_url': build_photo_thumb_url(photo_path) if photo_path else None,
            'detail': detail or '',
            'debt_amount': float(debt_amount or 0),
            'tariff_id': tariff_id,
            'tariff_name': tariff_name or '',
        })

    for student in students:
        counters['total_people'] += 1
        access = build_student_access_payload(
            student,
            settings,
            paid_map,
            payment_date_paid_map,
            today,
            debt_month_count=debt_month_counts.get(student.id),
            discount_months=discount_months,
            attendance_counts=attendance_counts
        )
        employee_no = str(student.id)
        group_name = student.group.name if student.group else ''
        reason = access['reason']
        reason_label = access['reason_label']

        if not access['can_sync_to_turnstile']:
            if reason == 'no_photo' or not access['has_photo']:
                category = 'no_photo'
            elif reason in HIK_MISSING_PAYMENT_REASONS:
                category = 'payment'
            else:
                category = 'inactive'
            detail = ''
            if category == 'payment' and access['debt']:
                detail = 'долг: {:,} сум'.format(int(access['debt'])).replace(',', ' ')
            push('student', student.id, employee_no, student.full_name, group_name,
                 student.status, reason, reason_label, category,
                 access['has_photo'], student.photo_path, detail, access['debt'],
                 student.tariff_id, student.tariff.name if student.tariff else '')
            continue

        failure = sync_failures.get(employee_no)
        if failure:
            push('student', student.id, employee_no, student.full_name, group_name,
                 student.status, 'sync_error', 'Ошибка записи в терминал', 'sync_error',
                 True, student.photo_path, failure, 0,
                 student.tariff_id, student.tariff.name if student.tariff else '')
            continue

        if check_photos:
            readable, photo_problem = check_photo_readable(student.photo_path)
            if not readable:
                push('student', student.id, employee_no, student.full_name, group_name,
                     student.status, 'photo_broken', 'Фото есть, но терминал его не примет',
                     'photo_broken', True, student.photo_path, photo_problem or '', 0,
                     student.tariff_id, student.tariff.name if student.tariff else '')
                continue

        counters['in_terminal'] += 1

    for user in User.query.order_by(User.full_name.asc()).all():
        counters['total_people'] += 1
        employee_no = '900000{}'.format(user.id)
        staff_name = user.full_name or user.username
        photo_url = build_photo_url(user.photo_path)
        if not user.is_active:
            push('staff', user.id, employee_no, staff_name, 'Сотрудники клуба',
                 'inactive', 'staff_inactive', ACCESS_REASON_LABELS['staff_inactive'], 'inactive',
                 bool(photo_url), user.photo_path)
            continue
        if not photo_url:
            push('staff', user.id, employee_no, staff_name, 'Сотрудники клуба',
                 'active', 'no_photo', ACCESS_REASON_LABELS['no_photo'], 'no_photo',
                 False, user.photo_path)
            continue
        failure = sync_failures.get(employee_no)
        if failure:
            push('staff', user.id, employee_no, staff_name, 'Сотрудники клуба',
                 'active', 'sync_error', 'Ошибка записи в терминал', 'sync_error',
                 True, user.photo_path, failure)
            continue
        if check_photos:
            readable, photo_problem = check_photo_readable(user.photo_path)
            if not readable:
                push('staff', user.id, employee_no, staff_name, 'Сотрудники клуба',
                     'active', 'photo_broken', 'Фото есть, но терминал его не примет', 'photo_broken',
                     True, user.photo_path, photo_problem or '')
                continue
        counters['in_terminal'] += 1

    by_category = {}
    by_reason = {}
    for item in items:
        by_category[item['category']] = by_category.get(item['category'], 0) + 1
        key = (item['reason'], item['reason_label'])
        by_reason[key] = by_reason.get(key, 0) + 1

    return jsonify({
        'success': True,
        'generated_at': get_local_datetime().isoformat(),
        'month': today.month,
        'year': today.year,
        'access_payment_policy': access_policy,
        'summary': {
            'total_people': counters['total_people'],
            'in_terminal': counters['in_terminal'],
            'missing': len(items),
            'by_category': [
                {
                    'category': key,
                    'label': HIK_MISSING_CATEGORY_LABELS.get(key, key),
                    'count': value,
                }
                for key, value in sorted(by_category.items(), key=lambda pair: -pair[1])
            ],
            'by_reason': [
                {'reason': key[0], 'label': key[1], 'count': value}
                for key, value in sorted(by_reason.items(), key=lambda pair: -pair[1])
            ],
        },
        'items': items,
    })


MONTH_NAMES_RU = [
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
]

STUDENT_STATUS_LABELS = {
    'active': 'Активен',
    'inactive': 'Неактивен',
    'archived': 'В архиве',
    'blacklist': 'Черный список',
}


def student_status_label(status):
    return STUDENT_STATUS_LABELS.get(status, status or '-')


def ensure_terminal_face_state_table():
    try:
        inspector = db.inspect(db.engine)
        if 'terminal_face_state' not in inspector.get_table_names():
            TerminalFaceState.__table__.create(db.engine)
            print('✓ Создана таблица terminal_face_state')
    except Exception as exc:
        print(f'ensure_terminal_face_state_table failed: {type(exc).__name__}: {exc}')


def get_reported_terminal_devices():
    """Терминалы, о которых bridge уже присылал состояние лиц."""
    try:
        ensure_terminal_face_state_table()
        rows = db.session.query(
            TerminalFaceState.device_name,
            func.max(TerminalFaceState.device_label)
        ).group_by(TerminalFaceState.device_name).all()
    except Exception as exc:
        print(f'get_reported_terminal_devices failed: {type(exc).__name__}: {exc}')
        return []
    return [
        {'device_name': name, 'device_label': label or deviceless_label(name)}
        for name, label in sorted(rows, key=lambda row: row[0] or '')
    ]


def get_student_terminal_face_state(student_id, employee_no=None, devices=None):
    """Что реально лежит в терминалах по данным bridge.

    Возвращаем строку по каждому известному терминалу: если ученика там нет,
    это осознанное "нет фото", а не отсутствие данных. Пустой список означает,
    что bridge еще ни разу не отчитывался.
    """
    employee_no = str(employee_no or student_id)
    devices = get_reported_terminal_devices() if devices is None else devices
    if not devices:
        return []
    try:
        ensure_terminal_face_state_table()
        rows = {
            row.device_name: row
            for row in TerminalFaceState.query.filter_by(employee_no=employee_no).all()
        }
    except Exception as exc:
        print(f'get_student_terminal_face_state failed: {type(exc).__name__}: {exc}')
        return []
    result = []
    for device in devices:
        row = rows.get(device['device_name'])
        result.append({
            'device_name': device['device_name'],
            'device_label': device['device_label'],
            'has_face': bool(row and row.has_face),
            'updated_at': row.updated_at.isoformat() if row and row.updated_at else None,
        })
    return result


def deviceless_label(device_name):
    if device_name == 'entry':
        return 'Вход'
    if device_name == 'exit':
        return 'Выход'
    return device_name or 'Терминал'


def get_terminal_face_state_bulk(employee_numbers):
    """employee_no -> состояние по каждому известному терминалу."""
    result = {}
    numbers = [str(value) for value in employee_numbers if value is not None]
    devices = get_reported_terminal_devices()
    if not numbers or not devices:
        return result
    try:
        ensure_terminal_face_state_table()
        rows = TerminalFaceState.query.filter(TerminalFaceState.employee_no.in_(numbers)).all()
    except Exception as exc:
        print(f'get_terminal_face_state_bulk failed: {type(exc).__name__}: {exc}')
        return result

    by_person = {}
    for row in rows:
        by_person.setdefault(row.employee_no, {})[row.device_name] = row

    for employee_no in numbers:
        person_rows = by_person.get(employee_no, {})
        result[employee_no] = [
            {
                'device_name': device['device_name'],
                'device_label': device['device_label'],
                'has_face': bool(person_rows.get(device['device_name']) and person_rows[device['device_name']].has_face),
            }
            for device in devices
        ]
    return result


@app.route('/api/hikvision/face-state', methods=['POST'])
def hikvision_face_state():
    """Bridge сообщает, чьи лица реально записаны в каждый терминал."""
    if not check_bridge_auth():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    ensure_terminal_face_state_table()
    data = request.get_json(silent=True) or {}
    device_name = str(data.get('device_name') or '').strip()[:64]
    device_label = str(data.get('device_label') or '').strip()[:120]
    entries = data.get('entries')
    if not device_name or not isinstance(entries, list):
        return jsonify({'success': False, 'message': 'device_name и entries обязательны'}), 400

    now = get_local_datetime()
    incoming = {}
    for entry in entries[:5000]:
        if not isinstance(entry, dict):
            continue
        employee_no = str(entry.get('employeeNo') or entry.get('employee_no') or '').strip()[:32]
        if not employee_no:
            continue
        incoming[employee_no] = {
            'has_face': bool(entry.get('hasFace', entry.get('has_face', True))),
            'photo_hash': str(entry.get('photoHash') or entry.get('photo_hash') or '')[:64],
        }

    existing = {
        row.employee_no: row
        for row in TerminalFaceState.query.filter_by(device_name=device_name).all()
    }

    for employee_no, values in incoming.items():
        row = existing.get(employee_no)
        if not row:
            row = TerminalFaceState(employee_no=employee_no, device_name=device_name)
            db.session.add(row)
        row.device_label = device_label or deviceless_label(device_name)
        row.has_face = values['has_face']
        row.photo_hash = values['photo_hash']
        row.updated_at = now

    if data.get('full_snapshot'):
        # Полная синхронизация: кого bridge не прислал, того в терминале нет.
        for employee_no, row in existing.items():
            if employee_no not in incoming:
                db.session.delete(row)

    db.session.commit()
    return jsonify({'success': True, 'saved': len(incoming), 'device_name': device_name})


def get_student_debt_months(student, settings=None, today=None):
    """Разбор долга по месяцам: за какие месяцы и сколько не хватает."""
    settings = settings or get_club_settings_instance()
    today = today or get_local_date()
    if not student or not student.tariff or student.club_funded:
        return []

    start_year, start_month = get_student_debt_start_pair(student, settings, today)
    if (start_year, start_month) > (today.year, today.month):
        return []

    rows = db.session.query(
        Payment.payment_year,
        Payment.payment_month,
        func.coalesce(func.sum(Payment.amount_paid), 0)
    ).filter(
        Payment.student_id == student.id,
        Payment.payment_year.isnot(None),
        Payment.payment_month.isnot(None)
    ).group_by(Payment.payment_year, Payment.payment_month).all()
    paid_by_month = {(year, month): float(total or 0) for year, month, total in rows}

    tariff_price = float(student.tariff.price or 0)
    min_lessons = get_min_lessons_for_debt(settings)
    attendance_counts = get_attendance_counts_by_month([student.id], start_year) if min_lessons else {}
    discount_months = get_discount_months([student.id], start_year)
    months = []
    for year, month in iter_month_pairs(start_year, start_month, today.year, today.month):
        paid = paid_by_month.get((year, month), 0)
        due = get_student_month_due(student, year, month, tariff_price)
        debt = max(0, due - paid)
        if debt <= 0:
            continue
        if not month_is_chargeable(student.id, year, month, attendance_counts, min_lessons):
            continue
        if (student.id, year, month) in discount_months:
            continue
        months.append({
            'year': year,
            'month': month,
            'label': f'{month:02d}.{year}',
            'month_name': MONTH_NAMES_RU[month - 1] if 1 <= month <= 12 else str(month),
            'tariff_price': due,
            'paid': paid,
            'debt': debt,
            'is_current': bool(year == today.year and month == today.month),
        })
    return months


MONTH_SHORT_RU = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
                  'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']


def get_student_year_months(student, settings=None, today=None, year=None):
    """Календарь оплат за год: что оплачено, что нет, что еще не наступило."""
    settings = settings or get_club_settings_instance()
    today = today or get_local_date()
    year = int(year or today.year)

    rows = db.session.query(
        Payment.payment_month,
        func.coalesce(func.sum(Payment.amount_paid), 0),
        func.max(Payment.payment_date),
        func.count(Payment.id)
    ).filter(
        Payment.student_id == student.id,
        Payment.payment_year == year,
        Payment.payment_month.isnot(None)
    ).group_by(Payment.payment_month).all()
    paid_by_month = {int(month): float(total or 0) for month, total, _, _ in rows}
    # Когда именно платили за этот месяц: показываем в плитке
    paid_at_by_month = {
        int(month): {'date': last_date, 'count': int(count or 0)}
        for month, _, last_date, count in rows
    }

    tariff_price = float(student.tariff.price or 0) if student.tariff else 0
    start_year, start_month = get_student_debt_start_pair(student, settings, today)

    min_lessons = get_min_lessons_for_debt(settings)
    attendance_counts = get_attendance_counts_by_month([student.id], year) if min_lessons else {}
    discount_months = get_discount_months([student.id], year)

    months = []
    for month in range(1, 13):
        paid = paid_by_month.get(month, 0)
        due = get_student_month_due(student, year, month, tariff_price)
        visits = attendance_counts.get((student.id, year, month), 0)
        if (year, month) > (today.year, today.month):
            state = 'future'
        elif (year, month) < (start_year, start_month):
            state = 'before_start'
        elif student.club_funded:
            state = 'paid'
        elif (student.id, year, month) in discount_months:
            state = 'discount'
        elif paid <= 0 and not month_is_chargeable(student.id, year, month, attendance_counts, min_lessons):
            state = 'no_lessons'
        elif due <= 0:
            state = 'no_tariff' if tariff_price <= 0 else 'paid'
        elif paid >= due:
            state = 'paid'
        elif paid > 0:
            state = 'partial'
        else:
            state = 'debt'

        months.append({
            'month': month,
            'short': MONTH_SHORT_RU[month - 1],
            'name': MONTH_NAMES_RU[month - 1],
            'paid': paid,
            'due': due,
            'is_discount': bool((student.id, year, month) in discount_months),
            'visits': visits,
            'paid_at': (
                paid_at_by_month[month]['date'].strftime('%d.%m.%Y')
                if paid_at_by_month.get(month) and paid_at_by_month[month]['date'] else ''
            ),
            'paid_day': (
                paid_at_by_month[month]['date'].day
                if paid_at_by_month.get(month) and paid_at_by_month[month]['date'] else None
            ),
            'payments_count': paid_at_by_month.get(month, {}).get('count', 0),
            'debt': max(0, due - paid) if state in {'debt', 'partial'} else 0,
            'min_lessons': min_lessons,
            'state': state,
            'is_current': bool(year == today.year and month == today.month),
        })
    return {'year': year, 'months': months}


def build_student_access_details(student, settings=None, today=None, paid_map=None, payment_date_paid_map=None):
    """Подробный разбор: пройдет ли ученик через турникет и почему."""
    settings = settings or get_club_settings_instance()
    today = today or get_local_date()
    if paid_map is None:
        paid_map = get_month_paid_map(today.year, today.month)
    if payment_date_paid_map is None:
        payment_date_paid_map = get_payment_date_paid_map(today.year, today.month)

    access = build_student_access_payload(student, settings, paid_map, payment_date_paid_map, today)
    debt_months = get_student_debt_months(student, settings, today)
    current = [item for item in debt_months if item['is_current']]
    previous = [item for item in debt_months if not item['is_current']]

    min_lessons = get_min_lessons_for_debt(settings)
    visits_now = 0
    if min_lessons:
        visits_now = get_attendance_counts_by_month([student.id], today.year).get(
            (student.id, today.year, today.month), 0
        )

    explanation = []
    if access['allowed']:
        if access['reason'] == 'club_funded':
            explanation.append('Клубное финансирование, оплата не проверяется.')
        elif access['reason'] == 'no_tariff':
            explanation.append('Тариф не указан, блокировка по оплате не применяется.')
        elif access['reason'] == 'grace_period':
            explanation.append(f"Идет льготный период, блокировка начинается с {access['block_day']} числа.")
        elif access['reason'] == 'no_lessons_this_month':
            # Самый частый повод удивиться "почему он проходит"
            explanation.append(
                f'За {today.month:02d}.{today.year} посещений {visits_now}, '
                f'а месяц считается долговым с {min_lessons}. Поэтому оплату за него пока не ждем.'
            )
        elif access['reason'] == 'month_discounted':
            explanation.append('Текущий месяц закрыт скидкой: остаток долгом не считается.')
        else:
            explanation.append('Оплата в порядке.')

        if previous:
            explanation.append(
                'Прошлые месяцы без оплаты, но и без занятий, поэтому долгом не считаются: '
                + ', '.join(item['label'] for item in previous) + '.'
            )
        if not access['has_photo']:
            explanation.append('Но фото для Face ID нет, поэтому в терминал ученик не попадет.')
    elif access['reason'] == 'inactive':
        explanation.append(
            f'Ученик со статусом «{student_status_label(student.status)}» в терминалы не выгружается.'
        )
    elif access['reason'] == 'no_photo':
        explanation.append('Нет фото для Face ID: записывать в терминал нечего.')
    else:
        if previous:
            explanation.append(
                'Долг за прошлые месяцы: ' + ', '.join(item['label'] for item in previous) + '.'
            )
        if current:
            explanation.append(f"Текущий месяц {current[0]['label']} оплачен не полностью.")
        if not previous and not current:
            explanation.append(access['reason_label'])
        if previous and access['max_debt_months'] is not None:
            explanation.append(f"Разрешено не более {access['max_debt_months']} месяцев долга подряд.")

    return {
        'will_pass': access['can_sync_to_turnstile'],
        'allowed': access['allowed'],
        'reason': access['reason'],
        'reason_label': access['reason_label'],
        'has_photo': access['has_photo'],
        'debt': access['debt'],
        'total_debt': sum(item['debt'] for item in debt_months),
        'debt_months': debt_months,
        'debt_months_count': len(debt_months),
        'previous_debt_months': previous,
        'current_month_debt': current[0]['debt'] if current else 0,
        'max_debt_months': access['max_debt_months'],
        'block_day': access['block_day'],
        'payment_policy': access['payment_policy'],
        'tariff_price': access['tariff_price'],
        'explanation': explanation,
    }


def ensure_student_logs_table():
    try:
        inspector = db.inspect(db.engine)
        if 'student_logs' not in inspector.get_table_names():
            StudentLog.__table__.create(db.engine)
            print('✓ Создана таблица student_logs')
    except Exception as exc:
        print(f'ensure_student_logs_table failed: {type(exc).__name__}: {exc}')


def current_actor():
    """Кто сейчас выполняет действие. Может не быть, если это планировщик."""
    try:
        if current_user and getattr(current_user, 'is_authenticated', False):
            return current_user.id, (current_user.full_name or current_user.username or '')
    except Exception:
        pass
    return None, 'Система'


def log_student_event(student_id, action, title, details=None, actor=None):
    """Записать событие в историю ученика. Коммит делает вызывающий код."""
    if not student_id:
        return None
    try:
        ensure_student_logs_table()
        actor_id, actor_name = actor if actor else current_actor()
        if isinstance(details, (list, tuple)):
            details = '\n'.join(str(item) for item in details if item)
        entry = StudentLog(
            student_id=int(student_id),
            action=str(action)[:40],
            title=str(title)[:200],
            details=(details or None),
            actor_id=actor_id,
            actor_name=(actor_name or '')[:120],
        )
        db.session.add(entry)
        return entry
    except Exception as exc:
        print(f'log_student_event failed: {type(exc).__name__}: {exc}')
        return None


def format_money_ru(value):
    try:
        return f'{int(round(float(value or 0))):,}'.replace(',', ' ')
    except (TypeError, ValueError):
        return str(value)


STUDENT_FORM_FONT = 'StudentForm'
STUDENT_FORM_FONT_BOLD = 'StudentFormBold'
_student_form_fonts_ready = False


def ensure_student_form_fonts():
    """Регистрируем шрифт с кириллицей: стандартные шрифты PDF ее не умеют."""
    global _student_form_fonts_ready
    if _student_form_fonts_ready:
        return True
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        vendor = os.path.join(app.static_folder, 'vendor', 'onest-ttf')
        regular = os.path.join(vendor, 'Onest-VariableFont_wght.ttf')
        bold = os.path.join(vendor, 'Manrope.ttf')
        if not os.path.isfile(regular):
            return False
        pdfmetrics.registerFont(TTFont(STUDENT_FORM_FONT, regular))
        pdfmetrics.registerFont(TTFont(STUDENT_FORM_FONT_BOLD, bold if os.path.isfile(bold) else regular))
        _student_form_fonts_ready = True
        return True
    except Exception as exc:
        print(f'ensure_student_form_fonts failed: {type(exc).__name__}: {exc}')
        return False


def get_form_photo_reader(photo_path):
    """Уменьшенное фото для анкеты. На 400 учеников иначе выходит файл в десятки МБ."""
    source_path = resolve_static_photo_file(photo_path)
    if not source_path:
        return None
    try:
        from reportlab.lib.utils import ImageReader
        with Image.open(source_path) as raw:
            image = ImageOps.exif_transpose(raw).convert('RGB')
            image.thumbnail((320, 420), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, 'JPEG', quality=72, optimize=True)
        buffer.seek(0)
        return ImageReader(buffer)
    except Exception as exc:
        print(f'form photo failed: {type(exc).__name__}: {exc}')
        return None


def draw_student_form_page(canvas, student, settings=None):
    """Одна страница анкеты: что знаем — печатаем, остальное — линейки для ручки."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    settings = settings or get_club_settings_instance()
    width, height = A4
    left = 15 * mm
    right = width - 15 * mm
    y = height - 16 * mm

    club_name = getattr(settings, 'club_name', None) or 'Футбольная школа'

    canvas.setFont(STUDENT_FORM_FONT_BOLD, 16)
    canvas.drawString(left, y, club_name)
    canvas.setFont(STUDENT_FORM_FONT, 10.5)
    canvas.setFillColorRGB(0.42, 0.45, 0.5)
    canvas.drawRightString(right, y, 'Анкета ученика')
    canvas.setFillColorRGB(0, 0, 0)

    y -= 6 * mm
    canvas.setLineWidth(0.8)
    canvas.setStrokeColorRGB(1, 0.54, 0)
    canvas.line(left, y, right, y)
    canvas.setStrokeColorRGB(0.8, 0.82, 0.85)

    # --- Фото и уже известные данные ---
    y -= 8 * mm
    photo_w, photo_h = 32 * mm, 42 * mm
    photo_x, photo_top = left, y
    photo_reader = get_form_photo_reader(student.photo_path)
    drawn = False
    if photo_reader:
        try:
            canvas.drawImage(photo_reader, photo_x, photo_top - photo_h,
                             width=photo_w, height=photo_h, preserveAspectRatio=True,
                             anchor='c', mask='auto')
            drawn = True
        except Exception as exc:
            print(f'student form photo failed: {type(exc).__name__}: {exc}')
    canvas.rect(photo_x, photo_top - photo_h, photo_w, photo_h, stroke=1, fill=0)
    if not drawn:
        canvas.setFont(STUDENT_FORM_FONT, 9)
        canvas.setFillColorRGB(0.6, 0.63, 0.67)
        canvas.drawCentredString(photo_x + photo_w / 2, photo_top - photo_h / 2, 'Фото')
        canvas.setFillColorRGB(0, 0, 0)

    info_x = left + photo_w + 8 * mm
    info_y = photo_top - 4 * mm
    canvas.setFont(STUDENT_FORM_FONT_BOLD, 15)
    canvas.drawString(info_x, info_y, student.full_name or '')

    canvas.setFont(STUDENT_FORM_FONT, 10)
    info_y -= 7 * mm
    known = [
        ('Группа', student.group.name if student.group else 'Без группы'),
        ('Номер ученика', student.student_number or '—'),
        ('Тариф', student.tariff.name if student.tariff else 'Не указан'),
        ('Дата поступления', student.admission_date.strftime('%d.%m.%Y') if student.admission_date else '—'),
    ]
    for label, value in known:
        canvas.setFillColorRGB(0.42, 0.45, 0.5)
        canvas.drawString(info_x, info_y, f'{label}:')
        canvas.setFillColorRGB(0, 0, 0)
        canvas.drawString(info_x + 38 * mm, info_y, str(value))
        info_y -= 6 * mm

    y = min(photo_top - photo_h, info_y) - 8 * mm

    def section(title, current_y):
        canvas.setFont(STUDENT_FORM_FONT_BOLD, 11)
        canvas.setFillColorRGB(1, 0.54, 0)
        canvas.drawString(left, current_y, title.upper())
        canvas.setFillColorRGB(0, 0, 0)
        return current_y - 6 * mm

    def field(label, value, current_y, col=0, width_mm=88):
        """Заполненное печатаем, пустое оставляем линейкой для ручки."""
        x = left if col == 0 else left + 92 * mm
        canvas.setFont(STUDENT_FORM_FONT, 8.5)
        canvas.setFillColorRGB(0.42, 0.45, 0.5)
        canvas.drawString(x, current_y, label)
        canvas.setFillColorRGB(0, 0, 0)
        line_y = current_y - 5.5 * mm
        canvas.setStrokeColorRGB(0.78, 0.8, 0.83)
        canvas.setLineWidth(0.6)
        canvas.line(x, line_y, x + width_mm * mm, line_y)
        text = '' if value in (None, '', '-') else str(value)
        if text:
            canvas.setFont(STUDENT_FORM_FONT, 10.5)
            canvas.drawString(x + 1.5 * mm, line_y + 1.6 * mm, text)
        return current_y

    def two_fields(left_pair, right_pair, current_y):
        field(left_pair[0], left_pair[1], current_y, col=0)
        if right_pair:
            field(right_pair[0], right_pair[1], current_y, col=1)
        return current_y - 12 * mm

    y = section('Данные ученика', y)
    y = two_fields(('Фамилия, имя, отчество', student.full_name),
                   ('Дата рождения', student.birth_year or ''), y)
    y = two_fields(('Телефон ученика', student.phone),
                   ('Телефон родителя', student.parent_phone), y)

    y = section('Родители', y - 2 * mm)
    y = two_fields(('ФИО матери', ''), ('Телефон матери', ''), y)
    y = two_fields(('ФИО отца', ''), ('Телефон отца', ''), y)
    y = two_fields(('Кем приходится плательщик', ''), ('Дополнительный телефон', ''), y)

    y = section('Адрес', y - 2 * mm)
    y = two_fields(('Город', student.city), ('Район', student.district), y)
    y = two_fields(('Улица', student.street), ('Дом, квартира', student.house_number), y)

    y = section('Паспорт или свидетельство о рождении', y - 2 * mm)
    y = two_fields(('Серия и номер', ' '.join(filter(None, [student.passport_series, student.passport_number]))),
                   ('Кем выдан', student.passport_issued_by), y)
    y = two_fields(('Дата выдачи', student.passport_issue_date.strftime('%d.%m.%Y') if student.passport_issue_date else ''),
                   ('Срок действия', student.passport_expiry_date.strftime('%d.%m.%Y') if student.passport_expiry_date else ''), y)

    y = section('Параметры и экипировка', y - 2 * mm)
    y = two_fields(('Рост, см', student.height), ('Вес, кг', student.weight), y)
    side = 'Левша' if student.dominant_side == 'left' else 'Правша' if student.dominant_side == 'right' else ''
    y = two_fields(('Ведущая нога', side), ('Размер футболки', student.jersey_size), y)
    y = two_fields(('Размер шорт', student.shorts_size), ('Размер бутс', student.boots_size), y)

    y = section('Здоровье', y - 2 * mm)
    y = two_fields(('Хронические заболевания, аллергии', ''), ('Группа крови', ''), y)
    y = two_fields(('Кому звонить в экстренном случае', ''), ('Телефон', ''), y)

    # --- Подписи ---
    y -= 4 * mm
    canvas.setFont(STUDENT_FORM_FONT, 8.5)
    canvas.setFillColorRGB(0.42, 0.45, 0.5)
    canvas.drawString(left, y, 'Данные заполняет родитель или законный представитель.')
    canvas.setFillColorRGB(0, 0, 0)

    y -= 12 * mm
    canvas.setStrokeColorRGB(0.78, 0.8, 0.83)
    canvas.line(left, y, left + 70 * mm, y)
    canvas.line(right - 60 * mm, y, right, y)
    canvas.setFont(STUDENT_FORM_FONT, 8.5)
    canvas.setFillColorRGB(0.42, 0.45, 0.5)
    canvas.drawString(left, y - 4.5 * mm, 'Подпись родителя')
    canvas.drawString(right - 60 * mm, y - 4.5 * mm, 'Дата заполнения')
    canvas.setFillColorRGB(0, 0, 0)

    canvas.setFont(STUDENT_FORM_FONT, 7.5)
    canvas.setFillColorRGB(0.62, 0.65, 0.69)
    canvas.drawString(left, 10 * mm, f'ID ученика: {student.id}')
    canvas.drawRightString(right, 10 * mm,
                           f'Сформировано {get_local_datetime().strftime("%d.%m.%Y")}')
    canvas.setFillColorRGB(0, 0, 0)


def build_students_form_pdf(students, settings=None):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdf_canvas

    settings = settings or get_club_settings_instance()
    buffer = io.BytesIO()
    pdf = pdf_canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle('Анкеты учеников')
    for index, student in enumerate(students):
        if index:
            pdf.showPage()
        draw_student_form_page(pdf, student, settings)
    pdf.save()
    buffer.seek(0)
    return buffer


@app.route('/api/students/<int:student_id>/form.pdf', methods=['GET'])
@login_required
def student_form_pdf(student_id):
    """Анкета одного ученика для печати и заполнения от руки."""
    if not ensure_student_form_fonts():
        return jsonify({'success': False, 'message': 'Не удалось подготовить шрифты для PDF'}), 500

    student = Student.query.options(
        joinedload(Student.group), joinedload(Student.tariff)
    ).filter(Student.id == student_id).first()
    if not student:
        return jsonify({'success': False, 'message': 'Ученик не найден'}), 404

    buffer = build_students_form_pdf([student])
    filename = f'anketa_{student.id}.pdf'
    return send_file(buffer, mimetype='application/pdf',
                     as_attachment=False, download_name=filename)


@app.route('/api/students/forms.pdf', methods=['GET'])
@login_required
def students_forms_pdf():
    """Анкеты пачкой: вся школа, отдельная группа или результат поиска."""
    if not ensure_student_form_fonts():
        return jsonify({'success': False, 'message': 'Не удалось подготовить шрифты для PDF'}), 500

    group_id = request.args.get('group_id', type=int)
    search = (request.args.get('q') or '').strip().lower()
    include_archived = request.args.get('include_archived') in {'1', 'true', 'yes'}

    query = Student.query.options(joinedload(Student.group), joinedload(Student.tariff))
    if not include_archived:
        query = query.filter(Student.status == 'active')
    if group_id:
        query = query.filter(Student.group_id == group_id)
    if search:
        like = f'%{search}%'
        query = query.filter(or_(
            func.lower(Student.full_name).like(like),
            func.lower(func.coalesce(Student.student_number, '')).like(like),
        ))

    students = query.outerjoin(Group).order_by(Group.name.asc(), Student.full_name.asc()).all()
    if not students:
        return jsonify({'success': False, 'message': 'Учеников не найдено'}), 404
    if len(students) > 600:
        return jsonify({
            'success': False,
            'message': f'Слишком много учеников за раз ({len(students)}). Выгружайте по группам.'
        }), 400

    buffer = build_students_form_pdf(students)
    name = 'ankety_vse.pdf' if not group_id else f'ankety_group_{group_id}.pdf'
    return send_file(buffer, mimetype='application/pdf', as_attachment=False, download_name=name)


@app.route('/api/groups/<int:group_id>/forms.pdf', methods=['GET'])
@login_required
def group_forms_pdf(group_id):
    """Анкеты всей группы одним файлом: по странице на ученика."""
    if not ensure_student_form_fonts():
        return jsonify({'success': False, 'message': 'Не удалось подготовить шрифты для PDF'}), 500

    group = db.session.get(Group, group_id)
    students = Student.query.options(
        joinedload(Student.group), joinedload(Student.tariff)
    ).filter(
        Student.group_id == group_id,
        Student.status == 'active'
    ).order_by(Student.full_name.asc()).all()
    if not students:
        return jsonify({'success': False, 'message': 'В группе нет активных учеников'}), 404

    buffer = build_students_form_pdf(students)
    safe_name = re.sub(r'[^\w\-]+', '_', (group.name if group else f'group_{group_id}'))
    return send_file(buffer, mimetype='application/pdf',
                     as_attachment=False, download_name=f'ankety_{safe_name}.pdf')


@app.route('/api/students/<int:student_id>/logs', methods=['GET'])
@login_required
def get_student_logs(student_id):
    """История изменений по ученику."""
    ensure_student_logs_table()
    limit = min(max(request.args.get('limit', 200, type=int) or 200, 1), 500)
    rows = StudentLog.query.filter_by(student_id=student_id) \
        .order_by(StudentLog.created_at.desc(), StudentLog.id.desc()) \
        .limit(limit).all()
    return jsonify({
        'success': True,
        'items': [
            {
                'id': row.id,
                'action': row.action,
                'title': row.title,
                'details': (row.details or '').split('\n') if row.details else [],
                'actor': row.actor_name or 'Система',
                'created_at': row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    })


@app.route('/api/students/<int:student_id>/access-details', methods=['GET'])
@login_required
def student_access_details(student_id):
    student = Student.query.options(joinedload(Student.tariff)).filter(Student.id == student_id).first()
    if not student:
        return jsonify({'success': False, 'message': 'Ученик не найден'}), 404
    return jsonify({
        'success': True,
        'student_id': student.id,
        'status': student.status,
        'status_label': student_status_label(student.status),
        'access': build_student_access_details(student),
        'terminals': get_student_terminal_face_state(student.id),
        'year_payments': get_student_year_months(student),
    })


def collect_student_month_plan(student, settings=None, today=None):
    """Сколько ученик должен и сколько внес по каждому месяцу от начала долга."""
    settings = settings or get_club_settings_instance()
    today = today or get_local_date()
    start_year, start_month = get_student_debt_start_pair(student, settings, today)
    if (start_year, start_month) > (today.year, today.month):
        return []

    tariff_price = float(student.tariff.price or 0) if student.tariff else 0
    rows = db.session.query(
        Payment.payment_year,
        Payment.payment_month,
        func.coalesce(func.sum(Payment.amount_paid), 0)
    ).filter(
        Payment.student_id == student.id,
        Payment.payment_year.isnot(None),
        Payment.payment_month.isnot(None)
    ).group_by(Payment.payment_year, Payment.payment_month).all()
    paid_by_month = {(year, month): float(total or 0) for year, month, total in rows}

    plan = []
    for year, month in iter_month_pairs(start_year, start_month, today.year, today.month):
        plan.append({
            'year': year,
            'month': month,
            'due': get_student_month_due(student, year, month, tariff_price),
            'paid': paid_by_month.get((year, month), 0),
        })
    return plan


def redistribute_student_payments(student, settings=None, today=None, actor_id=None):
    """Закрыть старые месяцы свежими деньгами.

    Общая сумма оплат и даты платежей не меняются: деньги просто
    переносятся на более ранние месяцы, чтобы долг не размазывался
    по нескольким месяцам, а собрался в самых свежих.
    """
    settings = settings or get_club_settings_instance()
    today = today or get_local_date()
    result = {
        'student_id': student.id,
        'full_name': student.full_name,
        'moved': 0.0,
        'moves': [],
        'debt_months_before': 0,
        'debt_months_after': 0,
        'changed': False,
    }

    if student.club_funded or not student.tariff:
        return result

    plan = collect_student_month_plan(student, settings, today)
    if not plan:
        return result

    result['debt_months_before'] = sum(1 for item in plan if item['paid'] < item['due'])

    # Раскладываем всю внесенную сумму по месяцам от старых к новым
    available = sum(item['paid'] for item in plan)
    target = {}
    for item in plan:
        share = min(item['due'], available)
        target[(item['year'], item['month'])] = share
        available -= share
    if available > 0:
        # Переплата остается в самом свежем месяце
        last = plan[-1]
        target[(last['year'], last['month'])] += available

    result['debt_months_after'] = sum(
        1 for item in plan if target[(item['year'], item['month'])] < item['due']
    )

    # Что нужно снять с месяца, а что доложить
    surplus = []
    deficit = []
    for item in plan:
        key = (item['year'], item['month'])
        diff = round(target[key] - item['paid'], 2)
        if diff < -0.009:
            surplus.append([item['year'], item['month'], -diff])
        elif diff > 0.009:
            deficit.append([item['year'], item['month'], diff])

    if not surplus or not deficit:
        return result

    payments = Payment.query.filter(
        Payment.student_id == student.id,
        Payment.payment_year.isnot(None),
        Payment.payment_month.isnot(None)
    ).order_by(Payment.payment_date.desc(), Payment.id.desc()).all()

    def payments_of(year, month):
        return [p for p in payments if p.payment_year == year and p.payment_month == month]

    for src_year, src_month, amount_to_move in surplus:
        remaining = amount_to_move
        for payment in payments_of(src_year, src_month):
            if remaining <= 0.009:
                break
            if not deficit:
                break
            take = min(float(payment.amount_paid or 0), remaining)
            if take <= 0.009:
                continue

            while take > 0.009 and deficit:
                dst_year, dst_month, need = deficit[0]
                chunk = min(take, need)

                if chunk >= float(payment.amount_paid or 0) - 0.009:
                    # Платеж целиком переезжает в другой месяц
                    payment.payment_year = dst_year
                    payment.payment_month = dst_month
                    moved_payment = payment
                else:
                    payment.amount_paid = float(payment.amount_paid) - chunk
                    moved_payment = Payment(
                        student_id=student.id,
                        tariff_id=payment.tariff_id,
                        amount_paid=chunk,
                        amount_due=0,
                        lessons_added=0,
                        is_full_payment=False,
                        payment_date=payment.payment_date,
                        tariff_name=payment.tariff_name,
                        payment_month=dst_month,
                        payment_year=dst_year,
                        payment_type=payment.payment_type,
                        created_by=actor_id,
                    )
                    db.session.add(moved_payment)

                note = f'Перенос {int(chunk)} сум с {src_month:02d}.{src_year} на {dst_month:02d}.{dst_year}'
                moved_payment.notes = f'{(moved_payment.notes or "").strip()} {note}'.strip()

                result['moves'].append({
                    'from': f'{src_month:02d}.{src_year}',
                    'to': f'{dst_month:02d}.{dst_year}',
                    'amount': chunk,
                })
                result['moved'] += chunk

                need -= chunk
                take -= chunk
                remaining -= chunk
                if need <= 0.009:
                    deficit.pop(0)
                else:
                    deficit[0][2] = need

    result['changed'] = bool(result['moves'])
    if result['changed']:
        log_student_event(
            student.id, 'payments_redistributed',
            f"Оплаты перенесены на ранние месяцы: {format_money_ru(result['moved'])} сум",
            [f"{item['amount'] and format_money_ru(item['amount'])} сум: {item['from']} → {item['to']}"
             for item in result['moves']]
            + [f"Месяцев с долгом: {result['debt_months_before']} → {result['debt_months_after']}"]
        )
    return result


@app.route('/api/students/bulk/redistribute-payments', methods=['POST'])
@login_required
def bulk_redistribute_payments():
    """Закрыть старые долги уже внесенными деньгами у выбранных учеников."""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    data = request.get_json(silent=True) or {}
    student_ids = [int(value) for value in (data.get('student_ids') or []) if str(value).isdigit()]
    if not student_ids:
        return jsonify({'success': False, 'message': 'Не выбрано ни одного ученика'}), 400

    settings = get_club_settings_instance()
    today = get_local_date()
    students = Student.query.options(joinedload(Student.tariff)).filter(Student.id.in_(student_ids)).all()

    results = []
    changed_students = []
    for student in students:
        outcome = redistribute_student_payments(student, settings, today, actor_id=current_user.id)
        results.append(outcome)
        if outcome['changed']:
            changed_students.append(student)

    if changed_students:
        db.session.commit()
        for student in changed_students:
            queue_hikvision_person('student', student.id, 'payments_redistributed')
        db.session.commit()
    else:
        db.session.rollback()

    total_moved = sum(item['moved'] for item in results)
    freed = sum(
        max(0, item['debt_months_before'] - item['debt_months_after'])
        for item in results
    )
    return jsonify({
        'success': True,
        'processed': len(results),
        'changed': len(changed_students),
        'total_moved': total_moved,
        'freed_months': freed,
        'results': [item for item in results if item['changed']],
        'message': (
            f'Перераспределено {int(total_moved):,} сум у {len(changed_students)} из {len(results)} учеников, '
            f'закрыто месяцев долга: {freed}'
        ).replace(',', ' ') if changed_students else 'Переносить нечего: оплаты уже разложены по месяцам'
    })


@app.route('/api/students/bulk/tariff', methods=['POST'])
@login_required
def bulk_change_tariff():
    """Сменить тариф сразу нескольким ученикам."""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    data = request.get_json(silent=True) or {}
    student_ids = [int(value) for value in (data.get('student_ids') or []) if str(value).isdigit()]
    if not student_ids:
        return jsonify({'success': False, 'message': 'Не выбрано ни одного ученика'}), 400

    tariff_id = data.get('tariff_id')
    tariff = None
    if tariff_id not in (None, '', 'null'):
        tariff = db.session.get(Tariff, int(tariff_id))
        if not tariff:
            return jsonify({'success': False, 'message': 'Тариф не найден'}), 404

    club_funded = data.get('club_funded')
    students = Student.query.options(joinedload(Student.tariff)).filter(Student.id.in_(student_ids)).all()
    for student in students:
        old_tariff = student.tariff.name if student.tariff else 'Без тарифа'
        old_price = float(student.tariff.price or 0) if student.tariff else 0
        new_tariff = tariff.name if tariff else 'Без тарифа'
        if old_tariff != new_tariff:
            log_student_event(
                student.id, 'tariff_changed',
                f'Тариф изменен: {old_tariff} → {new_tariff}',
                [f'Стоимость: {format_money_ru(old_price)} → '
                 f'{format_money_ru(float(tariff.price or 0) if tariff else 0)} сум']
            )
        student.tariff_id = tariff.id if tariff else None
        if tariff:
            student.tariff_type = tariff.name
        if club_funded is not None:
            student.club_funded = bool(club_funded)
        elif tariff and float(tariff.price or 0) == 0:
            # Бесплатный тариф означает, что занятия оплачивает клуб
            student.club_funded = True

    db.session.commit()

    # Пересчитываем допуск по новому тарифу: часть учеников уже не должники
    db.session.expire_all()
    settings = get_club_settings_instance()
    today = get_local_date()
    paid_map = get_month_paid_map(today.year, today.month)
    payment_date_paid_map = get_payment_date_paid_map(today.year, today.month)
    fresh = Student.query.options(joinedload(Student.tariff)).filter(Student.id.in_(student_ids)).all()
    debt_counts = get_debt_month_counts(fresh, settings, today, include_current=False)

    will_pass = []
    still_blocked = []
    for student in fresh:
        access = build_student_access_payload(
            student, settings, paid_map, payment_date_paid_map, today,
            debt_month_count=debt_counts.get(student.id)
        )
        target = will_pass if access['can_sync_to_turnstile'] else still_blocked
        target.append({
            'student_id': student.id,
            'full_name': student.full_name,
            'reason_label': access['reason_label'],
            'debt': access['debt'],
        })
        queue_hikvision_person('student', student.id, 'tariff_changed')
    db.session.commit()

    tariff_label = tariff.name if tariff else 'Без тарифа'
    message = f'Тариф «{tariff_label}» применен к {len(students)} ученикам'
    if will_pass:
        message += f'. Пройдут через турникет: {len(will_pass)}'
    if still_blocked:
        message += f', остаются закрытыми: {len(still_blocked)}'

    return jsonify({
        'success': True,
        'updated': len(students),
        'tariff': tariff_label,
        'will_pass': will_pass,
        'still_blocked': still_blocked,
        'message': message
    })


AUTO_ARCHIVE_MONTHS_DEFAULT = 0


def get_auto_archive_months(settings=None):
    """Через сколько месяцев без занятий ученик уходит в архив. 0 = не уходит."""
    settings = settings or get_club_settings_instance()
    try:
        value = int(getattr(settings, 'auto_archive_after_months', None) or 0)
    except (TypeError, ValueError):
        value = AUTO_ARCHIVE_MONTHS_DEFAULT
    return max(0, value)


def subtract_months(day, months):
    year = day.year
    month = day.month - int(months)
    while month <= 0:
        month += 12
        year -= 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last_day))


def find_students_to_auto_archive(settings=None, today=None):
    """Кого пора убрать в архив: не приходит дольше заданного срока."""
    settings = settings or get_club_settings_instance()
    today = today or get_local_date()
    months = get_auto_archive_months(settings)
    if not months:
        return []

    threshold = subtract_months(today, months)
    students = Student.query.filter(Student.status == 'active').all()
    if not students:
        return []

    last_visits = dict(
        db.session.query(Attendance.student_id, func.max(Attendance.date))
        .filter(Attendance.student_id.in_([student.id for student in students]))
        .group_by(Attendance.student_id)
        .all()
    )

    candidates = []
    for student in students:
        last_visit = last_visits.get(student.id)
        if last_visit:
            if last_visit >= threshold:
                continue
            reason = f'последнее занятие {last_visit.strftime("%d.%m.%Y")}'
        else:
            # Ни одного занятия: считаем от даты поступления
            started = student.admission_date
            if not started or started >= threshold:
                continue
            reason = f'занятий не было с момента поступления {started.strftime("%d.%m.%Y")}'
        candidates.append({
            'student': student,
            'student_id': student.id,
            'full_name': student.full_name,
            'group': student.group.name if student.group else '',
            'last_visit': last_visit.isoformat() if last_visit else None,
            'reason': reason,
        })
    return candidates


def run_auto_archive(settings=None, today=None, dry_run=False):
    """Перевести в архив тех, кто давно не приходит."""
    settings = settings or get_club_settings_instance()
    today = today or get_local_date()
    months = get_auto_archive_months(settings)
    candidates = find_students_to_auto_archive(settings, today)

    archived = []
    for item in candidates:
        student = item['student']
        if not dry_run:
            log_student_event(
                student.id, 'auto_archived',
                f'Автоархив: не приходил {months} мес. и больше',
                [item['reason']],
                actor=(None, 'Автоархив')
            )
            student.previous_status = student.status
            student.status = 'archived'
            student.archived_at = get_local_datetime()
        archived.append({
            'student_id': item['student_id'],
            'full_name': item['full_name'],
            'group': item['group'],
            'last_visit': item['last_visit'],
            'reason': item['reason'],
        })

    if archived and not dry_run:
        db.session.commit()
        for item in archived:
            queue_hikvision_person('student', item['student_id'], 'student_auto_archived',
                                   action='delete', employee_no=str(item['student_id']))
        db.session.commit()

    return {
        'months': months,
        'checked_at': get_local_datetime().isoformat(),
        'archived': archived,
        'count': len(archived),
        'dry_run': bool(dry_run),
    }


def auto_archive_job():
    """Ежедневная проверка. Работает только если срок задан в настройках."""
    with app.app_context():
        try:
            settings = get_club_settings_instance()
            if not get_auto_archive_months(settings):
                return
            result = run_auto_archive(settings)
            if result['count']:
                names = ', '.join(item['full_name'] for item in result['archived'][:10])
                print(f"Автоархив: {result['count']} учеников убраны в архив ({names})")
        except Exception as exc:
            db.session.rollback()
            print(f'Ошибка автоархива: {type(exc).__name__}: {exc}')


# Что можно скрыть в карточке ученика. Ключ -> подпись в настройках.
STUDENT_CARD_TABS = [
    ('payments', 'Вкладка «Оплаты»'),
    ('finances', 'Вкладка «Финансы»'),
    ('history', 'Вкладка «Награды»'),
    ('attendance', 'Вкладка «Посещения»'),
    ('changelog', 'Вкладка «История изменений»'),
]

STUDENT_CARD_BLOCKS = [
    ('turnstile', 'Блок «Турникет»'),
    ('year_payments', 'Блок «Оплаты по месяцам»'),
    ('facts', 'Плитки: тариф, баланс, баллы, в клубе с'),
    ('contacts', 'Блок «Контакты»'),
    ('cards', 'Блок «Карточки»'),
    ('params', 'Блок «Параметры»'),
    ('passport', 'Блок «Паспортные данные»'),
    ('address', 'Блок «Адрес»'),
    ('telegram', 'Блок «Telegram»'),
]


def get_student_card_sections(settings=None):
    """Какие вкладки и блоки показывать в карточке. По умолчанию все."""
    settings = settings or get_club_settings_instance()
    defaults = {key: True for key, _ in STUDENT_CARD_TABS}
    defaults.update({key: True for key, _ in STUDENT_CARD_BLOCKS})

    raw = getattr(settings, 'student_card_sections', None)
    if raw:
        try:
            saved = json.loads(raw)
            if isinstance(saved, dict):
                for key in defaults:
                    if key in saved:
                        defaults[key] = bool(saved[key])
        except (ValueError, TypeError):
            pass
    return defaults


def save_student_card_sections(settings, payload):
    known = {key for key, _ in STUDENT_CARD_TABS} | {key for key, _ in STUDENT_CARD_BLOCKS}
    clean = {key: bool(value) for key, value in (payload or {}).items() if key in known}
    settings.student_card_sections = json.dumps(clean, ensure_ascii=False)
    return clean


@app.route('/api/settings/student-card', methods=['GET'])
@login_required
def get_student_card_settings():
    settings = get_club_settings_instance()
    return jsonify({
        'success': True,
        'sections': get_student_card_sections(settings),
        'tabs': [{'key': key, 'label': label} for key, label in STUDENT_CARD_TABS],
        'blocks': [{'key': key, 'label': label} for key, label in STUDENT_CARD_BLOCKS],
    })


@app.route('/api/settings/student-card', methods=['POST'])
@login_required
def update_student_card_settings():
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    ensure_club_settings_columns()
    data = request.get_json(silent=True) or {}
    settings = get_club_settings_instance()
    saved = save_student_card_sections(settings, data.get('sections'))
    db.session.commit()
    hidden = sum(1 for value in get_student_card_sections(settings).values() if not value)
    return jsonify({
        'success': True,
        'sections': get_student_card_sections(settings),
        'message': f'Настройки карточки сохранены. Скрыто разделов: {hidden}' if hidden
                   else 'Настройки карточки сохранены. Показываются все разделы.'
    })


@app.route('/api/students/auto-archive/preview', methods=['GET'])
@login_required
def preview_auto_archive():
    """Кого затронет автоархив, без изменений."""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    settings = get_club_settings_instance()
    months = get_auto_archive_months(settings)
    if not months:
        return jsonify({'success': True, 'enabled': False, 'months': 0, 'candidates': [], 'count': 0})

    result = run_auto_archive(settings, dry_run=True)
    return jsonify({
        'success': True,
        'enabled': True,
        'months': months,
        'count': result['count'],
        'candidates': result['archived'],
    })


@app.route('/api/students/auto-archive/run', methods=['POST'])
@login_required
def run_auto_archive_now():
    """Запустить автоархив вручную."""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    settings = get_club_settings_instance()
    months = get_auto_archive_months(settings)
    if not months:
        return jsonify({
            'success': False,
            'message': 'Автоархив выключен: задайте срок в настройках'
        }), 400

    result = run_auto_archive(settings)
    if result['count']:
        names = ', '.join(item['full_name'] for item in result['archived'][:8])
        message = f"В архив убрано учеников: {result['count']} ({names}"
        message += ')' if result['count'] <= 8 else f" и еще {result['count'] - 8})"
    else:
        message = f'Никого не нашли: все активные ученики приходили за последние {months} мес.'

    result['success'] = True
    result['message'] = message
    return jsonify(result)


@app.route('/api/students/<int:student_id>/archive', methods=['POST'])
@login_required
def archive_student(student_id):
    """Ученик уходит в архив: из терминалов удаляется, данные остаются."""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    ensure_students_columns()
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({'success': False, 'message': 'Ученик не найден'}), 404
    if student.status == 'archived':
        return jsonify({'success': True, 'message': 'Ученик уже в архиве'})

    log_student_event(
        student.id, 'archived',
        f'Ученик переведен в архив (был статус «{student_status_label(student.status)}»)',
        ['Запись удалена из терминалов, оплаты и посещения сохранены']
    )
    student.previous_status = student.status
    student.status = 'archived'
    student.archived_at = get_local_datetime()
    db.session.commit()
    queue_hikvision_person('student', student.id, 'student_archived', action='delete',
                           employee_no=str(student.id))
    db.session.commit()
    return jsonify({
        'success': True,
        'message': f'{student.full_name} перемещен в архив',
        'status': student.status,
        'status_label': student_status_label(student.status),
    })


@app.route('/api/students/<int:student_id>/restore', methods=['POST'])
@login_required
def restore_student(student_id):
    """Вернуть ученика из архива."""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    ensure_students_columns()
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({'success': False, 'message': 'Ученик не найден'}), 404
    if student.status != 'archived':
        return jsonify({'success': False, 'message': 'Ученик не в архиве'}), 400

    restored = getattr(student, 'previous_status', None) or 'active'
    if restored == 'archived':
        restored = 'active'
    log_student_event(
        student.id, 'restored',
        f'Ученик возвращен из архива со статусом «{student_status_label(restored)}»'
    )
    student.status = restored
    student.archived_at = None
    student.previous_status = None
    db.session.commit()
    queue_hikvision_person('student', student.id, 'student_restored')
    db.session.commit()
    return jsonify({
        'success': True,
        'message': f'{student.full_name} возвращен из архива',
        'status': student.status,
        'status_label': student_status_label(student.status),
    })


@app.route('/api/hikvision/commands/next', methods=['GET'])
def hikvision_next_command():
    if not check_bridge_auth():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    ensure_device_commands_table()
    urgent_only = request.args.get('urgent') in {'1', 'true', 'yes'}
    query = DeviceCommand.query.filter_by(status='pending')
    if urgent_only:
        query = query.filter(DeviceCommand.command.in_(['HIKVISION_DOOR_OPEN', 'HIKVISION_CONTROL', 'HIKVISION_CLEAR_DEVICE']))
    cmd = query.order_by(DeviceCommand.created_at.asc()).first()
    if not cmd:
        db.session.commit()
        return jsonify({'command': None})
    cmd.status = 'processing'
    cmd.picked_at = get_local_datetime()
    status = BridgeStatus.query.filter_by(bridge_id='hikvision-school-bridge').first()
    if status:
        status.current_command_id = cmd.id
        status.current_action = f"Взял команду #{cmd.id}"
    db.session.commit()
    return jsonify({
        'command': {
            'id': cmd.id,
            'type': cmd.command,
            'payload': cmd.get_payload(),
            'created_at': cmd.created_at.isoformat() if cmd.created_at else None
        }
    })


@app.route('/api/hikvision/commands/<int:command_id>/result', methods=['POST'])
def hikvision_command_result(command_id):
    if not check_bridge_auth():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    cmd = db.session.get(DeviceCommand, command_id)
    if not cmd:
        return jsonify({'success': False, 'message': 'Command not found'}), 404
    data = request.get_json(silent=True) or {}
    cmd.status = 'done' if data.get('ok') else 'failed'
    cmd.result = str(data.get('result') or '')[:50000]
    cmd.finished_at = get_local_datetime()
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/hikvision/commands/history', methods=['GET'])
@login_required
def get_hikvision_commands_history():
    """Получить историю команд синхронизации Hikvision"""
    if current_user.role not in ['admin']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    ensure_device_commands_table()
    commands = DeviceCommand.query.filter(DeviceCommand.command.in_(['HIKVISION_SYNC', 'HIKVISION_PERSON', 'HIKVISION_DOOR_OPEN', 'HIKVISION_CONTROL', 'HIKVISION_CLEAR_DEVICE']))\
        .order_by(DeviceCommand.created_at.desc())\
        .limit(30)\
        .all()

    payload = []
    for cmd in commands:
        payload.append({
            'id': cmd.id,
            'command': cmd.command,
            'payload': cmd.get_payload(),
            'status': cmd.status,
            'result': cmd.result,
            'created_at': cmd.created_at.isoformat() if cmd.created_at else None,
            'picked_at': cmd.picked_at.isoformat() if cmd.picked_at else None,
            'finished_at': cmd.finished_at.isoformat() if cmd.finished_at else None,
        })

    return jsonify({
        'success': True,
        'commands': payload
    })


@app.route('/api/hikvision/commands/local', methods=['POST'])
def hikvision_create_local_command():
    """Создать запись о локальном запуске (startup/daily), чтобы записать ее лог в БД"""
    if not check_bridge_auth():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    ensure_device_commands_table()
    data = request.get_json(silent=True) or {}
    reason = data.get('reason', 'local')

    now = get_local_datetime()
    stale_before = now - timedelta(minutes=30)

    # Закрываем только реально зависшие processing-команды. Pending не трогаем:
    # bridge заберет их после завершения текущей операции.
    stuck_commands = DeviceCommand.query.filter(
        DeviceCommand.command == 'HIKVISION_SYNC',
        DeviceCommand.status == 'processing',
        DeviceCommand.picked_at < stale_before
    ).all()
    for old_cmd in stuck_commands:
        old_cmd.status = 'failed'
        old_cmd.result = 'Отменено, так как локальный bridge запустил новую синхронизацию.'
        old_cmd.finished_at = now

    # Создаем команду сразу в статусе 'processing'
    cmd = DeviceCommand(command='HIKVISION_SYNC', status='processing')
    cmd.set_payload({'reason': reason})
    cmd.picked_at = now
    db.session.add(cmd)
    db.session.commit()

    return jsonify({'success': True, 'command_id': cmd.id})


@app.route('/api/finances/expenses', methods=['GET'])
@login_required
def get_expense_stats():
    """Статистика расходов"""
    from datetime import date
    from sqlalchemy import func, extract
    
    ensure_expense_columns()
    today = date.today()
    
    # Сегодня
    expense_today = db.session.query(func.sum(Expense.amount)).filter(
        func.date(Expense.expense_date) == today
    ).scalar() or 0
    
    # Этот месяц
    expense_month = db.session.query(func.sum(Expense.amount)).filter(
        extract('year', Expense.expense_date) == today.year,
        extract('month', Expense.expense_date) == today.month
    ).scalar() or 0
    
    # Всего
    expense_total = db.session.query(func.sum(Expense.amount)).scalar() or 0
    
    # Последние расходы
    expenses = Expense.query.order_by(Expense.expense_date.desc()).limit(50).all()
    
    expenses_list = [{
        'id': e.id,
        # expense_date у расходов является фактическим моментом создания записи
        # и хранится как локальное время Ташкента без offset.
        'expense_date': f"{e.expense_date.isoformat()}+05:00",
        'category': e.category,
        'amount': e.amount,
        'description': e.description,
        'expense_source': getattr(e, 'expense_source', 'cash') or 'cash',
        'employee_id': getattr(e, 'employee_id', None),
        'employee_name': getattr(e, 'employee_name', None) or '',
        'salary_year': getattr(e, 'salary_year', None),
        'salary_month': getattr(e, 'salary_month', None)
    } for e in expenses]
    
    return jsonify({
        'today': expense_today,
        'month': expense_month,
        'total': expense_total,
        'expenses': expenses_list
    })


@app.route('/api/finances/employees', methods=['GET'])
@login_required
def get_finance_employees():
    """Список сотрудников для выплат зарплаты."""
    if not current_user.has_permission('finances', 'view'):
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403

    users = User.query.order_by(User.full_name.asc(), User.username.asc()).all()
    employees = [{
        'id': user.id,
        'name': user.full_name or user.username,
        'username': user.username,
        'role': user_role_name(user),
        'salary_type': getattr(user, 'salary_type', 'fixed') or 'fixed',
        'fixed_salary': getattr(user, 'fixed_salary', None),
        'is_active': bool(getattr(user, 'is_active', True))
    } for user in users if getattr(user, 'is_active', True) and not is_guest_role(user)]

    return jsonify({'success': True, 'employees': employees})


@app.route('/api/finances/analytics', methods=['GET'])
@login_required
def get_analytics():
    """Аналитика по месяцам одним набором агрегирующих запросов."""
    today = get_local_date()
    periods = []
    year, month = today.year, today.month
    for offset in range(11, -1, -1):
        absolute_month = year * 12 + month - 1 - offset
        periods.append((absolute_month // 12, absolute_month % 12 + 1))
    return jsonify({'months': build_finance_months(periods, include_name=True)})


def build_finance_months(periods, include_name=False):
    """Return finance summaries while keeping SQL count independent of month count."""
    from calendar import monthrange
    from sqlalchemy import extract

    if not periods:
        return []
    period_set = set(periods)
    first_year, first_month = periods[0]
    last_year, last_month = periods[-1]
    start_date = date(first_year, first_month, 1)
    if last_month == 12:
        end_date = date(last_year + 1, 1, 1)
    else:
        end_date = date(last_year, last_month + 1, 1)
    start_dt = datetime.combine(start_date, dt_time.min)
    end_dt = datetime.combine(end_date, dt_time.min)

    income_rows = db.session.query(
        extract('year', Payment.payment_date).label('year'),
        extract('month', Payment.payment_date).label('month'),
        func.coalesce(func.sum(Payment.amount_paid), 0).label('total'),
    ).filter(
        Payment.payment_date >= start_dt,
        Payment.payment_date < end_dt,
    ).group_by(
        extract('year', Payment.payment_date),
        extract('month', Payment.payment_date),
    ).all()
    expense_rows = db.session.query(
        extract('year', Expense.expense_date).label('year'),
        extract('month', Expense.expense_date).label('month'),
        func.coalesce(func.sum(Expense.amount), 0).label('total'),
    ).filter(
        Expense.expense_date >= start_dt,
        Expense.expense_date < end_dt,
    ).group_by(
        extract('year', Expense.expense_date),
        extract('month', Expense.expense_date),
    ).all()
    years = sorted({year for year, _ in periods})
    paid_rows = db.session.query(
        Payment.payment_year,
        Payment.payment_month,
        Payment.student_id,
        func.coalesce(func.sum(Payment.amount_paid), 0),
    ).filter(
        Payment.payment_year.in_(years),
        Payment.payment_month.isnot(None),
    ).group_by(Payment.payment_year, Payment.payment_month, Payment.student_id).all()
    students = Student.query.options(joinedload(Student.tariff)).filter_by(status='active').all()
    settings = get_club_settings_instance()

    income_map = {
        (int(row.year), int(row.month)): float(row.total or 0)
        for row in income_rows if row.year and row.month
    }
    expense_map = {
        (int(row.year), int(row.month)): float(row.total or 0)
        for row in expense_rows if row.year and row.month
    }
    paid_map = {
        (int(year), int(month), student_id): float(total or 0)
        for year, month, student_id, total in paid_rows
        if year is not None and month is not None and (int(year), int(month)) in period_set
    }
    global_start = normalize_month_pair(
        getattr(settings, 'access_debt_start_year', None),
        getattr(settings, 'access_debt_start_month', None),
    )
    today = get_local_date()
    month_names = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
                   'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
    result = []
    for year, month in periods:
        month_start = date(year, month, 1)
        month_end = date(year, month, monthrange(year, month)[1])
        eligible = [
            student for student in students
            if not student.admission_date or student.admission_date <= month_end
        ]
        income = income_map.get((year, month), 0.0)
        expense = expense_map.get((year, month), 0.0)
        dues = get_students_month_dues(eligible, year, month, settings)
        expected = sum(dues.values())
        debt = 0.0
        if (year, month) <= (today.year, today.month) and (not global_start or (year, month) >= global_start):
            debt = sum(
                max(0, dues.get(student.id, 0.0) - paid_map.get((year, month, student.id), 0))
                for student in eligible
            )
        item = {
            'income': float(income),
            'expense': float(expense),
            'balance': float(income) - float(expense),
            'debt': float(debt),
            'expected': float(expected),
            'student_count': len(eligible),
            'new_student_count': sum(
                1 for student in students
                if student.admission_date and month_start <= student.admission_date <= month_end
            ),
        }
        if include_name:
            item['month_name'] = f'{month_names[month - 1]} {year}'
        result.append(item)
    return result


@app.route('/api/finances/monthly', methods=['GET'])
@login_required
def get_finances_monthly():
    """Данные по месяцам: приход, расход, остаток (приход - расход)"""
    # Получаем год из параметра запроса или используем текущий
    year = request.args.get('year', type=int)
    if not year:
        year = date.today().year
    return jsonify({'months': build_finance_months([(year, month) for month in range(1, 13)])})


@app.route('/api/finances/payment-status-current', methods=['GET'])
@login_required
def get_payment_status_current_month():
    """Статусы оплат активных учеников за текущий учебный месяц."""
    from sqlalchemy import extract

    today = get_local_date()
    year = request.args.get('year', default=today.year, type=int)
    month = request.args.get('month', default=today.month, type=int)

    paid_rows = db.session.query(
        Payment.student_id,
        func.coalesce(func.sum(Payment.amount_paid), 0)
    ).filter(
        Payment.payment_year == year,
        Payment.payment_month == month
    ).group_by(Payment.student_id).all()
    paid_by_student = {student_id: float(total or 0) for student_id, total in paid_rows}

    groups = Group.query.order_by(Group.name.asc()).all()
    group_map = {
        group.id: {
            'group_id': group.id,
            'group_name': group.name,
            'total_students': 0,
            'paid_count': 0,
            'partial_count': 0,
            'unpaid_count': 0,
            'club_funded_count': 0,
            'expected_amount': 0.0,
            'paid_amount': 0.0,
            'debt_amount': 0.0,
            'club_expected_amount': 0.0,
        }
        for group in groups
    }
    no_group_key = 0
    group_map[no_group_key] = {
        'group_id': None,
        'group_name': 'Без группы',
        'total_students': 0,
        'paid_count': 0,
        'partial_count': 0,
        'unpaid_count': 0,
        'club_funded_count': 0,
        'expected_amount': 0.0,
        'paid_amount': 0.0,
        'debt_amount': 0.0,
        'club_expected_amount': 0.0,
    }

    totals = {
        'total_students': 0,
        'paid_count': 0,
        'partial_count': 0,
        'unpaid_count': 0,
        'club_funded_count': 0,
        'expected_amount': 0.0,
        'paid_amount': 0.0,
        'debt_amount': 0.0,
        'club_expected_amount': 0.0,
    }

    students = Student.query.filter(Student.status == 'active').options(
        joinedload(Student.tariff),
        joinedload(Student.group)
    ).all()
    group_dues = get_students_month_dues(students, year, month)

    for student in students:
        group_key = student.group_id or no_group_key
        group_row = group_map.setdefault(group_key, {
            'group_id': student.group_id,
            'group_name': student.group.name if student.group else 'Без группы',
            'total_students': 0,
            'paid_count': 0,
            'partial_count': 0,
            'unpaid_count': 0,
            'club_funded_count': 0,
            'expected_amount': 0.0,
            'paid_amount': 0.0,
            'debt_amount': 0.0,
            'club_expected_amount': 0.0,
        })

        tariff_price = float(group_dues.get(student.id, 0.0))
        paid_amount = min(float(paid_by_student.get(student.id, 0)), tariff_price) if tariff_price else float(paid_by_student.get(student.id, 0))
        debt_amount = max(0.0, tariff_price - paid_amount)

        totals['total_students'] += 1
        group_row['total_students'] += 1

        if student.club_funded:
            totals['club_funded_count'] += 1
            group_row['club_funded_count'] += 1
            totals['club_expected_amount'] += tariff_price
            group_row['club_expected_amount'] += tariff_price
            continue

        totals['expected_amount'] += tariff_price
        totals['paid_amount'] += paid_amount
        totals['debt_amount'] += debt_amount
        group_row['expected_amount'] += tariff_price
        group_row['paid_amount'] += paid_amount
        group_row['debt_amount'] += debt_amount

        if tariff_price > 0 and paid_amount >= tariff_price:
            totals['paid_count'] += 1
            group_row['paid_count'] += 1
        elif paid_amount > 0:
            totals['partial_count'] += 1
            group_row['partial_count'] += 1
        else:
            totals['unpaid_count'] += 1
            group_row['unpaid_count'] += 1

    groups_payload = [
        row for row in group_map.values()
        if row['total_students'] > 0
    ]
    groups_payload.sort(key=lambda row: (-row['total_students'], row['group_name']))

    expense_rows = db.session.query(
        Expense.category,
        func.coalesce(func.sum(Expense.amount), 0)
    ).filter(
        extract('year', Expense.expense_date) == year,
        extract('month', Expense.expense_date) == month
    ).group_by(Expense.category).all()
    expense_total = sum(float(total or 0) for _, total in expense_rows)
    expenses_payload = [{
        'category': category or 'Без категории',
        'amount': float(total or 0),
        'share': round((float(total or 0) / expense_total) * 100) if expense_total else 0,
    } for category, total in expense_rows]
    expenses_payload.sort(key=lambda row: (-row['amount'], row['category']))

    return jsonify({
        'year': year,
        'month': month,
        'totals': totals,
        'groups': groups_payload,
        'expenses': {
            'total': expense_total,
            'categories': expenses_payload,
        },
    })


# ===== ГРУППЫ =====

@app.route('/api/groups', methods=['GET'])
@login_required
def get_groups():
    """Получить список всех групп"""
    ensure_group_trainers_table()
    groups = Group.query.options(
        joinedload(Group.trainer_links).joinedload(GroupTrainer.user)
    ).order_by(Group.name.asc()).all()
    total_counts = dict(
        db.session.query(Student.group_id, func.count(Student.id))
        .filter(Student.group_id.isnot(None))
        .group_by(Student.group_id)
        .all()
    )
    active_counts = dict(
        db.session.query(Student.group_id, func.count(Student.id))
        .filter(Student.group_id.isnot(None), Student.status == 'active')
        .group_by(Student.group_id)
        .all()
    )

    result = []
    for g in groups:
        trainer_data = group_trainer_payload(g)
        result.append({
            'id': g.id,
            'name': g.name,
            'schedule_time': g.schedule_time if g.schedule_time else '--:--',
            'duration_minutes': g.duration_minutes or 60,
            'field_blocks': g.field_blocks or 1,
            'field_block_indices': g.get_field_block_indices(),
            'late_threshold': g.late_threshold,
            'max_students': g.max_students,
            'notes': g.notes,
            'schedule_days': g.get_schedule_days_list(),
            'schedule_days_label': g.get_schedule_days_display(),
            'student_count': total_counts.get(g.id, 0),
            'active_student_count': active_counts.get(g.id, 0),
            'is_full': bool(g.max_students and active_counts.get(g.id, 0) >= g.max_students),
            **trainer_data
        })
    return jsonify(result)


@app.route('/api/trainers', methods=['GET'])
@login_required
def get_trainers():
    """Получить активных сотрудников-тренеров для закрепления за группами"""
    if not (
        current_user.has_permission('groups', 'view')
        or current_user.has_permission('users', 'view')
        or current_user.has_permission('settings', 'view')
    ):
        return jsonify({'error': 'Доступ запрещен'}), 403

    ensure_users_table_columns()
    trainers = [
        user for user in User.query.options(joinedload(User.role_obj)).filter_by(is_active=True).order_by(User.full_name.asc(), User.username.asc()).all()
        if is_trainer_role(user)
    ]
    return jsonify([{
        'id': user.id,
        'username': user.username,
        'full_name': user.full_name or user.username,
        'photo_url': build_user_photo_thumb_url(user.photo_path)
    } for user in trainers])


@app.route('/api/club-settings', methods=['GET'])
@login_required
def get_club_settings():
    ensure_club_settings_columns()
    settings = get_club_settings_instance()
    generated_key = False
    if not getattr(settings, 'hikvision_device_key', None):
        settings.ensure_hikvision_device_key()
        generated_key = True
    try:
        expense_categories_raw = getattr(settings, 'expense_categories', '') or ''
        expense_categories = json.loads(expense_categories_raw) if expense_categories_raw else []
        if not isinstance(expense_categories, list):
            expense_categories = []
    except Exception:
        expense_categories = []

    if not expense_categories:
        expense_categories = [
            'Аренда', 'Зарплата', 'Оборудование', 'Коммунальные услуги',
            'Ремонт стадиона', 'Оплата за сайт', 'Дивидент', 'Прочее'
        ]
    
    # Фильтруем техническую категорию "Encashment" - она не должна показываться пользователю
    # В интерфейсе "Инкасация" добавляется автоматически
    expense_categories = [cat for cat in expense_categories if cat != 'Encashment']
    if 'Оплата за сайт' not in expense_categories:
        insert_at = expense_categories.index('Ремонт стадиона') + 1 if 'Ремонт стадиона' in expense_categories else len(expense_categories)
        expense_categories.insert(insert_at, 'Оплата за сайт')
    if generated_key:
        db.session.commit()
    
    return jsonify({
        'system_name': settings.system_name or 'FK QORASUV',
        'logo_url': get_system_logo_url(settings),
        'logo_is_custom': bool(getattr(settings, 'logo_path', None)),
        'square_logo_url': get_system_square_logo_url(settings),
        'square_logo_is_custom': bool(getattr(settings, 'square_logo_path', None)),
        'working_days': settings.get_working_days_list(),
        'work_start_time': settings.work_start_time.strftime('%H:%M'),
        'work_end_time': settings.work_end_time.strftime('%H:%M'),
        'max_groups_per_slot': settings.max_groups_per_slot,
        'block_future_payments': bool(getattr(settings, 'block_future_payments', False)),
        'rewards_reset_period_months': getattr(settings, 'rewards_reset_period_months', 1),
        'podium_display_count': getattr(settings, 'podium_display_count', 20),
        'telegram_bot_url': getattr(settings, 'telegram_bot_url', '') or '',
        'telegram_bot_token': getattr(settings, 'telegram_bot_token', '') or '',
        'telegram_notification_template': getattr(settings, 'telegram_notification_template', '') or '',
        'telegram_reward_template': getattr(settings, 'telegram_reward_template', '') or '',
        'telegram_card_template': getattr(settings, 'telegram_card_template', '') or '',
        'telegram_payment_template': getattr(settings, 'telegram_payment_template', '') or '',
        'rtsp_url': getattr(settings, 'rtsp_url', '') or '',
        'camera_kiosk_enabled': bool(getattr(settings, 'camera_kiosk_enabled', False)),
        'camera_kiosk_url': getattr(settings, 'camera_kiosk_url', '') or '',
        'camera_stream_fps': int(getattr(settings, 'camera_stream_fps', 30) or 30),
        'camera_tracking_fps': int(getattr(settings, 'camera_tracking_fps', 30) or 30),
        'camera_detection_fps': int(getattr(settings, 'camera_detection_fps', 10) or 10),
        'camera_width': int(getattr(settings, 'camera_width', 1920) or 1920),
        'camera_height': int(getattr(settings, 'camera_height', 1080) or 1080),
        'camera_recognition_frames': int(getattr(settings, 'camera_recognition_frames', 3) or 3),
        'camera_result_hold_seconds': int(getattr(settings, 'camera_result_hold_seconds', 10) or 10),
        'camera_kiosk_port': int(getattr(settings, 'camera_kiosk_port', 8090) or 8090),
        'payment_click_enabled': bool(getattr(settings, 'payment_click_enabled', False)),
        'payment_click_qr_url': getattr(settings, 'payment_click_qr_url', '') or '',
        'payment_payme_enabled': bool(getattr(settings, 'payment_payme_enabled', False)),
        'payment_payme_qr_url': getattr(settings, 'payment_payme_qr_url', '') or '',
        'payment_uzum_enabled': bool(getattr(settings, 'payment_uzum_enabled', False)),
        'payment_uzum_qr_url': getattr(settings, 'payment_uzum_qr_url', '') or '',
        'payment_uzcard_enabled': bool(getattr(settings, 'payment_uzcard_enabled', False)),
        'payment_humo_enabled': bool(getattr(settings, 'payment_humo_enabled', False)),
        'payment_paynet_enabled': bool(getattr(settings, 'payment_paynet_enabled', False)),
        'payment_paynet_qr_url': getattr(settings, 'payment_paynet_qr_url', '') or '',
        'payment_multicard_enabled': bool(getattr(settings, 'payment_multicard_enabled', False)),
        'payment_multicard_qr_url': getattr(settings, 'payment_multicard_qr_url', '') or '',
        'payment_oson_enabled': bool(getattr(settings, 'payment_oson_enabled', False)),
        'payment_oson_qr_url': getattr(settings, 'payment_oson_qr_url', '') or '',
        'payment_transfer_enabled': bool(getattr(settings, 'payment_transfer_enabled', False)),
        'payment_provider_configs': settings.get_payment_provider_configs() if hasattr(settings, 'get_payment_provider_configs') else {},
        'access_block_day': int(getattr(settings, 'access_block_day', 10) or 10),
        'access_payment_policy': get_access_payment_policy(settings),
        'hikvision_daily_sync_time': get_hikvision_daily_sync_time(settings),
        'access_debt_start_year': getattr(settings, 'access_debt_start_year', None),
        'access_debt_start_month': getattr(settings, 'access_debt_start_month', None),
        'access_max_debt_months': get_access_max_debt_months(settings),
        'min_lessons_for_debt': get_min_lessons_for_debt(settings),
        'auto_archive_after_months': get_auto_archive_months(settings),
        'access_open_until': (get_access_open_until(settings).isoformat()
                              if get_access_open_until(settings) else None),
        'access_open_day_active': is_access_open_day(settings),
        'hikvision_device_key': get_bridge_key(settings),
        'hikvision_devices': settings.get_hikvision_devices() or default_hikvision_devices(),
        'hikvision_parallel_devices': bool(getattr(settings, 'hikvision_parallel_devices', False)),
        'hikvision_cleanup_stale_users': bool(getattr(settings, 'hikvision_cleanup_stale_users', True)),
        # Телефоны руководства
        'director_phone': getattr(settings, 'director_phone', '') or '',
        'founder_phone': getattr(settings, 'founder_phone', '') or '',
        'cashier_phone': getattr(settings, 'cashier_phone', '') or '',
        'expense_categories': expense_categories
    })


def normalize_payment_provider_configs(raw_configs):
    if not isinstance(raw_configs, dict):
        return {}

    allowed_providers = {'payme', 'click', 'uzum', 'oson', 'paynet', 'multicard'}
    allowed_fields = {
        'enabled', 'mode', 'merchant_id', 'service_id', 'cashbox_id',
        'merchant_user_id', 'secret_key', 'token', 'api_key', 'uuid',
        'store_id', 'agent_id', 'terminal_id', 'login', 'password',
        'project_id', 'endpoint_url', 'checkout_url', 'callback_url',
        'webhook_sign_formula', 'account_key', 'test_amount', 'notes'
    }
    max_lengths = {
        'notes': 1000,
        'secret_key': 500,
        'token': 500,
        'api_key': 500,
        'password': 500,
        'endpoint_url': 500,
        'checkout_url': 500,
        'callback_url': 500,
    }
    normalized = {}
    for provider, config in raw_configs.items():
        provider_key = str(provider or '').strip().lower()
        if provider_key not in allowed_providers or not isinstance(config, dict):
            continue
        clean = {}
        for field, value in config.items():
            field_key = str(field or '').strip()
            if field_key not in allowed_fields:
                continue
            if field_key == 'enabled':
                clean[field_key] = bool(value)
                continue
            if field_key == 'mode':
                mode = str(value or '').strip().lower()
                clean[field_key] = mode if mode in {'sandbox', 'production'} else 'sandbox'
                continue
            text_value = str(value or '').strip()
            limit = max_lengths.get(field_key, 200)
            clean[field_key] = text_value[:limit]
        normalized[provider_key] = clean
    return normalized


@app.route('/api/payments/<provider>/callback', methods=['GET', 'POST'])
def payment_provider_callback(provider):
    provider_key = (provider or '').strip().lower()
    if provider_key not in {'payme', 'click', 'uzum', 'oson', 'paynet', 'multicard'}:
        return jsonify({'success': False, 'message': 'Unknown payment provider'}), 404

    settings = get_club_settings_instance()
    provider_configs = settings.get_payment_provider_configs()
    provider_config = provider_configs.get(provider_key, {})
    if not provider_config.get('enabled'):
        if provider_key == 'payme':
            payload = request.get_json(silent=True) or {}
            return jsonify({
                'jsonrpc': '2.0',
                'id': payload.get('id'),
                'error': {
                    'code': -32504,
                    'message': {
                        'ru': 'Платежный провайдер не включен',
                        'uz': 'Tolov provayderi yoqilmagan',
                        'en': 'Payment provider is not enabled'
                    }
                }
            })
        if provider_key == 'click':
            return jsonify({'error': -9, 'error_note': 'Payment provider is not enabled'})
        return jsonify({'success': False, 'message': 'Payment provider is not enabled'}), 403

    if provider_key == 'payme':
        payload = request.get_json(silent=True) or {}
        return jsonify({
            'jsonrpc': '2.0',
            'id': payload.get('id'),
            'error': {
                'code': -31001,
                'message': {
                    'ru': 'Обработчик оплаты подготовлен, но еще не подключен к учету оплат',
                    'uz': 'Tolov ishlovchisi tayyor, lekin hisobga ulanmagan',
                    'en': 'Payment handler is prepared but not connected to accounting yet'
                }
            }
        }), 501
    if provider_key == 'click':
        return jsonify({'error': -4, 'error_note': 'Payment handler is prepared but not connected yet'}), 501
    return jsonify({
        'success': False,
        'provider': provider_key,
        'message': 'Payment handler is prepared but not connected yet'
    }), 501


@app.route('/api/club-settings', methods=['PUT'])
@login_required
def update_club_settings():
    try:
        data = request.get_json()
        ensure_club_settings_columns()
        settings = get_club_settings_instance()

        def get_bool_setting(key, default_value):
            if key in data:
                return bool(data.get(key))
            return bool(default_value)

        def get_str_setting(key, default_value):
            if key in data:
                return (data.get(key) or '').strip()
            return (default_value or '').strip()

        system_name = (data.get('system_name') or '').strip() or 'FK QORASUV'
        working_days = parse_days_list(data.get('working_days'))
        work_start_time = datetime.strptime(data.get('work_start_time'), '%H:%M').time()
        work_end_time = datetime.strptime(data.get('work_end_time'), '%H:%M').time()
        max_groups_per_slot = int(data.get('max_groups_per_slot', 1))
        block_future_payments = bool(data.get('block_future_payments', False))
        rewards_reset_period_months = int(data.get('rewards_reset_period_months', 1))
        podium_display_count = int(data.get('podium_display_count', 20))
        telegram_bot_url = (data.get('telegram_bot_url') or '').strip()
        telegram_bot_token = (data.get('telegram_bot_token') or '').strip()
        telegram_notification_template = (data.get('telegram_notification_template') or '').strip()
        telegram_reward_template = (data.get('telegram_reward_template') or '').strip()
        telegram_card_template = (data.get('telegram_card_template') or '').strip()
        telegram_payment_template = (data.get('telegram_payment_template') or '').strip()
        rtsp_url = (data.get('rtsp_url') or '').strip()
        camera_kiosk_enabled = get_bool_setting('camera_kiosk_enabled', getattr(settings, 'camera_kiosk_enabled', False))
        camera_kiosk_url = get_str_setting('camera_kiosk_url', getattr(settings, 'camera_kiosk_url', '') or '')

        def get_camera_int(key, default_value, minimum, maximum):
            try:
                value = int(data.get(key, getattr(settings, key, default_value) or default_value))
            except (TypeError, ValueError):
                raise ValueError(f'Некорректное значение настройки камеры: {key}')
            if value < minimum or value > maximum:
                raise ValueError(f'Настройка камеры {key} должна быть от {minimum} до {maximum}')
            return value

        camera_stream_fps = get_camera_int('camera_stream_fps', 30, 1, 60)
        camera_tracking_fps = get_camera_int('camera_tracking_fps', 30, 1, 60)
        camera_detection_fps = get_camera_int('camera_detection_fps', 10, 1, 30)
        camera_width = get_camera_int('camera_width', 1920, 320, 3840)
        camera_height = get_camera_int('camera_height', 1080, 240, 2160)
        camera_recognition_frames = get_camera_int('camera_recognition_frames', 3, 1, 10)
        camera_result_hold_seconds = get_camera_int('camera_result_hold_seconds', 10, 1, 60)
        camera_kiosk_port = get_camera_int('camera_kiosk_port', 8090, 1024, 65535)
        if camera_kiosk_url and not re.match(r'^https?://', camera_kiosk_url, re.IGNORECASE):
            return jsonify({'success': False, 'message': 'Адрес киоска должен начинаться с http:// или https://'}), 400
        payment_click_enabled = get_bool_setting('payment_click_enabled', getattr(settings, 'payment_click_enabled', False))
        payment_click_qr_url = get_str_setting('payment_click_qr_url', getattr(settings, 'payment_click_qr_url', '') or '')
        payment_payme_enabled = get_bool_setting('payment_payme_enabled', getattr(settings, 'payment_payme_enabled', False))
        payment_payme_qr_url = get_str_setting('payment_payme_qr_url', getattr(settings, 'payment_payme_qr_url', '') or '')
        payment_uzum_enabled = get_bool_setting('payment_uzum_enabled', getattr(settings, 'payment_uzum_enabled', False))
        payment_uzum_qr_url = get_str_setting('payment_uzum_qr_url', getattr(settings, 'payment_uzum_qr_url', '') or '')
        payment_uzcard_enabled = get_bool_setting('payment_uzcard_enabled', getattr(settings, 'payment_uzcard_enabled', False))
        payment_humo_enabled = get_bool_setting('payment_humo_enabled', getattr(settings, 'payment_humo_enabled', False))
        payment_paynet_enabled = get_bool_setting('payment_paynet_enabled', getattr(settings, 'payment_paynet_enabled', False))
        payment_paynet_qr_url = get_str_setting('payment_paynet_qr_url', getattr(settings, 'payment_paynet_qr_url', '') or '')
        payment_multicard_enabled = get_bool_setting('payment_multicard_enabled', getattr(settings, 'payment_multicard_enabled', False))
        payment_multicard_qr_url = get_str_setting('payment_multicard_qr_url', getattr(settings, 'payment_multicard_qr_url', '') or '')
        payment_oson_enabled = get_bool_setting('payment_oson_enabled', getattr(settings, 'payment_oson_enabled', False))
        payment_oson_qr_url = get_str_setting('payment_oson_qr_url', getattr(settings, 'payment_oson_qr_url', '') or '')
        payment_transfer_enabled = get_bool_setting('payment_transfer_enabled', getattr(settings, 'payment_transfer_enabled', False))
        payment_provider_configs = normalize_payment_provider_configs(
            data.get('payment_provider_configs')
            if 'payment_provider_configs' in data
            else settings.get_payment_provider_configs()
        )
        access_block_day = int(data.get('access_block_day', getattr(settings, 'access_block_day', 10) or 10))
        access_payment_policy = (data.get('access_payment_policy') or getattr(settings, 'access_payment_policy', '') or 'partial_current_month').strip()
        hikvision_daily_sync_time = (data.get('hikvision_daily_sync_time') or getattr(settings, 'hikvision_daily_sync_time', '') or '03:00').strip()
        access_debt_start_year = data.get('access_debt_start_year', getattr(settings, 'access_debt_start_year', None))
        access_debt_start_month = data.get('access_debt_start_month', getattr(settings, 'access_debt_start_month', None))
        access_max_debt_months = data.get('access_max_debt_months', getattr(settings, 'access_max_debt_months', 0) or 0)
        min_lessons_for_debt = data.get('min_lessons_for_debt', getattr(settings, 'min_lessons_for_debt', 4))
        auto_archive_after_months = data.get('auto_archive_after_months', getattr(settings, 'auto_archive_after_months', 0) or 0)
        hikvision_device_key = get_str_setting('hikvision_device_key', getattr(settings, 'hikvision_device_key', '') or '')
        hikvision_devices = data.get('hikvision_devices') if isinstance(data.get('hikvision_devices'), list) else None
        hikvision_parallel_devices = get_bool_setting('hikvision_parallel_devices', getattr(settings, 'hikvision_parallel_devices', False))
        hikvision_cleanup_stale_users = get_bool_setting('hikvision_cleanup_stale_users', getattr(settings, 'hikvision_cleanup_stale_users', True))
        expense_categories = data.get('expense_categories') if isinstance(data.get('expense_categories'), list) else []
        expense_categories = [str(c).strip() for c in expense_categories if str(c).strip()]
        # Убираем техническую категорию "Encashment" и "Инкасация" - она не должна храниться в настройках
        expense_categories = [cat for cat in expense_categories if cat not in ['Encashment', 'Инкасация']]

        if not working_days:
            return jsonify({'success': False, 'message': 'Выберите рабочие дни'}), 400
        if work_end_time <= work_start_time:
            return jsonify({'success': False, 'message': 'Время окончания должно быть позже начала'}), 400
        if max_groups_per_slot <= 0:
            return jsonify({'success': False, 'message': 'Вместимость должна быть положительной'}), 400
        if rewards_reset_period_months < 1 or rewards_reset_period_months > 12:
            return jsonify({'success': False, 'message': 'Период сброса вознаграждений должен быть от 1 до 12 месяцев'}), 400
        if podium_display_count < 5 or podium_display_count > 50 or podium_display_count % 5 != 0:
            return jsonify({'success': False, 'message': 'Отображение пьедестала должно быть от 5 до 50 учеников с шагом 5'}), 400
        if access_block_day < 1 or access_block_day > 31:
            return jsonify({'success': False, 'message': 'День блокировки доступа должен быть от 1 до 31'}), 400
        if access_payment_policy not in {'full_current_month', 'partial_current_month', 'any_payment_this_month'}:
            access_payment_policy = 'partial_current_month'
        if not re.match(r'^\d{2}:\d{2}$', hikvision_daily_sync_time):
            return jsonify({'success': False, 'message': 'Время синхронизации должно быть в формате HH:MM'}), 400
        sync_hour, sync_minute = map(int, hikvision_daily_sync_time.split(':'))
        if sync_hour < 0 or sync_hour > 23 or sync_minute < 0 or sync_minute > 59:
            return jsonify({'success': False, 'message': 'Некорректное время синхронизации'}), 400
        if access_debt_start_year in ('', None):
            access_debt_start_year = None
        else:
            access_debt_start_year = int(access_debt_start_year)
        if access_debt_start_month in ('', None):
            access_debt_start_month = None
        else:
            access_debt_start_month = int(access_debt_start_month)
        if access_debt_start_month and (access_debt_start_month < 1 or access_debt_start_month > 12):
            return jsonify({'success': False, 'message': 'Месяц начала контроля доступа должен быть от 1 до 12'}), 400
        access_max_debt_months = int(access_max_debt_months or 0)
        if access_payment_policy == 'any_payment_this_month':
            if access_max_debt_months < 1 or access_max_debt_months > 36:
                return jsonify({'success': False, 'message': 'Лимит старого долга должен быть от 1 до 36 месяцев'}), 400
        else:
            access_max_debt_months = 0

        settings.system_name = system_name
        settings.set_working_days_list(working_days)
        settings.work_start_time = work_start_time
        settings.work_end_time = work_end_time
        settings.max_groups_per_slot = max_groups_per_slot
        settings.block_future_payments = block_future_payments
        settings.rewards_reset_period_months = rewards_reset_period_months
        settings.podium_display_count = podium_display_count
        settings.telegram_bot_url = telegram_bot_url if telegram_bot_url else None
        settings.telegram_bot_token = telegram_bot_token if telegram_bot_token else None
        
        # Сохранение телефонов руководства
        settings.director_phone = (data.get('director_phone') or '').strip() or None
        settings.founder_phone = (data.get('founder_phone') or '').strip() or None
        settings.cashier_phone = (data.get('cashier_phone') or '').strip() or None
        settings.telegram_notification_template = telegram_notification_template if telegram_notification_template else None
        settings.telegram_reward_template = telegram_reward_template if telegram_reward_template else None
        settings.telegram_card_template = telegram_card_template if telegram_card_template else None
        settings.telegram_payment_template = telegram_payment_template if telegram_payment_template else None
        settings.rtsp_url = rtsp_url if rtsp_url else None
        settings.camera_kiosk_enabled = camera_kiosk_enabled
        settings.camera_kiosk_url = camera_kiosk_url if camera_kiosk_url else None
        settings.camera_stream_fps = camera_stream_fps
        settings.camera_tracking_fps = min(camera_tracking_fps, camera_stream_fps)
        settings.camera_detection_fps = min(camera_detection_fps, camera_tracking_fps, camera_stream_fps)
        settings.camera_width = camera_width
        settings.camera_height = camera_height
        settings.camera_recognition_frames = camera_recognition_frames
        settings.camera_result_hold_seconds = camera_result_hold_seconds
        settings.camera_kiosk_port = camera_kiosk_port
        settings.payment_click_enabled = payment_click_enabled
        settings.payment_click_qr_url = payment_click_qr_url if payment_click_qr_url else None
        settings.payment_payme_enabled = payment_payme_enabled
        settings.payment_payme_qr_url = payment_payme_qr_url if payment_payme_qr_url else None
        settings.payment_uzum_enabled = payment_uzum_enabled
        settings.payment_uzum_qr_url = payment_uzum_qr_url if payment_uzum_qr_url else None
        settings.payment_uzcard_enabled = payment_uzcard_enabled
        settings.payment_humo_enabled = payment_humo_enabled
        settings.payment_paynet_enabled = payment_paynet_enabled
        settings.payment_paynet_qr_url = payment_paynet_qr_url if payment_paynet_qr_url else None
        settings.payment_multicard_enabled = payment_multicard_enabled
        settings.payment_multicard_qr_url = payment_multicard_qr_url if payment_multicard_qr_url else None
        settings.payment_oson_enabled = payment_oson_enabled
        settings.payment_oson_qr_url = payment_oson_qr_url if payment_oson_qr_url else None
        settings.payment_transfer_enabled = payment_transfer_enabled
        settings.set_payment_provider_configs(payment_provider_configs)
        settings.access_block_day = access_block_day
        settings.access_payment_policy = access_payment_policy
        settings.hikvision_daily_sync_time = hikvision_daily_sync_time
        settings.access_debt_start_year = access_debt_start_year
        settings.access_debt_start_month = access_debt_start_month
        settings.access_max_debt_months = access_max_debt_months
        try:
            settings.min_lessons_for_debt = max(0, int(min_lessons_for_debt))
        except (TypeError, ValueError):
            settings.min_lessons_for_debt = MIN_LESSONS_FOR_DEBT_DEFAULT
        try:
            settings.auto_archive_after_months = max(0, int(auto_archive_after_months))
        except (TypeError, ValueError):
            settings.auto_archive_after_months = AUTO_ARCHIVE_MONTHS_DEFAULT
        settings.hikvision_device_key = hikvision_device_key if hikvision_device_key else None
        settings.hikvision_parallel_devices = hikvision_parallel_devices
        settings.hikvision_cleanup_stale_users = hikvision_cleanup_stale_users
        if hikvision_devices is not None:
            settings.set_hikvision_devices(hikvision_devices)
        settings.expense_categories = json.dumps(expense_categories) if expense_categories else None
        queue_hikvision_sync('settings_updated')
        db.session.commit()
        reset_brand_cache()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/club-settings/logo', methods=['POST'])
@login_required
def upload_club_logo():
    try:
        ensure_club_settings_columns()
        settings = get_club_settings_instance()
        logo_file = request.files.get('logo')
        if not logo_file or not logo_file.filename:
            return jsonify({'success': False, 'message': 'Выберите файл логотипа'}), 400

        try:
            ext = detect_upload_image_extension(logo_file)
        except ValueError as exc:
            return jsonify({'success': False, 'message': str(exc)}), 400

        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        old_logo = getattr(settings, 'logo_path', None)
        filename = f"club_logo_{int(time.time())}{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        save_optimized_logo_upload(logo_file, filepath, (1200, 500))

        settings.logo_path = filename
        db.session.commit()

        if old_logo:
            old_filename = old_logo.replace('\\', '/').split('/')[-1]
            if old_filename.startswith('club_logo_'):
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_filename)
                try:
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except OSError:
                    pass

        reset_brand_cache()
        return jsonify({
            'success': True,
            'logo_url': get_system_logo_url(settings),
            'logo_is_custom': True
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/club-settings/logo', methods=['DELETE'])
@login_required
def reset_club_logo():
    try:
        ensure_club_settings_columns()
        settings = get_club_settings_instance()
        old_logo = getattr(settings, 'logo_path', None)
        settings.logo_path = None
        db.session.commit()

        if old_logo:
            old_filename = old_logo.replace('\\', '/').split('/')[-1]
            if old_filename.startswith('club_logo_'):
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_filename)
                try:
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except OSError:
                    pass

        reset_brand_cache()
        return jsonify({
            'success': True,
            'logo_url': get_system_logo_url(settings),
            'logo_is_custom': False
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/club-settings/square-logo', methods=['POST'])
@login_required
def upload_club_square_logo():
    try:
        ensure_club_settings_columns()
        settings = get_club_settings_instance()
        logo_file = request.files.get('logo')
        if not logo_file or not logo_file.filename:
            return jsonify({'success': False, 'message': 'Выберите квадратный логотип'}), 400

        try:
            ext = detect_upload_image_extension(logo_file)
        except ValueError as exc:
            return jsonify({'success': False, 'message': str(exc)}), 400

        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        old_logo = getattr(settings, 'square_logo_path', None)
        filename = f"club_square_logo_{int(time.time())}{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        save_optimized_logo_upload(logo_file, filepath, (640, 640))

        settings.square_logo_path = filename
        db.session.commit()

        if old_logo:
            old_filename = old_logo.replace('\\', '/').split('/')[-1]
            if old_filename.startswith('club_square_logo_'):
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_filename)
                try:
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except OSError:
                    pass

        reset_brand_cache()
        return jsonify({
            'success': True,
            'square_logo_url': get_system_square_logo_url(settings),
            'square_logo_is_custom': True
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/club-settings/square-logo', methods=['DELETE'])
@login_required
def reset_club_square_logo():
    try:
        ensure_club_settings_columns()
        settings = get_club_settings_instance()
        old_logo = getattr(settings, 'square_logo_path', None)
        settings.square_logo_path = None
        db.session.commit()

        if old_logo:
            old_filename = old_logo.replace('\\', '/').split('/')[-1]
            if old_filename.startswith('club_square_logo_'):
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_filename)
                try:
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except OSError:
                    pass

        reset_brand_cache()
        return jsonify({
            'success': True,
            'square_logo_url': get_system_square_logo_url(settings),
            'square_logo_is_custom': False
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/groups/add', methods=['POST'])
@login_required
def add_group():
    """Добавить новую группу"""
    try:
        ensure_group_trainers_table()
        data = request.get_json()
        name = data.get('name')
        schedule_time_str = data.get('schedule_time')  # "13:00"
        duration_minutes = int(data.get('duration_minutes', 60))
        # Количество блоков (на случай старых клиентов)
        field_blocks = int(data.get('field_blocks', 1))
        # Индексы блоков, которые занимает группа
        field_block_indices = data.get('field_block_indices') or []
        late_threshold = int(data.get('late_threshold', 15))
        max_students = data.get('max_students')
        if max_students:
            max_students = int(max_students)
        notes = data.get('notes', '')
        schedule_days = parse_days_list(data.get('schedule_days'))
        if not schedule_time_str:
            return jsonify({'success': False, 'message': 'Укажите время занятия'}), 400
        if not schedule_days:
            return jsonify({'success': False, 'message': 'Выберите дни недели'}), 400
        
        # Парсинг времени
        schedule_time = datetime.strptime(schedule_time_str, '%H:%M').time()
        is_valid, error_message = validate_group_schedule(schedule_time, schedule_days)
        if not is_valid:
            return jsonify({'success': False, 'message': error_message}), 400
        
        group = Group(
            name=name,
            schedule_time=schedule_time,
            duration_minutes=duration_minutes,
            late_threshold=late_threshold,
            max_students=max_students,
            notes=notes
        )
        # Если передали конкретные индексы блоков — используем их,
        # иначе считаем, что заняты первые field_blocks блока
        if field_block_indices:
            group.set_field_block_indices(field_block_indices)
        else:
            group.set_field_block_indices(list(range(field_blocks)))
        group.set_schedule_days_list(schedule_days)
        db.session.add(group)
        db.session.flush()
        sync_group_trainers(
            group.id,
            parse_int_list_payload(data, 'trainer_ids'),
            parse_int_list_payload(data, 'assistant_ids')
        )
        db.session.commit()
        
        return jsonify({'success': True, 'group_id': group.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/groups/<int:group_id>', methods=['PUT'])
@login_required
def update_group(group_id):
    """Обновить группу"""
    try:
        ensure_group_trainers_table()
        group = db.session.get(Group, group_id)
        if not group:
            return jsonify({'success': False, 'message': 'Группа не найдена'}), 404
        
        data = request.get_json()
        new_schedule_time = group.schedule_time
        new_schedule_days = group.get_schedule_days_list()
        if 'name' in data:
            group.name = data['name']
        if 'duration_minutes' in data:
            group.duration_minutes = int(data['duration_minutes'])
        # Обновление блоков поля
        if 'field_block_indices' in data:
            # Если пришёл массив индексов — сохраняем его
            group.set_field_block_indices(data['field_block_indices'])
        elif 'field_blocks' in data:
            # Старый формат: только количество блоков
            count = int(data['field_blocks'])
            group.set_field_block_indices(list(range(count)))
        if 'schedule_time' in data:
            raw_time = data.get('schedule_time')
            # Просто сохраняем как есть - строку или JSON
            new_schedule_time = raw_time
        if 'late_threshold' in data:
            group.late_threshold = int(data['late_threshold'])
        if 'max_students' in data:
            max_students = data['max_students']
            group.max_students = int(max_students) if max_students else None
        if 'notes' in data:
            group.notes = data['notes']
        if 'schedule_days' in data:
            new_schedule_days = parse_days_list(data['schedule_days'])
        
        # Валидацию пропускаем, если schedule_time - это JSON (разные времена для разных дней)
        needs_validation = ('schedule_time' in data) or ('schedule_days' in data) or not new_schedule_days
        is_json_schedule = isinstance(new_schedule_time, str) and new_schedule_time.startswith('{')
        
        if needs_validation and not is_json_schedule:
            effective_days = new_schedule_days or group.get_schedule_days_list()
            if not effective_days:
                effective_days = get_club_settings_instance().get_working_days_list()
            is_valid, error_message = validate_group_schedule(new_schedule_time, effective_days, exclude_group_id=group.id)
            if not is_valid:
                return jsonify({'success': False, 'message': error_message}), 400
            if not new_schedule_days:
                new_schedule_days = effective_days
        if new_schedule_days:
            group.set_schedule_days_list(new_schedule_days)
        group.schedule_time = new_schedule_time
        if 'trainer_ids' in data or 'assistant_ids' in data:
            sync_group_trainers(
                group.id,
                parse_int_list_payload(data, 'trainer_ids'),
                parse_int_list_payload(data, 'assistant_ids')
            )
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/groups/<int:group_id>', methods=['DELETE'])
@login_required
def delete_group(group_id):
    """Удалить группу"""
    try:
        group = db.session.get(Group, group_id)
        if not group:
            return jsonify({'success': False, 'message': 'Группа не найдена'}), 404
        
        # Переводим всех учеников группы в состояние "без группы"
        for student in group.students:
            student.group_id = None
        
        db.session.delete(group)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# ===== ТАРИФЫ =====

@app.route('/tariffs')
@login_required
def tariffs_page():
    return render_template('tariffs.html')


@app.route('/api/tariffs', methods=['GET'])
@login_required
def get_tariffs():
    """Получить список всех тарифов"""
    tariffs = Tariff.query.filter_by(is_active=True).order_by(Tariff.lessons_count).all()
    return jsonify([{
        'id': t.id,
        'name': t.name,
        'lessons_count': t.lessons_count,
        'price': t.price,
        'description': t.description,
        'price_per_lesson': round(t.price / t.lessons_count, 2) if t.lessons_count > 0 else 0
    } for t in tariffs])


@app.route('/api/tariffs/add', methods=['POST'])
@login_required
def add_tariff():
    """Добавить новый тариф"""
    try:
        data = request.get_json()
        name = data.get('name')
        lessons_count = int(data.get('lessons_count'))
        price = float(data.get('price'))
        description = data.get('description', '')
        
        tariff = Tariff(
            name=name,
            lessons_count=lessons_count,
            price=price,
            description=description
        )
        
        db.session.add(tariff)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tariffs/<int:tariff_id>', methods=['PUT'])
@login_required
def update_tariff(tariff_id):
    """Обновить тариф"""
    try:
        tariff = db.session.get(Tariff, tariff_id)
        if not tariff:
            return jsonify({'success': False, 'message': 'Тариф не найден'}), 404
        
        data = request.get_json()
        if 'name' in data:
            tariff.name = data['name']
        if 'lessons_count' in data:
            tariff.lessons_count = int(data['lessons_count'])
        if 'price' in data:
            tariff.price = float(data['price'])
        if 'description' in data:
            tariff.description = data['description']
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tariffs/<int:tariff_id>', methods=['DELETE'])
@login_required
def delete_tariff(tariff_id):
    """Удалить (деактивировать) тариф"""
    try:
        tariff = db.session.get(Tariff, tariff_id)
        if not tariff:
            return jsonify({'success': False, 'message': 'Тариф не найден'}), 404
        
        # Не удаляем физически, а деактивируем
        tariff.is_active = False
        db.session.commit()
        
        return jsonify({'success': True, 'message': f'Тариф "{tariff.name}" деактивирован'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# ===== ВОЗНАГРАЖДЕНИЯ =====

@app.route('/rewards')
@login_required
def rewards_page():
    """Страница управления вознаграждениями"""
    if not current_user.has_permission('rewards', 'view'):
        return redirect(url_for('dashboard'))
    return render_template('rewards.html')


@app.route('/api/rewards', methods=['GET'])
@login_required
def get_rewards():
    """Получить список всех типов вознаграждений"""
    if not current_user.has_permission('rewards', 'view'):
        return jsonify({'error': 'Доступ запрещен'}), 403
    
    rewards = RewardType.query.order_by(RewardType.created_at.desc()).all()
    return jsonify([{
        'id': r.id,
        'name': r.name,
        'points': r.points,
        'description': r.description or '',
        'created_at': r.created_at.isoformat() if r.created_at else None,
        'updated_at': r.updated_at.isoformat() if r.updated_at else None
    } for r in rewards])


@app.route('/api/rewards/add', methods=['POST'])
@login_required
def add_reward():
    """Добавить новый тип вознаграждения"""
    if not current_user.has_permission('rewards', 'edit'):
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        points = int(data.get('points', 1))
        description = data.get('description', '').strip()
        
        if not name:
            return jsonify({'success': False, 'message': 'Название вознаграждения не может быть пустым'}), 400
        
        if points < 1:
            return jsonify({'success': False, 'message': 'Количество баллов должно быть больше 0'}), 400
        
        reward = RewardType(
            name=name,
            points=points,
            description=description if description else None
        )
        
        db.session.add(reward)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Вознаграждение добавлено',
            'reward': {
                'id': reward.id,
                'name': reward.name,
                'points': reward.points,
                'description': reward.description or ''
            }
        })
    except ValueError:
        return jsonify({'success': False, 'message': 'Некорректное количество баллов'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/rewards/<int:reward_id>', methods=['PUT'])
@login_required
def update_reward(reward_id):
    """Обновить тип вознаграждения"""
    if not current_user.has_permission('rewards', 'edit'):
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    try:
        reward = db.session.get(RewardType, reward_id)
        if not reward:
            return jsonify({'success': False, 'message': 'Вознаграждение не найдено'}), 404
        
        data = request.get_json()
        if 'name' in data:
            name = data['name'].strip()
            if not name:
                return jsonify({'success': False, 'message': 'Название вознаграждения не может быть пустым'}), 400
            reward.name = name
        
        if 'points' in data:
            points = int(data['points'])
            if points < 1:
                return jsonify({'success': False, 'message': 'Количество баллов должно быть больше 0'}), 400
            reward.points = points
        
        if 'description' in data:
            reward.description = data['description'].strip() if data['description'].strip() else None
        
        reward.updated_at = get_local_datetime()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Вознаграждение обновлено',
            'reward': {
                'id': reward.id,
                'name': reward.name,
                'points': reward.points,
                'description': reward.description or ''
            }
        })
    except ValueError:
        return jsonify({'success': False, 'message': 'Некорректное количество баллов'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/rewards/<int:reward_id>', methods=['DELETE'])
@login_required
def delete_reward(reward_id):
    """Удалить тип вознаграждения"""
    if not current_user.has_permission('rewards', 'edit'):
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    try:
        reward = db.session.get(RewardType, reward_id)
        if not reward:
            return jsonify({'success': False, 'message': 'Вознаграждение не найдено'}), 404
        
        reward_name = reward.name
        db.session.delete(reward)
        db.session.commit()
        
        return jsonify({'success': True, 'message': f'Вознаграждение "{reward_name}" удалено'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# ===== ВЫДАЧА ВОЗНАГРАЖДЕНИЙ УЧЕНИКАМ =====

@app.route('/api/students/<int:student_id>/rewards', methods=['POST'])
@login_required
def issue_reward(student_id):
    """Выдать вознаграждение ученику"""
    if current_user.role not in ['admin', 'teacher']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    try:
        data = request.get_json()
        reward_type_id = int(data.get('reward_type_id'))
        
        student = db.session.get(Student, student_id)
        if not student:
            return jsonify({'success': False, 'message': 'Ученик не найден'}), 404
        
        reward_type = db.session.get(RewardType, reward_type_id)
        if not reward_type:
            return jsonify({'success': False, 'message': 'Тип вознаграждения не найден'}), 404
        
        from datetime import date
        current_date = date.today()
        
        # Создать запись о выдаче вознаграждения
        student_reward = StudentReward(
            student_id=student_id,
            reward_type_id=reward_type_id,
            points=reward_type.points,
            reward_name=reward_type.name,
            issued_by=current_user.id,
            month=current_date.month,
            year=current_date.year
        )
        
        db.session.add(student_reward)
        db.session.commit()
        
        # Подсчитать общее количество баллов за текущий месяц
        total_points = get_student_points_sum(student_id, current_date.month, current_date.year)
        
        # Отправить уведомление в Telegram
        reason = data.get('reason', '').strip()
        try:
            send_reward_notification(
                student_id=student_id,
                reward_name=reward_type.name,
                points=reward_type.points,
                total_points=total_points,
                reason=reason
            )
        except Exception as e:
            print(f"Ошибка отправки уведомления о вознаграждении: {e}")
            # Не прерываем выполнение, если уведомление не отправилось
        
        return jsonify({
            'success': True,
            'message': f'Вознаграждение "{reward_type.name}" выдано (+{reward_type.points} баллов)',
            'total_points': total_points
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/students/<int:student_id>/rewards', methods=['GET'])
@login_required
def get_student_rewards(student_id):
    """Получить историю вознаграждений ученика"""
    try:
        month = request.args.get('month', type=int)
        year = request.args.get('year', type=int)
        all_history = request.args.get('all', type=bool, default=False)
        
        from datetime import date
        if all_history:
            # Вернуть всю историю для вкладки истории
            rewards = StudentReward.query.filter_by(
                student_id=student_id
            ).order_by(StudentReward.issued_at.desc()).all()
        elif not month or not year:
            # По умолчанию - текущий месяц
            current_date = date.today()
            month = current_date.month
            year = current_date.year
            rewards = StudentReward.query.filter_by(
                student_id=student_id,
                month=month,
                year=year
            ).order_by(StudentReward.issued_at.desc()).all()
        else:
            # Конкретный месяц и год
            rewards = StudentReward.query.filter_by(
                student_id=student_id,
                month=month,
                year=year
            ).order_by(StudentReward.issued_at.desc()).all()
        
        result = []
        for r in rewards:
            # Проверяем is_deleted через прямой запрос к БД, если поле существует
            is_deleted = False
            deleted_at = None
            try:
                inspector = db.inspect(db.engine)
                columns = {col['name'] for col in inspector.get_columns('student_rewards')}
                if 'is_deleted' in columns:
                    result_row = db.session.execute(
                        db.text("SELECT is_deleted, deleted_at FROM student_rewards WHERE id = :id"),
                        {'id': r.id}
                    ).fetchone()
                    if result_row:
                        is_deleted = bool(result_row[0]) if result_row[0] is not None else False
                        deleted_at = result_row[1].isoformat() if result_row[1] else None
            except:
                pass
            
            # Альтернативная проверка через префикс
            if not is_deleted and r.reward_name and r.reward_name.startswith('[УДАЛЕНО] '):
                is_deleted = True
            
            result.append({
                'id': r.id,
                'reward_name': r.reward_name.replace('[УДАЛЕНО] ', '') if r.reward_name.startswith('[УДАЛЕНО] ') else r.reward_name,
                'points': r.points,
                'issued_at': r.issued_at.isoformat() if r.issued_at else None,
                'issuer_name': r.issuer.username if r.issuer else 'Система',
                'is_deleted': is_deleted,
                'deleted_at': deleted_at
            })
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/students/<int:student_id>/points', methods=['GET'])
@login_required
def get_student_points(student_id):
    """Получить общее количество баллов ученика за текущий месяц"""
    try:
        from datetime import date
        current_date = date.today()
        
        total_points = get_student_points_sum(student_id, current_date.month, current_date.year)
        
        return jsonify({'points': total_points})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ===== КАРТОЧКИ УЧЕНИКОВ =====

@app.route('/api/card-types', methods=['GET'])
@login_required
def get_card_types():
    """Получить список всех типов карточек"""
    try:
        # Проверить, есть ли типы карточек, если нет - создать
        card_types = CardType.query.order_by(CardType.id.asc()).all()
        if not card_types:
            # Автоматически создать типы карточек при первом запросе
            default_types = [
                CardType(name='Желтая', color='yellow', description='Предупреждение'),
                CardType(name='Красная', color='red', description='Удаление с поля'),
                CardType(name='Оранжевая', color='orange', description='Серьезное нарушение'),
                CardType(name='Синяя', color='blue', description='Замечание'),
                CardType(name='Зеленая', color='green', description='Положительное поведение')
            ]
            for card_type in default_types:
                db.session.add(card_type)
            db.session.commit()
            card_types = CardType.query.order_by(CardType.id.asc()).all()
        
        return jsonify([{
            'id': ct.id,
            'name': ct.name,
            'color': ct.color,
            'description': ct.description or ''
        } for ct in card_types])
    except Exception as e:
        # Если ошибка из-за отсутствия таблицы, создать её
        try:
            db.create_all()
            # Попробовать снова создать типы
            default_types = [
                CardType(name='Желтая', color='yellow', description='Предупреждение'),
                CardType(name='Красная', color='red', description='Удаление с поля'),
                CardType(name='Оранжевая', color='orange', description='Серьезное нарушение'),
                CardType(name='Синяя', color='blue', description='Замечание'),
                CardType(name='Зеленая', color='green', description='Положительное поведение')
            ]
            for card_type in default_types:
                db.session.add(card_type)
            db.session.commit()
            card_types = CardType.query.order_by(CardType.id.asc()).all()
            return jsonify([{
                'id': ct.id,
                'name': ct.name,
                'color': ct.color,
                'description': ct.description or ''
            } for ct in card_types])
        except Exception as e2:
            return jsonify({'error': str(e2)}), 500


@app.route('/api/students/<int:student_id>/cards', methods=['GET'])
@login_required
def get_student_cards(student_id):
    """Получить активные карточки ученика"""
    try:
        active_cards = StudentCard.query.filter_by(
            student_id=student_id,
            is_active=True
        ).order_by(StudentCard.issued_at.desc()).all()
        
        return jsonify([{
            'id': card.id,
            'card_type_id': card.card_type_id,
            'card_type_name': card.card_type.name,
            'card_type_color': card.card_type.color,
            'reason': card.reason,
            'issued_at': card.issued_at.isoformat() if card.issued_at else None,
            'issued_by': card.issuer_user.username if card.issuer_user else 'Система'
        } for card in active_cards])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/students/<int:student_id>/cards/history', methods=['GET'])
@login_required
def get_student_cards_history(student_id):
    """Получить всю историю карточек ученика"""
    try:
        all_cards = StudentCard.query.filter_by(
            student_id=student_id
        ).order_by(StudentCard.issued_at.desc()).all()
        
        result = []
        for card in all_cards:
            # Проверяем is_deleted через прямой запрос к БД, если поле существует
            is_deleted = False
            deleted_at = None
            try:
                inspector = db.inspect(db.engine)
                columns = {col['name'] for col in inspector.get_columns('student_cards')}
                if 'is_deleted' in columns:
                    result_row = db.session.execute(
                        db.text("SELECT is_deleted, deleted_at FROM student_cards WHERE id = :id"),
                        {'id': card.id}
                    ).fetchone()
                    if result_row:
                        is_deleted = bool(result_row[0]) if result_row[0] is not None else False
                        deleted_at = result_row[1].isoformat() if result_row[1] else None
            except:
                pass
            
            # Альтернативная проверка через префикс
            if not is_deleted and card.reason and card.reason.startswith('[УДАЛЕНО] '):
                is_deleted = True
            
            result.append({
                'id': card.id,
                'card_type_id': card.card_type_id,
                'card_type_name': card.card_type.name,
                'card_type_color': card.card_type.color,
                'reason': card.reason.replace('[УДАЛЕНО] ', '') if card.reason.startswith('[УДАЛЕНО] ') else card.reason,
                'issued_at': card.issued_at.isoformat() if card.issued_at else None,
                'issued_by': card.issuer_user.username if card.issuer_user else 'Система',
                'removed_at': card.removed_at.isoformat() if card.removed_at else None,
                'removed_by': card.remover_user.username if card.remover_user else None,
                'is_active': card.is_active,
                'is_deleted': is_deleted,
                'deleted_at': deleted_at
            })
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/students/<int:student_id>/cards', methods=['POST'])
@login_required
def issue_card(student_id):
    """Выдать карточку ученику"""
    if current_user.role not in ['admin', 'teacher']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    try:
        data = request.get_json()
        card_type_id = int(data.get('card_type_id'))
        reason = data.get('reason', '').strip()
        
        if not reason:
            return jsonify({'success': False, 'message': 'Укажите причину выдачи карточки'}), 400
        
        student = db.session.get(Student, student_id)
        if not student:
            return jsonify({'success': False, 'message': 'Ученик не найден'}), 404
        
        card_type = db.session.get(CardType, card_type_id)
        if not card_type:
            return jsonify({'success': False, 'message': 'Тип карточки не найден'}), 404
        
        # Создать запись о выдаче карточки
        student_card = StudentCard(
            student_id=student_id,
            card_type_id=card_type_id,
            reason=reason,
            issued_by=current_user.id,
            is_active=True
        )
        
        db.session.add(student_card)
        db.session.commit()
        
        # Отправить уведомление в Telegram
        try:
            send_card_notification(
                student_id=student_id,
                card_name=card_type.name,
                reason=reason
            )
        except Exception as e:
            print(f"Ошибка отправки уведомления о карточке: {e}")
            # Не прерываем выполнение, если уведомление не отправилось
        
        return jsonify({
            'success': True,
            'message': f'Карточка "{card_type.name}" выдана',
            'card': {
                'id': student_card.id,
                'card_type_id': card_type.id,
                'card_type_name': card_type.name,
                'card_type_color': card_type.color,
                'reason': reason
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/students/<int:student_id>/cards/<int:card_id>/remove', methods=['POST'])
@login_required
def remove_card(student_id, card_id):
    """Снять карточку с ученика"""
    if current_user.role not in ['admin', 'teacher']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    try:
        student_card = db.session.get(StudentCard, card_id)
        if not student_card or student_card.student_id != student_id:
            return jsonify({'success': False, 'message': 'Карточка не найдена'}), 404
        
        if not student_card.is_active:
            return jsonify({'success': False, 'message': 'Карточка уже снята'}), 400
        
        student_card.is_active = False
        student_card.removed_at = get_local_datetime()
        student_card.removed_by = current_user.id
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Карточка снята'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


def ensure_deleted_columns():
    """Добавить колонки is_deleted и deleted_at в таблицы student_rewards и student_cards если их нет"""
    try:
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        
        if 'student_rewards' in tables:
            columns = {col['name'] for col in inspector.get_columns('student_rewards')}
            if 'is_deleted' not in columns:
                try:
                    db.session.execute(db.text("ALTER TABLE student_rewards ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE"))
                    db.session.commit()
                    print("✓ Добавлена колонка is_deleted в student_rewards")
                except Exception as e:
                    db.session.rollback()
                    if "duplicate column" not in str(e).lower() and "already exists" not in str(e).lower():
                        print(f"Ошибка при добавлении is_deleted в student_rewards: {e}")
            
            if 'deleted_at' not in columns:
                try:
                    db.session.execute(db.text("ALTER TABLE student_rewards ADD COLUMN deleted_at TIMESTAMP"))
                    db.session.commit()
                    print("✓ Добавлена колонка deleted_at в student_rewards")
                except Exception as e:
                    db.session.rollback()
                    if "duplicate column" not in str(e).lower() and "already exists" not in str(e).lower():
                        print(f"Ошибка при добавлении deleted_at в student_rewards: {e}")
        
        if 'student_cards' in tables:
            columns = {col['name'] for col in inspector.get_columns('student_cards')}
            if 'is_deleted' not in columns:
                try:
                    db.session.execute(db.text("ALTER TABLE student_cards ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE"))
                    db.session.commit()
                    print("✓ Добавлена колонка is_deleted в student_cards")
                except Exception as e:
                    db.session.rollback()
                    if "duplicate column" not in str(e).lower() and "already exists" not in str(e).lower():
                        print(f"Ошибка при добавлении is_deleted в student_cards: {e}")
            
            if 'deleted_at' not in columns:
                try:
                    db.session.execute(db.text("ALTER TABLE student_cards ADD COLUMN deleted_at TIMESTAMP"))
                    db.session.commit()
                    print("✓ Добавлена колонка deleted_at в student_cards")
                except Exception as e:
                    db.session.rollback()
                    if "duplicate column" not in str(e).lower() and "already exists" not in str(e).lower():
                        print(f"Ошибка при добавлении deleted_at в student_cards: {e}")
    except Exception as e:
        print(f"Ошибка при проверке колонок удаления: {e}")


def get_student_points_sum(student_id, month=None, year=None):
    """Подсчитать сумму очков ученика за указанный месяц/год с учетом удаленных вознаграждений"""
    try:
        from datetime import date
        if month is None or year is None:
            current_date = date.today()
            month = month or current_date.month
            year = year or current_date.year
        
        # Проверить наличие колонки is_deleted
        inspector = db.inspect(db.engine)
        columns = {col['name'] for col in inspector.get_columns('student_rewards')}
        
        if 'is_deleted' in columns:
            # Использовать SQL запрос с фильтром is_deleted
            result = db.session.execute(
                db.text("""
                    SELECT COALESCE(SUM(points), 0) 
                    FROM student_rewards 
                    WHERE student_id = :student_id 
                    AND month = :month 
                    AND year = :year 
                    AND (is_deleted = 0 OR is_deleted IS NULL)
                """),
                {'student_id': student_id, 'month': month, 'year': year}
            ).scalar()
            return result or 0
        else:
            # Если колонки нет, использовать обычный запрос, но исключить записи с префиксом [УДАЛЕНО]
            total_points = db.session.query(func.sum(StudentReward.points)).filter(
                StudentReward.student_id == student_id,
                StudentReward.month == month,
                StudentReward.year == year,
                ~StudentReward.reward_name.like('[УДАЛЕНО]%')
            ).scalar() or 0
            return total_points
    except Exception as e:
        print(f"Ошибка при подсчете очков ученика {student_id}: {e}")
        # В случае ошибки вернуть 0 или попробовать базовый запрос
        try:
            total_points = db.session.query(func.sum(StudentReward.points)).filter(
                StudentReward.student_id == student_id,
                StudentReward.month == month,
                StudentReward.year == year
            ).scalar() or 0
            return total_points
        except:
            return 0


@app.route('/api/students/<int:student_id>/rewards/<int:reward_id>/delete', methods=['POST'])
@login_required
def delete_student_reward(student_id, reward_id):
    """Удалить вознаграждение (пометить как удаленное)"""
    if current_user.role not in ['admin', 'teacher']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    try:
        ensure_deleted_columns()
        reward = StudentReward.query.filter_by(id=reward_id, student_id=student_id).first()
        if not reward:
            return jsonify({'success': False, 'message': 'Вознаграждение не найдено'}), 404
        
        # Пометить как удаленное (мягкое удаление)
        # Используем прямой SQL-запрос для надежности
        inspector = db.inspect(db.engine)
        columns = {col['name'] for col in inspector.get_columns('student_rewards')}
        
        updated = False
        if 'deleted_at' in columns and 'is_deleted' in columns:
            try:
                db.session.execute(
                    db.text("UPDATE student_rewards SET is_deleted = 1, deleted_at = :deleted_at WHERE id = :id"),
                    {'deleted_at': get_local_datetime(), 'id': reward_id}
                )
                db.session.commit()
                updated = True
                print(f"✓ Вознаграждение {reward_id} помечено как удаленное через SQL (с deleted_at)")
            except Exception as sql_error:
                print(f"Ошибка SQL при удалении вознаграждения (с deleted_at): {sql_error}")
                db.session.rollback()
        
        if not updated and 'is_deleted' in columns:
            try:
                db.session.execute(
                    db.text("UPDATE student_rewards SET is_deleted = 1 WHERE id = :id"),
                    {'id': reward_id}
                )
                db.session.commit()
                updated = True
                print(f"✓ Вознаграждение {reward_id} помечено как удаленное через SQL (только is_deleted)")
            except Exception as sql_error:
                print(f"Ошибка SQL при удалении вознаграждения (только is_deleted): {sql_error}")
                db.session.rollback()
        
        if not updated:
            # Альтернативный способ - префикс в названии
            reward = StudentReward.query.filter_by(id=reward_id, student_id=student_id).first()
            if reward and not reward.reward_name.startswith('[УДАЛЕНО] '):
                reward.reward_name = f"[УДАЛЕНО] {reward.reward_name}"
                db.session.commit()
                updated = True
                print(f"✓ Вознаграждение {reward_id} помечено как удаленное через префикс")
        
        return jsonify({
            'success': True,
            'message': 'Вознаграждение удалено'
        })
    except Exception as e:
        db.session.rollback()
        print(f"Ошибка при удалении вознаграждения {reward_id}: {e}")
        return jsonify({'success': False, 'message': f'Ошибка при удалении: {str(e)}'}), 500


@app.route('/api/students/<int:student_id>/cards/<int:card_id>/delete', methods=['POST'])
@login_required
def delete_student_card(student_id, card_id):
    """Удалить карточку (пометить как удаленную)"""
    if current_user.role not in ['admin', 'teacher']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    try:
        ensure_deleted_columns()
        card = StudentCard.query.filter_by(id=card_id, student_id=student_id).first()
        if not card:
            return jsonify({'success': False, 'message': 'Карточка не найдена'}), 404
        
        # Пометить как удаленную (мягкое удаление)
        # Используем прямой SQL-запрос для надежности
        inspector = db.inspect(db.engine)
        columns = {col['name'] for col in inspector.get_columns('student_cards')}
        
        if 'deleted_at' in columns and 'is_deleted' in columns:
            db.session.execute(
                db.text("UPDATE student_cards SET is_deleted = 1, deleted_at = :deleted_at WHERE id = :id"),
                {'deleted_at': get_local_datetime(), 'id': card_id}
            )
        elif 'is_deleted' in columns:
            db.session.execute(
                db.text("UPDATE student_cards SET is_deleted = 1 WHERE id = :id"),
                {'id': card_id}
            )
        else:
            # Альтернативный способ - префикс в reason
            card.reason = f"[УДАЛЕНО] {card.reason}"
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Карточка удалена'
        })
    except Exception as e:
        db.session.rollback()
        # Если колонки не существуют, попробуем альтернативный способ
        try:
            card = StudentCard.query.filter_by(id=card_id, student_id=student_id).first()
            if card:
                # Используем reason для пометки
                card.reason = f"[УДАЛЕНО] {card.reason}"
                db.session.commit()
                return jsonify({
                    'success': True,
                    'message': 'Карточка удалена'
                })
        except:
            pass
        return jsonify({'success': False, 'message': str(e)}), 500


# ===== РЕЙТИНГ УЧЕНИКОВ =====

def query_rating_totals(year, month=None, group_id=None):
    """Aggregate rating points in one query instead of one query per student."""
    query = db.session.query(
        Student.id.label('student_id'),
        Student.group_id.label('group_id'),
        Student.full_name.label('full_name'),
        Student.photo_path.label('photo_path'),
        StudentReward.month.label('month'),
        func.coalesce(func.sum(StudentReward.points), 0).label('points'),
    ).join(
        StudentReward, StudentReward.student_id == Student.id
    ).filter(
        Student.status == 'active',
        StudentReward.year == year,
        ~StudentReward.reward_name.like('[УДАЛЕНО]%'),
    )
    if month is not None:
        query = query.filter(StudentReward.month == month)
    if group_id is not None:
        query = query.filter(Student.group_id == group_id)
    return query.group_by(
        Student.id,
        Student.group_id,
        Student.full_name,
        Student.photo_path,
        StudentReward.month,
    ).order_by(func.sum(StudentReward.points).desc()).all()


def serialize_rating_row(row):
    return {
        'student_id': row.student_id,
        'full_name': row.full_name,
        'photo_path': row.photo_path,
        'photo_url': build_photo_thumb_url(row.photo_path),
        'points': int(row.points or 0),
    }

@app.route('/rating')
@login_required
def rating_page():
    """Страница рейтинга учеников"""
    return render_template('rating.html')


@app.route('/api/rating/<int:group_id>', methods=['GET'])
@login_required
def get_group_rating(group_id):
    """Получить рейтинг учеников группы за текущий месяц"""
    try:
        from datetime import date
        current_date = date.today()
        
        # Получить настройки для количества мест в пьедестале
        settings = get_club_settings_instance()
        podium_count = getattr(settings, 'podium_display_count', 20)
        
        rating_data = [
            serialize_rating_row(row)
            for row in query_rating_totals(current_date.year, current_date.month, group_id)[:podium_count]
        ]
        
        return jsonify({
            'rating': rating_data,
            'month': current_date.month,
            'year': current_date.year
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/rating/all-groups', methods=['GET'])
@login_required
def get_all_groups_rating():
    """Получить рейтинг всех групп за текущий месяц"""
    try:
        from datetime import date
        current_date = date.today()
        
        # Получить настройки для количества мест в пьедестале
        settings = get_club_settings_instance()
        podium_count = getattr(settings, 'podium_display_count', 20)
        
        # Получить все группы
        groups = Group.query.all()
        
        rows_by_group = {}
        for row in query_rating_totals(current_date.year, current_date.month):
            bucket = rows_by_group.setdefault(row.group_id, [])
            if len(bucket) < podium_count:
                bucket.append(serialize_rating_row(row))

        result = []
        for group in groups:
            result.append({
                'group_id': group.id,
                'group_name': group.name,
                'rating': rows_by_group.get(group.id, [])
            })
        
        return jsonify({
            'groups': result,
            'month': current_date.month,
            'year': current_date.year
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/rating/winners-history', methods=['GET'])
@login_required
def get_winners_history():
    """Получить историю победителей (1 место) по месяцам для всех групп"""
    try:
        year = request.args.get('year', type=int)
        from datetime import date
        if not year:
            year = date.today().year
        
        # Получить все группы
        groups = Group.query.all()
        
        winners_map = {}
        for row in query_rating_totals(year):
            bucket = winners_map.setdefault((row.group_id, int(row.month)), [])
            if len(bucket) < 3:
                bucket.append(serialize_rating_row(row))

        result = {}
        for group in groups:
            group_winners = []
            for month in range(1, 13):
                students = winners_map.get((group.id, month), [])
                group_winners.append({
                    'month': month,
                    'students': students,
                    'is_empty': not students,
                })
            result[group.id] = {
                'group_id': group.id,
                'group_name': group.name,
                'winners': group_winners,
            }
        
        return jsonify({
            'year': year,
            'groups': list(result.values())
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ===== ЛОКАЦИИ =====

@app.route('/api/locations/cities', methods=['GET'])
def get_cities_list():
    """Получить список городов"""
    return jsonify(get_cities())


@app.route('/api/locations/districts/<city>', methods=['GET'])
def get_districts_list(city):
    """Получить список районов для города"""
    return jsonify(get_districts(city))


# ===== РАСПОЗНАВАНИЕ ЛИЦ =====

@app.route('/camera')
@login_required
def camera_page():
    """Read-only launcher/viewer for the camera kiosk running on bridge."""
    if not current_user.has_permission('camera', 'view'):
        return redirect(url_for('dashboard'))
    ensure_club_settings_columns()
    settings = get_club_settings_instance()
    kiosk_enabled = bool(getattr(settings, 'camera_kiosk_enabled', False))
    kiosk_url = (getattr(settings, 'camera_kiosk_url', '') or '').strip()
    if not kiosk_url:
        kiosk_port = int(getattr(settings, 'camera_kiosk_port', 8090) or 8090)
        kiosk_url = f'http://192.168.1.5:{kiosk_port}'
    return render_template('camera.html', kiosk_url=kiosk_url, kiosk_enabled=kiosk_enabled)



@app.route('/users')
@login_required
def users_page():
    """Страница управления пользователями"""
    # Проверка прав доступа
    if not current_user.has_permission('users', 'view'):
        return redirect(url_for('dashboard'))
    return render_template('users.html')


# ===== API ДЛЯ УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ =====

@app.route('/api/users', methods=['GET'])
@login_required
def get_users():
    """Получить список всех пользователей"""
    if not current_user.has_permission('users', 'view'):
        return jsonify({'error': 'Доступ запрещен'}), 403
    
    ensure_group_trainers_table()
    users = User.query.options(joinedload(User.trainer_group_links)).all()
    users_list = []
    for user in users:
        role_name = user.role_obj.name if user.role_obj else user.role
        primary_group_ids = sorted([
            link.group_id for link in getattr(user, 'trainer_group_links', [])
            if link.role == 'primary'
        ])
        assistant_group_ids = sorted([
            link.group_id for link in getattr(user, 'trainer_group_links', [])
            if link.role == 'assistant'
        ])
        users_list.append({
            'id': user.id,
            'username': user.username,
            'full_name': user.full_name,
            'phone': getattr(user, 'phone', None),
            'email': getattr(user, 'email', None),
            'google_linked': bool(getattr(user, 'google_sub', None)),
            'role': user.role,
            'role_id': user.role_id,
            'role_name': role_name,
            'is_active': user.is_active,
            'photo_path': user.photo_path,
            'photo_url': build_user_photo_thumb_url(user.photo_path),
            'photo_thumb_url': build_user_photo_thumb_url(user.photo_path),
            'salary_type': getattr(user, 'salary_type', 'fixed') or 'fixed',
            'fixed_salary': getattr(user, 'fixed_salary', None),
            'trainer_group_ids': primary_group_ids,
            'assistant_group_ids': assistant_group_ids,
            'created_at': user.created_at.isoformat() if user.created_at else None
        })
    
    return jsonify(users_list)


@app.route('/api/users', methods=['POST'])
@login_required
def create_user():
    """Создать нового пользователя"""
    if not current_user.has_permission('users', 'edit'):
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    try:
        ensure_group_trainers_table()
        data = request.form if request.form else (request.get_json(silent=True) or {})
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        full_name = data.get('full_name', '').strip()
        phone = (data.get('phone') or '').strip()
        email = normalize_email(data.get('email'))
        role_id = data.get('role_id') or None
        is_active = str(data.get('is_active', 'true')).lower() in ('true', '1', 'on', 'yes')
        salary_type, fixed_salary = parse_user_salary_fields(data)
        if is_guest_role_id(role_id):
            salary_type, fixed_salary = 'fixed', None
        
        if not username:
            return jsonify({'success': False, 'message': 'Введите имя пользователя'}), 400
        
        if not password or len(password) < 4:
            return jsonify({'success': False, 'message': 'Пароль должен быть не менее 4 символов'}), 400
        
        # Проверка уникальности имени пользователя
        if User.query.filter_by(username=username).first():
            return jsonify({'success': False, 'message': 'Пользователь с таким именем уже существует'}), 400

        if email and User.query.filter_by(email=email).first():
            return jsonify({'success': False, 'message': 'Пользователь с такой электронной почтой уже существует'}), 400
        
        # Создание пользователя
        user = User(
            username=username,
            password_hash=bcrypt.generate_password_hash(password).decode('utf-8'),
            full_name=full_name,
            phone=phone or None,
            email=email or None,
            role_id=role_id,
            role='custom' if role_id else 'admin',  # Для обратной совместимости
            salary_type=salary_type,
            fixed_salary=fixed_salary,
            is_active=is_active
        )
        
        db.session.add(user)
        db.session.flush()
        photo = request.files.get('photo') if request.files else None
        if photo and photo.filename:
            user.photo_path = save_user_photo(photo, user.id)
        sync_user_primary_trainer_groups(user, parse_int_list_payload(data, 'trainer_group_ids'))
        queue_hikvision_person('staff', user.id, 'staff_created')
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Пользователь успешно создан',
            'user': {
                'id': user.id,
                'username': user.username,
                'full_name': user.full_name,
                'role_id': user.role_id,
                'salary_type': user.salary_type,
                'fixed_salary': user.fixed_salary
            }
        })
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/users/<int:user_id>', methods=['PUT'])
@login_required
def update_user(user_id):
    """Обновить пользователя"""
    if not current_user.has_permission('users', 'edit'):
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    try:
        ensure_group_trainers_table()
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({'success': False, 'message': 'Пользователь не найден'}), 404
        
        data = request.form if request.form else (request.get_json(silent=True) or {})
        username = data.get('username')
        password = data.get('password')
        full_name = data.get('full_name')
        phone = data.get('phone')
        email = data.get('email')
        role_id = data.get('role_id')
        is_active = data.get('is_active')
        remove_photo = str(data.get('remove_photo', '')).lower() in ('true', '1', 'on', 'yes')
        salary_type, fixed_salary = parse_user_salary_fields(data)
        if is_guest_role_id(role_id if role_id is not None else user.role_id):
            salary_type, fixed_salary = 'fixed', None
        
        if username and username != user.username:
            if User.query.filter_by(username=username).first():
                return jsonify({'success': False, 'message': 'Пользователь с таким именем уже существует'}), 400
            user.username = username
        
        if password:
            if len(password) < 4:
                return jsonify({'success': False, 'message': 'Пароль должен быть не менее 4 символов'}), 400
            user.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        
        if full_name is not None:
            user.full_name = full_name

        if phone is not None:
            user.phone = (phone or '').strip() or None

        if email is not None:
            normalized_email = normalize_email(email)
            if normalized_email:
                existing = User.query.filter(User.email == normalized_email, User.id != user.id).first()
                if existing:
                    return jsonify({'success': False, 'message': 'Пользователь с такой электронной почтой уже существует'}), 400
            user.email = normalized_email or None
        
        if role_id is not None:
            user.role_id = role_id or None
            if role_id:
                user.role = 'custom'
        
        if is_active is not None:
            user.is_active = str(is_active).lower() in ('true', '1', 'on', 'yes')

        user.salary_type = salary_type
        user.fixed_salary = fixed_salary

        if remove_photo and user.photo_path:
            old_path = user.photo_path
            user.photo_path = None
            delete_user_photo_files(old_path)

        photo = request.files.get('photo') if request.files else None
        if photo and photo.filename:
            old_path = user.photo_path
            user.photo_path = save_user_photo(photo, user.id)
            delete_user_photo_files(old_path)

        if is_trainer_role_id(user.role_id) or user.role in TRAINER_ROLE_NAMES:
            sync_user_primary_trainer_groups(user, parse_int_list_payload(data, 'trainer_group_ids'))
        else:
            clear_user_trainer_groups(user)
        
        queue_hikvision_person('staff', user.id, 'staff_updated')
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Пользователь успешно обновлен'
        })
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    """Удалить пользователя"""
    if not current_user.has_permission('users', 'edit'):
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    try:
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({'success': False, 'message': 'Пользователь не найден'}), 404
        
        # Нельзя удалить самого себя
        if user.id == current_user.id:
            return jsonify({'success': False, 'message': 'Нельзя удалить самого себя'}), 400
        
        # Нельзя удалить последнего администратора
        if user.role == 'admin':
            admin_count = User.query.filter_by(role='admin').count()
            if admin_count <= 1:
                return jsonify({'success': False, 'message': 'Нельзя удалить последнего администратора'}), 400
        
        if user.photo_path:
            delete_user_photo_files(user.photo_path)

        db.session.delete(user)
        queue_hikvision_person('staff', user_id, 'staff_deleted', action='delete', employee_no=f"900000{user_id}")
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Пользователь успешно удален'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# ===== API ДЛЯ УПРАВЛЕНИЯ РОЛЯМИ =====

@app.route('/api/roles', methods=['GET'])
@login_required
def get_roles():
    """Получить список всех ролей с правами доступа"""
    if not current_user.has_permission('users', 'view'):
        return jsonify({'error': 'Доступ запрещен'}), 403
    
    roles = Role.query.order_by(Role.name.asc()).all()
    roles_list = []
    for role in roles:
        permissions_dict = {}
        for perm in role.permissions:
            permissions_dict[perm.section] = {
                'can_view': perm.can_view,
                'can_edit': perm.can_edit
            }
        
        roles_list.append({
            'id': role.id,
            'name': role.name,
            'description': role.description,
            'permissions': permissions_dict,
            'users_count': len(role.users),
            'is_system': role.name in SYSTEM_ROLE_NAMES
        })
    
    return jsonify(roles_list)


@app.route('/api/roles', methods=['POST'])
@login_required
def create_role():
    """Создать новую роль"""
    if not current_user.has_permission('users', 'edit'):
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    try:
        data = request.json
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        permissions = data.get('permissions', {})
        
        if not name:
            return jsonify({'success': False, 'message': 'Введите название роли'}), 400
        
        # Проверка уникальности
        if Role.query.filter_by(name=name).first():
            return jsonify({'success': False, 'message': 'Роль с таким названием уже существует'}), 400
        
        # Создание роли
        role = Role(name=name, description=description)
        db.session.add(role)
        db.session.flush()  # Получить ID роли
        
        # Добавление прав доступа
        for section in ROLE_SECTIONS:
            perm_data = permissions.get(section, {})
            permission = RolePermission(
                role_id=role.id,
                section=section,
                can_view=perm_data.get('can_view', False),
                can_edit=perm_data.get('can_edit', False)
            )
            db.session.add(permission)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Роль успешно создана',
            'role': {
                'id': role.id,
                'name': role.name
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/roles/<int:role_id>', methods=['PUT'])
@login_required
def update_role(role_id):
    """Обновить роль и её права доступа"""
    if not current_user.has_permission('users', 'edit'):
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    try:
        role = db.session.get(Role, role_id)
        if not role:
            return jsonify({'success': False, 'message': 'Роль не найдена'}), 404

        data = request.json
        name = data.get('name')
        description = data.get('description')
        permissions = data.get('permissions')
        
        if name and name != role.name:
            if Role.query.filter_by(name=name).first():
                return jsonify({'success': False, 'message': 'Роль с таким названием уже существует'}), 400
            role.name = name
        
        if description is not None:
            role.description = description
        
        # Обновление прав доступа
        if permissions:
            for section in ROLE_SECTIONS:
                perm_data = permissions.get(section, {})
                permission = RolePermission.query.filter_by(role_id=role.id, section=section).first()
                
                if permission:
                    permission.can_view = perm_data.get('can_view', False)
                    permission.can_edit = perm_data.get('can_edit', False)
                else:
                    permission = RolePermission(
                        role_id=role.id,
                        section=section,
                        can_view=perm_data.get('can_view', False),
                        can_edit=perm_data.get('can_edit', False)
                    )
                    db.session.add(permission)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Роль успешно обновлена'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/roles/<int:role_id>', methods=['DELETE'])
@login_required
def delete_role(role_id):
    """Удалить роль"""
    if not current_user.has_permission('users', 'edit'):
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    try:
        role = db.session.get(Role, role_id)
        if not role:
            return jsonify({'success': False, 'message': 'Роль не найдена'}), 404

        if role.name in SYSTEM_ROLE_NAMES:
            return jsonify({'success': False, 'message': 'Системную роль нельзя удалить'}), 400
        
        # Проверка, используется ли роль
        if len(role.users) > 0:
            return jsonify({'success': False, 'message': 'Роль используется пользователями. Сначала измените роли пользователей'}), 400
        
        db.session.delete(role)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Роль успешно удалена'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/cash')
@login_required
def cash_page():
    """Страница управления кассой - редирект на finances с вкладкой cash"""
    ensure_cash_transfers_table()
    return redirect(url_for('finances_page') + '#cash')


@app.route('/api/cash/balance', methods=['GET'])
@login_required
def get_cash_balance():
    """Получить остаток кассы (приход - расход - переданные средства)"""
    ensure_cash_transfers_table()
    from datetime import date
    from sqlalchemy import func
    
    # Общий приход
    total_income = db.session.query(func.sum(Payment.amount_paid)).scalar() or 0
    
    # Общий расход
    total_expenses = db.session.query(func.sum(Expense.amount)).scalar() or 0
    
    # Общая сумма переданных средств
    total_transferred = db.session.query(func.sum(CashTransfer.amount)).scalar() or 0
    
    # Остаток
    balance = total_income - total_expenses - total_transferred
    
    return jsonify({
        'balance': balance,
        'total_income': total_income,
        'total_expenses': total_expenses,
        'total_transferred': total_transferred
    })


@app.route('/api/cash/transfers', methods=['GET'])
@login_required
def get_cash_transfers():
    """Получить список передач денег управляющему"""
    try:
        ensure_cash_transfers_table()
        from datetime import datetime
        
        # Получить параметры фильтрации
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        recipient = request.args.get('recipient')
        
        query = CashTransfer.query
        
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                query = query.filter(CashTransfer.transfer_date >= date_from_obj)
            except:
                pass
        
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
                query = query.filter(CashTransfer.transfer_date <= date_to_obj)
            except:
                pass
        
        if recipient:
            query = query.filter(CashTransfer.recipient.ilike(f'%{recipient}%'))
        
        transfers = query.order_by(CashTransfer.transfer_date.desc()).all()
        
        transfers_list = []
        for t in transfers:
            creator_name = t.creator.username if t.creator else 'Неизвестно'
            transfers_list.append({
                'id': t.id,
                'amount': t.amount,
                'recipient': getattr(t, 'recipient', 'Не указано'),
                'transfer_date': t.transfer_date.isoformat() if isinstance(t.transfer_date, datetime) else t.transfer_date,
                'notes': t.notes,
                'created_by': t.created_by,
                'creator_name': creator_name,
                'created_at': t.created_at.isoformat() if t.created_at else None
            })
        
        return jsonify(transfers_list)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/cash/transfers', methods=['POST'])
@login_required
def create_cash_transfer():
    """Создать передачу денег управляющему"""
    ensure_cash_transfers_table()
    from datetime import datetime
    
    try:
        data = request.json
        amount = float(data.get('amount', 0))
        recipient = data.get('recipient', '').strip()
        transfer_date_str = data.get('transfer_date')
        notes = data.get('notes', '').strip()
        
        if amount <= 0:
            return jsonify({'success': False, 'message': 'Сумма должна быть больше нуля'}), 400
        
        if not recipient:
            return jsonify({'success': False, 'message': 'Укажите имя управляющего'}), 400
        
        # Парсинг даты
        if transfer_date_str:
            try:
                transfer_date = datetime.fromisoformat(transfer_date_str.replace('Z', '+00:00'))
            except:
                transfer_date = datetime.now()
        else:
            transfer_date = datetime.now()
        
        # Создать запись
        transfer = CashTransfer(
            amount=amount,
            recipient=recipient,
            transfer_date=transfer_date,
            notes=notes,
            created_by=current_user.id
        )
        
        db.session.add(transfer)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Передача денег успешно создана',
            'transfer': {
                'id': transfer.id,
                'amount': transfer.amount,
                'recipient': transfer.recipient,
                'transfer_date': transfer.transfer_date.isoformat(),
                'notes': transfer.notes
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/cash/transfers/<int:transfer_id>', methods=['PUT'])
@login_required
def update_cash_transfer(transfer_id):
    """Обновить передачу денег"""
    from datetime import datetime
    
    try:
        transfer = db.session.get(CashTransfer, transfer_id)
        if not transfer:
            return jsonify({'success': False, 'message': 'Передача не найдена'}), 404
        
        data = request.json
        amount = data.get('amount')
        recipient = data.get('recipient')
        transfer_date_str = data.get('transfer_date')
        notes = data.get('notes')
        
        if amount is not None:
            amount = float(amount)
            if amount <= 0:
                return jsonify({'success': False, 'message': 'Сумма должна быть больше нуля'}), 400
            transfer.amount = amount
        
        if recipient is not None:
            recipient = recipient.strip()
            if not recipient:
                return jsonify({'success': False, 'message': 'Укажите имя управляющего'}), 400
            transfer.recipient = recipient
        
        if transfer_date_str:
            try:
                transfer.transfer_date = datetime.fromisoformat(transfer_date_str.replace('Z', '+00:00'))
            except:
                pass
        
        if notes is not None:
            transfer.notes = notes.strip()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Передача денег успешно обновлена'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/cash/transfers/<int:transfer_id>', methods=['DELETE'])
@login_required
def delete_cash_transfer(transfer_id):
    """Удалить передачу денег"""
    try:
        transfer = db.session.get(CashTransfer, transfer_id)
        if not transfer:
            return jsonify({'success': False, 'message': 'Передача не найдена'}), 404
        
        db.session.delete(transfer)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Передача денег успешно удалена'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/recognize', methods=['POST'])
def recognize_face():
    """Распознать лицо из кадра камеры"""
    try:
        # Получить изображение (base64 или файл)
        if 'image' in request.files:
            image_file = request.files['image']
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp_recognize.jpg')
            image_file.save(temp_path)
            
            student_id = face_service.recognize_face_from_image(temp_path)
            os.remove(temp_path)
            
            if student_id:
                student = db.session.get(Student, student_id)
                return jsonify({
                    'success': True,
                    'student_id': student.id,
                    'student_name': student.full_name,
                    'balance': calculate_student_balance(student),
                    'photo': student.photo_path
                })
            else:
                return jsonify({'success': False, 'message': 'Лицо не распознано'})
        
        return jsonify({'success': False, 'message': 'Нет изображения'}), 400
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/recognize_multiple', methods=['POST'])
def recognize_multiple_faces():
    """Распознать несколько лиц из кадра камеры"""
    try:
        if 'image' in request.files:
            image_file = request.files['image']
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp_recognize.jpg')
            image_file.save(temp_path)
            
            recognized = face_service.recognize_multiple_faces_from_image(temp_path)
            os.remove(temp_path)
            
            if len(recognized) > 0:
                students_data = []
                for item in recognized:
                    student = db.session.get(Student, item['student_id'])
                    if student:
                        students_data.append({
                            'student_id': student.id,
                            'student_name': student.full_name,
                            'balance': calculate_student_balance(student),
                            'photo': student.photo_path
                        })
                
                return jsonify({
                    'success': True,
                    'count': len(students_data),
                    'students': students_data
                })
            else:
                return jsonify({'success': False, 'message': 'Лица не распознаны'})
        
        return jsonify({'success': False, 'message': 'Нет изображения'}), 400
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/students/<int:student_id>/delete-photo', methods=['POST'])
@login_required
def delete_student_photo(student_id):
    """Удалить фотографию ученика"""
    try:
        student = Student.query.get_or_404(student_id)
        if student.photo_path and os.path.exists(student.photo_path):
            try:
                os.remove(student.photo_path)
            except Exception as e:
                print(f"Ошибка при удалении файла: {e}")
        
        student.photo_path = None
        student.face_encoding = None
        access_face_verifier.invalidate_candidate_index()
        queue_hikvision_person('student', student.id, 'student_photo_deleted')
        db.session.commit()
        
        # Обновить кэш лиц
        reload_face_encodings()
        
        return jsonify({'success': True, 'message': 'Фотография удалена'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/recognize_from_cam', methods=['POST'])
@login_required
def recognize_from_cam():
    """Распознать лицо напрямую из потока камеры (берем готовые данные из фонового потока)"""
    try:
        # Получаем результаты из сервиса
        faces, _ = face_service.get_latest_results()
        
        results = []
        for face in faces:
            # Если лицо распознано и есть ID
            if face.get('is_recognized') and face.get('student_id'):
                student_id = face['student_id']
                
                # Загружаем инфо о студенте
                student = db.session.get(Student, student_id)
                if student:
                    results.append({
                        'student_id': student.id,
                        'student_name': student.full_name,
                        'balance': calculate_student_balance(student),
                        'photo': student.photo_path
                    })
        
        return jsonify({
            'success': True,
            'count': len(results),
            'students': results
        })
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"❌ Ошибка recognize_from_cam: {e}\n{error_trace}")
        return jsonify({'success': False, 'message': str(e)}), 500


def reload_face_encodings():
    """Перезагрузить все face encodings в память"""
    students = Student.query.filter_by(status='active').all()
    face_service.load_students(students)


# ===== ИНИЦИАЛИЗАЦИЯ =====

def init_db():
    """Создать таблицы и первого админа"""
    with app.app_context():
        db.create_all()
        
        # Выполнить миграции ОДИН РАЗ при запуске
        print("🛠️ Проверка и обновление структуры БД...")
        ensure_users_table_columns()
        ensure_roles_tables()
        ensure_club_settings_columns()
        ensure_students_columns()
        ensure_cash_transfers_table()
        ensure_device_commands_table()
        ensure_bridge_status_table()
        ensure_access_logs_table()
        ensure_tournament_tables()
        ensure_payment_columns()
        ensure_payment_indexes()
        ensure_payment_type_column()
        
        # Проверить, есть ли админ
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                password_hash=bcrypt.generate_password_hash('admin123').decode('utf-8'),
                role='admin'
            )
            db.session.add(admin)
            db.session.commit()
            print("Создан администратор: admin / admin123")
        
        # Убедиться, что у всех учеников есть код Telegram
        students_without_code = Student.query.filter(
            (Student.telegram_link_code.is_(None)) | (Student.telegram_link_code == '')
        ).all()
        if students_without_code:
            for student in students_without_code:
                ensure_student_has_telegram_code(student)
            db.session.commit()
            print(f"✓ Сгенерированы коды Telegram для {len(students_without_code)} учеников")
        
        # ОДИН РАЗ загружаем encodings
        print("👤 Загрузка базы лиц...")
        reload_face_encodings()


# ===== ПОМЕСЯЧНЫЕ ОПЛАТЫ =====

@app.route('/api/students/<int:student_id>/monthly-payments', methods=['GET'])
@login_required
def get_monthly_payments(student_id):
    """Получить помесячные оплаты ученика"""
    try:
        # Получить студента и его тариф
        student = db.session.get(Student, student_id)
        if not student:
            return jsonify({'error': 'Студент не найден'}), 404
        
        # Явно загружаем тариф, если он есть
        tariff_price = 0
        tariff_name = None
        if student.tariff_id:
            tariff = db.session.get(Tariff, student.tariff_id)
            if tariff:
                tariff_name = tariff.name
                tariff_price = float(tariff.price) if tariff.price else 0
        elif student.tariff:
            # Если тариф загружен через relationship
            tariff_name = student.tariff.name if student.tariff.name else None
            tariff_price = float(student.tariff.price) if student.tariff.price else 0
        
        # Получить все платежи ученика с метаданными месяца
        payments = Payment.query.filter_by(student_id=student_id).order_by(Payment.payment_date.desc()).all()
        
        # Группировать по месяцам используя payment_month и payment_year
        payments_by_month = {}
        for payment in payments:
            # Использовать payment_month/payment_year если есть, иначе брать из payment_date
            if payment.payment_month and payment.payment_year:
                month_key = f"{payment.payment_year}-{str(payment.payment_month).zfill(2)}"
            elif payment.payment_date:
                month_key = payment.payment_date.strftime('%Y-%m')
            else:
                continue
                
            if month_key not in payments_by_month:
                payments_by_month[month_key] = {
                    'payments': [],
                    'total_paid': 0,
                    'tariff_price': tariff_price,
                    'remainder': tariff_price
                }
            
            payments_by_month[month_key]['payments'].append({
                'id': payment.id,
                'date': payment.payment_date.isoformat() if payment.payment_date else None,
                'amount': float(payment.amount_paid),
                'payment_type': payment.payment_type or 'cash',
                'notes': payment.notes or '',
                'tariff_name': payment.tariff_name or ''
            })
            payments_by_month[month_key]['total_paid'] += float(payment.amount_paid)
            payments_by_month[month_key]['remainder'] = max(0, tariff_price - payments_by_month[month_key]['total_paid'])
        
        return jsonify({
            'payments_by_month': payments_by_month,
            'tariff_price': tariff_price,
            'tariff_name': tariff_name
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/students/add-monthly-payment', methods=['POST'])
@login_required
def add_monthly_payment():
    """Добавить помесячную оплату"""
    try:
        data = request.json
        student_id = data.get('student_id')
        year = data.get('year')
        month = data.get('month')
        payment_date = data.get('payment_date')
        amount = float(data.get('amount', 0))
        payment_type = data.get('payment_type', 'cash')  # Тип оплаты: cash, card, click, payme, uzum
        notes = data.get('notes', '')
        
        student = db.session.get(Student, student_id)
        if not student:
            return jsonify({'success': False, 'message': 'Ученик не найден'})

        # Блокировка оплат за будущие месяцы, если включено в настройках клуба
        settings = get_club_settings_instance()
        if getattr(settings, 'block_future_payments', False):
            today = get_local_date()
            if year > today.year or (year == today.year and month > today.month):
                return jsonify({'success': False, 'message': 'Оплата за будущие месяцы запрещена настройками клуба'}), 400

        # Проверка тарифа и текущих оплат за месяц
        tariff_price = None
        if student.tariff_id:
            tariff = db.session.get(Tariff, student.tariff_id)
            tariff_price = float(tariff.price) if tariff and tariff.price is not None else None

        if tariff_price is not None:
            existing_paid = db.session.query(db.func.sum(Payment.amount_paid)).filter(
                Payment.student_id == student_id,
                Payment.payment_year == year,
                Payment.payment_month == month
            ).scalar() or 0
            if existing_paid + amount > tariff_price:
                remainder = max(0, tariff_price - existing_paid)
                return jsonify({
                    'success': False,
                    'message': f'Оплата превышает стоимость тарифа. Осталось не более {remainder:.0f} сум'
                }), 400
        
        # Создать запись оплаты с привязкой к выбранному месяцу через notes и метаданные
        # payment_date используется только как дата фактической транзакции
        month_label = f"{month}/{year}"
        payment = Payment(
            student_id=student_id,
            tariff_id=student.tariff_id if student.tariff_id else None,
            amount_paid=amount,
            amount_due=0,
            payment_date=datetime.fromisoformat(payment_date),
            payment_type=payment_type,
            notes=f"{notes} (Оплата за {month_label})" if notes else f"Оплата за {month_label}",
            lessons_added=0,
            # Сохранить месяц в отдельном поле для корректной группировки
            payment_month=month,
            payment_year=year,
            is_discount=bool(data.get('is_discount'))
        )
        
        db.session.add(payment)
        log_student_event(
            student_id, 'payment_added',
            f'Добавлена оплата {format_money_ru(amount)} сум за {month:02d}.{year}',
            [f'Способ: {payment_type}',
             f'Дата оплаты: {datetime.fromisoformat(payment_date).strftime("%d.%m.%Y")}']
            + (['Отмечено скидкой: остаток за месяц долгом не считается']
               if data.get('is_discount') else [])
        )
        queue_hikvision_person('student', student_id, 'monthly_payment_added')
        db.session.commit()
        
        # Вычислить долг за этот месяц
        tariff_price = tariff_price or 0
        existing_paid = existing_paid or 0
        total_paid_after = existing_paid + amount
        debt = max(0, tariff_price - total_paid_after) if tariff_price > 0 else 0
        
        # Отправить уведомление в Telegram
        try:
            send_payment_notification(
                student_id=student_id,
                payment_date=payment.payment_date,
                month=month_label,
                payment_type=payment_type,
                amount_paid=amount,
                debt=debt if debt > 0 else None
            )
            
            # --- УВЕДОМЛЕНИЕ ДЛЯ РУКОВОДСТВА ---
            msg_mgmt = (
                f"💰 <b>Новая оплата (Помесячно)</b>\n"
                f"👤 Ученик: {student.full_name}\n"
                f"📆 Месяц: {month_label}\n"
                f"💵 Сумма: {format_currency(amount)} сум\n"
                f"💳 Тип: {payment_type}\n"
                f"📅 Дата: {payment.payment_date.strftime('%d.%m.%Y')}\n"
            )
            if debt > 0:
                msg_mgmt += f"⚠️ Долг за месяц: {format_currency(debt)} сум\n"
            
            send_management_notification(msg_mgmt, roles=['director', 'founder', 'cashier'])
            
        except Exception as e:
            print(f"Ошибка отправки уведомления об оплате: {e}")
            # Не прерываем выполнение, если уведомление не отправилось
        
        return jsonify({
            'success': True,
            'message': 'Оплата добавлена',
            'payment_id': payment.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/payments/<int:payment_id>', methods=['PUT'])
@login_required
def update_payment(payment_id):
    """Редактирование существующей оплаты (сумма, дата, комментарий)"""
    # Разрешим роли: admin, financier, payment_admin
    if getattr(current_user, 'role', None) not in ['admin', 'financier', 'payment_admin']:
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403

    try:
        data = request.get_json() or {}
        payment = db.session.get(Payment, payment_id)
        if not payment:
            return jsonify({'success': False, 'message': 'Оплата не найдена'}), 404
        month_labels_to_fix = None
        # Запоминаем "до", чтобы в истории было видно, что именно поменяли
        before = {
            'amount': float(payment.amount_paid or 0),
            'month': f'{payment.payment_month:02d}.{payment.payment_year}',
            'date': payment.payment_date.strftime('%d.%m.%Y') if payment.payment_date else '',
            'type': payment.payment_type or '',
        }
        changes = []

        # За какой месяц засчитана оплата (тренер мог выбрать не тот)
        if data.get('payment_month') and data.get('payment_year'):
            try:
                new_month = int(data['payment_month'])
                new_year = int(data['payment_year'])
            except (TypeError, ValueError):
                return jsonify({'success': False, 'message': 'Неверный месяц или год'}), 400
            if not 1 <= new_month <= 12:
                return jsonify({'success': False, 'message': 'Месяц должен быть от 1 до 12'}), 400
            if not 2000 <= new_year <= 2100:
                return jsonify({'success': False, 'message': 'Неверный год'}), 400
            month_labels_to_fix = (
                f'{payment.payment_month}/{payment.payment_year}',
                f'{new_month}/{new_year}',
            )
            payment.payment_month = new_month
            payment.payment_year = new_year
            if before['month'] != f'{new_month:02d}.{new_year}':
                changes.append(f"Месяц: {before['month']} → {new_month:02d}.{new_year}")

        # Валидация суммы
        if 'amount_paid' in data:
            new_amount = float(data.get('amount_paid'))
            if new_amount <= 0:
                return jsonify({'success': False, 'message': 'Сумма должна быть положительной'}), 400
            # Проверяем лимит по тарифу в рамках того же месяца
            tariff_price = None
            if payment.tariff_id:
                tariff_obj = db.session.get(Tariff, payment.tariff_id)
                tariff_price = float(tariff_obj.price) if tariff_obj and tariff_obj.price is not None else None
            if tariff_price is not None:
                existing_paid = db.session.query(db.func.sum(Payment.amount_paid)).filter(
                    Payment.student_id == payment.student_id,
                    Payment.payment_year == payment.payment_year,
                    Payment.payment_month == payment.payment_month,
                    Payment.id != payment.id
                ).scalar() or 0
                if existing_paid + new_amount > tariff_price:
                    remainder = max(0, tariff_price - existing_paid)
                    return jsonify({'success': False, 'message': f'Сумма превышает стоимость тарифа. Доступно не более {remainder:.0f} сум'}), 400
            if abs(before['amount'] - new_amount) > 0.009:
                changes.append(
                    f"Сумма: {format_money_ru(before['amount'])} → {format_money_ru(new_amount)} сум"
                )
            payment.amount_paid = new_amount

        if 'payment_date' in data and data.get('payment_date'):
            try:
                payment_date_str = data.get('payment_date')
                # Если дата в формате YYYY-MM-DD, добавить время
                if len(payment_date_str) == 10:
                    payment_date_str += 'T00:00:00'
                payment.payment_date = datetime.fromisoformat(payment_date_str.replace('Z', '+00:00'))
                if before['date'] != payment.payment_date.strftime('%d.%m.%Y'):
                    changes.append(f"Дата оплаты: {before['date']} → {payment.payment_date.strftime('%d.%m.%Y')}")
            except ValueError as e:
                return jsonify({'success': False, 'message': f'Неверный формат даты: {str(e)}'}), 400

        if 'is_discount' in data:
            new_discount = bool(data.get('is_discount'))
            if bool(payment.is_discount) != new_discount:
                changes.append('Скидка: ' + ('включена' if new_discount else 'снята'))
            payment.is_discount = new_discount

        if 'payment_type' in data:
            if (data.get('payment_type') or '') != before['type']:
                changes.append(f"Способ оплаты: {before['type'] or '—'} → {data.get('payment_type')}")
            payment.payment_type = data.get('payment_type')

        if 'notes' in data:
            payment.notes = data.get('notes')

        if changes:
            log_student_event(
                payment.student_id, 'payment_updated',
                f'Оплата изменена: {format_money_ru(payment.amount_paid)} сум '
                f'за {payment.payment_month:02d}.{payment.payment_year}',
                changes
            )

        # Подпись "Оплата за 7/2026" правим последней, уже поверх присланного текста
        if month_labels_to_fix and payment.notes:
            old_label, new_label = month_labels_to_fix
            if old_label != new_label:
                payment.notes = payment.notes.replace(
                    f'Оплата за {old_label}', f'Оплата за {new_label}'
                )

        queue_hikvision_person('student', payment.student_id, 'payment_updated')
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/payments/<int:payment_id>/delete', methods=['DELETE'])
@login_required
def delete_payment(payment_id):
    """Удалить оплату"""
    if getattr(current_user, 'role', None) not in ['admin', 'financier', 'payment_admin']:
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403

    try:
        payment = db.session.get(Payment, payment_id)
        if not payment:
            return jsonify({'success': False, 'message': 'Оплата не найдена'}), 404

        student = payment.student
        student_id = payment.student_id
        log_student_event(
            student_id, 'payment_deleted',
            f'Удалена оплата {format_money_ru(payment.amount_paid)} сум '
            f'за {payment.payment_month:02d}.{payment.payment_year}',
            [f'Дата оплаты: {payment.payment_date.strftime("%d.%m.%Y")}' if payment.payment_date else '',
             f'Способ: {payment.payment_type or "—"}']
        )
        db.session.delete(payment)
        queue_hikvision_person('student', student_id, 'payment_deleted')
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Оплата удалена',
            'new_balance': calculate_student_balance(student) if student else None
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/payments/<int:payment_id>/refund', methods=['POST'])
@login_required
def refund_payment(payment_id):
    """Возврат оплаты - создание обратной записи"""
    if getattr(current_user, 'role', None) not in ['admin', 'financier', 'payment_admin']:
        return jsonify({'success': False, 'message': 'Нет доступа'}), 403

    try:
        original_payment = db.session.get(Payment, payment_id)
        if not original_payment:
            return jsonify({'success': False, 'message': 'Оплата не найдена'}), 404

        # Создать обратную запись с отрицательной суммой
        refund_payment = Payment(
            student_id=original_payment.student_id,
            tariff_id=original_payment.tariff_id,
            amount_paid=-original_payment.amount_paid,  # Отрицательная сумма
            amount_due=0,
            lessons_added=-original_payment.lessons_added if original_payment.lessons_added else 0,  # Отрицательные уроки
            is_full_payment=False,
            payment_date=get_local_datetime(),
            tariff_name=original_payment.tariff_name,
            notes=f"Возврат оплаты #{original_payment.id}" + (f" ({original_payment.notes})" if original_payment.notes else ""),
            created_by=current_user.id,
            payment_month=original_payment.payment_month,
            payment_year=original_payment.payment_year,
            payment_type=original_payment.payment_type
        )
        
        db.session.add(refund_payment)
        queue_hikvision_person('student', original_payment.student_id, 'payment_refunded')
        db.session.commit()

        student = original_payment.student
        return jsonify({
            'success': True,
            'message': 'Возврат оплаты выполнен',
            'new_balance': calculate_student_balance(student) if student else None,
            'refund_id': refund_payment.id
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# ===== TELEGRAM API =====

@app.route('/api/telegram/register-by-phone', methods=['POST'])
def telegram_register_by_phone():
    """Регистрация Telegram по номеру телефона (контакту)"""
    data = request.get_json()
    chat_id = data.get('chat_id')
    raw_phone = data.get('phone')  # Номер от Telegram (может быть с + или без)
    
    if not chat_id or not raw_phone:
        return jsonify({'success': False, 'message': 'Нет данных'}), 400
        
    # Нормализация телефона для поиска: убираем всё кроме цифр
    phone_digits = ''.join(filter(str.isdigit, raw_phone))
    
    # --- ПРОВЕРКА НА РУКОВОДСТВО ---
    settings = get_club_settings_instance()
    
    is_director = phones_match_simple(getattr(settings, 'director_phone', ''), phone_digits)
    is_founder = phones_match_simple(getattr(settings, 'founder_phone', ''), phone_digits)
    is_cashier = phones_match_simple(getattr(settings, 'cashier_phone', ''), phone_digits)
    
    if is_director or is_founder or is_cashier:
        if is_director:
            settings.director_chat_id = str(chat_id)
        if is_founder:
            settings.founder_chat_id = str(chat_id)
        if is_cashier:
            settings.cashier_chat_id = str(chat_id)
            
        db.session.commit()
        
        roles = []
        if is_director: roles.append("Директор")
        if is_founder: roles.append("Учредитель")
        if is_cashier: roles.append("Кассир")
        
        return jsonify({
            'success': True,
            'message': f'Вы успешно авторизованы как: {", ".join(roles)}',
            'is_staff': True,
            'roles': roles
        })

    # --- ПОИСК УЧЕНИКА ---
    # Пытаемся найти ученика
    candidates = Student.query.filter(or_(Student.phone.isnot(None), Student.parent_phone.isnot(None))).all()
    matched_student = None
    
    for student in candidates:
        # Используем существующую умную проверку телефонов
        if phones_match(student.phone, list_to_phone(phone_digits)) or \
           phones_match(student.parent_phone, list_to_phone(phone_digits)) or \
           phones_match(student.phone, raw_phone) or \
           phones_match(student.parent_phone, raw_phone):
            matched_student = student
            break
            
    # Дополнительная попытка: если в базе номера без +, а пришел с + (или наоборот)
    if not matched_student:
         # Ищем по последним 9 цифрам (универсально)
         short_phone = phone_digits[-9:] if len(phone_digits) >= 9 else phone_digits
         for student in candidates:
             s_ph = ''.join(filter(str.isdigit, student.phone or ''))
             p_ph = ''.join(filter(str.isdigit, student.parent_phone or ''))
             if s_ph.endswith(short_phone) or p_ph.endswith(short_phone):
                 matched_student = student
                 break

    if matched_student:
        # Сохраняем chat_id
        matched_student.telegram_chat_id = str(chat_id)
        ensure_student_has_telegram_code(matched_student)
        db.session.commit()
        
        group_name = matched_student.group.name if matched_student.group else 'Без группы'
        
        return jsonify({
            'success': True,
            'message': f'Ты успешно привязан!',
            'student': {
                'id': matched_student.id,
                'full_name': matched_student.full_name,
                'group_name': group_name,
                'code': matched_student.telegram_link_code
            }
        })
    else:
        return jsonify({
            'success': False, 
            'message': 'Номер телефона не найден в базе учеников. Обратись к администратору.'
        })

def phones_match_simple(stored_phone, input_digits):
    """Простое сравнение телефонов по последним 9 цифрам"""
    if not stored_phone: return False
    stored_digits = ''.join(filter(str.isdigit, stored_phone))
    if len(stored_digits) < 9 or len(input_digits) < 9:
        return False # Слишком короткие номера
    return stored_digits[-9:] == input_digits[-9:]

def list_to_phone(digits):
    return digits # Заглушка, используем просто строку цифр для матчинга

@app.route('/api/telegram/register', methods=['POST'])
def telegram_register():
    """
    API для регистрации ученика в Telegram боте
    Используется ботом для привязки ученика по коду
    """
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        code = data.get('code')
        
        if not chat_id:
            return jsonify({'success': False, 'message': 'Chat ID не указан'}), 400
        
        if not code:
            return jsonify({'success': False, 'message': 'Код не указан'}), 400
        
        success, message, student = register_student_by_code(chat_id, code)
        
        if success:
            return jsonify({
                'success': True,
                'message': message,
                'student': {
                    'id': student.id,
                    'full_name': student.full_name,
                    'group_name': student.group.name if student.group else None
                }
            })
        else:
            return jsonify({'success': False, 'message': message}), 400
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/telegram/attendance-report', methods=['GET'])
def get_telegram_attendance_report():
    """Отчет о посещаемости для Telegram бота"""
    target_date_str = request.args.get('date') # '2023-11-20'
    if not target_date_str:
        return jsonify({'success': False, 'message': 'Дата не указана'}), 400
        
    try:
        target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'success': False, 'message': 'Неверный формат даты'}), 400
        
    all_groups = Group.query.order_by(Group.name).all()
    if not all_groups:
        return jsonify({'success': True, 'text': "Группы не найдены."})
        
    report_lines = [f"📊 <b>Посещаемость ({target_date.strftime('%d.%m.%Y')})</b>\n"]
    
    total_found = 0
    for group in all_groups:
        students = Student.query.filter_by(group_id=group.id, status='active').order_by(Student.full_name).all()
        if not students:
            continue
            
        total_found += 1
        report_lines.append(f"<b>🏗 Группа: {group.name}</b>")
        
        # Получаем список ID присутствующих в этой группе за этот день
        present_student_ids = set(
            row[0] for row in db.session.query(Attendance.student_id).filter_by(date=target_date).all()
        )
        
        for i, student in enumerate(students, 1):
            status_icon = "✅" if student.id in present_student_ids else "❌"
            report_lines.append(f"{i}. {student.full_name} — {status_icon}")
        
        report_lines.append("") # Пустая строка между группами
        
    if total_found == 0:
        final_text = f"На {target_date.strftime('%d.%m.%Y')} активных групп не найдено."
    else:
        final_text = "\n".join(report_lines)
        
    return jsonify({'success': True, 'text': final_text})

@app.route('/api/club-settings/public', methods=['GET'])
def get_club_settings_public():
    """
    Публичный endpoint для получения токена бота
    Используется только ботом для получения токена
    """
    settings = get_club_settings_instance()
    return jsonify({
        'system_name': settings.system_name or 'FK QORASUV',
        'logo_url': get_system_logo_url(settings),
        'square_logo_url': get_system_square_logo_url(settings),
        'telegram_bot_token': settings.telegram_bot_token or '',
        'director_phone': getattr(settings, 'director_phone', '') or '',
        'founder_phone': getattr(settings, 'founder_phone', '') or '',
        'cashier_phone': getattr(settings, 'cashier_phone', '') or ''
    })


@app.route('/api/service-control/state', methods=['GET'])
def get_service_control_state():
    """Публичный статус блокировки сервиса для frontend-overlay."""
    service_key = (request.args.get('service') or SERVICE_PRIMARY_KEY).strip()
    payload = build_service_state_payload(service_key)
    if not payload.get('success'):
        return jsonify(payload), 404
    return jsonify(payload)


@app.route('/api/telegram/service-control/status', methods=['GET'])
def telegram_service_control_status():
    """Статус сервиса для Telegram меню управления (staff + owner bot)."""
    service_key = (request.args.get('service') or SERVICE_PRIMARY_KEY).strip()
    chat_id = (request.args.get('chat_id') or '').strip()

    if not chat_id:
        return jsonify({'success': False, 'message': 'chat_id не указан'}), 400

    settings = get_club_settings_instance()
    if not can_manage_service_from_telegram(chat_id, settings):
        return jsonify({'success': False, 'message': 'Доступ запрещен для этого chat_id'}), 403

    payload = build_service_state_payload(service_key)
    if not payload.get('success'):
        return jsonify(payload), 404

    return jsonify(payload)


@app.route('/api/telegram/service-control/toggle', methods=['POST'])
def telegram_service_control_toggle():
    """Переключение сервиса из Telegram меню управления (staff + owner bot)."""
    data = request.get_json() or {}
    service_key = (data.get('service') or SERVICE_PRIMARY_KEY).strip()
    chat_id = str(data.get('chat_id') or '').strip()

    if not chat_id:
        return jsonify({'success': False, 'message': 'chat_id не указан'}), 400

    settings = get_club_settings_instance()
    if not can_manage_service_from_telegram(chat_id, settings):
        return jsonify({'success': False, 'message': 'Доступ запрещен для этого chat_id'}), 403

    try:
        controls = load_service_controls(settings)
        if service_key not in controls:
            return jsonify({'success': False, 'message': 'Сервис не найден'}), 404

        controls[service_key]['enabled'] = not bool(controls[service_key].get('enabled', True))
        controls[service_key]['updated_at'] = get_local_time().strftime('%Y-%m-%d %H:%M:%S')
        controls[service_key]['updated_by'] = f"chat:{chat_id}"
        controls[service_key]['support_phone'] = (
            controls[service_key].get('support_phone') or SERVICE_SUPPORT_PHONE_DEFAULT
        )

        save_service_controls(settings, controls)
        db.session.commit()

        payload = build_service_state_payload(service_key)
        return jsonify(payload)
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/telegram/send-payment-reminders', methods=['POST'])
@login_required
def send_payment_reminders_api():
    """
    Ручная отправка напоминаний об оплате (для тестирования или ручного запуска)
    """
    if current_user.role not in ['admin']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    try:
        result = send_monthly_payment_reminders()
        return jsonify(result)
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Ошибка при отправке напоминаний об оплате: {error_trace}")
        return jsonify({'success': False, 'message': f'Ошибка: {str(e)}'}), 500


@app.route('/api/groups/<int:group_id>/send-notification', methods=['POST'])
@login_required
def send_group_notification_api(group_id):
    """
    Отправить уведомления всем ученикам группы
    """
    if current_user.role not in ['admin', 'teacher']:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    try:
        data = request.get_json() or {}
        additional_text = data.get('additional_text', '')
        
        result = send_group_notification(group_id, additional_text)
        
        if result.get('success'):
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Ошибка при отправке уведомлений: {error_trace}")
        return jsonify({'success': False, 'message': f'Ошибка: {str(e)}'}), 500

@app.route('/api/system_stats', methods=['GET'])
def get_system_stats():
    """Получить параметры загрузки системы (Task Manager style)"""
    stats = {
        'cpu': psutil.cpu_percent(interval=None),
        'ram': psutil.virtual_memory().percent,
        'gpu': 0,
        'vram': 0,
        'gpu_temp': 0,
        'gpu_name': 'N/A'
    }
    
    if NVML_ENABLED:
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            name = pynvml.nvmlDeviceGetName(handle)
            
            stats['gpu'] = util.gpu
            stats['vram'] = int((mem.used / mem.total) * 100)
            stats['gpu_temp'] = temp
            stats['gpu_name'] = name.decode('utf-8') if isinstance(name, bytes) else name
        except Exception as e:
            print(f"NVML Error: {e}")
            
    return jsonify(stats)


@app.route('/api/camera/settings', methods=['GET', 'POST'])
def handle_camera_settings():
    """Управление настройками качества камеры"""
    global CAMERA_OVERRIDE_SOURCE
    camera = get_camera()
    if not camera:
        return jsonify({'success': False, 'message': 'Камера не доступна'}), 400
        
    if request.method == 'GET':
        return jsonify({
            'success': True, 
            'settings': {
                **camera.output_settings,
                'source': 'webcam' if CAMERA_OVERRIDE_SOURCE == 0 else 'ezviz'
            }
        })
        
    # POST
    data = request.json
    resolution = data.get('resolution')
    quality = data.get('quality')
    source = data.get('source') # 'webcam' или 'ezviz'

    if source == 'webcam':
        CAMERA_OVERRIDE_SOURCE = 0
    elif source == 'ezviz':
        CAMERA_OVERRIDE_SOURCE = None # Вернуться к настройкам БД
    
    if resolution in ['720p', '1080p', '2k']:
        camera.output_settings['resolution'] = resolution
        
    if quality:
        try:
            q = int(quality)
            if 1 <= q <= 100:
                camera.output_settings['quality'] = q
        except ValueError:
            pass
            
    return jsonify({
        'success': True, 
        'settings': camera.output_settings
    })


# Планировщик для автоматической отправки напоминаний об оплате
def send_daily_summary():
    """Ежедневный отчет руководству (21:00)"""
    with app.app_context():
        try:
            today = date.today()
            today_str = today.strftime('%d.%m.%Y')
            
            # 1. Посещаемость
            # Нужно найти все группы, у которых были занятия сегодня
            # Это сложная логика, пока просто возьмем всех студентов, у которых status='active'
            total_students = Student.query.filter_by(status='active').count()
            
            # Для точной посещаемости нужно смотреть таблицу Attendance (если она есть)
            # Предположим, у нас есть посещаемость. Если нет, покажем общие цифры.
            # (Здесь упрощенная логика, так как модели Attendance я не видел, но она подразумевается)
            
            # 2. Финансы (Оплаты)
            payments_today = Payment.query.filter(func.date(Payment.payment_date) == today).all()
            total_income = sum(p.amount_paid for p in payments_today)
            income_count = len(payments_today)
            
            # 3. Расходы
            expenses_today = Expense.query.filter(func.date(Expense.expense_date) == today).all()
            total_expenses = sum(e.amount for e in expenses_today)
            expense_count = len(expenses_today)
            
            # 4. Баланс
            balance = total_income - total_expenses
            
            msg = (
                f"📊 <b>Ежедневная сводка ({today_str})</b>\n\n"
                f"👥 <b>Ученики:</b>\n"
                f"   • Активных: {total_students}\n\n"
                f"💰 <b>Финансы:</b>\n"
                f"   • Приход: {format_currency(total_income)} сум ({income_count} платежей)\n"
                f"   • Расход: {format_currency(total_expenses)} сум ({expense_count} записей)\n"
                f"   • Сальдо: {format_currency(balance)} сум\n\n"
                f"<i>Подробности смотрите в CRM.</i>"
            )
            
            send_management_notification(msg, roles=['director', 'founder'])
            print(f"Ежедневная сводка отправлена {today_str}")
            
        except Exception as e:
            print(f"Ошибка в send_daily_summary: {e}")

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

def setup_scheduler():
    """Настройка планировщика для автоматической отправки напоминаний"""
    scheduler = BackgroundScheduler()
    
    # Запускать каждый день в 9:00 утра, но функция сама проверит, что это начало месяца (1-3 число)
    scheduler.add_job(
        func=send_monthly_payment_reminders_job,
        trigger=CronTrigger(hour=9, minute=0),
        id='send_payment_reminders',
        name='Отправка напоминаний об оплате',
        replace_existing=True
    )
    
    # Ежедневный отчет для руководства в 21:00
    scheduler.add_job(
        func=send_daily_summary,
        trigger=CronTrigger(hour=21, minute=0),
        id='send_daily_summary',
        name='Ежедневная сводка руководству',
        replace_existing=True
    )
    
    # Автоархив тех, кто давно не приходит: раз в сутки ночью
    scheduler.add_job(
        func=auto_archive_job,
        trigger=CronTrigger(hour=4, minute=30),
        id='auto_archive_students',
        name='Автоархив учеников без занятий',
        replace_existing=True
    )

    scheduler.start()
    print("✅ Планировщик запущен: автоматическая отправка напоминаний об оплате в начале месяца")
    return scheduler

def send_monthly_payment_reminders_job():
    """Задача для планировщика - отправка напоминаний об оплате"""
    with app.app_context():
        try:
            result = send_monthly_payment_reminders()
            print(f"📧 Напоминания об оплате: {result.get('message', 'Выполнено')}")
        except Exception as e:
            print(f"❌ Ошибка при отправке напоминаний об оплате: {e}")



# --- АВТОМАТИЧЕСКАЯ ИНИЦИАЛИЗАЦИЯ БД ---
# Выполняется при импорте модуля (работает и для Gunicorn на Railway, и локально)
with app.app_context():
    try:
        print("🔄 Проверка и создание таблиц БД...")
        db.create_all()
        # Теперь функции определены, можно вызывать
        ensure_users_table_columns()
        ensure_roles_tables()
        ensure_club_settings_columns()
        ensure_students_columns()
        ensure_expense_columns()
        ensure_cash_transfers_table()
        ensure_device_commands_table()
        ensure_bridge_status_table()
        ensure_access_logs_table()
        ensure_tournament_tables()
        ensure_payment_columns()
        ensure_payment_indexes()
        
        # Создание администратора
        print("👤 Проверка пользователя admin...")
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            print("🛠 Создание пользователя admin...")
            # Ищем роль
            admin_role = Role.query.filter_by(name='Администратор').first()
            role_id = admin_role.id if admin_role else None
            
            hashed_pw = bcrypt.generate_password_hash('admin').decode('utf-8')
            new_admin = User(
                username='admin', 
                password_hash=hashed_pw, 
                role='admin',
                role_id=role_id,
                full_name='Super Admin'
            )
            db.session.add(new_admin)
            db.session.commit()
            print("✅ Пользователь admin успешно создан (пароль: admin)")
        else:
            print("✅ Пользователь admin уже существует")

        print("✅ База данных успешно инициализирована")
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")
        import traceback
        traceback.print_exc()
# ---------------------------------------------
    # Восстановление дефолтных ассетов (если Volume пустой)
    try:
        backup_root = 'defaults'
        if os.path.exists(backup_root):
            print(f"📦 Поиск ассетов в: {backup_root}")
            files_in_backup = os.listdir(backup_root)
            print(f"📄 Найдены файлы в бэкапе: {files_in_backup}")

            upload_dir = app.config['UPLOAD_FOLDER']
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)
            
            restored_count = 0
            for filename in files_in_backup:
                src = os.path.join(backup_root, filename)
                
                # Игнорируем вложенные папки, берем только файлы
                if os.path.isdir(src):
                    continue
                    
                dst = os.path.join(upload_dir, filename)
                
                # Принудительно копируем (перезаписываем), чтобы исправить возможные битые файлы
                try:
                    shutil.copy2(src, dst)
                    restored_count += 1
                except Exception as copy_err:
                    print(f"⚠️ Не удалось скопировать {filename}: {copy_err}")
            
            if restored_count > 0:
                print(f"✅ Восстановлено {restored_count} файлов ассетов из {backup_root}")
            else:
                print("✅ Все ассеты уже на месте")
        else:
            print("⚠️ Папка defaults не найдена (возможно, ошибка сборки Docker)")
            
    except Exception as e:
        print(f"⚠️ Ошибка восстановления ассетов: {e}")
        import traceback
        traceback.print_exc()

# ---------------------------------------------

# Запуск планировщика (для продакшена и локальной разработки)
# Минимальные совместимые миграции должны выполняться и при импорте приложения
# Gunicorn. Полная init_db() в production намеренно не запускается.
try:
    with app.app_context():
        ensure_payment_type_column()
except Exception as e:
    print(f"⚠️ Не удалось проверить структуру payments: {e}")

# Подготавливаем ArcFace и векторный индекс в фоне, не задерживая открытие сайта.
start_access_face_index_prewarm()

# Используем try-except, чтобы ошибка планировщика не валила всё приложение
try:
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        scheduler = setup_scheduler()
except Exception as e:
    print(f"⚠️ Не удалось запустить планировщик: {e}")

if __name__ == '__main__':
    # init_db() # Удалено, инициализация выполняется выше
    
    # scheduler уже запущен выше
    
    # Для Railway используется gunicorn, но для локальной разработки используем встроенный сервер
    
    # Для Railway используется gunicorn, но для локальной разработки используем встроенный сервер
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'development') == 'development'
    
    try:
        app.run(debug=debug, host='0.0.0.0', port=port, use_reloader=False)  # use_reloader=False для планировщика
    except KeyboardInterrupt:
        scheduler.shutdown()


