import discord
from discord.ext import commands
from discord.ext.commands import Bot
import asyncio, os, datetime

import pymongo

from box.db_worker import cluster
from functions import detect, get_field, carve_int, has_permissions, visual_delta

db = cluster["guilds"]

#========Important variables========
mute_role_name = "Мут"

time_codes = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 3600*24,
    "w": 7*24*3600
}

spam_buffer = {}

#============Functions==============
# def functions
def is_id(variable):
    return ("int" in f"{type(variable)}".lower() and len(f"{variable}") == 18)

def col(*params):
    colors = {
        "dg": discord.Color.dark_green(),
        "dr": discord.Color.dark_red(),
        "do": discord.Color.from_rgb(122, 76, 2),
        "ddg": discord.Color.from_rgb(97, 122, 86)
    }
    if "int" in f"{type(params[0])}".lower():
        return discord.Color.from_rgb(*params)
    else:
        return colors[params[0]]

def anf(text):
    line = f"{text}"
    fsymbs = ">`*_~|"
    out = ""
    for s in line:
        if s in fsymbs:
            out += f"\\{s}"
        else:
            out += s
    return out

# async def functions
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

async def setup_mute_role(guild):
    mute_role = discord.utils.get(guild.roles, name=mute_role_name)
    if mute_role == None:
        mute_role = await guild.create_role(name=mute_role_name, permissions=discord.Permissions.none())
    
    for category in guild.categories:
        over = category.overwrites_for(mute_role)
        if over.is_empty():
            await category.set_permissions(mute_role, send_messages=False)
    for text_channel in guild.text_channels:
        over = text_channel.overwrites_for(mute_role)
        if over.is_empty():
            await category.set_permissions(mute_role, send_messages=False)

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

async def delete_recent(client, member, sec, not_more_than=None, start_channel=None):
    async def try_delete(obj):
        try:
            await obj.delete()
        except Exception:
            pass
        return
    
    now = datetime.datetime.utcnow()
    past = now - datetime.timedelta(seconds=sec)
    guild = member.guild
    to_delete = []
    finished = False

    if start_channel != None:
        async for message in start_channel.history(after=past):
            if message.author.id == member.id:
                to_delete.append(message)
                if not_more_than != None and len(to_delete) >= not_more_than:
                    finished = True
                    break
    
    if not finished:
        for channel in guild.text_channels:
            if channel != start_channel:
                async for message in channel.history(after=past):
                    if message.author.id == member.id:
                        to_delete.append(message)
                        if not_more_than != None and len(to_delete) >= not_more_than:
                            break
    
    for message in to_delete:
        client.loop.create_task(try_delete(message))

async def refresh_tasks(client):
        collection = db["mutes"]
        guilds = collection.find({})

        for mutes in guilds:
            guild = client.get_guild(mutes["_id"])
            for key in mutes:
                if key != "_id":
                    member_id = int(key)
                    member = guild.get_member(member_id)
                    data = mutes[key]

                    async def wmute_and_post_log():
                        log = await withdraw.mute(member, data)
                        if log != None:
                            await post_log(member.guild, log)
                        return
                    
                    client.loop.create_task(wmute_and_post_log())
        
        collection = db["bans"]
        guilds = collection.find({})

        for bans in guilds:
            guild = client.get_guild(bans["_id"])
            for key in bans:
                if key != "_id":
                    case = bans[key]

                    async def wban_and_post_log():
                        log = await withdraw.tempban(guild, int(key), case)
                        if log != None:
                            await post_log(guild, log)
                        return
                    
                    client.loop.create_task(wban_and_post_log())
        
        del guilds
# classes
class do_action:
    @staticmethod
    async def mute(member, moderator, duration, reason=None):
        guild = member.guild
        mute_role = discord.utils.get(guild.roles, name=mute_role_name)
        fix_required = False
        if mute_role == None:
            fix_required = True
            mute_role = await guild.create_role(name=mute_role_name, permissions=discord.Permissions.none())
        
        if guild.me.top_role.position > member.top_role.position:
            collection = db["mutes"]

            now = datetime.datetime.utcnow()
            ends_at = now + datetime.timedelta(seconds=duration)

            if not mute_role in member.roles:
                await member.add_roles(mute_role)

            collection.find_one_and_update(
                {"_id": guild.id},
                {"$set": { 
                    f"{member.id}": {
                        "ends_at": ends_at,
                        "moderator_id": moderator.id,
                        "reason": reason
                    }
                }},
                upsert=True
            )
        
        if fix_required:
            await setup_mute_role(guild)
    
    @staticmethod
    async def tempban(user, moderator, duration, reason=None):
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

class withdraw:
    @staticmethod
    async def mute(member, data=None, sec=None):
        guild = member.guild
        mute_role = discord.utils.get(guild.roles, name=mute_role_name)
        if mute_role != None and mute_role in member.roles:
            if data == None:
                collection = db["mutes"]
                result = collection.find_one(
                    {
                        "_id": guild.id,
                        f"{member.id}": {"$exists": True}
                    }
                )
                
                if result == None:
                    if mute_role in member.roles:
                        await member.remove_roles(mute_role)
                else:
                    data = result[f"{member.id}"]
                    del result

            if data != None:
                if sec == None:
                    future = data["ends_at"]
                    now = datetime.datetime.utcnow()
                    if future <= now:
                        sec = 0
                    else:
                        delta = future - now
                        sec = delta.seconds + 24*3600*delta.days
                
                await asyncio.sleep(sec)

                if mute_role in member.roles:
                    await member.remove_roles(mute_role)

                    mod = guild.get_member(data["moderator_id"])
                    reason = data["reason"]

                    collection = db["mutes"]
                    collection.find_one_and_update(
                        {"_id": guild.id, f"{member.id}": {"$exists": True}},
                        {"$unset": {f"{member.id}": ""}}
                    )
                
                    log_embed = discord.Embed(
                        title="🔑 Снят мут",
                        description=(
                            "**Подробнее о снятом муте:**\n"
                            f"> **Участник:** {member}\n"
                            f"> **Модератор:** {mod}\n"
                            f"> **Причина:** {reason}"
                        ),
                        color=col("ddg")
                    )

                    return log_embed
    
    @staticmethod
    async def tempban(guild, user_id, data=None, sec=None):
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

class punishments(commands.Cog):
    def __init__(self, client):
        self.client = client

    #==========Events==========

    # On Ready
    @commands.Cog.listener()
    async def on_ready(self):
        print(">> Punishments cog is loaded")
        await refresh_tasks(self.client)
    
    # If bot removed
    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        collection = db["mutes"]
        collection.find_one_and_delete({"_id": guild.id})
        collection = db["bans"]
        collection.find_one_and_delete({"_id": guild.id})

    # mute memory
    @commands.Cog.listener()
    async def on_member_join(self, member):
        mute_role = discord.utils.get(member.guild.roles, name=mute_role_name)
        if mute_role != None:
            collection = db["mutes"]
            result = collection.find_one(
                {
                    "_id": member.guild.id,
                    f"{member.id}": {"$exists": True}
                }
            )
            if result != None:
                await member.add_roles(mute_role)
                
                mute_data = result[f"{member.id}"]
                log = await withdraw.mute(member, mute_data)
                if log != None:
                    await post_log(member.guild, log)

    # spam check and actions
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild != None:

            if not has_permissions(message.author, ["manage_messages"]):
                server_id = message.guild.id
                collection = db["levers"]

                options = collection.find_one({"_id": server_id})
                antispam = get_field(options, "antispam")
                if antispam is None:
                    antispam = False

                if antispam:
                    global spam_buffer
                    user_id = message.author.id
                    weight = len(message.content)
                    reached_critical_point = False

                    if weight <= 10:
                        min_delay = datetime.timedelta(seconds=1)
                    elif weight >= 400:
                        min_delay = datetime.timedelta(seconds=10)
                    else:
                        min_delay = datetime.timedelta(seconds=2)
                    
                    now = datetime.datetime.utcnow()
                    server_data = get_field(spam_buffer, server_id)
                    if server_data == None:
                        server_data = {
                            user_id: {
                                "last_at": now,
                                "points": 1
                            }
                        }
                        spam_buffer.update([(server_id, server_data)])
                    else:
                        user_data = get_field(server_data, user_id)
                        if user_data == None:
                            spam_buffer[server_id].update([(user_id,
                            {
                                "last_at": now,
                                "points": 1
                            }
                            )])
                        else:
                            last_at = user_data["last_at"]
                            delta = now - last_at
                            if delta < min_delay:
                                if user_data["points"] >= 4:
                                    spam_buffer[server_id].pop(user_id)
                                    reached_critical_point = True
                                else:
                                    spam_buffer[server_id][user_id]["points"] += 1
                                    spam_buffer[server_id][user_id]["last_at"] = now
                            else:
                                if user_data["points"] < 1:
                                    spam_buffer[server_id].pop(user_id)
                                else:
                                    spam_buffer[server_id][user_id]["points"] -= 1
                                    spam_buffer[server_id][user_id]["last_at"] = now
                    
                    if reached_critical_point:
                        log_emb = discord.Embed(
                            title="🔒 Наложен автоматический мут",
                            description=(
                                f"**Участник:** {message.author}\n"
                                f"**Длительность:** {visual_delta(datetime.timedelta(seconds=3600))}\n"
                                f"**Причина:** спам"
                            ),
                            color=col("do")
                        )
                        await do_action.mute(message.author, message.guild.me, 3600, "спам")
                        await post_log(message.guild, log_emb)

                        await delete_recent(self.client, message.author, 60, start_channel=message.channel)

                        await try_send(message.author, embed=log_emb)
                        log_emb = await withdraw.mute(message.author)
                        if log_emb != None:
                            await post_log(message.guild, log_emb)

    #=========Commands=========

    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command()
    async def mute(self, ctx, member_s, raw_dur, *, reason="не указана"):
        if not has_permissions(ctx.author, ["manage_messages"]):
            reply = discord.Embed(
                title="❌ Недостаточно прав",
                description=(
                    "**Требуемые права:**\n"
                    "> Управлять сообщениями"
                ),
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        else:
            member = detect.member(ctx.guild, member_s)
            if member == None:
                reply = discord.Embed(
                    title="💢 Упс",
                    description=f"Вы указали {member_s}, подразумевая участника, но он не был найден",
                    color=col("dr")
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)
            
            else:
                t_code = raw_dur[-1:].lower()
                t_weight = raw_dur[:-1]
                if t_code not in time_codes or not t_weight.isdigit():
                    reply = discord.Embed(
                        title="💢 Неверный аргумент",
                        description=(
                            "Пожалуйста, укажите длительность в таком формате:\n"
                            "`5m` - 5 минут\n"
                            "`s - сек` `m - мин` `h - час` `d - сут` `w - нед`"
                        ),
                        color=col("dr")
                    )
                    reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                    await ctx.send(embed=reply)
                
                elif mute_role_name in [r.name for r in member.roles]:
                    reply = discord.Embed(
                        title="💢 Ошибка",
                        description=f"Участник {member} уже ограничен",
                        color=col("dr")
                    )
                    reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                    await ctx.send(embed=reply)

                elif ctx.author.top_role.position <= member.top_role.position and ctx.author.id != ctx.guild.owner_id:
                    reply = discord.Embed(
                        title="💢 Позиция",
                        description=f"Ваша наивысшая роль не выше роли {member}",
                        color=col("dr")
                    )
                    reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                    await ctx.send(embed=reply)
                
                elif ctx.guild.me.top_role.position <= member.top_role.position:
                    reply = discord.Embed(
                        title="⚠ У меня нет прав",
                        description=(
                            f"Моя наивысшая роль не выше, чем роль {member}\n"
                            "Чтобы исправить это, перетащите мою роль выше"
                        ),
                        color=discord.Color.dark_gold()
                    )
                    reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                    await ctx.send(embed=reply)

                else:
                    sec = int(t_weight) * time_codes[t_code]

                    delta = datetime.timedelta(seconds=sec)
                    if delta.days >= 14:
                        reply = discord.Embed(
                            title="💢 Превышен лимит",
                            description="Мут не может длиться дольше, чем 2 недели",
                            color = col("dr")
                        )
                        reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                        await ctx.send(embed=reply)
                    
                    else:
                        log_emb = discord.Embed(
                            title="🔒 Наложен мут",
                            description=(
                                f"**Участник:** {member}\n"
                                f"**Модератор:** {ctx.author}\n"
                                f"**Длительность:** {visual_delta(datetime.timedelta(seconds=sec))}\n"
                                f"**Причина:** {reason}"
                            ),
                            color=col("do")
                        )
                        await do_action.mute(member, ctx.author, sec, reason)

                        await post_log(ctx.guild, log_emb)
                        await ctx.send(embed=log_emb, delete_after=3)
                        await ctx.message.delete()
                        await try_send(member, embed=log_emb)

                        log_emb = await withdraw.mute(member)
                        if log_emb != None:
                            await post_log(ctx.guild, log_emb)

    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command()
    async def unmute(self, ctx, member_s):
        if not has_permissions(ctx.author, ["manage_messages"]):
            reply = discord.Embed(
                title="❌ Недостаточно прав",
                description=(
                    "**Необходимые права:**\n"
                    "> Управлять сообщениями"
                ),
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        else:
            member = detect.member(ctx.guild, member_s)

            if member == None:
                reply = discord.Embed(
                    title="💢 Упс",
                    description=f"Вы указали {member_s}, подразумевая участника, но он не был найден",
                    color=col("dr")
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)
            
            elif ctx.author.top_role.position <= member.top_role.position and ctx.author.id != ctx.guild.owner_id:
                reply = discord.Embed(
                    title="💢 Позиция",
                    description=f"Ваша наивысшая роль не выше роли {member}",
                    color=col("dr")
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)
            
            elif ctx.guild.me.top_role.position <= member.top_role.position:
                reply = discord.Embed(
                    title="⚠ У меня нет прав",
                    description=(
                        f"Моя наивысшая роль не выше роли {member}\n"
                        "Чтобы исправить это, перетащите мою роль выше"
                    ),
                    color=col("dr")
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)
            
            elif mute_role_name not in [r.name for r in member.roles]:
                reply = discord.Embed(
                    title="💢 Ошибка",
                    description=f"На участника {member_s} не наложен мут",
                    color=col("dr")
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)
            
            else:
                log = await withdraw.mute(member, sec=0)
                await post_log(ctx.guild, log)
                await ctx.send(embed=log, delete_after=3)
                await ctx.message.delete()

    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command()
    async def tempban(self, ctx, user_s, raw_dur, *, reason="не указана"):
        if not has_permissions(ctx.author, ["ban_members"]):
            reply = discord.Embed(
                title="❌ Недостаточно прав",
                description=(
                    "**Необходимые права:**\n"
                    "> Банить участников"
                ),
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        else:
            user = detect.user(user_s, self.client)
            if user == None:
                reply = discord.Embed(
                    title="💢 Упс",
                    description=f"Вы указали {user_s}, подразумевая пользователя, но он не был найден",
                    color=col("dr")
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)
            
            else:
                member = ctx.guild.get_member(user.id)
                perms_owned = True

                t_code = raw_dur[-1:].lower()
                t_weight = raw_dur[:-1]
                if t_code not in time_codes or not t_weight.isdigit():
                    perms_owned = False

                    reply = discord.Embed(
                        title="💢 Неверный аргумент",
                        description=(
                            "Пожалуйста, укажите длительность в таком формате:\n"
                            "`5m` - 5 минут\n"
                            "`s - сек` `m - мин` `h - час` `d - сут` `w - нед`"
                        ),
                        color=col("dr")
                    )
                    reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                    await ctx.send(embed=reply)
                
                elif member != None:
                    perms_owned = False

                    if ctx.author.top_role.position <= member.top_role.position and ctx.author.id != ctx.guild.owner_id:
                        reply = discord.Embed(
                            title="💢 Позиция",
                            description=f"Ваша наивысшая роль не выше роли {member}",
                            color=col("dr")
                        )
                        reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                        await ctx.send(embed=reply)
                    
                    elif ctx.guild.me.top_role.position <= member.top_role.position:
                        reply = discord.Embed(
                            title="⚠ У меня нет прав",
                            description=(
                                f"Моя наивысшая роль не выше, чем роль {member}\n"
                                "Чтобы исправить это, перетащите мою роль выше"
                            ),
                            color=discord.Color.dark_gold()
                        )
                        reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                        await ctx.send(embed=reply)
                    
                    else:
                        perms_owned = True
                
                elif await in_bans(ctx.guild, user):
                    perms_owned = False
                    reply = discord.Embed(
                        title="🛠 Упс",
                        description=f"{user} уже забанен"
                    )
                    reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                    await ctx.send(embed=reply)

                if perms_owned:
                    sec = int(t_weight) * time_codes[t_code]

                    delta = datetime.timedelta(seconds=sec)
                    if delta.days >= 35:
                        reply = discord.Embed(
                            title="💢 Превышен лимит",
                            description="Бан не может длиться дольше, чем 5 недель",
                            color = col("dr")
                        )
                        reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                        await ctx.send(embed=reply)
                    
                    else:
                        log_emb = discord.Embed(
                            title="⛔ Пользователь временно забанен",
                            description=(
                                f"**Пользователь:** {user}\n"
                                f"**Модератор:** {ctx.author}\n"
                                f"**Длительность:** {visual_delta(datetime.timedelta(seconds=sec))}\n"
                                f"**Причина:** {reason}"
                            ),
                            color=discord.Color.red()
                        )
                        await do_action.tempban(user, ctx.author, sec, reason)

                        await post_log(ctx.guild, log_emb)
                        await ctx.send(embed=log_emb, delete_after=3)
                        await ctx.message.delete()
                        await try_send(user, embed=log_emb)

                        log_emb = await withdraw.tempban(ctx.guild, user.id)
                        if log_emb != None:
                            await post_log(ctx.guild, log_emb)

    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command()
    async def unban(self, ctx, user_s):
        if not has_permissions(ctx.author, ["ban_members"]):
            reply = discord.Embed(
                title="❌ Недостаточно прав",
                description=(
                    "**Необходимые права:**\n"
                    "> Банить участников"
                ),
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        else:
            bans = await ctx.guild.bans()
            text = None
            for case in bans:
                if case.user.id == carve_int(user_s) or f"{case.user}" == user_s:
                    user = case.user
                    text = f"{case.reason}"
                    break
            if text == None:
                reply = discord.Embed(
                    title="💢 Упс",
                    description=f"Пользователя {user_s} нет в списке банов",
                    color=col("dr")
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)
            
            else:
                bruh = text.split("|", maxsplit=1)
                case = None
                if len(bruh) > 1 and bruh[0].isdigit():
                    collection = db["bans"]
                    result = collection.find_one(
                        {
                            "_id": ctx.guild.id,
                            f"{user.id}": {"$exists": True}
                        }
                    )
                    if result != None:
                        case = result[f"{user.id}"]
                        log_emb = await withdraw.tempban(ctx.guild, user.id, case, 0)
                
                if case == None:
                    await ctx.guild.unban(user)
                    log_emb = discord.Embed(
                        title="🚫 Пользователь разбанен",
                        description=(
                            "**Подробнее о снятом бане:**\n"
                            f"> **Пользователь:** {user}\n"
                            f"> **Модератор:** {ctx.author}\n"
                            f"> **Причина:** {text}"
                        ),
                        color=discord.Color.red()
                    )
                
                if log_emb != None:
                    await post_log(ctx.guild, log_emb)
                    await ctx.send(embed=log_emb, delete_after=3)
                await ctx.message.delete()
    
    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command()
    async def ban(self, ctx, user_s, *, reason="не указана"):
        if not has_permissions(ctx.author, ["administrator"]):
            reply = discord.Embed(
                title="❌ Недостаточно прав",
                description=(
                    "**Необходимые права:**\n"
                    "> Банить участников"
                ),
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        else:
            user = detect.user(self.client, user_s)
            if user == None:
                reply = discord.Embed(
                    title="💢 Упс",
                    description=f"Вы указали {user_s}, подразумевая пользователя, но он не был найден",
                    color=col("dr")
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)
            
            else:
                member = ctx.guild.get_member(user.id)
                perms_owned = True

                if member != None:
                    perms_owned = False

                    if ctx.author.top_role.position <= member.top_role.position and ctx.author.id != ctx.guild.owner_id:
                        reply = discord.Embed(
                            title="💢 Позиция",
                            description=f"Ваша наивысшая роль не выше роли {member}",
                            color=col("dr")
                        )
                        reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                        await ctx.send(embed=reply)
                    
                    elif ctx.guild.me.top_role.position <= member.top_role.position:
                        reply = discord.Embed(
                            title="⚠ У меня нет прав",
                            description=(
                                f"Моя наивысшая роль не выше, чем роль {member}\n"
                                "Чтобы исправить это, перетащите мою роль выше"
                            ),
                            color=discord.Color.dark_gold()
                        )
                        reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                        await ctx.send(embed=reply)
                    
                    else:
                        perms_owned = True
                
                elif await in_bans(ctx.guild, user):
                    perms_owned = False

                    reply = discord.Embed(
                        title="🛠 Упс",
                        description=f"{user} уже забанен"
                    )
                    reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                    await ctx.send(embed=reply)

                if perms_owned:
                    log_emb = discord.Embed(
                        title="⛔ Пользователь забанен",
                        description=(
                            f"> **Пользователь:** {user}\n"
                            f"> **Модератор:** {ctx.author}\n"
                            f"> **Причина:** {reason}"
                        ),
                        color=discord.Color.red()
                    )
                    await ctx.guild.ban(user, reason=reason[:+400])

                    await post_log(ctx.guild, log_emb)
                    await ctx.send(embed=log_emb, delete_after=3)
                    await ctx.message.delete()

    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command()
    async def kick(self, ctx, member_s, *, reason="не указана"):
        member = detect.member(ctx.guild, member_s)

        if not has_permissions(ctx.author, ["kick_members"]):
            reply = discord.Embed(
                title="❌ Недостаточно прав",
                description=(
                    "**Необходимые права:**\n"
                    "> Кикать участников"
                ),
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        elif member == None:
            reply = discord.Embed(
                title="💢 Упс",
                description=f"Вы указали {member_s}, подразумевая участника, но он не был найден",
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        elif member.top_role.position >= ctx.author.top_role.position and ctx.author.id != ctx.guild.owner_id:
            reply = discord.Embed(
                title="💢 Позиция",
                description=f"Ваша наивысшая роль не выше роли {member}",
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        elif ctx.guild.me.top_role.position <= member.top_role.position:
            reply = discord.Embed(
                title="⚠ У меня нет прав",
                description=(
                    f"Моя наивысшая роль не выше, чем роль {member}\n"
                    "Чтобы исправить это, перетащите мою роль выше"
                ),
                color=discord.Color.dark_gold()
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)

        else:
            log_emb = discord.Embed(
                title="⚖ Участник исключён",
                description=(
                    f"**Участник:** {member}\n"
                    f"**Модератор:** {ctx.author}\n"
                    f"**Причина:** {reason}"
                ),
                color=col(50, 50, 50)
            )

            await ctx.guild.kick(member, reason=reason)
            await post_log(ctx.guild, log_emb)
            await ctx.send(embed=log_emb, delete_after=3)
            await ctx.message.delete()

    #=========Error codes========
    @mute.error
    async def mute_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            p = ctx.prefix
            cmd = ctx.command.name
            reply = discord.Embed(
                title = f"❓ Об аргументах `{p}{cmd}`",
                description = (
                    f"**Описание:** ограничивает отправку сообщений во всех каналах\n"
                    f'**Использование:** `{p}{cmd} @Участник Время Причина`\n'
                    f"**Примеры:** `{p}{cmd} @User#1234 1h спам`\n"
                    f">> `{p}{cmd} @User#1234 1h`"
                )
            )
            reply.set_footer(text = f"{ctx.author}", icon_url = f"{ctx.author.avatar_url}")
            await ctx.send(embed = reply)
    
    @unmute.error
    async def unmute_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            p = ctx.prefix
            cmd = ctx.command.name
            reply = discord.Embed(
                title = f"❓ Об аргументах `{p}{cmd}`",
                description = (
                    f"**Описание:** снимает ограничения на отправку сообщений\n"
                    f'**Использование:** `{p}{cmd} @Участник`\n'
                    f"**Пример:** `{p}{cmd} @User#1234`\n"
                )
            )
            reply.set_footer(text = f"{ctx.author}", icon_url = f"{ctx.author.avatar_url}")
            await ctx.send(embed = reply)
    
    @ban.error
    async def ban_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            p = ctx.prefix
            cmd = ctx.command.name
            reply = discord.Embed(
                title = f"❓ Об аргументах `{p}{cmd}`",
                description = (
                    f"**Описание:** банит участника навсегда\n"
                    f'**Использование:** `{p}{cmd} @Участник Причина`\n'
                    f"**Пример:** `{p}{cmd} @User#1234 грубое нарушение`\n"
                )
            )
            reply.set_footer(text = f"{ctx.author}", icon_url = f"{ctx.author.avatar_url}")
            await ctx.send(embed = reply)
    
    @tempban.error
    async def tempban_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            p = ctx.prefix
            cmd = ctx.command.name
            reply = discord.Embed(
                title = f"❓ Об аргументах `{p}{cmd}`",
                description = (
                    f"**Описание:** временно банит участника\n"
                    f'**Использование:** `{p}{cmd} @Участник Время Причина`\n'
                    f"**Пример:** `{p}{cmd} @User#1234 1h нарушил правила`\n"
                )
            )
            reply.set_footer(text = f"{ctx.author}", icon_url = f"{ctx.author.avatar_url}")
            await ctx.send(embed = reply)
    
    @unban.error
    async def unban_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            p = ctx.prefix
            cmd = ctx.command.name
            reply = discord.Embed(
                title = f"❓ Об аргументах `{p}{cmd}`",
                description = (
                    f"**Описание:** снимает бан с пользователя\n"
                    f'**Использование:** `{p}{cmd} @Участник`\n'
                    f"**Пример:** `{p}{cmd} @User#1234`\n"
                )
            )
            reply.set_footer(text = f"{ctx.author}", icon_url = f"{ctx.author.avatar_url}")
            await ctx.send(embed = reply)

    @kick.error
    async def kick_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            p = ctx.prefix
            cmd = ctx.command.name
            reply = discord.Embed(
                title = f"❓ Об аргументах `{p}{cmd}`",
                description = (
                    f"**Описание:** исключает участника\n"
                    f'**Использование:** `{p}{cmd} @Участник Причина`\n'
                    f"**Пример:** `{p}{cmd} @User#1234 нарушение`\n"
                )
            )
            reply.set_footer(text = f"{ctx.author}", icon_url = f"{ctx.author.avatar_url}")
            await ctx.send(embed = reply)
    
def setup(client):
    client.add_cog(punishments(client))