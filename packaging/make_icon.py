"""Draw the application icon and write packaging/icon.icns and icon.png.

The icon is drawn with Qt so no image editor or extra dependency is needed:
a DIP chip on a blue rounded square. Run with:

    uv run python packaging/make_icon.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath

HERE = os.path.dirname(os.path.abspath(__file__))


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 1024, size / 1024)

    # Background: the macOS icon grid's rounded square (824 px inside 1024).
    bg = QPainterPath()
    bg.addRoundedRect(QRectF(100, 100, 824, 824), 185, 185)
    grad = QLinearGradient(QPointF(0, 100), QPointF(0, 924))
    grad.setColorAt(0, QColor("#3b82f6"))
    grad.setColorAt(1, QColor("#1d4ed8"))
    p.fillPath(bg, grad)

    # Pins: eight per side, drawn first so the body overlaps them.
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#e5e7eb"))
    for i in range(8):
        y = 300 + i * 60
        p.drawRoundedRect(QRectF(262, y, 70, 28), 6, 6)
        p.drawRoundedRect(QRectF(692, y, 70, 28), 6, 6)

    # Chip body with a notch and a pin-1 dot.
    body = QPainterPath()
    body.addRoundedRect(QRectF(312, 250, 400, 520), 28, 28)
    notch = QPainterPath()
    notch.addEllipse(QPointF(512, 250), 46, 46)
    p.fillPath(body.subtracted(notch), QColor("#111827"))
    p.setBrush(QColor("#374151"))
    p.drawEllipse(QPointF(370, 320), 18, 18)

    # A small "write" arrow on the chip.
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#60a5fa"))
    arrow = QPainterPath()
    arrow.moveTo(512, 640)
    arrow.lineTo(440, 550)
    arrow.lineTo(486, 550)
    arrow.lineTo(486, 420)
    arrow.lineTo(538, 420)
    arrow.lineTo(538, 550)
    arrow.lineTo(584, 550)
    arrow.closeSubpath()
    p.drawPath(arrow)
    p.end()
    return img


def main() -> int:
    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    draw(1024).save(os.path.join(HERE, "icon.png"))
    if sys.platform != "darwin":
        print("Wrote icon.png (icon.icns needs macOS's iconutil)")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        iconset = os.path.join(tmp, "icon.iconset")
        os.makedirs(iconset)
        for pts in (16, 32, 128, 256, 512):
            draw(pts).save(os.path.join(iconset, f"icon_{pts}x{pts}.png"))
            draw(pts * 2).save(os.path.join(iconset, f"icon_{pts}x{pts}@2x.png"))
        out = os.path.join(tmp, "icon.icns")
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", out], check=True)
        shutil.copy(out, os.path.join(HERE, "icon.icns"))
    print("Wrote icon.png and icon.icns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
