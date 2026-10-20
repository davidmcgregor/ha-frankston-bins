"""Client for the public services behind Frankston's bin day lookup."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any

import aiohttp

from .const import (
    GEOCODE_EARTH_BOUNDARY,
    GEOCODE_EARTH_KEY,
    GEOCODE_EARTH_URL,
    VICMAP_GEOCODER_URL,
    ZONES_URL,
)
from .schedule import find_zone_properties

_LOGGER = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=30)
MIN_VICMAP_SCORE = 80


class FrankstonBinsError(Exception):
    """Raised when the council data cannot be retrieved."""


@dataclass(frozen=True)
class AddressMatch:
    """A geocoded address."""

    address: str
    latitude: float
    longitude: float


class FrankstonBinsApi:
    """Talks to the Pozi zone file and the address geocoders."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        try:
            async with self._session.get(url, params=params, timeout=TIMEOUT) as resp:
                resp.raise_for_status()
                # connect.pozi.com doesn't always send an application/json type.
                return json.loads(await resp.read())
        except (TimeoutError, aiohttp.ClientError, ValueError) as err:
            raise FrankstonBinsError(f"Error fetching {url}: {err}") from err

    async def async_get_zones(self) -> dict[str, Any]:
        """Download the council's collection zone polygons."""
        data = await self._get_json(ZONES_URL)
        if not isinstance(data, dict) or not data.get("features"):
            raise FrankstonBinsError("Collection zone data was empty")
        return data

    async def async_get_zone_properties(
        self, latitude: float, longitude: float
    ) -> dict[str, Any] | None:
        """Return the schedule properties for the zone containing a point."""
        return find_zone_properties(await self.async_get_zones(), latitude, longitude)

    async def async_search_address(self, query: str) -> list[AddressMatch]:
        """Geocode an address, preferring the official Vicmap geocoder."""
        try:
            matches = await self._search_vicmap(query)
        except FrankstonBinsError as err:
            _LOGGER.debug("Vicmap geocoder failed, trying geocode.earth: %s", err)
            matches = []
        if not matches:
            matches = await self._search_geocode_earth(query)
        return matches

    async def _search_vicmap(self, query: str) -> list[AddressMatch]:
        data = await self._get_json(
            VICMAP_GEOCODER_URL,
            {"SingleLine": query, "f": "json", "outSR": "4326", "maxLocations": "10"},
        )
        if not isinstance(data, dict):
            raise FrankstonBinsError("Unexpected response from the Vicmap geocoder")
        matches = []
        for candidate in data.get("candidates") or []:
            try:
                if float(candidate.get("score") or 0) < MIN_VICMAP_SCORE:
                    continue
                matches.append(
                    AddressMatch(
                        address=_title_case(candidate["address"]),
                        latitude=float(candidate["location"]["y"]),
                        longitude=float(candidate["location"]["x"]),
                    )
                )
            except (AttributeError, KeyError, TypeError, ValueError):
                _LOGGER.debug("Skipping malformed Vicmap candidate: %s", candidate)
        return matches

    async def _search_geocode_earth(self, query: str) -> list[AddressMatch]:
        data = await self._get_json(
            GEOCODE_EARTH_URL,
            {
                "text": query,
                "layers": "address",
                "boundary.gid": GEOCODE_EARTH_BOUNDARY,
                "api_key": GEOCODE_EARTH_KEY,
                "size": "10",
            },
        )
        if not isinstance(data, dict):
            raise FrankstonBinsError("Unexpected response from geocode.earth")
        matches = []
        for feature in data.get("features") or []:
            try:
                longitude, latitude = feature["geometry"]["coordinates"][:2]
                properties = feature.get("properties") or {}
                matches.append(
                    AddressMatch(
                        address=properties.get("label") or properties.get("name") or query,
                        latitude=float(latitude),
                        longitude=float(longitude),
                    )
                )
            except (AttributeError, KeyError, TypeError, ValueError):
                _LOGGER.debug("Skipping malformed geocode.earth feature: %s", feature)
        return matches


def _title_case(address: str) -> str:
    """Turn Vicmap's '8 ROBINSONS ROAD FRANKSTON SOUTH 3199' into title case."""
    return " ".join(word.capitalize() for word in address.split())
