"""Fixtures for the Škoda API Connect tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.skoda_api_connect.api import SkodaVehicle
from custom_components.skoda_api_connect.const import CONF_API_KEY, CONF_VINS, DOMAIN

VIN = "TMBJJ7NX0LY000001"
VIN2 = "TMBJJ7NX0LY000002"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of custom_components in every test."""


def make_vehicle(vin: str = VIN, charging: bool = False) -> SkodaVehicle:
    """Build a vehicle payload shaped like the public API response."""
    return SkodaVehicle(
        vin=vin,
        data={
            "name": f"Car {vin[-1]}",
            "charging": {
                "status": {
                    "state": "CHARGING" if charging else "CONNECTED_NOT_CHARGING",
                    "stateOfChargeInPercent": 55,
                },
                "settings": {"targetStateOfChargeInPercent": 80},
            },
        },
    )


@pytest.fixture
def mock_entry() -> MockConfigEntry:
    """Return a config entry with one vehicle."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_KEY: "key", CONF_VINS: [VIN]},
        unique_id=VIN,
    )


@pytest.fixture
def mock_get_vehicle():
    """Patch the API client's get_vehicle."""
    async def _get(vin, include=None):
        return make_vehicle(vin)

    with patch(
        "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle",
        new=AsyncMock(side_effect=_get),
    ) as mock:
        yield mock
