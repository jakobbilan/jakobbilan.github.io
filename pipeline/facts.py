"""Every number the page's text quotes, stored in summary.json under "facts".

The page fills <span data-stat="facts.…"> elements from these values, so sentences
stay in step with the charts after each rebuild. Values keep full precision here;
rounding happens on the page through data-format.
"""

import pandas as pd

from . import compute, config


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
    out = {"share_ad": england["share_ad"], "fuel_poor": england["fuel_poor"], "fp_rate": england["fp_rate"]}
    outside = england.get("fp_outside_ad")
    if outside:
        out.update({"outside_max": outside, "outside_share_max": outside / england["fuel_poor"],
                    "inside_share_min": 1 - outside / england["fuel_poor"]})
    top = councils.dropna(subset=["fp_outside_ad"]).nlargest(3, "fp_outside_ad")
    for rank, (_, row) in enumerate(top.iterrows(), start=1):
        out.update({f"top{rank}_name": row["name"], f"top{rank}_outside": row.fp_outside_ad,
                    f"top{rank}_share": row.fp_outside_ad / row.fuel_poor})
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
    return {"fs_rate": config.FAIRER_SHARE_RATE, "fs_revenue": fairer["revenue"], "fs_less": fairer["less"],
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
