@echo off
cd /d %~dp0
if not exist .venv (
  python -m venv .venv
  call .venv\Scripts\activate
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate
)
if not exist .env copy .env.example .env
start http://127.0.0.1:8000
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
