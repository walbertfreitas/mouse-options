"""Ações executadas dentro do serviço, sem simular teclas.

No X11, uma tecla simulada logo depois de uma tecla do teclado de verdade faz o GNOME recarregar todos os
atalhos de todas as janelas e travar a tela por quase um segundo. Por isso, sempre que existe outro caminho,
pedimos a coisa diretamente: D-Bus (GNOME Shell, MPRIS, gsd-power, ScreenSaver), PipeWire/PulseAudio e,
para janelas no X11, mensagens EWMH ao gerenciador de janelas.

Uso para testar: python3 -m mouse_options.direct <ação>
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

from gi.repository import Gio, GLib

try:
    from Xlib import X, Xatom, display, protocol
except ImportError:  # sem python3-xlib: as ações de janela simulam as teclas
    X = None

# Ações que a extensão do GNOME Shell faz por dentro (com os balões nativos, e também no Wayland)
SHELL_ACTIONS = frozenset({
    "volume_up", "volume_down", "mute", "mic_mute", "brightness_up", "brightness_down", "overview", "app_grid",
    "screenshot", "show_desktop", "switch_windows", "switch_apps", "workspace_left", "workspace_right", "maximize",
    "minimize", "close_window"})

PAGER = 2  # fonte "pager": o gerenciador de janelas obedece sem a proteção contra roubo de foco
TOGGLE = 2  # _NET_WM_STATE
ICONIC = 3  # WM_CHANGE_STATE
ALL_DESKTOPS = 0xFFFFFFFF


def is_x11() -> bool:
    session = os.environ.get("XDG_SESSION_TYPE")
    if session:
        return session == "x11"
    return bool(os.environ.get("DISPLAY")) and not os.environ.get("WAYLAND_DISPLAY")


# ------------------------------------------------------------------------- janelas (X11)

class WM:
    def __init__(self):
        self.d = display.Display()
        self.root = self.d.screen().root

    def atom(self, name: str) -> int:
        return self.d.intern_atom(name)

    def window(self, wid: int):
        return self.d.create_resource_object("window", wid)

    def prop(self, wid: int | None, name: str) -> list:
        win = self.root if wid is None else self.window(wid)
        try:
            p = win.get_full_property(self.atom(name), X.AnyPropertyType)
        except Exception:  # noqa: BLE001 — a janela pode ter fechado no meio do caminho
            return []
        return list(p.value) if p else []

    def active(self) -> int | None:
        v = self.prop(None, "_NET_ACTIVE_WINDOW")
        return v[0] if v and v[0] else None

    def timestamp(self) -> int:
        """Hora atual do servidor X (o gerenciador de janelas ignora pedidos com hora 0)."""
        w = self.root.create_window(0, 0, 1, 1, 0, X.CopyFromParent, event_mask=X.PropertyChangeMask)
        w.change_property(self.atom("_MOUSE_OPTIONS_TIME"), Xatom.STRING, 8, b"")
        try:
            while True:
                ev = self.d.next_event()
                if ev.type == X.PropertyNotify and ev.window.id == w.id:
                    return ev.time
        finally:
            w.destroy()

    def send(self, wid: int | None, name: str, data: list) -> None:
        ev = protocol.event.ClientMessage(window=self.root if wid is None else self.window(wid),
                                          client_type=self.atom(name), data=(32, (data + [0] * 5)[:5]))
        self.root.send_event(ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        self.d.flush()

    def wm_class(self, wid: int | None) -> str:
        if not wid:
            return ""
        try:
            return (self.window(wid).get_wm_class() or ("", ""))[1]
        except Exception:  # noqa: BLE001
            return ""

    def switchable(self, wid: int, desktop: int) -> bool:
        """Janela que o Alt+Tab mostraria: normal, na barra de tarefas e na área de trabalho atual."""
        state = self.prop(wid, "_NET_WM_STATE")
        types = self.prop(wid, "_NET_WM_WINDOW_TYPE")
        desk = self.prop(wid, "_NET_WM_DESKTOP")
        return (self.atom("_NET_WM_STATE_SKIP_TASKBAR") not in state
                and (not types or types[0] in (self.atom("_NET_WM_WINDOW_TYPE_NORMAL"),
                                               self.atom("_NET_WM_WINDOW_TYPE_DIALOG")))
                and (not desk or desk[0] in (desktop, ALL_DESKTOPS)))

    def close(self):
        try:
            self.d.close()
        except Exception:  # noqa: BLE001
            pass


def show_desktop(wm: WM) -> None:
    showing = wm.prop(None, "_NET_SHOWING_DESKTOP")
    wm.send(None, "_NET_SHOWING_DESKTOP", [0 if showing and showing[0] else 1])


def _workspace(wm: WM, delta: int) -> None:
    count = (wm.prop(None, "_NET_NUMBER_OF_DESKTOPS") or [1])[0]
    target = (wm.prop(None, "_NET_CURRENT_DESKTOP") or [0])[0] + delta
    if 0 <= target < count:
        wm.send(None, "_NET_CURRENT_DESKTOP", [target, wm.timestamp()])


def workspace_left(wm: WM) -> None:
    _workspace(wm, -1)


def workspace_right(wm: WM) -> None:
    _workspace(wm, 1)


def maximize(wm: WM) -> None:
    if a := wm.active():
        wm.send(a, "_NET_WM_STATE", [TOGGLE, wm.atom("_NET_WM_STATE_MAXIMIZED_VERT"),
                                     wm.atom("_NET_WM_STATE_MAXIMIZED_HORZ"), PAGER])


def minimize(wm: WM) -> None:
    if a := wm.active():
        wm.send(a, "WM_CHANGE_STATE", [ICONIC])


def close_window(wm: WM) -> None:
    if a := wm.active():
        wm.send(a, "_NET_CLOSE_WINDOW", [wm.timestamp(), PAGER])


def _switch(wm: WM, other_app: bool) -> None:
    """Como um toque rápido no Alt+Tab: vai para a janela usada mais recentemente antes da atual."""
    a = wm.active()
    desktop = (wm.prop(None, "_NET_CURRENT_DESKTOP") or [0])[0]
    app = wm.wm_class(a) if a and other_app else None
    for wid in reversed(wm.prop(None, "_NET_CLIENT_LIST_STACKING")):  # de cima para baixo
        if wid != a and wm.switchable(wid, desktop) and (app is None or wm.wm_class(wid) != app):
            wm.send(wid, "_NET_ACTIVE_WINDOW", [PAGER, wm.timestamp(), a or 0])
            return


def switch_windows(wm: WM) -> None:
    _switch(wm, other_app=False)


def switch_apps(wm: WM) -> None:
    _switch(wm, other_app=True)


WINDOW_ACTIONS = {f.__name__: f for f in (show_desktop, workspace_left, workspace_right, maximize, minimize,
                                          close_window, switch_windows, switch_apps)}


# ------------------------------------------------------------------------- áudio

def _gsetting(schema: str, key: str, default):
    source = Gio.SettingsSchemaSource.get_default()
    found = source.lookup(schema, True) if source else None
    if not found or not found.has_key(key):
        return default
    return Gio.Settings.new(schema).get_value(key).unpack()


def _run(*cmds: list[str]) -> bool:
    """Roda o primeiro comando que existir no sistema."""
    for cmd in cmds:
        if shutil.which(cmd[0]):
            return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    return False


def _volume(direction: int) -> None:
    step = _gsetting("org.gnome.settings-daemon.plugins.media-keys", "volume-step", 5)
    limit = "1.5" if _gsetting("org.gnome.desktop.sound", "allow-volume-above-100-percent", False) else "1.0"
    if direction > 0:
        _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"], ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"])
        _run(["wpctl", "set-volume", "-l", limit, "@DEFAULT_AUDIO_SINK@", f"{step}%+"],
             ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"+{step}%"])
    else:
        _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{step}%-"],
             ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"-{step}%"])


# ------------------------------------------------------------------------- serviço

class Direct:
    """Executa as ações internas, mantendo abertas as conexões (X11, D-Bus) entre um clique e outro.

    Use sempre da mesma thread (o executor de ações do serviço).
    """

    SESSION_ACTIONS = ("play_pause", "next_track", "prev_track", "stop", "volume_up", "volume_down", "mute",
                       "mic_mute", "overview", "lock", "files", "calculator", "brightness_up", "brightness_down")

    def __init__(self):
        self._wm: WM | None = None
        self._bus: Gio.DBusConnection | None = None

    def available(self, name: str) -> bool:
        if name in WINDOW_ACTIONS:
            return X is not None and is_x11()
        return name in self.SESSION_ACTIONS

    def run(self, name: str) -> None:
        if name in WINDOW_ACTIONS:
            for attempt in range(2):
                try:
                    if self._wm is None:
                        self._wm = WM()
                    WINDOW_ACTIONS[name](self._wm)
                    return
                except Exception:  # noqa: BLE001 — conexão X caiu: reabre e tenta de novo
                    if self._wm:
                        self._wm.close()
                    self._wm = None
                    if attempt:
                        raise
        getattr(self, "_" + name)()

    # --- D-Bus

    @property
    def bus(self) -> Gio.DBusConnection:
        if self._bus is None or self._bus.is_closed():
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        return self._bus

    def _call(self, dest, path, iface, method, args=None, reply=None, timeout=1500):
        return self.bus.call_sync(dest, path, iface, method, args, reply, Gio.DBusCallFlags.NONE, timeout, None)

    def shell(self, name: str) -> bool:
        """Pede a ação à extensão do GNOME Shell. False se ela não estiver ativa ou não souber fazer."""
        from .daemon.api import SHELL_BUS_NAME, SHELL_INTERFACE, SHELL_PATH
        if name not in SHELL_ACTIONS:
            return False
        try:
            return bool(self._call(SHELL_BUS_NAME, SHELL_PATH, SHELL_INTERFACE, "Action",
                                   GLib.Variant("(s)", (name,)), timeout=800).unpack()[0])
        except GLib.Error:   # extensão desligada/ausente
            return False

    def _get(self, dest, path, iface, prop):
        return self._call(dest, path, "org.freedesktop.DBus.Properties", "Get",
                          GLib.Variant("(ss)", (iface, prop))).unpack()[0]

    # --- mídia (MPRIS): o player tocando; senão o primeiro pausado; senão qualquer um

    def _player(self) -> str | None:
        names = self._call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                           "ListNames").unpack()[0]
        playing = paused = first = None
        for n in names:
            if not n.startswith("org.mpris.MediaPlayer2."):
                continue
            try:
                status = self._get(n, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", "PlaybackStatus")
            except GLib.Error:
                continue
            first = first or n
            if status == "Playing":
                playing = n
                break
            if status == "Paused":
                paused = paused or n
        return playing or paused or first

    def _mpris(self, method: str) -> None:
        if player := self._player():
            self._call(player, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", method)

    def _play_pause(self):
        self._mpris("PlayPause")

    def _next_track(self):
        self._mpris("Next")

    def _prev_track(self):
        self._mpris("Previous")

    def _stop(self):
        self._mpris("Stop")

    # --- áudio

    def _volume_up(self):
        _volume(+1)

    def _volume_down(self):
        _volume(-1)

    def _mute(self):
        _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"], ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])

    def _mic_mute(self):
        _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "toggle"],
             ["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "toggle"])

    # --- GNOME

    def _overview(self):
        shell = ("org.gnome.Shell", "/org/gnome/Shell", "org.gnome.Shell")
        active = self._get(*shell, "OverviewActive")
        self._call(shell[0], shell[1], "org.freedesktop.DBus.Properties", "Set",
                   GLib.Variant("(ssv)", (shell[2], "OverviewActive", GLib.Variant("b", not active))))

    def _lock(self):
        try:  # não espera a tela de bloqueio aparecer
            self.bus.call("org.gnome.ScreenSaver", "/org/gnome/ScreenSaver", "org.gnome.ScreenSaver", "Lock",
                          None, None, Gio.DBusCallFlags.NONE, -1, None, None, None)
        except GLib.Error:
            _run(["loginctl", "lock-session"])

    def _brightness(self, method: str):
        self._call("org.gnome.SettingsDaemon.Power", "/org/gnome/SettingsDaemon/Power",
                   "org.gnome.SettingsDaemon.Power.Screen", method)

    def _brightness_up(self):
        self._brightness("StepUp")

    def _brightness_down(self):
        self._brightness("StepDown")

    def _files(self):
        Gio.AppInfo.launch_default_for_uri(GLib.filename_to_uri(os.path.expanduser("~"), None), None)

    def _calculator(self):
        app = Gio.DesktopAppInfo.new("org.gnome.Calculator.desktop")
        if app:
            app.launch([], None)
        else:
            _run(["gnome-calculator"], ["kcalc"], ["galculator"])


def main(argv: list[str]) -> int:
    d = Direct()
    names = sorted(set(WINDOW_ACTIONS) | set(Direct.SESSION_ACTIONS))
    if len(argv) != 1 or argv[0] not in names:
        print(f"uso: python3 -m mouse_options.direct {{{','.join(names)}}}", file=sys.stderr)
        return 2
    d.run(argv[0])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
