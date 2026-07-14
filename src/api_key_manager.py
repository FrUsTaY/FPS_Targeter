"""
Менеджер API-ключей для AI-провайдеров.
Централизованное управление ключами с валидацией.
"""

import logging
from settings import load_settings, save_settings

logger = logging.getLogger("APIKeyManager")


class APIKeyManager:
    """Управляет API-ключами всех провайдеров."""
    
    def __init__(self):
        self.settings = load_settings()
    
    def get_key(self, provider: str) -> str:
        """Получить ключ провайдера."""
        keys = {
            "OpenRouter": "openrouter_api_key",
            "GroqCloud": "groq_api_key",
            "Cloud Gemini": "gemini_api_key",
        }
        key_name = keys.get(provider, "")
        return self.settings.get(key_name, "").strip()
    
    def set_key(self, provider: str, key: str) -> None:
        """Установить ключ провайдера."""
        keys = {
            "OpenRouter": "openrouter_api_key",
            "GroqCloud": "groq_api_key",
            "Cloud Gemini": "gemini_api_key",
        }
        key_name = keys.get(provider, "")
        self.settings[key_name] = key.strip()
        save_settings(self.settings)
    
    def validate_all(self) -> dict:
        """Проверить все ключи. Возвращает {provider: (is_valid, error_msg)}."""
        results = {}
        for provider in ["OpenRouter", "GroqCloud", "Cloud Gemini"]:
            key = self.get_key(provider)
            if not key:
                results[provider] = (False, "Ключ не указан")
            else:
                # Можно добавить тестовую проверку
                results[provider] = (True, "")
        return results
    
    def reset_all(self) -> None:
        """Сбросить все ключи."""
        self.settings["openrouter_api_key"] = ""
        self.settings["groq_api_key"] = ""
        self.settings["gemini_api_key"] = ""
        save_settings(self.settings)
