"""Binary sensors for Frankston Bins."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import FrankstonBinsConfigEntry, FrankstonBinsCoordinator
from .entity import FrankstonBinsEntity, bin_picture, join_names
from .schedule import BIN_TYPES, BinType


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FrankstonBinsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [BinNightSensor(coordinator)]
    entities.extend(
        BinGoingOutSensor(coordinator, bin_type)
        for bin_type in BIN_TYPES
        if bin_type.key in coordinator.data.zone.schedules
    )
    async_add_entities(entities)


class BinNightSensor(FrankstonBinsEntity, BinarySensorEntity):
    """On when the bins need to go out tonight (or are being collected today)."""

    _attr_translation_key = "bin_night"

    def __init__(self, coordinator: FrankstonBinsCoordinator) -> None:
        super().__init__(coordinator, "bin_night")

    @property
    def is_on(self) -> bool:
        data = self.bins_data
        return data.days_until(data.next_collection.date) <= 1

    @property
    def icon(self) -> str:
        return "mdi:delete-alert" if self.is_on else "mdi:delete-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        collection = self.bins_data.next_collection
        return {
            "collection_date": collection.date.isoformat(),
            "bins": collection.bin_names,
            "message": f"Put out the {join_names(collection.bin_names)} bins",
        }


class BinGoingOutSensor(FrankstonBinsEntity, BinarySensorEntity):
    """On when this bin is collected on the next collection day."""

    def __init__(self, coordinator: FrankstonBinsCoordinator, bin_type: BinType) -> None:
        super().__init__(coordinator, f"{bin_type.key}_going_out")
        self.bin_type = bin_type
        self._attr_translation_key = f"{bin_type.key}_going_out"
        self._attr_icon = bin_type.icon

    @property
    def is_on(self) -> bool:
        return self.bin_type.key in self.bins_data.next_collection.bin_keys

    @property
    def entity_picture(self) -> str:
        return bin_picture(self.bin_type, self.is_on)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "collection_date": self.bins_data.next_collection.date.isoformat(),
            "lid_colour": self.bin_type.lid,
            "colour": self.bin_type.colour,
        }
