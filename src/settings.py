"""Сохранение/загрузка настроек (API-ключ Gemini, модель Ollama)."""

import json
import os
import sys
import logging

logger = logging.getLogger(__name__)

# Определяем путь к файлу настроек
if getattr(sys, "frozen", False):
    # Запущено из .exe
    base_path = os.path.dirname(sys.executable)
else:
    # Запущено из скрипта
    base_path = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(base_path, "fps_settings.json")

DEFAULTS = {
    "gemini_api_key": "",
    "run_at_startup": False,
    "openrouter_api_key": "",
    "groq_api_key": "",
    "monitor_hz": 165,
    "monitor_resolution": "1920x1080",
    "monitor_profiles": [{"name": "Default", "resolution": "1920x1080", "hz": 60}],
    "active_monitor_profile": "Default",
    "cloud_sync_enabled": False,
    "cloud_access_token": "",
    "cloud_refresh_token": "",
    "cloud_last_sync": "",
    "cloud_folder": "FPS_Targeter_Backup",
    "cloud_backup_name": "fps_targeter_backup.zip",
    "target_fps_user_modified": False,
    "tracked_games": []
}


def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        logger.info("Файл настроек не найден, используются значения по умолчанию.")
        return DEFAULTS.copy()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            s = json.load(f)
        for k, v in DEFAULTS.items():
            s.setdefault(k, v)
        # Маскируем ключи при логировании
        safe = {}
        for k, v in s.items():
            if "key" in k.lower() or"token" in k.lower():
                from logging_utils import mask_key

                safe[k] = mask_key(v) if isinstance(v, str) else v
            else:
                safe[k] = v
        logger.info(f"Настройки загружены: {safe}")
        return s
    except Exception as e:
        logger.error(f"Ошибка загрузки настроек: {e}")
        return DEFAULTS.copy()


def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
        f.flush()
        os.fsync(f.fileno())  # Гарантия записи на диск до возврата
    # Логируем с маскированием
    safe = {}
    for k, v in settings.items():
        if "key" in k.lower() or"token" in k.lower():
            from logging_utils import mask_key

            safe[k] = mask_key(v) if isinstance(v, str) else v
        else:
            safe[k] = v
    logger.info(f"Настройки сохранены: {safe}")


def get_monitor_profiles(settings):
    """Безопасно возвращает список профилей мониторов."""
    profiles = settings.get("monitor_profiles", [])
    if not profiles:
        profiles = [{"name":"Default","resolution":"1920x1080","hz": 60}]
    return profiles


def save_monitor_profile(settings, profile_name, resolution, hz):
    """Сохраняет или обновляет профиль монитора. Возвращает обновлённые settings."""
    profiles = get_monitor_profiles(settings)
    # Ищем существующий профиль с таким именем
    for i, p in enumerate(profiles):
        if p.get("name") == profile_name:
            profiles[i] = {"name": profile_name,"resolution": resolution,"hz": hz}
            break
    else:
        profiles.append({"name": profile_name,"resolution": resolution,"hz": hz})
    settings["monitor_profiles"] = profiles
    return settings


def delete_monitor_profile(settings, profile_name):
    """Удаляет профиль монитора. Нельзя удалить активный профиль."""
    if profile_name == settings.get("active_monitor_profile"):
        logger.warning(f"Попытка удалить активный профиль '{profile_name}' отклонена.")
        return settings, False
    profiles = get_monitor_profiles(settings)
    new_profiles = [p for p in profiles if p.get("name") != profile_name]
    if len(new_profiles) == len(profiles):
        logger.warning(f"Профиль '{profile_name}' не найден для удаления.")
        return settings, False
    settings["monitor_profiles"] = new_profiles
    logger.info(f"Удалён профиль монитора '{profile_name}'")
    return settings, True


def set_active_monitor_profile(settings, profile_name):
    """Устанавливает активный профиль и применяет его resolution/hz в основные настройки."""
    profiles = get_monitor_profiles(settings)
    for p in profiles:
        if p.get("name") == profile_name:
            settings["active_monitor_profile"] = profile_name
            settings["monitor_resolution"] = p.get("resolution","1920x1080")
            settings["monitor_hz"] = p.get("hz", 60)
            logger.info(
                f"Активный профиль монитора изменён на '{profile_name}'"
                f"({p.get('resolution')} @ {p.get('hz')} Гц)"
            )
            return settings, True
    logger.warning(f"Профиль '{profile_name}' не найден, активный профиль не изменён.")
    return settings, False
