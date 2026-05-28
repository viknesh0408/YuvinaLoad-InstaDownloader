@echo off
title YuvinaLoad – Download Server
color 0A

:: ═════════════════════════════════════════════════════════════════════════════
::  INSTAGRAM COOKIES BYPASS SETTING (Optional)
::  If Instagram blocks downloads, uncomment one of the lines below
::  to use cookies from your browser session where you are logged in.
:: ═════════════════════════════════════════════════════════════════════════════
:: set INSTAGRAM_COOKIES_BROWSER=chrome
:: set INSTAGRAM_COOKIES_BROWSER=edge
:: set INSTAGRAM_COOKIES_BROWSER=firefox
:: set INSTAGRAM_COOKIES_BROWSER=brave
:: set INSTAGRAM_COOKIES_BROWSER=opera
:: set INSTAGRAM_COOKIES_BROWSER=vivaldi

echo.
echo  ╔════════════════════════════════════════╗
echo  ║  YuvinaLoad  -  Instagram Downloader   ║
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
