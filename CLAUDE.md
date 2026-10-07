# Makro-dashboard

Statisk HTML-dashboard med makroøkonomiske nøgletal i seks sektioner: Global, USA, Europa, Danmark, Asien og Kina.
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
| `indicators.py` | Katalog over alle serier: kilde, id, sektion, enhed, beregning |
| `fetch_data.py` | Henter serier fra hver kilde og skriver `data/data.js` |
| `transforms.py` | Beregninger: år-over-år, spreads, ændringer |
| `index.html`, `style.css`, `app.js` | Selve dashboardet (Chart.js fra CDN) |
| `data/data.js` | Genereret data: `window.MACRO_DATA = {...}` |
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

## Kendte faldgruber

- **User-Agent:** FRED og IMF blokerer ukendte User-Agents, OECD blokerer Pythons standard. `curl/8.7.1` virker hos alle (se `USER_AGENT` i `fetch_data.py`).
- **SSL-fejl (`CERTIFICATE_VERIFY_FAILED`) lokalt:** python.org-Python bruger sin egen certifikatliste. Ret med `python3 -m pip install --upgrade certifi`.
- **Statistikbankens BULK-svar er ikke sorteret efter dato** – `to_observations` sorterer.
