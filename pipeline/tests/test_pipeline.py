import json
import math

import pandas as pd
import pytest

from pipeline import build, compute, config, hexmap, read
from pipeline.tests import synthetic

HEXJSON = config.FIXTURES / "lad-2025.hexjson"
FIXTURE = config.FIXTURES / "council-ratios-2026-27.csv"


def test_band_ratios_follow_the_act():
    assert [round(config.BAND_RATIO[b] * 9) for b in config.BANDS] == [6, 7, 8, 9, 11, 13, 15, 18]


def test_surcharge_schedule():
    values = [1_999_999, 2_000_000, 2_499_999, 2_500_000, 3_500_000, 5_000_000, 20_000_000]
    assert compute.surcharge(values).tolist() == [0, 2500, 2500, 3500, 5000, 7500, 7500]


def test_bill_from_band_mix():
    counts = pd.DataFrame({"lad": ["X"], **{b: [0] for b in config.BANDS}})
    counts.loc[0, ["A", "H"]] = [3, 1]
    counts["dwellings"] = 4
    bills = compute.bills_by_band_mix(counts, pd.DataFrame({"lad": ["X"], "band_d": [900.0]}))
    assert bills.bill.iloc[0] == pytest.approx((3 * 600 + 1800) / 4)
    assert bills.share_ad.iloc[0] == pytest.approx(0.75)


def test_numbers_and_suppression_markers():
    values = read.to_number(["1,230", "-", "[c]", "..", "£2,549.42", ""])
    assert values.iloc[0] == 1230 and values.iloc[4] == pytest.approx(2549.42)
    assert values.iloc[[1, 2, 3, 5]].isna().all()


@pytest.mark.parametrize("column, kind", [
    ("house_detached", "D"), ("house_semi", "S"), ("semi_detached_house", "S"), ("house_terraced", "T"),
    ("flat_mais", "F"), ("bungalow_unkw", "B"), ("bungalow_total", "B"), ("caravan_houseboat_mobilehome", "O"),
    ("annexe", "O"), ("unknown", "O"), ("all_properties", None), ("band", None), ("area_name", None),
])
def test_property_types(column, kind):
    assert read.property_type(column) == kind


def test_postcode_fields_in_both_products():
    lookup = read.postcode_fields(["PCD7", "PCD8", "PCDS", "DOINTR", "DOTERM", "USERTYPE", "OA21CD",
                                   "LSOA21CD", "MSOA21CD", "LADCD"])
    assert lookup == {"postcode": "PCDS", "msoa": "MSOA21CD", "lsoa": "LSOA21CD", "lad": "LADCD", "doterm": "DOTERM"}
    onspd = read.postcode_fields(["pcd", "pcd2", "pcds", "dointr", "doterm", "oslaua", "lsoa21", "msoa21"])
    assert onspd["msoa"] == "msoa21" and onspd["lad"] == "oslaua"


def test_long_format_band_counts(tmp_path):
    rows = ["GEOGRAPHY,ECODE,AREA_NAME,BAND,ALL_PROPERTIES"]
    for band, n in zip("ABCDEFGH", [10, 20, 30, 40, 0, 0, 0, 10]):
        rows.append(f"LSOA,E01000001,Somewhere 001A,{band},{n}")
    rows.append("LSOA,E01000001,Somewhere 001A,All,110")
    path = tmp_path / "long.csv"
    path.write_text("\n".join(rows))
    bands = read.read_band_counts(path)
    assert bands.loc[0, "dwellings"] == 110 and bands.loc[0, "H"] == 10 and bands.loc[0, "level"] == "lsoa"


def test_hexagons_tile():
    geo = hexmap.to_geojson(json.loads(HEXJSON.read_text()))
    assert len(geo["features"]) == 296
    ring = geo["features"][0]["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1] and len(ring) == 7
    assert hexmap.centre(1, 0)[0] - hexmap.centre(0, 0)[0] == pytest.approx(1)
    assert hexmap.centre(0, 1)[1] == pytest.approx(math.sqrt(3) / 2)
    assert hexmap.centre(0, 1)[0] == pytest.approx(0.5)


def test_weighted_quantile():
    assert compute.weighted_quantile([1, 2, 3], [1, 1, 1], 0.5) == pytest.approx(2)
    assert compute.weighted_quantile([1, 2, 3], [0, 0, 5], 0.5) == pytest.approx(3)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    directory = tmp_path_factory.mktemp("sources")
    paths, truth = synthetic.make_sources(directory, HEXJSON, FIXTURE, msoas_per_council=2, sales_per_msoa=36)
    cache = config.CACHE
    config.CACHE = directory / "cache"
    config.CACHE.mkdir()
    try:
        yield build.build_outputs(paths, {"levels": {"year": "2026-27"}}), truth
    finally:
        config.CACHE = cache


def test_end_to_end(built):
    (tables, summary, results, geo), truth = built
    councils, msoa = tables["councils"], tables["msoa"]
    assert len(councils) == 296 and councils.band_d.notna().all()
    assert not msoa.msoa.str.startswith("W").any()
    assert (msoa.rate > 0).all() and msoa.value.notna().all()
    status = {r["check"]: r["status"] for r in results}
    assert status["band_d_matches_published"] == "pass"
    assert status["postcode_match"] == "pass"
    england = summary["england"]
    assert england["revenue_neutral_rate"] == pytest.approx(england["rate_mix"])
    bins = tables["bins"]
    assert len(bins) == 40 and bins.value.is_monotonic_increasing


def test_bills_use_band_d_and_band_mix(built):
    (tables, *_), truth = built
    row = tables["msoa"].iloc[0]
    band_d = pd.read_csv(FIXTURE).set_index("lad").band_d.get(row.lad, 2400.0)
    counts = truth.set_index("msoa").loc[row.msoa, config.BANDS].astype(float)
    shown = counts.where(counts >= 5, 0).round(-1)
    expected = band_d * sum(shown[b] * config.BAND_RATIO[b] for b in config.BANDS) / shown.sum()
    assert row.bill == pytest.approx(expected, rel=1e-6)


def _hpi(codes, start):
    months = pd.date_range(start, "1996-12-01", freq="MS")
    return pd.DataFrame([{"code": c, "date": m, "price": 50_000.0 + i} for c in codes for i, m in enumerate(months)])


def test_regions_start_in_1991_when_every_region_reaches_back():
    hpi = pd.concat([_hpi(list(config.REGIONS), "1991-01-01"), _hpi([config.ENGLAND], "1995-01-01")])
    frame, base = compute.regional_prices(hpi)
    assert base == pd.Timestamp("1991-04-01")
    assert config.ENGLAND not in set(frame.code)
    assert (frame[frame.date == base].multiple == 1).all()


def test_regions_fall_back_to_1995():
    hpi = _hpi(list(config.REGIONS) + [config.ENGLAND], "1995-01-01")
    frame, base = compute.regional_prices(hpi)
    assert base == pd.Timestamp("1995-01-01") and frame.code.nunique() == 10


def test_facts_for_the_text(built):
    (tables, summary, results, geo), truth = built
    f = summary["facts"]
    assert set(f) == {"data", "policy", "fig1", "pair", "fig2", "fig3", "fig4", "fig5", "fig6"}
    assert f["fig1"]["cheap_rate"] > f["fig1"]["dear_rate"] and f["fig1"]["ratio"] > 1
    assert f["pair"]["a_name"] == "Burnley" and f["pair"]["b_name"] == "Westminster"
    assert f["fig4"]["rate_10m_with"] > f["fig4"]["rate_10m_now"]
    assert f["fig4"]["charge_2m"] == 2500 and f["fig4"]["charge_10m"] == 7500
    assert f["fig6"]["neutral_rate"] == pytest.approx(summary["england"]["revenue_neutral_rate"])
    assert 0 < f["fig6"]["neutral_less"] < 1 and f["fig6"]["fs_revenue"] < 1
    assert f["fig2"]["london_x"] > f["fig2"]["north_east_x"]


def test_figure_5_estimate_lies_within_its_bounds(built):
    (tables, summary, results, geo), truth = built
    england, fig5, councils = summary["england"], summary["facts"]["fig5"], tables["councils"]
    assert england["fp_outside_ad_min"] <= england["fp_outside_ad"] <= england["fp_outside_ad_max"] <= england["fuel_poor"]
    inside = councils.dropna(subset=["fp_outside_ad"])
    assert (inside.fp_outside_ad_min <= inside.fp_outside_ad + 1e-6).all()
    assert (inside.fp_outside_ad <= inside.fp_outside_ad_max + 1e-6).all()
    shares = [fig5[f"lab{k}_share_ad"] for k in range(1, 6)]
    assert shares == sorted(shares)
    assert 0 < fig5["top10_outside_share"] <= 1


def test_income_groups(built, tmp_path):
    (tables, summary, results, geo), truth = built
    msoa = tables["msoa"]
    assert msoa.income.notna().all()
    shares = msoa.groupby("income_group").dwellings.sum() / msoa.dwellings.sum()
    assert list(shares.index) == [1, 2, 3, 4, 5]
    assert (abs(shares - 0.2) < 0.06).all()                          # each group holds about a fifth of homes
    means = msoa.groupby("income_group").income.mean()
    assert means.is_monotonic_increasing
    fig6 = summary["facts"]["fig6"]
    assert 0 <= fig6["income1_less_neutral"] <= 1 and 0 <= fig6["income5_less_fs"] <= 1
    assert {r["check"]: r["status"] for r in results}["income_matched"] == "pass"


def test_income_reader_picks_before_housing_costs(built):
    (tables, summary, results, geo), truth = built
    sheets = pd.read_excel(build.config.CACHE.parent / "ons-small-area-income.xlsx", sheet_name=None, header=None)
    bhc = sheets["Net income before housing costs"]
    first = bhc[bhc[0].astype(str).str.match(r"^E02")].iloc[0]
    row = tables["msoa"].set_index("msoa").loc[first[0]]
    assert abs(row.income - round(float(first[6]), -2)) <= 100


def test_build_survives_missing_income(tmp_path):
    msoa = pd.DataFrame({"msoa": ["E02000001"], "dwellings": [100.0]})
    out = build.add_income(msoa, None)
    assert "income" not in out
    out = build.add_income(msoa, tmp_path / "missing.xlsx")
    assert "income" not in out
