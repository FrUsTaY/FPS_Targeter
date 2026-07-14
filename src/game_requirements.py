"""
Модуль управления системными требованиями игр.
Объединяет функциональность:
- Работа с базой требований (game_requirements.json)
- Расчёт FPS по требованиям
- Проверка требований через AI (OpenRouter/GroqCloud/Gemini)
"""

import json
import os
import sys
import re
import logging
import psutil

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QListWidget,
    QTextEdit,
    QLineEdit,
    QSpinBox,
    QCheckBox,
    QMessageBox,
    QFormLayout,
    QGroupBox,
    QComboBox,
)

# Определяем путь к файлам
if getattr(sys, "frozen", False):
    base_path = os.path.dirname(sys.executable)
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

REQUIREMENTS_FILE = os.path.join(base_path, "game_requirements.json")
REQUIREMENTS_CACHE = os.path.join(base_path, "game_requirements_ai.json")
BENCHMARK_FILE = os.path.join(base_path, "hardware_benchmark.json")

PRESETS_COEFFICIENTS = {
    "Низкие": 1.0,
    "Средние": 0.85,
    "Высокие": 0.7,
    "Ультра": 0.55,
    "Макс.": 0.4,
    "Кино": 0.3,
}

logger = logging.getLogger("GameRequirements")


def extract_first_cpu(cpu_string: str) -> str:
    """Извлекает первое название CPU из строки вида 'Intel i5-10400, AMD Ryzen 5 3600'."""
    if not cpu_string:
        return ""
    parts = re.split(r"[,/&]|\s+или\s+", cpu_string)
    if parts:
        return parts[0].strip()
    return cpu_string.strip()


def extract_first_gpu(gpu_string: str) -> str:
    """Извлекает первое название GPU из строки вида 'NVIDIA GTX 1060, AMD RX 580'."""
    if not gpu_string:
        return ""
    parts = re.split(r"[,/&]|\s+или\s+", gpu_string)
    if parts:
        return parts[0].strip()
    return gpu_string.strip()


def parse_steam_requirements_text(text: str) -> dict:
    """Извлекает из копированного блока Steam поля требований."""
    reqs = {
        "min_cpu": "",
        "min_gpu": "",
        "min_ram_gb": 0,
        "min_vram_gb": 0,
        "requires_hardware_rt": False,
    }
    lines = text.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("процессор"):
            cpu = re.sub(r"^процессор\s*:?\s*", "", line, flags=re.IGNORECASE).strip()
            if cpu:
                reqs["min_cpu"] = cpu
        elif line.lower().startswith("видеокарта"):
            gpu = re.sub(r"^видеокарта\s*:?\s*", "", line, flags=re.IGNORECASE).strip()
            if gpu:
                reqs["min_gpu"] = gpu
                vram_match = re.findall(r"(\d+)\s*GB", gpu, re.IGNORECASE)
                if vram_match:
                    reqs["min_vram_gb"] = int(vram_match[0])
        elif "озу" in line.lower() or "оперативная память" in line.lower():
            ram_match = re.search(r"(\d+)\s*GB", line, re.IGNORECASE)
            if ram_match:
                reqs["min_ram_gb"] = int(ram_match.group(1))
        if re.search(r"ray\s*tracing", line, re.IGNORECASE) or "RT" in line:
            reqs["requires_hardware_rt"] = True
    if reqs["min_vram_gb"] == 0:
        reqs["min_vram_gb"] = 1
    return reqs


def load_benchmarks():
    """Загружает таблицу производительности."""
    if not os.path.exists(BENCHMARK_FILE):
        return {"cpu_benchmarks": {}, "gpu_benchmarks": {}}
    with open(BENCHMARK_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_name(name: str) -> str:
    """Нормализует название CPU/GPU для поиска."""
    if not name:
        return ""
    name = name.lower()
    name = re.sub(r"intel\(r\)\s*core\(tm\)\s*", "", name)
    name = re.sub(r"amd\s*", "", name)
    name = re.sub(r"nvidia\s*", "", name)
    name = re.sub(r"geforce\s*", "", name)
    name = re.sub(r"radeon\s*", "", name)
    name = re.sub(r"graphics\s*", "", name)
    name = re.sub(r"@\s*\d+\.?\d*\s*ghz", "", name)
    name = re.sub(r"\d+\.?\d*\s*ghz", "", name)
    name = " ".join(name.split())
    return name


def get_cpu_score(cpu_name: str) -> int:
    """Возвращает балл CPU. С поддержкой эвристики и нормализации."""
    benchmarks = load_benchmarks().get("cpu_benchmarks", {})
    if not cpu_name:
        return 100

    if cpu_name in benchmarks:
        logger.debug(f"CPU точное совпадение: {cpu_name} = {benchmarks[cpu_name]}")
        return benchmarks[cpu_name]

    normalized = normalize_name(cpu_name)
    for key, score in benchmarks.items():
        key_norm = normalize_name(key)
        if key_norm == normalized:
            logger.debug(
                f"CPU совпадение после нормализации: '{cpu_name}' -> {key} = {score}"
            )
            return score

    patterns = [
        r"(i\d+-\d+[KF]*)",
        r"(ryzen\s*\d+\s*\d*[X]*\d*)",
        r"(r\d+\s*\d+[X]*\d*)",
        r"(athlon\s*\d+)",
        r"(pentium\s*\d+)",
        r"(celeron\s*\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            search_key = match.group(1)
            for key, score in benchmarks.items():
                if search_key in normalize_name(key):
                    logger.debug(
                        f"CPU частичное совпадение: '{cpu_name}' -> {key} = {score}"
                    )
                    return score

    logger.warning(
        f"CPU '{cpu_name}' не найден в базе, используется значение по умолчанию 100"
    )
    return 100


def get_gpu_score(gpu_name: str) -> int:
    """Возвращает балл GPU. С поддержкой эвристики и нормализации."""
    benchmarks = load_benchmarks().get("gpu_benchmarks", {})
    if not gpu_name:
        return 80

    if gpu_name in benchmarks:
        logger.debug(f"GPU точное совпадение: {gpu_name} = {benchmarks[gpu_name]}")
        return benchmarks[gpu_name]

    normalized = normalize_name(gpu_name)
    for key, score in benchmarks.items():
        key_norm = normalize_name(key)
        if key_norm == normalized:
            logger.debug(
                f"GPU совпадение после нормализации: '{gpu_name}' -> {key} = {score}"
            )
            return score

    patterns = [
        r"(rtx\s*\d+\s*[a-z]*)",
        r"(gtx\s*\d+\s*[a-z]*)",
        r"(rx\s*\d+\s*[a-z]*)",
        r"(radeon\s*\d+\s*[a-z]*)",
        r"(intel\s*arc\s*\w+\s*\d*)",
        r"(iris\s*xe\s*\w*)",
        r"(uhd\s*graphics\s*\d*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            search_key = match.group(1)
            for key, score in benchmarks.items():
                if search_key in normalize_name(key):
                    logger.debug(
                        f"GPU частичное совпадение: '{gpu_name}' -> {key} = {score}"
                    )
                    return score

    logger.warning(
        f"GPU '{gpu_name}' не найден в базе, используется значение по умолчанию 80"
    )
    return 80


def estimate_fps_from_requirements(
    reqs: dict,
    cpu_name: str,
    gpu_name: str,
    ram_gb: float,
    vram_gb: float,
    resolution: str = "1920x1080",
) -> dict:
    """
    Вычисляет прогноз FPS для всех пресетов на основе сравнения железа с минималками.
    resolution: разрешение монитора (например, "1920x1080") влияет на нагрузку GPU.
    Возвращает словарь {пресет: fps (int)}.
    """
    min_cpu_raw = reqs.get("min_cpu", "")
    min_gpu_raw = reqs.get("min_gpu", "")
    min_cpu = extract_first_cpu(min_cpu_raw)
    min_gpu = extract_first_gpu(min_gpu_raw)

    logger.debug(f"Извлечён CPU: '{min_cpu_raw}' -> '{min_cpu}'")
    logger.debug(f"Извлечён GPU: '{min_gpu_raw}' -> '{min_gpu}'")
    min_ram = reqs.get("min_ram_gb", 0)
    min_vram = reqs.get("min_vram_gb", 0)

    cpu_score_user = get_cpu_score(cpu_name)
    cpu_score_min = get_cpu_score(min_cpu) if min_cpu else 60

    gpu_score_user = get_gpu_score(gpu_name)
    gpu_score_min = get_gpu_score(min_gpu) if min_gpu else 50

    cpu_ratio = max(0.1, cpu_score_user / cpu_score_min) if cpu_score_min > 0 else 1.0
    gpu_ratio = max(0.1, gpu_score_user / gpu_score_min) if gpu_score_min > 0 else 1.0

    try:
        width = int(resolution.split("x")[0]) if "x" in resolution else 1920
    except Exception:
        width = 1920
    resolution_factor = max(0.3, min(1.5, (1920 / width) ** 0.7))

    base_fps_low = 30 * cpu_ratio * gpu_ratio * resolution_factor

    ram_factor = max(0.6, min(1.2, ram_gb / min_ram)) if min_ram > 0 else 1.0
    vram_factor = max(0.5, min(1.2, vram_gb / min_vram)) if min_vram > 0 else 1.0
    base_fps_low *= (ram_factor * vram_factor) ** 0.5

    fps_presets = {}
    for preset, coeff in PRESETS_COEFFICIENTS.items():
        fps = max(1, int(base_fps_low * coeff + 0.5))
        fps_presets[preset] = fps
    return fps_presets


class RequirementsManager:
    def __init__(self):
        self.filepath = REQUIREMENTS_FILE
        self.data = {}
        self.load()

    def game_exists(self, game_name: str) -> bool:
        """Проверяет, существует ли игра в базе требований."""
        return game_name in self.data

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}
        else:
            self.data = {}

    def save(self):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def get_games(self):
        return list(self.data.keys())

    def get_requirements(self, game: str):
        return self.data.get(game)

    def add_or_update(self, game: str, reqs: dict):
        self.data[game] = reqs
        self.save()

    def delete(self, game: str):
        if game in self.data:
            del self.data[game]
            self.save()


class AddEditRequirementDialog(QDialog):
    """Диалог добавления/редактирования требований одной игры."""

    def __init__(self, game_name="", reqs=None):
        super().__init__()
        self.setWindowTitle("Системные требования")
        self.setMinimumWidth(600)
        self.reqs = reqs if reqs else {}
        self.game_name = game_name

        layout = QVBoxLayout(self)
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Игра:"))
        self.game_edit = QLineEdit(game_name)
        name_layout.addWidget(self.game_edit)
        layout.addLayout(name_layout)

        layout.addWidget(
            QLabel("Вставьте сюда скопированный блок системных требований из Steam:")
        )
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText(
            "64-разрядные процессор и операционная система\nОС: Windows 10\nПроцессор: ...\n..."
        )
        layout.addWidget(self.text_edit)

        self.parse_btn = QPushButton("Автозаполнить поля из текста")
        self.parse_btn.clicked.connect(self._parse_text)
        layout.addWidget(self.parse_btn)

        form_group = QGroupBox("Параметры требований")
        form = QFormLayout()
        self.cpu_edit = QLineEdit(self.reqs.get("min_cpu", ""))
        self.gpu_edit = QLineEdit(self.reqs.get("min_gpu", ""))
        self.ram_spin = QSpinBox()
        self.ram_spin.setRange(0, 256)
        self.ram_spin.setValue(self.reqs.get("min_ram_gb", 0))
        self.vram_spin = QSpinBox()
        self.vram_spin.setRange(0, 128)
        self.vram_spin.setValue(self.reqs.get("min_vram_gb", 0))
        self.rt_check = QCheckBox()
        self.rt_check.setChecked(self.reqs.get("requires_hardware_rt", False))

        self.genre_combo = QComboBox()
        self.genre_combo.addItems(
            [
                "",
                "Action",
                "RPG",
                "Strategy",
                "Simulation",
                "Adventure",
                "Puzzle",
                "Platformer",
                "Racing",
                "Shooter",
                "Horror",
            ]
        )
        current_genre = self.reqs.get("genre", "")
        index = self.genre_combo.findText(current_genre)
        if index >= 0:
            self.genre_combo.setCurrentIndex(index)
        else:
            self.genre_combo.setCurrentIndex(0)

        form.addRow("Мин. процессор:", self.cpu_edit)
        form.addRow("Мин. видеокарта:", self.gpu_edit)
        form.addRow("Мин. ОЗУ (ГБ):", self.ram_spin)
        form.addRow("Мин. VRAM (ГБ):", self.vram_spin)
        form.addRow("Требует RT:", self.rt_check)
        form.addRow("Жанр:", self.genre_combo)
        form_group.setLayout(form)
        layout.addWidget(form_group)

        help_btn = QPushButton("❓ Справка")
        help_btn.clicked.connect(self._show_help)
        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)

        btn_box = QHBoxLayout()
        btn_box.addWidget(help_btn)
        btn_box.addStretch()
        btn_box.addWidget(save_btn)
        btn_box.addWidget(cancel_btn)
        layout.addLayout(btn_box)

    def _show_help(self):
        QMessageBox.about(
            self,
            "Справка: Системные требования",
            "📖 **Поля:**\n"
            "• Игра – название (обязательно).\n"
            "• Мин. процессор – например: Intel Core i5-8400.\n"
            "• Мин. видеокарта – например: NVIDIA GTX 1060 6GB.\n"
            "• Мин. ОЗУ (ГБ) – рекомендуемый объём.\n"
            "• Мин. VRAM (ГБ) – видеопамять.\n"
            "• Требует RT – аппаратная трассировка лучей.\n"
            "• Жанр – влияет на рекомендацию целевого FPS.\n\n"
            "💡 **Автозаполнение:**\n"
            "Вставьте скопированные требования из Steam и нажмите «Автозаполнить».",
        )

    def _parse_text(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            return
        parsed = parse_steam_requirements_text(text)
        self.cpu_edit.setText(parsed.get("min_cpu", ""))
        self.gpu_edit.setText(parsed.get("min_gpu", ""))
        self.ram_spin.setValue(parsed.get("min_ram_gb", 0))
        self.vram_spin.setValue(parsed.get("min_vram_gb", 0))
        self.rt_check.setChecked(parsed.get("requires_hardware_rt", False))

    def _save(self):
        game = self.game_edit.text().strip()
        if not game:
            QMessageBox.warning(self, "Ошибка", "Введите название игры.")
            return
        self.game_name = game
        genre = self.genre_combo.currentText()
        if genre == "":
            genre = None
        self.reqs = {
            "min_cpu": self.cpu_edit.text().strip(),
            "min_gpu": self.gpu_edit.text().strip(),
            "min_ram_gb": self.ram_spin.value(),
            "min_vram_gb": self.vram_spin.value(),
            "requires_hardware_rt": self.rt_check.isChecked(),
        }
        if genre:
            self.reqs["genre"] = genre
        self.accept()


class RequirementsDialog(QDialog):
    """Основное окно управления базой требований."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("База системных требований")
        self.setMinimumSize(500, 400)
        self.manager = RequirementsManager()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Список игр в базе:"))
        self.list_widget = QListWidget()
        self._refresh_list()
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Добавить")
        add_btn.clicked.connect(self._add_game)
        edit_btn = QPushButton("Редактировать")
        edit_btn.clicked.connect(self._edit_game)
        del_btn = QPushButton("Удалить")
        del_btn.clicked.connect(self._delete_game)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(edit_btn)
        btn_layout.addWidget(del_btn)
        layout.addLayout(btn_layout)

        help_btn = QPushButton("❓ Справка")
        help_btn.clicked.connect(self._show_help)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.close)

        btn_help_layout = QHBoxLayout()
        btn_help_layout.addWidget(help_btn)
        btn_help_layout.addStretch()
        btn_help_layout.addWidget(close_btn)
        layout.addLayout(btn_help_layout)

    def _show_help(self):
        QMessageBox.about(
            self,
            "Справка: База системных требований",
            "📖 **Назначение:**\n"
            "Хранение минимальных системных требований для игр.\n\n"
            "🔧 **Действия:**\n"
            "• Добавить – создание новой игры с требованиями.\n"
            "• Редактировать – изменение существующих требований.\n"
            "• Удалить – удаление игры из базы.\n\n"
            "🎮 **Как жанр влияет на рекомендацию целевого FPS:**\n"
            "При первом выборе игры во вкладке «Управление» программа предлагает целевой FPS на основе:\n"
            "1. Герцовка монитора – базовое значение.\n"
            "2. Производительность железа (баллы CPU/GPU, объём VRAM).\n"
            "3. Жанр игры – для следующих жанров FPS ограничивается до 60:\n"
            "   • RPG, Strategy, Simulation, Adventure, Puzzle, Platformer\n\n"
            "💡 **Почему?** В этих жанрах высокий FPS не даёт игрового преимущества, а нагрузка на железо снижается.\n\n"
            "📌 **Важно:** Рекомендация предлагается ТОЛЬКО для игр, добавленных в базу требований.\n"
            "Если игры нет в базе — рекомендация не выдаётся.\n\n"
            "💡 **Совет:**\n"
            "Используйте Ctrl+Shift+R для быстрого добавления требований из буфера обмена (Steam).\n\n"
            "📁 **Файл:** game_requirements.json",
        )

    def _refresh_list(self):
        self.list_widget.clear()
        games = self.manager.get_games()
        self.list_widget.addItems(games)

    def _add_game(self):
        dlg = AddEditRequirementDialog()
        if dlg.exec() == QDialog.Accepted:
            game = dlg.game_name
            reqs = dlg.reqs
            self.manager.add_or_update(game, reqs)
            self._refresh_list()

    def _edit_game(self):
        current = self.list_widget.currentItem()
        if not current:
            QMessageBox.warning(self, "Ошибка", "Выберите игру для редактирования.")
            return
        game = current.text()
        reqs = self.manager.get_requirements(game)
        dlg = AddEditRequirementDialog(game, reqs)
        if dlg.exec() == QDialog.Accepted:
            new_game = dlg.game_name
            if new_game != game:
                self.manager.delete(game)
            self.manager.add_or_update(new_game, dlg.reqs)
            self._refresh_list()

    def _delete_game(self):
        current = self.list_widget.currentItem()
        if not current:
            QMessageBox.warning(self, "Ошибка", "Выберите игру для удаления.")
            return
        game = current.text()
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Удалить '{game}' из базы требований?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.manager.delete(game)
            self._refresh_list()


def fetch_and_check(db, profile_id, game_name, settings, force_provider=None):
    """Проверяет соответствие железа системным требованиям игры через выбранный ИИ."""
    logger.info(f"Проверка требований для '{game_name}' (профиль {profile_id})...")
    cursor = db.conn.cursor()
    cursor.execute(
        "SELECT cpu_name, gpu_name, ram_total, vram_gb FROM hardware_profiles WHERE id=?",
        (profile_id,),
    )
    hw = cursor.fetchone()
    if not hw:
        logger.warning("Данные профиля не найдены, считаем требования пройденными.")
        return True, ""
    cpu, gpu, ram_str, vram = hw
    ram_total = psutil.virtual_memory().total / (1024**3)
    logger.info(f"Железо: CPU={cpu}, GPU={gpu}, RAM={ram_total:.1f} ГБ, VRAM={vram}")

    cache = {}
    if os.path.exists(REQUIREMENTS_CACHE):
        try:
            with open(REQUIREMENTS_CACHE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            logger.info(f"Кэш требований загружен: {len(cache)} записей.")
        except Exception as e:
            logger.warning(f"Ошибка чтения кэша требований: {e}")
    else:
        logger.info("Файл кэша требований не найден.")

    cache_key = f"{game_name}__profile_{profile_id}"
    logger.info(f"Ключ кэша: {cache_key}")

    if cache_key not in cache:
        logger.info(f"Требования для '{game_name}' отсутствуют в кэше, запрос к AI...")
        provider = force_provider if force_provider else settings.get("ai_provider", "")
        logger.info(
            f"Выбранный провайдер из настроек: {provider if provider else 'не задан'}"
        )
        if not provider:
            if settings.get("gemini_api_key", "").strip():
                provider = "Gemini"
            elif settings.get("openrouter_api_key", "").strip():
                provider = "OpenRouter"
            elif settings.get("groq_api_key", "").strip():
                provider = "GroqCloud"
            else:
                logger.error("Нет ни одного API-ключа для проверки требований.")
                return (
                    False,
                    "Невозможно проверить системные требования: нет ни одного API-ключа.\nДобавьте ключ во вкладке AI Scout.",
                )
            logger.info(f"Автоматически выбран провайдер: {provider}")
        if provider == "Gemini" and not settings.get("gemini_api_key", "").strip():
            logger.error("API-ключ Gemini отсутствует.")
            return (
                False,
                "Для проверки требований нужен API-ключ Gemini. Добавьте его в AI Scout.",
            )
        if (
            provider == "OpenRouter"
            and not settings.get("openrouter_api_key", "").strip()
        ):
            logger.error("API-ключ OpenRouter отсутствует.")
            return (
                False,
                "Для проверки требований нужен API-ключ OpenRouter. Добавьте его в AI Scout.",
            )
        if provider == "GroqCloud" and not settings.get("groq_api_key", "").strip():
            logger.error("API-ключ GroqCloud отсутствует.")
            return (
                False,
                "Для проверки требований нужен API-ключ GroqCloud. Добавьте его в AI Scout.",
            )

        if provider == "OpenRouter":
            from ai_engine import OpenRouterBackend

            backend = OpenRouterBackend(settings.get("openrouter_api_key", ""))
        elif provider == "GroqCloud":
            from ai_engine import GroqCloudBackend

            backend = GroqCloudBackend(settings.get("groq_api_key", ""))
        else:
            from ai_engine import GeminiBackend

            backend = GeminiBackend(settings.get("gemini_api_key", ""))

        prompt = (
            f"Найди официальные минимальные системные требования (ПК, Steam) для игры '{game_name}'.\n"
            f"Ответ должен быть СТРОГО в формате JSON без каких-либо дополнительных слов:\n"
            f'{{"min_cpu":"строка","min_gpu":"строка","min_ram_gb":число,"min_vram_gb":число,"requires_hardware_rt":true/false}}\n'
            f"Пример:\n"
            f'{{"min_cpu":"Intel Core i3-2100","min_gpu":"NVIDIA GeForce GTX 650","min_ram_gb":4,"min_vram_gb":1,"requires_hardware_rt":false}}\n'
            f"Если требования не найдены, верни ровно {{}} (пустой объект)."
        )
        logger.info(f"Отправка запроса к {provider} для получения требований...")
        logger.info(f"Промпт (первые 200 символов): {prompt[:200]}...")
        response = backend.generate(prompt)
        logger.info(f"Получен ответ длиной {len(response)} символов.")
        try:
            reqs = json.loads(response)
        except Exception:
            match = re.search(r"\{[^{}]*\}", response)
            if match:
                try:
                    reqs = json.loads(match.group())
                    logger.info("JSON извлечён с помощью регулярного выражения.")
                except Exception as e:
                    logger.warning(f"Не удалось распарсить JSON после извлечения: {e}")
                    reqs = {}
            else:
                logger.warning("JSON не найден в ответе.")
                reqs = {}

        logger.info(f"Извлечённые требования: {reqs}")
        if not reqs:
            logger.warning(f"Пустой ответ для '{game_name}', требования не кэшируются.")
            return True, ""
        logger.info(
            f"Требования для '{game_name}' (профиль {profile_id}) получены от {provider}: {reqs}"
        )
        cache[cache_key] = reqs
        with open(REQUIREMENTS_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
        logger.info("Кэш требований обновлён.")
    else:
        logger.info(f"Требования для '{game_name}' загружены из кэша.")
        reqs = cache[cache_key]

    if not reqs:
        return True, ""

    logger.info("Сравнение железа с минимальными требованиями...")
    issues = []
    min_ram = reqs.get("min_ram_gb", 0)
    if ram_total < min_ram:
        issues.append(f"ОЗУ: {ram_total:.1f} ГБ (требуется {min_ram} ГБ)")
        logger.warning(f"ОЗУ не проходит: {ram_total:.1f} < {min_ram}")

    effective_vram = vram if (vram and vram > 0) else 1.0
    min_vram = reqs.get("min_vram_gb", 0)
    if effective_vram < min_vram:
        issues.append(f"Видеопамять: {effective_vram:.1f} ГБ (требуется {min_vram} ГБ)")
        logger.warning(f"VRAM не проходит: {effective_vram:.1f} < {min_vram}")

    if reqs.get("requires_hardware_rt") and gpu:
        gpu_lower = gpu.lower()
        has_rt = any(
            tag in gpu_lower
            for tag in ["rtx", "rx 6", "rx 7", "radeon rx 6", "radeon rx 7"]
        )
        if not has_rt:
            issues.append(
                "Видеокарта не поддерживает аппаратную трассировку лучей (RT)"
            )
            logger.warning("Требуется RT, но видеокарта не поддерживает.")

    if issues:
        logger.warning(f"Требования не выполнены: {issues}")
        return False, "Не соответствует системным требованиям:\n" + "\n".join(issues)
    logger.info("Все системные требования выполнены.")
    return True, ""
