"""Calendar of upcoming bin collections."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import FrankstonBinsConfigEntry, FrankstonBinsCoordinator
from .entity import FrankstonBinsEntity, join_names
from .schedule import Collection


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FrankstonBinsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([BinsCalendar(entry.runtime_data)])


def _event(collection: Collection) -> CalendarEvent:
    return CalendarEvent(
        start=collection.date,
        end=collection.date + timedelta(days=1),
        summary=f"Bins: {join_names(collection.bin_names)}",
        description="Put bins out the night before, or by 6am on collection day.",
    )


class BinsCalendar(FrankstonBinsEntity, CalendarEntity):
    """All-day events for every collection day."""

    _attr_translation_key = "collections"
    _attr_icon = "mdi:delete-variant"

    def __init__(self, coordinator: FrankstonBinsCoordinator) -> None:
        super().__init__(coordinator, "calendar")

    @property
    def event(self) -> CalendarEvent | None:
        return _event(self.bins_data.next_collection)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        start: date = dt_util.as_local(start_date).date()
        # end_date is exclusive; an all-day event on that date isn't included.
        end: date = dt_util.as_local(end_date - timedelta(microseconds=1)).date()
        return [
            _event(collection) for collection in self.bins_data.zone.collections_between(start, end)
        ]
