import json
import subprocess
import psutil
import pynvml
import logging
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QSlider,
    QPushButton,
    QHBoxLayout,
    QApplication,
    QSizePolicy,
    QComboBox,
    QSpinBox,
    QMessageBox,
)
from PySide6.QtCore import Qt, QTimer

logger = logging.getLogger("Overlay")


class OverlayWindow(QWidget):
    def __init__(self, settings=None, games_list=None, db=None):
        super().__init__(parent=None)
        self.settings = (
            settings
            if settings
            else {
                "x": 0.5,
                "y": 0.5,
                "scale": 1.0,
                "color": "#00FF00",
                "auto_hide_seconds": 0,
                "bg_color": "#000000",
                "bg_alpha": 180,
            }
        )
        self.games_list = games_list or []
        self.db = db
        self._ai_recommendation = ""
        self._auto_hide_timer = QTimer()
        self._current_game = None  # для хранения текущей игры
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self.hide)

        self.setWindowFlags(
            Qt.WindowStaysOnTopHint
            | Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self.setMinimumSize(0, 0)

        self.label = QLabel("Загрузка...")
        self.label.setWordWrap(True)
        self.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.label.setMinimumSize(0, 0)

        self._apply_style()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.label)
        self.setLayout(layout)

        # Загружаем сохранённую позицию
        self._apply_saved_position()
        self.update_font(int(14 * self.settings.get("scale", 1.0)))
        self.resize(self.label.sizeHint())

        try:
            pynvml.nvmlInit()
            self.nvml_ready = True
            logger.info("Оверлей: NVML инициализирован успешно.")
        except Exception as e:
            self.nvml_ready = False
            logger.warning(f"Оверлей: NVML не инициализирован: {e}")

        self._init_rtss()  # Вызов заглушки

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_data)
        self.timer.start(1000)
        self.hide()  # Оверлей должен быть скрыт до появления игры
        logger.info(
            "Оверлей создан, таймер обновления запущен (интервал 1 сек). Оверлей скрыт до появления игры."
        )

    def move_to(self, x, y):
        """Перемещает оверлей на указанные координаты экрана."""
        self.move(x, y)
        self.settings["x"] = x
        self.settings["y"] = y
        self.save_settings()

    def update_position_from_settings(self):
        """Обновляет позицию оверлея из сохранённых настроек."""
        self._apply_initial_position()

    def set_game_pid(self, pid):
        """Устанавливает PID текущей игры для RTSS (заглушка, RTSS отключён)."""
        self._game_pid = pid
        # RTSS отключён из-за 64-bit Python
        pass

    def _init_rtss(self):
        """Инициализация RTSS (заглушка)."""
        self._rtss = None
        logger.info("RTSS отключён (32-bit библиотека несовместима с 64-bit Python)")

    def _get_fps_from_rtss(self):
        """Получение FPS из RTSS (заглушка)."""
        return None, None

    def show_safe(self):
        """Потокобезопасный показ оверлея."""
        self.show()

    def hide_safe(self):
        """Потокобезопасное скрытие оверлея."""
        self.hide()

    def set_current_game(self, game_name):
        """Устанавливает текущую игру для AI-рекомендаций."""
        self._current_game = game_name

    def _apply_style(self):
        color = self.settings.get("color", "#00FF00")
        bg_color = self.settings.get("bg_color", "#000000")
        bg_alpha = self.settings.get("bg_alpha", 180)
        self.label.setStyleSheet(f"""
            background-color: rgba({int(bg_color[1:3], 16)}, {int(bg_color[3:5], 16)}, {int(bg_color[5:7], 16)}, {bg_alpha});
            color: {color};
            font-weight: bold;
            padding: 4px;
            border-radius: 4px;
            border: 1px solid #333;
        """)

    def _apply_saved_position(self):
        """Загружает сохранённую позицию или ставит оверлей в центр."""
        nx = self.settings.get("x", 0.5)
        ny = self.settings.get("y", 0.5)

        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.x() + int(nx * (screen.width() - self.width()))
        y = screen.y() + int(ny * (screen.height() - self.height()))

        # Ограничиваем, чтобы не вылезал за экран
        x = max(screen.x(), min(screen.x() + screen.width() - self.width(), x))
        y = max(screen.y(), min(screen.y() + screen.height() - self.height(), y))

        self.move(x, y)
        logger.info(f"Оверлей: загружена позиция ({x}, {y})")

    def _get_ai_recommendation(self):
        """Получает последний AI-ответ для текущей игры."""
        if not self.db:
            return ""

        # Получаем список игр из калибровки
        games = []
        if self.games_list:
            # Если games_list - это QListWidget, извлекаем элементы
            if hasattr(self.games_list, "count") and hasattr(self.games_list, "item"):
                for i in range(self.games_list.count()):
                    item = self.games_list.item(i)
                    if item:
                        games.append(item.text())
            elif isinstance(self.games_list, list):
                games = self.games_list

        if not games:
            return ""

        # Берём первую игру из списка (можно улучшить позже)
        current_game = games[0] if games else None

        if current_game:
            profile_id = self.db.get_current_profile_id()
            if profile_id:
                response = self.db.get_ai_response_for_game(
                    profile_id, current_game, "Gemini"
                )
                if response:
                    # Обрезаем до 200 символов
                    return response[:200] + ("..." if len(response) > 200 else "")
        return ""

    def _refresh_data(self):
        # Не обновляем, если оверлей скрыт
        if not self.isVisible():
            return
        try:
            # RTSS отключён (64-bit Python), всегда показываем подсказку
            fps_str = "— (нажмите Ctrl+Shift+F для ввода)"

            cpu_name = self._get_cpu_name()
            cpu_usage = psutil.cpu_percent(interval=None)
            cpu_temp = self._get_cpu_temp()

            ram = psutil.virtual_memory()
            ram_used = (ram.total - ram.available) / (1024**3)
            ram_total = ram.total / (1024**3)

            gpu_name = "N/A"
            vram_used = vram_total = 0
            gpu_temp = "No Sensor"
            hotspot_temp = "No Sensor"
            if self.nvml_ready:
                try:
                    handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                    gpu_name = pynvml.nvmlDeviceGetName(handle)
                    mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    vram_used = mem.used / (1024**3)
                    vram_total = mem.total / (1024**3)
                    gpu_temp = pynvml.nvmlDeviceGetTemperature(
                        handle, pynvml.NVML_TEMPERATURE_GPU
                    )
                    try:
                        hotspot_temp = pynvml.nvmlDeviceGetTemperature(
                            handle, pynvml.NVML_TEMPERATURE_GPU_HOTSPOT
                        )
                    except Exception:
                        hotspot_temp = "No Sensor"
                except Exception:
                    pass

            text = (
                f"CPU: {cpu_name} ({cpu_usage}%) | {cpu_temp}°C\n"
                f"RAM: {ram_used:.1f} / {ram_total:.1f} GB\n"
                f"GPU: {gpu_name} | VRAM: {vram_used:.1f} / {vram_total:.1f} GB\n"
                f"Temp: {gpu_temp}°C / Hotspot: {hotspot_temp}°C\n"
                f"FPS: {fps_str}"
            )

            # Добавляем AI-рекомендацию, если есть
            ai_rec = self._get_ai_recommendation()
            if ai_rec:
                text += f"\n\n💡 AI: {ai_rec}"

            self.label.setText(text)

            # Принудительный adjustSize для исправления бага "CPU:" при первом запуске
            self.label.adjustSize()
            self.resize(self.label.sizeHint())

            # Автоскрытие
            auto_hide = self.settings.get("auto_hide_seconds", 0)
            if auto_hide > 0:
                self._auto_hide_timer.start(auto_hide * 1000)

        except Exception as e:
            logger.error(f"Оверлей: ошибка при обновлении данных: {e}")
            self.label.setText(f"Ошибка:\n{str(e)}")
            self.label.adjustSize()
            self.resize(self.label.sizeHint())

    def _get_cpu_name(self):
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            winreg.CloseKey(key)
            return name.strip()
        except Exception:
            import platform

            return platform.processor() or "CPU"

    def _get_cpu_temp(self):
        # Флаг для Windows, чтобы не создавать консольное окно
        CREATE_NO_WINDOW = 0x08000000
        try:
            out = subprocess.check_output(
                [
                    "wmic",
                    "/namespace:\\\\root\\wmi",
                    "PATH",
                    "MSAcpi_ThermalZoneTemperature",
                    "get",
                    "CurrentTemperature",
                ],
                timeout=2,
                text=True,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,  # ← КЛЮЧЕВОЕ ДОБАВЛЕНИЕ
            )
            for line in out.splitlines():
                if line.strip().isdigit():
                    return round(float(line.strip()) / 10.0 - 273.15, 1)
        except Exception:
            pass
        try:
            import wmi

            w = wmi.WMI(namespace="root\\wmi")
            temps = w.MSAcpi_ThermalZoneTemperature()
            if temps:
                return round((float(temps[0].CurrentTemperature) / 10.0) - 273.15, 1)
        except Exception:
            pass
        return "No Sensor"

    def update_font(self, size_px):
        logger.info(f"Оверлей: изменение размера шрифта на {size_px}px.")
        self.settings["scale"] = size_px / 14.0
        color = self.settings.get("color", "#00FF00")
        bg_color = self.settings.get("bg_color", "#000000")
        bg_alpha = self.settings.get("bg_alpha", 180)
        self.label.setStyleSheet(f"""
            background-color: rgba({int(bg_color[1:3], 16)}, {int(bg_color[3:5], 16)}, {int(bg_color[5:7], 16)}, {bg_alpha});
            color: {color};
            font-weight: bold;
            font-size: {size_px}px;
            padding: 4px;
            border-radius: 4px;
            border: 1px solid #333;
        """)
        self.resize(self.label.sizeHint())
        self.save_settings()

    def update_color(self, color):
        self.settings["color"] = color
        self._apply_style()
        self.update_font(int(14 * self.settings.get("scale", 1.0)))
        self.save_settings()

    def update_background(self, bg_color, bg_alpha):
        self.settings["bg_color"] = bg_color
        self.settings["bg_alpha"] = bg_alpha
        self._apply_style()
        self.update_font(int(14 * self.settings.get("scale", 1.0)))
        self.save_settings()

    def save_settings(self):
        self.settings["scale"] = self.settings.get("scale", 1.0)
        with open("overlay_settings.json", "w") as f:
            json.dump(self.settings, f)
        logger.info(
            f"Оверлей: настройки сохранены (x={self.settings['x']:.2f}, y={self.settings['y']:.2f}, scale={self.settings['scale']}, color={self.settings.get('color')}, bg_color={self.settings.get('bg_color')}, bg_alpha={self.settings.get('bg_alpha')}, auto_hide={self.settings.get('auto_hide_seconds', 0)})."
        )


class OverlayConfigWindow(QWidget):
    def __init__(self, overlay):
        super().__init__(parent=None)
        self.overlay = overlay
        logger.info("Оверлей: открыт конфигуратор.")
        self.setWindowTitle("Настройка оверлея")
        self.setWindowFlags(Qt.Tool | Qt.WindowCloseButtonHint)

        self.setFixedSize(640, 480)

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
                selection-background-color: #1A3A5A;
                selection-color: #00FFCC;
            }
            QSlider::groove:horizontal {
                background: #1A2234;
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #00FFCC;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSpinBox {
                background-color: #101A2C;
                border: 1px solid #1A2234;
                border-radius: 4px;
                padding: 4px;
                color: #FFFFFF;
            }
            QSpinBox:focus {
                border: 1px solid #00FFCC;
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
            QPushButton:pressed {
                background-color: #0A1220;
            }
        """)

        self.sample_label = QLabel("60")
        self.sample_label.setAlignment(Qt.AlignCenter)
        self.sample_label.setStyleSheet("""
            background-color: rgba(80, 80, 80, 160);
            color: #00FF00;
            font-size: 32px;
            font-weight: bold;
            border: 2px dashed #AAAAAA;
        """)
        self.sample_label.mousePressEvent = self._sample_press
        self.sample_label.mouseMoveEvent = self._sample_move
        self.sample_label.mouseReleaseEvent = self._sample_release
        self.sample_label.setFixedSize(80, 60)

        self.scale_slider = QSlider(Qt.Horizontal)
        self.scale_slider.setRange(8, 72)
        self.scale_slider.setValue(int(14 * overlay.settings.get("scale", 1.0)))
        self.scale_slider.valueChanged.connect(self._scale_changed)

        # Выбор цвета текста
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Цвет текста:"))
        self.color_combo = QComboBox()
        self.color_combo.addItems(["Зелёный", "Белый", "Жёлтый", "Красный", "Голубой"])
        self.color_combo.currentTextChanged.connect(self._color_changed)
        color_layout.addWidget(self.color_combo)

        # Выбор цвета фона
        bg_color_layout = QHBoxLayout()
        bg_color_layout.addWidget(QLabel("Цвет фона:"))
        self.bg_color_combo = QComboBox()
        self.bg_color_combo.addItems(
            ["Чёрный", "Тёмно-серый", "Синий", "Тёмно-зелёный", "Бордовый"]
        )
        self.bg_color_combo.currentTextChanged.connect(self._bg_color_changed)
        bg_color_layout.addWidget(self.bg_color_combo)

        # Выбор прозрачности фона
        alpha_layout = QHBoxLayout()
        alpha_layout.addWidget(QLabel("Прозрачность фона:"))
        self.alpha_slider = QSlider(Qt.Horizontal)
        self.alpha_slider.setRange(0, 255)
        self.alpha_slider.setValue(overlay.settings.get("bg_alpha", 180))
        self.alpha_slider.valueChanged.connect(self._alpha_changed)
        alpha_layout.addWidget(self.alpha_slider)
        self.alpha_label = QLabel(f"{overlay.settings.get('bg_alpha', 180)}")
        alpha_layout.addWidget(self.alpha_label)

        # Выбор автоскрытия
        hide_layout = QHBoxLayout()
        hide_layout.addWidget(QLabel("Автоскрытие через:"))
        self.hide_spin = QSpinBox()
        self.hide_spin.setRange(0, 300)
        self.hide_spin.setSuffix(" сек")
        self.hide_spin.setSpecialValueText("Никогда")
        self.hide_spin.setValue(overlay.settings.get("auto_hide_seconds", 0))
        self.hide_spin.valueChanged.connect(self._hide_changed)
        hide_layout.addWidget(self.hide_spin)
        hide_layout.addWidget(QLabel("(0 = никогда)"))

        help_btn = QPushButton("❓ Справка")
        help_btn.clicked.connect(self._show_help)
        close_btn = QPushButton("Закрыть конфигуратор")
        close_btn.clicked.connect(self.close)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(help_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)

        layout = QVBoxLayout()
        layout.addWidget(QLabel('Перетащите образец "60" для позиции оверлея:'))
        layout.addWidget(self.sample_label, 1, Qt.AlignCenter)
        layout.addWidget(QLabel("Размер шрифта (px):"))
        layout.addWidget(self.scale_slider)
        layout.addLayout(color_layout)
        layout.addLayout(bg_color_layout)
        layout.addLayout(alpha_layout)
        layout.addLayout(hide_layout)
        layout.addLayout(btn_layout)
        self.setLayout(layout)
        self.setLayout(layout)

        self._sync_sample_to_overlay()
        self._sync_color_to_combo()
        self.show()
        self._sync_bg_color_to_combo()

    def _show_help(self):
        QMessageBox.about(
            self,
            "Справка: Настройка оверлея",
            "📖 **Назначение:**\n"
            "Настройка внешнего вида системного оверлея.\n\n"
            "🔧 **Параметры:**\n"
            "• Перетащите «60» для изменения позиции.\n"
            "• Размер шрифта – от 8 до 72 px.\n"
            "• Цвет текста – зелёный, белый, жёлтый, красный, голубой.\n"
            "• Цвет фона – чёрный, тёмно-серый, синий, тёмно-зелёный, бордовый.\n"
            "• Прозрачность фона – от 0 (полностью прозрачный) до 255 (непрозрачный).\n"
            "• Автоскрытие – через N секунд (0 = никогда).\n\n"
            "💡 **Совет:**\n"
            "Оверлей отображает информацию о системе и рекомендации AI Scout.\n\n"
            "📁 **Файл:** overlay_settings.json",
        )

    def _sync_color_to_combo(self):
        color_map = {
            "#00FF00": "Зелёный",
            "#FFFFFF": "Белый",
            "#FFFF00": "Жёлтый",
            "#FF0000": "Красный",
            "#00FFFF": "Голубой",
        }
        current_color = self.overlay.settings.get("color", "#00FF00")
        text = color_map.get(current_color, "Зелёный")
        index = self.color_combo.findText(text)
        if index >= 0:
            self.color_combo.setCurrentIndex(index)

    def _sync_bg_color_to_combo(self):
        bg_map = {
            "#000000": "Чёрный",
            "#222222": "Тёмно-серый",
            "#001133": "Синий",
            "#003300": "Тёмно-зелёный",
            "#330000": "Бордовый",
        }
        current_bg = self.overlay.settings.get("bg_color", "#000000")
        text = bg_map.get(current_bg, "Чёрный")
        index = self.bg_color_combo.findText(text)
        if index >= 0:
            self.bg_color_combo.setCurrentIndex(index)

    def _sample_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
            self._sample_start_pos = self.sample_label.pos()
            event.accept()

    def _sample_move(self, event):
        if event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_start
            new_x = self._sample_start_pos.x() + delta.x()
            new_y = self._sample_start_pos.y() + delta.y()
            new_x = max(0, min(new_x, self.width() - self.sample_label.width()))
            new_y = max(0, min(new_y, self.height() - self.sample_label.height()))
            self.sample_label.move(new_x, new_y)
            self._sync_overlay_to_sample()
            event.accept()

    def _sample_release(self, event):
        pass

    def _sync_sample_to_overlay(self):
        nx = self.overlay.settings["x"]
        ny = self.overlay.settings["y"]
        sample_x = int(nx * (self.width() - self.sample_label.width()))
        sample_y = int(ny * (self.height() - self.sample_label.height()))
        self.sample_label.move(sample_x, sample_y)

    def _sync_overlay_to_sample(self):
        """Сохраняет позицию и перемещает оверлей."""
        if (self.width() - self.sample_label.width()) > 0:
            nx = self.sample_label.x() / (self.width() - self.sample_label.width())
        else:
            nx = 0.5
        if (self.height() - self.sample_label.height()) > 0:
            ny = self.sample_label.y() / (self.height() - self.sample_label.height())
        else:
            ny = 0.5

        nx = max(0.0, min(1.0, nx))
        ny = max(0.0, min(1.0, ny))

        # Сохраняем в настройки
        self.overlay.settings["x"] = nx
        self.overlay.settings["y"] = ny

        # Перемещаем оверлей на экране
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.x() + int(nx * (screen.width() - self.overlay.width()))
        y = screen.y() + int(ny * (screen.height() - self.overlay.height()))
        self.overlay.move(x, y)

        # НЕМЕДЛЕННО СОХРАНЯЕМ В ФАЙЛ
        self.overlay.save_settings()

        logger.info(f"Оверлей: позиция {nx:.2f}, {ny:.2f} сохранена")

    def _scale_changed(self, value):
        logger.info(f"Оверлей: масштаб изменён на {value}px.")
        self.overlay.update_font(value)
        font = self.sample_label.font()
        font.setPointSize(int(value * 0.8))
        self.sample_label.setFont(font)
        self.sample_label.adjustSize()

    def _color_changed(self, text):
        color_map = {
            "Зелёный": "#00FF00",
            "Белый": "#FFFFFF",
            "Жёлтый": "#FFFF00",
            "Красный": "#FF0000",
            "Голубой": "#00FFFF",
        }
        color = color_map.get(text, "#00FF00")
        self.overlay.update_color(color)
        self.sample_label.setStyleSheet(f"""
            background-color: rgba(80, 80, 80, 160);
            color: {color};
            font-size: 32px;
            font-weight: bold;
            border: 2px dashed #AAAAAA;
        """)

    def _bg_color_changed(self, text):
        color_map = {
            "Чёрный": "#000000",
            "Тёмно-серый": "#222222",
            "Синий": "#001133",
            "Тёмно-зелёный": "#003300",
            "Бордовый": "#330000",
        }
        color = color_map.get(text, "#000000")
        self.overlay.update_background(color, self.alpha_slider.value())

    def _alpha_changed(self, value):
        self.alpha_label.setText(str(value))
        bg_color = self.overlay.settings.get("bg_color", "#000000")
        self.overlay.update_background(bg_color, value)

    def _hide_changed(self, value):
        self.overlay.settings["auto_hide_seconds"] = value
        logger.info(f"Оверлей: автоскрытие установлено на {value} сек")

    def closeEvent(self, event):
        logger.info("Оверлей: конфигуратор закрыт.")
        self.overlay.save_settings()
        super().closeEvent(event)
