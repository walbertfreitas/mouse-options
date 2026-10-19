import importlib.machinery
import importlib.util
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_loader = importlib.machinery.SourceFileLoader("bt_repair", os.path.join(ROOT, "packaging", "bt-repair.py"))
_spec = importlib.util.spec_from_loader("bt_repair", _loader)
br = importlib.util.module_from_spec(_spec)
_loader.exec_module(br)

ADAPTER = "AA:BB:CC:DD:EE:00"
MOUSE = "AA:BB:CC:DD:EE:01"
HID = "0005:046D:B015.0004"
BROKEN = (f"3,1500,9000000,-;logitech-hidpp-device {HID}: item fetching failed at offset 43/44\n"
          f" SUBSYSTEM=hid\n DEVICE=+hid:{HID}\n")


class BtRepairTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sysfs = os.path.join(self.tmp.name, "sys")
        self.storage = os.path.join(self.tmp.name, "bt")
        os.makedirs(os.path.join(self.storage, ADAPTER, "cache"))
        os.makedirs(os.path.join(self.storage, ADAPTER, MOUSE))
        with open(os.path.join(self.storage, ADAPTER, MOUSE, "info"), "w") as f:
            f.write("[General]\nName=M720 Triathlon\n")
        self.cache = os.path.join(self.storage, ADAPTER, "cache", MOUSE)
        open(self.cache, "w").close()
        self.calls = []
        self.now = 1000.0

    def tearDown(self):
        self.tmp.cleanup()

    def uevent(self, phys=ADAPTER.lower(), uniq=MOUSE.lower(), name="M720 Triathlon"):
        os.makedirs(os.path.join(self.sysfs, HID), exist_ok=True)
        with open(os.path.join(self.sysfs, HID, "uevent"), "w") as f:
            f.write(f"DRIVER=logitech-hidpp-device\nHID_ID=0005:0000046D:0000B015\n"
                    f"HID_NAME={name}\nHID_PHYS={phys}\nHID_UNIQ={uniq}\n")

    def systemctl(self, action):
        # o cache tem de ser apagado com o BlueZ parado
        self.calls.append((action, os.path.exists(self.cache)))

    def repairer(self):
        return br.Repairer(self.sysfs, self.storage, self.systemctl, clock=lambda: self.now)

    def test_parses_only_broken_bluetooth_hid(self):
        self.assertEqual(br.broken_hid_id(BROKEN), HID)
        self.assertIsNone(br.broken_hid_id(
            "3,1,1,-;hid-generic 0003:046D:C52B.0001: item fetching failed at offset 1/2\n"))
        self.assertIsNone(br.broken_hid_id(
            f"6,2,2,-;logitech-hidpp-device {HID}: HID++ 4.5 device connected.\n"))
        self.assertEqual(br.broken_hid_id(
            f"3,3,3,-;hid-generic {HID}: unbalanced collection at end of report description\n"), HID)

    def test_repairs_by_address(self):
        self.uevent()
        self.assertEqual(self.repairer().handle(BROKEN), (ADAPTER, MOUSE))
        self.assertFalse(os.path.exists(self.cache))
        self.assertEqual(self.calls, [("stop", True), ("start", False)])
        self.assertTrue(os.path.exists(os.path.join(self.storage, ADAPTER, MOUSE, "info")))  # pareamento fica

    def test_falls_back_to_name_when_uniq_missing(self):
        self.uevent(uniq="")
        self.assertEqual(self.repairer().handle(BROKEN), (ADAPTER, MOUSE))

    def test_unknown_device_is_left_alone(self):
        self.uevent(uniq="", name="Outro Aparelho")
        self.assertIsNone(self.repairer().handle(BROKEN))
        self.assertTrue(os.path.exists(self.cache))
        self.assertEqual(self.calls, [])

    def test_no_cache_means_no_restart(self):
        self.uevent()
        os.remove(self.cache)
        self.assertIsNone(self.repairer().handle(BROKEN))
        self.assertEqual(self.calls, [])

    def test_cooldown(self):
        self.uevent()
        r = self.repairer()
        self.assertIsNotNone(r.handle(BROKEN))
        open(self.cache, "w").close()
        self.now += 60
        self.assertIsNone(r.handle(BROKEN))          # não entra em loop
        self.now += br.COOLDOWN
        self.assertIsNotNone(r.handle(BROKEN))


if __name__ == "__main__":
    unittest.main()
