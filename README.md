# jakobbilan.github.io

Personal website: plain HTML and CSS, served by GitHub Pages.

## Project page (PP434): council tax and home values

`project.html` compares what each home in England pays in council tax with what it is worth today.
Every number on the page is rebuilt from official open data by the code in `pipeline/`, which a
GitHub Actions workflow runs every day at 04:00 London time; a run that finds no new data changes no file and makes no commit.

### Layout

| Path | Contents |
| --- | --- |
| `project.html` | The page |
| `project/charts/` | One Vega-Lite specification per chart, and `theme.json`, the shared chart style |
| `project/data/` | Tables the charts read; written by the pipeline, not edited by hand |
| `project/geo/` | Hexagon map of English councils, GeoJSON |
| `project/css/`, `project/js/` | Page style; script that loads the charts and wires their controls |
| `project/vendor/`, `project/fonts/` | Pinned Vega 5.33.1, Vega-Lite 5.23.0, vega-embed 6.29.0 and the Inter typeface, with licences |
| `pipeline/` | Python: finds and downloads the sources, builds `project/data`, checks the result |
| `.github/workflows/update-data.yml` | Scheduled rebuild; can also be started by hand from the Actions tab |

### Rebuild locally

```
pip install -r requirements.txt
python -m pytest pipeline/tests    # offline, on synthetic files laid out like the real ones
python -m pipeline.build           # first run downloads about 600 MB into pipeline/cache
python -m pipeline.build --refresh # download every source again
```

### How each source is found

| Source | Access |
| --- | --- |
| Valuation Office, Council Tax: stock of properties (CTSOP1.1, CTSOP3.1) | GOV.UK Content API, `https://www.gov.uk/api/content/<page path>`; attachment picked by file name |
| MHCLG, Council Tax levels, Tables 1 to 9 | GOV.UK Content API, as above |
| DESNZ, sub-regional fuel poverty | GOV.UK Content API, as above |
| HM Land Registry, Price Paid Data | `https://price-paid-data.publicdata.landregistry.gov.uk/pp-<year>.csv` |
| HM Land Registry, UK House Price Index | newest monthly full file, found by trying recent months |
| ONS, postcode to OA, LSOA, MSOA and LAD lookup | ArcGIS catalogue search by title; the ONS Postcode Directory is the fallback |
| Open Innovations, hexagon layout of councils | GitHub, pinned to one commit |

Page paths and file-name patterns are in `pipeline/config.py`. When a new year's release
appears, the pipeline picks it up without code changes.

### Checks

The build stops and leaves the published data untouched if any of these fail: Band D matches
MHCLG's published 2026-27 values (`pipeline/fixtures`); at least 97% of sales match a postcode;
at least 6,500 small areas get a value; the number of homes in England is between 24 and 27.5
million; the flat-tax rate that raises today's total lies between 0.3% and 1.2%. Results are
saved in `project/data/summary.json`.

### Licences

Data: Open Government Licence v3.0 (HM Land Registry, Valuation Office, MHCLG, DESNZ, ONS);
postcode data also carries Ordnance Survey and Royal Mail rights. Hexagon layout: Open
Innovations, MIT. Vega, Vega-Lite, vega-embed: BSD-3-Clause. Inter: SIL Open Font Licence 1.1.
