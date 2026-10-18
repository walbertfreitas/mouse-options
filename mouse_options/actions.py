"""Catálogo de ações que um botão do mouse pode executar.

Quem executa as ações é o serviço (daemon/runner.py). Uma ação é guardada como um dicionário simples
("spec"), por exemplo:
    {"id": "copy"}                                  ação do catálogo
    {"id": "keys", "keys": ["Control_L", "c"]}      atalho de teclado personalizado
    {"id": "app", "desktop": "/usr/share/applications/firefox.desktop", "name": "Firefox"}
    {"id": "command", "cmd": "notify-send oi"}
    {"id": "gestures", "click": {...}, "up": {...}, "down": {...}, "left": {...}, "right": {...}}
    {"id": "default"}  função original do botão      {"id": "none"}  não fazer nada
"""
from __future__ import annotations

from dataclasses import dataclass

from . import shortcuts as sc
from .i18n import T

CATEGORIES = [
    ("navigation", "Navegação"),
    ("media", "Mídia e volume"),
    ("editing", "Edição"),
    ("windows", "Janelas e área de trabalho"),
    ("browser", "Navegador"),
    ("system", "Sistema"),
]

GESTURE_DIRECTIONS = [  # (chave, rótulo, movimento no Solaar)
    ("click", "Clique (sem mover)", None),
    ("up", "Segurar e mover para cima", "Mouse Up"),
    ("down", "Segurar e mover para baixo", "Mouse Down"),
    ("left", "Segurar e mover para a esquerda", "Mouse Left"),
    ("right", "Segurar e mover para a direita", "Mouse Right"),
]


@dataclass(frozen=True)
class CatalogAction:
    """Uma ação pronta do catálogo.

    O serviço executa `call` (função interna de direct.py, sem simular teclas) quando ela existe nesta
    sessão; senão simula `keys` (ou o atalho do sistema `shortcut`), `click` ou `scroll`.
    """
    id: str
    category: str
    label: str
    keys: tuple[str, ...] = ()
    shortcut: tuple[str, str] | None = None   # (schema, chave) do atalho no GNOME; `keys` é o padrão
    click: tuple[str, int] | None = None      # (botão, quantidade)
    scroll: tuple[int, int] | None = None     # (horizontal, vertical)
    call: str | None = None
    x11_only: bool = False                    # `call` só funciona no X11 (no Wayland usa as teclas)

    def simulated_keys(self) -> list[str]:
        if self.shortcut:
            return sc.system_shortcut(*self.shortcut, list(self.keys))
        return list(self.keys)


def _a(id, category, label, *keys, **kw):
    return CatalogAction(id, category, label, tuple(keys), **kw)


CATALOG: list[CatalogAction] = [
    # Navegação
    _a("back", "navigation", "Voltar", click=("button8", 1)),
    _a("forward", "navigation", "Avançar", click=("button9", 1)),
    _a("middle_click", "navigation", "Clique do meio", click=("middle", 1)),
    _a("left_click", "navigation", "Clique esquerdo", click=("left", 1)),
    _a("right_click", "navigation", "Clique direito", click=("right", 1)),
    _a("double_click", "navigation", "Clique duplo", click=("left", 2)),
    _a("scroll_left", "navigation", "Rolar para a esquerda", scroll=(-1, 0)),
    _a("scroll_right", "navigation", "Rolar para a direita", scroll=(1, 0)),
    _a("page_up", "navigation", "Página acima", "Prior"),
    _a("page_down", "navigation", "Página abaixo", "Next"),
    _a("home", "navigation", "Início do documento", "Control_L", "Home"),
    _a("end", "navigation", "Fim do documento", "Control_L", "End"),
    # Mídia
    _a("play_pause", "media", "Tocar / pausar", "XF86_AudioPlay", call="play_pause"),
    _a("next_track", "media", "Próxima faixa", "XF86_AudioNext", call="next_track"),
    _a("prev_track", "media", "Faixa anterior", "XF86_AudioPrev", call="prev_track"),
    _a("stop", "media", "Parar", "XF86_AudioStop", call="stop"),
    _a("volume_up", "media", "Aumentar volume", "XF86_AudioRaiseVolume", call="volume_up"),
    _a("volume_down", "media", "Diminuir volume", "XF86_AudioLowerVolume", call="volume_down"),
    _a("mute", "media", "Mudo", "XF86_AudioMute", call="mute"),
    _a("mic_mute", "media", "Silenciar microfone", "XF86_AudioMicMute", call="mic_mute"),
    # Edição
    _a("copy", "editing", "Copiar", "Control_L", "c"),
    _a("paste", "editing", "Colar", "Control_L", "v"),
    _a("cut", "editing", "Recortar", "Control_L", "x"),
    _a("undo", "editing", "Desfazer", "Control_L", "z"),
    _a("redo", "editing", "Refazer", "Control_L", "Shift_L", "z"),
    _a("select_all", "editing", "Selecionar tudo", "Control_L", "a"),
    _a("save", "editing", "Salvar", "Control_L", "s"),
    _a("find", "editing", "Localizar", "Control_L", "f"),
    _a("zoom_in", "editing", "Aumentar zoom", "Control_L", "plus"),
    _a("zoom_out", "editing", "Diminuir zoom", "Control_L", "minus"),
    _a("zoom_reset", "editing", "Zoom normal", "Control_L", "0"),
    # Janelas e área de trabalho (as teclas simuladas são os atalhos configurados no sistema)
    _a("overview", "windows", "Visão geral (Atividades)", "Super_L", shortcut=(sc.SHELL, "toggle-overview"),
       call="overview"),
    _a("app_grid", "windows", "Mostrar aplicativos", "Super_L", "a",
       shortcut=(sc.SHELL, "toggle-application-view")),
    _a("show_desktop", "windows", "Mostrar área de trabalho", "Super_L", "d", shortcut=(sc.WM, "show-desktop"),
       call="show_desktop", x11_only=True),
    _a("switch_windows", "windows", "Alternar janelas", "Alt_L", "Tab", shortcut=(sc.WM, "switch-windows"),
       call="switch_windows", x11_only=True),
    _a("switch_apps", "windows", "Alternar aplicativos", "Super_L", "Tab",
       shortcut=(sc.WM, "switch-applications"), call="switch_apps", x11_only=True),
    _a("workspace_left", "windows", "Área de trabalho anterior", "Super_L", "Prior",
       shortcut=(sc.WM, "switch-to-workspace-left"), call="workspace_left", x11_only=True),
    _a("workspace_right", "windows", "Próxima área de trabalho", "Super_L", "Next",
       shortcut=(sc.WM, "switch-to-workspace-right"), call="workspace_right", x11_only=True),
    _a("maximize", "windows", "Maximizar / restaurar janela", "Alt_L", "F10", shortcut=(sc.WM, "toggle-maximized"),
       call="maximize", x11_only=True),
    _a("minimize", "windows", "Minimizar janela", "Super_L", "h", shortcut=(sc.WM, "minimize"),
       call="minimize", x11_only=True),
    _a("close_window", "windows", "Fechar janela", "Alt_L", "F4", shortcut=(sc.WM, "close"),
       call="close_window", x11_only=True),
    _a("fullscreen", "windows", "Tela cheia", "F11"),
    # Navegador
    _a("new_tab", "browser", "Nova aba", "Control_L", "t"),
    _a("close_tab", "browser", "Fechar aba", "Control_L", "w"),
    _a("reopen_tab", "browser", "Reabrir aba fechada", "Control_L", "Shift_L", "t"),
    _a("next_tab", "browser", "Próxima aba", "Control_L", "Tab"),
    _a("prev_tab", "browser", "Aba anterior", "Control_L", "Shift_L", "Tab"),
    _a("refresh", "browser", "Atualizar página", "F5"),
    _a("browser_back", "browser", "Página anterior (Alt+←)", "Alt_L", "Left"),
    _a("browser_forward", "browser", "Próxima página (Alt+→)", "Alt_L", "Right"),
    # Sistema
    _a("screenshot", "system", "Captura de tela", "Print", shortcut=(sc.SHELL, "show-screenshot-ui")),
    _a("lock", "system", "Bloquear a tela", "Super_L", "l", shortcut=(sc.MEDIA, "screensaver"), call="lock"),
    _a("files", "system", "Abrir pasta pessoal", "Super_L", "e", shortcut=(sc.MEDIA, "home"), call="files"),
    _a("calculator", "system", "Calculadora", "XF86_Calculator", call="calculator"),
    _a("brightness_up", "system", "Aumentar brilho", "XF86_MonBrightnessUp", call="brightness_up"),
    _a("brightness_down", "system", "Diminuir brilho", "XF86_MonBrightnessDown", call="brightness_down"),
]
BY_ID = {a.id: a for a in CATALOG}

# Como reproduzir a função original de cada botão quando ele precisa ser desviado para o app
# (acontece quando só alguns aplicativos têm uma ação diferente).
NATIVE = {
    "Middle Button": {"click": ("middle", 1)},
    "Back Button": {"click": ("button8", 1)},
    "Forward Button": {"click": ("button9", 1)},
    "Left Tilt": {"scroll": (-1, 0)},
    "Right Tilt": {"scroll": (1, 0)},
    "Left Scroll Button": {"scroll": (-1, 0)},
    "Right Scroll Button": {"scroll": (1, 0)},
}


def is_default(spec: dict | None) -> bool:
    return not spec or spec.get("id") == "default"


KEY_LABELS = {
    "Control_L": "Ctrl", "Shift_L": "Shift", "Alt_L": "Alt", "Super_L": "Super", "Prior": "Page Up",
    "Next": "Page Down", "Return": "Enter", "Escape": "Esc", "BackSpace": "Backspace", "space": "Espaço",
    "plus": "+", "minus": "-", "Left": "←", "Right": "→", "Up": "↑", "Down": "↓",
}


def keys_label(keys: list[str]) -> str:
    return "+".join(T(KEY_LABELS.get(k, k.upper() if len(k) == 1 else k)) for k in keys)


def describe(spec: dict | None) -> str:
    """Texto curto para mostrar na interface."""
    if is_default(spec):
        return T("Padrão do mouse")
    kind = spec["id"]
    if kind == "none":
        return T("Nenhuma ação")
    if kind == "keys":
        return T("Atalho: {keys}", keys=keys_label(spec["keys"]))
    if kind == "app":
        return T("Abrir {name}", name=spec.get("name", "?"))
    if kind == "command":
        return T("Comando: {cmd}", cmd=spec["cmd"])
    if kind == "gestures":
        n = sum(1 for d, _l, _m in GESTURE_DIRECTIONS if not is_default(spec.get(d)) and spec.get(d, {}).get("id") != "none")
        return T("Gestos ({n} configurados)", n=n)
    if kind in BY_ID:
        return T(BY_ID[kind].label)
    return kind
