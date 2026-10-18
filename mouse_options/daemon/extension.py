"""Liga a extensão do GNOME do Mouse Options na primeira vez que o serviço roda para a pessoa.

O pacote instala a extensão para o sistema todo, mas cada pessoa precisa ligá-la. Fazemos isso uma vez só
(fica marcado num arquivo): se depois a pessoa desligar a extensão no app Extensões, a escolha é respeitada.
"""
from __future__ import annotations

import logging
import os

from gi.repository import Gio, GLib

from ..store import CONFIG_DIR
from .api import EXTENSION_UUID

MARKER = os.path.join(CONFIG_DIR, "extension-enabled")
log = logging.getLogger("mouse-options")


def ensure_enabled(marker: str = MARKER) -> bool:
    """Liga a extensão se nunca ligamos antes. Devolve True se ligou agora."""
    if os.path.exists(marker):
        return False
    source = Gio.SettingsSchemaSource.get_default()
    if source is None or source.lookup("org.gnome.shell", True) is None:
        return False   # não é GNOME
    settings = Gio.Settings.new("org.gnome.shell")
    enabled = settings.get_strv("enabled-extensions")
    if EXTENSION_UUID not in enabled:
        settings.set_strv("enabled-extensions", enabled + [EXTENSION_UUID])
    disabled = settings.get_strv("disabled-extensions")
    if EXTENSION_UUID in disabled:
        settings.set_strv("disabled-extensions", [u for u in disabled if u != EXTENSION_UUID])
    Gio.Settings.sync()
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    with open(marker, "w", encoding="utf-8"):
        pass
    # se o GNOME já conhece a extensão, ela passa a valer agora; senão, no próximo login
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        bus.call("org.gnome.Shell", "/org/gnome/Shell", "org.gnome.Shell.Extensions", "EnableExtension",
                 GLib.Variant("(s)", (EXTENSION_UUID,)), None, Gio.DBusCallFlags.NO_AUTO_START, 2000, None,
                 None, None)
    except GLib.Error:
        pass
    log.info("extensão do GNOME ligada")
    return True
