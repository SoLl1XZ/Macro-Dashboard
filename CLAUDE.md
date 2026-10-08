# Macro Dashboard

Statisk HTML-dashboard med makroøkonomiske nøgletal. Titlen er på engelsk; resten af siden er på dansk.
Et Python-script henter data fra offentlige API'er og skriver `data/data.js`, som siden læser.

## Faner, regioner og lande

- Topniveau: **Signaler** · Global · Nordamerika · Europa · Asien · **Sammenlign**.
  - Signaler viser kalender, ugens største bevægelser og z-score-heatmap.
  - Sammenlign viser to vilkårlige serier.
- Hver region har en oversigtsside, og dens lande glider ud ved hover eller fokus:
  - Nordamerika: `us`, `canada`
  - Europa: `uk`, `germany`, `france`, `denmark`, `norway`, `sweden`
  - Asien: `china`, `japan`, `korea`, `thailand`, `vietnam`, `indonesia`, `malaysia`, `india`
- Kun disse 16 lande må være på dashboardet.
- Strukturen er datadrevet: `SECTIONS` i `indicators.py` er `Section(id, title, region)` i menurækkefølge (låst af tests).
  - `app.js` bygger menuen og sætter Signaler først og Sammenlign sidst.
  - En ny topniveau-fane (fx "Aktieindekser") er én `Section(...)` uden region først i listen.
- **Gamle id'er bevares** (`us`, `europe`, `denmark`, `asia`, `china`, `japan`, `korea`), så gamle links som `#europe?range=10` virker.
- **Kernepaneler:**
  - Hver landefane starter med gruppen `CORE_GROUP` ("Kernetal") med titlerne i `CORE_TITLES`, i fast rækkefølge.
  - Et kernepanel udelades hellere, end at det viser noget forkert.
  - Landespecifikke paneler følger under `extras_group(land)` ("Særligt for …").
  - Fælles kernepaneler bygges med fabrikkerne `imf_gdp_panel`, `imf_unemployment_panel`, `confidence_panel`, `debt_panel` og `current_account_panel`.
- **Genbrug med `R(key, label)`** (`Ref`): et panel kan vise en serie, som et andet panel ejer, fx landenes tal i regionsoversigterne.
  - Hver serie-key ejes af præcis ét panel og hentes én gang.
  - Siden fylder ejerens data ind (`resolveReferences`).
  - Signaler og Sammenlign tæller kun ejeren, så intet vises to gange.

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
| `indicators.py` | Sektioner og regioner, katalog over alle serier (kilde, id, sektion, gruppe, enhed, beregning, referencelinjer, refs), kernetitler, CEPR-recessioner |
| `events.py` | ECB- og Fed-mødedatoer (manuel liste med kilder) og kalenderlogik |
| `fetch_data.py` | Henter serier fra hver kilde, recessioner (USREC) og Eurostats udgivelseskalender; skriver `data/data.js` |
| `transforms.py` | Beregninger: år-over-år, spreads, ændringer, percentil, z-score, ugebevægelse, recessionsperioder |
| `index.html`, `style.css`, `app.js`, `favicon.svg` | Selve dashboardet (Chart.js fra CDN). URL'en (`#europe?range=10`) er eneste kilde til tilstand |
| `data/data.js` | Genereret data: `window.MACRO_DATA = {...}`. Committes kun af GitHub Actions-botten |
| `tests/` | Unit tests (unittest) |

## Datakilder

- FRED (St. Louis Fed) – CSV-endpoint uden API-nøgle: `fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIE>`.
  Rummer også OECD- og IMF-serier, fx ledighed (`LRHUTTTT..M156S`), eksport (`XTEXVA01..M664S`),
  real BNP (`NGDPRSAXDC..Q`) og 3-mdr. renter (`IR3TIB01..M156N`) for Japan og Korea.
- ECB Data Portal – `data-api.ecb.europa.eu`
- Eurostat – `ec.europa.eu/eurostat/api`
- BIS – `stats.bis.org/api/v2`:
  - styringsrenter (`WS_CBPOL`, forespørgsel `"D.JP"`)
  - total credit (`WS_TC`, forespørgsel `"WS_TC/Q.KR.H.A.M.770.A"` = husholdningsgæld % af BNP)
  - valutakurser over for USD (`WS_XRU`, fx `"WS_XRU/D.ID.IDR.A"`; Vietnam kun månedligt `M.VN.VND.A`)
- IMF:
  - DataMapper (`imf_weo`): årlige tal inkl. prognoser; BNP-vækst, gæld, betalingsbalance og ledighed (`LUR`)
  - SDMX CPI (`imf_cpi`)
  - kvartalsvist nationalregnskab (`imf_qnea`, real-BNP i niveau → `"yoy"`; kun Malaysia, se faldgruber)
- OECD (`oecd`, forespørgsel `"DATAFLOW/MÅLING/LAND"`; skabeloner i `OECD_DATAFLOWS`):
  - `FINMARK`: renter `IRLT` / `IR3TIB`
  - `CLI`: tillid `CCICP` / `BCICP`
  - `PRICES`: kerne-CPI `_TXCP01_NRG`
  - `QNA`: BNP-vækst år/år `GY` for Kina og Indien
- Eurostat for HICP, kerne-HICP, ledighed og BNP for DE, FR, DK, NO og SE (`geo=..`); ECB for valuta over for EUR
- Danmarks Statistik (inkl. Nationalbankens tal) – `api.statbank.dk/v1`
- Japans finansministerium (`mof`) – JGB-rentekurven 1–40 år, dagligt: `historical/jgbcme_all.csv` + `jgbcme.csv`

## Vigtige beslutninger

- Data gemmes som `.js` (ikke `.json`), fordi en side åbnet via `file://` ikke må `fetch()` lokale filer.
- FRED tillader ikke browser-kald (ingen CORS), derfor hentes alt i Python frem for i browseren.
- Automatisk opdatering sker via GitHub Actions; siden publiceres med GitHub Pages.

## GitHub og automatisk opdatering

- Repo: https://github.com/SoLl1XZ/Macro-Dashboard (offentligt). Siden: https://soll1xz.github.io/Macro-Dashboard/
- `.github/workflows/update.yml` kører kl. 06:00 UTC, ved push til `main` og manuelt (`gh workflow run update.yml`):
  tests → `fetch_data.py` → commit af `data/data.js` → publicering af `index.html`, `app.js`, `style.css`, `favicon.svg`, `data/` til Pages.
- Commits bruger noreply-adressen `222303744+SoLl1XZ@users.noreply.github.com` (sat i repoets lokale git-config), aldrig gmail.
- Spørg altid før `git push`. Hent bot-commits med `git pull` før lokale ændringer.
- Commit aldrig en lokalt genereret `data/data.js` (konflikt med botten). Kassér den før pull: `git restore data/data.js`.

## Kendte faldgruber

- **User-Agent:** FRED og IMF blokerer ukendte User-Agents, OECD blokerer Pythons standard. `curl/8.7.1` virker hos alle (se `USER_AGENT` i `fetch_data.py`).
- **SSL-fejl (`CERTIFICATE_VERIFY_FAILED`) lokalt:** python.org-Python bruger sin egen certifikatliste. Ret med `python3 -m pip install --upgrade certifi`.
- **Statistikbankens BULK-svar er ikke sorteret efter dato** – `to_observations` sorterer.
- **Eurostat:** eurozonen hedder `EA21` fra 2026 (`EA20` stopper i 2025; nogle datasæt bruger `EA`). År-over-år-vækst (`PCH_SM`) findes kun for kalenderkorrigerede data (`s_adj=CA`).
- **Manuelle lister:** CEPR-recessioner (`indicators.py`) og ECB/Fed-møder (`events.py`) har intet API. Siden advarer, når mødelisterne løber tør.
- **DOM:** `append()` returnerer `undefined`. Kæd aldrig `x.append(...).append(...)`; brug en variabel eller `appendChild()`.
- **MoF-filerne:** to filer (historik til forrige måned + indeværende måned), datoer som `2026/10/1`, `-` = ingen
  rente den dag, og den aktuelle fil slutter med en note i japansk tegnsæt (ikke UTF-8) – derfor `http_get(..., errors="replace")`.
- **Aktiekilder (testet 2026-10-08, aktiefanen udskudt):** Yahoo svarer `429` på vores User-Agent; Stooq kræver en
  JavaScript proof-of-work bot-udfordring – den omgås ikke; Euronext og Nasdaq Nordic afviser. Officielle muligheder:
  FRED (`SP500`, `NASDAQCOM`, `DJIA`, `NIKKEI225`), ECB (`FM/M.U2.EUR.DS.EI.DJES50I.HSTA` = Euro Stoxx 50, månedsgennemsnit)
  og OECD `DF_FINMARK` måling `SHARE` (brede nationale aktieindeks, månedligt – ikke DAX/CAC/OMXC25).
- **OECD:**
  - API'et svarede `403` under test 2026-10-08, sandsynligvis en hastighedsgrænse. Saml derfor lande med `+` i én forespørgsel pr. dataflow og måling (ca. 5 kald pr. kørsel).
  - En fejlet forespørgsel fælder kun sine egne serier (`PartialBatch`).
- **FRED's OECD-kopier er delvist døde:**
  - CPI (`CPALTT01`) og tillid (`CSCICP03`/`BSCICP03`) stoppede 2021–2025. Brug OECD direkte (`PRICES`, `CLI`).
  - Ledighed (`LRHUTTTT`), 3-mdr.-renter (`IR3TIB01`), dag-til-dag-renter (`IRSTCI01`) og kvartals-BNP (`NGDPRSAXDC`) virker.
  - UK's 3-mdr.-rente stoppede januar 2026 (kurven bruger SONIA), og Sveriges dag-til-dag-rente stoppede 2020.
- **IMF's kvartals-BNP (`QNEA`) kan have brud.** Kinas serie gav 9,5 % i 2026 mod OECD's 4,3 %, og Thailands årssummer passer ikke med WEO (2023: 4,8 % mod 2,2 %). Kun Malaysia, der passer med WEO, bruges. Tjek mod WEO, før et nyt land tages i brug.
- **Inflationsmål:** linjen vises kun ved faste centralbankmål.
  - Kina og Vietnam har årlige regeringsmål og Malaysia intet tal, så de har ingen linje.
  - Norge (KPI) og Sverige (KPIF) vises med HICP; beskrivelsen siger, at målet gælder et andet indeks.
- **Mangler en gratis kilde (testet 2026-10-08), så panelerne er udeladt:**
  - Styringsrente for Vietnam.
  - Statsrenter og rentekurve for Thailand, Vietnam, Indonesien og Malaysia. IMF `MFS_IR` har en "statsobligationsrente" uden løbetid, som ikke bruges.
  - Kvartals-BNP for Thailand og Vietnam.
  - Tillid for Thailand, Vietnam og Malaysia; Norge har kun erhvervstillid.
  - 2-årige renter findes kun for USA og Japan. ECB har kun eurozone-AAA, og Statistikbankens `DNRENTM` stoppede 2012.
  - Kerne-CPI for Canada, Japan, Kina og ASEAN/Indien. Japans FRED-serie stoppede 2021.
  - Industriproduktion for Japan/Korea (stoppede 2024-03).
  - Månedlig ledighed for de asiatiske EM-lande (kun årlig fra IMF).
  - Officielle kilder uden nøgle, der virker, men ikke er tilføjet (Eriks beslutning): Bank of Canada Valet (2 år, CPI-trim), Riksbank SWEA (2 år, SWESTR), SCB (KPIF), ONS og Bank Negara Malaysia.
- **Menuen:**
  - Fanerne genopbygges ved hver navigation. Tastaturfokus flyttes derfor tilbage (`restoreNavFocus`).
  - En lukket menu er `inert`, ellers kan Tab nå dens links, mens de fader ud.
  - Under 600 px er hover-menuen slået fra, og landerækken bruges.
- **Browser-cache ved lokal test:** `python3 -m http.server` får browseren til at genbruge gammel `style.css`/`app.js`. Hent dem med `fetch(fil, {cache: "reload"})` før `location.reload()`.
- **"Forældet" er generelle grænser pr. frekvens:** BIS' kreditdata udkommer ca. 2 kvartaler forsinket og markeres derfor
  som forældede, selvom det er normalt. Ugens bevægelser tæller kun serier med data fra de seneste 7 dage.
- **Ingen to y-akser** (heller ikke i Sammenlign): forskellige enheder vises som to grafer, eller begge omregnes til indeks 100.
