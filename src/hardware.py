# Стало (добавлен метод get_gpu_temps – вставлен после _detect)
"""
Модуль Hardware Passport (исправлен — маркетинговое имя CPU)
Автоматическая детекция CPU, RAM и GPU (NVIDIA).
Безопасен при отсутствии библиотек или железа.
"""

import platform
import psutil
import logging
import sys

logger = logging.getLogger("Hardware")


class HardwarePassport:
    def __init__(self):
        self.cpu_name = None
        self.ram_gb = None
        self.gpu_name = None
        self.vram_gb = None
        self.nvml_available = False
        self._detect()

    def _get_cpu_name_windows(self) -> str | None:
        """Пытается прочитать маркетинговое имя CPU из реестра Windows."""
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            winreg.CloseKey(key)
            return name.strip()
        except Exception:
            return None

    def _get_gpu_name_windows(self):
        """Возвращает имя видеокарты через WMI (в том числе встроенную графику)."""
        try:
            import wmi
            import pythoncom

            # Инициализация COM для текущего потока (важно для фоновых потоков)
            pythoncom.CoInitialize()
            try:
                w = wmi.WMI()
                for adapter in w.Win32_VideoController():
                    if adapter.Name:
                        return adapter.Name.strip()
            finally:
                pythoncom.CoUninitialize()
        except Exception:
            pass
        return None

    def _detect(self):
        logger.info(f"Python интерпретатор: {sys.executable}")
        # --- CPU (маркетинговое имя) ---
        cpu = None
        if platform.system() == "Windows":
            cpu = self._get_cpu_name_windows()
        if not cpu:
            try:
                cpu = platform.processor()
                if not cpu or not cpu.strip():
                    cpu = None
            except Exception:
                cpu = None
        if not cpu:
            cpu = "Неизвестный CPU"
        self.cpu_name = cpu
        from_register = (
            platform.system() == "Windows" and self._get_cpu_name_windows() is not None
        )
        method = "реестр" if from_register else "platform.processor()"
        logger.info(f"CPU обнаружен: {self.cpu_name} (метод: {method})")

        # --- RAM ---
        try:
            total = psutil.virtual_memory().total
            self.ram_gb = round(total / (1024**3), 1)
            logger.info(f"RAM обнаружено: {self.ram_gb} ГБ (всего {total} байт)")
        except Exception as e:
            self.ram_gb = 0
            logger.error(f"RAM error: {e}")

        # --- GPU (NVIDIA) ---
        pynvml = None
        try:
            import pynvml
        except ImportError:
            logger.warning(
                "Библиотека nvidia-ml-py не установлена. "
                "Установите её командой: pip install nvidia-ml-py\n"
                "Также убедитесь, что драйвер NVIDIA работает (проверьте nvidia-smi)."
            )

        if pynvml:
            try:
                pynvml.nvmlInit()
                self.nvml_available = True
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                self.gpu_name = pynvml.nvmlDeviceGetName(handle)
                info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                self.vram_gb = round(info.total / (1024**3), 1)
                logger.info(
                    f"GPU обнаружен (NVML): {self.gpu_name}, VRAM: {self.vram_gb} ГБ"
                )
                pynvml.nvmlShutdown()
            except Exception as e:
                logger.warning(
                    f"Ошибка при опросе GPU через NVML: {e}. Возможно, драйвер не NVIDIA."
                )

        # Если NVIDIA не нашлась, пробуем получить через WMI
        if not self.gpu_name:
            logger.info("NVML не дал результата, попытка через WMI...")
            self.gpu_name = self._get_gpu_name_windows()
            self.vram_gb = None  # для встроенной графики VRAM обычно не критичен
            if self.gpu_name:
                logger.info(f"GPU обнаружен (WMI): {self.gpu_name}")
            else:
                logger.warning("GPU не обнаружен ни через NVML, ни через WMI.")

    @staticmethod
    def get_display_info():
        """
        Возвращает словарь с текущим разрешением и частотой обновления основного монитора.
        Использует WinAPI (GetDC + GetDeviceCaps) на Windows.
        На других ОС возвращает заглушку.
        """
        import platform as _platform

        if _platform.system() != "Windows":
            logger.warning(
                "Определение разрешения и герцовки поддерживается только на Windows."
            )
            return {"resolution": "1920x1080", "hz": 60}

        try:
            import ctypes

            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            hdc = user32.GetDC(None)

            # Разрешение экрана
            width = gdi32.GetDeviceCaps(hdc, 8)  # HORZRES
            height = gdi32.GetDeviceCaps(hdc, 10)  # VERTRES
            resolution = f"{width}x{height}"

            # Частота обновления
            hz = gdi32.GetDeviceCaps(hdc, 116)  # VREFRESH
            user32.ReleaseDC(None, hdc)

            logger.info(f"Дисплей: разрешение={resolution}, герцовка={hz} Гц")
            return {"resolution": resolution, "hz": hz}
        except Exception as e:
            logger.warning(f"Не удалось определить параметры дисплея: {e}")
            return {"resolution": "1920x1080", "hz": 60}

    def get_gpu_temps(self):
        """Возвращает словарь с температурами GPU (gpu, hotspot)."""
        if not self.nvml_available:
            return {}
        try:
            import pynvml

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            temps = {
                "gpu": pynvml.nvmlDeviceGetTemperature(
                    handle, pynvml.NVML_TEMPERATURE_GPU
                ),
            }
            try:
                temps["hotspot"] = pynvml.nvmlDeviceGetTemperature(
                    handle, pynvml.NVML_TEMPERATURE_GPU_HOTSPOT
                )
            except Exception:
                temps["hotspot"] = None
            pynvml.nvmlShutdown()
            return temps
        except Exception:
            return {}
