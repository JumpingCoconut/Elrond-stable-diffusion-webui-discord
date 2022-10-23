cd ..
start /B cmd /C ".\venv\Scripts\activate.bat && pip install pipreqs && pipreqs . --force"
pause