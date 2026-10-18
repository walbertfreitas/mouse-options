"""Tradução da interface (português ↔ inglês).

O texto em português é a chave; `T()` devolve a versão do idioma atual e aplica
`str.format` quando há parâmetros. Para incluir um idioma novo, adicione-o em LANGS e
crie um dicionário como EN.
"""
from __future__ import annotations

import os

LANGS = {"pt": "Português", "en": "English"}

from .i18n_en import EN  # traduções para o inglês (texto em português → inglês)

_TABLES = {"en": EN}
_lang = "pt"


def default_language() -> str:
    """Idioma do sistema: português se for pt_*, senão inglês."""
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value:
            return "pt" if value.lower().startswith("pt") else "en"
    return "en"


def set_language(code: str) -> None:
    global _lang
    _lang = code if code in LANGS else "pt"


def language() -> str:
    return _lang


def T(text: str, **kw) -> str:
    out = _TABLES.get(_lang, {}).get(text, text)
    return out.format(**kw) if kw else out
