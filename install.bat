@echo off

rem Install the python virtual environment. 
python -m venv venv
rem Note: If multiple python versions are installed, use this command instead to use python 3.10
rem c:/python310/python.exe -m venv venv

rem Activate environment and install requirements
call venv/Scripts/activate.bat
python.exe -m pip install --upgrade pip
python.exe -m pip install -r requirements.txt
pause