"""Select platform for the Škoda API Connect integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import SkodaVehicle
from .coordinator import Expectation, SkodaConfigEntry, SkodaDataUpdateCoordinator
from .entity import SkodaVehicleEntity


def _has_charge_modes(vehicle: SkodaVehicle) -> bool:
    return bool(vehicle.get("charging", "settings", "availableChargeModes"))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Škoda API Connect charge mode select from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        SkodaChargeModeSelect(coordinator, vin)
        for vin, vehicle in coordinator.data.vehicles.items()
        if _has_charge_modes(vehicle)
    )


class SkodaChargeModeSelect(SkodaVehicleEntity, SelectEntity):
    """Represents the preferred charge mode (e.g. MANUAL, TIMER)."""

    _attr_translation_key = "charge_mode"
    _expected_key = "charge_mode"

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_charge_mode"

    @property
    def options(self) -> list[str]:
        """Return the charge modes the vehicle offers."""
        return list(self.vehicle.get("charging", "settings", "availableChargeModes") or [])

    @property
    def current_option(self) -> str | None:
        """Return the active charge mode."""
        if (expected := self._expected()) is not None:
            return expected
        return self.vehicle.get("charging", "settings", "preferredChargeMode")

    async def async_select_option(self, option: str) -> None:
        """Change the charge mode."""
        await self.coordinator.async_command(
            self.vin,
            self.coordinator.api.set_charge_mode(self.vin, option),
            Expectation("charge_mode", option, "charging"),
        )
