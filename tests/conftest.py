"""Fixtures for Frankston Bins tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from custom_components.frankston_bins.const import (
    GEOCODE_EARTH_URL,
    VICMAP_GEOCODER_URL,
    ZONES_URL,
)

FIXTURES = Path(__file__).parent / "fixtures"

# 8 Robinsons Road, Frankston South: Area 3, Wednesday collection.
EXAMPLE_ADDRESS = {
    "address": "8 Robinsons Road Frankston South 3199",
    "latitude": -38.175893290950604,
    "longitude": 145.14358768903006,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading the custom integration in every test."""
    return


@pytest.fixture
def zones() -> dict[str, Any]:
    """Snapshot of the council's collection zones (October 2026)."""
    return json.loads((FIXTURES / "zones.json").read_text())


@pytest.fixture
def example_zone(zones) -> dict[str, Any]:
    from custom_components.frankston_bins.schedule import find_zone_properties

    return find_zone_properties(zones, EXAMPLE_ADDRESS["latitude"], EXAMPLE_ADDRESS["longitude"])


def vicmap_response(*candidates: tuple[str, float, float, float]) -> dict[str, Any]:
    return {
        "candidates": [
            {"address": address, "location": {"x": lon, "y": lat}, "score": score}
            for address, lat, lon, score in candidates
        ]
    }


@pytest.fixture
def mock_services(aioclient_mock, zones):
    """Mock the zone file and a Vicmap match for 8 Robinsons Road."""
    aioclient_mock.get(ZONES_URL, json=zones)
    aioclient_mock.get(
        VICMAP_GEOCODER_URL,
        json=vicmap_response(
            (
                "8 ROBINSONS ROAD FRANKSTON SOUTH 3199",
                EXAMPLE_ADDRESS["latitude"],
                EXAMPLE_ADDRESS["longitude"],
                98.5,
            )
        ),
    )
    aioclient_mock.get(GEOCODE_EARTH_URL, json={"features": []})
    return aioclient_mock
