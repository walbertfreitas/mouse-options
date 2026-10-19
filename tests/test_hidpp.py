"""Testes da camada HID++ e do motor de botões (com o aparelho simulado)."""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from fake_hidpp import FakeMouse  # noqa: E402
from mouse_options.daemon import engine as en  # noqa: E402
from mouse_options.hidpp import device as hd  # noqa: E402
from mouse_options.store import ALL_APPS  # noqa: E402


class DeviceTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeMouse()
        self.dev = hd.Device(self.fake)

    def test_identity_matches_solaar(self):
        self.assertEqual(self.dev.ping(), (4, 5))
        ids = self.dev.ids()
        self.assertEqual((ids.unit_id, ids.model_id), ("1A2B3C4D", "B015405E0000"))
        self.assertEqual(ids.transports, {"btleid": "B015", "wpid": "405E"})
        self.assertEqual(self.dev.name(), "M720 Triathlon Multi-Device Mouse")
        self.assertEqual(self.dev.kind(), "mouse")

    def test_controls(self):
        controls = {c.name: c for c in self.dev.controls()}
        self.assertFalse(controls["Left Button"].divertable)
        self.assertTrue(controls["Back Button"].divertable and controls["Back Button"].raw_xy)
        self.assertTrue(controls["Virtual Gesture Button"].virtual)

    def test_divert_and_raw_xy(self):
        self.dev.set_reporting(0x53, True)
        self.assertEqual(self.dev.reporting(0x53), (True, False))
        self.dev.set_reporting(0xD0, True, raw_xy=True)
        self.assertEqual(self.dev.reporting(0xD0), (True, True))
        self.dev.set_reporting(0xD0, False)
        self.assertEqual(self.dev.reporting(0xD0), (False, False))

    def test_settings(self):
        self.assertEqual(self.dev.battery(), hd.Battery(20))
        self.assertEqual(self.dev.pointer_speed(), 283)
        self.dev.set_pointer_speed(300)
        self.assertEqual(self.dev.pointer_speed(), 300)
        self.dev.set_wheel_mode(invert=True)
        self.assertEqual(self.dev.wheel_mode(), hd.WheelEvent(invert=True, hires=True))
        self.assertEqual(self.dev.hosts(), (3, 0))
        self.assertEqual(self.dev.host_names(3), ["Laptop", "Phone", "Desktop"])

    def test_dpi_smartshift_thumbwheel(self):
        mx = FakeMouse(features=FakeMouse().features + [hd.ADJUSTABLE_DPI, hd.SMART_SHIFT_ENHANCED, hd.THUMB_WHEEL])
        dev = hd.Device(mx)
        choices = dev.dpi_choices()
        self.assertEqual((choices[0], choices[1], choices[-1], len(choices)), (200, 250, 4000, 77))
        self.assertEqual(dev.dpi(), 1000)
        dev.set_dpi(1600)
        self.assertEqual(dev.dpi(), 1600)
        self.assertEqual(dev.smart_shift(), 10)
        dev.set_smart_shift(50)                        # sempre com cliques
        self.assertEqual(mx.ratchet[1], 255)
        self.assertEqual(dev.smart_shift(), 50)
        mx.ratchet = (1, 10, 10)                       # roda solta
        self.assertEqual(dev.smart_shift(), 1)
        self.assertFalse(dev.thumb_invert())
        dev.set_thumb_invert(True)
        self.assertTrue(dev.thumb_invert())
        list_dev = hd.Device(FakeMouse(features=[hd.ROOT, hd.FEATURE_SET, hd.ADJUSTABLE_DPI]))
        list_dev.transport.dpi_list = struct.pack("!HHHH", 400, 800, 1600, 3200)
        self.assertEqual(list_dev.dpi_choices(), [400, 800, 1600, 3200])

    def test_missing_feature(self):
        dev = hd.Device(FakeMouse(features=[hd.ROOT, hd.FEATURE_SET, hd.DEVICE_NAME]))
        self.assertIsNone(dev.pointer_speed())
        self.assertIsNone(dev.battery())
        self.assertIsNone(dev.dpi_choices())
        self.assertIsNone(dev.smart_shift())
        self.assertIsNone(dev.thumb_invert())
        self.assertEqual(dev.controls(), [])

    def test_notifications(self):
        for fid in (hd.REPROG_CONTROLS_V4, hd.BATTERY_STATUS, hd.WIRELESS_DEVICE_STATUS):
            self.dev.has(fid)
        n = self.fake.notification
        self.assertEqual(self.dev.parse(n(hd.REPROG_CONTROLS_V4, 0, struct.pack("!4H", 0x53, 0xD0, 0, 0))),
                         hd.ButtonsEvent(frozenset({0x53, 0xD0})))
        self.assertEqual(self.dev.parse(n(hd.REPROG_CONTROLS_V4, 1, struct.pack("!hh", -40, 7))), hd.MoveEvent(-40, 7))
        self.assertEqual(self.dev.parse(n(hd.BATTERY_STATUS, 0, bytes([55, 50, 1]))),
                         hd.BatteryEvent(hd.Battery(55, charging=True)))
        self.assertIsInstance(self.dev.parse(n(hd.WIRELESS_DEVICE_STATUS, 0, bytes([1, 1, 0]))), hd.ReconfigureEvent)
        self.assertIsNone(self.dev.parse(n(hd.BATTERY_STATUS, 0, bytes([55]), index=2)))  # outro aparelho


class FakeFocus:
    def __init__(self, names=()):
        self.current = list(names)

    def names(self):
        return list(self.current)

    matches = staticmethod(lambda names, app: any(n.startswith(app) for n in names))


CONFIG = {"apps": {
    ALL_APPS: {"Back Button": {"id": "volume_down"}, "Middle Button": {"id": "play_pause"},
               "MultiPlatform Gesture Button": {"id": "gestures", "click": {"id": "overview"},
                                                "left": {"id": "workspace_left"}}},
    "nemo": {"Back Button": {"id": "back"}, "Forward Button": {"id": "copy"}},
}}
NAMES = {0x52: "Middle Button", 0x53: "Back Button", 0x56: "Forward Button", 0x5B: "Left Tilt",
         0xD0: "MultiPlatform Gesture Button"}


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.ran = []
        self.focus = FakeFocus(["Brave-browser", "brave"])
        self.engine = en.ButtonEngine(lambda spec, control: self.ran.append((control, spec["id"])), self.focus)
        self.engine.configure(CONFIG, NAMES)

    def press(self, *cids):
        self.engine.handle(hd.ButtonsEvent(frozenset(cids)))

    def test_modes(self):
        self.assertEqual(self.engine.modes, {"Middle Button": en.DIVERT, "Back Button": en.DIVERT,
                                             "Forward Button": en.DIVERT, "Left Tilt": en.REGULAR,
                                             "MultiPlatform Gesture Button": en.GESTURES})

    def test_general_profile_and_app_profile(self):
        self.press(0x53)
        self.press()
        self.focus.current = ["Nemo", "nemo"]
        self.press(0x53)
        self.press()
        self.press(0x56)   # só o Nemo muda o Forward: nos outros apps ele reproduz a função original
        self.press()
        self.focus.current = ["code"]
        self.press(0x56)
        self.assertEqual(self.ran, [("Back Button", "volume_down"), ("Back Button", "back"),
                                    ("Forward Button", "copy"), ("Forward Button", "default")])

    def test_acts_once_per_press(self):
        self.press(0x53)
        self.press(0x53, 0x52)   # segurando o voltar e apertando o do meio
        self.press()
        self.assertEqual(self.ran, [("Back Button", "volume_down"), ("Middle Button", "play_pause")])

    def test_gestures(self):
        self.press(0xD0)
        self.press()
        self.press(0xD0)
        for _ in range(10):
            self.engine.handle(hd.MoveEvent(-30, 4))   # para a esquerda, meio na diagonal
        self.press()
        self.press(0xD0)
        self.engine.handle(hd.MoveEvent(0, -400))      # para cima: não configurado
        self.press()
        self.assertEqual(self.ran, [("MultiPlatform Gesture Button", "overview"),
                                    ("MultiPlatform Gesture Button", "workspace_left")])

    def test_app_gestures_keep_general_click(self):
        # a pessoa pôs "voltar" no gesto para a esquerda só no Brave; o clique continua na Visão geral
        config = {"apps": {ALL_APPS: {"MultiPlatform Gesture Button": {"id": "overview"}},
                           "brave-browser": {"MultiPlatform Gesture Button": {"id": "gestures",
                                                                              "left": {"id": "back"}}}}}
        self.focus.current = ["brave-browser"]
        self.engine.configure(config, NAMES)
        self.assertEqual(self.engine.modes["MultiPlatform Gesture Button"], en.GESTURES)

        def gesture(dx):
            self.press(0xD0)
            self.engine.handle(hd.MoveEvent(dx, 0))
            self.press()
        gesture(0)
        gesture(-400)
        self.focus.current = ["code"]
        gesture(0)
        gesture(-400)      # fora do Brave o gesto não existe
        self.assertEqual([spec for _c, spec in self.ran], ["overview", "back", "overview"])

    def test_direction(self):
        self.assertEqual(en.gesture_direction(0.5, -1), "click")
        self.assertEqual(en.gesture_direction(3, -1), "right")
        self.assertEqual(en.gesture_direction(-1, 4), "down")


class RunnerTest(unittest.TestCase):
    def test_prefers_direct_and_falls_back_to_keys(self):
        from mouse_options.daemon.runner import Runner

        class FakeDirect:
            def __init__(self):
                self.calls = []

            def available(self, name):
                return name == "volume_down"

            def shell(self, name):
                return name == "maximize"

            def run(self, name):
                self.calls.append(name)

        class FakeInput:
            def __init__(self):
                self.events = []

            def keys(self, keys):
                self.events.append(("keys", keys))
                return True

            def click(self, button, count=1):
                self.events.append(("click", button))
                return True

            def scroll(self, dx, dy):
                self.events.append(("scroll", dx, dy))

            def close(self):
                pass

        direct, vin = FakeDirect(), FakeInput()
        r = Runner(lambda: vin, direct)
        r.run({"id": "volume_down"}, "Back Button")
        r.run({"id": "copy"}, "Left Tilt")
        r.run({"id": "default"}, "Back Button")
        r.run({"id": "default"}, "Right Tilt")
        r.run({"id": "keys", "keys": ["Control_L", "t"]}, "Middle Button")
        r.run({"id": "maximize"}, "Middle Button")   # a extensão faz: nada de teclas
        r.close()
        self.assertEqual(direct.calls, ["volume_down"])
        self.assertEqual(vin.events, [("keys", ["Control_L", "c"]), ("click", "button8"), ("scroll", 1, 0),
                                      ("keys", ["Control_L", "t"])])


class KeysymNameTest(unittest.TestCase):
    def test_names_match_what_the_service_simulates(self):
        """Os nomes gravados pela tela de atalho precisam ser os do xkb (sem depender do Solaar)."""
        from mouse_options.dialogs import keysym_name
        self.assertEqual([keysym_name(k) for k in (0xFF55, 0xFFFF, 0xFF1B, 0x61, 0xFFC2, 0x1008FF14)],
                         ["Prior", "Delete", "Escape", "a", "F5", "XF86AudioPlay"])
        self.assertIsNone(keysym_name(0))


class KeymapTest(unittest.TestCase):
    def test_layouts(self):
        try:
            from evdev import ecodes as e

            from mouse_options.daemon.vinput import Keymap
        except Exception as ex:  # noqa: BLE001
            self.skipTest(str(ex))
        us, br = Keymap("us"), Keymap("br")
        self.assertEqual(us.lookup("plus"), (e.KEY_EQUAL, (e.KEY_LEFTSHIFT,)))
        self.assertEqual(us.lookup("slash"), (e.KEY_SLASH, ()))
        self.assertEqual(br.lookup("ccedilla"), (e.KEY_SEMICOLON, ()))
        self.assertEqual(br.lookup("XF86_AudioPlay"), (e.KEY_PLAYPAUSE, ()))
        self.assertIsNone(us.lookup("nao_existe"))


if __name__ == "__main__":
    unittest.main()


class FastReconnectTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        from mouse_options.daemon.manager import Manager
        from mouse_options.daemon.state import State
        d = tempfile.mkdtemp()
        self.manager = Manager(None, None, lambda: None, lambda k, c: None, store_path=os.path.join(d, "c.json"),
                               state=State(os.path.join(d, "devices.json")))

    def identify(self, fake):
        dev = hd.Device(fake)
        dev.ping()
        before = len(fake.log)
        result = self.manager._identify(dev, dev.ids())
        return result, len(fake.log) - before

    def test_second_connection_uses_cache(self):
        fake = FakeMouse()
        (name, kind, controls, cache), first = self.identify(fake)
        self.assertEqual((name, kind, len(controls)), ("M720 Triathlon Multi-Device Mouse", "mouse", 9))
        self.manager.state.entry("1A2B3C4D")["cache"] = cache
        (_n, _k, cached_controls, new_cache), second = self.identify(FakeMouse())
        self.assertIsNone(new_cache)
        self.assertEqual(cached_controls, controls)
        self.assertLessEqual(second, 3)   # identificação (2) + conferência da tabela (1)
        self.assertGreater(first, 15)

    def test_one_cache_per_route(self):
        """Pelo receptor o M720 declara outros recursos: o cache do Bluetooth não pode ser descartado."""
        from mouse_options.daemon.manager import cache_name
        (_n, _k, _c, bt_cache), _ = self.identify(FakeMouse())
        self.manager.state.entry("1A2B3C4D")[cache_name("direct")] = bt_cache
        via_receiver = FakeMouse(features=FakeMouse().features + [hd.ADJUSTABLE_DPI])
        dev = hd.Device(via_receiver)
        dev.ping()
        *_, rx_cache = self.manager._identify(dev, dev.ids(), "receiver")
        self.assertIsNotNone(rx_cache)                              # 1ª vez pelo receptor: descobre
        self.manager.state.entry("1A2B3C4D")[cache_name("receiver")] = rx_cache
        *_, again = self.identify(FakeMouse())[0]                   # de volta ao Bluetooth
        self.assertIsNone(again)                                    # o cache dele continua valendo

    def test_changed_device_is_discovered_again(self):
        (_n, _k, _c, cache), _ = self.identify(FakeMouse())
        self.manager.state.entry("1A2B3C4D")["cache"] = cache
        changed = FakeMouse(features=[hd.ROOT, hd.FEATURE_SET, hd.DEVICE_FW_VERSION, hd.DEVICE_NAME,
                                      hd.REPROG_CONTROLS_V4, hd.BATTERY_STATUS])
        (_n, _k, controls, new_cache), _ = self.identify(changed)
        self.assertIsNotNone(new_cache)
        self.assertEqual(new_cache["feature_count"], 5)
        self.assertEqual(len(controls), 9)


class ReceiverTest(unittest.TestCase):
    def manager(self):
        import tempfile

        from mouse_options.daemon.manager import Manager
        from mouse_options.daemon.state import State
        d = tempfile.mkdtemp()
        changed = []
        m = Manager(None, None, lambda: changed.append(1), lambda k, c: None, store_path=os.path.join(d, "c.json"),
                    state=State(os.path.join(d, "devices.json")))
        return m, changed

    def test_slot_from_hid_phys(self):
        from mouse_options.daemon.manager import Manager

        class Hid:
            def __init__(self, phys):
                self.properties = {"HID_PHYS": phys}

        class Dev:
            def __init__(self, phys):
                self.hid = Hid(phys)

            def find_parent(self, _subsystem):
                return self.hid

        self.assertEqual(Manager._receiver_slot(Dev("usb-0000:00:14.0-4/input2:1")), 1)
        self.assertIsNone(Manager._receiver_slot(Dev("usb-0000:00:14.0-4/input2")))
        self.assertIsNone(Manager._receiver_slot(Dev("f4:c8:8a:f8:0d:8f")))   # Bluetooth

    def test_receiver_session_parks_and_comes_back(self):
        from mouse_options.daemon.manager import Session
        m, changed = self.manager()

        class T:
            closed = False

        s = Session("/dev/hidraw2", T(), None, "1A2B3C4D", {}, [], None)
        m.sessions["/dev/hidraw2"] = s
        m._slots["/dev/hidraw2"] = 1
        m._link_changed("/dev/hidraw2", online=False)          # foi para o Bluetooth
        self.assertNotIn("/dev/hidraw2", m.sessions)
        self.assertIs(m._parked["/dev/hidraw2"], s.transport)
        self.assertEqual(changed, [1])
        opened = []
        m._pool.submit = lambda fn, *args: opened.append(args)   # não abre de verdade no teste
        m._link_changed("/dev/hidraw2", online=True)            # voltou ao receptor
        self.assertEqual(opened, [("/dev/hidraw2", s.transport)])
        self.assertNotIn("/dev/hidraw2", m._parked)
