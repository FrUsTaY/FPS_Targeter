"""
Редактор таблицы производительности (hardware_benchmark.json)
Позволяет просматривать, добавлять, редактировать и удалять CPU и GPU.
"""

import json
import os
import sys
import logging
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLineEdit,
    QSpinBox,
    QMessageBox,
    QHeaderView,
    QWidget,
    QFormLayout,
    QDialogButtonBox,
    QLabel,
)

logger = logging.getLogger(__name__)

# Определяем путь к файлу бенчмарков
if getattr(sys, "frozen", False):
    base_path = os.path.dirname(sys.executable)
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

BENCHMARK_FILE = os.path.join(base_path, "hardware_benchmark.json")


class BenchmarkEditor(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Редактор таблицы производительности")
        self.setMinimumSize(700, 500)

        self.benchmarks = self._load_benchmarks()
        self._init_ui()
        self._refresh_tables()

    def _show_help(self):
        QMessageBox.about(
            self,
            "Справка: Таблица производительности",
            "📖 **Назначение:**\n"
            "Хранение баллов производительности для CPU и GPU.\n"
            "Баллы используются в локальной калибровке.\n\n"
            "🔧 **Шкала баллов:**\n"
            "• GTX 1060 6GB = 100 (базовый уровень)\n"
            "• RTX 5090 = 1100 (флагман)\n"
            "• RTX 5070 = 800\n"
            "• RTX 4090 = 950\n\n"
            "💡 **Совет:**\n"
            "Добавляйте новые модели вручную или редактируйте существующие.\n"
            "Баллы должны быть относительными (чем выше, тем мощнее).\n\n"
            "📁 **Файл:** hardware_benchmark.json",
        )

    def _load_benchmarks(self):
        """Загружает текущую таблицу производительности."""
        if not os.path.exists(BENCHMARK_FILE):
            return {"cpu_benchmarks": {}, "gpu_benchmarks": {}}
        try:
            with open(BENCHMARK_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки {BENCHMARK_FILE}: {e}")
            return {"cpu_benchmarks": {}, "gpu_benchmarks": {}}

    def _save_benchmarks(self):
        """Сохраняет таблицу производительности."""
        try:
            with open(BENCHMARK_FILE, "w", encoding="utf-8") as f:
                json.dump(self.benchmarks, f, indent=2, ensure_ascii=False)
            logger.info("Таблица производительности сохранена")
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения {BENCHMARK_FILE}: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить таблицу:\n{e}")
            return False

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Вкладки CPU и GPU
        self.tabs = QTabWidget()

        # Вкладка CPU
        self.cpu_table = QTableWidget()
        self.cpu_table.setColumnCount(2)
        self.cpu_table.setHorizontalHeaderLabels(["Процессор", "Баллы"])
        self.cpu_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.cpu_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.cpu_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.cpu_table.setStyleSheet("""
            QTableWidget {
                background-color: #101A2C;
                alternate-background-color: #0D1520;
                color: #E0E6ED;
                gridline-color: #1A2234;
                selection-background-color: #1A3A5A;
                selection-color: #00FFCC;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QHeaderView::section {
                background-color: #0A1220;
                color: #8892B0;
                border: 1px solid #1A2234;
                padding: 4px;
            }
            QTableCornerButton::section {
                background-color: #0A1220;
                border: 1px solid #1A2234;
            }
        """)

        cpu_buttons = self._create_button_panel("cpu")
        cpu_widget = QWidget()
        cpu_layout = QVBoxLayout(cpu_widget)
        cpu_layout.addWidget(self.cpu_table)
        cpu_layout.addLayout(cpu_buttons)

        self.tabs.addTab(cpu_widget, "CPU")

        # Вкладка GPU
        self.gpu_table = QTableWidget()
        self.gpu_table.setColumnCount(2)
        self.gpu_table.setHorizontalHeaderLabels(["Видеокарта", "Баллы"])
        self.gpu_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.gpu_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.gpu_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.gpu_table.setStyleSheet("""
            QTableWidget {
                background-color: #101A2C;
                alternate-background-color: #0D1520;
                color: #E0E6ED;
                gridline-color: #1A2234;
                selection-background-color: #1A3A5A;
                selection-color: #00FFCC;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QHeaderView::section {
                background-color: #0A1220;
                color: #8892B0;
                border: 1px solid #1A2234;
                padding: 4px;
            }
            QTableCornerButton::section {
                background-color: #0A1220;
                border: 1px solid #1A2234;
            }
        """)

        gpu_buttons = self._create_button_panel("gpu")
        gpu_widget = QWidget()
        gpu_layout = QVBoxLayout(gpu_widget)
        gpu_layout.addWidget(self.gpu_table)
        gpu_layout.addLayout(gpu_buttons)

        self.tabs.addTab(gpu_widget, "GPU")

        layout.addWidget(self.tabs)

        # Кнопки закрытия и справки
        help_btn = QPushButton("❓ Справка")
        help_btn.clicked.connect(self._show_help)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(help_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _create_button_panel(self, tab_name):
        """Создаёт панель кнопок для вкладки."""
        layout = QHBoxLayout()

        add_btn = QPushButton("➕ Добавить")
        add_btn.clicked.connect(lambda: self._add_item(tab_name))

        edit_btn = QPushButton("✏️ Редактировать")
        edit_btn.clicked.connect(lambda: self._edit_item(tab_name))

        delete_btn = QPushButton("🗑 Удалить")
        delete_btn.clicked.connect(lambda: self._delete_item(tab_name))

        layout.addWidget(add_btn)
        layout.addWidget(edit_btn)
        layout.addWidget(delete_btn)
        layout.addStretch()

        return layout

    def _refresh_tables(self):
        """Обновляет обе таблицы."""
        self._refresh_table("cpu")
        self._refresh_table("gpu")

    def _refresh_table(self, table_type):
        """Обновляет одну таблицу."""
        if table_type == "cpu":
            table = self.cpu_table
            data = self.benchmarks.get("cpu_benchmarks", {})
        else:
            table = self.gpu_table
            data = self.benchmarks.get("gpu_benchmarks", {})

        table.setRowCount(len(data))
        for row, (name, score) in enumerate(sorted(data.items())):
            table.setItem(row, 0, QTableWidgetItem(name))
            table.setItem(row, 1, QTableWidgetItem(str(score)))

    def _get_current_item(self, table_type):
        """Возвращает выбранный элемент."""
        if table_type == "cpu":
            table = self.cpu_table
            benchmarks = self.benchmarks.get("cpu_benchmarks", {})
        else:
            table = self.gpu_table
            benchmarks = self.benchmarks.get("gpu_benchmarks", {})

        current_row = table.currentRow()
        if current_row < 0:
            return None, None

        name_item = table.item(current_row, 0)
        if not name_item:
            return None, None

        name = name_item.text()
        score = benchmarks.get(name)
        return name, score

    def _add_item(self, table_type):
        """Диалог добавления новой записи."""
        dialog = BenchmarkItemDialog(table_type, self)
        if dialog.exec() != QDialog.Accepted:
            return

        name, score = dialog.get_data()
        if not name:
            return

        if table_type == "cpu":
            benchmarks = self.benchmarks.setdefault("cpu_benchmarks", {})
        else:
            benchmarks = self.benchmarks.setdefault("gpu_benchmarks", {})

        if name in benchmarks:
            QMessageBox.warning(self, "Ошибка", f"Запись '{name}' уже существует.")
            return

        benchmarks[name] = score

        if self._save_benchmarks():
            self._refresh_table(table_type)
            logger.info(f"Добавлен {table_type.upper()}: {name} = {score}")

    def _edit_item(self, table_type):
        """Редактирование выбранной записи."""
        name, score = self._get_current_item(table_type)
        if not name:
            QMessageBox.warning(self, "Ошибка", "Выберите запись для редактирования.")
            return

        dialog = BenchmarkItemDialog(table_type, self, name, score)
        if dialog.exec() != QDialog.Accepted:
            return

        new_name, new_score = dialog.get_data()
        if not new_name:
            return

        if table_type == "cpu":
            benchmarks = self.benchmarks.get("cpu_benchmarks", {})
        else:
            benchmarks = self.benchmarks.get("gpu_benchmarks", {})

        # Если имя изменилось, удаляем старую запись
        if new_name != name:
            del benchmarks[name]

        benchmarks[new_name] = new_score

        if self._save_benchmarks():
            self._refresh_table(table_type)
            logger.info(
                f"Изменён {table_type.upper()}: {name} -> {new_name} = {new_score}"
            )

    def _delete_item(self, table_type):
        """Удаление выбранной записи."""
        name, score = self._get_current_item(table_type)
        if not name:
            QMessageBox.warning(self, "Ошибка", "Выберите запись для удаления.")
            return

        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Удалить '{name}' (баллы: {score})?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        if table_type == "cpu":
            benchmarks = self.benchmarks.get("cpu_benchmarks", {})
        else:
            benchmarks = self.benchmarks.get("gpu_benchmarks", {})

        if name in benchmarks:
            del benchmarks[name]

        if self._save_benchmarks():
            self._refresh_table(table_type)
            logger.info(f"Удалён {table_type.upper()}: {name}")


class BenchmarkItemDialog(QDialog):
    """Диалог добавления/редактирования одной записи."""

    def __init__(self, table_type, parent=None, name="", score=100):
        super().__init__(parent)
        self.table_type = table_type
        self.setWindowTitle(
            f"Добавить {table_type.upper()}"
            if not name
            else f"Редактировать {table_type.upper()}"
        )
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText(
            "Например: Intel Core i7-13700K"
            if table_type == "cpu"
            else "Например: NVIDIA GeForce RTX 4090"
        )
        form.addRow("Название:", self.name_edit)

        self.score_spin = QSpinBox()
        self.score_spin.setRange(1, 2000)
        self.score_spin.setValue(score)
        form.addRow("Баллы (1-2000):", self.score_spin)

        layout.addLayout(form)

        info_label = QLabel(
            "💡 Баллы — условная единица производительности.\n"
            "Чем выше, тем мощнее устройство.\n"
            "Рекомендуемая шкала: GTX 1060 6GB = 100, RTX 4090 = 950"
        )
        info_label.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(info_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        name = self.name_edit.text().strip()
        score = self.score_spin.value()
        return name, score
