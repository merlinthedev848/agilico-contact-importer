@echo off
echo ===================================================
echo Building Agilico Contact Importer - Lite Single-File EXE
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

echo [2/2] Compiling app.py into a single standalone executable...
pyinstaller --clean --noconfirm AgilicoContactImporter.spec

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [RETRY] Attempting direct pyinstaller build with bundled assets...
    pyinstaller --clean --noconfirm --onefile --noconsole --collect-all selenium --add-data "logo.png;." --add-data "logo.ico;." --icon=logo.ico --name "Agilico Contact Importer - Lite" app.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] PyInstaller compilation failed.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ===================================================
echo Build completed successfully!
echo Executable location: dist\Agilico Contact Importer - Lite.exe
echo ===================================================
pause
