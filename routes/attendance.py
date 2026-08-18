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

    if not face_encodings:
        return JSONResponse({'matches': []})

    students = get_students()
    known_students = [
        s for s in students
        if s.get('encoding') is not None and len(s['encoding']) > 0
    ]

    if not known_students:
        return JSONResponse({'matches': []})

    matches = []

    for face_encoding in face_encodings:
        best_match = None
        best_distance = 1.0

        for student in known_students:
            known_encoding = np.asarray(student['encoding'], dtype=np.float64)
            is_match, distance = compare_faces(face_encoding, [known_encoding], tolerance=0.45)
            if is_match and distance < best_distance:
                best_match = student
                best_distance = distance

        # Unknown face -> skip completely, kuch bhi return/log nahi hoga
        if best_match is None:
            continue

        inserted = log_attendance(best_match['rollno'], best_match['name'], best_match.get('class_name'))
        matches.append({
            'rollno': best_match['rollno'],
            'name': best_match['name'],
            'class': best_match.get('class_name') or 'Unknown',
            'already': not inserted,
        })

    return JSONResponse({'matches': matches})