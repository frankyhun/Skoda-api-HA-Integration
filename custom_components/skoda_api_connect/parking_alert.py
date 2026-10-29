"""Critical notification when a vehicle is parked but not secured."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import SkodaVehicle
from .const import CONF_NOTIFY_TARGETS, DOMAIN, PARKED_STATE
from .coordinator import SkodaConfigEntry, SkodaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

# (field in vehicle.status.overall, label, value that counts as secured, required).
# The API always reports the required fields; reliableLockStatus is optional and only
# checked when the vehicle reports it.
SECURED_CHECKS: tuple[tuple[str, str, str, bool], ...] = (
    ("reliableLockStatus", "Reliable lock status", "LOCKED", False),
    ("doors", "Doors", "CLOSED", True),
    ("doorsLocked", "Doors locked", "YES", True),
    ("locked", "Locked", "YES", True),
    ("windows", "Windows", "CLOSED", True),
)
# Reported for vehicles without electric windows; such a check is skipped.
_UNSUPPORTED = "UNSUPPORTED"

# Makes the Companion app alert even in silent / Do Not Disturb mode.
# "push" is read by iOS, the other keys by Android; each ignores the other's.
CRITICAL_PUSH_DATA: dict[str, Any] = {
    "push": {"sound": {"name": "default", "critical": 1, "volume": 1.0}},
    "ttl": 0,
    "priority": "high",
    "channel": "alarm_stream",
}


def is_parked(vehicle: SkodaVehicle) -> bool | None:
    """Return whether the vehicle is parked, or None if the API did not report it."""
    state = vehicle.get("parkingPosition", "state")
    return None if state is None else state == PARKED_STATE


def unsecured_reasons(vehicle: SkodaVehicle) -> list[str]:
    """Return what is not secured, or an empty list if not parked or all secured.

    An UNKNOWN value, or a missing required one, counts as not secured, since it
    cannot be confirmed.
    """
    if not is_parked(vehicle):
        return []
    reasons = []
    for field_name, label, secured, required in SECURED_CHECKS:
        value = vehicle.get("status", "overall", field_name)
        if value is None and not required:
            continue
        if value != secured and value != _UNSUPPORTED:
            reasons.append(f"{label}: {value or 'unknown'}")
    return reasons


@dataclass
class _Incident:
    """A vehicle that was seen parked and not secured."""

    since: datetime
    notified: bool = False
    # The vehicle was woken to confirm the incident with a fresh report.
    woken: bool = False
    cancel_timer: CALLBACK_TYPE | None = None


class SkodaParkingAlert:
    """Sends one notification per incident and vehicle, after the grace period.

    An incident starts at the first poll that shows the vehicle parked and not secured,
    and ends at the first poll that shows it secured or not parked. Failed polls neither
    start nor end an incident. Incidents are stored, so a restart or reload does not
    send the alert again.

    If the vehicle reported the problem within one polling interval before that poll
    (it parked since the previous poll), the incident begins at that report instead.
    The vehicle usually sleeps right after parking and reports nothing newer, so this
    report is as current as the data gets.

    The alert is only sent on data the vehicle reported when or after the incident
    began: an older snapshot may miss that the vehicle was secured without reporting
    it. If there is no such report when the grace period ends, the vehicle is woken
    once (two requests), and the alert waits for the report that follows.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SkodaConfigEntry,
        coordinator: SkodaDataUpdateCoordinator,
    ) -> None:
        """Initialize the alert."""
        self._hass = hass
        self._entry = entry
        self._coordinator = coordinator
        self._incidents: dict[str, _Incident] = {}
        self._store: Store[dict[str, dict[str, Any]]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.parking_alert"
        )
        self._unloaded = False

    async def async_start(self) -> None:
        """Restore open incidents, then watch the polls and the options."""
        stored = await self._store.async_load() or {}
        for vin, incident in stored.items():
            since = dt_util.parse_datetime(str(incident.get("since")))
            if vin in self._coordinator.vins and since is not None:
                self._incidents[vin] = _Incident(
                    since, bool(incident.get("notified")), bool(incident.get("woken"))
                )
        entry = self._entry
        entry.async_on_unload(self._coordinator.async_add_listener(self._async_check))
        # The grace period or the notification targets changed.
        entry.async_on_unload(entry.add_update_listener(self._async_options_updated))
        entry.async_on_unload(self._async_unload)
        self._async_check()

    @callback
    def _async_unload(self) -> None:
        # An update listener task may still run after a reload has unloaded the entry.
        self._unloaded = True
        for incident in self._incidents.values():
            self._async_cancel_timer(incident)

    @callback
    def _async_save(self) -> None:
        data = {
            vin: {
                "since": incident.since.isoformat(),
                "notified": incident.notified,
                "woken": incident.woken,
            }
            for vin, incident in self._incidents.items()
        }
        # Unloading the entry waits for this task, so a reload reads the latest state.
        self._entry.async_create_task(self._hass, self._store.async_save(data))

    @callback
    def _async_check(self) -> None:
        coordinator = self._coordinator
        if self._unloaded or not coordinator.last_update_success or not coordinator.data:
            return
        for vin, vehicle in coordinator.data.vehicles.items():
            # Data cached from before a restart may be stale; wait for a real poll.
            if coordinator.last_success.get(vin) is None:
                continue
            incident = self._incidents.get(vin)
            if not unsecured_reasons(vehicle):
                if incident is not None:
                    self._async_cancel_timer(incident)
                    del self._incidents[vin]
                    self._async_save()
                continue
            if incident is None:
                self._incidents[vin] = _Incident(since=self._incident_start(vin, vehicle))
                self._async_save()
                self._async_schedule(vin)
            elif not incident.notified and incident.cancel_timer is None:
                # Restored after a restart, or still waiting for notification targets
                # or a fresh report.
                self._async_schedule(vin)

    def _incident_start(self, vin: str, vehicle: SkodaVehicle) -> datetime:
        """Return when a new incident began: the report showing it, if it is recent."""
        now = dt_util.utcnow()
        reported = vehicle.captured("status")
        coordinator = self._coordinator
        interval = timedelta(
            minutes=coordinator.interval_minutes(vin, coordinator.active_interval_kind(vin))
        )
        if reported is not None and now - interval <= reported <= now:
            return reported
        return now

    async def _async_options_updated(
        self, hass: HomeAssistant, entry: SkodaConfigEntry
    ) -> None:
        if self._unloaded:
            return
        for vin in list(self._incidents):
            self._async_schedule(vin)

    @callback
    def _async_schedule(self, vin: str) -> None:
        """(Re)arm the timer of an open incident."""
        incident = self._incidents[vin]
        self._async_cancel_timer(incident)
        if incident.notified:
            return
        grace = timedelta(minutes=self._coordinator.alert_grace_minutes(vin))
        delay = (incident.since + grace - dt_util.utcnow()).total_seconds()
        if delay <= 0:
            self._async_fire(vin)
        else:
            incident.cancel_timer = async_call_later(
                self._hass, delay, partial(self._async_fire, vin)
            )

    @staticmethod
    @callback
    def _async_cancel_timer(incident: _Incident) -> None:
        if incident.cancel_timer is not None:
            incident.cancel_timer()
            incident.cancel_timer = None

    @callback
    def _async_fire(self, vin: str, _now: datetime | None = None) -> None:
        incident = self._incidents.get(vin)
        if self._unloaded or incident is None:
            return
        incident.cancel_timer = None
        # Use the latest known data; it may have changed since the incident began.
        vehicle = self._coordinator.data.vehicles[vin]
        reasons = unsecured_reasons(vehicle)
        targets: list[str] = self._entry.options.get(CONF_NOTIFY_TARGETS, [])
        if not reasons or not targets:
            # Without targets nothing is sent, and the incident stays open so
            # targets added later still get notified.
            return
        captured = vehicle.captured("status")
        if captured is None or captured < incident.since:
            # The vehicle may have been secured since without reporting it. Wait for a
            # newer report; every later poll checks again.
            self._async_wake_once(vin, incident)
            return
        incident.notified = True
        self._async_save()
        # Not a background task: those are cancelled on unload, which would lose an
        # alert that is already stored as sent.
        self._entry.async_create_task(
            self._hass,
            self._async_send(targets, vehicle.name, reasons),
            f"{DOMAIN}_parking_alert_{vin}",
        )

    @callback
    def _async_wake_once(self, vin: str, incident: _Incident) -> None:
        if incident.woken or not self._coordinator.can_wake(vin):
            return
        incident.woken = True
        self._async_save()
        self._entry.async_create_background_task(
            self._hass, self._async_wake(vin), f"{DOMAIN}_parking_alert_wake_{vin}"
        )

    async def _async_wake(self, vin: str) -> None:
        _LOGGER.info("Waking a vehicle to confirm that it is parked but not secured")
        try:
            # The follow-up refresh of the command brings the new report.
            await self._coordinator.async_wake_vehicle(vin)
        except HomeAssistantError as err:
            _LOGGER.warning("Could not wake a vehicle for the parking alert: %s", err)

    async def _async_send(self, targets: list[str], name: str, reasons: list[str]) -> None:
        title = f"{name} is not secured"
        message = "Parked, but: " + ", ".join(reasons)
        await asyncio.gather(
            *(self._async_send_one(target, title, message) for target in targets)
        )

    async def _async_send_one(self, target: str, title: str, message: str) -> None:
        domain, _, service = target.partition(".")
        service_data: dict[str, Any] = {"title": title, "message": message}
        if service.startswith("mobile_app_"):
            service_data["data"] = CRITICAL_PUSH_DATA
        try:
            await self._hass.services.async_call(domain, service, service_data, blocking=True)
        except Exception:  # noqa: BLE001 - one failing target must not stop the others
            _LOGGER.exception("Could not send the parking alert to %s", target)
