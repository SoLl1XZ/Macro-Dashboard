// Tests for lib.js. Run with: node --test tests/js/
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const lib = require("../../lib.js");

const TABS = ["signals", "global", "japan", "europe", "compare"];

test("range: whole years 1-100 or 0 (Maks); anything else gives the default", () => {
  assert.equal(lib.parseRange("7"), 7);
  assert.equal(lib.parseRange("0"), 0);
  assert.equal(lib.parseRange("100"), 100);
  for (const bad of ["101", "-3", "2.5", "abc", "", null, "007x"]) {
    assert.equal(lib.parseRange(bad), lib.DEFAULT_RANGE_YEARS, String(bad));
  }
});

test("hash: tab, range, panel, full screen and a month window", () => {
  const state = lib.parseHashState("#japan?range=7&panel=jp_jgb&full=1&from=2007-01&to=2012-12", TABS, "signals");
  assert.equal(state.sectionId, "japan");
  assert.equal(state.rangeYears, 7);
  assert.equal(state.panel, "jp_jgb");
  assert.equal(state.full, true);
  assert.equal(state.from, "2007-01");
  assert.equal(state.to, "2012-12");
  assert.equal([...state.params].length, 0); // the known keys are taken out
});

test("hash: unknown tab, missing range and bad months fall back", () => {
  const state = lib.parseHashState("#nowhere?from=2012-13&to=2007-01", TABS, "signals");
  assert.equal(state.sectionId, "signals");
  assert.equal(state.rangeYears, lib.DEFAULT_RANGE_YEARS);
  assert.equal(state.from, null); // month 13 doesn't exist
  assert.equal(state.full, false);
  const reversed = lib.parseHashState("#japan?from=2012-01&to=2007-01", TABS, "signals");
  assert.deepEqual([reversed.from, reversed.to], [null, null]); // start after end
});

test("hash: old links keep working", () => {
  const state = lib.parseHashState("#europe?range=10", TABS, "signals");
  assert.deepEqual([state.sectionId, state.rangeYears, state.panel], ["europe", 10, null]);
  const compare = lib.parseHashState("#compare?a=de_10y&b=us_10y&index=1", TABS, "signals");
  assert.equal(compare.params.get("a"), "de_10y");
  assert.equal(compare.params.get("index"), "1");
});

test("buildHash round-trips and keeps links short and readable", () => {
  assert.equal(lib.buildHash("japan", 5), "#japan"); // default range left out
  assert.equal(lib.buildHash("japan", 7, { panel: "jp_jgb", full: true, from: null }),
               "#japan?range=7&panel=jp_jgb&full=1");
  assert.equal(lib.buildHash("compare", 5, { c: ["denmark", "sweden"], p: "inflation" }),
               "#compare?c=denmark,sweden&p=inflation");
  const state = lib.parseHashState(lib.buildHash("japan", 0, { panel: "jp_jgb" }), TABS, "signals");
  assert.deepEqual([state.rangeYears, state.panel], [0, "jp_jgb"]);
});

test("compare: default choice, user choice, unknown ids and at most 8 countries", () => {
  const countries = ["denmark", "sweden", "norway", "germany", "france", "uk", "us", "canada", "japan", "korea"];
  const parse = query => lib.parseCompareSelection(new URLSearchParams(query), countries);
  assert.deepEqual(parse(""), { ...lib.DEFAULT_COMPARE, advanced: false });
  assert.deepEqual(parse("c=sweden,narnia,sweden&p=inflation,nonsense"),
                   { countries: ["sweden"], parameters: ["inflation"], advanced: false });
  assert.equal(parse(`c=${countries.join(",")}`).countries.length, lib.MAX_COMPARE_COUNTRIES);
  assert.deepEqual(parse("c=&p=").countries, []); // cleared on purpose, not the default
  assert.equal(parse("a=de_10y&b=us_10y").advanced, true);
});

test("normalizeText ignores case, Danish letters and accents", () => {
  assert.equal(lib.normalizeText("Økonomisk STEMNING"), "okonomisk stemning");
  assert.equal(lib.normalizeText("Ædelmetaller på Råvarer"), "aedelmetaller pa ravarer");
  assert.equal(lib.normalizeText("Réal"), "real");
});

test("editDistance counts typos and stops early above the limit", () => {
  assert.equal(lib.editDistance("inflaton", "inflation", 2), 1); // one letter missing
  assert.equal(lib.editDistance("ledihged", "ledighed", 2), 1); // two letters swapped
  assert.equal(lib.editDistance("kobber", "guld", 1), 2); // limit + 1
});

test("wordScore: whole word > start > middle > typo", () => {
  assert.equal(lib.wordScore("inflation", "inflation"), 4);
  assert.equal(lib.wordScore("infl", "inflation"), 3);
  assert.equal(lib.wordScore("rente", "styringsrente"), 2);
  assert.equal(lib.wordScore("inflaton", "inflation"), 1);
  assert.equal(lib.wordScore("ab", "abc"), 3);
  assert.equal(lib.wordScore("xyz", "abc"), 0); // short words get no typos
});

const DOCS = [
  { name: "Japan › Statsrenter", words: lib.tokenize("Japan Asien Kernetal Statsrenter 10 år 2 år"), order: 1 },
  { name: "Japan › Inflation", words: lib.tokenize("Japan Asien Kernetal Inflation CPI"), order: 2 },
  { name: "Danmark › Ledighed", words: lib.tokenize("Danmark Europa Kernetal Ledighed Bruttoledighed"), order: 3 },
  { name: "Råvarer › Guld", words: lib.tokenize("Råvarer Ædelmetaller Guld (USD/troy oz)"), order: 4 },
  { name: "Tyskland › Styringsrente", words: lib.tokenize("Tyskland Europa Styringsrente ECB's indlånsrente"), order: 5 },
];
const names = query => lib.search(query, DOCS).map(document => document.name);

test("search: every word must match, in any order and any case", () => {
  assert.deepEqual(names("japan statsrenter"), ["Japan › Statsrenter"]);
  assert.deepEqual(names("RENTER JAPAN"), ["Japan › Statsrenter"]);
  assert.deepEqual(names("japan"), ["Japan › Statsrenter", "Japan › Inflation"]);
  assert.deepEqual(names(""), []);
});

test("search: a word in a title or country outranks one in a series name", () => {
  const documents = [
    // Global's policy rates panel lists "Japan (BoJ)" as one of its series.
    { name: "Global › Styringsrenter", words: lib.tokenize("Global Styringsrenter"),
      seriesWords: lib.tokenize("USA (Fed) Japan (BoJ)"), order: 1 },
    { name: "Japan › Statsrenter", words: lib.tokenize("Japan Asien Kernetal Statsrenter"),
      seriesWords: lib.tokenize("10 år 2 år"), order: 2 },
  ];
  assert.deepEqual(lib.search("japan renter", documents).map(document => document.name),
                   ["Japan › Statsrenter", "Global › Styringsrenter"]);
});

test("search: synonyms, typos and words in the middle", () => {
  assert.deepEqual(names("gold"), ["Råvarer › Guld"]);
  assert.deepEqual(names("unemployment denmark"), ["Danmark › Ledighed"]);
  assert.deepEqual(names("ecb"), ["Tyskland › Styringsrente"]);
  assert.deepEqual(names("ledihged"), ["Danmark › Ledighed"]);
  assert.deepEqual(names("aedelmetal"), ["Råvarer › Guld"]);
  assert.deepEqual(names("ædelmetal"), ["Råvarer › Guld"]);
  assert.deepEqual(names("cpi japan"), ["Japan › Inflation"]);
});

test("search: share prices by name and in English", () => {
  // Built like buildSearchIndex in app.js: title, group and tab as words, series as seriesWords.
  const panel = (title, group, series, order) => ({
    name: `Aktier › ${title}`, words: lib.tokenize(`${title} ${group} Aktier`),
    seriesWords: lib.tokenize(series), order,
  });
  const documents = [
    panel("Aktier i Europa", "Regioner", "Euroområdet Tyskland Danmark", 1),
    panel("S&P 500", "Kendte indeks", "S&P 500", 2),
    panel("Euro Stoxx 50", "Kendte indeks", "Euro Stoxx 50", 3),
    panel("Fald fra toppen i Europa", "Fald fra toppen", "Euroområdet Tyskland Danmark", 4),
    ...DOCS.map(document => ({ ...document, order: document.order + 10 })),
  ];
  const found = query => lib.search(query, documents).map(document => document.name);
  assert.deepEqual(found("S&P 500"), ["Aktier › S&P 500"]);
  assert.deepEqual(found("sp500"), ["Aktier › S&P 500"]);
  assert.deepEqual(found("stocks"), ["Aktier › Aktier i Europa", "Aktier › S&P 500",
                                     "Aktier › Euro Stoxx 50", "Aktier › Fald fra toppen i Europa"]);
  assert.deepEqual(found("aktieindeks"), found("stocks"));
  assert.deepEqual(found("drawdown"), ["Aktier › Fald fra toppen i Europa"]);
  assert.deepEqual(found("equities germany"), ["Aktier › Aktier i Europa", "Aktier › Fald fra toppen i Europa"]);
});
