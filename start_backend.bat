@echo off
echo Starting SmartCart 2.0 FastAPI Backend...
cd backend
set PYTHONPATH=%cd%
call .venv\Scripts\activate.bat
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
