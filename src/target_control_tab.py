"""
Вкладка "Управление" – расчёт оптимального пресета под целевой FPS,
индикатор заполнения видеопамяти (VRAM Guard) и кнопка "Применить и проверить".
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QProgressBar,
    QPushButton,
    QComboBox,
    QGroupBox,
    QMessageBox,
    QGridLayout,
    QScrollArea,
)
from PySide6.QtCore import Qt
import statistics
import logging
from calibration_tab import PRESETS
from game_requirements import (
    get_cpu_score,
    get_gpu_score,
    extract_first_cpu,
    extract_first_gpu,
)
from settings import load_settings
from performance_widgets import LiveMonitorWidget, ArcGauge, PresetButtonRow

file_logger = logging.getLogger("TargetControl")

# Приблизительное потребление VRAM разными пресетами (в ГБ)
PRESET_VRAM_ESTIMATE = {
    "Низкие": 2.5,
    "Средние": 4.0,
    "Высокие": 5.5,
    "Ультра": 7.0,
    "Макс.": 7.8,
    "Кино": 8.5,
}


class TargetControlTab(QWidget):
    def __init__(self, db, log_func=None):
        super().__init__()
        self.db = db
        self.log = log_func if log_func else print
        self.current_profile_id = None
        self.current_game = None
        self._user_modified_target_fps = (
            False  # флаг, что пользователь сам менял значение
        )
        self._init_ui()
        self._load_profile()
        # Загружаем целевой FPS из БД для текущей игры (если есть)
        # Пока нет игры, оставляем значение по умолчанию 60
        self.target_fps_spin.setValue(60)
        self._user_modified_target_fps = False

    def _log(self, msg):
        """Выводит сообщение в GUI и в файловый лог."""
        self.log(msg)
        file_logger.info(msg)

    def _init_ui(self):
        # Скролл — чтобы всё влезало при маленьком окне
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollArea > QWidget > QWidget { background: transparent; }
            QScrollBar:vertical {
                background: #0A0F18;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #1A3A5A;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical { height: 0px; }
        """)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(inner)
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Блок живого мониторинга
        self.live_monitor = LiveMonitorWidget()
        layout.addWidget(self.live_monitor)

        # Верхняя панель – выбор игры (из калибровочных данных)
        game_layout = QHBoxLayout()
        game_layout.addWidget(QLabel("Игра:"))
        self.game_combo = QComboBox()
        self.game_combo.currentTextChanged.connect(self._on_game_changed)
        self.game_combo.setStyleSheet("""
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
            QComboBox QAbstractItemView {
                background-color: #101A2C;
                border: 1px solid #1A2234;
                color: #FFFFFF;
                selection-background-color: #1A3A5A;
                selection-color: #00FFCC;
                outline: none;
            }
        """)
        game_layout.addWidget(self.game_combo, 1)
        layout.addLayout(game_layout)

        # Группа "Целевой FPS"
        fps_group = QGroupBox("Целевой FPS")
        fps_layout = QHBoxLayout()
        self.target_fps_spin = QSpinBox()
        self.target_fps_spin.setRange(30, 240)
        self.target_fps_spin.setValue(60)
        self.target_fps_spin.setMaximumWidth(100)  # Ограничиваем максимальную ширину
        self.target_fps_spin.setToolTip(
            "📊 Математический расчет. Программа выберет пресет из ваших реальных замеров (Калибровки), который выдает не менее этого числа."
        )
        self.target_fps_spin.valueChanged.connect(self._on_target_fps_changed)
        fps_layout.addWidget(self.target_fps_spin)
        fps_layout.addStretch()  # Добавляем растяжение, чтобы поле не растягивалось на всю ширину
        fps_group.setLayout(fps_layout)
        layout.addWidget(fps_group)

        # Группа "Рекомендация"
        rec_group = QGroupBox("Оптимальный пресет")
        rec_layout = QVBoxLayout()
        self.preset_buttons = PresetButtonRow()
        rec_layout.addWidget(self.preset_buttons)
        self.recommended_preset_label = QLabel("—")
        self.recommended_preset_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #4CAF50;"
        )
        rec_layout.addWidget(self.recommended_preset_label)
        self.expected_fps_label = QLabel("Ожидаемый FPS: —")
        rec_layout.addWidget(self.expected_fps_label)
        rec_group.setLayout(rec_layout)
        layout.addWidget(rec_group)

        # Группа "Прогноз FPS по пресетам"
        self.prediction_group = QGroupBox("Прогноз FPS по пресетам")
        prediction_layout = QVBoxLayout()
        self.prediction_labels = {}
        grid = QGridLayout()
        for i, preset in enumerate(PRESETS):
            lbl = QLabel(f"{preset}:")
            val = QLabel("—")
            self.prediction_labels[preset] = val
            grid.addWidget(lbl, i // 3, (i % 3) * 2)
            grid.addWidget(val, i // 3, (i % 3) * 2 + 1)
        prediction_layout.addLayout(grid)
        self.prediction_group.setLayout(prediction_layout)
        layout.addWidget(self.prediction_group)

        # Группа "Запас производительности"
        perf_group = QGroupBox("Запас производительности")
        perf_layout = QVBoxLayout()

        self.cpu_mult_label = QLabel("CPU: —")
        self.gpu_mult_label = QLabel("GPU: —")
        self.bottleneck_label = QLabel("Узкое место: —")

        perf_layout.addWidget(self.cpu_mult_label)
        perf_layout.addWidget(self.gpu_mult_label)
        perf_layout.addWidget(self.bottleneck_label)
        perf_group.setLayout(perf_layout)
        layout.addWidget(perf_group)

        # Индикатор VRAM Guard (дуговой)
        vram_group = QGroupBox("Видеопамять (VRAM Guard)")
        vram_layout = QHBoxLayout()
        self.vram_arc = ArcGauge()
        self.vram_label = QLabel("Занято: 0 ГБ / Лимит: 0 ГБ")
        self.vram_label.setAlignment(Qt.AlignVCenter)
        self.vram_bar = QProgressBar()  # оставляем для совместимости логики
        self.vram_bar.setRange(0, 100)
        self.vram_bar.setValue(0)
        self.vram_bar.setVisible(False)  # скрыт, но логика работает как раньше
        vram_layout.addWidget(self.vram_arc)
        vram_layout.addWidget(self.vram_label, stretch=1)
        vram_group.setLayout(vram_layout)
        layout.addWidget(vram_group)

        # Предупреждение при превышении
        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet("color: red; font-weight: bold;")
        self.warning_label.setVisible(False)
        layout.addWidget(self.warning_label)

        # Кнопка "Применить и проверить"
        btn_layout = QHBoxLayout()
        self.apply_btn = QPushButton("Применить и проверить")
        self.apply_btn.clicked.connect(self._apply_and_check)
        btn_layout.addStretch()
        btn_layout.addWidget(self.apply_btn)
        layout.addLayout(btn_layout)

        layout.addStretch()

    def refresh(self):
        """Обновляет список игр при переключении вкладки."""
        self._log("[Управление] refresh() вызван")
        self._load_profile()
        if self.current_game:
            self._log(
                f"[Управление] refresh: current_game={self.current_game}, вызываем _calculate_and_display()"
            )
            self._calculate_and_display()
        else:
            self._log("[Управление] refresh: current_game пуст")

    def _load_profile(self):
        self.current_profile_id = self.db.get_current_profile_id()
        if not self.current_profile_id:
            self.game_combo.clear()
            return
        games = self.db.get_games_for_profile(self.current_profile_id)
        current = self.game_combo.currentText()
        self.game_combo.blockSignals(True)
        self.game_combo.clear()
        self.game_combo.addItems(games)
        if current in games:
            self.game_combo.setCurrentText(current)
        self.game_combo.blockSignals(False)

        # Принудительно синхронизируем current_game и пересчитываем
        if self.game_combo.count() > 0:
            self._on_game_changed(self.game_combo.currentText())
        else:
            self.current_game = None
            self.recommended_preset_label.setText("—")
            self.expected_fps_label.setText("Ожидаемый FPS: —")
            for lbl in self.prediction_labels.values():
                lbl.setText("—")

    def _on_game_changed(self, game_name):
        self.current_game = game_name
        self._log(f"[Управление] Выбрана игра: '{game_name}', запуск расчёта...")

        # Загружаем сохранённый target FPS для этой игры
        saved_fps = self.db.get_target_fps_for_game(self.current_profile_id, game_name)
        if saved_fps is not None:
            # Есть сохранённое значение – используем его
            self.target_fps_spin.setValue(saved_fps)
            self._log(
                f"[Управление] Загружен сохранённый target FPS для '{game_name}': {saved_fps}"
            )
            self._user_modified_target_fps = True
            self._calculate_and_display()
            return

        # Проверяем, отклонил ли пользователь рекомендацию ранее
        if self.db.is_recommendation_dismissed(self.current_profile_id, game_name):
            self._log(
                f"[Управление] Пользователь ранее отклонил рекомендацию для игры '{game_name}'"
            )
            self.target_fps_spin.setValue(60)
            self._calculate_and_display()
            return

        # Нет сохранённого значения – предлагаем
        suggested = self._suggest_target_fps(game_name)

        # Если рекомендация не выдана (игры нет в базе) — не показываем диалог
        if suggested is None:
            self._log(
                f"[Управление] Для игры '{game_name}' нет рекомендации (отсутствует в базе требований)"
            )
            self.target_fps_spin.setValue(60)
            self._calculate_and_display()
            return

        self.target_fps_spin.setValue(suggested)
        self._log(f"[Управление] Предложен target FPS для '{game_name}': {suggested}")

        # Показываем всплывающее уведомление
        reply = QMessageBox.question(
            self,
            "Рекомендация по FPS",
            f"На основе вашего железа и жанра игры рекомендуем установить целевой FPS = {suggested}.\n\n"
            f"Сохранить это значение для игры '{game_name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )

        if reply == QMessageBox.Yes:
            # Сохраняем предложенное значение
            self.db.save_target_fps_for_game(
                self.current_profile_id, game_name, suggested
            )
            self._log(
                f"[Управление] Сохранён target FPS={suggested} для игры '{game_name}'"
            )
            self._user_modified_target_fps = True
        else:
            # Пользователь отказался – сохраняем флаг отказа
            self.db.save_recommendation_dismissed(
                self.current_profile_id, game_name
            )
            self._log(
                f"[Управление] Пользователь отказался от предложения для '{game_name}'"
            )

        self._calculate_and_display()

    def _on_target_fps_changed(self, value):
        self._user_modified_target_fps = True
        self._log(f"[Управление] Пользователь изменил target FPS на {value}")

        # Сохраняем в БД для текущей игры
        if self.current_game and self.current_profile_id:
            self.db.save_target_fps_for_game(
                self.current_profile_id, self.current_game, value
            )

        self._calculate_and_display()

    def _calculate_performance_headroom(self, game_name):
        """Рассчитывает множители CPU/GPU относительно минимальных требований игры."""
        self._log(f"[Запас] Начинаем расчёт для игры '{game_name}'")

        if not self.current_profile_id or not game_name:
            self._log("[Запас] Нет profile_id или game_name")
            return None, None, None

        # Загружаем требования игры
        import json
        import os

        reqs_file = "game_requirements.json"
        if not os.path.exists(reqs_file):
            self._log(f"[Запас] Файл {reqs_file} не найден")
            return None, None, None

        try:
            with open(reqs_file, "r", encoding="utf-8") as f:
                all_reqs = json.load(f)
            reqs = all_reqs.get(game_name)
            if not reqs:
                self._log(
                    f"[Запас] Игра '{game_name}' не найдена в game_requirements.json"
                )
                return None, None, None
            self._log(f"[Запас] Требования для '{game_name}': {reqs}")
        except Exception as e:
            self._log(f"[Запас] Ошибка загрузки требований: {e}")
            return None, None, None

        # Получаем железо пользователя
        cursor = self.db.conn.cursor()
        cursor.execute(
            "SELECT cpu_name, gpu_name FROM hardware_profiles WHERE id=?",
            (self.current_profile_id,),
        )
        hw = cursor.fetchone()
        if not hw:
            self._log("[Запас] Нет данных о железе пользователя")
            return None, None, None

        user_cpu = hw[0] or ""
        user_gpu = hw[1] or ""
        self._log(f"[Запас] Железо пользователя: CPU='{user_cpu}', GPU='{user_gpu}'")

        # Получаем минимальные требования
        min_cpu_raw = reqs.get("min_cpu", "")
        min_gpu_raw = reqs.get("min_gpu", "")
        min_cpu = extract_first_cpu(min_cpu_raw) if min_cpu_raw else ""
        min_gpu = extract_first_gpu(min_gpu_raw) if min_gpu_raw else ""
        self._log(
            f"[Запас] Минимальные требования (после парсинга): CPU='{min_cpu}', GPU='{min_gpu}'"
        )

        if not min_cpu or not min_gpu:
            self._log("[Запас] Минимальные требования не распознаны")
            return None, None, None

        # Получаем баллы
        user_cpu_score = get_cpu_score(user_cpu)
        min_cpu_score = get_cpu_score(min_cpu)
        user_gpu_score = get_gpu_score(user_gpu)
        min_gpu_score = get_gpu_score(min_gpu)

        self._log(
            f"[Запас] Баллы: user_cpu={user_cpu_score}, min_cpu={min_cpu_score}, user_gpu={user_gpu_score}, min_gpu={min_gpu_score}"
        )

        # Рассчитываем множители
        cpu_mult = user_cpu_score / min_cpu_score if min_cpu_score > 0 else 0
        gpu_mult = user_gpu_score / min_gpu_score if min_gpu_score > 0 else 0

        # Определяем узкое место
        if cpu_mult < gpu_mult:
            bottleneck = f"⚠️ CPU (множитель {cpu_mult:.1f}x, GPU {gpu_mult:.1f}x)"
        elif gpu_mult < cpu_mult:
            bottleneck = f"⚠️ GPU (множитель {gpu_mult:.1f}x, CPU {cpu_mult:.1f}x)"
        else:
            bottleneck = "✅ Сбалансировано"

        self._log(
            f"[Запас] Результат: CPU={cpu_mult:.1f}x, GPU={gpu_mult:.1f}x, узкое место={bottleneck}"
        )

        return cpu_mult, gpu_mult, bottleneck

    def _suggest_target_fps(self, game_name):
        """Предлагает целевой FPS на основе монитора, железа и жанра игры."""
        settings = load_settings()
        monitor_hz = settings.get("monitor_hz", 60)

        # Проверяем, есть ли игра в базе требований
        from game_requirements import RequirementsManager

        reqs_manager = RequirementsManager()
        game_in_db = reqs_manager.game_exists(game_name)
        genre = None

        if game_in_db:
            reqs = reqs_manager.get_requirements(game_name)
            genre = reqs.get("genre") if reqs else None
            self._log(
                f"[Предложение FPS] Игра '{game_name}' найдена в базе, жанр: {genre}"
            )
        else:
            self._log(
                f"[Предложение FPS] Игра '{game_name}' НЕ найдена в базе требований"
            )

        # Если игры нет в базе — не предлагаем рекомендацию
        if not game_in_db:
            self._log(
                f"[Предложение FPS] Игра '{game_name}' отсутствует в базе, рекомендация не выдаётся"
            )
            return None

        # Получаем баллы пользователя
        cursor = self.db.conn.cursor()
        cursor.execute(
            "SELECT cpu_name, gpu_name, vram_gb FROM hardware_profiles WHERE id=?",
            (self.current_profile_id,),
        )
        hw = cursor.fetchone()
        if not hw:
            return monitor_hz

        user_cpu = hw[0] or ""
        user_gpu = hw[1] or ""
        user_vram = hw[2] or 0

        user_cpu_score = get_cpu_score(user_cpu)
        user_gpu_score = get_gpu_score(user_gpu)

        self._log(
            f"[Предложение FPS] Монитор: {monitor_hz} Гц, CPU: {user_cpu_score}, GPU: {user_gpu_score}, VRAM: {user_vram} ГБ"
        )

        # Базовое значение — герцовка монитора
        suggested = monitor_hz

        # Если железо слабое — ограничиваем до 60 FPS
        if user_cpu_score < 200 or user_gpu_score < 200:
            suggested = min(suggested, 60)
            self._log(f"[Предложение FPS] Железо слабое, ограничиваем до {suggested}")

        # Если железо очень слабое — 30 FPS
        if user_cpu_score < 100 or user_gpu_score < 80:
            suggested = 30
            self._log("[Предложение FPS] Железо очень слабое, устанавливаем 30 FPS")

        # Если VRAM меньше 4 ГБ — ограничиваем до 60 FPS
        if user_vram < 4 and user_vram > 0:
            suggested = min(suggested, 60)
            self._log(
                f"[Предложение FPS] VRAM {user_vram} ГБ < 4 ГБ, ограничиваем до {suggested}"
            )

        # Корректировка по жанру (если указан)
        if genre in [
            "RPG",
            "Strategy",
            "Simulation",
            "Adventure",
            "Puzzle",
            "Platformer",
        ]:
            suggested = min(suggested, 60)
            self._log(
                f"[Предложение FPS] Жанр {genre} не требует высокого FPS, ограничиваем до {suggested}"
            )

        # Ограничение снизу
        suggested = max(suggested, 30)

        self._log(f"[Предложение FPS] Итоговое предложение: {suggested} FPS")
        return suggested

    def _calculate_and_display(self):
        """Основной математический движок: подбор пресета под целевой FPS и обновление VRAM."""
        self._log("[Управление] _calculate_and_display() начал работу")
        if not self.current_game or not self.current_profile_id:
            self._log(
                "[Управление] Игра или профиль не выбраны, расчёт не выполняется."
            )
            self.recommended_preset_label.setText("—")
            self.expected_fps_label.setText("Ожидаемый FPS: —")
            self.vram_bar.setValue(0)
            self.vram_label.setText("Занято: 0 ГБ / Лимит: 0 ГБ")
            self.warning_label.setVisible(False)
            for lbl in self.prediction_labels.values():
                lbl.setText("—")
            return

        self._log(
            f"[Управление] Загрузка замеров FPS для игры '{self.current_game}' (профиль {self.current_profile_id})..."
        )
        presets_data = self.db.get_presets_for_game(
            self.current_profile_id, self.current_game
        )
        if not presets_data:
            self._log("[Управление] Нет калибровочных данных, расчёт невозможен.")
            self.recommended_preset_label.setText("Нет калибровочных данных")
            self.expected_fps_label.setText("—")
            self.vram_bar.setValue(0)
            for lbl in self.prediction_labels.values():
                lbl.setText("—")
            return

        # Преобразуем в словарь {пресет: средний FPS}
        preset_fps = {}
        for preset, fps_str in presets_data:
            if fps_str:
                try:
                    fps_list = [
                        float(v.strip()) for v in fps_str.split(",") if v.strip()
                    ]
                    if fps_list:
                        preset_fps[preset] = statistics.mean(fps_list)
                        self.prediction_labels[preset].setText(
                            f"{preset_fps[preset]:.0f}"
                        )
                        self._log(
                            f"  {preset}: средний FPS = {preset_fps[preset]:.0f} (из значений: {fps_str})"
                        )
                    else:
                        self.prediction_labels[preset].setText("—")
                except (ValueError, statistics.StatisticsError):
                    self.prediction_labels[preset].setText("—")
                    self._log(f"  {preset}: ошибка парсинга FPS ('{fps_str}')")
            else:
                self.prediction_labels[preset].setText("—")

        if not preset_fps:
            self._log("[Управление] Не удалось извлечь ни одного числового FPS.")
            self.recommended_preset_label.setText("Нет данных FPS")
            return

        target = self.target_fps_spin.value()
        self._log(f"[Управление] Целевой FPS: {target}")

        # Поиск пресета, у которого FPS >= target, с минимальным превышением
        better_presets = {p: fps for p, fps in preset_fps.items() if fps >= target}
        if better_presets:
            recommended = min(better_presets, key=lambda p: better_presets[p])
            expected_fps = preset_fps[recommended]
            self._log(
                f"  Есть пресеты, достигающие цели: {list(better_presets.keys())}"
            )
            self._log(f"  Выбран ближайший: {recommended} ({expected_fps:.1f} FPS)")
        else:
            recommended = max(preset_fps, key=lambda p: preset_fps[p])
            expected_fps = preset_fps[recommended]
            self._log(
                f"  Нет пресетов, достигающих целевого FPS. Выбран максимальный: {recommended} ({expected_fps:.1f} FPS)"
            )

        self.recommended_preset_label.setText(f"Рекомендуемый пресет: {recommended}")
        self.expected_fps_label.setText(f"Ожидаемый FPS: {expected_fps:.1f}")
        self.preset_buttons.set_active(recommended)
        if expected_fps < target:
            self.expected_fps_label.setStyleSheet("color: red; font-weight: bold;")
            self._log(
                f"  Внимание: ожидаемый FPS ({expected_fps:.1f}) ниже целевого ({target})."
            )
        else:
            self.expected_fps_label.setStyleSheet("color: white; font-weight: normal;")

        # VRAM
        cursor = self.db.conn.cursor()
        cursor.execute(
            "SELECT vram_gb FROM hardware_profiles WHERE id=?",
            (self.current_profile_id,),
        )
        row = cursor.fetchone()
        vram_limit = row[0] if row and row[0] else 8.0
        self._log(f"[Управление] VRAM лимит: {vram_limit} ГБ")

        estimated_usage = PRESET_VRAM_ESTIMATE.get(recommended, 4.0)
        usage_percent = (
            min(int(estimated_usage / vram_limit * 100), 100) if vram_limit > 0 else 100
        )
        self.vram_bar.setValue(usage_percent)
        self.vram_label.setText(
            f"Занято: {estimated_usage:.1f} ГБ / Лимит: {vram_limit} ГБ"
        )
        self.vram_arc.set_value(estimated_usage, vram_limit)
        self._log(
            f"  Пресет {recommended}: ожидаемое использование VRAM {estimated_usage:.1f} ГБ ({usage_percent}%)"
        )

        if vram_limit > 0 and estimated_usage > vram_limit * 0.95:
            self.warning_label.setText(
                "Внимание: риск статтеров – видеопамять почти заполнена!"
            )
            self.warning_label.setVisible(True)
            self._log("  Предупреждение: VRAM заполнена более чем на 95%!")
        else:
            self.warning_label.setVisible(False)

        # Градиентная заливка VRAM (зелёный -> жёлтый -> красный)
        if usage_percent < 75:
            self.vram_bar.setStyleSheet("""
                QProgressBar {
                    border: 1px solid #555;
                    border-radius: 5px;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #4CAF50, stop:1 #8BC34A);
                    border-radius: 4px;
                }
            """)
        elif usage_percent <= 90:
            self.vram_bar.setStyleSheet("""
                QProgressBar {
                    border: 1px solid #555;
                    border-radius: 5px;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #FFC107, stop:1 #FF9800);
                    border-radius: 4px;
                }
            """)
        else:
            self.vram_bar.setStyleSheet("""
                QProgressBar {
                    border: 1px solid #555;
                    border-radius: 5px;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #F44336, stop:1 #D32F2F);
                    border-radius: 4px;
                }
            """)

        # Расчёт запаса производительности
        try:
            cpu_mult, gpu_mult, bottleneck = self._calculate_performance_headroom(
                self.current_game
            )
            self._log(
                f"[Управление] Результат headroom: cpu_mult={cpu_mult}, gpu_mult={gpu_mult}, bottleneck={bottleneck}"
            )
        except Exception as e:
            self._log(f"[Управление] ОШИБКА в _calculate_performance_headroom: {e}")
            import traceback

            self._log(traceback.format_exc())
            cpu_mult = gpu_mult = None

        if cpu_mult and gpu_mult:
            cpu_color = (
                "#4CAF50"
                if cpu_mult >= 2
                else "#FFC107"
                if cpu_mult >= 1
                else "#F44336"
            )
            gpu_color = (
                "#4CAF50"
                if gpu_mult >= 2
                else "#FFC107"
                if gpu_mult >= 1
                else "#F44336"
            )

            self.cpu_mult_label.setText(f"CPU: {cpu_mult:.1f}x над минималками")
            self.cpu_mult_label.setStyleSheet(f"color: {cpu_color}; font-weight: bold;")
            self.gpu_mult_label.setText(f"GPU: {gpu_mult:.1f}x над минималками")
            self.gpu_mult_label.setStyleSheet(f"color: {gpu_color}; font-weight: bold;")
            self.bottleneck_label.setText(f"Узкое место: {bottleneck}")
            self._log(
                f"  Запас производительности: CPU={cpu_mult:.1f}x, GPU={gpu_mult:.1f}x"
            )
        else:
            self.cpu_mult_label.setText("CPU: —")
            self.gpu_mult_label.setText("GPU: —")
            self.bottleneck_label.setText("Узкое место: нет требований")

        self._log(
            f"  Итог: целевой FPS={target}, рекомендован {recommended} (ожидаемый FPS={expected_fps:.1f}, VRAM {estimated_usage:.1f} ГБ)"
        )

    def set_target_fps(self, value):
        """Устанавливает целевой FPS и пересчитывает рекомендацию."""
        self.target_fps_spin.setValue(value)
        self._calculate_and_display()

    def _apply_and_check(self):
        """Фиксация профиля (пока просто уведомление)."""
        self._log("[Управление] Нажата кнопка 'Применить и проверить'")
        if not self.current_game:
            self._log("  Ошибка: не выбрана игра.")
            QMessageBox.warning(self, "Ошибка", "Выберите игру и целевой FPS.")
            return
        target = self.target_fps_spin.value()
        preset = self.recommended_preset_label.text().replace(
            "Рекомендуемый пресет: ", ""
        )
        vram = self.vram_label.text()
        msg = f"Применён профиль:\nИгра: {self.current_game}\nЦелевой FPS: {target}\nПресет: {preset}\n{vram}"
        self._log(
            f"  Применён профиль: игра='{self.current_game}', целевой FPS={target}, пресет={preset}, {vram}"
        )
        QMessageBox.information(self, "Профиль применён", msg)
