"""Paths, statutory parameters and source locations for the council tax project."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "pipeline" / "cache"
OUT_DATA = ROOT / "project" / "data"
OUT_GEO = ROOT / "project" / "geo"
FIXTURES = ROOT / "pipeline" / "fixtures"

USER_AGENT = "council-tax-project/1.0 (+https://github.com/jakobbilan/jakobbilan.github.io)"

# Local Government Finance Act 1992, s.5: bills in the proportion 6:7:8:9:11:13:15:18
BANDS = list("ABCDEFGH")
BAND_RATIO = {"A": 6 / 9, "B": 7 / 9, "C": 8 / 9, "D": 1.0,
              "E": 11 / 9, "F": 13 / 9, "G": 15 / 9, "H": 18 / 9}

# High Value Council Tax Surcharge from April 2028 (HM Treasury fact sheet, updated 28 October 2026):
# lower edge of each value band and its annual charge
SURCHARGE = [(2_000_000, 2_500), (2_500_000, 3_500), (3_500_000, 5_000), (5_000_000, 7_500)]

# Fairer Share's proposed proportional property tax (replaces council tax and stamp duty)
FAIRER_SHARE_RATE = 0.0048

# Household Energy Payment, Budget 28 October 2026: £100 to homes in Bands A-D
ENERGY_PAYMENT_BANDS = list("ABCD")

# MHCLG, Council Tax levels 2026-27: used as sanity checks, not as inputs
MHCLG_REQUIREMENT = 46.806e9
MHCLG_PER_DWELLING = 1868

# Sales window: from this date to LAG_MONTHS before the latest price index month
SALES_FROM = "2024-01-01"
LAG_MONTHS = 2
MIN_SALES = 10

# GOV.UK pages whose attachments change name every year; {placeholders} filled at run time
GOVUK_PAGES = {
    "ctsop": "/government/statistics/council-tax-stock-of-properties-{year}",
    "levels": "/government/statistics/council-tax-levels-set-by-local-authorities-in-england-{fy0}-to-{fy1}",
    "fuel_poverty": "/government/statistics/sub-regional-fuel-poverty-data-{pub}-{data}-data",
}
ATTACHMENT_PATTERNS = {
    "ctsop_bands": r"CTSOP[_ ]?1[._ ]1.*\.zip$",
    "ctsop_types": r"CTSOP[_ ]?3[._ ]1.*\.zip$",
    "levels": r"Tables?_1-9.*\.ods$",
    "fuel_poverty": r"fuel-poverty-sub-regional.*\.xlsx$",
}

PPD_URL = "https://price-paid-data.publicdata.landregistry.gov.uk/pp-{year}.csv"
HPI_URL = ("https://publicdata.landregistry.gov.uk/market-trend-data/"
           "house-price-index-data/UK-HPI-full-file-{ym}.csv")

ARCGIS_SEARCH = "https://www.arcgis.com/sharing/rest/search"
ARCGIS_ITEM_DATA = "https://www.arcgis.com/sharing/rest/content/items/{item}/data"
POSTCODE_LOOKUP_TITLE = "Postcode to OA (2021) to LSOA to MSOA to LAD"
ONSPD_FALLBACK_ITEM = "6fff67d204fd4f339591ed667a6e3642"  # ONS Postcode Directory (May 2026)

HEXJSON_URL = ("https://raw.githubusercontent.com/odileeds/hexmaps/"
               "17982f91f7f21b84b6c876f952437c8986172811/maps/uk-local-authority-districts-2025.hexjson")

REGIONS = {
    "E12000001": "North East",
    "E12000002": "North West",
    "E12000003": "Yorkshire and The Humber",
    "E12000004": "East Midlands",
    "E12000005": "West Midlands",
    "E12000006": "East of England",
    "E12000007": "London",
    "E12000008": "South East",
    "E12000009": "South West",
}
ENGLAND = "E92000001"

# Price Paid property types, and how the Valuation Office types map onto them
PPD_TYPES = ["D", "S", "T", "F"]

# Councils and values the page's text quotes (figures 1, 3 and 4)
PAIR = ("E07000117", "E09000033")            # Burnley, Westminster
SURCHARGE_COUNCIL = "E09000033"              # Band H home in Westminster
COMPARE_COUNCIL = "E07000117"                # against the average home in Burnley
SURCHARGE_VALUES = (2_000_000, 5_000_000, 10_000_000)

# ONS: model-based income estimates for small areas (MSOAs). Editions are listed newest first on this page
INCOME_PAGE = ("https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/datasets/"
               "smallareaincomeestimatesformiddlelayersuperoutputareasenglandandwales")
INCOME_GROUPS = 5            # fifths of areas by income, each holding a fifth of homes
