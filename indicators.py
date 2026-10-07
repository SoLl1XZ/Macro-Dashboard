"""Catalog of every indicator shown on the dashboard.

A Panel is one card on the page (one chart). It holds one or more Series.
The first series in a panel is the "primary" one whose latest value is
shown as the headline number.

Query format per source:
    fred      FRED series id                       "DGS10"
    ecb       ECB flow/key                         "FM/D.U2.EUR.4F.KR.DFR.LEV"
    eurostat  dataset?filters                      "prc_hicp_minr?geo=EA&coicop18=TOTAL&unit=RCH_A"
    bis       WS_CBPOL key (policy rates)          "D.US"
    imf_weo   IMF DataMapper indicator/country     "NGDP_RPCH/WEOWORLD"
    imf_cpi   IMF CPI year-over-year, country      "JPN"
    oecd_lt   OECD 10-year government bond yield   "DEU"
    statbank  Statistics Denmark table?filters     "AUS08?OMRÅDE=000&SAESONFAK=9"
    derived   computed from other series           ("it_10y", "de_10y")
"""

from dataclasses import dataclass

SECTIONS: list[tuple[str, str]] = [
    ("global", "Global"),
    ("us", "USA"),
    ("europe", "Europa"),
    ("denmark", "Danmark"),
    ("asia", "Asien"),
    ("china", "Kina"),
]


@dataclass(frozen=True)
class Series:
    key: str
    label: str
    source: str
    query: str | tuple[str, str]
    # None = use as delivered; "yoy" = % change vs. same period last year;
    # "diff" = change vs. previous observation; "spread" = a - b in %-points.
    transform: str | None = None


@dataclass(frozen=True)
class Panel:
    id: str
    section: str
    title: str
    unit: str
    description: str
    series: tuple[Series, ...]
    # How headline changes are shown: "diff" = difference in the unit (%-points for rates),
    # "pct" = percent change (prices, indices, exchange rates).
    change: str = "diff"
    decimals: int = 2  # values >= 1000 are always shown without decimals
    # Optional sub-heading within the section. Panels of one group must be adjacent.
    group: str | None = None


def S(key: str, label: str, source: str, query, transform: str | None = None) -> Series:
    return Series(key, label, source, query, transform)


PANELS: list[Panel] = [
    # ------------------------------------------------------------------ GLOBAL
    Panel("oil", "global", "Olie", "USD/tønde",
          "Råoliepris. Påvirker inflation, handelsbalancer og centralbankernes renteudsigter.",
          (S("brent", "Brent", "fred", "DCOILBRENTEU"),
           S("wti", "WTI", "fred", "DCOILWTICO")), change="pct"),
    Panel("gas", "global", "Naturgas", "USD/MMBtu",
          "Gaspris i USA (Henry Hub, daglig) og Europa (månedlig). Vigtig for europæisk energiinflation.",
          (S("gas_us", "Henry Hub (USA)", "fred", "DHHNGSP"),
           S("gas_eu", "Europa", "fred", "PNGASEUUSDM")), change="pct"),
    Panel("copper", "global", "Kobber", "USD/ton",
          "Kaldes 'Dr. Copper': følsom over for global industriproduktion og byggeri.",
          (S("copper", "Kobber", "fred", "PCOPPUSDM"),), change="pct"),
    Panel("wheat", "global", "Hvede", "USD/ton",
          "Global fødevarepris. Driver fødevareinflation, især i emerging markets.",
          (S("wheat", "Hvede", "fred", "PWHEAMTUSDM"),), change="pct"),
    Panel("dollar", "global", "Dollarindeks (bredt)", "Indeks",
          "Dollarens styrke mod handelspartnere. Stærk dollar strammer globale finansielle forhold.",
          (S("usd_broad", "Bredt dollarindeks", "fred", "DTWEXBGS"),), change="pct"),
    Panel("vix", "global", "VIX – frygtindeks", "Indeks",
          "Forventet volatilitet i S&P 500 de næste 30 dage. Over ~30 = stress på markederne.",
          (S("vix", "VIX", "fred", "VIXCLS"),)),
    Panel("policy_rates", "global", "Styringsrenter", "%",
          "Centralbankernes officielle renter side om side.",
          (S("pr_us", "USA (Fed)", "bis", "D.US"),
           S("pr_ea", "Eurozone (ECB)", "bis", "D.XM"),
           S("pr_gb", "UK (BoE)", "bis", "D.GB"),
           S("pr_jp", "Japan (BoJ)", "bis", "D.JP"),
           S("pr_cn", "Kina (PBoC)", "bis", "D.CN"),
           S("pr_dk", "Danmark (NB)", "bis", "D.DK"),
           S("pr_ch", "Schweiz (SNB)", "bis", "D.CH"))),
    Panel("world_gdp", "global", "BNP-vækst inkl. IMF-prognose", "% år/år",
          "Real BNP-vækst. Indeværende og kommende år er IMF-prognoser (World Economic Outlook).",
          (S("gdp_world", "Verden", "imf_weo", "NGDP_RPCH/WEOWORLD"),
           S("gdp_adv", "Avancerede økonomier", "imf_weo", "NGDP_RPCH/ADVEC"),
           S("gdp_em", "Emerging markets", "imf_weo", "NGDP_RPCH/OEMDC"))),
    Panel("world_infl", "global", "Inflation inkl. IMF-prognose", "% år/år",
          "Gennemsnitlig forbrugerprisinflation. Indeværende og kommende år er IMF-prognoser.",
          (S("infl_world", "Verden", "imf_weo", "PCPIPCH/WEOWORLD"),
           S("infl_adv", "Avancerede økonomier", "imf_weo", "PCPIPCH/ADVEC"),
           S("infl_em", "Emerging markets", "imf_weo", "PCPIPCH/OEMDC"))),

    # --------------------------------------------------------------------- USA
    Panel("us_fed", "us", "Fed funds-rente", "%",
          "Fed's målinterval (øvre/nedre) og den faktiske effektive rente.",
          (S("us_ffr", "Effektiv rente", "fred", "DFF"),
           S("us_ff_upper", "Mål (øvre)", "fred", "DFEDTARU"),
           S("us_ff_lower", "Mål (nedre)", "fred", "DFEDTARL"))),
    Panel("us_yields", "us", "Statsrenter (Treasuries)", "%",
          "Renten på amerikanske statsobligationer: verdens vigtigste 'risikofri' rente.",
          (S("us_10y", "10 år", "fred", "DGS10"),
           S("us_3m", "3 mdr.", "fred", "DGS3MO"),
           S("us_2y", "2 år", "fred", "DGS2"),
           S("us_30y", "30 år", "fred", "DGS30"))),
    Panel("us_curve", "us", "Rentekurve-spreads", "%-point",
          "Forskel mellem lang og kort rente. Negativ (inverteret kurve) har historisk varslet recession.",
          (S("us_10y2y", "10 år − 2 år", "fred", "T10Y2Y"),
           S("us_10y3m", "10 år − 3 mdr.", "fred", "T10Y3M"))),
    Panel("us_credit", "us", "Kreditspreads", "%-point",
          "Merrente på virksomhedsobligationer over statsrenter. Stiger når markedet frygter konkurser.",
          (S("us_hy", "High yield", "fred", "BAMLH0A0HYM2"),
           S("us_ig", "Investment grade", "fred", "BAMLC0A0CM"))),
    Panel("us_inflation", "us", "Inflation", "% år/år",
          "Forbrugerpriser (CPI) og Fed's foretrukne mål: kerne-PCE. Fed sigter efter 2 %.",
          (S("us_cpi", "CPI", "fred", "CPIAUCSL", "yoy"),
           S("us_core_cpi", "Kerne-CPI", "fred", "CPILFESL", "yoy"),
           S("us_core_pce", "Kerne-PCE", "fred", "PCEPILFE", "yoy"))),
    Panel("us_breakeven", "us", "Inflationsforventning (10 år)", "%",
          "Markedets forventede gennemsnitlige inflation de næste 10 år (breakeven).",
          (S("us_be10", "10-årig breakeven", "fred", "T10YIE"),)),
    Panel("us_unemployment", "us", "Ledighed", "%",
          "Arbejdsløshedsprocent. Halvdelen af Fed's dobbelte mandat.",
          (S("us_unrate", "Ledighed", "fred", "UNRATE"),)),
    Panel("us_payrolls", "us", "Nye job (nonfarm payrolls)", "1.000 job/md.",
          "Månedlig ændring i antal lønmodtagere uden for landbruget.",
          (S("us_nfp", "Ændring i job", "fred", "PAYEMS", "diff"),)),
    Panel("us_claims", "us", "Nye ledighedsansøgninger", "Antal/uge",
          "Ugentlige førstegangsansøgninger om dagpenge. Tidlig indikator for arbejdsmarkedet.",
          (S("us_icsa", "Ansøgninger", "fred", "ICSA"),), change="pct"),
    Panel("us_gdp", "us", "BNP-vækst", "% (annualiseret k/k)",
          "Real BNP-vækst i kvartalet, omregnet til årlig takt.",
          (S("us_gdp", "Real BNP", "fred", "A191RL1Q225SBEA"),)),
    Panel("us_sentiment", "us", "Forbrugertillid", "Indeks",
          "University of Michigan Consumer Sentiment.",
          (S("us_umcsent", "Forbrugertillid", "fred", "UMCSENT"),)),
    Panel("us_mortgage", "us", "30-årig boligrente", "%",
          "Gennemsnitlig rente på nye 30-årige fastforrentede boliglån.",
          (S("us_mort30", "30-årig fast", "fred", "MORTGAGE30US"),)),
    Panel("us_equities", "us", "S&P 500", "Indeks",
          "De 500 største amerikanske aktier.",
          (S("sp500", "S&P 500", "fred", "SP500"),), change="pct"),

    # ------------------------------------------------------------------ EUROPA
    Panel("ecb_rates", "europe", "ECB-renter", "%",
          "ECB styrer med indlånsrenten. €STR er den faktiske dag-til-dag-rente mellem banker.",
          (S("ecb_dfr", "Indlånsrente", "ecb", "FM/D.U2.EUR.4F.KR.DFR.LEV"),
           S("ecb_mro", "Refinansieringsrente", "ecb", "FM/D.U2.EUR.4F.KR.MRR_FR.LEV"),
           S("estr", "€STR", "ecb", "EST/B.EU000A2X2A25.WT")),
          group="Renter og spreads"),
    Panel("ea_rate_expectation", "europe", "Markedets renteforventning", "%-point",
          "2-årig AAA-rente minus ECB's indlånsrente. Negativ: markedet venter rentenedsættelser. "
          "Positiv: markedet venter stigninger.",
          (S("ea_2y_dfr", "2 år − ECB-rente", "derived", ("ea_2y", "ecb_dfr"), "spread"),),
          group="Renter og spreads"),
    Panel("ea_curve", "europe", "Eurozone-rentekurve (AAA)", "%",
          "Renter på AAA-ratede eurozone-statsobligationer (ECB's daglige rentekurve).",
          (S("ea_10y", "10 år", "ecb", "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y"),
           S("ea_2y", "2 år", "ecb", "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y")),
          group="Renter og spreads"),
    Panel("ea_curve_spread", "europe", "Rentekurve-spread (AAA)", "%-point",
          "10-årig minus 2-årig AAA-rente. Negativ (inverteret kurve) har historisk varslet svag vækst.",
          (S("ea_10y2y", "10 år − 2 år", "derived", ("ea_10y", "ea_2y"), "spread"),),
          group="Renter og spreads"),
    Panel("eu_10y", "europe", "10-årige statsrenter: Tyskland og Frankrig", "%",
          "Månedlige gennemsnit for eurozonens to største økonomier.",
          (S("de_10y", "Tyskland", "oecd_lt", "DEU"),
           S("fr_10y", "Frankrig", "oecd_lt", "FRA")),
          group="Renter og spreads"),
    Panel("eu_10y_south", "europe", "10-årige statsrenter: Sydeuropa", "%",
          "Månedlige gennemsnit for de lande, der var i centrum af gældskrisen i 2010–2012.",
          (S("it_10y", "Italien", "oecd_lt", "ITA"),
           S("es_10y", "Spanien", "oecd_lt", "ESP"),
           S("gr_10y", "Grækenland", "oecd_lt", "GRC"),
           S("pt_10y", "Portugal", "oecd_lt", "PRT")),
          group="Renter og spreads"),
    Panel("eu_spreads", "europe", "Statsrente-spreads til Tyskland", "%-point",
          "Merrente over tyske statsobligationer. Måler uro om gæld i eurozonen.",
          (S("btp_bund", "Italien − Tyskland", "derived", ("it_10y", "de_10y"), "spread"),
           S("oat_bund", "Frankrig − Tyskland", "derived", ("fr_10y", "de_10y"), "spread"),
           S("bono_bund", "Spanien − Tyskland", "derived", ("es_10y", "de_10y"), "spread"),
           S("ggb_bund", "Grækenland − Tyskland", "derived", ("gr_10y", "de_10y"), "spread"),
           S("pgb_bund", "Portugal − Tyskland", "derived", ("pt_10y", "de_10y"), "spread")),
          group="Renter og spreads"),
    Panel("ea_inflation", "europe", "Inflation (HICP)", "% år/år",
          "Eurozonens harmoniserede forbrugerpriser. ECB sigter efter 2 %.",
          (S("ea_hicp", "HICP", "eurostat", "prc_hicp_minr?geo=EA&coicop18=TOTAL&unit=RCH_A"),
           S("ea_core", "Kerne (ekskl. energi og fødevarer)", "eurostat",
             "prc_hicp_minr?geo=EA&coicop18=TOT_X_NRG_FOOD&unit=RCH_A"),
           S("ea_services", "Serviceydelser", "eurostat", "prc_hicp_minr?geo=EA&coicop18=SERV&unit=RCH_A")),
          group="Inflation"),
    Panel("ea_gdp", "europe", "BNP-vækst (eurozonen)", "% år/år",
          "Real BNP-vækst sammenlignet med samme kvartal året før.",
          (S("ea_gdp", "Real BNP", "ecb", "MNA/Q.Y.I9.W2.S1.S1.B.B1GQ._Z._Z._Z.EUR.LR.GY"),),
          group="Vækst og arbejdsmarked"),
    Panel("ea_unemployment", "europe", "Ledighed (eurozonen)", "%",
          "Sæsonkorrigeret arbejdsløshed i eurozonen.",
          (S("ea_unrate", "Ledighed", "ecb", "LFSI/M.I9.S.UNEHRT.TOTAL0.15_74.T"),),
          group="Vækst og arbejdsmarked"),
    Panel("ea_lending", "europe", "Udlånsrenter i eurozonen", "%",
          "Bankernes samlede lånerente for virksomheder og for boliglån til husholdninger.",
          (S("ea_lend_nfc", "Virksomheder", "ecb", "MIR/M.U2.B.A2I.AM.R.A.2240.EUR.N"),
           S("ea_lend_hh", "Boliglån", "ecb", "MIR/M.U2.B.A2C.AM.R.A.2250.EUR.N")),
          group="Kredit og penge"),
    Panel("ea_m3", "europe", "Pengemængde M3", "% år/år",
          "Vækst i pengemængden. Lav vækst kan signalere stram kreditgivning.",
          (S("ea_m3", "M3", "ecb", "BSI/M.U2.Y.V.M30.X.I.U2.2300.Z01.A"),),
          group="Kredit og penge"),
    Panel("eu_credit", "europe", "Euro high yield-spread", "%-point",
          "Merrente på risikable europæiske virksomhedsobligationer.",
          (S("eu_hy", "Euro high yield", "fred", "BAMLHE00EHYIOAS"),),
          group="Kredit og penge"),
    Panel("eurusd", "europe", "EUR/USD", "USD pr. EUR",
          "Eurokursen over for dollar (ECB's referencekurs).",
          (S("eurusd", "EUR/USD", "ecb", "EXR/D.USD.EUR.SP00.A"),), change="pct", decimals=4,
          group="Valuta"),
    Panel("uk", "europe", "UK: renter og inflation", "%",
          "Bank of Englands styringsrente, 10-årig statsrente og britisk CPI-inflation.",
          (S("uk_bank_rate", "BoE-rente", "bis", "D.GB"),
           S("gb_10y", "10-årig statsrente", "oecd_lt", "GBR"),
           S("uk_cpi", "CPI (% år/år)", "imf_cpi", "GBR")),
          group="Storbritannien"),

    # ----------------------------------------------------------------- DANMARK
    Panel("dk_rates", "denmark", "Nationalbankens renter", "%",
          "Nationalbanken følger ECB for at holde fastkursen. DESTR er den danske dag-til-dag-rente.",
          (S("dk_cd", "Indskudsbevisrente", "statbank", "DNRENTD?INSTRUMENT=OIBNAA&LAND=DK&OPGOER=E"),
           S("dk_current", "Foliorente", "statbank", "DNRENTD?INSTRUMENT=OFONAA&LAND=DK&OPGOER=E"),
           S("dk_lending", "Udlånsrente", "statbank", "DNRENTD?INSTRUMENT=OIRNAA&LAND=DK&OPGOER=E"),
           S("destr", "DESTR", "statbank", "DNRENTD?INSTRUMENT=DESNAA&LAND=DK&OPGOER=E"))),
    Panel("dk_ecb_spread", "denmark", "Rentespænd til ECB", "%-point",
          "Nationalbankens indskudsbevisrente minus ECB's indlånsrente. Bruges til at forsvare kronen.",
          (S("dk_ecb", "Danmark − ECB", "derived", ("dk_cd", "ecb_dfr"), "spread"),)),
    Panel("eurdkk", "denmark", "EUR/DKK (fastkurs)", "DKK pr. EUR",
          "Kronen er bundet til euroen omkring centralkursen 7,46038.",
          (S("eurdkk", "EUR/DKK", "ecb", "EXR/D.DKK.EUR.SP00.A"),), change="pct", decimals=4),
    Panel("dk_10y", "denmark", "10-årig statsrente", "%",
          "Dansk 10-årig statsrente sammenlignet med Tyskland.",
          (S("dk_10y", "Danmark", "oecd_lt", "DNK"),
           S("dk_de_10y", "Spænd til Tyskland", "derived", ("dk_10y", "de_10y"), "spread"))),
    Panel("dk_mortgage", "denmark", "Realkreditrente (nye lån)", "%",
          "Gennemsnitlig rente inkl. bidrag på nye realkreditlån til husholdninger.",
          (S("dk_mort", "Nye lån, husholdninger", "statbank",
             "DNRNURI?DATA=AL51EFFR&INDSEK=1400&VALUTA=Z01&LØBETID1=ALLE&RENTFIX=ALLE&LAANSTR=ALLE"),)),
    Panel("dk_inflation", "denmark", "Inflation (forbrugerpriser)", "% år/år",
          "Ændring i forbrugerprisindekset sammenlignet med samme måned året før.",
          (S("dk_cpi", "Forbrugerprisindeks", "statbank", "PRIS01?VAREGR=000000&ENHED=300"),)),
    Panel("dk_unemployment", "denmark", "Ledighed", "% af arbejdsstyrken",
          "Sæsonkorrigeret bruttoledighed.",
          (S("dk_unrate", "Ledighed", "statbank", "AUS08?OMRÅDE=000&SAESONFAK=9"),)),
    Panel("dk_gdp", "denmark", "BNP-vækst", "% k/k",
          "Real, sæsonkorrigeret BNP-vækst i forhold til kvartalet før.",
          (S("dk_gdp", "Real BNP", "statbank", "NKN1?TRANSAKT=B1GQK&PRISENHED=L_V&SÆSON=Y"),)),
    Panel("dk_housing", "denmark", "Huspriser", "% år/år",
          "Prisudvikling på ejendomssalg i hele landet.",
          (S("dk_house", "Enfamiliehuse", "statbank", "EJ56?OMRÅDE=000&EJENDOMSKATE=0111&TAL=310"),
           S("dk_flat", "Ejerlejligheder", "statbank", "EJ56?OMRÅDE=000&EJENDOMSKATE=2103&TAL=310"))),
    Panel("dk_confidence", "denmark", "Forbrugertillid", "Nettotal",
          "Forbrugernes forventninger til egen og landets økonomi. Over 0 = optimisme.",
          (S("dk_ftillid", "Forbrugertillid", "statbank", "FORV1?INDIKATOR=F1"),)),

    # ------------------------------------------------------------------- ASIEN
    Panel("asia_policy", "asia", "Styringsrenter", "%",
          "Centralbankrenter i Japan, Indien og Sydkorea.",
          (S("jp_policy", "Japan (BoJ)", "bis", "D.JP"),
           S("in_policy", "Indien (RBI)", "bis", "D.IN"),
           S("kr_policy", "Sydkorea (BoK)", "bis", "D.KR"))),
    Panel("asia_10y", "asia", "10-årige statsrenter", "%",
          "Månedlige gennemsnit.",
          (S("jp_10y", "Japan", "oecd_lt", "JPN"),
           S("in_10y", "Indien", "oecd_lt", "IND"),
           S("kr_10y", "Sydkorea", "oecd_lt", "KOR"))),
    Panel("asia_inflation", "asia", "Inflation", "% år/år",
          "Forbrugerprisinflation (IMF).",
          (S("jp_cpi", "Japan", "imf_cpi", "JPN"),
           S("in_cpi", "Indien", "imf_cpi", "IND"),
           S("kr_cpi", "Sydkorea", "imf_cpi", "KOR"))),
    Panel("usdjpy", "asia", "USD/JPY", "JPY pr. USD",
          "Yenen over for dollar. Påvirkes stærkt af renteforskellen mellem USA og Japan.",
          (S("usdjpy", "USD/JPY", "fred", "DEXJPUS"),), change="pct"),
    Panel("asia_fx", "asia", "USD/INR og USD/KRW", "Lokal valuta pr. USD",
          "Indiske rupees og koreanske won over for dollar.",
          (S("usdinr", "USD/INR", "fred", "DEXINUS"),
           S("usdkrw", "USD/KRW", "fred", "DEXKOUS")), change="pct"),
    Panel("asia_gdp", "asia", "BNP-vækst inkl. IMF-prognose", "% år/år",
          "Real BNP-vækst. Indeværende og kommende år er IMF-prognoser.",
          (S("jp_gdp", "Japan", "imf_weo", "NGDP_RPCH/JPN"),
           S("in_gdp", "Indien", "imf_weo", "NGDP_RPCH/IND"),
           S("kr_gdp", "Sydkorea", "imf_weo", "NGDP_RPCH/KOR"))),
    Panel("nikkei", "asia", "Nikkei 225", "Indeks",
          "Japans førende aktieindeks.",
          (S("nikkei", "Nikkei 225", "fred", "NIKKEI225"),), change="pct"),

    # -------------------------------------------------------------------- KINA
    Panel("cn_lpr", "china", "Loan Prime Rate (1 år)", "%",
          "Kinas reelle styringsrente siden 2019 (benchmark for bankernes udlån).",
          (S("cn_lpr", "LPR 1 år", "bis", "D.CN"),)),
    Panel("cn_10y", "china", "10-årig statsrente", "%",
          "Kinesisk 10-årig statsrente sammenlignet med USA.",
          (S("cn_10y", "Kina", "oecd_lt", "CHN"),
           S("us_10y_m", "USA", "fred", "GS10"))),
    Panel("cn_inflation", "china", "Inflation", "% år/år",
          "Forbrugerprisinflation. Lav/negativ inflation har været et tegn på svag efterspørgsel.",
          (S("cn_cpi", "CPI", "imf_cpi", "CHN"),)),
    Panel("usdcny", "china", "USD/CNY", "CNY pr. USD",
          "Yuan over for dollar. Styres delvist af centralbanken.",
          (S("usdcny", "USD/CNY", "fred", "DEXCHUS"),), change="pct", decimals=4),
    Panel("cn_gdp", "china", "BNP-vækst inkl. IMF-prognose", "% år/år",
          "Real BNP-vækst. Indeværende og kommende år er IMF-prognoser.",
          (S("cn_gdp", "Kina", "imf_weo", "NGDP_RPCH/CHN"),)),
    Panel("cn_debt", "china", "Statsgæld", "% af BNP",
          "Bruttogæld i den offentlige sektor (IMF; indeværende og kommende år er prognoser).",
          (S("cn_debt", "Offentlig gæld", "imf_weo", "GGXWDG_NGDP/CHN"),)),
    Panel("cn_current_account", "china", "Betalingsbalance", "% af BNP",
          "Overskud på betalingsbalancens løbende poster (IMF; indeværende og kommende år er prognoser).",
          (S("cn_ca", "Løbende poster", "imf_weo", "BCA_NGDPD/CHN"),)),
]
