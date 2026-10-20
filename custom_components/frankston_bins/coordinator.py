"""Data coordinator for Frankston Bins."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import FrankstonBinsApi, FrankstonBinsError
from .const import (
    CONF_ROLLOVER,
    DEFAULT_ROLLOVER,
    DOMAIN,
    UPCOMING_DAYS,
    UPDATE_INTERVAL,
    ZONE_REFRESH_INTERVAL,
)
from .schedule import Collection, Zone, ZoneDataError, reference_date

_LOGGER = logging.getLogger(__name__)

CONF_ZONE = "zone"

type FrankstonBinsConfigEntry = ConfigEntry[FrankstonBinsCoordinator]


@dataclass(frozen=True)
class BinsData:
    """Everything the entities need, calculated for the current moment."""

    zone: Zone
    reference_date: date
    next_collection: Collection
    upcoming: list[Collection]

    def next_date_for(self, bin_key: str) -> date | None:
        schedule = self.zone.schedules.get(bin_key)
        return schedule.next_date(self.reference_date) if schedule else None

    def days_until(self, day: date) -> int:
        return (day - dt_util.now().date()).days


class FrankstonBinsCoordinator(DataUpdateCoordinator[BinsData]):
    """Keeps the zone data fresh and recalculates collection dates."""

    config_entry: FrankstonBinsConfigEntry

    def __init__(self, hass: HomeAssistant, entry: FrankstonBinsConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.api = FrankstonBinsApi(async_get_clientsession(hass))
        self._zone_properties: dict[str, Any] | None = entry.data.get(CONF_ZONE)
        self._zone_fetched: datetime | None = None

    @property
    def rollover(self) -> time:
        value = self.config_entry.options.get(CONF_ROLLOVER, DEFAULT_ROLLOVER)
        return dt_util.parse_time(value) or time(12)

    async def _async_refresh_zone(self) -> None:
        """Re-download the zone data in case the council changes the schedule."""
        entry = self.config_entry
        try:
            properties = await self.api.async_get_zone_properties(
                entry.data[CONF_LATITUDE], entry.data[CONF_LONGITUDE]
            )
        except FrankstonBinsError as err:
            if self._zone_properties is None:
                raise UpdateFailed(str(err)) from err
            _LOGGER.warning("Using cached collection zone, refresh failed: %s", err)
            return
        self._zone_fetched = dt_util.utcnow()
        if properties is None:
            if self._zone_properties is None:
                raise UpdateFailed("Address is not inside a Frankston collection zone")
            _LOGGER.warning("Address no longer matches a zone; using cached zone")
            return
        if properties != self._zone_properties:
            _LOGGER.info("Collection zone updated: %s", properties)
            self._zone_properties = properties
            self.hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_ZONE: properties}
            )

    async def _async_update_data(self) -> BinsData:
        if (
            self._zone_properties is None
            or self._zone_fetched is None
            or dt_util.utcnow() - self._zone_fetched >= ZONE_REFRESH_INTERVAL
        ):
            await self._async_refresh_zone()
        assert self._zone_properties is not None
        try:
            zone = Zone.from_properties(self._zone_properties)
        except ZoneDataError as err:
            raise UpdateFailed(f"Invalid collection zone data: {err}") from err
        return self.calculate(zone)

    def calculate(self, zone: Zone) -> BinsData:
        ref = reference_date(dt_util.now(), self.rollover)
        return BinsData(
            zone=zone,
            reference_date=ref,
            next_collection=zone.next_collection(ref),
            upcoming=zone.collections_between(ref, ref + timedelta(days=UPCOMING_DAYS)),
        )

    def recalculate(self) -> None:
        """Recompute dates without hitting the network (e.g. at midnight)."""
        if self.data is not None:
            self.async_set_updated_data(self.calculate(self.data.zone))
