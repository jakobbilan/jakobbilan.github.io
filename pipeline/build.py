"""Build every data file the project page reads.

    python -m pipeline.build            download what is new, rebuild project/data
    python -m pipeline.build --refresh  download everything again

Outputs go to project/data and project/geo. If any check fails, nothing is written.
"""

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from . import checks, compute, config, facts, fetch, hexmap, read, sales

MSOA_NAMES_URL = "https://houseofcommonslibrary.github.io/msoanames/MSOA-Names-2.2.csv"


def resolve_sources(today, refresh=False):
    """Find and download the newest release of every source."""
    paths, meta = {}, {}

    url, page = fetch.find_govuk_file(fetch.ctsop_pages(today), config.ATTACHMENT_PATTERNS["ctsop_bands"])
    paths["ctsop_bands"] = fetch.download(url, refresh=refresh)
    meta["ctsop_bands"] = {"url": url, "page": page}
    url, page = fetch.find_govuk_file(fetch.ctsop_pages(today), config.ATTACHMENT_PATTERNS["ctsop_types"])
    paths["ctsop_types"] = fetch.download(url, refresh=refresh)
    meta["ctsop_types"] = {"url": url, "page": page}

    url, page = fetch.find_govuk_file(fetch.levels_pages(today), config.ATTACHMENT_PATTERNS["levels"])
    paths["levels"] = fetch.download(url, refresh=refresh)
    first, second = re.search(r"(\d{4})-to-(\d{4})", page).groups()
    meta["levels"] = {"url": url, "page": page, "year": f"{first}-{second[2:]}"}

    url, page = fetch.find_govuk_file(fetch.fuel_poverty_pages(today), config.ATTACHMENT_PATTERNS["fuel_poverty"])
    paths["fuel_poverty"] = fetch.download(url, refresh=refresh)
    meta["fuel_poverty"] = {"url": url, "page": page}

    url, month = fetch.latest_hpi_url(today)
    paths["hpi"] = fetch.download(url, refresh=refresh)
    meta["hpi"] = {"url": url, "month": month}

    paths["ppd"] = []
    for year in range(int(config.SALES_FROM[:4]), today.year + 1):
        url = config.PPD_URL.format(year=year)
        if fetch.exists(url):
            paths["ppd"].append(fetch.download(url, refresh=refresh or year == today.year))
    meta["ppd"] = {"files": [p.name for p in paths["ppd"]]}

    paths["lookup"], title, url = fetch.postcode_lookup(refresh=refresh)
    meta["lookup"] = {"url": url, "title": title}

    paths["hexjson"] = fetch.download(config.HEXJSON_URL, "lad-2025.hexjson", refresh=refresh)
    meta["hexjson"] = {"url": config.HEXJSON_URL}

    try:
        paths["msoa_names"] = fetch.download(MSOA_NAMES_URL, refresh=refresh)
    except Exception as error:
        fetch.log(f"MSOA names unavailable ({error}); using Valuation Office names")
    return paths, meta


def msoa_names(path):
    frame = read.normalise_columns(pd.read_csv(path, dtype=str, encoding="utf-8-sig", encoding_errors="replace"))
    code = next(c for c in frame.columns if c.startswith("msoa21cd"))
    names = [c for c in frame.columns if "hcl" in c and c.endswith("nm")] or [c for c in frame.columns if c.endswith("nm")]
    return frame.set_index(code)[names[0]]


def build_outputs(paths, meta):
    """Read every source, compute all tables, run checks. Returns tables, summary and check results."""
    fetch.log("reading band counts, property types and Band D")
    bands = read.read_band_counts(paths["ctsop_bands"])
    types = read.read_type_counts(paths["ctsop_types"], "msoa").rename(columns={"code": "msoa"})
    band_d = read.read_band_d(paths["levels"])
    hpi = read.read_hpi(paths["hpi"])

    lookup = paths["lookup"]
    if str(lookup).endswith(".zip"):
        lookup = read.extract_largest_csv(lookup, config.CACHE / (lookup.stem + ".csv"))
    fetch.log("matching sales to areas")
    s = sales.summarise(paths["ppd"], lookup, hpi)

    geo = hexmap.to_geojson(json.loads(open(paths["hexjson"], encoding="utf-8").read()))
    places = pd.DataFrame([f["properties"] for f in geo["features"]])[["lad", "name", "region"]]

    # Councils: band mix and Band D
    lad_counts = bands[bands.level == "lad"].rename(columns={"code": "lad"})
    councils = compute.bills_by_band_mix(lad_counts, band_d.drop(columns="name"))
    councils = places.merge(councils.drop(columns="name"), on="lad", how="left")

    # MSOAs: bill from band mix, value from sales weighted by the stock of each type
    msoa_counts = bands[bands.level == "msoa"].rename(columns={"code": "msoa"})
    msoa_counts = msoa_counts.merge(s["msoa_lad"], on="msoa", how="inner")
    msoa = compute.bills_by_band_mix(msoa_counts, band_d.drop(columns="name"))
    prices = compute.type_prices(types, s["msoa"], s["lad"], s["lad_all"], s["msoa_lad"])
    msoa = msoa.merge(compute.stock_value(prices), on="msoa", how="left")
    msoa = msoa.merge(s["msoa_sales"], on="msoa", how="left").fillna({"sales": 0})
    msoa["rate"] = msoa.bill / msoa.value
    msoa = msoa.merge(places.rename(columns={"name": "council"}), on="lad", how="left")
    if "msoa_names" in paths:
        names = msoa_names(paths["msoa_names"])
        msoa["name"] = msoa.msoa.map(names).fillna(msoa["name"])
    msoa = msoa.dropna(subset=["bill", "value"])
    msoa["r_local"] = msoa.lad.map(compute.revenue_neutral(msoa, by="lad"))

    # Council totals from their MSOAs
    weights = msoa.assign(bill_total=msoa.bill * msoa.dwellings, value_total=msoa.value * msoa.dwellings)
    totals = weights.groupby("lad").agg(bill_total=("bill_total", "sum"), value_total=("value_total", "sum"),
                                        msoa_dwellings=("dwellings", "sum"))
    councils = councils.merge(totals, on="lad", how="left")
    councils["value"] = councils.value_total / councils.msoa_dwellings
    councils["rate_mix"] = councils.bill_total / councils.value_total
    councils["r_local"] = councils.rate_mix

    latest = hpi[hpi.date == s["reference"]].set_index("code").price
    councils["price"] = councils.lad.map(latest)
    councils["rate_press"] = councils.band_d / councils.price
    march = hpi[hpi.date == pd.Timestamp("2026-03-01")][["code", "price"]]
    march = march.rename(columns={"code": "lad", "price": "price_march"}) if len(march) else None

    # Energy payment: share of homes in Bands A-D against fuel poverty
    fp_lad, fp_lsoa = read.read_fuel_poverty(paths["fuel_poverty"])
    councils = councils.merge(fp_lad.rename(columns={"code": "lad", "rate": "fp_rate"}), on="lad", how="left")
    if fp_lsoa is not None:
        lsoa = bands[bands.level == "lsoa"].rename(columns={"code": "lsoa"})
        lsoa["share_eh"] = lsoa[list("EFGH")].sum(axis=1) / lsoa.dwellings.where(lsoa.dwellings > 0)
        lsoa = lsoa.merge(fp_lsoa.rename(columns={"code": "lsoa"}), on="lsoa", how="inner")
        lsoa = lsoa.merge(s["lsoa_lad"], on="lsoa", how="left")
        lsoa["fp_outside_ad"] = lsoa.fuel_poor * lsoa.share_eh
        councils["fp_outside_ad"] = councils.lad.map(lsoa.groupby("lad").fp_outside_ad.sum())

    councils = councils.merge(s["high_value"], on="lad", how="left")

    england = {
        "dwellings": float(councils.dwellings.sum()),
        "bill_per_dwelling": float((councils.bill * councils.dwellings).sum() / councils.dwellings.sum()),
        "value_per_dwelling": float(weights.value_total.sum() / weights.dwellings.sum()),
        "rate_mix": float(weights.bill_total.sum() / weights.value_total.sum()),
        "revenue_neutral_rate": float(compute.revenue_neutral(msoa)),
        "share_ad": float(councils[config.ENERGY_PAYMENT_BANDS].sum().sum() / councils.dwellings.sum()),
        "fuel_poor": float(councils.fuel_poor.sum()),
        "fp_rate": float(councils.fuel_poor.sum() / councils.households.sum()),
        "fp_outside_ad": float(councils.fp_outside_ad.sum()) if "fp_outside_ad" in councils else None,
        "msoas": int(len(msoa)),
        "sales_used": int(s["n_sales"]),
        "msoa_fallback_share": float((msoa.fallback_share * msoa.dwellings).sum() / msoa.dwellings.sum()),
    }

    results = checks.run(councils, msoa, england, s, meta.get("levels", {}).get("year"), march)

    bins = compute.rate_bins(msoa)
    regions, base = compute.regional_prices(hpi)
    fetch.log(f"regional prices from {base:%B %Y}")
    references = pd.DataFrame([
        {"key": "fairer_share", "label": "Fairer Share proposal", "rate": config.FAIRER_SHARE_RATE},
        {"key": "neutral", "label": "Flat rate raising today's total", "rate": england["revenue_neutral_rate"]},
        {"key": "england", "label": "England average", "rate": england["rate_mix"]},
        {"key": "england_share_ad", "label": "England, homes in Bands A-D", "rate": england["share_ad"]},
        {"key": "england_fp", "label": "England, fuel-poor households", "rate": england["fp_rate"]},
    ])

    ranked = councils.dropna(subset=["rate_mix"]).sort_values("rate_mix")
    summary = {
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "price_month": s["reference"].strftime("%Y-%m"),
        "sales_window": [str(s["window"][0]), str(s["window"][1] - timedelta(days=1))],
        "regions_base": base.strftime("%Y-%m"),
        "england": england,
        "highest": ranked.iloc[-1][["lad", "name", "rate_mix", "rate_press"]].to_dict(),
        "lowest": ranked.iloc[0][["lad", "name", "rate_mix", "rate_press"]].to_dict(),
        "gap_mix": float(ranked.rate_mix.iloc[-1] / ranked.rate_mix.iloc[0]),
        "gap_press": float(councils.rate_press.max() / councils.rate_press.min()),
        "sources": meta,
    }
    tables = {"msoa": msoa, "bins": bins, "councils": councils, "regions": regions, "references": references}
    summary["facts"] = facts.collect(tables, summary, results)
    return tables, summary, results, geo


def write_outputs(tables, summary, results, geo):
    config.OUT_DATA.mkdir(parents=True, exist_ok=True)
    config.OUT_GEO.mkdir(parents=True, exist_ok=True)

    msoa = tables["msoa"]
    out = pd.DataFrame({
        "msoa": msoa.msoa, "name": msoa["name"], "lad": msoa.lad, "council": msoa.council, "region": msoa.region,
        "dwellings": msoa.dwellings.round().astype(int), "bill": msoa.bill.round(0),
        "value": (msoa.value / 100).round() * 100, "rate": msoa.rate.round(6),
        "sales": msoa.sales.astype(int), "r_local": msoa.r_local.round(6),
    })
    out.sort_values("msoa").to_csv(config.OUT_DATA / "msoa.csv", index=False)

    bins = tables["bins"].copy()
    bins["value"] = bins.value.round(-2)
    bins[["rate_p25", "rate", "rate_p75"]] = bins[["rate_p25", "rate", "rate_p75"]].round(6)
    bins.to_csv(config.OUT_DATA / "msoa_bins.csv", index=False)

    c = tables["councils"]
    columns = {"lad": None, "name": None, "region": None, "dwellings": 0, "band_d": 2, "bill": 0, "value": -2,
               "price": 0, "rate_mix": 6, "rate_press": 6, "share_ad": 4, "households": 0, "fuel_poor": 0,
               "fp_rate": 4, "fp_outside_ad": 0, "sales_2m": 0, "sales_all": 0, "r_local": 6}
    council_out = pd.DataFrame({k: (c[k].round(d) if d is not None else c[k]) for k, d in columns.items()
                                if k in c})
    council_out.sort_values("lad").to_csv(config.OUT_DATA / "councils.csv", index=False)

    regions = tables["regions"].copy()
    regions["date"] = regions.date.dt.strftime("%Y-%m-%d")
    regions["price"] = regions.price.round(0)
    regions["multiple"] = regions.multiple.round(4)
    regions[["region", "code", "date", "price", "multiple"]].to_csv(config.OUT_DATA / "regions.csv", index=False)

    tables["references"].assign(rate=lambda f: f.rate.round(6)).to_csv(
        config.OUT_DATA / "reference_rates.csv", index=False)

    def clean(value):
        if isinstance(value, (np.floating, float)):
            return None if np.isnan(value) else float(value)
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [clean(v) for v in value]
        if isinstance(value, (pd.Timestamp, date)):
            return value.isoformat()
        return value

    summary = clean({**summary, "checks": results})
    with open(config.OUT_DATA / "summary.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)
    with open(config.OUT_GEO / "hex-lad-2025.geojson", "w", encoding="utf-8") as handle:
        json.dump(geo, handle, separators=(",", ":"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="download every source again")
    args = parser.parse_args(argv)

    paths, meta = resolve_sources(date.today(), refresh=args.refresh)
    tables, summary, results, geo = build_outputs(paths, meta)
    for result in results:
        fetch.log(f"{result['status']:5}  {result['check']}: {result['detail']}")
    if any(r["status"] == "fail" for r in results):
        fetch.log("checks failed; outputs left unchanged")
        return 1
    write_outputs(tables, summary, results, geo)
    fetch.log(f"wrote {config.OUT_DATA.relative_to(config.ROOT)} and {config.OUT_GEO.relative_to(config.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
