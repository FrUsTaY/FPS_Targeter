"""
Модуль синхронизации с Яндекс.Диском (упрощённый).
Прямой ввод токена, без регистрации приложения.
"""
import os
import sys
import json
import logging
import requests
from datetime import datetime
from PySide6.QtCore import QThread, Signal
import urllib3
import zipfile
import shutil

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger("CloudSync")
API_BASE = "https://cloud-api.yandex.net/v1/disk"

# Определяем путь к временным файлам
if getattr(sys, "frozen", False):
    base_path = os.path.dirname(sys.executable)
else:
    base_path = os.path.dirname(os.path.abspath(__file__))


class YandexDiskAPI:
    """API для работы с Яндекс.Диском (по токену)."""
    def __init__(self, access_token):
        self.access_token = access_token
        self.headers = {"Authorization": f"OAuth {access_token}"}

    def _request(self, method, url, **kwargs):
        """Выполняет запрос к API."""
        try:
            kwargs["verify"] = False
            resp = requests.request(method, url, headers=self.headers, **kwargs)
            if resp.status_code == 401:
                logger.warning("Токен истёк или недействителен")
                return None
            return resp
        except Exception as e:
            logger.error(f"Ошибка запроса: {e}")
            return None

    def ensure_folder(self, folder_path):
        """Создаёт папку на Диске, если её нет."""
        url = f"{API_BASE}/resources"
        params = {"path": folder_path}
        resp = self._request("GET", url, params=params)
        if resp and resp.status_code == 200:
            return True
        params = {"path": folder_path}
        resp = self._request("PUT", url, params=params)
        if resp and resp.status_code == 201:
            logger.info(f"Папка создана: {folder_path}")
            return True
        logger.error(
            f"Не удалось создать папку: {resp.status_code if resp else 'No response'}"
        )
        return False

    def upload_file(self, local_path, remote_path):
        """Загружает файл на Диск."""
        url = f"{API_BASE}/resources/upload"
        params = {"path": remote_path,"overwrite":"true"}
        resp = self._request("GET", url, params=params)
        if not resp or resp.status_code != 200:
            logger.error(
                f"Не удалось получить URL для загрузки: {resp.status_code if resp else 'No response'}"
            )
            return False

        upload_url = resp.json().get("href")
        if not upload_url:
            return False

        with open(local_path, "rb") as f:
            resp = requests.put(upload_url, data=f, timeout=60, verify=False)

        if resp.status_code == 201:
            logger.info(f"Файл загружен: {remote_path}")
            return True
        logger.error(f"Ошибка загрузки: {resp.status_code}")
        return False

    def download_file(self, remote_path, local_path):
        """Скачивает файл с Диска."""
        url = f"{API_BASE}/resources/download"
        params = {"path": remote_path}
        resp = self._request("GET", url, params=params)
        if not resp or resp.status_code != 200:
            logger.error(
                f"Не удалось получить URL для скачивания: {resp.status_code if resp else 'No response'}"
            )
            return False

        download_url = resp.json().get("href")
        if not download_url:
            return False

        resp = requests.get(download_url, timeout=60, verify=False)
        if resp.status_code == 200:
            with open(local_path, "wb") as f:
                f.write(resp.content)
            logger.info(f"Файл скачан: {remote_path}")
            return True
        logger.error(f"Ошибка скачивания: {resp.status_code}")
        return False

    def get_file_info(self, remote_path):
        """Возвращает информацию о файле (размер, дата изменения)."""
        url = f"{API_BASE}/resources"
        params = {"path": remote_path}
        resp = self._request("GET", url, params=params)
        if resp and resp.status_code == 200:
            data = resp.json()
            return {"size": data.get("size"),"modified": data.get("modified")}
        return None

    def list_files(self, folder_path, pattern=None):
        """Возвращает список файлов в папке."""
        url = f"{API_BASE}/resources/files"
        params = {"path": folder_path}
        resp = self._request("GET", url, params=params)
        if resp and resp.status_code == 200:
            items = resp.json().get("items", [])
            return items
        return []


def get_token_url():
    """Возвращает URL для получения токена Яндекс.Диска."""
    return "https://oauth.yandex.ru/authorize?response_type=token&client_id="


class SyncThread(QThread):
    """Поток для синхронизации без блокировки UI."""
    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, db, settings, action="upload"):
        super().__init__()
        self.db = db
        self.settings = settings
        self.action = action  # upload, download, auto

    def run(self):
        try:
            if self.action == "upload":
                self._upload()
            elif self.action == "download":
                self._download()
            else:
                self._auto_sync()
        except Exception as e:
            logger.error(f"Ошибка синхронизации: {e}")
            self.finished.emit(False, str(e))

    def _get_backup_name(self):
        """Генерирует имя файла бекапа на основе UUID активного профиля."""
        profile_id = self.db.get_current_profile_id()
        if not profile_id:
            return "backup_unknown.json"
        profile_uuid = self.db.get_profile_uuid(profile_id)
        if not profile_uuid:
            return "backup_unknown.json"
        # Очищаем UUID от недопустимых символов (хотя UUID безопасен)
        import re
        safe_uuid = re.sub(r'[\\/*?:"<>|]', '', profile_uuid)
        return f"backup_{safe_uuid}.json"

    def _upload(self):
        """Экспортирует текущий профиль в JSON и загружает на Яндекс.Диск."""
        self.progress.emit("Экспорт профиля в JSON...")
        
        profile_id = self.db.get_current_profile_id()
        if not profile_id:
            self.finished.emit(False, "Нет активного профиля")
            return

        # Получаем данные через существующий метод экспорта
        export_data = self.db.export_profile_to_dict(profile_id)
        if not export_data:
            self.finished.emit(False, "Не удалось экспортировать данные профиля")
            return

        # Добавляем метаинформацию (дата экспорта)
        from datetime import datetime
        export_data["export_info"] = {
            "export_date": datetime.now().isoformat(),
            "profile_id": profile_id,
            "version": "1.0",
            "cloud_sync": True
        }

        # Сохраняем во временный JSON-файл
        temp_json = os.path.join(base_path, "temp_backup.json")
        try:
            import json
            with open(temp_json, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Профиль экспортирован во временный файл: {temp_json}")
        except Exception as e:
            self.finished.emit(False, f"Ошибка при создании JSON-файла: {e}")
            return

        self.progress.emit("Загрузка на Яндекс.Диск...")
        folder = self.settings.get("cloud_folder", "FPS_Targeter_Backup")
        backup_name = self._get_backup_name()
        remote_path = f"{folder}/{backup_name}"
        token = self.settings.get("cloud_access_token")
        api = YandexDiskAPI(token)

        if not api.ensure_folder(folder):
            os.remove(temp_json)
            self.finished.emit(False, "Не удалось создать/найти папку на Диске")
            return

        if api.upload_file(temp_json, remote_path):
            self.settings["cloud_last_sync"] = datetime.now().isoformat()
            from settings import save_settings
            save_settings(self.settings)
            os.remove(temp_json)
            self.finished.emit(True, "Бекап профиля успешно загружен в облако")
        else:
            os.remove(temp_json)
            self.finished.emit(False, "Ошибка загрузки файла на Диск")

    def _download(self):
        """Скачивает JSON-файл с Диска и импортирует его в текущий профиль."""
        self.progress.emit("Проверка облака...")
        
        profile_id = self.db.get_current_profile_id()
        if not profile_id:
            self.finished.emit(False, "Нет активного профиля")
            return

        folder = self.settings.get("cloud_folder", "FPS_Targeter_Backup")
        backup_name = self._get_backup_name()
        remote_path = f"{folder}/{backup_name}"
        token = self.settings.get("cloud_access_token")
        api = YandexDiskAPI(token)

        file_info = api.get_file_info(remote_path)
        if not file_info:
            self.finished.emit(False, "В облаке нет сохранённого бекапа для этого профиля")
            return

        self.progress.emit("Скачивание файла...")
        temp_json = os.path.join(base_path, "temp_backup.json")
        if not api.download_file(remote_path, temp_json):
            self.finished.emit(False, "Ошибка скачивания файла")
            return

        self.progress.emit("Восстановление данных...")
        try:
            import json
            with open(temp_json, "r", encoding="utf-8") as f:
                import_data = json.load(f)

            # Проверяем структуру
            if "profile" not in import_data:
                raise ValueError("Файл не содержит секции profile")

            # Импортируем в текущий профиль (очистит и перезапишет все данные)
            self.db.import_profile_from_dict(import_data, target_profile_id=profile_id, set_as_current=True)

            # Обновляем настройки (API-ключи, профили мониторов уже внутри импорта)
            from settings import load_settings, save_settings
            self.settings = load_settings()
            self.settings["cloud_last_sync"] = datetime.now().isoformat()
            save_settings(self.settings)

            os.remove(temp_json)

            # Сигнализируем UI о необходимости обновить интерфейс
            self.finished.emit(True, "Восстановление из облака выполнено|RELOAD_UI")
        except Exception as e:
            logger.error(f"Ошибка импорта из скачанного файла: {e}")
            os.remove(temp_json)
            self.finished.emit(False, f"Ошибка при восстановлении данных: {e}")

    def _auto_sync(self):
        """Автосинхронизация: сравнивает даты и выбирает более новую версию."""
        self.progress.emit("Проверка облачной версии...")

        folder = self.settings.get("cloud_folder","FPS_Targeter_Backup")

        profile_id = self.db.get_current_profile_id()
        if profile_id:
            cursor = self.db.conn.cursor()
            cursor.execute(
                "SELECT cpu_name, gpu_name FROM hardware_profiles WHERE id=?",
                (profile_id,),
            )
            hw = cursor.fetchone()
            if hw:
                cpu_short = hw[0].split(" @")[0].strip() if hw[0] else"Unknown"
                gpu_short = hw[1].split(" (")[0].strip() if hw[1] else"Unknown"
                import re
                cpu_clean = re.sub(r'[\\/*?:"<>|]',"", cpu_short)
                gpu_clean = re.sub(r'[\\/*?:"<>|]',"", gpu_short)
                backup_name = f"fps_targeter_backup_{cpu_clean}_{gpu_clean}.zip"
            else:
                backup_name = self.settings.get(
                    "cloud_backup_name","fps_targeter_backup.zip"
                )
        else:
            backup_name = self.settings.get(
                "cloud_backup_name","fps_targeter_backup.zip"
            )

        remote_path = f"{folder}/{backup_name}"
        token = self.settings.get("cloud_access_token")
        api = YandexDiskAPI(token)

        file_info = api.get_file_info(remote_path)
        if not file_info:
            self.finished.emit(False, "В облаке нет сохранённого бэкапа")
            return

        cloud_modified = file_info.get("modified","")
        local_sync = self.settings.get("cloud_last_sync","")

        if cloud_modified > local_sync:
            self.progress.emit("Облачная версия новее, загружаем...")
            self._download()
        else:
            self.progress.emit("Локальная версия актуальна")
            self.finished.emit(True, "Синхронизация не требуется")