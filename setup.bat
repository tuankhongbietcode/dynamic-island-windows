@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo [1/2] Tao moi truong Python rieng (.venv)...
py -3 -m venv .venv 2>nul
if errorlevel 1 (
    python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
    echo Khong tao duoc .venv. Hay cai Python 3.11+ tu python.org roi chay lai.
    pause
    exit /b 1
)

echo [2/2] Cai thu vien...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo.
echo Xong. Bam start-island.vbs de chay.
pause
