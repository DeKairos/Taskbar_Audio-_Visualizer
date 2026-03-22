@echo off
setlocal
cd /d "%~dp0"

if exist "venv_win\Scripts\python.exe" (
    "venv_win\Scripts\python.exe" "main.py"
) else (
    python "main.py"
)

endlocal
