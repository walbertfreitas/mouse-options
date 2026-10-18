"""Conversa HID++ com um /dev/hidraw: pedidos com resposta e notificações espontâneas.

Cada mensagem HID++ tem: relatório (0x10 curto, 7 bytes; 0x11 longo, 20 bytes), número do aparelho
(0xFF = conectado direto; 1..6 = atrás de um receptor), recurso/sub-id, endereço (função << 4 | swid) e dados.
Respostas repetem recurso e endereço do pedido; notificações HID++ 2.0 vêm com swid 0. O que não é resposta
a um pedido nosso vai para on_notification (inclusive respostas a outros programas; quem recebe filtra).
"""
from __future__ import annotations

import array
import errno
import fcntl
import os
import select
import threading
import time
from dataclasses import dataclass
from typing import Callable

SHORT, LONG = 0x10, 0x11
SIZES = {SHORT: 7, LONG: 20}
SWID = 0x0B          # nosso "software id" (o kernel usa 0x01; o Solaar, outros)
ERROR_10 = 0x8F      # erro HID++ 1.0 (receptores)
ERROR_20 = 0xFF      # erro HID++ 2.0
_HIDIOCGRDESCSIZE, _HIDIOCGRDESC = 0x80044801, 0x90044802

ERRORS_20 = {1: "desconhecido", 2: "argumento inválido", 3: "fora do intervalo", 4: "falha do hardware",
             5: "erro do Logitech interno", 6: "índice de recurso inválido", 7: "função inválida", 8: "ocupado",
             9: "não suportado"}


class HidppError(Exception):
    def __init__(self, code: int, protocol: int = 2):
        self.code = code
        self.protocol = protocol
        text = ERRORS_20.get(code, "?") if protocol == 2 else f"HID++ 1.0 {code:#x}"
        super().__init__(f"erro HID++ {code:#x} ({text})")


class Timeout(Exception):
    pass


@dataclass(frozen=True)
class Message:
    report: int
    index: int        # número do aparelho
    sub_id: int       # índice do recurso (2.0) ou sub-id (1.0)
    address: int      # função << 4 | swid (2.0) ou registrador (1.0)
    data: bytes

    @classmethod
    def parse(cls, raw: bytes) -> "Message | None":
        if len(raw) < 4 or raw[0] not in SIZES:
            return None
        return cls(raw[0], raw[1], raw[2], raw[3], bytes(raw[4:SIZES[raw[0]]]))

    @property
    def function(self) -> int:
        return self.address >> 4

    @property
    def swid(self) -> int:
        return self.address & 0x0F


def report_ids(fd: int) -> set[int]:
    """Relatórios que o aparelho declara no descritor HID (alguns só aceitam o longo)."""
    size = array.array("i", [0])
    fcntl.ioctl(fd, _HIDIOCGRDESCSIZE, size)
    buf = array.array("B", list(size[0].to_bytes(4, "little")) + [0] * 4096)
    fcntl.ioctl(fd, _HIDIOCGRDESC, buf)
    desc = bytes(buf[4:4 + size[0]])
    ids, i = set(), 0
    while i < len(desc):
        b = desc[i]
        if b == 0xFE:  # item longo
            i += 3 + desc[i + 1]
            continue
        n = (0, 1, 2, 4)[b & 3]
        if b & 0xFC == 0x84 and n:
            ids.add(desc[i + 1])
        i += 1 + n
    return ids


class Transport:
    """Um /dev/hidraw aberto, com uma thread que lê tudo o que chega."""

    def __init__(self, path: str, on_notification: Callable[[Message], None] | None = None,
                 on_close: Callable[[], None] | None = None):
        self.path = path
        self.fd = os.open(path, os.O_RDWR)
        try:
            self.reports = report_ids(self.fd) & set(SIZES)
        except OSError:
            self.reports = {SHORT, LONG}
        self.on_notification = on_notification
        self.on_close = on_close
        self._lock = threading.Lock()        # um pedido por vez
        self._cond = threading.Condition()
        self._waiting: tuple | None = None   # (índice, sub_id, endereço) esperado
        self._reply: Message | Exception | None = None
        self._stop_r, self._stop_w = os.pipe()
        self.closed = False
        self._thread = threading.Thread(target=self._read_loop, name=f"hidpp {path}", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ envio

    def request(self, index: int, sub_id: int, function: int, params: bytes = b"", timeout: float = 2.0,
                long: bool | None = None) -> bytes:
        """Envia um pedido HID++ 2.0 (função de um recurso) e devolve os dados da resposta."""
        return self._send(index, sub_id, (function << 4) | SWID, params, timeout, long).data

    def register(self, index: int, sub_id: int, register: int, params: bytes = b"", timeout: float = 2.0,
                 long: bool | None = None) -> bytes:
        """Acesso a registrador HID++ 1.0 (receptores): sub_id 0x80/0x81 curto, 0x82/0x83 longo."""
        return self._send(index, sub_id, register, params, timeout, long).data

    def _send(self, index, sub_id, address, params, timeout, long) -> Message:
        if long is None:
            long = len(params) > 3 or SHORT not in self.reports
        report = LONG if long else SHORT
        raw = bytes([report, index, sub_id, address]) + bytes(params)
        raw = raw.ljust(SIZES[report], b"\0")[:SIZES[report]]
        with self._lock:
            with self._cond:
                self._waiting, self._reply = (index, sub_id, address), None
            try:
                self._write(raw)
            except OSError as e:
                with self._cond:
                    self._waiting = None
                raise Timeout(str(e)) from e
            with self._cond:
                self._cond.wait_for(lambda: self._reply is not None or self.closed, timeout)
                reply, self._waiting, self._reply = self._reply, None, None
        if isinstance(reply, Exception):
            raise reply
        if reply is None:
            raise Timeout(f"sem resposta de {self.path} (aparelho {index:#x}, {sub_id:#x}/{address:#x})")
        return reply

    def _write(self, raw: bytes) -> None:
        """Receptores ocupados (ex.: logo depois de parear) às vezes recusam o envio no USB com EPIPE/EAGAIN:
        espera um pouco e tenta de novo antes de desistir."""
        for attempt in range(4):
            try:
                os.write(self.fd, raw)
                return
            except OSError as e:
                if e.errno not in (errno.EPIPE, errno.EAGAIN) or attempt == 3:
                    raise
                time.sleep(0.05 * (attempt + 1))

    # ------------------------------------------------------------------ leitura

    def _match(self, msg: Message) -> Message | Exception | None:
        if self._waiting is None:
            return None
        index, sub_id, address = self._waiting
        if msg.index != index:
            return None
        if msg.sub_id == sub_id and msg.address == address:
            return msg
        if msg.sub_id == ERROR_20 and msg.address == sub_id and msg.data[:1] == bytes([address]):
            return HidppError(msg.data[1])
        if msg.sub_id == ERROR_10 and msg.address == sub_id and msg.data[:1] == bytes([address]):
            return HidppError(msg.data[1], protocol=1)
        return None

    def _read_loop(self):
        try:
            while True:
                ready, _, _ = select.select([self.fd, self._stop_r], [], [])
                if self._stop_r in ready:
                    break
                try:
                    raw = os.read(self.fd, 64)
                except BlockingIOError:
                    continue
                msg = Message.parse(raw)
                if msg is None:
                    continue
                with self._cond:
                    reply = self._match(msg)
                    if reply is not None:
                        self._reply = reply
                        self._cond.notify_all()
                        continue
                if self.on_notification:   # o resto: notificações (e respostas a outros programas)
                    try:
                        self.on_notification(msg)
                    except Exception:  # noqa: BLE001 — um erro ao tratar não pode matar a leitura
                        import traceback
                        traceback.print_exc()
        except OSError:
            pass  # o aparelho saiu do sistema
        finally:
            with self._cond:
                self.closed = True
                self._cond.notify_all()
            for fd in (self.fd, self._stop_r):
                try:
                    os.close(fd)
                except OSError:
                    pass
            if self.on_close:
                self.on_close()

    def close(self):
        if not self.closed:
            try:
                os.write(self._stop_w, b"x")
            except OSError:
                pass
        self._thread.join(2)
        try:
            os.close(self._stop_w)
        except OSError:
            pass
