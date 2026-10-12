"""Tests for setting up and unloading the integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.skoda_api_connect.api import (
    SkodaApiError,
    SkodaAuthError,
    SkodaRateLimitError,
)
from custom_components.skoda_api_connect.const import CONF_API_KEY, CONF_VINS, DOMAIN

from .conftest import VIN


async def test_setup_and_unload(hass: HomeAssistant, mock_entry, mock_get_vehicle) -> None:
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_entry.state is ConfigEntryState.LOADED
    assert mock_get_vehicle.await_count == 1

    assert await hass.config_entries.async_unload(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_entry.state is ConfigEntryState.NOT_LOADED


async def test_auth_error_starts_reauth(hass: HomeAssistant, mock_entry) -> None:
    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle",
        new=AsyncMock(side_effect=SkodaAuthError("bad key", status=401)),
    ):
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()
    assert mock_entry.state is ConfigEntryState.SETUP_ERROR
    assert any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())


async def test_api_error_retries_setup(hass: HomeAssistant, mock_entry) -> None:
    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle",
        new=AsyncMock(side_effect=SkodaApiError("boom", status=500)),
    ):
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()
    assert mock_entry.state is ConfigEntryState.SETUP_RETRY


async def test_rate_limit_retries_setup(hass: HomeAssistant, mock_entry) -> None:
    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle",
        new=AsyncMock(side_effect=SkodaRateLimitError("slow down", status=429)),
    ):
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()
    assert mock_entry.state is ConfigEntryState.SETUP_RETRY


async def test_entities_created(hass: HomeAssistant, mock_entry, mock_get_vehicle) -> None:
    mock_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    states = hass.states.async_all("number")
    ids = {s.entity_id for s in states}
    assert len(ids) == 3  # charge limit + idle/charging interval
    assert any("charging" in i for i in ids)
