import asyncio
from discord.ext.commands import Bot
import aiohttp
import logging

class TopGG:
    def __init__(
        self,
        bot: Bot,
        topgg_token: str,
        webhook_port: int,
        webhook_auth: str,
        autopost_servercount: bool = True,
    ):
        self.bot = bot
        self.logger = logging.getLogger("topgg")
        self.topgg_token = topgg_token
        self.webhook_port = webhook_port
        self.webhook_auth = webhook_auth
        if autopost_servercount and bot.mode == "normal":
            asyncio.create_task(self._servercount_task())

    async def check_vote(self, user_id: int) -> bool:
        """Checks if a user has voted or not"""
        url = f"https://top.gg/api/bots/{self.bot.user.id}/check?userId={user_id}"
        headers = {"Authorization": self.topgg_token}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                json_response = await response.json()
                return bool(json_response["voted"])


    async def _servercount_task(self):
        await self.bot.wait_until_ready()
        url = f"https://top.gg/api/bots/{self.bot.user.id}/stats"
        headers = {"Authorization": self.topgg_token}
        while True:
            try:
                guilds = len(self.bot.guilds)
                payload = {"server_count": guilds}
                self.logger.info(
                    f"Sending POST request to topgg using payload: {str(payload)}"
                )
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url, json=payload, headers=headers
                    ) as response:
                        if response.status == 200:
                            self.logger.debug("Server count updated successfully.")
                        else:
                            self.logger.info(session.headers)
                            self.logger.error(
                                f"Failed to update server count. Status: {response.status}"
                            )
                            self.logger.error(response.content.read_nowait())
            except Exception as e:
                self.logger.exception(
                    f"An error occurred while updating server count: {e}"
                )
            await asyncio.sleep(3600)  # Wait for 1 hour before retrying
