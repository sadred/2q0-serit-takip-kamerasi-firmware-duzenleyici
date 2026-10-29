@echo off
rem Denizli Garaj 2Q Serit Takip Kamerasi Yazilim Duzenleyici
setlocal
cd /d "%~dp0"

set "PYW=pythonw"
where pythonw >nul 2>&1
if errorlevel 1 (
  where python >nul 2>&1
  if errorlevel 1 (
    echo Python bulunamadi. https://www.python.org/downloads/ adresinden Python 3.9+ kurun.
    pause
    exit /b 1
  )
  set "PYW=python"
)

start "" %PYW% "%~dp0denizli_garaj_2q.py"
