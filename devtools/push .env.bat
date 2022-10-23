@echo off
cd ..

echo Are you SURE you want to push your .env File?
echo It may contain your discord key!
echo ...
more .env
echo ...
set /p firstline=< .env
echo First line: %firstline%
echo ...
echo Press button to add it to the git update index.
pause
@echo on
git update-index --no-assume-unchanged .env
@echo off
echo Now you can push the file via git. Press the button when done pushing.
pause
@echo on
git update-index --assume-unchanged .env
@echo off
echo File removed from git update index again.
pause