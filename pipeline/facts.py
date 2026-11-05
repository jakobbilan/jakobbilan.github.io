"""Every number the page's text quotes, stored in summary.json under "facts".

The page fills <span data-stat="facts.…"> elements from these values, so sentences
stay in step with the charts after each rebuild. Values keep full precision here;
rounding happens on the page through data-format.
"""

import numpy as np
import pandas as pd

from . import compute, config

# Councils with fewer fuel-poor households are not labelled in figure 5 (the chart uses the same floor)
MIN_FUEL_POOR = 1000


def _row(councils, code):
    return councils.set_index("lad").loc[code]


def staircase(bins):
    """Median rate in the cheapest and dearest groups of homes (each 1/40 of all homes)."""
    low, high = bins.iloc[0], bins.iloc[-1]
    return {"cheap_value": low.value, "cheap_rate": low.rate, "dear_value": high.value, "dear_rate": high.rate,
            "ratio": low.rate / high.rate, "group_share": 1 / len(bins)}


def pair(councils, codes=config.PAIR):
    out = {}
    for key, code in zip(("a", "b"), codes):
        row = _row(councils, code)
        out.update({f"{key}_name": row["name"], f"{key}_band_d": row.band_d, f"{key}_bill": row.bill,
                    f"{key}_value": row.value, f"{key}_price": row.price, f"{key}_rate": row.rate_mix,
                    f"{key}_rate_press": row.rate_press, f"{key}_share_ad": row.share_ad})
    out["gap_mix"] = out["a_rate"] / out["b_rate"]
    out["gap_press"] = out["a_rate_press"] / out["b_rate_press"]
    return out


def extremes(councils):
    out = {}
    for key, column in (("mix", "rate_mix"), ("press", "rate_press")):
        ranked = councils.dropna(subset=[column]).sort_values(column)
        high, low = ranked.iloc[-1], ranked.iloc[0]
        out.update({f"high_{key}_name": high["name"], f"high_{key}_rate": high[column],
                    f"low_{key}_name": low["name"], f"low_{key}_rate": low[column],
                    f"gap_{key}": high[column] / low[column]})
    return out


def regions(frame):
    first, last = frame.date.min(), frame.date.max()
    out = {"base": f"{first:%Y-%m}", "latest": f"{last:%Y-%m}"}
    for key, code in (("london", "E12000007"), ("north_east", "E12000001"), ("england", config.ENGLAND)):
        series = frame[frame.code == code].set_index("date").price
        if first in series.index and last in series.index:
            out.update({f"{key}_start": series[first], f"{key}_end": series[last],
                        f"{key}_x": series[last] / series[first]})
    if "london_x" in out and "north_east_x" in out:
        out["london_vs_north_east"] = out["london_x"] / out["north_east_x"]
    return out


def surcharge(councils, council=config.SURCHARGE_COUNCIL, compare=config.COMPARE_COUNCIL,
              values=config.SURCHARGE_VALUES):
    home, other = _row(councils, council), _row(councils, compare)
    band_h = home.band_d * config.BAND_RATIO["H"]
    out = {"council": home["name"], "band_h": band_h, "compare": other["name"], "compare_rate": other.rate_mix}
    for value in values:
        label = f"{value / 1e6:g}m"
        charge = float(compute.surcharge([value])[0])
        out.update({f"charge_{label}": charge, f"rate_{label}_now": band_h / value,
                    f"rate_{label}_with": (band_h + charge) / value})
    top = f"{max(values) / 1e6:g}m"
    out["compare_vs_top"] = other.rate_mix / out[f"rate_{top}_with"]
    total = councils.sales_2m.sum()
    leader = councils.sort_values("sales_2m").iloc[-1]
    out.update({"sales_2m": total, "london_share": councils[councils.region == "London"].sales_2m.sum() / total,
                "top_name": leader["name"], "top_sales": leader.sales_2m, "top_share": leader.sales_2m / total})
    return out


def energy(councils, england):
    """Fuel-poor households outside Bands A-D: a proportional estimate (est) between two bounds (min, max)."""
    out = {"share_ad": england["share_ad"], "fuel_poor": england["fuel_poor"], "fp_rate": england["fp_rate"]}
    for suffix, key in (("est", "fp_outside_ad"), ("min", "fp_outside_ad_min"), ("max", "fp_outside_ad_max")):
        if england.get(key) is not None:
            out[f"outside_{suffix}"] = england[key]
            out[f"outside_share_{suffix}"] = england[key] / england["fuel_poor"]
    if "outside_share_est" in out:
        out["inside_share_est"] = 1 - out["outside_share_est"]
    known = councils.dropna(subset=["fp_outside_ad", "fuel_poor"])
    for rank, (_, row) in enumerate(known.nlargest(3, "fp_outside_ad").iterrows(), start=1):
        out.update({f"top{rank}_name": row["name"], f"top{rank}_outside": row.fp_outside_ad,
                    f"top{rank}_share": row.fp_outside_ad / row.fuel_poor})
    # the councils labelled in figure 5: fewest homes in Bands A-D
    sizable = known[known.fuel_poor >= MIN_FUEL_POOR]
    for rank, (_, row) in enumerate(sizable.nsmallest(5, "share_ad").iterrows(), start=1):
        out.update({f"lab{rank}_name": row["name"], f"lab{rank}_share_ad": row.share_ad, f"lab{rank}_fp_rate": row.fp_rate,
                    f"lab{rank}_miss_est": row.fp_outside_ad / row.fuel_poor})
        for suffix in ("min", "max"):
            column = f"fp_outside_ad_{suffix}"
            if column in row and pd.notna(row[column]):
                out[f"lab{rank}_miss_{suffix}"] = row[column] / row.fuel_poor
    total = known.fp_outside_ad.sum()
    out["top10_outside_share"] = known.nlargest(10, "fp_outside_ad").fp_outside_ad.sum() / total
    out["london_outside_share"] = known[known.region == "London"].fp_outside_ad.sum() / total
    return out


def flat_tax(msoa, neutral):
    """Homes in areas whose average bill would fall, and what each rate raises, as in figure 6."""
    homes = msoa.dwellings.sum()
    bills = (msoa.bill * msoa.dwellings).sum()

    def outcome(rates):
        less = msoa.dwellings * (rates * msoa.value < msoa.bill)
        by = pd.DataFrame({"lad": msoa.lad, "less": less, "homes": msoa.dwellings}).groupby("lad").sum()
        return {"less": less.sum() / homes, "councils_more": int((by.less / by.homes < 0.5).sum()),
                "revenue": (rates * msoa.value * msoa.dwellings).sum() / bills}

    fairer, flat, local = outcome(config.FAIRER_SHARE_RATE), outcome(neutral), outcome(msoa.r_local)
    by_income = slope_marks(msoa)
    if "income_group" in msoa:
        for group in range(1, config.INCOME_GROUPS + 1):
            part = msoa[msoa.income_group == group]
            homes_in = part.dwellings.sum()
            if homes_in:
                by_income[f"income{group}_less_neutral"] = (part.dwellings * (neutral * part.value < part.bill)).sum() / homes_in
                by_income[f"income{group}_less_fs"] = (part.dwellings * (config.FAIRER_SHARE_RATE * part.value < part.bill)).sum() / homes_in
                by_income[f"income{group}_mean"] = (part.income * part.dwellings).sum() / homes_in
                if "net_income" in part:
                    income_total = (part.net_income * part.dwellings).sum()
                    if income_total:
                        by_income[f"income{group}_burden_today"] = (part.bill * part.dwellings).sum() / income_total
                        by_income[f"income{group}_burden_neutral"] = (neutral * part.value * part.dwellings).sum() / income_total
                        by_income[f"income{group}_burden_fs"] = (config.FAIRER_SHARE_RATE * part.value * part.dwellings).sum() / income_total
    return {**by_income,"fs_rate": config.FAIRER_SHARE_RATE, "fs_revenue": fairer["revenue"], "fs_less": fairer["less"],
            "fs_councils_more": fairer["councils_more"], "neutral_rate": neutral, "neutral_less": flat["less"],
            "neutral_councils_more": flat["councils_more"], "local_less": local["less"],
            "local_councils_more": local["councils_more"], "councils": int(msoa.lad.nunique())}


def collect(tables, summary, results):
    england = summary["england"]
    councils = tables["councils"]
    return {
        "data": {"homes": england["dwellings"], "areas": england["msoas"],
                 "councils": int(councils.band_d.notna().sum()), "sales": england["sales_used"],
                 "sales_from": summary["sales_window"][0], "sales_to": summary["sales_window"][1],
                 "price_month": summary["price_month"], "fallback_share": england["msoa_fallback_share"],
                 "bill": england["bill_per_dwelling"], "value": england["value_per_dwelling"],
                 "rate": england["rate_mix"], "checks_passed": sum(r["status"] == "pass" for r in results),
                 "checks": len(results)},
        "policy": {"fairer_share_rate": config.FAIRER_SHARE_RATE, "surcharge_threshold": config.SURCHARGE[0][0],
                   "surcharge_min": config.SURCHARGE[0][1], "surcharge_max": config.SURCHARGE[-1][1]},
        "fig1": staircase(tables["bins"]),
        "pair": pair(councils),
        "fig2": regions(tables["regions"]),
        "fig3": extremes(councils),
        "fig4": surcharge(councils),
        "fig5": energy(councils, england),
        "fig6": flat_tax(tables["msoa"], england["revenue_neutral_rate"]),
    }


def slope_marks(msoa):
    """How steeply bills rise with value. theta_today: the elasticity of the average bill with respect to the average
    value across areas (weighted by homes). theta_equal: the elasticity at which a bill raising today's total, in
    proportion to value**theta, takes the same share of household income in the poorest and richest fifths of areas."""
    w, lv, lb = msoa.dwellings, np.log(msoa.value), np.log(msoa.bill)
    mv, mb = np.average(lv, weights=w), np.average(lb, weights=w)
    marks = {"theta_today": float(np.average((lv - mv) * (lb - mb), weights=w) / np.average((lv - mv) ** 2, weights=w))}
    denominator = "net_income" if "net_income" in msoa else ("income" if "income" in msoa else None)
    if denominator and "income_group" in msoa:
        total = (w * msoa.bill).sum()
        top = msoa.income_group.max()
        def gap(theta):
            raw = msoa.value ** theta
            new = raw * total / (w * raw).sum()
            share = lambda part: (new[part.index] * part.dwellings).sum() / (part[denominator] * part.dwellings).sum()
            return share(msoa[msoa.income_group == 1]) - share(msoa[msoa.income_group == top])
        lo, hi = 0.0, 2.0
        if gap(lo) > 0 > gap(hi):
            for _ in range(50):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if gap(mid) > 0 else (lo, mid)
            marks["theta_equal"] = (lo + hi) / 2
    return marks
