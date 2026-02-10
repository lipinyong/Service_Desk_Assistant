@echo off
pip install pyinstaller -q
pyinstaller chat.spec --clean
pyinstaller app.spec --clean
echo See dist\chat and dist\app
