"""Native vector visuals and shared design system for the desktop application."""
import math
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHeaderView, QLabel,
                              QPushButton, QTableWidget, QVBoxLayout, QWidget)

STYLE = """
QWidget {font-family:'Segoe UI';font-size:13px;color:#202a3c;}
QMainWindow, #content {background:#f4f6fa;}
#sidebar {background:#101829;} #sidebar QLabel {color:#8592ab;}
#sidebar #brand {color:#ffffff;font-size:22px;font-weight:800;letter-spacing:2px;}
#sideTag {color:#8395be;font-size:10px;font-weight:600;letter-spacing:2px;}
#sidebar QPushButton {background:transparent;color:#9caac3;text-align:left;padding:14px 15px;border:0;border-radius:10px;font-weight:500;}
#sidebar QPushButton:checked {background:#233659;color:white;border-left:3px solid #7b9cff;font-weight:700;}
#sidebar QPushButton:hover {background:#1c2942;color:white;}
#sidebar #sideDemo {border:1px solid #3d4e6b;color:#c0cfff;background:#1c2942;}
#sidebar #sidePanel {background:#19243a;border:1px solid #273650;border-radius:12px;}
#title {font-size:26px;font-weight:700;color:#162237;}
#subtitle, #muted {color:#778297;}
#eyebrow {color:#5372ac;font-size:10px;font-weight:700;letter-spacing:2px;}
#card {background:white;border:1px solid #e4e9f2;border-radius:16px;}
#cardTitle {font-size:15px;font-weight:700;color:#1e2c43;}
#metricValue {font-size:29px;font-weight:700;color:#17253d;}
#metricAccent {font-size:29px;font-weight:700;color:#3865f1;}
#badge {background:#e8edf9;color:#426193;border:1px solid #dce4f4;border-radius:15px;padding:7px 13px;font-size:11px;font-weight:700;}
#badge[state="live"] {color:#117866;background:#dff5ed;border:1px solid #bfe8d7;}
#badge[state="demo"] {color:#926026;background:#fff1dc;border:1px solid #f1d8ad;}
#status {color:#56708e;background:#eaf0f9;border:1px solid #dbe5f3;border-radius:10px;padding:11px;}
#banner {background:#fff3df;color:#936423;border-radius:9px;padding:8px;font-size:11px;}
#hero {background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #1c2f60,stop:1 #2848a3);border-radius:20px;}
#heroTitle {color:white;font-size:35px;font-weight:700;}
#heroText {color:#b7c9f3;font-size:14px;}
#heroTag {color:#92b4ff;font-size:11px;font-weight:700;letter-spacing:2px;}
#heroButton {background:white;color:#284dba;border:0;padding:12px 20px;}
#heroSecondary {background:#304a83;color:#d4e1ff;border:1px solid #5b72a5;padding:12px 18px;}
#sectionCaption {color:#53627a;font-size:11px;font-weight:700;letter-spacing:1px;}
#readiness {background:#f2f5fb;border-radius:10px;padding:10px;color:#70809a;font-size:12px;}
#readiness[ready="true"] {background:#e9f7f0;color:#23735a;}
#empty {color:#7e8da5;font-size:13px;padding:18px;background:#f7f9fc;border-radius:10px;}
#videoCard {background:#101b30;border:1px solid #25334a;border-radius:16px;}
#videoCard QLabel {color:#91a6c7;}
#videoCard #cardTitle {color:#e4edff;}
#videoCard #cameraState {color:#a5bffc;background:#233957;border-radius:9px;padding:5px 9px;font-size:10px;font-weight:600;}
#smallValue {font-size:18px;font-weight:700;}
#number {font-size:11px;font-weight:700;color:#446ce6;background:#edf2ff;border-radius:9px;padding:5px 7px;}
QPushButton {background:white;border:1px solid #dce3ef;border-radius:9px;padding:9px 13px;font-weight:600;color:#526482;}
QPushButton:hover {background:#edf2ff;border:1px solid #b9c9ef;color:#345fc9;}
QPushButton:pressed {background:#dde7ff;}
QPushButton:disabled {color:#9da8bb;background:#f1f4f9;border-color:#e4e9f2;}
#primary {background:#3865f1;color:white;border:1px solid #3865f1;} #primary:hover {background:#284fd0;}
#primary:disabled {background:#e2e8f5;color:#98a5c3;border-color:#e2e8f5;}
#danger {color:#bd5b4d;background:#fff3ef;border:1px solid #f1d8d2;}
#danger:disabled {color:#a8aebc;background:#f4f6fa;border-color:#e5e9f1;}
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit {background:#f8faff;border:1px solid #dce4f1;border-radius:8px;padding:8px;color:#344666;selection-background-color:#3865f1;}
QLineEdit:focus,QTextEdit:focus,QComboBox:focus {border:1px solid #6d91fb;background:white;}
QComboBox QAbstractItemView {background:white;color:#344666;selection-background-color:#e9efff;selection-color:#234cc1;border:1px solid #dce4f1;}
QTableWidget {background:white;border:0;gridline-color:#edf1f7;alternate-background-color:#fafbfe;selection-background-color:#e9efff;selection-color:#254fb8;}
QHeaderView::section {background:#f6f8fc;color:#7d8ba4;border:0;border-bottom:1px solid #e8edf5;padding:10px;font-size:11px;font-weight:600;}
QTableWidget::item {padding:7px;} QScrollArea {border:0;background:transparent;}
QScrollBar:vertical {width:7px;background:transparent;} QScrollBar::handle:vertical {background:#d3dceb;border-radius:3px;min-height:25px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QScrollBar:horizontal {height:7px;background:transparent;} QScrollBar::handle:horizontal {background:#d3dceb;min-width:25px;border-radius:3px;}
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal {width:0;}
QCheckBox {spacing:9px;color:#51637e;} QCheckBox::indicator {width:17px;height:17px;border:1px solid #bdcbe1;border-radius:5px;background:white;}
QCheckBox::indicator:checked {background:#3865f1;border-color:#3865f1;}
QProgressBar {border:0;background:#edf2fa;border-radius:4px;max-height:7px;color:transparent;}
QProgressBar::chunk {background:#3865f1;border-radius:4px;}
QToolTip {background:#182944;color:white;border:0;padding:8px;border-radius:6px;}
"""

EVENT_COLORS = {"phone": "#e67d55", "multiple": "#b78bda", "absence": "#dea94a", "head": "#5aa4cc", "window": "#6890ef", "alt_tab": "#6890ef", "copy": "#8595c4", "paste": "#8595c4", "screenshot": "#8595c4", "camera": "#b35b68", "system": "#b35b68"}


def label(text, name=None):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(True)
    return widget


def button(text, handler, name=None):
    widget = QPushButton(text)
    if name:
        widget.setObjectName(name)
    widget.clicked.connect(handler)
    return widget


def card(title=None):
    widget = QFrame()
    widget.setObjectName("card")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)
    if title:
        layout.addWidget(label(title, "cardTitle"))
    return widget, layout


def table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.verticalHeader().hide()
    widget.verticalHeader().setDefaultSectionSize(41)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setAlternatingRowColors(True)
    widget.setShowGrid(False)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    widget.horizontalHeader().setStretchLastSection(True)
    return widget


def icon(kind, color="#97aaca"):
    pix = QPixmap(24, 24)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if kind == "home":
        for x, y in ((4, 4), (14, 4), (4, 14), (14, 14)):
            p.drawRoundedRect(QRectF(x, y, 6, 6), 1.5, 1.5)
    elif kind == "monitor":
        p.drawRoundedRect(QRectF(3, 4, 18, 13), 3, 3)
        p.drawLine(12, 17, 12, 21)
        p.drawLine(8, 21, 16, 21)
        p.drawPolyline([QPointF(6, 11), QPointF(9, 11), QPointF(11, 7), QPointF(14, 14), QPointF(16, 10), QPointF(18, 10)])
    elif kind == "archive":
        p.drawRoundedRect(QRectF(4, 6, 16, 15), 2, 2)
        p.drawRoundedRect(QRectF(3, 3, 18, 4), 1, 1)
        p.drawLine(9, 11, 15, 11)
    elif kind == "settings":
        for y, x in ((6, 9), (12, 16), (18, 7)):
            p.drawLine(3, y, 21, y)
            p.setBrush(QColor("#101829"))
            p.drawEllipse(QPointF(x, y), 2.6, 2.6)
    else:
        p.drawEllipse(QRectF(3, 3, 18, 18))
        p.drawLine(12, 10, 12, 17)
        p.drawPoint(12, 7)
    p.end()
    return QIcon(pix)


class ShieldArt(QWidget):
    """Vector illustration expressing the observation pipeline, not fake metrics."""
    def __init__(self):
        super().__init__()
        self.setMinimumSize(190, 190)
        self.setMaximumWidth(285)
        self.setAccessibleName("Эмблема QORGAU: защита и наблюдение")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(self.width() / 2, self.height() / 2)
        scale = min(self.width(), self.height()) / 250
        p.scale(scale, scale)
        p.setPen(QPen(QColor("#4a66a8"), 1))
        for radius in (76, 104, 126):
            p.drawEllipse(QPointF(0, 0), radius, radius)
        for angle in (30, 150, 270):
            rad = math.radians(angle)
            x, y = math.cos(rad) * 104, math.sin(rad) * 104
            p.setPen(QPen(QColor("#87aaff"), 1.5))
            p.setBrush(QColor("#294585"))
            p.drawEllipse(QPointF(x, y), 9, 9)
            p.setBrush(QColor("#91b2ff"))
            p.drawEllipse(QPointF(x, y), 3, 3)
        shield = QPainterPath(QPointF(0, -68))
        shield.lineTo(56, -45)
        shield.lineTo(50, 21)
        shield.cubicTo(45, 49, 21, 66, 0, 77)
        shield.cubicTo(-21, 66, -45, 49, -50, 21)
        shield.lineTo(-56, -45)
        shield.closeSubpath()
        gradient = QLinearGradient(-40, -60, 50, 70)
        gradient.setColorAt(0, QColor("#93b5ff"))
        gradient.setColorAt(1, QColor("#4e78e2"))
        p.setBrush(gradient)
        p.setPen(QPen(QColor("#a8c7ff"), 2))
        p.drawPath(shield)
        p.setPen(QPen(QColor("#e8f0ff"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPolyline([QPointF(-22, 2), QPointF(-6, 18), QPointF(27, -19)])


class Timeline(QWidget):
    eventSelected = Signal(int)

    def __init__(self):
        super().__init__()
        self.events = []
        self.duration = 0
        self.hits = []
        self.selected = -1
        self.setMinimumHeight(78)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Временная шкала событий экзамена")
        self.setAccessibleDescription("Выберите событие мышью либо стрелками влево и вправо, затем нажмите Enter. Все события также доступны в таблице.")

    def set_events(self, events, duration):
        self.events, self.duration = list(events), max(1, duration)
        if self.selected >= len(self.events):
            self.selected = -1
        self.update()

    def paintEvent(self, event):
        from .reports import clock
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        left, right, y = 8, self.width() - 8, 29
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#edf2fa"))
        p.drawRoundedRect(QRectF(left, y - 8, right - left, 16), 8, 8)
        self.hits = []
        for index, item in enumerate(self.events):
            start = item.start if hasattr(item, "start") else item["start"]
            end = item.end if hasattr(item, "end") else item["end"]
            kind = item.kind if hasattr(item, "kind") else item["kind"]
            x = left + min(1, start / self.duration) * (right - left)
            finish = left + min(1, (end if end is not None else self.duration) / self.duration) * (right - left)
            rect = QRectF(x - 3, y - 8 - (index % 3) * 3, max(7, finish - x), 16)
            p.setBrush(QColor(EVENT_COLORS.get(kind, "#7b91b8")))
            p.drawRoundedRect(rect, 3, 3)
            self.hits.append((rect.adjusted(-3, -5, 3, 5), index))
        p.setPen(QColor("#8a99b0"))
        p.setFont(QFont("Segoe UI", 10))
        for fraction in (0, .25, .5, .75, 1):
            x = left + fraction * (right - left)
            width = 76
            box = QRectF(max(0, min(self.width() - width, x - width / 2)), 49, width, 20)
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, clock(fraction * self.duration))
        if not self.events:
            p.setPen(QColor("#9aa9bf"))
            p.drawText(QRectF(0, 3, self.width(), 20), Qt.AlignmentFlag.AlignCenter, "Здесь появятся отметки событий")

    def mouseMoveEvent(self, event):
        from .engine import TITLES
        from .reports import clock
        for rect, index in reversed(self.hits):
            if rect.contains(event.position()):
                item = self.events[index]
                kind = item.kind if hasattr(item, "kind") else item["kind"]
                start = item.start if hasattr(item, "start") else item["start"]
                self.setToolTip(f"{clock(start)} · {TITLES.get(kind, kind)} · нажмите для выбора")
                self.setCursor(Qt.CursorShape.PointingHandCursor)
                return
        self.setToolTip("")
        self.unsetCursor()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            for rect, index in reversed(self.hits):
                if rect.contains(event.position()):
                    self.selected = index
                    self.eventSelected.emit(index)
                    return

    def keyPressEvent(self, event):
        if self.events and event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            direction = 1 if event.key() == Qt.Key.Key_Right else -1
            self.selected = (0 if direction == 1 else len(self.events) - 1) if self.selected < 0 else (self.selected + direction) % len(self.events)
            self.eventSelected.emit(self.selected)
            self.update()
            event.accept()
        elif self.events and self.selected >= 0 and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.eventSelected.emit(self.selected)
            event.accept()
        else:
            super().keyPressEvent(event)
