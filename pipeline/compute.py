"""Calculations on tidy tables: bills, values, effective rates and the flat-tax rate.

Every area gets two numbers, an average annual bill and an average current
value; everything shown on the page is a ratio or a sum of those two.
"""

import numpy as np
import pandas as pd

from . import config

RATIOS = pd.Series(config.BAND_RATIO)


def bills_by_band_mix(counts, band_d, key="lad"):
    """Average gross bill per home: council Band D times the statutory ratio, weighted by band counts."""
    frame = counts.merge(band_d[[key, "band_d"]], on=key, how="inner")
    weighted = frame[config.BANDS].mul(RATIOS[config.BANDS].values, axis=1).sum(axis=1)
    frame["bill"] = frame.band_d * weighted / frame.dwellings.where(frame.dwellings > 0)
    frame["share_ad"] = frame[config.ENERGY_PAYMENT_BANDS].sum(axis=1) / frame.dwellings.where(frame.dwellings > 0)
    return frame


def surcharge(value):
    """Annual High Value Council Tax Surcharge for a home of a given value (zero below £2m)."""
    value = np.asarray(value, dtype=float)
    charge = np.zeros_like(value)
    for floor, amount in config.SURCHARGE:
        charge = np.where(value >= floor, amount, charge)
    return charge


def type_prices(msoa_types, msoa_medians, lad_medians, lad_overall, msoa_lad):
    """Price for each property type in each MSOA, falling back to council medians where sales are thin."""
    frame = msoa_types.merge(msoa_lad, on="msoa", how="left")
    for kind in config.PPD_TYPES:
        own = msoa_medians[msoa_medians.ptype == kind].set_index("msoa")
        own = own[own.n >= config.MIN_SALES]["median"]
        council = lad_medians[lad_medians.ptype == kind].set_index("lad")["median"]
        price = frame.msoa.map(own)
        frame[f"fallback_{kind}"] = price.isna()
        price = price.fillna(frame.lad.map(council)).fillna(frame.lad.map(lad_overall))
        frame[f"price_{kind}"] = price
    # Price Paid does not record bungalows separately: price them between detached and semi-detached
    frame["price_B"] = frame[["price_D", "price_S"]].mean(axis=1)
    houses = frame[config.PPD_TYPES].sum(axis=1)
    mix_price = sum(frame[k] * frame[f"price_{k}"] for k in config.PPD_TYPES) / houses.where(houses > 0)
    frame["price_O"] = mix_price.fillna(frame.lad.map(lad_overall))
    return frame


def stock_value(prices):
    """Average value per home in each MSOA: type prices weighted by the area's stock of each type."""
    kinds = config.PPD_TYPES + ["B", "O"]
    counts = prices[kinds].clip(lower=0)
    total = counts.sum(axis=1)
    value = sum(counts[k] * prices[f"price_{k}"] for k in kinds) / total.where(total > 0)
    fallback = sum(counts[k] * prices[f"fallback_{k}"] for k in config.PPD_TYPES) / total.where(total > 0)
    return pd.DataFrame({"msoa": prices.msoa, "value": value, "fallback_share": fallback})


def revenue_neutral(frame, by=None):
    """Flat rate on value that raises the same as today's bills: total bills over total value."""
    bills = frame.bill * frame.dwellings
    values = frame.value * frame.dwellings
    if by is None:
        return bills.sum() / values.sum()
    return (bills.groupby(frame[by]).sum() / values.groupby(frame[by]).sum()).rename("r_local")


def weighted_quantile(values, weights, q):
    order = np.argsort(values)
    values, weights = np.asarray(values)[order], np.asarray(weights)[order]
    cumulative = np.cumsum(weights) - 0.5 * weights
    return np.interp(q * weights.sum(), cumulative, values)


def rate_bins(frame, n=40):
    """Effective rate by value: areas sorted by value and cut into n groups of equal numbers of homes."""
    frame = frame.dropna(subset=["value", "rate"]).sort_values("value").copy()
    share = (frame.dwellings.cumsum() - 0.5 * frame.dwellings) / frame.dwellings.sum()
    frame["bin"] = np.minimum((share * n).astype(int), n - 1)
    rows = []
    for number, group in frame.groupby("bin"):
        w = group.dwellings.values
        rows.append({
            "bin": int(number),
            "value": weighted_quantile(group.value.values, w, 0.5),
            "rate_p25": weighted_quantile(group.rate.values, w, 0.25),
            "rate": weighted_quantile(group.rate.values, w, 0.5),
            "rate_p75": weighted_quantile(group.rate.values, w, 0.75),
            "dwellings": int(w.sum()),
        })
    return pd.DataFrame(rows)


def regional_prices(hpi, base_dates=("1991-04-01", "1995-01-01")):
    """Average price by English region, and as a multiple of its level when the bands were fixed."""
    codes = list(config.REGIONS) + [config.ENGLAND]
    frame = hpi[hpi.code.isin(codes)][["code", "date", "price"]].dropna().copy()
    base = None
    for candidate in pd.to_datetime(list(base_dates)):
        at_base = frame[frame.date == candidate]
        if at_base.code.nunique() == len(codes):
            base = candidate
            break
    if base is None:
        base = frame.groupby("code").date.min().max()
    frame = frame[frame.date >= base]
    start = frame[frame.date == base].set_index("code").price
    frame["multiple"] = frame.price / frame.code.map(start)
    frame["region"] = frame.code.map({**config.REGIONS, config.ENGLAND: "England"})
    return frame.sort_values(["code", "date"]).reset_index(drop=True), base
