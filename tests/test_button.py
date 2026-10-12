"""Tests for the refresh button."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.skoda_api_connect.api import SkodaRateLimitError

from .conftest import VIN


def _button_id(hass: HomeAssistant) -> str:
    return er.async_get(hass).async_get_entity_id("button", "skoda_api_connect", f"{VIN}_refresh")


async def test_refresh_button_polls_now(
    hass: HomeAssistant, mock_entry: MockConfigEntry, mock_get_vehicle
) -> None:
    mock_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_get_vehicle.await_count == 1

    # The vehicle was just polled, so only the button can cause another request.
    await hass.services.async_call(
        "button", "press", {"entity_id": _button_id(hass)}, blocking=True
    )
    await hass.async_block_till_done()
    assert mock_get_vehicle.await_count == 2


async def test_refresh_button_refused_while_rate_limited(
    hass: HomeAssistant, mock_entry: MockConfigEntry, mock_get_vehicle
) -> None:
    mock_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = mock_entry.runtime_data

    from datetime import timedelta

    mock_get_vehicle.side_effect = SkodaRateLimitError(
        "slow down", status=429, retry_after=timedelta(minutes=30)
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": _button_id(hass)}, blocking=True
    )
    await hass.async_block_till_done()
    assert coordinator.poll_results[VIN].status == "rate_limited"
    calls = mock_get_vehicle.await_count

    with pytest.raises(HomeAssistantError, match="rate limited"):
        await hass.services.async_call(
            "button", "press", {"entity_id": _button_id(hass)}, blocking=True
        )
    assert mock_get_vehicle.await_count == calls
