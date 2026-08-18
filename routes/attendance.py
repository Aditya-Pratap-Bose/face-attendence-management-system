import os
from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from database import get_students, init_db, log_attendance
from services.face_model import compare_faces, detect_faces, read_image_frame

import numpy as np

init_db()

router = APIRouter()
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'src', 'templates')
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get('/')
async def attendance_page(request: Request):
    return templates.TemplateResponse(request=request, name='attendance.html', context={'request': request})


@router.post('/api/recognize')
async def api_recognize(frame: UploadFile = File(...)):
    try:
        image_bytes = await frame.read()
        image = read_image_frame(image_bytes)
        _, face_encodings = detect_faces(image)
    except ValueError as exc:
        return JSONResponse({'error': str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({'error': f'Could not process image: {exc}'}, status_code=400)

    students = get_students()
    if not students:
        return JSONResponse({'matches': []})

    known_encodings = []
    for student in students:
        if not student['encoding']:
            continue
        known_encodings.append(np.asarray(student['encoding'], dtype=np.float64))

    matches = []
    if not face_encodings:
        return JSONResponse({'matches': []})

    for face_encoding in face_encodings:
        best_match = None
        best_distance = 1.0

        for student in students:
            if not student['encoding']:
                continue
            known_encoding = np.asarray(student['encoding'], dtype=np.float64)
            is_match, distance = compare_faces(face_encoding, [known_encoding], tolerance=0.45)
            if is_match and distance < best_distance:
                best_match = student
                best_distance = distance

        if best_match is None:
            matches.append({'rollno': 'unknown', 'name': 'Unknown', 'class': 'Unknown', 'already': False})
            continue

        inserted = log_attendance(best_match['rollno'], best_match['name'], best_match.get('class_name'))
        matches.append({
            'rollno': best_match['rollno'],
            'name': best_match['name'],
            'class': best_match.get('class_name') or 'Unknown',
            'already': not inserted,
        })

    return JSONResponse({'matches': matches})
