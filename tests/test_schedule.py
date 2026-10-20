"""Tests for the collection date maths, checked against the council's calendars."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from custom_components.frankston_bins.schedule import (
    Zone,
    ZoneDataError,
    find_zone_properties,
    point_in_geometry,
    reference_date,
)


def wednesdays(year: int):
    day = date(year, 1, 1)
    while day.weekday() != 2:
        day += timedelta(days=1)
    while day.year == year:
        yield day
        day += timedelta(days=7)


def test_example_address_is_area_3_wednesday(example_zone):
    zone = Zone.from_properties(example_zone)
    assert zone.area == "Area 3"
    assert zone.collection_weekday == "Wednesday"
    assert set(zone.schedules) == {"general_waste", "recycling", "fogo", "glass"}


def test_matches_2026_area_3_printed_calendar(example_zone):
    """Compare against the council's 2026 Area 3 collection calendar PDF.

    In that calendar the week of 5 January is FOGO + glass, weeks then
    alternate recycling / FOGO, and glass is every fourth FOGO week.
    """
    zone = Zone.from_properties(example_zone)
    collections = {
        c.date: c.bin_keys for c in zone.collections_between(date(2026, 1, 1), date(2026, 12, 31))
    }

    days = list(wednesdays(2026))
    assert list(collections) == days  # General waste every week, nothing else on other days

    for index, day in enumerate(days):
        bins = collections[day]
        assert "general_waste" in bins
        expected_stream = "fogo" if index % 2 == 0 else "recycling"
        assert expected_stream in bins, day
        assert ("recycling" in bins) != ("fogo" in bins), day

    glass_days = [day for day, bins in collections.items() if "glass" in bins]
    assert glass_days == [
        date(2026, 1, 7),
        date(2026, 2, 4),
        date(2026, 3, 4),
        date(2026, 4, 1),
        date(2026, 4, 29),
        date(2026, 5, 27),
        date(2026, 6, 24),
        date(2026, 7, 22),
        date(2026, 8, 19),
        date(2026, 9, 16),
        date(2026, 10, 14),
        date(2026, 11, 11),
        date(2026, 12, 9),
    ]


@pytest.mark.parametrize(
    ("today", "expected_date", "expected_bins"),
    [
        (date(2026, 10, 20), date(2026, 10, 21), ["general_waste", "recycling"]),
        (date(2026, 10, 21), date(2026, 10, 21), ["general_waste", "recycling"]),
        (date(2026, 10, 22), date(2026, 10, 28), ["general_waste", "fogo"]),
        (date(2026, 11, 5), date(2026, 11, 11), ["general_waste", "fogo", "glass"]),
    ],
)
def test_next_collection(example_zone, today, expected_date, expected_bins):
    collection = Zone.from_properties(example_zone).next_collection(today)
    assert collection.date == expected_date
    assert collection.bin_keys == expected_bins


def test_bin_next_dates(example_zone):
    zone = Zone.from_properties(example_zone)
    today = date(2026, 10, 20)
    assert zone.schedules["general_waste"].next_date(today) == date(2026, 10, 21)
    assert zone.schedules["recycling"].next_date(today) == date(2026, 10, 21)
    assert zone.schedules["fogo"].next_date(today) == date(2026, 10, 28)
    assert zone.schedules["glass"].next_date(today) == date(2026, 11, 11)


def test_every_zone_parses_and_is_consistent(zones):
    for feature in zones["features"]:
        zone = Zone.from_properties(feature["properties"])
        weekdays = {s.weekday for s in zone.schedules.values()}
        assert weekdays == {feature["properties"]["rub_day"]}
        rec, fogo = zone.schedules["recycling"], zone.schedules["fogo"]
        # Recycling and FOGO alternate weeks, never on the same day.
        day = rec.next_date(date(2026, 1, 1))
        assert not fogo.is_collected_on(day)
        assert fogo.is_collected_on(day + timedelta(days=7))


def test_reference_date_rolls_over():
    rollover = time(12)
    assert reference_date(datetime(2026, 10, 21, 11, 59), rollover) == date(2026, 10, 21)
    assert reference_date(datetime(2026, 10, 21, 12, 0), rollover) == date(2026, 10, 22)


def test_zone_lookup_outside_frankston(zones):
    # Melbourne CBD
    assert find_zone_properties(zones, -37.8136, 144.9631) is None


def test_point_in_polygon_respects_holes():
    square = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    hole = [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]
    polygon = {"type": "Polygon", "coordinates": [square, hole]}
    assert point_in_geometry(2, 2, polygon)
    assert not point_in_geometry(5, 5, polygon)
    assert not point_in_geometry(11, 5, polygon)


def test_zone_without_glass_service():
    zone = Zone.from_properties(
        {
            "area": "Area 9",
            "rub_start": "2017-01-02",
            "rub_weeks": 1.0,
            "rec_start": "2012-01-02",
            "rec_weeks": 2.0,
            "gls_start": None,
            "gls_weeks": None,
        }
    )
    assert set(zone.schedules) == {"general_waste", "recycling"}


@pytest.mark.parametrize(
    "properties",
    [
        {},
        {"rub_start": "not a date", "rub_weeks": 1},
        {"rub_start": "2017-01-02", "rub_weeks": "x"},
        {"rub_start": "2017-01-02", "rub_weeks": 0.2},
    ],
)
def test_invalid_zone_data(properties):
    with pytest.raises(ZoneDataError):
        Zone.from_properties(properties)
