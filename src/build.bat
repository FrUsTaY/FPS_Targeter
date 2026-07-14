@echo off
echo === FPS Targeter Builder ===
echo.

REM Проверка установленного Python
python --version
if %errorlevel% neq 0 (
    echo ERROR: Python не найден!
    pause
    exit /b 1
)

echo Очистка старых сборок...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "*.spec" del /q "*.spec"
if exist "temp_backup.json" del /q "temp_backup.json"

echo Установка зависимостей...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo WARNING: Некоторые зависимости могли не установиться
)

echo.
echo Сборка .exe файла...
pyinstaller --onefile --windowed --add-data "fps_settings.json;." --add-data "game_presets_db.json;." --add-data "game_requirements.json;." --add-data "hardware_benchmark.json;." main.py
if %errorlevel% neq 0 (
    echo ERROR: Сборка не удалась!
    pause
    exit /b 1
)

echo.
echo === Сборка завершена! ===
echo Готовый .exe файл находится в папке dist/
pause
