"""Janelas de escolha: ação, atalho de teclado, aplicativo e gestos."""
from __future__ import annotations

import os
import sys

from . import actions, apps
from .i18n import T
from .qt import QtCore, QtGui, QtWidgets

Qt = QtCore.Qt
W = QtWidgets
INHERIT = {"id": "__inherit__"}  # "usar a configuração de Todos os aplicativos"
BUTTON_TEXTS = {"Ok": "OK", "Cancel": "Cancelar", "Close": "Fechar"}


def button_box(*names: str) -> W.QDialogButtonBox:
    """Botões padrão com o texto no idioma do app (sem isso, dependem do tema do sistema e às vezes ficam em
    inglês)."""
    box = W.QDialogButtonBox()
    for name in names:
        box.addButton(getattr(W.QDialogButtonBox.StandardButton, name)).setText(T(BUTTON_TEXTS[name]))
    return box


def app_icon(name: str) -> QtGui.QIcon:
    if not name:
        return QtGui.QIcon.fromTheme("application-x-executable")
    if os.path.isabs(name) and os.path.exists(name):
        return QtGui.QIcon(name)
    icon = QtGui.QIcon.fromTheme(name)
    return icon if not icon.isNull() else QtGui.QIcon.fromTheme("application-x-executable")


# ---------------------------------------------------------------- atalho de teclado

def _keysym_names() -> dict[int, str]:
    sys.path.insert(0, "/usr/share/solaar/lib")
    try:
        from keysyms.keysymdef import keysymdef
    except ImportError:
        return {}
    out: dict[int, str] = {}
    for name, value in keysymdef.items():
        out.setdefault(value, name)
    return out


class KeyCaptureDialog(W.QDialog):
    """Grava uma combinação de teclas (ex.: Ctrl+Shift+T)."""

    MOD_KEYS = {Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_Super_L,
                Qt.Key.Key_Super_R, Qt.Key.Key_AltGr}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("Atalho de teclado"))
        self.keys: list[str] | None = None
        self._names = _keysym_names()
        lay = W.QVBoxLayout(self)
        lay.addWidget(W.QLabel(T("Pressione a combinação de teclas que o botão deve enviar.")))
        self.show_keys = W.QLabel("…", objectName="bigkeys", alignment=Qt.AlignmentFlag.AlignCenter)
        self.show_keys.setMinimumHeight(60)
        lay.addWidget(self.show_keys)
        buttons = button_box("Ok", "Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ok = buttons.button(W.QDialogButtonBox.StandardButton.Ok)
        self.ok.setEnabled(False)
        lay.addWidget(buttons)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def keyPressEvent(self, ev):  # noqa: N802 — nome exigido pelo Qt
        if ev.key() in self.MOD_KEYS:
            return
        mods = ev.modifiers()
        keys = []
        if mods & Qt.KeyboardModifier.ControlModifier:
            keys.append("Control_L")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            keys.append("Shift_L")
        if mods & Qt.KeyboardModifier.AltModifier:
            keys.append("Alt_L")
        if mods & Qt.KeyboardModifier.MetaModifier:
            keys.append("Super_L")
        name = self._names.get(ev.nativeVirtualKey())  # no X11, é o keysym da tecla
        if not name:
            text = QtGui.QKeySequence(ev.key()).toString()
            name = text if text else None
        if not name:
            return
        if len(name) == 1:
            name = name.lower()
        self.keys = keys + [name]
        self.show_keys.setText(actions.keys_label(self.keys))
        self.ok.setEnabled(True)


# ---------------------------------------------------------------- escolha de app

class AppPickerDialog(W.QDialog):
    """Lista janelas abertas e apps instalados. Devolve (App ou None, identificador, nome)."""

    def __init__(self, parent=None, title="", windows=True):
        super().__init__(parent)
        self.setWindowTitle(title or T("Escolher aplicativo"))
        self.resize(460, 520)
        self.choice = None
        lay = W.QVBoxLayout(self)
        self.search = W.QLineEdit(placeholderText=T("Pesquisar…"))
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        self.list = W.QListWidget()
        self.list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        self.list.setIconSize(QtCore.QSize(24, 24))
        self.list.itemDoubleClicked.connect(lambda _i: self._accept())
        lay.addWidget(self.list)
        buttons = button_box("Ok", "Cancel")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        installed = apps.installed_apps()
        if windows:
            for ident, wtitle in apps.open_windows():
                app = next((a for a in installed if a.match.lower() == ident.lower()), None)
                name = app.name if app else ident
                item = W.QListWidgetItem(app_icon(app.icon if app else ""),
                                         T("{name} — janela aberta: {title}", name=name, title=wtitle[:60]))
                item.setData(Qt.ItemDataRole.UserRole, (app, ident, name))
                self.list.addItem(item)
        for a in installed:
            item = W.QListWidgetItem(app_icon(a.icon), a.name)
            item.setData(Qt.ItemDataRole.UserRole, (a, a.match, a.name))
            self.list.addItem(item)
        self.search.setFocus()

    def _filter(self, text):
        t = text.lower()
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(t not in item.text().lower())

    def _accept(self):
        item = self.list.currentItem()
        if item and not item.isHidden():
            self.choice = item.data(Qt.ItemDataRole.UserRole)
            self.accept()


# ---------------------------------------------------------------- escolha de ação

OPENS_DIALOG = {"keys", "app", "command", "gestures"}


class ActionPickerDialog(W.QDialog):
    """Escolhe a ação de um botão, organizada por categorias (como no Options+)."""

    def __init__(self, parent, control_label: str, current: dict | None, allow_gestures: bool,
                 in_app_profile: bool):
        super().__init__(parent)
        self.setWindowTitle(T("Ação para: {name}", name=control_label))
        self.resize(640, 520)
        self.result_spec = None
        self.allow_gestures = allow_gestures
        self.in_app_profile = in_app_profile
        self.current = current
        lay = W.QVBoxLayout(self)
        self.search = W.QLineEdit(placeholderText=T("Pesquisar ação…"))
        self.search.textChanged.connect(self._refill)
        lay.addWidget(self.search)
        row = W.QHBoxLayout()
        self.cats = W.QListWidget(maximumWidth=230)
        self.items = W.QListWidget()
        self.items.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.items.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        self.items.itemDoubleClicked.connect(lambda _i: self._choose())
        self.items.itemClicked.connect(self._clicked)
        row.addWidget(self.cats)
        row.addWidget(self.items, 1)
        lay.addLayout(row, 1)

        self.special = [("default", T("Padrão do mouse")), ("none", T("Nenhuma ação")),
                        ("keys", T("Atalho de teclado…")), ("app", T("Abrir aplicativo…")),
                        ("command", T("Executar comando…"))]
        if allow_gestures:
            self.special.append(("gestures", T("Gestos (segurar e mover)…")))
        if in_app_profile:
            self.special.insert(0, ("inherit", T("Usar a configuração de Todos os aplicativos")))
        self.cats.addItem(T("Básico"))
        for _cid, cname in actions.CATEGORIES:
            self.cats.addItem(T(cname))
        self.cats.currentRowChanged.connect(lambda _r: self._refill())
        self.cats.setCurrentRow(self._initial_row())

        buttons = button_box("Ok", "Cancel")
        buttons.accepted.connect(self._choose)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.search.setFocus()

    def _initial_row(self):
        if self.current and self.current.get("id") in actions.BY_ID:
            cat = actions.BY_ID[self.current["id"]].category
            return 1 + [c for c, _n in actions.CATEGORIES].index(cat)
        return 0

    def _entries(self):
        """Itens visíveis: categoria escolhida, ou tudo que bate com a pesquisa."""
        text = self.search.text().strip().lower()
        row = self.cats.currentRow()
        out = []
        if text or row == 0:
            out += [("special", sid, label) for sid, label in self.special if not text or text in label.lower()]
        for a in actions.CATALOG:
            in_cat = row > 0 and a.category == actions.CATEGORIES[row - 1][0]
            if (text and text in T(a.label).lower()) or (not text and in_cat):
                out.append(("catalog", a.id, T(a.label)))
        return out

    def _refill(self):
        self.items.clear()
        current_id = (self.current or {}).get("id")
        for kind, ident, label in self._entries():
            item = W.QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, (kind, ident))
            self.items.addItem(item)
            if ident == current_id:
                self.items.setCurrentItem(item)

    def _clicked(self, item):
        """Itens com "…" abrem a janela deles já no primeiro clique."""
        if item.data(Qt.ItemDataRole.UserRole)[1] in OPENS_DIALOG:
            self._choose()

    def _choose(self):
        item = self.items.currentItem()
        if not item:
            return
        kind, ident = item.data(Qt.ItemDataRole.UserRole)
        spec = None
        if kind == "catalog":
            spec = {"id": ident}
        elif ident in ("default", "none"):
            spec = {"id": ident}
        elif ident == "inherit":
            spec = INHERIT
        elif ident == "keys":
            d = KeyCaptureDialog(self)
            if d.exec() and d.keys:
                spec = {"id": "keys", "keys": d.keys}
        elif ident == "app":
            d = AppPickerDialog(self, T("Abrir qual aplicativo?"), windows=False)
            if d.exec() and d.choice and d.choice[0]:
                a = d.choice[0]
                spec = {"id": "app", "desktop": a.desktop, "name": a.name}
        elif ident == "command":
            cmd, ok = W.QInputDialog.getText(self, T("Executar comando"),
                                             T("Comando (executado como no terminal):"))
            if ok and cmd.strip():
                spec = {"id": "command", "cmd": cmd.strip()}
        elif ident == "gestures":
            if (self.current or {}).get("id") == "gestures":
                base = self.current
            elif self.current:
                base = {"id": "gestures", "click": self.current}
            else:  # sem ação própria: num perfil de app, o clique continua igual a Todos os aplicativos
                base = {"id": "gestures"}
            d = GestureDialog(self, base, inherit=self.in_app_profile)
            if d.exec():
                spec = d.spec
        if spec is not None:
            self.result_spec = spec
            self.accept()


class GestureDialog(W.QDialog):
    """Uma ação para cada direção: clicar, ou segurar o botão e mover o mouse."""

    def __init__(self, parent, spec: dict, inherit: bool = False):
        super().__init__(parent)
        self.setWindowTitle(T("Gestos"))
        self.inherit = inherit   # perfil de app: o que não for definido segue Todos os aplicativos
        self.spec = {"id": "gestures", **{k: v for k, v in spec.items() if k != "id"}}
        lay = W.QVBoxLayout(self)
        lay.addWidget(W.QLabel(T("Segure o botão e mova o mouse numa direção para executar a ação."),
                               wordWrap=True))
        grid = W.QGridLayout()
        self.labels = {}
        for row, (key, label, _movement) in enumerate(actions.GESTURE_DIRECTIONS):
            grid.addWidget(W.QLabel(T(label)), row, 0)
            value = W.QLabel(self._describe(key), objectName="action")
            grid.addWidget(value, row, 1)
            btn = W.QPushButton(T("Alterar…"))
            btn.clicked.connect(lambda _c=False, k=key: self._edit(k))
            grid.addWidget(btn, row, 2)
            self.labels[key] = value
        lay.addLayout(grid)
        buttons = button_box("Ok", "Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _describe(self, key):
        spec = self.spec.get(key)
        if spec is None:
            if self.inherit:
                return T("Igual a Todos os aplicativos")
            spec = {"id": "default"} if key == "click" else {"id": "none"}
        return actions.describe(spec)

    def _edit(self, key):
        label = next(T(lbl) for k, lbl, _m in actions.GESTURE_DIRECTIONS if k == key)
        d = ActionPickerDialog(self, label, self.spec.get(key), allow_gestures=False, in_app_profile=self.inherit)
        if d.exec() and d.result_spec is not None:
            if d.result_spec is INHERIT:
                self.spec.pop(key, None)
            else:
                self.spec[key] = d.result_spec
            self.labels[key].setText(self._describe(key))
