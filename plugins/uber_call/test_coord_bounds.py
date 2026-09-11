"""Coordinate bounds for Uber deep links (#13291)."""

import pytest

from uber_links import build_location


def test_accepts_valid_bounds():
    loc = build_location(latitude=90, longitude=-180)
    assert loc.latitude == 90
    assert loc.longitude == -180


@pytest.mark.parametrize(
    ("lat", "lng"),
    [(91, 0), (0, 181), (-91, 0), (0, -181)],
)
def test_rejects_out_of_range(lat, lng):
    with pytest.raises(ValueError, match="Invalid coordinates"):
        build_location(latitude=lat, longitude=lng)
