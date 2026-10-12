"""Button platform for the Škoda API Connect integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SkodaConfigEntry, SkodaDataUpdateCoordinator
from .entity import SkodaVehicleEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Škoda API Connect refresh button from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(SkodaRefreshButton(coordinator, vin) for vin in coordinator.data.vehicles)


class SkodaRefreshButton(SkodaVehicleEntity, ButtonEntity):
    """Polls the vehicle immediately (one request of the API quota)."""

    _attr_translation_key = "refresh"

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the button."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_refresh"

    @property
    def available(self) -> bool:
        """Stay available while polling fails, so a refresh can be retried."""
        return True

    async def async_press(self) -> None:
        """Refresh the vehicle."""
        await self.coordinator.async_refresh_vehicle(self.vin)
