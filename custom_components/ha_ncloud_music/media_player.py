import logging, datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.media_player.const import MediaPlayerEntityFeature
from homeassistant.const import (
    CONF_URL,
    CONF_NAME,
    STATE_OFF, 
    STATE_ON, 
    STATE_PLAYING,
    STATE_PAUSED,
    STATE_IDLE,
)

from .manifest import manifest

DOMAIN = manifest.domain

_LOGGER = logging.getLogger(__name__)

SUPPORT_FEATURES = MediaPlayerEntityFeature.VOLUME_STEP | MediaPlayerEntityFeature.VOLUME_MUTE | MediaPlayerEntityFeature.VOLUME_SET | \
    MediaPlayerEntityFeature.PLAY_MEDIA | MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.PAUSE | MediaPlayerEntityFeature.PREVIOUS_TRACK | MediaPlayerEntityFeature.NEXT_TRACK | \
    MediaPlayerEntityFeature.BROWSE_MEDIA | MediaPlayerEntityFeature.SEEK | MediaPlayerEntityFeature.CLEAR_PLAYLIST | MediaPlayerEntityFeature.SHUFFLE_SET | MediaPlayerEntityFeature.REPEAT_SET

# 定时器时间
TIME_BETWEEN_UPDATES = datetime.timedelta(seconds=1)
UNSUB_INTERVAL = None

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:

    entities = []
    for source_media_player in entry.options.get('media_player', []):
      entities.append(CloudMusicMediaPlayer(hass, source_media_player))

    def media_player_interval(now):
      for mp in entities:
        mp.interval(now)

    # 开启定时器
    global UNSUB_INTERVAL
    if UNSUB_INTERVAL is not None:
      UNSUB_INTERVAL()
    UNSUB_INTERVAL = async_track_time_interval(hass, media_player_interval, TIME_BETWEEN_UPDATES)

    async_add_entities(entities, True)

class CloudMusicMediaPlayer(MediaPlayerEntity):

    def __init__(self, hass, source_media_player):
        self.hass = hass
        self._attributes = {
            'platform': 'cloud_music'
        }
        # fixed attribute
        self._attr_media_image_remotely_accessible = True
        self._attr_device_class = 'tv'
        self._attr_supported_features = SUPPORT_FEATURES

        # default attribute
        self.source_media_player = source_media_player
        self._attr_name = f'{manifest.name} {source_media_player.split(".")[1]}'
        self._attr_unique_id = f'{manifest.domain}{source_media_player}'
        self._attr_state =  STATE_ON
        self._attr_volume_level = 1
        self._attr_repeat = 'all'
        self._attr_shuffle = False

        self.cloud_music = hass.data['cloud_music']
        self.before_state = None
        self.current_state = None
        self._last_position_update = None

    def interval(self, now):
        """定时器回调 - 参考lsCoding666实现"""
        # 暂停时不更新
        if self._attr_state != STATE_PLAYING:
            return
        
        # 获取当前时间
        new_updated_at = datetime.datetime.now()
        
        # 自主计时（每秒+1）
        if not hasattr(self, '_last_position_update') or self._last_position_update is None:
            self._last_position_update = new_updated_at
            self._attr_media_position = 0
        else:
            self._attr_media_position += 1
            self._last_position_update = new_updated_at
            self._attr_media_position_updated_at = datetime.datetime.now(datetime.timezone.utc)
        
        # 从底层读取duration
        media_player = self.media_player
        if media_player is not None:
            attrs = media_player.attributes
            self._attr_media_duration = int(attrs.get('media_duration', 0))
            
            # 判断是否下一曲（lsCoding666的逻辑）
            if self.before_state is not None:
                if self.before_state['media_duration'] > 0:
                    delta = self._attr_media_duration - self._attr_media_position
                    if delta <= 1 and self._attr_media_duration > 1:
                        self._attr_state = STATE_PAUSED
                        self.before_state = None
                        self.hass.loop.call_soon_threadsafe(
                            lambda: self.hass.create_task(self.async_media_next_track())
                        )
                        return
                
                # 补充：如果底层变off（MPD播完后）
                if media_player.state == STATE_OFF and self._attr_state == STATE_PLAYING:
                    self._attr_state = STATE_PAUSED
                    self.before_state = None
                    self.hass.loop.call_soon_threadsafe(
                        lambda: self.hass.create_task(self.async_media_next_track())
                    )
                    return
            
            # 更新状态记录
            self.before_state = {
                'media_position': int(self._attr_media_position),
                'media_duration': int(self._attr_media_duration),
                'state': media_player.state
            }
            self.current_state = media_player.state
        
        # 更新元数据
        if hasattr(self, 'playlist'):
            music_info = self.playlist[self.playindex]
            self._attr_app_name = music_info.singer
            self._attr_media_image_url = music_info.thumbnail
            self._attr_media_album_name = music_info.album
            self._attr_media_title = music_info.song
            self._attr_media_artist = music_info.singer
        
        # 立即通知HA更新界面
        self.hass.loop.call_soon_threadsafe(self.async_write_ha_state)

    @property
    def media_player(self):
        if self.entity_id is not None and self.source_media_player is not None:
            return self.hass.states.get(self.source_media_player)

    @property
    def device_info(self):
        return {
            'identifiers': {
                (DOMAIN, manifest.documentation)
            },
            'name': self.name,
            'manufacturer': 'shaonianzhentan',
            'model': 'CloudMusic',
            'sw_version': manifest.version
        }

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_browse_media(self, media_content_type=None, media_content_id=None):
        return await self.cloud_music.async_browse_media(self, media_content_type, media_content_id)

    async def async_volume_up(self):
        await self.async_call('volume_up')

    async def async_volume_down(self):
        await self.async_call('volume_down')

    async def async_mute_volume(self, mute):
        self._attr_is_volume_muted = mute
        await self.async_call('mute_volume', { 'is_volume_muted': mute })

    async def async_set_volume_level(self, volume: float):
        self._attr_volume_level = volume
        await self.async_call('volume_set', { 'volume_level': volume })

    async def async_play_media(self, media_type, media_id, **kwargs):

        self._attr_state = STATE_PAUSED
        # 重置进度计时
        self._attr_media_position = 0
        self._attr_media_position_updated_at = datetime.datetime.now(datetime.timezone.utc)
        self._last_position_update = None
        
        media_content_id = media_id
        result = await self.cloud_music.async_play_media(self, self.cloud_music, media_id)
        if result is not None:
            if result == 'index':
                # 播放当前列表指定项
                media_content_id = self.playlist[self.playindex].url
            elif result.startswith('http'):
                # HTTP播放链接
                media_content_id = result
            else:
                # 添加播放列表到播放器
                media_content_id = self.playlist[self.playindex].url

        self._attr_media_content_id = media_content_id
        await self.async_call('play_media', {
            'media_content_id': media_content_id,
            'media_content_type': 'music'
        })
        self._attr_state = STATE_PLAYING

        self.before_state = None

    async def async_media_play(self):
        self._attr_state = STATE_PLAYING
        await self.async_call('media_play')

    async def async_media_pause(self):
        self._attr_state = STATE_PAUSED
        await self.async_call('media_pause')

    async def async_set_repeat(self, repeat):
        self._attr_repeat = repeat

    async def async_set_shuffle(self, shuffle):
        self._attr_shuffle = shuffle

    async def async_media_next_track(self):
        self._attr_state = STATE_PAUSED
        await self.cloud_music.async_media_next_track(self, self._attr_shuffle)

    async def async_media_previous_track(self):
        self._attr_state = STATE_PAUSED
        await self.cloud_music.async_media_previous_track(self, self._attr_shuffle)

    async def async_media_seek(self, position):
        # 重置自主计时
        self._attr_media_position = position
        self._last_position_update = datetime.datetime.now()
        self._attr_media_position_updated_at = datetime.datetime.now(datetime.timezone.utc)
        await self.async_call('media_seek', { 'seek_position': position })

    async def async_clear_playlist(self):
        if hasattr(self, 'playlist'):
            del self.playlist

    async def async_media_stop(self):
        await self.async_call('media_stop')

    # 更新属性
    async def async_update(self):
        pass

    # 调用服务
    async def async_call(self, service, service_data={}):
        media_player = self.media_player
        if media_player is not None:
            service_data.update({ 'entity_id': media_player.entity_id })
            await self.hass.services.async_call('media_player', service, service_data)