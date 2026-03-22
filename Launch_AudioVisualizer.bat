@echo off
setlocal
cd /d "%~dp0"

if exist "venv_win\Scripts\pythonw.exe" (
    start "" /b "venv_win\Scripts\pythonw.exe" "main.py"
) else if exist "venv_win\Scripts\python.exe" (
    start "" /b "venv_win\Scripts\python.exe" "main.py"
) else if exist "%LocalAppData%\Programs\Python\Python313\pythonw.exe" (
    start "" /b "%LocalAppData%\Programs\Python\Python313\pythonw.exe" "main.py"
) else (
    start "" /b pythonw "main.py"
)

endlocal
