"""Base entity for the Škoda API Connect integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import SkodaVehicle
from .const import DOMAIN, MANUFACTURER
from .coordinator import SkodaDataUpdateCoordinator


class SkodaVehicleEntity(CoordinatorEntity[SkodaDataUpdateCoordinator]):
    """Base class for all entities tied to a single Škoda vehicle."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the entity for a given vehicle VIN."""
        super().__init__(coordinator)
        self.vin = vin
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, vin)},
            manufacturer=MANUFACTURER,
            name=self.vehicle.name,
            serial_number=vin,
        )

    # Key of the state a command of this entity is expected to cause (see Expectation).
    _expected_key: str | None = None

    def _expected(self) -> Any | None:
        """Return the state an accepted command should cause, or None if none is pending."""
        if self._expected_key is None:
            return None
        return self.coordinator.expected(self.vin, self._expected_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Mark a state that is only expected, not yet reported by the vehicle."""
        return {"pending": True} if self._expected() is not None else None

    @property
    def vehicle(self) -> SkodaVehicle:
        """Return the current vehicle data from the coordinator."""
        return self.coordinator.data.vehicles[self.vin]

    @property
    def available(self) -> bool:
        """Return True while there is data for this vehicle.

        A failed poll (e.g. rate limit backoff) keeps the last known state instead of
        turning every entity unavailable; the API status sensor shows the failure.
        """
        data = self.coordinator.data
        return data is not None and self.vin in data.vehicles
