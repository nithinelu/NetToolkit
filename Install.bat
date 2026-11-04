@echo off
REM Install dependencies, locating a real Python (ignoring the MS Store stub).
cd /d "%~dp0"

py -3 --version >nul 2>&1
if %errorlevel%==0 (
  py -3 -m pip install -r requirements.txt
  pause
  goto :eof
)

for /f "delims=" %%P in ('dir /b /o-n "%LOCALAPPDATA%\Python\pythoncore-*" 2^>nul') do (
  if exist "%LOCALAPPDATA%\Python\%%P\python.exe" (
    "%LOCALAPPDATA%\Python\%%P\python.exe" -m pip install -r requirements.txt
    pause
    goto :eof
  )
)

python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Could not find Python. Install Python 3.9+ from https://www.python.org
  echo and tick "Add Python to PATH".
)
pause
