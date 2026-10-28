"""Number platform for the Škoda API Connect integration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import SkodaVehicle
from .const import (
    AUTO_WAKE_NUMBER_MAX_MINUTES,
    KEY_ALERT_GRACE,
    KEY_AUTO_WAKE,
    MAX_ALERT_GRACE_MINUTES,
    MIN_AUTO_WAKE_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
    POLL_INTERVAL_NUMBER_MAX_MINUTES,
)
from .coordinator import Expectation, SkodaConfigEntry, SkodaDataUpdateCoordinator
from .entity import SkodaVehicleEntity


def _has_charge_limit(vehicle: SkodaVehicle) -> bool:
    return vehicle.has("charging", "settings", "targetStateOfChargeInPercent")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Škoda API Connect charge limit number entity from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            SkodaChargeLimitNumber(coordinator, vin)
            for vin, vehicle in coordinator.data.vehicles.items()
            if _has_charge_limit(vehicle)
        ]
        + [
            SkodaPollIntervalNumber(entry, coordinator, vin, kind)
            for vin in coordinator.data.vehicles
            for kind in ("idle", "charging")
        ]
        + [
            SkodaAutoWakeNumber(coordinator, vin)
            for vin, vehicle in coordinator.data.vehicles.items()
            if not coordinator.read_only and vehicle.supports("setChargeMode")
        ]
        + [
            SkodaParkingAlertGraceNumber(coordinator, vin)
            for vin in coordinator.data.vehicles
        ]
    )


class SkodaChargeLimitNumber(SkodaVehicleEntity, NumberEntity):
    """Represents the target state-of-charge limit."""

    _attr_translation_key = "charge_limit"
    _expected_key = "charge_limit"
    _attr_native_unit_of_measurement = PERCENTAGE
    # Vehicles typically accept 50-100 in steps of 10 and reject other values.
    _attr_native_min_value = 50
    _attr_native_max_value = 100
    _attr_native_step = 10
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_charge_limit"

    @property
    def native_value(self) -> float | None:
        """Return the currently configured charge limit."""
        if (expected := self._expected()) is not None:
            return expected
        return self.vehicle.get("charging", "settings", "targetStateOfChargeInPercent")

    async def async_set_native_value(self, value: float) -> None:
        """Set a new charge limit."""
        await self.coordinator.async_command(
            self.vin,
            self.coordinator.api.set_charging_limit(self.vin, int(value)),
            Expectation("charge_limit", int(value), "charging"),
        )


class SkodaPollIntervalNumber(SkodaVehicleEntity, NumberEntity):
    """Polling interval of one vehicle, for its normal state or while it is charging.

    Stored in the entry options and applied immediately, without reloading the entry.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = MIN_SCAN_INTERVAL_MINUTES
    _attr_native_max_value = POLL_INTERVAL_NUMBER_MAX_MINUTES
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(
        self, entry, coordinator: SkodaDataUpdateCoordinator, vin: str, kind: str
    ) -> None:
        """Initialize the number entity; ``kind`` is "idle" or "charging"."""
        super().__init__(coordinator, vin)
        self._entry = entry
        self._kind = kind
        self._attr_translation_key = f"poll_interval_{kind}"
        self._attr_unique_id = f"{vin}_poll_interval_{kind}"

    @property
    def native_value(self) -> float:
        """Return the configured interval in minutes."""
        return self.coordinator.interval_minutes(self.vin, self._kind)

    async def async_set_native_value(self, value: float) -> None:
        """Persist the new interval; the entry's update listener applies it."""
        self.coordinator.set_vehicle_option(self.vin, self._kind, int(value))
        self.async_write_ha_state()


class SkodaAutoWakeNumber(SkodaVehicleEntity, NumberEntity):
    """Minutes without vehicle data after which a charging vehicle is woken (0 = off).

    Stored in the entry options like the polling intervals. Each wake-up costs two
    requests of the API quota, which is why this is off by default.
    """

    _attr_translation_key = "auto_wake"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = 0
    _attr_native_max_value = AUTO_WAKE_NUMBER_MAX_MINUTES
    _attr_native_step = 5
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:sleep-off"

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_auto_wake"

    @property
    def native_value(self) -> float:
        """Return the configured time in minutes, 0 if the automatic wake-up is off."""
        return self.coordinator.auto_wake_minutes(self.vin)

    async def async_set_native_value(self, value: float) -> None:
        """Persist the new time, raised to the minimum if it is not 0."""
        minutes = int(value)
        if minutes:
            minutes = max(minutes, MIN_AUTO_WAKE_MINUTES)
        self.coordinator.set_vehicle_option(self.vin, KEY_AUTO_WAKE, minutes)
        self.async_write_ha_state()


class SkodaParkingAlertGraceNumber(SkodaVehicleEntity, NumberEntity):
    """Minutes a parked vehicle may stay unsecured before the parking alert is sent.

    Stored in the entry options like the polling intervals; 0 sends the alert at once.
    """

    _attr_translation_key = "parking_alert_grace"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = 0
    _attr_native_max_value = MAX_ALERT_GRACE_MINUTES
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_parking_alert_grace"

    @property
    def native_value(self) -> float:
        """Return the configured grace period in minutes."""
        return self.coordinator.alert_grace_minutes(self.vin)

    async def async_set_native_value(self, value: float) -> None:
        """Persist the new grace period; the parking alert applies it to an open incident."""
        self.coordinator.set_vehicle_option(self.vin, KEY_ALERT_GRACE, int(value))
        self.async_write_ha_state()
