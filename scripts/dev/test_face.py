
import numpy as np
import face_recognition
import cv2
import os

print(f"NumPy version: {np.__version__}")
try:
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    locs = face_recognition.face_locations(img)
    print("face_recognition.face_locations test: OK")
except Exception as e:
    print(f"face_recognition test FAILED: {e}")
