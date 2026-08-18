import os
import re
from datetime import datetime
from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from database import export_attendance_csv, get_attendance_rows, init_db

init_db()

router = APIRouter()
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'src', 'templates')
templates = Jinja2Templates(directory=TEMPLATES_DIR)

DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _validate_date(date: str) -> str:
    """Returns a safe YYYY-MM-DD string, defaulting to today if invalid/missing."""
    if date and DATE_RE.match(date):
        try:
            datetime.strptime(date, '%Y-%m-%d')
            return date
        except ValueError:
            pass
    return datetime.now().strftime('%Y-%m-%d')


@router.get('/')
async def download_page(request: Request):
    today = datetime.now().strftime('%Y-%m-%d')
    return templates.TemplateResponse(request=request, name='download.html', context={'request': request, 'today': today})


@router.get('/api/view')
async def api_view(date: str = Query(None)):
    date = _validate_date(date)
    try:
        rows = get_attendance_rows(date)
        return JSONResponse({'date': date, 'rows': rows})
    except Exception as exc:
        return JSONResponse({'error': str(exc)}, status_code=500)


@router.get('/api/download')
async def api_download(date: str = Query(None)):
    date = _validate_date(date)
    try:
        path = export_attendance_csv(date)
        if not path or not os.path.exists(path):
            return JSONResponse({'error': 'CSV not found.'}, status_code=404)
        return FileResponse(path, media_type='text/csv', filename=os.path.basename(path))
    except Exception as exc:
        return JSONResponse({'error': str(exc)}, status_code=500)