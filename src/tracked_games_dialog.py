"""
Диалог управления списком отслеживаемых игр для оверлея.
"""

import psutil
import logging
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QMessageBox,
    QInputDialog,
)
from PySide6.QtCore import Qt, QThread, Signal

logger = logging.getLogger("TrackedGames")


class ProcessScannerThread(QThread):
    """Поток для сканирования запущенных процессов."""

    finished = Signal(list)
    error = Signal(str)
    progress = Signal(str)

    def run(self):
        try:
            processes = []
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    proc_name = proc.info["name"]
                    if proc_name and proc_name.endswith(".exe"):
                        processes.append(proc_name.lower())
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            # Убираем дубликаты и сортируем
            processes = sorted(list(set(processes)))
            self.finished.emit(processes)
        except Exception as e:
            self.error.emit(str(e))


class TrackedGamesDialog(QDialog):
    """Диалог управления списком отслеживаемых игр."""

    def __init__(self, settings, save_callback, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.save_callback = save_callback
        self.setWindowTitle("Настройка отслеживания игр")
        self.setMinimumSize(500, 450)

        self._init_ui()
        self._refresh_list()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Информационная метка
        info_label = QLabel(
            "🔍 Оверлей будет автоматически появляться при запуске этих игр\n"
            "и следовать за окном игры. При Alt+Tab оверлей скрывается."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #8892B0; font-size: 9pt; padding: 5px;")
        layout.addWidget(info_label)

        # Список отслеживаемых игр
        layout.addWidget(QLabel("📋 Отслеживаемые игры (.exe файлы):"))
        self.tracked_list = QListWidget()
        self.tracked_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.tracked_list.setStyleSheet("""
            QListWidget {
                background-color: #101A2C;
                border: 1px solid #1A2234;
                border-radius: 6px;
                color: #E0E6ED;
                outline: none;
            }
            QListWidget::item:selected {
                background-color: #1A3A5A;
                color: #FFFFFF;
            }
            QListWidget::item:hover {
                background-color: #1A2A3A;
            }
        """)
        layout.addWidget(self.tracked_list)

        # Кнопки управления списком
        btn_layout1 = QHBoxLayout()
        self.add_btn = QPushButton("➕ Добавить вручную")
        self.add_btn.clicked.connect(self._add_manually)
        self.remove_btn = QPushButton("🗑 Удалить выбранные")
        self.remove_btn.clicked.connect(self._remove_selected)
        btn_layout1.addWidget(self.add_btn)
        btn_layout1.addWidget(self.remove_btn)
        btn_layout1.addStretch()
        layout.addLayout(btn_layout1)

        # Блок быстрого добавления из процессов
        layout.addWidget(QLabel("🎮 Быстрое добавление из запущенных процессов:"))
        self.scan_btn = QPushButton("🔍 Сканировать запущенные процессы")
        self.scan_btn.clicked.connect(self._scan_processes)
        layout.addWidget(self.scan_btn)

        self.scan_progress = QLabel("")
        self.scan_progress.setStyleSheet("color: #8892B0; font-size: 9pt;")
        layout.addWidget(self.scan_progress)

        self.processes_list = QListWidget()
        self.processes_list.setVisible(False)
        self.processes_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.processes_list.setStyleSheet("""
            QListWidget {
                background-color: #101A2C;
                border: 1px solid #1A2234;
                border-radius: 6px;
                color: #E0E6ED;
                outline: none;
            }
            QListWidget::item:selected {
                background-color: #1A3A5A;
                color: #FFFFFF;
            }
            QListWidget::item:hover {
                background-color: #1A2A3A;
            }
        """)
        layout.addWidget(self.processes_list)

        btn_layout2 = QHBoxLayout()
        self.add_from_proc_btn = QPushButton("➕ Добавить выбранные из процессов")
        self.add_from_proc_btn.clicked.connect(self._add_from_processes)
        self.add_from_proc_btn.setVisible(False)
        btn_layout2.addWidget(self.add_from_proc_btn)
        btn_layout2.addStretch()
        layout.addLayout(btn_layout2)

        # Кнопки закрытия
        help_btn = QPushButton("❓ Справка")
        help_btn.clicked.connect(self._show_help)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)

        btn_layout3 = QHBoxLayout()
        btn_layout3.addWidget(help_btn)
        btn_layout3.addStretch()
        btn_layout3.addWidget(close_btn)
        layout.addLayout(btn_layout3)

    def _refresh_list(self):
        """Обновляет список отслеживаемых игр."""
        self.tracked_list.clear()
        tracked = self.settings.get("tracked_games", [])
        for exe_name in sorted(tracked):
            item = QListWidgetItem(exe_name)
            item.setToolTip(f"Оверлей будет отслеживать процесс: {exe_name}")
            self.tracked_list.addItem(item)

        if not tracked:
            item = QListWidgetItem("(список пуст)")
            item.setFlags(Qt.NoItemFlags)
            self.tracked_list.addItem(item)

    def _add_manually(self):
        """Ручное добавление .exe файла."""
        exe_name, ok = QInputDialog.getText(
            self,
            "Добавить игру",
            "Введите имя исполняемого файла игры:\n"
            "Примеры: cyberpunk2077.exe, eldenring.exe\n\n"
            "Можно указать полный путь или только имя файла.",
        )
        if ok and exe_name.strip():
            exe = exe_name.strip().lower()
            tracked = self.settings.get("tracked_games", [])
            if exe in tracked:
                QMessageBox.information(self, "Информация", f"'{exe}' уже в списке.")
                return
            tracked.append(exe)
            self.settings["tracked_games"] = tracked
            self.save_callback(self.settings)
            self._refresh_list()
            logger.info(f"Добавлена игра в отслеживание: {exe}")

    def _remove_selected(self):
        """Удаляет выбранные игры из списка."""
        selected = self.tracked_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите игры для удаления.")
            return

        tracked = self.settings.get("tracked_games", [])
        for item in selected:
            exe = item.text()
            if exe in tracked:
                tracked.remove(exe)

        self.settings["tracked_games"] = tracked
        self.save_callback(self.settings)
        self._refresh_list()
        logger.info(
            f"Удалены игры из отслеживания: {[item.text() for item in selected]}"
        )

    def _scan_processes(self):
        """Сканирует запущенные процессы."""
        self.scan_btn.setEnabled(False)
        self.scan_progress.setText("⏳ Сканирование процессов...")
        self.processes_list.clear()
        self.processes_list.setVisible(False)
        self.add_from_proc_btn.setVisible(False)

        self.scanner = ProcessScannerThread()
        self.scanner.finished.connect(self._on_scan_finished)
        self.scanner.error.connect(self._on_scan_error)
        self.scanner.start()

    def _on_scan_finished(self, processes):
        self.scan_btn.setEnabled(True)
        self.scan_progress.setText(f"✅ Найдено процессов: {len(processes)}")
        self.processes_list.setVisible(True)
        self.add_from_proc_btn.setVisible(True)

        tracked = self.settings.get("tracked_games", [])
        for proc in processes:
            item = QListWidgetItem(proc)
            if proc in tracked:
                item.setBackground(Qt.darkGreen)
                item.setToolTip("Уже в списке отслеживания")
                item.setFlags(Qt.NoItemFlags)
            self.processes_list.addItem(item)

    def _on_scan_error(self, error_msg):
        self.scan_btn.setEnabled(True)
        self.scan_progress.setText(f"❌ Ошибка: {error_msg}")
        QMessageBox.warning(
            self, "Ошибка", f"Не удалось сканировать процессы:\n{error_msg}"
        )

    def _add_from_processes(self):
        """Добавляет выбранные процессы в список отслеживания."""
        selected = self.processes_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите процессы для добавления.")
            return

        tracked = self.settings.get("tracked_games", [])
        added = []
        for item in selected:
            proc = item.text()
            if proc not in tracked:
                tracked.append(proc)
                added.append(proc)

        if added:
            self.settings["tracked_games"] = tracked
            self.save_callback(self.settings)
            self._refresh_list()
            logger.info(f"Добавлены процессы в отслеживание: {added}")
            QMessageBox.information(self, "Успех", f"Добавлено процессов: {len(added)}")
        else:
            QMessageBox.information(
                self, "Информация", "Выбранные процессы уже в списке."
            )

        # Очищаем список процессов
        self.processes_list.clear()
        self.processes_list.setVisible(False)
        self.add_from_proc_btn.setVisible(False)
        self.scan_progress.setText("")

    def _show_help(self):
        QMessageBox.about(
            self,
            "Справка: Отслеживание игр",
            "📖 **Как это работает:**\n\n"
            "1. Добавьте .exe файлы игр, которые хотите отслеживать.\n"
            "2. Включите оверлей (чекбокс в трей-меню).\n"
            "3. При запуске игры оверлей автоматически появится поверх окна.\n"
            "4. При переключении на другое окно (Alt+Tab) оверлей скроется.\n\n"
            "🔧 **Способы добавления:**\n"
            "• Вручную – введите имя .exe файла.\n"
            "• Из процессов – выберите из списка запущенных программ.\n\n"
            "💡 **Совет:**\n"
            "Для игр из Steam можно добавить основной .exe файл игры.\n"
            "Имя можно посмотреть в свойствах ярлыка или в диспетчере задач.",
        )
