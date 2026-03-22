# Cleanup Workflow

Keep source clean by removing generated artifacts only.

Do not delete source `.py` files, `installer/AudioVisualizer.iss`, or documentation unless intentionally refactoring.

## Safe Cleanup Targets

- build/
- dist/ (optional when preparing clean workspace)
- **pycache**/
- generated .spec files

## Recommended Commands

From project root:

```powershell
Remove-Item .\build -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item .\dist -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item .\AudioVisualizer.spec -Force -ErrorAction SilentlyContinue
Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
```

## When To Run Cleanup

- Before troubleshooting packaging failures
- Before creating a release candidate
- After toolchain updates (PyInstaller, Qt, Python)
