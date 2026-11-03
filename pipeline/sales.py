"""Sale prices from HM Land Registry Price Paid Data, matched to MSOAs and brought to one month.

Yearly files have no header row; columns follow HM Land Registry's published order.
Category A rows are standard sales at market value; category B adds repossessions,
buy-to-let and company purchases, which are kept only for counting £2m+ sales.
"""

import csv

import duckdb
import pandas as pd

from . import config, read

PPD_COLUMNS = ["id", "price", "date", "postcode", "ptype", "old_new", "duration", "paon", "saon",
               "street", "locality", "town", "district", "county", "category", "status"]


def index_tables(hpi):
    """Monthly price index by council and type, and its value in the reference month."""
    lads = hpi[hpi.code.str.match(r"^E0[6-9]\d{6}$")].copy()
    counts = lads.dropna(subset=["index"]).groupby("date").code.nunique()
    reference = counts[counts >= 0.95 * counts.max()].index.max()
    long = []
    for kind in config.PPD_TYPES:
        part = lads[["code", "date", f"index_{kind}"]].rename(columns={f"index_{kind}": "idx"})
        part["ptype"] = kind
        long.append(part)
    part = lads[["code", "date", "index"]].rename(columns={"index": "idx"})
    part["ptype"] = "*"
    long.append(part)
    idx = pd.concat(long).dropna(subset=["idx"]).rename(columns={"code": "lad", "date": "month"})
    ref = idx[idx.month == reference][["lad", "ptype", "idx"]].rename(columns={"idx": "ref"})
    return idx, ref, reference


def lookup_header(path):
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as handle:
        return next(csv.reader(handle))


def _quote(path):
    return "'" + str(path).replace("'", "''") + "'"


def summarise(sales_paths, lookup_csv, hpi):
    """Medians by MSOA and type, council fallbacks, £2m+ counts and the match rate."""
    fields = read.postcode_fields(lookup_header(lookup_csv))
    idx, ref, reference = index_tables(hpi)
    con = duckdb.connect()
    con.register("idx_frame", idx)
    con.register("ref_frame", ref)

    live = f"AND {fields['doterm']} IS NULL" if fields["doterm"] else ""
    con.execute(f"""
        CREATE TEMP TABLE pc AS
        SELECT upper(replace("{fields['postcode']}", ' ', '')) AS pc,
               "{fields['msoa']}" AS msoa, "{fields['lad']}" AS lad
               {f', "{fields["lsoa"]}" AS lsoa' if fields['lsoa'] else ", NULL AS lsoa"}
        FROM read_csv({_quote(lookup_csv)}, header=true, all_varchar=true)
        WHERE "{fields['msoa']}" LIKE 'E02%' OR "{fields['msoa']}" LIKE 'W02%'
    """)
    # terminated postcodes still appear on older sales, so keep them for matching
    con.execute("CREATE TEMP TABLE pc_unique AS SELECT pc, any_value(msoa) AS msoa, any_value(lad) AS lad "
                "FROM pc GROUP BY pc")

    columns = ", ".join(f"'{c}': 'VARCHAR'" for c in PPD_COLUMNS)
    paths = "[" + ", ".join(_quote(p) for p in sales_paths) + "]"
    con.execute(f"""
        CREATE TEMP TABLE sales AS
        SELECT id, TRY_CAST(price AS DOUBLE) AS price,
               TRY_CAST(substr(date, 1, 10) AS DATE) AS sold,
               upper(replace(postcode, ' ', '')) AS pc, ptype, category
        FROM read_csv({paths}, header=false, columns={{{columns}}}, null_padding=true,
                      quote='"', escape='"', ignore_errors=true)
        WHERE price IS NOT NULL
        QUALIFY row_number() OVER (PARTITION BY id ORDER BY sold DESC) = 1
    """)

    latest = con.execute("SELECT max(date_trunc('month', sold)) FROM sales").fetchone()[0]
    cutoff = (pd.Timestamp(latest) - pd.DateOffset(months=config.LAG_MONTHS - 1)).date()
    start = pd.Timestamp(config.SALES_FROM).date()

    con.execute(f"""
        CREATE TEMP TABLE adj AS
        SELECT s.price, s.sold, s.ptype, p.msoa, p.lad,
               s.price * coalesce(r.ref / nullif(i.idx, 0), ra.ref / nullif(ia.idx, 0), 1) AS price_adj
        FROM sales s
        JOIN pc_unique p USING (pc)
        LEFT JOIN idx_frame i ON i.lad = p.lad AND i.ptype = s.ptype
             AND i.month = date_trunc('month', least(s.sold, DATE '{reference.date()}'))
        LEFT JOIN ref_frame r ON r.lad = p.lad AND r.ptype = s.ptype
        LEFT JOIN idx_frame ia ON ia.lad = p.lad AND ia.ptype = '*'
             AND ia.month = date_trunc('month', least(s.sold, DATE '{reference.date()}'))
        LEFT JOIN ref_frame ra ON ra.lad = p.lad AND ra.ptype = '*'
        WHERE s.category = 'A' AND s.ptype IN ('D', 'S', 'T', 'F') AND p.msoa LIKE 'E02%'
          AND s.sold >= DATE '{start}' AND s.sold < DATE '{cutoff}'
    """)

    msoa = con.execute("SELECT msoa, ptype, median(price_adj) AS median, count(*) AS n "
                       "FROM adj GROUP BY 1, 2").df()
    lad = con.execute("SELECT lad, ptype, median(price_adj) AS median, count(*) AS n "
                      "FROM adj GROUP BY 1, 2").df()
    lad_all = con.execute("SELECT lad, median(price_adj) AS median FROM adj GROUP BY 1").df()
    msoa_sales = con.execute("SELECT msoa, count(*) AS sales FROM adj GROUP BY 1").df()
    high = con.execute(f"""
        SELECT p.lad, count(*) FILTER (WHERE s.price >= 2000000) AS sales_2m, count(*) AS sales_all
        FROM sales s JOIN pc_unique p USING (pc)
        WHERE p.msoa LIKE 'E02%' AND s.sold >= DATE '{start}' AND s.sold < DATE '{cutoff}'
        GROUP BY 1
    """).df()
    matched = con.execute(f"""
        SELECT avg(CASE WHEN p.pc IS NULL THEN 0 ELSE 1 END)
        FROM sales s LEFT JOIN pc_unique p USING (pc)
        WHERE s.category = 'A' AND s.sold >= DATE '{start}' AND s.sold < DATE '{cutoff}'
          AND coalesce(s.pc, '') <> ''
    """).fetchone()[0]
    msoa_lad = con.execute("SELECT msoa, mode(lad) AS lad FROM pc WHERE msoa LIKE 'E02%' GROUP BY 1").df()
    lsoa_lad = con.execute("SELECT lsoa, mode(lad) AS lad FROM pc "
                           "WHERE lsoa LIKE 'E01%' GROUP BY 1").df()
    n_sales = con.execute("SELECT count(*) FROM adj").fetchone()[0]
    con.close()

    return {
        "msoa": msoa, "lad": lad, "lad_all": lad_all.set_index("lad")["median"], "msoa_sales": msoa_sales,
        "high_value": high, "match_rate": matched, "msoa_lad": msoa_lad, "lsoa_lad": lsoa_lad,
        "reference": reference, "window": (start, cutoff), "n_sales": n_sales,
    }
