"""Aplicativos instalados (.desktop) e janelas abertas, para escolher ações e perfis por app."""
from __future__ import annotations

import configparser
import glob
import locale
import os
import shlex
from dataclasses import dataclass

DESKTOP_DIRS = [
    "/usr/share/applications",
    "/usr/local/share/applications",
    "/var/lib/flatpak/exports/share/applications",
    os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
    os.path.expanduser("~/.local/share/applications"),
    "/var/lib/snapd/desktop/applications",
]


@dataclass
class App:
    name: str
    icon: str
    desktop: str          # caminho do .desktop (para abrir com `gio launch`)
    match: str            # texto que identifica a janela do app para o Solaar (WM_CLASS ou executável)


def _localized(section, key: str) -> str:
    lang = (locale.getlocale()[0] or os.environ.get("LANG", "")).split(".")[0]
    for k in (f"{key}[{lang}]", f"{key}[{lang.split('_')[0]}]", key):
        if lang and k in section or k == key and k in section:
            return section[k]
    return ""


def _exec_name(exec_line: str) -> str:
    try:
        parts = [p for p in shlex.split(exec_line) if not p.startswith("%")]
    except ValueError:
        parts = exec_line.split()
    while parts and (parts[0] == "env" or "=" in parts[0]):
        parts.pop(0)
    if len(parts) >= 3 and os.path.basename(parts[0]) == "flatpak" and parts[1] == "run":
        app_id = next((p for p in parts[2:] if not p.startswith("-")), "")
        return app_id
    return os.path.basename(parts[0]) if parts else ""


def installed_apps() -> list[App]:
    seen: dict[str, App] = {}
    for folder in DESKTOP_DIRS:
        for path in sorted(glob.glob(os.path.join(folder, "*.desktop"))):
            cp = configparser.RawConfigParser(strict=False, interpolation=None)
            cp.optionxform = str
            try:
                cp.read(path, encoding="utf-8")
            except (configparser.Error, UnicodeDecodeError, OSError):
                continue
            if "Desktop Entry" not in cp:
                continue
            e = cp["Desktop Entry"]
            if e.get("Type") != "Application" or e.get("NoDisplay", "").lower() == "true" \
                    or e.get("Hidden", "").lower() == "true" or not e.get("Exec"):
                continue
            name = _localized(e, "Name") or os.path.basename(path)
            match = e.get("StartupWMClass") or _exec_name(e["Exec"])
            seen[os.path.basename(path)] = App(name, e.get("Icon", ""), path, match)  # pastas do usuário sobrepõem
    return sorted(seen.values(), key=lambda a: a.name.lower())


def open_windows() -> list[tuple[str, str]]:
    """(identificador da janela, nome) dos apps com janela aberta.

    Pergunta à extensão do GNOME Shell (enxerga todos os apps, também no Wayland); sem ela, lê do X11.
    """
    windows = _windows_from_extension()
    return windows if windows is not None else _windows_from_x11()


def _windows_from_extension() -> list[tuple[str, str]] | None:
    import json

    try:
        from gi.repository import Gio, GLib
    except ImportError:
        return None
    from .daemon.api import SHELL_BUS_NAME, SHELL_INTERFACE, SHELL_PATH
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        reply = bus.call_sync(SHELL_BUS_NAME, SHELL_PATH, SHELL_INTERFACE, "ListWindows", None, None,
                              Gio.DBusCallFlags.NONE, 1000, None)
        return [tuple(w) for w in json.loads(reply.unpack()[0])]
    except (GLib.Error, ValueError):
        return None


def _windows_from_x11() -> list[tuple[str, str]]:
    try:
        from Xlib import X, display
    except ImportError:
        return []
    result: list[tuple[str, str]] = []
    try:
        d = display.Display()
        root = d.screen().root
        client_list = root.get_full_property(d.intern_atom("_NET_CLIENT_LIST"), X.AnyPropertyType)
        name_atom, utf8 = d.intern_atom("_NET_WM_NAME"), d.intern_atom("UTF8_STRING")
        for wid in (client_list.value if client_list else []):
            w = d.create_resource_object("window", wid)
            wm_class = w.get_wm_class()
            if not wm_class:
                continue
            prop = w.get_full_property(name_atom, utf8)
            title = prop.value.decode("utf-8", "replace") if prop else (w.get_wm_name() or "")
            ident = wm_class[0] or wm_class[1]
            if ident and all(c != ident for c, _t in result):
                result.append((ident, title))
        d.close()
    except Exception:  # noqa: BLE001 — sem X11 (Wayland) ou janela que sumiu no meio da leitura
        return result
    return result
