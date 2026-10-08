"""Fetch every series in the indicator catalog from its public API."""

import csv
import io
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from events import calendar_warnings, upcoming_events
from indicators import (EURO_AREA_PEAKS_AND_TROUGHS, PANELS, RECESSIONS_BY_SECTION, SECTIONS,
                        Panel, Series)
from transforms import (Observation, difference, infer_frequency, is_stale, peak_trough_periods,
                        recession_periods, shift_months, spread, summarize, thin_before,
                        year_over_year)

Batch = dict[str, list[Observation]]  # query -> observations

# One year before the dashboard's first date, so year-over-year changes exist from the start.
FETCH_START = "1999-01-01"
DISPLAY_START = "2000-01-01"
DAILY_HISTORY_YEARS = 2  # older daily data is thinned to one point per week
OUTPUT_PATH = Path(__file__).parent / "data" / "data.js"
DATA_JS_PREFIX = "window.MACRO_DATA = "
SOURCE_NAMES = {
    "fred": "FRED", "ecb": "ECB", "eurostat": "Eurostat", "bis": "BIS",
    "imf_weo": "IMF World Economic Outlook", "imf_cpi": "IMF", "oecd_lt": "OECD",
    "statbank": "Danmarks Statistik", "mof": "Japans finansministerium", "derived": "Beregnet",
}
SDMX_CSV = "application/vnd.sdmx.data+csv;version=1.0.0"
# The APIs' bot filters disagree: FRED and the IMF block custom agents, the OECD blocks
# Python's default one. A curl-style agent is accepted by all of them (tested 2026-10-07).
USER_AGENT = "curl/8.7.1"


# --------------------------------------------------------------------------- helpers

def http_get(url: str, accept: str | None = None, attempts: int = 3, errors: str = "strict") -> str:
    """GET a URL as text. errors="replace" tolerates bytes that aren't valid UTF-8."""
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers)
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.read().decode("utf-8", errors=errors)
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
# other dataflows are named in front of the key, e.g. "WS_TC/Q.KR.H.A.M.770.A" (total credit).
BIS_DATAFLOW_VERSIONS = {"WS_CBPOL": "1.0", "WS_TC": "2.0"}


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


def fetch_oecd_lt(countries: list[str]) -> Batch:
    url = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/"
           f"{'+'.join(countries)}.M.IRLT.PA....."
           f"?startPeriod={FETCH_START[:7]}&dimensionAtObservation=AllDimensions"
           "&detail=dataonly&format=csvfile")
    return group_sdmx_rows(http_get(url), "REF_AREA")


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
    "mof": fetch_mof_jgb,
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
        else:
            processed[s.key] = spread(processed[s.query[0]], processed[s.query[1]])
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
            topic = "TOTAL_CREDIT" if s.query.startswith("WS_TC/") else "CBPOL"
            return f"https://data.bis.org/topics/{topic}"
        case "imf_weo":
            return f"https://www.imf.org/external/datamapper/{s.query.split('/')[0]}@WEO"
        case "imf_cpi":
            return "https://data.imf.org/en/datasets/IMF.STA:CPI"
        case "oecd_lt":
            return ("https://data-explorer.oecd.org/vis?df[ds]=dsDisseminateFinalDMZ"
                    "&df[id]=DSD_STES%40DF_FINMARK&df[ag]=OECD.SDD.STES")
        case "statbank":
            return f"https://www.statistikbanken.dk/{s.query.split('?')[0]}"
        case "mof":
            return "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/index.htm"
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
        "sections": [{"id": section_id, "title": title, "recessions": RECESSIONS_BY_SECTION.get(section_id)}
                     for section_id, title in SECTIONS],
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
                "series": [series_payload(s, panel, processed, errors, today) for s in panel.series],
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
    previous_by_key = {s["key"]: s for panel in previous["panels"] for s in panel["series"]}
    reused = []
    for panel in payload["panels"]:
        for index, series in enumerate(panel["series"]):
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
    all_series = [s for panel in PANELS for s in panel.series]
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
