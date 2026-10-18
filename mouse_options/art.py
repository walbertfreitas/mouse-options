"""Imagens dos mouses e onde fica cada botão nelas.

Cada botão tem: o ponto sobre a imagem (x, y relativos à imagem, 0..1), o lado em que a etiqueta
numerada aparece ("L" ou "R") e a altura da etiqueta (0..1). Mouses sem imagem própria usam o
desenho genérico, com as posições de controls.py.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

IMAGES = os.path.join(os.path.dirname(__file__), "images")


@dataclass
class Art:
    image: str                       # arquivo PNG com fundo transparente
    callouts: dict = field(default_factory=dict)  # controle → ((x, y), lado, altura da etiqueta)

    @property
    def path(self) -> str:
        return os.path.join(IMAGES, self.image)


# Imagem do M720: ilustração gerada pelo autor do projeto (sem marcas), recortada do fundo.
M720 = Art("m720.png", {
    "Left Tilt": ((0.567, 0.176), "L", 0.10),
    "Forward Button": ((0.249, 0.389), "L", 0.33),
    "Back Button": ((0.264, 0.512), "L", 0.50),
    "MultiPlatform Gesture Button": ((0.089, 0.464), "L", 0.42),  # risquinho no apoio do polegar
    "Middle Button": ((0.628, 0.176), "R", 0.10),
    "Right Tilt": ((0.693, 0.190), "R", 0.24),
})

MODELS = [("M720", M720)]


def for_mouse(name: str) -> Art | None:
    for key, art in MODELS:
        if key.lower() in (name or "").lower() and os.path.exists(art.path):
            return art
    return None
