"""Bin collection date maths for Frankston City Council.

Frankston publishes one GeoJSON polygon per collection zone (via Pozi). Each
zone's properties describe every bin stream as an anchor date plus a repeat
interval, e.g. ``rec_start: 2012-01-04`` / ``rec_weeks: 2``. A bin is collected
on any date that is a whole number of intervals away from its anchor date.

This mirrors the "garbage" transformer used by frankston.pozi.com, the
council's own bin-day lookup. This module has no Home Assistant dependencies
so it can be unit tested on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any


@dataclass(frozen=True)
class BinType:
    """A kerbside bin stream."""

    key: str
    code: str  # Prefix used in the council's zone data
    name: str
    lid: str  # Lid colour, as the council describes it
    colour: str  # Hex colour used for the dashboard visuals
    icon: str


BIN_TYPES: tuple[BinType, ...] = (
    BinType("general_waste", "rub", "General Waste", "red", "#e0362c", "mdi:trash-can"),
    BinType("recycling", "rec", "Mixed Recycling", "yellow", "#f5c400", "mdi:recycle"),
    BinType("fogo", "grn", "Food & Garden Organics", "light green", "#5cb85c", "mdi:leaf"),
    BinType("glass", "gls", "Glass Recycling", "purple", "#7b3fa0", "mdi:bottle-wine"),
)
BIN_TYPES_BY_KEY = {bin_type.key: bin_type for bin_type in BIN_TYPES}


class ZoneDataError(ValueError):
    """Raised when a zone is missing or has malformed schedule data."""


@dataclass(frozen=True)
class BinSchedule:
    """A repeating collection schedule for one bin."""

    bin: BinType
    start: date
    interval_weeks: int

    @property
    def period_days(self) -> int:
        return self.interval_weeks * 7

    @property
    def weekday(self) -> str:
        return self.start.strftime("%A")

    def next_date(self, on_or_after: date) -> date:
        """Return the first collection on or after the given date."""
        if on_or_after <= self.start:
            return self.start
        remainder = (on_or_after - self.start).days % self.period_days
        if remainder == 0:
            return on_or_after
        return on_or_after + timedelta(days=self.period_days - remainder)

    def dates_between(self, start: date, end: date) -> list[date]:
        """Return every collection date in the inclusive range."""
        dates = []
        current = self.next_date(start)
        while current <= end:
            dates.append(current)
            current += timedelta(days=self.period_days)
        return dates

    def is_collected_on(self, day: date) -> bool:
        return self.next_date(day) == day


@dataclass(frozen=True)
class Collection:
    """All bins collected on a single day."""

    date: date
    bins: tuple[BinType, ...]

    @property
    def bin_keys(self) -> list[str]:
        return [bin_type.key for bin_type in self.bins]

    @property
    def bin_names(self) -> list[str]:
        return [bin_type.name for bin_type in self.bins]


@dataclass(frozen=True)
class Zone:
    """A collection zone and the schedules that apply within it."""

    area: str
    schedules: dict[str, BinSchedule]

    @classmethod
    def from_properties(cls, properties: dict[str, Any]) -> Zone:
        """Build a zone from the council's GeoJSON feature properties."""
        schedules = {}
        for bin_type in BIN_TYPES:
            start = properties.get(f"{bin_type.code}_start")
            weeks = properties.get(f"{bin_type.code}_weeks")
            if not start or not weeks:
                # Not every property gets every service (e.g. no glass bin).
                continue
            try:
                schedule = BinSchedule(
                    bin=bin_type,
                    start=date.fromisoformat(str(start)[:10]),
                    interval_weeks=int(float(weeks)),
                )
            except ValueError as err:
                raise ZoneDataError(
                    f"Invalid {bin_type.name} schedule: {start!r} every {weeks!r} weeks"
                ) from err
            if schedule.interval_weeks < 1:
                raise ZoneDataError(f"Invalid {bin_type.name} interval: {weeks!r}")
            schedules[bin_type.key] = schedule
        if not schedules:
            raise ZoneDataError("Zone has no bin schedules")
        return cls(area=str(properties.get("area") or "Unknown"), schedules=schedules)

    @property
    def collection_weekday(self) -> str:
        """The weekday of the weekly general waste collection."""
        schedule = self.schedules.get("general_waste") or next(iter(self.schedules.values()))
        return schedule.weekday

    def collection_on(self, day: date) -> Collection | None:
        bins = tuple(
            schedule.bin for schedule in self.schedules.values() if schedule.is_collected_on(day)
        )
        return Collection(day, bins) if bins else None

    def collections_between(self, start: date, end: date) -> list[Collection]:
        """Return every collection day in the inclusive range, in order."""
        days: dict[date, list[BinType]] = {}
        for schedule in self.schedules.values():
            for day in schedule.dates_between(start, end):
                days.setdefault(day, []).append(schedule.bin)
        order = {bin_type.key: index for index, bin_type in enumerate(BIN_TYPES)}
        return [
            Collection(day, tuple(sorted(bins, key=lambda b: order[b.key])))
            for day, bins in sorted(days.items())
        ]

    def next_collection(self, on_or_after: date) -> Collection:
        """Return the next collection day on or after the given date."""
        first = min(s.next_date(on_or_after) for s in self.schedules.values())
        collection = self.collection_on(first)
        assert collection is not None
        return collection


def reference_date(now: datetime, rollover: time) -> date:
    """Return the date from which upcoming collections should be counted.

    On collection day the trucks have usually been by mid-morning, so after
    the rollover time we stop showing today's collection and move on to the
    next one.
    """
    today = now.date()
    if now.time() >= rollover:
        return today + timedelta(days=1)
    return today


def point_in_geometry(lon: float, lat: float, geometry: dict[str, Any]) -> bool:
    """Return True if a point lies within a GeoJSON Polygon or MultiPolygon."""
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if geometry_type == "Polygon":
        polygons = [coordinates]
    elif geometry_type == "MultiPolygon":
        polygons = coordinates
    else:
        return False
    return any(_point_in_polygon(lon, lat, polygon) for polygon in polygons)


def _point_in_polygon(x: float, y: float, rings: list[list[list[float]]]) -> bool:
    """Even-odd test against an outer ring, excluding any holes."""
    if not rings or not _point_in_ring(x, y, rings[0]):
        return False
    return not any(_point_in_ring(x, y, hole) for hole in rings[1:])


def _point_in_ring(x: float, y: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def find_zone_properties(geojson: dict[str, Any], lat: float, lon: float) -> dict[str, Any] | None:
    """Return the properties of the zone containing the point, if any."""
    for feature in geojson.get("features") or []:
        if point_in_geometry(lon, lat, feature.get("geometry") or {}):
            return dict(feature.get("properties") or {})
    return None
