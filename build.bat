@echo off
echo ===================================================
echo Building Agilico Contact Importer Single-File EXE
echo ===================================================

echo.
echo [1/2] Installing required dependencies...
pip install selenium webdriver-manager pyinstaller

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Failed to install dependencies. Please check your Python and pip installation.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [2/2] Compiling app.py into a single standalone executable...
pyinstaller --onefile --noconsole app.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] PyInstaller compilation failed.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ===================================================
echo Build completed successfully!
echo Executable location: dist\app.exe
echo ===================================================
pause
