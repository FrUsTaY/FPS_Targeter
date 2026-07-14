"""
Модуль для автоматического импорта игр из Steam.
Находит установленные игры, парсит libraryfolders.vdf и .acf файлы.
"""

import os
import re
import logging
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QProgressBar,
    QMessageBox,
)
from PySide6.QtCore import Qt, QThread, Signal

logger = logging.getLogger("SteamImporter")


def find_steam_folder():
    """Находит папку Steam через реестр Windows."""
    import sys

    if sys.platform != "win32":
        return None

    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"
        )
        steam_path = winreg.QueryValueEx(key, "InstallPath")[0]
        winreg.CloseKey(key)
        return steam_path
    except Exception:
        return None


def parse_library_folders(steam_path):
    """
    Парсит libraryfolders.vdf и возвращает список путей к библиотекам Steam.
    """
    libraries = [steam_path]  # основная библиотека

    library_file = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if not os.path.exists(library_file):
        logger.warning(f"Файл libraryfolders.vdf не найден: {library_file}")
        return libraries

    try:
        with open(library_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Ищем пути вида "path" "D:\\SteamLibrary"
        pattern = r'"path"\s*"([^"]+)"'
        matches = re.findall(pattern, content)
        for path in matches:
            # Заменяем двойные обратные слеши на одинарные
            path = path.replace("\\\\", "\\")
            if os.path.exists(path) and path not in libraries:
                libraries.append(path)
        logger.info(f"Найдено библиотек Steam: {len(libraries)}")
    except Exception as e:
        logger.error(f"Ошибка парсинга libraryfolders.vdf: {e}")

    return libraries


def get_installed_games(libraries):
    """
    Проходит по всем библиотекам и извлекает названия игр из .acf файлов.
    Возвращает список словарей: [{"appid": ..., "name": ...}]
    """
    games = []
    seen_appids = set()

    for lib_path in libraries:
        steamapps_path = os.path.join(lib_path, "steamapps")
        if not os.path.exists(steamapps_path):
            continue

        for file in os.listdir(steamapps_path):
            if file.endswith(".acf"):
                acf_path = os.path.join(steamapps_path, file)
                try:
                    with open(acf_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    # Извлекаем appid
                    appid_match = re.search(r'"appid"\s*"(\d+)"', content)
                    if not appid_match:
                        continue
                    appid = appid_match.group(1)

                    # Извлекаем название игры
                    name_match = re.search(r'"name"\s*"([^"]+)"', content)
                    if not name_match:
                        continue
                    name = name_match.group(1)

                    # Пропускаем дубликаты (если игра установлена в нескольких библиотеках)
                    if appid not in seen_appids:
                        seen_appids.add(appid)
                        games.append({"appid": appid, "name": name})
                        logger.debug(f"Найдена игра: {name} (appid={appid})")
                except Exception as e:
                    logger.warning(f"Ошибка чтения {file}: {e}")

    logger.info(f"Всего найдено игр в Steam: {len(games)}")
    return sorted(games, key=lambda x: x["name"].lower())


class SteamScannerThread(QThread):
    """Поток для сканирования Steam без блокировки UI."""

    finished = Signal(list)  # список игр
    error = Signal(str)
    progress = Signal(int, int)  # текущий, всего

    def run(self):
        try:
            logger.info("Начинаем сканирование Steam...")
            self.progress.emit(0, 3)

            self.progress.emit(1, 3)
            steam_path = find_steam_folder()
            if not steam_path:
                self.error.emit("Steam не найден. Убедитесь, что Steam установлен.")
                return

            self.progress.emit(2, 3)
            libraries = parse_library_folders(steam_path)

            self.progress.emit(3, 3)
            games = get_installed_games(libraries)

            self.finished.emit(games)
        except Exception as e:
            logger.error(f"Ошибка сканирования Steam: {e}")
            self.error.emit(str(e))


class SteamImportDialog(QDialog):
    """Диалог выбора игр из Steam для импорта."""

    def __init__(self, db, profile_id, parent=None):
        super().__init__(parent)
        self.db = db
        self.profile_id = profile_id
        self.setWindowTitle("Импорт игр из Steam")
        self.setMinimumSize(500, 400)

        self.games = []
        self.selected_games = []

        self._init_ui()
        self._start_scan()

    def _show_help(self):
        QMessageBox.about(
            self,
            "Справка: Импорт из Steam",
            "📖 **Назначение:**\n"
            "Автоматическое добавление установленных игр из Steam в калибровку.\n\n"
            "🔧 **Как работает:**\n"
            "1. Сканирование папок Steam.\n"
            "2. Поиск .acf файлов с установленными играми.\n"
            "3. Отображение списка найденных игр.\n\n"
            "💡 **Совет:**\n"
            "Выберите нужные игры и нажмите «Импортировать выбранные».\n"
            "Игры, уже существующие в профиле, будут пропущены.",
        )

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Устанавливаем тёмную тему для всего окна
        self.setStyleSheet("""
            QWidget {
                background-color: #0D1520;
                color: #E0E6ED;
                font-family: "Segoe UI", sans-serif;
                font-size: 9pt;
            }
            QLabel {
                color: #8892B0;
            }
            QListWidget {
                background-color: #101A2C;
                border: 1px solid #1A2234;
                border-radius: 6px;
                color: #E0E6ED;
                outline: none;
            }
            QListWidget::item:selected {
                background-color: #1A3A5A;
                color: #00FFCC;
            }
            QListWidget::item:hover:!selected {
                background-color: #1A2A3A;
            }
            QProgressBar {
                background-color: #101A2C;
                border: 1px solid #1A2234;
                border-radius: 4px;
                text-align: center;
                color: #FFFFFF;
            }
            QProgressBar::chunk {
                background-color: #00C8A5;
                border-radius: 3px;
            }
            QPushButton {
                background-color: #101A2C;
                border: 1px solid #1A2234;
                border-radius: 6px;
                padding: 6px 12px;
                color: #E0E6ED;
            }
            QPushButton:hover {
                background-color: #1A2A3A;
                border: 1px solid #00FFCC;
                color: #FFFFFF;
            }
            QPushButton:disabled {
                background-color: #0A1220;
                border: 1px solid #1A2234;
                color: #3A4A5A;
            }
        """)

        self.status_label = QLabel("Сканирование Steam...")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 3)
        layout.addWidget(self.progress_bar)

        self.games_list = QListWidget()
        self.games_list.setSelectionMode(QListWidget.MultiSelection)
        self.games_list.setVisible(False)
        layout.addWidget(self.games_list)

        self.select_all_btn = QPushButton("Выбрать всё")
        self.select_all_btn.clicked.connect(self._select_all)
        self.select_all_btn.setVisible(False)

        self.deselect_all_btn = QPushButton("Снять всё")
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        self.deselect_all_btn.setVisible(False)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.select_all_btn)
        btn_layout.addWidget(self.deselect_all_btn)
        layout.addLayout(btn_layout)

        self.import_btn = QPushButton("Импортировать выбранные")
        self.import_btn.clicked.connect(self._import_games)
        self.import_btn.setVisible(False)
        self.import_btn.setEnabled(False)

        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self.reject)

        self.help_btn = QPushButton("❓ Справка")
        self.help_btn.clicked.connect(self._show_help)
        self.help_btn.setVisible(False)

        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(self.help_btn)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.import_btn)
        bottom_layout.addWidget(self.cancel_btn)
        layout.addLayout(bottom_layout)

    def _start_scan(self):
        self.scanner = SteamScannerThread()
        self.scanner.progress.connect(self._on_progress)
        self.scanner.finished.connect(self._on_scan_finished)
        self.scanner.error.connect(self._on_scan_error)
        self.scanner.start()

    def _on_progress(self, current, total):
        self.progress_bar.setValue(current)
        if current == total:
            self.status_label.setText(
                "Сканирование завершено. Выберите игры для импорта:"
            )

    def _on_scan_finished(self, games):
        self.games = games
        self.progress_bar.setVisible(False)
        self.games_list.setVisible(True)
        self.select_all_btn.setVisible(True)
        self.deselect_all_btn.setVisible(True)
        self.import_btn.setVisible(True)
        self.help_btn.setVisible(True)

        for game in games:
            item = QListWidgetItem(game["name"])
            item.setData(Qt.UserRole, game)
            self.games_list.addItem(item)

        self.status_label.setText(f"Найдено игр: {len(games)}")
        self.games_list.itemSelectionChanged.connect(self._on_selection_changed)

    def _on_scan_error(self, error_msg):
        QMessageBox.warning(
            self, "Ошибка", f"Не удалось просканировать Steam:\n{error_msg}"
        )
        self.reject()

    def _on_selection_changed(self):
        self.import_btn.setEnabled(len(self.games_list.selectedItems()) > 0)

    def _select_all(self):
        self.games_list.selectAll()

    def _deselect_all(self):
        self.games_list.clearSelection()

    def _import_games(self):
        selected = self.games_list.selectedItems()
        if not selected:
            return

        imported_count = 0
        for item in selected:
            game_data = item.data(Qt.UserRole)
            game_name = game_data["name"]

            # Проверяем, есть ли уже такая игра в профиле
            existing_games = self.db.get_games_for_profile(self.profile_id)
            if game_name in existing_games:
                logger.info(f"Игра '{game_name}' уже есть в профиле, пропускаем")
                continue

            # Добавляем игру
            self.db.add_game_to_profile(self.profile_id, game_name)
            logger.info(f"Импортирована игра: {game_name}")
            imported_count += 1

        QMessageBox.information(
            self,
            "Импорт завершён",
            f"Добавлено игр: {imported_count}\n"
            f"Пропущено (уже есть): {len(selected) - imported_count}",
        )

        self.accept()
