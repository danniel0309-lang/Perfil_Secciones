"""Generate a synthetic survey CSV for trying the program.

    python examples/generate_sample.py  [salida.csv]

Road of 400 m with a station every 20 m, seven points per section
(PAR, SAR, BV, EJE, BV, SAR, PAR, 2 m apart), sags in the longitudinal
profile and a stretch with one-way cross-slope, so the
lowest point of the section moves from the edges to one side.
"""

from __future__ import annotations

import csv
import math
import random
import sys
from pathlib import Path

HEADER = ["Abscisa", "PAR", "SAR", "BV", "EJE", "BV", "SAR", "PAR"]
OFFSETS = [-6, -4, -2, 0, 2, 4, 6]


def axis_elevation(x: float) -> float:
    """Centerline elevation (m) at chainage x."""
    return 2540.000 - 0.012 * x + 0.9 * math.sin(2 * math.pi * x / 170.0) + 0.0015 * (x / 20) ** 2


def cross_slope(x: float) -> float:
    """Pavement cross-slope (m/m): crown 2 %, one-way (superelevation) 220..320 m."""
    if 220 <= x <= 320:
        return -0.03
    return 0.02


def build_rows(seed: int = 7) -> list:
    rnd = random.Random(seed)
    rows = []
    for k in range(21):
        x = 20.0 * k
        z0 = axis_elevation(x)
        s = cross_slope(x)
        vals = []
        for off in OFFSETS:
            a = abs(off)
            if s > 0:                       # crown: both sides fall away from the axis
                drop = s * min(a, 2) + 0.04 * max(min(a, 4) - 2, 0) + 0.08 * max(a - 4, 0)
                z = z0 - drop
            else:                           # one-way slope: falls towards the left
                z = z0 - s * off
            z += rnd.uniform(-0.003, 0.003)
            vals.append(round(z, 3))
        vals[3] = round(z0 + rnd.uniform(-0.002, 0.002), 3)
        rows.append([f"K0+{int(x):03d}"] + vals)
    return rows


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("secciones_ejemplo.csv")
    rows = build_rows()
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerows(rows)
    print(f"wrote {out} ({len(rows)} sections)")


if __name__ == "__main__":
    main()
