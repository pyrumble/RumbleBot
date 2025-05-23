import math
import traceback
import aiohttp
import discord
from wavelink import Playable
import wavelink
from bot.misc import (
    get_color_from_source,
    get_logo_path_from_source,
    truncate_string,
)
from .player import CustomPlayer
from easy_pil import Editor, Font, load_image_async

API_URL = "http://localhost:8000"


class EditPlaylistModal(discord.ui.Modal):
    def __init__(self, plid: int):
        self.plid = plid
        super().__init__(title="Edit playlist", timeout=120)

    playlist_name = discord.ui.TextInput(
        label="name", style=discord.TextStyle.short, required=False
    )
    description = discord.ui.TextInput(
        label="Description", style=discord.TextStyle.short, required=False
    )
    thumbnail_url = discord.ui.TextInput(
        label="Thumbnail url", style=discord.TextStyle.short, required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        async with aiohttp.ClientSession() as session:
            async with session.patch(
                API_URL + f"/playlist/{self.plid}/",
                json={
                    "name": self.playlist_name.value,
                    "description": self.description.value,
                    "thumbnail_url": self.thumbnail_url.value,
                },
                headers={"master-key": interaction.client.api_master_key},
            ) as response:
                await interaction.response.defer(ephemeral=True)
                cpanel = await interaction.original_response()
                if response.status == 200:
                    resp = await response.json()
                    edited = dict(resp).get("edited")
                    
                    if edited:
                        await interaction.followup.send(f"Playlist edited sucessfully:\nChanges: {", ".join(f"`{i}`" for i in edited)}",ephemeral=True)
                    else:
                        await interaction.followup.send("Cancelled",ephemeral=True)
                    await cpanel.delete(delay=0.1)
                else:
                    await interaction.followup.send(
                        f"Back-end error! {response.status}",ephemeral=True
                        )


class BasePagination(discord.ui.View):
    def __init__(self, timeout: float | None):
        self.current_pag: int = 1
        self.start: int = (self.current_pag - 1) * 10
        self.end: int = self.start + 10
        super().__init__(timeout=timeout)

    async def get_embed(self):
        return self._generate_embed()

    def _update_buttons(self): ...

    def _generate_embed(self) -> discord.Embed: ...

    @discord.ui.button(label="<-")
    async def go_back(self, interaction: discord.Interaction, button):
        self.current_pag -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=await self.get_embed(), view=self)

    @discord.ui.button(label="->")
    async def go_next(self, interaction: discord.Interaction, button):
        self.current_pag += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=await self.get_embed(), view=self)


class QueueView(BasePagination):
    def __init__(self, player: CustomPlayer):
        self.player = player
        self.current_pag: int = 1
        self.start: int = (self.current_pag - 1) * 10
        self.end: int = self.start + 10
        super().__init__(timeout=40)
        self._update_buttons()

    async def get_embed(self):
        return self._generate_embed()

    def _update_buttons(self):
        self.pages = math.ceil(len(self.player.queue) / 10)
        if self.pages == 0:
            self.pages = 1
        self.clear_queue.disabled = True if len(self.player.queue) == 0 else False
        self.go_back.disabled = True if self.current_pag == 1 else False
        self.go_next.disabled = True if self.current_pag == self.pages else False

    def _generate_embed(self) -> discord.Embed:
        self.start: int = (self.current_pag - 1) * 10
        self.end: int = self.start + 10
        current = self.player.current
        embed = discord.Embed(
            title="Queue",
            description=f"**Now playing:** 💿 [{truncate_string(current.title,20)}]({current.uri}) `{self.player.ms_to_formatted_time(current.length)}`\n",
            color=discord.Color.random(),
        )
        if len(self.player.queue) > 0:
            for i, track in enumerate(
                list(self.player.queue)[self.start : self.end], start=self.start
            ):
                embed.description += f"\n**{i+1}-** [{truncate_string(track.title,30)}]({track.uri}) `{self.player.ms_to_formatted_time(track.length)}`"
            embed.set_footer(text=f"Pag {self.current_pag} of {self.pages}")
        else:
            embed.description += "\nQueue is empty!"
        return embed

    @discord.ui.button(label="Clear queue", style=discord.ButtonStyle.danger)
    async def clear_queue(self, interaction: discord.Interaction, button):
        self.player.queue.clear()
        self._update_buttons()
        await interaction.response.send_message(
            "Queue cleared sucessfully.", ephemeral=True
        )
        await self.message.edit(view=self, embed=await self.get_embed())


class CustomPlaylistPagination(BasePagination):
    def __init__(self, plid: int, userid: str):
        self.userid = userid
        self.current_pag: int = 1
        self.start: int = (self.current_pag - 1) * 10
        self.end: int = self.start + 10
        self.plid = plid
        super().__init__(timeout=60)
        self.plownerid: str = None
        self.plname: str = None
        self.pldesc: str | None = None
        self.plartworkurl: str | None = None
        self.tracks: list[tuple[dict]] = []
        self.pltotaltracks: int = None

    async def setup(self):
        async with aiohttp.ClientSession(API_URL) as session:
            async with session.get(
                f"/playlist/{self.plid}", json={ "user_id": self.userid}
            ) as response:
                pl_data = await response.json()
                self.plownerid = pl_data[1]
                self.plname = pl_data[2]
                self.pldesc = pl_data[3]
                self.plartworkurl = pl_data[4]
            async with session.get(f"/playlist/{self.plid}/tracks/") as response:
                if response.status == 200:
                    resp = await response.json()
                    node = wavelink.Pool.get_node()
                    b64tracks = tuple(t[1]["track"] for t in resp)
                    if  b64tracks and len(b64tracks) > 0:   
                        track_data = await node.send("POST",path="v4/decodetracks", data=b64tracks)
                        self.tracks.extend(track_data)
                self.pltotaltracks = len(self.tracks) if self.tracks else 0

        self._update_buttons()

    def _update_buttons(self):
        self.pages = math.ceil(self.pltotaltracks / 10)
        if self.pages == 0:
            self.pages = 1

        self.go_back.disabled = True if self.current_pag == 1 else False
        self.go_next.disabled = True if self.current_pag == self.pages else False

    async def get_embed(self):
        return await self._generate_embed()

    async def _generate_embed(self) -> discord.Embed:
        self.start: int = (self.current_pag - 1) * 10
        self.end: int = self.start + 10
        embed = discord.Embed(
            title=self.plname,
            description="Item | Title",
            color=discord.Color.random(),
        )
        if self.pltotaltracks > 0:
            for i, track in enumerate(
                self.tracks[self.start : self.end], start=self.start
            ):
                embed.description += f"\n**{i+1}-** [{track['info']['title']}]({track['info']['uri']})"
            embed.set_footer(text=f"Pag {self.current_pag} of {self.pages}")
        else:
            embed.description += "\nYour playlist is empty!"
        return embed


class ManagePlaylistMenu(discord.ui.View):
    def __init__(self, plid: int, userid: str):
        self.userid = userid
        self.plid = plid
        super().__init__(timeout=60)

    async def on_timeout(self):
        for i in self.children:
            i.disabled = True
        if self.message:
            await self.message.edit(view=self)

    @discord.ui.button(label="Edit playlist", style=discord.ButtonStyle.blurple)
    async def edit_playlist(self, interaction: discord.Interaction, button):
        modal = EditPlaylistModal(self.plid)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Show tracks", style=discord.ButtonStyle.blurple)
    async def ls_tracks(self, interaction: discord.Interaction, button):
        menu = CustomPlaylistPagination(self.plid, self.userid)
        await menu.setup()
        embed = await menu.get_embed()
        await interaction.response.send_message(view=menu, embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Delete all tracks", style=discord.ButtonStyle.danger, row=1
    )
    async def _clear_pl(self, interaction, button):
       async with aiohttp.ClientSession(API_URL) as session:
            async with session.delete(
                f"/playlist/{self.plid}/tracks",
                json={"user_id": str(interaction.user.id)},
                headers={"master-key": interaction.client.api_master_key},
            ) as response:
                if response.status == 200:
                    await interaction.response.defer(ephemeral=True)
                    cpanel = await interaction.original_response()
                    await interaction.followup.send(
                        "You've successfully deleted tracks from your playlist", ephemeral=True
                    )
                    await cpanel.delete(delay=0.1)
                else:
                    await interaction.followup.send(
                        f"Unexpected backend error: {response.status}"
                    )

    @discord.ui.button(label="DELETE PLAYLIST", style=discord.ButtonStyle.danger, row=1)
    async def _del_pl(self, interaction: discord.Interaction, button):
        async with aiohttp.ClientSession(API_URL) as session:
            async with session.delete(
                f"/playlist/{self.plid}/",
                json={"user_id": str(interaction.user.id)},
                headers={"master-key": interaction.client.api_master_key},
            ) as response:
                if response.status == 200:
                    await interaction.response.defer(ephemeral=True)
                    cpanel = await interaction.original_response()
                    await interaction.followup.send(
                        "Playlist deleted sucessfully.",
                    )
                    await cpanel.delete(delay=0.1)
                else:
                    await interaction.followup.send(
                        f"Unexpected backend error: {response.status}"
                    )


class NowplayingDevView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Debug", emoji="💻")
    async def extra(self, interaction: discord.Interaction, button):
        if interaction.user.id != 1340860785680978080:
            return await interaction.response.send_message(
                "You can't use this button. :(",
                ephemeral=True,
            )
        player: CustomPlayer | None = interaction.guild.voice_client
        if not player:
            return
        desc = f"""
Track Source: `{player.current.source}`
Track ISRC: `{player.current.isrc}`
Player Node: `{player.node.identifier}`
Track extras: 
```
{dict(player.current.extras)}
```
"""
        embed = discord.Embed(title="Current track & player info", description=desc)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class PlayerButtons(discord.ui.View):

    def __init__(self, player: CustomPlayer):
        self.player = player
        super().__init__(timeout=None)

    async def get_img(self):
        current = self.player.current

        # Configuración de tamaños y posiciones
        BG_SIZE = (350, 180)
        LOGO_SIZE = (30, 30)
        TRACK_IMG_SIZE = (100, 100)
        BOT_LOGO_SIZE = (25, 25)

        # Cargar la imagen de fondo
        bg = Editor("./bot/img/track_start_bg.png").resize(BG_SIZE)

        # Insertar logo de la fuente (Spotify, YouTube, etc.)
        logo = (
            Editor(get_logo_path_from_source(current.source))
            .circle_image()
            .resize(LOGO_SIZE)
        )
        bg.paste(logo, (10, 10))

        # Definir fuentes
        font_bold = Font.poppins(variant="bold", size=15)
        font_light = Font.poppins(size=16, variant="light")
        font_italic = Font.poppins(size=14, variant="italic")

        # Texto principal
        bg.text((50, 17), "Now playing...", font=font_bold, color="white")

        # Marco para la imagen del track
        bg.rectangle((7, 47), width=105, height=106, color="lightgray", stroke_width=1)

        # Barra de color lateral
        color_rgb = get_color_from_source(current.source).to_rgb()
        bg.rectangle((0, 0), width=3, height=180, color=color_rgb, stroke_width=1)

        # Insertar imagen del track si está disponible
        if current.artwork:
            track_img = await load_image_async(current.artwork)
            if track_img:
                track_logo = Editor(track_img).resize(TRACK_IMG_SIZE)
                bg.paste(track_logo, (10, 50))

        # Insertar logo del bot
        bot_logo_img = await load_image_async(
            self.player.client.user.display_avatar.url
        )
        if bot_logo_img:
            bot_logo = Editor(bot_logo_img).circle_image().resize(BOT_LOGO_SIZE)
            bg.paste(bot_logo, (195, 145))

        # Texto del pie
        bg.text((225, 150), "RumbleBot", font=font_light, color="white")
        bg.text(
            (120, 70), truncate_string(current.title), font=font_light, color="white"
        )
        bg.text(
            (120, 100), truncate_string(current.author), font=font_italic, color="white"
        )

        return bg

    def _update_buttons(self):
        self.prev_song.disabled = len(self.player.backpack) < 1
        self.pause_resume.disabled = not self.player.playing
        self.queue.disabled = not self.player.playing
        self.replay.disabled = not self.player.playing
        self.next_song.disabled = len(self.player.queue) < 1

    def disable_buttons(self):
        for i in self.children:
            i.disabled = True

    def enable_buttons(self):
        for i in self.children:
            i.disabled = False

    async def update_menu(self):
        channel = self.player.fetch("channel")
        track_start_img = await self.get_img()
        file = discord.File(fp=track_start_img.image_bytes, filename="img.png")

        old_message: discord.Message = self.player.fetch("message")
        if old_message:
            self.player.remove_key("menu")
            self.player.remove_key("message")
            await old_message.edit(view=None)

        buttons = PlayerButtons(self.player)
        buttons._update_buttons()
        buttons.message = await channel.send(silent=True, view=buttons, files=(file,))
        self.player.store("menu", buttons)
        self.player.store("message", buttons.message)

    @discord.ui.button(
        emoji="<:replay:1332401801881718846>", style=discord.ButtonStyle.gray
    )
    async def replay(self, interaction, button):
        if not self.player.member_in_vc(interaction.user):
            return await interaction.response.send_message(
                "You're not in a voice channel or you're not in my voice channel.",
                ephemeral=True,
            )
        await interaction.response.send_message(
            "Let's play that song again!",
            ephemeral=True,
        )
        await self.player.replay()

    @discord.ui.button(
        emoji="<:stop:1200837670151127180>", style=discord.ButtonStyle.danger
    )
    async def disconnect_player(self, interaction: discord.Interaction, button):
        if not self.player.member_in_vc(interaction.user):
            return await interaction.response.send_message(
                "You're not in a voice channel or you're not in my voice channel.",
                ephemeral=True,
            )
        await self.player.stop(clear_queues=True, disconnect=True)
        self.disable_buttons()
        await interaction.response.edit_message(view=self)
        embed = discord.Embed(
            title="Disconnected",
            description=f"Player disconnected by {interaction.user.mention}",
            color=discord.Color.random(),
        )
        await interaction.followup.send(embed=embed)

    @discord.ui.button(
        emoji="<:queue:1332722382393315401>", style=discord.ButtonStyle.gray
    )
    async def queue(self, interaction: discord.Interaction, button):
        menu = QueueView(self.player)
        embed = await menu.get_embed()
        await interaction.response.send_message(view=menu, embed=embed, ephemeral=True)
        menu.message = await interaction.original_response()

    @discord.ui.button(
        emoji="<:prev:1234650501971316867>",
        style=discord.ButtonStyle.blurple,
        row=1,
    )
    async def prev_song(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not self.player.member_in_vc(interaction.user):
            return await interaction.response.send_message(
                "You're not in a voice channel or you're not in my voice channel.",
                ephemeral=True,
            )
        try:
            await interaction.response.defer()
            if self.player.paused:
                await self.player.pause(False)
            await self.player.prev()

        except IndexError:
            pass

    @discord.ui.button(
        emoji="<:pausa:1200841413710065704>",
        style=discord.ButtonStyle.blurple,
        row=1,
    )
    async def pause_resume(self, interaction: discord.Interaction, button):
        if not self.player.member_in_vc(interaction.user):
            return await interaction.response.send_message(
                "You're not in a voice channel or you're not in my voice channel.",
                ephemeral=True,
            )
        await self.player.pause(not self.player.paused)
        button.style = (
            discord.ButtonStyle.green
            if self.player.paused
            else discord.ButtonStyle.blurple
        )
        button.emoji = (
            "<:play:1200837254990549072>"
            if self.player.paused
            else "<:pausa:1200841413710065704>"
        )
        await interaction.response.edit_message(view=self)

    @discord.ui.button(
        emoji="<:skip:1234650741701087314>",
        style=discord.ButtonStyle.blurple,
        row=1,
    )
    async def next_song(self, interaction: discord.Interaction, button):
        await interaction.response.defer()
        if not self.player.member_in_vc(interaction.user):
            return await interaction.response.send_message(
                "You're not in a voice channel or you're not in my voice channel.",
                ephemeral=True,
            )

        if self.player.paused:
            await self.player.pause(False)
        await self.player.skip()


__all__ = [
    "PlayerButtons",
    "NowplayingDevView",
    "ManagePlaylistMenu",
    "QueueView",
    "CustomPlaylistPagination",
]
