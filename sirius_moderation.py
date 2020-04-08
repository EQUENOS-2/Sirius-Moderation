import discord
from discord.ext import commands
from discord.ext.commands import Bot
import asyncio, os, datetime

import pymongo

from box.db_worker import cluster
from functions import visual_delta

prefix = ".."
client = commands.Bot(command_prefix=prefix)
client.remove_command("help")

token = f"{os.environ.get('moderator_token')}"

db = cluster["guilds"]
owner_ids = [301295716066787332]

def dict_view(Dict):
    inc_depth = ["{", "[", "("]
    dec_depth = ["}", "]", ")"]
    line = f"{Dict}"
    out = ""
    depth = 0
    for s in line:
        if s in inc_depth:
            depth += 1
            out += s + "\n" + depth * "\t"
        elif s in dec_depth:
            depth -= 1
            out += "\n" + depth * "\t" + s
        elif s == ",":
            out += s + "\n" + depth * "\t"
        else:
            if not (s == " " and out[-1:] == " "):
                out += s
    return out

def find_alias(table, word):
    out = None
    for key in table:
        if word in table[key]:
            out = key
            break
    return out

@client.event
async def on_ready():
    print(
        f">> {client.user} is ready\n"
        f">> Prefix: {prefix}\n"
        ">> Loading cogs..."
    )

#========Commands=========

@client.command(aliases = ["lo"])
async def logout(ctx):
    if ctx.author.id in owner_ids:
        await ctx.send("```\n>> Logging out...```")
        await client.logout()

@client.command(aliases = ["view-db"])
async def view_db(ctx, coll="test"):
    collection = db[coll]
    res = collection.find_one(
        {"_id": ctx.guild.id}
    )
    
    reply = discord.Embed(
        title="💾 Relevant collection data",
        description=(
            f"**ID:** {ctx.guild.id}\n\n"
            f"```json\n{dict_view(res)}\n```"
        ),
        color=discord.Color.dark_blue()
    )
    await ctx.send(embed=reply)

@commands.cooldown(1, 1, commands.BucketType.member)
@client.command()
async def help(ctx, *, section=None):
    p = ctx.prefix
    sections = {
        "settings": ["settings", "s", "setting"],
        "moderation": ["moderation", "m", "moderate", "mod"],
        "utility": ["utility", "util", "u", "utils"],
        "tokens": ["tokens", "t"]
    }
    titles = {
        "settings": "О настройках",
        "moderation": "Модерация",
        "utility": "Полезные команды",
        "tokens": "Система токенов"
    }
    if section is None:
        reply = discord.Embed(
            title="📖 Меню помощи",
            description=(
                "Введите команду, интересующую Вас:\n\n"
                f"`{p}help settings` - настройка\n"
                f"`{p}help moderation` - модерация\n"
                f"`{p}help utility` - полезное\n"
                f"`{p}help tokens` - система токенов\n"
            ),
            color=ctx.guild.me.color
        )
        reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
        await ctx.send(embed=reply)
    
    else:
        section = find_alias(sections, section.lower())
        if section is None:
            reply = discord.Embed(
                title="🔎 Раздел не найден",
                description=f"Попробуйте снова с одной из команд, указанных в `{p}help`"
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        else:
            text = open(f"box/{section}.txt", "r", encoding="utf8").read()
            text = text.replace("{p}", p)

            reply = discord.Embed(
                title=f"📋 {titles[section]}",
                description=text,
                color=ctx.guild.me.color
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)

#========On cooldown======
@client.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        cool_notify = discord.Embed(
            title='⏳ Подождите немного',
            description = f"Осталось {visual_delta(int(error.retry_after))}"
        )
        cool_notify.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
        await ctx.send(embed=cool_notify)

for file_name in os.listdir("./cogs"):
    if file_name.endswith(".py"):
        client.load_extension(f"cogs.{file_name[:-3]}")

client.run(token)
