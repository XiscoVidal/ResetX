@echo off
cd /d "%~dp0"
powershell -Command "Start-Process '.\venv\Scripts\python.exe' -ArgumentList 'main.py' -Verb RunAs"
