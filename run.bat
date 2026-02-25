@echo off
setlocal
cd /d %~dp0
if not exist data mkdir data
if not exist data\logs mkdir data\logs
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m src.main
endlocal
