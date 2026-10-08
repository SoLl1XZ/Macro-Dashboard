"use strict";

// Pure helpers without the DOM: the URL state and the search matching. The page loads this
// file before app.js; Node loads it for the tests in tests/js (see the export at the end).

// ------------------------------------------------------------------------ URL state
// The URL is the single source of truth for what is shown, e.g.
// "#japan?range=7&panel=jp_jgb&full=1&from=2007-01&to=2012-12". So a copied link, a
// reload or the back button restores exactly the same view.

const DEFAULT_RANGE_YEARS = 5; // short enough that 2020's outliers don't flatten every chart
const MAX_RANGE_YEARS = 100;
const PRESET_RANGES = [1, 5, 10, 0]; // the buttons; 0 = all data ("Maks")

// 0 means all data; otherwise a whole number of years from 1 to 100.
function isValidRange(years) {
  return Number.isInteger(years) && (years === 0 || (years >= 1 && years <= MAX_RANGE_YEARS));
}

function parseRange(text) {
  if (text === null || !/^\d{1,3}$/.test(text)) return DEFAULT_RANGE_YEARS;
  const years = Number(text);
  return isValidRange(years) ? years : DEFAULT_RANGE_YEARS;
}

// "2007-01" (a month), or null for anything else.
function parseMonth(text) {
  return typeof text === "string" && /^\d{4}-(0[1-9]|1[0-2])$/.test(text) ? text : null;
}

// "denmark,sweden,,denmark" -> ["denmark", "sweden"]
function parseList(text) {
  if (!text) return [];
  return [...new Set(text.split(",").map(item => item.trim()).filter(Boolean))];
}

// Everything the URL can say. `params` keeps the rest for the Compare tab (c, p, a, b, index).
function parseHashState(hash, tabIds, fallbackTabId) {
  const [tabPart, query = ""] = hash.replace(/^#/, "").split("?");
  const params = new URLSearchParams(query);
  let from = parseMonth(params.get("from"));
  let to = parseMonth(params.get("to"));
  if (from && to && from > to) [from, to] = [null, null];
  const state = {
    sectionId: tabIds.includes(tabPart) ? tabPart : fallbackTabId,
    rangeYears: params.has("range") ? parseRange(params.get("range")) : DEFAULT_RANGE_YEARS,
    panel: params.get("panel") || null,
    full: params.get("full") === "1",
    from,
    to,
    params,
  };
  for (const key of ["range", "panel", "full", "from", "to"]) params.delete(key);
  return state;
}

// The hash for a tab. Empty values are left out, true becomes 1, lists keep their commas
// readable ("c=denmark,sweden"), and the default period is left out to keep links short.
function buildHash(sectionId, rangeYears, extra = {}) {
  const parts = [];
  if (rangeYears !== DEFAULT_RANGE_YEARS) parts.push(`range=${rangeYears}`);
  for (const [key, value] of Object.entries(extra)) {
    if (value === null || value === undefined || value === false || value === "") continue;
    const text = value === true ? "1" : Array.isArray(value) ? value.join(",") : String(value);
    parts.push(`${key}=${encodeURIComponent(text).replaceAll("%2C", ",")}`);
  }
  return `#${sectionId}${parts.length ? `?${parts.join("&")}` : ""}`;
}

// ---------------------------------------------------------------------- Compare tab

const MAX_COMPARE_COUNTRIES = 8; // more lines than this can't be told apart
const CORE_GROUP = "Kernetal"; // the group of a country's core panels (CORE_GROUP in indicators.py)

// The core panels a comparison can show, with stable slugs for the URL. The titles must
// match CORE_TITLES in indicators.py (a Python test checks this).
const COMPARE_PARAMETERS = [
  { slug: "styringsrente", title: "Styringsrente" },
  { slug: "statsrenter", title: "Statsrenter" },
  { slug: "rentekurve", title: "Rentekurve" },
  { slug: "inflation", title: "Inflation" },
  { slug: "ledighed", title: "Ledighed" },
  { slug: "bnp-kvartal", title: "BNP-vækst (kvartal)" },
  { slug: "bnp-imf", title: "BNP-vækst inkl. IMF-prognose" },
  { slug: "valuta", title: "Valuta" },
  { slug: "tillid", title: "Forbruger- og erhvervstillid" },
  { slug: "statsgaeld", title: "Statsgæld" },
  { slug: "betalingsbalance", title: "Betalingsbalance" },
];

const DEFAULT_COMPARE = {
  countries: ["denmark", "sweden", "norway", "germany"],
  parameters: ["styringsrente", "inflation", "ledighed", "bnp-kvartal"],
};

// The countries and parameters chosen on the Compare tab. A missing c= or p= means the
// default choice; an empty one (c=) means the user cleared it. a= or b= is the old
// comparison of two series, kept as the "advanced" mode so old links still work.
function parseCompareSelection(params, countryIds) {
  const knownCountries = new Set(countryIds);
  const knownSlugs = new Set(COMPARE_PARAMETERS.map(parameter => parameter.slug));
  const countries = params.has("c")
    ? parseList(params.get("c")).filter(id => knownCountries.has(id)).slice(0, MAX_COMPARE_COUNTRIES)
    : DEFAULT_COMPARE.countries.filter(id => knownCountries.has(id));
  const parameters = params.has("p")
    ? parseList(params.get("p")).filter(slug => knownSlugs.has(slug))
    : DEFAULT_COMPARE.parameters;
  return { countries, parameters, advanced: params.has("a") || params.has("b") };
}

// ------------------------------------------------------------------------- search

// Lower case, Danish letters spelled out (æ -> ae, ø -> o) and accents removed (å -> a,
// é -> e), so "okonomi" finds "Økonomi" and "real" finds "Réal".
function normalizeText(text) {
  return text.toLowerCase()
    .replaceAll("æ", "ae").replaceAll("ø", "o").replaceAll("ß", "ss")
    .normalize("NFD").replace(/[̀-ͯ]/g, "");
}

function tokenize(text) {
  return normalizeText(text).split(/[^a-z0-9]+/).filter(Boolean);
}

// Edits (insert, delete, change, swap two neighbours) to turn a into b, or limit + 1 as
// soon as it is clear the answer is above the limit.
function editDistance(a, b, limit) {
  if (Math.abs(a.length - b.length) > limit) return limit + 1;
  let before = null;
  let previous = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const current = [i];
    let rowMinimum = i;
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      let value = Math.min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost);
      if (before && i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
        value = Math.min(value, before[j - 2] + 1);
      }
      current.push(value);
      rowMinimum = Math.min(rowMinimum, value);
    }
    if (rowMinimum > limit) return limit + 1;
    before = previous;
    previous = current;
  }
  return previous[b.length];
}

// Typos allowed for a word: none for short words, which would match too much.
function allowedTypos(word) {
  return word.length >= 8 ? 2 : word.length >= 4 ? 1 : 0;
}

// How well one search word matches one word of a document: a whole word beats the start
// of a word, which beats the middle of one, which beats a word with a typo. 0 = no match.
function wordScore(query, word) {
  if (word === query) return 4;
  if (word.startsWith(query)) return 3;
  if (query.length >= 2 && word.includes(query)) return 2;
  const typos = allowedTypos(query);
  if (typos === 0) return 0;
  // Compare with the whole word and with its start, so a half-typed word with a typo
  // ("inflaz") still finds "inflation".
  const distance = Math.min(editDistance(query, word, typos),
                            editDistance(query, word.slice(0, query.length), typos));
  return distance <= typos ? 1 : 0;
}

// English and common abbreviations -> words used on the (Danish) page.
const SYNONYMS = {
  cpi: ["inflation"], hicp: ["inflation"], prices: ["inflation", "priser"],
  yield: ["rente", "statsrenter"], yields: ["statsrenter"], bond: ["statsrenter"], bonds: ["statsrenter"],
  rate: ["rente"], rates: ["renter"], interest: ["rente"],
  unemployment: ["ledighed"], jobless: ["ledighed"], jobs: ["job", "ledighed"],
  gdp: ["bnp"], growth: ["vaekst"], recession: ["bnp"],
  policy: ["styringsrente"], central: ["styringsrente"],
  fed: ["styringsrente", "usa"], ecb: ["styringsrente", "ecb"], boj: ["styringsrente", "japan"],
  boe: ["styringsrente", "storbritannien"], pboc: ["styringsrente", "kina"], rbi: ["styringsrente", "indien"],
  bok: ["styringsrente", "sydkorea"], boc: ["styringsrente", "canada"], riksbank: ["styringsrente", "sverige"],
  nationalbanken: ["styringsrente", "danmark"],
  gold: ["guld"], silver: ["solv"], platinum: ["platin"], oil: ["olie"], crude: ["olie"],
  gas: ["naturgas"], lng: ["naturgas"], copper: ["kobber"], aluminum: ["aluminium"], nickel: ["nikkel"],
  zinc: ["zink"], iron: ["jernmalm"], coal: ["kul"], uranium: ["uran"], wheat: ["hvede"],
  corn: ["majs"], soy: ["sojabonner"], soybeans: ["sojabonner"], rice: ["ris"], coffee: ["kaffe"],
  cocoa: ["kakao"], sugar: ["sukker"], commodities: ["ravarer"],
  currency: ["valuta"], fx: ["valuta"], exchange: ["valuta"], dollar: ["dollarindeks", "usd"],
  debt: ["gaeld"], deficit: ["budgetsaldo"], confidence: ["tillid"], sentiment: ["tillid"],
  exports: ["eksport"], housing: ["huspriser"], mortgage: ["realkredit", "boligrente"],
  stocks: ["aktier"], equities: ["aktier"], shares: ["aktier"], aktieindeks: ["aktier"], bors: ["aktier"],
  drawdown: ["fald"], sp500: ["500"], spx: ["500"],
  uk: ["storbritannien"], britain: ["storbritannien"], germany: ["tyskland"], france: ["frankrig"],
  denmark: ["danmark"], norway: ["norge"], sweden: ["sverige"], china: ["kina"], korea: ["sydkorea"],
  india: ["indien"], indonesia: ["indonesien"], europe: ["europa"], asia: ["asien"],
  america: ["nordamerika", "usa"], us: ["usa"],
};

// A search word's best match in a document, counting its synonyms too.
function bestWordScore(query, words) {
  const alternatives = [query, ...(SYNONYMS[query] ?? [])];
  let best = 0;
  for (const alternative of alternatives) {
    for (const word of words) best = Math.max(best, wordScore(alternative, word));
  }
  return best;
}

// Documents matching every word of the query, best first. A document has `words` (its
// title, country, region and group), optional `seriesWords` (the names of its series,
// which count half: "Japan (BoJ)" in Global's policy rates is not about Japan) and an
// `order` that breaks ties, so results follow the page's order.
function search(query, documents, limit = 12) {
  const queryWords = tokenize(query);
  if (queryWords.length === 0) return [];
  const hits = [];
  for (const document of documents) {
    let total = 0;
    for (const queryWord of queryWords) {
      const score = Math.max(bestWordScore(queryWord, document.words),
                             bestWordScore(queryWord, document.seriesWords ?? []) / 2);
      if (score === 0) {
        total = 0;
        break;
      }
      total += score;
    }
    if (total > 0) hits.push({ document, score: total });
  }
  hits.sort((a, b) => b.score - a.score || a.document.order - b.document.order);
  return hits.slice(0, limit).map(hit => hit.document);
}

if (typeof module === "object" && module.exports) {
  module.exports = {
    DEFAULT_RANGE_YEARS, MAX_RANGE_YEARS, PRESET_RANGES, isValidRange, parseRange, parseMonth,
    parseList, parseHashState, buildHash, MAX_COMPARE_COUNTRIES, CORE_GROUP, COMPARE_PARAMETERS,
    DEFAULT_COMPARE, parseCompareSelection, normalizeText, tokenize, editDistance, wordScore,
    SYNONYMS, search,
  };
}
