"""Switch platform for Daikin Comfort Control - Vacation Mode."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DaikinCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Daikin switch entities from a config entry."""
    coordinators: list[DaikinCoordinator] = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        DaikinVacationSwitch(coordinator) for coordinator in coordinators
    )


class DaikinVacationSwitch(CoordinatorEntity[DaikinCoordinator], SwitchEntity):
    """Switch that maps to Daikin vacation / holiday mode (en_hol).

    When ON  -> GET /common/set_holiday?port=<port>&en_hol=1
    When OFF -> GET /common/set_holiday?port=<port>&en_hol=0

    Device identifier uses device.uid to match climate.py and sensor.py
    so all entities appear under the same device card.
    """

    _attr_has_entity_name = True
    _attr_name = "Vacation Mode"
    _attr_icon = "mdi:palm-tree"

    def __init__(self, coordinator: DaikinCoordinator) -> None:
        super().__init__(coordinator)
        device = coordinator.device
        # unique_id uses uid+port to match the pattern of other entities
        self._attr_unique_id = f"{DOMAIN}_{device.uid}_{device.port}_vacation"
        # identifiers MUST match climate.py and sensor.py exactly
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.uid)},
            name=device.name,
            manufacturer="Daikin",
            model="BRP069C4x",
            sw_version=device.fw_ver.replace("_", "."),
        )

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.state.vacation

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.client.set_vacation(
                self.coordinator.device, enable=True
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to enable vacation mode: %s", err)
            return
        self.coordinator.set_optimistic_vacation(enable=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.client.set_vacation(
                self.coordinator.device, enable=False
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to disable vacation mode: %s", err)
            return
        self.coordinator.set_optimistic_vacation(enable=False)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
