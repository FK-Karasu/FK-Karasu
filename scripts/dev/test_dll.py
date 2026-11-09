import os

def check_cuda_dlls():
    print("="*60)
    print("🔍 ПРОВЕРКА НАЛИЧИЯ КРИТИЧЕСКИХ ФАЙЛОВ CUDA")
    print("="*60)
    
    cuda_bin = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4\bin"
    
    # Список файлов, которые НУЖНЫ для работы (onnxruntime + insightface)
    required_dlls = [
        "cublas64_12.dll",
        "cublasLt64_12.dll",
        "cudart64_12.dll",
        "cufft64_11.dll",
        "curand64_10.dll",
        "cusolver64_11.dll",
        "cusparse64_12.dll",
        "cudnn64_9.dll", # Библиотека cuDNN
        "zlibwapi.dll"   # Часто забываемый файл
    ]
    
    if not os.path.exists(cuda_bin):
        print(f"❌ ПАПКА НЕ НАЙДЕНА: {cuda_bin}")
        print("Пожалуйста, проверьте версию установленной CUDA (v12.4?).")
        return

    print(f"📂 Путь: {cuda_bin}\n")
    
    found_count = 0
    for dll in required_dlls:
        path = os.path.join(cuda_bin, dll)
        if os.path.exists(path):
            size_mb = os.path.getsize(path) / (1024 * 1024)
            print(f"✅ [ОК] {dll:<20} ({size_mb:>6.1f} MB)")
            found_count += 1
        else:
            print(f"❌ [НЕТ] {dll:<20} <-- ИМЕННО ЭТОГО НЕ ХВАТАЕТ!")

    print("\n" + "="*60)
    if found_count == len(required_dlls):
        print("🚀 ВСЕ ФАЙЛЫ НА МЕСТЕ!")
        print("Если всё равно пишет CPU, просто перезапустите компьютер.")
    else:
        print(f"⚠️ Найдено файлов: {found_count} из {len(required_dlls)}")
        print("Для работы на GPU нужны ВСЕ эти файлы.")
    print("="*60)

if __name__ == "__main__":
    check_cuda_dlls()
