"""Diagnostics support for the Škoda API Connect integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY, CONF_VINS
from .coordinator import SkodaConfigEntry

TO_REDACT = {
    CONF_API_KEY,
    CONF_VINS,
    "vin",
    "licensePlate",
    "renderUrl",
    "gpsCoordinates",
    "formattedAddress",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SkodaConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "read_only": coordinator.read_only,
        "vehicle_count": len(coordinator.vins),
        "vehicles": {
            f"vehicle_{index}": async_redact_data(
                {"data": vehicle.data, "errors": vehicle.errors}, TO_REDACT
            )
            for index, vehicle in enumerate(coordinator.data.vehicles.values(), start=1)
        },
    }
