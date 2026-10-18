"""Qual aplicativo está em foco, para os perfis por aplicativo.

No X11 lemos a janela ativa (EWMH). No Wayland nenhum programa comum pode saber isso; quem sabe é o próprio
GNOME Shell, e a extensão do Mouse Options (fase 2) vai informar o serviço. Sem ela, vale o perfil geral.
"""
from __future__ import annotations

import os

from ..direct import is_x11

try:
    from Xlib import X, display
except ImportError:
    X = None


def _process_name(pid: int) -> list[str]:
    names = []
    try:
        with open(f"/proc/{pid}/comm") as f:
            names.append(f.read().strip())
    except OSError:
        pass
    try:
        names.append(os.path.basename(os.readlink(f"/proc/{pid}/exe")))
    except OSError:
        pass
    return names


class Focus:
    """Nomes que identificam o app em foco: classe da janela (WM_CLASS) e nome do processo.

    Um perfil vale quando algum desses nomes começa com o texto do perfil (a mesma regra do Solaar).
    """

    def __init__(self):
        self._d = None
        self.external: list[str] | None = None   # informado pela extensão do GNOME (Wayland)

    def names(self) -> list[str]:
        if self.external is not None:
            return self.external
        if X is None or not is_x11():
            return []
        try:
            if self._d is None:
                self._d = display.Display()
            d = self._d
            root = d.screen().root
            active = root.get_full_property(d.intern_atom("_NET_ACTIVE_WINDOW"), X.AnyPropertyType)
            wid = active.value[0] if active and len(active.value) else 0
            if not wid:
                return []
            win = d.create_resource_object("window", wid)
            names = list(win.get_wm_class() or ())
            pid = win.get_full_property(d.intern_atom("_NET_WM_PID"), X.AnyPropertyType)
            if pid and len(pid.value):
                names += _process_name(pid.value[0])
            return [n for n in names if n]
        except Exception:  # noqa: BLE001 — conexão caiu ou janela sumiu: tenta de novo no próximo clique
            self._d = None
            return []

    @staticmethod
    def matches(names: list[str], app: str) -> bool:
        return any(n.startswith(app) for n in names)
