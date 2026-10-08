"""Fetch every series in the indicator catalog from its public API."""

import csv
import http.client
import io
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from events import calendar_warnings, upcoming_events
from indicators import (EURO_AREA_PEAKS_AND_TROUGHS, INPUT_SERIES, PANELS, RECESSIONS_BY_SECTION,
                        SECTIONS, Panel, Series, owned_series)
from transforms import (Observation, difference, in_latest_prices, infer_frequency, is_stale,
                        peak_trough_periods, ratio, recession_periods, shift_months, spread,
                        summarize, thin_before, year_over_year)

Batch = dict[str, list[Observation]]  # query -> observations

# One year before the dashboard's first date, so year-over-year changes exist from the start.
FETCH_START = "1999-01-01"
DISPLAY_START = "2000-01-01"
DAILY_HISTORY_YEARS = 2  # older daily data is thinned to one point per week
OUTPUT_PATH = Path(__file__).parent / "data" / "data.js"
DATA_JS_PREFIX = "window.MACRO_DATA = "
SOURCE_NAMES = {
    "fred": "FRED", "ecb": "ECB", "eurostat": "Eurostat", "bis": "BIS",
    "imf_weo": "IMF World Economic Outlook", "imf_cpi": "IMF", "imf_qnea": "IMF", "oecd": "OECD",
    "statbank": "Danmarks Statistik", "mof": "Japans finansministerium",
    "worldbank": "Verdensbanken (Pink Sheet)", "derived": "Beregnet",
}
SDMX_CSV = "application/vnd.sdmx.data+csv;version=1.0.0"
# The APIs' bot filters disagree: FRED and the IMF block custom agents, the OECD blocks
# Python's default one. A curl-style agent is accepted by all of them (tested 2026-10-07).
USER_AGENT = "curl/8.7.1"


# --------------------------------------------------------------------------- helpers

def http_get(url: str, accept: str | None = None, attempts: int = 3, errors: str = "strict",
             retry_not_found: bool = False) -> str:
    """GET a URL as text. errors="replace" tolerates bytes that aren't valid UTF-8."""
    return http_get_bytes(url, accept, attempts, retry_not_found).decode("utf-8", errors=errors)


def http_get_bytes(url: str, accept: str | None = None, attempts: int = 3,
                   retry_not_found: bool = False) -> bytes:
    """GET a URL as raw bytes, e.g. a spreadsheet.

    retry_not_found tries a 404 once more, for an API that sometimes answers 404 for
    something that exists.
    """
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers)
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            # A 4xx means the query itself is wrong, so retrying cannot help.
            # 429 (rate limited) and 5xx (server trouble) are often temporary.
            temporary = error.code == 429 or error.code >= 500
            second_chance = retry_not_found and error.code == 404 and attempt == 1
            if not (temporary or second_chance) or attempt == attempts:
                raise
        # Network trouble is usually brief: no answer, a dropped connection (RemoteDisconnected,
        # a ConnectionError) or an answer cut off halfway (IncompleteRead, an HTTPException).
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException):
            if attempt == attempts:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def normalize_period(period: str) -> str:
    """Convert the period formats used by the different APIs to an ISO date.

    Periods longer than a day are mapped to their first day, e.g. 2026-Q2 -> 2026-04-01.
    """
    period = period.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", period):
        return period
    if m := re.fullmatch(r"(\d{4})M(\d{2})D(\d{2})", period):  # Statbank daily: 2026M10D06
        return f"{m[1]}-{m[2]}-{m[3]}"
    if m := re.fullmatch(r"(\d{4})-?M?(\d{2})", period):  # 2026-08, 2026M08, 2026-M08
        return f"{m[1]}-{m[2]}-01"
    if m := re.fullmatch(r"(\d{4})-?[QK]([1-4])", period):  # 2026-Q2, 2026Q2, 2026K2 (Danish)
        return f"{m[1]}-{3 * int(m[2]) - 2:02d}-01"
    if re.fullmatch(r"\d{4}", period):
        return f"{period}-01-01"
    raise ValueError(f"Unknown period format: {period!r}")


def parse_number(value: object) -> float | None:
    """Return a float, or None for the many ways APIs mark missing values ('', '.', '..', NaN)."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def to_observations(pairs: Iterable[tuple[str, object]]) -> list[Observation]:
    """Normalize (period, value) pairs: ISO dates, drop missing values, sort, keep one value per date."""
    by_date: dict[str, float] = {}
    for period, raw_value in pairs:
        value = parse_number(raw_value)
        date = normalize_period(period)
        if value is not None and date >= FETCH_START:
            by_date[date] = value
    return sorted(by_date.items())


def group_sdmx_rows(text: str, key_column: str) -> Batch:
    """Split an SDMX CSV response covering several countries into one series per country."""
    pairs_by_key: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in csv.DictReader(io.StringIO(text)):
        pairs_by_key[row[key_column]].append((row["TIME_PERIOD"], row["OBS_VALUE"]))
    return {key: to_observations(pairs) for key, pairs in pairs_by_key.items()}


# ------------------------------------------------------- fetchers: one query per call

def fetch_fred(series_id: str) -> list[Observation]:
    # The fredgraph CSV endpoint needs no API key (the JSON API does).
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={FETCH_START}"
    # FRED now and then answers 404 for a series that exists (twice from GitHub's servers on
    # 2026-10-08), so a 404 gets a second try before it counts as a wrong series id.
    rows = list(csv.reader(io.StringIO(http_get(url, retry_not_found=True))))
    return to_observations((row[0], row[1]) for row in rows[1:] if len(row) >= 2)


def fetch_ecb(flow_and_key: str) -> list[Observation]:
    url = (f"https://data-api.ecb.europa.eu/service/data/{flow_and_key}"
           f"?format=csvdata&detail=dataonly&startPeriod={FETCH_START}")
    rows = csv.DictReader(io.StringIO(http_get(url)))
    return to_observations((row["TIME_PERIOD"], row["OBS_VALUE"]) for row in rows)


def fetch_eurostat(query: str) -> list[Observation]:
    dataset, filters = query.split("?", 1)
    url = (f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}"
           f"?{filters}&format=JSON&sinceTimePeriod={FETCH_START[:7]}")
    data = json.loads(http_get(url))
    # JSON-stat stores all values in one flat list. When every dimension except time is
    # fixed to a single value, a value's flat position equals its position on the time axis.
    sizes = dict(zip(data["id"], data["size"]))
    if any(size == 0 for size in sizes.values()):
        raise ValueError(f"Eurostat returned nothing; a code in the filter may not exist: {sizes}")
    if any(size != 1 for dimension, size in sizes.items() if dimension != "time"):
        raise ValueError(f"Ambiguous Eurostat query, fix every dimension except time: {sizes}")
    position_by_period = data["dimension"]["time"]["category"]["index"]
    values = data["value"]
    return to_observations(
        (period, values.get(str(position))) for period, position in position_by_period.items()
    )


# BIS dataflows and their versions. A query without a dataflow ("D.US") means policy rates;
# other dataflows are named in front of the key, e.g. "WS_TC/Q.KR.H.A.M.770.A" (total credit)
# or "WS_XRU/D.ID.IDR.A" (rupiah per US dollar, daily average).
BIS_DATAFLOW_VERSIONS = {"WS_CBPOL": "1.0", "WS_TC": "2.0", "WS_XRU": "1.0"}
BIS_TOPICS = {"WS_CBPOL": "CBPOL", "WS_TC": "TOTAL_CREDIT", "WS_XRU": "XRU"}  # data.bis.org pages


def fetch_bis(query: str) -> list[Observation]:
    dataflow, key = query.split("/", 1) if "/" in query else ("WS_CBPOL", query)
    url = (f"https://stats.bis.org/api/v2/data/dataflow/BIS/{dataflow}/{BIS_DATAFLOW_VERSIONS[dataflow]}/{key}"
           f"?startPeriod={FETCH_START}&detail=dataonly")
    rows = csv.DictReader(io.StringIO(http_get(url, accept=SDMX_CSV)))
    return to_observations((row["TIME_PERIOD"], row["OBS_VALUE"]) for row in rows)


def fetch_statbank(query: str) -> list[Observation]:
    table, filters = query.split("?", 1)
    params = urllib.parse.parse_qsl(filters) + [("lang", "en"), ("Tid", "*")]
    url = f"https://api.statbank.dk/v1/data/{table}/BULK?{urllib.parse.urlencode(params)}"
    rows = list(csv.reader(io.StringIO(http_get(url)), delimiter=";"))
    # BULK format: one column per filter variable, then time and value as the last two.
    return to_observations((row[-2], row[-1]) for row in rows[1:] if len(row) >= 2)


# --------------------------------------------- fetchers: many queries in one call
# These APIs are either rate limited (OECD) or return all countries at once (IMF),
# so each request covers several queries.

def fetch_imf_weo(queries: list[str]) -> Batch:
    countries_by_indicator: dict[str, list[str]] = defaultdict(list)
    for query in queries:
        indicator, country = query.split("/")
        countries_by_indicator[indicator].append(country)

    batch: Batch = {}
    for indicator, countries in countries_by_indicator.items():
        data = json.loads(http_get(f"https://www.imf.org/external/datamapper/api/v1/{indicator}"))
        values_by_country = data["values"][indicator]
        for country in countries:
            yearly_values = values_by_country.get(country, {})
            batch[f"{indicator}/{country}"] = to_observations(yearly_values.items())
    return batch


def fetch_imf_cpi(countries: list[str]) -> Batch:
    url = ("https://api.imf.org/external/sdmx/2.1/data/IMF.STA,CPI/"
           f"{'+'.join(countries)}.CPI._T.YOY_PCH_PA_PT.M"
           f"?startPeriod={FETCH_START[:7]}&detail=dataonly")
    return group_sdmx_rows(http_get(url, accept=SDMX_CSV), "COUNTRY")


def fetch_imf_qnea(countries: list[str]) -> Batch:
    # Real GDP in national currency, not seasonally adjusted: the "yoy" transform turns
    # it into growth versus the same quarter last year, which needs no seasonal adjustment.
    url = ("https://api.imf.org/external/sdmx/2.1/data/IMF.STA,QNEA/"
           f"{'+'.join(countries)}.B1GQ.Q.NSA.XDC.Q"
           f"?startPeriod={FETCH_START[:4]}&detail=dataonly")
    return group_sdmx_rows(http_get(url, accept=SDMX_CSV), "COUNTRY")


class PartialBatch(Exception):
    """Raised by a batch fetcher when some of its requests failed and others worked."""

    def __init__(self, batch: Batch, errors: dict[str, str]):
        super().__init__(f"{len(errors)} queries failed")
        self.batch = batch
        self.errors = errors


# OECD dataflows as (flow id, series key template). A query is "DATAFLOW/MEASURE/COUNTRY",
# e.g. "FINMARK/IRLT/DEU" for Germany's 10-year yield; the measure and the countries fill in
# the template. Keys tested 2026-10-08.
OECD_DATAFLOWS = {
    "FINMARK": ("OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0", "{countries}.M.{measure}.PA....."),
    "CLI": ("OECD.SDD.STES,DSD_STES@DF_CLI,4.1", "{countries}.M.{measure}.IX._Z.AA.IX._Z.H"),
    "PRICES": ("OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0", "{countries}.M.N.CPI.PA.{measure}.N.GY"),
    "QNA": ("OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA_EXPENDITURE_GROWTH_G20,1.1",
            "Q.Y.{countries}.S1.S1.B1GQ._Z._Z._Z.PC.L.{measure}.T0102"),
}


def fetch_oecd(queries: list[str]) -> Batch:
    """One request per dataflow and measure, covering all its countries at once.

    The OECD rate-limits its API (it answered 403 during testing), so few requests matter.
    A failed request only fails its own queries: see PartialBatch.
    """
    countries_by_measure: dict[tuple[str, str], list[str]] = defaultdict(list)
    for query in queries:
        dataflow, measure, country = query.split("/")
        countries_by_measure[(dataflow, measure)].append(country)

    batch: Batch = {}
    errors: dict[str, str] = {}
    for (dataflow, measure), countries in countries_by_measure.items():
        flow_id, key_template = OECD_DATAFLOWS[dataflow]
        key = key_template.format(countries="+".join(countries), measure=measure)
        url = (f"https://sdmx.oecd.org/public/rest/data/{flow_id}/{key}"
               f"?startPeriod={FETCH_START[:7]}&dimensionAtObservation=AllDimensions"
               "&detail=dataonly&format=csvfile")
        queries_here = [f"{dataflow}/{measure}/{country}" for country in countries]
        try:
            by_country = group_sdmx_rows(http_get(url), "REF_AREA")
        except Exception as error:  # the other dataflows may still work
            errors.update({query: describe(error) for query in queries_here})
            continue
        for query, country in zip(queries_here, countries):
            batch[query] = by_country.get(country, [])
    if errors:
        raise PartialBatch(batch, errors)
    return batch


# Japan's Ministry of Finance: the full history up to last month, then the current month.
MOF_URLS = (
    "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv",
    "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv",
)


def parse_mof_csv(text: str) -> Batch:
    """Parse a JGB yield file from Japan's Ministry of Finance into one series per maturity.

    The file has a title line, a header ("Date,1Y,2Y,...") and sometimes a note at the end;
    only rows dated YYYY/M/D are data. "-" marks a maturity that had no yield that day.
    """
    rows = list(csv.reader(io.StringIO(text)))
    header = next((row for row in rows if row and row[0] == "Date"), None)
    if header is None:
        raise ValueError("No 'Date' header in the MoF file")
    maturities = [maturity for maturity in header[1:] if maturity]
    pairs: dict[str, list[tuple[str, str]]] = {maturity: [] for maturity in maturities}
    for row in rows:
        m = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", row[0]) if row else None
        if m is None:
            continue
        iso_date = f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}"
        for maturity, value in zip(maturities, row[1:]):
            pairs[maturity].append((iso_date, value))
    return {maturity: to_observations(series) for maturity, series in pairs.items()}


def fetch_mof_jgb(maturities: list[str]) -> Batch:
    values_by_maturity: dict[str, dict[str, float]] = defaultdict(dict)
    for url in MOF_URLS:  # the current month comes last, so its values win where they overlap
        # The current-month file ends with a note in a Japanese encoding, not valid UTF-8.
        for maturity, observations in parse_mof_csv(http_get(url, errors="replace")).items():
            values_by_maturity[maturity].update(observations)
    return {maturity: sorted(values_by_maturity[maturity].items())
            for maturity in maturities if maturity in values_by_maturity}


# The World Bank's "Pink Sheet": monthly commodity prices, including the precious metals
# that FRED no longer has. The file's path changes with each yearly edition, so the link
# is looked up on the overview page every run.
PINK_SHEET_PAGE = "https://www.worldbank.org/en/research/commodity-markets"
PINK_SHEET_PRICES = "Monthly Prices"
XLSX = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
XLSX_RELATION = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def find_pink_sheet_url(html: str) -> str:
    match = re.search(r"""https?://[^"'\s<>]+/CMO-Historical-Data-Monthly\.xlsx""", html)
    if match is None:
        raise ValueError("No link to CMO-Historical-Data-Monthly.xlsx on the World Bank page")
    return match.group(0)


def xlsx_cell_text(cell: ET.Element, shared_strings: list[str]) -> str | None:
    """A cell's text: numbers are stored in the cell, most texts in a shared list."""
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(f"{XLSX}t"))
    value = cell.find(f"{XLSX}v")
    if value is None or value.text is None:
        return None
    return shared_strings[int(value.text)] if kind == "s" else value.text


def read_xlsx_rows(data: bytes, sheet_name: str) -> dict[int, dict[str, str | None]]:
    """One worksheet of an .xlsx file as {row number: {column letters: text}}.

    An .xlsx file is a zip of XML files, so the standard library is enough: the workbook
    names the sheets, its relations file says which XML file holds each one.
    """
    with zipfile.ZipFile(io.BytesIO(data)) as book:
        workbook = ET.fromstring(book.read("xl/workbook.xml"))
        relations = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        target_by_id = {relation.get("Id"): relation.get("Target") for relation in relations}
        sheet_id = next((sheet.get(XLSX_RELATION) for sheet in workbook.iter(f"{XLSX}sheet")
                         if sheet.get("name") == sheet_name), None)
        if sheet_id is None:
            raise ValueError(f"No sheet named {sheet_name!r}")
        target = target_by_id[sheet_id].lstrip("/")
        path = target if target.startswith("xl/") else f"xl/{target}"
        shared_strings = []
        if "xl/sharedStrings.xml" in book.namelist():
            shared_strings = ["".join(t.text or "" for t in item.iter(f"{XLSX}t"))
                              for item in ET.fromstring(book.read("xl/sharedStrings.xml"))]
        sheet = ET.fromstring(book.read(path))
    rows: dict[int, dict[str, str | None]] = {}
    for row in sheet.iter(f"{XLSX}row"):
        rows[int(row.get("r"))] = {re.match(r"[A-Z]+", cell.get("r"))[0]: xlsx_cell_text(cell, shared_strings)
                                   for cell in row.iter(f"{XLSX}c")}
    return rows


def parse_pink_sheet(data: bytes) -> Batch:
    """Monthly prices per commodity, keyed by the Pink Sheet's column header (e.g. "Gold").

    The sheet has a few title lines, a row of commodity names, a row of units such as
    "($/troy oz)", and then one row per month ("2026M09" in column A). "…" marks no price.
    """
    rows = read_xlsx_rows(data, PINK_SHEET_PRICES)
    month_rows = [number for number, cells in sorted(rows.items())
                  if re.fullmatch(r"\d{4}M\d{2}", (cells.get("A") or "").strip())]
    if not month_rows:
        raise ValueError("No monthly rows in the Pink Sheet")

    def is_units_row(cells: dict) -> bool:
        texts = [text for text in cells.values() if text]
        return bool(texts) and all(text.strip().startswith("(") for text in texts)

    above = [number for number in sorted(rows) if number < month_rows[0] and not is_units_row(rows[number])]
    headers = {column: text.strip() for column, text in rows[above[-1]].items() if column != "A" and text}
    return {name: to_observations((rows[number]["A"], rows[number].get(column)) for number in month_rows)
            for column, name in headers.items()}


def fetch_pink_sheet(commodities: list[str]) -> Batch:
    prices = parse_pink_sheet(http_get_bytes(find_pink_sheet_url(http_get(PINK_SHEET_PAGE))))
    return {commodity: prices[commodity] for commodity in commodities if commodity in prices}


SINGLE_FETCHERS: dict[str, Callable[[str], list[Observation]]] = {
    "fred": fetch_fred,
    "ecb": fetch_ecb,
    "eurostat": fetch_eurostat,
    "bis": fetch_bis,
    "statbank": fetch_statbank,
}
BATCH_FETCHERS: dict[str, Callable[[list[str]], Batch]] = {
    "imf_weo": fetch_imf_weo,
    "imf_cpi": fetch_imf_cpi,
    "imf_qnea": fetch_imf_qnea,
    "oecd": fetch_oecd,
    "mof": fetch_mof_jgb,
    "worldbank": fetch_pink_sheet,
}


# ----------------------------------------------------------------------- orchestration

def describe(error: Exception) -> str:
    return f"{type(error).__name__}: {error}"[:200]


def fetch_source(source: str, queries: list[str]) -> tuple[Batch, dict[str, str]]:
    """Fetch all queries for one source. Returns (observations, errors), both keyed by query."""
    batch: Batch = {}
    errors: dict[str, str] = {}
    # Broad excepts are deliberate: one broken API or series must never stop the whole run.
    if source in BATCH_FETCHERS:
        try:
            batch = BATCH_FETCHERS[source](queries)
        except PartialBatch as partial:
            batch, errors = partial.batch, dict(partial.errors)
        except Exception as error:
            return {}, {query: describe(error) for query in queries}
    else:
        for query in queries:
            try:
                batch[query] = SINGLE_FETCHERS[source](query)
            except Exception as error:
                errors[query] = describe(error)

    for query in queries:
        if query not in errors and not batch.get(query):
            errors[query] = "No observations returned"
    return batch, errors


def fetch_all(series: list[Series]) -> tuple[dict[str, list[Observation]], dict[str, str]]:
    """Fetch every non-derived series. Returns (observations, errors), both keyed by series key."""
    queries_by_source: dict[str, set[str]] = defaultdict(set)
    for s in series:
        if s.source != "derived":
            queries_by_source[s.source].add(s.query)  # set: several panels may share a query

    batches: dict[str, Batch] = {}
    errors_by_source: dict[str, dict[str, str]] = {}
    for source, queries in queries_by_source.items():
        started = time.monotonic()
        batches[source], errors_by_source[source] = fetch_source(source, sorted(queries))
        print(f"  {source:9s} {len(queries):3d} queries, "
              f"{len(errors_by_source[source])} failed, {time.monotonic() - started:5.1f}s")

    observations: dict[str, list[Observation]] = {}
    failures: dict[str, str] = {}
    for s in series:
        if s.source == "derived":
            continue
        if s.query in errors_by_source[s.source]:
            failures[s.key] = errors_by_source[s.source][s.query]
        else:
            observations[s.key] = batches[s.source][s.query]
    return observations, failures


def print_status(series: list[Series], observations: dict[str, list[Observation]],
                 failures: dict[str, str]) -> None:
    for s in series:
        if s.key in failures:
            print(f"  FAIL {s.key:14s} {s.source:9s} {failures[s.key]}")
        elif s.key in observations:
            obs = observations[s.key]
            print(f"  ok   {s.key:14s} {s.source:9s} {len(obs):6d} obs  "
                  f"{obs[0][0]} .. {obs[-1][0]}  last={obs[-1][1]:g}")


# ------------------------------------------------------------------- transform + output

def apply_transforms(all_series: list[Series], observations: dict[str, list[Observation]],
                     failures: dict[str, str]) -> tuple[dict[str, list[Observation]], dict[str, str]]:
    """Apply each series' transform. Returns (processed observations, errors) keyed by series key."""
    processed: dict[str, list[Observation]] = {}
    errors = dict(failures)
    # Own transforms first: derived series are computed from these results.
    for s in all_series:
        if s.source == "derived" or s.key not in observations:
            continue
        obs = observations[s.key]
        if s.transform == "yoy":
            obs = year_over_year(obs)
        elif s.transform == "diff":
            obs = difference(obs)
        processed[s.key] = obs

    for s in all_series:
        if s.source != "derived":
            continue
        missing = [key for key in s.query if key not in processed]
        if missing:
            errors[s.key] = f"Missing input: {', '.join(missing)}"
            continue
        a, b = processed[s.query[0]], processed[s.query[1]]
        match s.transform:
            case "spread":
                processed[s.key] = spread(a, b)
            case "ratio":
                processed[s.key] = ratio(a, b)
            case "real":
                processed[s.key] = in_latest_prices(a, b)
    return processed, errors


def rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def rounded_summary(summary: dict | None) -> dict | None:
    if summary is None:
        return None
    fields = ("last", "change1m", "change1y", "percentile10y", "zscore10y", "weekChange", "weekMoveZ")
    return {**summary, **{field: rounded(summary[field]) for field in fields}}


def source_url(s: Series) -> str | None:
    """A human-readable page for the series, linked from the dashboard."""
    match s.source:
        case "fred":
            return f"https://fred.stlouisfed.org/series/{s.query}"
        case "ecb":
            flow, key = s.query.split("/", 1)
            return f"https://data.ecb.europa.eu/data/datasets/{flow}/{flow}.{key}"
        case "eurostat":
            return f"https://ec.europa.eu/eurostat/databrowser/view/{s.query.split('?')[0]}/default/table"
        case "bis":
            dataflow = s.query.split("/")[0] if "/" in s.query else "WS_CBPOL"
            return f"https://data.bis.org/topics/{BIS_TOPICS[dataflow]}"
        case "imf_weo":
            return f"https://www.imf.org/external/datamapper/{s.query.split('/')[0]}@WEO"
        case "imf_cpi":
            return "https://data.imf.org/en/datasets/IMF.STA:CPI"
        case "imf_qnea":
            return "https://data.imf.org/en/datasets/IMF.STA:QNEA"
        case "oecd":
            agency, flow, _ = OECD_DATAFLOWS[s.query.split("/")[0]][0].split(",")
            return ("https://data-explorer.oecd.org/vis?df[ds]=dsDisseminateFinalDMZ"
                    f"&df[id]={urllib.parse.quote(flow)}&df[ag]={agency}")
        case "statbank":
            return f"https://www.statistikbanken.dk/{s.query.split('?')[0]}"
        case "mof":
            return "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/index.htm"
        case "worldbank":
            return PINK_SHEET_PAGE
        case _:
            return None  # derived series are computed here, not published anywhere


def series_payload(s: Series, panel: Panel, processed: dict[str, list[Observation]],
                   errors: dict[str, str], today: str) -> dict:
    obs = [o for o in processed.get(s.key, []) if o[0] >= DISPLAY_START]
    summary = summarize(obs, panel.change, today)  # before thinning: needs every daily point
    frequency = infer_frequency(obs)  # also before thinning, which would make daily data look weekly
    thinning_cutoff = shift_months(today, -12 * DAILY_HISTORY_YEARS)
    return {
        "key": s.key,
        "label": s.label,
        "source": SOURCE_NAMES[s.source],
        "sourceUrl": source_url(s),
        "frequency": frequency,
        # In IMF's World Economic Outlook the current year is already a projection.
        "forecastFrom": f"{today[:4]}-01-01" if s.source == "imf_weo" else None,
        "error": errors.get(s.key),
        "stale": summary is not None and is_stale(summary["lastDate"], frequency, today),
        "fallbackFrom": None,  # set by reuse_previous_data when this run's fetch failed
        "summary": rounded_summary(summary),
        "data": [[d, rounded(v)] for d, v in thin_before(obs, thinning_cutoff)],
    }


def build_payload(panels: list[Panel], processed: dict[str, list[Observation]],
                  errors: dict[str, str], today: str) -> dict:
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sections": [{"id": section.id, "title": section.title, "region": section.region,
                      "recessions": RECESSIONS_BY_SECTION.get(section.id)}
                     for section in SECTIONS],
        "panels": [
            {
                "id": panel.id,
                "section": panel.section,
                "title": panel.title,
                "unit": panel.unit,
                "description": panel.description,
                "change": panel.change,
                "decimals": panel.decimals,
                "group": panel.group,
                "referenceLines": [{"value": value, "label": label} for value, label in panel.reference_lines],
                "split": panel.split,
                "comparable": panel.comparable,
                # A reference is only a pointer; the page fills in the owner's data.
                "series": [series_payload(s, panel, processed, errors, today) if isinstance(s, Series)
                           else {"ref": s.key, "label": s.label}
                           for s in panel.series],
            }
            for panel in panels
        ],
    }


def fetch_hicp_flash_dates(today: str) -> list[str]:
    """Release dates of Eurostat's flash estimate of euro area inflation, from its calendar."""
    end = (date.fromisoformat(today) + timedelta(days=400)).isoformat()
    url = ("https://ec.europa.eu/eurostat/o/calendars/eventsJson?theme=0&category=0&keywords="
           f"&isEuroindicator=&authorInclude=&authorExclude=&start={today}T00:00:00Z"
           f"&end={end}T00:00:00Z&timeZone=UTC")
    events = json.loads(http_get(url))
    return sorted({event["start"][:10] for event in events
                   if "flash estimate inflation euro area" in event["title"].lower()})


def calendar_events(previous: dict | None, today: str) -> list[dict]:
    try:
        flash_dates = fetch_hicp_flash_dates(today)
    except Exception as error:  # keep the dates from the last run rather than none
        print(f"  FAIL Eurostat calendar: {describe(error)}")
        flash_dates = [event["date"] for event in (previous or {}).get("events", [])
                       if event["institution"] == "Eurostat"]
    return upcoming_events(flash_dates, today)


def fetch_recessions(previous: dict | None) -> dict[str, list[list[str]]]:
    """Recession periods per dating source, as [start, end) date pairs."""
    euro_area = [list(period) for period in peak_trough_periods(EURO_AREA_PEAKS_AND_TROUGHS)]
    try:
        us = [list(period) for period in recession_periods(fetch_fred("USREC"))]
    except Exception as error:  # keep the last known US dates rather than losing the shading
        print(f"  FAIL USREC: {describe(error)}")
        us = (previous or {}).get("recessions", {}).get("us", [])
    return {"us": us, "euro_area": euro_area}


def load_previous_payload(path: Path) -> dict | None:
    """The data from the last run, or None if the file is missing or unreadable."""
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text.removeprefix(DATA_JS_PREFIX).rstrip().removesuffix(";"))
    except (OSError, ValueError):
        return None


def reuse_previous_data(payload: dict, previous: dict | None, today: str) -> list[str]:
    """Fill series that failed in this run with their data from the previous run.

    A temporary API outage then shows slightly older data with a warning instead of an
    empty chart. Returns the keys of the series that were filled in.
    """
    if previous is None:
        return []
    previous_by_key = {s["key"]: s for panel in previous["panels"] for s in panel["series"] if "key" in s}
    reused = []
    for panel in payload["panels"]:
        for index, series in enumerate(panel["series"]):
            if "ref" in series:  # a reference shows its owner's series, fallback included
                continue
            old = previous_by_key.get(series["key"])
            if series["data"] or not old or not old["data"]:
                continue
            panel["series"][index] = {
                **series,  # labels and links from the current catalog, data from the old run
                "data": old["data"],
                "summary": old["summary"],
                "frequency": old["frequency"],
                "stale": is_stale(old["summary"]["lastDate"], old["frequency"], today),
                # If the previous run was itself a fallback, keep the original fetch time.
                "fallbackFrom": old.get("fallbackFrom") or previous["generatedAt"],
            }
            reused.append(series["key"])
    return reused


def write_data_js(payload: dict, path: Path) -> None:
    # A .js file, not .json: a page opened via file:// may load scripts but not fetch() files.
    text = DATA_JS_PREFIX + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n"
    path.parent.mkdir(exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)  # atomic swap: the page never sees a half-written file


def main() -> int:
    today = date.today().isoformat()
    all_series = owned_series(PANELS) + INPUT_SERIES
    print("Fetching...")
    observations, failures = fetch_all(all_series)
    if "--verbose" in sys.argv:
        print_status(all_series, observations, failures)
    if not observations:
        print("Nothing could be fetched; keeping the existing data file.", file=sys.stderr)
        return 1

    processed, errors = apply_transforms(all_series, observations, failures)
    payload = build_payload(PANELS, processed, errors, today)
    previous = load_previous_payload(OUTPUT_PATH)
    reused = reuse_previous_data(payload, previous, today)
    payload["recessions"] = fetch_recessions(previous)
    payload["events"] = calendar_events(previous, today)
    payload["calendarWarnings"] = calendar_warnings(today)
    write_data_js(payload, OUTPUT_PATH)
    for key, message in errors.items():
        print(f"  FAIL {key}: {message}")
    if reused:
        print(f"  Kept previous data for {len(reused)} failed series: {', '.join(reused)}")
    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"Wrote {OUTPUT_PATH.name}: {len(processed)} series ok, {len(errors)} failed, {size_kb:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
