"""Fetch every series in the indicator catalog from its public API."""

import csv
import io
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Iterable

from indicators import PANELS, Series

Observation = tuple[str, float]  # (ISO date "YYYY-MM-DD", value)
Batch = dict[str, list[Observation]]  # query -> observations

# One year before the dashboard's first date, so year-over-year changes exist from the start.
FETCH_START = "1999-01-01"
SDMX_CSV = "application/vnd.sdmx.data+csv;version=1.0.0"
# The APIs' bot filters disagree: FRED and the IMF block custom agents, the OECD blocks
# Python's default one. A curl-style agent is accepted by all of them (tested 2026-10-07).
USER_AGENT = "curl/8.7.1"


# --------------------------------------------------------------------------- helpers

def http_get(url: str, accept: str | None = None, attempts: int = 3) -> str:
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers)
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            # A 4xx means the query itself is wrong, so retrying cannot help.
            # 429 (rate limited) and 5xx (server trouble) are often temporary.
            if not (error.code == 429 or error.code >= 500) or attempt == attempts:
                raise
        except (urllib.error.URLError, TimeoutError):
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
    rows = list(csv.reader(io.StringIO(http_get(url))))
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
    if any(size != 1 for dimension, size in sizes.items() if dimension != "time"):
        raise ValueError(f"Ambiguous Eurostat query, fix every dimension except time: {sizes}")
    position_by_period = data["dimension"]["time"]["category"]["index"]
    values = data["value"]
    return to_observations(
        (period, values.get(str(position))) for period, position in position_by_period.items()
    )


def fetch_bis(key: str) -> list[Observation]:
    url = (f"https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/{key}"
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


def fetch_oecd_lt(countries: list[str]) -> Batch:
    url = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/"
           f"{'+'.join(countries)}.M.IRLT.PA....."
           f"?startPeriod={FETCH_START[:7]}&dimensionAtObservation=AllDimensions"
           "&detail=dataonly&format=csvfile")
    return group_sdmx_rows(http_get(url), "REF_AREA")


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
    "oecd_lt": fetch_oecd_lt,
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


def main() -> None:
    all_series = [s for panel in PANELS for s in panel.series]
    print("Fetching...")
    observations, failures = fetch_all(all_series)
    print_status(all_series, observations, failures)
    print(f"\n{len(observations)} series fetched, {len(failures)} failed.")


if __name__ == "__main__":
    main()
