@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (python -m venv .venv)
call .venv\Scripts\activate
python -m pip install -r requirements.txt
if errorlevel 1 (echo Dependency installation failed & pause & exit /b 1)
python -m streamlit run app.py
pause
