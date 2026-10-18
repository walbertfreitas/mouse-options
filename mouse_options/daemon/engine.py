"""Decide o que fazer quando um botão desviado é apertado (ou solto, no caso dos gestos).

Configuração de um aparelho (config.json → devices[chave]):
    {"apps": {"*": {"Back Button": spec, ...}, "nemo": {...}}, ...}
Para cada botão vale o perfil do app em foco, se ele tiver algo para esse botão; senão, o perfil geral ("*").
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable

from .. import actions
from ..hidpp.device import ButtonsEvent, MoveEvent
from ..store import ALL_APPS

REGULAR, DIVERT, GESTURES = 0, 1, 2
GESTURE_THRESHOLD = 2.5    # unidades (~5 por cm, como no Solaar): abaixo disso o gesto conta como clique
GESTURE_SCALE = 15 / 1000  # converte o movimento bruto (pontos a 1000 DPI) para as unidades acima


def divert_mode(spec: dict | None) -> int:
    if spec and spec.get("id") == "gestures":
        return GESTURES
    return REGULAR if actions.is_default(spec) else DIVERT


def control_modes(dev_config: dict, control_names: list[str]) -> dict[str, int]:
    """Como cada botão precisa ficar: normal, desviado ou desviado com movimento (gestos).

    Se algum perfil usa gestos, o botão inteiro vai para o modo de gestos; se só um app muda o botão,
    ele é desviado em todos e o perfil geral reproduz a função original.
    """
    apps = dev_config.get("apps", {})
    out = {}
    for name in control_names:
        modes = {divert_mode(profile.get(name)) for profile in apps.values() if profile.get(name) is not None}
        out[name] = max(modes, default=REGULAR)
    return out


def resolve(dev_config: dict, control: str, focus_names: list[str], matches: Callable[[list[str], str], bool]) -> dict:
    """A ação de um botão para o app em foco."""
    apps = dev_config.get("apps", {})
    for app, profile in apps.items():
        if app != ALL_APPS and profile.get(control) is not None and matches(focus_names, app):
            return profile[control]
    return apps.get(ALL_APPS, {}).get(control) or {"id": "default"}


def gesture_direction(dx: float, dy: float) -> str:
    """'click' se mal se moveu; senão a direção predominante (diagonais contam pelo eixo maior)."""
    if math.hypot(dx, dy) < GESTURE_THRESHOLD:
        return "click"
    if abs(dx) >= abs(dy):
        return "right" if dx > 0 else "left"
    return "down" if dy > 0 else "up"


def gesture_action(spec: dict, direction: str) -> dict | None:
    """Ação de um gesto. Um botão em modo de gestos com ação simples: ela vale para o clique."""
    if spec.get("id") != "gestures":
        return spec if direction == "click" else None
    sub = spec.get(direction)
    if sub is None and direction == "click":
        return {"id": "default"}
    return sub


def resolve_gesture(dev_config: dict, control: str, focus_names: list[str],
                    matches: Callable[[list[str], str], bool], direction: str) -> dict | None:
    """A ação de um gesto (ou do clique) para o app em foco.

    Num perfil de app, o que os gestos dele não definem vem de Todos os aplicativos: dá para pôr
    "voltar" num gesto do navegador sem perder o que o clique do botão faz no resto.
    """
    apps = dev_config.get("apps", {})
    for app, profile in apps.items():
        spec = profile.get(control)
        if app != ALL_APPS and spec is not None and matches(focus_names, app):
            if spec.get("id") != "gestures" or direction in spec:
                return gesture_action(spec, direction)
            break
    return gesture_action(apps.get(ALL_APPS, {}).get(control) or {"id": "default"}, direction)


@dataclass
class _Held:
    control: str
    mode: int
    focus: list[str]
    dx: float = 0.0
    dy: float = 0.0
    since: float = field(default_factory=time.monotonic)


class ButtonEngine:
    """Estado dos botões de um aparelho. Chamado sempre da mesma thread (o laço principal do serviço)."""

    def __init__(self, run: Callable[[dict, str], None], focus, on_pressed: Callable[[int], None] | None = None):
        self._run = run
        self._focus = focus
        self._on_pressed = on_pressed
        self.config: dict = {}
        self.names: dict[int, str] = {}       # cid → nome
        self.modes: dict[str, int] = {}
        self._held: dict[int, _Held] = {}

    def configure(self, dev_config: dict, names: dict[int, str]) -> None:
        self.config, self.names = dev_config, names
        self.modes = control_modes(dev_config, list(names.values()))
        self._held.clear()

    def handle(self, event) -> None:
        if isinstance(event, ButtonsEvent):
            now = event.cids
            for cid in now - set(self._held):
                self._press(cid)
            for cid in set(self._held) - now:
                self._release(cid)
        elif isinstance(event, MoveEvent):
            for held in self._held.values():
                if held.mode == GESTURES:
                    held.dx += event.dx * GESTURE_SCALE
                    held.dy += event.dy * GESTURE_SCALE

    def _press(self, cid: int) -> None:
        name = self.names.get(cid)
        if self._on_pressed:
            self._on_pressed(cid)
        mode = self.modes.get(name, REGULAR) if name else REGULAR
        focus = self._focus.names() if mode != REGULAR else []
        self._held[cid] = _Held(name or "", mode, focus)
        if mode == DIVERT:
            self._run(resolve(self.config, name, focus, self._focus.matches), name)

    def _release(self, cid: int) -> None:
        held = self._held.pop(cid, None)
        if held is None or held.mode != GESTURES:
            return
        action = resolve_gesture(self.config, held.control, held.focus, self._focus.matches,
                                 gesture_direction(held.dx, held.dy))
        if action:
            self._run(action, held.control)
