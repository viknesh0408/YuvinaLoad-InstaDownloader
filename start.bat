@echo off
title YuvinaLoad – Download Server
color 0A

:: ═════════════════════════════════════════════════════════════════════════════
::  YOUTUBE BOT BLOCK BYPASS SETTING (Optional)
::  If YouTube blocks downloads and asks you to sign in, uncomment one of the
::  lines below depending on which browser you use to watch YouTube.
:: ═════════════════════════════════════════════════════════════════════════════
:: set YOUTUBE_COOKIES_BROWSER=chrome
:: set YOUTUBE_COOKIES_BROWSER=edge
:: set YOUTUBE_COOKIES_BROWSER=firefox
:: set YOUTUBE_COOKIES_BROWSER=brave
:: set YOUTUBE_COOKIES_BROWSER=opera
:: set YOUTUBE_COOKIES_BROWSER=vivaldi

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
