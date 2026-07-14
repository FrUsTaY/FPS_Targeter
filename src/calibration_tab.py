"""
Вкладка "Калибровка" (обновлённый визуал)
"""

import json
import os
import psutil
import re
import statistics
import sys
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QGridLayout,
    QSpinBox,
    QMessageBox,
    QInputDialog,
    QGroupBox,
    QLabel,
)
from ai_engine import OpenRouterBackend, GroqCloudBackend, GeminiBackend
from settings import load_settings
from gpu_name_resolver import get_search_gpu_name

PRESETS = ["Низкие", "Средние", "Высокие", "Ультра", "Макс.", "Кино"]
MAX_FPS_FIELDS = 3

if getattr(sys, "frozen", False):
    # Запущено из .exe
    base_path = os.path.dirname(sys.executable)
else:
    # Запущено из .py
    base_path = os.path.dirname(os.path.abspath(__file__))

PRESETS_DB_FILE = os.path.join(base_path, "game_presets_db.json")

# Цвета бейджей для каждого пресета
PRESET_COLORS = {
    "Низкие": ("#1A3A1A", "#00C853"),
    "Средние": ("#1A2E3A", "#00B0FF"),
    "Высокие": ("#2A2A1A", "#FFD600"),
    "Ультра": ("#2A1A3A", "#AA00FF"),
    "Макс.": ("#3A1A1A", "#FF6D00"),
    "Кино": ("#3A1A2A", "#FF1744"),
}


def predict_fps(current_fps, current_preset, target_preset, game_name=None):
    db = {}
    if os.path.exists(PRESETS_DB_FILE):
        try:
            with open(PRESETS_DB_FILE, "r", encoding="utf-8") as f:
                db = json.load(f)
        except Exception as e:
            print(f"[Predict] Ошибка чтения {PRESETS_DB_FILE}: {e}")
    coeffs = db.get(game_name, db.get("default", {}))
    if not coeffs:
        return None
    k_current = coeffs.get(current_preset)
    k_target = coeffs.get(target_preset)
    if not k_current or not k_target:
        return None
    return round((current_fps / k_current) * k_target, 1)


# ─────────────────────────────────────────────
#  Карточка игры в списке
# ─────────────────────────────────────────────
class GameCard(QWidget):
    """Карточка игры: название + бейджи пресетов с FPS."""

    def __init__(self, game_name: str, fps_data: dict, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 4)
        layout.setSpacing(4)

        # Название игры
        name_lbl = QLabel(game_name)
        name_lbl.setStyleSheet(
            "color: #E0E6ED; font-weight: bold; font-size: 10pt; background: transparent;"
        )
        layout.addWidget(name_lbl)

        # Бейджи пресетов
        badges_row = QHBoxLayout()
        badges_row.setSpacing(3)
        badges_row.setContentsMargins(0, 0, 0, 0)

        for preset in PRESETS:
            fps = fps_data.get(preset)
            bg, fg = PRESET_COLORS.get(preset, ("#1A2234", "#8892B0"))
            if fps:
                text = f"{preset[:3]} {int(float(fps))}"
            else:
                text = preset[:3]
                bg = "#0D1520"
                fg = "#3A4A5A"

            badge = QLabel(text)
            badge.setStyleSheet(f"""
                QLabel {{
                    background-color: {bg};
                    color: {fg};
                    border: 1px solid {fg};
                    border-radius: 3px;
                    padding: 1px 3px;
                    font-size: 7pt;
                    font-weight: bold;
                }}
            """)
            badge.setFixedHeight(16)
            badges_row.addWidget(badge)

        badges_row.addStretch()
        layout.addLayout(badges_row)


# ─────────────────────────────────────────────
#  Кнопки выбора пресета
# ─────────────────────────────────────────────
class PresetSelector(QWidget):
    """Строка кнопок для выбора пресета (замена QComboBox)."""

    preset_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = PRESETS[0]
        self._buttons = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        for name in PRESETS:
            btn = QPushButton(name)
            btn.setFixedHeight(26)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, n=name: self._select(n))
            self._buttons[name] = btn
            layout.addWidget(btn)

        self._select(PRESETS[0])

    def _select(self, name):
        self._current = name
        for n, btn in self._buttons.items():
            if n == name:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #00C8A5;
                        border: 1px solid #00FFCC;
                        border-radius: 4px;
                        color: #000000;
                        font-weight: bold;
                        font-size: 9pt;
                    }
                """)
                btn.setChecked(True)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #101A2C;
                        border: 1px solid #1A2234;
                        border-radius: 4px;
                        color: #8892B0;
                        font-size: 9pt;
                    }
                    QPushButton:hover {
                        border: 1px solid #00FFCC;
                        color: #E0E6ED;
                    }
                """)
                btn.setChecked(False)
        self.preset_changed.emit(name)

    def currentText(self):
        return self._current

    def addItems(self, items):
        pass  # совместимость — пресеты уже заданы


# ─────────────────────────────────────────────
#  Основная вкладка
# ─────────────────────────────────────────────
class CalibrationTab(QWidget):
    def __init__(self, db, log_func=None):
        super().__init__()
        self.db = db
        self.log = log_func if log_func else print
        self.current_profile_id = None
        self.current_game = None
        self._init_ui()
        self._load_profile()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(8)

        # ── Левая панель — список игр ──────────────────
        left_panel = QVBoxLayout()
        left_panel.setSpacing(6)

        search_label = QLabel("Поиск игры:")
        search_label.setStyleSheet("color: #8892B0; font-size: 9pt;")
        left_panel.addWidget(search_label)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Введите название...")
        self.search_edit.textChanged.connect(self._filter_games)
        left_panel.addWidget(self.search_edit)

        # Список игр — кастомные карточки
        self.game_list = QListWidget()
        self.game_list.setSpacing(2)
        self.game_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.game_list.setStyleSheet("""

            QListWidget {
                background-color: #080E18;
                border: 1px solid #1A2234;
                border-radius: 6px;
                outline: none;
            }
            QListWidget::item {
                border-radius: 4px;
                padding: 2px;
            }
            QListWidget::item:selected {
                background-color: #0D2040;
                border-left: 3px solid #00FFCC;
            }
            QListWidget::item:hover:!selected {
                background-color: #0D1826;
            }
        """)
        self.game_list.currentTextChanged.connect(self._on_game_selected)
        left_panel.addWidget(self.game_list, stretch=1)

        # Кнопки управления играми
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)
        self.add_game_btn = QPushButton("Добавить")
        self.edit_game_btn = QPushButton("Ред.")
        self.del_game_btn = QPushButton("Удалить")
        self.req_db_btn = QPushButton("База требований")
        self.add_game_btn.clicked.connect(self._add_game)
        self.edit_game_btn.clicked.connect(self._edit_game)
        self.del_game_btn.clicked.connect(self._delete_game)
        self.req_db_btn.clicked.connect(self._open_requirements_manager)
        for btn in [
            self.add_game_btn,
            self.edit_game_btn,
            self.del_game_btn,
            self.req_db_btn,
        ]:
            btn_layout.addWidget(btn)
        left_panel.addLayout(btn_layout)
        main_layout.addLayout(left_panel, 1)

        # ── Правая панель — замеры ─────────────────────
        right_panel = QVBoxLayout()
        right_panel.setSpacing(8)

        # Группа пресетов — кнопки вместо комбобокса
        preset_group = QGroupBox("Пресет")
        preset_layout = QVBoxLayout(preset_group)
        preset_layout.setContentsMargins(8, 14, 8, 8)
        self.preset_combo = PresetSelector()
        self.preset_combo.preset_changed.connect(self._load_preset_data)
        preset_layout.addWidget(self.preset_combo)
        right_panel.addWidget(preset_group)

        # Группа замеров FPS
        fps_group = QGroupBox("Замеры FPS")
        fps_inner = QVBoxLayout(fps_group)
        fps_inner.setContentsMargins(8, 14, 8, 8)

        hint = QLabel("Введите от 1 до 3 замеров для вычисления среднего FPS")
        hint.setStyleSheet("color: #8892B0; font-size: 9pt;")
        hint.setWordWrap(True)
        fps_inner.addWidget(hint)

        grid = QGridLayout()
        grid.setSpacing(6)
        self.fps_fields = []
        self.history_buttons = []

        for i in range(MAX_FPS_FIELDS):
            lbl = QLabel(f"Замер {i + 1} (FPS):")
            lbl.setStyleSheet("color: #8892B0; font-size: 9pt;")
            spin = QSpinBox()
            spin.setRange(0, 999)
            spin.setValue(0)
            if i >= 1:
                spin.setEnabled(False)
                spin.setToolTip(
                    "Введите значение в предыдущем замере, чтобы активировать это поле."
                )
            spin.valueChanged.connect(lambda val, idx=i: self._toggle_next_field(idx))
            self.fps_fields.append(spin)

            history_btn = QPushButton("📜")
            history_btn.setFixedWidth(30)
            history_btn.setToolTip("Показать историю замеров для этого пресета")
            history_btn.clicked.connect(lambda checked, idx=i: self._show_history(idx))
            history_btn.setEnabled(False)
            self.history_buttons.append(history_btn)

            grid.addWidget(lbl, 0, i * 3)
            grid.addWidget(spin, 0, i * 3 + 1)
            grid.addWidget(history_btn, 0, i * 3 + 2)

        fps_inner.addLayout(grid)
        right_panel.addWidget(fps_group)

        # Метка профиля GPU
        self.profile_gpu_label = QLabel("Профиль: неизвестно")
        self.profile_gpu_label.setStyleSheet(
            "color: #8892B0; font-style: italic; font-size: 9pt;"
        )
        right_panel.addWidget(self.profile_gpu_label)

        # Кнопки калибровки — с цветным акцентом
        self.predict_btn = QPushButton("Машинная калибровка")
        self.predict_btn.setToolTip(
            "Рассчитывает FPS для всех пресетов на основе одного сохранённого замера"
        )
        self.predict_btn.clicked.connect(self._predict_all)

        self.ai_calibrate_btn = QPushButton("AI‑калибровка (Gemini)")
        self.ai_calibrate_btn.setToolTip(
            "Использует Gemini для автоматического расчёта FPS по пресетам"
        )
        self.ai_calibrate_btn.clicked.connect(self._ai_fill_presets)

        self.local_calibrate_btn = QPushButton("Локальная калибровка")
        self.local_calibrate_btn.setToolTip(
            "Рассчитывает FPS на основе системных требований игры и вашего железа"
        )
        self.local_calibrate_btn.clicked.connect(self._local_calibrate)

        self.save_btn = QPushButton("Сохранить результаты для этого ПК")
        self.save_btn.setToolTip("Сохраняет введённые значения FPS в базу данных")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #0D2A1A;
                border: 1px solid #00C853;
                border-radius: 6px;
                color: #00C853;
                padding: 7px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0D3A20;
                border: 1px solid #00FFCC;
                color: #00FFCC;
            }
        """)
        self.save_btn.clicked.connect(self._save_fps)

        for btn in [self.predict_btn, self.ai_calibrate_btn, self.local_calibrate_btn]:
            right_panel.addWidget(btn)
        right_panel.addWidget(self.save_btn)

        # Индикатор текущего метода калибровки
        self.calibration_status = QLabel("Метод: Машинная калибровка")
        self.calibration_status.setStyleSheet("color: #00FFCC; font-size: 8pt;")
        right_panel.addWidget(self.calibration_status)

        right_panel.addStretch()
        main_layout.addLayout(right_panel, 2)

    # ─── ЗАГРУЗКА ПРОФИЛЯ ─────────────────────────────
    def _load_profile(self):
        self.current_profile_id = self.db.get_current_profile_id()
        if self.current_profile_id is None:
            self.log("Нет активного профиля. Игры не загружены.")
            self.game_list.clear()
            return
        self._refresh_game_list()
        self._update_gpu_label()

    def _update_gpu_label(self):
        if not self.current_profile_id:
            self.profile_gpu_label.setText("Профиль: не выбран")
            return
        cursor = self.db.conn.cursor()
        cursor.execute(
            "SELECT gpu_name FROM hardware_profiles WHERE id=?",
            (self.current_profile_id,),
        )
        row = cursor.fetchone()
        if row and row[0]:
            self.profile_gpu_label.setText(f"Профиль для: {row[0]}")
        else:
            self.profile_gpu_label.setText("Профиль: GPU не обнаружен")

    def _get_fps_data_for_game(self, game_name):
        """Возвращает dict {preset: fps_str} для карточки."""
        if not self.current_profile_id:
            return {}
        presets = self.db.get_presets_for_game(self.current_profile_id, game_name)
        result = {}
        for preset, fps_str in presets:
            if fps_str:
                try:
                    vals = [float(v.strip()) for v in fps_str.split(",") if v.strip()]
                    if vals:
                        result[preset] = statistics.mean(vals)
                except Exception:
                    pass
        return result

    def _refresh_game_list(self):
        if self.current_profile_id is None:
            return
        all_games = self.db.get_games_for_profile(self.current_profile_id)
        filter_text = self.search_edit.text().strip().lower()
        filtered = (
            [g for g in all_games if filter_text in g.lower()]
            if filter_text
            else all_games
        )

        # Запоминаем текущую игру
        current_text = ""
        if self.game_list.currentItem():
            current_text = self.game_list.currentItem().data(Qt.UserRole)

        self.game_list.blockSignals(True)
        self.game_list.clear()

        for game_name in filtered:
            fps_data = self._get_fps_data_for_game(game_name)
            card = GameCard(game_name, fps_data)

            item = QListWidgetItem(self.game_list)
            item.setData(Qt.UserRole, game_name)  # храним имя скрыто
            item.setSizeHint(card.sizeHint())
            self.game_list.addItem(item)
            self.game_list.setItemWidget(item, card)

        self.game_list.blockSignals(False)

        # Восстанавливаем выбор (заблокируем сигналы на случай изменения выбора)
        self.game_list.blockSignals(True)
        if current_text:
            self.log(f"[Refresh Game List] Restoring selection to: {current_text}")
            for i in range(self.game_list.count()):
                item = self.game_list.item(i)
                if item.data(Qt.UserRole) == current_text:
                    self.log(f"[Refresh Game List] Setting current row to {i}")
                    self.game_list.setCurrentRow(i)
                    self.game_list.blockSignals(False)
                    return
        self.log("[Refresh Game List] No previous selection, setting to first item or clearing")
        if self.game_list.count() > 0:
            self.game_list.setCurrentRow(0)
        else:
            for field in self.fps_fields:
                field.setValue(0)
        self.game_list.blockSignals(False)

    def _filter_games(self):
        self._refresh_game_list()

    def _on_game_selected(self, game_name):
        self.log(f"[Game Selection] _on_game_selected called with game_name: {game_name}")
        if self.current_profile_id is None:
            self.log("[Game Selection] No active profile, returning")
            return
        # _load_preset_data уже вызовет _update_calibration_status
        self._load_preset_data()

    def _load_preset_data(self):
        game_name = (
            self.game_list.currentItem().data(Qt.UserRole)
            if self.game_list.currentItem()
            else None
        )
        self.log(f"[Load Preset] game_name from selection: {game_name}")
        if not game_name or self.current_profile_id is None:
            self.log("[Load Preset] No game_name or profile_id, returning")
            return
        preset = self.preset_combo.currentText()
        presets = self.db.get_presets_for_game(self.current_profile_id, game_name)
        data = None
        for p, fps_str in presets:
            if p == preset:
                data = fps_str
                break
        for field in self.fps_fields:
            field.setValue(0)
        if data:
            try:
                values = [float(v.strip()) for v in data.split(",") if v.strip()]
                for i, val in enumerate(values[:MAX_FPS_FIELDS]):
                    self.fps_fields[i].setValue(int(val))
            except ValueError:
                pass
        for i, btn in enumerate(self.history_buttons):
            history = self.db.get_fps_history(
                self.current_profile_id, game_name, preset, limit=1
            )
            btn.setEnabled(len(history) > 0)
        
        # Обновляем индикатор метода калибровки
        self.log(f"[Load Preset] Calling _update_calibration_status with {game_name}")
        self._update_calibration_status(game_name)

    def _toggle_next_field(self, idx):
        if idx < MAX_FPS_FIELDS - 1:
            self.fps_fields[idx + 1].setEnabled(self.fps_fields[idx].value() > 0)
        if self.fps_fields[idx].value() == 0 and idx < MAX_FPS_FIELDS - 1:
            self.fps_fields[idx + 1].setEnabled(False)
            self.fps_fields[idx + 1].setValue(0)

    # ─── CRUD ИГР ─────────────────────────────────────
    def _add_game(self):
        if self.current_profile_id is None:
            QMessageBox.warning(self, "Ошибка", "Нет активного профиля оборудования.")
            return
        name, ok = QInputDialog.getText(self, "Добавить игру", "Название игры:")
        if ok and name.strip():
            game = name.strip()
            self.add_game_btn.setEnabled(False)
            try:
                self.db.add_game_to_profile(self.current_profile_id, game)
                self.log(
                    f"Игра '{game}' добавлена в профиль (ID={self.current_profile_id})."
                )
                self._refresh_game_list()
                for i in range(self.game_list.count()):
                    if self.game_list.item(i).text() == game:
                        self.game_list.setCurrentRow(i)
                        break
            finally:
                self.add_game_btn.setEnabled(True)

    def _edit_game(self):
        if self.current_profile_id is None:
            QMessageBox.warning(self, "Ошибка", "Нет активного профиля оборудования.")
            return
        current_item = self.game_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Ошибка", "Выберите игру для редактирования.")
            return
        # Получаем имя игры из UserRole
        old_name = current_item.data(Qt.UserRole)
        if not old_name:
            QMessageBox.warning(self, "Ошибка", "Не удалось определить название игры.")
            return
        new_name, ok = QInputDialog.getText(
            self, "Редактировать игру", "Новое название:", text=old_name
        )
        if ok and new_name.strip() and new_name.strip() != old_name:
            new_name = new_name.strip()
            try:
                self.db.rename_game_in_profile(
                    self.current_profile_id, old_name, new_name
                )
                self.log(f"Игра '{old_name}' переименована в '{new_name}'.")
                self._refresh_game_list()
                for i in range(self.game_list.count()):
                    item = self.game_list.item(i)
                    if item.data(Qt.UserRole) == new_name:
                        self.game_list.setCurrentRow(i)
                        break
            except ValueError as e:
                QMessageBox.warning(self, "Ошибка", str(e))

    def _delete_game(self):
        if self.current_profile_id is None:
            QMessageBox.warning(self, "Ошибка", "Нет активного профиля оборудования.")
            return
        current_item = self.game_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Ошибка", "Выберите игру для удаления.")
            return
        # Получаем имя игры из UserRole (а не из text())
        game_name = current_item.data(Qt.UserRole)
        if not game_name:
            QMessageBox.warning(self, "Ошибка", "Не удалось определить название игры.")
            return
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Удалить игру '{game_name}' и все её замеры?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.db.delete_game_from_profile(self.current_profile_id, game_name)
            self.log(f"Игра '{game_name}' удалена.")
            self._refresh_game_list()

    def _save_fps(self):
        if self.current_profile_id is None:
            QMessageBox.warning(self, "Ошибка", "Нет активного профиля оборудования.")
            return
        if self.game_list.currentItem() is None:
            QMessageBox.warning(self, "Ошибка", "Выберите игру из списка.")
            return
        game_name = self.game_list.currentItem().data(Qt.UserRole)
        preset = self.preset_combo.currentText()
        fps_values = [field.value() for field in self.fps_fields if field.value() > 0.0]
        if not fps_values:
            QMessageBox.warning(
                self, "Нет данных", "Введите хотя бы одно значение FPS (больше 0)."
            )
            return
        fps_str = ",".join(str(v) for v in fps_values)
        self.db.save_fps(self.current_profile_id, game_name, preset, fps_str, "Ручной ввод")
        QMessageBox.information(
            self, "Успех", f"Замеры для '{game_name}' ({preset}) сохранены."
        )
        self.log(f"Замеры сохранены: {game_name} / {preset} -> {fps_str}")
        # _load_preset_data уже вызовет _update_calibration_status
        self._load_preset_data()

    def _get_calibration_method(self, game_name):
        """Определяет метод калибровки игры на основе данных в базе."""
        self.log(f"[Calibration Method] START - game={game_name}, profile_id={self.current_profile_id}")
        
        if not game_name or self.current_profile_id is None:
            self.log("[Calibration Method] NO - No game_name or profile_id")
            return None
        
        # Сначала проверяем историю на наличие метода
        cursor = self.db.conn.cursor()
        
        # Ищем методы калибровки (не "Ручной ввод" и не "Ручная калибровка")
        # Проверяем все уникальные методы в истории
        cursor.execute(
            "SELECT DISTINCT method FROM fps_history WHERE profile_id=? AND game_name=? AND method IS NOT NULL AND method NOT IN ('Ручной ввод', 'Ручная калибровка')",
            (self.current_profile_id, game_name)
        )
        rows = cursor.fetchall()
        self.log(f"[Calibration Method] Query 1 returned {len(rows)} rows")
        if rows:
            for row in rows:
                method = row[0]
                self.log(f"[Calibration Method] Query 1 found method: {method}")
        
        if rows:
            # Если найдены методы калибровки, возвращаем первый из них
            method = rows[0][0]
            self.log(f"[Calibration Method] FOUND method: {method}")
            return method
        
        self.log("[Calibration Method] NO calibration method found, checking history data")
        
        # Если метод не указан в истории, определяем по логике:
        # - Локальная калибровка обычно сохраняет только некоторые пресеты (не все)
        # - Машинная/AI калибровка сохраняют все пресеты
        
        # Проверяем наличие данных в fps_history (основной источник)
        cursor.execute(
            "SELECT preset, fps_value FROM fps_history WHERE profile_id=? AND game_name=? ORDER BY id DESC",
            (self.current_profile_id, game_name)
        )
        history_data = cursor.fetchall()
        self.log(f"[Calibration Method] History data count: {len(history_data)}")
        
        if not history_data:
            self.log("[Calibration Method] NO DATA - No history data")
            return None
        
        # Собираем уникальные пресеты из истории
        presets_from_history = list(set(preset for preset, _ in history_data))
        has_all_presets = len(presets_from_history) >= 3
        
        self.log(f"[Calibration Method] ANALYZING - game={game_name}, presets={len(presets_from_history)}, all={presets_from_history}")
        
        # Если есть история, это калибровка (машинная или локальная)
        # Определяем по количеству пресетов
        if has_all_presets:
            self.log("[Calibration Method] RESULT: Machine calibration")
            return "Машинная калибровка"
        else:
            self.log("[Calibration Method] RESULT: Local calibration")
            return "Локальная калибровка"

    def _update_calibration_status(self, game_name):
        """Обновляет индикатор метода калибровки на основе выбранной игры."""
        self.log(f"[Calibration Status] UPDATE - game={game_name}")
        
        if not game_name:
            self.log("[Calibration Status] NO GAME - Setting 'not selected'")
            self.calibration_status.setText("Метод: не выбрана игра")
            return
        
        method = self._get_calibration_method(game_name)
        self.log(f"[Calibration Status] RESULT - method={method}")
        
        if method:
            self.log(f"[Calibration Status] UI UPDATE - label='Метод: {method}'")
            self.calibration_status.setText(f"Метод: {method}")
        else:
            self.log("[Calibration Status] UI UPDATE - label='Метод: не калибровано'")
            self.calibration_status.setText("Метод: не калибровано")

    # ─── КАЛИБРОВКА ────────────────────────────────────
    def _predict_all(self):
        if self.current_profile_id is None:
            QMessageBox.warning(self, "Ошибка", "Нет активного профиля.")
            return
        game_name = (
            self.game_list.currentItem().data(Qt.UserRole)
            if self.game_list.currentItem()
            else None
        )
        if not game_name:
            QMessageBox.warning(self, "Ошибка", "Выберите игру.")
            return

        self.log(f"=== Машинная калибровка: игра '{game_name}' ===")
        current_preset = self.preset_combo.currentText()
        entered_values = [
            field.value() for field in self.fps_fields if field.value() > 0
        ]
        if entered_values:
            existing_presets = self.db.get_presets_for_game(
                self.current_profile_id, game_name
            )
            already_saved = any(
                p == current_preset and fps_str for p, fps_str in existing_presets
            )
            if not already_saved:
                reply = QMessageBox.question(
                    self,
                    "Несохранённые данные",
                    f"В полях ввода есть значения для пресета '{current_preset}', которые ещё не сохранены.\n"
                    "Сохранить их перед расчётом?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if reply == QMessageBox.Yes:
                    self._save_fps()

        presets_data = self.db.get_presets_for_game(self.current_profile_id, game_name)
        if not presets_data:
            QMessageBox.warning(
                self, "Нет данных", "Сначала сохраните хотя бы один замер FPS."
            )
            return

        source_preset = None
        source_fps = None
        for preset, fps_str in presets_data:
            if fps_str:
                try:
                    source_fps = float(fps_str.split(",")[0].strip())
                    source_preset = preset
                    break
                except ValueError:
                    continue

        if not source_preset:
            QMessageBox.warning(
                self, "Нет данных", "Нет числового значения FPS в замерах."
            )
            return

        self.log(f"Исходный замер: {source_preset} = {source_fps} FPS")
        coeffs = {}
        if os.path.exists(PRESETS_DB_FILE):
            try:
                with open(PRESETS_DB_FILE, "r", encoding="utf-8") as f:
                    db_presets = json.load(f)
                coeffs = db_presets.get(game_name, db_presets.get("default", {}))
            except Exception:
                pass

        # Загружаем коэффициенты из файла
        coeffs = {}
        if os.path.exists(PRESETS_DB_FILE):
            try:
                with open(PRESETS_DB_FILE, "r", encoding="utf-8") as f:
                    preset_db = json.load(f)
                coeffs = preset_db.get(game_name, preset_db.get("default", {}))
                self.log(f"Коэффициенты для '{game_name}': {coeffs}")
                self.log(f"Ключи в coeffs: {list(coeffs.keys())}")  # ← добавить
                self.log(f"PRESETS список: {PRESETS}")  # ← добавить
            except Exception as e:
                self.log(f"Ошибка загрузки коэффициентов: {e}")
        else:
            self.log(f"Файл {PRESETS_DB_FILE} не найден!")  # ← добавить

        for preset in PRESETS:
            if preset == source_preset:
                fps_str = str(int(source_fps))
            else:
                # Получаем коэффициенты
                k_source = coeffs.get(source_preset)
                k_target = coeffs.get(preset)

                if k_source and k_target and k_source > 0:
                    # Рассчитываем по коэффициентам
                    predicted = (source_fps / k_source) * k_target
                    fps_str = str(int(round(predicted)))
                    self.log(
                        f"  {preset}: {source_fps} / {k_source} * {k_target} = {predicted:.1f} FPS"
                    )
                else:
                    # Если нет коэффициентов — не сохраняем
                    self.log(f"  {preset}: нет коэффициентов, пропускаем")
                    continue

            self.db.save_fps(self.current_profile_id, game_name, preset, fps_str, "Машинная калибровка")

        self.log("Машинная калибровка завершена.")
        # _load_preset_data уже вызовет _update_calibration_status
        self._load_preset_data()
        self._refresh_game_list()
        QMessageBox.information(self, "Готово", "Прогноз сохранён для всех пресетов.")

    def _ai_fill_presets(self):
        if self.current_profile_id is None:
            QMessageBox.warning(self, "Ошибка", "Нет активного профиля.")
            return
        game_name = (
            self.game_list.currentItem().data(Qt.UserRole)
            if self.game_list.currentItem()
            else None
        )
        if not game_name:
            QMessageBox.warning(self, "Ошибка", "Выберите игру.")
            return

        existing = self.db.get_presets_for_game(self.current_profile_id, game_name)
        if existing and any(fps_str for _, fps_str in existing):
            self._load_preset_data()
            QMessageBox.information(
                self, "Данные уже есть", "Прогноз уже сохранён для этой игры."
            )
            return

        from game_requirements import fetch_and_check

        settings = load_settings()
        self.log("AI-калибровка: запрос к Gemini", bold=True)
        ok, msg = fetch_and_check(
            self.db,
            self.current_profile_id,
            game_name,
            settings,
            force_provider="Gemini",
        )
        if not ok:
            QMessageBox.warning(self, "Системные требования", msg)
            return

        cursor = self.db.conn.cursor()
        cursor.execute(
            "SELECT cpu_name, gpu_name FROM hardware_profiles WHERE id=?",
            (self.current_profile_id,),
        )
        hw = cursor.fetchone()
        if not hw:
            QMessageBox.warning(self, "Ошибка", "Нет данных о железе.")
            return
        cpu = hw[0] or "Unknown CPU"
        gpu = get_search_gpu_name(hw[1])

        prompt = (
            f"Ты технический эксперт по производительности игр. "
            f"Оцени средний FPS для игры '{game_name}' на следующем оборудовании:\n"
            f"Процессор: {cpu}\nВидеокарта: {gpu}\n"
            f"Помни: чем выше настройки, тем НИЖЕ FPS. "
            f"Настройки: {', '.join(PRESETS)}.\n"
            f"Ответь СТРОГО одним JSON без текста:\n"
            f'{{"Низкие": число, "Средние": число, "Высокие": число, "Ультра": число, "Макс.": число, "Кино": число}}\n'
            f"Числа должны убывать от Низких к Кино."
        )

        self._ai_btn_original_text = self.ai_calibrate_btn.text()
        self.ai_calibrate_btn.setText("⏳ Загрузка...")
        self.ai_calibrate_btn.setEnabled(False)

        api_key = settings.get("gemini_api_key", "").strip()
        if not api_key:
            self.ai_calibrate_btn.setText(self._ai_btn_original_text)
            self.ai_calibrate_btn.setEnabled(True)
            QMessageBox.warning(self, "Ошибка", "API-ключ Gemini не указан.")
            return

        self.thread = AIFetcherThread("Gemini", prompt, settings)
        self.thread.finished.connect(self._on_ai_data_ready)
        self.thread.error.connect(self._on_ai_error)
        self.thread.start()

    def _on_ai_data_ready(self, response_text):
        self.ai_calibrate_btn.setText(self._ai_btn_original_text)
        self.ai_calibrate_btn.setEnabled(True)
        game_name = (
            self.game_list.currentItem().data(Qt.UserRole)
            if self.game_list.currentItem()
            else None
        )
        if not game_name:
            return
        try:
            match = re.search(r"\{[^}]+\}", response_text)
            data = json.loads(match.group() if match else response_text)
        except Exception as e:
            self.log(f"Ошибка парсинга ответа AI: {e}")
            QMessageBox.warning(
                self, "Ошибка", f"Не удалось распарсить ответ AI:\n{response_text}"
            )
            return

        for preset in PRESETS:
            if preset in data:
                try:
                    fps_val = float(data[preset])
                    if fps_val > 0:
                        self.db.save_fps(
                            self.current_profile_id,
                            game_name,
                            preset,
                            str(int(fps_val)),
                            "AI-калибровка (Gemini)",
                        )
                except ValueError:
                    pass

        self._load_preset_data()
        self._refresh_game_list()
        QMessageBox.information(self, "Готово", "Данные от AI сохранены.")
        self.log("AI-калибровка завершена.")

    def _on_ai_error(self, error_msg):
        self.ai_calibrate_btn.setText(self._ai_btn_original_text)
        self.ai_calibrate_btn.setEnabled(True)
        QMessageBox.warning(
            self, "Ошибка AI", f"Не удалось получить данные:\n{error_msg}"
        )

    def _delete_history_entry(self, history_id, dialog, table, row):
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            "Удалить этот замер из истории?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.db.delete_fps_history_entry(history_id)
            dialog.accept()
            self._show_history(0)
            self.log(f"Удалена запись истории ID={history_id}")

    def _show_history(self, field_index):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QDialog,
            QVBoxLayout,
            QHBoxLayout,
            QListWidget,
            QListWidgetItem,
            QLabel,
            QPushButton,
            QWidget,
        )
        from PySide6.QtGui import QPalette, QColor

        game_name = (
            self.game_list.currentItem().data(Qt.UserRole)
            if self.game_list.currentItem()
            else None
        )
        if not game_name or self.current_profile_id is None:
            return
        preset = self.preset_combo.currentText()
        history = self.db.get_fps_history(self.current_profile_id, game_name, preset)
        if not history:
            QMessageBox.information(
                self, "История", f"Нет замеров для {preset} / '{game_name}'."
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"История: {game_name} — {preset}")
        dialog.setMinimumSize(550, 400)
        dialog.resize(600, 450)

        # Тёмная тема для диалога
        dialog.setStyleSheet("""
            QDialog {
                background-color: #0D1520;
            }
            QListWidget {
                background-color: #080E18;
                border: 1px solid #1A2234;
                border-radius: 6px;
                outline: none;
                padding: 0px;
            }
            QListWidget::item {
                background-color: #080E18;
                border: none;
                margin: 0px;
                padding: 0px;
            }
            QListWidget::item:hover {
                background-color: #0D2040;
            }
            QListWidget::item:selected {
                background-color: #1A3A5A;
            }
            QPushButton {
                background-color: #0D2A1A;
                border: 1px solid #00C853;
                border-radius: 4px;
                color: #00C853;
                padding: 6px 12px;
                font-weight: bold;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #0D3A20;
                border: 1px solid #00FFCC;
                color: #00FFCC;
            }
            QLabel {
                color: #E0E6ED;
            }
            QScrollBar:vertical {
                background: #0A0F18;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #1A3A5A;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #2A5A7A;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # Устанавливаем палитру
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor(13, 21, 32))
        dark_palette.setColor(QPalette.WindowText, QColor(224, 230, 237))
        dark_palette.setColor(QPalette.Base, QColor(8, 14, 24))
        dark_palette.setColor(QPalette.Text, QColor(224, 230, 237))
        dialog.setPalette(dark_palette)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        # Заголовок с информацией
        info_label = QLabel(f"📊 История замеров: {game_name} → {preset}")
        info_label.setStyleSheet(
            "color: #00FFCC; font-weight: bold; font-size: 10pt; padding: 4px;"
        )
        layout.addWidget(info_label)

        # Список для записей истории
        list_widget = QListWidget()
        list_widget.setAlternatingRowColors(False)
        list_widget.setSelectionMode(QListWidget.NoSelection)
        list_widget.setSpacing(1)
        list_widget.setVerticalScrollMode(QListWidget.ScrollPerPixel)

        # Добавляем заголовок как отдельный элемент
        header_widget = QWidget()
        header_widget.setFixedHeight(32)
        header_widget.setStyleSheet("""
            QWidget {
                background-color: #0A1220;
                border-bottom: 1px solid #1A2234;
            }
        """)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(8, 4, 8, 4)

        num_header = QLabel("#")
        num_header.setStyleSheet("color: #00FFCC; font-weight: bold; font-size: 9pt;")
        num_header.setFixedWidth(40)

        date_header = QLabel("Дата и время")
        date_header.setStyleSheet("color: #00FFCC; font-weight: bold; font-size: 9pt;")
        date_header.setMinimumWidth(220)

        fps_header = QLabel("FPS")
        fps_header.setStyleSheet("color: #00FFCC; font-weight: bold; font-size: 9pt;")
        fps_header.setFixedWidth(60)
        fps_header.setAlignment(Qt.AlignCenter)

        action_header = QLabel("Действие")
        action_header.setStyleSheet(
            "color: #00FFCC; font-weight: bold; font-size: 9pt;"
        )
        action_header.setFixedWidth(110)

        header_layout.addWidget(num_header)
        header_layout.addWidget(date_header)
        header_layout.addWidget(fps_header)
        header_layout.addWidget(action_header)
        header_layout.addStretch()

        header_item = QListWidgetItem(list_widget)
        header_item.setSizeHint(header_widget.sizeHint())
        header_item.setFlags(Qt.NoItemFlags)
        list_widget.addItem(header_item)
        list_widget.setItemWidget(header_item, header_widget)

        # Добавляем записи истории
        for row, (hid, fps_val, timestamp) in enumerate(history):
            # Виджет строки
            row_widget = QWidget()
            row_widget.setStyleSheet("""
                QWidget {
                    background-color: #080E18;
                }
                QWidget:hover {
                    background-color: #0D2040;
                }
            """)
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(8, 6, 8, 6)

            # Номер строки
            num_label = QLabel(str(row + 1))
            num_label.setStyleSheet("color: #8892B0; font-size: 9pt;")
            num_label.setFixedWidth(40)
            num_label.setAlignment(Qt.AlignCenter)

            # Дата и время
            date_str = timestamp[:19] if timestamp else "?"
            date_label = QLabel(date_str)
            date_label.setStyleSheet("color: #CDD6F4; font-size: 9pt;")
            date_label.setMinimumWidth(220)

            # FPS
            fps_label = QLabel(str(int(fps_val)))
            fps_label.setStyleSheet(
                "color: #00FFCC; font-weight: bold; font-size: 10pt;"
            )
            fps_label.setFixedWidth(60)
            fps_label.setAlignment(Qt.AlignCenter)

            # Кнопка удаления
            del_btn = QPushButton("🗑 Удалить")
            del_btn.setFixedWidth(100)
            del_btn.setFixedHeight(28)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.clicked.connect(
                lambda checked, hid=hid: self._delete_history_entry(
                    hid, dialog, None, row
                )
            )

            row_layout.addWidget(num_label)
            row_layout.addWidget(date_label)
            row_layout.addWidget(fps_label)
            row_layout.addWidget(del_btn)
            row_layout.addStretch()

            item = QListWidgetItem(list_widget)
            item.setSizeHint(row_widget.sizeHint())
            item.setFlags(Qt.NoItemFlags)
            list_widget.addItem(item)
            list_widget.setItemWidget(item, row_widget)

        layout.addWidget(list_widget)

        # Кнопка закрытия
        close_btn = QPushButton("Закрыть")
        close_btn.setFixedWidth(120)
        close_btn.setFixedHeight(32)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(dialog.accept)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        dialog.exec()

    def _open_requirements_manager(self):
        from game_requirements import RequirementsDialog

        dlg = RequirementsDialog(self)
        dlg.exec()

    def refresh(self):
        self._load_profile()
        self._refresh_game_list()
        if hasattr(self, "current_game") and self.current_game:
            self._load_preset_data()

    def _local_calibrate(self):
        if self.current_profile_id is None:
            QMessageBox.warning(self, "Ошибка", "Нет активного профиля.")
            return
        game_name = (
            self.game_list.currentItem().data(Qt.UserRole)
            if self.game_list.currentItem()
            else None
        )
        if not game_name:
            QMessageBox.warning(self, "Ошибка", "Выберите игру.")
            return

        self.log(f"=== Локальная калибровка: '{game_name}' ===")
        existing = self.db.get_presets_for_game(self.current_profile_id, game_name)
        if existing and any(fps_str for _, fps_str in existing):
            self._load_preset_data()
            QMessageBox.information(
                self, "Данные уже есть", "Локальный прогноз уже сохранён."
            )
            return

        requirements_file = "game_requirements.json"
        if not os.path.exists(requirements_file):
            QMessageBox.warning(
                self, "Ошибка", "Файл game_requirements.json не найден."
            )
            return
        with open(requirements_file, "r", encoding="utf-8") as f:
            all_reqs = json.load(f)
        reqs = all_reqs.get(game_name)
        if not reqs:
            QMessageBox.warning(
                self,
                "Нет требований",
                f"Для '{game_name}' нет данных в базе требований.",
            )
            return

        cursor = self.db.conn.cursor()
        cursor.execute(
            "SELECT cpu_name, gpu_name, ram_total, vram_gb FROM hardware_profiles WHERE id=?",
            (self.current_profile_id,),
        )
        hw = cursor.fetchone()
        if not hw:
            QMessageBox.warning(self, "Ошибка", "Нет данных о железе.")
            return
        cpu, gpu, ram_str, vram = hw
        ram_total = psutil.virtual_memory().total / (1024**3)
        vram_val = vram if (vram and vram > 0) else 1.0

        from game_requirements import estimate_fps_from_requirements

        settings = load_settings()
        monitor_resolution = settings.get("monitor_resolution", "1920x1080")
        fps_data = estimate_fps_from_requirements(
            reqs, cpu, gpu, ram_total, vram_val, monitor_resolution
        )

        existing_presets = self.db.get_presets_for_game(
            self.current_profile_id, game_name
        )
        existing_dict = {p: fps_str for p, fps_str in existing_presets}

        for preset, fps_val in fps_data.items():
            existing_fps = existing_dict.get(preset, "")
            if not existing_fps or existing_fps in ("0", "0.0", ""):
                self.db.save_fps(
                    self.current_profile_id, game_name, preset, str(fps_val), "Локальная калибровка"
                )
                self.log(f"  {preset}: {fps_val} FPS")

        self._load_preset_data()
        self._refresh_game_list()
        QMessageBox.information(self, "Готово", "Локальный прогноз сохранён.")
        self.log("Локальная калибровка завершена.")


class AIFetcherThread(QThread):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, provider, prompt, settings):
        super().__init__()
        self.provider = provider
        self.prompt = prompt
        self.settings = settings

    def run(self):
        try:
            if self.provider == "OpenRouter":
                backend = OpenRouterBackend(self.settings.get("openrouter_api_key", ""))
            elif self.provider == "GroqCloud":
                backend = GroqCloudBackend(self.settings.get("groq_api_key", ""))
            else:
                backend = GeminiBackend(self.settings.get("gemini_api_key", ""))
            result = backend.generate(self.prompt)
            if result.startswith("Ошибка") or result.startswith("Режим отладки"):
                self.error.emit(result)
            else:
                self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
