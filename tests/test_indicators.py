"""Consistency checks for the catalog, so a typo is caught before a fetch run."""

import unittest
from collections import Counter

from fetch_data import BATCH_FETCHERS, SINGLE_FETCHERS
from indicators import PANELS, SECTIONS

ALL_SERIES = [s for panel in PANELS for s in panel.series]
KNOWN_SOURCES = set(SINGLE_FETCHERS) | set(BATCH_FETCHERS) | {"derived"}


class CatalogTest(unittest.TestCase):
    def test_series_keys_and_panel_ids_are_unique(self):
        for name, values in (("series key", [s.key for s in ALL_SERIES]),
                             ("panel id", [p.id for p in PANELS])):
            duplicates = [value for value, count in Counter(values).items() if count > 1]
            self.assertEqual(duplicates, [], f"duplicate {name}")

    def test_sections_and_sources_are_known(self):
        section_ids = {section_id for section_id, _ in SECTIONS}
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

    def test_panels_of_a_group_are_adjacent(self):
        # The page starts a new sub-heading whenever the group changes, so a group split
        # by another group would show its heading twice.
        for section_id, _ in SECTIONS:
            groups_in_order = [p.group for p in PANELS if p.section == section_id and p.group]
            runs = [group for i, group in enumerate(groups_in_order) if i == 0 or groups_in_order[i - 1] != group]
            self.assertEqual(len(runs), len(set(runs)), f"{section_id}: {runs}")

    def test_derived_series_use_fetched_series_as_input(self):
        fetched_keys = {s.key for s in ALL_SERIES if s.source != "derived"}
        for s in ALL_SERIES:
            if s.source == "derived":
                self.assertLessEqual(set(s.query), fetched_keys, s.key)


if __name__ == "__main__":
    unittest.main()
