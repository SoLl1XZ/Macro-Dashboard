"""Catalog of every indicator shown on the dashboard.

A Panel is one card on the page (one chart). It holds one or more Series.
The first series in a panel is the "primary" one whose latest value is
shown as the headline number.

Query format per source:
    fred      FRED series id                       "DGS10"
    ecb       ECB flow/key                         "FM/D.U2.EUR.4F.KR.DFR.LEV"
    eurostat  dataset?filters                      "prc_hicp_minr?geo=EA&coicop18=TOTAL&unit=RCH_A"
    bis       WS_CBPOL key (policy rates), or      "D.US"
              dataflow/key                         "WS_XRU/D.ID.IDR.A"
    imf_weo   IMF DataMapper indicator/country     "NGDP_RPCH/WEOWORLD"
    imf_cpi   IMF CPI year-over-year, country      "JPN"
    imf_qnea  IMF quarterly real GDP, country      "MYS"
    oecd      OECD dataflow/measure/country        "FINMARK/IRLT/DEU" (see OECD_DATAFLOWS)
    statbank  Statistics Denmark table?filters     "AUS08?OMRÅDE=000&SAESONFAK=9"
    worldbank Pink Sheet column header             "Gold"
    derived   computed from other series           ("fr_10y", "de_10y")
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    # The id of the region the section belongs to, or None for a top-level tab.
    # A top-level section that other sections point to is that region's overview.
    region: str | None = None


# Menu order. The page puts Signaler in front and Sammenlign at the end; a region's
# countries fold out under it. The old ids (us, europe, denmark, asia, china, japan, korea)
# are kept, so links from before the regions still work.
SECTIONS: list[Section] = [
    Section("global", "Global"),
    Section("north-america", "Nordamerika"),
    Section("us", "USA", "north-america"),
    Section("canada", "Canada", "north-america"),
    Section("europe", "Europa"),
    Section("uk", "Storbritannien", "europe"),
    Section("germany", "Tyskland", "europe"),
    Section("france", "Frankrig", "europe"),
    Section("denmark", "Danmark", "europe"),
    Section("norway", "Norge", "europe"),
    Section("sweden", "Sverige", "europe"),
    Section("asia", "Asien"),
    Section("china", "Kina", "asia"),
    Section("japan", "Japan", "asia"),
    Section("korea", "Sydkorea", "asia"),
    Section("thailand", "Thailand", "asia"),
    Section("vietnam", "Vietnam", "asia"),
    Section("indonesia", "Indonesien", "asia"),
    Section("malaysia", "Malaysia", "asia"),
    Section("india", "Indien", "asia"),
]

# Every country tab starts with these panels, in this order and with these titles, so the
# countries read the same way. A panel without a trustworthy free source is left out.
CORE_GROUP = "Kernetal"
CORE_TITLES = ("Styringsrente", "Statsrenter", "Rentekurve", "Inflation", "Ledighed",
               "BNP-vækst (kvartal)", "BNP-vækst inkl. IMF-prognose", "Valuta",
               "Forbruger- og erhvervstillid", "Statsgæld", "Betalingsbalance")


def extras_group(country: str) -> str:
    """Heading for a country's own panels after the core ones."""
    return f"Særligt for {country}"


@dataclass(frozen=True)
class Series:
    key: str
    label: str
    source: str
    query: str | tuple[str, str]
    # None = use as delivered; "yoy" = % change vs. same period last year;
    # "diff" = change vs. previous observation. Derived series: "spread" = a - b in
    # %-points, "ratio" = a / b, "real" = a in the prices of b's latest month.
    transform: str | None = None


@dataclass(frozen=True)
class Ref:
    """Shows a series that another panel owns, e.g. a country's inflation in a regional overview.

    The data is fetched once, and the Signals tab only counts it where it is owned.
    """
    key: str
    label: str


@dataclass(frozen=True)
class Panel:
    id: str
    section: str
    title: str
    unit: str
    description: str
    series: tuple[Series | Ref, ...]
    # How headline changes are shown: "diff" = difference in the unit (%-points for rates),
    # "pct" = percent change (prices, indices, exchange rates).
    change: str = "diff"
    decimals: int = 2  # values >= 1000 are always shown without decimals
    # Optional sub-heading within the section. Panels of one group must be adjacent.
    group: str | None = None
    # Horizontal reference lines as (value, label), e.g. an inflation target.
    reference_lines: tuple[tuple[float, str], ...] = ()


# Euro area recessions as (peak quarter, trough quarter) from the CEPR-EABCN Business Cycle
# Dating Committee, checked 2026-10-07 at
# https://eabcn.org/dbc/peaksandtroughs/chronology-euro-area-business-cycles
# The committee has no API, so a new decision must be added here by hand. Earlier
# recessions (1974–1993) are left out: the dashboard starts in 2000.
EURO_AREA_PEAKS_AND_TROUGHS = [("2008-Q1", "2009-Q2"), ("2011-Q3", "2013-Q1"), ("2019-Q4", "2020-Q2")]

# Which recession dating is shaded behind the charts of each section.
RECESSIONS_BY_SECTION = {"us": "us", "europe": "euro_area", "germany": "euro_area",
                         "france": "euro_area", "denmark": "euro_area"}

INFLATION_TARGET_FED = ((2.0, "Fed-mål 2 %"),)
INFLATION_TARGET_ECB = ((2.0, "ECB-mål 2 %"),)


def S(key: str, label: str, source: str, query, transform: str | None = None) -> Series:
    return Series(key, label, source, query, transform)


def R(key: str, label: str) -> Ref:
    return Ref(key, label)


# Series that are fetched only as input to derived series, never shown on their own.
INPUT_SERIES: list[Series] = [
    # The CPI level (not its growth, which us_cpi shows) turns prices into today's dollars.
    S("us_cpi_index", "USA: forbrugerprisindeks", "fred", "CPIAUCSL"),
]


def owned_series(panels: list[Panel]) -> list[Series]:
    """Every series the catalog fetches: references are left out, their data comes from the owner."""
    return [s for panel in panels for s in panel.series if isinstance(s, Series)]


# Core panels that are built the same way for every country. `prefix` names the keys
# (e.g. "ca" gives ca_debt); `code` is the IMF/OECD country code (e.g. "CAN").

def imf_gdp_panel(section: str, key: str, code: str) -> Panel:
    return Panel(key, section, "BNP-vækst inkl. IMF-prognose", "% år/år",
                 "Real BNP-vækst pr. år. Indeværende og kommende år er IMF-prognoser.",
                 (S(key, "Real BNP", "imf_weo", f"NGDP_RPCH/{code}"),), group=CORE_GROUP)


def imf_unemployment_panel(section: str, prefix: str, code: str) -> Panel:
    # For countries without monthly data in our sources: annual, with IMF projections.
    return Panel(f"{prefix}_unemployment", section, "Ledighed", "%",
                 "Arbejdsløshed pr. år (IMF). Månedlige tal findes ikke i de gratis kilder, vi bruger. "
                 "Indeværende og kommende år er prognoser.",
                 (S(f"{prefix}_unrate", "Ledighed", "imf_weo", f"LUR/{code}"),), group=CORE_GROUP)


def confidence_panel(section: str, prefix: str, code: str, consumer: bool = True,
                     business: bool = True, note: str = "") -> Panel:
    series = []
    if consumer:
        series.append(S(f"{prefix}_cci", "Forbrugertillid", "oecd", f"CLI/CCICP/{code}"))
    if business:
        series.append(S(f"{prefix}_bci", "Erhvervstillid", "oecd", f"CLI/BCICP/{code}"))
    return Panel(f"{prefix}_confidence", section, "Forbruger- og erhvervstillid", "Indeks",
                 "OECD's sammenlignelige tillidsindikatorer fra nationale spørgeundersøgelser. "
                 "100 = langsigtet gennemsnit." + (f" {note}" if note else ""),
                 tuple(series), group=CORE_GROUP, reference_lines=((100.0, "Gennemsnit"),))


def debt_panel(section: str, key: str, code: str) -> Panel:
    return Panel(key, section, "Statsgæld", "% af BNP",
                 "Offentlig bruttogæld (IMF). Indeværende og kommende år er prognoser.",
                 (S(key, "Offentlig gæld", "imf_weo", f"GGXWDG_NGDP/{code}"),), group=CORE_GROUP)


def current_account_panel(section: str, key: str, code: str) -> Panel:
    return Panel(key, section, "Betalingsbalance", "% af BNP",
                 "Overskud (+) eller underskud (−) på betalingsbalancens løbende poster (IMF). "
                 "Indeværende og kommende år er prognoser.",
                 (S(key, "Løbende poster", "imf_weo", f"BCA_NGDPD/{code}"),), group=CORE_GROUP)


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
          "De største centralbankers renter side om side. Hver rente vises også under sit land.",
          (R("us_ffr", "USA (Fed)"),
           R("ecb_dfr", "Eurozonen (ECB)"),
           R("uk_bank_rate", "UK (BoE)"),
           R("jp_policy", "Japan (BoJ)"),
           R("cn_lpr", "Kina (PBoC)"),
           R("dk_cd", "Danmark (NB)"))),
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

    # ------------------------------------------------------------- NORDAMERIKA
    # The overview only refers to series that the USA and Canada tabs own.
    Panel("na_policy", "north-america", "Styringsrenter", "%",
          "Fed's effektive rente og Bank of Canadas styringsrente.",
          (R("us_ffr", "USA (Fed)"), R("ca_policy", "Canada (BoC)"))),
    Panel("na_10y", "north-america", "10-årige statsrenter", "%",
          "USA dagligt, Canada som månedligt gennemsnit.",
          (R("us_10y", "USA"), R("ca_10y", "Canada"))),
    Panel("na_inflation", "north-america", "Inflation", "% år/år",
          "Forbrugerprisinflation (CPI). Begge centralbanker sigter efter 2 %.",
          (R("us_cpi", "USA"), R("ca_cpi", "Canada")),
          reference_lines=((2.0, "Fed- og BoC-mål 2 %"),)),
    Panel("na_unemployment", "north-america", "Ledighed", "%",
          "Arbejdsløshed, sæsonkorrigeret.",
          (R("us_unrate", "USA"), R("ca_unrate", "Canada"))),
    Panel("na_gdp", "north-america", "BNP-vækst (kvartal)", "% år/år",
          "Real BNP sammenlignet med samme kvartal året før.",
          (R("us_gdp_yoy", "USA"), R("ca_gdp_q", "Canada"))),

    # --------------------------------------------------------------------- USA
    Panel("us_fed", "us", "Styringsrente", "%",
          "Fed's målinterval (øvre/nedre) og den faktiske effektive dag-til-dag-rente.",
          (S("us_ffr", "Effektiv rente", "fred", "DFF"),
           S("us_ff_upper", "Mål (øvre)", "fred", "DFEDTARU"),
           S("us_ff_lower", "Mål (nedre)", "fred", "DFEDTARL")),
          group=CORE_GROUP),
    Panel("us_yields", "us", "Statsrenter", "%",
          "Renten på amerikanske statsobligationer (Treasuries): verdens vigtigste 'risikofri' rente.",
          (S("us_10y", "10 år", "fred", "DGS10"),
           S("us_3m", "3 mdr.", "fred", "DGS3MO"),
           S("us_2y", "2 år", "fred", "DGS2"),
           S("us_30y", "30 år", "fred", "DGS30")),
          group=CORE_GROUP),
    Panel("us_curve", "us", "Rentekurve", "%-point",
          "Forskel mellem lang og kort rente. Negativ (inverteret kurve) har historisk varslet recession.",
          (S("us_10y2y", "10 år − 2 år", "fred", "T10Y2Y"),
           S("us_10y3m", "10 år − 3 mdr.", "fred", "T10Y3M")),
          group=CORE_GROUP),
    Panel("us_inflation", "us", "Inflation", "% år/år",
          "Forbrugerpriser (CPI) og Fed's foretrukne mål: kerne-PCE. Fed sigter efter 2 %.",
          (S("us_cpi", "CPI", "fred", "CPIAUCSL", "yoy"),
           S("us_core_cpi", "Kerne-CPI", "fred", "CPILFESL", "yoy"),
           S("us_core_pce", "Kerne-PCE", "fred", "PCEPILFE", "yoy")),
          group=CORE_GROUP, reference_lines=INFLATION_TARGET_FED),
    Panel("us_unemployment", "us", "Ledighed", "%",
          "Arbejdsløshedsprocent. Halvdelen af Fed's dobbelte mandat.",
          (S("us_unrate", "Ledighed", "fred", "UNRATE"),),
          group=CORE_GROUP),
    Panel("us_gdp_q", "us", "BNP-vækst (kvartal)", "% år/år",
          "Real BNP sammenlignet med samme kvartal året før. USA's egen overskrift er den "
          "annualiserede vækst (se længere nede).",
          (S("us_gdp_yoy", "Real BNP", "fred", "GDPC1", "yoy"),),
          group=CORE_GROUP),
    imf_gdp_panel("us", "us_gdp_imf", "USA"),
    Panel("us_fx", "us", "Valuta", "Indeks",
          "Dollarens styrke mod handelspartnere (bredt dollarindeks; samme serie som under Global).",
          (R("usd_broad", "Bredt dollarindeks"),), change="pct", group=CORE_GROUP),
    confidence_panel("us", "us", "USA"),
    debt_panel("us", "us_debt", "USA"),
    current_account_panel("us", "us_ca", "USA"),
    Panel("us_payrolls", "us", "Nye job (nonfarm payrolls)", "1.000 job/md.",
          "Månedlig ændring i antal lønmodtagere uden for landbruget.",
          (S("us_nfp", "Ændring i job", "fred", "PAYEMS", "diff"),),
          group=extras_group("USA")),
    Panel("us_claims", "us", "Nye ledighedsansøgninger", "Antal/uge",
          "Ugentlige førstegangsansøgninger om dagpenge. Tidlig indikator for arbejdsmarkedet.",
          (S("us_icsa", "Ansøgninger", "fred", "ICSA"),), change="pct",
          group=extras_group("USA")),
    Panel("us_gdp", "us", "BNP-vækst (annualiseret k/k)", "% (annualiseret k/k)",
          "Real BNP-vækst i kvartalet, omregnet til årlig takt: det tal, USA selv offentliggør.",
          (S("us_gdp", "Real BNP", "fred", "A191RL1Q225SBEA"),),
          group=extras_group("USA")),
    Panel("us_credit", "us", "Kreditspreads", "%-point",
          "Merrente på virksomhedsobligationer over statsrenter. Stiger når markedet frygter konkurser.",
          (S("us_hy", "High yield", "fred", "BAMLH0A0HYM2"),
           S("us_ig", "Investment grade", "fred", "BAMLC0A0CM")),
          group=extras_group("USA")),
    Panel("us_breakeven", "us", "Inflationsforventning (10 år)", "%",
          "Markedets forventede gennemsnitlige inflation de næste 10 år (breakeven).",
          (S("us_be10", "10-årig breakeven", "fred", "T10YIE"),),
          group=extras_group("USA")),
    Panel("us_mortgage", "us", "30-årig boligrente", "%",
          "Gennemsnitlig rente på nye 30-årige fastforrentede boliglån.",
          (S("us_mort30", "30-årig fast", "fred", "MORTGAGE30US"),),
          group=extras_group("USA")),
    Panel("us_sentiment", "us", "Forbrugertillid (Michigan)", "Indeks",
          "University of Michigan Consumer Sentiment: den originale serie bag OECD's tal ovenfor.",
          (S("us_umcsent", "Forbrugertillid", "fred", "UMCSENT"),),
          group=extras_group("USA")),
    Panel("us_equities", "us", "S&P 500", "Indeks",
          "De 500 største amerikanske aktier.",
          (S("sp500", "S&P 500", "fred", "SP500"),), change="pct",
          group=extras_group("USA")),

    # ------------------------------------------------------------------ CANADA
    Panel("ca_policy", "canada", "Styringsrente", "%",
          "Bank of Canadas styringsrente, dag-til-dag-renten og den 3-måneders interbankrente "
          "(de to sidste som månedlige gennemsnit).",
          (S("ca_policy", "BoC-rente", "bis", "D.CA"),
           S("ca_overnight", "Dag-til-dag-rente", "fred", "IRSTCI01CAM156N"),
           S("ca_3m", "3-mdr. interbankrente", "fred", "IR3TIB01CAM156N")),
          group=CORE_GROUP),
    Panel("ca_yields", "canada", "Statsrenter", "%",
          "10-årig statsrente (månedligt gennemsnit). En 2-årig rente findes ikke i vores kilder.",
          (S("ca_10y", "10 år", "oecd", "FINMARK/IRLT/CAN"),),
          group=CORE_GROUP),
    Panel("ca_curve", "canada", "Rentekurve", "%-point",
          "10-årig statsrente minus 3-måneders interbankrente (månedlige gennemsnit). "
          "Negativ (inverteret kurve) har historisk varslet svag vækst.",
          (S("ca_10y3m", "10 år − 3 mdr.", "derived", ("ca_10y", "ca_3m"), "spread"),),
          group=CORE_GROUP),
    Panel("ca_inflation", "canada", "Inflation", "% år/år",
          "Forbrugerprisinflation (IMF). Kerneinflation findes ikke i de gratis kilder, vi bruger.",
          (S("ca_cpi", "CPI", "imf_cpi", "CAN"),),
          group=CORE_GROUP, reference_lines=((2.0, "BoC-mål 2 % (1–3 %)"),)),
    Panel("ca_unemployment", "canada", "Ledighed", "%",
          "Harmoniseret arbejdsløshed (OECD), sæsonkorrigeret.",
          (S("ca_unrate", "Ledighed", "fred", "LRHUTTTTCAM156S"),),
          group=CORE_GROUP),
    Panel("ca_gdp_q", "canada", "BNP-vækst (kvartal)", "% år/år",
          "Real BNP sammenlignet med samme kvartal året før.",
          (S("ca_gdp_q", "Real BNP", "fred", "NGDPRSAXDCCAQ", "yoy"),),
          group=CORE_GROUP),
    imf_gdp_panel("canada", "ca_gdp_imf", "CAN"),
    Panel("usdcad", "canada", "Valuta", "CAD pr. USD",
          "Canadiske dollar over for amerikanske dollar.",
          (S("usdcad", "USD/CAD", "fred", "DEXCAUS"),), change="pct", decimals=4,
          group=CORE_GROUP),
    confidence_panel("canada", "ca", "CAN"),
    debt_panel("canada", "ca_debt", "CAN"),
    current_account_panel("canada", "ca_ca", "CAN"),

    # ------------------------------------------------------------------ EUROPA
    # The euro area as a whole and the ECB. The countries have tabs of their own.
    Panel("ecb_rates", "europe", "ECB-renter", "%",
          "ECB styrer med indlånsrenten. €STR er den faktiske dag-til-dag-rente mellem banker, og "
          "3-mdr. Euribor (månedligt gennemsnit) er den rente, mange lån følger.",
          (S("ecb_dfr", "Indlånsrente", "ecb", "FM/D.U2.EUR.4F.KR.DFR.LEV"),
           S("ecb_mro", "Refinansieringsrente", "ecb", "FM/D.U2.EUR.4F.KR.MRR_FR.LEV"),
           S("estr", "€STR", "ecb", "EST/B.EU000A2X2A25.WT"),
           # FRED's copy of the OECD's German 3-month rate, which is Euribor.
           S("euribor_3m", "3-mdr. Euribor", "fred", "IR3TIB01DEM156N")),
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
    Panel("ea_inflation", "europe", "Inflation (HICP)", "% år/år",
          "Eurozonens harmoniserede forbrugerpriser. ECB sigter efter 2 %.",
          (S("ea_hicp", "HICP", "eurostat", "prc_hicp_minr?geo=EA&coicop18=TOTAL&unit=RCH_A"),
           S("ea_core", "Kerne (ekskl. energi og fødevarer)", "eurostat",
             "prc_hicp_minr?geo=EA&coicop18=TOT_X_NRG_FOOD&unit=RCH_A"),
           S("ea_services", "Serviceydelser", "eurostat", "prc_hicp_minr?geo=EA&coicop18=SERV&unit=RCH_A")),
          group="Inflation", reference_lines=INFLATION_TARGET_ECB),
    # Eurostat rather than ECB: the ECB's copy of this series lagged a quarter behind.
    Panel("ea_gdp", "europe", "BNP-vækst (eurozonen)", "% år/år",
          "Real BNP-vækst sammenlignet med samme kvartal året før.",
          (S("ea_gdp", "Real BNP", "eurostat", "namq_10_gdp?geo=EA&na_item=B1GQ&unit=CLV_PCH_SM&s_adj=SCA"),),
          group="Vækst og aktivitet"),
    Panel("ea_unemployment", "europe", "Ledighed (eurozonen)", "%",
          "Sæsonkorrigeret arbejdsløshed i eurozonen.",
          (S("ea_unrate", "Ledighed", "ecb", "LFSI/M.I9.S.UNEHRT.TOTAL0.15_74.T"),),
          group="Vækst og aktivitet"),
    # Eurostat's euro area code is EA21 since Bulgaria joined in 2026 (EA20 stops in 2025).
    # Year-over-year rates are only published for calendar-adjusted (CA) data.
    Panel("ea_sentiment", "europe", "Økonomisk stemning (ESI)", "Indeks",
          "EU-Kommissionens samlede stemningsindikator for erhverv og forbrugere. 100 = langsigtet gennemsnit.",
          (S("ea_esi", "ESI (eurozonen)", "eurostat", "ei_bssi_m_r2?geo=EA21&indic=BS-ESI-I&s_adj=SA"),),
          group="Vækst og aktivitet", reference_lines=((100.0, "Gennemsnit"),)),
    Panel("ea_industry", "europe", "Industriproduktion", "% år/år",
          "Produktion i industrien (ekskl. byggeri). Tyskland er eurozonens industrielle motor.",
          (S("ea_ip", "Eurozonen", "eurostat",
             "sts_inpr_m?geo=EA21&indic_bt=PRD&nace_r2=B-D&s_adj=CA&unit=PCH_SM"),
           R("de_ip", "Tyskland")),
          group="Vækst og aktivitet"),
    Panel("ea_retail", "europe", "Detailsalg (volumen)", "% år/år",
          "Detailhandlens salg målt i mængder. En direkte måling af forbrugernes efterspørgsel.",
          (S("ea_retail", "Eurozonen", "eurostat",
             "sts_trtu_m?geo=EA21&indic_bt=VOL_SLS&nace_r2=G47&s_adj=CA&unit=PCH_SM"),),
          group="Vækst og aktivitet"),
    Panel("ea_lending", "europe", "Udlånsrenter i eurozonen", "%",
          "Bankernes samlede lånerente for virksomheder og for boliglån til husholdninger.",
          (S("ea_lend_nfc", "Virksomheder", "ecb", "MIR/M.U2.B.A2I.AM.R.A.2240.EUR.N"),
           S("ea_lend_hh", "Boliglån", "ecb", "MIR/M.U2.B.A2C.AM.R.A.2250.EUR.N")),
          group="Kredit og penge"),
    Panel("ea_loan_growth", "europe", "Udlånsvækst", "% år/år",
          "Vækst i bankernes udlån. Viser mere direkte end M3, om de højere renter bider.",
          (S("ea_loans_nfc", "Virksomheder", "ecb", "BSI/M.U2.Y.U.A20T.A.I.U2.2240.Z01.A"),
           S("ea_loans_hh", "Husholdninger", "ecb", "BSI/M.U2.Y.U.A20T.A.I.U2.2250.Z01.A")),
          group="Kredit og penge"),
    Panel("ea_m3", "europe", "Pengemængde M3", "% år/år",
          "Vækst i pengemængden. Lav vækst kan signalere stram kreditgivning.",
          (S("ea_m3", "M3", "ecb", "BSI/M.U2.Y.V.M30.X.I.U2.2300.Z01.A"),),
          group="Kredit og penge"),
    Panel("ecb_balance", "europe", "ECB's balance", "mio. EUR",
          "Eurosystemets samlede aktiver (ugentligt). Faldende balance = QT (opstramning).",
          (S("ecb_assets", "Samlede aktiver", "fred", "ECBASSETSW"),), change="pct",
          group="Kredit og penge"),
    Panel("eu_credit", "europe", "Euro high yield-spread", "%-point",
          "Merrente på risikable europæiske virksomhedsobligationer.",
          (S("eu_hy", "Euro high yield", "fred", "BAMLHE00EHYIOAS"),),
          group="Kredit og penge"),
    Panel("eurusd", "europe", "EUR/USD", "USD pr. EUR",
          "Eurokursen over for dollar (ECB's referencekurs).",
          (S("eurusd", "EUR/USD", "ecb", "EXR/D.USD.EUR.SP00.A"),), change="pct", decimals=4,
          group="Valuta"),

    # The six countries side by side. Each series is owned by its country's tab.
    Panel("eu_country_inflation", "europe", "Inflation pr. land", "% år/år",
          "Harmoniserede forbrugerpriser (HICP); for UK det tilsvarende CPI. Linjen viser de 2 %, som "
          "centralbankerne sigter efter (Danmark via fastkursen til euroen).",
          (R("uk_cpi", "Storbritannien"), R("de_hicp", "Tyskland"), R("fr_hicp", "Frankrig"),
           R("dk_hicp", "Danmark"), R("no_hicp", "Norge"), R("se_hicp", "Sverige")),
          group="Lande", reference_lines=((2.0, "Mål 2 %"),)),
    Panel("eu_country_unemployment", "europe", "Ledighed pr. land", "%",
          "Harmoniseret arbejdsløshed, sæsonkorrigeret.",
          (R("uk_unrate", "Storbritannien"), R("de_unrate", "Tyskland"), R("fr_unrate", "Frankrig"),
           R("dk_unrate_lfs", "Danmark"), R("no_unrate", "Norge"), R("se_unrate", "Sverige")),
          group="Lande"),
    Panel("eu_country_gdp", "europe", "BNP-vækst pr. land", "% år/år",
          "Real BNP-vækst sammenlignet med samme kvartal året før.",
          (R("uk_gdp_q", "Storbritannien"), R("de_gdp", "Tyskland"), R("fr_gdp", "Frankrig"),
           R("dk_gdp_yoy", "Danmark"), R("no_gdp", "Norge"), R("se_gdp", "Sverige")),
          group="Lande"),
    Panel("eu_country_10y", "europe", "10-årige statsrenter pr. land", "%",
          "Månedlige gennemsnit.",
          (R("gb_10y", "Storbritannien"), R("de_10y", "Tyskland"), R("fr_10y", "Frankrig"),
           R("dk_10y", "Danmark"), R("no_10y", "Norge"), R("se_10y", "Sverige")),
          group="Lande"),
    Panel("eu_country_debt", "europe", "Statsgæld pr. land", "% af BNP",
          "Offentlig bruttogæld (IMF). Indeværende og kommende år er prognoser.",
          (R("uk_debt", "Storbritannien"), R("de_debt", "Tyskland"), R("fr_debt", "Frankrig"),
           R("dk_debt", "Danmark"), R("no_debt", "Norge"), R("se_debt", "Sverige")),
          group="Lande"),

    # ---------------------------------------------------------- STORBRITANNIEN
    Panel("uk_policy", "uk", "Styringsrente", "%",
          "Bank of Englands styringsrente og dag-til-dag-renten SONIA (månedligt gennemsnit).",
          (S("uk_bank_rate", "BoE-rente", "bis", "D.GB"),
           S("uk_sonia", "SONIA", "fred", "IRSTCI01GBM156N")),
          group=CORE_GROUP),
    Panel("uk_yields", "uk", "Statsrenter", "%",
          "10-årig statsrente (gilts, månedligt gennemsnit). En 2-årig rente findes ikke i vores kilder.",
          (S("gb_10y", "10 år", "oecd", "FINMARK/IRLT/GBR"),),
          group=CORE_GROUP),
    Panel("uk_curve", "uk", "Rentekurve", "%-point",
          "10-årig statsrente minus dag-til-dag-renten SONIA (månedlige gennemsnit). Den 3-måneders "
          "interbankrente, som de andre lande bruger, stoppede for UK i januar 2026.",
          (S("uk_10y_sonia", "10 år − SONIA", "derived", ("gb_10y", "uk_sonia"), "spread"),),
          group=CORE_GROUP),
    Panel("uk_inflation", "uk", "Inflation", "% år/år",
          "Forbrugerprisinflation (CPI, IMF) og kerneinflation (OECD). Bank of England sigter efter 2 %.",
          (S("uk_cpi", "CPI", "imf_cpi", "GBR"),
           S("uk_core", "Kerne (ekskl. energi og fødevarer)", "oecd", "PRICES/_TXCP01_NRG/GBR")),
          group=CORE_GROUP, reference_lines=((2.0, "BoE-mål 2 %"),)),
    Panel("uk_unemployment", "uk", "Ledighed", "%",
          "Harmoniseret arbejdsløshed (OECD), sæsonkorrigeret. De britiske tal kommer flere måneder forsinket.",
          (S("uk_unrate", "Ledighed", "fred", "LRHUTTTTGBM156S"),),
          group=CORE_GROUP),
    Panel("uk_gdp_q", "uk", "BNP-vækst (kvartal)", "% år/år",
          "Real BNP sammenlignet med samme kvartal året før.",
          (S("uk_gdp_q", "Real BNP", "fred", "NGDPRSAXDCGBQ", "yoy"),),
          group=CORE_GROUP),
    imf_gdp_panel("uk", "uk_gdp_imf", "GBR"),
    Panel("uk_fx", "uk", "Valuta", "Kurs",
          "Pundet over for dollar (USD pr. GBP) og euroen over for pundet (GBP pr. EUR), som markedet "
          "normalt noterer dem. Når pundet styrkes, stiger GBP/USD, og EUR/GBP falder.",
          (S("gbpusd", "GBP/USD", "fred", "DEXUSUK"),
           S("eurgbp", "EUR/GBP", "ecb", "EXR/D.GBP.EUR.SP00.A")), change="pct", decimals=4,
          group=CORE_GROUP),
    confidence_panel("uk", "uk", "GBR"),
    debt_panel("uk", "uk_debt", "GBR"),
    current_account_panel("uk", "uk_ca", "GBR"),

    # ---------------------------------------------------------------- TYSKLAND
    Panel("de_policy", "germany", "Styringsrente", "%",
          "Tyskland bruger euro, så ECB's indlånsrente er styringsrenten. €STR er den faktiske "
          "dag-til-dag-rente. Samme serier som under Europa.",
          (R("ecb_dfr", "ECB's indlånsrente"), R("estr", "€STR")),
          group=CORE_GROUP),
    Panel("de_yields", "germany", "Statsrenter", "%",
          "10-årig statsrente (Bund, månedligt gennemsnit): eurozonens benchmark. "
          "En 2-årig rente findes ikke i vores kilder.",
          (S("de_10y", "10 år", "oecd", "FINMARK/IRLT/DEU"),),
          group=CORE_GROUP),
    Panel("de_curve", "germany", "Rentekurve", "%-point",
          "10-årig statsrente minus 3-mdr. Euribor (månedlige gennemsnit). Negativ (inverteret kurve) "
          "har historisk varslet svag vækst.",
          (S("de_10y3m", "10 år − 3 mdr.", "derived", ("de_10y", "euribor_3m"), "spread"),),
          group=CORE_GROUP),
    Panel("de_inflation", "germany", "Inflation", "% år/år",
          "Harmoniserede forbrugerpriser (HICP) og kerneinflation. ECB sigter efter 2 % for eurozonen.",
          (S("de_hicp", "HICP", "eurostat", "prc_hicp_minr?geo=DE&coicop18=TOTAL&unit=RCH_A"),
           S("de_core", "Kerne (ekskl. energi og fødevarer)", "eurostat",
             "prc_hicp_minr?geo=DE&coicop18=TOT_X_NRG_FOOD&unit=RCH_A")),
          group=CORE_GROUP, reference_lines=INFLATION_TARGET_ECB),
    Panel("de_unemployment", "germany", "Ledighed", "%",
          "Harmoniseret arbejdsløshed (15–74 år), sæsonkorrigeret.",
          (S("de_unrate", "Ledighed", "eurostat", "une_rt_m?geo=DE&age=TOTAL&sex=T&s_adj=SA&unit=PC_ACT"),),
          group=CORE_GROUP),
    Panel("de_gdp_q", "germany", "BNP-vækst (kvartal)", "% år/år",
          "Real BNP sammenlignet med samme kvartal året før.",
          (S("de_gdp", "Real BNP", "eurostat", "namq_10_gdp?geo=DE&na_item=B1GQ&unit=CLV_PCH_SM&s_adj=SCA"),),
          group=CORE_GROUP),
    imf_gdp_panel("germany", "de_gdp_imf", "DEU"),
    Panel("de_fx", "germany", "Valuta", "USD pr. EUR",
          "Euroen over for dollar (ECB's referencekurs; samme serie som under Europa).",
          (R("eurusd", "EUR/USD"),), change="pct", decimals=4, group=CORE_GROUP),
    confidence_panel("germany", "de", "DEU"),
    debt_panel("germany", "de_debt", "DEU"),
    current_account_panel("germany", "de_ca", "DEU"),
    Panel("de_industry", "germany", "Industriproduktion", "% år/år",
          "Produktion i industrien (ekskl. byggeri). Tyskland er eurozonens industrielle motor.",
          (S("de_ip", "Industriproduktion", "eurostat",
             "sts_inpr_m?geo=DE&indic_bt=PRD&nace_r2=B-D&s_adj=CA&unit=PCH_SM"),),
          group=extras_group("Tyskland")),
    Panel("de_budget", "germany", "Budgetsaldo", "% af BNP",
          "Offentligt overskud (+) eller underskud (−). EU's grænse er −3 %. "
          "Indeværende og kommende år er IMF-prognoser.",
          (S("de_balance", "Offentlig saldo", "imf_weo", "GGXCNL_NGDP/DEU"),),
          group=extras_group("Tyskland"), reference_lines=((-3.0, "EU-grænse −3 %"),)),

    # ---------------------------------------------------------------- FRANKRIG
    Panel("fr_policy", "france", "Styringsrente", "%",
          "Frankrig bruger euro, så ECB's indlånsrente er styringsrenten. €STR er den faktiske "
          "dag-til-dag-rente. Samme serier som under Europa.",
          (R("ecb_dfr", "ECB's indlånsrente"), R("estr", "€STR")),
          group=CORE_GROUP),
    Panel("fr_yields", "france", "Statsrenter", "%",
          "10-årig statsrente (OAT, månedligt gennemsnit). En 2-årig rente findes ikke i vores kilder.",
          (S("fr_10y", "10 år", "oecd", "FINMARK/IRLT/FRA"),),
          group=CORE_GROUP),
    Panel("fr_curve", "france", "Rentekurve", "%-point",
          "10-årig statsrente minus 3-mdr. Euribor (månedlige gennemsnit). Negativ (inverteret kurve) "
          "har historisk varslet svag vækst.",
          (S("fr_10y3m", "10 år − 3 mdr.", "derived", ("fr_10y", "euribor_3m"), "spread"),),
          group=CORE_GROUP),
    Panel("fr_inflation", "france", "Inflation", "% år/år",
          "Harmoniserede forbrugerpriser (HICP) og kerneinflation. ECB sigter efter 2 % for eurozonen.",
          (S("fr_hicp", "HICP", "eurostat", "prc_hicp_minr?geo=FR&coicop18=TOTAL&unit=RCH_A"),
           S("fr_core", "Kerne (ekskl. energi og fødevarer)", "eurostat",
             "prc_hicp_minr?geo=FR&coicop18=TOT_X_NRG_FOOD&unit=RCH_A")),
          group=CORE_GROUP, reference_lines=INFLATION_TARGET_ECB),
    Panel("fr_unemployment", "france", "Ledighed", "%",
          "Harmoniseret arbejdsløshed (15–74 år), sæsonkorrigeret.",
          (S("fr_unrate", "Ledighed", "eurostat", "une_rt_m?geo=FR&age=TOTAL&sex=T&s_adj=SA&unit=PC_ACT"),),
          group=CORE_GROUP),
    Panel("fr_gdp_q", "france", "BNP-vækst (kvartal)", "% år/år",
          "Real BNP sammenlignet med samme kvartal året før.",
          (S("fr_gdp", "Real BNP", "eurostat", "namq_10_gdp?geo=FR&na_item=B1GQ&unit=CLV_PCH_SM&s_adj=SCA"),),
          group=CORE_GROUP),
    imf_gdp_panel("france", "fr_gdp_imf", "FRA"),
    Panel("fr_fx", "france", "Valuta", "USD pr. EUR",
          "Euroen over for dollar (ECB's referencekurs; samme serie som under Europa).",
          (R("eurusd", "EUR/USD"),), change="pct", decimals=4, group=CORE_GROUP),
    confidence_panel("france", "fr", "FRA"),
    debt_panel("france", "fr_debt", "FRA"),
    current_account_panel("france", "fr_ca", "FRA"),
    Panel("fr_oat_bund", "france", "OAT−Bund-spread", "%-point",
          "Merrente på franske over for tyske 10-årige statsobligationer. Måler markedets uro om fransk gæld.",
          (S("oat_bund", "Frankrig − Tyskland", "derived", ("fr_10y", "de_10y"), "spread"),),
          group=extras_group("Frankrig")),
    Panel("fr_budget", "france", "Budgetsaldo", "% af BNP",
          "Offentligt overskud (+) eller underskud (−). EU's grænse er −3 %. "
          "Indeværende og kommende år er IMF-prognoser.",
          (S("fr_balance", "Offentlig saldo", "imf_weo", "GGXCNL_NGDP/FRA"),),
          group=extras_group("Frankrig"), reference_lines=((-3.0, "EU-grænse −3 %"),)),

    # ----------------------------------------------------------------- DANMARK
    Panel("dk_rates", "denmark", "Styringsrente", "%",
          "Nationalbanken følger ECB for at holde fastkursen. DESTR er den danske dag-til-dag-rente, "
          "og den 3-måneders interbankrente er et månedligt gennemsnit.",
          (S("dk_cd", "Indskudsbevisrente", "statbank", "DNRENTD?INSTRUMENT=OIBNAA&LAND=DK&OPGOER=E"),
           S("dk_current", "Foliorente", "statbank", "DNRENTD?INSTRUMENT=OFONAA&LAND=DK&OPGOER=E"),
           S("dk_lending", "Udlånsrente", "statbank", "DNRENTD?INSTRUMENT=OIRNAA&LAND=DK&OPGOER=E"),
           S("destr", "DESTR", "statbank", "DNRENTD?INSTRUMENT=DESNAA&LAND=DK&OPGOER=E"),
           S("dk_3m", "3-mdr. interbankrente", "fred", "IR3TIB01DKM156N")),
          group=CORE_GROUP),
    Panel("dk_10y", "denmark", "Statsrenter", "%",
          "10-årig statsrente (månedligt gennemsnit). En 2-årig rente findes ikke i vores kilder "
          "(Statistikbankens serie stoppede i 2012).",
          (S("dk_10y", "10 år", "oecd", "FINMARK/IRLT/DNK"),),
          group=CORE_GROUP),
    Panel("dk_curve", "denmark", "Rentekurve", "%-point",
          "10-årig statsrente minus 3-måneders interbankrente (månedlige gennemsnit). "
          "Negativ (inverteret kurve) har historisk varslet svag vækst.",
          (S("dk_10y3m", "10 år − 3 mdr.", "derived", ("dk_10y", "dk_3m"), "spread"),),
          group=CORE_GROUP),
    Panel("dk_inflation", "denmark", "Inflation", "% år/år",
          "Det danske forbrugerprisindeks (KPI) og det harmoniserede indeks (HICP) med kerneinflation, "
          "som kan sammenlignes med andre EU-lande.",
          (S("dk_cpi", "Forbrugerprisindeks (KPI)", "statbank", "PRIS01?VAREGR=000000&ENHED=300"),
           S("dk_hicp", "HICP", "eurostat", "prc_hicp_minr?geo=DK&coicop18=TOTAL&unit=RCH_A"),
           S("dk_core", "Kerne-HICP (ekskl. energi og fødevarer)", "eurostat",
             "prc_hicp_minr?geo=DK&coicop18=TOT_X_NRG_FOOD&unit=RCH_A")),
          # Denmark has no target of its own; the fixed exchange rate imports the ECB's.
          group=CORE_GROUP, reference_lines=INFLATION_TARGET_ECB),
    Panel("dk_unemployment", "denmark", "Ledighed", "%",
          "Bruttoledighed (registreret, Danmarks Statistik) og harmoniseret ledighed (spørgeundersøgelse, "
          "Eurostat), som kan sammenlignes med andre lande. Begge sæsonkorrigeret.",
          (S("dk_unrate", "Bruttoledighed", "statbank", "AUS08?OMRÅDE=000&SAESONFAK=9"),
           S("dk_unrate_lfs", "Harmoniseret", "eurostat",
             "une_rt_m?geo=DK&age=TOTAL&sex=T&s_adj=SA&unit=PC_ACT")),
          group=CORE_GROUP),
    Panel("dk_gdp_q", "denmark", "BNP-vækst (kvartal)", "% år/år",
          "Real BNP sammenlignet med samme kvartal året før (Eurostat). Væksten i forhold til kvartalet før "
          "står længere nede.",
          (S("dk_gdp_yoy", "Real BNP", "eurostat",
             "namq_10_gdp?geo=DK&na_item=B1GQ&unit=CLV_PCH_SM&s_adj=SCA"),),
          group=CORE_GROUP),
    imf_gdp_panel("denmark", "dk_gdp_imf", "DNK"),
    Panel("dk_fx", "denmark", "Valuta", "DKK pr. valuta",
          "Kronen over for dollar og euro. Over for euroen ligger den fast (se fastkursen længere nede).",
          (S("usddkk", "USD/DKK", "fred", "DEXDNUS"),
           S("eurdkk", "EUR/DKK", "ecb", "EXR/D.DKK.EUR.SP00.A")), change="pct", decimals=4,
          group=CORE_GROUP),
    confidence_panel("denmark", "dk", "DNK"),
    debt_panel("denmark", "dk_debt", "DNK"),
    current_account_panel("denmark", "dk_ca", "DNK"),
    Panel("eurdkk", "denmark", "EUR/DKK (fastkurs)", "DKK pr. EUR",
          "Kronen er bundet til euroen omkring centralkursen 7,46038.",
          (R("eurdkk", "EUR/DKK"),), change="pct", decimals=4,
          group=extras_group("Danmark"), reference_lines=((7.46038, "Centralkurs 7,46038"),)),
    Panel("dk_ecb_spread", "denmark", "Rentespænd til ECB", "%-point",
          "Nationalbankens indskudsbevisrente minus ECB's indlånsrente. Bruges til at forsvare kronen.",
          (S("dk_ecb", "Danmark − ECB", "derived", ("dk_cd", "ecb_dfr"), "spread"),),
          group=extras_group("Danmark")),
    Panel("dk_de_spread", "denmark", "Rentespænd til Tyskland", "%-point",
          "Dansk minus tysk 10-årig statsrente (månedlige gennemsnit).",
          (S("dk_de_10y", "Danmark − Tyskland", "derived", ("dk_10y", "de_10y"), "spread"),),
          group=extras_group("Danmark")),
    Panel("dk_mortgage", "denmark", "Realkreditrente (nye lån)", "%",
          "Gennemsnitlig rente inkl. bidrag på nye realkreditlån til husholdninger.",
          (S("dk_mort", "Nye lån, husholdninger", "statbank",
             "DNRNURI?DATA=AL51EFFR&INDSEK=1400&VALUTA=Z01&LØBETID1=ALLE&RENTFIX=ALLE&LAANSTR=ALLE"),),
          group=extras_group("Danmark")),
    Panel("dk_housing", "denmark", "Huspriser", "% år/år",
          "Prisudvikling på ejendomssalg i hele landet.",
          (S("dk_house", "Enfamiliehuse", "statbank", "EJ56?OMRÅDE=000&EJENDOMSKATE=0111&TAL=310"),
           S("dk_flat", "Ejerlejligheder", "statbank", "EJ56?OMRÅDE=000&EJENDOMSKATE=2103&TAL=310")),
          group=extras_group("Danmark")),
    Panel("dk_gdp", "denmark", "BNP-vækst (k/k)", "% k/k",
          "Real, sæsonkorrigeret BNP-vækst i forhold til kvartalet før: det tal, Danmarks Statistik "
          "selv offentliggør.",
          (S("dk_gdp", "Real BNP", "statbank", "NKN1?TRANSAKT=B1GQK&PRISENHED=L_V&SÆSON=Y"),),
          group=extras_group("Danmark")),
    Panel("dk_ftillid", "denmark", "Forbrugertillid (Danmarks Statistik)", "Nettotal",
          "Forbrugernes forventninger til egen og landets økonomi. Over 0 = optimisme. "
          "Den originale serie bag OECD's tal ovenfor.",
          (S("dk_ftillid", "Forbrugertillid", "statbank", "FORV1?INDIKATOR=F1"),),
          group=extras_group("Danmark")),

    # ------------------------------------------------------------------- NORGE
    Panel("no_policy", "norway", "Styringsrente", "%",
          "Norges Banks styringsrente, dag-til-dag-renten og den 3-måneders interbankrente "
          "(de to sidste som månedlige gennemsnit).",
          (S("no_policy", "Norges Bank-rente", "bis", "D.NO"),
           S("no_overnight", "Dag-til-dag-rente", "fred", "IRSTCI01NOM156N"),
           S("no_3m", "3-mdr. interbankrente", "fred", "IR3TIB01NOM156N")),
          group=CORE_GROUP),
    Panel("no_yields", "norway", "Statsrenter", "%",
          "10-årig statsrente (månedligt gennemsnit). En 2-årig rente findes ikke i vores kilder.",
          (S("no_10y", "10 år", "oecd", "FINMARK/IRLT/NOR"),),
          group=CORE_GROUP),
    Panel("no_curve", "norway", "Rentekurve", "%-point",
          "10-årig statsrente minus 3-måneders interbankrente (månedlige gennemsnit). "
          "Negativ (inverteret kurve) har historisk varslet svag vækst.",
          (S("no_10y3m", "10 år − 3 mdr.", "derived", ("no_10y", "no_3m"), "spread"),),
          group=CORE_GROUP),
    Panel("no_inflation", "norway", "Inflation", "% år/år",
          "Harmoniserede forbrugerpriser (HICP) og kerneinflation (Eurostat). Norges Banks mål på 2 % "
          "gælder det nationale forbrugerprisindeks (KPI), der er beregnet lidt anderledes.",
          (S("no_hicp", "HICP", "eurostat", "prc_hicp_minr?geo=NO&coicop18=TOTAL&unit=RCH_A"),
           S("no_core", "Kerne (ekskl. energi og fødevarer)", "eurostat",
             "prc_hicp_minr?geo=NO&coicop18=TOT_X_NRG_FOOD&unit=RCH_A")),
          group=CORE_GROUP, reference_lines=((2.0, "Norges Banks mål 2 %"),)),
    Panel("no_unemployment", "norway", "Ledighed", "%",
          "Harmoniseret arbejdsløshed (15–74 år), sæsonkorrigeret.",
          (S("no_unrate", "Ledighed", "eurostat", "une_rt_m?geo=NO&age=TOTAL&sex=T&s_adj=SA&unit=PC_ACT"),),
          group=CORE_GROUP),
    Panel("no_gdp_q", "norway", "BNP-vækst (kvartal)", "% år/år",
          "Real BNP for hele økonomien (inkl. olie og gas) sammenlignet med samme kvartal året før.",
          (S("no_gdp", "Real BNP", "eurostat", "namq_10_gdp?geo=NO&na_item=B1GQ&unit=CLV_PCH_SM&s_adj=SCA"),),
          group=CORE_GROUP),
    imf_gdp_panel("norway", "no_gdp_imf", "NOR"),
    Panel("no_fx", "norway", "Valuta", "NOK pr. valuta",
          "Norske kroner over for dollar og euro.",
          (S("usdnok", "USD/NOK", "fred", "DEXNOUS"),
           S("eurnok", "EUR/NOK", "ecb", "EXR/D.NOK.EUR.SP00.A")), change="pct", decimals=4,
          group=CORE_GROUP),
    confidence_panel("norway", "no", "NOR", consumer=False,
                     note="Forbrugertillid for Norge findes ikke hos OECD."),
    debt_panel("norway", "no_debt", "NOR"),
    current_account_panel("norway", "no_ca", "NOR"),
    Panel("no_oil", "norway", "Oliepris (Brent)", "USD/tønde",
          "Norges økonomi og krone afhænger af olie og gas. Samme serie som under Global.",
          (R("brent", "Brent"),), change="pct",
          group=extras_group("Norge")),

    # ------------------------------------------------------------------ SVERIGE
    Panel("se_policy", "sweden", "Styringsrente", "%",
          "Riksbankens styringsrente og den 3-måneders interbankrente (månedligt gennemsnit). "
          "En dag-til-dag-rente findes ikke i vores kilder (OECD-serien stoppede i 2020).",
          (S("se_policy", "Riksbank-rente", "bis", "D.SE"),
           S("se_3m", "3-mdr. interbankrente", "fred", "IR3TIB01SEM156N")),
          group=CORE_GROUP),
    Panel("se_yields", "sweden", "Statsrenter", "%",
          "10-årig statsrente (månedligt gennemsnit). En 2-årig rente findes ikke i vores kilder.",
          (S("se_10y", "10 år", "oecd", "FINMARK/IRLT/SWE"),),
          group=CORE_GROUP),
    Panel("se_curve", "sweden", "Rentekurve", "%-point",
          "10-årig statsrente minus 3-måneders interbankrente (månedlige gennemsnit). "
          "Negativ (inverteret kurve) har historisk varslet svag vækst.",
          (S("se_10y3m", "10 år − 3 mdr.", "derived", ("se_10y", "se_3m"), "spread"),),
          group=CORE_GROUP),
    Panel("se_inflation", "sweden", "Inflation", "% år/år",
          "Harmoniserede forbrugerpriser (HICP) og kerneinflation (Eurostat). Riksbankens mål på 2 % "
          "gælder KPIF (forbrugerpriser med fast rente), der er beregnet lidt anderledes.",
          (S("se_hicp", "HICP", "eurostat", "prc_hicp_minr?geo=SE&coicop18=TOTAL&unit=RCH_A"),
           S("se_core", "Kerne (ekskl. energi og fødevarer)", "eurostat",
             "prc_hicp_minr?geo=SE&coicop18=TOT_X_NRG_FOOD&unit=RCH_A")),
          group=CORE_GROUP, reference_lines=((2.0, "Riksbankens mål 2 %"),)),
    Panel("se_unemployment", "sweden", "Ledighed", "%",
          "Harmoniseret arbejdsløshed (15–74 år), sæsonkorrigeret.",
          (S("se_unrate", "Ledighed", "eurostat", "une_rt_m?geo=SE&age=TOTAL&sex=T&s_adj=SA&unit=PC_ACT"),),
          group=CORE_GROUP),
    Panel("se_gdp_q", "sweden", "BNP-vækst (kvartal)", "% år/år",
          "Real BNP sammenlignet med samme kvartal året før.",
          (S("se_gdp", "Real BNP", "eurostat", "namq_10_gdp?geo=SE&na_item=B1GQ&unit=CLV_PCH_SM&s_adj=SCA"),),
          group=CORE_GROUP),
    imf_gdp_panel("sweden", "se_gdp_imf", "SWE"),
    Panel("se_fx", "sweden", "Valuta", "SEK pr. valuta",
          "Svenske kroner over for dollar og euro.",
          (S("usdsek", "USD/SEK", "fred", "DEXSDUS"),
           S("eursek", "EUR/SEK", "ecb", "EXR/D.SEK.EUR.SP00.A")), change="pct", decimals=4,
          group=CORE_GROUP),
    confidence_panel("sweden", "se", "SWE"),
    debt_panel("sweden", "se_debt", "SWE"),
    current_account_panel("sweden", "se_ca", "SWE"),

    # ------------------------------------------------------------------- ASIEN
    # The eight countries side by side. Each series is owned by its country's tab.
    Panel("asia_policy", "asia", "Styringsrenter", "%",
          "Centralbankernes styringsrenter. Vietnams findes ikke i vores kilder.",
          (R("cn_lpr", "Kina"), R("jp_policy", "Japan"), R("kr_policy", "Sydkorea"),
           R("th_policy", "Thailand"), R("id_policy", "Indonesien"), R("my_policy", "Malaysia"),
           R("in_policy", "Indien"))),
    Panel("asia_inflation", "asia", "Inflation", "% år/år",
          "Forbrugerprisinflation (IMF).",
          (R("cn_cpi", "Kina"), R("jp_cpi", "Japan"), R("kr_cpi", "Sydkorea"), R("th_cpi", "Thailand"),
           R("vn_cpi", "Vietnam"), R("id_cpi", "Indonesien"), R("my_cpi", "Malaysia"), R("in_cpi", "Indien"))),
    Panel("asia_gdp", "asia", "BNP-vækst inkl. IMF-prognose", "% år/år",
          "Real BNP-vækst pr. år. Indeværende og kommende år er IMF-prognoser.",
          (R("cn_gdp", "Kina"), R("jp_gdp", "Japan"), R("kr_gdp", "Sydkorea"), R("th_gdp", "Thailand"),
           R("vn_gdp", "Vietnam"), R("id_gdp", "Indonesien"), R("my_gdp", "Malaysia"), R("in_gdp", "Indien"))),
    Panel("asia_debt", "asia", "Statsgæld", "% af BNP",
          "Offentlig bruttogæld (IMF). Indeværende og kommende år er prognoser.",
          (R("cn_debt", "Kina"), R("jp_debt", "Japan"), R("kr_debt", "Sydkorea"), R("th_debt", "Thailand"),
           R("vn_debt", "Vietnam"), R("id_debt", "Indonesien"), R("my_debt", "Malaysia"), R("in_debt", "Indien"))),

    # -------------------------------------------------------------------- KINA
    Panel("cn_lpr", "china", "Styringsrente", "%",
          "Kinas 1-årige Loan Prime Rate (benchmark for bankernes udlån og reelt styringsrenten siden "
          "2019) og den 3-måneders interbankrente (månedligt gennemsnit).",
          (S("cn_lpr", "LPR 1 år", "bis", "D.CN"),
           S("cn_3m", "3-mdr. interbankrente", "fred", "IR3TIB01CNM156N")),
          group=CORE_GROUP),
    Panel("cn_10y", "china", "Statsrenter", "%",
          "Kinesisk 10-årig statsrente (månedligt gennemsnit, fra 2014) sammenlignet med den amerikanske.",
          (S("cn_10y", "Kina, 10 år", "oecd", "FINMARK/IRLT/CHN"),
           S("us_10y_m", "USA, 10 år", "fred", "GS10")),
          group=CORE_GROUP),
    Panel("cn_curve", "china", "Rentekurve", "%-point",
          "10-årig statsrente minus 3-måneders interbankrente (månedlige gennemsnit).",
          (S("cn_10y3m", "10 år − 3 mdr.", "derived", ("cn_10y", "cn_3m"), "spread"),),
          group=CORE_GROUP),
    Panel("cn_inflation", "china", "Inflation", "% år/år",
          "Forbrugerprisinflation (IMF). Lav eller negativ inflation har været et tegn på svag efterspørgsel. "
          "Ingen mållinje: regeringen sætter et nyt mål hvert år (2026: ca. 2 %), så en fast linje ville "
          "være misvisende. Kerneinflation findes ikke i de gratis kilder, vi bruger.",
          (S("cn_cpi", "CPI", "imf_cpi", "CHN"),),
          group=CORE_GROUP),
    imf_unemployment_panel("china", "cn", "CHN"),
    Panel("cn_gdp_q", "china", "BNP-vækst (kvartal)", "% år/år",
          "Real BNP sammenlignet med samme kvartal året før (OECD).",
          (S("cn_gdp_q", "Real BNP", "oecd", "QNA/GY/CHN"),),
          group=CORE_GROUP),
    imf_gdp_panel("china", "cn_gdp", "CHN"),
    Panel("usdcny", "china", "Valuta", "CNY pr. USD",
          "Yuan over for dollar. Styres delvist af centralbanken.",
          (S("usdcny", "USD/CNY", "fred", "DEXCHUS"),), change="pct", decimals=4,
          group=CORE_GROUP),
    confidence_panel("china", "cn", "CHN"),
    debt_panel("china", "cn_debt", "CHN"),
    current_account_panel("china", "cn_ca", "CHN"),

    # ------------------------------------------------------------------- JAPAN
    Panel("jp_policy", "japan", "Styringsrente", "%",
          "Bank of Japans styringsrente og den 3-måneders interbankrente (månedligt gennemsnit).",
          (S("jp_policy", "BoJ-rente", "bis", "D.JP"),
           S("jp_3m", "3-mdr. interbankrente", "fred", "IR3TIB01JPM156N")),
          group=CORE_GROUP),
    Panel("jp_jgb", "japan", "Statsrenter", "%",
          "Japanske statsrenter (JGB) fra finansministeriets daglige rentekurve.",
          (S("jgb_10y", "10 år", "mof", "10Y"),
           S("jgb_2y", "2 år", "mof", "2Y"),
           S("jgb_5y", "5 år", "mof", "5Y"),
           S("jgb_30y", "30 år", "mof", "30Y")),
          group=CORE_GROUP),
    Panel("jp_curve", "japan", "Rentekurve", "%-point",
          "10-årig minus 2-årig statsrente. Stigende spread: markedet venter højere renter på lang sigt.",
          (S("jgb_10y2y", "10 år − 2 år", "derived", ("jgb_10y", "jgb_2y"), "spread"),),
          group=CORE_GROUP),
    Panel("jp_inflation", "japan", "Inflation", "% år/år",
          "Forbrugerprisinflation (IMF). Kerneinflation findes ikke i de gratis kilder, vi bruger.",
          (S("jp_cpi", "CPI", "imf_cpi", "JPN"),),
          group=CORE_GROUP, reference_lines=((2.0, "BoJ-mål 2 %"),)),
    Panel("jp_unemployment", "japan", "Ledighed", "%",
          "Harmoniseret arbejdsløshed (OECD), sæsonkorrigeret.",
          (S("jp_unrate", "Ledighed", "fred", "LRHUTTTTJPM156S"),),
          group=CORE_GROUP),
    Panel("jp_gdp_q", "japan", "BNP-vækst (kvartal)", "% år/år",
          "Real BNP sammenlignet med samme kvartal året før.",
          (S("jp_gdp_q", "Real BNP", "fred", "NGDPRSAXDCJPQ", "yoy"),),
          group=CORE_GROUP),
    imf_gdp_panel("japan", "jp_gdp", "JPN"),
    Panel("usdjpy", "japan", "Valuta", "JPY pr. USD",
          "Yenen over for dollar. Påvirkes stærkt af renteforskellen mellem USA og Japan.",
          (S("usdjpy", "USD/JPY", "fred", "DEXJPUS"),), change="pct",
          group=CORE_GROUP),
    confidence_panel("japan", "jp", "JPN"),
    debt_panel("japan", "jp_debt", "JPN"),
    current_account_panel("japan", "jp_ca", "JPN"),
    Panel("jp_exports", "japan", "Eksport", "% år/år",
          "Vareeksportens værdi i yen sammenlignet med samme måned året før (OECD).",
          (S("jp_exports", "Vareeksport", "fred", "XTEXVA01JPM664S", "yoy"),),
          group=extras_group("Japan")),
    Panel("nikkei", "japan", "Nikkei 225", "Indeks",
          "Japans førende aktieindeks (prisindeks).",
          (S("nikkei", "Nikkei 225", "fred", "NIKKEI225"),), change="pct",
          group=extras_group("Japan")),

    # ---------------------------------------------------------------- SYDKOREA
    Panel("kr_policy", "korea", "Styringsrente", "%",
          "Bank of Koreas styringsrente og den 3-måneders interbankrente (månedligt gennemsnit).",
          (S("kr_policy", "BoK-rente", "bis", "D.KR"),
           S("kr_3m", "3-mdr. interbankrente", "fred", "IR3TIB01KRM156N")),
          group=CORE_GROUP),
    Panel("kr_10y", "korea", "Statsrenter", "%",
          "10-årig statsrente (månedligt gennemsnit). En 2-årig rente findes ikke i vores kilder.",
          (S("kr_10y", "10 år", "oecd", "FINMARK/IRLT/KOR"),),
          group=CORE_GROUP),
    Panel("kr_curve", "korea", "Rentekurve", "%-point",
          "10-årig statsrente minus 3-måneders interbankrente (månedlige gennemsnit). "
          "Negativ (inverteret kurve) har historisk varslet svag vækst.",
          (S("kr_10y3m", "10 år − 3 mdr.", "derived", ("kr_10y", "kr_3m"), "spread"),),
          group=CORE_GROUP),
    Panel("kr_inflation", "korea", "Inflation", "% år/år",
          "Forbrugerprisinflation (IMF) og kerneinflation (OECD).",
          (S("kr_cpi", "CPI", "imf_cpi", "KOR"),
           S("kr_core", "Kerne (ekskl. energi og fødevarer)", "oecd", "PRICES/_TXCP01_NRG/KOR")),
          group=CORE_GROUP, reference_lines=((2.0, "BoK-mål 2 %"),)),
    Panel("kr_unemployment", "korea", "Ledighed", "%",
          "Harmoniseret arbejdsløshed (OECD), sæsonkorrigeret.",
          (S("kr_unrate", "Ledighed", "fred", "LRHUTTTTKRM156S"),),
          group=CORE_GROUP),
    Panel("kr_gdp_q", "korea", "BNP-vækst (kvartal)", "% år/år",
          "Real BNP sammenlignet med samme kvartal året før.",
          (S("kr_gdp_q", "Real BNP", "fred", "NGDPRSAXDCKRQ", "yoy"),),
          group=CORE_GROUP),
    imf_gdp_panel("korea", "kr_gdp", "KOR"),
    Panel("usdkrw", "korea", "Valuta", "KRW pr. USD",
          "Won over for dollar.",
          (S("usdkrw", "USD/KRW", "fred", "DEXKOUS"),), change="pct",
          group=CORE_GROUP),
    confidence_panel("korea", "kr", "KOR"),
    debt_panel("korea", "kr_debt", "KOR"),
    current_account_panel("korea", "kr_ca", "KOR"),
    Panel("kr_exports", "korea", "Eksport", "% år/år",
          "Vareeksportens værdi i won sammenlignet med samme måned året før (OECD). "
          "Koreas eksport af chips og elektronik følges som en tidlig indikator for den globale cyklus.",
          (S("kr_exports", "Vareeksport", "fred", "XTEXVA01KRM664S", "yoy"),),
          group=extras_group("Sydkorea")),
    Panel("kr_household_debt", "korea", "Husholdningsgæld", "% af BNP",
          "Husholdningernes samlede gæld (BIS, kvartalsvis). Nr. 9 af 48 lande i BIS' data (1. kvt. 2026).",
          (S("kr_hh_debt", "Husholdninger", "bis", "WS_TC/Q.KR.H.A.M.770.A"),),
          group=extras_group("Sydkorea")),
    Panel("kr_us_spread", "korea", "Rentespænd til USA", "%-point",
          "Koreansk minus amerikansk 10-årig statsrente (månedlige gennemsnit). Spændet påvirker "
          "kapitalstrømmene og dermed wonen.",
          (S("kr_us_10y", "Sydkorea − USA", "derived", ("kr_10y", "us_10y_m"), "spread"),),
          group=extras_group("Sydkorea")),

    # ---------------------------------------------------------------- THAILAND
    # No yields, quarterly GDP or confidence: see "Mangler en gratis kilde" in CLAUDE.md.
    Panel("th_policy", "thailand", "Styringsrente", "%",
          "Bank of Thailands styringsrente.",
          (S("th_policy", "BoT-rente", "bis", "D.TH"),),
          group=CORE_GROUP),
    Panel("th_inflation", "thailand", "Inflation", "% år/år",
          "Forbrugerprisinflation (IMF). Bank of Thailand sigter efter 1–3 %.",
          (S("th_cpi", "CPI", "imf_cpi", "THA"),),
          group=CORE_GROUP, reference_lines=((1.0, "BoT-bånd 1 %"), (3.0, "BoT-bånd 3 %"))),
    imf_unemployment_panel("thailand", "th", "THA"),
    imf_gdp_panel("thailand", "th_gdp", "THA"),
    Panel("usdthb", "thailand", "Valuta", "THB pr. USD",
          "Baht over for dollar.",
          (S("usdthb", "USD/THB", "fred", "DEXTHUS"),), change="pct",
          group=CORE_GROUP),
    debt_panel("thailand", "th_debt", "THA"),
    current_account_panel("thailand", "th_ca", "THA"),

    # ----------------------------------------------------------------- VIETNAM
    # No policy rate, yields, quarterly GDP or confidence in our sources.
    Panel("vn_inflation", "vietnam", "Inflation", "% år/år",
          "Forbrugerprisinflation (IMF). Ingen mållinje: Nationalforsamlingen sætter et nyt loft hvert år "
          "(2026: 4,5 %), så en fast linje ville være misvisende.",
          (S("vn_cpi", "CPI", "imf_cpi", "VNM"),),
          group=CORE_GROUP),
    imf_unemployment_panel("vietnam", "vn", "VNM"),
    imf_gdp_panel("vietnam", "vn_gdp", "VNM"),
    Panel("usdvnd", "vietnam", "Valuta", "VND pr. USD",
          "Dong over for dollar (månedligt gennemsnit, BIS). Dagskurser findes ikke i vores kilder.",
          (S("usdvnd", "USD/VND", "bis", "WS_XRU/M.VN.VND.A"),), change="pct",
          group=CORE_GROUP),
    debt_panel("vietnam", "vn_debt", "VNM"),
    current_account_panel("vietnam", "vn_ca", "VNM"),

    # -------------------------------------------------------------- INDONESIEN
    Panel("id_policy", "indonesia", "Styringsrente", "%",
          "Bank Indonesias styringsrente og dag-til-dag-renten (månedligt gennemsnit).",
          (S("id_policy", "BI-rente", "bis", "D.ID"),
           S("id_overnight", "Dag-til-dag-rente", "fred", "IRSTCI01IDM156N")),
          group=CORE_GROUP),
    Panel("id_inflation", "indonesia", "Inflation", "% år/år",
          "Forbrugerprisinflation (IMF). Bank Indonesia sigter efter 2,5 % ± 1 procentpoint.",
          (S("id_cpi", "CPI", "imf_cpi", "IDN"),),
          group=CORE_GROUP, reference_lines=((2.5, "BI-mål 2,5 % (±1)"),)),
    imf_unemployment_panel("indonesia", "id", "IDN"),
    Panel("id_gdp_q", "indonesia", "BNP-vækst (kvartal)", "% år/år",
          "Real BNP sammenlignet med samme kvartal året før.",
          (S("id_gdp_q", "Real BNP", "fred", "NGDPRSAXDCIDQ", "yoy"),),
          group=CORE_GROUP),
    imf_gdp_panel("indonesia", "id_gdp", "IDN"),
    Panel("usdidr", "indonesia", "Valuta", "IDR pr. USD",
          "Rupiah over for dollar (dagligt gennemsnit, BIS).",
          (S("usdidr", "USD/IDR", "bis", "WS_XRU/D.ID.IDR.A"),), change="pct",
          group=CORE_GROUP),
    confidence_panel("indonesia", "id", "IDN"),
    debt_panel("indonesia", "id_debt", "IDN"),
    current_account_panel("indonesia", "id_ca", "IDN"),

    # ---------------------------------------------------------------- MALAYSIA
    Panel("my_policy", "malaysia", "Styringsrente", "%",
          "Bank Negara Malaysias styringsrente (Overnight Policy Rate).",
          (S("my_policy", "BNM-rente (OPR)", "bis", "D.MY"),),
          group=CORE_GROUP),
    Panel("my_inflation", "malaysia", "Inflation", "% år/år",
          "Forbrugerprisinflation (IMF). Bank Negara Malaysia har ikke et talfæstet inflationsmål.",
          (S("my_cpi", "CPI", "imf_cpi", "MYS"),),
          group=CORE_GROUP),
    imf_unemployment_panel("malaysia", "my", "MYS"),
    # IMF's quarterly accounts: for Malaysia they match IMF's annual growth (checked
    # 2026-10-08); for Thailand and China they did not, so those are left out.
    Panel("my_gdp_q", "malaysia", "BNP-vækst (kvartal)", "% år/år",
          "Real BNP sammenlignet med samme kvartal året før (IMF's kvartalsvise nationalregnskab).",
          (S("my_gdp_q", "Real BNP", "imf_qnea", "MYS", "yoy"),),
          group=CORE_GROUP),
    imf_gdp_panel("malaysia", "my_gdp", "MYS"),
    Panel("usdmyr", "malaysia", "Valuta", "MYR pr. USD",
          "Ringgit over for dollar.",
          (S("usdmyr", "USD/MYR", "fred", "DEXMAUS"),), change="pct", decimals=4,
          group=CORE_GROUP),
    debt_panel("malaysia", "my_debt", "MYS"),
    current_account_panel("malaysia", "my_ca", "MYS"),

    # ------------------------------------------------------------------ INDIEN
    Panel("in_policy", "india", "Styringsrente", "%",
          "Reserve Bank of Indias styringsrente (repo), dag-til-dag-renten og den 3-måneders "
          "interbankrente (de to sidste som månedlige gennemsnit).",
          (S("in_policy", "RBI-rente", "bis", "D.IN"),
           S("in_overnight", "Dag-til-dag-rente", "fred", "IRSTCI01INM156N"),
           S("in_3m", "3-mdr. interbankrente", "oecd", "FINMARK/IR3TIB/IND")),
          group=CORE_GROUP),
    Panel("in_10y", "india", "Statsrenter", "%",
          "10-årig statsrente (månedligt gennemsnit, fra 2011). En 2-årig rente findes ikke i vores kilder.",
          (S("in_10y", "10 år", "oecd", "FINMARK/IRLT/IND"),),
          group=CORE_GROUP),
    Panel("in_curve", "india", "Rentekurve", "%-point",
          "10-årig statsrente minus 3-måneders interbankrente (månedlige gennemsnit).",
          (S("in_10y3m", "10 år − 3 mdr.", "derived", ("in_10y", "in_3m"), "spread"),),
          group=CORE_GROUP),
    Panel("in_inflation", "india", "Inflation", "% år/år",
          "Forbrugerprisinflation (IMF). Reserve Bank of India sigter efter 4 % med et tolerancebånd på 2–6 %.",
          (S("in_cpi", "CPI", "imf_cpi", "IND"),),
          group=CORE_GROUP, reference_lines=((4.0, "RBI-mål 4 % (2–6 %)"),)),
    imf_unemployment_panel("india", "in", "IND"),
    Panel("in_gdp_q", "india", "BNP-vækst (kvartal)", "% år/år",
          "Real BNP sammenlignet med samme kvartal året før (OECD).",
          (S("in_gdp_q", "Real BNP", "oecd", "QNA/GY/IND"),),
          group=CORE_GROUP),
    imf_gdp_panel("india", "in_gdp", "IND"),
    Panel("usdinr", "india", "Valuta", "INR pr. USD",
          "Rupee over for dollar.",
          (S("usdinr", "USD/INR", "fred", "DEXINUS"),), change="pct",
          group=CORE_GROUP),
    confidence_panel("india", "in", "IND"),
    debt_panel("india", "in_debt", "IND"),
    current_account_panel("india", "in_ca", "IND"),
]
