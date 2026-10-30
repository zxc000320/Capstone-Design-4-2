@echo off
cd /d "%~dp0"
echo [1/2] Creating virtual environment (.venv)...
if not exist .venv (
    python -m venv .venv || py -m venv .venv
)
if not exist .venv\Scripts\python.exe (
    echo Failed to create .venv. Check that Python is installed.
    pause
    exit /b 1
)
echo [2/2] Installing packages...
.venv\Scripts\python -m pip install --upgrade pip -q
.venv\Scripts\python -m pip install -r requirements.txt
echo.
echo Running tests...
.venv\Scripts\python app\tests\run_tests.py
echo.
echo Done. Double-click run.bat to start the program.
pause
