#!/bin/bash

echo "=== FPS Targeter Builder ==="
echo ""

# Проверка установленного Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 не найден!"
    exit 1
fi

python3 --version

# Установка зависимостей
echo "Установка зависимостей..."
pip3 install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "WARNING: Некоторые зависимости могли не установиться"
fi

echo ""
echo "Сборка .exe файла..."
echo "Примечание: Для сборки .exe на非-Windows системах нужен Wine и win32com"
pyinstaller --onefile --windowed --clean main.py

if [ $? -ne 0 ]; then
    echo "ERROR: Сборка не удалась!"
    exit 1
fi

echo ""
echo "=== Сборка завершена! ==="
echo "Готовый .exe файл находится в папке dist/"
echo ""
echo "Для Windows рекомендуется использовать simple_build.bat"
