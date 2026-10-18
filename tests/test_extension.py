import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCRIPT = """
import sys
from gi.repository import Gio
from mouse_options.daemon import extension as ex
from mouse_options.daemon.api import EXTENSION_UUID as U
s = Gio.Settings.new("org.gnome.shell")
s.set_strv("disabled-extensions", [U])
first = ex.ensure_enabled(sys.argv[1])
s.set_strv("enabled-extensions", [])          # a pessoa desligou depois
second = ex.ensure_enabled(sys.argv[1])
print(first, second, U in s.get_strv("disabled-extensions"), s.get_strv("enabled-extensions"))
"""


class ExtensionTest(unittest.TestCase):
    def test_enables_once(self):
        from gi.repository import Gio
        source = Gio.SettingsSchemaSource.get_default()
        if source is None or source.lookup("org.gnome.shell", True) is None:
            self.skipTest("sem o GNOME Shell")
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, GSETTINGS_BACKEND="memory", PYTHONPATH=ROOT,
                       DBUS_SESSION_BUS_ADDRESS="unix:path=" + os.path.join(tmp, "nobus"))
            out = subprocess.run([sys.executable, "-c", SCRIPT, os.path.join(tmp, "marker")], env=env,
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(out.stdout.strip(), "True False False []", out.stderr)


if __name__ == "__main__":
    unittest.main()
