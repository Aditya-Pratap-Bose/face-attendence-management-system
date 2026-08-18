import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from database import delete_student, get_students, init_db

init_db()

router = APIRouter()
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'src', 'templates')
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get('/')
async def students_page(request: Request):
    return templates.TemplateResponse(request=request, name='students.html', context={'request': request})


@router.get('/api/list')
async def api_list_students():
    students = get_students()
    # Never send face encodings to the browser — the client has no need
    # for that data, and it's sensitive biometric information.
    safe_students = [
        {
            'rollno': s['rollno'],
            'name': s['name'],
            'class_name': s['class_name'],
            'created_at': s['created_at'],
        }
        for s in students
    ]
    return JSONResponse({'students': safe_students})


@router.delete('/api/delete/{rollno}')
async def api_delete_student(rollno: str):
    rollno = (rollno or '').strip()
    if not rollno:
        return JSONResponse({'error': 'Roll number is required.'}, status_code=400)

    try:
        deleted = delete_student(rollno)
    except Exception as exc:
        return JSONResponse({'error': f'Could not delete student: {exc}'}, status_code=500)

    if not deleted:
        return JSONResponse({'error': 'Student not found.'}, status_code=404)

    return JSONResponse({'deleted': True, 'rollno': rollno})