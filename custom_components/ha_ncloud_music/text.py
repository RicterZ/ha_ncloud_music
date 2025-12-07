"""Text platform for ha_ncloud_music integration.
提供搜索关键词输入实体，支持状态恢复。
"""
import logging
from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import ENTITY_NAME_SEARCH_INPUT
from .manifest import manifest

_LOGGER = logging.getLogger(__name__)

DOMAIN = manifest.domain


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置 text 实体平台"""
    async_add_entities([CloudMusicSearchInput(hass, entry)])


class CloudMusicSearchInput(RestoreEntity, TextEntity):
    """云音乐搜索关键词输入实体"""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """初始化搜索输入实体"""
        self.hass = hass
        self._entry = entry
        self._attr_name = f"{manifest.name} 搜索关键词"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{ENTITY_NAME_SEARCH_INPUT}"
        self._attr_icon = "mdi:magnify"
        self._attr_native_max = 100
        self._attr_native_min = 0
        self._attr_mode = "text"
        self._attr_native_value = ""

    @property
    def device_info(self):
        """返回设备信息，将实体归类到集成设备下"""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": manifest.name,
            "manufacturer": "shaonianzhentan",
            "model": "Cloud Music",
            "sw_version": manifest.version,
        }

    async def async_added_to_hass(self) -> None:
        """实体添加到 Home Assistant 时恢复状态"""
        await super().async_added_to_hass()
        
        # 恢复上次保存的搜索关键词
        if (old_state := await self.async_get_last_state()) is not None:
            self._attr_native_value = old_state.state
            _LOGGER.debug(f"恢复搜索关键词: {self._attr_native_value}")

    async def async_set_value(self, value: str) -> None:
        """设置搜索关键词"""
        self._attr_native_value = value
        self.async_write_ha_state()
        _LOGGER.debug(f"更新搜索关键词: {value}")
