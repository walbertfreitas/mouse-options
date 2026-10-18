"""Receptores Logitech (Unifying, Bolt…): quem está pareado e como parear um aparelho novo.

Receptores falam HID++ 1.0 por registradores, sempre no número de aparelho 0xFF:
    0xB2 (escrita curta)  pareamento: [0x01, 0, tempo] abre, [0x02, 0, 0] fecha, [0x03, posição, 0] despareia
    0xB5 (leitura longa)  informações: 0x03 receptor (série em [1:5], máximo de aparelhos em [6]),
                          0x20+n-1 aparelho n (wpid em [3:5], tipo em [7] & 0x0F), 0x40+n-1 nome de n
Notificações: 0x4A = cadeado de pareamento aberto/fechado (com erro), 0x41 = aparelho conectou/desconectou
(ligação perdida = bit 0x40 do primeiro byte de dados; o endereço é o protocolo).
O Bolt pareia de outro jeito (descoberta + senha); por enquanto só listamos os aparelhos dele.
"""
from __future__ import annotations

from dataclasses import dataclass

from .transport import HidppError, Message, Timeout, Transport

INDEX = 0xFF
PAIRING, INFO = 0xB2, 0xB5
WRITE_SHORT, READ_LONG = 0x80, 0x83
LOCK_NOTIFICATION, LINK_NOTIFICATION = 0x4A, 0x41
SLOTS = range(1, 7)
PAIR_TIMEOUT = 60   # segundos com o receptor aberto esperando o aparelho

UNIFYING = {0xC52B, 0xC532}
BOLT = {0xC548}

DEVICE_KINDS = {1: "keyboard", 2: "mouse", 3: "numpad", 4: "presenter", 7: "remote", 8: "trackball",
                9: "touchpad", 0x0D: "headset"}
PAIRING_ERRORS = {1: "timeout", 2: "unsupported", 3: "full", 6: "timeout"}


def kind_of(product_id: int) -> str:
    if product_id in UNIFYING:
        return "unifying"
    if product_id in BOLT:
        return "bolt"
    return "other"


@dataclass(frozen=True)
class Paired:
    slot: int
    wpid: str
    kind: str
    name: str


@dataclass(frozen=True)
class LockEvent:
    open: bool
    error: str | None        # "timeout", "unsupported", "full" ou None


@dataclass(frozen=True)
class LinkEvent:
    slot: int
    wpid: str
    online: bool


class Receiver:
    def __init__(self, transport: Transport, product_id: int):
        self.transport = transport
        self.product_id = product_id
        self.kind = kind_of(product_id)

    @property
    def can_pair(self) -> bool:
        return self.kind == "unifying"

    def _read(self, sub: int) -> bytes:
        try:
            return self.transport.register(INDEX, READ_LONG, INFO, bytes([sub]))
        except Timeout:   # ocupado conversando com um aparelho recém-pareado: mais uma chance
            return self.transport.register(INDEX, READ_LONG, INFO, bytes([sub]))

    def _write(self, action: int, slot: int = 0, value: int = 0) -> None:
        self.transport.register(INDEX, WRITE_SHORT, PAIRING, bytes([action, slot, value]))

    def info(self) -> tuple[str, int]:
        """(número de série, quantos aparelhos cabem)."""
        try:
            d = self._read(0x03)
        except (HidppError, Timeout):
            return "", len(SLOTS)
        slots = d[6] if 0 < d[6] <= len(SLOTS) else len(SLOTS)
        return d[1:5].hex().upper(), slots

    def paired(self, slots: int = len(SLOTS)) -> list[Paired]:
        """Aparelhos pareados (ligados ou não)."""
        out = []
        for n in range(1, slots + 1):
            try:
                d = self._read(0x20 + n - 1)
            except HidppError:
                continue   # posição vazia
            wpid = d[3:5].hex().upper()
            if wpid == "0000":
                continue
            try:
                raw = self._read(0x40 + n - 1)
                name = raw[2:2 + raw[1]].decode("ascii", "replace")
            except (HidppError, Timeout):
                name = ""
            out.append(Paired(n, wpid, DEVICE_KINDS.get(d[7] & 0x0F, "unknown"), name))
        return out

    def open_lock(self, seconds: int = PAIR_TIMEOUT) -> None:
        """Abre o receptor para parear: o próximo aparelho ligado (ou com o canal escolhido) é aceito."""
        self._write(0x01, 0, max(1, min(255, seconds)))

    def close_lock(self) -> None:
        self._write(0x02)

    def unpair(self, slot: int) -> None:
        self._write(0x03, slot)

    @staticmethod
    def parse(msg: Message) -> LockEvent | LinkEvent | None:
        if msg.sub_id == LOCK_NOTIFICATION and msg.index == INDEX:
            code = msg.data[0] if msg.data else 0
            return LockEvent(bool(msg.address & 0x01), PAIRING_ERRORS.get(code, "failed") if code else None)
        if msg.sub_id == LINK_NOTIFICATION and msg.index in SLOTS:
            # o endereço diz o protocolo (0x04 Unifying, 0x10 Bolt…); a ligação está no bit 0x40 do 1º byte
            return LinkEvent(msg.index, msg.data[1:3][::-1].hex().upper(), not msg.data[0] & 0x40)
        return None
