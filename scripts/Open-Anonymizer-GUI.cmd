@echo off
setlocal
cd /d "%~dp0.."
title Anonymizer GUI (dev)
echo.
echo === Anonymizer GUI (dev worktree) ===
echo Repo: %CD%
echo.

set "PYTHONPATH=%CD%\src"
set "PY="

if exist "%USERPROFILE%\Downloads\anonymizer\.venv\Scripts\python.exe" set "PY=%USERPROFILE%\Downloads\anonymizer\.venv\Scripts\python.exe"
if not defined PY if exist "%CD%\.venv\Scripts\python.exe" set "PY=%CD%\.venv\Scripts\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Anonymizer\runtime\python.exe" set "PY=%LOCALAPPDATA%\Anonymizer\runtime\python.exe"

if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)

if not defined PY (
  echo ERROR: No python.exe found.
  pause
  exit /b 1
)

echo Python: %PY%
echo PYTHONPATH: %PYTHONPATH%
echo Log: %TEMP%\anonymizer-gui.log
echo.

"%PY%" -c "import anonymizer; print('anonymizer', anonymizer.__version__, anonymizer.__file__)"
if errorlevel 1 (
  echo ERROR: import failed
  pause
  exit /b 1
)

set "SAMPLE=%CD%\samples\en\loc_purchase_agreement.pdf"
if exist "%SAMPLE%" (
  echo Opening options with sample PDF...
  echo.
  "%PY%" -m anonymizer.gui "%SAMPLE%"
) else (
  echo Opening file launcher...
  echo.
  "%PY%" -m anonymizer.gui
)

echo.
echo Exit code: %ERRORLEVEL%
echo --- log tail ---
if exist "%TEMP%\anonymizer-gui.log" more +0 "%TEMP%\anonymizer-gui.log" | more
echo.
pause
endlocal
