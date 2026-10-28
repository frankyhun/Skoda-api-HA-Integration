"""Tests for the parking alert, its grace period, targets and sensors."""

from __future__ import annotations

import copy
import time
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.skoda_api_connect.api import SkodaRateLimitError, SkodaVehicle
from custom_components.skoda_api_connect.const import (
    CONF_API_KEY,
    CONF_CHARGING_SCAN_INTERVAL,
    CONF_NOTIFY_TARGETS,
    CONF_READ_ONLY,
    CONF_VEHICLE_INTERVALS,
    CONF_VINS,
    DOMAIN,
    KEY_ALERT_GRACE,
)
from custom_components.skoda_api_connect.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.skoda_api_connect.parking_alert import unsecured_reasons

from .conftest import VIN

GET = "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle"
PHONE = "notify.mobile_app_phone"

SECURED = {
    "name": "Car 1",
    "status": {
        "overall": {
            "doorsLocked": "YES",
            "locked": "YES",
            "doors": "CLOSED",
            "windows": "CLOSED",
            "lights": "OFF",
            "reliableLockStatus": "LOCKED",
        }
    },
    "parkingPosition": {"state": "PARKED"},
}


def _data(state: str = "PARKED", **overall: str) -> dict:
    data = copy.deepcopy(SECURED)
    data["parkingPosition"]["state"] = state
    data["status"]["overall"].update(overall)
    return data


UNSECURED = _data(doors="OPEN", windows="OPEN")


def _entry(grace: int | None = 0, targets: list[str] | None = None) -> MockConfigEntry:
    options: dict = {}
    if targets is not None:
        options[CONF_NOTIFY_TARGETS] = targets
    if grace is not None:
        options[CONF_VEHICLE_INTERVALS] = {VIN: {KEY_ALERT_GRACE: grace}}
    return MockConfigEntry(
        domain=DOMAIN, data={CONF_API_KEY: "key", CONF_VINS: [VIN]}, options=options
    )


class _Api:
    """Serves the current payload from get_vehicle."""

    def __init__(self, data: dict) -> None:
        self.data = data
        self.mock = AsyncMock(side_effect=self._get)

    async def _get(self, vin, include=None):
        return SkodaVehicle(vin=vin, data=copy.deepcopy(self.data))


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, data: dict):
    api = _Api(data)
    patcher = patch(GET, new=api.mock)
    patcher.start()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return api, patcher


async def _poll(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    coordinator = entry.runtime_data
    coordinator._force.add(VIN)
    await coordinator.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)


async def _tick(hass: HomeAssistant, freezer, minutes: float) -> None:
    freezer.tick(timedelta(minutes=minutes))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)


def test_unsecured_reasons() -> None:
    def reasons(data: dict) -> list[str]:
        return unsecured_reasons(SkodaVehicle(vin=VIN, data=data))

    assert reasons(SECURED) == []
    assert reasons(UNSECURED) == ["Doors: OPEN", "Windows: OPEN"]
    assert reasons(_data("IN_MOTION", doors="OPEN")) == []
    assert reasons({"status": SECURED["status"]}) == []  # parking state not reported
    # Without electric windows the window check is skipped.
    assert reasons(_data(windows="UNSUPPORTED")) == []
    # Unknown or missing values cannot be confirmed as secured.
    assert reasons(_data(doorsLocked="TRUNK_OPENED", reliableLockStatus="UNKNOWN")) == [
        "Reliable lock status: UNKNOWN",
        "Doors locked: TRUNK_OPENED",
    ]
    assert reasons({"name": "Car 1", "parkingPosition": {"state": "PARKED"}}) == [
        "Reliable lock status: unknown",
        "Doors: unknown",
        "Doors locked: unknown",
        "Locked: unknown",
        "Windows: unknown",
    ]


async def test_immediate_alert_once_per_incident(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    api, p = await _setup(hass, entry, UNSECURED)
    try:
        assert len(calls) == 1
        assert calls[0].data["title"] == "Car 1 is not secured"
        assert calls[0].data["message"] == "Parked, but: Doors: OPEN, Windows: OPEN"
        assert calls[0].data["data"]["push"]["sound"]["critical"] == 1
        assert calls[0].data["data"]["channel"] == "alarm_stream"

        await _poll(hass, entry)  # still unsecured: no repeat
        assert len(calls) == 1

        api.data = SECURED
        await _poll(hass, entry)
        api.data = _data(locked="NO", reliableLockStatus="UNLOCKED")  # new incident
        await _poll(hass, entry)
        assert len(calls) == 2
        assert calls[1].data["message"] == (
            "Parked, but: Reliable lock status: UNLOCKED, Locked: NO"
        )
    finally:
        p.stop()


async def test_grace_period(hass: HomeAssistant, freezer) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(grace=7, targets=[PHONE])
    api, p = await _setup(hass, entry, UNSECURED)
    try:
        assert calls == []
        await _tick(hass, freezer, 5)
        await _poll(hass, entry)  # still unsecured, grace not over
        assert calls == []
        await _tick(hass, freezer, 2)
        assert len(calls) == 1
    finally:
        p.stop()


async def test_secured_within_grace_period(hass: HomeAssistant, freezer) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(grace=10, targets=[PHONE])
    api, p = await _setup(hass, entry, UNSECURED)
    try:
        await _tick(hass, freezer, 5)
        api.data = SECURED
        await _poll(hass, entry)
        await _tick(hass, freezer, 10)
        assert calls == []
    finally:
        p.stop()


async def test_failed_poll_keeps_incident(hass: HomeAssistant, freezer) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(grace=7, targets=[PHONE])
    api, p = await _setup(hass, entry, UNSECURED)
    try:
        api.mock.side_effect = SkodaRateLimitError("slow down", status=429)
        await _poll(hass, entry)
        await _tick(hass, freezer, 7)  # the last known data is still unsecured
        assert len(calls) == 1
    finally:
        p.stop()


async def test_grace_slider_reschedules(hass: HomeAssistant, freezer) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(grace=None, targets=[PHONE])  # default: 5 minutes
    api, p = await _setup(hass, entry, UNSECURED)
    try:
        entity_id = er.async_get(hass).async_get_entity_id(
            "number", DOMAIN, f"{VIN}_parking_alert_grace"
        )
        state = hass.states.get(entity_id)
        assert state.state == "5"
        assert (state.attributes["min"], state.attributes["max"], state.attributes["step"]) == (0, 30, 1)
        assert state.attributes["mode"] == "slider"

        await _tick(hass, freezer, 1)
        await hass.services.async_call(
            "number", "set_value", {"entity_id": entity_id, "value": 2}, blocking=True
        )
        await hass.async_block_till_done(wait_background_tasks=True)
        assert entry.options[CONF_VEHICLE_INTERVALS][VIN][KEY_ALERT_GRACE] == 2
        assert entry.options[CONF_NOTIFY_TARGETS] == [PHONE]  # untouched
        assert calls == []
        # Grace counts from when the problem was first seen, so it is due 2 minutes in.
        await _tick(hass, freezer, 1)
        assert len(calls) == 1
    finally:
        p.stop()


async def test_not_parked(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    api, p = await _setup(hass, entry, _data("IN_MOTION", doors="OPEN"))
    try:
        await _poll(hass, entry)
        assert calls == []
    finally:
        p.stop()


async def test_multiple_targets(hass: HomeAssistant) -> None:
    phone = async_mock_service(hass, "notify", "mobile_app_phone")
    telegram = async_mock_service(hass, "notify", "telegram")
    entry = _entry(targets=[PHONE, "notify.telegram"])
    api, p = await _setup(hass, entry, UNSECURED)
    try:
        assert len(phone) == 1 and "data" in phone[0].data
        assert len(telegram) == 1 and "data" not in telegram[0].data  # not critical
    finally:
        p.stop()


async def test_no_alert_from_cached_data(hass: HomeAssistant, hass_storage) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    key = f"{DOMAIN}.{entry.entry_id}"
    hass_storage[key] = {"version": 1, "minor_version": 1, "key": key, "data": {VIN: UNSECURED}}
    entry.add_to_hass(hass)
    with patch(GET, new=AsyncMock(side_effect=SkodaRateLimitError("slow down", status=429))):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
    # Set up from the cache while rate limited, but the cache may be stale.
    assert entry.runtime_data.data.vehicles[VIN].get("status", "overall", "doors") == "OPEN"
    assert calls == []

    api = _Api(UNSECURED)
    with (
        patch(GET, new=api.mock),
        patch(
            "custom_components.skoda_api_connect.coordinator.time.monotonic",
            return_value=time.monotonic() + 3700,
        ),
    ):
        await _poll(hass, entry)
    assert len(calls) == 1


async def test_options_flow_targets(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    async_mock_service(hass, "notify", "telegram")
    async_mock_service(hass, "notify", "send_message")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_KEY: "key", CONF_VINS: [VIN]},
        options={**_entry().options, CONF_SCAN_INTERVAL: 15},
    )
    api, p = await _setup(hass, entry, UNSECURED)
    try:
        assert calls == []  # no targets yet: the incident stays open
        result = await hass.config_entries.options.async_init(entry.entry_id)
        key = next(k for k in result["data_schema"].schema if k == CONF_NOTIFY_TARGETS)
        offered = result["data_schema"].schema[key].config["options"]
        assert offered == [PHONE, "notify.telegram"]

        base = {CONF_SCAN_INTERVAL: 15, CONF_CHARGING_SCAN_INTERVAL: 5, CONF_READ_ONLY: False}
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {**base, CONF_NOTIFY_TARGETS: ["notify.nope"]}
        )
        assert result["errors"] == {CONF_NOTIFY_TARGETS: "unknown_notify_target"}
        assert result["description_placeholders"]["target"] == "notify.nope"

        # Names are normalised and de-duplicated; the open incident is alerted at once.
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {**base, CONF_NOTIFY_TARGETS: ["mobile_app_phone", PHONE, " notify.telegram "]},
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done(wait_background_tasks=True)
        assert entry.options[CONF_NOTIFY_TARGETS] == [PHONE, "notify.telegram"]
        assert entry.options[CONF_VEHICLE_INTERVALS] == {VIN: {KEY_ALERT_GRACE: 0}}
        assert len(calls) == 1

        # The current targets are suggested in the form.
        result = await hass.config_entries.options.async_init(entry.entry_id)
        key = next(k for k in result["data_schema"].schema if k == CONF_NOTIFY_TARGETS)
        assert key.description == {"suggested_value": [PHONE, "notify.telegram"]}

        # Clearing the field removes the targets, whether it is sent empty or left out.
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {**base, CONF_NOTIFY_TARGETS: []}
        )
        assert entry.options[CONF_NOTIFY_TARGETS] == []
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_NOTIFY_TARGETS: [PHONE]}
        )
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result["flow_id"], base)
        assert entry.options[CONF_NOTIFY_TARGETS] == []
    finally:
        p.stop()


async def test_sensors(hass: HomeAssistant) -> None:
    entry = _entry()
    api, p = await _setup(
        hass, entry, _data(doors="OPEN", doorsLocked="OPENED", reliableLockStatus="UNLOCKED")
    )
    try:
        registry = er.async_get(hass)

        def state(platform: str, key: str):
            entity_id = registry.async_get_entity_id(platform, DOMAIN, f"{VIN}_{key}")
            return hass.states.get(entity_id)

        assert state("sensor", "doors_locked").state == "OPENED"
        assert state("sensor", "reliable_lock_status").state == "UNLOCKED"
        assert state("sensor", "parking_state").state == "PARKED"
        unsecured = state("binary_sensor", "parked_unsecured")
        assert unsecured.state == "on"
        assert unsecured.attributes["device_class"] == "problem"
        assert unsecured.attributes["reasons"] == [
            "Reliable lock status: UNLOCKED",
            "Doors: OPEN",
            "Doors locked: OPENED",
        ]

        api.data = _data("IN_MOTION", doors="OPEN")
        await _poll(hass, entry)
        assert state("binary_sensor", "parked_unsecured").state == "off"
        assert state("sensor", "parking_state").state == "IN_MOTION"
    finally:
        p.stop()


async def test_sensors_not_created_without_data(hass: HomeAssistant) -> None:
    entry = _entry()
    api, p = await _setup(hass, entry, {"name": "Car 1"})
    try:
        registry = er.async_get(hass)
        for platform, key in (
            ("sensor", "doors_locked"),
            ("sensor", "reliable_lock_status"),
            ("sensor", "parking_state"),
            ("binary_sensor", "parked_unsecured"),
        ):
            assert registry.async_get_entity_id(platform, DOMAIN, f"{VIN}_{key}") is None
    finally:
        p.stop()


async def test_diagnostics_redact_targets(hass: HomeAssistant) -> None:
    async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    api, p = await _setup(hass, entry, SECURED)
    try:
        result = await async_get_config_entry_diagnostics(hass, entry)
        assert result["options"][CONF_NOTIFY_TARGETS] == "**REDACTED**"
        assert "mobile_app_phone" not in str(result)
    finally:
        p.stop()
