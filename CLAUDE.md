# Makro-dashboard

Statisk HTML-dashboard med makroøkonomiske nøgletal i seks sektioner: Global, USA, Europa, Danmark, Asien og Kina,
plus fanerne **Signaler** (kalender, ugens største bevægelser, z-score-heatmap) og **Sammenlign** (to vilkårlige serier).
Et Python-script henter data fra offentlige API'er og skriver `data/data.js`, som siden læser.

## Kør

```bash
python3 fetch_data.py      # henter alle serier og skriver data/data.js
open index.html            # åbner dashboardet (virker via file://)
```

Kun Pythons standardbibliotek bruges; der skal ikke installeres pakker.

## Test

```bash
python3 -m unittest discover tests
```

## Struktur

| Fil | Ansvar |
|-----|--------|
| `indicators.py` | Katalog over alle serier: kilde, id, sektion, gruppe, enhed, beregning, referencelinjer; CEPR-recessioner |
| `events.py` | ECB- og Fed-mødedatoer (manuel liste med kilder) og kalenderlogik |
| `fetch_data.py` | Henter serier fra hver kilde, recessioner (USREC) og Eurostats udgivelseskalender; skriver `data/data.js` |
| `transforms.py` | Beregninger: år-over-år, spreads, ændringer, percentil, z-score, ugebevægelse, recessionsperioder |
| `index.html`, `style.css`, `app.js` | Selve dashboardet (Chart.js fra CDN). URL'en (`#europe?range=10`) er eneste kilde til tilstand |
| `data/data.js` | Genereret data: `window.MACRO_DATA = {...}`. Committes kun af GitHub Actions-botten |
| `tests/` | Unit tests (unittest) |

## Datakilder

- FRED (St. Louis Fed) – CSV-endpoint uden API-nøgle: `fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIE>`
- ECB Data Portal – `data-api.ecb.europa.eu`
- Eurostat – `ec.europa.eu/eurostat/api`
- BIS – styringsrenter (`stats.bis.org/api/v2`, dataflow `WS_CBPOL`)
- IMF DataMapper – `imf.org/external/datamapper/api/v1`
- Danmarks Statistik (inkl. Nationalbankens tal) – `api.statbank.dk/v1`

## Vigtige beslutninger

- Data gemmes som `.js` (ikke `.json`), fordi en side åbnet via `file://` ikke må `fetch()` lokale filer.
- FRED tillader ikke browser-kald (ingen CORS), derfor hentes alt i Python frem for i browseren.
- Automatisk opdatering sker via GitHub Actions; siden publiceres med GitHub Pages.

## GitHub og automatisk opdatering

- Repo: https://github.com/SoLl1XZ/Macro-Dashboard (offentligt). Siden: https://soll1xz.github.io/Macro-Dashboard/
- `.github/workflows/update.yml` kører kl. 06:00 UTC, ved push til `main` og manuelt (`gh workflow run update.yml`):
  tests → `fetch_data.py` → commit af `data/data.js` → publicering af `index.html`, `app.js`, `style.css`, `data/` til Pages.
- Commits bruger noreply-adressen `222303744+SoLl1XZ@users.noreply.github.com` (sat i repoets lokale git-config), aldrig gmail.
- Spørg altid før `git push`. Hent bot-commits med `git pull` før lokale ændringer.
- Commit aldrig en lokalt genereret `data/data.js` (konflikt med botten). Kassér den før pull: `git restore data/data.js`.

## Kendte faldgruber

- **User-Agent:** FRED og IMF blokerer ukendte User-Agents, OECD blokerer Pythons standard. `curl/8.7.1` virker hos alle (se `USER_AGENT` i `fetch_data.py`).
- **SSL-fejl (`CERTIFICATE_VERIFY_FAILED`) lokalt:** python.org-Python bruger sin egen certifikatliste. Ret med `python3 -m pip install --upgrade certifi`.
- **Statistikbankens BULK-svar er ikke sorteret efter dato** – `to_observations` sorterer.
- **Eurostat:** eurozonen hedder `EA21` fra 2026 (`EA20` stopper i 2025; nogle datasæt bruger `EA`). År-over-år-vækst (`PCH_SM`) findes kun for kalenderkorrigerede data (`s_adj=CA`).
- **Manuelle lister:** CEPR-recessioner (`indicators.py`) og ECB/Fed-møder (`events.py`) har intet API. Siden advarer, når mødelisterne løber tør.
- **Ingen to y-akser** (heller ikke i Sammenlign): forskellige enheder vises som to grafer, eller begge omregnes til indeks 100.
