@echo off
title YuvinaLoad – Download Server
color 0A

echo.
echo  ╔════════════════════════════════════════╗
echo  ║   YuvinaLoad  -  YouTube Downloader    ║
echo  ╚════════════════════════════════════════╝
echo.

:: Check Python
python --version >nul 2>&1
if not errorlevel 1 (
  echo  Python found. Starting server...
  echo.
  python server.py
  goto :done
)

python3 --version >nul 2>&1
if not errorlevel 1 (
  echo  Python3 found. Starting server...
  echo.
  python3 server.py
  goto :done
)

echo  ╔════════════════════════════════════════╗
echo  ║  Python is not installed!              ║
echo  ║                                        ║
echo  ║  Please install Python from:           ║
echo  ║  https://python.org/downloads          ║
echo  ║                                        ║
echo  ║  Make sure to check:                   ║
echo  ║  [x] Add Python to PATH               ║
echo  ╚════════════════════════════════════════╝
echo.

:done
pause
