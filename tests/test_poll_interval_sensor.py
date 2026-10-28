"""Tests for the sensor showing the polling interval currently in use."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import VIN, make_vehicle

GET = "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle"


def _sensor(hass: HomeAssistant) -> str:
    return er.async_get(hass).async_get_entity_id(
        "sensor", "skoda_api_connect", f"{VIN}_poll_interval"
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, charging: bool) -> None:
    entry.add_to_hass(hass)
    with patch(GET, new=AsyncMock(return_value=make_vehicle(charging=charging))):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def test_shows_normal_interval(hass: HomeAssistant, mock_entry: MockConfigEntry) -> None:
    await _setup(hass, mock_entry, charging=False)
    state = hass.states.get(_sensor(hass))
    assert state.state == "10"
    assert state.attributes["mode"] == "idle"
    assert state.attributes["unit_of_measurement"] == "min"
    await mock_entry.runtime_data.async_shutdown()


async def test_shows_charging_interval(hass: HomeAssistant, mock_entry: MockConfigEntry) -> None:
    await _setup(hass, mock_entry, charging=True)
    state = hass.states.get(_sensor(hass))
    assert state.state == "5"
    assert state.attributes["mode"] == "charging"
    await mock_entry.runtime_data.async_shutdown()


async def test_follows_a_changed_setting_at_once(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_entry, charging=False)
    number = er.async_get(hass).async_get_entity_id(
        "number", "skoda_api_connect", f"{VIN}_poll_interval_idle"
    )
    await hass.services.async_call(
        "number", "set_value", {"entity_id": number, "value": 25}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(_sensor(hass)).state == "25"
    await mock_entry.runtime_data.async_shutdown()
