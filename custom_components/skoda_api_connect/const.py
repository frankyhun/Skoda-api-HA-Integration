"""Constants for the Škoda API Connect integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "skoda_api_connect"

API_BASE_URL: Final = "https://public.api.connect.skoda-auto.cz"
API_KEYS_URL: Final = "https://go.skoda.eu/api-keys"

CONF_API_KEY: Final = "api_key"
CONF_VINS: Final = "vins"
CONF_READ_ONLY: Final = "read_only"
CONF_CHARGING_SCAN_INTERVAL: Final = "charging_scan_interval"
# Also use the charging interval while the charging cable is plugged in (not only while charging).
CONF_PLUGGED_IN_FAST_POLLING: Final = "plugged_in_fast_polling"
# Per-vehicle overrides in the entry options: {vin: {"idle": minutes, "charging": minutes}}
CONF_VEHICLE_INTERVALS: Final = "vehicle_intervals"
# Key of the per-vehicle override of CONF_PLUGGED_IN_FAST_POLLING inside CONF_VEHICLE_INTERVALS[vin].
KEY_PLUGGED_IN: Final = "plugged_in"

# The public API allows 20 requests per hour and VIN (the limit is documented as not
# final), and every command counts against the same quota. One poll costs a single
# request per vehicle, so 10 minutes leaves roughly half of the quota for commands.
# MIN_SCAN_INTERVAL_MINUTES is a hard floor (3 min = 20 requests/hour, i.e. the whole quota
# without any room for commands) for the options flow and the polling interval numbers.
DEFAULT_SCAN_INTERVAL_MINUTES: Final = 10
# Polling interval while a vehicle is charging (state changes are what you want to see).
DEFAULT_CHARGING_SCAN_INTERVAL_MINUTES: Final = 5
MIN_SCAN_INTERVAL_MINUTES: Final = 3
MAX_SCAN_INTERVAL_MINUTES: Final = 1440
# Upper end of the sliders of the per-vehicle polling interval number entities.
POLL_INTERVAL_NUMBER_MAX_MINUTES: Final = 120

# Commands are accepted asynchronously (HTTP 202); refresh once shortly afterwards so the
# new state shows up without waiting for the next poll.
POST_COMMAND_REFRESH_DELAY: Final = 30

MANUFACTURER: Final = "Škoda"
