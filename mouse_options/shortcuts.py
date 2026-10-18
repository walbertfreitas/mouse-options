"""Lê os atalhos de teclado do GNOME/Zorin e converte para nomes de tecla do X11 (formato do Solaar).

Assim, uma ação como "Mostrar área de trabalho" usa o atalho que está configurado no sistema da
pessoa. Fora do GNOME (ou se o atalho estiver vazio), usa um padrão razoável.
"""
from __future__ import annotations

import re
import subprocess

MODIFIERS = {
    "primary": "Control_L", "control": "Control_L", "ctrl": "Control_L",
    "super": "Super_L", "alt": "Alt_L", "shift": "Shift_L", "meta": "Super_L",
}
# Alguns nomes do GTK que diferem do Solaar/X11
KEY_ALIASES = {"Page_Up": "Prior", "Page_Down": "Next"}


def parse_accelerator(accel: str) -> list[str] | None:
    """'<Primary><Super>d' → ['Control_L', 'Super_L', 'd']"""
    if not accel:
        return None
    mods = re.findall(r"<([^>]+)>", accel)
    key = re.sub(r"<[^>]+>", "", accel)
    if not key:
        return None
    out = []
    for m in mods:
        name = MODIFIERS.get(m.lower())
        if not name:
            return None
        out.append(name)
    out.append(KEY_ALIASES.get(key, key))
    return out


def gsettings_binding(schema: str, key: str) -> list[str] | None:
    try:
        raw = subprocess.run(["gsettings", "get", schema, key], capture_output=True, text=True,
                             timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    for accel in re.findall(r"'([^']*)'", raw):
        keys = parse_accelerator(accel)
        if keys:
            return keys
    return None


WM = "org.gnome.desktop.wm.keybindings"
SHELL = "org.gnome.shell.keybindings"
MEDIA = "org.gnome.settings-daemon.plugins.media-keys"


def system_shortcut(schema: str, key: str, fallback: list[str]) -> list[str]:
    return gsettings_binding(schema, key) or fallback
