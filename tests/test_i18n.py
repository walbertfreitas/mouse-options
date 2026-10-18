"""Garante que todo texto mostrado na interface tem tradução para o inglês."""
import ast
import os
import string
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mouse_options import actions, controls, i18n  # noqa: E402

PKG = os.path.join(os.path.dirname(__file__), "..", "mouse_options")


def _strings(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.IfExp):
        return _strings(node.body) + _strings(node.orelse)
    return []


def collect_ui_texts():
    texts = set()
    for name in os.listdir(PKG):
        if not name.endswith(".py") or name.startswith("i18n"):
            continue
        with open(os.path.join(PKG, name), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "T" and node.args:
                texts.update(_strings(node.args[0]))
    texts.update(a.label for a in actions.CATALOG)
    texts.update(name for _c, name in actions.CATEGORIES)
    texts.update(label for _k, label, _m in actions.GESTURE_DIRECTIONS)
    texts.update(v for v in actions.KEY_LABELS.values() if any(ch.isalpha() and not ch.isascii() for ch in v))  # só "Espaço" muda
    texts.update(label for label, _pos in controls.KNOWN.values())
    return texts


class Translations(unittest.TestCase):
    def test_every_ui_text_has_english(self):
        texts = collect_ui_texts()
        self.assertGreater(len(texts), 100)
        missing = sorted(t for t in texts if t not in i18n.EN)
        self.assertEqual(missing, [], "Textos sem tradução em i18n_en.EN")

    def test_placeholders_match(self):
        fields = lambda s: {f for _, f, _, _ in string.Formatter().parse(s) if f}  # noqa: E731
        for pt, en in i18n.EN.items():
            self.assertEqual(fields(pt), fields(en), pt)


if __name__ == "__main__":
    unittest.main()
