"""Frankston City Council bin collections for Home Assistant."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType

from .const import CARD_FILENAME, DOMAIN, STATIC_URL, VERSION
from .coordinator import FrankstonBinsConfigEntry, FrankstonBinsCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the bin images and the dashboard card."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "www"), True)]
    )
    add_extra_js_url(hass, f"{STATIC_URL}/{CARD_FILENAME}?v={VERSION}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FrankstonBinsConfigEntry) -> bool:
    """Set up a property from a config entry."""
    coordinator = FrankstonBinsCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    @callback
    def _recalculate(_now) -> None:
        coordinator.recalculate()

    # Dates only change at midnight and at the rollover time on collection day.
    rollover = coordinator.rollover
    entry.async_on_unload(async_track_time_change(hass, _recalculate, hour=0, minute=0, second=1))
    entry.async_on_unload(
        async_track_time_change(
            hass,
            _recalculate,
            hour=rollover.hour,
            minute=rollover.minute,
            second=rollover.second,
        )
    )
    options = dict(entry.options)

    async def _async_entry_updated(hass: HomeAssistant, entry: FrankstonBinsConfigEntry) -> None:
        # The coordinator also updates the entry when the zone data changes;
        # only an options change needs a reload.
        if dict(entry.options) != options:
            await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FrankstonBinsConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
