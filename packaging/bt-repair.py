#!/usr/bin/python3
# Mouse Options — reparo automático do cache do Bluetooth (roda como root).
#
# Se a conexão de um mouse/teclado Bluetooth LE cai no meio da leitura do
# "mapa de relatórios" (o descritor HID), o BlueZ guarda o mapa pela metade
# no cache GATT e reusa esse mapa quebrado em toda reconexão: o kernel recusa
# o aparelho ("item fetching failed at offset ...") e ele nunca mais funciona.
# Este serviço lê as mensagens do kernel e, quando isso acontece com um
# aparelho Bluetooth, para o BlueZ, apaga só o cache daquele aparelho (o
# pareamento fica) e liga o BlueZ de novo: na reconexão o mapa é lido inteiro.
import os
import re
import subprocess
import sys
import time

SYSFS_HID = "/sys/bus/hid/devices"
STORAGE = "/var/lib/bluetooth"
COOLDOWN = 600          # no máximo um reparo por aparelho a cada 10 min

# Mensagens do hid-core quando o descritor HID está quebrado
_BROKEN = re.compile(
    r"^\S+ (?P<id>0005:[0-9A-F]{4}:[0-9A-F]{4}\.[0-9A-F]{4}): "
    r"(item fetching failed|unbalanced (collection|delimiter)|item \d+ \d+ \d+ \d+ parsing failed)")
_MAC = re.compile(r"^[0-9A-F]{2}(:[0-9A-F]{2}){5}$")


def log(msg):
    print(msg, flush=True)


def broken_hid_id(record):
    """Id do aparelho HID Bluetooth (barramento 0005) com descritor quebrado, ou None.
    `record` é um registro do /dev/kmsg: "pri,seq,ts,flags;mensagem\\n[ CHAVE=valor...]"."""
    head = record.split("\n", 1)[0]
    msg = head.split(";", 1)[1] if ";" in head else head
    m = _BROKEN.match(msg)
    return m.group("id") if m else None


def _uevent(hid_id, sysfs):
    try:
        with open(os.path.join(sysfs, hid_id, "uevent")) as f:
            return dict(line.rstrip("\n").split("=", 1) for line in f if "=" in line)
    except OSError:
        return {}


def _info_name(path):
    try:
        with open(path) as f:
            for line in f:
                if line.startswith("Name="):
                    return line[5:].rstrip("\n")
    except OSError:
        pass
    return None


def resolve(hid_id, sysfs=SYSFS_HID, storage=STORAGE):
    """(adaptador, aparelho) em maiúsculas para o aparelho HID, ou None.
    O BlueZ cria o aparelho com phys = adaptador e uniq = endereço do aparelho;
    se o uniq vier vazio (conexão caiu durante a criação), procura pelo nome."""
    ev = _uevent(hid_id, sysfs)
    adapter = ev.get("HID_PHYS", "").upper()
    device = ev.get("HID_UNIQ", "").upper()
    adapters = [adapter] if _MAC.match(adapter) else \
        [a for a in _listdir(storage) if _MAC.match(a)]
    if _MAC.match(device):
        for a in adapters:
            if os.path.isdir(os.path.join(storage, a, device)):
                return a, device
        return None
    name = ev.get("HID_NAME")
    if not name:
        return None
    found = [(a, d) for a in adapters for d in _listdir(os.path.join(storage, a))
             if _MAC.match(d) and _info_name(os.path.join(storage, a, d, "info")) == name]
    return found[0] if len(found) == 1 else None


def _listdir(path):
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def _systemctl(*args):
    subprocess.run(["systemctl", *args, "bluetooth.service"], check=False)


def repair(adapter, device, storage=STORAGE, systemctl=_systemctl):
    """Apaga o cache GATT do aparelho com o BlueZ parado (ao parar, ele grava o
    cache que tem na memória). Devolve True se havia cache para apagar."""
    cache = os.path.join(storage, adapter, "cache", device)
    if not os.path.exists(cache):
        return False
    systemctl("stop")
    try:
        os.remove(cache)
    except FileNotFoundError:
        pass
    finally:
        systemctl("start")
    return True


class Repairer:
    def __init__(self, sysfs=SYSFS_HID, storage=STORAGE, systemctl=_systemctl, clock=time.monotonic):
        self.sysfs, self.storage, self.systemctl, self.clock = sysfs, storage, systemctl, clock
        self.last = {}

    def handle(self, record):
        hid_id = broken_hid_id(record)
        if hid_id is None:
            return None
        target = resolve(hid_id, self.sysfs, self.storage)
        if target is None:
            log(f"{hid_id}: mapa HID quebrado, mas o aparelho Bluetooth não foi identificado")
            return None
        now = self.clock()
        if target in self.last and now - self.last[target] < COOLDOWN:
            log(f"{target[1]}: mapa HID ainda quebrado depois do reparo; "
                "remova o aparelho e pareie de novo")
            return None
        self.last[target] = now
        if repair(*target, storage=self.storage, systemctl=self.systemctl):
            log(f"{target[1]}: mapa HID quebrado no cache do BlueZ; cache apagado e Bluetooth reiniciado")
            return target
        log(f"{target[1]}: mapa HID quebrado, mas não há cache do BlueZ para apagar")
        return None


def records(path="/dev/kmsg"):
    """Registros novos do kernel (a partir de agora)."""
    fd = os.open(path, os.O_RDONLY)
    os.lseek(fd, 0, os.SEEK_END)
    while True:
        try:
            data = os.read(fd, 8192)
        except BrokenPipeError:      # registros sobrescritos antes de lermos
            continue
        yield data.decode("utf-8", "replace")


def main():
    if os.geteuid() != 0:
        sys.exit("bt-repair: precisa rodar como root")
    log("vigiando o kernel por mapas HID quebrados de aparelhos Bluetooth")
    repairer = Repairer()
    for record in records():
        repairer.handle(record)


if __name__ == "__main__":
    main()
