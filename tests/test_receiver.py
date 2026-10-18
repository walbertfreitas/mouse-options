"""Receptor simulado: registradores HID++ 1.0 como o Unifying responde, e o fluxo de pareamento no serviço."""
import os
import tempfile
import unittest

from mouse_options.hidpp import receiver as rx
from mouse_options.hidpp.transport import HidppError, Message


class FakeReceiver:
    """Unifying com o M720 na posição 1 e um teclado na 3."""

    def __init__(self):
        self.devices = {1: ("405E", 2, "M720 Triathlon"), 3: ("4075", 1, "K270")}
        self.writes = []
        self.reports = {0x10, 0x11}
        self.closed = False

    def register(self, index, sub_id, register, params=b"", timeout=2.0, long=None):
        assert index == 0xFF
        if (sub_id, register) == (rx.READ_LONG, rx.INFO):
            sub = params[0]
            if sub == 0x03:
                return bytes([0x03]) + bytes.fromhex("12345678") + bytes([0, 6]) + bytes(9)
            slot = (sub & 0x0F) + 1
            if slot not in self.devices:
                raise HidppError(0x02, protocol=1)
            wpid, kind, name = self.devices[slot]
            if sub & 0xF0 == 0x20:
                return bytes([sub, 0, 8]) + bytes.fromhex(wpid) + bytes([0, 0, kind]) + bytes(8)
            if sub & 0xF0 == 0x40:
                return bytes([sub, len(name)]) + name.encode() + bytes(14 - len(name))
        if (sub_id, register) == (rx.WRITE_SHORT, rx.PAIRING):
            self.writes.append(bytes(params))
            return b""
        raise HidppError(0x01, protocol=1)

    def close(self):
        self.closed = True


def lock(open_, error=0):
    return Message(0x10, 0xFF, 0x4A, 0x01 if open_ else 0x00, bytes([error, 0, 0]))


def link(slot, wpid, online=True):
    # como o M720 mandou de verdade: 01 41 04 625e40 (sem ligação) e 01 41 04 a25e40 (ligado)
    return Message(0x10, slot, 0x41, 0x04, bytes([0xA2 if online else 0x62]) + bytes.fromhex(wpid)[::-1])


class ReceiverTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeReceiver()
        self.r = rx.Receiver(self.fake, 0xC52B)

    def test_info_and_paired(self):
        self.assertEqual(self.r.kind, "unifying")
        self.assertTrue(self.r.can_pair)
        self.assertEqual(self.r.info(), ("12345678", 6))
        self.assertEqual(self.r.paired(), [rx.Paired(1, "405E", "mouse", "M720 Triathlon"),
                                           rx.Paired(3, "4075", "keyboard", "K270")])

    def test_lock_and_unpair(self):
        self.r.open_lock()
        self.r.close_lock()
        self.r.unpair(3)
        self.assertEqual(self.fake.writes, [bytes([1, 0, 60]), bytes([2, 0, 0]), bytes([3, 3, 0])])

    def test_parse(self):
        self.assertEqual(rx.Receiver.parse(lock(True)), rx.LockEvent(True, None))
        self.assertEqual(rx.Receiver.parse(lock(False, 1)), rx.LockEvent(False, "timeout"))
        self.assertEqual(rx.Receiver.parse(link(2, "4082")), rx.LinkEvent(2, "4082", True))
        self.assertEqual(rx.Receiver.parse(link(1, "405E", online=False)), rx.LinkEvent(1, "405E", False))

    def test_bolt_lists_but_does_not_pair(self):
        self.assertEqual(rx.Receiver(self.fake, 0xC548).kind, "bolt")
        self.assertFalse(rx.Receiver(self.fake, 0xC548).can_pair)


class PairingFlowTest(unittest.TestCase):
    def setUp(self):
        from mouse_options.daemon.manager import Manager, ReceiverSession
        from mouse_options.daemon.state import State
        d = tempfile.mkdtemp()
        self.events = []
        self.m = Manager(None, None, lambda: None, lambda k, c: None, store_path=os.path.join(d, "c.json"),
                         state=State(os.path.join(d, "devices.json")), on_receivers=lambda: self.events.append(1))
        self.m._pool.submit = lambda fn, *args: fn(*args)          # sem threads no teste
        self.m._on_main = lambda fn, timeout=5.0: fn()
        self.fake = FakeReceiver()
        self.rs = ReceiverSession("/dev/hidraw0", self.fake, rx.Receiver(self.fake, 0xC52B),
                                  "/sys/devices/x/0003:046D:C52B.0001")
        self.m._refresh_receiver(self.rs)
        self.m.receivers["/dev/hidraw0"] = self.rs

    def test_list_with_online_state(self):
        self.m.sessions["/dev/hidraw3"] = type("S", (), {"info": {"codename": "M720 Triathlon"}})()
        self.m._slots["/dev/hidraw3"] = 1
        self.m._hid_paths["/dev/hidraw3"] = "/sys/devices/x/0003:046D:C52B.0001/0003:046D:405E.0002"
        info = self.m.receivers_info()[0]
        self.assertEqual((info["kind"], info["serial"], info["can_pair"]), ("unifying", "12345678", True))
        self.assertEqual([(d["slot"], d["name"], d["online"]) for d in info["devices"]],
                         [(1, "M720 Triathlon", True), (3, "K270", False)])

    def test_pairing_a_new_device(self):
        self.m.start_pairing("/dev/hidraw0")
        self.assertEqual(self.fake.writes[-1], bytes([1, 0, 60]))
        self.m._receiver_event("/dev/hidraw0", lock(True))
        self.assertTrue(self.rs.pairing["open"])
        self.fake.devices[2] = ("4082", 2, "MX Anywhere 3")             # o aparelho aceitou
        self.m._receiver_event("/dev/hidraw0", link(2, "4082", online=False))   # ordem real do receptor
        self.m._receiver_event("/dev/hidraw0", lock(False))
        self.m._receiver_event("/dev/hidraw0", link(2, "4082"))
        self.assertEqual(self.rs.pairing, {"open": False, "error": None, "new": "4082"})
        self.assertIn((2, "MX Anywhere 3"), [(d["slot"], d["name"]) for d in self.m.receivers_info()[0]["devices"]])

    def test_pairing_timeout(self):
        self.m.start_pairing("/dev/hidraw0")
        self.m._receiver_event("/dev/hidraw0", lock(True))
        self.m._receiver_event("/dev/hidraw0", lock(False, 1))
        self.assertEqual(self.rs.pairing, {"open": False, "error": "timeout", "new": None})

    def test_unpair(self):
        def unpair_write(*args, **kwargs):
            out = FakeReceiver.register(self.fake, *args, **kwargs)
            if self.fake.writes and self.fake.writes[-1][0] == 3:
                self.fake.devices.pop(self.fake.writes[-1][1], None)
            return out
        self.fake.register = unpair_write
        self.m.unpair("/dev/hidraw0", 3)
        self.assertEqual([d["slot"] for d in self.m.receivers_info()[0]["devices"]], [1])

    def test_link_lost_on_device_hidraw(self):
        """Bytes reais: o M720 foi para o Bluetooth (01 41 04 625e40) e voltou ao receptor (01 41 04 a25e40)."""
        from mouse_options.daemon.manager import Session
        reapplied = []
        self.m._pool.submit = lambda fn, *args: reapplied.append(fn.__name__)

        class T:
            closed = False

        self.m.sessions["/dev/hidraw2"] = Session("/dev/hidraw2", T(), None, "1A2B3C4D", {}, [], None)
        self.m._slots["/dev/hidraw2"] = 1
        self.m._dispatch("/dev/hidraw2", Message(0x11, 1, 0x41, 0x04, bytes.fromhex("625e40")))
        self.assertNotIn("/dev/hidraw2", self.m.sessions)
        self.assertIn("/dev/hidraw2", self.m._parked)
        self.m._dispatch("/dev/hidraw2", Message(0x11, 1, 0x41, 0x04, bytes.fromhex("a25e40")))
        self.assertEqual(reapplied, ["_open"])   # voltou: abre de novo

    def test_bolt_refuses_pairing(self):
        self.rs.receiver = rx.Receiver(self.fake, 0xC548)
        with self.assertRaises(ValueError):
            self.m.start_pairing("/dev/hidraw0")


if __name__ == "__main__":
    unittest.main()
