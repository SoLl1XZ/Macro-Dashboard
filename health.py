"""The series this run could not fetch, as the text of a GitHub issue.

GitHub Actions runs this after the fetch (see .github/workflows/update.yml): it prints nothing
when every source worked, otherwise Markdown for the "Datakilder fejler" issue, which GitHub
mails to the repository owner. Stale series are left out: their sources are slow, not broken.
"""

import json
from collections import defaultdict
from pathlib import Path

DATA_PATH = Path(__file__).parent / "data" / "data.js"


def load_payload(path: Path = DATA_PATH) -> dict:
    text = path.read_text(encoding="utf-8")
    return json.loads(text[text.index("{"):text.rindex("}") + 1])  # data.js is "window.MACRO_DATA = {...};"


def failed_series(payload: dict) -> list[dict]:
    """Series whose fetch failed in this run. A reference ("ref") repeats its owner's series."""
    return [series for panel in payload["panels"] for series in panel["series"]
            if "key" in series and series.get("error")]


def count(n: int) -> str:
    return f"{n} serie" if n == 1 else f"{n} serier"


def issue_body(payload: dict) -> str:
    failed = failed_series(payload)
    if not failed:
        return ""
    # One line per error and what the page shows instead, so an outage of one source is one line.
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for series in failed:
        fallback = series.get("fallbackFrom")
        shows = f"siden viser data fra {fallback[:10]}" if fallback else "ingen data på siden"
        groups[(series["error"], shows)].append(f"`{series['key']}`")
    lines = [f"Kørslen {payload['generatedAt'][:16].replace('T', ' ')} UTC kunne ikke hente {count(len(failed))}.", ""]
    for (error, shows), keys in groups.items():
        lines.append(f"- **{error}** ({count(len(keys))}, {shows}): {', '.join(keys)}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(issue_body(load_payload()), end="")
