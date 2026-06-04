"""Switch platform for Daikin Comfort Control — Vacation Mode."""
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
from .coordinator import DaikinCoordinator, DaikinDeviceData
from .exceptions import DaikinApiError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinators: list[DaikinCoordinator] = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        DaikinVacationSwitch(coordinator) for coordinator in coordinators
    )


class DaikinVacationSwitch(CoordinatorEntity[DaikinCoordinator], SwitchEntity):
    """Toggle Daikin vacation / holiday mode (en_hol).

    Uses device.device_id as the device identifier — same as climate.py
    and sensor.py — so all entities appear under one device card.
    """

    _attr_has_entity_name = True
    _attr_name = "Vacation Mode"
    _attr_icon = "mdi:palm-tree"

    def __init__(self, coordinator: DaikinCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{coordinator.device_id}_vacation"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            name=coordinator.device_name,
            manufacturer="Daikin",
            model="BRP069C4x",
        )

    @property
    def _d(self) -> DaikinDeviceData:
        return self.coordinator.data

    @property
    def is_on(self) -> bool | None:
        if self._d is None:
            return None
        return self._d.vacation

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.api.set_device_parameters(
                self.coordinator.device_id, {"en_hol": "1"}
            )
            self.coordinator.set_optimistic_vacation(True)
        except DaikinApiError as err:
            _LOGGER.error("Failed to enable vacation mode: %s", err)
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.api.set_device_parameters(
                self.coordinator.device_id, {"en_hol": "0"}
            )
            self.coordinator.set_optimistic_vacation(False)
        except DaikinApiError as err:
            _LOGGER.error("Failed to disable vacation mode: %s", err)
            await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
