#!/usr/bin/env python3
"""Independent read-only camera monitor for the bridge mini PC.

The Hikvision bridge, terminal access and attendance flow are intentionally not
touched. This process only reads RTSP, tracks faces, asks the main server for a
name/payment color, and serves a local kiosk page.
"""

import base64
import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
from flask import Flask, Response, jsonify
from PIL import Image, ImageDraw, ImageFont


SERVER_URL = os.environ.get('SERVER_URL', 'https://karasu.uz').rstrip('/')
DEVICE_KEY = os.environ.get('DEVICE_INGEST_KEY', '').strip()
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CONFIG_REFRESH_SECONDS = max(10, int(os.environ.get('CAMERA_CONFIG_REFRESH_SECONDS', '30')))

DEFAULTS = {
    'enabled': os.environ.get('CAMERA_KIOSK_ENABLED', '').strip().lower() in {'1', 'true', 'yes', 'on'},
    'rtsp_url': os.environ.get('CAMERA_RTSP_URL', ''),
    'stream_fps': int(os.environ.get('CAMERA_STREAM_FPS', '30')),
    'tracking_fps': int(os.environ.get('CAMERA_TRACKING_FPS', '30')),
    'detection_fps': int(os.environ.get('CAMERA_DETECTION_FPS', '10')),
    'width': int(os.environ.get('CAMERA_WIDTH', '1920')),
    'height': int(os.environ.get('CAMERA_HEIGHT', '1080')),
    'recognition_frames': int(os.environ.get('CAMERA_RECOGNITION_FRAMES', '3')),
    'result_hold_seconds': int(os.environ.get('CAMERA_RESULT_HOLD_SECONDS', '10')),
    'kiosk_port': int(os.environ.get('CAMERA_KIOSK_PORT', '8090')),
}

app = Flask(__name__)


def clamp(value, minimum, maximum, fallback):
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return fallback


def as_bool(value, fallback=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return fallback
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


class CameraKiosk:
    def __init__(self):
        self.config = dict(DEFAULTS)
        self.config_lock = threading.Lock()
        self.frame_lock = threading.Lock()
        self.latest_jpeg = None
        self.latest_at = 0.0
        self.status = 'starting'
        self.error = ''
        self.capture = None
        self.detector = None
        self.tracks = {}
        self.next_track_id = 1
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='camera-recognize')
        self.stop_event = threading.Event()
        self.font = self._load_font()

    @staticmethod
    def _load_font():
        paths = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            '/usr/share/fonts/dejavu/DejaVuSans.ttf',
            'C:/Windows/Fonts/arial.ttf',
        ]
        for path in paths:
            if os.path.isfile(path):
                try:
                    return ImageFont.truetype(path, 26)
                except OSError:
                    pass
        return ImageFont.load_default()

    def fetch_config(self):
        request = urllib.request.Request(
            f'{SERVER_URL}/api/hikvision/config',
            headers={'x-device-key': DEVICE_KEY, 'Accept': 'application/json'},
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode('utf-8'))
        remote = payload.get('camera') or {}
        clean = {
            'enabled': as_bool(remote.get('enabled'), False),
            'rtsp_url': str(remote.get('rtsp_url') or self.config.get('rtsp_url') or '').strip(),
            'stream_fps': clamp(remote.get('stream_fps'), 1, 60, 30),
            'tracking_fps': clamp(remote.get('tracking_fps'), 1, 60, 30),
            'detection_fps': clamp(remote.get('detection_fps'), 1, 30, 10),
            'width': clamp(remote.get('width'), 320, 3840, 1920),
            'height': clamp(remote.get('height'), 240, 2160, 1080),
            'recognition_frames': clamp(remote.get('recognition_frames'), 1, 10, 3),
            'result_hold_seconds': clamp(remote.get('result_hold_seconds'), 1, 60, 10),
            'kiosk_port': clamp(remote.get('kiosk_port'), 1024, 65535, 8090),
        }
        clean['detection_fps'] = min(clean['detection_fps'], clean['stream_fps'])
        with self.config_lock:
            source_changed = clean['rtsp_url'] != self.config.get('rtsp_url')
            disabled_now = self.config.get('enabled') and not clean['enabled']
            self.config.update(clean)
        if (source_changed or disabled_now) and self.capture is not None:
            self.capture.release()
            self.capture = None

    def config_loop(self):
        while not self.stop_event.is_set():
            try:
                self.fetch_config()
            except Exception as exc:
                self.error = f'Не удалось получить настройки: {type(exc).__name__}'
            self.stop_event.wait(CONFIG_REFRESH_SECONDS)

    def load_detector(self):
        if self.detector is not None:
            return
        from insightface.app import FaceAnalysis

        self.detector = FaceAnalysis(
            name='buffalo_s',
            root=os.path.join(PROJECT_ROOT, 'models'),
            providers=['CPUExecutionProvider'],
            allowed_modules=['detection'],
        )
        self.detector.prepare(ctx_id=-1, det_size=(640, 640))

    def open_capture(self):
        with self.config_lock:
            url = self.config.get('rtsp_url') or ''
            width = self.config['width']
            height = self.config['height']
        if not url:
            self.status = 'waiting_config'
            self.error = 'RTSP URL не настроен'
            return False
        os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp|fflags;nobuffer|max_delay;300000'
        capture = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if not capture.isOpened():
            capture.release()
            self.status = 'camera_offline'
            self.error = 'Не удалось открыть RTSP поток'
            return False
        self.capture = capture
        self.status = 'online'
        self.error = ''
        return True

    @staticmethod
    def iou(first, second):
        ax1, ay1, ax2, ay2 = first
        bx1, by1, bx2, by2 = second
        x1, y1 = max(ax1, bx1), max(ay1, by1)
        x2, y2 = min(ax2, bx2), min(ay2, by2)
        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = max(1, ax2 - ax1) * max(1, ay2 - ay1)
        area_b = max(1, bx2 - bx1) * max(1, by2 - by1)
        return intersection / float(area_a + area_b - intersection)

    def update_tracks(self, detections, frame, now):
        unmatched_tracks = set(self.tracks)
        unmatched_detections = set(range(len(detections)))
        pairs = []
        for track_id, track in self.tracks.items():
            for index, bbox in enumerate(detections):
                score = self.iou(track['bbox'], bbox)
                if score >= 0.18:
                    pairs.append((score, track_id, index))
        for _, track_id, index in sorted(pairs, reverse=True):
            if track_id not in unmatched_tracks or index not in unmatched_detections:
                continue
            track = self.tracks[track_id]
            previous = np.asarray(track['bbox'], dtype=np.float32)
            current = np.asarray(detections[index], dtype=np.float32)
            track['velocity'] = (current - previous) * 0.65
            track['bbox'] = detections[index]
            track['last_seen'] = now
            track['misses'] = 0
            self.collect_crop(track, frame)
            unmatched_tracks.remove(track_id)
            unmatched_detections.remove(index)

        for track_id in unmatched_tracks:
            self.tracks[track_id]['misses'] += 1
        for index in unmatched_detections:
            bbox = detections[index]
            track_id = self.next_track_id
            self.next_track_id += 1
            self.tracks[track_id] = {
                'id': track_id,
                'bbox': bbox,
                'velocity': np.zeros(4, dtype=np.float32),
                'last_seen': now,
                'misses': 0,
                'samples': [],
                'recognizing': False,
                'result': None,
                'result_at': 0.0,
            }
            self.collect_crop(self.tracks[track_id], frame)

        for track_id in list(self.tracks):
            track = self.tracks[track_id]
            if now - track['last_seen'] > 1.3 or track['misses'] > 15:
                del self.tracks[track_id]

    def predict_tracks(self, frame_width, frame_height):
        for track in self.tracks.values():
            predicted = np.asarray(track['bbox'], dtype=np.float32) + track['velocity']
            predicted[[0, 2]] = np.clip(predicted[[0, 2]], 0, frame_width - 1)
            predicted[[1, 3]] = np.clip(predicted[[1, 3]], 0, frame_height - 1)
            track['bbox'] = tuple(int(value) for value in predicted)
            track['velocity'] *= 0.78

    def collect_crop(self, track, frame):
        if track['result'] is not None or track['recognizing']:
            return
        x1, y1, x2, y2 = track['bbox']
        padding_x = int((x2 - x1) * 0.18)
        padding_y = int((y2 - y1) * 0.18)
        x1, y1 = max(0, x1 - padding_x), max(0, y1 - padding_y)
        x2, y2 = min(frame.shape[1], x2 + padding_x), min(frame.shape[0], y2 + padding_y)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0 or crop.shape[0] < 80 or crop.shape[1] < 80:
            return
        sharpness = float(cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
        track['samples'].append((sharpness, crop.copy()))
        track['samples'] = sorted(track['samples'], key=lambda item: item[0], reverse=True)[:10]
        with self.config_lock:
            required = self.config['recognition_frames']
        if len(track['samples']) >= required:
            track['recognizing'] = True
            samples = [item[1] for item in track['samples'][:required]]
            self.executor.submit(self.recognize_track, track['id'], samples)

    @staticmethod
    def encode_crop(crop):
        height, width = crop.shape[:2]
        scale = min(1.0, 640.0 / max(height, width))
        if scale < 1.0:
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        ok, encoded = cv2.imencode('.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if not ok:
            return ''
        return 'data:image/jpeg;base64,' + base64.b64encode(encoded.tobytes()).decode('ascii')

    def request_recognition(self, track_id, crop):
        payload = json.dumps({
            'track_id': str(track_id),
            'image_data_url': self.encode_crop(crop),
        }).encode('utf-8')
        request = urllib.request.Request(
            f'{SERVER_URL}/api/camera-kiosk/recognize',
            data=payload,
            method='POST',
            headers={
                'Content-Type': 'application/json',
                'x-device-key': DEVICE_KEY,
            },
        )
        with urllib.request.urlopen(request, timeout=12) as response:
            return json.loads(response.read().decode('utf-8'))

    def recognize_track(self, track_id, samples):
        try:
            results = [self.request_recognition(track_id, sample) for sample in samples]
            confirmed = [item for item in results if item.get('student') and item.get('status') == 'confirmed']
            ids = [item['student']['id'] for item in confirmed]
            winner = max(set(ids), key=ids.count) if ids else None
            required = max(1, (len(samples) // 2) + 1)
            result = next((item for item in reversed(confirmed) if item['student']['id'] == winner), None)
            if winner is None or ids.count(winner) < required:
                result = {
                    'status': 'ambiguous' if confirmed else 'unknown',
                    'color': 'yellow',
                    'student': None,
                    'reason': 'Нет устойчивого совпадения',
                }
        except Exception as exc:
            result = {
                'status': 'offline',
                'color': 'gray',
                'student': None,
                'reason': f'Сервер недоступен: {type(exc).__name__}',
            }
        track = self.tracks.get(track_id)
        if track is not None:
            track['result'] = result
            track['result_at'] = time.monotonic()
            track['recognizing'] = False

    def detect(self, frame):
        self.load_detector()
        faces = self.detector.get(frame)
        detections = []
        for face in faces:
            x1, y1, x2, y2 = (int(value) for value in face.bbox)
            if x2 - x1 >= 50 and y2 - y1 >= 50:
                detections.append((x1, y1, x2, y2))
        return detections

    def draw(self, frame):
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(image)
        colors = {
            'green': (31, 205, 110),
            'red': (239, 68, 68),
            'yellow': (245, 158, 11),
            'gray': (148, 163, 184),
        }
        for track in list(self.tracks.values()):
            x1, y1, x2, y2 = track['bbox']
            x1 = max(0, min(image.width - 1, int(x1)))
            y1 = max(0, min(image.height - 1, int(y1)))
            x2 = max(0, min(image.width - 1, int(x2)))
            y2 = max(0, min(image.height - 1, int(y2)))
            if x2 <= x1 or y2 <= y1:
                continue
            result = track.get('result') or {}
            color_key = result.get('color') or ('gray' if track.get('recognizing') else 'yellow')
            color = colors.get(color_key, colors['yellow'])
            student = result.get('student') or {}
            label = student.get('full_name') or ('Определяется...' if track.get('recognizing') else 'Лицо')
            draw.rectangle((x1, y1, x2, y2), outline=color, width=5)
            text_box = draw.textbbox((0, 0), label, font=self.font)
            text_width = text_box[2] - text_box[0]
            text_height = text_box[3] - text_box[1]
            label_height = text_height + 14
            label_top = y1 - label_height if y1 >= label_height else y2
            label_top = max(0, min(image.height - label_height, label_top))
            label_bottom = min(image.height, label_top + label_height)
            label_left = max(0, min(image.width - 1, x1))
            label_right = min(image.width, label_left + text_width + 22)
            draw.rounded_rectangle(
                (label_left, label_top, max(label_left + 1, label_right), label_bottom),
                radius=8,
                fill=color,
            )
            draw.text((label_left + 10, label_top + 5), label, font=self.font, fill=(255, 255, 255))
        return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)

    def make_placeholder(self, message):
        with self.config_lock:
            width, height = self.config['width'], self.config['height']
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.putText(frame, message, (max(30, width // 8), height // 2), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (220, 220, 220), 2)
        return frame

    def camera_loop(self):
        last_detection = 0.0
        last_tracking = 0.0
        while not self.stop_event.is_set():
            with self.config_lock:
                enabled = self.config.get('enabled', False)
                stream_fps = self.config['stream_fps']
                tracking_fps = self.config['tracking_fps']
                detection_fps = self.config['detection_fps']
                result_hold_seconds = self.config['result_hold_seconds']
                width = self.config['width']
                height = self.config['height']
            if not enabled:
                if self.capture is not None:
                    self.capture.release()
                    self.capture = None
                self.detector = None
                self.tracks.clear()
                with self.frame_lock:
                    self.latest_jpeg = None
                self.status = 'disabled'
                self.error = ''
                self.stop_event.wait(1.0)
                continue
            started = time.monotonic()
            if self.capture is None and not self.open_capture():
                frame = self.make_placeholder(self.error or 'Camera offline')
                self.publish(frame)
                self.stop_event.wait(1.0)
                continue
            ok, frame = self.capture.read()
            if not ok:
                self.capture.release()
                self.capture = None
                self.status = 'camera_offline'
                self.error = 'RTSP поток прерван'
                continue
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
            now = time.monotonic()
            if now - last_tracking >= 1.0 / max(1, tracking_fps):
                self.predict_tracks(frame.shape[1], frame.shape[0])
                last_tracking = now
            for track in self.tracks.values():
                if track.get('result') and now - track.get('result_at', now) >= result_hold_seconds:
                    track['result'] = None
                    track['samples'] = []
            if now - last_detection >= 1.0 / max(1, detection_fps):
                try:
                    detections = self.detect(frame)
                    self.update_tracks(detections, frame, now)
                    self.status = 'online'
                    self.error = ''
                except Exception as exc:
                    self.status = 'recognition_error'
                    self.error = f'Ошибка детекции: {type(exc).__name__}'
                last_detection = now
            try:
                rendered = self.draw(frame)
            except Exception as exc:
                self.status = 'render_error'
                self.error = f'Ошибка отрисовки: {type(exc).__name__}'
                rendered = frame
            self.publish(rendered)
            elapsed = time.monotonic() - started
            self.stop_event.wait(max(0.0, (1.0 / max(1, stream_fps)) - elapsed))

    def publish(self, frame):
        ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 84])
        if ok:
            with self.frame_lock:
                self.latest_jpeg = encoded.tobytes()
                self.latest_at = time.time()

    def start(self):
        threading.Thread(target=self.config_loop, daemon=True, name='camera-config').start()
        threading.Thread(target=self.camera_loop, daemon=True, name='camera-capture').start()


kiosk = CameraKiosk()


@app.get('/')
def index():
    return '''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Видеомониторинг</title><style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#080b12;color:#fff;font-family:Arial,sans-serif;cursor:none}
main{position:relative;width:100%;height:100%;display:grid;place-items:center}img{width:100%;height:100%;object-fit:contain}
.status{position:absolute;top:16px;left:16px;padding:9px 13px;border-radius:9px;background:rgba(8,11,18,.72);font-size:14px;backdrop-filter:blur(8px)}
</style></head><body><main><img id="stream" src="/stream.mjpg" alt="Камера"><div class="status" id="status">Подключение...</div></main>
<script>
const stream=document.getElementById('stream'),statusEl=document.getElementById('status');
let reconnectTimer=null,lastReconnect=Date.now();
function reconnectStream(){clearTimeout(reconnectTimer);lastReconnect=Date.now();stream.src='/stream.mjpg?t='+lastReconnect}
function scheduleReconnect(){clearTimeout(reconnectTimer);reconnectTimer=setTimeout(reconnectStream,1500)}
stream.addEventListener('error',scheduleReconnect);
setInterval(async()=>{try{const r=await fetch('/api/status',{cache:'no-store'}),d=await r.json();statusEl.textContent=d.status==='online'?'Камера подключена':(d.error||d.status);const age=Date.now()-lastReconnect;if(d.status==='online'&&((!stream.naturalWidth&&age>10000)||age>60000))reconnectStream()}catch(e){statusEl.textContent='Нет связи с camera-kiosk';scheduleReconnect()}},2000)
</script>
</body></html>'''


@app.get('/stream.mjpg')
def stream():
    def generate():
        while True:
            with kiosk.frame_lock:
                frame = kiosk.latest_jpeg
            if frame:
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
            time.sleep(1.0 / max(1, kiosk.config.get('stream_fps', 30)))
    response = Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response


@app.get('/api/status')
def api_status():
    with kiosk.config_lock:
        config = {key: value for key, value in kiosk.config.items() if key != 'rtsp_url'}
    return jsonify({
        'status': kiosk.status,
        'error': kiosk.error,
        'tracks': len(kiosk.tracks),
        'last_frame_at': kiosk.latest_at,
        'config': config,
    })


if __name__ == '__main__':
    if not DEVICE_KEY:
        raise SystemExit('DEVICE_INGEST_KEY is required')
    try:
        kiosk.fetch_config()
    except Exception as exc:
        kiosk.error = f'Не удалось получить начальные настройки: {type(exc).__name__}'
    kiosk.start()
    port = clamp(kiosk.config.get('kiosk_port'), 1024, 65535, 8090)
    app.run(host='0.0.0.0', port=port, threaded=True, use_reloader=False)
