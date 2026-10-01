"""Protect the last valid public snapshot from malformed or partial updates."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sync_gdp as gdp


def response(series="gdp_cny"):
    indicator, countries, _, _ = gdp.SERIES[series]
    last = datetime.now(timezone.utc).year - 1
    records = [{"countryiso3code": c, "date": str(y), "value": 2.5 if series == "gdp_growth" else 1000 + y,
                "indicator": {"id": indicator}, "obs_status": ""}
               for c in countries for y in range(last - 35, last + 1)]
    return [{"page": 1, "pages": 1, "total": len(records), "sourceid": "2",
             "lastupdated": "2026-01-01"}, records]


def rows(series="gdp_cny"):
    return gdp.parse_response(response(series), series, "2026-01-01T00:00:00+00:00")[0]


class ResponseTests(unittest.TestCase):
    def test_null_stays_empty_and_publication_is_unknown(self):
        payload = response()
        payload[1][0]["value"] = None
        result, _ = gdp.parse_response(payload, "gdp_cny", "now")
        self.assertEqual(result[0]["value"], "")
        self.assertEqual(result[0]["published_at"], "")

    def test_bad_values_are_rejected(self):
        for value in [True, "nan", float("inf"), 0, -1, "bad"]:
            with self.subTest(value=value):
                payload = response()
                payload[1][0]["value"] = value
                with self.assertRaises(ValueError):
                    gdp.parse_response(payload, "gdp_cny", "now")

    def test_real_growth_can_be_negative(self):
        payload = response("gdp_growth")
        payload[1][0]["value"] = -5
        result, _ = gdp.parse_response(payload, "gdp_growth", "now")
        self.assertEqual(result[0]["value"], "-5")

    def test_bad_country_indicator_year_and_duplicates(self):
        for field, value in [("countryiso3code", "GBR"), ("indicator", {"id": "wrong"}),
                             ("date", "2024-Q1"), ("date", str(datetime.now(timezone.utc).year))]:
            with self.subTest(field=field, value=value):
                payload = response()
                payload[1][0][field] = value
                with self.assertRaises(ValueError):
                    gdp.parse_response(payload, "gdp_cny", "now")
        payload = response()
        payload[1][1] = payload[1][0]
        with self.assertRaises(ValueError):
            gdp.parse_response(payload, "gdp_cny", "now")

    def test_partial_pagination_and_wrong_source(self):
        for field, value in [("pages", 2), ("total", 999), ("sourceid", "1")]:
            payload = response()
            payload[0][field] = value
            with self.assertRaises(ValueError):
                gdp.parse_response(payload, "gdp_cny", "now")

    def test_missing_country_history(self):
        payload = response("gdp_usd")
        payload[1] = [r for r in payload[1] if r["countryiso3code"] != "USA"]
        payload[0]["total"] = len(payload[1])
        with self.assertRaises(ValueError):
            gdp.parse_response(payload, "gdp_usd", "now")


class RevisionTests(unittest.TestCase):
    def test_partial_history_and_null_regression(self):
        old = rows()
        with self.assertRaises(ValueError):
            gdp.check_revision(old, old[1:])
        new = deepcopy(old)
        new[0]["value"] = ""
        with self.assertRaises(ValueError):
            gdp.check_revision(old, new)

    def test_real_revision_is_accepted(self):
        old = rows()
        new = deepcopy(old)
        new[0]["value"] = "4000"
        self.assertEqual(gdp.check_revision(old, new), (0, 1))

    def test_duplicate_snapshot_and_unit_change(self):
        old = rows()
        with self.assertRaises(ValueError):
            gdp.check_revision(old, old + [old[0]])
        new = deepcopy(old)
        new[0]["unit"] = "USD"
        with self.assertRaises(ValueError):
            gdp.check_revision(old, new)

    def test_polling_does_not_refresh_snapshot_timestamp(self):
        def fake_fetch(url):
            for name, (indicator, _, _, _) in gdp.SERIES.items():
                if indicator in url:
                    if "/country/" in url:
                        return response(name)
                    return [{}, [{"id": indicator, "source": {"id": "2"},
                                  "sourceNote": "definition", "sourceOrganization": "provider"}]]
            raise AssertionError(url)
        with patch.object(gdp, "fetch_json", side_effect=fake_fetch):
            previous, meta = gdp.collect([], {})
            meta["retrieved_at"] = "2026-01-02T00:00:00+00:00"
            for row in previous:
                row["retrieved_at"] = meta["retrieved_at"]
            current, current_meta = gdp.collect(previous, meta)
        self.assertIs(current, previous)
        self.assertIs(current_meta, meta)

    def test_fetch_failure_never_reaches_publish(self):
        with patch.object(gdp, "load_snapshot", return_value=(rows(), {})), \
             patch.object(gdp, "fetch_json", side_effect=TimeoutError), \
             patch.object(gdp, "publish") as publish, \
             patch.object(sys, "argv", ["sync_gdp.py"]):
            with self.assertRaises(TimeoutError):
                gdp.main()
        publish.assert_not_called()

    def test_render_failure_preserves_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            existing = root / "data/gdp.csv"
            existing.write_text("last valid snapshot", encoding="utf-8")
            with patch.object(gdp, "ROOT", root), \
                 patch.object(gdp, "render_charts", side_effect=RuntimeError("render failed")):
                with self.assertRaises(RuntimeError):
                    gdp.publish(rows(), {})
            self.assertEqual(existing.read_text(), "last valid snapshot")
            self.assertFalse((root / "data/gdp.metadata.json").exists())


if __name__ == "__main__":
    unittest.main()
