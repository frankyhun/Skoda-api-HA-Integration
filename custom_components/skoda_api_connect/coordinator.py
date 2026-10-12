"""Data update coordinator for the Škoda API Connect integration."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    SkodaApi,
    SkodaApiError,
    SkodaAuthError,
    SkodaConnectionError,
    SkodaRateLimitError,
    SkodaVehicle,
)
from .const import (
    CONF_CHARGING_SCAN_INTERVAL,
    CONF_PLUGGED_IN_FAST_POLLING,
    CONF_VEHICLE_INTERVALS,
    DEFAULT_CHARGING_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    KEY_PLUGGED_IN,
    POST_COMMAND_REFRESH_DELAY,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_SAVE_DELAY = 60
# Without a wait time from the API, pause this long after a rate limit.
DEFAULT_RATE_LIMIT_BACKOFF = timedelta(minutes=15)
MIN_RATE_LIMIT_BACKOFF = timedelta(minutes=1)
# Added to the wait time reported by the API so the first request after it is not rejected again.
RATE_LIMIT_MARGIN = timedelta(seconds=30)
MAX_RATE_LIMIT_BACKOFF = timedelta(hours=1)
# A vehicle counts as due slightly early so scheduler jitter never skips a whole tick.
DUE_TOLERANCE_SECONDS = 10


STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_AUTH_ERROR = "auth_error"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_CONNECTION_ERROR = "connection_error"
STATUS_API_ERROR = "api_error"
POLL_STATUSES = [
    STATUS_OK,
    STATUS_PARTIAL,
    STATUS_AUTH_ERROR,
    STATUS_RATE_LIMITED,
    STATUS_CONNECTION_ERROR,
    STATUS_API_ERROR,
]


@dataclass
class PollResult:
    """Outcome of the most recent request that polled one vehicle."""

    status: str
    time: datetime
    error: str | None = None
    http_status: int | None = None
    problem: str | None = None
    # When the request quota is available again (only after a rate limit, HTTP 429).
    retry_at: datetime | None = None
    # Parts of the vehicle the API reported as unavailable ("partial" results).
    omitted: list[str] = field(default_factory=list)


def _poll_result(result: SkodaVehicle | Exception) -> PollResult:
    now = dt_util.utcnow()
    if isinstance(result, SkodaVehicle):
        return PollResult(
            STATUS_PARTIAL if result.errors else STATUS_OK, now, omitted=list(result.errors)
        )
    if isinstance(result, SkodaAuthError):
        status = STATUS_AUTH_ERROR
    elif isinstance(result, SkodaRateLimitError):
        status = STATUS_RATE_LIMITED
    elif isinstance(result, SkodaConnectionError):
        status = STATUS_CONNECTION_ERROR
    else:
        status = STATUS_API_ERROR
    retry_after = getattr(result, "retry_after", None)
    return PollResult(
        status,
        now,
        error=str(result),
        http_status=getattr(result, "status", None),
        problem=getattr(result, "problem", None),
        retry_at=now + retry_after if retry_after is not None else None,
    )


@dataclass
class SkodaData:
    """Container for all configured vehicles."""

    vehicles: dict[str, SkodaVehicle] = field(default_factory=dict)


class SkodaDataUpdateCoordinator(DataUpdateCoordinator[SkodaData]):
    """Coordinator that polls the MyŠkoda Public API for every configured vehicle."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: SkodaConfigEntry,
        api: SkodaApi,
        vins: list[str],
    ) -> None:
        """Set up the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=None,
        )
        self.api = api
        self.vins = vins
        self.read_only = False
        self._cancel_refresh: CALLBACK_TYPE | None = None
        self._last_fetch: dict[str, float] = {}
        self._force: set[str] = set()
        # Per vehicle: time.monotonic() until which polling is paused after a rate limit.
        self._paused_until: dict[str, float] = {}
        # Result of the last poll per vehicle, and the last time a poll succeeded.
        self.poll_results: dict[str, PollResult] = {}
        self.last_success: dict[str, datetime] = {}
        self.update_interval = self._shortest_interval()
        # Last known vehicle data, so the entities can be set up while the API is rate limited.
        self._store: Store[dict[str, dict]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{config_entry.entry_id}"
        )

    async def _async_load_cached(self) -> SkodaData | None:
        """Return the last stored data if it covers every configured vehicle."""
        stored = await self._store.async_load()
        if not isinstance(stored, dict) or not all(
            isinstance(stored.get(vin), dict) and stored[vin] for vin in self.vins
        ):
            return None
        return SkodaData(
            vehicles={vin: SkodaVehicle(vin=vin, data=stored[vin]) for vin in self.vins}
        )

    # -- per-vehicle polling intervals -------------------------------------------------

    def is_charging(self, vin: str) -> bool:
        """Return whether the last known state of the vehicle is "charging"."""
        vehicle = self.data.vehicles.get(vin) if self.data else None
        return bool(vehicle and vehicle.get("charging", "status", "state") == "CHARGING")

    def is_plugged_in(self, vin: str) -> bool:
        """Return whether the last known state says the charging cable is plugged in."""
        vehicle = self.data.vehicles.get(vin) if self.data else None
        if vehicle is None:
            return False
        plug = vehicle.get("charging", "status", "plugConnectionState")
        if plug is not None:
            return plug == "CONNECTED"
        # Older responses lack the plug state; a disconnected plug is always CONNECT_CABLE.
        state = vehicle.get("charging", "status", "state")
        return state is not None and state != "CONNECT_CABLE"

    def uses_charging_interval(self, vin: str) -> bool:
        """Return whether the vehicle is polled at its (shorter) charging interval."""
        if self.is_charging(vin):
            return True
        return self.plugged_in_fast_polling(vin) and self.is_plugged_in(vin)

    def plugged_in_fast_polling(self, vin: str) -> bool:
        """Return whether a plugged-in cable selects the charging interval for this vehicle.

        A per-vehicle setting overrides the global option.
        """
        options = self.config_entry.options
        override = options.get(CONF_VEHICLE_INTERVALS, {}).get(vin, {}).get(KEY_PLUGGED_IN)
        if override is not None:
            return bool(override)
        return bool(options.get(CONF_PLUGGED_IN_FAST_POLLING, False))

    def set_vehicle_option(self, vin: str, key: str, value: int | bool) -> None:
        """Store a per-vehicle polling setting; the entry's update listener applies it."""
        options = self.config_entry.options
        overrides = {v: dict(k) for v, k in options.get(CONF_VEHICLE_INTERVALS, {}).items()}
        overrides.setdefault(vin, {})[key] = value
        self.hass.config_entries.async_update_entry(
            self.config_entry, options={**options, CONF_VEHICLE_INTERVALS: overrides}
        )

    def interval_minutes(self, vin: str, kind: str) -> int:
        """Return the configured interval of a vehicle; ``kind`` is "idle" or "charging"."""
        options = self.config_entry.options
        override = options.get(CONF_VEHICLE_INTERVALS, {}).get(vin, {}).get(kind)
        if override is not None:
            return int(override)
        if kind == "charging":
            return int(
                options.get(CONF_CHARGING_SCAN_INTERVAL, DEFAULT_CHARGING_SCAN_INTERVAL_MINUTES)
            )
        return int(options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES))

    def _interval_for(self, vin: str) -> timedelta:
        kind = "charging" if self.uses_charging_interval(vin) else "idle"
        return timedelta(minutes=self.interval_minutes(vin, kind))

    def _delay_for(self, vin: str) -> timedelta:
        """Return the time until the vehicle is polled next: its interval, or the pause."""
        remaining = self._paused_until.get(vin, 0) - time.monotonic()
        if remaining > 0:
            return timedelta(seconds=remaining + 1)
        return self._interval_for(vin)

    def _shortest_interval(self) -> timedelta:
        return min(self._delay_for(vin) for vin in self.vins)

    def _is_due(self, vin: str) -> bool:
        if not self.data or vin not in self.data.vehicles:
            return True
        if time.monotonic() < self._paused_until.get(vin, 0):
            return False  # rate limited: wait for the quota instead of requesting again
        if vin in self._force or vin not in self._last_fetch:
            return True
        elapsed = time.monotonic() - self._last_fetch[vin]
        return elapsed >= self._interval_for(vin).total_seconds() - DUE_TOLERANCE_SECONDS

    def reschedule(self) -> None:
        """Apply changed interval settings to the next poll."""
        interval = self._shortest_interval()
        if interval != self.update_interval:
            self.update_interval = interval
            self._schedule_refresh()

    async def _async_update_data(self) -> SkodaData:
        """Fetch the latest data for every vehicle from the cloud API."""
        due = [vin for vin in self.vins if self._is_due(vin)]
        results = await asyncio.gather(
            *(self.api.get_vehicle(vin) for vin in due), return_exceptions=True
        )
        fetched = dict(zip(due, results, strict=True))
        self._force.clear()
        for vin, result in fetched.items():
            self.poll_results[vin] = poll = _poll_result(result)
            if not isinstance(result, Exception):
                self.last_success[vin] = poll.time
        if any(isinstance(result, Exception) for result in fetched.values()):
            # Home Assistant does not notify listeners about a failed update that follows a
            # failed one, so push the new poll results (status, last attempt) to the sensors.
            self.async_update_listeners()

        vehicles: dict[str, SkodaVehicle] = {}
        failures: list[Exception] = []
        for vin in self.vins:
            if vin not in fetched:
                # Not due yet: keep the last known state.
                vehicles[vin] = self.data.vehicles[vin]
                continue
            result = fetched[vin]
            if isinstance(result, SkodaAuthError):
                raise ConfigEntryAuthFailed(str(result)) from result
            if isinstance(result, SkodaRateLimitError):
                backoff = self._rate_limit_backoff(result)
                self._paused_until[vin] = time.monotonic() + backoff.total_seconds()
                _LOGGER.warning(
                    "Škoda API rate limit hit; pausing polling of a vehicle for %s",
                    backoff,
                )
                if not self.data:
                    if cached := await self._async_load_cached():
                        # Startup during a rate limit: set up with the last known state
                        # instead of failing the setup, and poll again once the quota is back.
                        self.update_interval = self._shortest_interval()
                        return cached
                    raise UpdateFailed(
                        "Škoda API rate limit reached; backing off",
                        retry_after=backoff.total_seconds(),
                    ) from result
                # Not an error: keep the last known state and poll again after the pause.
                vehicles[vin] = self.data.vehicles[vin]
                continue
            if isinstance(result, Exception):
                failures.append(result)
                # Keep the last known state for a vehicle whose request failed.
                if self.data and vin in self.data.vehicles:
                    vehicles[vin] = self.data.vehicles[vin]
                continue
            vehicles[vin] = result
            self._last_fetch[vin] = time.monotonic()

        if failures and len(failures) == len(fetched):
            raise UpdateFailed(
                f"Error communicating with Škoda API: {failures[0]}"
            ) from failures[0]
        for failure in failures:
            _LOGGER.warning("Could not update a vehicle: %s", failure)
        data = SkodaData(vehicles=vehicles)
        self._store.async_delay_save(
            lambda: {vin: vehicle.data for vin, vehicle in data.vehicles.items()},
            STORAGE_SAVE_DELAY,
        )
        # A vehicle that started or stopped charging switches to its other interval.
        self.data = data
        self.update_interval = self._shortest_interval()
        return data

    @staticmethod
    def _rate_limit_backoff(err: SkodaRateLimitError) -> timedelta:
        if err.retry_after is None:
            return DEFAULT_RATE_LIMIT_BACKOFF
        backoff = err.retry_after + RATE_LIMIT_MARGIN
        return min(max(backoff, MIN_RATE_LIMIT_BACKOFF), MAX_RATE_LIMIT_BACKOFF)

    async def async_command(self, vin: str, command: Awaitable[None]) -> None:
        """Run a remote command and schedule a single follow-up refresh of that vehicle.

        Commands count against the same request quota as polling, so instead of
        refreshing after every call this waits a moment for the vehicle and refreshes once.
        """
        if self.read_only:
            command.close()  # type: ignore[attr-defined]
            raise HomeAssistantError(
                "Škoda API Connect is configured in read-only mode; disable it in the "
                "integration options to use this control"
            )
        try:
            await command
        except SkodaAuthError as err:
            raise HomeAssistantError(f"The API key was rejected: {err}") from err
        except SkodaRateLimitError as err:
            raise HomeAssistantError(f"Škoda API rate limit reached: {err}") from err
        except SkodaApiError as err:
            raise HomeAssistantError(f"The vehicle did not accept the request: {err}") from err

        self._force.add(vin)
        if self._cancel_refresh:
            self._cancel_refresh()
        self._cancel_refresh = async_call_later(
            self.hass, POST_COMMAND_REFRESH_DELAY, self._async_delayed_refresh
        )

    async def async_refresh_vehicle(self, vin: str) -> None:
        """Poll one vehicle now, regardless of its polling interval.

        Costs one request of the quota, so it is refused while the API is rate limited.
        """
        result = self.poll_results.get(vin)
        if (
            result is not None
            and result.status == STATUS_RATE_LIMITED
            and result.retry_at is not None
            and result.retry_at > dt_util.utcnow()
        ):
            raise HomeAssistantError(
                "The Škoda API is rate limited until "
                f"{dt_util.as_local(result.retry_at):%H:%M}"
            )
        self._force.add(vin)
        await self.async_request_refresh()

    async def _async_delayed_refresh(self, _now) -> None:
        self._cancel_refresh = None
        await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        """Cancel any pending follow-up refresh."""
        if self._cancel_refresh:
            self._cancel_refresh()
            self._cancel_refresh = None
        await super().async_shutdown()


# Generic alias used to type-annotate config entries for this integration.
SkodaConfigEntry = ConfigEntry[SkodaDataUpdateCoordinator]
