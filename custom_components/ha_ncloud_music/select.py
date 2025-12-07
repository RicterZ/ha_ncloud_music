"""Select platform for ha_ncloud_music integration.
提供搜索结果选择实体，用户选择后直接播放。
"""
import logging
from typing import List
from homeassistant.components.select import SelectEntity
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN, MediaType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from datetime import timedelta

from .const import (
    ENTITY_NAME_SEARCH_RESULTS,
    DATA_SEARCH_RESULTS,
    DATA_LAST_UPDATE,
    DATA_KEYWORD,
)
from .manifest import manifest

_LOGGER = logging.getLogger(__name__)

DOMAIN = manifest.domain


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置 select 实体平台"""
    async_add_entities([CloudMusicSearchResults(hass, entry)])


class CloudMusicSearchResults(SelectEntity):
    """云音乐搜索结果选择实体
    
    动态监听共享数据的变化，更新选项列表。
    用户选择歌曲后，自动调用媒体播放器播放。
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """初始化搜索结果选择实体"""
        self.hass = hass
        self._entry = entry
        self._attr_name = f"{manifest.name} 搜索结果"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{ENTITY_NAME_SEARCH_RESULTS}"
        self._attr_icon = "mdi:playlist-music"
        
        # 初始状态
        self._attr_options = ["暂无搜索结果"]
        self._attr_current_option = "暂无搜索结果"
        
        # 缓存：存储选项到 MusicInfo 的映射
        self._music_map = {}
        self._last_update_time = 0
        
        # 共享数据键
        self._search_data_key = f'{DOMAIN}_{entry.entry_id}_search_data'

    @property
    def device_info(self):
        """返回设备信息"""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": manifest.name,
            "manufacturer": "shaonianzhentan",
            "model": "Cloud Music",
            "sw_version": manifest.version,
        }

    async def async_added_to_hass(self) -> None:
        """实体添加到 Home Assistant 时设置轮询更新"""
        await super().async_added_to_hass()
        
        # 每秒检查一次共享数据是否更新
        async_track_time_interval(
            self.hass,
            self._async_check_update,
            timedelta(seconds=1)
        )
        
        # 立即检查一次
        await self._async_check_update(None)

    @callback
    async def _async_check_update(self, now) -> None:
        """检查共享数据是否有更新"""
        search_data = self.hass.data.get(self._search_data_key)
        if search_data is None:
            return

        # 检查时间戳是否更新
        last_update = search_data.get(DATA_LAST_UPDATE, 0)
        if last_update <= self._last_update_time:
            return

        # 数据已更新，刷新选项列表
        self._last_update_time = last_update
        await self._async_refresh_options()

    async def _async_refresh_options(self) -> None:
        """从共享数据刷新选项列表"""
        search_data = self.hass.data.get(self._search_data_key)
        if search_data is None:
            return

        music_list = search_data.get(DATA_SEARCH_RESULTS, [])
        keyword = search_data.get(DATA_KEYWORD, '')

        if not music_list:
            # 空结果
            self._attr_options = [f"未找到"{keyword}"的搜索结果"]
            self._attr_current_option = self._attr_options[0]
            self._music_map = {}
            _LOGGER.debug("搜索结果为空，清空选项列表")
        else:
            # 格式化选项：歌手 - 歌名
            new_options = []
            new_music_map = {}
            
            for music_info in music_list:
                # 格式：歌手 - 歌名
                option_text = f"{music_info.singer} - {music_info.song}"
                new_options.append(option_text)
                new_music_map[option_text] = music_info

            self._attr_options = new_options
            self._attr_current_option = new_options[0] if new_options else "暂无搜索结果"
            self._music_map = new_music_map
            
            _LOGGER.info(f"已更新搜索结果选项，共 {len(new_options)} 首歌曲")

        # 通知 Home Assistant 状态已更新
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """用户选择歌曲时触发播放
        
        这是核心交互逻辑：选择即播放，无需二次确认。
        """
        self._attr_current_option = option
        self.async_write_ha_state()

        # 检查是否是占位符选项
        if option.startswith("未找到") or option == "暂无搜索结果":
            _LOGGER.debug(f"选择了占位符选项: {option}")
            return

        # 从映射中获取对应的 MusicInfo
        music_info = self._music_map.get(option)
        if music_info is None:
            _LOGGER.warning(f"未找到选项对应的歌曲信息: {option}")
            self.hass.components.persistent_notification.create(
                f"歌曲信息丢失: {option}",
                title="播放失败"
            )
            return

        # 查找云音乐媒体播放器
        media_player_entity_id = None
        for entity_id in self.hass.states.async_entity_ids(MEDIA_PLAYER_DOMAIN):
            state = self.hass.states.get(entity_id)
            if state and state.attributes.get('platform') == 'cloud_music':
                media_player_entity_id = entity_id
                break

        if media_player_entity_id is None:
            _LOGGER.warning("未找到云音乐媒体播放器")
            self.hass.components.persistent_notification.create(
                "未找到云音乐媒体播放器，请先配置媒体播放器",
                title="播放失败"
            )
            return

        # 调用媒体播放器播放歌曲
        _LOGGER.info(f"播放选中歌曲: {music_info.song} - {music_info.singer} (URL: {music_info.url})")
        try:
            # 使用歌曲的播放 URL
            await self.hass.services.async_call(
                MEDIA_PLAYER_DOMAIN,
                'play_media',
                {
                    'entity_id': media_player_entity_id,
                    'media_content_id': music_info.url,
                    'media_content_type': MediaType.MUSIC,
                },
                blocking=True
            )
            _LOGGER.info(f"开始播放: {music_info.singer} - {music_info.song}")
            
            # 可选：显示友好通知
            self.hass.components.persistent_notification.create(
                f"正在播放: {music_info.singer} - {music_info.song}",
                title="云音乐播放"
            )
            
        except Exception as e:
            _LOGGER.error(f"播放歌曲失败: {e}", exc_info=True)
            self.hass.components.persistent_notification.create(
                f"播放失败: {str(e)}",
                title="云音乐播放错误"
            )
