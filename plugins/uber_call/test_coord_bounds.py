"""Coordinate bounds for Uber deep links (#13291)."""

import unittest

from uber_links import build_location


class TestCoordinateBounds(unittest.TestCase):
    def test_accepts_valid_bounds(self):
        loc = build_location(latitude=90, longitude=-180)
        self.assertEqual(loc.latitude, 90)
        self.assertEqual(loc.longitude, -180)

    def test_rejects_out_of_range_pair(self):
        for lat, lng in [(91, 0), (0, 181), (-91, 0), (0, -181)]:
            with self.assertRaises(ValueError):
                build_location(latitude=lat, longitude=lng)

    def test_rejects_out_of_range_single_coordinate(self):
        with self.assertRaises(ValueError):
            build_location(latitude=200, longitude=None)
        with self.assertRaises(ValueError):
            build_location(latitude=None, longitude=181)


if __name__ == "__main__":
    unittest.main()
