"""Testes da migração do Solaar e das garantias do catálogo de ações."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mouse_options import actions, direct, solaar_import as si  # noqa: E402
from mouse_options.devices import Control, MouseInfo  # noqa: E402
from mouse_options.store import ALL_APPS, Store  # noqa: E402


def m720():
    return MouseInfo(key="1A2B3C4D", name="M720 Triathlon Multi-Device Mouse", codename="M720 Triathlon",
                     kind="mouse", online=True,
                     controls=[Control(82, "Middle Button", True), Control(83, "Back Button", True),
                               Control(86, "Forward Button", True), Control(91, "Left Tilt", True),
                               Control(93, "Right Tilt", True), Control(208, "MultiPlatform Gesture Button", True)])


def store():
    return Store(os.path.join(tempfile.mkdtemp(), "config.json"))


class ImportFromSolaar(unittest.TestCase):
    def test_user_rules(self):
        rules = [
            [{"Device": "1A2B3C4D"}, {"Key": ["Middle Button", "pressed"]}, {"KeyPress": [["XF86_AudioPlay"], "click"]}],
            [{"Device": "1A2B3C4D"}, {"Process": "nemo"}, {"Key": ["Back Button", "pressed"]},
             {"MouseClick": ["button8", 1]}],
            [{"Key": ["Left Tilt", "pressed"]}, {"KeyPress": "Control_L"}],                      # forma curta
            [{"Key": ["Right Tilt", "pressed"]}, {"MouseScroll": [1, 0]}],
            [{"Key": ["Forward Button", "pressed"]}, {"Execute": ["sh", "-c", "notify-send oi"]}],
            [{"Device": "OUTRO"}, {"Key": ["Back Button", "pressed"]}, {"KeyPress": "a"}],         # outro mouse
            [{"Key": ["Back Button", "pressed"]}, {"Test": "thumb_wheel_up"}, {"KeyPress": "b"}],  # complexa
        ]
        st = store()
        self.assertEqual(si.import_existing(st, m720(), rules), 5)
        self.assertEqual(st.get("1A2B3C4D", ALL_APPS, "Middle Button"), {"id": "play_pause"})
        self.assertEqual(st.get("1A2B3C4D", "nemo", "Back Button"), {"id": "back"})
        self.assertEqual(st.get("1A2B3C4D", ALL_APPS, "Left Tilt"), {"id": "keys", "keys": ["Control_L"]})
        self.assertEqual(st.get("1A2B3C4D", ALL_APPS, "Right Tilt"), {"id": "scroll_right"})
        self.assertEqual(st.get("1A2B3C4D", ALL_APPS, "Forward Button"), {"id": "command", "cmd": "notify-send oi"})
        self.assertIsNone(st.get("1A2B3C4D", ALL_APPS, "Back Button"))

    def test_existing_config_wins(self):
        st = store()
        st.set("1A2B3C4D", ALL_APPS, "Middle Button", {"id": "copy"})
        rule = [{"Key": ["Middle Button", "pressed"]}, {"KeyPress": "XF86_AudioPlay"}]
        si.import_existing(st, m720(), [rule])
        self.assertEqual(st.get("1A2B3C4D", ALL_APPS, "Middle Button"), {"id": "copy"})

    def test_disable_solaar_autostart(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "autostart", "solaar.desktop")
        with mock.patch.object(si, "AUTOSTART_OVERRIDE", path), mock.patch.object(si, "solaar_running", lambda: []):
            self.assertTrue(si.disable_solaar())
            self.assertFalse(si.disable_solaar())   # já desligado
        self.assertIn("Hidden=true", open(path).read())


class Catalog(unittest.TestCase):
    NO_KEYS_ON_X11 = ("play_pause", "next_track", "prev_track", "stop", "volume_up", "volume_down", "mute",
                      "mic_mute", "overview", "show_desktop", "switch_windows", "switch_apps", "workspace_left",
                      "workspace_right", "maximize", "minimize", "close_window", "lock", "files", "calculator",
                      "brightness_up", "brightness_down")

    def test_direct_paths_exist(self):
        # tecla simulada no X11 faz o GNOME recarregar os atalhos e travar a tela: essas ações não simulam
        d = direct.Direct()
        with mock.patch.dict(os.environ, {"XDG_SESSION_TYPE": "x11"}):
            for aid in self.NO_KEYS_ON_X11:
                a = actions.BY_ID[aid]
                self.assertTrue(a.call and d.available(a.call), aid)

    def test_window_actions_use_keys_on_wayland(self):
        d = direct.Direct()
        with mock.patch.dict(os.environ, {"XDG_SESSION_TYPE": "wayland"}):
            self.assertFalse(d.available("show_desktop"))
            self.assertTrue(d.available("volume_up"))

    def test_every_action_can_run(self):
        for a in actions.CATALOG:
            self.assertTrue(a.call or a.click or a.scroll or a.keys, a.id)


if __name__ == "__main__":
    unittest.main()
