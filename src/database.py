"""
Модуль базы данных SQLite для FPS Targeter (v2.3)
Добавлены: таблица ai_responses, методы сохранения/получения ответов ИИ,
поле vram_gb в hardware_profiles для динамического использования в промптах.
"""

import sqlite3
import os
import json

DEFAULT_GAME_PRESETS = {
    "default": {
        "Ультра": 1.0,
        "Высокие": 1.3,
        "Средние": 1.6,
        "Низкие": 2.1,
        "Макс.": 0.9,
        "Кино": 0.75
    }
}

def ensure_game_presets():
    """Создаёт файл game_presets_db.json со стандартными коэффициентами, если его нет."""
    # Определяем папку, где находится .exe или .py
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    presets_path = os.path.join(base_path, "game_presets_db.json")
    if not os.path.exists(presets_path):
        try:
            with open(presets_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_GAME_PRESETS, f, indent=2, ensure_ascii=False)
            logger.info("Создан стандартный game_presets_db.json")
        except Exception as e:
            logger.error(f"Не удалось создать game_presets_db.json: {e}")
import logging
import sys

logger = logging.getLogger("Database")
DB_NAME = "fps_data.db"


class Database:
    def __init__(self, db_path=None):
        if db_path is None:
            # Определяем папку, где находится .exe
            if getattr(sys, "frozen", False):
                # Запущено из .exe
                base_path = os.path.dirname(sys.executable)
            else:
                # Запущено из скрипта
                base_path = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_path, DB_NAME)
            logger.info(f"Путь к БД: {db_path}")
        logger.info(f"Путь к БД: {db_path}")
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()
        self._migrate()
        logger.info("База данных (v2.3) инициализирована.")
        # Создаём файл пресетов, если его нет
        ensure_game_presets()

    def get_profile_uuid(self, profile_id: int) -> str | None:
        """Возвращает UUID профиля по его ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT uuid FROM hardware_profiles WHERE id=?", (profile_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def find_profile_by_uuid(self, uuid: str) -> int | None:
        """Находит ID профиля по UUID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM hardware_profiles WHERE uuid=?", (uuid,))
        row = cursor.fetchone()
        return row[0] if row else None

    def _create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hardware_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT UNIQUE,
                cpu_name TEXT NOT NULL,
                gpu_name TEXT,
                ram_total TEXT,
                vram_gb REAL DEFAULT 8.0,
                is_current INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS games_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL,
                game_name TEXT NOT NULL,
                preset TEXT NOT NULL,
                fps_results TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (profile_id) REFERENCES hardware_profiles(id) ON DELETE CASCADE,
                UNIQUE(profile_id, game_name, preset)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fps_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL,
                game_name TEXT NOT NULL,
                preset TEXT NOT NULL,
                fps_value REAL NOT NULL,
                method TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (profile_id) REFERENCES hardware_profiles(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL,
                game_name TEXT NOT NULL,
                ai_type TEXT NOT NULL,
                response_text TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (profile_id) REFERENCES hardware_profiles(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS game_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL,
                game_name TEXT NOT NULL,
                target_fps INTEGER DEFAULT 60,
                recommendation_dismissed INTEGER DEFAULT 0,
                FOREIGN KEY (profile_id) REFERENCES hardware_profiles(id) ON DELETE CASCADE,
                UNIQUE(profile_id, game_name)
            )
        """)
        self.conn.commit()

    def _migrate(self):
        """Миграции базы данных."""
        cursor = self.conn.cursor()

        # Миграция: добавляем колонку uuid, если её нет
        cursor.execute("PRAGMA table_info(hardware_profiles)")
        cols = [col[1] for col in cursor.fetchall()]
        if "uuid" not in cols:
            cursor.execute("ALTER TABLE hardware_profiles ADD COLUMN uuid TEXT UNIQUE")
            # Генерируем UUID для существующих профилей
            cursor.execute("SELECT id, cpu_name, gpu_name FROM hardware_profiles")
            profiles = cursor.fetchall()
            for pid, cpu, gpu in profiles:
                import hashlib

                unique_str = f"{cpu}_{gpu}_{pid}"
                uuid_val = hashlib.md5(unique_str.encode()).hexdigest()[:16]
                cursor.execute(
                    "UPDATE hardware_profiles SET uuid=? WHERE id=?", (uuid_val, pid)
                )

        # Удаляем дубликаты в games_data перед добавлением UNIQUE
        cursor.execute("""
            DELETE FROM games_data 
            WHERE id NOT IN (
                SELECT MIN(id) 
                FROM games_data 
                GROUP BY profile_id, game_name, preset
            )
        """)
        self.conn.commit()

        # Добавляем UNIQUE ограничение, если его нет
        cursor.execute("PRAGMA index_list('games_data')")
        indexes = [row[2] for row in cursor.fetchall() if row[2]]
        if "sqlite_autoindex_games_data_1" not in indexes:
            try:
                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_game_preset 
                    ON games_data (profile_id, game_name, preset)
                """)
                self.conn.commit()
                logger.info("Миграция: добавлено уникальное ограничение для games_data")
            except sqlite3.OperationalError as e:
                logger.warning(f"Не удалось добавить уникальное ограничение: {e}")

            self.conn.commit()
            logger.info("Миграция: добавлена колонка uuid в hardware_profiles")

        # Добавляем колонку vram_gb, если её нет (для старых баз)
        cursor.execute("PRAGMA table_info(hardware_profiles)")
        cols = [col[1] for col in cursor.fetchall()]
        if "vram_gb" not in cols:
            cursor.execute(
                "ALTER TABLE hardware_profiles ADD COLUMN vram_gb REAL DEFAULT 8.0"
            )
            self.conn.commit()
            logger.info("Миграция: добавлена колонка vram_gb в hardware_profiles")

        # Миграция для ответов ИИ — добавляем колонки для каждого провайдера
        cursor.execute("PRAGMA table_info(games_data)")
        games_cols = [col[1] for col in cursor.fetchall()]

        # Список всех нужных колонок
        ai_columns = ["response_gemini", "response_openrouter", "response_groq"]

        for col in ai_columns:
            if col not in games_cols:
                cursor.execute(
                    f"ALTER TABLE games_data ADD COLUMN {col} TEXT DEFAULT ''"
                )
                logger.info(f"Миграция: добавлена колонка {col} в games_data")

        # Если была старая колонка response_hf — переносим в response_openrouter (опционально)
        if "response_hf" in games_cols and "response_openrouter" in games_cols:
            cursor.execute("""
                UPDATE games_data 
                SET response_openrouter = response_hf 
                WHERE response_openrouter = '' AND response_hf != ''
            """)
            self.conn.commit()
            logger.info(
                "Миграция: перенесены данные из response_hf в response_openrouter"
            )

        self.conn.commit()

        # Миграция: добавляем колонку method в fps_history, если её нет
        cursor.execute("PRAGMA table_info(fps_history)")
        cols = [col[1] for col in cursor.fetchall()]
        if "method" not in cols:
            cursor.execute(
                "ALTER TABLE fps_history ADD COLUMN method TEXT"
            )
            self.conn.commit()
            logger.info("Миграция: добавлена колонка method в fps_history")

        # Миграция: создаём таблицу game_settings, если её нет
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='game_settings'"
        )
        if not cursor.fetchone():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS game_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL,
                    game_name TEXT NOT NULL,
                    target_fps INTEGER DEFAULT 60,
                    recommendation_dismissed INTEGER DEFAULT 0,
                    FOREIGN KEY (profile_id) REFERENCES hardware_profiles(id) ON DELETE CASCADE,
                    UNIQUE(profile_id, game_name)
                )
            """)
            self.conn.commit()
            logger.info("Миграция: создана таблица game_settings")

        cursor.execute("PRAGMA table_info(game_settings)")
        settings_cols = [col[1] for col in cursor.fetchall()]
        if "recommendation_dismissed" not in settings_cols:
            cursor.execute(
                "ALTER TABLE game_settings ADD COLUMN recommendation_dismissed INTEGER DEFAULT 0"
            )
            self.conn.commit()
            logger.info(
                "Миграция: добавлена колонка recommendation_dismissed в game_settings"
            )

        self.conn.commit()

    # --- Профили ---
    def get_all_profiles(self):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, cpu_name, gpu_name, ram_total, vram_gb, is_current FROM hardware_profiles ORDER BY id"
        )
        return cursor.fetchall()

    def get_current_profile_id(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM hardware_profiles WHERE is_current=1 LIMIT 1")
        row = cursor.fetchone()
        return row[0] if row else None

    def set_current_profile(self, profile_id):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE hardware_profiles SET is_current=0")
        cursor.execute(
            "UPDATE hardware_profiles SET is_current=1 WHERE id=?", (profile_id,)
        )
        self.conn.commit()
        logger.info(f"Активный профиль: ID={profile_id}")

    def find_profile_by_hardware(self, cpu: str, gpu: str | None):
        cursor = self.conn.cursor()
        # Если GPU определён, ищем точное совпадение
        if gpu:
            cursor.execute(
                "SELECT id FROM hardware_profiles WHERE cpu_name=? AND gpu_name=? LIMIT 1",
                (cpu, gpu),
            )
            row = cursor.fetchone()
            if row:
                return row[0]
        # Если GPU не определён или точное совпадение не найдено, ищем профиль по CPU
        # Сначала пытаемся найти с пометкой "Не обнаружен" (без GPU)
        cursor.execute(
            "SELECT id FROM hardware_profiles WHERE cpu_name=? AND gpu_name='Не обнаружен' LIMIT 1",
            (cpu,),
        )
        row = cursor.fetchone()
        if row:
            return row[0]
        # Если и такого нет, ищем любой профиль с таким CPU (например, с другой видеокартой)
        cursor.execute(
            "SELECT id FROM hardware_profiles WHERE cpu_name=? LIMIT 1", (cpu,)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def create_profile(self, cpu: str, gpu: str | None, ram: str, vram_gb: float = 8.0):
        cursor = self.conn.cursor()
        gpu_val = gpu if gpu else "Не обнаружен"
        uuid_val = self.generate_profile_uuid(cpu, gpu_val, ram)
        cursor.execute(
            """
            INSERT INTO hardware_profiles (uuid, cpu_name, gpu_name, ram_total, vram_gb)
            VALUES (?, ?, ?, ?, ?)
        """,
            (uuid_val, cpu, gpu_val, ram, vram_gb),
        )
        self.conn.commit()
        new_id = cursor.lastrowid
        logger.info(
            f"Создан профиль ID={new_id}, UUID={uuid_val}: CPU={cpu}, GPU={gpu_val}, RAM={ram}, VRAM={vram_gb} ГБ"
        )
        return new_id

    def generate_profile_uuid(self, cpu: str, gpu: str, ram: str) -> str:
        """Генерирует уникальный UUID для профиля на основе железа."""
        import hashlib

        unique_str = f"{cpu}_{gpu}_{ram}"
        return hashlib.md5(unique_str.encode()).hexdigest()[:16]

    # --- Игры ---
    def get_games_for_profile(self, profile_id):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT DISTINCT game_name FROM games_data WHERE profile_id=? ORDER BY game_name",
            (profile_id,),
        )
        return [row[0] for row in cursor.fetchall()]

    def add_game_to_profile(self, profile_id, game_name):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM games_data WHERE profile_id=? AND game_name=?",
            (profile_id, game_name),
        )
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO games_data (profile_id, game_name, preset, fps_results) VALUES (?, ?, ?, '')",
                (profile_id, game_name, "Низкие"),
            )
            self.conn.commit()
            logger.info(
                f"Игра '{game_name}' добавлена в профиль {profile_id} с пресетом 'Низкие'."
            )
        else:
            logger.warning(
                f"Игра '{game_name}' уже существует в профиле {profile_id}, добавление пропущено."
            )

    def rename_game_in_profile(self, profile_id, old_name, new_name):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM games_data WHERE profile_id=? AND game_name=?",
            (profile_id, new_name),
        )
        if cursor.fetchone()[0] > 0:
            raise ValueError(f"Игра '{new_name}' уже существует в профиле.")
        cursor.execute(
            "UPDATE games_data SET game_name=? WHERE profile_id=? AND game_name=?",
            (new_name, profile_id, old_name),
        )
        self.conn.commit()
        logger.info(
            f"Игра '{old_name}' переименована в '{new_name}' в профиле {profile_id}."
        )

    def delete_game_from_profile(self, profile_id, game_name):
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM games_data WHERE profile_id=? AND game_name=?",
            (profile_id, game_name),
        )
        deleted_count = cursor.rowcount
        cursor.execute(
            "DELETE FROM game_settings WHERE profile_id=? AND game_name=?",
            (profile_id, game_name),
        )
        self.conn.commit()
        logger.info(
            f"Игра '{game_name}' удалена из профиля {profile_id}. Затронуто записей: {deleted_count}."
        )

    def get_presets_for_game(self, profile_id, game_name):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT preset, fps_results FROM games_data WHERE profile_id=? AND game_name=? ORDER BY preset",
            (profile_id, game_name),
        )
        return cursor.fetchall()

    def save_fps(self, profile_id, game_name, preset, fps_values_str, method=None):
        """Сохраняет замер FPS в историю и обновляет текущее значение."""
        cursor = self.conn.cursor()

        # Сохраняем в историю (для каждого значения отдельно)
        fps_list = [float(v.strip()) for v in fps_values_str.split(",") if v.strip()]
        for fps_val in fps_list:
            cursor.execute(
                """
                INSERT INTO fps_history (profile_id, game_name, preset, fps_value, method)
                VALUES (?, ?, ?, ?, ?)
            """,
                (profile_id, game_name, preset, fps_val, method),
            )

        # Обновляем текущее значение в games_data (с заменой при конфликте)
        cursor.execute(
            """
            INSERT OR REPLACE INTO games_data (profile_id, game_name, preset, fps_results, date)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
            (profile_id, game_name, preset, fps_values_str),
        )

        self.conn.commit()
        logger.info(
            f"Сохранены замеры: {game_name} / {preset} → {fps_values_str} (добавлено {len(fps_list)} записей в историю)"
        )

    def get_fps_history(self, profile_id, game_name, preset, limit=50):
        """Возвращает историю замеров FPS для конкретного пресета."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, fps_value, timestamp
            FROM fps_history
            WHERE profile_id=? AND game_name=? AND preset=?
            ORDER BY timestamp DESC
            LIMIT ?
        """,
            (profile_id, game_name, preset, limit),
        )
        return cursor.fetchall()

    def delete_fps_history_entry(self, history_id):
        """Удаляет конкретную запись из истории по ID."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM fps_history WHERE id=?", (history_id,))
        self.conn.commit()
        logger.info(f"Удалена запись истории ID={history_id}")
        return cursor.rowcount > 0

    # --- AI ответы ---
    def save_ai_response(self, profile_id, game_name, ai_type, response_text):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO ai_responses (profile_id, game_name, ai_type, response_text) VALUES (?, ?, ?, ?)",
            (profile_id, game_name, ai_type, response_text),
        )
        self.conn.commit()
        text_preview = response_text[:80].replace("\n", " ") + (
            "..." if len(response_text) > 80 else ""
        )
        logger.info(
            f"Ответ ИИ ({ai_type}) сохранён для игры '{game_name}' в профиле {profile_id} (длина {len(response_text)} символов, начало: '{text_preview}')"
        )

    def get_last_ai_response(self, profile_id, game_name):
        """Возвращает последний ответ для данной игры и профиля (кортеж: ai_type, response_text, timestamp) или None."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT ai_type, response_text, timestamp FROM ai_responses "
            "WHERE profile_id=? AND game_name=? ORDER BY timestamp DESC LIMIT 1",
            (profile_id, game_name),
        )
        return cursor.fetchone()

    # Стало (новый метод + метод close)
    def merge_profiles(self, source_profile_id: int, target_profile_id: int):
        """
        Переносит все игры и AI‑ответы из profile_id = source_profile_id в target_profile_id.
        Конфликтующие записи (одинаковые game_name + preset) пропускаются.
        После успешного переноса исходный профиль удаляется.
        """
        cursor = self.conn.cursor()

        # Игры: обновляем только те, которые не конфликтуют с уже существующими в целевом профиле
        cursor.execute(
            """UPDATE games_data SET profile_id = ?
               WHERE profile_id = ?
                 AND (game_name, preset) NOT IN (
                     SELECT game_name, preset FROM games_data WHERE profile_id = ?
                 )""",
            (target_profile_id, source_profile_id, target_profile_id),
        )
        games_moved = cursor.rowcount

        # Если остались записи, которые нельзя перенести — удаляем их (или можно оставить, но проще удалить)
        cursor.execute(
            "DELETE FROM games_data WHERE profile_id = ?", (source_profile_id,)
        )
        games_deleted = cursor.rowcount

        # AI‑ответы: просто меняем profile_id, конфликтов быть не может (нет уникальности)
        cursor.execute(
            "UPDATE ai_responses SET profile_id = ? WHERE profile_id = ?",
            (target_profile_id, source_profile_id),
        )
        ai_moved = cursor.rowcount

        # Удаляем опустевший профиль
        cursor.execute(
            "DELETE FROM hardware_profiles WHERE id = ?", (source_profile_id,)
        )

        self.conn.commit()
        logger.info(
            f"Миграция: из профиля {source_profile_id} → {target_profile_id}. "
            f"Перенесено игр: {games_moved}, удалено конфликтующих: {games_deleted}, "
            f"перенесено AI-ответов: {ai_moved}. Профиль {source_profile_id} удалён."
        )
        return games_moved + ai_moved

    def delete_profile(self, profile_id):
        """
        Удаляет профиль и все связанные записи (игры, AI‑ответы).
        Возвращает True, если профиль существовал и был удалён.
        """
        cursor = self.conn.cursor()
        # Проверяем существование профиля
        cursor.execute("SELECT id FROM hardware_profiles WHERE id=?", (profile_id,))
        if not cursor.fetchone():
            return False
        # Каскадное удаление включено, поэтому связанные записи удалятся автоматически
        cursor.execute("DELETE FROM hardware_profiles WHERE id=?", (profile_id,))
        # Если удалённый профиль был активным, сбрасываем текущий
        cursor.execute("UPDATE hardware_profiles SET is_current=0 WHERE is_current=1")
        # Назначаем новый активный профиль (первый попавшийся)
        cursor.execute("SELECT id FROM hardware_profiles ORDER BY id LIMIT 1")
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE hardware_profiles SET is_current=1 WHERE id=?", (row[0],)
            )
            logger.info(
                f"После удаления профиля {profile_id} новым активным назначен профиль ID={row[0]}."
            )
        else:
            logger.warning("Все профили удалены, активный профиль отсутствует.")
        self.conn.commit()
        logger.info(f"Профиль ID={profile_id} удалён.")
        return True

    def save_ai_response_for_game(
        self, profile_id, game_name, response_text, model_type="Gemini"
    ):
        """
        Сохраняет AI-ответ для конкретного провайдера.
        model_type: "Gemini", "OpenRouter", "GroqCloud"
        """
        # Определяем колонку
        model_lower = model_type.lower()
        if "gemini" in model_lower:  # сработает для "gemini" и "cloud gemini"
            column = "response_gemini"
        elif model_lower == "openrouter":
            column = "response_openrouter"
        elif model_lower == "groqcloud":
            column = "response_groq"
        else:
            column = "response_gemini"  # fallback

        cursor = self.conn.cursor()

        # Проверяем существование колонки (на случай, если миграция не сработала)
        cursor.execute("PRAGMA table_info(games_data)")
        columns = [col[1] for col in cursor.fetchall()]
        if column not in columns:
            cursor.execute(
                f"ALTER TABLE games_data ADD COLUMN {column} TEXT DEFAULT ''"
            )
            self.conn.commit()
            logger.info(f"Миграция: добавлена колонка {column} в games_data")

        # Сохраняем ответ
        cursor.execute(
            f"""
            UPDATE games_data 
            SET {column}=?, date=CURRENT_TIMESTAMP 
            WHERE profile_id=? AND game_name=?
        """,
            (response_text, profile_id, game_name),
        )

        if cursor.rowcount == 0:
            cursor.execute(
                f"""
                INSERT INTO games_data (profile_id, game_name, preset, {column}) 
                VALUES (?, ?, ?, ?)
            """,
                (profile_id, game_name, "Низкие", response_text),
            )

        self.conn.commit()
        logger.info(
            f"Ответ ИИ ({model_type}) сохранён для игры '{game_name}' (длина {len(response_text)} символов)"
        )

    def get_ai_response_for_game(self, profile_id, game_name, model_type="Gemini"):
        """
        Возвращает AI-ответ для конкретного провайдера.
        model_type: "Gemini", "OpenRouter", "GroqCloud"
        """
        model_lower = model_type.lower()
        if "gemini" in model_lower:  # сработает для "gemini" и "cloud gemini"
            column = "response_gemini"
        elif model_lower == "openrouter":
            column = "response_openrouter"
        elif model_lower == "groqcloud":
            column = "response_groq"
        else:
            return ""  # неизвестный провайдер

        cursor = self.conn.cursor()

        # Проверяем существование колонки
        cursor.execute("PRAGMA table_info(games_data)")
        columns = [col[1] for col in cursor.fetchall()]
        if column not in columns:
            return ""  # колонки ещё нет

        cursor.execute(
            f"""
            SELECT {column} 
            FROM games_data 
            WHERE profile_id=? AND game_name=? AND {column} != '' 
            ORDER BY date DESC LIMIT 1
        """,
            (profile_id, game_name),
        )
        row = cursor.fetchone()
        return row[0] if row else ""

    def get_target_fps_for_game(self, profile_id: int, game_name: str) -> int | None:
        """Возвращает сохранённый целевой FPS для игры или None."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT target_fps FROM game_settings WHERE profile_id=? AND game_name=?",
            (profile_id, game_name),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def save_target_fps_for_game(
        self, profile_id: int, game_name: str, target_fps: int
    ):
        """Сохраняет целевой FPS для игры."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO game_settings (profile_id, game_name, target_fps, recommendation_dismissed)
            VALUES (?, ?, ?, 0)
            ON CONFLICT(profile_id, game_name) DO UPDATE SET
                target_fps=excluded.target_fps,
                recommendation_dismissed=0
        """,
            (profile_id, game_name, target_fps),
        )
        self.conn.commit()
        logger.info(
            f"Сохранён target FPS={target_fps} для игры '{game_name}' (профиль {profile_id})"
        )

    def save_recommendation_dismissed(
        self, profile_id: int, game_name: str
    ):
        """Сохраняет факт отказа от рекомендации для игры."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO game_settings (profile_id, game_name, target_fps, recommendation_dismissed)
            VALUES (?, ?, 60, 1)
            ON CONFLICT(profile_id, game_name) DO UPDATE SET
                recommendation_dismissed=1
        """,
            (profile_id, game_name),
        )
        self.conn.commit()
        logger.info(
            f"Сохранён отказ от рекомендации для игры '{game_name}' (профиль {profile_id})"
        )

    def is_recommendation_dismissed(self, profile_id: int, game_name: str) -> bool:
        """Проверяет, отклонил ли пользователь рекомендацию для игры."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT recommendation_dismissed FROM game_settings WHERE profile_id=? AND game_name=?",
            (profile_id, game_name),
        )
        row = cursor.fetchone()
        return bool(row[0]) if row else False

    def delete_game_settings(self, profile_id: int, game_name: str):
        """Удаляет настройки игры (target FPS)."""
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM game_settings WHERE profile_id=? AND game_name=?",
            (profile_id, game_name),
        )
        self.conn.commit()
        logger.info(f"Удалены настройки для игры '{game_name}' (профиль {profile_id})")

    def cleanup_old_history(self, days: int = 30):
        """Удаляет записи из истории FPS старше N дней."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            DELETE FROM fps_history 
            WHERE timestamp < datetime('now', ?)
            """,
            (f'-{days} days',),
        )
        deleted = cursor.rowcount
        self.conn.commit()
        if deleted > 0:
            logger.info(f"Очищено {deleted} старых записей истории FPS")

    def export_profile_to_dict(self, profile_id):
        """Экспортирует все данные профиля в словарь для сохранения в JSON.
        Включает также API-ключи, профили мониторов, системные требования и таблицу производительности.
        """
        import json
        cursor = self.conn.cursor()

        # Данные профиля
        cursor.execute(
            "SELECT cpu_name, gpu_name, ram_total, vram_gb FROM hardware_profiles WHERE id=?",
            (profile_id,),
        )
        profile = cursor.fetchone()
        if not profile:
            return None
        cpu_name, gpu_name, ram_total, vram_gb = profile

        # Игры и замеры
        cursor.execute(
            "SELECT game_name, preset, fps_results FROM games_data WHERE profile_id=?",
            (profile_id,),
        )
        games = []
        for row in cursor.fetchall():
            games.append({"game_name": row[0], "preset": row[1], "fps_results": row[2]})

        # История замеров
        cursor.execute(
            "SELECT game_name, preset, fps_value, timestamp FROM fps_history WHERE profile_id=?",
            (profile_id,),
        )
        history = []
        for row in cursor.fetchall():
            history.append(
                {
                    "game_name": row[0],
                    "preset": row[1],
                    "fps_value": row[2],
                    "timestamp": row[3],
                }
            )

        # AI ответы (последние для каждой пары игра+тип)
        cursor.execute("""
            SELECT game_name, ai_type, response_text, timestamp
            FROM (
                SELECT game_name, ai_type, response_text, timestamp,
                       ROW_NUMBER() OVER (PARTITION BY game_name, ai_type ORDER BY timestamp DESC) as rn
                FROM ai_responses
                WHERE profile_id = ?
            ) ranked
            WHERE rn = 1
        """, (profile_id,))
        ai_responses = []
        for row in cursor.fetchall():
            ai_responses.append(
                {
                    "game_name": row[0],
                    "ai_type": row[1],
                    "response_text": row[2],
                    "timestamp": row[3],
                }
            )

        uuid_val = self.get_profile_uuid(profile_id)

        # Настройки игр (target FPS)
        cursor.execute(
            "SELECT game_name, target_fps FROM game_settings WHERE profile_id=?",
            (profile_id,),
        )
        game_settings = []
        for row in cursor.fetchall():
            game_settings.append({"game_name": row[0], "target_fps": row[1]})

        # ===== ДОБАВЛЯЕМ НОВЫЕ СЕКЦИИ =====
        # 1. Настройки из fps_settings.json (API-ключи и профили мониторов)
        try:
            from settings import load_settings
            settings = load_settings()
            extra_settings = {
                "gemini_api_key": settings.get("gemini_api_key", ""),
                "openrouter_api_key": settings.get("openrouter_api_key", ""),
                "groq_api_key": settings.get("groq_api_key", ""),
                "monitor_profiles": settings.get("monitor_profiles", []),
                "active_monitor_profile": settings.get("active_monitor_profile", ""),
            }
        except Exception as e:
            logger.warning(f"Не удалось загрузить настройки для экспорта: {e}")
            extra_settings = {}

        # 2. Системные требования
        requirements = {}
        if os.path.exists("game_requirements.json"):
            try:
                with open("game_requirements.json", "r", encoding="utf-8") as f:
                    requirements = json.load(f)
            except Exception as e:
                logger.warning(f"Не удалось прочитать game_requirements.json: {e}")

        # 3. Таблица производительности
        benchmark = {}
        if os.path.exists("hardware_benchmark.json"):
            try:
                with open("hardware_benchmark.json", "r", encoding="utf-8") as f:
                    benchmark = json.load(f)
            except Exception as e:
                logger.warning(f"Не удалось прочитать hardware_benchmark.json: {e}")

        # 4. Пресеты игр для машинной калибровки
        game_presets = {}
        if os.path.exists("game_presets_db.json"):
            try:
                with open("game_presets_db.json", "r", encoding="utf-8") as f:
                    game_presets = json.load(f)
            except Exception as e:
                logger.warning(f"Не удалось прочитать game_presets_db.json: {e}")

        # Формируем итоговый словарь
        result = {
            "profile": {
                "uuid": uuid_val,
                "cpu_name": cpu_name,
                "gpu_name": gpu_name,
                "ram_total": ram_total,
                "vram_gb": vram_gb,
            },
            "games": games,
            "history": history,
            "ai_responses": ai_responses,
            "game_settings": game_settings,
            "extra_settings": extra_settings,          # API-ключи и профили мониторов
            "game_requirements": requirements,        # База системных требований
            "hardware_benchmark": benchmark,          # Таблица производительности
            "game_presets": game_presets,
        }
        return result

    def import_profile_from_dict(self, data, target_profile_id=None, set_as_current=True):
        """Импортирует профиль из словаря.
        Если target_profile_id указан — импортирует в существующий профиль (очищая его данные).
        Если target_profile_id не указан — создаёт новый профиль.
        Также восстанавливает API-ключи, профили мониторов, системные требования и таблицу производительности.
        Возвращает profile_id.
        """
        import json
        profile_data = data.get("profile", {})
        if not profile_data:
            return None

        uuid_val = profile_data.get("uuid")
        cpu = profile_data.get("cpu_name", "Unknown")
        gpu = profile_data.get("gpu_name", "Unknown")
        ram = profile_data.get("ram_total", "8 GB")
        vram = profile_data.get("vram_gb", 8.0)

        # Если UUID есть, пробуем найти существующий профиль с таким же UUID
        if uuid_val:
            existing_id = self.find_profile_by_uuid(uuid_val)
            if existing_id:
                target_profile_id = existing_id
                logger.info(
                    f"Найден существующий профиль с UUID={uuid_val}, ID={target_profile_id}"
                )

        cursor = self.conn.cursor()

        if target_profile_id:
            # Проверяем, существует ли целевой профиль
            cursor.execute(
                "SELECT id FROM hardware_profiles WHERE id=?", (target_profile_id,)
            )
            if cursor.fetchone():
                profile_id = target_profile_id
                # Очищаем все данные целевого профиля
                cursor.execute(
                    "DELETE FROM games_data WHERE profile_id=?", (profile_id,)
                )
                cursor.execute(
                    "DELETE FROM fps_history WHERE profile_id=?", (profile_id,)
                )
                cursor.execute(
                    "DELETE FROM ai_responses WHERE profile_id=?", (profile_id,)
                )
                # Обновляем железо профиля
                cursor.execute(
                    """
                    UPDATE hardware_profiles 
                    SET cpu_name=?, gpu_name=?, ram_total=?, vram_gb=?
                    WHERE id=?
                """,
                    (cpu, gpu, ram, vram, profile_id),
                )
                self.conn.commit()
                logger.info(f"Очищен и обновлён существующий профиль ID={profile_id}")
            else:
                target_profile_id = None

        if not target_profile_id:
            # Создаём новый профиль
            profile_id = self.create_profile(cpu, gpu, ram, vram)
        else:
            profile_id = target_profile_id

        # Импортируем игры и замеры
        for game in data.get("games", []):
            game_name = game.get("game_name")
            preset = game.get("preset")
            fps_results = game.get("fps_results", "")
            if game_name and preset:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO games_data (profile_id, game_name, preset, fps_results, date)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                    (profile_id, game_name, preset, fps_results),
                )

        # Импортируем историю замеров
        for hist in data.get("history", []):
            game_name = hist.get("game_name")
            preset = hist.get("preset")
            fps_value = hist.get("fps_value")
            timestamp = hist.get("timestamp")
            if game_name and preset and fps_value:
                if timestamp:
                    cursor.execute(
                        """
                        INSERT INTO fps_history (profile_id, game_name, preset, fps_value, timestamp)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                        (profile_id, game_name, preset, fps_value, timestamp),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO fps_history (profile_id, game_name, preset, fps_value)
                        VALUES (?, ?, ?, ?)
                    """,
                        (profile_id, game_name, preset, fps_value),
                    )

        # Импортируем AI ответы
        for ai in data.get("ai_responses", []):
            game_name = ai.get("game_name")
            ai_type = ai.get("ai_type")
            response_text = ai.get("response_text")
            timestamp = ai.get("timestamp")
            if game_name and ai_type and response_text:
                if timestamp:
                    cursor.execute(
                        """
                        INSERT INTO ai_responses (profile_id, game_name, ai_type, response_text, timestamp)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                        (profile_id, game_name, ai_type, response_text, timestamp),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO ai_responses (profile_id, game_name, ai_type, response_text)
                        VALUES (?, ?, ?, ?)
                    """,
                        (profile_id, game_name, ai_type, response_text),
                    )
                # Восстановление в столбец games_data
                model_lower = ai_type.lower()
                if "gemini" in model_lower:
                    column = "response_gemini"
                elif model_lower == "openrouter":
                    column = "response_openrouter"
                elif model_lower == "groqcloud":
                    column = "response_groq"
                else:
                    continue
                cursor.execute(
                    f"""
                    UPDATE games_data 
                    SET {column} = ?
                    WHERE profile_id = ? AND game_name = ?
                """,
                    (response_text, profile_id, game_name),
                )
                if cursor.rowcount == 0:
                    cursor.execute(
                        f"""
                        INSERT INTO games_data (profile_id, game_name, preset, {column})
                        VALUES (?, ?, 'Низкие', ?)
                    """,
                        (profile_id, game_name, response_text),
                    )

        # Импортируем настройки игр (target FPS)
        for setting in data.get("game_settings", []):
            game_name = setting.get("game_name")
            target_fps = setting.get("target_fps", 60)
            if game_name:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO game_settings (profile_id, game_name, target_fps)
                    VALUES (?, ?, ?)
                """,
                    (profile_id, game_name, target_fps),
                )

        self.conn.commit()

        # ===== ВОССТАНАВЛИВАЕМ ДОПОЛНИТЕЛЬНЫЕ ФАЙЛЫ =====
        # 1. Восстановление настроек (API-ключи, профили мониторов)
        extra = data.get("extra_settings", {})
        if extra:
            try:
                from settings import load_settings, save_settings
                current_settings = load_settings()
                # Обновляем только те поля, которые есть в extra
                for key in ["gemini_api_key", "openrouter_api_key", "groq_api_key",
                            "monitor_profiles", "active_monitor_profile"]:
                    if key in extra:
                        current_settings[key] = extra[key]
                save_settings(current_settings)
                logger.info("API-ключи и профили мониторов восстановлены из импорта")
            except Exception as e:
                logger.warning(f"Не удалось восстановить настройки: {e}")

        # 2. Восстановление системных требований
        requirements = data.get("game_requirements", {})
        if requirements:
            try:
                with open("game_requirements.json", "w", encoding="utf-8") as f:
                    json.dump(requirements, f, indent=2, ensure_ascii=False)
                logger.info("База системных требований восстановлена из импорта")
            except Exception as e:
                logger.warning(f"Не удалось сохранить game_requirements.json: {e}")

        # 3. Восстановление таблицы производительности
        benchmark = data.get("hardware_benchmark", {})
        if benchmark:
            try:
                with open("hardware_benchmark.json", "w", encoding="utf-8") as f:
                    json.dump(benchmark, f, indent=2, ensure_ascii=False)
                logger.info("Таблица производительности восстановлена из импорта")
            except Exception as e:
                logger.warning(f"Не удалось сохранить hardware_benchmark.json: {e}")

        # 4. Восстановление пресетов игр (машинная калибровка)
        game_presets = data.get("game_presets", {})
        if game_presets:
            try:
                with open("game_presets_db.json", "w", encoding="utf-8") as f:
                    json.dump(game_presets, f, indent=2, ensure_ascii=False)
                logger.info("Пресеты игр восстановлены из импорта")
            except Exception as e:
                logger.warning(f"Не удалось сохранить game_presets_db.json: {e}")

        if set_as_current:
            self.set_current_profile(profile_id)

        logger.info(f"Импортирован профиль ID={profile_id} (CPU={cpu}, GPU={gpu})")
        return profile_id

    def close(self):
        self.conn.close()
