"""Hexagon map of English councils from the Open Innovations hexjson layout.

The layout is "odd-r": pointy-topped hexagons in rows, odd rows shifted half a
hexagon to the right, rows counted upwards (north). Centres are placed one unit
apart along a row and sqrt(3)/2 apart between rows, so hexagons tile exactly.
Vega-Lite draws the result with an identity projection, y flipped.
"""

import json
import math

from . import config

RADIUS = 1 / math.sqrt(3)


def centre(q, r):
    return q + 0.5 * (r & 1), r * math.sqrt(3) / 2


def hexagon(cx, cy, radius=RADIUS):
    angles = [math.radians(90 + 60 * k) for k in range(6)]  # anticlockwise from the top vertex
    ring = [[round(cx + radius * math.cos(a), 5), round(cy + radius * math.sin(a), 5)] for a in angles]
    return ring + [ring[0]]


def to_geojson(hexjson, country="E"):
    features = []
    for code, hexagon_info in sorted(hexjson["hexes"].items()):
        if not code.startswith(country):
            continue
        cx, cy = centre(hexagon_info["q"], hexagon_info["r"])
        features.append({
            "type": "Feature",
            "properties": {
                "lad": code,
                "name": hexagon_info["n"],
                "region": config.REGIONS.get(hexagon_info.get("region"), ""),
                "x": round(cx, 4),
                "y": round(cy, 4),
            },
            "geometry": {"type": "Polygon", "coordinates": [hexagon(cx, cy)]},
        })
    return {"type": "FeatureCollection", "features": features}


def write(hexjson_path, target):
    hexjson = json.loads(open(hexjson_path, encoding="utf-8").read())
    collection = to_geojson(hexjson)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(collection, handle, separators=(",", ":"))
    return collection
