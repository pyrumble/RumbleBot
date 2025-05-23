import time
from typing import Optional
import asqlite
import discord
import wavelink
from discord import app_commands
import bot.player as customplayer
from bot.enums import SourceEmoji
from discord import app_commands


SOURCES: list[app_commands.Choice[str]] = [
    app_commands.Choice(name="Spotify (Default)", value="spsearch:"),
    app_commands.Choice(name="Deezer", value="dzsearch:"),
    app_commands.Choice(name="Apple Music", value="amsearch:"),
    app_commands.Choice(name="Soundcloud", value="scsearch:"),
]

TEN_SECONDS_CD_CMDS = {"play", "add-track", "replay"}
SIX_SECONDS_CD_CMDS = {"check-vote", "create", "ls", "manage", "stats", "queue", "nowplaying", "playfile"} 

# Exceptions


class UserNotConnectedError(app_commands.CheckFailure):
    pass

class NotPlayingMusicError(app_commands.CheckFailure):
    pass

# Classes


class TopGGButton(discord.ui.Button):
    def __init__(
        self,
    ):
        super().__init__(
            style=discord.ButtonStyle.url,
            url="https://top.gg/bot/1341140133814079498",
            label="Go to top.gg",
        )


# decorators
def new_get_player():
    async def c(interaction: discord.Interaction):
        if not interaction.guild:
            raise app_commands.CheckFailure(
                "Guild-only command."
            )
        should_connect = interaction.command.name in ("play", "playfile")
        client: customplayer.CustomPlayer | None = interaction.guild.voice_client
        if not client:
            if should_connect:
                if not interaction.user.voice or not interaction.user.voice.channel:
                    raise UserNotConnectedError()

                vc_perms = interaction.user.voice.channel.permissions_for(
                    interaction.guild.me
                )
                missing_vc_perms = list(
                    p[0] for p in vc_perms if p[0] in ("connect", "speak") and not p[1]
                )
                if len(missing_vc_perms) > 0:
                    raise app_commands.BotMissingPermissions(
                        missing_permissions=missing_vc_perms
                    )
                channel_perms = interaction.channel.permissions_for(
                    interaction.guild.me
                )
                missing_channel_perms = list(
                    p[0]
                    for p in channel_perms
                    if p[0] in ("view_channel", "send_messages") and not p[1]
                )
                if len(missing_channel_perms) > 0:
                    raise app_commands.BotMissingPermissions(
                        missing_permissions=missing_channel_perms
                    )
                if interaction.user.voice.channel.user_limit > 0:
                    if (
                        len(interaction.user.voice.channel.members)
                        >= interaction.user.voice.channel.user_limit
                        and not interaction.guild.me.guild_permissions.move_members
                    ):
                        raise app_commands.CheckFailure("Your voice channel is full!")

                try:
                    player = await interaction.user.voice.channel.connect(
                        cls=customplayer.CustomPlayer
                    )
                    player.store("channel", interaction.channel)
                    player.autoplay = wavelink.AutoPlayMode.partial
                    player.queue.mode = wavelink.QueueMode.normal
                except discord.errors.ClientException:
                    pass
            else:
                raise NotPlayingMusicError()

        else:
            channel = client.fetch("channel")
            if channel != interaction.channel:
                raise app_commands.CheckFailure(
                    f"Player got initialized in {channel.mention}.\nYou'd use this command there!"
                )
            if not client.playing and not should_connect:
                raise NotPlayingMusicError()
            if not interaction.user.voice or not interaction.user.voice.channel:
                raise app_commands.CheckFailure(
                    f"You're not connected in my voice channel!.\nJoin here: {interaction.guild.me.voice.channel.mention}"
                )

            if (
                interaction.user.voice.channel
                and interaction.user.voice.channel != interaction.guild.me.voice.channel
            ):
                raise app_commands.CheckFailure(
                    f"I'm already connected in a voice channel and I won't move from here\nJoin here: {interaction.guild.me.voice.channel.mention}"
                )

        return True

    return app_commands.check(c)


# useful funcs

async def cooldown_for_vote(interaction: discord.Interaction) -> Optional[app_commands.Cooldown]:
    """Check if the user has voted and set a cooldown"""
    async with asqlite.connect("dynamiccooldowns.db") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT expires_at FROM cooldowns WHERE userid = ?",
                (interaction.user.id,)
            )
            result = await cursor.fetchone()
            if interaction.command.name not in TEN_SECONDS_CD_CMDS | SIX_SECONDS_CD_CMDS:
                return None
            if result and result[0] > time.time(): # Cooldown reduction
                if interaction.command.name in TEN_SECONDS_CD_CMDS:
                    return app_commands.Cooldown(1,5)
                elif interaction.command.name in SIX_SECONDS_CD_CMDS: 
                    return  app_commands.Cooldown(1,3)
            if interaction.command.name in TEN_SECONDS_CD_CMDS:
                    return app_commands.Cooldown(1,10)
            elif interaction.command.name in SIX_SECONDS_CD_CMDS:
                return app_commands.Cooldown(1,6)
      

async def cog_app_command_error_handler(interaction, error):
    if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Command in cooldown!\nTry again in {round(error.retry_after, 1)} seconds.",
                ephemeral=True,
            )
    elif isinstance(error, app_commands.BotMissingPermissions):
        await interaction.response.send_message(
            "I'm missing some permissions!\nPermissions: "
            + ", ".join(error.missing_permissions)
        )
    elif isinstance(error, UserNotConnectedError):
        await interaction.response.send_message(
            "You're not connected to a voice channel!", ephemeral=True
        )
    elif isinstance(error, NotPlayingMusicError):
        await interaction.response.send_message("There's not music playing.",ephemeral=True)
    elif isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(content=error, ephemeral=True)

    else:
        raise error

def get_color_from_source(src: str):
    match src:
        case "spotify":
            return discord.Color.green()
        case "deezer":
            return discord.Color.purple()
        case "soundcloud":
            return discord.Color.orange()
        case "applemusic":
            return discord.Color.pink()
        case "youtube":
            return discord.Color.red()
        case _:
            return discord.Color.from_rgb(255, 255, 255)


def get_logo_path_from_source(src: str):
    sources = {"deezer", "spotify", "soundcloud", "applemusic", "http", "youtube"}
    if src in sources:
        return f"./bot/img/{src}.png"
    else:
        return f"./bot/img/http.png"


def get_emoji_from_source(src: str):
    match src:
        case "spotify":
            return SourceEmoji.SPOTIFY.value
        case "deezer":
            return SourceEmoji.DEEZER.value
        case "soundcloud":
            return SourceEmoji.SOUNDCLOUD.value
        case "applemusic":
            return SourceEmoji.APPLEMUSIC.value
        case "youtube": 
            return SourceEmoji.YOUTUBE.value
        case _:
            return SourceEmoji.HTTP.value

def truncate_string(s: str, max_len: int = None) -> str:
    if not max_len: max_len = 25
    return s[:25] + "..." if len(s) > max_len else s