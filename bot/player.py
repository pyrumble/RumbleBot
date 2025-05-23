import wavelink
import discord
import datetime

class CustomPlayer(wavelink.Player):

    def __init__(
        self, client: discord.Client, channel, *, nodes: list | None = None
    ) -> None:
        super().__init__(client, channel, nodes=nodes)
        self.__stored_data = {}
        self.backpack: list[wavelink.Playable] = []

    def store(self, key: str, value):
        """Store any key=value in the player's dict"""
        self.__stored_data[key] = value

    def get_formatted_track_album(self, t: wavelink.Playable):
        return (
            f"[{t.album.name}]({t.album.url})"
            if t.album.name and t.album.url
            else t.album.name if t.album.name
            else None
        )

    def ms_to_formatted_time(self, ms: int):
        tiempo_total_s = datetime.timedelta(milliseconds=float(ms))
        tiempo_total_e = datetime.timedelta(seconds=tiempo_total_s.seconds)
        return tiempo_total_e

    def get_formatted_track_title(self, t: wavelink.Playable):
        return f"[{t.title}]({t.uri})" if t.uri else f"`{t.title}`"

    def get_formatted_track_author(self, t: wavelink.Playable):
        return f"[{t.author}]({t.artist.url})" if t.artist.url else f"__{t.author}__"

    def member_in_vc(self, member: discord.Member):
        """Returns True if the member is in the player's voice channel"""
        if member.voice is not None:
            return (
                True if member.voice.channel == self.guild.me.voice.channel else False
            )
        return False

    def fetch(self, key: str):
        """Fetch a value from the player's dict"""

        return self.__stored_data[key] if key in self.__stored_data else None

    async def pause(self, value: bool) -> None:
        await super().pause(value)
      
    def remove_key(self, key: str):
        """Remove a key from the player's dict"""
        if key in self.__stored_data:
            del self.__stored_data[key]

    def get_current_track_pos(self) -> datetime.timedelta:
        tiempo_ahora_s = datetime.timedelta(milliseconds=float(self.position))
        tiempo_ahora_e = datetime.timedelta(seconds=tiempo_ahora_s.seconds)
        return tiempo_ahora_e

    def get_current_track_len(self) -> datetime.timedelta:
        tiempo_total_s = datetime.timedelta(milliseconds=float(self.current.length))
        tiempo_total_e = datetime.timedelta(seconds=tiempo_total_s.seconds)
        return tiempo_total_e

    async def stop(self, clear_queues: bool = False, disconnect: bool = False):
        """|coro|

        Stop the player"""

        if clear_queues:
            self.queue.clear()
            self.backpack.clear()
            self.auto_queue.clear()
            self.queue.history.clear()
        await self.skip(force=True)
        if disconnect:
            await self.disconnect()

    async def prev(self):
        """|coro|

        Plays the previous track
        
        Raises: IndexError
        """
        index = len(self.backpack) - 1
        if index < 0:
            raise IndexError()
        
        if self.current:
            self.queue.put_at(0,self.current)
        await self.play(self.backpack[index])
        del self.backpack[index]
        
    

    async def replay(self):
        """|coro|

        Replays the current track
        
        Raises: AttributeError
        """
        track = self.current
        if not track:
            raise AttributeError
        if self.paused:
            await self.pause(False)

        await self.play(track)

        