"""Teclado e mouse virtuais (uinput), para as ações que só existem como atalho ou clique.

Funciona no X11 e no Wayland. As teclas são escolhidas pelo layout de teclado da pessoa (via libxkbcommon,
o mesmo motor de layouts do GNOME): para "plus" no ABNT2 sai Shift+= , e assim por diante.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import time

from evdev import UInput, ecodes as e

from ..direct import _gsetting

BUTTONS = {"left": e.BTN_LEFT, "right": e.BTN_RIGHT, "middle": e.BTN_MIDDLE,
           "button8": e.BTN_SIDE, "button9": e.BTN_EXTRA, "back": e.BTN_SIDE, "forward": e.BTN_EXTRA}
# modificador do XKB → tecla que o produz
MOD_KEYS = {"Shift": e.KEY_LEFTSHIFT, "Control": e.KEY_LEFTCTRL, "Mod1": e.KEY_LEFTALT, "Mod4": e.KEY_LEFTMETA,
            "Mod5": e.KEY_RIGHTALT, "Lock": None, "Mod2": None, "Mod3": None}


class _RuleNames(ctypes.Structure):
    _fields_ = [(n, ctypes.c_char_p) for n in ("rules", "model", "layout", "variant", "options")]


def current_layout() -> tuple[str, str, str]:
    """(layout, variante, opções) da fonte de entrada em uso no GNOME; padrão "us"."""
    sources = _gsetting("org.gnome.desktop.input-sources", "mru-sources", []) or \
        _gsetting("org.gnome.desktop.input-sources", "sources", [])
    options = ",".join(_gsetting("org.gnome.desktop.input-sources", "xkb-options", []))
    for kind, name in sources:
        if kind == "xkb":
            layout, _, variant = name.partition("+")
            return layout, variant, options
    return "us", "", options


class Keymap:
    """Descobre que tecla física (e com quais modificadores) produz cada símbolo no layout atual."""

    def __init__(self, layout: str, variant: str = "", options: str = ""):
        lib = ctypes.CDLL(ctypes.util.find_library("xkbcommon") or "libxkbcommon.so.0")
        lib.xkb_context_new.restype = ctypes.c_void_p
        lib.xkb_keymap_new_from_names.restype = ctypes.c_void_p
        lib.xkb_keymap_new_from_names.argtypes = [ctypes.c_void_p, ctypes.POINTER(_RuleNames), ctypes.c_int]
        for f in ("xkb_keymap_min_keycode", "xkb_keymap_max_keycode"):
            getattr(lib, f).restype = ctypes.c_uint32
            getattr(lib, f).argtypes = [ctypes.c_void_p]
        lib.xkb_keymap_num_levels_for_key.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32]
        lib.xkb_keymap_key_get_syms_by_level.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                                         ctypes.c_uint32, ctypes.POINTER(ctypes.POINTER(ctypes.c_uint32))]
        lib.xkb_keymap_key_get_mods_for_level.restype = ctypes.c_size_t
        lib.xkb_keymap_key_get_mods_for_level.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                                          ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
                                                          ctypes.c_size_t]
        lib.xkb_keymap_num_mods.restype = ctypes.c_uint32
        lib.xkb_keymap_num_mods.argtypes = [ctypes.c_void_p]
        lib.xkb_keymap_mod_get_name.restype = ctypes.c_char_p
        lib.xkb_keymap_mod_get_name.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        lib.xkb_keysym_from_name.restype = ctypes.c_uint32
        lib.xkb_keysym_from_name.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.xkb_keymap_unref.argtypes = [ctypes.c_void_p]
        lib.xkb_context_unref.argtypes = [ctypes.c_void_p]
        self._lib = lib
        ctx = lib.xkb_context_new(0)
        names = _RuleNames(b"evdev", b"pc105", layout.encode(), variant.encode(), options.encode())
        km = lib.xkb_keymap_new_from_names(ctx, ctypes.byref(names), 0)
        if not km:
            names = _RuleNames(b"evdev", b"pc105", b"us", b"", b"")
            km = lib.xkb_keymap_new_from_names(ctx, ctypes.byref(names), 0)
        self._table: dict[int, tuple[int, tuple[int, ...]]] = {}   # keysym → (keycode evdev, modificadores)
        mod_names = [lib.xkb_keymap_mod_get_name(km, i).decode() for i in range(lib.xkb_keymap_num_mods(km))]
        syms = ctypes.POINTER(ctypes.c_uint32)()
        masks = (ctypes.c_uint32 * 8)()
        for kc in range(lib.xkb_keymap_min_keycode(km), lib.xkb_keymap_max_keycode(km) + 1):
            for level in range(lib.xkb_keymap_num_levels_for_key(km, kc, 0)):
                n = lib.xkb_keymap_key_get_syms_by_level(km, kc, 0, level, ctypes.byref(syms))
                if n != 1:
                    continue
                count = lib.xkb_keymap_key_get_mods_for_level(km, kc, 0, level, masks, 8)
                mask = min((masks[i] for i in range(count)), default=0, key=lambda m: bin(m).count("1"))
                mods = tuple(MOD_KEYS.get(mod_names[b]) for b in range(32) if mask & (1 << b))
                if None in mods:
                    continue
                current = self._table.get(syms[0])
                if current is None or len(mods) < len(current[1]):   # o jeito com menos modificadores
                    self._table[syms[0]] = (kc - 8, mods)
        lib.xkb_keymap_unref(km)
        lib.xkb_context_unref(ctx)

    def lookup(self, name: str) -> tuple[int, tuple[int, ...]] | None:
        """'plus' → (KEY_EQUAL, (KEY_LEFTSHIFT,)). Aceita nomes do X11/Solaar ('XF86_AudioPlay' também)."""
        if name.startswith("XF86_"):
            name = "XF86" + name[5:]
        sym = self._lib.xkb_keysym_from_name(name.encode(), 0) or self._lib.xkb_keysym_from_name(name.encode(), 1)
        return self._table.get(sym) if sym else None


class VirtualInput:
    NAME = "Mouse Options virtual input"

    def __init__(self):
        keys = list(range(e.KEY_ESC, e.KEY_MICMUTE + 1)) + list(BUTTONS.values())
        self.ui = UInput({e.EV_KEY: sorted(set(keys)),
                          e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL, e.REL_HWHEEL, e.REL_WHEEL_HI_RES,
                                     e.REL_HWHEEL_HI_RES]}, name=self.NAME,
                          # virtual, não USB: o libinput trata mouse USB/Bluetooth como "mouse externo", e o modo
                          # "desligar o touchpad com mouse externo" do GNOME deixaria o touchpad sempre desligado
                          bustype=e.BUS_VIRTUAL)
        self._layout = None
        self._keymap: Keymap | None = None

    def _map(self) -> Keymap:
        layout = current_layout()
        if layout != self._layout:   # a pessoa trocou o layout
            self._layout, self._keymap = layout, Keymap(*layout)
        return self._keymap

    def _emit(self, code: int, value: int):
        self.ui.write(e.EV_KEY, code, value)
        self.ui.syn()

    def keys(self, names: list[str]) -> bool:
        """Aperta a combinação (na ordem) e solta (na ordem inversa). False se alguma tecla não existe."""
        keymap = self._map()
        plan = []
        for n in names:
            found = keymap.lookup(n)
            if found is None:
                return False
            plan.append(found)
        down: list[int] = []
        for code, mods in plan:
            for c in (*mods, code):
                if c not in down:
                    self._emit(c, 1)
                    down.append(c)
        for c in reversed(down):
            self._emit(c, 0)
        return True

    def click(self, button: str, count: int = 1) -> bool:
        code = BUTTONS.get(button)
        if code is None:
            return False
        for i in range(count):
            self._emit(code, 1)
            self._emit(code, 0)
            if i + 1 < count:
                time.sleep(0.03)
        return True

    def scroll(self, dx: int, dy: int) -> None:
        if dy:
            self.ui.write(e.EV_REL, e.REL_WHEEL, dy)
            self.ui.write(e.EV_REL, e.REL_WHEEL_HI_RES, dy * 120)
        if dx:
            self.ui.write(e.EV_REL, e.REL_HWHEEL, dx)
            self.ui.write(e.EV_REL, e.REL_HWHEEL_HI_RES, dx * 120)
        self.ui.syn()

    def close(self):
        self.ui.close()
