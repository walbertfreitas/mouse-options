"""Encontra os aparelhos Logitech, configura cada um e acompanha o que acontece com eles.

- Descoberta e conexão/desconexão na hora, pelo udev (sem ficar consultando de tempos em tempos).
- Conversa com o aparelho (lenta, ~15 ms por pergunta) em threads de trabalho; os eventos (botões, bateria,
  reconexão) são tratados no laço principal, na ordem em que chegam.
- Desvios e ajustes são temporários no aparelho: reaplicados quando ele reconecta ou avisa que reiniciou,
  e desfeitos quando o serviço para (os botões voltam ao normal).
"""
from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from typing import Callable

import pyudev
from gi.repository import GLib

from ..hidpp import device as hd
from ..hidpp.transport import HidppError, Timeout, Transport
from ..store import Store
from .engine import GESTURES, REGULAR, ButtonEngine
from .state import State

log = logging.getLogger("mouse-options.manager")

LOGITECH = 0x046D
POINTING = ("mouse", "trackball", "touchpad")
SPEED_RANGE = (46, 511)          # POINTER_SPEED: 256 = 1,0×
RECEIVER_SLOTS = range(1, 7)     # aparelhos atrás de um receptor Unifying/Bolt
NOT_THERE = (0x08, 0x09)         # erros HID++ 1.0 do receptor: aparelho desconhecido / não conectado
# recursos cujas notificações tratamos (e que usamos depois): as posições deles vão para o cache
NOTIFYING_FEATURES = (hd.FEATURE_SET, hd.DEVICE_FW_VERSION, hd.REPROG_CONTROLS_V4, hd.WIRELESS_DEVICE_STATUS,
                      hd.UNIFIED_BATTERY, hd.BATTERY_STATUS, hd.BATTERY_VOLTAGE, hd.HIRES_WHEEL, hd.POINTER_SPEED,
                      hd.CHANGE_HOST, hd.HOSTS_INFO, hd.ADJUSTABLE_DPI, hd.SMART_SHIFT, hd.SMART_SHIFT_ENHANCED,
                      hd.THUMB_WHEEL)
# ajuste guardado → campo mostrado na interface
SETTINGS = {"pointer_speed": "pointer_speed", "hires-smooth-invert": "invert_scroll",
            "hires-smooth-resolution": "smooth_scroll", "dpi": "dpi", "smart-shift": "smart_shift",
            "thumb-scroll-invert": "thumb_invert"}


def codename(name: str) -> str:
    """'M720 Triathlon Multi-Device Mouse' → 'M720 Triathlon'."""
    name = re.sub(r"^Logitech\s+", "", name)
    return re.sub(r"\s+(Multi-Device\s+)?(Wireless\s+)?(Mouse|Trackball)$", "", name).strip() or name


class Session:
    """Um aparelho conectado agora."""

    def __init__(self, path: str, transport: Transport, dev: hd.Device, key: str, info: dict,
                 controls: list[hd.ControlInfo], engine: ButtonEngine):
        self.path, self.transport, self.dev, self.key = path, transport, dev, key
        self.info, self.controls, self.engine = info, controls, engine
        self.lock = threading.Lock()   # uma conversa de configuração por vez

    @property
    def names(self) -> dict[int, str]:
        return {c.cid: c.name for c in self.controls if c.divertable and not c.virtual}


class Manager:
    def __init__(self, runner, focus, on_changed: Callable[[], None], on_pressed: Callable[[str, int], None],
                 store_path: str | None = None, state: State | None = None):
        self.runner, self.focus = runner, focus
        self.on_changed, self.on_pressed = on_changed, on_pressed
        self.store_path = store_path
        self.store = self._load_store()
        self.state = state or State()
        self.sessions: dict[str, Session] = {}     # caminho do hidraw → sessão
        self._opening: set[str] = set()
        self._slots: dict[str, int] = {}             # hidraw de aparelho atrás de receptor → posição
        self._parked: dict[str, Transport] = {}      # aparelhos do receptor desligados agora: esperando conectar
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="aparelho")
        self._udev = pyudev.Context()
        self._monitor = None

    def _load_store(self) -> Store:
        return Store(self.store_path) if self.store_path else Store()

    # ------------------------------------------------------------------ descoberta

    def start(self) -> None:
        self._monitor = pyudev.Monitor.from_netlink(self._udev)
        self._monitor.filter_by("hidraw")
        self._monitor.start()
        GLib.io_add_watch(self._monitor.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN, self._on_udev)
        for d in self._udev.list_devices(subsystem="hidraw"):
            self._consider(d)

    def _on_udev(self, *_):
        while (d := self._monitor.poll(0)) is not None:
            if d.action == "add":
                self._consider(d)
        return True

    @staticmethod
    def _is_candidate(d) -> bool:
        hid = d.find_parent("hid")
        if hid is None:
            return False
        try:
            _bus, vendor, _product = (int(x, 16) for x in hid.properties.get("HID_ID", "").split(":"))
        except ValueError:
            return False
        # receptores (logitech-djreceiver) ficam para a fase dos receptores; os aparelhos pareados com eles
        # aparecem como logitech-hidpp-device e são tratados aqui
        return vendor == LOGITECH and hid.driver in ("logitech-hidpp-device", "hid-generic")

    def _consider(self, d) -> None:
        path = d.device_node
        if not path or path in self.sessions or path in self._opening or path in self._parked \
                or not self._is_candidate(d):
            return
        slot = self._receiver_slot(d)
        if slot is not None:
            self._slots[path] = slot
        self._opening.add(path)
        self._pool.submit(self._open, path)

    @staticmethod
    def _receiver_slot(d) -> int | None:
        """Aparelho atrás de um receptor: o kernel põe a posição no fim do endereço (…/input2:1)."""
        match = re.search(r":(\d)$", d.find_parent("hid").properties.get("HID_PHYS", ""))
        return int(match.group(1)) if match and int(match.group(1)) in RECEIVER_SLOTS else None

    # ------------------------------------------------------------------ abrir / configurar (thread de trabalho)

    def _open(self, path: str, transport: Transport | None = None) -> None:
        try:
            self._open_inner(path, transport)
        except Exception:  # noqa: BLE001
            log.exception("não foi possível abrir %s", path)
        finally:
            GLib.idle_add(self._opening.discard, path)

    def _open_inner(self, path: str, transport: Transport | None = None) -> None:
        """Etapa rápida: identificar e desviar os botões. Depois, sem atrasar os botões, o resto."""
        started = time.monotonic()
        slot = self._slots.get(path)
        if transport is None:
            transport = Transport(path, on_notification=lambda m: GLib.idle_add(self._dispatch, path, m),
                                  on_close=lambda: GLib.idle_add(self._closed, path))
        dev = self._find_device(transport, slot)
        if dev is None:
            if slot is not None:   # pareado com o receptor, mas desligado/em outro canal: espera conectar
                GLib.idle_add(self._park, path, transport)
            else:
                transport.close()
            return
        ids = dev.ids()
        identity = self._identify(dev, ids)
        if identity is None:
            transport.close()
            return
        name, kind, controls, cache = identity
        key = ids.unit_id if ids else name
        known = self.state.devices.get(key, {}).get("info", {})
        info = {
            "key": key, "name": name, "codename": codename(name), "kind": kind,
            "unit_id": ids.unit_id if ids else "", "model_id": ids.model_id if ids else "", "online": True,
            "battery": None, "charging": False,
            "controls": [{"cid": c.cid, "name": c.name, "gestures": c.raw_xy}
                         for c in controls if c.divertable and not c.virtual],
            "pointer_range": list(SPEED_RANGE),
            # até a leitura completa, mostra o que se sabia da última vez
            **{k: known.get(k) for k in (*SETTINGS.values(), "dpi_choices", "current_host")},
            "hosts": known.get("hosts", []),
        }
        engine = ButtonEngine(self.runner.submit, self.focus, lambda cid, k=key: self.on_pressed(k, cid))
        session = Session(path, transport, dev, key, info, controls, engine)

        def register():
            session.engine.configure(self.store.device(key) if key in self.store.data["devices"] else {},
                                     session.names)
            for other_path, other in list(self.sessions.items()):   # um aparelho só tem uma conexão por vez
                if other.key == key and other_path != path:
                    self._link_changed(other_path, online=False)
            self.sessions[path] = session
            if cache:
                self.state.entry(key)["cache"] = cache
                self.state.save()

        self._on_main(register)
        self._apply(session)
        log.info("%s pronto em %.0f ms (%s, %s)", name, (time.monotonic() - started) * 1000, key, path)
        GLib.idle_add(self.on_changed)
        self._complete(session)

    def _park(self, path: str, transport: Transport) -> bool:
        if not transport.closed:
            self._parked[path] = transport
        return False

    def _find_device(self, transport: Transport, slot: int | None = None) -> hd.Device | None:
        for index in ((slot,) if slot is not None else (0xFF, *RECEIVER_SLOTS)):
            candidate = hd.Device(transport, index)
            for _ in range(3):   # recém-conectado às vezes demora a responder
                if candidate.ping(timeout=0.6):
                    return candidate if candidate.protocol[0] >= 2 else None
        return None

    def _identify(self, dev: hd.Device, ids) -> tuple | None:
        """(nome, tipo, botões, cache novo ou None). Usa o que foi guardado se o aparelho for o mesmo."""
        cache = self.state.devices.get(ids.unit_id, {}).get("cache") if ids else None
        if cache and cache.get("model_id") == ids.model_id and cache.get("kind") in POINTING:
            dev.preload({int(fid): idx for fid, idx in cache["features"].items()})
            try:
                if dev.feature_count() == cache["feature_count"]:
                    return cache["name"], cache["kind"], [hd.ControlInfo(**c) for c in cache["controls"]], None
            except (HidppError, Timeout):
                pass
            dev.forget()   # o aparelho mudou (ex.: atualização de firmware): descobre tudo de novo
        kind = dev.kind()
        if kind not in POINTING:
            log.info("%s é %s; por enquanto só mouses são configurados", dev.transport.path, kind)
            return None
        name = dev.name() or "Logitech"
        controls = dev.controls()
        for fid in NOTIFYING_FEATURES:   # para reconhecer as notificações e já guardar as posições
            dev.has(fid)
        new_cache = {"model_id": ids.model_id if ids else "", "feature_count": dev.feature_count(),
                     "features": {str(fid): idx for fid, idx in dev.known_features().items()},
                     "name": name, "kind": kind, "controls": [asdict(c) for c in controls]}
        return name, kind, controls, new_cache

    def _complete(self, s: Session) -> None:
        """Etapa completa: bateria, ajustes e Easy-Switch; reaplica os ajustes guardados."""
        with s.lock:
            battery = _safe(s.dev.battery)
            wheel = _safe(s.dev.wheel_mode)
            hosts = _safe(s.dev.hosts)
            names = _safe(lambda: s.dev.host_names(hosts[0])) if hosts else None
            speed = _safe(s.dev.pointer_speed)
            extra = {"dpi": _safe(s.dev.dpi), "dpi_choices": _safe(s.dev.dpi_choices),
                     "smart_shift": _safe(s.dev.smart_shift), "thumb_invert": _safe(s.dev.thumb_invert)}
        fresh = {
            **extra,
            "battery": battery.level if battery else None, "charging": bool(battery and battery.charging),
            "pointer_speed": speed,
            "invert_scroll": wheel.invert if wheel else None, "smooth_scroll": wheel.hires if wheel else None,
            "hosts": [n or f"Canal {i + 1}" for i, n in enumerate(names or [])] if hosts else [],
            "current_host": hosts[1] if hosts else None,
        }

        def merge():
            s.info.update(fresh)
            entry = self.state.entry(s.key)
            entry["info"] = {k: v for k, v in s.info.items() if k not in ("online", "battery", "charging")}
            for setting, field in SETTINGS.items():   # o que está no mouse vira o ajuste guardado (1ª vez)
                if setting not in entry["settings"] and fresh.get(field) is not None:
                    entry["settings"][setting] = fresh[field]
            self.state.save()

        self._on_main(merge)
        with s.lock:
            try:
                self._apply_settings(s, self.state.entry(s.key)["settings"])
            except (HidppError, Timeout, hd.Unsupported) as e:
                if not self._gone(s, e):
                    log.warning("%s: ajustes não aplicados: %s", s.key, e)
        GLib.idle_add(self.on_changed)

    @staticmethod
    def _on_main(fn, timeout: float = 5.0) -> None:
        """Roda fn no laço principal e espera terminar (o estado só é mexido de lá)."""
        done = threading.Event()

        def run():
            try:
                fn()
            finally:
                done.set()
            return False

        GLib.idle_add(run)
        done.wait(timeout)

    def _apply(self, s: Session) -> None:
        """Desvia os botões conforme a configuração."""
        with s.lock:
            try:
                for c in s.controls:
                    if not c.divertable or c.virtual:
                        continue
                    mode = s.engine.modes.get(c.name, REGULAR)
                    s.dev.set_reporting(c.cid, mode != REGULAR, mode == GESTURES and c.raw_xy)
            except (HidppError, Timeout, hd.Unsupported) as e:
                if self._gone(s, e):
                    return
                log.warning("%s: não deu para aplicar tudo: %s", s.key, e)

    def _gone(self, s: Session, error: Exception) -> bool:
        """O receptor disse que o aparelho não está conectado nele: marca como desconectado."""
        if isinstance(error, HidppError) and error.protocol == 1 and error.code in NOT_THERE \
                and s.path in self._slots:
            GLib.idle_add(lambda: self._link_changed(s.path, online=False) or False)
            return True
        return False

    def _reapply(self, s: Session) -> None:
        self._apply(s)
        if s.path not in self.sessions:
            return
        with s.lock:
            try:
                self._apply_settings(s, self.state.entry(s.key)["settings"])
            except (HidppError, Timeout, hd.Unsupported) as e:
                if not self._gone(s, e):
                    log.warning("%s: ajustes não aplicados: %s", s.key, e)

    @staticmethod
    def _apply_settings(s: Session, settings: dict) -> None:
        if "pointer_speed" in settings and s.info.get("pointer_speed") is not None:
            s.dev.set_pointer_speed(settings["pointer_speed"])
            s.info["pointer_speed"] = settings["pointer_speed"]
        if "dpi" in settings and s.info.get("dpi") is not None:
            s.dev.set_dpi(settings["dpi"])
            s.info["dpi"] = settings["dpi"]
        if "smart-shift" in settings and s.info.get("smart_shift") is not None:
            s.dev.set_smart_shift(settings["smart-shift"])
            s.info["smart_shift"] = settings["smart-shift"]
        if "thumb-scroll-invert" in settings and s.info.get("thumb_invert") is not None:
            s.dev.set_thumb_invert(settings["thumb-scroll-invert"])
            s.info["thumb_invert"] = settings["thumb-scroll-invert"]
        invert, hires = settings.get("hires-smooth-invert"), settings.get("hires-smooth-resolution")
        if (invert is not None or hires is not None) and s.info.get("invert_scroll") is not None:
            s.dev.set_wheel_mode(invert=invert, hires=hires)
            if invert is not None:
                s.info["invert_scroll"] = invert
            if hires is not None:
                s.info["smooth_scroll"] = hires

    # ------------------------------------------------------------------ eventos (laço principal)

    def _dispatch(self, path: str, msg) -> bool:
        if msg.sub_id == 0x41 and msg.index in RECEIVER_SLOTS:   # receptor: aparelho conectou/desconectou
            self._link_changed(path, online=not msg.address & 0x40)
            return False
        if path in self._parked:
            if msg.index == self._slots.get(path) and msg.sub_id < 0x80:   # o aparelho voltou a falar
                self._link_changed(path, online=True)
            return False
        s = self.sessions.get(path)
        if s is None:
            return False
        event = s.dev.parse(msg)
        if isinstance(event, (hd.ButtonsEvent, hd.MoveEvent)):
            s.engine.handle(event)
        elif isinstance(event, hd.BatteryEvent):
            b = event.battery
            if (b.level, b.charging) != (s.info["battery"], s.info["charging"]):
                s.info["battery"], s.info["charging"] = b.level, b.charging
                self.on_changed()
        elif isinstance(event, hd.ReconfigureEvent):
            log.info("%s reiniciou; reaplicando", s.key)
            self._pool.submit(self._reapply, s)
        elif isinstance(event, hd.WheelEvent):
            s.info["invert_scroll"], s.info["smooth_scroll"] = event.invert, event.hires
            self.on_changed()
        return False

    def _link_changed(self, path: str, online: bool) -> None:
        if online and path in self._parked and path not in self._opening:
            self._opening.add(path)
            self._pool.submit(self._open, path, self._parked.pop(path))
        elif online and path in self.sessions:   # acordou: pode ter perdido os desvios
            self._pool.submit(self._reapply, self.sessions[path])
        elif not online and path in self.sessions:
            s = self.sessions.pop(path)
            self._parked[path] = s.transport   # o hidraw continua: espera o aparelho voltar
            log.info("%s desconectado do receptor", s.key)
            self.on_changed()

    def _closed(self, path: str) -> bool:
        self._parked.pop(path, None)
        self._slots.pop(path, None)
        s = self.sessions.pop(path, None)
        if s:
            log.info("%s desconectado", s.key)
            self.on_changed()
        return False

    # ------------------------------------------------------------------ pedidos da interface

    def devices(self) -> list[dict]:
        online = {s.key: s for s in self.sessions.values()}
        out = [dict(s.info) for s in online.values()]
        for key, entry in self.state.devices.items():
            if key not in online and entry.get("info"):
                info = dict(entry["info"], online=False, battery=None, charging=False)
                settings = entry.get("settings", {})
                info["pointer_speed"] = settings.get("pointer_speed", info.get("pointer_speed"))
                out.append(info)
        return out

    def reload(self) -> None:
        """A interface salvou o config.json: reconfigura os botões de todos os aparelhos."""
        self.store = self._load_store()
        for s in self.sessions.values():
            s.engine.configure(self.store.device(s.key) if s.key in self.store.data["devices"] else {}, s.names)
            self._pool.submit(self._apply, s)

    def set_settings(self, key: str, settings: dict) -> None:
        self.state.entry(key)["settings"].update(settings)
        self.state.save()
        for s in self.sessions.values():
            if s.key == key:
                self._pool.submit(self._settings_now, s, settings)

    def _settings_now(self, s: Session, settings: dict) -> None:
        with s.lock:
            try:
                self._apply_settings(s, settings)
            except (HidppError, Timeout, hd.Unsupported) as e:
                log.warning("%s: ajuste não aplicado: %s", s.key, e)
        GLib.idle_add(self.on_changed)

    def set_host(self, key: str, host: int) -> None:
        for s in self.sessions.values():
            if s.key == key:
                self._pool.submit(s.dev.set_host, host)

    def stop(self) -> None:
        """Devolve os botões ao normal antes de sair."""
        for s in list(self.sessions.values()):
            with s.lock:
                for c in s.controls:
                    if c.divertable and not c.virtual and s.engine.modes.get(c.name, REGULAR) != REGULAR:
                        try:
                            s.dev.set_reporting(c.cid, False, False)
                        except (HidppError, Timeout, hd.Unsupported):
                            pass
            s.transport.close()
        for t in self._parked.values():
            t.close()
        self._pool.shutdown(wait=False)


def _safe(fn):
    try:
        return fn()
    except (HidppError, Timeout, hd.Unsupported):
        return None
