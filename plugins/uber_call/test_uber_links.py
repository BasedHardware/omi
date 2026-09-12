import math
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from uber_links import build_location, build_uber_deep_links


class UberDeepLinkTests(unittest.TestCase):
    def test_destination_builds_mobile_web_and_app_links(self):
        links = build_uber_deep_links(destination="SFO Airport")

        self.assertTrue(links.web_link.startswith("https://m.uber.com/ul/?"))
        self.assertTrue(links.app_link.startswith("uber://?"))
        self.assertIn("action=setPickup", links.web_link)
        self.assertIn("pickup=my_location", links.web_link)
        self.assertIn("dropoff[formatted_address]=SFO%20Airport", links.web_link)
        self.assertIn("dropoff[nickname]=SFO%20Airport", links.web_link)

    def test_coordinates_and_product_id_are_preserved(self):
        pickup = build_location(latitude=37.775818, longitude=-122.418028, formatted_address="1455 Market St")
        dropoff = build_location(latitude=37.6213129, longitude=-122.3789554, formatted_address="SFO")

        links = build_uber_deep_links(pickup=pickup, dropoff=dropoff, product_id="product-123")

        self.assertIn("pickup[latitude]=37.775818", links.web_link)
        self.assertIn("pickup[longitude]=-122.418028", links.web_link)
        self.assertIn("dropoff[latitude]=37.6213129", links.web_link)
        self.assertIn("dropoff[longitude]=-122.3789554", links.web_link)
        self.assertIn("product_id=product-123", links.web_link)

    def test_destination_is_required(self):
        with self.assertRaises(ValueError):
            build_uber_deep_links()

    def test_whitespace_destination_is_rejected(self):
        with self.assertRaises(ValueError):
            build_uber_deep_links(destination="   ")

    # --- new coordinate-validation regression tests (issue #13291) ---

    def test_latitude_above_90_is_rejected(self):
        with self.assertRaises(ValueError, msg="latitude 91 should be rejected"):
            build_location(latitude=91, longitude=0)

    def test_latitude_below_minus_90_is_rejected(self):
        with self.assertRaises(ValueError):
            build_location(latitude=-91, longitude=0)

    def test_longitude_above_180_is_rejected(self):
        with self.assertRaises(ValueError, msg="longitude 181 should be rejected"):
            build_location(latitude=0, longitude=181)

    def test_longitude_below_minus_180_is_rejected(self):
        with self.assertRaises(ValueError):
            build_location(latitude=0, longitude=-181)

    def test_non_finite_latitude_nan_is_rejected(self):
        with self.assertRaises(ValueError):
            build_location(latitude=float("nan"), longitude=0)

    def test_non_finite_latitude_inf_is_rejected(self):
        with self.assertRaises(ValueError):
            build_location(latitude=float("inf"), longitude=0)

    def test_non_finite_longitude_nan_is_rejected(self):
        with self.assertRaises(ValueError):
            build_location(latitude=0, longitude=float("nan"))

    def test_boundary_values_are_accepted(self):
        # exact boundary values should be valid
        loc = build_location(latitude=90, longitude=180)
        self.assertEqual(loc.latitude, 90.0)
        self.assertEqual(loc.longitude, 180.0)

        loc2 = build_location(latitude=-90, longitude=-180)
        self.assertEqual(loc2.latitude, -90.0)
        self.assertEqual(loc2.longitude, -180.0)

    def test_valid_coordinates_pass_through_unchanged(self):
        pickup = build_location(latitude=37.775818, longitude=-122.418028)
        self.assertAlmostEqual(pickup.latitude, 37.775818)
        self.assertAlmostEqual(pickup.longitude, -122.418028)

    def test_pickup_out_of_range_coordinate_raises_on_build_location(self):
        with self.assertRaises(ValueError):
            build_location(latitude=91, longitude=0)


if __name__ == "__main__":
    unittest.main()
