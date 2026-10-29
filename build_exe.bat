@echo off
rem Builds dist\PokeScan.exe, a single standalone file (no Python needed to run it).
rem Needs Python 3.10+ from python.org on the PC that builds it.
cd /d "%~dp0"

where py >nul 2>nul && (set PY=py -3) || (set PY=python)

echo Creating build environment...
%PY% -m venv .buildenv || goto :fail
call .buildenv\Scripts\activate.bat || goto :fail

echo Installing packages...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt pyinstaller || goto :fail

echo Building PokeScan.exe...
pyinstaller --noconfirm --clean --onefile --windowed --name PokeScan ^
  --add-data "pokedex.json;." ^
  --collect-all rapidocr_onnxruntime ^
  --collect-submodules pynput pokescan.py || goto :fail

echo.
echo Done: %~dp0dist\PokeScan.exe
echo You can copy that file anywhere and double-click it.
pause
exit /b 0

:fail
echo.
echo Build failed. Scroll up for the error.
pause
exit /b 1
