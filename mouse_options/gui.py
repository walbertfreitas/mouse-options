"""Janela principal do Mouse Options."""
from __future__ import annotations

import os
import sys
from functools import partial

from . import actions, art, controls, devices, i18n, solaar_import
from .client import DaemonClient, ServiceUnavailable
from .dialogs import INHERIT, ActionPickerDialog, AppPickerDialog, app_icon
from .i18n import T
from .qt import QtCore, QtGui, QtWidgets, Signal
from .store import ALL_APPS, Store

Qt = QtCore.Qt
W = QtWidgets
QColor, QPainter, QPen, QPainterPath = QtGui.QColor, QtGui.QPainter, QtGui.QPen, QtGui.QPainterPath

APP_NAME = "Mouse Options"

# Paleta clara e moderna
ACCENT = "#2563EB"          # azul de destaque
ACCENT_HOVER = "#1D4ED8"
ACCENT_SOFT = "#EFF4FF"
BG = "#F3F4F6"
SURFACE = "#FFFFFF"
BORDER = "#E5E7EB"
TEXT = "#111827"
MUTED = "#6B7280"

STYLE = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-size: 10pt; }}
QLabel, QCheckBox {{ background: transparent; }}
QDialog {{ background: {BG}; }}
QLabel#devicename {{ font-size: 22pt; font-weight: 800; letter-spacing: -0.3px; }}
QLabel#battery {{ background: #DCFCE7; color: #166534; border-radius: 11px; padding: 3px 10px; font-weight: 600; }}
QLabel#battery[low="true"] {{ background: #FEE2E2; color: #991B1B; }}
QLabel#battery[offline="true"] {{ background: #E5E7EB; color: #4B5563; }}
QLabel#banner {{ background: #FEF3C7; color: #92400E; border-radius: 10px; padding: 10px 12px; }}
QLabel#cardtitle {{ font-weight: 600; }}
QLabel#action {{ color: {ACCENT}; }}
QLabel#hint {{ color: {MUTED}; }}
QLabel#inherited {{ color: {MUTED}; font-style: italic; }}
QLabel#section {{ font-size: 12pt; font-weight: 600; }}
QLabel#bigkeys {{ font-size: 20pt; font-weight: 600; color: {ACCENT}; background: {SURFACE};
    border: 2px dashed #BFDBFE; border-radius: 12px; }}
QTabWidget::pane {{ border: none; background: transparent; }}
QTabWidget::tab-bar {{ alignment: center; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 8px 20px; margin: 0 4px; border-radius: 17px;
    font-weight: 600; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ background: {SURFACE}; color: {ACCENT}; border: 1px solid {BORDER}; }}
QPushButton {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 10px;
    padding: 7px 16px; font-weight: 500; }}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton:pressed {{ background: {ACCENT_SOFT}; }}
QPushButton:disabled {{ color: #9CA3AF; border-color: {BORDER}; }}
QPushButton#primary, QPushButton:default {{ background: {ACCENT}; color: white; border-color: {ACCENT}; }}
QPushButton:default:hover {{ background: {ACCENT_HOVER}; color: white; }}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; color: white; }}
QPushButton#appchip {{ border-radius: 17px; padding: 0 16px; min-height: 34px; max-height: 34px; }}
QPushButton#appchip:checked {{ background: {ACCENT}; color: white; border-color: {ACCENT}; }}
QPushButton#link {{ border: none; background: transparent; color: {ACCENT}; padding: 4px 8px; }}
QPushButton#link:hover {{ text-decoration: underline; }}
QFrame#card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px; }}
QFrame#card:hover, QFrame#card[active="true"] {{ border: 1px solid {ACCENT}; background: #FBFCFF; }}
QFrame#panel {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 16px; }}
QListWidget, QLineEdit, QComboBox {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px;
    padding: 6px; selection-background-color: {ACCENT_SOFT}; selection-color: {ACCENT}; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; border: 1px solid {BORDER}; selection-background-color: {ACCENT_SOFT};
    selection-color: {ACCENT}; }}
QListWidget::item {{ padding: 8px 8px; border-radius: 8px; margin: 1px 0; }}
QListWidget::item:hover {{ background: #F3F6FF; }}
QListWidget::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}
QSlider::groove:horizontal {{ height: 6px; background: {BORDER}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: white; border: 2px solid {ACCENT}; width: 10px; height: 10px;
    margin: -4px 0; border-radius: 7px; }}
QSlider::handle:horizontal:hover {{ background: {ACCENT_SOFT}; }}
QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border: 1.5px solid #9CA3AF; border-radius: 5px; background: {SURFACE}; }}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url(@CHECK@); }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: #D1D5DB; border-radius: 3px; }}
QScrollBar::handle:hover {{ background: #9CA3AF; }}
QScrollBar::handle:vertical {{ min-height: 32px; }}
QScrollBar::handle:horizontal {{ min-width: 32px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: none; background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QAbstractScrollArea::corner {{ background: transparent; }}
QToolTip {{ background: {TEXT}; color: white; border: none; padding: 6px; border-radius: 6px; }}
"""


def app_style() -> str:
    """Estilo final: gera a marca de seleção (✓) das caixas, desenhada pelo próprio app."""
    folder = os.path.join(os.path.expanduser("~"), ".cache", "mouse-options")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "check.png")
    pix = QtGui.QPixmap(18, 18)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("white"), 2.4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(4, 9.5), QtCore.QPointF(7.5, 13), QtCore.QPointF(14, 5.5)]))
    p.end()
    pix.save(path, "PNG")
    return STYLE.replace("@CHECK@", path)


class MouseView(W.QWidget):
    """Imagem do mouse com marcadores nos botões, ligados por linhas a etiquetas numeradas (estilo Options+)."""

    clicked = Signal(str)
    hovered = Signal(str)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(420, 440)
        self.callouts: list[tuple[str, int, tuple[float, float], str, float]] = []
        self.hover: str | None = None
        self.highlight: str | None = None
        self.selected: str | None = None
        self.art = None
        self.pixmap = None
        self.setMouseTracking(True)

    def set_controls(self, names: list[str], model: str = ""):
        self.art = art.for_mouse(model)
        self.pixmap = QtGui.QPixmap(self.art.path) if self.art else None
        self.callouts = []
        for i, name in enumerate(names, 1):
            if self.art and name in self.art.callouts:
                dot, side, label_y = self.art.callouts[name]
            elif not self.art and controls.position(name):
                dot = controls.position(name)
                side, label_y = ("L" if dot[0] < 0.5 else "R"), dot[1]
            else:
                continue
            self.callouts.append((name, i, dot, side, label_y))
        self._spread_labels()
        self.update()

    def _spread_labels(self):
        """Evita etiquetas sobrepostas do mesmo lado."""
        for side in ("L", "R"):
            items = sorted((c for c in self.callouts if c[3] == side), key=lambda c: c[4])
            last = -1.0
            for idx, c in enumerate(items):
                y = max(c[4], last + 0.085)
                last = y
                j = self.callouts.index(c)
                self.callouts[j] = (c[0], c[1], c[2], c[3], y)

    def set_highlight(self, name: str | None):
        if name != self.highlight:
            self.highlight = name
            self.update()

    def set_selected(self, name: str | None):
        if name != self.selected:
            self.selected = name
            self.update()

    # --- geometria
    def _image_rect(self) -> QtCore.QRectF:
        w, h = self.width(), self.height()
        aspect = (self.pixmap.width() / self.pixmap.height()) if self.pixmap else 0.58
        ih = min(h * 0.92, (w - 160) / aspect)
        iw = ih * aspect
        return QtCore.QRectF((w - iw) / 2, (h - ih) / 2, iw, ih)

    def _dot(self, pos) -> QtCore.QPointF:
        r = self._image_rect()
        return QtCore.QPointF(r.left() + pos[0] * r.width(), r.top() + pos[1] * r.height())

    def _badge(self, side, label_y) -> QtCore.QPointF:
        r = self._image_rect()
        x = r.left() - 46 if side == "L" else r.right() + 46
        return QtCore.QPointF(x, r.top() + label_y * r.height())

    # --- desenho
    def paintEvent(self, _ev):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = self._image_rect()
        # sombra suave no "chão"
        shadow = QtGui.QRadialGradient(QtCore.QPointF(r.center().x(), r.bottom() - r.height() * 0.03), r.width() * 0.5)
        shadow.setColorAt(0, QColor(17, 24, 39, 60))
        shadow.setColorAt(1, QColor(17, 24, 39, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(shadow)
        p.drawEllipse(QtCore.QRectF(r.left() + r.width() * 0.08, r.bottom() - r.height() * 0.07,
                                    r.width() * 0.84, r.height() * 0.08))
        if self.pixmap:
            p.drawPixmap(r.toRect(), self.pixmap)
        else:
            self._draw_generic(p, r)
        self._draw_callouts(p)

    def _draw_generic(self, p, r):
        body = QPainterPath()
        body.addRoundedRect(r.adjusted(r.width() * 0.12, 0, -r.width() * 0.12, 0), r.width() * 0.36, r.height() * 0.28)
        grad = QtGui.QLinearGradient(r.topLeft(), r.bottomRight())
        grad.setColorAt(0, QColor("#4B5563"))
        grad.setColorAt(1, QColor("#1F2937"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawPath(body)
        p.setPen(QPen(QColor("#111827"), 2))
        p.drawLine(QtCore.QPointF(r.center().x(), r.top() + 6), QtCore.QPointF(r.center().x(), r.top() + r.height() * 0.36))
        wheel = QtCore.QRectF(r.center().x() - r.width() * 0.05, r.top() + r.height() * 0.10,
                              r.width() * 0.10, r.height() * 0.16)
        p.setBrush(QColor("#D1D5DB"))
        p.drawRoundedRect(wheel, wheel.width() / 2, wheel.width() / 2)

    def _draw_callouts(self, p):
        font = p.font()
        font.setPixelSize(12)
        font.setBold(True)
        p.setFont(font)
        for name, number, dot, side, label_y in self.callouts:
            active = name in (self.hover, self.highlight, self.selected)
            d, b = self._dot(dot), self._badge(side, label_y)
            # linha guia: horizontal até perto da imagem e depois até o ponto
            elbow = QtCore.QPointF(b.x() + (22 if side == "L" else -22), b.y())
            p.setPen(QPen(QColor(ACCENT) if active else QColor("#9CA3AF"), 1.6 if active else 1.2))
            p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(b.x() + (14 if side == "L" else -14), b.y()), elbow, d]))
            # ponto sobre o botão
            p.setPen(QPen(QColor("white"), 2))
            p.setBrush(QColor(ACCENT))
            p.drawEllipse(d, 6 if active else 5, 6 if active else 5)
            if active:
                halo = QColor(ACCENT)
                halo.setAlpha(60)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(halo)
                p.drawEllipse(d, 12, 12)
            # etiqueta numerada
            p.setPen(QPen(QColor(ACCENT), 2))
            p.setBrush(QColor(ACCENT) if active else QColor("white"))
            p.drawEllipse(b, 14, 14)
            p.setPen(QColor("white") if active else QColor(ACCENT))
            p.drawText(QtCore.QRectF(b.x() - 14, b.y() - 14, 28, 28), Qt.AlignmentFlag.AlignCenter, str(number))

    # --- interação
    def _at(self, pos) -> str | None:
        for name, _n, dot, side, label_y in self.callouts:
            for c, radius in ((self._dot(dot), 14), (self._badge(side, label_y), 16)):
                if (c.x() - pos.x()) ** 2 + (c.y() - pos.y()) ** 2 <= radius ** 2:
                    return name
        return None

    def mouseMoveEvent(self, ev):  # noqa: N802
        name = self._at(ev.position())
        if name != self.hover:
            self.hover = name
            self.setCursor(Qt.CursorShape.PointingHandCursor if name else Qt.CursorShape.ArrowCursor)
            self.hovered.emit(name or "")
            self.update()

    def leaveEvent(self, _ev):  # noqa: N802
        if self.hover:
            self.hover = None
            self.hovered.emit("")
            self.update()

    def mousePressEvent(self, ev):  # noqa: N802
        name = self._at(ev.position())
        if name:
            self.clicked.emit(name)


class ElidedLabel(W.QLabel):
    """Texto de uma linha que, sem espaço, termina em "…" em vez de alargar o cartão."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setSizePolicy(W.QSizePolicy.Policy.Ignored, W.QSizePolicy.Policy.Preferred)

    def paintEvent(self, _ev):  # noqa: N802
        painter = QtGui.QPainter(self)
        text = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, self.width())
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.setFont(self.font())
        painter.drawText(self.rect(), int(self.alignment()), text)


class ControlCard(W.QFrame):
    def __init__(self, number: int, name: str, on_click, on_hover):
        super().__init__(objectName="card")
        self.name = name
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = W.QGridLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setHorizontalSpacing(12)
        badge = W.QLabel(str(number), alignment=Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(28, 28)
        badge.setStyleSheet(f"background: {ACCENT_SOFT}; color: {ACCENT}; border-radius: 14px; font-weight: 700;")
        self.title = W.QLabel(objectName="cardtitle")
        self.action = W.QLabel(objectName="action")
        self.note = ElidedLabel(objectName="inherited")   # na mesma linha da ação, para não alongar o cartão
        chevron = W.QLabel("›", objectName="hint")
        chevron.setStyleSheet("font-size: 18pt;")
        lay.addWidget(badge, 0, 0, 2, 1)
        lay.addWidget(self.title, 0, 1)
        line = W.QHBoxLayout()
        line.setSpacing(6)
        line.addWidget(self.action)
        line.addWidget(self.note, 1)
        lay.addLayout(line, 1, 1)
        lay.addWidget(chevron, 0, 2, 2, 1)
        lay.setColumnStretch(1, 1)
        self._on_click, self._on_hover = on_click, on_hover

    def set_active(self, active: bool):
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, _ev):  # noqa: N802
        self._on_click(self.name)

    def enterEvent(self, _ev):  # noqa: N802
        self._on_hover(self.name)

    def leaveEvent(self, _ev):  # noqa: N802
        self._on_hover("")


class MainWindow(W.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.settings = QtCore.QSettings("mouse-options", "mouse-options")
        i18n.set_language(self.settings.value("language", i18n.default_language()))
        self.store = Store()
        self.mice: list[devices.MouseInfo] = []
        self.current: devices.MouseInfo | None = None
        self.app = ALL_APPS
        self.pending_settings: dict[str, dict] = {}
        self.cards: dict[str, ControlCard] = {}
        self.selected: str | None = None     # botão escolhido (clicado ou apertado no mouse)

        self.client = DaemonClient(self)
        self.client.devices_changed.connect(self._on_discovered)
        self.client.button_pressed.connect(self._on_mouse_button)
        W.QApplication.instance().installEventFilter(self)
        self.apply_timer = QtCore.QTimer(self, singleShot=True, interval=600, timeout=self._apply_now)

        self._last_msg = ("", {})
        self._build()
        self._discover()
        QtCore.QTimer.singleShot(400, self._check_solaar)

    def _check_solaar(self):
        """Solaar e Mouse Options juntos brigam pelos botões do mouse: oferece desligar o Solaar."""
        if not solaar_import.solaar_running():
            return
        q = T("O Solaar está aberto. Ele e o Mouse Options controlam os botões do mouse ao mesmo tempo e "
              "um atrapalha o outro.\n\nFechar o Solaar e impedir que ele inicie com o computador? "
              "(Dá para desfazer apagando ~/.config/autostart/solaar.desktop.)")
        if W.QMessageBox.question(self, APP_NAME, q) == W.QMessageBox.StandardButton.Yes:
            solaar_import.disable_solaar()
            try:
                self.client.reload()   # reaplica os botões que o Solaar deixou do jeito dele
            except ServiceUnavailable:
                pass

    # ------------------------------------------------------------ montagem

    def _build(self):
        root = W.QWidget()
        self.setCentralWidget(root)
        outer = W.QVBoxLayout(root)
        outer.setContentsMargins(24, 18, 24, 12)
        outer.setSpacing(12)

        # cabeçalho: nome do mouse em destaque, bateria e seleção de aparelho
        top = W.QHBoxLayout()
        self.device_name = W.QLabel(objectName="devicename")
        self.battery = W.QLabel(objectName="battery")
        self.device_combo = W.QComboBox(minimumWidth=220)
        self.device_combo.currentIndexChanged.connect(self._select_device)
        self.refresh_btn = W.QPushButton(clicked=self._discover)
        top.addWidget(self.device_name)
        top.addSpacing(10)
        top.addWidget(self.battery, alignment=Qt.AlignmentFlag.AlignVCenter)
        top.addStretch(1)
        top.addWidget(self.device_combo)
        top.addWidget(self.refresh_btn)
        outer.addLayout(top)

        self.tabs = W.QTabWidget()
        self.tabs.addTab(self._build_buttons_tab(), "")
        self.tabs.addTab(self._build_pointer_tab(), "")
        self.tabs.addTab(self._build_easyswitch_tab(), "")
        self.tabs.currentChanged.connect(lambda i: self._set_apps_visible(i == 0))
        outer.addWidget(self.tabs, 1)

        bottom = W.QHBoxLayout()
        self.status = W.QLabel(objectName="hint")
        self.lang_combo = W.QComboBox()
        for code, name in i18n.LANGS.items():
            self.lang_combo.addItem(name, code)
        self.lang_combo.setCurrentIndex(list(i18n.LANGS).index(i18n.language()))
        self.lang_combo.currentIndexChanged.connect(self._on_language)
        self.lang_label = W.QLabel(objectName="hint")
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.lang_label)
        bottom.addWidget(self.lang_combo)
        outer.addLayout(bottom)
        self._retranslate()

    def _build_buttons_tab(self):
        page = W.QWidget()
        col = W.QVBoxLayout(page)
        col.setContentsMargins(0, 12, 0, 0)
        # perfis por aplicativo (barra de "pílulas")
        self.apps_row = W.QHBoxLayout()
        col.addLayout(self.apps_row)
        lay = W.QHBoxLayout()
        lay.setSpacing(16)
        col.addLayout(lay, 1)

        left = W.QFrame(objectName="panel")
        ll = W.QVBoxLayout(left)
        self.mouse_view = MouseView()
        self.mouse_view.clicked.connect(self._edit_control)
        self.mouse_view.hovered.connect(self._hover_from_view)
        ll.addWidget(self.mouse_view)
        lay.addWidget(left, 3)

        right = W.QFrame(objectName="panel")
        rl = W.QVBoxLayout(right)
        rl.setContentsMargins(16, 16, 16, 12)
        self.buttons_title = W.QLabel(objectName="section")
        self.buttons_hint = W.QLabel(objectName="hint", wordWrap=True)
        rl.addWidget(self.buttons_title)
        rl.addWidget(self.buttons_hint)
        scroll = self.cards_scroll = W.QScrollArea(widgetResizable=True)
        holder = W.QWidget()
        holder.setStyleSheet("background: transparent;")
        self.cards_box = W.QVBoxLayout(holder)
        self.cards_box.setContentsMargins(0, 4, 4, 4)
        self.cards_box.setSpacing(8)
        scroll.setWidget(holder)
        rl.addWidget(scroll, 1)
        self.reset_btn = W.QPushButton(clicked=self._reset_profile, objectName="link")
        rl.addWidget(self.reset_btn, alignment=Qt.AlignmentFlag.AlignRight)
        lay.addWidget(right, 2)
        return page

    def _build_pointer_tab(self):
        page = W.QWidget()
        outer = W.QVBoxLayout(page)
        outer.setContentsMargins(0, 16, 0, 0)
        panel = W.QFrame(objectName="panel")
        panel.setFixedWidth(640)
        panel.setSizePolicy(W.QSizePolicy.Policy.Fixed, W.QSizePolicy.Policy.Maximum)   # encolhe com o conteúdo
        lay = W.QVBoxLayout(panel)
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(10)
        self.speed_title = W.QLabel(objectName="section")
        self.speed = W.QSlider(Qt.Orientation.Horizontal)
        self.speed_value = W.QLabel(objectName="action")
        self.speed_value.setMinimumWidth(56)
        self.speed.valueChanged.connect(self._on_speed)
        self.invert = W.QCheckBox()
        self.invert.toggled.connect(lambda v: self._queue_setting("hires-smooth-invert", v))
        self.smooth = W.QCheckBox()
        self.smooth.toggled.connect(lambda v: self._queue_setting("hires-smooth-resolution", v))
        self.scroll_title = W.QLabel(objectName="section")
        self.pointer_hint = W.QLabel(objectName="hint", wordWrap=True)
        # recursos que só alguns mouses têm (aparecem quando o mouse informa)
        self.dpi_title = W.QLabel(objectName="section")
        self.dpi = W.QSlider(Qt.Orientation.Horizontal)
        self.dpi_value = W.QLabel(objectName="action")
        self.dpi_value.setMinimumWidth(80)
        self.dpi.valueChanged.connect(self._on_dpi)
        self.shift_title = W.QLabel(objectName="section")
        self.shift = W.QSlider(Qt.Orientation.Horizontal)
        self.shift.setRange(1, 50)
        self.shift_value = W.QLabel(objectName="action")
        self.shift_value.setMinimumWidth(150)
        self.shift.valueChanged.connect(self._on_shift)
        self.shift_hint = W.QLabel(objectName="hint", wordWrap=True)
        self.thumb_invert = W.QCheckBox()
        self.thumb_invert.toggled.connect(lambda v: self._queue_setting("thumb-scroll-invert", v))
        row = W.QHBoxLayout()
        row.addWidget(self.speed, 1)
        row.addWidget(self.speed_value)
        self.pointer_hint.setMinimumHeight(42)
        self.pointer_hint.setAlignment(Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.speed_title)
        lay.addLayout(row)
        lay.addSpacing(4)
        lay.addWidget(self.pointer_hint)
        dpi_row = W.QHBoxLayout()
        dpi_row.addWidget(self.dpi, 1)
        dpi_row.addWidget(self.dpi_value)
        lay.addWidget(self.dpi_title)
        lay.addLayout(dpi_row)
        lay.addSpacing(18)
        lay.addWidget(self.scroll_title)
        lay.addWidget(self.invert)
        lay.addWidget(self.smooth)
        lay.addWidget(self.thumb_invert)
        shift_row = W.QHBoxLayout()
        shift_row.addWidget(self.shift, 1)
        shift_row.addWidget(self.shift_value)
        lay.addSpacing(10)
        lay.addWidget(self.shift_title)
        lay.addLayout(shift_row)
        lay.addWidget(self.shift_hint)
        outer.addWidget(panel, alignment=Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)
        return page

    def _build_easyswitch_tab(self):
        page = W.QWidget()
        outer = W.QVBoxLayout(page)
        outer.setContentsMargins(0, 16, 0, 0)
        panel = W.QFrame(objectName="panel")
        panel.setFixedWidth(640)
        lay = W.QVBoxLayout(panel)
        lay.setContentsMargins(24, 22, 24, 22)
        self.es_title = W.QLabel(objectName="section")
        self.es_hint = W.QLabel(objectName="hint", wordWrap=True)
        self.es_list = W.QVBoxLayout()
        self.es_list.setSpacing(8)
        self.es_banner = W.QLabel(objectName="banner", wordWrap=True)
        self.es_banner.hide()
        lay.addWidget(self.es_title)
        lay.addWidget(self.es_hint)
        lay.addSpacing(8)
        lay.addWidget(self.es_banner)
        lay.addLayout(self.es_list)
        outer.addWidget(panel, alignment=Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)
        return page

    def _hover_from_view(self, name):
        for n, card in self.cards.items():
            card.set_active(n in (name, self.selected))

    def _hover_from_card(self, name):
        self.mouse_view.set_highlight(name or None)

    # ------------------------------------------------------------ idioma

    def _retranslate(self):
        self.refresh_btn.setText(T("Procurar mouses"))
        self.tabs.setTabText(0, T("Botões"))
        self.tabs.setTabText(1, T("Ponteiro e rolagem").replace("&", "&&"))
        self.tabs.setTabText(2, T("Easy-Switch"))
        self.lang_label.setText(T("Idioma:"))
        self.reset_btn.setText(T("Restaurar este perfil"))
        self.speed_title.setText(T("Velocidade do ponteiro"))
        self.invert.setText(T("Inverter a direção da rolagem"))
        self.smooth.setText(T("Rolagem suave (alta resolução)"))
        self.pointer_hint.setText(T("A velocidade é gravada no próprio mouse. O sistema também tem a sua "
                                    "própria aceleração em Configurações → Mouse."))
        self.es_hint.setText(T("Aparelhos pareados com este mouse. Para trocar, use o botão Easy-Switch do mouse."))
        self.es_title.setText(T("Easy-Switch"))
        self.scroll_title.setText(T("Rolagem"))
        self.dpi_title.setText(T("Sensibilidade (DPI)"))
        self.shift_title.setText(T("SmartShift (roda que solta sozinha)"))
        self.shift_hint.setText(T("Gire a roda rápido e ela passa a girar solta; devagar, volta a ter os cliques. "
                                  "Arraste para a esquerda para soltar com menos esforço."))
        self.thumb_invert.setText(T("Inverter a roda do polegar"))
        if hasattr(self, "current"):
            self._show_shift(self.shift.value())
        self.es_banner.setText(T("O mouse foi para outro aparelho (Easy-Switch). Ele volta a aparecer aqui "
                                 "assim que você trocar de volta para este computador."))
        self.buttons_title.setText(T("Botões"))
        self._msg(self._last_msg[0], **self._last_msg[1])
        self._refresh_all()

    def _on_language(self, index):
        code = self.lang_combo.itemData(index)
        i18n.set_language(code)
        self.settings.setValue("language", code)
        self._retranslate()

    # ------------------------------------------------------------ aparelhos

    def _discover(self):
        self._msg("Procurando mouses Logitech…")
        try:
            mice = self.client.devices()
        except ServiceUnavailable as e:
            self._msg("O serviço do Mouse Options não respondeu: {msg}", msg=str(e))
            return
        self._on_discovered(mice)

    def _on_discovered(self, mice):
        """Lista vinda do serviço (ele também manda os mouses conhecidos que estão desconectados)."""
        previous = self.current.key if self.current else None
        self.mice = mice
        imported = False
        rules = None
        for m in mice:
            if not self.store.known(m.key):   # primeira vez: traz o que a pessoa tinha no Solaar
                rules = rules if rules is not None else solaar_import.read_rules()
                self.store.device(m.key, m.codename)
                solaar_import.import_existing(self.store, m, rules)
                self.store.save()
                imported = True
        if imported:
            self.client.reload()
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for m in mice:
            self.device_combo.addItem(m.codename or m.name, m.key)
        self.device_combo.blockSignals(False)
        if mice:
            self._msg("{n} mouse(s) encontrado(s).", n=sum(m.online for m in mice))
            keys = [m.key for m in mice]
            index = keys.index(previous) if previous in keys else 0
            self.device_combo.setCurrentIndex(index)
            self._select_device(index, keep_app=previous == keys[index])
        else:
            self.current = None
            self._msg("Nenhum mouse Logitech encontrado. Ligue o mouse e clique em Procurar mouses.")
            self._refresh_all()

    def _select_device(self, index, keep_app=False):
        self.current = self.mice[index] if 0 <= index < len(self.mice) else None
        if not keep_app:
            self.app = ALL_APPS
            self.selected = None
        self._refresh_all()

    # ------------------------------------------------------------ atualização da tela

    def _refresh_all(self):
        if not hasattr(self, "cards_box"):
            return
        self._refresh_header()
        self._refresh_apps()
        self._refresh_buttons()
        self._refresh_pointer()
        self._refresh_easyswitch()

    @staticmethod
    def _clear(layout):
        while layout.count():
            w = layout.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def _refresh_header(self):
        m = self.current
        self.device_name.setText((m.codename or m.name) if m else APP_NAME)
        self.device_combo.setVisible(len(self.mice) > 1)
        if not m or (m.battery is None and m.online):
            self.battery.hide()
            return
        self.battery.show()
        if m.online:
            self.battery.setText(("⚡ " if m.charging else "") + T("Bateria: {pct}%", pct=m.battery))
        else:
            self.battery.setText(T("Em outro aparelho"))
        self.battery.setProperty("offline", "false" if m.online else "true")
        self.battery.setProperty("low", "true" if m.online and m.battery <= 20 and not m.charging else "false")
        self.battery.style().unpolish(self.battery)
        self.battery.style().polish(self.battery)

    def _refresh_apps(self):
        self._clear(self.apps_row)
        if not self.current:
            return
        label = W.QLabel(T("Configurar para:"), objectName="hint")
        self.apps_row.addWidget(label)
        key = self.current.key
        for app in [ALL_APPS] + self.store.apps(key):
            name = T("Todos os aplicativos") if app == ALL_APPS else self.store.app_name(key, app)
            chip = W.QPushButton(name, objectName="appchip", checkable=True, checked=app == self.app)
            chip.clicked.connect(partial(self._select_app, app))
            if app != ALL_APPS:
                chip.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                chip.customContextMenuRequested.connect(partial(self._app_menu, app, chip))
            self.apps_row.addWidget(chip)
        add = W.QPushButton(T("+ Adicionar aplicativo"), objectName="appchip")
        add.clicked.connect(self._add_app)
        self.apps_row.addWidget(add)
        self.apps_row.addStretch(1)
        self._set_apps_visible(self.tabs.currentIndex() == 0)

    def _refresh_buttons(self):
        self._clear(self.cards_box)
        self.cards = {}
        m = self.current
        if not m:
            self.mouse_view.set_controls([])
            self.buttons_hint.setText("")
            self.reset_btn.setVisible(False)   # sem mouse, não há perfil para restaurar
            return
        names = [c.name for c in m.controls]
        self.mouse_view.set_controls(names, f"{m.codename} {m.name}")
        where = T("todos os aplicativos") if self.app == ALL_APPS else self.store.app_name(m.key, self.app)
        self.buttons_hint.setText(T("Clique num botão (no desenho ou na lista) para escolher o que ele faz em {where}.",
                                    where=where))
        for i, c in enumerate(m.controls, 1):
            card = ControlCard(i, c.name, self._edit_control, self._hover_from_card)
            spec, inherited = self.store.effective(m.key, self.app, c.name)
            card.title.setText(controls.label(c.name))
            card.action.setText(actions.describe(spec))
            card.note.setText("· " + T("igual a Todos os aplicativos") if inherited else "")
            card.note.setToolTip(card.note.text()[2:])
            card.note.setVisible(inherited)
            card.set_active(c.name == self.selected)
            self.cards_box.addWidget(card)
            self.cards[c.name] = card
        self.mouse_view.set_selected(self.selected)
        self.reset_btn.setVisible(True)

    def _refresh_pointer(self):
        m = self.current
        has_speed = bool(m and m.pointer_speed is not None)
        has_dpi = bool(m and m.dpi is not None and m.dpi_choices)
        has_shift = bool(m and m.smart_shift is not None)
        for w in (self.speed, self.speed_value, self.speed_title):
            w.setVisible(has_speed)
        for w in (self.dpi, self.dpi_value, self.dpi_title):
            w.setVisible(has_dpi)
        for w in (self.shift, self.shift_value, self.shift_title, self.shift_hint):
            w.setVisible(has_shift)
        self.invert.setVisible(bool(m and m.invert_scroll is not None))
        self.smooth.setVisible(bool(m and m.smooth_scroll is not None))
        self.thumb_invert.setVisible(bool(m and m.thumb_invert is not None))
        if not m:
            return
        pending = self.pending_settings.get(m.key, {})
        widgets = (self.speed, self.invert, self.smooth, self.dpi, self.shift, self.thumb_invert)
        for w in widgets:
            w.blockSignals(True)
        if has_dpi:
            self.dpi.setRange(0, len(m.dpi_choices) - 1)
            want = pending.get("dpi", m.dpi)
            self.dpi.setValue(min(range(len(m.dpi_choices)), key=lambda i: abs(m.dpi_choices[i] - want)))
            self.dpi_value.setText(f"{m.dpi_choices[self.dpi.value()]} DPI")
        if has_shift:
            self.shift.setValue(pending.get("smart-shift", m.smart_shift))
            self._show_shift(self.shift.value())
        if m.thumb_invert is not None:
            self.thumb_invert.setChecked(pending.get("thumb-scroll-invert", m.thumb_invert))
        if has_speed:
            self.speed.setRange(*m.pointer_range)
            self.speed.setValue(pending.get("pointer_speed", m.pointer_speed))
            self._show_speed(self.speed.value())
        if m.invert_scroll is not None:
            self.invert.setChecked(pending.get("hires-smooth-invert", m.invert_scroll))
        if m.smooth_scroll is not None:
            self.smooth.setChecked(pending.get("hires-smooth-resolution", m.smooth_scroll))
        for w in widgets:
            w.blockSignals(False)

    def _refresh_easyswitch(self):
        self._clear(self.es_list)
        m = self.current
        self.es_banner.setVisible(bool(m and not m.online))
        if not m or not m.hosts:
            self.es_list.addWidget(W.QLabel(T("Este mouse não informa os aparelhos pareados."), objectName="hint"))
            return
        for i, host in enumerate(m.hosts):
            card = W.QFrame(objectName="card")
            lay = W.QHBoxLayout(card)
            num = W.QLabel(f"{i + 1}", alignment=Qt.AlignmentFlag.AlignCenter)
            num.setFixedSize(30, 30)
            on = m.online and i == m.current_host
            num.setStyleSheet(f"background: {ACCENT if on else ACCENT_SOFT}; color: {'white' if on else ACCENT}; "
                              "border-radius: 15px; font-weight: 700;")
            lay.addWidget(num)
            lay.addWidget(W.QLabel(host or T("(vazio)")), 1)
            if on:
                lay.addWidget(W.QLabel(T("● conectado agora"), objectName="action"))
            self.es_list.addWidget(card)

    # ------------------------------------------------------------ edição

    def _set_apps_visible(self, visible):
        for i in range(self.apps_row.count()):
            w = self.apps_row.itemAt(i).widget()
            if w:
                w.setVisible(visible)

    def _select_app(self, app):
        self.app = app
        self._refresh_apps()
        self._refresh_buttons()

    def _add_app(self):
        if not self.current:
            return
        d = AppPickerDialog(self, T("Configuração específica para qual aplicativo?"))
        if d.exec() and d.choice:
            _app, ident, name = d.choice
            self.store.add_app(self.current.key, ident, name)
            self.store.save()
            self._select_app(ident)

    def _app_menu(self, app, chip, pos):
        menu = W.QMenu(self)
        remove = menu.addAction(T("Remover configuração deste aplicativo"))
        if menu.exec(chip.mapToGlobal(pos)) == remove:
            self.store.remove_app(self.current.key, app)
            self.store.save()
            if self.app == app:
                self.app = ALL_APPS
            self._refresh_apps()
            self._refresh_buttons()
            self._schedule_apply()

    def _edit_control(self, name):
        m = self.current
        if not m:
            return
        control = next(c for c in m.controls if c.name == name)
        self._select_control(name)
        spec, inherited = self.store.effective(m.key, self.app, name)
        d = ActionPickerDialog(self, controls.label(name), None if inherited else spec,
                               allow_gestures=control.gestures, in_app_profile=self.app != ALL_APPS)
        accepted = d.exec()
        self._select_control(None)  # terminou de configurar: o botão volta a ficar desmarcado
        if not accepted or d.result_spec is None:
            return
        new = None if d.result_spec is INHERIT else d.result_spec
        if self.app == ALL_APPS and new is not None and new.get("id") == "default":
            new = None  # padrão em "Todos" = sem regra
        self.store.set(m.key, self.app, name, new)
        self.store.save()
        self._refresh_buttons()
        self._schedule_apply()

    def _reset_profile(self):
        m = self.current
        if not m:
            return
        q = T("Voltar todos os botões ao padrão do mouse em {where}?",
              where=T("todos os aplicativos") if self.app == ALL_APPS else self.store.app_name(m.key, self.app))
        if W.QMessageBox.question(self, APP_NAME, q) != W.QMessageBox.StandardButton.Yes:
            return
        for c in m.controls:
            self.store.set(m.key, self.app, c.name, None)
        self.store.save()
        self._refresh_buttons()
        self._schedule_apply()

    def _select_control(self, name):
        """Marca um botão como escolhido: no desenho e na lista (rolando até ele)."""
        self.selected = name
        for n, card in self.cards.items():
            card.set_active(n == name)
        self.mouse_view.set_selected(name)
        if name in self.cards:
            self.cards_scroll.ensureWidgetVisible(self.cards[name], 0, 12)

    # ------------------------------------------------------------ mouse ao vivo

    def _on_mouse_button(self, key, cid):
        """Um botão foi apertado no mouse: com a janela em uso, seleciona esse botão na tela."""
        m = self.current
        if not m or m.key != key or not self.isActiveWindow():
            return
        control = next((c for c in m.controls if c.cid == cid), None)
        if control:
            self._pressed(control.name)

    def _pressed(self, name):
        self.tabs.setCurrentIndex(0)
        self._select_control(name)
        self._msg("Você apertou: {name}. Clique nele para escolher a ação.", name=partial(controls.label, name))

    def eventFilter(self, obj, ev):  # noqa: N802
        """Botões que não estão desviados chegam como cliques comuns: também selecionam o botão."""
        if self.current and self.isActiveWindow() and isinstance(obj, QtGui.QWindow):
            name = None
            if ev.type() == QtCore.QEvent.Type.MouseButtonPress:
                name = {Qt.MouseButton.MiddleButton: "Middle Button", Qt.MouseButton.BackButton: "Back Button",
                        Qt.MouseButton.ForwardButton: "Forward Button"}.get(ev.button())
            elif ev.type() == QtCore.QEvent.Type.Wheel and ev.angleDelta().y() == 0 and ev.pixelDelta().isNull():
                dx = ev.angleDelta().x()  # inclinar a roda gera rolagem horizontal "em degraus"
                if dx and dx % 120 == 0:
                    name = "Left Tilt" if dx > 0 else "Right Tilt"
            if name and any(c.name == name for c in self.current.controls):
                self._pressed(name)
        return super().eventFilter(obj, ev)

    def _on_dpi(self, index):
        m = self.current
        if not m or not m.dpi_choices:
            return
        value = m.dpi_choices[index]
        self.dpi_value.setText(f"{value} DPI")
        self._queue_setting("dpi", value)

    def _show_shift(self, value):
        if value <= 1:
            self.shift_value.setText(T("Sempre solta"))
        elif value >= 50:
            self.shift_value.setText(T("Sempre com cliques"))
        else:
            self.shift_value.setText(T("Solta a partir de {n}", n=value))

    def _on_shift(self, value):
        self._show_shift(value)
        self._queue_setting("smart-shift", value)

    def _show_speed(self, value):
        self.speed_value.setText(f"{value / 256:.2f}×")

    def _on_speed(self, value):
        self._show_speed(value)
        self._queue_setting("pointer_speed", value)

    def _queue_setting(self, name, value):
        if not self.current:
            return
        self.pending_settings.setdefault(self.current.key, {})[name] = value
        self._schedule_apply()

    # ------------------------------------------------------------ aplicar

    def _schedule_apply(self):
        self._msg("Alterações pendentes…")
        self.apply_timer.start()

    def _apply_now(self):
        """Salva e avisa o serviço: vale na hora, sem reiniciar nada."""
        settings, self.pending_settings = self.pending_settings, {}
        try:
            self.store.save()
            self.client.reload()
            for key, values in settings.items():
                self.client.set_settings(key, values)
        except ServiceUnavailable as e:
            self._msg("Erro ao aplicar: {msg}", msg=str(e))
            return
        self._msg("Pronto! As alterações já estão valendo.")

    def _msg(self, text, **kw):
        """Mensagem na barra de baixo (texto em português; é traduzida e lembrada para trocas de idioma)."""
        self._last_msg = (text, kw)
        kw = {k: v() if callable(v) else v for k, v in kw.items()}   # funções: textos que também mudam de idioma
        self.status.setText(T(text, **kw) if text else "")

    def closeEvent(self, ev):  # noqa: N802
        if self.apply_timer.isActive():
            self.apply_timer.stop()
            self._apply_now()
        ev.accept()


def _native_title_bar():
    """No GNOME com Wayland, o Qt desenha a barra de título por conta própria, fora do padrão do sistema;
    pelo XWayland quem desenha é o GNOME, igual aos outros apps. (No KDE e no X11 já fica certo.)"""
    gnome = "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper().split(":")
    if gnome and os.environ.get("WAYLAND_DISPLAY") and os.environ.get("DISPLAY") \
            and "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "xcb"
        os.environ.setdefault("RESOURCE_NAME", "mouse-options")   # WM_CLASS: liga a janela ao atalho do menu


def main():
    _native_title_bar()
    app = W.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName("mouse-options")
    app.setStyleSheet(app_style())
    icon = os.path.join(os.path.dirname(__file__), "icon.svg")
    if os.path.exists(icon):
        app.setWindowIcon(QtGui.QIcon(icon))
    win = MainWindow()
    win.resize(1180, 760)
    win.show()
    sys.exit(app.exec())
