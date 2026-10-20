"""Base entity for Frankston Bins."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ADDRESS, DOMAIN, LOOKUP_URL, STATIC_URL
from .coordinator import BinsData, FrankstonBinsCoordinator
from .schedule import BIN_TYPES, BinType


class FrankstonBinsEntity(CoordinatorEntity[FrankstonBinsCoordinator]):
    """An entity belonging to one property's bin service."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FrankstonBinsCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        zone = coordinator.data.zone
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Frankston Bins",
            manufacturer="Frankston City Council",
            model=f"{zone.area}, {zone.collection_weekday} collection",
            model_id=entry.data[CONF_ADDRESS],
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=LOOKUP_URL,
        )

    @property
    def bins_data(self) -> BinsData:
        return self.coordinator.data


def bin_picture(bin_type: BinType, active: bool = True) -> str:
    suffix = "" if active else "-off"
    return f"{STATIC_URL}/{bin_type.key}{suffix}.svg"


def bin_details(data: BinsData) -> list[dict[str, Any]]:
    """Per-bin details, used by the dashboard card."""
    going_out = set(data.next_collection.bin_keys)
    details = []
    for bin_type in BIN_TYPES:
        schedule = data.zone.schedules.get(bin_type.key)
        if schedule is None:
            continue
        next_date = schedule.next_date(data.reference_date)
        details.append(
            {
                "key": bin_type.key,
                "name": bin_type.name,
                "lid": bin_type.lid,
                "colour": bin_type.colour,
                "icon": bin_type.icon,
                "next_date": next_date.isoformat(),
                "days_until": data.days_until(next_date),
                "going_out": bin_type.key in going_out,
                "every_weeks": schedule.interval_weeks,
            }
        )
    return details


def join_names(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


def relative_day(day: date, days_until: int) -> str:
    if days_until == 0:
        return "Today"
    if days_until == 1:
        return "Tomorrow"
    if 1 < days_until < 7:
        return day.strftime("%A")
    return f"{day.strftime('%a')} {day.day} {day.strftime('%b')}"
