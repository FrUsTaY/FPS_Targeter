"""
Модуль глобальной горячей клавиши (Windows) – финальный исправленный
Сигнал вынесен в HotkeyManager(QObject).
Исправление: int(message) для корректной работы ctypes.cast.
"""

import sys
import logging
from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
import ctypes
from ctypes import wintypes

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_NOREPEAT = 0x4000  # Чтобы не повторялось при зажатии
    VK_F = 0x46
    VK_R = 0x52
    WM_HOTKEY = 0x0312

    class HotkeyManager(QObject):
        """Владелец сигналов горячих клавиш"""

        alt_f_pressed = Signal()
        ctrl_shift_r_pressed = Signal()
        ctrl_shift_f_pressed = Signal()  # Ручной ввод FPS

        def __init__(self, parent=None):
            super().__init__(parent)
            self._filter = None
            self._hwnd = None
            self._hotkey_ids = {"alt_f": 1, "ctrl_shift_r": 2, "ctrl_shift_f": 3}

        def register(self, hwnd: int):
            logger.info("Регистрация глобальных горячих клавиш...")
            self._hwnd = hwnd
            self._filter = WinHotkeyFilter(self)
            user32 = ctypes.windll.user32

            # Alt+F
            if not user32.RegisterHotKey(
                hwnd, self._hotkey_ids["alt_f"], MOD_ALT, VK_F
            ):
                logger.error("Не удалось зарегистрировать горячую клавишу Alt+F.")
                raise RuntimeError("Не удалось зарегистрировать горячую клавишу Alt+F")
            logger.info("Горячая клавиша Alt+F зарегистрирована.")

            # Ctrl+Shift+R
            if not user32.RegisterHotKey(
                hwnd, self._hotkey_ids["ctrl_shift_r"], MOD_CONTROL | MOD_SHIFT, VK_R
            ):
                logger.warning(
                    "Не удалось зарегистрировать Ctrl+Shift+R (возможно, занята)."
                )
            else:
                logger.info("Горячая клавиша Ctrl+Shift+R зарегистрирована.")

            # Ctrl+Shift+F (ручной ввод FPS)
            if not user32.RegisterHotKey(
                hwnd,
                self._hotkey_ids["ctrl_shift_f"],
                MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT,
                VK_F,
            ):
                logger.warning(
                    "Не удалось зарегистрировать Ctrl+Shift+F (возможно, занята)."
                )
            else:
                logger.info(
                    "Горячая клавиша Ctrl+Shift+F зарегистрирована (ручной ввод FPS)."
                )

        def unregister(self):
            if self._hwnd:
                user32 = ctypes.windll.user32
                for key_name, key_id in self._hotkey_ids.items():
                    user32.UnregisterHotKey(self._hwnd, key_id)
                    logger.info(f"Горячая клавиша {key_name} разрегистрирована.")
                self._hwnd = None
            self._filter = None

    class WinHotkeyFilter(QAbstractNativeEventFilter):
        """Фильтр событий (не QObject), перенаправляет в менеджер"""

        def __init__(self, manager: HotkeyManager):
            super().__init__()
            self._manager = manager

        def nativeEventFilter(self, eventType, message):
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG))
            if msg[0].message == WM_HOTKEY:
                hotkey_id = msg[0].wParam
                if hotkey_id == self._manager._hotkey_ids["alt_f"]:
                    logger.info("Горячая клавиша Alt+F нажата.")
                    self._manager.alt_f_pressed.emit()
                    return True, 0
                elif hotkey_id == self._manager._hotkey_ids["ctrl_shift_r"]:
                    logger.info("Горячая клавиша Ctrl+Shift+R нажата.")
                    self._manager.ctrl_shift_r_pressed.emit()
                    return True, 0
                elif hotkey_id == self._manager._hotkey_ids["ctrl_shift_f"]:
                    logger.info(
                        "Горячая клавиша Ctrl+Shift+F нажата (ручной ввод FPS)."
                    )
                    self._manager.ctrl_shift_f_pressed.emit()
                    return True, 0
            return False, 0
else:

    class HotkeyManager(QObject):
        alt_f_pressed = Signal()
        ctrl_shift_r_pressed = Signal()
        ctrl_shift_f_pressed = Signal()

        def register(self, hwnd):
            logger.info(
                "Глобальные горячие клавиши не поддерживаются на данной платформе."
            )

        def unregister(self):
            pass
