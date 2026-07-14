"""
Менеджер сетевых проверок для AI-провайдеров.
Предоставляет единый интерфейс для проверки доступности API.
"""

import logging
from PySide6.QtCore import QThread, Signal

from ai_engine import (
    OpenRouterBackend,
    GroqCloudBackend,
    GeminiBackend,
)

logger = logging.getLogger("NetworkManager")


class NetworkCheckThread(QThread):
    """Поток для проверки сетевого подключения."""
    result = Signal(bool, str)
    
    def __init__(self, provider: str, api_key: str):
        super().__init__()
        self.provider = provider
        self.api_key = api_key
    
    def run(self):
        if not self.api_key:
            self.result.emit(False, f"API-ключ {self.provider} не указан")
            return
        
        if self.provider == "OpenRouter":
            ok, msg = OpenRouterBackend.check_connection(self.api_key)
        elif self.provider == "GroqCloud":
            ok, msg = GroqCloudBackend.check_connection(self.api_key)
        elif self.provider == "Cloud Gemini":
            ok, msg = GeminiBackend.check_connection(self.api_key)
        else:
            ok, msg = False, "Неизвестный провайдер"
        
        self.result.emit(ok, msg)


class NetworkManager:
    """Менеджер сетевых проверок."""
    
    def __init__(self):
        self.current_thread = None
    
    def check_network(self, provider: str, api_key: str, callback):
        """
        Проверяет сетевое подключение.
        callback(ok: bool, message: str) — функция обратного вызова.
        """
        if self.current_thread and self.current_thread.isRunning():
            self.current_thread.wait()
        
        self.current_thread = NetworkCheckThread(provider, api_key)
        self.current_thread.result.connect(callback)
        self.current_thread.start()
