"""Generate a visually rich sample DXF (no external deps).

Writes a small floor-plan-like drawing with rooms, walls, doors, text and
circles so you can see something interesting when the renderer runs.

Usage:
    python generate_sample.py            # writes ./sample_floorplan.dxf
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable

OUT = Path(__file__).with_name("sample_floorplan.dxf")


def _hdr() -> list[str]:
    return [
        "0", "SECTION", "2", "HEADER",
        "9", "$ACADVER", "1", "AC1014",
        "9", "$INSBASE", "10", "0.0", "20", "0.0", "30", "0.0",
        "9", "$EXTMIN", "10", "0.0", "20", "0.0", "30", "0.0",
        "9", "$EXTMAX", "10", "200.0", "20", "120.0", "30", "0.0",
        "0", "ENDSEC",
    ]


def _tables() -> list[str]:
    layers = [
        ("WALLS", 1),       # red
        ("DOORS", 3),       # green
        ("WINDOWS", 5),     # blue
        ("FURNITURE", 6),   # magenta
        ("TEXT", 7),        # white/black
        ("DIM", 4),         # cyan
    ]
    out = ["0", "SECTION", "2", "TABLES",
           "0", "TABLE", "2", "LAYER", "70", str(len(layers))]
    for name, color in layers:
        out += ["0", "LAYER", "2", name, "70", "0",
                "62", str(color), "6", "CONTINUOUS"]
    out += ["0", "ENDTAB", "0", "ENDSEC"]
    return out


def _line(layer: str, x1: float, y1: float, x2: float, y2: float) -> list[str]:
    return ["0", "LINE", "8", layer,
            "10", f"{x1}", "20", f"{y1}", "30", "0",
            "11", f"{x2}", "21", f"{y2}", "31", "0"]


def _rect(layer: str, x: float, y: float, w: float, h: float) -> list[str]:
    return (_line(layer, x, y, x + w, y) +
            _line(layer, x + w, y, x + w, y + h) +
            _line(layer, x + w, y + h, x, y + h) +
            _line(layer, x, y + h, x, y))


def _circle(layer: str, cx: float, cy: float, r: float) -> list[str]:
    return ["0", "CIRCLE", "8", layer,
            "10", f"{cx}", "20", f"{cy}", "30", "0",
            "40", f"{r}"]


def _arc(layer: str, cx: float, cy: float, r: float,
         start_deg: float, end_deg: float) -> list[str]:
    return ["0", "ARC", "8", layer,
            "10", f"{cx}", "20", f"{cy}", "30", "0",
            "40", f"{r}",
            "50", f"{start_deg}", "51", f"{end_deg}"]


def _text(layer: str, x: float, y: float, height: float, value: str) -> list[str]:
    return ["0", "TEXT", "8", layer,
            "10", f"{x}", "20", f"{y}", "30", "0",
            "40", f"{height}",
            "1", value]


def _polyline(layer: str, pts: Iterable[tuple[float, float]], closed: bool = False) -> list[str]:
    pts = list(pts)
    flag = 1 if closed else 0
    out = ["0", "POLYLINE", "8", layer, "66", "1", "70", str(flag),
           "10", "0", "20", "0", "30", "0"]
    for x, y in pts:
        out += ["0", "VERTEX", "8", layer,
                "10", f"{x}", "20", f"{y}", "30", "0"]
    out += ["0", "SEQEND"]
    return out


def _door(x: float, y: float, width: float, swing: str = "right") -> list[str]:
    """Door symbol: a gap in the wall + an arc indicating swing."""
    out: list[str] = []
    if swing == "right":
        out += _arc("DOORS", x, y, width, 0, 90)
        out += _line("DOORS", x, y, x + width, y)
    else:
        out += _arc("DOORS", x + width, y, width, 90, 180)
        out += _line("DOORS", x, y, x + width, y)
    return out


def build_dxf() -> str:
    body: list[str] = ["0", "SECTION", "2", "ENTITIES"]

    # Outer walls (200 x 120 building)
    body += _rect("WALLS", 0, 0, 200, 120)
    # Inner walls dividing rooms
    body += _line("WALLS", 80, 0, 80, 70)       # vertical wall
    body += _line("WALLS", 80, 70, 200, 70)     # horizontal wall
    body += _line("WALLS", 140, 70, 140, 120)   # vertical upper wall
    body += _line("WALLS", 0, 50, 50, 50)       # entry hall divider
    body += _line("WALLS", 50, 0, 50, 50)

    # Doors
    body += _door(35, 50, 12, "right")
    body += _door(80, 30, 14, "left")
    body += _door(140, 70, 14, "right")
    body += _door(95, 70, 14, "left")

    # Windows (double line on outer walls)
    for x in (15, 110, 165):
        body += _line("WINDOWS", x, 119.5, x + 18, 119.5)
        body += _line("WINDOWS", x, 120.5, x + 18, 120.5)
    for y in (20, 90):
        body += _line("WINDOWS", -0.5, y, -0.5, y + 14)
        body += _line("WINDOWS",  0.5, y,  0.5, y + 14)

    # Furniture: kitchen counter (rect strip), dining table (circle), sofa (rounded poly)
    body += _rect("FURNITURE", 145, 75, 50, 8)            # kitchen counter
    body += _rect("FURNITURE", 145, 95, 50, 8)            # cabinets
    body += _circle("FURNITURE", 110, 95, 12)             # dining table
    for ang in range(0, 360, 60):
        cx = 110 + 18 * math.cos(math.radians(ang))
        cy = 95 + 18 * math.sin(math.radians(ang))
        body += _circle("FURNITURE", cx, cy, 4)           # chairs

    # Sofa as rounded rectangle approximation
    body += _polyline("FURNITURE",
                      [(10, 75), (60, 75), (60, 95), (10, 95)], closed=True)
    body += _rect("FURNITURE", 14, 79, 12, 12)
    body += _rect("FURNITURE", 30, 79, 12, 12)
    body += _rect("FURNITURE", 46, 79, 12, 12)

    # Bedroom bed
    body += _rect("FURNITURE", 90, 10, 40, 25)
    body += _rect("FURNITURE", 95, 12, 30, 6)             # pillows

    # Bathroom fixtures
    body += _circle("FURNITURE", 25, 25, 6)               # sink
    body += _rect("FURNITURE", 38, 12, 10, 18)            # bathtub

    # Labels
    body += _text("TEXT", 20, 100, 4.5, "LIVING ROOM")
    body += _text("TEXT", 95, 100, 4.5, "DINING")
    body += _text("TEXT", 155, 95, 4.5, "KITCHEN")
    body += _text("TEXT", 100, 20, 4.5, "BEDROOM")
    body += _text("TEXT", 8, 35, 3, "BATH")
    body += _text("TEXT", 55, 30, 3, "ENTRY")
    body += _text("TEXT", 155, 80, 3, "PANTRY")
    body += _text("TEXT", 80, -8, 5, "FLOOR PLAN  -  GENERATED SAMPLE")

    # Dimension lines (decorative, not real DXF DIMENSION entities)
    body += _line("DIM", 0, -4, 200, -4)
    body += _line("DIM", 0, -3, 0, -5)
    body += _line("DIM", 200, -3, 200, -5)
    body += _text("DIM", 95, -3.5, 2.5, "200")

    body += ["0", "ENDSEC", "0", "EOF"]

    parts = _hdr() + _tables() + body
    # join in DXF line-pair format
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    OUT.write_text(build_dxf())
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
