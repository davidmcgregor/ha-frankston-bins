"""Tests for the config and options flows."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.frankston_bins.const import (
    CONF_ADDRESS,
    CONF_ROLLOVER,
    DOMAIN,
    GEOCODE_EARTH_URL,
    VICMAP_GEOCODER_URL,
    ZONES_URL,
)

from .conftest import EXAMPLE_ADDRESS, vicmap_response


@pytest.fixture(autouse=True)
async def setup_dependencies(hass: HomeAssistant) -> None:
    """Load the integration (and frontend/http) before starting flows.

    Otherwise the first flow sets up the dependencies in the background, and on
    some Home Assistant versions a delayed storage write can outlive the test.
    """
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_single_match_creates_entry(hass: HomeAssistant, mock_services, example_zone):
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "8 Robinsons Road, Frankston South"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "8 Robinsons Road Frankston South 3199"
    assert result["data"][CONF_LATITUDE] == EXAMPLE_ADDRESS["latitude"]
    assert result["data"][CONF_LONGITUDE] == EXAMPLE_ADDRESS["longitude"]
    assert result["data"]["zone"] == example_zone


async def test_multiple_matches_lets_user_pick(hass: HomeAssistant, aioclient_mock, zones):
    aioclient_mock.get(ZONES_URL, json=zones)
    aioclient_mock.get(
        VICMAP_GEOCODER_URL,
        json=vicmap_response(
            (
                "8 ROBINSONS ROAD FRANKSTON SOUTH 3199",
                EXAMPLE_ADDRESS["latitude"],
                EXAMPLE_ADDRESS["longitude"],
                95,
            ),
            ("8 ROBINSONS STREET CARRUM DOWNS 3201", -38.0977, 145.1795, 90),
            ("8 ROBINSONS STREET MELBOURNE 3000", -37.8136, 144.9631, 90),  # outside Frankston
        ),
    )
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "8 Robinsons"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pick"
    options = result["data_schema"].schema["match"].config["options"]
    assert [o["label"] for o in options] == [
        "8 Robinsons Road Frankston South 3199",
        "8 Robinsons Street Carrum Downs 3201",
    ]

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"match": "1"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "8 Robinsons Street Carrum Downs 3201"


async def test_address_outside_frankston(hass: HomeAssistant, aioclient_mock, zones):
    aioclient_mock.get(ZONES_URL, json=zones)
    aioclient_mock.get(
        VICMAP_GEOCODER_URL,
        json=vicmap_response(("1 SPRING STREET MELBOURNE 3000", -37.8136, 144.9631, 99)),
    )
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "1 Spring Street Melbourne"}
    )
    assert result["errors"] == {CONF_ADDRESS: "outside_frankston"}


async def test_no_match_falls_back_to_geocode_earth(hass: HomeAssistant, aioclient_mock, zones):
    aioclient_mock.get(ZONES_URL, json=zones)
    aioclient_mock.get(VICMAP_GEOCODER_URL, status=500)
    aioclient_mock.get(
        GEOCODE_EARTH_URL,
        json={
            "features": [
                {
                    "geometry": {"coordinates": [145.143588, -38.175893]},
                    "properties": {"label": "8 Robinsons Road, Frankston South, VIC, Australia"},
                }
            ]
        },
    )
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "8 Robinsons Road, Frankston South"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "8 Robinsons Road, Frankston South, VIC, Australia"
    assert result["data"]["zone"]["area"] == "Area 3"


async def test_address_not_found(hass: HomeAssistant, aioclient_mock, zones):
    aioclient_mock.get(ZONES_URL, json=zones)
    aioclient_mock.get(VICMAP_GEOCODER_URL, json={"candidates": []})
    aioclient_mock.get(GEOCODE_EARTH_URL, json={"features": []})
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "nowhere"}
    )
    assert result["errors"] == {CONF_ADDRESS: "address_not_found"}


async def test_cannot_connect(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(
        VICMAP_GEOCODER_URL,
        json=vicmap_response(("8 ROBINSONS ROAD FRANKSTON SOUTH 3199", -38.18, 145.14, 99)),
    )
    aioclient_mock.get(ZONES_URL, status=503)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "8 Robinsons Road"}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_blank_address_uses_home_location(hass: HomeAssistant, mock_services):
    hass.config.latitude = EXAMPLE_ADDRESS["latitude"]
    hass.config.longitude = EXAMPLE_ADDRESS["longitude"]
    hass.config.location_name = "Home"
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Home"
    assert result["data"]["zone"]["area"] == "Area 3"


async def test_duplicate_address_aborts(hass: HomeAssistant, mock_services):
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{EXAMPLE_ADDRESS['latitude']:.5f},{EXAMPLE_ADDRESS['longitude']:.5f}",
    ).add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "8 Robinsons Road, Frankston South"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant, mock_services, example_zone):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: EXAMPLE_ADDRESS["address"],
            CONF_LATITUDE: EXAMPLE_ADDRESS["latitude"],
            CONF_LONGITUDE: EXAMPLE_ADDRESS["longitude"],
            "zone": example_zone,
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ROLLOVER: "09:30:00"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {CONF_ROLLOVER: "09:30:00"}
    assert entry.runtime_data.rollover.hour == 9


async def test_malformed_vicmap_candidates_fall_back(hass: HomeAssistant, aioclient_mock, zones):
    aioclient_mock.get(ZONES_URL, json=zones)
    aioclient_mock.get(
        VICMAP_GEOCODER_URL,
        json={
            "candidates": [
                {"address": "NO SCORE", "score": None, "location": {"x": 1, "y": 2}},
                {"score": 99, "location": {"x": 1, "y": 2}},  # no address
                {"address": "NO LOCATION", "score": 99},
            ]
        },
    )
    aioclient_mock.get(
        GEOCODE_EARTH_URL,
        json={
            "features": [
                {"geometry": None, "properties": {"label": "broken"}},
                {"properties": {"label": "also broken"}},
                {
                    "geometry": {"coordinates": [145.143588, -38.175893]},
                    "properties": {"label": "8 Robinsons Road, Frankston South, VIC, Australia"},
                },
            ]
        },
    )
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "8 Robinsons Road, Frankston South"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "8 Robinsons Road, Frankston South, VIC, Australia"


async def test_unexpected_geocoder_payload_is_cannot_connect(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(VICMAP_GEOCODER_URL, json=["not", "a", "dict"])
    aioclient_mock.get(GEOCODE_EARTH_URL, json=["not", "a", "dict"])
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "8 Robinsons Road"}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_same_property_from_other_geocoder_aborts(hass: HomeAssistant, aioclient_mock, zones):
    """geocode.earth places the address ~10 m from where Vicmap did."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{EXAMPLE_ADDRESS['latitude']:.5f},{EXAMPLE_ADDRESS['longitude']:.5f}",
        data={
            CONF_ADDRESS: EXAMPLE_ADDRESS["address"],
            CONF_LATITUDE: EXAMPLE_ADDRESS["latitude"],
            CONF_LONGITUDE: EXAMPLE_ADDRESS["longitude"],
        },
    ).add_to_hass(hass)
    aioclient_mock.get(ZONES_URL, json=zones)
    aioclient_mock.get(VICMAP_GEOCODER_URL, status=500)
    aioclient_mock.get(
        GEOCODE_EARTH_URL,
        json={
            "features": [
                {
                    "geometry": {"coordinates": [145.14368, -38.17595]},
                    "properties": {"label": "8 Robinsons Road, Frankston South, VIC, Australia"},
                }
            ]
        },
    )
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "8 Robinsons Road, Frankston South"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_vicmap_no_match_and_fallback_down_is_not_found(
    hass: HomeAssistant, aioclient_mock, zones
):
    """A geocode.earth outage mustn't hide Vicmap's 'no such address'."""
    aioclient_mock.get(ZONES_URL, json=zones)
    aioclient_mock.get(VICMAP_GEOCODER_URL, json={"candidates": []})
    aioclient_mock.get(GEOCODE_EARTH_URL, status=503)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "99 Nowhere Street"}
    )
    assert result["errors"] == {CONF_ADDRESS: "address_not_found"}


async def test_both_geocoders_down_is_cannot_connect(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(VICMAP_GEOCODER_URL, status=503)
    aioclient_mock.get(GEOCODE_EARTH_URL, status=503)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "8 Robinsons Road"}
    )
    assert result["errors"] == {"base": "cannot_connect"}
