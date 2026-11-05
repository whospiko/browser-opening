@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set PYTHON=.venv\Scripts\python.exe
) else (
  set PYTHON=py -3.12
)
%PYTHON% -m pip install -q -r requirements.txt
if exist dist\browser-tool-config.exe del dist\browser-tool-config.exe
if exist dist\browser-tool.exe del dist\browser-tool.exe
if exist dist\browser-tool-setup.exe del dist\browser-tool-setup.exe
if exist dist\payload rmdir /s /q dist\payload
set CRYPTO_HIDDENS=--hidden-import cryptography --hidden-import cryptography.fernet --hidden-import keyring --hidden-import keyring.backends --hidden-import keyring.backends.Windows --hidden-import keyring.backends.chainer --hidden-import keyring.backends.fail --hidden-import secure_store --hidden-import version --hidden-import updater --hidden-import windows_placer
%PYTHON% -m PyInstaller --noconfirm --clean --onefile --windowed --name browser-tool-config --icon assets\icon.ico --paths src --collect-all screeninfo --hidden-import tkinter %CRYPTO_HIDDENS% src\config_app.py
%PYTHON% -m PyInstaller --noconfirm --clean --onefile --windowed --name browser-tool --icon assets\icon.ico --paths src --collect-all screeninfo --hidden-import tkinter %CRYPTO_HIDDENS% src\launcher_app.py
mkdir dist\payload
copy /y dist\browser-tool-config.exe dist\payload\ >nul
copy /y dist\browser-tool.exe dist\payload\ >nul
%PYTHON% -m PyInstaller --noconfirm --clean --onefile --windowed --name browser-tool-setup --icon assets\icon.ico --paths src --add-data "dist\payload;payload" --hidden-import tkinter src\setup_app.py
if exist dist\browser-tool-windows.zip del dist\browser-tool-windows.zip
%PYTHON% -c "import zipfile; from pathlib import Path; z=Path('dist/browser-tool-windows.zip'); f=zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED); f.write('dist/payload/browser-tool-config.exe','browser-tool-config.exe'); f.write('dist/payload/browser-tool.exe','browser-tool.exe'); f.close(); print('Wrote', z)"
echo.
echo Ship these files:
dir dist\browser-tool-setup.exe
dir dist\browser-tool-windows.zip
echo.
echo (Also built as payload inputs: dist\browser-tool-config.exe dist\browser-tool.exe)
