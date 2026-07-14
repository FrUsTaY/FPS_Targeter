"""
Виджеты живого мониторинга производительности для FPS Targeter.
"""

import psutil
import logging

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGroupBox,
    QSizePolicy,
    QPushButton,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QPainterPath, QLinearGradient, QColor, QPen, QFont

logger = logging.getLogger("PerfWidgets")


# ─────────────────────────────────────────────
#  Живой мини-график
# ─────────────────────────────────────────────
class MiniGraph(QWidget):
    def __init__(self, color="#00FFCC", history=40, parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self.history = history
        self.data = [0.0] * history
        self.setFixedHeight(52)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("background-color: #0D1826; border-radius: 4px;")

    def push(self, value: float):
        self.data.append(max(0.0, min(100.0, float(value))))
        self.data.pop(0)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        n = len(self.data)
        if n < 2:
            return

        def px(i):
            return i * w / (n - 1)

        def py(v):
            return h - 4 - v / 100.0 * (h - 8)

        pts = [(px(i), py(v)) for i, v in enumerate(self.data)]

        # заливка
        fill = QPainterPath()
        fill.moveTo(pts[0][0], pts[0][1])
        for x, y in pts[1:]:
            fill.lineTo(x, y)
        fill.lineTo(w, h)
        fill.lineTo(0, h)
        fill.closeSubpath()

        grad = QLinearGradient(0, 0, 0, h)
        top_c = QColor(self.color)
        top_c.setAlpha(110)
        bot_c = QColor(self.color)
        bot_c.setAlpha(0)
        grad.setColorAt(0, top_c)
        grad.setColorAt(1, bot_c)
        p.fillPath(fill, grad)

        # линия
        line = QPainterPath()
        line.moveTo(pts[0][0], pts[0][1])
        for x, y in pts[1:]:
            line.lineTo(x, y)

        pen = QPen(self.color, 2.0)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.drawPath(line)


# ─────────────────────────────────────────────
#  Дуговой индикатор VRAM
# ─────────────────────────────────────────────
class ArcGauge(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self._used_gb = 0.0
        self._total_gb = 0.0
        self.setFixedSize(130, 90)
        self.setStyleSheet("background-color: transparent;")

    def set_value(self, used_gb: float, total_gb: float):
        self._used_gb = used_gb
        self._total_gb = total_gb
        self._value = min(used_gb / total_gb, 1.0) if total_gb > 0 else 0.0
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        r = 42
        cx, cy = w // 2, h - 8

        v = self._value
        if v < 0.75:
            arc_color = QColor("#00FFCC")
        elif v < 0.90:
            arc_color = QColor("#FFC107")
        else:
            arc_color = QColor("#F44336")

        rx = cx - r
        ry = cy - r
        rw = rh = r * 2

        # Фоновая дуга
        pen_bg = QPen(QColor("#2A3A4A"), 9, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen_bg)
        p.drawArc(rx, ry, rw, rh, 180 * 16, 180 * 16)

        # Заполненная дуга
        pen_fg = QPen(arc_color, 9, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen_fg)
        span = int(180 * 16 * self._value)
        if span > 0:
            p.drawArc(rx, ry, rw, rh, 180 * 16, -span)

        # Значение
        p.setPen(arc_color)
        font_big = QFont("Segoe UI", 11, QFont.Bold)
        p.setFont(font_big)
        p.drawText(
            0,
            cy - 20,
            w,
            20,
            Qt.AlignHCenter,
            f"{self._used_gb:.1f}/{self._total_gb:.0f}",
        )

        # Подпись
        p.setPen(QColor("#8892B0"))
        font_small = QFont("Segoe UI", 8)
        p.setFont(font_small)
        p.drawText(0, cy - 4, w, 14, Qt.AlignHCenter, "GB USED")


# ─────────────────────────────────────────────
#  Кнопки пресетов
# ─────────────────────────────────────────────
PRESET_BUTTONS = ["Низкие", "Средние", "Высокие", "Ультра", "Макс.", "Кино"]


class PresetButtonRow(QWidget):
    """
    Строка кнопок пресетов. Активный подсвечивается зелёным.
    Только визуал — не меняет логику расчёта.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        for name in PRESET_BUTTONS:
            btn = QPushButton(name)
            btn.setFixedHeight(28)
            btn.setEnabled(False)  # только отображение, не кликабельно
            btn.setStyleSheet(self._style_inactive())
            self._buttons[name] = btn
            layout.addWidget(btn)

    def _style_active(self):
        return """
            QPushButton {
                background-color: #00C8A5;
                border: 1px solid #00FFCC;
                border-radius: 5px;
                color: #000000;
                font-weight: bold;
                font-size: 9pt;
            }
        """

    def _style_inactive(self):
        return """
            QPushButton {
                background-color: #101A2C;
                border: 1px solid #1A2234;
                border-radius: 5px;
                color: #8892B0;
                font-size: 9pt;
            }
        """

    def set_active(self, preset_name: str):
        """Подсветить кнопку с именем preset_name."""
        for name, btn in self._buttons.items():
            if name == preset_name:
                btn.setStyleSheet(self._style_active())
            else:
                btn.setStyleSheet(self._style_inactive())


# ─────────────────────────────────────────────
#  Блок «Real-time Performance» с температурой
# ─────────────────────────────────────────────
class LiveMonitorWidget(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("⚡ Real-time Performance", parent)
        self._nvml_ok = False
        self._nvml_handle = None
        self._init_nvml()
        self._build_ui()
        self._start_timer()

    def _init_nvml(self):
        try:
            import pynvml

            pynvml.nvmlInit()
            self._nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self._nvml_ok = True
        except Exception as e:
            logger.warning(f"LiveMonitor: NVML недоступен — {e}")

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 16, 8, 8)
        root.setSpacing(10)

        # --- CPU ---
        cpu_col = QVBoxLayout()
        cpu_col.setSpacing(3)
        self._cpu_label = QLabel("CPU  0%")
        self._cpu_label.setStyleSheet(
            "color:#00FFCC; font-weight:bold; font-size:11px; background:transparent;"
        )
        self._cpu_graph = MiniGraph(color="#00FFCC")
        cpu_col.addWidget(self._cpu_label)
        cpu_col.addWidget(self._cpu_graph)
        root.addLayout(cpu_col, stretch=3)

        # --- GPU + температура ---
        gpu_col = QVBoxLayout()
        gpu_col.setSpacing(3)
        self._gpu_label = QLabel("GPU  0%")
        self._gpu_label.setStyleSheet(
            "color:#00E5FF; font-weight:bold; font-size:11px; background:transparent;"
        )
        self._gpu_graph = MiniGraph(color="#00E5FF")
        gpu_col.addWidget(self._gpu_label)
        gpu_col.addWidget(self._gpu_graph)
        root.addLayout(gpu_col, stretch=3)

        # --- VRAM дуга ---
        vram_col = QVBoxLayout()
        vram_col.setAlignment(Qt.AlignCenter)
        vram_col.setSpacing(2)
        self._arc = ArcGauge()
        self._vram_sub = QLabel("нет данных")
        self._vram_sub.setAlignment(Qt.AlignCenter)
        self._vram_sub.setStyleSheet(
            "color:#8892B0; font-size:8px; background:transparent;"
        )
        vram_col.addWidget(self._arc, alignment=Qt.AlignCenter)
        vram_col.addWidget(self._vram_sub)
        root.addLayout(vram_col, stretch=2)

        self.setStyleSheet("""
            QGroupBox {
                border: 1px solid #1E3A5A;
                border-radius: 8px;
                margin-top: 10px;
                background-color: #080E18;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 6px;
                color: #00FFCC;
                font-weight: bold;
            }
        """)

    def _start_timer(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(900)

    def _tick(self):
        # CPU
        try:
            cpu_pct = psutil.cpu_percent(interval=None)
        except Exception:
            cpu_pct = 0.0

        self._cpu_graph.push(cpu_pct)
        self._cpu_label.setText(f"CPU  {cpu_pct:.0f}%")

        # GPU + VRAM + температура
        gpu_pct = 0.0
        vram_used = 0.0
        vram_total = 0.0
        gpu_temp = None

        if self._nvml_ok:
            try:
                import pynvml

                util = pynvml.nvmlDeviceGetUtilizationRates(self._nvml_handle)
                gpu_pct = float(util.gpu)
                mem = pynvml.nvmlDeviceGetMemoryInfo(self._nvml_handle)
                vram_used = mem.used / 1024**3
                vram_total = mem.total / 1024**3
                gpu_temp = pynvml.nvmlDeviceGetTemperature(
                    self._nvml_handle, pynvml.NVML_TEMPERATURE_GPU
                )
            except Exception as e:
                logger.debug(f"LiveMonitor GPU tick error: {e}")

        self._gpu_graph.push(gpu_pct)

        # Метка GPU: процент + температура если доступна
        if gpu_temp is not None:
            # Цвет температуры
            if gpu_temp < 70:
                temp_color = "#00FFCC"
            elif gpu_temp < 85:
                temp_color = "#FFC107"
            else:
                temp_color = "#F44336"
            self._gpu_label.setText(
                f"GPU  {gpu_pct:.0f}%  "
                f"<span style='color:{temp_color}'>· {gpu_temp}°C</span>"
            )
        else:
            self._gpu_label.setText(f"GPU  {gpu_pct:.0f}%")

        if vram_total > 0:
            self._arc.set_value(vram_used, vram_total)
            self._vram_sub.setText(f"{vram_used:.1f} / {vram_total:.0f} GB")

    def stop(self):
        if hasattr(self, "_timer"):
            self._timer.stop()
