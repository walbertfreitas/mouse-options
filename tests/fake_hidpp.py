"""Um aparelho HID++ 2.0 simulado, para testar sem mouse conectado.

Responde como o M720 Triathlon (Bluetooth) respondeu de verdade; dá para mudar os recursos para imitar
outros modelos.
"""
import struct

from mouse_options.hidpp import device as hd
from mouse_options.hidpp.transport import HidppError, Message


class FakeMouse:
    def __init__(self, features=None, name="M720 Triathlon Multi-Device Mouse", kind=3):
        self.features = features or [hd.ROOT, hd.FEATURE_SET, hd.DEVICE_FW_VERSION, hd.DEVICE_NAME,
                                     hd.WIRELESS_DEVICE_STATUS, hd.BATTERY_STATUS, hd.CHANGE_HOST, hd.HOSTS_INFO,
                                     hd.REPROG_CONTROLS_V4, hd.POINTER_SPEED, hd.HIRES_WHEEL]
        self.name = name.encode()
        self.kind = kind
        # cid, flags, flags2 (como o M720 declara)
        self.controls = [(0x50, 0x01, 0), (0x51, 0x01, 0)] + \
            [(c, 0x71, 0x01) for c in (0x52, 0x53, 0x56, 0x5B, 0x5D, 0xD0)] + [(0xD7, 0xA0, 0x03)]
        self.reporting = {}
        self.speed = 283
        self.wheel = 0x02
        self.hosts = ["Laptop", "Phone", "Desktop"]
        self.current_host = 0
        self.battery = (20, 5, 0)
        self.dpi_list = struct.pack("!HHH", 200, 0xE000 | 50, 4000)   # faixa 200–4000, passo 50
        self.dpi = 1000
        self.ratchet = (2, 10, 10)    # modo, limiar, limiar padrão
        self.thumb = [0, 0]           # desvio, inverter
        self.log = []

    def index(self, fid):
        return self.features.index(fid) if fid in self.features else 0

    def request(self, index, sub_id, function, params=b"", timeout=2.0, long=None):
        params = bytes(params).ljust(16, b"\0")
        self.log.append((sub_id, function, params[:4]))
        if sub_id >= len(self.features):
            raise HidppError(6)
        fid = self.features[sub_id]
        if fid == hd.ROOT:
            if function == 0:
                return bytes([self.index(struct.unpack("!H", params[:2])[0]), 0, 0])
            if function == 1:
                return bytes([4, 5, params[2]])
        if fid == hd.FEATURE_SET:
            if function == 0:
                return bytes([len(self.features) - 1])
            if function == 1:
                return struct.pack("!HBB", self.features[params[0]], 0, 0)
        if fid == hd.DEVICE_FW_VERSION and function == 0:
            return bytes([3]) + bytes.fromhex("1A2B3C4D") + bytes([0, 0x06]) + bytes.fromhex("B015405E0000")
        if fid == hd.DEVICE_NAME:
            if function == 0:
                return bytes([len(self.name)])
            if function == 1:
                return self.name[params[0]:params[0] + 16]
            if function == 2:
                return bytes([self.kind])
        if fid == hd.REPROG_CONTROLS_V4:
            if function == 0:
                return bytes([len(self.controls)])
            if function == 1:
                cid, flags, flags2 = self.controls[params[0]]
                return struct.pack("!HHBBBBB", cid, 0, flags, 0, 1, 0, flags2)
            if function == 2:
                cid = struct.unpack("!H", params[:2])[0]
                return struct.pack("!HBH", cid, self.reporting.get(cid, 0), 0)
            if function == 3:
                cid, flags = struct.unpack("!HB", params[:3])
                value = self.reporting.get(cid, 0)
                if flags & 0x02:
                    value = (value & ~0x01) | (flags & 0x01)
                if flags & 0x20:
                    value = (value & ~0x10) | (flags & 0x10)
                self.reporting[cid] = value
                return params[:5]
        if fid == hd.BATTERY_STATUS and function == 0:
            return bytes(self.battery)
        if fid == hd.POINTER_SPEED:
            if function == 0:
                return struct.pack("!H", self.speed)
            if function == 1:
                self.speed = struct.unpack("!H", params[:2])[0]
                return b""
        if fid == hd.HIRES_WHEEL:
            if function == 1:
                return bytes([self.wheel])
            if function == 2:
                self.wheel = params[0]
                return bytes([self.wheel])
        if fid == hd.ADJUSTABLE_DPI:
            if function == 0:
                return bytes([1])
            if function == 1:
                return bytes([0]) + self.dpi_list
            if function == 2:
                return struct.pack("!BHH", 0, self.dpi, 1000)
            if function == 3:
                self.dpi = struct.unpack("!H", params[1:3])[0]
                return params[:3]
        if fid in (hd.SMART_SHIFT, hd.SMART_SHIFT_ENHANCED):
            read, write = (0, 1) if fid == hd.SMART_SHIFT else (1, 2)
            if function == read:
                return bytes(self.ratchet)
            if function == write:
                mode = params[0] or self.ratchet[0]
                self.ratchet = (mode, params[1] or self.ratchet[1], self.ratchet[2])
                return b""
        if fid == hd.THUMB_WHEEL:
            if function == 1:
                return bytes(self.thumb)
            if function == 2:
                self.thumb = [params[0], params[1]]
                return bytes(self.thumb)
        if fid == hd.CHANGE_HOST and function == 0:
            return bytes([len(self.hosts), self.current_host])
        if fid == hd.HOSTS_INFO:
            if function == 0:
                return bytes([0x01, 0, len(self.hosts), self.current_host])
            if function == 1:
                return bytes([params[0], 1, 0, 1, len(self.hosts[params[0]].encode()), 24])
            if function == 3:
                name = self.hosts[params[0]].encode()
                return bytes([params[0], params[1]]) + name[params[1]:params[1] + 14]
        raise HidppError(7)

    def notification(self, fid, event, data: bytes, index=0xFF) -> Message:
        return Message(0x11, index, self.index(fid), event << 4, bytes(data).ljust(16, b"\0"))
