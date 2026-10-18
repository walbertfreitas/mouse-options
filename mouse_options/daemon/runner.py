"""Executa as ações configuradas, uma de cada vez, numa thread própria.

A ordem de preferência para cada ação do catálogo é: função interna sem simular teclas (direct.py);
senão clique/rolagem/atalho pelo teclado e mouse virtuais (vinput.py).
"""
from __future__ import annotations

import logging
import queue
import subprocess
import threading

from gi.repository import Gio

from .. import actions
from ..direct import Direct, is_x11

log = logging.getLogger("mouse-options.runner")


class Runner:
    def __init__(self, vinput_factory=None, direct: Direct | None = None):
        self._queue: queue.Queue = queue.Queue()
        self._direct = direct or Direct()
        self._vinput_factory = vinput_factory
        self._vinput = None
        self._thread = threading.Thread(target=self._loop, name="ações", daemon=True)
        self._thread.start()

    def submit(self, spec: dict, control: str) -> None:
        self._queue.put((spec, control))

    def close(self):
        self._queue.put(None)
        self._thread.join(2)
        if self._vinput:
            self._vinput.close()

    @property
    def vinput(self):
        if self._vinput is None and self._vinput_factory:
            self._vinput = self._vinput_factory()
        return self._vinput

    def prepare(self):
        """Cria o teclado virtual já no início: o sistema leva um instante para reconhecê-lo."""
        self._queue.put(("prepare", None))

    def _loop(self):
        while True:
            item = self._queue.get()
            if item is None:
                return
            spec, control = item
            try:
                if spec == "prepare":
                    _ = self.vinput
                else:
                    self.run(spec, control)
            except Exception:  # noqa: BLE001 — uma ação com erro não pode derrubar o serviço
                log.exception("falha ao executar %s", spec)

    # ------------------------------------------------------------------ execução

    def run(self, spec: dict, control: str) -> None:
        kind = spec.get("id")
        log.debug("%s → %s", control, kind)
        if kind in (None, "none", "gestures"):
            return
        if kind == "default":
            native = actions.NATIVE.get(control)
            if native:
                self._simulate(native.get("click"), native.get("scroll"), None)
        elif kind == "keys":
            self._keys(spec["keys"])
        elif kind == "app":
            app = Gio.DesktopAppInfo.new_from_filename(spec["desktop"])
            if app:
                app.launch([], None)
            else:
                log.warning("app não encontrado: %s", spec["desktop"])
        elif kind == "command":
            subprocess.Popen(["sh", "-c", spec["cmd"]], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif kind in actions.BY_ID:
            a = actions.BY_ID[kind]
            if self._direct.shell(kind):   # extensão do GNOME: nativo, com os balões do sistema
                return
            if a.call and not (a.x11_only and not is_x11()) and self._direct.available(a.call):
                try:
                    self._direct.run(a.call)
                    return
                except Exception:  # noqa: BLE001 — o caminho direto falhou: usa o atalho
                    log.exception("ação interna %s falhou; simulando o atalho", a.call)
            self._simulate(a.click, a.scroll, a.simulated_keys() if a.keys or a.shortcut else None)
        else:
            log.warning("ação desconhecida: %s", kind)

    def _simulate(self, click, scroll, keys):
        if click:
            self.vinput.click(*click)
        elif scroll:
            self.vinput.scroll(*scroll)
        elif keys:
            self._keys(keys)

    def _keys(self, keys):
        if not self.vinput.keys(list(keys)):
            log.warning("atalho com tecla que não existe neste layout: %s", keys)
