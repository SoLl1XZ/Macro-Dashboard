"""Consistency checks for the catalog, so a typo is caught before a fetch run."""

import unittest
from collections import Counter

from fetch_data import BATCH_FETCHERS, SINGLE_FETCHERS
from indicators import CORE_GROUP, CORE_TITLES, PANELS, SECTIONS, Ref, owned_series

COUNTRIES_BY_REGION = {
    "north-america": ["us", "canada"],
    "europe": ["uk", "germany", "france", "denmark", "norway", "sweden"],
    "asia": ["china", "japan", "korea", "thailand", "vietnam", "indonesia", "malaysia", "india"],
}

ALL_SERIES = owned_series(PANELS)
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
                self.assertEqual(s.transform, "spread", s.key)
            else:
                self.assertIn(s.transform, {None, "yoy", "diff"}, s.key)

    def test_sections_are_in_the_agreed_menu_order(self):
        # The page adds Signaler in front and Sammenlign at the end of these.
        self.assertEqual([section.id for section in SECTIONS],
                         ["global", "north-america", *COUNTRIES_BY_REGION["north-america"],
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
                # as differences or as percent changes depending on the panel.
                self.assertEqual(owner_by_key[ref.key].change, panel.change)

    def test_derived_series_use_fetched_series_as_input(self):
        fetched_keys = {s.key for s in ALL_SERIES if s.source != "derived"}
        for s in ALL_SERIES:
            if s.source == "derived":
                self.assertLessEqual(set(s.query), fetched_keys, s.key)


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


if __name__ == "__main__":
    unittest.main()
