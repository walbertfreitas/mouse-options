"""Configuração do Mouse Options (o que cada botão faz, por aplicativo).

Arquivo: ~/.config/mouse-options/config.json
{
  "devices": {
    "<unit id>": {
      "name": "M720 Triathlon",
      "apps": {"*": {"Back Button": {...spec...}}, "firefox": {...}},
      "app_names": {"firefox": "Firefox"}
    }
  },
  "managed_rules": [ ...regras que o app gerou no rules.yaml do Solaar... ]
}
"""
from __future__ import annotations

import json
import os

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "mouse-options")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
ALL_APPS = "*"


class Store:
    def __init__(self, path: str = CONFIG_FILE):
        self.path = path
        self.data: dict = {"devices": {}, "managed_rules": []}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data.update(json.load(f))

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    # --- aparelhos ------------------------------------------------------------

    def device(self, key: str, name: str = "") -> dict:
        devs = self.data["devices"]
        if key not in devs:
            devs[key] = {"name": name, "apps": {ALL_APPS: {}}, "app_names": {}}
        elif name:
            devs[key]["name"] = name
        return devs[key]

    def known(self, key: str) -> bool:
        return key in self.data["devices"]

    # --- ações ------------------------------------------------------------------

    def get(self, key: str, app: str, control: str) -> dict | None:
        return self.device(key)["apps"].get(app, {}).get(control)

    def effective(self, key: str, app: str, control: str) -> tuple[dict | None, bool]:
        """Ação que vale para o app e se ela foi herdada de "Todos os aplicativos"."""
        own = self.get(key, app, control)
        if own is not None or app == ALL_APPS:
            return own, False
        return self.get(key, ALL_APPS, control), True

    def set(self, key: str, app: str, control: str, spec: dict | None) -> None:
        apps = self.device(key)["apps"]
        profile = apps.setdefault(app, {})
        if spec is None:
            profile.pop(control, None)
        else:
            profile[control] = spec

    # --- aplicativos ------------------------------------------------------------

    def apps(self, key: str) -> list[str]:
        return [a for a in self.device(key)["apps"] if a != ALL_APPS]

    def add_app(self, key: str, app: str, name: str) -> None:
        dev = self.device(key)
        dev["apps"].setdefault(app, {})
        dev["app_names"][app] = name

    def remove_app(self, key: str, app: str) -> None:
        dev = self.device(key)
        dev["apps"].pop(app, None)
        dev["app_names"].pop(app, None)

    def app_name(self, key: str, app: str) -> str:
        return self.device(key)["app_names"].get(app, app)
