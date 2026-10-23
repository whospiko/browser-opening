@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" src\launcher_app.py %*
) else (
  py -3.12 src\launcher_app.py %*
)
