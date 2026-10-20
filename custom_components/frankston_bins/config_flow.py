"""Config flow for Frankston Bins."""

from __future__ import annotations

import logging
import math
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TimeSelector,
)
import voluptuous as vol

from .api import AddressMatch, FrankstonBinsApi, FrankstonBinsError
from .const import CONF_ADDRESS, CONF_ROLLOVER, DEFAULT_ROLLOVER, DOMAIN, LOOKUP_URL
from .coordinator import CONF_ZONE
from .schedule import Zone, ZoneDataError, find_zone_properties

_LOGGER = logging.getLogger(__name__)

CONF_MATCH = "match"
DUPLICATE_DISTANCE_M = 30


class FrankstonBinsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Find a property's collection zone from its address."""

    VERSION = 1

    def __init__(self) -> None:
        self._matches: list[tuple[AddressMatch, dict[str, Any]]] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> FrankstonBinsOptionsFlow:
        return FrankstonBinsOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            query = user_input.get(CONF_ADDRESS, "").strip()
            api = FrankstonBinsApi(async_get_clientsession(self.hass))
            try:
                if query:
                    candidates = await api.async_search_address(query)
                else:
                    candidates = [
                        AddressMatch(
                            self.hass.config.location_name,
                            self.hass.config.latitude,
                            self.hass.config.longitude,
                        )
                    ]
                zones = await api.async_get_zones() if candidates else {}
            except FrankstonBinsError as err:
                _LOGGER.warning("Error looking up address: %s", err)
                errors["base"] = "cannot_connect"
            else:
                self._matches = _unique_matches(candidates, zones)
                if not candidates:
                    errors[CONF_ADDRESS] = "address_not_found"
                elif not self._matches:
                    errors[CONF_ADDRESS] = "outside_frankston"
                elif len(self._matches) == 1:
                    return await self._async_create(*self._matches[0])
                else:
                    return await self.async_step_pick()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Optional(CONF_ADDRESS): TextSelector()}), user_input
            ),
            errors=errors,
            description_placeholders={"lookup_url": LOOKUP_URL},
        )

    async def async_step_pick(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose between several matching addresses."""
        if user_input is not None:
            return await self._async_create(*self._matches[int(user_input[CONF_MATCH])])

        options = [
            SelectOptionDict(value=str(index), label=match.address)
            for index, (match, _) in enumerate(self._matches)
        ]
        return self.async_show_form(
            step_id="pick",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MATCH): SelectSelector(
                        SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST)
                    )
                }
            ),
        )

    async def _async_create(self, match: AddressMatch, zone: dict[str, Any]) -> ConfigFlowResult:
        await self.async_set_unique_id(f"{match.latitude:.5f},{match.longitude:.5f}")
        self._abort_if_unique_id_configured()
        # The two geocoders can place the same address a few metres apart.
        for entry in self._async_current_entries(include_ignore=False):
            if (
                CONF_LATITUDE in entry.data
                and _distance_m(
                    match.latitude,
                    match.longitude,
                    entry.data[CONF_LATITUDE],
                    entry.data[CONF_LONGITUDE],
                )
                <= DUPLICATE_DISTANCE_M
            ):
                return self.async_abort(reason="already_configured")
        return self.async_create_entry(
            title=match.address,
            data={
                CONF_ADDRESS: match.address,
                CONF_LATITUDE: match.latitude,
                CONF_LONGITUDE: match.longitude,
                CONF_ZONE: zone,
            },
        )


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance in metres; plenty accurate over a few hundred metres."""
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return math.hypot(x, y) * 6_371_000


def _unique_matches(
    candidates: list[AddressMatch], zones: dict[str, Any]
) -> list[tuple[AddressMatch, dict[str, Any]]]:
    """Keep candidates that fall inside a valid Frankston collection zone."""
    matches = []
    seen = set()
    for candidate in candidates:
        if candidate.address.lower() in seen:
            continue
        properties = find_zone_properties(zones, candidate.latitude, candidate.longitude)
        if properties is None:
            continue
        try:
            Zone.from_properties(properties)
        except ZoneDataError:
            continue
        seen.add(candidate.address.lower())
        matches.append((candidate, properties))
    return matches


class FrankstonBinsOptionsFlow(OptionsFlow):
    """Change when today's collection rolls over to the next one."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ROLLOVER,
                        default=self.config_entry.options.get(CONF_ROLLOVER, DEFAULT_ROLLOVER),
                    ): TimeSelector(),
                }
            ),
        )
