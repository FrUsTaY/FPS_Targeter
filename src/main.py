"""
Запуск приложения FPS Targeter (Шаг 2 – интеллектуальный мост)
"""

import os
import sys
import logging
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog

from hardware import HardwarePassport
from ui import MainWindow
from hotkey import HotkeyManager
from database import Database

from logging.handlers import RotatingFileHandler

# --- Очистка лога при старте, если включена в настройках ---
from settings import load_settings as _load_settings

_settings = _load_settings()
if _settings.get("clear_log_on_start", False):
    # Определяем путь к лог-файлу
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    log_file = os.path.join(base_path, "fps_targeter.log")
    if os.path.exists(log_file):
        try:
            os.remove(log_file)
        except Exception:
            pass  # если не удалось удалить старый лог — не фатально

# Определяем путь к лог-файлу для RotatingFileHandler
if getattr(sys, "frozen", False):
    base_path = os.path.dirname(sys.executable)
else:
    base_path = os.path.dirname(os.path.abspath(__file__))
log_file_path = os.path.join(base_path, "fps_targeter.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            log_file_path,
            maxBytes=5 * 1024 * 1024,  # 5 МБ
            backupCount=2,
            encoding="utf-8",
        ),
    ],
)


def resolve_current_profile(db, hw):
    cpu = hw.cpu_name
    gpu = hw.gpu_name
    ram = f"{hw.ram_gb} GB" if hw.ram_gb else "N/A"
    logging.info(f"Поиск профиля для CPU={cpu}, GPU={gpu}")

    existing_id = db.find_profile_by_hardware(cpu, gpu)
    if existing_id is not None:
        db.set_current_profile(existing_id)
        logging.info(
            f"Найден существующий профиль: ID={existing_id} (CPU: {cpu}, GPU: {gpu})"
        )
        return

    msg_box = QMessageBox()
    msg_box.setWindowTitle("Новое оборудование")
    msg_box.setText(
        "Обнаружено новое оборудование.\nСоздать новый профиль или использовать существующий?"
    )
    new_btn = msg_box.addButton("Создать новый", QMessageBox.AcceptRole)
    existing_btn = msg_box.addButton("Выбрать существующий", QMessageBox.ActionRole)
    msg_box.addButton("Выход", QMessageBox.RejectRole)
    msg_box.exec()

    if msg_box.clickedButton() == new_btn:
        new_id = db.create_profile(cpu, gpu, ram, hw.vram_gb or 1.0)
        db.set_current_profile(new_id)
        logging.info(
            f"Создан новый профиль ID={new_id} (CPU: {cpu}, GPU: {gpu}, RAM: {ram}, VRAM: {hw.vram_gb})"
        )
    elif msg_box.clickedButton() == existing_btn:
        profiles = db.get_all_profiles()
        if not profiles:
            QMessageBox.warning(
                None, "Предупреждение", "Нет существующих профилей. Будет создан новый."
            )
            new_id = db.create_profile(cpu, gpu, ram, hw.vram_gb or 1.0)
            db.set_current_profile(new_id)
        else:
            items = [f"ID {p[0]}: {p[1]} / {p[2]}" for p in profiles]
            choice, ok = QInputDialog.getItem(
                None, "Выберите профиль", "Профиль:", items, 0, False
            )
            if ok and choice:
                idx = items.index(choice)
                profile_id = profiles[idx][0]
                db.set_current_profile(profile_id)
                logging.info(
                    f"Выбран существующий профиль ID={profile_id} (CPU: {profiles[idx][1]}, GPU: {profiles[idx][2]})"
                )
            else:
                new_id = db.create_profile(cpu, gpu, ram, hw.vram_gb or 1.0)
                db.set_current_profile(new_id)
    else:
        # Пользователь нажал Выход — завершаем программу
        sys.exit(0)


def validate_config_files():
    """Проверяет целостность JSON-файлов, восстанавливает при необходимости."""
    import json
    
    # Импортируем DEFAULT_GAME_PRESETS из database.py
    from database import DEFAULT_GAME_PRESETS
    
    files_to_check = {
        "game_presets_db.json": DEFAULT_GAME_PRESETS,
    }
    
    # Файлы game_requirements.json и hardware_benchmark.json не должны перезаписываться
    # - они уже включены в .exe и содержат актуальные данные
    
    # Определяем папку, где находится .exe или .py
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    for filename, default_data in files_to_check.items():
        filepath = os.path.join(base_path, filename)
        if not os.path.exists(filepath):
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(default_data, f, indent=2, ensure_ascii=False)
                logging.info(f"Создан отсутствующий файл: {filename}")
            except Exception as e:
                logging.error(f"Не удалось создать {filename}: {e}")
        elif os.path.getsize(filepath) == 0:
            # Файл существует, но пустой - восстанавливаем
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(default_data, f, indent=2, ensure_ascii=False)
                logging.info(f"Восстановлен пустой файл: {filename}")
            except Exception as e:
                logging.error(f"Не удалось восстановить {filename}: {e}")


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    logging.info("=== FPS Targeter v2.3 запущен ===")
    logging.info(f"Платформа: {sys.platform}, Python {sys.version}")

    # --- Валидация конфигурационных файлов ---
    validate_config_files()

    # --- Hardware Passport ---
    logging.info("Определение оборудования...")
    hw = HardwarePassport()
    hw_report = []
    hw_report.append(f"CPU: {hw.cpu_name}")
    hw_report.append(f"RAM: {hw.ram_gb} GB")
    if hw.gpu_name:
        hw_report.append(f"GPU: {hw.gpu_name} (VRAM: {hw.vram_gb} GB)")
    else:
        hw_report.append("GPU: не обнаружен (NVIDIA)")
    status = "\n".join(hw_report)
    logging.info("Оборудование определено:\n" + status)

    # Автоопределение разрешения и герцовки монитора
    display_info = hw.get_display_info()
    current_hz = display_info.get("hz", 0)
    current_resolution = display_info.get("resolution", "")

    settings = _load_settings()
    need_save = False

    # Проверяем, существует ли файл настроек (чтобы понять, первый ли это запуск)
    from settings import SETTINGS_FILE

    is_first_launch = not os.path.exists(SETTINGS_FILE)

    # 1. Обновляем автоопределённые значения
    if current_hz > 0 and settings.get("monitor_hz", 0) != current_hz:
        settings["monitor_hz"] = current_hz
        need_save = True
        logging.info(f"Автоопределена герцовка: {current_hz} Гц")
    if current_resolution and settings.get("monitor_resolution") != current_resolution:
        settings["monitor_resolution"] = current_resolution
        need_save = True
        logging.info(f"Автоопределено разрешение: {current_resolution}")

    # 2. Работа с профилями мониторов
    from settings import set_active_monitor_profile, save_monitor_profile

    if is_first_launch:
        # Первый запуск: создаём профиль Default с автоопределёнными параметрами
        logging.info(
            f"Первый запуск: создаём профиль 'Default' с параметрами {current_resolution} @ {current_hz} Гц"
        )
        settings = save_monitor_profile(
            settings, "Default", current_resolution or "1920x1080", current_hz or 60
        )
        settings, _ = set_active_monitor_profile(settings, "Default")
        need_save = True
    else:
        # Не первый запуск: применяем существующий активный профиль
        active_profile_name = settings.get("active_monitor_profile", "Default")
        logging.info(f"Применяем активный профиль '{active_profile_name}'")
        settings, _ = set_active_monitor_profile(settings, active_profile_name)
        need_save = True

    if need_save:
        from settings import save_settings

        save_settings(settings)
        logging.info("Настройки монитора и профили сохранены")

    # --- База данных ---
    logging.info("Инициализация базы данных...")
    db = Database()
    logging.info("База данных готова.")

    # --- Интеллектуальный мост: определяем профиль ---
    resolve_current_profile(db, hw)

    # --- Главное окно ---
    logging.info("Инициализация главного окна...")
    window = MainWindow(hardware_info=status, db=db)
    window.log("Программа запущена.")
    window.show()
    logging.info("Главное окно отображено.")

    # --- Глобальная горячая клавиша ---
    if sys.platform == "win32":
        hotkey_manager = HotkeyManager()
        hotkey_manager.register(int(window.winId()))
        hotkey_manager.alt_f_pressed.connect(window.toggle_window)
        hotkey_manager.ctrl_shift_r_pressed.connect(window.open_quick_add_requirements)
        hotkey_manager.ctrl_shift_f_pressed.connect(
            window.on_manual_fps_request
        )  # Добавлено
        app.installNativeEventFilter(hotkey_manager._filter)
        app.aboutToQuit.connect(hotkey_manager.unregister)
        logging.info(
            "Горячие клавиши Alt+F, Ctrl+Shift+R, Ctrl+Shift+F зарегистрированы."
        )
    else:
        window.log("[!] Глобальная горячая клавиша поддерживается только в Windows.")

    exit_code = app.exec()
    logging.info(f"=== FPS Targeter завершён (код {exit_code}) ===")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
