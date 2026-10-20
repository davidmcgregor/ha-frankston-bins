"""Constants for the Frankston Bins integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "frankston_bins"

CONF_ADDRESS: Final = "address"
CONF_ROLLOVER: Final = "rollover_time"
DEFAULT_ROLLOVER: Final = "12:00:00"

# Collection zones published by the council through Pozi. This is the same
# file frankston.pozi.com (linked from the council's bin collections page)
# uses to answer "when is my bin day?".
ZONES_URL: Final = (
    "https://connect.pozi.com/userdata/frankston-publisher/Community/"
    "Kerbside_Garbage_Collection_(Widget).json"
)

# Vicmap (Victorian Government) address geocoder, also used by frankston.pozi.com.
VICMAP_GEOCODER_URL: Final = (
    "https://corp-geo.mapshare.vic.gov.au/arcgis/rest/services/Geocoder/"
    "VMAddressEZIAdd/GeocodeServer/findAddressCandidates"
)
# Fallback geocoder, with the public key frankston.pozi.com uses, limited to
# the Frankston local government area.
GEOCODE_EARTH_URL: Final = "https://api.geocode.earth/v1/search"
GEOCODE_EARTH_KEY: Final = "ge-39bfbedc55be11c0"
GEOCODE_EARTH_BOUNDARY: Final = "whosonfirst:county:102048609"

COUNCIL_URL: Final = (
    "https://www.frankston.vic.gov.au/My-Property/Waste-and-recycling/My-bins/Bin-collections"
)
LOOKUP_URL: Final = "https://frankston.pozi.com"

# Zone data rarely changes; dates are recalculated locally every update.
UPDATE_INTERVAL: Final = timedelta(minutes=30)
ZONE_REFRESH_INTERVAL: Final = timedelta(hours=12)

# How far ahead to build the upcoming collection list / calendar.
UPCOMING_DAYS: Final = 56

STATIC_URL: Final = f"/{DOMAIN}_static"
CARD_FILENAME: Final = "frankston-bins-card.js"
