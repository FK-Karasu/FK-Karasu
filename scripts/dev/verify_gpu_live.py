import cv2
import numpy as np
from insightface.app import FaceAnalysis
import time

def verify():
    print("🔍 Тест производительности GPU...")
    
    # Пытаемся инициализировать
    providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
    try:
        app = FaceAnalysis(name='buffalo_l', providers=providers)
        # ctx_id=0 форсирует GPU. Если не сработает, обычно выдает предупреждение или ошибку
        app.prepare(ctx_id=0, det_size=(640, 640))
        
        # Проверяем, какой провайдер реально подцепился
        for model_name, model in app.models.items():
            actual = model.session.get_providers()
            print(f"📦 Модель {model_name}: {actual}")
            if 'CUDAExecutionProvider' not in actual:
                print(f"❌ ВНИМАНИЕ: Модель {model_name} НЕ использует CUDA!")
            else:
                print(f"✅ Модель {model_name} использует GPU (CUDA)")

        # Тест скорости
        img = np.zeros((640, 640, 3), dtype=np.uint8)
        start = time.time()
        for _ in range(10):
            app.get(img)
        end = time.time()
        fps = 10 / (end - start)
        print(f"🚀 Скорость обработки: {fps:.2f} кадров/сек")

    except Exception as e:
        print(f"❌ Ошибка при инициализации GPU: {e}")

if __name__ == "__main__":
    verify()
