"""A interface conversando com o serviço mouse-optionsd pelo D-Bus da sessão."""
from __future__ import annotations

import json

from .daemon.api import BUS_NAME, INTERFACE, OBJECT_PATH
from .devices import MouseInfo
from .qt import QtCore, QtDBus, Signal, Slot


class ServiceUnavailable(Exception):
    pass


class DaemonClient(QtCore.QObject):
    devices_changed = Signal(list)       # list[MouseInfo]
    button_pressed = Signal(str, int)    # chave do mouse, CID

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bus = QtDBus.QDBusConnection.sessionBus()
        self.bus.connect(BUS_NAME, OBJECT_PATH, INTERFACE, "DevicesChanged", self._on_changed)
        self.bus.connect(BUS_NAME, OBJECT_PATH, INTERFACE, "ButtonPressed", self._on_pressed)

    def _call(self, method: str, *args, timeout: int = 8000):
        msg = QtDBus.QDBusMessage.createMethodCall(BUS_NAME, OBJECT_PATH, INTERFACE, method)
        if args:
            msg.setArguments(list(args))
        reply = self.bus.call(msg, QtDBus.QDBus.CallMode.Block, timeout)
        if reply.type() == QtDBus.QDBusMessage.MessageType.ErrorMessage:
            raise ServiceUnavailable(reply.errorMessage() or reply.errorName())
        return reply.arguments()

    def devices(self) -> list[MouseInfo]:
        """Pede a lista ao serviço (o D-Bus inicia o serviço se ele não estiver rodando)."""
        return [MouseInfo.from_dict(d) for d in json.loads(self._call("GetDevices")[0])]

    def reload(self) -> None:
        self._call("Reload")

    def set_settings(self, key: str, settings: dict) -> None:
        self._call("SetSettings", key, json.dumps(settings))

    def set_host(self, key: str, host: int) -> None:
        self._call("SetHost", key, host)

    @Slot(QtDBus.QDBusMessage)
    def _on_changed(self, msg):
        self.devices_changed.emit([MouseInfo.from_dict(d) for d in json.loads(msg.arguments()[0])])

    @Slot(QtDBus.QDBusMessage)
    def _on_pressed(self, msg):
        key, cid = msg.arguments()
        self.button_pressed.emit(key, int(cid))
