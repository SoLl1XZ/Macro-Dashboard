# Macro Dashboard

Statisk HTML-dashboard med makroøkonomiske nøgletal. Titlen er på engelsk; resten af siden er på dansk.
Et Python-script henter data fra offentlige API'er og skriver `data/data.js`, som siden læser.

## Faner, regioner og lande

- Topniveau: **Signaler** · Global · Aktier · Råvarer · Nordamerika · Europa · Asien · **Sammenlign**.
  - Signaler viser kalender, ugens største bevægelser og z-score-heatmap.
  - Global har dollarindeks, VIX, styringsrenter og verdens-BNP og -inflation.
  - Råvarer (`commodities`) har grupperne Indeks, Energi, Industrimetaller, Ædelmetaller, Landbrug og Analyse
    (alle `change="pct"`). Olie, gas, kobber og hvede er flyttet hertil med uændrede keys.
  - Aktier (`equities`) har kun månedsgennemsnit, så hele fanen opdateres samtidig, ca. en uge efter
    månedens udgang (Eriks valg 2026-10-08; en test låser det). Grupperne:
    - Regioner: OECD's brede indeks (2015 = 100) pr. region via `SHARE_PRICE_REGIONS`.
    - Kendte indeks: S&P 500, Euro Stoxx 50 og Nikkei 225 fra ECB. De daglige FRED-versioner på USA- og
      Japan-fanerne er flyttet hertil som månedlige med de gamle keys (`sp500`, `nikkei`).
    - Fald fra toppen (`drawdown`) med en linje ved −20 % (bjørnemarked).
    - Thailand, Vietnam og Malaysia mangler (ingen gratis kilde).
  - Sammenlign: vælg lande (højst 8, chips pr. region, hurtigvalg) og parametre (kernetitlerne).
    Én graf pr. parameter med fast farve pr. land, plus en tabel farvet efter 10-års-percentil.
    Den gamle sammenligning af to vilkårlige serier findes som "Avanceret" (`a=`/`b=`).
- Hver region har en oversigtsside, og dens lande glider ud ved hover eller fokus:
  - Nordamerika: `us`, `canada`
  - Europa: `uk`, `germany`, `france`, `denmark`, `norway`, `sweden`
  - Asien: `china`, `japan`, `korea`, `thailand`, `vietnam`, `indonesia`, `malaysia`, `india`
- Kun disse 16 lande må være på dashboardet.
- Strukturen er datadrevet: `SECTIONS` i `indicators.py` er `Section(id, title, region)` i menurækkefølge (låst af tests).
  - `app.js` bygger menuen og sætter Signaler først og Sammenlign sidst.
  - En ny topniveau-fane er én `Section(...)` uden region i listen (Aktier står mellem Global og Råvarer).
- **Gamle id'er bevares** (`us`, `europe`, `denmark`, `asia`, `china`, `japan`, `korea`), så gamle links som `#europe?range=10` virker.
- **Kernepaneler:**
  - Hver landefane starter med gruppen `CORE_GROUP` ("Kernetal") med titlerne i `CORE_TITLES`, i fast rækkefølge.
  - Et kernepanel udelades hellere, end at det viser noget forkert.
  - Landespecifikke paneler følger under `extras_group(land)` ("Særligt for …").
  - Fælles kernepaneler bygges med fabrikkerne `imf_gdp_panel`, `imf_unemployment_panel`, `confidence_panel`, `debt_panel` og `current_account_panel`.
- **Genbrug med `R(key, label)`** (`Ref`): et panel kan vise en serie, som et andet panel ejer, fx landenes tal i regionsoversigterne.
  - Hver serie-key ejes af præcis ét panel og hentes én gang.
  - Siden fylder ejerens data ind (`resolveReferences`) inkl. ejerens enhed og `change`.
  - Signaler og Sammenlign tæller kun ejeren, så intet vises to gange.
- **Andre panel-felter:**
  - `split=True`: én graf pr. serie med fælles tidsakse, til serier i forskellige enheder (aldrig to y-akser).
  - `comparable="<key>"`: den serie, Sammenlign bruger, når det ikke er den første. Danmark viser fx
    bruttoledighed og KPI først, men sammenlignes med harmoniseret ledighed og HICP.
- **`INPUT_SERIES`** hentes kun som input til beregninger (fx US CPI-niveau til real oliepris) og vises ikke.
- **Derived-beregninger:** `spread` (a − b), `ratio` (a / b), `real` (a i seneste måneds priser via indeks b)
  og med ét input `drawdown` (% under den hidtil højeste værdi siden `FETCH_START`).

## URL'en (eneste kilde til tilstand)

`#<fane>?range=7&panel=jp_jgb&full=1&from=2007-01&to=2012-12` — parsing og opbygning er rene funktioner i
`lib.js` (`parseHashState`, `buildHash`), testet med Node.

| Parameter | Betydning |
|---|---|
| `range` | Periode i hele år, 1–100, eller 0 = Maks. Mangler den, er det 5 år. Ugyldige værdier giver 5. |
| `panel` | Scroll til panelet og fremhæv det (søgning, Signaler, delte links). |
| `full=1` | Åbn panelet i fuldskærm. Tilbage-knappen lukker. |
| `from`, `to` | Udsnit (`YYYY-MM`) i fuldskærm. Uden for fuldskærm er en grafs udsnit kun i hukommelsen. |
| `c`, `p` | Sammenlign: lande (`c=denmark,sweden`) og parametre med stabile slugs (`p=inflation,ledighed`). |
| `a`, `b`, `index` | Sammenlign, avanceret: to serie-keys og indeks 100. |

## Funktioner på siden

- **Søgning** (Ctrl/Cmd+K, "/" eller luppen): indbygget `<dialog>`. Matcher i `lib.js`: æøå og accenter ignoreres,
  1–2 stavefejl tolereres, synonymer (`SYNONYMS`, fx gold → guld), og ord i serienavne tæller halvt.
- **Fuldskærm**: udvid-knap på hvert kort (eller klik på grafen med mus). Zoom/pan kun på x-aksen med
  chartjs-plugin-zoom 2.2.0 + hammerjs 2.0.8 (pinned med SRI); y-aksen følger det synlige udsnit af sig selv.
- **Tidsudsnit pr. graf**: en slider med oversigt under hver graf (`renderRangeSlider`). Udsnittet gemmes pr. panel
  (`panelWindows`) og nulstilles, når den globale periode ændres. I fuldskærm er slider, zoom og kortet bagved synkroniseret.
- **Ydelse**: grafer oprettes først, når de er inden for 300 px af skærmen, og ødelægges, når de forsvinder
  (`showCharts`, IntersectionObserver). Kun `.chart > canvas` er grafer; sliderens oversigt er også et canvas.

## Kør

```bash
python3 fetch_data.py      # henter alle serier og skriver data/data.js
open index.html            # åbner dashboardet (virker via file://)
```

Kun Pythons standardbibliotek bruges; der skal ikke installeres pakker.

## Test

```bash
python3 -m unittest discover tests     # Python: katalog, hentning, beregninger
node --test tests/js/*.test.js          # JavaScript: lib.js (URL, Sammenlign-valg, søgning)
```

Node er installeret med Homebrew; testene bruger kun Nodes indbyggede test-runner (ingen npm-pakker).
GitHub Actions kører begge.

## Struktur

| Fil | Ansvar |
|-----|--------|
| `indicators.py` | Sektioner og regioner, katalog over alle serier (kilde, id, sektion, gruppe, enhed, beregning, referencelinjer, refs), kernetitler, CEPR-recessioner |
| `events.py` | ECB- og Fed-mødedatoer (manuel liste med kilder) og kalenderlogik |
| `fetch_data.py` | Henter serier fra hver kilde, recessioner (USREC) og Eurostats udgivelseskalender; skriver `data/data.js` |
| `transforms.py` | Beregninger: år-over-år, spreads, fald fra toppen, ændringer, percentil, z-score, ugebevægelse, recessionsperioder |
| `lib.js` | Ren logik uden DOM (URL-tilstand, Sammenlign-valg, søgematch); indlæses før `app.js` og testes med Node |
| `index.html`, `style.css`, `app.js`, `favicon.svg` | Selve dashboardet (Chart.js + zoom-plugin fra CDN med SRI) |
| `data/data.js` | Genereret data: `window.MACRO_DATA = {...}`. Committes kun af GitHub Actions-botten |
| `tests/` | Python-tests (unittest), `tests/js/` (Node) og `tests/fixtures/` (lille Pink Sheet-xlsx + scriptet, der laver den) |

## Datakilder

- FRED (St. Louis Fed) – CSV-endpoint uden API-nøgle: `fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIE>`.
  Rummer også OECD- og IMF-serier, fx ledighed (`LRHUTTTT..M156S`), eksport (`XTEXVA01..M664S`),
  real BNP (`NGDPRSAXDC..Q`) og 3-mdr. renter (`IR3TIB01..M156N`) for Japan og Korea.
- ECB Data Portal – `data-api.ecb.europa.eu`, inkl. månedlige aktieindeks (`FM/M.<land>.<valuta>.DS.EI.<indeks>.HSTA`).
  `HSTA` er månedsgennemsnittet af daglige lukkekurser (krydstjekket mod FRED's daglige S&P 500: samme tal).
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
  - `FINMARK`: renter `IRLT` / `IR3TIB` (enhed `PA`) og aktieindeks `SHARE` (enhed `IX`, se `FINMARK_UNITS`)
  - `CLI`: tillid `CCICP` / `BCICP`
  - `PRICES`: kerne-CPI `_TXCP01_NRG`
  - `QNA`: BNP-vækst år/år `GY` for Kina og Indien
- Eurostat for HICP, kerne-HICP, ledighed og BNP for DE, FR, DK, NO og SE (`geo=..`); ECB for valuta over for EUR
- Danmarks Statistik (inkl. Nationalbankens tal) – `api.statbank.dk/v1`
- FRED's IMF-råvarepriser (månedlige, fx `PALUMUSDM`, `PNGASJPUSDM`, `PIORECRUSDM`) og råvareindeks
  (`PALLFNFINDEXM`, `PNRGINDEXM`, `PMETAINDEXM`, `PFOODINDEXM`, 2016 = 100). Kaffe og sukker er i US cents/lb, uran i USD/lb.
- Verdensbankens Pink Sheet (`worldbank`, forespørgsel = kolonneoverskrift, fx `"Gold"`): guld, sølv og platin,
  som FRED ikke længere har. Månedlig xlsx, læst med `zipfile` + `xml.etree`.
- Japans finansministerium (`mof`) – JGB-rentekurven 1–40 år, dagligt: `historical/jgbcme_all.csv` + `jgbcme.csv`

## Vigtige beslutninger

- Data gemmes som `.js` (ikke `.json`), fordi en side åbnet via `file://` ikke må `fetch()` lokale filer.
- FRED tillader ikke browser-kald (ingen CORS), derfor hentes alt i Python frem for i browseren.
- Automatisk opdatering sker via GitHub Actions; siden publiceres med GitHub Pages.

## GitHub og automatisk opdatering

- Repo: https://github.com/SoLl1XZ/Macro-Dashboard (offentligt). Siden: https://soll1xz.github.io/Macro-Dashboard/
- `.github/workflows/update.yml` kører kl. 06:17 UTC (ikke på hel time, som GitHub ofte springer over eller udsætter:
  06:00-kørslen den 8. oktober startede først 12:21), ved push til
  `main` og manuelt (`gh workflow run update.yml`): Python- og JS-tests → `fetch_data.py` → commit af `data/data.js` →
  publicering af `index.html`, `lib.js`, `app.js`, `style.css`, `favicon.svg`, `data/` til Pages.
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
- **Aktiekilder (testet 2026-10-08):**
  - Fravalgt: Yahoo svarer `429` på vores User-Agent. Stooq kræver en JavaScript proof-of-work bot-udfordring, som
    ikke omgås. Euronext og Nasdaq Nordic afviser. MSCI's end-of-day-endpoint svarer, men vilkårene forbyder
    automatisk udtræk og videregivelse.
  - Daglige tal uden nøgle findes kun på FRED (`SP500` og `DJIA` kun 10 år, `NASDAQCOM`, `NIKKEI225`). De bruges ikke,
    fordi Aktier skal opdateres samtidig.
  - OECD's `SHARE`: euroområdet er præcis Euro Stoxx, og Danmark er OMXC (alle aktier); begge krydstjekket.
    USA og Japan er bredere indeks end S&P 500 og Nikkei (de vokser langsommere), men OECD nævner ikke hvilke.
  - Danmarks Statistik `MPK13` har OMXC25 og sektorer, men en måned senere end OECD og ECB.
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
  - Under 820 px scroller fanerne sidelæns, hover-menuen er slået fra, og landerækken bruges. Med 8 faner kræver
    menuen 786 px (741 px uden pilene). Tilføjes en fane, så mål menuens bredde og flyt grænsen i `style.css`.
- **Browser-cache ved lokal test:** `python3 -m http.server` får browseren til at genbruge gammel `style.css`/`app.js`. Hent dem med `fetch(fil, {cache: "reload"})` før `location.reload()`.
- **"Forældet" er generelle grænser pr. frekvens** (`MAX_AGE_DAYS`). En kilde, der altid er langsommere, får sin egen
  grænse med `S(..., max_age_days=365)` (BIS' kreditdata, IMF's kvartals-BNP for Malaysia). Ugens bevægelser tæller kun
  serier med data fra de seneste 7 dage.
- **Netværk:** `http_get` prøver igen ved timeout, afbrudt forbindelse (`RemoteDisconnected`), afkortet svar
  (`IncompleteRead`), 429 og 5xx. En 4xx betyder en forkert forespørgsel og prøves ikke igen, undtagen FRED: den kan
  svare 404 for en serie, der findes (set fra GitHubs servere 2026-10-08), så `fetch_fred` prøver en 404 én gang mere
  (`retry_not_found`).
- **Y-aksen:** `maxTicksLimit: 8`. Med færre springer Chart.js til et groft trin, og akser bliver halvtomme
  (JGB: −2 til 6 for data mellem −0,13 og 4,17). Mål på alle grafer efter ændringer: data skal fylde mindst 60 % af aksen.
  Bevidst undtagelse: en referencelinje er altid med på aksen (`suggestedMin`/`suggestedMax`), så fx "Fald fra toppen i
  Nordamerika" ved 1 år går ned til −20 % for data mellem −4 og 0.
- **Panel-anker ved genindlæsning:** med `panel=` i URL'en sættes `history.scrollRestoration = "manual"`, ellers lægger
  browseren sin gamle scrollposition oven på scroll til panelet.
- **Smalle telefoner (320 px):** ændringer kan brydes mellem tal og enhed; "%‑point" har en ikke-brydende bindestreg (U+2011).
- **Ingen to y-akser** (heller ikke i Sammenlign): forskellige enheder vises som to grafer, eller begge omregnes til indeks 100.
  Valuta i Sammenlign vises som indeks 100 og som noteret (USD/XXX stiger, når valutaen svækkes; EUR/USD og GBP/USD omvendt).
- **Pink Sheet:** linket til `CMO-Historical-Data-Monthly.xlsx` indeholder en hash, der skifter med hver årgang,
  så det findes på `worldbank.org/en/research/commodity-markets` ved hver kørsel. "…" = ingen pris.
- **Lokale browsertests:** i et skjult browserpanel kører hverken `requestAnimationFrame` eller IntersectionObserver,
  så lazy grafer bliver ikke oprettet der. Det er ikke en fejl i siden.
- **Browserværktøjets taster:** "slash" og "Page_Down" sender en tom tast; brug "PageDown", og test "/" med en syntetisk hændelse.
