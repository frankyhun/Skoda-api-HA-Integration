"""Binary sensor platform for the Škoda API Connect integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import SkodaVehicle
from .coordinator import SkodaConfigEntry, SkodaDataUpdateCoordinator
from .entity import SkodaVehicleEntity
from .parking_alert import is_parked, unsecured_reasons

_UNKNOWN = ("UNKNOWN", "UNSUPPORTED")


def _is(*path: str, value: str) -> Callable[[SkodaVehicle], bool | None]:
    """Return a function comparing the value at ``path`` to ``value``.

    Missing or unknown values yield None (unknown) instead of False.
    """

    def check(vehicle: SkodaVehicle) -> bool | None:
        current = vehicle.get(*path)
        if current is None or current in _UNKNOWN:
            return None
        return current == value

    return check


def _reported(*path: str) -> Callable[[SkodaVehicle], bool]:
    return lambda vehicle: vehicle.has(*path)


@dataclass(frozen=True, kw_only=True)
class SkodaBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Škoda API Connect binary sensor entity."""

    value_fn: Callable[[SkodaVehicle], bool | None]
    exists_fn: Callable[[SkodaVehicle], bool]


BINARY_SENSOR_DESCRIPTIONS: tuple[SkodaBinarySensorEntityDescription, ...] = (
    SkodaBinarySensorEntityDescription(
        key="doors_open",
        translation_key="doors_open",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=_is("status", "overall", "doors", value="OPEN"),
        exists_fn=_reported("status", "overall", "doors"),
    ),
    SkodaBinarySensorEntityDescription(
        key="windows_open",
        translation_key="windows_open",
        device_class=BinarySensorDeviceClass.WINDOW,
        value_fn=_is("status", "overall", "windows", value="OPEN"),
        exists_fn=_reported("status", "overall", "windows"),
    ),
    SkodaBinarySensorEntityDescription(
        key="trunk_open",
        translation_key="trunk_open",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=_is("status", "detail", "trunk", value="OPEN"),
        exists_fn=_reported("status", "detail", "trunk"),
    ),
    SkodaBinarySensorEntityDescription(
        key="bonnet_open",
        translation_key="bonnet_open",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=_is("status", "detail", "bonnet", value="OPEN"),
        exists_fn=_reported("status", "detail", "bonnet"),
    ),
    SkodaBinarySensorEntityDescription(
        key="lights_on",
        translation_key="lights_on",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_fn=_is("status", "overall", "lights", value="ON"),
        exists_fn=_reported("status", "overall", "lights"),
    ),
    SkodaBinarySensorEntityDescription(
        # For the LOCK device class "on" means unlocked.
        key="unlocked",
        translation_key="unlocked",
        device_class=BinarySensorDeviceClass.LOCK,
        value_fn=_is("status", "overall", "locked", value="NO"),
        exists_fn=_reported("status", "overall", "locked"),
    ),
    SkodaBinarySensorEntityDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=_is("charging", "status", "state", value="CHARGING"),
        exists_fn=_reported("charging", "status"),
    ),
    SkodaBinarySensorEntityDescription(
        key="plugged_in",
        translation_key="plugged_in",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=_is("charging", "status", "plugConnectionState", value="CONNECTED"),
        exists_fn=_reported("charging", "status", "plugConnectionState"),
    ),
    SkodaBinarySensorEntityDescription(
        key="plug_lock",
        translation_key="plug_lock",
        device_class=BinarySensorDeviceClass.LOCK,
        value_fn=_is("charging", "status", "plugLockState", value="UNLOCKED"),
        exists_fn=_reported("charging", "status", "plugLockState"),
    ),
    SkodaBinarySensorEntityDescription(
        key="vehicle_in_saved_location",
        translation_key="vehicle_in_saved_location",
        icon="mdi:home-map-marker",
        value_fn=lambda v: v.get("charging", "isVehicleInSavedLocation"),
        exists_fn=_reported("charging", "isVehicleInSavedLocation"),
    ),
)


def _parked_unsecured(vehicle: SkodaVehicle) -> bool | None:
    """Return the parking alert condition; unknown while the parking state is not reported."""
    if is_parked(vehicle) is None:
        return None
    return bool(unsecured_reasons(vehicle))


PARKED_UNSECURED_DESCRIPTION = SkodaBinarySensorEntityDescription(
    key="parked_unsecured",
    translation_key="parked_unsecured",
    device_class=BinarySensorDeviceClass.PROBLEM,
    value_fn=_parked_unsecured,
    exists_fn=_reported("parkingPosition", "state"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Škoda API Connect binary sensors from a config entry."""
    coordinator = entry.runtime_data
    entities: list[SkodaBinarySensor] = [
        SkodaBinarySensor(coordinator, vin, description)
        for vin, vehicle in coordinator.data.vehicles.items()
        for description in BINARY_SENSOR_DESCRIPTIONS
        if description.exists_fn(vehicle)
    ]
    entities.extend(
        SkodaParkedUnsecuredSensor(coordinator, vin, PARKED_UNSECURED_DESCRIPTION)
        for vin, vehicle in coordinator.data.vehicles.items()
        if PARKED_UNSECURED_DESCRIPTION.exists_fn(vehicle)
    )
    async_add_entities(entities)


class SkodaBinarySensor(SkodaVehicleEntity, BinarySensorEntity):
    """Represents a boolean state of a Škoda vehicle."""

    entity_description: SkodaBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: SkodaDataUpdateCoordinator,
        vin: str,
        description: SkodaBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, vin)
        self.entity_description = description
        self._attr_unique_id = f"{vin}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return true if the condition described is active."""
        return self.entity_description.value_fn(self.vehicle)


class SkodaParkedUnsecuredSensor(SkodaBinarySensor):
    """On while the vehicle is parked but not secured - the parking alert condition."""

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return what is not secured."""
        return {"reasons": unsecured_reasons(self.vehicle)}
