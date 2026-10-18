"""O que o serviço lembra de cada aparelho: dados para mostrar mesmo desconectado e os ajustes a reaplicar.

Arquivo próprio (~/.config/mouse-options/devices.json), separado do config.json que a interface edita,
para os dois nunca sobrescreverem as mudanças um do outro.
"""
from __future__ import annotations

import json
import os

from ..store import CONFIG_DIR

STATE_FILE = os.path.join(CONFIG_DIR, "devices.json")


class State:
    def __init__(self, path: str = STATE_FILE):
        self.path = path
        self.devices: dict[str, dict] = {}
        try:
            with open(path, encoding="utf-8") as f:
                self.devices = json.load(f).get("devices", {})
        except (OSError, ValueError):
            pass

    def entry(self, key: str) -> dict:
        return self.devices.setdefault(key, {"info": {}, "settings": {}})

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"devices": self.devices}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
