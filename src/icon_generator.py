"""
Генератор иконки для системного трея (без внешних файлов)
"""

from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QBrush
from PySide6.QtCore import Qt


def create_fps_icon():
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Фон — красный круг
    painter.setBrush(QBrush(QColor("#C0392B")))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(2, 2, size - 4, size - 4)

    # Белые буквы FPS
    font = QFont("Segoe UI", 20, QFont.Bold)
    painter.setFont(font)
    painter.setPen(QColor("white"))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "FPS")
    painter.end()

    return QIcon(pixmap)
