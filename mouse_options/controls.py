"""Nomes amigáveis e posição no desenho de cada botão conhecido dos mouses Logitech.

As posições são relativas ao desenho do mouse (0..1 na horizontal e na vertical, vista de cima,
com o lado do polegar à esquerda). Botões desconhecidos aparecem só na lista, sem ponto no desenho.
"""
from __future__ import annotations

from .i18n import T

# nome no Solaar → (nome em português, (x, y) no desenho ou None)
KNOWN = {
    "Middle Button": ("Botão do meio (clique na roda)", (0.50, 0.20)),
    "Left Tilt": ("Inclinar a roda para a esquerda", (0.33, 0.21)),
    "Right Tilt": ("Inclinar a roda para a direita", (0.67, 0.21)),
    "Left Scroll Button": ("Inclinar a roda para a esquerda", (0.33, 0.21)),
    "Right Scroll Button": ("Inclinar a roda para a direita", (0.67, 0.21)),
    "Back Button": ("Botão voltar (lateral)", (0.075, 0.56)),
    "Forward Button": ("Botão avançar (lateral)", (0.085, 0.44)),
    "MultiPlatform Gesture Button": ("Botão de gestos (polegar)", (0.10, 0.70)),
    "Gesture Button": ("Botão de gestos (polegar)", (0.10, 0.70)),
    "Mouse Gesture Button": ("Botão de gestos (polegar)", (0.10, 0.70)),
    "Gesture Button Navigation": ("Botão de gestos (polegar)", (0.10, 0.70)),
    "Smart Shift": ("Botão de troca da roda (SmartShift)", (0.50, 0.34)),
    "DPI Switch": ("Botão de DPI", (0.50, 0.34)),
    "DPI Change": ("Botão de DPI", (0.50, 0.34)),
    "Top Button": ("Botão superior", (0.50, 0.34)),
    "App Switch Gesture": ("Gesto de troca de apps", None),
}


def label(name: str) -> str:
    known = KNOWN.get(name)
    return T(known[0]) if known else name


def position(name: str) -> tuple[float, float] | None:
    known = KNOWN.get(name)
    return known[1] if known else None
