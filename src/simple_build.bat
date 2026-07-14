@echo off
echo === FPS Targeter Simple Builder ===
echo.

cd /d "%~dp0"

REM Проверка установленного Python
python --version
if %errorlevel% neq 0 (
    echo ERROR: Python не найден!
    pause
    exit /b 1
)

REM Проверка наличия всех необходимых файлов
echo Проверка файлов...
if not exist "fps_settings.json" (
    echo WARNING: fps_settings.json не найден, будет создан по умолчанию
)
if not exist "game_presets_db.json" (
    echo WARNING: game_presets_db.json не найден, будет создан по умолчанию
)

echo.
echo Сборка .exe файла...
pyinstaller --onefile --windowed --clean main.py

if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo СБОРКА НЕ УДАЛОСЬ!
    echo ========================================
    pause
    exit /b 1
)

echo.
echo ========================================
echo === СБОРКА УСПЕШНА! ===
echo ========================================
echo Готовый .exe файл находится в папке dist/main.exe
echo.
echo Размер файла:
dir dist\main.exe | find "main.exe"
echo.
pause
