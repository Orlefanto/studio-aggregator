@echo off
cd /d %~dp0
python collect.py
start "studio-server" /min python -m http.server 8765
timeout /t 1 /nobreak >nul
start "" http://localhost:8765