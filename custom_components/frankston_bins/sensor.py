"""Sensors for Frankston Bins."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import UPCOMING_DAYS
from .coordinator import BinsData, FrankstonBinsConfigEntry, FrankstonBinsCoordinator
from .entity import (
    FrankstonBinsEntity,
    bin_details,
    bin_picture,
    join_names,
    relative_day,
)
from .schedule import BIN_TYPES, BinType


@dataclass(frozen=True, kw_only=True)
class BinsSensorDescription(SensorEntityDescription):
    value_fn: Callable[[BinsData], date | int | str | None]
    attributes_fn: Callable[[BinsData], dict[str, Any]] | None = None


def _summary(data: BinsData) -> str:
    collection = data.next_collection
    when = relative_day(collection.date, data.days_until(collection.date))
    return f"{when}: {join_names(collection.bin_names)}"


def _next_collection_attributes(data: BinsData) -> dict[str, Any]:
    collection = data.next_collection
    return {
        "bins": collection.bin_names,
        "bin_keys": collection.bin_keys,
        "days_until": data.days_until(collection.date),
        "summary": _summary(data),
        "area": data.zone.area,
        "collection_day": data.zone.collection_weekday,
        "bin_details": bin_details(data),
        "upcoming": [{"date": c.date.isoformat(), "bins": c.bin_keys} for c in data.upcoming[:9]],
    }


SENSORS: tuple[BinsSensorDescription, ...] = (
    BinsSensorDescription(
        key="next_collection",
        translation_key="next_collection",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:calendar-clock",
        value_fn=lambda data: data.next_collection.date,
        attributes_fn=_next_collection_attributes,
    ),
    BinsSensorDescription(
        key="bins_to_put_out",
        translation_key="bins_to_put_out",
        icon="mdi:delete-empty",
        value_fn=lambda data: ", ".join(data.next_collection.bin_names),
        attributes_fn=lambda data: {
            "bins": data.next_collection.bin_names,
            "bin_keys": data.next_collection.bin_keys,
            "collection_date": data.next_collection.date.isoformat(),
        },
    ),
    BinsSensorDescription(
        key="summary",
        translation_key="summary",
        icon="mdi:text-box-outline",
        value_fn=_summary,
    ),
    BinsSensorDescription(
        key="days_until_collection",
        translation_key="days_until_collection",
        icon="mdi:calendar-arrow-right",
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=lambda data: data.days_until(data.next_collection.date),
    ),
    BinsSensorDescription(
        key="collection_zone",
        translation_key="collection_zone",
        icon="mdi:map-marker-radius",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: f"{data.zone.area} ({data.zone.collection_weekday})",
        attributes_fn=lambda data: {
            "area": data.zone.area,
            "collection_day": data.zone.collection_weekday,
            **{
                f"{key}_start": schedule.start.isoformat()
                for key, schedule in data.zone.schedules.items()
            },
            **{
                f"{key}_every_weeks": schedule.interval_weeks
                for key, schedule in data.zone.schedules.items()
            },
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FrankstonBinsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [BinsSensor(coordinator, description) for description in SENSORS]
    entities.extend(
        BinDateSensor(coordinator, bin_type)
        for bin_type in BIN_TYPES
        if bin_type.key in coordinator.data.zone.schedules
    )
    async_add_entities(entities)


class BinsSensor(FrankstonBinsEntity, SensorEntity):
    """A sensor describing the next collection."""

    entity_description: BinsSensorDescription

    def __init__(
        self, coordinator: FrankstonBinsCoordinator, description: BinsSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> date | int | str | None:
        return self.entity_description.value_fn(self.bins_data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.bins_data)


class BinDateSensor(FrankstonBinsEntity, SensorEntity):
    """The next collection date for one bin."""

    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator: FrankstonBinsCoordinator, bin_type: BinType) -> None:
        super().__init__(coordinator, bin_type.key)
        self.bin_type = bin_type
        self._attr_translation_key = bin_type.key
        self._attr_icon = bin_type.icon

    @property
    def _schedule(self):
        return self.bins_data.zone.schedules[self.bin_type.key]

    @property
    def available(self) -> bool:
        return super().available and self.bin_type.key in self.bins_data.zone.schedules

    @property
    def native_value(self) -> date:
        return self._schedule.next_date(self.bins_data.reference_date)

    @property
    def entity_picture(self) -> str:
        return bin_picture(self.bin_type, self._going_out)

    @property
    def _going_out(self) -> bool:
        return self.bin_type.key in self.bins_data.next_collection.bin_keys

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.bins_data
        schedule = self._schedule
        next_date = self.native_value
        return {
            "days_until": data.days_until(next_date),
            "going_out_next_collection": self._going_out,
            "every_weeks": schedule.interval_weeks,
            "collection_day": schedule.weekday,
            "lid_colour": self.bin_type.lid,
            "colour": self.bin_type.colour,
            "upcoming": [
                day.isoformat()
                for day in schedule.dates_between(
                    data.reference_date, data.reference_date + timedelta(days=UPCOMING_DAYS)
                )
            ],
        }
