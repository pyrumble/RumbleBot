import importlib
import bot.player as customplayer
import bot.views as views
import bot.enums as misc_enums
import bot.dbmanager as dbmanager
from bot.misc import (
    cooldown_for_vote,
    cog_app_command_error_handler,
    new_get_player,
    get_color_from_source,
    TopGGButton,
    get_emoji_from_source,
    SOURCES,
)
from typing import Optional
import wavelink
import yaml
from discord.ext import commands
import discord
import re
import asyncio
from discord import app_commands


with open("config.yml") as cfg:
    CONFIG = yaml.safe_load(cfg)

URL_REGEX = re.compile(
    r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)"
)


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        print("[Music] Loading...")
        await dbmanager.dbsetup()
        if not wavelink.Pool.nodes:
            nodes = [wavelink.Node(**i) for i in CONFIG["llnodes"]]
            await wavelink.Pool.connect(nodes=nodes, client=self.bot)
        else:
            await wavelink.Pool.reconnect()

        print("[Music] Sucess!")

    async def cog_unload(self) -> None:
        importlib.reload(customplayer)
        importlib.reload(dbmanager)
        importlib.reload(misc_enums)
        importlib.reload(views)

    async def cog_command_error(self, ctx, error) -> None:
        if isinstance(error, commands.CommandInvokeError):
            await ctx.send("Error")
        raise error

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:

        await cog_app_command_error_handler(interaction,error)

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        print(f"Node {payload.node.identifier} is ready!")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player: customplayer.CustomPlayer = payload.player
        if player is None:
            return
        buttons = views.PlayerButtons(player)
        
        asyncio.create_task(buttons.update_menu())

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player: customplayer.CustomPlayer | None = payload.player
        if player is None:
            return
        if payload.reason != "replaced":
            player.backpack.append(payload.track)

        if len(player.queue) == 0:
            menu = player.fetch("menu")
            message = player.fetch("message")
            if menu and message:
                menu._update_buttons()
                await message.edit(view=menu)

    @commands.Cog.listener()
    async def on_wavelink_track_exception(
        self, payload: wavelink.TrackExceptionEventPayload
    ):
        if not payload.player:
            return
        embed = discord.Embed(
            title="Error!",
            description=f"Unexpected error while playing `{payload.track.title}`:\n```{dict(payload.exception)}```",
            color=discord.Color.red(),
        )
        channel: discord.TextChannel = payload.player.fetch("channel")
        if channel:
            await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: customplayer.CustomPlayer):
        if not player:
            return
        channel: discord.TextChannel = player.fetch("channel")
        menu = player.fetch("menu")
        message = player.fetch("message")
        if menu != None and message != None:
            menu.disable_buttons()
            await message.edit(view=menu)
        if channel:
            embed = discord.Embed(
                title="Disconnected",
                description="Player is inactive.",
                color=discord.Color.random(),
            )
            await channel.send(
                embed=embed,
            )

        await player.disconnect()

    @app_commands.command(name="play")
    @app_commands.guild_only()
    @app_commands.choices(src=SOURCES)
    @app_commands.describe(
        query="Track title or track link",
        searchtype="Search type (ignored if query is a link)",
        src="Source (ignored if query is a link)",
    )
    @new_get_player()
    @app_commands.checks.dynamic_cooldown(cooldown_for_vote)
    async def playmusic(
        self,
        interaction: discord.Interaction,
        query: str,
        src: Optional[app_commands.Choice[str]],
        searchtype: Optional[misc_enums.SearchType],
    ):
        """Play a song in a voice channel from a link or a search query"""

        player: customplayer.CustomPlayer = interaction.guild.voice_client
        node: wavelink.Node = player.node
        await interaction.response.defer(thinking=True)
        if query.startswith(("https://www.youtube.com/watch", "https://youtu.be/")):
            return await interaction.followup.send(
                "We don't support Youtube!", ephemeral=True
            )
        
        lscompatible = {"spsearch:", "dzsearch:", "amsearch:"}
        if not searchtype:
            searchtype = misc_enums.SearchType.Track
        if not re.match(URL_REGEX, query):
            match searchtype:
                case misc_enums.SearchType.Track:
                    source = "spsearch:" if src is None else src.value
                    result: wavelink.Search = await wavelink.Playable.search(
                        query, source=source, node=node
                    )
                case misc_enums.SearchType.Album:
                    source = (
                        "spsearch:"
                        if src is None or src.value not in lscompatible
                        else src.value
                    )
                    search = f"{source}{query}"
                    data = await node.send(
                        path="v4/loadsearch",
                        params={"query": search, "types": ["album"]},
                    )
                    if len(data["albums"]) < 1:
                        return await interaction.followup.send(
                            "Couldn't find anything. Try another search query."
                        )
                    result: wavelink.Search = await wavelink.Playable.search(
                        wavelink.Playlist(data["albums"][0]).url, node=node
                    )
                case misc_enums.SearchType.Playlist:
                    source = (
                        "spsearch:"
                        if src is None or src.value not in lscompatible
                        else src.value
                    )
                    search = f"{source}{query}"
                    data = await node.send(
                        path="v4/loadsearch",
                        params={"query": search, "types": ["playlist"]},
                    )
                    if len(data["playlists"]) < 1:
                        return await interaction.followup.send(
                            "Couldn't find anything. Try another search query."
                        )
                    result: wavelink.Search = await wavelink.Playable.search(
                        wavelink.Playlist(data["playlists"][0]).url, node=node
                    )
                case misc_enums.SearchType.Artist:
                    source = (
                        "spsearch:"
                        if src is None or src.value not in lscompatible
                        else src.value
                    )
                    search = f"{source}{query}"
                    data = await node.send(
                        path="v4/loadsearch",
                        params={"query": search, "types": ["artist"]},
                    )
                    if len(data["artists"]) < 1:
                        return await interaction.followup.send(
                            "Couldn't find anything. Try another search query."
                        )
                    result: wavelink.Search = await wavelink.Playable.search(
                        wavelink.Playlist(data["artists"][0]).url, node=node
                    )
        else:
            result = await wavelink.Playable.search(query, node=node)

        if len(result) == 0:
            return await interaction.followup.send(
                "Couldn't find anything. Try another search query."
            )
        if isinstance(result, wavelink.Playlist):

            for track in result:
                track.extras = {"requester_id": interaction.user.id}
                await player.queue.put_wait(track)
            embed = discord.Embed(
                description=f"{get_emoji_from_source(result[0].source)} Added [{result.name}]({result.url}) - `{len(result)}` tracks",
                color=get_color_from_source(result[0].source),
            )

        else:
            track: wavelink.Playable = result[0]
            track.extras = {"requester_id": interaction.user.id}
            await player.queue.put_wait(track)

            embed = discord.Embed(
                description=f"{get_emoji_from_source(track.source)} Added {player.get_formatted_track_author(track)} - {player.get_formatted_track_title(track)}",
                color=get_color_from_source(track.source),
            )

        await interaction.followup.send(embed=embed)
        menu = player.fetch("menu")
        message = player.fetch("message")
        if menu != None and message != None:
            menu._update_buttons()
            await message.edit(view=menu)
        if not player.playing:
            await player.play(player.queue.get())

    @app_commands.command(name="nowplaying")
    @new_get_player()
    @app_commands.guild_only()
    @app_commands.checks.dynamic_cooldown(cooldown_for_vote)
    async def nowplaying(self, interaction: discord.Interaction):
        """Show which music is currently playing in the voice channel"""
        player: customplayer.CustomPlayer = interaction.guild.voice_client
        requester = interaction.guild.get_member(
            dict(player.current.extras)["requester_id"]
        )
        embed = discord.Embed(
            description=f"### 💿 {player.get_formatted_track_author(player.current)} - [{player.current.title}]({player.current.uri})",
            color=get_color_from_source(player.current.source),
        )
        album_name = player.get_formatted_track_album(player.current)
        if album_name is not None:
            embed.add_field(name="🗃️ Album", value=album_name, inline=False)
        embed.add_field(
            name="⏰Time",
            value=f"{player.get_current_track_pos()} / {player.get_current_track_len()}",
            inline=False,
        )

        message: discord.Message = player.fetch("message")
        if message:
            embed.add_field(
                name="⏯️ Player", value=f"[Click here]({message.jump_url})", inline=False
            )
        if player.current.artwork:
            embed.set_thumbnail(url=player.current.artwork)
        embed.add_field(name="Track added by", value=requester.mention, inline=False)
        embed.add_field(
            name="📩 Queue", value=f"`{len(player.queue)}` tracks", inline=False
        )
        embed.set_footer(
            text="Developer: pyrumble",
            icon_url=self.bot.user.display_avatar.url,
        )
        await interaction.response.send_message(
            embed=embed, ephemeral=True, view=views.NowplayingDevView()
        )

    @app_commands.command(name="replay")
    @app_commands.guild_only()
    @new_get_player()
    @app_commands.checks.dynamic_cooldown(cooldown_for_vote)
    async def replay_song(self, interaction: discord.Interaction):
        """Replay the current track"""
        player: customplayer.CustomPlayer = interaction.guild.voice_client
        await interaction.response.send_message(
            "Let's play that song again!",
            ephemeral=True,
        )
        await player.replay()

    @app_commands.command(name="queue")
    @app_commands.guild_only()
    @new_get_player()
    @app_commands.checks.dynamic_cooldown(cooldown_for_vote)
    async def queue(self, interaction: discord.Interaction):
        """Show the player's queue"""
        player: customplayer.CustomPlayer = interaction.guild.voice_client
        menu = views.QueueView(player)
        embed = await menu.get_embed()
        await interaction.response.send_message(view=menu, embed=embed)
        menu.message = await interaction.original_response()

    @app_commands.command(
        name="loop",
        description="Toggle the loop mode",
    )
    @new_get_player()
    @app_commands.checks.dynamic_cooldown(cooldown_for_vote)
    async def loopmode(self, interaction: discord.Interaction):
        player: customplayer.CustomPlayer = interaction.guild.voice_client
        if player.queue.mode == wavelink.QueueMode.normal:
            player.queue.mode = wavelink.QueueMode.loop
        elif player.queue.mode == wavelink.QueueMode.loop:
            player.queue.mode = wavelink.QueueMode.loop_all
        else:
            player.queue.mode = wavelink.QueueMode.normal

        match player.queue.mode:
            case wavelink.QueueMode.loop:
                msg = "Loop mode: track."
            case wavelink.QueueMode.loop_all:
                msg = "Loop mode: queue."
            case wavelink.QueueMode.normal:
                msg = "Loop mode: disabled."
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="playfile", description="Add an audio file to the queue")
    @app_commands.describe(track_file="Audio file")
    @new_get_player()
    @app_commands.checks.dynamic_cooldown(cooldown_for_vote)
    async def playfile(
        self, interaction: discord.Interaction, track_file: discord.Attachment
    ):
        await interaction.response.defer(thinking=True)
        if "audio" in track_file.content_type:
            player: customplayer.CustomPlayer = interaction.guild.voice_client
            result = await wavelink.Playable.search(track_file.url)
            track: wavelink.Playable = result[0]
            track.extras = {"requester_id": interaction.user.id}
            await player.queue.put_wait(track)
            embed = discord.Embed(
                description=f"Added `{track_file.filename}` to the queue",
                color=discord.Color.blue(),
            )
            await interaction.followup.send(embed=embed)
            if not player.playing:
                await player.play(player.queue.get())
        else:
            await interaction.followup.send("The file isn't an audio")


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
