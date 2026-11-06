@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto python
py -3 saas\pilote.py --ouvrir
if errorlevel 1 pause
exit /b
:python
python saas\pilote.py --ouvrir
if errorlevel 1 pause
