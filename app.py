import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os

from routes.enroll import router as enroll_router
from routes.attendance import router as attendance_router
from routes.download import router as download_router
from routes.students import router as students_router

app = FastAPI(title='Face Recognition Attendance System')

app.include_router(enroll_router, prefix='/enroll')
app.include_router(attendance_router, prefix='/attendance')
app.include_router(download_router, prefix='/download')
app.include_router(students_router, prefix='/students')

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')

TEMPLATES_DIR = os.path.join(BASE_DIR, 'src', 'templates')
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@app.get('/')
async def index(request: Request):
    return templates.TemplateResponse(request, 'home.html', context={'request': request})


if __name__ == '__main__':
    uvicorn.run('app:app', host='0.0.0.0', port=8000, reload=True)
