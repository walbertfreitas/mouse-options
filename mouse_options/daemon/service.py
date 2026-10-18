"""O serviço em segundo plano do Mouse Options (mouse-optionsd) e sua interface D-Bus.

A interface gráfica conversa com ele pelo barramento da sessão:
    GetDevices() → JSON com os aparelhos (conectados e conhecidos)
    Reload()                     o config.json mudou: reconfigura os botões
    SetSettings(chave, JSON)     velocidade do ponteiro, rolagem…: aplica na hora e guarda
    SetHost(chave, canal)        Easy-Switch
    sinais DevicesChanged(JSON) e ButtonPressed(chave, cid)
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys

from gi.repository import Gio, GLib

from .api import BUS_NAME, INTERFACE, OBJECT_PATH
from .extension import ensure_enabled as ensure_extension
from .focus import Focus
from .manager import Manager
from .runner import Runner

INTROSPECTION = f"""
<node>
  <interface name="{INTERFACE}">
    <method name="GetDevices"><arg type="s" name="devices" direction="out"/></method>
    <method name="Reload"/>
    <method name="SetSettings">
      <arg type="s" name="key" direction="in"/><arg type="s" name="settings" direction="in"/>
    </method>
    <method name="SetHost">
      <arg type="s" name="key" direction="in"/><arg type="i" name="host" direction="in"/>
    </method>
    <method name="SetFocus"><arg type="as" name="names" direction="in"/></method>
    <method name="ClearFocus"/>
    <signal name="DevicesChanged"><arg type="s" name="devices"/></signal>
    <signal name="ButtonPressed"><arg type="s" name="key"/><arg type="u" name="cid"/></signal>
  </interface>
</node>
"""

log = logging.getLogger("mouse-options")


class Service:
    def __init__(self, vinput: bool = True):
        self.loop = GLib.MainLoop()
        self.conn: Gio.DBusConnection | None = None
        self.focus = Focus()
        factory = None
        if vinput:
            from .vinput import VirtualInput
            factory = VirtualInput
        self.runner = Runner(factory)
        self.manager = Manager(self.runner, self.focus, self._changed, self._pressed)

    # ------------------------------------------------------------------ D-Bus

    def _on_bus(self, conn, _name):
        self.conn = conn
        node = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION)
        conn.register_object(OBJECT_PATH, node.interfaces[0], self._on_call, None, None)

    def _on_name(self, _conn, _name):
        log.info("serviço no ar")
        try:
            ensure_extension()
        except Exception:  # noqa: BLE001 — sem a extensão o serviço funciona (só perde o que depende dela)
            log.exception("não deu para ligar a extensão do GNOME")
        self.runner.prepare()
        self.manager.start()

    def _on_name_lost(self, _conn, _name):
        log.error("outro mouse-optionsd já está rodando")
        self.loop.quit()

    def _on_call(self, _conn, _sender, _path, _iface, method, params, invocation):
        try:
            args = params.unpack()
            if method == "GetDevices":
                invocation.return_value(GLib.Variant("(s)", (json.dumps(self.manager.devices()),)))
                return
            if method == "Reload":
                self.manager.reload()
            elif method == "SetSettings":
                self.manager.set_settings(args[0], json.loads(args[1]))
            elif method == "SetHost":
                self.manager.set_host(args[0], args[1])
            elif method == "SetFocus":      # a extensão do GNOME avisa quem está em foco
                self.focus.external = list(args[0])
            elif method == "ClearFocus":    # extensão desligada: volta a descobrir sozinho (X11)
                self.focus.external = None
            invocation.return_value(None)
        except Exception as e:  # noqa: BLE001
            log.exception("erro em %s", method)
            invocation.return_dbus_error(f"{INTERFACE}.Error", str(e))

    def _emit(self, name, sig, args):
        if self.conn:
            self.conn.emit_signal(None, OBJECT_PATH, INTERFACE, name, GLib.Variant(sig, args))

    def _changed(self):
        self._emit("DevicesChanged", "(s)", (json.dumps(self.manager.devices()),))
        return False

    def _pressed(self, key: str, cid: int):
        self._emit("ButtonPressed", "(su)", (key, cid))

    # ------------------------------------------------------------------ ciclo de vida

    def run(self) -> int:
        owner = Gio.bus_own_name(Gio.BusType.SESSION, BUS_NAME, Gio.BusNameOwnerFlags.DO_NOT_QUEUE,
                                 self._on_bus, self._on_name, self._on_name_lost)
        for sig in (signal.SIGTERM, signal.SIGINT):
            GLib.unix_signal_add(GLib.PRIORITY_HIGH, sig, self._quit)
        self.loop.run()
        self.manager.stop()
        self.runner.close()
        Gio.bus_unown_name(owner)
        return 0

    def _quit(self):
        log.info("encerrando: devolvendo os botões ao normal")
        self.loop.quit()
        return False


def main() -> int:
    level = logging.DEBUG if os.environ.get("MOUSE_OPTIONS_DEBUG") else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    return Service().run()
