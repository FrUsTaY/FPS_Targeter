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
echo Копирование необходимых конфигурационных файлов в dist...
if exist "game_requirements.json" copy /y "game_requirements.json" "dist\game_requirements.json" >nul
if exist "hardware_benchmark.json" copy /y "hardware_benchmark.json" "dist\hardware_benchmark.json" >nul
if exist "overlay_settings.json" copy /y "overlay_settings.json" "dist\overlay_settings.json" >nul
echo Файлы успешно скопированы.

echo.
echo ========================================
echo === СБОРКА УСПЕШНА! ===
echo ========================================
echo Готовый .exe файл и конфигурации находятся в папке dist/
echo.
echo Размер файла:
dir dist\main.exe | find "main.exe"
echo.
pause
