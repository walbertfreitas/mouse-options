"""Vigia de ligações Bluetooth travadas."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mouse_options.daemon import manager as mg  # noqa: E402
from mouse_options.daemon import watchdog as wd  # noqa: E402


class LinkWatchTest(unittest.TestCase):
    def test_silent_mouse_is_pinged_and_dropped_after_two_misses(self):
        w = wd.LinkWatch(started=0)
        self.assertTrue(w.should_ping(now=10, last_rx=5))
        w.pending = True
        self.assertFalse(w.should_ping(now=13, last_rx=5))   # um ping por vez
        self.assertFalse(w.answered(False))
        self.assertTrue(w.should_ping(now=16, last_rx=5))
        self.assertTrue(w.answered(False))
        self.assertFalse(w.active(now=17))                   # desistiu: não vigia mais

    def test_answer_or_traffic_resets_misses(self):
        w = wd.LinkWatch(started=0)
        w.answered(False)
        w.answered(True)
        self.assertFalse(w.answered(False))
        self.assertFalse(w.should_ping(now=20, last_rx=19))  # mouse em uso: não pinga
        self.assertEqual(w.misses, 0)

    def test_only_first_minutes(self):
        w = wd.LinkWatch(started=100)
        self.assertTrue(w.active(now=100 + wd.WINDOW - 1))
        self.assertFalse(w.active(now=100 + wd.WINDOW))


class Hid:
    def __init__(self, props):
        self.properties = props


class Dev:
    def __init__(self, props):
        self.hid = Hid(props)

    def find_parent(self, _subsystem):
        return self.hid


class ManagerWatchTest(unittest.TestCase):
    def setUp(self):
        from mouse_options.daemon.state import State
        d = tempfile.mkdtemp()
        self.m = mg.Manager(None, None, lambda: None, lambda k, c: None, store_path=os.path.join(d, "c.json"),
                            state=State(os.path.join(d, "devices.json")))
        self.m._pool.submit = lambda fn, *args: fn(*args)

    def test_bt_address(self):
        self.assertEqual(mg.Manager._bt_address(Dev({"HID_ID": "0005:0000046D:0000B015",
                                                     "HID_UNIQ": "aa:bb:cc:dd:ee:01"})), "AA:BB:CC:DD:EE:01")
        self.assertIsNone(mg.Manager._bt_address(Dev({"HID_ID": "0003:0000046D:0000C52B", "HID_UNIQ": ""})))
        self.assertIsNone(mg.Manager._bt_address(Dev({"HID_ID": "0005:0000046D:0000B015", "HID_UNIQ": ""})))

    def run_watch(self, responds: bool, last_rx: float = 0.0):
        class T:
            closed = False

        class D:
            pings = 0

            def ping(self, timeout):
                D.pings += 1
                return (4, 5) if responds else None

        t = T()
        t.last_rx = last_rx
        s = mg.Session("/dev/hidraw1", t, D(), "1A2B3C4D", {}, [], None)
        self.m.sessions[s.path] = s
        self.m._bt[s.path] = "AA:BB:CC:DD:EE:01"
        ticks, dropped = [], []
        with mock.patch.object(mg.GLib, "timeout_add", lambda _ms, fn: ticks.append(fn)), \
                mock.patch.object(mg.GLib, "idle_add", lambda fn: fn()), \
                mock.patch.object(mg.time, "monotonic", lambda: 100.0), \
                mock.patch.object(mg, "bluez_disconnect", dropped.append):
            self.m._watch(s)
            results = [ticks[0]() for _ in range(5)]
        return D.pings, dropped, results

    def test_stalled_link_is_dropped(self):
        pings, dropped, results = self.run_watch(responds=False)
        self.assertEqual(pings, 2)
        self.assertEqual(dropped, ["AA:BB:CC:DD:EE:01"])
        self.assertEqual(results[-1], False)                  # parou de vigiar

    def test_healthy_link_is_left_alone(self):
        pings, dropped, results = self.run_watch(responds=True)
        self.assertEqual((pings, dropped), (5, []))
        self.assertTrue(all(results))

    def test_busy_mouse_is_not_pinged(self):
        pings, dropped, _ = self.run_watch(responds=False, last_rx=99.0)
        self.assertEqual((pings, dropped), (0, []))

    def test_not_bluetooth_is_not_watched(self):
        s = mg.Session("/dev/hidraw2", None, None, "X", {}, [], None)
        with mock.patch.object(mg.GLib, "timeout_add") as timeout_add:
            self.m._watch(s)
        timeout_add.assert_not_called()


if __name__ == "__main__":
    unittest.main()
