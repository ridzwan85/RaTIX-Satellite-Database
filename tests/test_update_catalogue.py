import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "update_catalogue.py"
SPEC = importlib.util.spec_from_file_location("update_catalogue", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def valid_record(norad_id=25544):
    return {
        "OBJECT_NAME": "ISS (ZARYA)",
        "OBJECT_ID": "1998-067A",
        "NORAD_CAT_ID": norad_id,
        "EPOCH": "2026-11-15T00:00:00.000Z",
        "MEAN_MOTION": 15.5,
        "ECCENTRICITY": 0.0005,
        "INCLINATION": 51.6,
        "RA_OF_ASC_NODE": 120.0,
        "ARG_OF_PERICENTER": 80.0,
        "MEAN_ANOMALY": 20.0,
    }


class CatalogueValidationTests(unittest.TestCase):
    def test_valid_record(self):
        records, newest = MODULE.validate_catalogue([valid_record()])
        self.assertEqual(len(records), 1)
        self.assertEqual(newest, "2026-11-15T00:00:00Z")

    def test_epoch_without_timezone_is_treated_as_utc(self):
        record = valid_record()
        record["EPOCH"] = "2026-11-15T06:23:28.204224"
        _, newest = MODULE.validate_catalogue([record])
        self.assertEqual(newest, "2026-11-15T06:23:28.204224Z")

    def test_duplicate_norad_id_rejected(self):
        with self.assertRaises(MODULE.CatalogueError):
            MODULE.validate_catalogue([valid_record(), valid_record()])

    def test_invalid_eccentricity_rejected(self):
        record = valid_record()
        record["ECCENTRICITY"] = 1.2
        with self.assertRaises(MODULE.CatalogueError):
            MODULE.validate_catalogue([record])

    def test_empty_catalogue_rejected(self):
        with self.assertRaises(MODULE.CatalogueError):
            MODULE.validate_catalogue([])

    def test_download_retries_transient_network_errors(self):
        class FakeResponse:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return b"[]"

        calls = []
        def flaky_urlopen(request, timeout):
            calls.append(timeout)
            if len(calls) < 3:
                raise MODULE.URLError("temporary timeout")
            return FakeResponse()

        original_urlopen = MODULE.urlopen
        original_sleep = MODULE.time.sleep
        try:
            MODULE.urlopen = flaky_urlopen
            MODULE.time.sleep = lambda seconds: None
            payload = MODULE.download_json(attempts=5, timeout=180)
        finally:
            MODULE.urlopen = original_urlopen
            MODULE.time.sleep = original_sleep

        self.assertEqual(payload, b"[]")
        self.assertEqual(calls, [180, 180, 180])

    def test_publish_creates_manifest_and_snapshot(self):
        payload = json.dumps([valid_record()]).encode("utf-8")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = MODULE.publish(payload, root)
            self.assertEqual(manifest["record_count"], 1)
            self.assertTrue((root / "latest.json").exists())
            self.assertTrue((root / manifest["file"]).exists())


if __name__ == "__main__":
    unittest.main()
