import os
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from database import get_student_by_rollno, get_students, init_db, save_student
from services.face_model import compare_faces, detect_faces, read_image_frame

import numpy as np

init_db()

router = APIRouter()
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'src', 'templates')
templates = Jinja2Templates(directory=TEMPLATES_DIR)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB cap on uploaded image


@router.get('/')
async def enroll_page(request: Request):
    return templates.TemplateResponse(request=request, name='enroll.html', context={'request': request})


@router.post('/api/enroll')
async def api_enroll(
    name: str = Form(...),
    rollno: str = Form(...),
    class_name: str = Form(''),
    frame: UploadFile = File(...),
):
    name = (name or '').strip()
    rollno = (rollno or '').strip()
    class_name = (class_name or '').strip()

    if not name or not rollno:
        return JSONResponse({'error': 'Name and roll number are required.'}, status_code=400)

    # Basic content-type check before spending time decoding
    if frame.content_type and not frame.content_type.startswith('image/'):
        return JSONResponse({'error': 'Uploaded file must be an image.'}, status_code=400)

    try:
        image_bytes = await frame.read()
    except Exception as exc:
        return JSONResponse({'error': f'Could not read uploaded file: {exc}'}, status_code=400)

    if not image_bytes:
        return JSONResponse({'error': 'Uploaded file is empty.'}, status_code=400)

    if len(image_bytes) > MAX_UPLOAD_BYTES:
        return JSONResponse({'error': 'Uploaded file is too large.'}, status_code=400)

    try:
        image = read_image_frame(image_bytes)
        _, face_encodings = detect_faces(image)
    except ValueError as exc:
        return JSONResponse({'error': str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({'error': f'Could not process image: {exc}'}, status_code=400)

    if not face_encodings:
        return JSONResponse({'error': 'No face detected in the uploaded image.'}, status_code=400)

    existing_student = get_student_by_rollno(rollno)
    if existing_student:
        return JSONResponse({'exists': True, 'message': 'Roll number already enrolled.'})

    known_students = [
        s for s in get_students()
        if s.get('encoding') is not None and len(s['encoding']) > 0
    ]

    if known_students:
        known_encodings = [
            np.asarray(s['encoding'], dtype=np.float64) for s in known_students
        ]
        matches, _ = compare_faces(face_encodings[0], known_encodings, tolerance=0.45)

        # Support both a single bool and a list of bools from compare_faces
        if isinstance(matches, (list, tuple, np.ndarray)):
            for student, is_match in zip(known_students, matches):
                if is_match:
                    return JSONResponse({
                        'exists': True,
                        'message': f'Face matches existing student {student["name"]} ({student["rollno"]}).',
                        'existing_rollno': student['rollno'],
                    })
        else:
            if matches:
                student = known_students[0]
                return JSONResponse({
                    'exists': True,
                    'message': f'Face matches existing student {student["name"]} ({student["rollno"]}).',
                    'existing_rollno': student['rollno'],
                })

    try:
        save_student(rollno, name, np.asarray(face_encodings[0], dtype=np.float64), class_name)
    except Exception as exc:
        # Covers a race where two requests pass the existence check simultaneously
        # (requires a UNIQUE constraint on rollno in the DB for this to trigger reliably)
        return JSONResponse({'error': f'Could not save student: {exc}'}, status_code=409)

    return JSONResponse({'done': True, 'count': 1, 'message': 'Student enrolled successfully.'})