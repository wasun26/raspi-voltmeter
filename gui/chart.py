"""Plotting helpers with a small PyQt6 fallback when pyqtgraph is unavailable."""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget


class SimpleCurve:
    def __init__(self, widget, color):
        self.widget = widget
        self.color = QColor(color)
        self.x = []
        self.y = []

    def setData(self, x, y):
        self.x = list(x)
        self.y = list(y)
        self.widget.update()


class SimplePlotWidget(QWidget):
    """Tiny line plot compatible with the subset of pyqtgraph used here."""

    def __init__(self):
        super().__init__()
        self._title = ""
        self._left_label = "Voltage"
        self._bottom_label = "Time"
        self._curves = []
        self.setMinimumHeight(240)

    def setLabel(self, axis, text, units=None):
        label = f"{text} ({units})" if units else text
        if axis == "left":
            self._left_label = label
        elif axis == "bottom":
            self._bottom_label = label
        self.update()

    def setTitle(self, title):
        self._title = title
        self.update()

    def plot(self, pen=None, name=None):
        color = "#2E7D32"
        if isinstance(pen, dict):
            color = pen.get("color", color)
        curve = SimpleCurve(self, color)
        self._curves.append(curve)
        return curve

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        margin_left = 58
        margin_right = 18
        margin_top = 34
        margin_bottom = 42
        plot_rect = QRectF(
            margin_left,
            margin_top,
            max(1, self.width() - margin_left - margin_right),
            max(1, self.height() - margin_top - margin_bottom),
        )

        painter.setPen(QPen(QColor("#d0d0d0"), 1))
        painter.drawRect(plot_rect)
        for i in range(1, 4):
            y = plot_rect.top() + plot_rect.height() * i / 4
            painter.drawLine(QPointF(plot_rect.left(), y), QPointF(plot_rect.right(), y))

        painter.setPen(QColor("#333333"))
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(0, 6, self.width(), 22, Qt.AlignmentFlag.AlignCenter, self._title)

        label_font = QFont()
        label_font.setPointSize(9)
        painter.setFont(label_font)
        painter.drawText(
            int(plot_rect.left()),
            self.height() - 26,
            int(plot_rect.width()),
            18,
            Qt.AlignmentFlag.AlignCenter,
            self._bottom_label,
        )
        painter.save()
        painter.translate(14, plot_rect.center().y())
        painter.rotate(-90)
        painter.drawText(
            int(-plot_rect.height() / 2),
            0,
            int(plot_rect.height()),
            18,
            Qt.AlignmentFlag.AlignCenter,
            self._left_label,
        )
        painter.restore()

        all_x = [value for curve in self._curves for value in curve.x]
        all_y = [value for curve in self._curves for value in curve.y]
        if not all_x or not all_y:
            painter.setPen(QColor("#777777"))
            painter.drawText(plot_rect, Qt.AlignmentFlag.AlignCenter, "Waiting for data")
            return

        x_min, x_max = min(all_x), max(all_x)
        y_min, y_max = min(all_y), max(all_y)
        if x_min == x_max:
            x_max = x_min + 1.0
        if y_min == y_max:
            pad = max(abs(y_min) * 0.1, 0.001)
            y_min -= pad
            y_max += pad
        else:
            pad = (y_max - y_min) * 0.08
            y_min -= pad
            y_max += pad

        def map_point(x, y):
            px = plot_rect.left() + ((x - x_min) / (x_max - x_min)) * plot_rect.width()
            py = plot_rect.bottom() - ((y - y_min) / (y_max - y_min)) * plot_rect.height()
            return QPointF(px, py)

        for curve in self._curves:
            if len(curve.x) < 2 or len(curve.y) < 2:
                continue
            painter.setPen(QPen(curve.color, 2))
            points = [map_point(x, y) for x, y in zip(curve.x, curve.y)]
            for start, end in zip(points, points[1:]):
                painter.drawLine(start, end)


def make_pen(color, width=2):
    try:
        import pyqtgraph as pg

        return pg.mkPen(color=color, width=width)
    except Exception:
        return {"color": color, "width": width}


def create_plot_widget():
    try:
        import pyqtgraph as pg

        return pg.PlotWidget()
    except Exception:
        return SimplePlotWidget()


def normalize_data(data):
    if not data:
        return []
    return data
