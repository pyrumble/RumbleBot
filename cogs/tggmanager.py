import asyncio
import asqlite
from discord.ext import commands
from discord import app_commands
from bot.misc import TopGGButton
import discord
from fastapi import FastAPI, Request
import uvicorn
import  yaml
import topgg
import  logging
import time
from bot.misc import cooldown_for_vote, cog_app_command_error_handler

logger = logging.getLogger("topgg")

class TopGGManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wh_server = None
        self.enabled = False
        with open("config.yml") as cfg:
            CONFIG: dict = yaml.safe_load(cfg)

            topgg_token = CONFIG.get("topggToken",None)
            webhook_auth = CONFIG.get("topggWebhookAuth",None)
            if not topgg_token: 
                logger.error("Top.gg token not found in config.yml!\nDisabling Top.gg integration.")
                return
            self.enabled = True           
            self.topgg = topgg.TopGG(
            bot,
            topgg_token,
            webhook_port=8001,
            webhook_auth=webhook_auth,
            )
        super().__init__()
    
    async def cog_app_command_error(self, interaction, error):
        await cog_app_command_error_handler(interaction, error)

    async def cog_load(self):
        if not self.enabled:
            return
        topgg_app = FastAPI()

        @topgg_app.post("/topggwebhook")
        async def topgg_webhook(request: Request):
            auth = request.headers.get("Authorization")
            if auth != self.topgg.webhook_auth:
                logger.warning("Unauthorized webhook request received.")
                return {"error": "Unauthorized"}, 401
            data = await request.json()
            user_id = data.get("user")
            user = await self.bot.fetch_user(user_id)
            logger.info("%s (%s) has voted for the bot! - %s", user.display_name,user.name, user.id)
            # Check if the user is already in the database
            async with asqlite.connect("dynamiccooldowns.db") as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        "SELECT * FROM cooldowns WHERE userid = ?",
                        (user_id,),
                    )
                    row = await cursor.fetchone()
                    if row:
                        # If the user is already in the database, update the expiration time
                        await cursor.execute(
                            "UPDATE cooldowns SET expires_at = ? WHERE userid = ?",
                            (time.time() + 43200, user_id),
                        )
                    else:
                        # If the user is not in the database, insert a new row
                        await cursor.execute(
                            "INSERT INTO cooldowns (userid, expires_at) VALUES (?, ?)",
                            (user_id, time.time() + 43200),
                        )
                    await conn.commit()
            embed = discord.Embed(
                title="Thank you for voting!",
                description="You've gained a 50% cooldown reduction on all commands for 12 hours. More benefits coming soon.",
                color=discord.Color.dark_red(),
            )
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            embed.set_footer(
                text="No reply to this message. If you have any questions, please contact the bot owner.",
            )
            try:
                await user.send(embed=embed)
            except discord.Forbidden as e:
                logger.warning(
                    "Can't send DM to user with id %s\nReason: %s", data["user"], e
                )
            except discord.HTTPException as e:
                logger.warning(
                    "Can't send DM to user with id %s\nReason: %s", data["user"], e
                )

            return {"status": "ok"}
        config = uvicorn.Config(app=topgg_app, host="0.0.0.0", port=8001, log_level="info")
        self.wh_server = uvicorn.Server(config)
        asyncio.create_task(self.wh_server.serve())

    async def cog_unload(self):
        if not self.enabled:
            return
        await self.wh_server.shutdown()

    @app_commands.command(name="check-vote", description="Check if you have voted or not.")
    @app_commands.checks.dynamic_cooldown(cooldown_for_vote)
    async def get_topgg(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False,thinking=True)
        if not self.enabled:    
            return await interaction.followup.send(
                embed=discord.Embed(
                    title="Top.gg",
                    description="Top.gg integration is disabled.",
                    color=discord.Color.red()
                ).set_thumbnail(url=self.bot.user.display_avatar.url),
            )
        if not await self.topgg.check_vote(interaction.user.id):
            view = discord.ui.View()
            view.add_item(TopGGButton())
            return await interaction.followup.send(
                embed=discord.Embed(
                    title="Top.gg",
                    description="You have not voted for the bot!",
                    color=discord.Color.yellow()
                ).set_thumbnail(url=self.bot.user.display_avatar.url),
                view=view,
            )
        else:
            return await interaction.followup.send("You have already voted!\nYou can vote every 12 hours.")


async def setup(bot):
    await bot.add_cog(TopGGManager(bot))
