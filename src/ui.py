"""
Главное окно приложения FPS Targeter (исправленный порядок инициализации)
Интегрированы вкладки "Калибровка","AI Scout", заглушка"Управление".
"""

import json
import logging
import os
import sys
import webbrowser
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QSystemTrayIcon,
    QMenu,
    QInputDialog,
    QMessageBox,
    QCheckBox,
    QStatusBar,
    QWidgetAction,
    QLabel,
    QGroupBox,  # ← добавлено для спойлера логов
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QPalette, QColor, QFont

from calibration_tab import CalibrationTab
from ai_scout_tab import AIScoutTab, ProviderButton
from target_control_tab import TargetControlTab
from overlay_manager import OverlayWindow, OverlayConfigWindow
from game_tracker import GameOverlayTracker

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def _is_autostart_enabled(self) -> bool:
        """Проверяет, включён ли автозапуск программы."""
        if sys.platform != "win32":
            return False

        try:
            import winreg

            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
            app_name = "FPS_Targeter"

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ
            ) as key:
                value, _ = winreg.QueryValueEx(key, app_name)
                return True
        except Exception:
            return False

    def _show_welcome_dialog(self):
        """Показывает окно с описанием программы с чекбоксом «Больше не показывать»."""
        from PySide6.QtWidgets import QCheckBox
        from settings import load_settings, save_settings

        # Создаём кастомный диалог
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Добро пожаловать в FPS Targeter!")
        msg_box.setText(
            "🎮 **FPS Targeter 3.1** — рождён из боли геймера.\n\n"
            "📌 **Проблема:**\n"
            "Вы купили мощный ПК, но в играх просадки FPS?\n"
            "Настройки графики — это тёмный лес?\n"
            "А VRAM постоянно переполняется?\n\n"
            "🔧 **Решение:**\n"
            "FPS Targeter анализирует ваше железо, калибрует FPS в 6 пресетах,\n"
            "подсказывает оптимальные настройки через AI (OpenRouter, Groq, Gemini)\n"
            "и контролирует видеопамять.\n\n"
            "✨ **Уникальность:**\n"
            "• Локальная калибровка на основе системных требований\n"
            "• AI Scout с тремя провайдерами\n"
            "• Оверлей поверх игр с рекомендациями\n"
            "• Трекер игр для автоматического появления оверлея\n"
            "• Синхронизация профиля через Яндекс.Диск\n\n"
            "🏆 **Результат:**\n"
            "Стабильный FPS, никакой магии — чистая математика и AI.\n\n"
            "Приятного использования! 🚀"
        )

        # Добавляем чекбокс
        checkbox = QCheckBox("Больше не показывать это окно")
        msg_box.setCheckBox(checkbox)

        # Кнопка OK
        msg_box.setStandardButtons(QMessageBox.Ok)

        # Показываем диалог
        msg_box.exec()

        # Если чекбокс отмечен — сохраняем флаг
        if checkbox.isChecked():
            settings = load_settings()
            settings["first_launch_done"] = True
            save_settings(settings)

    def _set_autostart(self, enabled: bool):
        """Включает или выключает автозапуск."""
        if sys.platform != "win32":
            return

        try:
            import winreg
            import os

            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
            app_name = "FPS_Targeter"

            # Определяем путь к программе
            if getattr(sys, "frozen", False):
                # Запущено из .exe
                app_path = f'"{sys.executable}"'
            else:
                # Запущено из скрипта
                app_path = f'"{sys.executable}""{os.path.abspath(__file__)}"'

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
            ) as key:
                if enabled:
                    winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, app_path)
                    self.log("Автозапуск включён")
                else:
                    try:
                        winreg.DeleteValue(key, app_name)
                        self.log("Автозапуск выключен")
                    except WindowsError:
                        pass
        except Exception as e:
            self.log(f"Ошибка настройки автозапуска: {e}")

    def _toggle_autostart(self):
        """Переключает автозапуск."""
        enabled = self.autostart_action.isChecked()
        self._set_autostart(enabled)

    def _ensure_overlay(self):
        """Создаёт оверлей (только если чекбокс активен)."""
        if (
            not hasattr(self, "monitor_checkbox")
            or not self.monitor_checkbox.isChecked()
        ):
            return False
        if not hasattr(self, "overlay") or self.overlay is None:
            try:
                # Определяем путь к файлу настроек оверлея
                if getattr(sys, "frozen", False):
                    base_path = os.path.dirname(sys.executable)
                else:
                    base_path = os.path.dirname(os.path.abspath(__file__))
                
                # Загружаем настройки оверлея из отдельного файла
                overlay_settings = {}
                overlay_settings_path = os.path.join(base_path, "overlay_settings.json")
                if os.path.exists(overlay_settings_path):
                    try:
                        with open(overlay_settings_path,"r") as f:
                            overlay_settings = json.load(f)
                    except Exception:
                        pass
                # Получаем список игр из калибровки (извлекаем тексты из QListWidget)
                games_list = []
                game_widget = self.calibration_tab.game_list
                if game_widget:
                    for i in range(game_widget.count()):
                        item = game_widget.item(i)
                        if item:
                            games_list.append(item.text())
                self.overlay = OverlayWindow(
                    settings=overlay_settings, games_list=games_list, db=self.db
                )
            except Exception as e:
                self.log(f"Ошибка создания оверлея: {e}")
                return False
        # Не показываем оверлей сразу, только если трекер его активирует
        # self.overlay.show()  # закомментировано
        return True

    def _start_game_tracker(self):
        """Запускает трекер игр."""
        if not hasattr(self, "overlay") or self.overlay is None:
            return

        # Если трекер уже работает, не запускаем
        if self.game_tracker is not None:
            return

        from settings import load_settings

        settings = load_settings()
        games_to_track = settings.get("tracked_games", [])

        if not games_to_track:
            self.log("Список отслеживаемых игр пуст.")
            return

        self.game_tracker = GameOverlayTracker(
            games_list=games_to_track,
            overlay=self.overlay,
            settings=self.overlay.settings,
        )

        # Подключаем сигналы
        self.game_tracker.show_overlay.connect(self.overlay.show_safe)
        self.game_tracker.hide_overlay.connect(self.overlay.hide_safe)
        self.game_tracker.update_game_info.connect(self.overlay.set_current_game)

        self.game_tracker.start()
        self.log(f"Трекер игр запущен. Отслеживаемые игры: {games_to_track}")
        # Проверяем видимость оверлея после запуска
        QTimer.singleShot(500, self._check_overlay_visibility)

    def _stop_game_tracker(self):
        """Останавливает трекер игр."""
        if self.game_tracker is not None:
            self.game_tracker.stop()
            self.game_tracker = None
            self.log("Трекер игр остановлен")

    def show_help_dialog(self):
        """Показывает окно справки."""
        QMessageBox.about(
            self,
            "Справка по FPS Targeter",
            "📖 **Основные возможности:**\n\n"
            "• **Калибровка** – добавление игр и ввод реальных замеров FPS.\n"
            "• **AI Scout** – получение рекомендаций от искусственного интеллекта.\n"
            "• **Управление** – подбор оптимального пресета под целевой FPS.\n\n"
            "🎮 **Горячие клавиши (глобальные):**\n"
            "• **Alt+F** – показать/скрыть главное окно (работает из любой программы).\n"
            "• **Ctrl+Shift+R** – быстрое добавление системных требований из буфера обмена.\n"
            "• **Ctrl+Shift+F** – ручной ввод текущего FPS (из RTSS/Steam оверлея) в калибровку.\n\n"
            "🔧 **Дополнительные функции:**\n"
            "• Профили мониторов – сохранение и переключение разрешений/герцовки.\n"
            "• Таблица производительности – ручное редактирование баллов CPU/GPU.\n"
            "• Импорт из Steam – автоматическое добавление установленных игр.\n"
            "• Облачная синхронизация – резервное копирование профиля на Яндекс.Диск.\n\n"
            "💡 **Советы:**\n"
            "• Наведите курсор на любую кнопку – появится подсказка.\n"
            "• Используйте Ctrl+Shift+F когда игра активна – введите FPS из оверлея.\n"
            "• Для быстрого добавления системных требований скопируйте блок с Steam и нажмите Ctrl+Shift+R.\n\n"
            "📁 **Файлы программы:**\n"
            "• fps_data.db – основная база данных.\n"
            "• fps_settings.json – настройки программы.\n"
            "• game_requirements.json – база системных требований.\n"
            "• hardware_benchmark.json – таблица производительности.\n\n"
            "© 2026 Alexey Smolin\n"
            "Версия: 3.1 (с глобальными горячими клавишами)",
        )

    def _destroy_overlay(self):
        """Прячет и удаляет оверлей, закрывает конфигуратор (если открыт)."""
        if (
            hasattr(self, "overlay_configurator")
            and self.overlay_configurator is not None
        ):
            try:
                self.overlay_configurator.close()
            except Exception:
                pass
            self.overlay_configurator = None
        if hasattr(self, "overlay") and self.overlay is not None:
            try:
                self.overlay.hide()
                self.overlay.close()
            except Exception:
                pass
            self.overlay = None

    def _toggle_overlay(self, enabled):
        if enabled:
            self._ensure_overlay()
            self._start_game_tracker()
        else:
            self._stop_game_tracker()
            self._destroy_overlay()

    def _toggle_overlay_edit(self):
        """Открывает конфигуратор оверлея."""
        if (
            not hasattr(self, "monitor_checkbox")
            or not self.monitor_checkbox.isChecked()
        ):
            self.log("Сначала включите чекбокс 'Включить оверлей в играх'")
            return
        if not self._ensure_overlay():
            self.log("Не удалось запустить оверлей.")
            return
        if (
            hasattr(self, "overlay_configurator")
            and self.overlay_configurator is not None
        ):
            try:
                self.overlay_configurator.close()
            except Exception:
                pass
            self.overlay_configurator = None

        # Включаем режим редактирования в трекере
        if self.game_tracker:
            self.game_tracker.set_editing_mode(True)

        # Показываем оверлей
        if self.overlay:
            self.overlay.show()

        try:
            self.overlay_configurator = OverlayConfigWindow(self.overlay)
            self.overlay_configurator.destroyed.connect(self._on_edit_overlay_closed)
            self.overlay_configurator.show()
        except Exception as e:
            self.log(f"Ошибка открытия конфигуратора: {e}")
            if self.game_tracker:
                self.game_tracker.set_editing_mode(False)

    def _on_edit_overlay_closed(self):
        """Выключает режим редактирования после закрытия редактора."""
        self.log("Редактор оверлея закрыт")
        self.overlay_configurator = None

        # Принудительно скрываем оверлей
        if self.overlay:
            self.overlay.hide_safe()

        # Запускаем трекер обратно
        self._start_game_tracker()

    def _check_overlay_visibility(self):
        """Проверяет, нужно ли показывать оверлей."""
        if not self.overlay or not self.game_tracker:
            return

        try:
            import win32gui

            hwnd = getattr(self.game_tracker, "_current_game_hwnd", None)
            if not hwnd:
                self.overlay.hide_safe()
                return

            foreground_hwnd = win32gui.GetForegroundWindow()
            is_foreground = hwnd == foreground_hwnd
            is_iconic = win32gui.IsIconic(hwnd)

            if not (is_foreground and not is_iconic):
                self.overlay.hide_safe()
        except Exception as e:
            logger.error(f"Ошибка проверки видимости оверлея: {e}")

    def _on_overlay_configurator_closed(self):
        """Выключает режим редактирования в трекере после закрытия конфигуратора."""
        if self.game_tracker:
            self.game_tracker.set_editing_mode(False)
        self.log("Редактор оверлея закрыт, трекер возобновлён")

    def __init__(self, hardware_info="", db=None):
        super().__init__()
        self.setWindowTitle("FPS Targeter")
        self.setMinimumSize(800, 600)
        from icon_generator import create_fps_icon

        self.setWindowIcon(create_fps_icon())
        self.db = db
        self._apply_dark_theme()

        # Показываем окно приветствия, если флаг ещё не установлен
        from settings import load_settings

        settings = load_settings()
        if not settings.get("first_launch_done", False):
            QTimer.singleShot(500, self._show_welcome_dialog)

        # Трекер игр для оверлея
        self.game_tracker = None

        # # Автосинхронизация при запуске (ОТКЛЮЧЕНО)
        # from settings import load_settings
        # sync_settings = load_settings()
        # if sync_settings.get("cloud_sync_enabled", False) and sync_settings.get(
        #     "cloud_access_token"
        # ):
        #     QTimer.singleShot(1000, lambda: self.cloud_sync(auto=True))

        # Статус-бар первым
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._status_bar_default_message = ""
        self._status_bar_timer = QTimer()
        self._status_bar_timer.setSingleShot(True)
        self._status_bar_timer.timeout.connect(self._restore_status_bar)
        self._update_status_bar()

        # Центральный виджет – один раз
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Вкладки
        self.tabs = QTabWidget()
        self.calibration_tab = CalibrationTab(db=self.db, log_func=self.log)
        self.tabs.addTab(self.calibration_tab, "Калибровка")

        self.ai_scout_tab = AIScoutTab(
            db=self.db, log_func=self.log, status_func=self._set_status_message
        )
        self.tabs.addTab(self.ai_scout_tab, "AI Scout")

        self.target_control_tab = TargetControlTab(db=self.db, log_func=self.log)
        self.tabs.addTab(self.target_control_tab, "Управление")
        layout.addWidget(self.tabs)

        # Лог-панель с кнопкой очистки и спойлером
        self.log_expander = QGroupBox()
        self.log_expander.setStyleSheet("""
            QGroupBox {
                border: 1px solid #1A2234;
                border-radius: 6px;
                margin-top: 6px;
                padding-top: 6px;
                background-color: #080E18;
            }
        """)
        
        log_layout = QVBoxLayout()
        log_layout.setContentsMargins(8, 8, 8, 8)
        
        # Заголовок с кнопкой сворачивания
        log_header = QHBoxLayout()
        log_header.setContentsMargins(0, 0, 0, 0)
        
        self.log_title = QLabel("\u25B8 Лог")
        self.log_title.setStyleSheet("color: #00FFCC; font-weight: bold; font-size: 9pt;")
        
        self.toggle_log_btn = QPushButton("\u25BC")
        self.toggle_log_btn.setFixedSize(22, 22)
        self.toggle_log_btn.setToolTip("Свернуть/развернуть логи (нажмите, чтобы скрыть/показать)")
        self.toggle_log_btn.setStyleSheet("""
            QPushButton {
                background-color: #0D1520;
                border: 1px solid #1A2234;
                border-radius: 4px;
                color: #00FFCC;
                font-size: 16pt;
                font-weight: bold;
                padding: 0;
            }
            QPushButton:hover {
                border: 1px solid #00FFCC;
                background-color: #0D2030;
                color: #FFFFFF;
            }
        """)
        self.toggle_log_btn.clicked.connect(self._toggle_log_expanded)
        
        clear_btn = QPushButton("🗑 Очистить")
        clear_btn.setFixedWidth(90)
        clear_btn.setFixedHeight(22)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #0D1520;
                border: 1px solid #1A2234;
                border-radius: 4px;
                color: #8892B0;
                font-size: 8pt;
                padding: 2px 6px;
            }
            QPushButton:hover {
                border: 1px solid #00FFCC;
                color: #E0E6ED;
            }
        """)
        clear_btn.clicked.connect(lambda: self.log_widget.clear())
        
        log_header.addWidget(self.log_title)
        log_header.addStretch()
        log_header.addWidget(self.toggle_log_btn)
        log_header.addWidget(clear_btn)
        
        # Контейнер для лога (для управления видимостью)
        self.log_container = QWidget()
        self.log_container_layout = QVBoxLayout()
        self.log_container_layout.setContentsMargins(0, 0, 0, 0)
        self.log_container_layout.setSpacing(0)
        
        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setFont(QFont("Consolas", 9))
        self.log_widget.setStyleSheet("""
            QTextEdit {
                background-color: #060B14;
                border: 1px solid #1A2234;
                border-radius: 4px;
                color: #8FBCBB;
                font-family: 'Consolas', monospace;
                padding: 4px;
            }
        """)
        
        self.log_container_layout.addWidget(self.log_widget)
        self.log_container.setLayout(self.log_container_layout)
        
        log_layout.addLayout(log_header)
        log_layout.addWidget(self.log_container)
        self.log_expander.setLayout(log_layout)
        
        layout.addWidget(self.log_expander)
        
        # Сохраняем начальное состояние
        self._log_expanded = True

        # Чекбокс "Связать цели"
        self.link_checkbox = QCheckBox("Связать цели (AI Scout ↔ Управление)")
        self.link_checkbox.setStyleSheet("color: #CCCCCC;")
        self.link_checkbox.toggled.connect(self._on_link_toggled)
        layout.addWidget(self.link_checkbox)

        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Кнопка полного закрытия программы
        exit_btn = QPushButton("Полностью закрыть программу")
        exit_btn.setFixedWidth(250)
        exit_btn.setToolTip("Завершить работу программы (не сворачивать в трей)")
        exit_btn.clicked.connect(self.quit_app)
        layout.addWidget(exit_btn, alignment=Qt.AlignRight)

        # Системный трей
        self.tray_icon = QSystemTrayIcon(self)
        from icon_generator import create_fps_icon

        self.tray_icon.setIcon(create_fps_icon())
        self.tray_icon.setToolTip("FPS Targeter")

        tray_menu = QMenu()
        show_action = QAction("Показать / Скрыть", self)
        show_action.setToolTip("Показать или скрыть главное окно программы")
        show_action.triggered.connect(self.toggle_window)

        delete_profile_action = QAction("Удалить профиль", self)
        delete_profile_action.setToolTip(
            "Удалить текущий профиль оборудования и все его данные"
        )
        delete_profile_action.triggered.connect(self.delete_profile_dialog)

        about_action = QAction("О программе", self)
        about_action.setToolTip("Информация о программе и авторе")
        about_action.triggered.connect(self.show_about_dialog)

        # Профили мониторов
        monitor_profiles_action = QAction("🖥️ Профили мониторов...", self)
        monitor_profiles_action.setToolTip(
            "Создание, редактирование и переключение профилей мониторов"
        )
        monitor_profiles_action.triggered.connect(self.open_monitor_profiles_dialog)

        # Редактор таблицы производительности
        benchmark_editor_action = QAction(
            "📊 Редактировать таблицу производительности", self
        )
        benchmark_editor_action.setToolTip(
            "Ручное добавление и редактирование баллов CPU/GPU"
        )
        benchmark_editor_action.triggered.connect(self.open_benchmark_editor)

        # Чекбокс мониторинга
        self.monitor_checkbox = QCheckBox("Включить оверлей в играх")
        self.monitor_checkbox.setToolTip("Показывать информационный оверлей поверх игр")
        self.monitor_checkbox.setEnabled(True)
        check_action = QWidgetAction(self)
        check_action.setDefaultWidget(self.monitor_checkbox)
        self.monitor_checkbox.toggled.connect(self._toggle_overlay)

        # Кнопка "Редактировать оверлей"
        edit_overlay_action = QAction("Редактировать оверлей (перетащить)", self)
        edit_overlay_action.setToolTip(
            "Настройка позиции, цвета и прозрачности оверлея"
        )
        edit_overlay_action.triggered.connect(self._toggle_overlay_edit)

        # Кнопка справки
        help_action = QAction("❓ Справка", self)
        help_action.setToolTip("Общая информация о программе и её функциях")
        help_action.triggered.connect(self.show_help_dialog)

        quit_action = QAction("Выход", self)
        quit_action.setToolTip("Завершить работу программы")
        quit_action.triggered.connect(self.quit_app)

        # Импорт из Steam
        steam_import_action = QAction("🎮 Импорт игр из Steam...", self)
        steam_import_action.setToolTip(
            "Автоматическое добавление установленных игр из Steam"
        )
        steam_import_action.triggered.connect(self.import_steam_games)

        # Экспорт/Импорт профиля
        export_profile_action = QAction("💾 Экспортировать профиль...", self)
        export_profile_action.setToolTip("Сохранить все данные профиля в JSON файл")
        export_profile_action.triggered.connect(self.export_profile)

        import_profile_action = QAction("📂 Импортировать профиль...", self)
        import_profile_action.setToolTip(
            "Восстановить профиль из ранее сохранённого JSON файла"
        )
        import_profile_action.triggered.connect(self.import_profile)
        # Облачная синхронизация
        # cloud_sync_action удалён, так как его функциональность дублируется через экспорт/импорт
        cloud_settings_action = QAction("⚙️ Настройки облака...", self)
        cloud_settings_action.setToolTip("Настройка токена и папки для Яндекс.Диска")
        cloud_settings_action.triggered.connect(self.cloud_settings)

        # Автозапуск
        self.autostart_action = QAction("🚀 Автозапуск с Windows", self)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setToolTip(
            "Запускать программу автоматически при загрузке Windows"
        )
        self.autostart_action.triggered.connect(self._toggle_autostart)
        self.autostart_action.setChecked(self._is_autostart_enabled())

        # Настройка отслеживания игр для оверлея
        tracked_games_action = QAction("🎮 Настроить отслеживание игр...", self)
        tracked_games_action.setToolTip(
            "Добавить/удалить игры, для которых оверлей будет автоматически показываться"
        )
        tracked_games_action.triggered.connect(self.open_tracked_games_dialog)

        tray_menu.addAction(show_action)
        tray_menu.addAction(delete_profile_action)
        tray_menu.addAction(about_action)
        tray_menu.addAction(monitor_profiles_action)
        tray_menu.addAction(benchmark_editor_action)
        tray_menu.addAction(steam_import_action)
        tray_menu.addSeparator()
        tray_menu.addAction(export_profile_action)
        tray_menu.addAction(import_profile_action)
        tray_menu.addSeparator()
        # tray_menu.addAction(cloud_sync_action)  # удалено – дублируется экспортом/импортом
        tray_menu.addAction(cloud_settings_action)
        tray_menu.addAction(self.autostart_action)
        tray_menu.addAction(tracked_games_action)
        tray_menu.addSeparator()
        tray_menu.addAction(check_action)
        tray_menu.addAction(edit_overlay_action)
        tray_menu.addAction(help_action)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()
        self.log(hardware_info)

        # Принудительно обновить статус-бар после полной инициализации
        QTimer.singleShot(100, self._update_status_bar)

    def _set_status_message(self, msg=None, timeout=3000):
        """Устанавливает сообщение в статус-бар.
        Если msg=None — возвращает к основному сообщению.
        Если msg задан — показывает его на timeout миллисекунд, затем возвращается.
        """
        if not hasattr(self, "status_bar"):
            return
        if msg is None:
            self._restore_status_bar()
        else:
            self.status_bar.showMessage(msg)
            self._status_bar_timer.start(timeout)

    def _restore_status_bar(self):
        """Возвращает статус-бар к основному сообщению (GPU, VRAM, монитор)."""
        if (
            hasattr(self, "_status_bar_default_message")
            and self._status_bar_default_message
        ):
            self.status_bar.showMessage(self._status_bar_default_message)
        else:
            self._update_status_bar()

    def _apply_dark_theme(self):
        QApplication.setStyle("Fusion")

        # Радиальный градиент для главного окна (киберпанк-эффект)
        self.setStyleSheet("""
            /* Глобальные настройки для всех виджетов */
            QWidget {
                color: #E0E6ED;
                font-family: "Segoe UI","Microsoft Sans Serif", sans-serif;
                font-size: 9pt;
            }
            
            /* Увеличенный шрифт для SpinBox (цифры) */
            QSpinBox {
                font-size: 10pt;
                font-weight: bold;
            }
            
            /* Цифры FPS в рекомендациях */
            QLabel {
                font-size: 9pt;
            }
            
            QMainWindow {
                background: qradialgradient(cx:0.5, cy:0.5, radius:1.5,
                    stop:0 #0A1428,
                    stop:0.6 #080F1A,
                    stop:1 #05080D);
            }
            
            /* Стиль вкладок */
            QTabWidget::pane {
                border: 1px solid #1A2234;
                border-radius: 8px;
                background: rgba(10, 20, 40, 80);
            }
            
            QTabBar::tab {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #101A2C,
                    stop:1 #0A1220);
                color: #8892B0;
                padding: 8px 16px;
                margin: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                border: 1px solid #1A2234;
                border-bottom: none;
            }
            
            QTabBar::tab:selected {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1A2234,
                    stop:1 #0D1520);
                color: #FFFFFF;
                border: 1px solid #00FFCC;
                border-bottom: none;
            }
            
            QTabBar::tab:hover:!selected {
                background: #1A2A3A;
                border: 1px solid #2A4A6A;
                color: #E0E6ED;
            }
            
            /* Стиль групп */
            QGroupBox {
                font-weight: bold;
                border: 1px solid #1A2234;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 8px;
                background: rgba(5, 8, 13, 40);
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 0 6px;
                color: #00C8A5;
            }
            
            /* Стиль кнопок */
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
            
            QPushButton:pressed {
                background-color: #0A1220;
                border: 1px solid #00FFAA;
                color: #FFFFFF;
            }
            
            /* Стиль полей ввода */
            QLineEdit, QSpinBox {
                background-color: #101A2C;
                border: 1px solid #162238;
                border-radius: 4px;
                padding: 4px;
                padding-right: 20px;
                color: #FFFFFF;
            }
            
            QLineEdit:focus, QSpinBox:focus {
                border: 1px solid #00FFCC;
            }
            
            QLineEdit[text=""] {
                color: #6272A4;
            }
            
            /* Стиль для QSpinBox (без стрелок, ручной ввод) */
            QSpinBox {
                background-color: #101A2C;
                border: 1px solid #162238;
                border-radius: 4px;
                padding: 4px;
                color: #FFFFFF;
            }
            
            QSpinBox:focus {
                border: 1px solid #00FFCC;
            }
            
            QSpinBox::up-button, QSpinBox::down-button {
                width: 0px;
                height: 0px;
                subcontrol-origin: margin;
            }
            
            /* Стрелки через символы Unicode не работают — оставляем стандартные */
            
            /* Стиль выпадающих списков */
            QComboBox {
                background-color: #101A2C;
                border: 1px solid #1A2234;
                border-radius: 4px;
                padding: 4px;
                color: #FFFFFF;
            }
            
            QComboBox:focus {
                border: 1px solid #00FFCC;
            }
            
            QComboBox:hover:!focus {
                border: 1px solid #2A4A6A;
            }
            
            QComboBox QAbstractItemView {
                background-color: #101A2C;
                border: 1px solid #1A2234;
                color: #FFFFFF;
                selection-background-color: #162238;
                selection-color: #00FFCC;
            }
            
            /* Стиль радиокнопок */
            QRadioButton {
                color: #E0E6ED;
                spacing: 6px;
            }
            
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #162238;
                border-radius: 8px;
                background-color: #101A2C;
            }
            
            QRadioButton::indicator:hover {
                border: 1px solid #00C8A5;
            }
            
            QRadioButton::indicator:checked {
                border: 1px solid #00FFCC;
                background-color: #00C8A5;
            }
            
            /* Стиль чекбоксов */
            QCheckBox {
                color: #E0E6ED;
                spacing: 5px;
            }
            
            QCheckBox::indicator {
                width: 15px;
                height: 15px;
                border: 1px solid #25354C;
                border-radius: 3px;
                background-color: #101A2C;
            }
            
            QCheckBox::indicator:hover {
                border: 1px solid #00C8A5;
            }
            
            QCheckBox::indicator:checked {
                border: 1px solid #00FFCC;
                background-color: #00C8A5;
            }
            
            /* Стиль списков */
            QListWidget {
                background-color: #101A2C;
                border: 1px solid #1A2234;
                border-radius: 6px;
                color: #E0E6ED;
                outline: none;
            }
            
            QListWidget::item:selected {
                background-color: #1A3A5A;
                border-left: 3px solid #00FFCC;
                color: #FFFFFF;
            }
            
            QListWidget::item:hover {
                background-color: #1A2A3A;
            }
            
            /* Стиль лог-панели */
            QTextEdit {
                background-color: #0A0F18;
                border: 1px solid #1A2234;
                border-radius: 6px;
                color: #B8C7E7;
                font-family: 'Consolas', monospace;
            }
            
            /* Стиль статус-бара */
            QStatusBar {
                background-color: #0A0F18;
                color: #8892B0;
                border-top: 1px solid #1A2234;
            }
            
            /* Стиль для QMessageBox (всплывающие окна) */
            QMessageBox {
                background-color: #0D1520;
                color: #E0E6ED;
            }
            
            QMessageBox QPushButton {
                min-width: 80px;
            }
            
            /* Стиль для QInputDialog */
            QInputDialog {
                background-color: #0D1520;
                color: #E0E6ED;
            }
            
            /* Стиль для QDialog (диалоги) */
            QDialog {
                background-color: #0D1520;
            }
            
            /* Стиль для QProgressBar (VRAM) */
            QProgressBar {
                border: 1px solid #1A2234;
                border-radius: 4px;
                text-align: center;
                color: #FFFFFF;
                background-color: #101A2C;
            }

QToolTip {
                background-color: #0D1520;
                color: #E0E6ED;
                border: 1px solid #00FFCC;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9pt;
            }

            QComboBox QAbstractItemView {
                background-color: #101A2C;
                border: 1px solid #1A2234;
                color: #FFFFFF;
                selection-background-color: #1A3A5A;
                selection-color: #00FFCC;
                outline: none;
            }
        """)

        # Оставляем палитру для базовых элементов
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.WindowText, Qt.white)
        dark_palette.setColor(QPalette.Base, QColor(16, 26, 44))
        dark_palette.setColor(QPalette.AlternateBase, QColor(20, 30, 45))
        dark_palette.setColor(QPalette.ToolTipBase, QColor(30, 40, 55))
        dark_palette.setColor(QPalette.ToolTipText, Qt.white)
        dark_palette.setColor(QPalette.Text, Qt.white)
        dark_palette.setColor(QPalette.Button, QColor(30, 40, 55))
        dark_palette.setColor(QPalette.ButtonText, Qt.white)
        dark_palette.setColor(QPalette.BrightText, Qt.red)
        dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.Highlight, QColor(0, 170, 136))
        dark_palette.setColor(QPalette.HighlightedText, Qt.black)
        self.setPalette(dark_palette)

    def _dummy_tab(self, name):
        w = QWidget()
        w.setLayout(QVBoxLayout())
        w.layout().addWidget(QTextEdit(f"Вкладка «{name}» (будет реализована позже)"))
        return w

    def _on_tab_changed(self, index):
        """Вызывает refresh() у вкладки, если она поддерживает обновление."""
        tab = self.tabs.widget(index)
        if hasattr(tab, "refresh"):
            tab.refresh()
        self._update_status_bar()

    def _on_link_toggled(self, checked):
        """Связывает или развязывает слайдеры целевого FPS."""
        if checked:
            # Подключаем взаимную синхронизацию
            self.ai_scout_tab.target_fps_slider.valueChanged.connect(
                self.target_control_tab.set_target_fps
            )
            self.target_control_tab.target_fps_spin.valueChanged.connect(
                self.ai_scout_tab.set_target_fps
            )
            # Принудительно синхронизируем текущие значения: AI Scout → Управление
            self.target_control_tab.set_target_fps(
                self.ai_scout_tab.target_fps_slider.value()
            )
            self.log("Слайдеры целевого FPS связаны и синхронизированы.")
        else:
            try:
                self.ai_scout_tab.target_fps_slider.valueChanged.disconnect(
                    self.target_control_tab.set_target_fps
                )
                self.target_control_tab.target_fps_spin.valueChanged.disconnect(
                    self.ai_scout_tab.set_target_fps
                )
            except TypeError:
                pass
            self.log("Слайдеры работают независимо.")

    def _update_status_bar(self):
        """Обновляет статус-бар: GPU, VRAM, разрешение и герцовка монитора."""
        if not self.db:
            return
        profile_id = self.db.get_current_profile_id()
        if not profile_id:
            msg = "Профиль не выбран"
            self._status_bar_default_message = msg
            self.status_bar.showMessage(msg)
            return
        cursor = self.db.conn.cursor()
        cursor.execute(
            "SELECT gpu_name, vram_gb FROM hardware_profiles WHERE id=?", (profile_id,)
        )
        row = cursor.fetchone()
        if row:
            gpu, vram = row
            from settings import load_settings

            settings = load_settings()
            resolution = settings.get("monitor_resolution","?")
            hz = settings.get("monitor_hz","?")
            msg = f"  🖥  GPU: {gpu}   |   💾 VRAM: {vram} ГБ   |   📺 {resolution} @ {hz} Гц"
            self._status_bar_default_message = msg
            self.status_bar.showMessage(msg)
            # Цветной стиль статус-бара
            self.status_bar.setStyleSheet("""
                QStatusBar {
                    background-color: #080E18;
                    color: #00FFCC;
                    border-top: 1px solid #1A3A5A;
                    font-size: 9pt;
                    padding-left: 4px;
                }
            """)
        else:
            msg = "Нет данных GPU"
            self._status_bar_default_message = msg
            self.status_bar.showMessage(msg)

    def log(self, message: str, bold=False, color=None):
        """Форматированный вывод в лог-панель."""
        if not hasattr(self, "log_widget"):
            print(message)
            return
        if bold or color:
            style = ""
            if bold:
                style += "font-weight:bold;"
            if color:
                style += f"color:{color};"
            html = f"<span style='{style}'>{message}</span>"
            self.log_widget.append(html)
        else:
            self.log_widget.append(message)

    def _toggle_log_expanded(self):
        """Сворачивает/разворачивает логи."""
        self._log_expanded = not self._log_expanded
        if self._log_expanded:
            self.toggle_log_btn.setText("\u25BC")  # ▼
            self.toggle_log_btn.setToolTip("Свернуть логи (нажмите, чтобы скрыть)")
            self.log_title.setText("\u25B8 Лог")  # ▸
            self.log_container_layout.setContentsMargins(0, 0, 0, 0)
            self.log_widget.setMaximumHeight(130)
        else:
            self.toggle_log_btn.setText("\u25B6")  # ▶
            self.toggle_log_btn.setToolTip("Развернуть логи (нажмите, чтобы показать)")
            self.log_title.setText("\u25A1 Лог")  # □
            self.log_container_layout.setContentsMargins(0, 0, 0, 0)
            self.log_widget.setMaximumHeight(0)

    def toggle_window(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.toggle_window()

    def delete_profile_dialog(self):
        """Диалог выбора и удаления профиля оборудования."""
        if not self.db:
            return
        profiles = self.db.get_all_profiles()
        if not profiles:
            QMessageBox.information(self, "Удаление профиля","Нет ни одного профиля.")
            return
        # Составляем список для выбора
        items = []
        for p in profiles:
            pid, cpu, gpu, ram, vram, _ = p
            gpu_str = gpu if gpu else "GPU не определён"
            items.append(f"ID {pid}: {cpu} | {gpu_str} | RAM {ram}")
        choice, ok = QInputDialog.getItem(
            self, "Выберите профиль для удаления","Профиль:", items, 0, False
        )
        if not ok or not choice:
            return
        idx = items.index(choice)
        profile_id = profiles[idx][0]
        # Защита от удаления текущего профиля, если он единственный
        current_id = self.db.get_current_profile_id()
        if profile_id == current_id and len(profiles) == 1:
            QMessageBox.warning(self, "Ошибка","Нельзя удалить единственный профиль.")
            return
        # Предупреждение
        reply = QMessageBox.warning(
            self,
            "Подтверждение удаления",
            f"Профиль ID={profile_id} будет удалён навсегда!\n"
            "Все связанные игры и AI‑ответы исчезнут без возможности восстановления.\n\n"
            "Продолжить?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        # Удаляем
        if self.db.delete_profile(profile_id):
            self.log(f"Профиль ID={profile_id} удалён.")
            # Если удалили текущий профиль, то назначился другой; нужно обновить все вкладки
            # Принудительно обновим интерфейс
            for i in range(self.tabs.count()):
                tab = self.tabs.widget(i)
                if hasattr(tab, "refresh"):
                    tab.refresh()
            self._update_status_bar()
        else:
            QMessageBox.warning(self, "Ошибка","Не удалось удалить профиль.")

    def show_about_dialog(self):
        """Показывает окно с описанием программы."""
        QMessageBox.about(
            self,
            "О программе FPS Targeter",
            "🎮 **FPS Targeter v3.1** — инженерный пульт для геймеров.\n\n"
            "📌 **Назначение:**\n"
            "• Расчёт оптимальных настроек графики под целевой FPS.\n"
            "• Контроль заполнения видеопамяти (VRAM Guard).\n"
            "• Получение советов от трёх AI-провайдеров (OpenRouter, GroqCloud, Gemini).\n\n"
            "🔧 **Основные функции:**\n"
            "• Автоопределение железа (CPU, GPU, ОЗУ, VRAM, герцовка монитора).\n"
            "• Калибровка: замеры FPS для 6 пресетов, история замеров, ручной ввод FPS (Ctrl+Shift+F).\n"
            "• AI Scout: три AI-провайдера, настройка моделей, копирование curl команд для просмотра доступных моделей.\n"
            "• Управление: математический подбор пресета, запас производительности (CPU/GPU), дуговой индикатор VRAM.\n"
            "• Оверлей: показ системной информации и AI-рекомендаций поверх игр, настройка позиции и цветов, автоскрытие.\n"
            "• Трекер игр: автоматическое появление оверлея при запуске отслеживаемых .exe файлов.\n"
            "• Профили мониторов: сохранение и переключение разрешений и герцовки.\n"
            "• Таблица производительности: редактирование баллов CPU/GPU для локальной калибровки.\n"
            "• Системные требования: база игр, парсинг из Steam (Ctrl+Shift+R), быстрая проверка.\n"
            "• Импорт из Steam: автоматическое добавление установленных игр в профиль.\n"
            "• Экспорт/импорт профиля: бэкап всех данных в JSON.\n"
            "• Облачная синхронизация: полный бэкап на Яндекс.Диск (ZIP-архив).\n\n"
            "🎮 **Глобальные горячие клавиши:**\n"
            "• Alt+F — показать/скрыть главное окно.\n"
            "• Ctrl+Shift+R — быстрое добавление системных требований из буфера обмена.\n"
            "• Ctrl+Shift+F — ручной ввод текущего FPS в калибровку.\n\n"
            "© 2026 Alexey Smolin\n"
            "Все права защищены\n"
            "Версия: 3.1 (стабильный релиз)",
        )

    def open_monitor_profiles_dialog(self):
        """Открывает диалог управления профилями мониторов."""
        self.log("DEBUG: открытие профилей мониторов...")
        from settings import load_settings
        from monitor_profiles_dialog import MonitorProfilesDialog

        settings = load_settings()
        self.log(
            f"DEBUG: настройки загружены, профилей: {len(settings.get('monitor_profiles', []))}"
        )

        def on_profiles_saved():
            """Callback без аргументов - просто обновляем UI из текущих settings."""
            # Перезагружаем settings из файла, так как диалог уже сохранил их
            from settings import load_settings

            updated_settings = load_settings()
            self._update_status_bar()
            if hasattr(self, "ai_scout_tab"):
                current_hz = updated_settings.get("monitor_hz", 60)
                if hasattr(self.ai_scout_tab, "monitor_hz_slider"):
                    self.ai_scout_tab.monitor_hz_slider.setValue(current_hz)
            self.log("Профили мониторов обновлены.")

        try:
            dialog = MonitorProfilesDialog(settings, on_profiles_saved, self)
            self.log("DEBUG: диалог создан, показываем...")
            result = dialog.exec()
            self.log(f"DEBUG: диалог закрыт, result={result}")
        except Exception as e:
            self.log(f"DEBUG: ОШИБКА - {e}")
            import traceback

            traceback.print_exc()

    def open_benchmark_editor(self):
        """Открывает редактор таблицы производительности."""
        from benchmark_editor import BenchmarkEditor

        dialog = BenchmarkEditor(self)
        if dialog.exec():
            # После закрытия редактора можно обновить статус-бар (опционально)
            self._update_status_bar()
            self.log("Таблица производительности обновлена.")

    def import_steam_games(self):
        """Открывает диалог импорта игр из Steam."""
        from steam_importer import SteamImportDialog
        from PySide6.QtWidgets import QMessageBox

        profile_id = self.db.get_current_profile_id()
        if not profile_id:
            QMessageBox.warning(self, "Ошибка","Нет активного профиля оборудования.")
            return

        dialog = SteamImportDialog(self.db, profile_id, self)
        if dialog.exec():
            # Обновляем список игр во всех вкладках
            self.calibration_tab.refresh()
            self.ai_scout_tab.refresh()
            self.target_control_tab.refresh()
            self.log("Игры из Steam импортированы в профиль.")

    def export_profile(self):
        """Экспорт профиля: либо в локальный JSON, либо в облако."""
        # Диалог выбора
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Экспорт профиля")
        msg_box.setText("Выберите, куда сохранить резервную копию профиля:")
        msg_box.setMinimumWidth(300)
        local_btn = msg_box.addButton("Сохранить\nлокально", QMessageBox.ActionRole)
        cloud_btn = msg_box.addButton("Отправить\nв облако", QMessageBox.ActionRole)
        msg_box.addButton("Отмена", QMessageBox.RejectRole)
        msg_box.exec()
        clicked = msg_box.clickedButton()

        if clicked == local_btn:
            # --- Локальное сохранение ---
            from PySide6.QtWidgets import QFileDialog
            from datetime import datetime

            profile_id = self.db.get_current_profile_id()
            if not profile_id:
                QMessageBox.warning(self, "Ошибка","Нет активного профиля для экспорта.")
                return

            data = self.db.export_profile_to_dict(profile_id)
            if not data:
                QMessageBox.warning(self, "Ошибка","Не удалось получить данные профиля.")
                return

            data["export_info"] = {
                "export_date": datetime.now().isoformat(),
                "profile_id": profile_id,
                "version":"1.0",
            }

            file_path, _ = QFileDialog.getSaveFileName(
                self, "Сохранить профиль","","JSON файлы (*.json)"
            )
            if not file_path:
                return

            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                self.log(f"Профиль экспортирован в {file_path}")
                QMessageBox.information(self, "Успех", f"Профиль сохранён в:\n{file_path}")
            except Exception as e:
                self.log(f"Ошибка экспорта: {e}")
                QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить файл:\n{e}")

        elif clicked == cloud_btn:
            # --- Сохранение в облако ---
            from settings import load_settings
            cloud_settings = load_settings()
            # Проверяем только наличие токена, флаг cloud_sync_enabled игнорируем
            if not cloud_settings.get("cloud_access_token"):
                QMessageBox.warning(self, "Ошибка", "Токен доступа отсутствует. Пожалуйста, настройте облако.")
                return

            from cloud_sync import SyncThread
            self.cloud_thread = SyncThread(self.db, cloud_settings, action="upload")
            self.cloud_thread.progress.connect(lambda msg: self.log(f"[Облако] {msg}"))
            self.cloud_thread.finished.connect(self._on_cloud_sync_finished)
            self.cloud_thread.start()
            self.log("[Облако] Запущена загрузка профиля в облако...")

    def import_profile(self):
        """Импорт профиля: либо из локального JSON, либо из облака."""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Импорт профиля")
        msg_box.setText("Выберите, откуда восстановить резервную копию профиля:")
        msg_box.setMinimumWidth(300)
        local_btn = msg_box.addButton("Из локального\nфайла", QMessageBox.ActionRole)
        cloud_btn = msg_box.addButton("Из облака", QMessageBox.ActionRole)
        msg_box.addButton("Отмена", QMessageBox.RejectRole)
        msg_box.exec()
        clicked = msg_box.clickedButton()

        if clicked == local_btn:
            # --- Импорт из локального файла ---
            from PySide6.QtWidgets import QFileDialog
            import json

            profile_id = self.db.get_current_profile_id()
            if not profile_id:
                QMessageBox.warning(self, "Ошибка","Нет активного профиля для импорта.")
                return

            file_path, _ = QFileDialog.getOpenFileName(
                self, "Загрузить профиль","","JSON файлы (*.json)"
            )
            if not file_path:
                return

            reply = QMessageBox.question(
                self,
                "Подтверждение",
                f"Импорт заменит все данные в текущем профиле (игры, замеры, историю).\n"
                f"Текущий профиль ID={profile_id}\n\nПродолжить?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "profile" not in data:
                    QMessageBox.warning(self, "Ошибка","Неверный формат файла.")
                    return
                new_id = self.db.import_profile_from_dict(data, target_profile_id=profile_id, set_as_current=True)
                if not new_id:
                    QMessageBox.warning(self, "Ошибка","Не удалось импортировать профиль.")
                    return
                self._refresh_all_after_import()
                self.log(f"Профиль импортирован из {file_path}")
                QMessageBox.information(self, "Успех","Профиль успешно импортирован.")
            except Exception as e:
                self.log(f"Ошибка импорта: {e}")
                QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить файл:\n{e}")

        elif clicked == cloud_btn:
            # --- Импорт из облака ---
            from settings import load_settings
            cloud_settings = load_settings()
            # Проверяем только наличие токена, флаг cloud_sync_enabled игнорируем
            if not cloud_settings.get("cloud_access_token"):
                QMessageBox.warning(self, "Ошибка", "Токен доступа отсутствует. Пожалуйста, настройте облако.")
                return

            reply = QMessageBox.question(
                self,
                "Восстановление из облака",
                "Вы уверены, что хотите восстановить данные из облака? Текущий профиль будет полностью заменен.",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

            from cloud_sync import SyncThread
            self.cloud_thread = SyncThread(self.db, cloud_settings, action="download")
            self.cloud_thread.progress.connect(lambda msg: self.log(f"[Облако] {msg}"))
            self.cloud_thread.finished.connect(self._on_cloud_sync_finished)
            self.cloud_thread.start()
            self.log("[Облако] Запущена загрузка профиля из облака...")

    def _refresh_all_after_import(self):
        """Обновляет все вкладки и статус-бар после импорта профиля."""
        self._update_status_bar()
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if hasattr(tab, "refresh"):
                tab.refresh()
        if hasattr(self.calibration_tab, "_refresh_game_list"):
            self.calibration_tab._refresh_game_list()
            self.calibration_tab._load_preset_data()

        # Обновляем API-ключи и настройки в AI Scout
        from settings import load_settings
        new_settings = load_settings()
        self.ai_scout_tab.settings = new_settings

        # Поля API-ключей
        self.ai_scout_tab.openrouter_token_edit.blockSignals(True)
        self.ai_scout_tab.openrouter_token_edit.setText(new_settings.get("openrouter_api_key", ""))
        self.ai_scout_tab.openrouter_token_edit.blockSignals(False)

        self.ai_scout_tab.groq_token_edit.blockSignals(True)
        self.ai_scout_tab.groq_token_edit.setText(new_settings.get("groq_api_key", ""))
        self.ai_scout_tab.groq_token_edit.blockSignals(False)

        self.ai_scout_tab.gemini_key_edit.blockSignals(True)
        self.ai_scout_tab.gemini_key_edit.setText(new_settings.get("gemini_api_key", ""))
        self.ai_scout_tab.gemini_key_edit.blockSignals(False)

        # Эмулируем ручной ввод для внутренней синхронизации
        self.ai_scout_tab.gemini_key_edit.textEdited.emit(self.ai_scout_tab.gemini_key_edit.text())
        self.ai_scout_tab.openrouter_token_edit.textEdited.emit(self.ai_scout_tab.openrouter_token_edit.text())
        self.ai_scout_tab.groq_token_edit.textEdited.emit(self.ai_scout_tab.groq_token_edit.text())

        if hasattr(self.ai_scout_tab, "_update_provider_keys"):
            self.ai_scout_tab._update_provider_keys()
        if hasattr(self.ai_scout_tab, "_load_response_for_current_model"):
            self.ai_scout_tab._load_response_for_current_model()

    def open_quick_add_requirements(self):
        """Быстрое добавление системных требований из буфера обмена (Ctrl+Shift+R)."""
        import logging

        logger = logging.getLogger(__name__)
        logger.info("open_quick_add_requirements: вызван метод")

        from PySide6.QtWidgets import QApplication, QMessageBox
        from game_requirements import (
            AddEditRequirementDialog,
            parse_steam_requirements_text,
        )
        from game_requirements import RequirementsManager

        # Получаем текст из буфера обмена
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        logger.info(
            f"open_quick_add_requirements: длина текста из буфера = {len(text)} символов"
        )

        if not text:
            self.log(
                "Буфер обмена пуст. Скопируйте системные требования из Steam и нажмите Ctrl+Shift+R."
            )
            logger.warning("open_quick_add_requirements: буфер обмена пуст")
            QMessageBox.information(
                self,
                "Нет данных",
                "Буфер обмена пуст.\n\nСкопируйте системные требования из Steam и нажмите Ctrl+Shift+R снова.",
            )
            return

        self.log("Обработка Ctrl+Shift+R: парсинг требований из буфера обмена...")
        logger.info("open_quick_add_requirements: начинаем парсинг")

        # Парсим требования
        parsed = parse_steam_requirements_text(text)
        logger.info(f"open_quick_add_requirements: результат парсинга = {parsed}")

        # Проверяем, удалось ли что-то извлечь
        if (
            not parsed.get("min_cpu")
            and not parsed.get("min_gpu")
            and parsed.get("min_ram_gb") == 0
        ):
            self.log("Не удалось распознать системные требования в буфере обмена.")
            logger.warning(
                "open_quick_add_requirements: не удалось распознать требования"
            )
            QMessageBox.warning(
                self,
                "Ошибка парсинга",
                "Не удалось распознать системные требования в буфере обмена.\n\n"
                "Убедитесь, что скопирован блок с требованиями (Процессор, Видеокарта, ОЗУ).",
            )
            return

        # Открываем диалог с предзаполненными полями
        logger.info(
            "open_quick_add_requirements: создаём диалог AddEditRequirementDialog"
        )
        dialog = AddEditRequirementDialog()

        # Заполняем поля
        dialog.cpu_edit.setText(parsed.get("min_cpu",""))
        dialog.gpu_edit.setText(parsed.get("min_gpu",""))
        dialog.ram_spin.setValue(parsed.get("min_ram_gb", 0))
        dialog.vram_spin.setValue(parsed.get("min_vram_gb", 0))
        dialog.rt_check.setChecked(parsed.get("requires_hardware_rt", False))

        # Очищаем поле названия игры и устанавливаем фокус на него
        dialog.game_edit.clear()
        dialog.game_edit.setFocus()
        dialog.game_edit.setPlaceholderText(
            "Введите название игры (например, Cyberpunk 2077)"
        )

        # Увеличиваем размер диалога для удобства
        dialog.resize(650, 500)

        logger.info("open_quick_add_requirements: запускаем диалог")
        if dialog.exec():
            # Сохраняем в базу требований
            manager = RequirementsManager()
            game_name = dialog.game_name
            logger.info(
                f"open_quick_add_requirements: получено название игры = '{game_name}'"
            )
            if not game_name:
                logger.warning("open_quick_add_requirements: название игры пустое")
                QMessageBox.warning(
                    self, "Ошибка","Название игры не может быть пустым."
                )
                return
            manager.add_or_update(game_name, dialog.reqs)
            self.log(f"Системные требования для '{game_name}' добавлены в базу.")
            logger.info(
                f"open_quick_add_requirements: требования для '{game_name}' сохранены"
            )
            QMessageBox.information(
                self, "Готово", f"Требования для '{game_name}' сохранены."
            )
        else:
            logger.info("open_quick_add_requirements: диалог закрыт без сохранения")

    def on_manual_fps_request(self):
        """Обработчик Ctrl+Shift+F - ручной ввод FPS для калибровки."""
        from PySide6.QtWidgets import QInputDialog, QMessageBox

        # Проверяем, что активна вкладка калибровки и выбрана игра
        current_tab = self.tabs.currentWidget()
        if current_tab != self.calibration_tab:
            QMessageBox.information(
                self,
                "Ручной ввод FPS",
                "Переключитесь на вкладку «Калибровка» и выберите игру и пресет.",
            )
            return

        # Проверяем, выбрана ли игра
        game_item = self.calibration_tab.game_list.currentItem()
        if not game_item:
            QMessageBox.warning(self, "Ошибка","Сначала выберите игру в списке.")
            return

        game_name = game_item.data(Qt.UserRole)
        preset = self.calibration_tab.preset_combo.currentText()

        # Диалог ввода FPS
        fps_value, ok = QInputDialog.getInt(
            self,
            "Ручной ввод FPS",
            f"Игра: {game_name}\nПресет: {preset}\n\n"
            f"Введите текущий FPS из RTSS/Steam оверлея:",
            60,  # значение по умолчанию
            1,  # минимум
            999,  # максимум
        )

        if ok and fps_value > 0:
            # Сохраняем замер
            profile_id = self.db.get_current_profile_id()
            if profile_id:
                # Получаем существующие замеры для этого пресета
                existing = self.db.get_presets_for_game(profile_id, game_name)
                existing_fps = ""
                for p, fps_str in existing:
                    if p == preset and fps_str:
                        existing_fps = fps_str
                        break

                # Добавляем новый замер (до 3 значений)
                if existing_fps:
                    values = [
                        int(v.strip()) for v in existing_fps.split(",") if v.strip()
                    ]
                    if len(values) >= 3:
                        # Сдвигаем: удаляем первый, добавляем новый
                        values.pop(0)
                    values.append(fps_value)
                    new_fps_str = ",".join(str(v) for v in values)
                else:
                    new_fps_str = str(fps_value)

                self.db.save_fps(profile_id, game_name, preset, new_fps_str)
                self.log(f"📊 Ручной ввод: {game_name} / {preset} -> {fps_value} FPS")

                # Обновляем интерфейс
                self.calibration_tab._load_preset_data()
                self.calibration_tab._refresh_game_list()

                QMessageBox.information(
                    self,
                    "Готово",
                    f"Замер FPS = {fps_value} сохранён для\n{game_name} / {preset}",
                )
        else:
            self.log("Ручной ввод FPS отменён.")

    def cloud_sync(self, auto=False):
        """Запускает синхронизацию с Яндекс.Диском.
        auto=True – автоматическая синхронизация (без диалога)
        auto=False – ручная синхронизация (с диалогом выбора)
        """
        from settings import load_settings
        from cloud_sync import SyncThread

        settings = load_settings()

        # Для ручной синхронизации проверяем только наличие токена
        # Для автосинхронизации проверяем и токен, и флаг
        if auto and not settings.get("cloud_sync_enabled", False):
            return

        token = settings.get("cloud_access_token")
        if not token:
            if not auto:
                QMessageBox.warning(
                    self,
                    "Ошибка",
                    "Токен доступа отсутствует.\n"
                    "Нажмите «Настройки облака» и выполните авторизацию.",
                )
            return

        token = settings.get("cloud_access_token")
        if not token:
            if not auto:
                QMessageBox.warning(
                    self,
                    "Ошибка",
                    "Токен доступа отсутствует. Выполните авторизацию в настройках.",
                )
            return

        if auto:
            action = "auto"
            self.log("[Облако] Автосинхронизация...")
        else:
            # Создаём диалог с информативными кнопками
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Синхронизация")
            msg_box.setText("Выберите действие:")
            msg_box.setInformativeText(
                "📤 Загрузить профиль в облако (сохранить текущие данные)\n"
                "📥 Скачать профиль из облака (восстановить из резервной копии)"
            )
            upload_btn = msg_box.addButton("📤 Загрузить", QMessageBox.AcceptRole)
            download_btn = msg_box.addButton("📥 Скачать", QMessageBox.ActionRole)
            msg_box.addButton("Отмена", QMessageBox.RejectRole)

            msg_box.exec()

            clicked = msg_box.clickedButton()
            if clicked == upload_btn:
                action = "upload"
                self.log("[Облако] Запущена загрузка профиля...")
            elif clicked == download_btn:
                action = "download"
                self.log("[Облако] Запущена загрузка профиля из облака...")
            else:
                self.log("[Облако] Синхронизация отменена")
                return

        self.cloud_thread = SyncThread(self.db, settings, action=action)
        self.cloud_thread.progress.connect(lambda msg: self.log(f"[Облако] {msg}"))
        self.cloud_thread.finished.connect(self._on_cloud_sync_finished)
        self.cloud_thread.start()

    def _on_cloud_sync_finished(self, success, message):
        if success:
            if "|RELOAD_UI" in message:
                message = message.replace("|RELOAD_UI", "")
                self.log("[Облако] Восстановление данных завершено, обновляем интерфейс...")
                self._refresh_all_after_import()
                QMessageBox.information(self, "Восстановление", "Профиль успешно восстановлен из облака.\nИнтерфейс обновлён.")
            else:
                self.log(f"[Облако] {message}")
                QMessageBox.information(self, "Синхронизация", message)
        else:
            self.log(f"[Облако] Ошибка: {message}")
            QMessageBox.warning(self, "Ошибка синхронизации", message)

    def cloud_settings(self):
        """Настройки облачной синхронизации (только токен)."""
        from settings import load_settings, save_settings
        from cloud_sync import get_token_url
        from PySide6.QtWidgets import (
            QDialog,
            QVBoxLayout,
            QLabel,
            QPushButton,
            QLineEdit,
            QGroupBox,
            QCheckBox,
        )

        settings = load_settings()

        dialog = QDialog(self)
        dialog.setWindowTitle("Настройки облачной синхронизации")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)

        # Чекбокс включения синхронизации
        enabled_cb = QCheckBox(
            "Включить автоматическую синхронизацию при запуске и закрытии"
        )
        enabled_cb.setChecked(settings.get("cloud_sync_enabled", False))
        layout.addWidget(enabled_cb)

        # Группа токена
        token_group = QGroupBox("Токен доступа Яндекс.Диск")
        token_layout = QVBoxLayout(token_group)

        token_edit = QLineEdit()
        token_edit.setPlaceholderText("Вставьте сюда токен доступа")
        token_edit.setText(settings.get("cloud_access_token",""))
        token_layout.addWidget(token_edit)

        # Кнопка получения токена
        get_token_btn = QPushButton("🔑 Получить токен")
        get_token_btn.clicked.connect(lambda: webbrowser.open(get_token_url()))
        token_layout.addWidget(get_token_btn)

        info_label = QLabel(
            "1. Нажмите «Получить токен»\n"
            "2. Авторизуйтесь под своим Яндекс ID\n"
            "3. Скопируйте токен из адресной строки (часть после #access_token=)\n"
            "4. Вставьте токен в поле выше"
        )
        info_label.setStyleSheet("color: #888888; font-size: 11px;")
        token_layout.addWidget(info_label)

        layout.addWidget(token_group)

        # Путь к папке
        layout.addWidget(QLabel("Папка на Яндекс.Диске:"))
        folder_edit = QLineEdit(settings.get("cloud_folder","FPS_Targeter_Backup"))
        folder_edit.setPlaceholderText("Папка на Диске для хранения")
        layout.addWidget(folder_edit)

        # Кнопки
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Сохранить")
        cancel_btn = QPushButton("Отмена")
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        def save():
            settings["cloud_sync_enabled"] = enabled_cb.isChecked()
            settings["cloud_access_token"] = token_edit.text().strip()
            settings["cloud_folder"] = folder_edit.text().strip()
            save_settings(settings)
            self.log("Настройки облака сохранены")
            dialog.accept()

        def cancel():
            dialog.reject()

        save_btn.clicked.connect(save)
        cancel_btn.clicked.connect(cancel)

        dialog.exec()

    def open_tracked_games_dialog(self):
        """Открывает диалог управления отслеживанием игр."""
        from settings import load_settings, save_settings
        from tracked_games_dialog import TrackedGamesDialog

        settings = load_settings()

        def on_tracked_games_saved(new_settings):
            save_settings(new_settings)
            # Перезапускаем трекер, если оверлей активен
            if hasattr(self, "monitor_checkbox") and self.monitor_checkbox.isChecked():
                self._stop_game_tracker()
                self._start_game_tracker()
            self.log("Список отслеживаемых игр обновлён.")

        dialog = TrackedGamesDialog(settings, on_tracked_games_saved, self)
        dialog.exec()

    def quit_app(self):
        # Останавливаем трекер игр
        self._stop_game_tracker()

        # # Автосинхронизация при закрытии (ОТКЛЮЧЕНО)
        # from settings import load_settings
        # sync_settings = load_settings()
        # if sync_settings.get("cloud_sync_enabled", False) and sync_settings.get(
        #     "cloud_access_token"
        # ):
        #     self.cloud_sync(auto=True)
        #     # Дадим время на синхронизацию
        #     import time
        #     time.sleep(1)

        self.ai_scout_tab.cleanup()
        self.tray_icon.hide()
        QApplication.quit()

    def closeEvent(self, event):
        self.ai_scout_tab.cleanup()
        self._destroy_overlay()
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "FPS Targeter",
            "Приложение свёрнуто в трей. Нажмите Alt+F для восстановления.",
            QSystemTrayIcon.Information,
            2000,
        )

    def changeEvent(self, event):
        """Перехватывает сворачивание окна и отправляет в трей вместо панели задач."""
        from PySide6.QtCore import QEvent

        if event.type() == QEvent.WindowStateChange:
            if self.isMinimized():
                event.ignore()
                self.hide()
                self.tray_icon.showMessage(
                    "FPS Targeter",
                    "Приложение свёрнуто в трей. Нажмите Alt+F для восстановления.",
                    QSystemTrayIcon.Information,
                    2000,
                )
            else:
                super().changeEvent(event)
        else:
            super().changeEvent(event)
