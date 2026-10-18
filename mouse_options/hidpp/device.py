"""Um aparelho HID++ 2.0 (mouse, teclado…) e os recursos que o app usa.

Tudo é guiado pelo que o próprio aparelho declara: perguntamos ao recurso ROOT em que posição está cada
recurso que nos interessa; o que ele não tiver simplesmente não aparece. Assim o mesmo código serve para
qualquer modelo Logitech com HID++ 2.0.
"""
from __future__ import annotations

import struct
import threading
from dataclasses import dataclass, field

from .names import control_name
from .transport import HidppError, Message, Timeout, Transport

# Recursos (feature IDs) usados
ROOT = 0x0000
FEATURE_SET = 0x0001
DEVICE_FW_VERSION = 0x0003
DEVICE_NAME = 0x0005
BATTERY_STATUS = 0x1000
BATTERY_VOLTAGE = 0x1001
UNIFIED_BATTERY = 0x1004
CHANGE_HOST = 0x1814
HOSTS_INFO = 0x1815
REPROG_CONTROLS_V4 = 0x1B04
WIRELESS_DEVICE_STATUS = 0x1D4B
POINTER_SPEED = 0x2205
HIRES_WHEEL = 0x2121
ADJUSTABLE_DPI = 0x2201
SMART_SHIFT = 0x2110
SMART_SHIFT_ENHANCED = 0x2111
THUMB_WHEEL = 0x2150

SMART_SHIFT_RANGE = (1, 50)   # 1 = roda solta quase sempre; 50 = sempre com cliques (como no Solaar)

KINDS = {0: "keyboard", 1: "remote", 2: "numpad", 3: "mouse", 4: "touchpad", 5: "trackball", 6: "presenter",
         7: "receiver"}

# REPROG_CONTROLS_V4: flags de cada controle e bits de setCidReporting
_C_MOUSE, _C_REPROG, _C_DIVERT, _C_PERSIST, _C_VIRTUAL = 0x01, 0x10, 0x20, 0x40, 0x80
_C2_RAW_XY = 0x01
_R_DIVERT, _R_DVALID, _R_RAW_XY, _R_RVALID = 0x01, 0x02, 0x10, 0x20

# HIRES_WHEEL: modo da roda
_W_TARGET, _W_HIRES, _W_INVERT = 0x01, 0x02, 0x04

# tensão (mV) → % para baterias de lítio (BATTERY_VOLTAGE)
_VOLTAGE_CURVE = [(4186, 100), (4067, 90), (3989, 80), (3922, 70), (3859, 60), (3811, 50), (3778, 40),
                  (3751, 30), (3717, 20), (3671, 10), (3646, 5), (3579, 2), (3500, 0)]


class Unsupported(Exception):
    """O aparelho não tem o recurso pedido."""


@dataclass(frozen=True)
class ControlInfo:
    cid: int
    name: str
    divertable: bool
    raw_xy: bool
    virtual: bool
    mouse: bool


@dataclass
class Battery:
    level: int | None       # %
    charging: bool = False
    full: bool = False


# ---------------------------------------------------------------- eventos vindos do aparelho

@dataclass(frozen=True)
class ButtonsEvent:
    cids: frozenset[int]    # controles desviados que estão apertados agora


@dataclass(frozen=True)
class MoveEvent:
    dx: int
    dy: int


@dataclass(frozen=True)
class BatteryEvent:
    battery: Battery


@dataclass(frozen=True)
class ReconfigureEvent:
    """O aparelho reiniciou/reconectou e perdeu os ajustes temporários (desvios etc.)."""


@dataclass(frozen=True)
class WheelEvent:
    invert: bool
    hires: bool


@dataclass
class DeviceIds:
    unit_id: str
    model_id: str
    transports: dict[str, str] = field(default_factory=dict)   # btid/btleid/wpid/usbid → id do modelo


class Device:
    def __init__(self, transport: Transport, index: int = 0xFF):
        self.transport = transport
        self.index = index
        self._features: dict[int, int | None] = {}    # id → índice (None = não tem)
        self._by_index: dict[int, int] = {}
        self._lock = threading.Lock()
        self.protocol: tuple[int, int] | None = None

    # ------------------------------------------------------------------ básico

    def ping(self, timeout: float = 2.0) -> tuple[int, int] | None:
        """Versão do protocolo HID++, ou None se o aparelho não respondeu (desligado/dormindo)."""
        try:
            d = self.transport.request(self.index, 0x00, 1, b"\0\0\xAA", timeout=timeout)
        except (Timeout, HidppError):
            return None
        self.protocol = (d[0], d[1])
        return self.protocol

    def feature(self, fid: int) -> int | None:
        with self._lock:
            if fid not in self._features:
                if fid == ROOT:
                    self._features[fid] = 0
                else:
                    d = self.transport.request(self.index, 0x00, 0, struct.pack("!H", fid))
                    self._features[fid] = d[0] or None
                if self._features[fid] is not None:
                    self._by_index[self._features[fid]] = fid
            return self._features[fid]

    def has(self, fid: int) -> bool:
        return self.feature(fid) is not None

    def known_features(self) -> dict[int, int | None]:
        """Posições já descobertas (id → índice), para guardar e reaproveitar na próxima conexão."""
        with self._lock:
            return dict(self._features)

    def preload(self, features: dict[int, int | None]) -> None:
        """Usa posições guardadas de uma conexão anterior (a tabela de um aparelho não muda)."""
        with self._lock:
            self._features.update(features)
            self._by_index.update({idx: fid for fid, idx in features.items() if idx is not None})

    def forget(self) -> None:
        with self._lock:
            self._features.clear()
            self._by_index.clear()

    def feature_count(self) -> int | None:
        fs = self.feature(FEATURE_SET)
        return None if fs is None else self.transport.request(self.index, fs, 0)[0]

    def call(self, fid: int, function: int, params: bytes = b"", timeout: float = 2.0) -> bytes:
        idx = self.feature(fid)
        if idx is None:
            raise Unsupported(f"recurso {fid:#06x} ausente")
        return self.transport.request(self.index, idx, function, params, timeout=timeout)

    def features(self) -> dict[int, int]:
        """Todos os recursos declarados (id → versão)."""
        fs = self.feature(FEATURE_SET)
        if fs is None:
            return {}
        count = self.transport.request(self.index, fs, 0)[0]
        out = {}
        for i in range(count + 1):
            d = self.transport.request(self.index, fs, 1, bytes([i]))
            fid = d[0] << 8 | d[1]
            out[fid] = d[3]
            with self._lock:
                self._features.setdefault(fid, i)
                self._by_index.setdefault(i, fid)
        return out

    # ------------------------------------------------------------------ identificação

    def ids(self) -> DeviceIds | None:
        """unitId e modelId (os mesmos que o Solaar usa para identificar o aparelho)."""
        try:
            d = self.call(DEVICE_FW_VERSION, 0)
        except Unsupported:
            return None
        model = d[7:13]
        transports, offset = {}, 0
        for name, flag in (("btid", 0x1), ("btleid", 0x2), ("wpid", 0x4), ("usbid", 0x8)):
            if d[6] & flag:
                transports[name] = model[offset:offset + 2].hex().upper()
                offset += 2
        return DeviceIds(d[1:5].hex().upper(), model.hex().upper(), transports)

    def name(self) -> str | None:
        try:
            length = self.call(DEVICE_NAME, 0)[0]
        except Unsupported:
            return None
        name = b""
        while len(name) < length:
            chunk = self.call(DEVICE_NAME, 1, bytes([len(name)]))
            name += chunk[:length - len(name)]
        return name.rstrip(b"\0").decode("utf-8", "replace")

    def kind(self) -> str | None:
        try:
            return KINDS.get(self.call(DEVICE_NAME, 2)[0])
        except Unsupported:
            return None

    # ------------------------------------------------------------------ botões

    def controls(self) -> list[ControlInfo]:
        try:
            count = self.call(REPROG_CONTROLS_V4, 0)[0]
        except Unsupported:
            return []
        out = []
        for i in range(count):
            d = self.call(REPROG_CONTROLS_V4, 1, bytes([i]))
            cid = d[0] << 8 | d[1]
            flags, flags2 = d[4], d[8]
            out.append(ControlInfo(cid, control_name(cid), bool(flags & _C_DIVERT), bool(flags2 & _C2_RAW_XY),
                                   bool(flags & _C_VIRTUAL), bool(flags & _C_MOUSE)))
        return out

    def set_reporting(self, cid: int, divert: bool, raw_xy: bool = False) -> None:
        """Desvia (ou devolve) um botão para o app. Desvio temporário: some se o aparelho reiniciar."""
        flags = _R_DVALID | (_R_DIVERT if divert else 0) | _R_RVALID | (_R_RAW_XY if raw_xy else 0)
        self.call(REPROG_CONTROLS_V4, 3, struct.pack("!HBH", cid, flags, 0))

    def reporting(self, cid: int) -> tuple[bool, bool]:
        d = self.call(REPROG_CONTROLS_V4, 2, struct.pack("!H", cid))
        return bool(d[2] & _R_DIVERT), bool(d[2] & _R_RAW_XY)

    # ------------------------------------------------------------------ bateria

    def battery(self) -> Battery | None:
        if self.has(UNIFIED_BATTERY):
            return _unified_battery(self.call(UNIFIED_BATTERY, 1))
        if self.has(BATTERY_STATUS):
            return _battery_status(self.call(BATTERY_STATUS, 0))
        if self.has(BATTERY_VOLTAGE):
            return _battery_voltage(self.call(BATTERY_VOLTAGE, 0))
        return None

    # ------------------------------------------------------------------ ajustes

    def pointer_speed(self) -> int | None:
        """256 = velocidade normal (1,0×)."""
        if not self.has(POINTER_SPEED):
            return None
        return struct.unpack("!H", self.call(POINTER_SPEED, 0)[:2])[0]

    def set_pointer_speed(self, value: int) -> None:
        self.call(POINTER_SPEED, 1, struct.pack("!H", max(1, min(0xFFFF, int(value)))))

    def wheel_mode(self) -> WheelEvent | None:
        if not self.has(HIRES_WHEEL):
            return None
        m = self.call(HIRES_WHEEL, 1)[0]
        return WheelEvent(bool(m & _W_INVERT), bool(m & _W_HIRES))

    def set_wheel_mode(self, invert: bool | None = None, hires: bool | None = None) -> None:
        m = self.call(HIRES_WHEEL, 1)[0]
        if invert is not None:
            m = (m | _W_INVERT) if invert else (m & ~_W_INVERT)
        if hires is not None:
            m = (m | _W_HIRES) if hires else (m & ~_W_HIRES)
        self.call(HIRES_WHEEL, 2, bytes([m & 0xFF]))

    def dpi_choices(self) -> list[int] | None:
        """DPIs aceitos pelo sensor: lista, ou faixa "mínimo, passo, máximo" (ADJUSTABLE_DPI)."""
        if not self.has(ADJUSTABLE_DPI):
            return None
        d = self.call(ADJUSTABLE_DPI, 1, b"\0")
        values, step = [], None
        for v in struct.unpack("!7H", bytes(d[1:15]).ljust(14, b"\0")):
            if v == 0:
                break
            if v >> 13 == 0b111:
                step = v & 0x1FFF
            else:
                values.append(v)
        if step and len(values) == 2:
            return list(range(values[0], values[1] + 1, step))
        return values or None

    def dpi(self) -> int | None:
        if not self.has(ADJUSTABLE_DPI):
            return None
        d = self.call(ADJUSTABLE_DPI, 2, b"\0")
        value = d[1] << 8 | d[2]
        return value or (d[3] << 8 | d[4]) or None   # 0 = usando o padrão

    def set_dpi(self, value: int) -> None:
        self.call(ADJUSTABLE_DPI, 3, struct.pack("!BH", 0, int(value)))

    def _smart_shift(self) -> tuple[int, int, int] | None:
        """(recurso, função de leitura, função de escrita): a versão "enhanced" troca as funções."""
        if self.has(SMART_SHIFT_ENHANCED):
            return SMART_SHIFT_ENHANCED, 1, 2
        if self.has(SMART_SHIFT):
            return SMART_SHIFT, 0, 1
        return None

    def smart_shift(self) -> int | None:
        found = self._smart_shift()
        if not found:
            return None
        d = self.call(found[0], found[1])
        if d[0] == 1:   # modo roda solta
            return SMART_SHIFT_RANGE[0]
        return max(SMART_SHIFT_RANGE[0], min(d[1], SMART_SHIFT_RANGE[1]))

    def set_smart_shift(self, value: int) -> None:
        found = self._smart_shift()
        if not found:
            raise Unsupported("SmartShift ausente")
        threshold = 255 if value >= SMART_SHIFT_RANGE[1] else max(SMART_SHIFT_RANGE[0], int(value))
        params = bytes([0, threshold]) + (b"\0" if found[0] == SMART_SHIFT_ENHANCED else b"")
        self.call(found[0], found[2], params)

    def thumb_invert(self) -> bool | None:
        if not self.has(THUMB_WHEEL):
            return None
        return bool(self.call(THUMB_WHEEL, 1)[1] & 0x01)

    def set_thumb_invert(self, invert: bool) -> None:
        current = self.call(THUMB_WHEEL, 1)
        self.call(THUMB_WHEEL, 2, bytes([current[0] & 0x01, 1 if invert else 0]))

    def hosts(self) -> tuple[int, int] | None:
        """(quantidade de canais Easy-Switch, canal atual começando em 0)."""
        if not self.has(CHANGE_HOST):
            return None
        d = self.call(CHANGE_HOST, 0)
        return d[0], d[1]

    def host_names(self, count: int) -> list[str | None]:
        """Nome do computador em cada canal, quando o aparelho guarda (HOSTS_INFO)."""
        names: list[str | None] = [None] * count
        if not self.has(HOSTS_INFO) or not self.call(HOSTS_INFO, 0)[0] & 0x01:   # sabe guardar nomes?
            return names
        for host in range(count):
            try:
                info = self.call(HOSTS_INFO, 1, bytes([host]))
                length = info[4]   # host, status, bus, páginas, tamanho do nome, tamanho máximo
                name = b""
                while len(name) < length:
                    chunk = self.call(HOSTS_INFO, 3, bytes([host, len(name)]))
                    if chunk[1] != len(name):
                        break
                    name += chunk[2:2 + min(14, length - len(name))]
                names[host] = name.rstrip(b"\0").decode("utf-8", "replace") or None
            except (HidppError, Timeout):
                pass
        return names

    def set_host(self, host: int) -> None:
        """Troca para outro canal: o aparelho se desconecta daqui na hora (não há resposta)."""
        try:
            self.call(CHANGE_HOST, 1, bytes([host]), timeout=0.3)
        except Timeout:
            pass

    # ------------------------------------------------------------------ notificações

    def parse(self, msg: Message):
        """Transforma uma notificação deste aparelho num evento (ou None)."""
        if msg.index != self.index or msg.swid != 0:
            return None
        fid = self._by_index.get(msg.sub_id)
        if fid is None:
            return None
        event, d = msg.function, msg.data
        if fid == REPROG_CONTROLS_V4:
            if event == 0:
                return ButtonsEvent(frozenset(c for c in struct.unpack("!4H", d[:8]) if c))
            if event == 1:
                dx, dy = struct.unpack("!hh", d[:4])
                return MoveEvent(dx, dy)
        elif fid == UNIFIED_BATTERY and event == 0:
            return BatteryEvent(_unified_battery(d))
        elif fid == BATTERY_STATUS and event == 0:
            return BatteryEvent(_battery_status(d))
        elif fid == BATTERY_VOLTAGE and event == 0:
            return BatteryEvent(_battery_voltage(d))
        elif fid == WIRELESS_DEVICE_STATUS and event == 0:
            if d[0] == 1 and d[1] == 1:   # "reconfiguração necessária"
                return ReconfigureEvent()
        elif fid == HIRES_WHEEL and event == 1:
            return WheelEvent(bool(d[0] & _W_INVERT), bool(d[0] & _W_HIRES))
        return None


def _battery_status(d: bytes) -> Battery:
    status = d[2]
    return Battery(d[0] or None, charging=status in (1, 2, 4), full=status == 3)


def _unified_battery(d: bytes) -> Battery:
    level = d[0]
    if not level:   # alguns só informam a faixa
        level = next((pct for bit, pct in ((8, 90), (4, 50), (2, 20), (1, 5)) if d[1] & bit), None)
    return Battery(level, charging=d[2] in (1, 2), full=d[2] == 3)


def _battery_voltage(d: bytes) -> Battery:
    mv = d[0] << 8 | d[1]
    level = 0
    for volts, pct in _VOLTAGE_CURVE:
        if mv >= volts:
            level = pct
            break
    return Battery(level, charging=bool(d[2] & 0x80))
