"""
AI Engine – формирование промпта и backends.
"""

import logging
import ssl
import warnings
from importlib import import_module

import requests
import urllib3
from PySide6.QtCore import QThread, Signal

warnings.filterwarnings("ignore", category=FutureWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
genai = import_module("google.generativeai")

# Отключаем проверку SSL-сертификатов (только для работы через VPN)
ssl._create_default_https_context = ssl._create_unverified_context

logger = logging.getLogger("AIEngine")

# Дефолтные настройки провайдеров
PROVIDER_DEFAULTS = {
    "OpenRouter": {
        "model": "deepseek/deepseek-r1:free",
        "api_url": "https://openrouter.ai/api/v1/chat/completions",
    },
    "GroqCloud": {
        "model": "llama-3.1-8b-instant",
        "api_url": "https://api.groq.com/openai/v1/chat/completions",
    },
    "Cloud Gemini": {
        "model": "gemini-2.0-flash-lite",
        "api_url": "",  # Gemini использует SDK, URL не нужен
    },
}


def get_provider_settings(settings, provider_name):
    """Возвращает актуальные модель, URL и отображаемое имя для провайдера из settings."""
    key = f"provider_{provider_name.lower().replace(' ', '_')}"
    saved = settings.get(key, {})
    defaults = PROVIDER_DEFAULTS.get(provider_name, {})
    return {
        "model": saved.get("model", defaults.get("model", "")),
        "api_url": saved.get("api_url", defaults.get("api_url", "")),
        "display_name": saved.get("display_name", provider_name),  # ← добавлено
    }


def save_provider_settings(settings, provider_name, model, api_url, display_name=None):
    """Сохраняет модель, URL и отображаемое имя провайдера в settings dict."""
    key = f"provider_{provider_name.lower().replace(' ', '_')}"
    data = {"model": model, "api_url": api_url}
    if display_name:
        data["display_name"] = display_name
    settings[key] = data
    return settings


def build_prompt(
    db, profile_id, game_name, target_fps=165, monitor_hz=165, ai_type="Gemini"
):
    cursor = db.conn.cursor()
    cursor.execute(
        "SELECT cpu_name, gpu_name, ram_total, vram_gb FROM hardware_profiles WHERE id=?",
        (profile_id,),
    )
    hw = cursor.fetchone()
    if not hw:
        return "", {}
    cpu, gpu, ram, vram = hw
    vram_total = vram if vram else 8.0

    presets_data = db.get_presets_for_game(profile_id, game_name)
    presets_str = ""
    for preset, fps in presets_data:
        presets_str += f"{preset}: {fps}\n"

    gpu_lower = gpu.lower()
    if "rtx 5070" in gpu_lower:
        tone = "ultra_quality"
        vram_note = "Видеопамяти 12 ГБ более чем достаточно. Не снижай качество."
        quality_rule = (
            "ЗАПРЕЩЕНО предлагать настройки ниже High/Ultra. Используй DLSS 4."
        )
    elif "p106-100" in gpu_lower:
        tone = "balanced"
        vram_note = "Видеопамяти 6 ГБ хватит для средних и высоких текстур."
        quality_rule = "Предлагай баланс, активно используй Lossless Scaling X3."
    else:
        tone = "general"
        vram_note = "Следи, чтобы настройки не превышали доступную видеопамять."
        quality_rule = "Подбирай настройки под целевой FPS."

    from settings import load_settings

    s = load_settings()
    monitor_resolution = s.get("monitor_resolution", "1920x1080")

    prompt = f"""Ты — технический эксперт по оптимизации игр. Проанализируй оборудование и замеры FPS, чтобы достичь цели в {target_fps} FPS.

ОБОРУДОВАНИЕ:
- Процессор: {cpu}
- Видеокарта: {gpu} (VRAM: {vram_total} ГБ)
- ОЗУ: {ram} ГБ
- Монитор: {monitor_resolution} @ {monitor_hz} Гц (G-Sync включён)
- Доступен Lossless Scaling 3.1 (алгоритм LSFG 3.1)

ЗАМЕРЫ FPS:
{presets_str}

ПРАВИЛА:
РЕЖИМ: {tone.upper()}.
{quality_rule}
{vram_note}
Целевой FPS: {target_fps}. Используй Lossless Scaling LSFG 3.1. Множитель X3 даст тройной прирост. Если базовый FPS * множитель > {monitor_hz}, это нормально – G-Sync сгладит.

ШАБЛОН ОТВЕТА (строго соблюдай):
Анализ: (где узкое место — CPU или GPU)
Настройки: Тени (Low/Medium/High/Ultra), Текстуры (Low/Medium/High/Ultra), Облака (Low/Medium/High)
Lossless Scaling: LSFG 3.1, Множитель X2 или X3
Итог: (ожидаемый FPS после оптимизации) FPS

Отвечай кратко, техническим стилем, без лишних объяснений."""

    meta = {"cpu": cpu, "gpu": gpu, "ram": ram, "vram": vram_total}
    return prompt, meta


class OpenRouterBackend:
    def __init__(self, api_key, model=None, api_url=None):
        self.api_key = api_key
        self.model = model or PROVIDER_DEFAULTS["OpenRouter"]["model"]
        self.api_url = api_url or PROVIDER_DEFAULTS["OpenRouter"]["api_url"]

    def generate(self, prompt):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300,
        }
        try:
            resp = requests.post(
                self.api_url, headers=headers, json=payload, timeout=30, verify=False
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            else:
                return f"Ошибка OpenRouter {resp.status_code}: {resp.text[:200]}"
        except requests.exceptions.ConnectionError:
            return "Ошибка: нет подключения к интернету"
        except requests.exceptions.Timeout:
            return "Ошибка: таймаут соединения"
        except Exception as e:
            logger.exception("Непредвиденная ошибка AI-запроса OpenRouter")
            return f"Ошибка: {type(e).__name__}"

    @staticmethod
    def check_connection(api_key, timeout=10):
        """Реальная проверка доступности API с ключом."""
        try:
            # Отправляем минимальный запрос к модели
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "openrouter/free",
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5,
            }
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
                verify=False,
            )
            if resp.status_code == 200:
                return True, "OpenRouter доступен"
            elif resp.status_code == 401:
                return False, "Неверный API-ключ OpenRouter"
            elif resp.status_code == 429:
                return True, "OpenRouter доступен (квота исчерпана)"
            else:
                return False, f"Ошибка: код {resp.status_code}"
        except requests.exceptions.SSLError:
            return False, "SSL ошибка (возможно, требуется VPN)"
        except requests.exceptions.ConnectionError:
            return False, "Нет подключения к интернету"
        except requests.exceptions.Timeout:
            return False, "Таймаут (сервер не отвечает)"
        except Exception as e:
            return False, f"Ошибка: {e}"


class GroqCloudBackend:
    def __init__(self, api_key, model=None, api_url=None):
        self.api_key = api_key
        self.model = model or PROVIDER_DEFAULTS["GroqCloud"]["model"]
        self.api_url = api_url or PROVIDER_DEFAULTS["GroqCloud"]["api_url"]

    def generate(self, prompt):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300,
        }
        try:
            print(f"DEBUG GroqCloud: URL={self.api_url}")
            print(f"DEBUG GroqCloud: model={self.model}")
            print(f"DEBUG GroqCloud: api_key={self.api_key[:20]}...")

            resp = requests.post(
                self.api_url, headers=headers, json=payload, timeout=30, verify=False
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            else:
                return f"Ошибка Groq {resp.status_code}: {resp.text[:200]}"
        except requests.exceptions.ConnectionError:
            return "Ошибка: нет подключения к интернету"
        except requests.exceptions.Timeout:
            return "Ошибка: таймаут соединения"
        except Exception as e:
            logger.exception("Непредвиденная ошибка AI-запроса GroqCloud")
            return f"Ошибка: {type(e).__name__}"

    @staticmethod
    def check_connection(api_key, timeout=10):
        """Реальная проверка доступности GroqCloud API с ключом."""
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5,
            }
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
                verify=False,
            )
            if resp.status_code == 200:
                return True, "GroqCloud доступен"
            elif resp.status_code == 401:
                return False, "Неверный API-ключ GroqCloud"
            elif resp.status_code == 429:
                return True, "GroqCloud доступен (квота исчерпана)"
            else:
                return False, f"Ошибка: код {resp.status_code}"
        except requests.exceptions.SSLError:
            return False, "SSL ошибка (возможно, требуется VPN)"
        except requests.exceptions.ConnectionError:
            return False, "Нет подключения к интернету"
        except requests.exceptions.Timeout:
            return False, "Таймаут (сервер не отвечает)"
        except Exception as e:
            return False, f"Ошибка: {e}"


class GeminiBackend:
    def __init__(self, api_key, model=None):
        self.model_name = model or PROVIDER_DEFAULTS["Cloud Gemini"]["model"]
        genai.configure(api_key=api_key, transport="rest")
        self.model = genai.GenerativeModel(self.model_name)

    def generate(self, prompt):
        try:
            response = self.model.generate_content(
                prompt, request_options={"timeout": 30}
            )
            return response.text
        except genai.types.BlockedPromptException:
            return "Ошибка: запрос заблокирован политикой Gemini"
        except genai.types.StopCandidateException:
            return "Ошибка: генерация остановлена (неприемлемый контент)"
        except Exception as e:
            error_str = str(e)
            if "API_KEY" in error_str or "403" in error_str:
                return "Ошибка: неверный API-ключ Gemini"
            elif "429" in error_str:
                return "Ошибка: превышена квота Gemini (TooManyRequests)"
            elif "timed out" in error_str.lower():
                return "Ошибка: таймаут соединения"
            elif "connection" in error_str.lower() or "network" in error_str.lower():
                return "Ошибка: нет подключения к интернету"
            else:
                logger.exception(f"Непредвиденная ошибка AI-запроса Gemini: {error_str}")
                return f"Ошибка Gemini: {type(e).__name__}"

    @staticmethod
    def check_connection(api_key, timeout=10):
        """Реальная проверка доступности Gemini API с ключом."""
        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key, transport="rest")
            model = genai.GenerativeModel("gemini-2.0-flash-lite")
            response = model.generate_content(
                "Hi", request_options={"timeout": timeout}
            )
            if response.text:
                return True, "Gemini доступен"
            else:
                return False, "Gemini вернул пустой ответ"
        except Exception as e:
            error_str = str(e)
            if "API_KEY" in error_str or "403" in error_str:
                return False, "Неверный API-ключ Gemini"
            elif "429" in error_str:
                return True, "Gemini доступен (квота исчерпана)"
            elif "SSL" in error_str or "CERTIFICATE" in error_str:
                return False, "SSL ошибка (возможно, требуется VPN)"
            elif "timed out" in error_str.lower():
                return False, "Таймаут (сервер не отвечает)"
            else:
                return False, f"Ошибка: {error_str[:100]}"


class AIWorker(QThread):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, backend, prompt, db, profile_id, game_name, ai_type):
        super().__init__()
        self.backend = backend
        self.prompt = prompt
        self.db = db
        self.profile_id = profile_id
        self.game_name = game_name
        self.ai_type = ai_type

    def run(self):
        try:
            result = self.backend.generate(self.prompt)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
