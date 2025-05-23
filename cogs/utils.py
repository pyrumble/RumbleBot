import json
import discord
from discord.ext import commands
import os
from discord import app_commands
import wavelink
from bot.misc import cog_app_command_error_handler, cooldown_for_vote
import bot.player as customplayer


async def reload_cogs(bot: commands.Bot):
    for file in os.listdir("./cogs"):
        if file.endswith(".py"):
            await bot.reload_extension(f"cogs.{file[:-3]}")

class Utils(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        super().__init__()

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await cog_app_command_error_handler(interaction,error)

    @commands.command(name="sync")
    async def sync_cmd(self, ctx: commands.Context):
        if await self.bot.is_owner(ctx.author):
            cmds = len(await self.bot.tree.sync())
            await ctx.send(cmds)

    @commands.command(name="reload")
    async def reloadcogs(self, ctx: commands.Context):
        if await self.bot.is_owner(ctx.author):
            await reload_cogs(self.bot)
            await ctx.send("Sucess.")

    @commands.command()
    @commands.is_owner()
    async def fetch_nodes(self, ctx):
        nodes = wavelink.Pool.nodes
        embed = discord.Embed(title="Lavalink Nodes")
        for name, node in nodes.items():
            desc = f"""
Players: `{len(node.players)}`
LL version: `{await node.fetch_version()}`
"""
            embed.add_field(name=name, value=desc)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def node_info(self, ctx: commands.Context, node: str):
        node: wavelink.Node = wavelink.Pool.get_node(node)
        info = await node.fetch_info()
    
        desc = f"""
Players: `{len(node.players)}`
JVM: `{info.jvm}`
LP version: `{info.lavaplayer}`
LL version: `{info.version.semver}`
Plugins: ```{tuple((p.__dict__ for p in info.plugins))}```
"""
        embed = discord.Embed(title=f"Node {node.identifier} info", description=desc)

        await ctx.send(embed=embed)

    @app_commands.command(name="info", description="What is this?")
    @app_commands.checks.dynamic_cooldown(cooldown_for_vote)
    async def info(self, interaction: discord.Interaction):
        desc = """
Best discord music bot. It supports Spotify, Deezer, Apple Music and Soundcloud.

__**Features**__
- Powered by **Lavalink**
- Custom playlists `/playlist`
- Advanced `/play` command
"""
        embed = discord.Embed(
            title="RumbleBot", description=desc, color=discord.Colour.yellow()
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text=f"Developer: pyrumble")
        await interaction.response.send_message(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def fetch_players(self, ctx: commands.Context):
        text = ""
        for node in wavelink.Pool.nodes:
            for player in wavelink.Pool.get_node(node).players:
                text += f"Node: `{node}`, Player: `{player}`\n"
        await ctx.send(text)

    @commands.command()
    @commands.is_owner()
    async def fetch_player(self,ctx: commands.Context, playerid: str):
        for node in wavelink.Pool.nodes.values():
            if int(playerid) in wavelink.Pool.get_node(node.identifier).players.keys():
                data = await node.send("GET", path=f"v4/sessions/{node.session_id}/players/{playerid}")
                with open(f"playerdata-{playerid}.json", "w") as f:
                    json.dump(data, f, indent=4)  
                with open(f"playerdata-{playerid}.json", "r") as f:              
                    await ctx.send("Player data is too long! Check attached file.", file=discord.File(f,filename=f"playerdata-{playerid}.json"))
                    os.remove(f"playerdata-{playerid}.json")



    @app_commands.command(name="stats", description="Show RumbleBot's stats")
    @app_commands.checks.dynamic_cooldown(cooldown_for_vote)
    async def stats(self, interaction: discord.Interaction):
        embed = discord.Embed(title="RumbleBot's stats", color=discord.Color.random(),timestamp=discord.utils.utcnow())
        players = 0
        for n in wavelink.Pool.nodes:
            for _ in wavelink.Pool.nodes[n].players:          
                players += 1
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.add_field(name="🎶 Players", value=f"There's {players} players.", inline=False)
        embed.add_field(name="🗃️ Guilds",value=f"{len(self.bot.guilds)} discord guilds!",inline=False)
        embed.add_field(name="🔗 Lavalink nodes", value=f"{len(wavelink.Pool.nodes)} nodes.", inline=False)
        embed.add_field(name="📡 Ping", value=f"{round(self.bot.latency * 1000)}ms", inline=False)
        await interaction.response.send_message(embed=embed)
        

async def setup(bot):
    await bot.add_cog(Utils(bot))
