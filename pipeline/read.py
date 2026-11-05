"""Readers for the source files. Each returns a tidy DataFrame.

Layouts are detected from headers and area codes rather than fixed positions,
because column names and table layouts have changed between annual releases.
"""

import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from . import config

AREA_CODE = re.compile(r"^[EWSNK]\d{8}$")
LAD_CODE = re.compile(r"^E0[6-9]\d{6}$")
SUPPRESSED = {"", "-", "..", "[c]", "[z]", "[x]", "[low]", "*", "nan", "none", "null"}


def to_number(values):
    """Numbers from published tables: drop commas and £, treat suppression markers as missing."""
    text = pd.Series(values, dtype="object").astype(str).str.strip()
    text = text.str.replace(",", "", regex=False).str.replace("£", "", regex=False)
    text = text.where(~text.str.lower().isin(SUPPRESSED))
    return pd.to_numeric(text, errors="coerce")


def level_of(code):
    prefix = str(code)[:3]
    return {"E01": "lsoa", "E02": "msoa", "E06": "lad", "E07": "lad", "E08": "lad", "E09": "lad",
            "E10": "county", "E12": "region", "E92": "england"}.get(prefix, "other")


def normalise_columns(frame):
    frame = frame.copy()
    frame.columns = [re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_") for c in frame.columns]
    return frame


def code_column(frame, preferred=("ecode", "area_code", "code", "geography_code", "area_codes")):
    for name in preferred:
        if name in frame.columns:
            return name
    shares = {c: frame[c].astype(str).str.strip().str.match(AREA_CODE).mean() for c in frame.columns}
    best = max(shares, key=shares.get)
    if shares[best] < 0.5:
        raise ValueError("no column of area codes found")
    return best


def read_zipped_csv(path, member_pattern=None):
    """The largest CSV in a zip archive (or the one matching member_pattern)."""
    with zipfile.ZipFile(path) as archive:
        members = [m for m in archive.infolist() if m.filename.lower().endswith(".csv")]
        if member_pattern:
            matching = [m for m in members if re.search(member_pattern, m.filename, re.IGNORECASE)]
            members = matching or members
        if not members:
            raise ValueError(f"no CSV inside {path}")
        member = max(members, key=lambda m: m.file_size)
        with archive.open(member) as handle:
            frame = pd.read_csv(handle, dtype=str, encoding="utf-8-sig", encoding_errors="replace",
                                keep_default_na=False, low_memory=False)
    return normalise_columns(frame)


def extract_largest_csv(path, target):
    """Unpack the largest CSV from a zip archive to target (for DuckDB)."""
    target = Path(target)
    if target.exists() and target.stat().st_size > 0 and target.stat().st_mtime >= Path(path).stat().st_mtime:
        return target
    with zipfile.ZipFile(path) as archive:
        members = [m for m in archive.infolist() if m.filename.lower().endswith(".csv")]
        member = max(members, key=lambda m: m.file_size)
        with archive.open(member) as source, open(target, "wb") as sink:
            while chunk := source.read(1 << 20):
                sink.write(chunk)
    return target


# Valuation Office: properties by band (CTSOP1.1) ------------------------------------------

BAND_WIDE = re.compile(r"^band_?([a-i])$")


def read_band_counts(path):
    """Homes by Council Tax band for every English area in CTSOP1.1 (LSOA, MSOA, LAD and above)."""
    frame = read_zipped_csv(path) if str(path).endswith(".zip") else normalise_columns(
        pd.read_csv(path, dtype=str, keep_default_na=False))
    code = code_column(frame)
    name = "area_name" if "area_name" in frame.columns else None
    wide = {BAND_WIDE.match(c).group(1).upper(): c for c in frame.columns if BAND_WIDE.match(c)}

    if set(config.BANDS) <= set(wide):
        out = pd.DataFrame({b: to_number(frame[wide[b]]).values for b in config.BANDS})
    elif "band" in frame.columns:
        count = next(c for c in ("all_properties", "number_of_properties", "count", "properties")
                     if c in frame.columns)
        long = pd.DataFrame({"code": frame[code].str.strip().values, "band": frame["band"].str.strip().str.upper().values,
                             "n": to_number(frame[count]).values})
        out = (long[long.band.isin(config.BANDS)]
               .pivot_table(index="code", columns="band", values="n", aggfunc="sum")
               .reindex(columns=config.BANDS).reset_index())
        out.columns.name = None
        names = frame.groupby(frame[code].str.strip())[name].first() if name else None
        out.insert(1, "name", out.code.map(names).values if name else "")
        out["level"] = out.code.map(level_of)
        return _finish_bands(out)
    else:
        raise ValueError("no band columns in CTSOP1.1")

    out.insert(0, "code", frame[code].str.strip().values)
    out.insert(1, "name", frame[name].str.strip().values if name else "")
    out["level"] = out.code.map(level_of)
    return _finish_bands(out)


def _finish_bands(out):
    out = out[out.code.str.startswith("E")].copy()
    out[config.BANDS] = out[config.BANDS].fillna(0)
    out["dwellings"] = out[config.BANDS].sum(axis=1)
    return out.drop_duplicates("code").reset_index(drop=True)


# Valuation Office: properties by band and type (CTSOP3.1) --------------------------------

def property_type(column):
    """Map a CTSOP3.1 column to a Price Paid type: D, S, T, F; B for bungalows; O for the rest."""
    c = column.lower()
    if any(word in c for word in ("all_prop", "geography", "ecode", "ba_code", "area_name", "band")):
        return None
    if "bung" in c:
        return "B"
    if "semi" in c:
        return "S"
    if "detach" in c:
        return "D"
    if "terr" in c:
        return "T"
    if "flat" in c or "mais" in c:
        return "F"
    if any(word in c for word in ("annex", "caravan", "houseboat", "mobile", "unknown", "unkw", "other")):
        return "O"
    return None


def read_type_counts(path, level="msoa"):
    """Homes by property type for each area at one level (summed over bands)."""
    frame = read_zipped_csv(path) if str(path).endswith(".zip") else normalise_columns(
        pd.read_csv(path, dtype=str, keep_default_na=False))
    code = code_column(frame)
    frame = frame[frame[code].str.strip().map(level_of) == level].copy()
    frame["_code"] = frame[code].str.strip()

    if "band" in frame.columns:
        band = frame["band"].str.strip().str.upper()
        has_all = band.isin(["ALL", "ALL BANDS", "TOTAL"]).any()
        frame = frame[band.isin(["ALL", "ALL BANDS", "TOTAL"])] if has_all else frame[band.isin(config.BANDS)]

    groups = {}
    for column in frame.columns:
        kind = property_type(column)
        if kind:
            groups.setdefault(kind, []).append(column)
    if not {"D", "S", "T", "F"} <= set(groups):
        raise ValueError(f"CTSOP3.1 type columns not recognised: {list(frame.columns)}")

    out = pd.DataFrame({"code": frame["_code"].values})
    for kind, columns in groups.items():
        totals = [c for c in columns if "total" in c]
        use = totals or columns
        out[kind] = np.nansum(np.column_stack([to_number(frame[c]).values for c in use]), axis=1)
    out = out.groupby("code", as_index=False).sum()
    for kind in ("B", "O"):
        if kind not in out:
            out[kind] = 0.0
    return out[["code", "D", "S", "T", "F", "B", "O"]]


# MHCLG: area Band D by billing authority (Tables 1-9) ------------------------------------

def _sheet_score(sheet):
    sheet = sheet.fillna("").astype(str)
    text = " ".join(sheet.values.ravel()[:4000]).lower()
    codes = sheet.apply(lambda col: col.str.strip().str.match(LAD_CODE)).sum().max()
    score = 3 * ("table 9" in text) + 2 * ("2 adults" in text or "two adults" in text) + 2 * (codes >= 290)
    return score, codes


def read_band_d(path):
    """Area Band D for every English billing authority, including parish precepts."""
    sheets = pd.read_excel(path, engine="odf" if str(path).endswith(".ods") else None,
                           sheet_name=None, header=None, dtype=str)
    ranked = sorted(sheets.items(), key=lambda item: _sheet_score(item[1]), reverse=True)
    for _, sheet in ranked:
        result = _band_d_from_sheet(sheet)
        if result is not None and len(result) >= 250:
            return result
    raise ValueError("Band D column not found in the council tax levels tables")


def _band_d_from_sheet(sheet):
    sheet = sheet.fillna("")
    is_code = sheet.apply(lambda col: col.astype(str).str.strip().str.match(LAD_CODE))
    if is_code.values.sum() < 250:
        return None
    code_col = is_code.sum().idxmax()
    first_data_row = is_code[code_col].idxmax()
    header = sheet.iloc[:first_data_row]

    band_d_col = None
    for column in sheet.columns:
        cells = header[column].astype(str).str.strip().str.lower()
        if cells.str.contains(r"\bband\s*d\b").any() or cells.eq("d").any():
            band_d_col = column
            break
    if band_d_col is None:
        return None

    name_col = None
    for column in sheet.columns:
        if column == code_col:
            continue
        values = sheet.loc[is_code[code_col], column].astype(str)
        if values.str.contains(r"[A-Za-z]{3}").mean() > 0.9:
            name_col = column
            break

    rows = sheet[is_code[code_col]]
    out = pd.DataFrame({
        "lad": rows[code_col].astype(str).str.strip().values,
        "name": rows[name_col].astype(str).str.strip().values if name_col is not None else "",
        "band_d": to_number(rows[band_d_col]).values,
    })
    out = out.dropna(subset=["band_d"]).drop_duplicates("lad")
    return out if out.band_d.between(500, 5000).mean() > 0.95 else None


# HM Land Registry: UK House Price Index full file ----------------------------------------

HPI_COLUMNS = {
    "Date": "date", "RegionName": "name", "AreaCode": "code", "AveragePrice": "price", "Index": "index",
    "DetachedIndex": "index_D", "SemiDetachedIndex": "index_S", "TerracedIndex": "index_T", "FlatIndex": "index_F",
    "DetachedPrice": "price_D", "SemiDetachedPrice": "price_S", "TerracedPrice": "price_T", "FlatPrice": "price_F",
}


def read_hpi(path):
    frame = pd.read_csv(path, usecols=lambda c: c in HPI_COLUMNS, dtype=str)
    frame = frame.rename(columns=HPI_COLUMNS)
    frame["date"] = pd.to_datetime(frame["date"], dayfirst=True, errors="coerce")
    for column in frame.columns:
        if column.startswith(("price", "index")):
            frame[column] = to_number(frame[column]).values
    return frame.dropna(subset=["date", "code"]).reset_index(drop=True)


# ONS postcode lookup ------------------------------------------------------------------------

def postcode_fields(header):
    """Column names for postcode, MSOA, LSOA, LAD and termination date in either ONS product."""
    lower = {c.lower(): c for c in header}

    def pick(*names):
        for n in names:
            if n in lower:
                return lower[n]
        return None

    fields = {
        "postcode": pick("pcds", "pcd8", "pcd7", "pcd"),
        "msoa": pick("msoa21cd", "msoa21"),
        "lsoa": pick("lsoa21cd", "lsoa21"),
        "lad": pick("ladcd", "lad25cd", "lad24cd", "lad23cd", "oslaua", "laua"),
        "doterm": pick("doterm"),
    }
    missing = [k for k in ("postcode", "msoa", "lad") if fields[k] is None]
    if missing:
        raise ValueError(f"postcode lookup lacks {missing}: {header[:20]}")
    return fields


# DESNZ: sub-regional fuel poverty ---------------------------------------------------------

def read_fuel_poverty(path):
    """Households and fuel-poor households for councils (Table 2) and LSOAs (Table 4)."""
    sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=str)
    found = {}
    for _, sheet in sheets.items():
        table = _fuel_poverty_table(sheet)
        if table is None:
            continue
        level = table.code.map(level_of).value_counts().idxmax()
        if level in ("lad", "lsoa") and level not in found:
            found[level] = table[table.code.map(level_of) == level].reset_index(drop=True)
    if "lad" not in found:
        raise ValueError("council-level fuel poverty table not found")
    return found["lad"], found.get("lsoa")


def _fuel_poverty_table(sheet):
    sheet = sheet.fillna("")
    is_code = sheet.apply(lambda col: col.astype(str).str.strip().str.match(AREA_CODE))
    if is_code.values.sum() < 100:
        return None
    code_col = is_code.sum().idxmax()
    first = is_code[code_col].idxmax()
    header = sheet.iloc[:first].astype(str).apply(lambda col: " ".join(col).lower())

    def column_where(test):
        for column, text in header.items():
            if test(text):
                return column
        return None

    households = column_where(lambda t: "households" in t and "fuel" not in t and "proportion" not in t)
    fuel_poor = column_where(lambda t: "fuel" in t and "number" in t)
    share = column_where(lambda t: "proportion" in t or "%" in t)
    if households is None or fuel_poor is None:
        return None
    rows = sheet[is_code[code_col]]
    out = pd.DataFrame({
        "code": rows[code_col].astype(str).str.strip().values,
        "households": to_number(rows[households]).values,
        "fuel_poor": to_number(rows[fuel_poor]).values,
    })
    out["rate"] = (to_number(rows[share]).values / 100) if share is not None else out.fuel_poor / out.households
    return out.dropna(subset=["households", "fuel_poor"])


# ONS: income estimates for small areas --------------------------------------------------

MSOA_CODE = re.compile(r"^[EW]02\d{6}$")
NOT_ESTIMATE = ("confidence", "limit", "interval", "upper", "lower")


def read_income(path):
    """Mean equivalised household disposable income before housing costs, by MSOA.

    The workbook holds one sheet per income measure. The sheet is chosen by the words in its name and title rows,
    the header by the first row of MSOA codes and the column by its label, so a changed layout is tolerated."""
    sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=str)
    best = None
    for name, sheet in sheets.items():
        found = _income_table(name, sheet)
        if found is not None and (best is None or found[1] > best[1]):
            best = found
    if best is None or best[1] < 2:
        raise ValueError("no sheet of net income before housing costs by MSOA")
    return best[0]


def _income_table(name, sheet):
    sheet = sheet.fillna("")
    is_code = sheet.apply(lambda col: col.astype(str).str.strip().str.match(MSOA_CODE))
    if is_code.values.sum() < 100:
        return None
    code_col = is_code.sum().idxmax()
    first = is_code[code_col].idxmax()
    above = sheet.iloc[:first].astype(str)
    header = above.apply(lambda col: " ".join(col).lower())
    title = (str(name) + " " + " ".join(above.values.ravel())).lower()
    score = 0
    score += 2 if ("before housing" in title or "bhc" in title) else 0
    score -= 3 if ("after housing" in title or "ahc" in title) else 0
    score += 1 if "equivalised" in title else 0
    score -= 2 if "total" in title else 0
    rows = is_code[code_col]
    for column, text in header.items():
        if column == code_col or not ("income" in text or "£" in text) or any(w in text for w in NOT_ESTIMATE):
            continue
        values = to_number(sheet.loc[rows, column])
        if values.notna().mean() > 0.9 and values.median() > 1000:
            out = pd.DataFrame({"msoa": sheet.loc[rows, code_col].str.strip().values, "income": values.values})
            return out.dropna(), score
    return None
