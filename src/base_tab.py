"""
Базовый класс для всех вкладок приложения.
Предоставляет стандартный метод refresh().
"""

from PySide6.QtWidgets import QWidget


class BaseTab(QWidget):
    """Базовая вкладка с унифицированным refresh()."""
    
    def __init__(self, db, log_func=None):
        super().__init__()
        self.db = db
        self.log = log_func if log_func else print
        self.current_profile_id = None
    
    def refresh(self):
        """
        Обновляет состояние вкладки.
        Переопределяется в подклассах.
        """
        self.current_profile_id = self.db.get_current_profile_id()
        if not self.current_profile_id:
            self._clear_ui()
    
    def _clear_ui(self):
        """Очищает UI при отсутствии профиля."""
        pass  # Переопределяется в подклассах
