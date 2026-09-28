import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent))
import conversations_to_geojson as c2g


class TestConversationsToGeoJSON(unittest.TestCase):

    def setUp(self):
        self.sample_convs = [
            {
                "id": "conv-geo-1",
                "title": "Coffee at Blue Bottle",
                "category": "personal",
                "started_at": "2026-09-28T09:00:00Z",
                "duration_seconds": 1200,
                "geolocation": {
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "altitude": 15.0,
                    "address": "66 Mint St, San Francisco, CA",
                    "location_name": "Blue Bottle Coffee"
                },
                "structured": {
                    "overview": "Met with team to discuss mobile SDK launch."
                },
                "transcript": "Hello everyone, good morning."
            },
            {
                "id": "conv-geo-2",
                "title": "Remote Brainstorming Session",
                "category": "work",
                "started_at": "2026-09-28T14:00:00Z",
                "structured": {
                    "overview": "Discussed feature roadmap."
                },
                # No coordinates
            }
        ]

    def test_geojson_valid_feature_collection(self):
        with TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "conversations.json"
            input_file.write_text(json.dumps(self.sample_convs), encoding="utf-8")
            output_file = Path(tmpdir) / "output.geojson"

            ret = c2g.main([str(input_file), "-o", str(output_file)])
            self.assertEqual(ret, 0)
            self.assertTrue(output_file.exists())

            data = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(data["type"], "FeatureCollection")
            features = data["features"]
            self.assertEqual(len(features), 2)

            # Feature 1 (with coordinates)
            f1 = next(f for f in features if f["properties"]["id"] == "conv-geo-1")
            self.assertEqual(f1["type"], "Feature")
            self.assertEqual(f1["geometry"]["type"], "Point")
            self.assertEqual(f1["geometry"]["coordinates"], [-122.4194, 37.7749, 15.0])
            self.assertEqual(f1["properties"]["title"], "Coffee at Blue Bottle")
            self.assertEqual(f1["properties"]["location_name"], "Blue Bottle Coffee")

            # Feature 2 (without coordinates: geometry is None)
            f2 = next(f for f in features if f["properties"]["id"] == "conv-geo-2")
            self.assertIsNone(f2["geometry"])

    def test_require_coords_flag(self):
        with TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "conversations.json"
            input_file.write_text(json.dumps(self.sample_convs), encoding="utf-8")
            output_file = Path(tmpdir) / "filtered.geojson"

            ret = c2g.main([str(input_file), "-o", str(output_file), "--require-coords"])
            self.assertEqual(ret, 0)

            data = json.loads(output_file.read_text(encoding="utf-8"))
            features = data["features"]
            # Only conv-geo-1 should remain
            self.assertEqual(len(features), 1)
            self.assertEqual(features[0]["properties"]["id"], "conv-geo-1")

    def test_deduplication(self):
        with TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "f1.json"
            f2 = Path(tmpdir) / "f2.json"
            f1.write_text(json.dumps([self.sample_convs[0]]), encoding="utf-8")
            f2.write_text(json.dumps(self.sample_convs), encoding="utf-8")

            output_file = Path(tmpdir) / "dedup.geojson"
            ret = c2g.main([str(f1), str(f2), "-o", str(output_file)])
            self.assertEqual(ret, 0)

            data = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(len(data["features"]), 2)

    def test_category_filter(self):
        with TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "conversations.json"
            input_file.write_text(json.dumps(self.sample_convs), encoding="utf-8")
            output_file = Path(tmpdir) / "category.geojson"

            ret = c2g.main([str(input_file), "-o", str(output_file), "--filter-category", "work"])
            self.assertEqual(ret, 0)

            data = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(len(data["features"]), 1)
            self.assertEqual(data["features"][0]["properties"]["category"], "work")

    def test_path_traversal_safety(self):
        ret = c2g.main(["dummy.json", "-o", "../evil.geojson"])
        self.assertEqual(ret, 2)


if __name__ == "__main__":
    unittest.main()
