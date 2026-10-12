"""Tests for the config and options flows."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.skoda_api_connect.api import (
    SkodaApiError,
    SkodaAuthError,
    SkodaRateLimitError,
)
from custom_components.skoda_api_connect.const import (
    CONF_API_KEY,
    CONF_CHARGING_SCAN_INTERVAL,
    CONF_READ_ONLY,
    CONF_VINS,
    DOMAIN,
)

from .conftest import VIN, VIN2, make_vehicle

GET = "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle"
SETUP = "custom_components.skoda_api_connect.async_setup_entry"


async def _start(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return result


async def test_user_flow_success(hass: HomeAssistant) -> None:
    result = await _start(hass)
    with patch(GET, new=AsyncMock(return_value=make_vehicle())), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: " key ", CONF_VINS: f"{VIN.lower()}, {VIN2} {VIN}"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_API_KEY: "key", CONF_VINS: [VIN, VIN2]}


async def test_user_flow_invalid_vin(hass: HomeAssistant) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "key", CONF_VINS: "TOOSHORT"}
    )
    assert result["errors"] == {"base": "invalid_vin"}


async def test_user_flow_errors_then_recovery(hass: HomeAssistant) -> None:
    cases = [
        (SkodaAuthError("x", status=401), "invalid_auth"),
        (SkodaRateLimitError("x", status=429), "rate_limited"),
        (SkodaApiError("x", status=500), "cannot_connect"),
        (RuntimeError("x"), "cannot_connect"),
    ]
    result = await _start(hass)
    for exc, code in cases:
        with patch(GET, new=AsyncMock(side_effect=exc)):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_API_KEY: "key", CONF_VINS: VIN}
            )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": code}
    with patch(GET, new=AsyncMock(return_value=make_vehicle())), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: "key", CONF_VINS: VIN}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_already_configured(hass: HomeAssistant, mock_entry) -> None:
    mock_entry.add_to_hass(hass)
    result = await _start(hass)
    with patch(GET, new=AsyncMock(return_value=make_vehicle())):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: "key", CONF_VINS: VIN}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_new_api_key(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=VIN, data={CONF_API_KEY: "old", CONF_VINS: [VIN]}
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    with patch(GET, new=AsyncMock(return_value=make_vehicle())), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: " new ", CONF_VINS: VIN}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {CONF_API_KEY: "new", CONF_VINS: [VIN]}


async def test_reconfigure_invalid_key_keeps_entry(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=VIN, data={CONF_API_KEY: "old", CONF_VINS: [VIN]}
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    with patch(GET, new=AsyncMock(side_effect=SkodaAuthError("expired"))):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: "bad", CONF_VINS: VIN}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data[CONF_API_KEY] == "old"


async def test_reconfigure_rejects_vins_of_other_entry(hass: HomeAssistant) -> None:
    other = MockConfigEntry(
        domain=DOMAIN, unique_id=VIN2, data={CONF_API_KEY: "k2", CONF_VINS: [VIN2]}
    )
    other.add_to_hass(hass)
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=VIN, data={CONF_API_KEY: "old", CONF_VINS: [VIN]}
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    with patch(GET, new=AsyncMock(return_value=make_vehicle())):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: "new", CONF_VINS: VIN2}
        )
    assert result["errors"] == {"base": "already_configured"}
    assert entry.data[CONF_API_KEY] == "old"


async def test_options_flow_keeps_vehicle_intervals(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_KEY: "key", CONF_VINS: [VIN]},
        options={"vehicle_intervals": {VIN: {"idle": 30}}},
    )
    entry.add_to_hass(hass)
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_SCAN_INTERVAL: 15, CONF_CHARGING_SCAN_INTERVAL: 6, CONF_READ_ONLY: True},
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["vehicle_intervals"] == {VIN: {"idle": 30}}
    assert entry.options[CONF_SCAN_INTERVAL] == 15
    assert entry.options[CONF_CHARGING_SCAN_INTERVAL] == 6
    assert entry.options[CONF_READ_ONLY] is True


async def test_options_flow_rejects_below_minimum(hass: HomeAssistant, mock_entry) -> None:
    import voluptuous as vol

    mock_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(mock_entry.entry_id)
    try:
        await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_SCAN_INTERVAL: 1, CONF_CHARGING_SCAN_INTERVAL: 5, CONF_READ_ONLY: False},
        )
    except vol.Invalid:
        return
    raise AssertionError("interval below the minimum was accepted")
