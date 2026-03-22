# Developer Setup

## Requirements

- Windows 10 or newer
- Python 3.10+
- PowerShell

## Initial Setup

From project root:

```powershell
.\venv_win\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Verify Environment

After activation, verify interpreter path:

```powershell
python -c "import sys; print(sys.executable)"
```

It should point to `venv_win`.

## Common Setup Issues

- If activation fails, run PowerShell as current user and allow local scripts:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

- If dependencies fail to install, upgrade pip first:

```powershell
python -m pip install --upgrade pip
```

- If audio capture dependencies fail, ensure you are on Windows and using Python 3.10+.
