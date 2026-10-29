"""Tests for the climate entity's modes and for polling faster while the climate runs."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.skoda_api_connect.api import SkodaVehicle

from .conftest import VIN

GET = "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle"
AIR_CONDITIONING = ["startAirConditioning", "stopAirConditioning"]
VENTILATION = ["startActiveVentilation", "stopActiveVentilation"]


def _vehicle(
    *, operations: list[str], state: str = "OFF", ventilation: str | None = None
) -> SkodaVehicle:
    data = {
        "name": "Car 1",
        "operations": [{"name": name} for name in operations],
        "airConditioning": {"state": state, "targetTemperature": {"value": 21.0}},
        "charging": {"status": {"state": "CONNECT_CABLE"}},
    }
    if ventilation is not None:
        data["activeVentilation"] = {"state": ventilation}
    return SkodaVehicle(vin=VIN, data=data)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, vehicle: SkodaVehicle):
    entry.add_to_hass(hass)
    with patch(GET, new=AsyncMock(return_value=vehicle)):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry.runtime_data


def _climate(hass: HomeAssistant) -> str:
    return er.async_get(hass).async_get_entity_id(
        "climate", "skoda_api_connect", f"{VIN}_air_conditioning"
    )


async def test_ventilation_mode_only_if_the_vehicle_supports_it(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    c = await _setup(hass, mock_entry, _vehicle(operations=AIR_CONDITIONING))
    modes = hass.states.get(_climate(hass)).attributes["hvac_modes"]
    assert set(modes) == {"off", "heat_cool"}
    await c.async_shutdown()


async def test_ventilation_mode_offered_when_supported(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    c = await _setup(hass, mock_entry, _vehicle(operations=AIR_CONDITIONING + VENTILATION))
    modes = hass.states.get(_climate(hass)).attributes["hvac_modes"]
    assert set(modes) == {"off", "heat_cool", "fan_only"}
    await c.async_shutdown()


@pytest.mark.parametrize(
    ("state", "ventilation", "fast"),
    [
        ("OFF", None, False),
        ("COMPLETED", None, False),
        ("HEATING", None, True),
        ("COOLING", None, True),
        ("HEATING_AUXILIARY", None, True),
        ("VENTILATION", None, True),
        ("OFF", "PREHEATING", True),
        ("OFF", "VENTILATION", True),
        ("OFF", "OFF", False),
    ],
)
async def test_polls_faster_while_the_climate_runs(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    state: str,
    ventilation: str | None,
    fast: bool,
) -> None:
    c = await _setup(
        hass,
        mock_entry,
        _vehicle(operations=AIR_CONDITIONING + VENTILATION, state=state, ventilation=ventilation),
    )
    assert c.is_climate_active(VIN) is fast
    assert c.uses_charging_interval(VIN) is fast
    assert c.update_interval == timedelta(minutes=5 if fast else 10)
    await c.async_shutdown()
