"""Vigia de ligações Bluetooth travadas.

Logo depois de voltar da suspensão, a ligação Bluetooth LE com o mouse às vezes trava: o rádio continua
ligado (para o BlueZ o mouse está conectado), mas nada passa em nenhum sentido. O BlueZ só percebe quando um
pedido fica 30 s sem resposta; se ninguém pergunta nada ao mouse, a ligação fica travada para sempre.

Nos primeiros minutos de cada conexão, quando o mouse fica em silêncio, o vigia manda um ping HID++; se dois
seguidos ficam sem resposta, pede ao BlueZ para desconectar. Aparelho confiável continua na reconexão
automática do BlueZ, que o liga de novo em seguida, agora sem travar.
"""
from __future__ import annotations

import logging

from gi.repository import Gio, GLib

log = logging.getLogger("mouse-options.watchdog")

WINDOW = 180.0       # s depois de conectar: quando os travamentos aparecem
INTERVAL = 3.0       # s entre as verificações
PING_TIMEOUT = 2.0   # s: um mouse acordado responde em milissegundos; dormindo, em menos de 1 s
MISSES = 2           # pings seguidos sem resposta para considerar travada


class LinkWatch:
    """Decide quando pingar e quando desistir da ligação (sem relógio nem threads: fácil de testar)."""

    def __init__(self, started: float):
        self.started = started
        self.misses = 0
        self.pending = False   # um ping em andamento
        self.done = False

    def active(self, now: float) -> bool:
        return not self.done and now - self.started < WINDOW

    def should_ping(self, now: float, last_rx: float) -> bool:
        """Pinga só se o mouse está em silêncio: se dados estão chegando, a ligação está viva."""
        if self.pending:
            return False
        if now - last_rx < INTERVAL:
            self.misses = 0
            return False
        return True

    def answered(self, ok: bool) -> bool:
        """Resultado do ping; True = ligação travada, derrubar."""
        self.pending = False
        self.misses = 0 if ok else self.misses + 1
        if self.misses >= MISSES:
            self.done = True
            return True
        return False


def bluez_disconnect(address: str) -> None:
    """Pede ao BlueZ para desconectar o aparelho com este endereço (sem esperar)."""
    def found(bus, result):
        try:
            objects = bus.call_finish(result).unpack()[0]
        except GLib.Error as e:
            log.warning("BlueZ indisponível: %s", e.message)
            return
        path = next((p for p, ifaces in objects.items()
                     if ifaces.get("org.bluez.Device1", {}).get("Address", "").upper() == address), None)
        if path is None:
            log.warning("%s não encontrado no BlueZ", address)
            return
        bus.call("org.bluez", path, "org.bluez.Device1", "Disconnect", None, None,
                 Gio.DBusCallFlags.NONE, 10000, None, done)

    def done(bus, result):
        try:
            bus.call_finish(result)
        except GLib.Error as e:
            log.warning("%s: o BlueZ não desconectou: %s", address, e.message)

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
    except GLib.Error as e:
        log.warning("barramento do sistema indisponível: %s", e.message)
        return
    bus.call("org.bluez", "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects", None, None,
             Gio.DBusCallFlags.NONE, 5000, None, found)
