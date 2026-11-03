# Map geometry

All files are GeoJSON in planar coordinates, drawn by Vega-Lite with an identity projection (y flipped).

| File | Contents | Built by |
| --- | --- | --- |
| `hex-lad-2025.geojson` | One hexagon per English council, unit spacing | `pipeline/hexmap.py`, from Open Innovations' hexjson (MIT), on every build |
| `regions-2025-hex.geojson` | The nine regions, dissolved from the hexagons | mapshaper, once |
| `lad-2025-map.geojson` | Council boundaries, British National Grid (EPSG:27700), metres | mapshaper, once |
| `regions-2025-map.geojson` | The nine regions, dissolved from the boundaries | mapshaper, once |
| `neighbours-2025.json` | For each council, the councils it borders or faces within 400 m (across a river) | shapely, once, from `lad-2025-map.geojson` |

Boundaries: ONS local authority districts (December 2024), generalised, as split per council in
[open-innovations/geography-bits](https://github.com/open-innovations/geography-bits) (`data/LAD24CD`, commit `b70d8fb`).
Barnsley (E08000016) and Sheffield (E08000019) take their April 2025 codes, E08000038 and E08000039; their
boundary change that month was small and is not redrawn. Source: Office for National Statistics, Open Government
Licence v3.0. Contains OS data © Crown copyright and database right 2026.

Commands (mapshaper 0.7.87), after merging the 296 English files into `lad24-england.geojson` with properties
`lad` (2025 code) and `region` (region code):

```
mapshaper -i lad24-england.geojson snap snap-interval=0.001 -proj EPSG:27700 -simplify 20% keep-shapes -clean \
          -o lad-2025-map.geojson format=geojson precision=10
mapshaper lad-2025-map.geojson -dissolve region -o regions-2025-map.geojson format=geojson precision=10
mapshaper hex-lad-2025.geojson -snap -dissolve region -o regions-2025-hex.geojson format=geojson precision=0.0001
```
