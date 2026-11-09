@echo off
cd /d "%~dp0"
start "" pythonw.exe -X utf8 -m automation.review_loop.gui
