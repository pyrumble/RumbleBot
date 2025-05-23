import aiohttp
import asqlite
import discord
import wavelink
import importlib
from bot.misc import cog_app_command_error_handler, cooldown_for_vote, new_get_player, SOURCES
from typing import Optional
import bot.player as customplayer
import bot.views as views
import bot.enums as misc_enums
import bot.dbmanager as dbmanager
from discord.ext import commands
from discord import app_commands
import re

URL_REGEX = re.compile(
    r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)"
)

API_URL = "http://localhost:8000"


@app_commands.guild_only()
class CustomPlaylist(commands.GroupCog, group_name="playlist"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.playlist_api = None
        super().__init__()

    async def cog_unload(self) -> None:
        importlib.reload(customplayer)
        importlib.reload(dbmanager)
        importlib.reload(misc_enums)
        importlib.reload(views)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:

        await cog_app_command_error_handler(interaction,error)

    @app_commands.command(name="create", description="Create a playlist")
    @app_commands.describe(name="Playlist name", desc="Playlist description")
    @app_commands.checks.dynamic_cooldown(cooldown_for_vote)
    async def create_playlist(
        self, interaction: discord.Interaction, name: str, desc: Optional[str]
    ):
        async with aiohttp.ClientSession(API_URL) as session:
            async with session.post("/playlist/", json={"user_id": str(interaction.user.id), "name": name, "description": desc}) as response:
                if response.status == 200:
                    data = await response.json()
                    pl_id = data["pl_id"]

                    await interaction.response.send_message(
                        f"Playlist created: `{name}`\n- Playlist ID: `{pl_id}`\n- Use `/playlist ls` to view your playlists.",
                        ephemeral=True,
                    )
                    await interaction.followup.send(
                        "> :warning: This custom playlist system isn't definitive! It's subject to unexpected changes, such as the total loss of data related to users' playlists.",
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(f"Backend error! `{response.status}`")

    @app_commands.command(name="add-track")
    @app_commands.choices(src=SOURCES)
    @app_commands.describe(
        plid="Playlist ID",
        query="Track title or track link",
        src="Source (ignored if query is a link)",
        searchtype="Search type (ignored if query is a link)",       
    )
    @app_commands.checks.dynamic_cooldown(cooldown_for_vote)
    async def add_track(
        self,
        interaction: discord.Interaction,
        plid: int,
        query: str,
        searchtype: Optional[misc_enums.SearchType],
        src: Optional[app_commands.Choice[str]],
    ):
        """Add a song to a custom playlist"""
        await interaction.response.defer(thinking=True)
        node: wavelink.Node = wavelink.Pool.get_node()
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
                        return await interaction.followup.send("Couldn't find anything. Try another search query.")
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
                        return await interaction.followup.send("Couldn't find anything. Try another search query.")
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
                        return await interaction.followup.send("Couldn't find anything. Try another search query.")
                    result: wavelink.Search = await wavelink.Playable.search(
                        wavelink.Playlist(data["artists"][0]).url, node=node
                    )
        else:
            result: wavelink.Search = await wavelink.Playable.search(query, node=node)

        if len(result) == 0:
            return await interaction.followup.send("Couldn't find anything. Try another search query.")
        if isinstance(result, wavelink.Playlist):
            tracks_data = []
            for track in result.tracks:
                t_data = {"user_id": str(interaction.user.id)}
                t_data.update({"encoded": track.raw_data.get("encoded")})
                tracks_data.append(t_data)

            async with aiohttp.ClientSession(API_URL) as session:
                async with session.post(
                    f"/playlist/{plid}/tracks/",
                    json={
                        "user_id": str(interaction.user.id),
                        "tracks": tracks_data,
                    },
                    headers={"master-key": self.bot.api_master_key}
                ) as response:
                    if response.status == 200:
                        pass
                    else:
                        return await interaction.followup.send(
                            f"Unexpected backend error. `{response.status}`"
                        )
            embed = discord.Embed(
                description=f"Added`{result.name}` to the playlist - `{len(result)}` tracks!",
                color=discord.Color.blue(),
            )
           
        else:
            track: wavelink.Playable = result[0]

            async with aiohttp.ClientSession(
                API_URL
            ) as session:

                async with session.post(
                     f"/playlist/{plid}/track/",
                    json={
                        "user_id": str(interaction.user.id),
                        "encoded": track.raw_data.get("encoded"),
                    },
                    headers={"master-key": self.bot.api_master_key}
                ) as response:
                    print(await response.text())
                    if response.status == 200:
                        pass
                    else:
                        return await interaction.followup.send(
                            f"Unexpected error. {response.status}"
                        )
            embed = discord.Embed(
                description=f"Added `{track.author} - {track.title}` to the playlist!",
                color=discord.Color.blue(),
            )
           
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="ls", description="Show your playlists")
    @app_commands.checks.dynamic_cooldown(cooldown_for_vote)
    async def show_all_pl(self, interaction: discord.Interaction):
        async with asqlite.connect("userplaylists.db") as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT * FROM playlists WHERE userid=?", (interaction.user.id,)
                )
                result = await cur.fetchall()
                if len(result) < 1:
                    return await interaction.response.send_message(
                        "You don't have any playlist!"
                    )
                embed = discord.Embed(
                    title=f"{interaction.user.name}'s playlists",
                    color=discord.Color.random(),
                    description="|Title| |ID| |Description|\n",
                )
                for r in result:
                    embed.description += f"- **{r[2]}** `{r[0]}` '{r[3]}'\n"
                await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="play", description="Play a custom playlist"
    )
    @app_commands.checks.dynamic_cooldown(cooldown_for_vote)
    @app_commands.describe(plid="Playlist ID")
    @new_get_player()
    async def play_pl(self, interaction: discord.Interaction, plid: int):
        player: customplayer.CustomPlayer = interaction.guild.voice_client
        await interaction.response.defer()
        async with aiohttp.ClientSession(API_URL) as session:
            async with session.get(f"/playlist/{plid}/tracks/") as response:
                if response.status == 200:
                    resp = await response.json()
                    data = tuple(((t[0], t[1]["track"]) for t in resp))

                elif 404:
                    return await interaction.followup.send(
                        f"The playlist wth ID `{plid}` doesn't have any songs or doesn't exist."
                    )
            async with session.get(f"/playlist/{plid}/", json={"user_id": str( interaction.user.id)}) as response:
                playlist = await response.json()
                owner_id = playlist[1]
                plname = playlist[2]
                thumbnail_url = playlist[4]
                desc = playlist[3]
            tracks: list[tuple[int, wavelink.Playable]] = []
            for i in data:
                raw = await player.node.send(
                    path="v4/decodetrack", params={"encodedTrack": i[1]}
                )
                tracks.append((i[0], wavelink.Playable(raw)))

        
        if not data:
            return await interaction.followup.send(
                "Your playlist is empty or not found"
            )
        embed = discord.Embed(
            description=f"Added custom playlist: **{plname}** - `{len(data)}` tracks.",
            color=discord.Color.random(),
        )
         
        embed.set_thumbnail(
            url=thumbnail_url if thumbnail_url else self.bot.user.display_avatar.url
        )
        for tid, t in tracks:
            t.extras = {
                "requester_id": interaction.user.id,
                "customPlaylist": {
                    "plId": plid,
                    "trackId": tid,
                    "name": plname,
                    "description": desc,
                    "ownerId": owner_id,
                    "totalTracks": len(tracks),
                    "artworkUrl": thumbnail_url,
                },
            }
            await player.queue.put_wait(t)
        await interaction.followup.send(embed=embed)
        menu = player.fetch("menu")
        message = player.fetch("message")
        if menu != None and message != None:
            menu._update_buttons()
            await message.edit(view=menu)
        if not player.playing:
            await player.play(player.queue.get())

    @app_commands.command(
        name="manage", description="Manage a playlist"
    )
    @app_commands.describe(plid="Playlist ID")
    @app_commands.checks.dynamic_cooldown(cooldown_for_vote)
    async def manage(self, interaction: discord.Interaction, plid: int):
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiohttp.ClientSession(API_URL) as session:
            async with session.get(
                f"/playlist/{plid}/", json={"user_id": str(interaction.user.id)}
            ) as response:
                if response.status == 200:
                    playlist_data = await response.json()
                elif response.status >= 400 and response.status < 500:
                    return await interaction.followup.send(
                        "Playlist not found"
                    )
                else:
                    return await interaction.followup.send(f"Unexpected backend error: {response.status}")
            async with session.get(f"/playlist/{plid}/tracks") as response:
                tracks = await response.json()
                total_tracks = len(tracks) if tracks else 0
                embed = discord.Embed(
                    
                    title=f"🗃️ {playlist_data[2]}", color=discord.Color.yellow()
                )
                embed.add_field(
                    name="Description",
                    value="None" if not playlist_data[3] else f"`{playlist_data[3]}`",
                    inline=False,
                )
                embed.add_field(
                    name="🎵 Tracks", value=f"`{total_tracks}` tracks"
                )
                if playlist_data[4]:
                    embed.set_thumbnail(url=playlist_data[4])
                view = views.ManageCustomPlMenu(plid, str(interaction.user.id))
                view.message = await interaction.original_response()
                await interaction.followup.send(
                    embed=embed,                               
                    view=view),
                


async def setup(bot: commands.Bot):
    await bot.add_cog(CustomPlaylist(bot))
