from __future__ import annotations

import cv2
import face_recognition
import numpy as np


def read_image_frame(file_bytes: bytes):
    array = np.frombuffer(file_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('Could not decode uploaded image.')
    return image


def detect_faces(image):
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    locations = face_recognition.face_locations(rgb_image)
    encodings = face_recognition.face_encodings(rgb_image, locations)
    return locations, encodings


def compare_faces(candidate_encoding, known_encodings, tolerance: float = 0.45):
    if not known_encodings:
        return False, 1.0
    distances = face_recognition.face_distance(known_encodings, candidate_encoding)
    best_index = int(np.argmin(distances)) if len(distances) else -1
    best_distance = float(distances[best_index]) if best_index >= 0 else 1.0
    is_match = bool(best_distance <= tolerance)
    return is_match, best_distance
