"""
Диалог управления профилями мониторов.
Позволяет добавлять, удалять, переключать профили (разрешение + герцовка).
"""

import logging
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QLabel,
    QLineEdit,
    QSpinBox,
    QFormLayout,
    QMessageBox,
    QListWidgetItem,
)
from PySide6.QtCore import Qt

logger = logging.getLogger(__name__)


class MonitorProfilesDialog(QDialog):
    def __init__(self, settings, save_callback=None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.save_callback = save_callback  # для уведомления ui
        self.setWindowTitle("Профили мониторов")
        self.setMinimumSize(400, 400)

        self._init_ui()
        self._refresh_list()

    def _show_help(self):
        QMessageBox.about(
            self,
            "Справка: Профили мониторов",
            "📖 **Назначение:**\n"
            "Сохранение и быстрое переключение между настройками монитора.\n\n"
            "🔧 **Действия:**\n"
            "• Добавить – создать новый профиль (разрешение + герцовка).\n"
            "• Редактировать – изменить существующий профиль.\n"
            "• Удалить – удалить профиль (активный удалить нельзя).\n"
            "• Сделать активным – применить профиль (обновляет статус-бар).\n\n"
            "💡 **Совет:**\n"
            "Активный профиль применяется автоматически при запуске программы.",
        )

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Список профилей
        self.profile_list = QListWidget()
        self.profile_list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(QLabel("Сохранённые профили:"))
        layout.addWidget(self.profile_list)

        # Кнопки управления
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("➕ Добавить")
        self.add_btn.clicked.connect(self._add_profile)
        self.edit_btn = QPushButton("✏️ Редактировать")
        self.edit_btn.clicked.connect(self._edit_profile)
        self.delete_btn = QPushButton("🗑 Удалить")
        self.delete_btn.clicked.connect(self._delete_profile)
        self.activate_btn = QPushButton("✅ Сделать активным")
        self.activate_btn.clicked.connect(self._activate_profile)
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addWidget(self.activate_btn)
        layout.addLayout(btn_layout)

        # Информация об активном профиле
        self.active_label = QLabel("Активный профиль: —")
        self.active_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        layout.addWidget(self.active_label)

        # Кнопки
        help_btn = QPushButton("❓ Справка")
        help_btn.clicked.connect(self._show_help)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(help_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _refresh_list(self):
        """Обновляет список профилей из settings."""
        from settings import get_monitor_profiles

        profiles = get_monitor_profiles(self.settings)
        active_name = self.settings.get("active_monitor_profile", "")

        self.profile_list.clear()
        for p in profiles:
            name = p.get("name", "?")
            resolution = p.get("resolution", "?")
            hz = p.get("hz", "?")
            display_text = f"{name} — {resolution} @ {hz} Гц"
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, name)  # сохраняем имя профиля
            if name == active_name:
                item.setBackground(Qt.darkGreen)
                item.setToolTip("Активный профиль")
            self.profile_list.addItem(item)

        self.active_label.setText(f"Активный профиль: {active_name}")

    def _get_selected_profile_name(self):
        """Возвращает имя выбранного профиля или None."""
        current = self.profile_list.currentItem()
        if current:
            return current.data(Qt.UserRole)
        return None

    def _on_selection_changed(self):
        """Включает/выключает кнопки в зависимости от выбора."""
        has_selection = self.profile_list.currentItem() is not None
        self.edit_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)
        self.activate_btn.setEnabled(has_selection)

    def _add_profile(self):
        """Диалог добавления нового профиля."""
        dialog = ProfileEditDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        name, resolution, hz = dialog.get_data()
        if not name:
            return

        from settings import save_monitor_profile

        self.settings = save_monitor_profile(self.settings, name, resolution, hz)
        print(
            f"DEBUG: После save_monitor_profile, профилей в settings: {len(self.settings.get('monitor_profiles', []))}"
        )
        self._save_and_refresh()

    def _edit_profile(self):
        """Редактирование выбранного профиля."""
        old_name = self._get_selected_profile_name()
        if not old_name:
            return

        # Находим текущие значения
        from settings import get_monitor_profiles

        profiles = get_monitor_profiles(self.settings)
        current = None
        for p in profiles:
            if p.get("name") == old_name:
                current = p
                break
        if not current:
            return

        dialog = ProfileEditDialog(
            self, old_name, current.get("resolution", ""), current.get("hz", 60)
        )
        if dialog.exec() != QDialog.Accepted:
            return
        new_name, resolution, hz = dialog.get_data()
        if not new_name:
            return

        # Если имя изменилось — старый профиль удаляем, новый добавляем
        from settings import delete_monitor_profile, save_monitor_profile

        if new_name != old_name:
            self.settings, _ = delete_monitor_profile(self.settings, old_name)
        self.settings = save_monitor_profile(self.settings, new_name, resolution, hz)

        # Если редактируем активный профиль — обновляем активные настройки
        if self.settings.get("active_monitor_profile") == old_name:
            from settings import set_active_monitor_profile

            self.settings, _ = set_active_monitor_profile(self.settings, new_name)

        self._save_and_refresh()

    def _delete_profile(self):
        """Удаление выбранного профиля."""
        name = self._get_selected_profile_name()
        if not name:
            return

        # Защита от удаления активного профиля (функция уже проверяет)
        from settings import delete_monitor_profile

        self.settings, ok = delete_monitor_profile(self.settings, name)
        if not ok:
            QMessageBox.warning(
                self,
                "Ошибка",
                f"Нельзя удалить активный профиль '{name}'.\nСначала сделайте активным другой профиль.",
            )
            return

        self._save_and_refresh()

    def _activate_profile(self):
        """Активирует выбранный профиль."""
        name = self._get_selected_profile_name()
        if not name:
            return

        from settings import set_active_monitor_profile

        self.settings, ok = set_active_monitor_profile(self.settings, name)
        if not ok:
            QMessageBox.warning(
                self, "Ошибка", f"Не удалось активировать профиль '{name}'."
            )
            return

        self._save_and_refresh()

        # Уведомляем пользователя
        resolution = self.settings.get("monitor_resolution", "?")
        hz = self.settings.get("monitor_hz", "?")
        QMessageBox.information(
            self,
            "Профиль активирован",
            f"Активный профиль: {name}\n"
            f"Разрешение: {resolution}\n"
            f"Герцовка: {hz} Гц\n\n"
            f"При следующем запуске программы эти значения будут применены автоматически.",
        )

    def _save_and_refresh(self):
        from settings import save_settings

        save_settings(self.settings)
        if self.save_callback:
            self.save_callback()  # уведомляем ui о сохранении
        self._refresh_list()


class ProfileEditDialog(QDialog):
    """Диалог добавления/редактирования одного профиля."""

    def __init__(self, parent=None, name="", resolution="1920x1080", hz=60):
        super().__init__(parent)
        self.setWindowTitle("Профиль монитора")
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("Например: 144Hz Gaming")
        form.addRow("Название:", self.name_edit)

        self.resolution_edit = QLineEdit(resolution)
        self.resolution_edit.setPlaceholderText("1920x1080")
        form.addRow("Разрешение:", self.resolution_edit)

        self.hz_spin = QSpinBox()
        self.hz_spin.setRange(30, 360)
        self.hz_spin.setValue(hz)
        form.addRow("Герцовка (Гц):", self.hz_spin)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def get_data(self):
        return (
            self.name_edit.text().strip(),
            self.resolution_edit.text().strip(),
            self.hz_spin.value(),
        )
