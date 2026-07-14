"""
Мониторинг игровых процессов и управление оверлеем (упрощённая версия).
"""

import time
import logging
import psutil
import win32gui
import win32process
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger("GameTracker")


class GameOverlayTracker(QThread):
    """Фоновый поток для отслеживания игр."""

    show_overlay = Signal()
    hide_overlay = Signal()
    update_game_info = Signal(str)

    def __init__(self, games_list, overlay, settings):
        super().__init__()
        self.games_list = games_list
        self.overlay = overlay
        self.settings = settings
        self._running = True
        self._current_game_hwnd = None
        self._current_game_name = None
        self._editing_mode = False

    def set_editing_mode(self, enabled: bool):
        """Включает/выключает режим редактирования."""
        self._editing_mode = enabled
        if enabled:
            logger.info("Режим редактирования включён, трекер приостановлен")
        else:
            logger.info("Режим редактирования выключен, трекер возобновлён")

    def stop(self):
        self._running = False
        self.wait()

    def run(self):
        logger.info("GameOverlayTracker запущен")

        while self._running:
            try:
                self._check_games()
            except Exception as e:
                logger.error(f"Ошибка в трекере: {e}")

            time.sleep(1.0)

        logger.info("GameOverlayTracker остановлен")

    def _check_games(self):
        if self._editing_mode:
            return

        # Ищем запущенные игры
        running_games = []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                proc_name = proc.info["name"].lower()
                if proc_name in self.games_list:
                    running_games.append((proc, proc_name))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not running_games:
            if self._current_game_hwnd is not None:
                self._current_game_hwnd = None
                self._current_game_name = None
                self.hide_overlay.emit()
            return

        proc, proc_name = running_games[0]
        hwnd = self._find_game_window(proc.info["pid"])

        if not hwnd:
            return

        # Проверяем, активно ли окно игры
        foreground_hwnd = win32gui.GetForegroundWindow()
        is_foreground = hwnd == foreground_hwnd

        # Проверяем, не свёрнута ли игра
        is_iconic = win32gui.IsIconic(hwnd)

        if is_foreground and not is_iconic:
            if self._current_game_hwnd != hwnd:
                self._current_game_hwnd = hwnd
                self._current_game_name = proc_name
                self.update_game_info.emit(proc_name)
                self.show_overlay.emit()
                logger.info(f"Оверлей активирован для игры: {proc_name}")
        else:
            if self._current_game_hwnd is not None:
                self._current_game_hwnd = None
                self._current_game_name = None
                self.hide_overlay.emit()
                logger.info("Оверлей скрыт")

    def _find_game_window(self, pid):
        def enum_callback(hwnd, hwnd_list):
            if win32gui.IsWindowVisible(hwnd):
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                if found_pid == pid:
                    hwnd_list.append(hwnd)
            return True

        hwnd_list = []
        win32gui.EnumWindows(enum_callback, hwnd_list)
        return hwnd_list[0] if hwnd_list else None
