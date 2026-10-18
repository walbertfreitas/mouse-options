"""Migração a partir do Solaar.

O Mouse Options tem o próprio serviço (mouse-optionsd) e não usa mais o Solaar. Este módulo:
  1. na primeira vez que um mouse aparece, traz para o app as regras simples que a pessoa tinha no Solaar
     (~/.config/solaar/rules.yaml), para ninguém perder a configuração;
  2. desliga o início automático do Solaar (só um programa pode desviar os botões por vez). O Solaar continua
     instalado; para voltar a usá-lo basta apagar ~/.config/autostart/solaar.desktop.
"""
from __future__ import annotations

import os
import signal
import subprocess

import yaml

from . import actions
from .store import ALL_APPS, Store

CONFIG_HOME = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
RULES_FILE = os.path.join(CONFIG_HOME, "solaar", "rules.yaml")
AUTOSTART_OVERRIDE = os.path.join(CONFIG_HOME, "autostart", "solaar.desktop")


def read_rules(path: str = RULES_FILE) -> list[list]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return [d for d in yaml.safe_load_all(f) if d]
    except (OSError, yaml.YAMLError):
        return []


def import_existing(store: Store, mouse, rules: list[list]) -> int:
    """Traz as regras do tipo [Key: [botão, pressed], ação] (com Device/Process opcionais). Devolve quantas."""
    names = {c.name for c in mouse.controls}
    count = 0
    for rule in rules:
        if not isinstance(rule, list):
            continue
        cond = {k: v for c in rule if isinstance(c, dict) and len(c) == 1 for k, v in c.items()}
        if set(cond) - {"Device", "Process", "Key", "KeyPress", "MouseClick", "MouseScroll", "Execute"}:
            continue
        if "Device" in cond and cond["Device"] != mouse.key:
            continue
        key = cond.get("Key")
        if not (isinstance(key, list) and len(key) == 2 and key[0] in names and key[1] == "pressed"):
            continue
        spec = spec_from_actions(rule)
        if spec is None:
            continue
        app = cond.get("Process", ALL_APPS)
        if app != ALL_APPS:
            store.add_app(mouse.key, app, app)
        if store.get(mouse.key, app, key[0]) is None:
            store.set(mouse.key, app, key[0], spec)
            count += 1
    return count


def _keys(args) -> list[str]:
    """KeyPress do Solaar aceita 'tecla', ['tecla', ...] ou [[teclas], 'click']."""
    if isinstance(args, list) and len(args) == 2 and args[1] in ("click", "depress", "release"):
        args = args[0]
    return [args] if isinstance(args, str) else list(args)


def spec_from_actions(rule: list) -> dict | None:
    acts = [c for c in rule if isinstance(c, dict) and next(iter(c)) in ("KeyPress", "MouseClick", "MouseScroll",
                                                                          "Execute")]
    if len(acts) != 1:
        return None
    kind, args = next(iter(acts[0].items()))
    if kind == "KeyPress":
        keys = _keys(args)
        for a in actions.CATALOG:
            if a.keys and list(a.keys) == keys:
                return {"id": a.id}
        return {"id": "keys", "keys": keys}
    if kind == "MouseClick":
        args = args if isinstance(args, list) else [args]
        click = (args[0], int(args[1]) if len(args) > 1 else 1)
        return next(({"id": a.id} for a in actions.CATALOG if a.click == click), None)
    if kind == "MouseScroll":
        scroll = tuple(int(x) for x in args)
        return next(({"id": a.id} for a in actions.CATALOG if a.scroll == scroll), None)
    args = args if isinstance(args, list) else [args]
    if args[:2] == ["sh", "-c"] and len(args) == 3:
        return {"id": "command", "cmd": args[2]}
    return {"id": "command", "cmd": " ".join(args)}


def solaar_running() -> list[int]:
    out = subprocess.run(["pgrep", "-u", str(os.getuid()), "-f", r"^/usr/bin/python3 /usr/bin/solaar"],
                         capture_output=True, text=True).stdout
    return [int(p) for p in out.split()]


def disable_solaar() -> bool:
    """Para o Solaar e impede que ele inicie com a sessão. Devolve True se mudou algo."""
    changed = False
    if not os.path.exists(AUTOSTART_OVERRIDE):
        os.makedirs(os.path.dirname(AUTOSTART_OVERRIDE), exist_ok=True)
        with open(AUTOSTART_OVERRIDE, "w", encoding="utf-8") as f:
            f.write("[Desktop Entry]\nType=Application\nName=Solaar\nExec=solaar\nHidden=true\n"
                    "# Desligado pelo Mouse Options (só um programa pode controlar os botões do mouse).\n"
                    "# Apague este arquivo para o Solaar voltar a iniciar com a sessão.\n")
        changed = True
    for pid in solaar_running():
        try:
            os.kill(pid, signal.SIGTERM)
            changed = True
        except ProcessLookupError:
            pass
    return changed
