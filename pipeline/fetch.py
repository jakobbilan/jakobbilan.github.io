"""Download sources into a local cache and find the newest release of each one.

Annual releases move to new web addresses every year. Rather than hard-coding
them, the GOV.UK Content API is asked for the attachments of each statistics
page, and the price index and postcode lookup are found by date and by title.
"""

import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from html import unescape
from urllib.parse import unquote, urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config

_session = None


def log(message):
    print(f"{time.strftime('%H:%M:%S')}  {message}", file=sys.stderr, flush=True)


def session():
    global _session
    if _session is None:
        retry = Retry(total=5, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=["GET", "HEAD"])
        _session = requests.Session()
        _session.headers["User-Agent"] = config.USER_AGENT
        _session.mount("https://", HTTPAdapter(max_retries=retry))
    return _session


def exists(url):
    """True if the server answers 200 for this address."""
    try:
        response = session().head(url, allow_redirects=True, timeout=60)
        if response.status_code == 405:
            response = session().get(url, stream=True, timeout=60)
            response.close()
        return response.status_code == 200
    except requests.RequestException:
        return False


def download(url, name=None, refresh=False):
    """Fetch a file into the cache once; later runs reuse it unless refresh is set."""
    config.CACHE.mkdir(parents=True, exist_ok=True)
    if name is None:
        parts = urlparse(url).path.strip("/").split("/")
        name = "-".join(parts[-2:]) if "media" in parts else parts[-1]
    target = config.CACHE / name
    if target.exists() and target.stat().st_size > 0 and not refresh:
        log(f"cached   {name}")
        return target
    log(f"download {url}")
    partial = target.with_suffix(target.suffix + ".part")
    with session().get(url, stream=True, timeout=600) as response:
        response.raise_for_status()
        with open(partial, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 20):
                handle.write(chunk)
    partial.replace(target)
    log(f"saved    {name} ({target.stat().st_size / 1e6:.1f} MB)")
    return target


def _collect_urls(node, found):
    if isinstance(node, dict):
        url = node.get("url")
        if isinstance(url, str) and "assets.publishing.service.gov.uk" in url:
            found.append(url)
        for value in node.values():
            _collect_urls(value, found)
    elif isinstance(node, list):
        for value in node:
            _collect_urls(value, found)


def govuk_attachments(path):
    """Attachment links on a GOV.UK page: Content API first, page HTML as fallback."""
    found = []
    try:
        response = session().get(f"https://www.gov.uk/api/content{path}", timeout=60)
        if response.status_code == 200:
            _collect_urls(response.json(), found)
    except (requests.RequestException, json.JSONDecodeError):
        pass
    if not found:
        try:
            response = session().get(f"https://www.gov.uk{path}", timeout=60)
            if response.status_code == 200:
                found = re.findall(r"https://assets\.publishing\.service\.gov\.uk/media/[^\"'<>\s]+",
                                   response.text)
        except requests.RequestException:
            pass
    return list(dict.fromkeys(found))


def find_govuk_file(page_paths, pattern):
    """First attachment whose file name matches pattern, searching pages in order."""
    regex = re.compile(pattern, re.IGNORECASE)
    for path in page_paths:
        for url in govuk_attachments(path):
            if regex.search(Path(urlparse(url).path).name):
                return url, f"https://www.gov.uk{path}"
    raise RuntimeError(f"no attachment matching {pattern!r} on {page_paths}")


def ctsop_pages(today=None):
    year = (today or date.today()).year
    return [config.GOVUK_PAGES["ctsop"].format(year=y) for y in (year, year - 1, year - 2)]


def levels_pages(today=None):
    year = (today or date.today()).year
    return [config.GOVUK_PAGES["levels"].format(fy0=y, fy1=y + 1) for y in (year, year - 1, year - 2)]


def fuel_poverty_pages(today=None):
    year = (today or date.today()).year
    return [config.GOVUK_PAGES["fuel_poverty"].format(pub=y, data=y - 2) for y in (year, year - 1, year - 2)]


def months_back(today, n):
    month = today.year * 12 + today.month - 1 - n
    return month // 12, month % 12 + 1


def latest_hpi_url(today=None):
    """Newest UK House Price Index full file; releases trail the data month by about two months."""
    today = today or date.today()
    for n in range(0, 10):
        year, month = months_back(today, n)
        url = config.HPI_URL.format(ym=f"{year}-{month:02d}")
        if exists(url):
            return url, f"{year}-{month:02d}"
    raise RuntimeError("no UK HPI full file found in the last ten months")


def arcgis_item(title, types=("CSV Collection", "CSV")):
    """Most recently modified public ArcGIS item whose title starts with title."""
    params = {"q": f'title:"{title}"', "f": "json", "num": 50,
              "sortField": "modified", "sortOrder": "desc"}
    try:
        response = session().get(config.ARCGIS_SEARCH, params=params, timeout=60)
        response.raise_for_status()
        results = response.json().get("results", [])
    except (requests.RequestException, json.JSONDecodeError):
        return None
    for item in results:
        if item.get("type") in types and item.get("title", "").startswith(title):
            return item
    return None


def postcode_lookup(refresh=False):
    """Postcode to 2021 MSOA lookup: the small best-fit file, else the full postcode directory."""
    item = arcgis_item(config.POSTCODE_LOOKUP_TITLE)
    if item:
        url = config.ARCGIS_ITEM_DATA.format(item=item["id"])
        return download(url, f"postcode-lookup-{item['id']}.zip", refresh), item["title"], url
    url = config.ARCGIS_ITEM_DATA.format(item=config.ONSPD_FALLBACK_ITEM)
    return download(url, "onspd.zip", refresh), "ONS Postcode Directory", url


def latest_ons_edition(page_url, contains="smallareaincomeestimates"):
    """The newest workbook on an ONS dataset page, which lists its editions newest first."""
    response = session().get(page_url, timeout=60)
    response.raise_for_status()
    links = [unescape(link) for link in re.findall(r'href="([^"]*file\?uri=[^"]*\.xlsx?)"', response.text)]
    links = [link for link in links if contains in unquote(link)]
    if not links:
        raise ValueError(f"no workbook found on {page_url}")
    url = urljoin(page_url, links[0])
    edition = re.search(r"financialyearending(\d{4})", unquote(url))
    return url, (f"financial year ending {edition.group(1)}" if edition else None)
