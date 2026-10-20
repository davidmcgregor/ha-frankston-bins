"""Tests for the entities, calendar and dashboard card registration."""

from __future__ import annotations

from datetime import datetime

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.frankston_bins.const import CONF_ADDRESS, DOMAIN, ZONES_URL

from .conftest import EXAMPLE_ADDRESS

PREFIX = "frankston_bins"


@pytest.fixture
async def setup_entry(hass: HomeAssistant, freezer: FrozenDateTimeFactory, example_zone):
    """Set up 8 Robinsons Road on Tuesday 20 October 2026, 7pm Melbourne time."""
    await hass.config.async_set_time_zone("Australia/Melbourne")
    freezer.move_to(
        datetime(2026, 10, 20, 19, 0, tzinfo=dt_util.get_time_zone("Australia/Melbourne"))
    )

    async def _setup(zone=example_zone) -> MockConfigEntry:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=EXAMPLE_ADDRESS["address"],
            data={
                CONF_ADDRESS: EXAMPLE_ADDRESS["address"],
                CONF_LATITUDE: EXAMPLE_ADDRESS["latitude"],
                CONF_LONGITUDE: EXAMPLE_ADDRESS["longitude"],
                "zone": zone,
            },
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry

    return _setup


async def test_entities_on_bin_night(hass: HomeAssistant, mock_services, setup_entry):
    entry = await setup_entry()
    assert entry.state is ConfigEntryState.LOADED

    next_collection = hass.states.get(f"sensor.{PREFIX}_next_collection")
    assert next_collection.state == "2026-10-21"
    assert next_collection.attributes["bins"] == ["General Waste", "Mixed Recycling"]
    assert next_collection.attributes["days_until"] == 1
    assert next_collection.attributes["area"] == "Area 3"
    assert next_collection.attributes["collection_day"] == "Wednesday"
    details = {d["key"]: d for d in next_collection.attributes["bin_details"]}
    assert details["glass"]["next_date"] == "2026-11-11"
    assert details["glass"]["days_until"] == 22
    assert details["recycling"]["going_out"] is True
    assert details["fogo"]["going_out"] is False

    assert (
        hass.states.get(f"sensor.{PREFIX}_bins_to_put_out").state
        == "General Waste, Mixed Recycling"
    )
    assert (
        hass.states.get(f"sensor.{PREFIX}_summary").state
        == "Tomorrow: General Waste and Mixed Recycling"
    )
    assert hass.states.get(f"sensor.{PREFIX}_days_until_collection").state == "1"
    assert hass.states.get(f"sensor.{PREFIX}_collection_zone").state == "Area 3 (Wednesday)"

    assert hass.states.get(f"sensor.{PREFIX}_general_waste").state == "2026-10-21"
    assert hass.states.get(f"sensor.{PREFIX}_recycling").state == "2026-10-21"
    assert hass.states.get(f"sensor.{PREFIX}_fogo").state == "2026-10-28"
    glass = hass.states.get(f"sensor.{PREFIX}_glass")
    assert glass.state == "2026-11-11"
    assert glass.attributes["entity_picture"] == "/frankston_bins_static/glass-off.svg"
    assert glass.attributes["upcoming"][:2] == ["2026-11-11", "2026-12-09"]

    assert hass.states.get(f"binary_sensor.{PREFIX}_bin_night").state == STATE_ON
    recycling_out = hass.states.get(f"binary_sensor.{PREFIX}_recycling_going_out")
    assert recycling_out.state == STATE_ON
    assert recycling_out.attributes["entity_picture"] == "/frankston_bins_static/recycling.svg"
    assert hass.states.get(f"binary_sensor.{PREFIX}_general_waste_going_out").state == STATE_ON
    assert hass.states.get(f"binary_sensor.{PREFIX}_fogo_going_out").state == STATE_OFF
    assert hass.states.get(f"binary_sensor.{PREFIX}_glass_going_out").state == STATE_OFF

    calendar = hass.states.get(f"calendar.{PREFIX}_collections")
    assert calendar.attributes["message"] == "Bins: General Waste and Mixed Recycling"


async def test_rolls_over_after_collection(
    hass: HomeAssistant, mock_services, setup_entry, freezer: FrozenDateTimeFactory
):
    await setup_entry()

    # Collection morning: still showing today's collection.
    freezer.move_to(dt_util.parse_datetime("2026-10-21T08:00:00+11:00"))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert (
        hass.states.get(f"sensor.{PREFIX}_summary").state
        == "Today: General Waste and Mixed Recycling"
    )
    assert hass.states.get(f"binary_sensor.{PREFIX}_bin_night").state == STATE_ON

    # After midday it moves on to next week's FOGO collection.
    freezer.move_to(dt_util.parse_datetime("2026-10-21T12:00:01+11:00"))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(f"sensor.{PREFIX}_next_collection").state == "2026-10-28"
    assert (
        hass.states.get(f"sensor.{PREFIX}_summary").state
        == "Wed 28 Oct: General Waste and Food & Garden Organics"
    )
    assert hass.states.get(f"sensor.{PREFIX}_days_until_collection").state == "7"
    assert hass.states.get(f"binary_sensor.{PREFIX}_bin_night").state == STATE_OFF
    assert hass.states.get(f"binary_sensor.{PREFIX}_fogo_going_out").state == STATE_ON
    assert hass.states.get(f"binary_sensor.{PREFIX}_recycling_going_out").state == STATE_OFF


async def test_glass_week(hass: HomeAssistant, mock_services, setup_entry, freezer):
    await setup_entry()
    freezer.move_to(dt_util.parse_datetime("2026-11-10T18:00:00+11:00"))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert (
        hass.states.get(f"sensor.{PREFIX}_bins_to_put_out").state
        == "General Waste, Food & Garden Organics, Glass Recycling"
    )
    assert hass.states.get(f"binary_sensor.{PREFIX}_glass_going_out").state == STATE_ON


async def test_calendar_events(hass: HomeAssistant, mock_services, setup_entry, hass_client):
    await setup_entry()
    client = await hass_client()
    response = await client.get(
        f"/api/calendars/calendar.{PREFIX}_collections"
        "?start=2026-10-31T13:00:00Z&end=2026-11-18T13:00:00Z"
    )
    assert response.status == 200
    events = await response.json()
    assert [(e["start"]["date"], e["summary"]) for e in events] == [
        ("2026-11-04", "Bins: General Waste and Mixed Recycling"),
        ("2026-11-11", "Bins: General Waste, Food & Garden Organics and Glass Recycling"),
        ("2026-11-18", "Bins: General Waste and Mixed Recycling"),
    ]


async def test_uses_cached_zone_when_offline(hass: HomeAssistant, aioclient_mock, setup_entry):
    aioclient_mock.get(ZONES_URL, status=503)
    entry = await setup_entry()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(f"sensor.{PREFIX}_next_collection").state == "2026-10-21"


async def test_zone_changes_are_saved(
    hass: HomeAssistant, aioclient_mock, zones, setup_entry, example_zone
):
    # The council moves Area 3's glass cycle by a week.
    for feature in zones["features"]:
        if feature["properties"] == example_zone:
            feature["properties"] = {**example_zone, "gls_start": "2025-03-12"}
    aioclient_mock.get(ZONES_URL, json=zones)
    entry = await setup_entry()
    assert entry.data["zone"]["gls_start"] == "2025-03-12"
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(f"sensor.{PREFIX}_glass").state == "2026-10-21"


async def test_fails_without_zone(hass: HomeAssistant, aioclient_mock, setup_entry):
    aioclient_mock.get(ZONES_URL, status=503)
    entry = await setup_entry(zone=None)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_card_is_served(hass: HomeAssistant, mock_services, setup_entry, hass_client):
    await setup_entry()
    client = await hass_client()
    for path in ("frankston-bins-card.js", "glass.svg", "fogo-off.svg"):
        response = await client.get(f"/frankston_bins_static/{path}")
        assert response.status == 200, path


async def test_unload(hass: HomeAssistant, mock_services, setup_entry):
    entry = await setup_entry()
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
