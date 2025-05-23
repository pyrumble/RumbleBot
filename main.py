import discord
import yaml
import random
from typing import Literal
from discord.ext import commands, tasks
import logging
import os

"""PyRumble"""

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", help_command=None, intents=intents)

logger = logging.getLogger("bot")

with open("config.yml") as cfg:
    CONFIG = yaml.safe_load(cfg)

MODE: Literal["normal", "dev"] =  CONFIG["mode"]
bot.api_master_key = CONFIG["masterKey"]


match MODE:
    case "normal":
        TOKEN = CONFIG["botToken"]
        bot.mode = "normal"
    case "dev":
        TOKEN = CONFIG["testingToken"]
        bot.mode = "dev"
    case _:
        logger.error("Mode isn't correct!")
        exit()

async def load_cogs():
    for file in os.listdir("./cogs"):   
        if file.endswith(".py"):
            await bot.load_extension(f"cogs.{file[:-3]}")

@tasks.loop(minutes=5)
async def refresh_rpc():
    n = random.randint(1,2)
    if n == 1:
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening,name = f"music in {len(bot.guilds)} guilds"))
    elif 2:
        await bot.change_presence(activity=discord.CustomActivity(name="Made in Python"))

@refresh_rpc.before_loop
async def before_refresh_rpc():
    await bot.wait_until_ready()

@bot.event
async def setup_hook():
    refresh_rpc.start()
    logger.info("Loading commands...") 
    await load_cogs()
    logger.info("All commands have loaded sucessfully!")


@bot.event
async def on_ready():
    logger.info("Bot is ready!\nBot mode: %s", MODE)

if __name__ == "__main__":
    bot.run(TOKEN,root_logger=True)