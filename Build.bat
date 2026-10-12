@echo off
set NameApp=Win Hub
set projectdirectory=%~dp0
set projectassets=%projectdirectory%Assets
set projectfavicon=%projectassets%\img\favicon.ico
set mainprojectfile=%projectdirectory%Win-hub.py
del /f /q "%nameapp%.exe"
pyinstaller --noconfirm --onefile --windowed --icon "%projectfavicon%" --name "%nameapp%" --uac-admin --hidden-import "winreg" --hidden-import "os" --hidden-import "sys" --hidden-import "json" --hidden-import "time" --hidden-import "queue" --hidden-import "shutil" --hidden-import "ctypes" --hidden-import "threading" --hidden-import "subprocess" --hidden-import "pathlib" --hidden-import "tkinter" --hidden-import "Pillow" --hidden-import "customtkinter"  "%mainprojectfile%"
rd /s /q "%~dp0Project-Build"
timeout /t 4 >nul
del /f /q "%nameapp%.spec"
rd /s /q "build"
mkdir "%~dp0Project-Build"
copy /y "%~dp0dist\%nameapp%.exe" "%~dp0Project-Build"
timeout /t 2 >nul
rd /s /q "dist"