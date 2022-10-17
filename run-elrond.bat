@echo off
echo Dont forget to enter your discord-bot token in the file .env! 
echo Starting bot...
start /B cmd /C ".\venv\Scripts\activate.bat && python elrond.py"
pause