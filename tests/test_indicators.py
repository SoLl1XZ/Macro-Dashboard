"""Consistency checks for the catalog, so a typo is caught before a fetch run."""

import re
import unittest
from collections import Counter
from pathlib import Path

from fetch_data import BATCH_FETCHERS, SINGLE_FETCHERS
from indicators import CORE_GROUP, CORE_TITLES, INPUT_SERIES, PANELS, SECTIONS, Ref, owned_series

COUNTRIES_BY_REGION = {
    "north-america": ["us", "canada"],
    "europe": ["uk", "germany", "france", "denmark", "norway", "sweden"],
    "asia": ["china", "japan", "korea", "thailand", "vietnam", "indonesia", "malaysia", "india"],
}

# Input-only series count too: their keys must not clash, and derived series may use them.
ALL_SERIES = owned_series(PANELS) + INPUT_SERIES
ALL_REFS = [(panel, s) for panel in PANELS for s in panel.series if isinstance(s, Ref)]
KNOWN_SOURCES = set(SINGLE_FETCHERS) | set(BATCH_FETCHERS) | {"derived"}


class CatalogTest(unittest.TestCase):
    def test_series_keys_and_panel_ids_are_unique(self):
        for name, values in (("series key", [s.key for s in ALL_SERIES]),
                             ("panel id", [p.id for p in PANELS])):
            duplicates = [value for value, count in Counter(values).items() if count > 1]
            self.assertEqual(duplicates, [], f"duplicate {name}")

    def test_sections_and_sources_are_known(self):
        section_ids = {section.id for section in SECTIONS}
        for panel in PANELS:
            self.assertIn(panel.section, section_ids, panel.id)
            self.assertIn(panel.change, {"diff", "pct"}, panel.id)
        for s in ALL_SERIES:
            self.assertIn(s.source, KNOWN_SOURCES, s.key)

    def test_transforms_are_known(self):
        for s in ALL_SERIES:
            if s.source == "derived":
                self.assertIn(s.transform, {"spread", "ratio", "real"}, s.key)
            else:
                self.assertIn(s.transform, {None, "yoy", "diff"}, s.key)

    def test_sections_are_in_the_agreed_menu_order(self):
        # The page adds Signaler in front and Sammenlign at the end of these.
        self.assertEqual([section.id for section in SECTIONS],
                         ["global", "commodities", "north-america", *COUNTRIES_BY_REGION["north-america"],
                          "europe", *COUNTRIES_BY_REGION["europe"],
                          "asia", *COUNTRIES_BY_REGION["asia"]])

    def test_panels_of_a_group_are_adjacent(self):
        # The page starts a new sub-heading whenever the group changes, so a group split
        # by another group would show its heading twice.
        for section in SECTIONS:
            groups_in_order = [p.group for p in PANELS if p.section == section.id and p.group]
            runs = [group for i, group in enumerate(groups_in_order) if i == 0 or groups_in_order[i - 1] != group]
            self.assertEqual(len(runs), len(set(runs)), f"{section.id}: {runs}")

    def test_references_point_to_series_owned_elsewhere(self):
        owner_by_key = {s.key: panel for panel in PANELS for s in panel.series if not isinstance(s, Ref)}
        for panel, ref in ALL_REFS:
            with self.subTest(panel=panel.id, ref=ref.key):
                self.assertIn(ref.key, owner_by_key)
                # The page shows the owner's 1-month and 1-year changes, which are computed
                # as differences or as percent changes depending on the panel. A split panel
                # formats each series on its own, with its owner's change type.
                if not panel.split:
                    self.assertEqual(owner_by_key[ref.key].change, panel.change)

    def test_comparable_series_belongs_to_its_panel(self):
        for panel in PANELS:
            if panel.comparable:
                self.assertIn(panel.comparable, [s.key for s in panel.series], panel.id)

    def test_derived_series_use_fetched_series_as_input(self):
        fetched_keys = {s.key for s in ALL_SERIES if s.source != "derived"}
        for s in ALL_SERIES:
            if s.source == "derived":
                self.assertLessEqual(set(s.query), fetched_keys, s.key)


class CommoditiesTest(unittest.TestCase):
    PANELS = [panel for panel in PANELS if panel.section == "commodities"]

    def test_groups_come_in_the_agreed_order(self):
        groups = list(dict.fromkeys(panel.group for panel in self.PANELS))
        self.assertEqual(groups, ["Indeks", "Energi", "Industrimetaller", "Ædelmetaller", "Landbrug", "Analyse"])

    def test_prices_change_in_percent(self):
        for panel in self.PANELS:
            self.assertEqual(panel.change, "pct", panel.id)

    def test_moved_series_keep_their_keys(self):
        # Links and saved comparisons from before the Råvarer tab use these keys.
        keys = {s.key for s in owned_series(self.PANELS)}
        self.assertLessEqual({"brent", "wti", "gas_us", "gas_eu", "copper", "wheat"}, keys)


class RegionTest(unittest.TestCase):
    def test_every_region_is_a_top_level_section(self):
        top_level = {section.id for section in SECTIONS if section.region is None}
        for section in SECTIONS:
            if section.region is not None:
                self.assertIn(section.region, top_level, section.id)

    def test_countries_lie_in_their_region(self):
        countries = {region: [section.id for section in SECTIONS if section.region == region]
                     for region in COUNTRIES_BY_REGION}
        self.assertEqual(countries, COUNTRIES_BY_REGION)

    def test_ids_from_before_the_regions_still_exist(self):
        # Old links such as #europe?range=10 or #denmark must keep working.
        ids = {section.id for section in SECTIONS}
        self.assertLessEqual({"global", "us", "europe", "denmark", "asia", "china", "japan", "korea"}, ids)


class CompareParametersTest(unittest.TestCase):
    def test_lib_js_lists_the_core_titles_in_order(self):
        # The Compare tab finds a country's core panel by title, so lib.js must use the
        # same titles as CORE_TITLES here.
        lib = (Path(__file__).parent.parent / "lib.js").read_text(encoding="utf-8")
        block = lib[lib.index("const COMPARE_PARAMETERS"):lib.index("];", lib.index("const COMPARE_PARAMETERS"))]
        self.assertEqual(re.findall(r'title: "([^"]+)"', block), list(CORE_TITLES))
        self.assertIn(f'const CORE_GROUP = "{CORE_GROUP}";', lib)


class CorePanelsTest(unittest.TestCase):
    def country_panels(self):
        for section in SECTIONS:
            if section.region is not None:
                yield section.id, [panel for panel in PANELS if panel.section == section.id]

    def test_core_panels_come_first_in_the_agreed_order(self):
        for country, panels in self.country_panels():
            with self.subTest(country=country):
                is_core = [panel.group == CORE_GROUP for panel in panels]
                self.assertEqual(is_core, sorted(is_core, reverse=True))  # no core panel after an extra
                titles = [panel.title for panel in panels if panel.group == CORE_GROUP]
                self.assertLessEqual(set(titles), set(CORE_TITLES))
                positions = [CORE_TITLES.index(title) for title in titles]
                self.assertEqual(positions, sorted(set(positions)))  # in order, each at most once

    def test_every_country_has_the_panels_our_sources_cover_for_all(self):
        # IMF and the exchange rates cover all 16 countries; the other core panels are
        # left out where no trustworthy free source exists (see CLAUDE.md).
        always = {"Inflation", "Ledighed", "BNP-vækst inkl. IMF-prognose", "Valuta",
                  "Statsgæld", "Betalingsbalance"}
        for country, panels in self.country_panels():
            with self.subTest(country=country):
                self.assertLessEqual(always, {panel.title for panel in panels if panel.group == CORE_GROUP})


if __name__ == "__main__":
    unittest.main()
