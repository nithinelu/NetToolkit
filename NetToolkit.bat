@echo off
REM Launch NetToolkit, locating a real Python (ignoring the MS Store stub).
cd /d "%~dp0"

REM 1) Python launcher, if present
py -3 --version >nul 2>&1
if %errorlevel%==0 (
  py -3 toolkit.py
  if errorlevel 1 pause
  goto :eof
)

REM 2) Python install-manager runtime under %LOCALAPPDATA%\Python
for /f "delims=" %%P in ('dir /b /o-n "%LOCALAPPDATA%\Python\pythoncore-*" 2^>nul') do (
  if exist "%LOCALAPPDATA%\Python\%%P\python.exe" (
    "%LOCALAPPDATA%\Python\%%P\python.exe" toolkit.py
    if errorlevel 1 pause
    goto :eof
  )
)

REM 3) Fall back to whatever "python" resolves to
python toolkit.py
if errorlevel 1 (
  echo.
  echo Could not find Python. Install Python 3.9+ from https://www.python.org
  echo and tick "Add Python to PATH", then run Install.bat once.
  pause
)
