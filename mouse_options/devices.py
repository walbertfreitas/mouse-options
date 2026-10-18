"""Os mouses como a interface os vê (vindos do serviço mouse-optionsd)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Control:
    cid: int                 # número do controle no protocolo HID++ (ex.: 83 = Back Button)
    name: str                # nome do controle (o mesmo do Solaar, ex.: "Back Button")
    gestures: bool           # aceita "segurar e mover" (raw XY)


@dataclass
class MouseInfo:
    key: str                 # identificador estável (unitId)
    name: str
    codename: str
    kind: str
    online: bool
    unit_id: str = ""
    model_id: str = ""
    battery: int | None = None
    charging: bool = False
    controls: list[Control] = field(default_factory=list)
    pointer_speed: int | None = None        # 256 = 1.0×
    pointer_range: tuple[int, int] = (46, 511)
    invert_scroll: bool | None = None
    smooth_scroll: bool | None = None
    hosts: list[str] = field(default_factory=list)
    current_host: int | None = None
    dpi: int | None = None
    dpi_choices: list[int] = field(default_factory=list)
    smart_shift: int | None = None          # 1 (roda solta) … 50 (sempre com cliques)
    thumb_invert: bool | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "MouseInfo":
        return cls(key=d["key"], name=d.get("name", ""), codename=d.get("codename") or d.get("name", ""),
                   kind=d.get("kind", "mouse"), online=bool(d.get("online")), unit_id=d.get("unit_id", ""),
                   model_id=d.get("model_id", ""), battery=d.get("battery"), charging=bool(d.get("charging")),
                   controls=[Control(c["cid"], c["name"], bool(c.get("gestures"))) for c in d.get("controls", [])],
                   pointer_speed=d.get("pointer_speed"), pointer_range=tuple(d.get("pointer_range", (46, 511))),
                   invert_scroll=d.get("invert_scroll"), smooth_scroll=d.get("smooth_scroll"),
                   hosts=list(d.get("hosts", [])), current_host=d.get("current_host"),
                   dpi=d.get("dpi"), dpi_choices=list(d.get("dpi_choices") or []), smart_shift=d.get("smart_shift"),
                   thumb_invert=d.get("thumb_invert"))
