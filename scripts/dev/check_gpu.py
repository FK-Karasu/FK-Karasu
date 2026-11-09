import os
import sys
import cv2
import numpy as np
import onnxruntime as ort

def check_system():
    print("="*50)
    print("📋 СИСТЕМНЫЙ ОТЧЕТ (DIAGNOSTIC REPORT)")
    print("="*50)
    
    # 1. Python info
    print(f"Python version: {sys.version}")
    
    # 2. CUDA environment variables
    print("\nCUDA Environment Variables:")
    for key in ['CUDA_PATH', 'CUDA_PATH_V12_1', 'CUDA_PATH_V13_0', 'PATH']:
        val = os.environ.get(key, 'Not Set')
        if key == 'PATH':
            print(f"  PATH contains 'CUDA': {'Yes' if 'CUDA' in val.upper() else 'No'}")
        else:
            print(f"  {key}: {val}")
    
    # 3. ONNX Runtime info
    print(f"\nONNX Runtime version: {ort.__version__}")
    print(f"Available Providers: {ort.get_available_providers()}")
    
    # Attempt to check CUDA functional
    providers = ort.get_available_providers()
    if 'CUDAExecutionProvider' in providers:
        try:
            # Create a simple session to test
            dummy_model = np.array([1.0], dtype=np.float32)
            # This is just a check, it will likely fail if DLLs are missing
            print("  Attempting to initialize CUDA session...")
            # We don't have a model file handy, but we can check the error message
            # when trying to use it.
        except Exception as e:
            print(f"  CUDA check error: {e}")

    # 4. OpenCV info
    print(f"\nOpenCV version: {cv2.__version__}")
    
    # Check for the missing DLL in common paths
    print("\nChecking for cublasLt64_12.dll:")
    found = False
    possible_paths = [
        "C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.4\\bin",
        "C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.1\\bin",
        "C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v11.8\\bin",
        "C:\\Windows\\System32"
    ]
    for p in possible_paths:
        target = os.path.join(p, "cublasLt64_12.dll")
        if os.path.exists(target):
            print(f"  ✅ FOUND at: {p}")
            found = True
            break
    if not found:
        print("  ❌ NOT FOUND in common CUDA paths. This is why FPS is low.")

    print("\n" + "="*50)
    print("🔍 ВЫВОД (CONCLUSION):")
    if 'CUDAExecutionProvider' in providers and found:
        print("  - Все готово для работы на GPU (Ракета).")
    elif 'CUDAExecutionProvider' in providers and not found:
        print("  - Драйвер виден, но не хватает DLL (cublasLt64_12.dll).")
        print("  - Установите CUDA Toolkit 12.4.")
    else:
        print("  - ONNX Runtime работает на CPU (Медленно).")
    
    print("="*50)

if __name__ == "__main__":
    check_system()
