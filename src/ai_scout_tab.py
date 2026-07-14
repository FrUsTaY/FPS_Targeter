"""
Вкладка AI Scout – запрос к ИИ на основе замеров FPS.
"""

import urllib3

from PySide6.QtCore import QTimer, QThread, Signal, Qt
from PySide6.QtGui import QGuiApplication, QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QGroupBox,
    QRadioButton,
    QButtonGroup,
    QSpinBox,
    QMessageBox,
    QFrame,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
)

from ai_engine import (
    build_prompt,
    OpenRouterBackend,
    GroqCloudBackend,
    GeminiBackend,
    AIWorker,
    get_provider_settings,
    save_provider_settings,
    PROVIDER_DEFAULTS,
)
from settings import load_settings, save_settings
from api_key_manager import APIKeyManager
from network_manager import NetworkManager

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ─────────────────────────────────────────────
#  Диалог настроек провайдера
# ─────────────────────────────────────────────
class ProviderSettingsDialog(QDialog):
    def __init__(
        self,
        provider_name: str,
        current_model: str,
        current_url: str,
        current_display_name: str,
        parent=None,
    ):
        super().__init__(parent)
        self.provider_name = provider_name
        self.setWindowTitle(f"Настройки — {provider_name}")
        self.setMinimumWidth(420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Заголовок
        title = QLabel(f"⚙️  {provider_name}")
        title.setStyleSheet("font-size: 12pt; font-weight: bold; color: #00FFCC;")
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #1A2234;")
        layout.addWidget(sep)

        form = QFormLayout()
        form.setSpacing(8)

        # ← НОВОЕ: поле отображаемого имени
        self.display_name_edit = QLineEdit(current_display_name)
        self.display_name_edit.setPlaceholderText(provider_name)
        self.display_name_edit.setToolTip(
            "Имя, которое будет отображаться на кнопке провайдера"
        )
        form.addRow("Отображаемое имя:", self.display_name_edit)

        # Поле модели
        self.model_edit = QLineEdit(current_model)
        self.model_edit.setPlaceholderText("например: deepseek/deepseek-r1:free")
        form.addRow("Модель:", self.model_edit)

        # Поле URL — скрываем для Gemini
        self.url_edit = QLineEdit(current_url)
        self.url_edit.setPlaceholderText("https://...")
        self.url_label = QLabel("URL эндпоинта:")
        if provider_name == "Cloud Gemini":
            self.url_edit.setVisible(False)
            self.url_label.setVisible(False)
        form.addRow(self.url_label, self.url_edit)

        layout.addLayout(form)

        # Подсказка с популярными моделями
        if provider_name == "OpenRouter":
            hint_text = (
                "Популярные модели OpenRouter:\n"
                "• openrouter/free — автоматически выбирает лучшую свободную\n"
                "• nvidia/nemotron-3-super-120b-a12b:free — один из самых сильных бесплатных\n"
                "• deepseek/deepseek-v4-flash:free — отличный reasoning + кодинг\n"
                "• google/gemma-4-31b-it:free — хороший баланс скорость/качество\n"
                "• meta-llama/llama-4-scout:free — быстрый и универсальный"
            )
        elif provider_name == "GroqCloud":
            hint_text = (
                "Популярные модели GroqCloud:\n"
                "• llama-3.3-70b-versatile — лучший баланс качество/скорость\n"
                "• meta-llama/llama-4-scout-17b-16e-instruct — новая и очень хорошая\n"
                "• llama-3.1-8b-instant — максимальная скорость + высокие лимиты\n"
                "• openai/gpt-oss-120b — большая модель"
            )
        elif provider_name == "Cloud Gemini":
            hint_text = (
                "Популярные модели Gemini:\n"
                "• gemini-3.1-flash-lite — универсальный ежедневный чат, скорость\n"
                "• gemini-2.5-flash — универсальные задачи, хорошее качество\n"
                "• gemini-2.5-pro — сложные задачи, reasoning, кодинг\n"
                "• gemini-3.1-pro-preview — максимальное качество, сложные рассуждения\n"
                "• gemini-3.5-flash — новейшая, экспериментальная"
            )
        else:
            hint_text = ""

        if hint_text:
            hint = QLabel(hint_text)
            hint.setTextInteractionFlags(
                Qt.TextSelectableByMouse
            )  # ← добавляем выделение
            hint.setStyleSheet(
                "color: #8892B0; font-size: 8pt;"
                "background: #060B14; border: 1px solid #1A2234;"
                "border-radius: 4px; padding: 6px;"
            )
            layout.addWidget(hint)

        # Кнопка «Сбросить по умолчанию»
        reset_btn = QPushButton("↺ Сбросить по умолчанию")
        reset_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            "color: #8892B0; font-size: 8pt; text-align: left; padding: 0; }"
            "QPushButton:hover { color: #00FFCC; }"
        )
        reset_btn.clicked.connect(self._reset_defaults)
        layout.addWidget(reset_btn)

        # Кнопки OK / Отмена
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Применить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _reset_defaults(self):
        defaults = PROVIDER_DEFAULTS.get(self.provider_name, {})
        self.model_edit.setText(defaults.get("model",""))
        self.url_edit.setText(defaults.get("api_url",""))

    @property
    def model(self):
        return self.model_edit.text().strip()

    @property
    def api_url(self):
        return self.url_edit.text().strip()

    @property
    def display_name(self):
        return self.display_name_edit.text().strip() or self.provider_name


# ─────────────────────────────────────────────
#  Кнопка провайдера
# ─────────────────────────────────────────────
class ProviderButton(QPushButton):
    ICONS = {
        "OpenRouter":"🔀 ",
        "GroqCloud":"⚡ ",
        "Cloud Gemini":"✨ ",
    }

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.name = name
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(34)
        self.setMinimumWidth(120)
        self.setText(f"{self.ICONS.get(name, '🤖 ')}{name}")
        self._update_style(False)

    def set_active(self, active: bool):
        self.setChecked(active)
        self._update_style(active)

    def _update_style(self, checked: bool):
        if checked:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #0D2A3A;
                    border: 1px solid #00FFCC;
                    border-radius: 6px;
                    color: #00FFCC;
                    font-weight: bold;
                    font-size: 10pt;
                    text-align: left;
                    padding-left: 12px;
                }
                QPushButton:hover {
                    background-color: #0D3A4A;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #0A1520;
                    border: 1px solid #2A3A4A;
                    border-radius: 6px;
                    color: #8892B0;
                    font-size: 10pt;
                    text-align: left;
                    padding-left: 12px;
                }
                QPushButton:hover {
                    border: 1px solid #4A6A8A;
                    background-color: #0D1A2A;
                    color: #B8C7E7;
                }
            """)


# ─────────────────────────────────────────────
#  Основная вкладка
# ─────────────────────────────────────────────
class AIScoutTab(QWidget):
    def __init__(self, db, log_func=None, status_func=None):
        super().__init__()
        self.db = db
        self.log = log_func if log_func else print
        self.status_func = status_func
        self.settings = load_settings()
        self.worker = None
        self.current_profile_id = None
        self.current_ai_type = "OpenRouter"
        self.is_network_ok = False
        self.api_manager = APIKeyManager()
        self.network_manager = NetworkManager()
        self._init_ui()
        self.log("AI Scout инициализирован, начальная проверка сети...")
        QTimer.singleShot(
            50, lambda: self.set_ai_status("loading","Статус ИИ: Проверка связи...")
        )
        QTimer.singleShot(0, self._async_check_network)
        # Загружаем ответ для текущего провайдера после загрузки игр
        QTimer.singleShot(1500, self._load_response_for_current_model)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── Строка: Игра + FPS + Герцовка ─────────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        game_lbl = QLabel("Игра:")
        game_lbl.setStyleSheet("color: #8892B0;")
        self.game_combo = QComboBox()
        self.game_combo.setMaxVisibleItems(10)
        self.game_combo.currentTextChanged.connect(self._on_game_selected)
        self.game_combo.setStyleSheet("""
            QComboBox {
                background-color: #101A2C;
                border: 1px solid #1A2234;
                border-radius: 4px;
                padding: 4px 8px;
                color: #FFFFFF;
                min-width: 140px;
            }
            QComboBox:focus { border: 1px solid #00FFCC; }
            QComboBox QAbstractItemView {
                background-color: #101A2C;
                border: 1px solid #1A2234;
                color: #FFFFFF;
                selection-background-color: #1A3A5A;
                selection-color: #00FFCC;
            }
        """)
        top_row.addWidget(game_lbl)
        top_row.addWidget(self.game_combo)

        fps_lbl = QLabel("Целевой FPS:")
        fps_lbl.setStyleSheet("color: #8892B0;")
        self.target_fps_slider = QSpinBox()
        self.target_fps_slider.setRange(30, 240)
        self.target_fps_slider.setValue(self.settings.get("target_fps", 165))
        self.target_fps_slider.setFixedWidth(70)
        self.target_fps_slider.valueChanged.connect(self._save_sliders)
        top_row.addWidget(fps_lbl)
        top_row.addWidget(self.target_fps_slider)

        hz_lbl = QLabel("Монитор (Гц):")
        hz_lbl.setStyleSheet("color: #8892B0;")
        self.monitor_hz_slider = QSpinBox()
        self.monitor_hz_slider.setRange(60, 360)
        self.monitor_hz_slider.setValue(self.settings.get("monitor_hz", 165))
        self.monitor_hz_slider.setFixedWidth(70)
        self.monitor_hz_slider.valueChanged.connect(self._save_sliders)
        self.auto_hz_btn = QPushButton("🌐")
        self.auto_hz_btn.setFixedWidth(32)
        self.auto_hz_btn.setToolTip("Автоопределение герцовки монитора")
        self.auto_hz_btn.clicked.connect(self._auto_detect_hz)
        top_row.addWidget(hz_lbl)
        top_row.addWidget(self.monitor_hz_slider)
        top_row.addWidget(self.auto_hz_btn)
        top_row.addStretch()
        layout.addLayout(top_row)

        # ── Провайдеры — кнопка + шестерёнка рядом ────────
        providers_row = QHBoxLayout()
        providers_row.setSpacing(4)

        self._provider_buttons = {}
        self._provider_group = QButtonGroup(self)

        for name in ["OpenRouter","GroqCloud","Cloud Gemini"]:
            # Загружаем сохранённое отображаемое имя
            ps = get_provider_settings(self.settings, name)
            display_name = ps.get("display_name", name)

            btn = ProviderButton(name)
            # Переопределяем текст кнопки, если есть сохранённое имя
            if display_name != name:
                icon = ProviderButton.ICONS.get(name, "🤖")
                btn.setText(f"{icon}{display_name}")
                btn.display_name = display_name
            btn.clicked.connect(lambda checked, n=name: self._on_provider_clicked(n))
            self._provider_buttons[name] = btn
            self._provider_group.addButton(btn)
            providers_row.addWidget(btn)

            # Кнопка ⚙️ рядом с провайдером
            gear_btn = QPushButton("⚙")
            gear_btn.setFixedSize(28, 34)
            gear_btn.setToolTip(f"Настройки модели {name}")
            gear_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0A1520;
                    border: 1px solid #2A3A4A;
                    border-radius: 6px;
                    color: #8892B0;
                    font-size: 12px;
                    padding: 0;
                }
                QPushButton:hover {
                    border: 1px solid #00FFCC;
                    color: #00FFCC;
                    background-color: #0D1A2A;
                }
            """)
            gear_btn.clicked.connect(
                lambda checked, n=name: self._open_provider_settings(n)
            )
            providers_row.addWidget(gear_btn)

            # Небольшой отступ между провайдерами
            providers_row.addSpacing(6)

        providers_row.addStretch()
        layout.addLayout(providers_row)
        self._provider_buttons["OpenRouter"].set_active(True)

        # ── Текущая модель (информационная строка) ─────────
        self._model_info_lbl = QLabel()
        self._model_info_lbl.setStyleSheet(
            "color: #8892B0; font-size: 8pt; font-style: italic;"
        )
        layout.addWidget(self._model_info_lbl)
        self._update_model_info_label()

        # ── Настройки API ──────────────────────────────────
        self.api_group = QGroupBox("API ключ")
        api_layout = QVBoxLayout(self.api_group)
        api_layout.setContentsMargins(8, 14, 8, 8)

        self.openrouter_widget = QWidget()
        or_layout = QVBoxLayout(self.openrouter_widget)
        or_layout.setContentsMargins(0, 0, 0, 0)
        self.openrouter_token_edit = QLineEdit(self.settings.get("openrouter_api_key", ""))
        self.openrouter_token_edit.setEchoMode(QLineEdit.Password)
        self.openrouter_token_edit.setPlaceholderText("Вставьте API ключ OpenRouter...")
        self.openrouter_token_edit.textChanged.connect(self._save_api_keys)
        or_layout.addWidget(self.openrouter_token_edit)

        self.groq_widget = QWidget()
        groq_layout = QVBoxLayout(self.groq_widget)
        groq_layout.setContentsMargins(0, 0, 0, 0)
        self.groq_token_edit = QLineEdit(self.settings.get("groq_api_key", ""))
        self.groq_token_edit.setEchoMode(QLineEdit.Password)
        self.groq_token_edit.setPlaceholderText("Вставьте API ключ GroqCloud...")
        self.groq_token_edit.textChanged.connect(self._save_api_keys)
        groq_layout.addWidget(self.groq_token_edit)

        self.gemini_widget = QWidget()
        gemini_layout = QVBoxLayout(self.gemini_widget)
        gemini_layout.setContentsMargins(0, 0, 0, 0)
        self.gemini_key_edit = QLineEdit(self.settings.get("gemini_api_key", ""))
        self.gemini_key_edit.setEchoMode(QLineEdit.Password)
        self.gemini_key_edit.setPlaceholderText("Вставьте API ключ Gemini...")
        self.gemini_key_edit.textChanged.connect(self._save_api_keys)
        gemini_layout.addWidget(self.gemini_key_edit)

        api_layout.addWidget(self.openrouter_widget)
        api_layout.addWidget(self.groq_widget)
        api_layout.addWidget(self.gemini_widget)
        self.groq_widget.setVisible(False)
        self.gemini_widget.setVisible(False)
        layout.addWidget(self.api_group)

        # ── Кнопка сброса API-настроек ───────────────────────
        reset_api_btn = QPushButton("↺ Сбросить все настройки AI")
        reset_api_btn.setFixedHeight(36)
        reset_api_btn.setStyleSheet("""
            QPushButton {
                background-color: #1A1A2A;
                border: 1px solid #FF6D00;
                border-radius: 6px;
                color: #FF6D00;
                font-size: 9pt;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #2A1A0A;
                border: 1px solid #FFB74D;
                color: #FFFFFF;
            }
        """)
        reset_api_btn.clicked.connect(self._reset_api_settings)
        layout.addWidget(reset_api_btn)

        # ── Кнопка отправки + статус ───────────────────────
        send_row = QHBoxLayout()
        self.send_btn = QPushButton("  🤖  Отправить запрос ИИ")
        self.send_btn.setFixedHeight(36)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #0D2A3A;
                border: 1px solid #00FFCC;
                border-radius: 6px;
                color: #00FFCC;
                font-weight: bold;
                font-size: 10pt;
                padding: 4px 16px;
            }
            QPushButton:hover {
                background-color: #0D3A4A;
                border: 1px solid #00FFE5;
                color: #FFFFFF;
            }
            QPushButton:disabled {
                background-color: #0A1520;
                border: 1px solid #1A2234;
                color: #3A4A5A;
            }
        """)
        self.send_btn.clicked.connect(self._send_request)

        # Кнопка справки по моделям
        self.help_btn = QPushButton("❓ Справка по моделям")
        self.help_btn.setFixedHeight(36)
        self.help_btn.setStyleSheet("""
            QPushButton {
                background-color: #0A1520;
                border: 1px solid #2A3A4A;
                border-radius: 6px;
                color: #8892B0;
                font-size: 9pt;
                padding: 4px 12px;
            }
            QPushButton:hover {
                border: 1px solid #00FFCC;
                color: #00FFCC;
                background-color: #0D1A2A;
            }
        """)
        self.help_btn.clicked.connect(self._show_models_help)

        self.network_led = QLabel("●")
        self.network_led.setStyleSheet("color: #3A4A5A; font-size: 14px;")
        self.network_led.setFixedWidth(20)
        self.network_led.installEventFilter(self)

        self._status_lbl = QLabel("Проверка связи...")
        self._status_lbl.setStyleSheet("color: #8892B0; font-size: 8pt;")

        send_row.addWidget(self.send_btn)
        send_row.addWidget(self.help_btn)
        send_row.addWidget(self.network_led)
        send_row.addWidget(self._status_lbl)
        send_row.addStretch()
        layout.addLayout(send_row)

        # ── Область ответа ─────────────────────────────────
        response_lbl = QLabel("▸ Ответ ИИ")
        response_lbl.setStyleSheet("color: #00FFCC; font-weight: bold; font-size: 9pt;")
        layout.addWidget(response_lbl)

        self.response_area = QTextEdit()
        self.response_area.setReadOnly(True)
        self.response_area.setPlaceholderText("Ответ от ИИ появится здесь...")
        self.response_area.setFont(QFont("Segoe UI", 9))
        self.response_area.setStyleSheet("""
            QTextEdit {
                background-color: #060B14;
                border: 1px solid #1A2234;
                border-radius: 6px;
                color: #CDD6F4;
                padding: 8px;
            }
        """)
        layout.addWidget(self.response_area, stretch=1)

        # Совместимость
        self.radio_openrouter = QRadioButton()
        self.radio_openrouter.setChecked(True)
        self.radio_openrouter.setVisible(False)
        self.radio_groq = QRadioButton()
        self.radio_groq.setVisible(False)
        self.radio_gemini = QRadioButton()
        self.radio_gemini.setVisible(False)
        self.provider_group = QButtonGroup(self)
        self.provider_group.addButton(self.radio_openrouter, 0)
        self.provider_group.addButton(self.radio_groq, 1)
        self.provider_group.addButton(self.radio_gemini, 2)

    # ── Настройки провайдера ───────────────────────────────
    def _open_provider_settings(self, provider_name: str):
        """Открывает диалог настройки модели, URL и отображаемого имени провайдера."""
        self.settings = load_settings()
        ps = get_provider_settings(self.settings, provider_name)

        dlg = ProviderSettingsDialog(
            provider_name,
            current_model=ps["model"],
            current_url=ps["api_url"],
            current_display_name=ps.get("display_name", provider_name),  # ← добавлено
            parent=self,
        )
        if dlg.exec() == QDialog.Accepted:
            self.settings = save_provider_settings(
                self.settings, provider_name, dlg.model, dlg.api_url, dlg.display_name
            )
            save_settings(self.settings)
            self._update_provider_button_text(
                provider_name, dlg.display_name
            )  # ← обновить кнопку
            self._update_model_info_label()
            self.log(
                f"[AI Scout] {provider_name}: отображаемое имя → {dlg.display_name}"
            )
            self.log(f"[AI Scout] {provider_name}: модель → {dlg.model}")
            if dlg.api_url:
                self.log(f"[AI Scout] {provider_name}: URL → {dlg.api_url}")

    def _update_model_info_label(self):
        """Обновляет информационную строку с текущей моделью."""
        ps = get_provider_settings(self.settings, self.current_ai_type)
        model = ps.get("model","—")
        self._model_info_lbl.setText(f"Модель: {model}")

    def _update_provider_button_text(self, provider_name: str, new_display_name: str):
        """Обновляет текст на кнопке провайдера."""
        btn = self._provider_buttons.get(provider_name)
        if btn:
            icon = ProviderButton.ICONS.get(provider_name, "🤖")
            btn.setText(f"{icon}{new_display_name}")
            # Сохраняем новое имя для будущих обновлений
            btn.display_name = new_display_name

    # ── Выбор провайдера ───────────────────────────────────
    def _on_provider_clicked(self, name):
        for n, btn in self._provider_buttons.items():
            btn.set_active(n == name)
        self.current_ai_type = name
        self.openrouter_widget.setVisible(name == "OpenRouter")
        self.groq_widget.setVisible(name == "GroqCloud")
        self.gemini_widget.setVisible(name == "Cloud Gemini")
        self.radio_openrouter.setChecked(name == "OpenRouter")
        self.radio_groq.setChecked(name == "GroqCloud")
        self.radio_gemini.setChecked(name == "Cloud Gemini")
        self.settings["ai_provider"] = name
        save_settings(self.settings)
        self._update_model_info_label()
        self.log(f"AI Scout: провайдер → {name}")
        self._load_response_for_current_model()
        self._async_check_network()

    def _toggle_provider(self):
        if self.radio_openrouter.isChecked():
            self._on_provider_clicked("OpenRouter")
        elif self.radio_groq.isChecked():
            self._on_provider_clicked("GroqCloud")
        elif self.radio_gemini.isChecked():
            self._on_provider_clicked("Cloud Gemini")

    # ── Запрос к AI ────────────────────────────────────────
    def _send_request(self):
        if self.worker is not None and self.worker.isRunning():
            return
        if not self.current_profile_id:
            self.log("Нет активного профиля.")
            return
        if not self.is_network_ok:
            self.log(
                "ВНИМАНИЕ: Проверка сети показала недоступность, но пробуем отправить запрос..."
            )
            # Не возвращаем, а продолжаем
        self.set_ai_status("loading","Отправка запроса...")

        game = self.game_combo.currentText()
        if not game:
            return

        from game_requirements import fetch_and_check

        ok, msg = fetch_and_check(self.db, self.current_profile_id, game, self.settings)
        if not ok:
            QMessageBox.warning(self, "Системные требования", msg)
            return

        target_fps = self.target_fps_slider.value()
        monitor_hz = self.monitor_hz_slider.value()
        ai_type = self.current_ai_type

        prompt, _ = build_prompt(
            self.db, self.current_profile_id, game, target_fps, monitor_hz, ai_type
        )
        if not prompt:
            return

        self.settings["gemini_api_key"] = self.gemini_key_edit.text()
        self.settings["openrouter_api_key"] = self.openrouter_token_edit.text()
        self.settings["groq_api_key"] = self.groq_token_edit.text()
        save_settings(self.settings)

        # Получаем актуальные модель и URL из настроек
        ps = get_provider_settings(self.settings, ai_type)
        model = ps["model"]
        api_url = ps["api_url"]

        if ai_type == "OpenRouter":
            token = self.openrouter_token_edit.text().strip()
            if not token:
                self.log("API-ключ OpenRouter не указан.")
                return
            backend = OpenRouterBackend(token, model=model, api_url=api_url)
        elif ai_type == "GroqCloud":
            token = self.groq_token_edit.text().strip()
            if not token:
                self.log("API-ключ GroqCloud не указан.")
                return
            backend = GroqCloudBackend(token, model=model, api_url=api_url)
        else:
            api_key = self.gemini_key_edit.text().strip()
            if not api_key:
                self.log("API-ключ Gemini не указан.")
                return
            backend = GeminiBackend(api_key, model=model)

        self.log(f"Запрос: {ai_type} / {model}")
        self._send_btn_original_text = self.send_btn.text()
        self.send_btn.setText("⏳  Ожидание ответа...")
        self.send_btn.setEnabled(False)
        self.response_area.clear()

        self.worker = AIWorker(
            backend, prompt, self.db, self.current_profile_id, game, ai_type
        )
        self.worker.finished.connect(self._on_response)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_response(self, text):
        self.response_area.setPlainText(text)
        self.send_btn.setText(self._send_btn_original_text)
        self.send_btn.setEnabled(True)
        self.worker = None
        if text.startswith("Режим отладки:") or text.startswith("Ошибка"):
            self.set_ai_status("error","Ошибка сети / блокировка")
        else:
            self.set_ai_status("ok","AI доступен")
            if self.current_profile_id:
                game = self.game_combo.currentText()
                # Сохраняем в столбец (для быстрого доступа)
                self.db.save_ai_response_for_game(
                    self.current_profile_id, game, text, self.current_ai_type
                )
                # Сохраняем в таблицу ai_responses (для экспорта/импорта)
                self.db.save_ai_response(
                    self.current_profile_id, game, self.current_ai_type, text
                )
                self.log(
                    f"СОХРАНЁН ответ для {game} / {self.current_ai_type}, длина {len(text)}"
                )

    def _on_error(self, err):
        msg = (
            "Gemini недоступен без VPN."
            if "CERTIFICATE_VERIFY_FAILED" in err
            else f"Ошибка: {err}"
        )
        self.response_area.setPlainText(msg)
        self.send_btn.setText(self._send_btn_original_text)
        self.send_btn.setEnabled(True)
        self.worker = None
        self.set_ai_status("error","Ошибка сети / блокировка")

    # ── Утилиты ────────────────────────────────────────────
    def cleanup(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(2000)
        self.worker = None

    def refresh(self):
        current_game = self.game_combo.currentText()
        self.current_profile_id = None
        self._load_games()
        if current_game:
            idx = self.game_combo.findText(current_game)
            if idx >= 0:
                self.game_combo.setCurrentIndex(idx)

    def _load_games(self):
        self.current_profile_id = self.db.get_current_profile_id()
        if not self.current_profile_id:
            self.game_combo.clear()
            self.response_area.clear()
            return
        games = self.db.get_games_for_profile(self.current_profile_id)
        self.game_combo.blockSignals(True)
        self.game_combo.clear()
        self.game_combo.addItems(games)
        self.game_combo.blockSignals(False)
        if games:
            self.game_combo.setCurrentIndex(0)
        else:
            self.response_area.clear()
        # После загрузки игр загружаем ответ
        if self.current_profile_id and self.game_combo.currentText():
            self._load_response_for_current_model()

    def _on_game_selected(self, game_name):
        if not game_name or not self.current_profile_id:
            self.response_area.clear()
            return
        self._load_response_for_current_model()

    def _auto_detect_hz(self):
        from hardware import HardwarePassport

        hw = HardwarePassport()
        info = hw.get_display_info()
        hz = info.get("hz", 0)
        if hz > 0:
            self.monitor_hz_slider.setValue(hz)
            self.log(f"Герцовка: {hz} Гц")

    def _async_check_network(self):
        """Проверка сети через централизованный менеджер."""
        provider = self.current_ai_type
        api_key = self.api_manager.get_key(provider)
        
        if not api_key:
            self.is_network_ok = False
            self.set_ai_status("error", f"API-ключ {provider} не указан")
            return
        
        def on_check_complete(ok, message):
            self.is_network_ok = ok
            self.log(f"Сеть: {'OK' if ok else 'НЕДОСТУПЕН'} ({message})")
            self.set_ai_status("ok" if ok else "error", message)
        
        self.network_manager.check_network(provider, api_key, on_check_complete)



    def set_ai_status(self, state, message=None):
        colors = {"loading":"#FFC107","ok":"#00FFCC","error":"#F44336"}
        color = colors.get(state, "#3A4A5A")
        self.network_led.setStyleSheet(f"color: {color}; font-size: 14px;")
        self._status_lbl.setText(message or "")
        self._status_lbl.setStyleSheet(f"color: {color}; font-size: 8pt;")
        if message and self.status_func:
            self.status_func(message)

    def update_led_style(self, state):
        colors = {"green":"#00FFCC","red":"#F44336","gray":"#3A4A5A"}
        self.network_led.setStyleSheet(
            f"color: {colors.get(state, '#3A4A5A')}; font-size: 14px;"
        )

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent

        if obj == self.network_led:
            if event.type() in (QEvent.Enter, QEvent.Leave):
                return True
        return super().eventFilter(obj, event)

    def _save_sliders(self):
        self.settings["target_fps"] = self.target_fps_slider.value()
        self.settings["monitor_hz"] = self.monitor_hz_slider.value()
        save_settings(self.settings)

    def _save_api_keys(self):
        """Сохраняет текущие ключи через менеджер."""
        self.api_manager.set_key("OpenRouter", self.openrouter_token_edit.text())
        self.api_manager.set_key("GroqCloud", self.groq_token_edit.text())
        self.api_manager.set_key("Cloud Gemini", self.gemini_key_edit.text())
        self.log("API-ключи сохранены через менеджер")

    def set_target_fps(self, value):
        self.target_fps_slider.setValue(value)

    def _load_response_for_current_model(self):
        game = self.game_combo.currentText()
        if not game or not self.current_profile_id:
            self.response_area.clear()
            return
        response = self.db.get_ai_response_for_game(
            self.current_profile_id, game, self.current_ai_type
        )
        self.response_area.setPlainText(response if response else "")

    def _show_models_help(self):
        """Показывает диалог со способами просмотра доступных моделей."""
        from PySide6.QtWidgets import (
            QDialog,
            QVBoxLayout,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QFrame,
        )

        dialog = QDialog(self)
        dialog.setWindowTitle("🔍 Как посмотреть доступные модели AI")
        dialog.setMinimumWidth(550)
        dialog.setMinimumHeight(450)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        # Заголовок
        title = QLabel("📋 Способы получения списка моделей")
        title.setStyleSheet("font-size: 13pt; font-weight: bold; color: #00FFCC;")
        layout.addWidget(title)

        # Разделитель
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #1A2234;")
        layout.addWidget(sep)

        # Получаем API-ключи из настроек
        gemini_key = self.settings.get("gemini_api_key","")
        openrouter_key = self.settings.get("openrouter_api_key","")
        groq_key = self.settings.get("groq_api_key","")

        # ─────────────────────────────────────────
        # 1. OpenRouter
        # ─────────────────────────────────────────
        or_group = QFrame()
        or_group.setStyleSheet("""
            QFrame {
                background-color: #060B14;
                border: 1px solid #1A2234;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        or_layout = QVBoxLayout(or_group)

        or_title = QLabel("🔀 OpenRouter")
        or_title.setStyleSheet("font-weight: bold; color: #00FFCC; font-size: 10pt;")
        or_layout.addWidget(or_title)

        or_link = QLabel("📖 Сайт со списком моделей: https://openrouter.ai/models")
        or_link.setStyleSheet("color: #8892B0; font-size: 9pt;")
        or_link.setTextInteractionFlags(Qt.TextSelectableByMouse)
        or_layout.addWidget(or_link)

        if openrouter_key:
            or_cmd = f'curl -X GET "https://openrouter.ai/api/v1/models" -H"Authorization: Bearer {openrouter_key}"'
            or_cmd_filtered = f'curl -X GET "https://openrouter.ai/api/v1/models?min_price=0" -H"Authorization: Bearer {openrouter_key}"'

            or_cmd_btn = QPushButton("📋 Скопировать команду (все модели)")
            or_cmd_btn.setToolTip(
                "Копирует команду curl для получения ВСЕХ доступных моделей OpenRouter\nВыполните её в терминале (PowerShell / cmd)"
            )
            or_cmd_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0A1520;
                    border: 1px solid #2A3A4A;
                    border-radius: 4px;
                    color: #8892B0;
                    font-size: 8pt;
                    padding: 4px 8px;
                }
                QPushButton:hover {
                    border: 1px solid #00FFCC;
                    color: #00FFCC;
                }
            """)
            or_cmd_btn.clicked.connect(
                lambda: self._copy_to_clipboard(or_cmd, "OpenRouter")
            )

            or_cmd_filtered_btn = QPushButton(
                "📋 Скопировать команду (только бесплатные)"
            )
            or_cmd_filtered_btn.setToolTip(
                "Копирует команду curl для получения ТОЛЬКО БЕСПЛАТНЫХ моделей OpenRouter\nВыполните её в терминале (PowerShell / cmd)"
            )
            or_cmd_filtered_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0A1520;
                    border: 1px solid #2A3A4A;
                    border-radius: 4px;
                    color: #8892B0;
                    font-size: 8pt;
                    padding: 4px 8px;
                }
                QPushButton:hover {
                    border: 1px solid #00FFCC;
                    color: #00FFCC;
                }
            """)
            or_cmd_filtered_btn.clicked.connect(
                lambda: self._copy_to_clipboard(
                    or_cmd_filtered, "OpenRouter (бесплатные)"
                )
            )

            or_btn_row = QHBoxLayout()
            or_btn_row.addWidget(or_cmd_btn)
            or_btn_row.addWidget(or_cmd_filtered_btn)
            or_btn_row.addStretch()
            or_layout.addLayout(or_btn_row)
        else:
            or_no_key = QLabel(
                "⚠️ API-ключ OpenRouter не указан. Добавьте ключ в поле выше."
            )
            or_no_key.setStyleSheet("color: #F44336; font-size: 8pt;")
            or_layout.addWidget(or_no_key)

        layout.addWidget(or_group)

        # ─────────────────────────────────────────
        # 2. GroqCloud
        # ─────────────────────────────────────────
        groq_group = QFrame()
        groq_group.setStyleSheet("""
            QFrame {
                background-color: #060B14;
                border: 1px solid #1A2234;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        groq_layout = QVBoxLayout(groq_group)

        groq_title = QLabel("⚡ GroqCloud")
        groq_title.setStyleSheet("font-weight: bold; color: #00FFCC; font-size: 10pt;")
        groq_layout.addWidget(groq_title)

        groq_link = QLabel(
            "📖 Сайт со списком моделей: https://console.groq.com/docs/models"
        )
        groq_link.setStyleSheet("color: #8892B0; font-size: 9pt;")
        groq_link.setTextInteractionFlags(Qt.TextSelectableByMouse)
        groq_layout.addWidget(groq_link)

        if groq_key:
            groq_cmd = f'curl -X GET "https://api.groq.com/openai/v1/models" -H"Authorization: Bearer {groq_key}"'

            groq_cmd_btn = QPushButton("📋 Скопировать команду curl")
            groq_cmd_btn.setToolTip(
                "Копирует команду curl для получения списка доступных моделей GroqCloud\nВыполните её в терминале (PowerShell / cmd)"
            )
            groq_cmd_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0A1520;
                    border: 1px solid #2A3A4A;
                    border-radius: 4px;
                    color: #8892B0;
                    font-size: 8pt;
                    padding: 4px 8px;
                }
                QPushButton:hover {
                    border: 1px solid #00FFCC;
                    color: #00FFCC;
                }
            """)
            groq_cmd_btn.clicked.connect(
                lambda: self._copy_to_clipboard(groq_cmd, "GroqCloud")
            )
            groq_layout.addWidget(groq_cmd_btn)
        else:
            groq_no_key = QLabel(
                "⚠️ API-ключ GroqCloud не указан. Добавьте ключ в поле выше."
            )
            groq_no_key.setStyleSheet("color: #F44336; font-size: 8pt;")
            groq_layout.addWidget(groq_no_key)

        layout.addWidget(groq_group)

        # ─────────────────────────────────────────
        # 3. Cloud Gemini
        # ─────────────────────────────────────────
        gemini_group = QFrame()
        gemini_group.setStyleSheet("""
            QFrame {
                background-color: #060B14;
                border: 1px solid #1A2234;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        gemini_layout = QVBoxLayout(gemini_group)

        gemini_title = QLabel("✨ Google Gemini")
        gemini_title.setStyleSheet(
            "font-weight: bold; color: #00FFCC; font-size: 10pt;"
        )
        gemini_layout.addWidget(gemini_title)

        if gemini_key:
            gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini_key}"

            gemini_link = QLabel(
                "🔗 Ссылка для просмотра моделей (нажмите Ctrl+C или скопируйте кнопкой)"
            )
            gemini_link.setStyleSheet("color: #8892B0; font-size: 9pt;")
            gemini_link.setWordWrap(True)
            gemini_layout.addWidget(gemini_link)

            gemini_url_display = QLabel(f"{gemini_url[:80]}...")
            gemini_url_display.setStyleSheet(
                "color: #4A6A8A; font-size: 8pt; font-family: monospace;"
            )
            gemini_url_display.setWordWrap(True)
            gemini_layout.addWidget(gemini_url_display)

            btn_row = QHBoxLayout()

            gemini_copy_btn = QPushButton("📋 Копировать ссылку")
            gemini_copy_btn.setToolTip(
                "Копирует прямую ссылку с вашим API-ключом\nВставьте её в браузер, чтобы увидеть список доступных моделей Gemini"
            )
            gemini_copy_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0A1520;
                    border: 1px solid #2A3A4A;
                    border-radius: 4px;
                    color: #8892B0;
                    font-size: 8pt;
                    padding: 4px 8px;
                }
                QPushButton:hover {
                    border: 1px solid #00FFCC;
                    color: #00FFCC;
                }
            """)
            gemini_copy_btn.clicked.connect(
                lambda: self._copy_to_clipboard(gemini_url, "Gemini URL")
            )

            gemini_open_btn = QPushButton("🌐 Открыть в браузере")
            gemini_open_btn.setToolTip(
                "Открывает ссылку с вашим API-ключом прямо в браузере\nСписок доступных моделей Gemini откроется сразу"
            )
            gemini_open_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0A1520;
                    border: 1px solid #2A3A4A;
                    border-radius: 4px;
                    color: #8892B0;
                    font-size: 8pt;
                    padding: 4px 8px;
                }
                QPushButton:hover {
                    border: 1px solid #00FFCC;
                    color: #00FFCC;
                }
            """)
            gemini_open_btn.clicked.connect(lambda: self._open_url(gemini_url))

            btn_row.addWidget(gemini_copy_btn)
            btn_row.addWidget(gemini_open_btn)
            btn_row.addStretch()
            gemini_layout.addLayout(btn_row)
        else:
            gemini_no_key = QLabel(
                "⚠️ API-ключ Gemini не указан. Добавьте ключ в поле выше."
            )
            gemini_no_key.setStyleSheet("color: #F44336; font-size: 8pt;")
            gemini_layout.addWidget(gemini_no_key)

        layout.addWidget(gemini_group)

        # ─────────────────────────────────────────
        # Информационная подсказка
        # ─────────────────────────────────────────
        info_label = QLabel(
            "💡 **Примечание:**\n"
            "• Команды curl можно выполнить в терминале (PowerShell, cmd, bash)\n"
            "• Для работы curl в Windows он должен быть установлен (встроен в Win10/11)\n"
            "• Ответ приходит в формате JSON — можно просмотреть в любом текстовом редакторе"
        )
        info_label.setStyleSheet("color: #8892B0; font-size: 8pt;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Кнопка закрытия
        close_btn = QPushButton("Закрыть")
        close_btn.setFixedHeight(32)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #0D2A3A;
                border: 1px solid #00FFCC;
                border-radius: 6px;
                color: #00FFCC;
                font-weight: bold;
                font-size: 9pt;
                padding: 4px 16px;
            }
            QPushButton:hover {
                background-color: #0D3A4A;
                color: #FFFFFF;
            }
        """)
        close_btn.clicked.connect(dialog.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        dialog.exec()

    def _copy_to_clipboard(self, text: str, name: str):
        """Копирует текст в буфер обмена и показывает уведомление."""
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(text)
        self.log(f"📋 Команда для {name} скопирована в буфер обмена")

        # Временное сообщение в статус-бар
        if self.status_func:
            self.status_func(f"Скопировано: {name}")

    def _open_url(self, url: str):
        """Открывает URL в браузере."""
        import webbrowser

        webbrowser.open(url)
        self.log(f"🌐 Открыт URL: {url[:60]}...")

    def _reset_api_settings(self):
        """Сбрасывает все API-ключи к значениям по умолчанию."""
        self.api_manager.reset_all()
        
        # Обновляем UI
        self.gemini_key_edit.setText("")
        self.openrouter_token_edit.setText("")
        self.groq_token_edit.setText("")
        
        self.log("↺ Все API-ключи сброшены")
        QMessageBox.information(self, "Сброс настроек", "Все API-ключи успешно сброшены.")


# === Устаревшие классы (оставлены для обратной совместимости) ===
# В ФАЗЕ 4 перенесены в network_manager.py
        super().__init__()
        self.provider = provider
        self.api_key = api_key

    def run(self):
        if self.provider == "OpenRouter":
            ok, message = OpenRouterBackend.check_connection(self.api_key)
        elif self.provider == "GroqCloud":
            ok, message = GroqCloudBackend.check_connection(self.api_key)
        elif self.provider == "Cloud Gemini":
            ok, message = GeminiBackend.check_connection(self.api_key)
        else:
            ok, message = False, "Неизвестный провайдер"
        self.result.emit(ok, message)
