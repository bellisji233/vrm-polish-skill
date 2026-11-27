@echo off
rem Double-click to start: serves this folder on localhost:8190 and opens the browser
cd /d "%~dp0"
start "" "http://localhost:8190/"
python -m http.server 8190 --bind 127.0.0.1
