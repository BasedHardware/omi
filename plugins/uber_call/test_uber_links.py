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


if __name__ == "__main__":
    unittest.main()
