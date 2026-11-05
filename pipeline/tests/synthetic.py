"""Synthetic copies of every source, laid out like the published files.

The values are invented. They exist so the whole pipeline can be run and tested
without downloading anything; the layouts follow the documented formats.
"""

import csv
import io
import json
import math
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import config

GROWTH_SINCE_1991 = {  # rough multiples, for shaping fake bands only
    "London": 7.0, "South East": 5.0, "East of England": 5.0, "South West": 4.6, "West Midlands": 3.9,
    "East Midlands": 3.9, "North West": 3.6, "Yorkshire and The Humber": 3.6, "North East": 3.0,
}
BAND_EDGES = [40_000, 52_000, 68_000, 88_000, 120_000, 160_000, 320_000]
TYPE_PREMIUM = {"D": 1.55, "S": 1.0, "T": 0.86, "F": 0.68}


def councils(hexjson_path, fixture_path):
    hexes = json.loads(Path(hexjson_path).read_text())["hexes"]
    fixture = pd.read_csv(fixture_path).set_index("lad")
    rows = []
    for code, info in sorted(hexes.items()):
        if not code.startswith("E"):
            continue
        published = fixture.loc[code] if code in fixture.index else None
        rows.append({
            "lad": code, "name": info["n"], "region": config.REGIONS[info["region"]],
            "band_d": float(published.band_d) if published is not None else 2400.0,
            "price": float(published.avg_price) if published is not None else 420_000.0,
        })
    return pd.DataFrame(rows)


def make_sources(directory, hexjson_path, fixture_path, msoas_per_council=3, sales_per_msoa=60, seed=7):
    rng = np.random.default_rng(seed)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    lads = councils(hexjson_path, fixture_path)

    msoa_rows, lsoa_rows, sale_rows, postcode_rows = [], [], [], []
    msoa_number, lsoa_number, postcode_number = 0, 0, 0
    for lad in lads.itertuples():
        growth = GROWTH_SINCE_1991[lad.region]
        count = max(1, int(msoas_per_council * rng.uniform(0.6, 1.6)))
        for k in range(count):
            msoa_number += 1
            msoa = f"E02{msoa_number:06d}"
            value = lad.price * float(rng.lognormal(0, 0.3))
            homes = int(rng.normal(3800, 500))
            flats = 0.55 if lad.region == "London" else 0.18
            shares = np.array([0.16, 0.28, 0.26 - 0.1 * (flats > 0.3), flats, 0.08, 0.02])
            shares = shares / shares.sum()
            types = dict(zip(["D", "S", "T", "F", "B", "O"], rng.multinomial(homes, shares)))
            values_1991 = value / growth * rng.lognormal(0, 0.45, homes)
            bands = np.searchsorted(BAND_EDGES, values_1991)
            band_counts = {b: int((bands == i).sum()) for i, b in enumerate(config.BANDS)}
            msoa_rows.append({"msoa": msoa, "lad": lad.lad, "name": f"{lad.name} {k + 1:03d}",
                              "value": value, **band_counts, **types})
            codes = []
            for j in range(5):
                lsoa_number += 1
                codes.append(f"E01{lsoa_number:06d}")
            split = rng.dirichlet(np.ones(5) * 4)
            for j, lsoa in enumerate(codes):
                part = {b: int(round(band_counts[b] * split[j])) for b in config.BANDS}
                lsoa_rows.append({"lsoa": lsoa, "msoa": msoa, "lad": lad.lad,
                                  "name": f"{lad.name} {k + 1:03d}{chr(65 + j)}", **part})
            for j in range(12):
                postcode_number += 1
                postcode = f"Z{postcode_number // 1000:03d} {postcode_number % 1000:03d}"
                postcode_rows.append({"pcds": postcode, "msoa": msoa, "lsoa": codes[j % 5], "lad": lad.lad})
                for _ in range(sales_per_msoa // 12):
                    kind = rng.choice(["D", "S", "T", "F"], p=[0.2, 0.3, 0.3, 0.2])
                    price = value * TYPE_PREMIUM[kind] * float(rng.lognormal(0, 0.22))
                    day = pd.Timestamp("2024-01-01") + pd.Timedelta(days=int(rng.integers(0, 970)))
                    category = "A" if rng.random() > 0.08 else "B"
                    sale_rows.append([f"{{{len(sale_rows):08d}}}", int(price), day.strftime("%Y-%m-%d 00:00"),
                                      postcode, kind, "N", "F", "1", "", "HIGH STREET", "", "TOWN",
                                      lad.name.upper(), "COUNTY", category, "A"])
    msoas = pd.DataFrame(msoa_rows)
    lsoas = pd.DataFrame(lsoa_rows)

    # a few Welsh postcodes and sales, which the pipeline must leave out
    postcode_rows.append({"pcds": "CF10 1AA", "msoa": "W02000001", "lsoa": "W01000001", "lad": "W06000015"})
    sale_rows.append(["{WALES001}", 250000, "2025-05-01 00:00", "CF10 1AA", "T", "N", "F", "1", "", "QUEEN ST",
                      "", "CARDIFF", "CARDIFF", "CARDIFF", "A", "A"])

    paths = {}
    paths["ctsop_bands"] = _ctsop_bands(directory, lads, msoas, lsoas)
    paths["ctsop_types"] = _ctsop_types(directory, msoas)
    paths["levels"] = _levels(directory, lads)
    paths["hpi"] = _hpi(directory, lads)
    paths["ppd"] = _ppd(directory, sale_rows)
    paths["lookup"] = _lookup(directory, postcode_rows)
    paths["fuel_poverty"] = _fuel_poverty(directory, lads, msoas, lsoas, rng)
    paths["income"] = _income(directory, msoas, lads, rng)
    paths["hexjson"] = Path(hexjson_path)
    return paths, msoas


def _csv_text(rows):
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue()


def _ctsop_bands(directory, lads, msoas, lsoas):
    rows = [["GEOGRAPHY", "BA_CODE", "ECODE", "AREA_NAME"] + [f"BAND_{b}" for b in "ABCDEFGHI"] + ["ALL_PROPERTIES"]]

    def line(level, code, name, counts):
        values = [counts.get(b, 0) for b in config.BANDS]
        shown = [("-" if 0 < v < 5 else round(v, -1)) for v in values]
        return [level, "N/A", code, name] + shown + ["..", round(sum(values), -1)]

    for lad in lads.itertuples():
        inside = msoas[msoas.lad == lad.lad]
        rows.append(line("LAUA", lad.lad, lad.name, inside[config.BANDS].sum().to_dict()))
        for m in inside.itertuples():
            rows.append(line("MSOA", m.msoa, m.name, {b: getattr(m, b) for b in config.BANDS}))
            for l in lsoas[lsoas.msoa == m.msoa].itertuples():
                rows.append(line("LSOA", l.lsoa, l.name, {b: getattr(l, b) for b in config.BANDS}))
    path = directory / "CTSOP_1_1.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("CTSOP1_1_2026.csv", _csv_text(rows))
    return path


def _ctsop_types(directory, msoas):
    header = ["GEOGRAPHY", "BA_CODE", "ECODE", "AREA_NAME", "BAND", "BUNGALOW", "FLAT_MAIS", "HOUSE_TERRACED",
              "HOUSE_SEMI", "HOUSE_DETACHED", "ANNEXE", "CARAVAN_HOUSEBOAT_MOBILEHOME", "UNKNOWN", "ALL_PROPERTIES"]
    rows = [header]
    for m in msoas.itertuples():
        total = m.B + m.F + m.T + m.S + m.D + m.O
        rows.append(["MSOA", "N/A", m.msoa, m.name, "All", m.B, m.F, m.T, m.S, m.D, m.O // 2, m.O - m.O // 2, 0, total])
        rows.append(["MSOA", "N/A", m.msoa, m.name, "A", 0, m.F // 3, 0, 0, 0, 0, 0, 0, m.F // 3])
    path = directory / "CTSOP_3_1.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("CTSOP3_1_2026.csv", _csv_text(rows))
    return path


def _levels(directory, lads):
    title = pd.DataFrame([["Table 9: Area council tax for a dwelling occupied by 2 adults by band, 2026-27"],
                          ["Source: synthetic"], [""]])
    header = ["ONS code", "Billing authority", "Class"] + [f"Band {b}" for b in config.BANDS]
    body = [[r.lad, r.name, "SD"] + [round(r.band_d * config.BAND_RATIO[b], 2) for b in config.BANDS]
            for r in lads.itertuples()]
    table9 = pd.concat([title, pd.DataFrame([header] + body)], ignore_index=True)
    table8 = pd.DataFrame([["Table 8: something else"], ["ONS code", "Authority", "Band D"]] +
                          [[r.lad, r.name, r.band_d * 0.9] for r in lads.itertuples()])
    path = directory / "Tables_1-9_2026-27.ods"
    with pd.ExcelWriter(path, engine="odf") as writer:
        pd.DataFrame([["Cover"]]).to_excel(writer, sheet_name="Cover", header=False, index=False)
        table8.to_excel(writer, sheet_name="Table_8", header=False, index=False)
        table9.to_excel(writer, sheet_name="Table_9", header=False, index=False)
    return path


def _hpi(directory, lads):
    months = pd.date_range("1991-04-01", "2026-08-01", freq="MS")
    rows = []
    region_growth = {r: g for r, g in GROWTH_SINCE_1991.items()}
    regions = list(config.REGIONS.items()) + [(config.ENGLAND, "England")]
    for code, name in regions:
        growth = region_growth.get(name, 4.5)
        for i, month in enumerate(months):
            share = i / (len(months) - 1)
            price = 60_000 * growth ** share * (1 + 0.04 * math.sin(i / 9))
            rows.append({"Date": month.strftime("%d/%m/%Y"), "RegionName": name, "AreaCode": code,
                         "AveragePrice": round(price, 2), "Index": round(100 * price / 250_000, 4)})
    recent = pd.date_range("2023-01-01", "2026-08-01", freq="MS")
    for lad in lads.itertuples():
        if lad.lad == "E06000053":  # no index for the Isles of Scilly
            continue
        for i, month in enumerate(recent):
            factor = 1.03 ** ((i - 38) / 12)
            row = {"Date": month.strftime("%d/%m/%Y"), "RegionName": lad.name, "AreaCode": lad.lad,
                   "AveragePrice": round(lad.price * factor, 2), "Index": round(120 * factor, 4)}
            for kind, column in (("D", "Detached"), ("S", "SemiDetached"), ("T", "Terraced"), ("F", "Flat")):
                row[f"{column}Index"] = round(120 * factor * (1 + 0.01 * "DSTF".index(kind)), 4)
                row[f"{column}Price"] = round(lad.price * TYPE_PREMIUM[kind] * factor, 2)
            rows.append(row)
    columns = ["Date", "RegionName", "AreaCode", "AveragePrice", "Index", "IndexSA", "1m%Change", "12m%Change",
               "AveragePriceSA", "SalesVolume", "DetachedPrice", "DetachedIndex", "Detached1m%Change",
               "Detached12m%Change", "SemiDetachedPrice", "SemiDetachedIndex", "SemiDetached1m%Change",
               "SemiDetached12m%Change", "TerracedPrice", "TerracedIndex", "Terraced1m%Change",
               "Terraced12m%Change", "FlatPrice", "FlatIndex", "Flat1m%Change", "Flat12m%Change"]
    path = directory / "UK-HPI-full-file-2026-08.csv"
    pd.DataFrame(rows).reindex(columns=columns).to_csv(path, index=False)
    return path


def _ppd(directory, sale_rows):
    by_year = {}
    for row in sale_rows:
        by_year.setdefault(row[2][:4], []).append(row)
    paths = []
    for year, rows in sorted(by_year.items()):
        path = directory / f"pp-{year}.csv"
        with open(path, "w", newline="") as handle:
            csv.writer(handle, quoting=csv.QUOTE_ALL).writerows(rows)
        paths.append(path)
    return paths


def _lookup(directory, postcode_rows):
    frame = pd.DataFrame(postcode_rows)
    out = pd.DataFrame({
        "PCD7": frame.pcds.str.replace(" ", ""), "PCD8": frame.pcds, "PCDS": frame.pcds,
        "DOINTR": "199801", "DOTERM": "", "USERTYPE": "0", "OA21CD": "", "LSOA21CD": frame.lsoa,
        "MSOA21CD": frame.msoa, "LADCD": frame.lad, "LSOA21NM": "", "MSOA21NM": "", "LADNM": "", "LADNMW": "",
    })
    path = directory / "postcode-lookup.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("PCD_OA21_LSOA21_MSOA21_LAD_MAY26_UK_LU.csv", out.to_csv(index=False))
    return path


def _fuel_poverty(directory, lads, msoas, lsoas, rng):
    path = directory / "fuel-poverty-sub-regional-2026-2024-data-tables.xlsx"
    homes = msoas.groupby("lad")[config.BANDS].sum().sum(axis=1)
    rate = (0.22 - 0.25 * (lads.set_index("lad").price.clip(100_000, 600_000) - 100_000) / 500_000).clip(0.06, 0.2)
    table2 = [["Table 2: Fuel poor households by administrative area, 2024"], [""],
              ["Area Codes", "Area names", "Number of households", "Number of households in fuel poverty",
               "Proportion of households fuel poor (%)"]]
    for lad in lads.itertuples():
        households = int(homes.get(lad.lad, 0) * 0.96)
        poor = int(households * rate[lad.lad])
        table2.append([lad.lad, lad.name, households, poor, round(100 * poor / max(households, 1), 1)])
    table4 = [["Table 4: Fuel poor households by LSOA, 2024"], [""],
              ["LSOA Code", "LSOA Name", "LA Code", "LA Name", "Region", "Number of households",
               "Number of households in fuel poverty", "Proportion of households fuel poor (%)"]]
    for l in lsoas.itertuples():
        households = int(sum(getattr(l, b) for b in config.BANDS) * 0.96)
        poor = int(households * rate[l.lad] * rng.uniform(0.6, 1.4))
        table4.append([l.lsoa, l.name, l.lad, "", "", households, poor, round(100 * poor / max(households, 1), 1)])
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame([["Contents"]]).to_excel(writer, sheet_name="Contents", header=False, index=False)
        pd.DataFrame(table2).to_excel(writer, sheet_name="Table 2", header=False, index=False)
        pd.DataFrame(table4).to_excel(writer, sheet_name="Table 4", header=False, index=False)
    return path


def _income(directory, msoas, lads, rng):
    """ONS-style small area income workbook: contents, then one sheet per income measure, each with title rows."""
    path = directory / "ons-small-area-income.xlsx"
    price = lads.set_index("lad").price
    header = ["MSOA code", "MSOA name", "Local authority code", "Local authority name", "Region code", "Region name"]
    def sheet(title, label, scale):
        rows = [[title], ["Financial year ending 2023"], [""], header + [label, "Upper confidence limit (£)",
                                                                       "Lower confidence limit (£)", "Confidence interval (£)"]]
        for m in msoas.itertuples():
            income = round(scale * (24_000 + 0.05 * price[m.lad]) * rng.uniform(0.8, 1.2), -2)
            rows.append([m.msoa, m.name, m.lad, "", "", "", income, income * 1.1, income * 0.9, income * 0.2])
        return pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame([["Contents"], ["Income estimates for small areas"]]).to_excel(writer, sheet_name="Contents", header=False, index=False)
        sheet("Total annual income", "Total annual income (£)", 1.6).to_excel(writer, sheet_name="Total annual income", header=False, index=False)
        sheet("Net annual income (unequivalised)", "Net annual income (£)", 1.3).to_excel(writer, sheet_name="Net annual income", header=False, index=False)
        sheet("Net annual income before housing costs (equivalised)", "Net annual income before housing costs (£)", 1.0).to_excel(
            writer, sheet_name="Net income before housing costs", header=False, index=False)
        sheet("Net annual income after housing costs (equivalised)", "Net annual income after housing costs (£)", 0.7).to_excel(
            writer, sheet_name="Net income after housing costs", header=False, index=False)
    return path
