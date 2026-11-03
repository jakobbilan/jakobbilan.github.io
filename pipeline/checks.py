"""Checks run on every build. A failed check stops the build so the page keeps its last good data."""

import pandas as pd

from . import config


def _result(name, ok, detail, warn_only=False):
    status = "pass" if ok else ("warn" if warn_only else "fail")
    return {"check": name, "status": status, "detail": detail}


def run(councils, msoa, england, sales_stats, fiscal_year, hpi_march_2026=None):
    results = []
    fixture_path = config.FIXTURES / "council-ratios-2026-27.csv"
    fixture = pd.read_csv(fixture_path) if fixture_path.exists() else None

    results.append(_result("band_d_councils", councils.band_d.notna().sum() >= 290,
                           f"{int(councils.band_d.notna().sum())} councils with an area Band D"))

    if fixture is not None and fiscal_year == "2026-27":
        merged = fixture.merge(councils[["lad", "band_d"]], on="lad", suffixes=("_published", ""))
        gap = (merged.band_d - merged.band_d_published).abs()
        results.append(_result("band_d_matches_published", len(merged) >= 290 and gap.median() <= 0.5
                               and gap.max() <= 5,
                               f"{len(merged)} councils compared; median gap £{gap.median():.2f}, "
                               f"largest £{gap.max():.2f}"))
        if hpi_march_2026 is not None:
            merged = merged.merge(hpi_march_2026, on="lad", how="inner")
            ours = 100 * merged.band_d / merged.price_march
            within = ((ours - merged.pct).abs() <= 0.015).mean()
            results.append(_result("replicates_july_2026_ranking", within >= 0.9,
                                   f"{within:.0%} of {len(merged)} councils within 0.015 points "
                                   "of the published Band D / price ratio", warn_only=True))

    total = england["dwellings"]
    results.append(_result("dwellings_total", 24e6 <= total <= 27.5e6, f"{total / 1e6:.2f}m homes in England"))

    ratio = england["bill_per_dwelling"] / config.MHCLG_PER_DWELLING
    results.append(_result("gross_bill_vs_mhclg", 1.0 <= ratio <= 1.45,
                           f"gross £{england['bill_per_dwelling']:,.0f} per home vs MHCLG net "
                           f"£{config.MHCLG_PER_DWELLING:,} ({ratio:.2f}x)", warn_only=True))

    match = sales_stats["match_rate"]
    results.append(_result("postcode_match", match >= 0.97, f"{match:.2%} of sales matched to an area"))

    covered = int(msoa.value.notna().sum())
    results.append(_result("msoa_coverage", covered >= 6500, f"{covered:,} MSOAs with a value"))

    r_star = england["revenue_neutral_rate"]
    results.append(_result("revenue_neutral_rate", 0.003 <= r_star <= 0.012, f"{r_star:.3%}"))

    return results
