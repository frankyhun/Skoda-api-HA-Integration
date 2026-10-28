"""Tests for the expected state shown after an accepted command."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.skoda_api_connect.api import SkodaApiError, SkodaVehicle

from .conftest import VIN

GET = "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle"
API = "custom_components.skoda_api_connect.api.SkodaApi"


def _iso(age: timedelta) -> str:
    return (dt_util.utcnow() - age).strftime("%Y-%m-%dT%H:%M:%SZ")


def _vehicle(
    *, charging: bool = False, climate: bool = False, limit: int = 80, age: timedelta
) -> SkodaVehicle:
    """Build a vehicle whose sections were last reported ``age`` ago."""
    stamp = _iso(age)
    data = {
        "name": "Car 1",
        "charging": {
            "status": {"state": "CHARGING" if charging else "CONNECTED_NOT_CHARGING"},
            "settings": {
                "targetStateOfChargeInPercent": limit,
                "preferredChargeMode": "MANUAL",
                "availableChargeModes": ["MANUAL", "TIMER"],
            },
            "carCapturedTimestamp": stamp,
        },
        "airConditioning": {
            "state": "COOLING" if climate else "OFF",
            "targetTemperature": {"value": 21.0},
            "carCapturedTimestamp": stamp,
        },
    }
    return SkodaVehicle(vin=VIN, data=data)


@asynccontextmanager
async def _running(hass: HomeAssistant, entry: MockConfigEntry, holder: dict):
    """Set the integration up; ``holder["vehicle"]`` is what the API returns."""

    async def _get(vin, include=None):
        return holder["vehicle"]

    with patch(GET, new=AsyncMock(side_effect=_get)):
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data
        try:
            yield coordinator
        finally:
            await coordinator.async_shutdown()


def _entity(hass: HomeAssistant, domain: str, key: str) -> str:
    return er.async_get(hass).async_get_entity_id(domain, "skoda_api_connect", f"{VIN}_{key}")


async def _refresh(coordinator) -> None:
    coordinator._force.add(VIN)
    await coordinator.async_refresh()


async def test_switch_shows_expected_state_until_vehicle_reports(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    holder = {"vehicle": _vehicle(age=timedelta(hours=1))}
    async with _running(hass, mock_entry, holder) as coordinator:
        switch = _entity(hass, "switch", "charging")
        assert hass.states.get(switch).state == "off"

        with patch(f"{API}.start_charging", new=AsyncMock()):
            await hass.services.async_call(
                "switch", "turn_on", {"entity_id": switch}, blocking=True
            )
        state = hass.states.get(switch)
        assert state.state == "on"
        assert state.attributes["pending"] is True

        # A poll that still returns the old data must not undo it.
        await _refresh(coordinator)
        await hass.async_block_till_done()
        state = hass.states.get(switch)
        assert state.state == "on"
        assert state.attributes["pending"] is True

        # The vehicle reports newer data: what it says wins and nothing is pending.
        holder["vehicle"] = _vehicle(charging=True, age=timedelta(seconds=-5))
        await _refresh(coordinator)
        await hass.async_block_till_done()
        state = hass.states.get(switch)
        assert state.state == "on"
        assert "pending" not in state.attributes


async def test_vehicle_report_contradicting_the_command_wins(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    holder = {"vehicle": _vehicle(age=timedelta(hours=1))}
    async with _running(hass, mock_entry, holder) as coordinator:
        switch = _entity(hass, "switch", "charging")
        with patch(f"{API}.start_charging", new=AsyncMock()):
            await hass.services.async_call(
                "switch", "turn_on", {"entity_id": switch}, blocking=True
            )
        assert hass.states.get(switch).state == "on"

        holder["vehicle"] = _vehicle(charging=False, age=timedelta(seconds=-5))
        await _refresh(coordinator)
        await hass.async_block_till_done()
        state = hass.states.get(switch)
        assert state.state == "off"
        assert "pending" not in state.attributes


async def test_rejected_command_expects_nothing(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    holder = {"vehicle": _vehicle(age=timedelta(hours=1))}
    async with _running(hass, mock_entry, holder) as coordinator:
        switch = _entity(hass, "switch", "charging")
        with (
            patch(f"{API}.start_charging", new=AsyncMock(side_effect=SkodaApiError("no", status=400))),
            pytest.raises(HomeAssistantError),
        ):
            await hass.services.async_call(
                "switch", "turn_on", {"entity_id": switch}, blocking=True
            )
        assert coordinator.expected(VIN, "charging") is None
        state = hass.states.get(switch)
        assert state.state == "off"
        assert "pending" not in state.attributes


async def test_expected_state_expires_without_a_report(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    holder = {"vehicle": _vehicle(age=timedelta(hours=1))}
    async with _running(hass, mock_entry, holder) as coordinator:
        switch = _entity(hass, "switch", "charging")
        with patch(f"{API}.start_charging", new=AsyncMock()):
            await hass.services.async_call(
                "switch", "turn_on", {"entity_id": switch}, blocking=True
            )
        assert hass.states.get(switch).state == "on"

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
        await hass.async_block_till_done()
        assert coordinator.expected(VIN, "charging") is None
        assert hass.states.get(switch).state == "off"


async def test_climate_shows_expected_mode_and_expires_sooner(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    holder = {"vehicle": _vehicle(age=timedelta(hours=1))}
    async with _running(hass, mock_entry, holder):
        climate = _entity(hass, "climate", "air_conditioning")
        assert hass.states.get(climate).state == "off"

        with patch(f"{API}.start_air_conditioning", new=AsyncMock()):
            await hass.services.async_call(
                "climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": "heat_cool"},
                blocking=True,
            )
        state = hass.states.get(climate)
        assert state.state == "heat_cool"
        assert state.attributes["pending"] is True

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=4))
        await hass.async_block_till_done()
        assert hass.states.get(climate).state == "off"


async def test_charge_limit_and_mode_show_expected_values(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    holder = {"vehicle": _vehicle(age=timedelta(hours=1))}
    async with _running(hass, mock_entry, holder):
        number = _entity(hass, "number", "charge_limit")
        select = _entity(hass, "select", "charge_mode")

        with patch(f"{API}.set_charging_limit", new=AsyncMock()):
            await hass.services.async_call(
                "number", "set_value", {"entity_id": number, "value": 90}, blocking=True
            )
        assert float(hass.states.get(number).state) == 90
        assert hass.states.get(number).attributes["pending"] is True

        with patch(f"{API}.set_charge_mode", new=AsyncMock()):
            await hass.services.async_call(
                "select", "select_option", {"entity_id": select, "option": "TIMER"},
                blocking=True,
            )
        assert hass.states.get(select).state == "TIMER"
        assert hass.states.get(select).attributes["pending"] is True
