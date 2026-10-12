"""Tests for the per-vehicle polling interval logic."""

from __future__ import annotations

import time
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.skoda_api_connect.api import SkodaRateLimitError
from custom_components.skoda_api_connect.const import (
    CONF_API_KEY,
    CONF_CHARGING_SCAN_INTERVAL,
    CONF_VEHICLE_INTERVALS,
    CONF_VINS,
    DOMAIN,
)

from .conftest import VIN, VIN2, make_vehicle

GET = "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle"


def _entry(options=None, vins=(VIN,)) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_KEY: "key", CONF_VINS: list(vins)},
        options=options or {},
    )


async def _setup(hass, entry, state):
    """Set up with ``state`` = {vin: charging?}; returns (mock, state dict)."""

    async def _get(vin, include=None):
        return make_vehicle(vin, charging=state[vin])

    mock = AsyncMock(side_effect=_get)
    patcher = patch(GET, new=mock)
    patcher.start()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return mock, patcher


async def test_defaults(hass: HomeAssistant) -> None:
    entry = _entry()
    mock, p = await _setup(hass, entry, {VIN: False})
    try:
        c = entry.runtime_data
        assert c.interval_minutes(VIN, "idle") == 10
        assert c.interval_minutes(VIN, "charging") == 5
        assert c.update_interval == timedelta(minutes=10)
    finally:
        p.stop()


async def test_global_and_per_vehicle_override_precedence(hass: HomeAssistant) -> None:
    entry = _entry(
        {
            CONF_SCAN_INTERVAL: 20,
            CONF_CHARGING_SCAN_INTERVAL: 7,
            CONF_VEHICLE_INTERVALS: {VIN: {"idle": 30}},
        }
    )
    mock, p = await _setup(hass, entry, {VIN: False})
    try:
        c = entry.runtime_data
        assert c.interval_minutes(VIN, "idle") == 30  # override wins
        assert c.interval_minutes(VIN, "charging") == 7  # falls back to global charging
    finally:
        p.stop()


async def test_charging_vehicle_uses_charging_interval(hass: HomeAssistant) -> None:
    entry = _entry()
    mock, p = await _setup(hass, entry, {VIN: True})
    try:
        c = entry.runtime_data
        assert c.is_charging(VIN)
        assert c.update_interval == timedelta(minutes=5)
    finally:
        p.stop()


async def test_only_due_vehicles_are_polled(hass: HomeAssistant, freezer) -> None:
    """VIN is charging (5 min), VIN2 idle (10 min): the 5-minute tick must skip VIN2."""
    entry = _entry(vins=(VIN, VIN2))
    state = {VIN: True, VIN2: False}
    mock, p = await _setup(hass, entry, state)
    try:
        assert mock.await_count == 2
        mock.reset_mock()
        c = entry.runtime_data
        assert c.update_interval == timedelta(minutes=5)

        base = time.monotonic()
        with patch("custom_components.skoda_api_connect.coordinator.time.monotonic", return_value=base + 300):
            await c.async_refresh()
        polled = [call.args[0] for call in mock.await_args_list]
        assert polled == [VIN]

        mock.reset_mock()
        with patch("custom_components.skoda_api_connect.coordinator.time.monotonic", return_value=base + 601):
            await c.async_refresh()
        assert {call.args[0] for call in mock.await_args_list} == {VIN, VIN2}
    finally:
        p.stop()


async def test_interval_switches_when_charging_stops(hass: HomeAssistant) -> None:
    entry = _entry()
    state = {VIN: True}
    mock, p = await _setup(hass, entry, state)
    try:
        c = entry.runtime_data
        assert c.update_interval == timedelta(minutes=5)
        state[VIN] = False
        with patch("custom_components.skoda_api_connect.coordinator.time.monotonic", return_value=time.monotonic() + 301):
            await c.async_refresh()
        assert c.update_interval == timedelta(minutes=10)
    finally:
        p.stop()


async def test_number_entity_updates_option_without_reload(hass: HomeAssistant) -> None:
    entry = _entry()
    mock, p = await _setup(hass, entry, {VIN: False})
    try:
        c = entry.runtime_data
        ent = "number.car_1_polling_interval"
        await hass.services.async_call(
            "number", "set_value", {"entity_id": ent, "value": 25}, blocking=True
        )
        await hass.async_block_till_done()
        assert entry.options[CONF_VEHICLE_INTERVALS][VIN]["idle"] == 25
        assert entry.runtime_data is c  # not reloaded
        assert c.update_interval == timedelta(minutes=25)
    finally:
        p.stop()


async def test_rate_limit_backs_off(hass: HomeAssistant) -> None:
    entry = _entry()
    mock, p = await _setup(hass, entry, {VIN: False})
    try:
        c = entry.runtime_data
        mock.side_effect = SkodaRateLimitError(
            "x", status=429, retry_after=timedelta(minutes=11)
        )
        with patch("custom_components.skoda_api_connect.coordinator.time.monotonic", return_value=time.monotonic() + 601):
            await c.async_refresh()
        # A rate limit is not an error: the entities keep their last state.
        assert c.last_update_success
        assert c.data.vehicles[VIN] is not None
        # The next poll waits for the quota (the API's wait time plus a margin).
        assert c.update_interval > timedelta(minutes=10)
        calls = mock.await_count
        await c.async_refresh()
        assert mock.await_count == calls
        # The wait time reported by the API is used, with a margin and a floor / ceiling.
        assert c._rate_limit_backoff(SkodaRateLimitError("x", retry_after=timedelta(minutes=11))) == timedelta(minutes=11, seconds=30)
        assert c._rate_limit_backoff(SkodaRateLimitError("x", retry_after=timedelta(seconds=1))) == timedelta(minutes=1)
        assert c._rate_limit_backoff(SkodaRateLimitError("x", retry_after=timedelta(hours=5))) == timedelta(hours=1)
        assert c._rate_limit_backoff(SkodaRateLimitError("x")) == timedelta(minutes=15)
    finally:
        p.stop()


async def test_plugged_in_uses_charging_interval_only_when_enabled(hass: HomeAssistant) -> None:
    from custom_components.skoda_api_connect.api import SkodaVehicle

    def _plugged(plug):
        status = {"state": "READY_FOR_CHARGING"}
        if plug is not None:
            status["plugConnectionState"] = plug
        return SkodaVehicle(VIN, {"name": "Car", "charging": {"status": status}})

    entry = _entry()
    mock, p = await _setup(hass, entry, {VIN: False})
    try:
        c = entry.runtime_data
        c.data.vehicles[VIN] = _plugged("CONNECTED")
        assert not c.uses_charging_interval(VIN)  # option off by default

        hass.config_entries.async_update_entry(
            entry, options={**entry.options, "plugged_in_fast_polling": True}
        )
        await hass.async_block_till_done()
        c = entry.runtime_data
        c.data.vehicles[VIN] = _plugged("CONNECTED")
        assert c.uses_charging_interval(VIN)
        c.reschedule()
        assert c.update_interval == timedelta(minutes=5)

        c.data.vehicles[VIN] = _plugged("DISCONNECTED")
        assert not c.uses_charging_interval(VIN)
        c.data.vehicles[VIN] = _plugged(None)  # no plug field: state != CONNECT_CABLE -> plugged
        assert c.uses_charging_interval(VIN)
        c.data.vehicles[VIN] = SkodaVehicle(
            VIN, {"charging": {"status": {"state": "CONNECT_CABLE"}}}
        )
        assert not c.uses_charging_interval(VIN)
    finally:
        p.stop()


async def test_plugged_in_switch_overrides_global_option_per_vehicle(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er

    entry = _entry(vins=(VIN, VIN2))
    mock, p = await _setup(hass, entry, {VIN: False, VIN2: False})
    try:
        c = entry.runtime_data
        reg = er.async_get(hass)
        ids = {
            vin: reg.async_get_entity_id("switch", DOMAIN, f"{vin}_poll_when_plugged_in")
            for vin in (VIN, VIN2)
        }
        assert all(ids.values())
        assert not c.plugged_in_fast_polling(VIN)  # follows the (off) global option

        await hass.services.async_call("switch", "turn_on", {"entity_id": ids[VIN]}, blocking=True)
        await hass.async_block_till_done()
        c = entry.runtime_data
        assert c.plugged_in_fast_polling(VIN)
        assert not c.plugged_in_fast_polling(VIN2)
        assert hass.states.get(ids[VIN]).state == "on"
        assert hass.states.get(ids[VIN2]).state == "off"

        # A per-vehicle "off" beats a global "on".
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, "plugged_in_fast_polling": True}
        )
        await hass.async_block_till_done()
        c = entry.runtime_data
        await hass.services.async_call("switch", "turn_off", {"entity_id": ids[VIN]}, blocking=True)
        await hass.async_block_till_done()
        c = entry.runtime_data
        assert not c.plugged_in_fast_polling(VIN)
        assert c.plugged_in_fast_polling(VIN2)  # global option still applies
    finally:
        p.stop()


async def test_poll_interval_numbers_allow_three_minutes(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er

    entry = _entry()
    mock, p = await _setup(hass, entry, {VIN: False})
    try:
        reg = er.async_get(hass)
        for kind in ("idle", "charging"):
            entity_id = reg.async_get_entity_id("number", DOMAIN, f"{VIN}_poll_interval_{kind}")
            assert hass.states.get(entity_id).attributes["min"] == 3
            await hass.services.async_call(
                "number", "set_value", {"entity_id": entity_id, "value": 3}, blocking=True
            )
            await hass.async_block_till_done()
        c = entry.runtime_data
        assert c.interval_minutes(VIN, "idle") == 3
        assert c.interval_minutes(VIN, "charging") == 3
        assert c.update_interval == timedelta(minutes=3)
    finally:
        p.stop()
