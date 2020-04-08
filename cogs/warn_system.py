import discord
from discord.ext import commands
from discord.ext.commands import Bot
import asyncio, os, datetime

import pymongo

from box.db_worker import cluster
from functions import detect, get_field, has_permissions, visual_delta

db = cluster["guilds"]

def col(*params):
    colors = {
        "dg": discord.Color.dark_green(),
        "dr": discord.Color.dark_red(),
        "do": discord.Color.from_rgb(122, 76, 2),
        "ddg": discord.Color.from_rgb(97, 122, 86),
        "o": discord.Color.orange()
    }
    if "int" in f"{type(params[0])}".lower():
        return discord.Color.from_rgb(*params)
    else:
        return colors[params[0]]

def is_id(variable):
    return ("int" in f"{type(variable)}".lower() and len(f"{variable}") == 18)

async def in_bans(guild, user):
    if not is_id(user):
        user = user.id
    bans = await guild.bans()
    found = False
    for case in bans:
        banned_id = case.user.id
        if banned_id == user:
            found = True
            break
    return found

async def post_log(guild, log_embed):
    collection = db["channels"]
    result = collection.find_one(
        {
            "_id": guild.id,
            "mod_log": {"$exists": True}
        }
    )
    if result != None:
        channel = guild.get_channel(result["mod_log"])
        if channel != None:
            try:
                await channel.send(embed=log_embed)
            except Exception:
                pass

async def try_send(channel, text=None, embed=None):
    try:
        await channel.send(content=text, embed=embed)
    except Exception:
        pass

async def do_tempban(user, moderator, duration, reason=None):
    guild = moderator.guild
    reason = f"{moderator.id}|{reason[:+380]}"
    if not await in_bans(guild, user):
        now = datetime.datetime.utcnow()
        ends_at = now + datetime.timedelta(seconds=duration)

        await guild.ban(user, reason=reason, delete_message_days=0)

        collection = db["bans"]
        collection.find_one_and_update(
            {"_id": guild.id},
            {"$set": {
                f"{user.id}": {
                    "ends_at": ends_at
                }
            }},
            upsert=True
        )

async def withdraw_tempban(guild, user_id, data=None, sec=None):
    if data == None:
        collection = db["bans"]
        result = collection.find_one(
            {
                "_id": guild.id,
                f"{user_id}": {"$exists": True}
            }
        )
        if result != None:
            data = result[f"{user_id}"]

    if data != None:
        if sec == None:
            future = data["ends_at"]
            now = datetime.datetime.utcnow()
            if now >= future:
                sec = 0
            else:
                delta = future - now
                sec = delta.seconds + delta.days * 24*3600

        await asyncio.sleep(sec)
        
        text = None
        bans = await guild.bans()
        for case in bans:
            if case.user.id == user_id:
                user = case.user
                text = case.reason
                break
        
        if text != None:
            await guild.unban(user)

            collection = db["bans"]
            collection.find_one_and_update(
                {
                    "_id": guild.id,
                    f"{user.id}": {"$exists": True}
                },
                {"$unset": {f"{user.id}": ""}}
            )

            s_mod_id, reason = text.split("|", maxsplit=1)
            mod = guild.get_member(int(s_mod_id))

            log_embed = discord.Embed(
                title="🚫 Пользователь разбанен",
                description=(
                    "**Подробнее о снятом бане:**\n"
                    f"> **Пользователь:** {user}\n"
                    f"> **Модератор:** {mod}\n"
                    f"> **Причина:** {reason}"
                ),
                color=col("dr")
            )

            return log_embed

class warn_system(commands.Cog):
    def __init__(self, client):
        self.client = client

    #========== Events ===========
    @commands.Cog.listener()
    async def on_ready(self):
        print(">> Warn system cog is loaded")
    
    # If bot removed
    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        collection = db["warns"]
        collection.find_one_and_delete({"_id": guild.id})
    
    #======== Commands ===========
    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command()
    async def warn(self, ctx, member_s, *, reason="не указана"):
        if not has_permissions(ctx.author, ["ban_members"]):
            reply = discord.Embed(
                title="❌ Недостаточно прав",
                description=(
                    "**Необходимые права:**\n"
                    f"> Банить участников"
                ),
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        else:
            member = detect.member(ctx.guild, member_s)
            if member is None:
                reply = discord.Embed(
                    title="💢 Упс",
                    description=f"Вы указали {member_s}, подразумевая участника, но он не был найден",
                    color=col("dr")
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)
            
            elif member.top_role.position >= ctx.author.top_role.position and ctx.author.id != ctx.guild.owner_id:
                reply = discord.Embed(
                    title="💢 Упс",
                    description="Роль этого участника не ниже Вашей",
                    color=col("dr")
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)
            
            else:
                collection = db["warns"]

                result = collection.find_one(
                    {
                        "_id": ctx.guild.id,
                        f"{member.id}": {"$exists": True}
                    }
                )
                member_warns = get_field(result, f"{member.id}")
                if member_warns is None:
                    total_warns = 0
                else:
                    total_warns = len(member_warns)
                
                if total_warns >= 5:
                    reply = discord.Embed(
                        title="💢 Лимит",
                        description="У участника не может быть больше **5** предупреждений",
                        color=col("dr")
                    )
                    reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                    await ctx.send(embed=reply)
                
                elif total_warns >= 4:
                    sec = 24*3600
                    log_emb = discord.Embed(
                        title="⛔ Пользователь временно забанен",
                        description=(
                            f"**Пользователь:** {member}\n"
                            f"**Модератор:** {ctx.author}\n"
                            f"**Длительность:** {visual_delta(datetime.timedelta(seconds=sec))}\n"
                            f"**Причина:** набрал 5 или более предупреждений"
                        ),
                        color=discord.Color.red()
                    )
                    await do_tempban(member, ctx.author, sec, reason)

                    await post_log(ctx.guild, log_emb)
                    await ctx.send(embed=log_emb, delete_after=3)
                    await ctx.message.delete()
                    await try_send(member, embed=log_emb)

                    log_emb = await withdraw_tempban(ctx.guild, member.id)
                    if log_emb != None:
                        await post_log(ctx.guild, log_emb)

                else:
                    warn_json = {
                        "mod_id": ctx.author.id,
                        "reason": reason,
                        "timestamp": datetime.datetime.utcnow()
                    }

                    collection.find_one_and_update(
                        {"_id": ctx.guild.id},
                        {"$addToSet": {f"{member.id}": warn_json}},
                        upsert=True
                    )

                    warn_log = discord.Embed(
                        title="🔸 Предупреждение",
                        description=(
                            f"**Участник:** {member}\n"
                            f"**Модератор:** {ctx.author}\n"
                            f"**Причина:** {reason}\n"
                        ),
                        color=col("o")
                    )
                    await ctx.send(embed=warn_log, delete_after=3)
                    await post_log(ctx.guild, warn_log)
                    await ctx.message.delete()
                    await try_send(member, embed=warn_log)

    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command(aliases=["clean-warns", "remove-warn"])
    async def unwarn(self, ctx, member_s, number):
        p = ctx.prefix
        number = number.lower()
        if not has_permissions(ctx.author, ["ban_members"]):
            reply = discord.Embed(
                title="❌ Недостаточно прав",
                description=(
                    "**Необходимые права:**\n"
                    f"> Банить участников"
                ),
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        else:
            member = detect.member(ctx.guild, member_s)
            if member is None:
                reply = discord.Embed(
                    title="💢 Упс",
                    description=f"Вы указали {member_s}, подразумевая участника, но он не был найден",
                    color=col("dr")
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)
            
            elif number != "all" and not number.isdigit():
                reply = discord.Embed(
                    title="💢 Ошибка",
                    description=(
                        f"Номер варна должен быть целым числом или параметром `all`. Введено: {number}\n"
                        f"Подробнее: `{p}unwarn`"
                    ),
                    color=col("dr")
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)
            else:
                collection = db["warns"]
                desc = None
                if number == "all":
                    collection.find_one_and_update(
                        {"_id": ctx.guild.id, f"{member.id}": {"$exists": True}},
                        {"$unset": {f"{member.id}": ""}}
                    )
                    desc = (
                        f"**Участник:** {member}\n"
                        f"**Модератор:** {ctx.author}\n"
                        f"**Все предупреждения** сняты"
                    )
                else:
                    number = int(number)
                    result = collection.find_one(
                        {"_id": ctx.guild.id, f"{member.id}": {"$exists": True}},
                        projection={f"{member.id}": True}
                    )
                    member_warns = get_field(result, f"{member.id}")

                    if member_warns is None or member_warns == []:
                        error_desc = f"У участника {member} нет предупреждений"
                    elif len(member_warns) < number or number < 1:
                        error_desc = f"Варн не найден. Всего варнов: {len(member_warns)}"
                    else:
                        member_warns.pop(number - 1)
                        collection.find_one_and_update(
                            {"_id": ctx.guild.id, f"{member.id}": {"$exists": True}},
                            {"$set": {f"{member.id}": member_warns}}
                        )
                        desc = (
                            f"**Участник:** {member}\n"
                            f"**Модератор:** {ctx.author}\n"
                            f"**Номер:** {number}"
                        )
                    
                if desc is None:
                    reply = discord.Embed(
                        title="💢 Ошибка",
                        description=error_desc
                    )
                    reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                    await ctx.send(embed=reply)
                
                else:
                    log_emb = discord.Embed(
                        title="♻ Сняты предупреждения",
                        description=desc,
                        color=col("dg")
                    )
                    log_emb.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                    await ctx.send(embed=log_emb, delete_after=3)
                    await post_log(ctx.guild, log_emb)
                    await ctx.message.delete()

    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command(aliases=["user-warns"])
    async def warns(self, ctx, *, member_s=None):
        if member_s == None:
            member = ctx.author
        else:
            member = detect.member(ctx.guild, member_s)
        
        if member is None:
            reply = discord.Embed(
                title="💢 Упс",
                description=f"Вы указали {member_s}, подразумевая участника, но он не был найден",
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        else:
            collection = db["warns"]
            result = collection.find_one(
                {"_id": ctx.guild.id, f"{member.id}": {"$exists": True}},
                projection={f"{member.id}": True}
            )

            member_warns = get_field(result, f"{member.id}")
            if member_warns is None:
                desc = "Отсутствуют"
                member_warns = []
            else:
                desc = ""
            
            reply = discord.Embed(
                title=f"📚 Предупреждения {member}",
                description=desc,
                color=col("o")
            )
            reply.set_thumbnail(url=f"{member.avatar_url}")
            for i in range(len(member_warns)):
                w = member_warns[i]
                dt = f"{w['timestamp']}"[:-10].replace("-", ".")
                mod = ctx.guild.get_member(w['mod_id'])

                reply.add_field(
                    name=f"🔸 **{i+1}**",
                    value=(
                        f"**Модератор:** {mod}\n"
                        f"**Причина:** {w['reason']}\n"
                        f"**Дата и время:** `{dt}` (UTC)\n"
                    ),
                    inline=False
                )
            
            await ctx.send(embed=reply)

    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command(aliases=["server-warns", "warns-top", "warn-top"])
    async def server_warns(self, ctx, page="1"):
        interval = 10

        if not page.isdigit():
            reply = discord.Embed(
                title="💢 Ошибка",
                description=f"Номер страницы должен быть целым числом. Введено: {page}",
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        else:
            page_arg_passed = True
            page = int(page)
            collection = db["warns"]

            result = collection.find_one(
                {"_id": ctx.guild.id},
                projection={"_id": False}
            )
            if result is None or result == {}:
                desc = "Отсутствуют"

            else:
                pairs = []
                for id_key in result:
                    pairs.append((int(id_key), len(result[id_key])))
                pairs.sort(key=lambda pair: pair[1], reverse=True)

                total_warned = len(pairs)
                total_pages = (total_warned - 1) // interval + 1

                if page < 1 or page > total_pages:
                    page_arg_passed = False

                    reply = discord.Embed(
                        title="📖 Страница не найдена",
                        description=f"**Всего страниц:** {total_pages}"
                    )
                    reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                    await ctx.send(embed=reply)
                
                else:
                    lower_bound = (page - 1) * interval
                    upper_bound = min(page * interval, total_warned)
                    desc = ""
                    for i in range(lower_bound, upper_bound):
                        user = ctx.guild.get_member(pairs[i][0])
                        w = pairs[i][1]
                        desc += f"**{i + 1})** {user} • **{w}** 🔸\n"
            
            if page_arg_passed:
                reply = discord.Embed(
                    title="📑 Список предупреждённых пользователей",
                    description=desc,
                    color=col("o")
                )
                reply.set_thumbnail(url=f"{ctx.guild.icon_url}")
                reply.set_footer(text=f"Стр. {page}/{total_pages}")
                await ctx.send(embed=reply)

    #======== Errors =========
    @warn.error
    async def warn_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            p = ctx.prefix
            cmd = ctx.command.name
            reply = discord.Embed(
                title = f"❓ Об аргументах `{p}{cmd}`",
                description = (
                    f"**Описание:** предупреждает участника\n"
                    f'**Использование:** `{p}{cmd} @Участник Причина`\n'
                    f"**Примеры:** `{p}{cmd} @User#1234 нарушил правила`\n"
                    f">> `{p}{cmd} @User#1234`"
                )
            )
            reply.set_footer(text = f"{ctx.author}", icon_url = f"{ctx.author.avatar_url}")
            await ctx.send(embed = reply)

    @unwarn.error
    async def unwarn_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            p = ctx.prefix
            cmd = ctx.command.name
            reply = discord.Embed(
                title = f"❓ Об аргументах `{p}{cmd}`",
                description = (
                    f"**Описание:** убирает указанные предупреждения\n"
                    f'**Использование:** `{p}{cmd} @Участник Номера_варнов`\n'
                    f"**Примеры:** `{p}{cmd} @User#1234 1`\n"
                    f">> `{p}{cmd} @User#1234 all` - убрать все варны"
                )
            )
            reply.set_footer(text = f"{ctx.author}", icon_url = f"{ctx.author.avatar_url}")
            await ctx.send(embed = reply)

def setup(client):
    client.add_cog(warn_system(client))