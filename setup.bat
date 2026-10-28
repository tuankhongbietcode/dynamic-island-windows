@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================
echo   Dynamic Island - cai dat
echo ============================================
echo.

echo [1/3] Kiem tra Python...
set "PYEXE="
py -3 -c "import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1
if not errorlevel 1 set "PYEXE=py -3"
if not defined PYEXE (
    python -c "import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYEXE=python"
)
if not defined PYEXE (
    echo    Khong tim thay Python 3.9 tro len.
    echo    Tai tai: https://www.python.org/downloads/
    echo    Nho tich "Add python.exe to PATH" khi cai.
    pause
    exit /b 1
)
echo    OK: %PYEXE%

echo.
echo [2/3] Tao moi truong rieng (.venv)...
if exist ".venv\Scripts\python.exe" (
    echo    Da co san, bo qua.
) else (
    %PYEXE% -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo    Khong tao duoc .venv.
        pause
        exit /b 1
    )
)

echo.
echo [3/3] Cai thu vien (lan dau hoi lau, ~1-2 phut)...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo    Cai dat that bai. Chay lai file nay de thu lai.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -c "import PySide6, psutil, winrt; print('   Kiem tra: OK')"
if errorlevel 1 (
    echo    Thieu thu vien, hay chay lai setup.bat.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Xong. Dang khoi dong Dynamic Island...
echo ============================================
start "" wscript.exe "%~dp0start-island.vbs"
timeout /t 2 >nul
exit /b 0
