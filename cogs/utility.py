import discord
from discord.ext import commands
from discord.ext.commands import Bot
import asyncio, os, datetime

import pymongo
from box.db_worker import cluster
from functions import get_field, rus_timestamp, detect, has_permissions

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

def detect_isolation(text, lll):
    wid=len(lll)
    iso=False
    out=[]
    for i in range(len(text)-wid+1):
        piece=text[i:i+wid]
        if piece==lll:
            if iso==True:
                iso=False
                end=i
                if start<end:
                    out.append(text[start:end])
            else:
                iso=True
                start=i+wid
    return out

def list_sum(List, insert = "\n"):
    out=""
    for elem in List:
        out += str(insert) + str(elem)
    return out[1:len(out)]

async def refresh_counters(guild):
    vcs = {
        "всего": None,
        "ботов": None,
        "людей": None
    }

    total_members = guild.member_count
    total_bots = 0
    for m in guild.members:
        if m.bot:
            total_bots += 1

    for vc in guild.voice_channels:
        for key in vcs:
            if vcs[key] is None and key in vc.name.lower():
                vcs[key] = vc
                break
    heading = None
    total_missing = 0
    for key in vcs:
        if vcs[key] is not None:
            heading = vcs[key].category
            break
        else:
            total_missing += 1
    
    if total_missing >= 3:
        heading = await guild.create_category("📊 Статистика сервера")
        await heading.set_permissions(guild.default_role, connect = False)
    elif heading is None:
        heading = guild
    
    for key in vcs:
        if vcs[key] is None:
            if key == "всего":
                name = f"Всего: {total_members}"
            elif key == "ботов":
                name = f"Ботов: {total_bots}"
            elif key == "людей":
                name = f"Людей: {total_members - total_bots}"
            vc = await heading.create_voice_channel(name)
            await vc.set_permissions(guild.default_role, connect = False)
        else:
            amount = None
            if key == "всего":
                amount = total_members
            elif key == "ботов":
                amount = total_bots
            elif key == "людей":
                amount = total_members - total_bots
            name = vcs[key].name.split(":", maxsplit=1)[0]
            name = f"{name}: {amount}"

            await vcs[key].edit(name=name)

async def get_message(channel_id, message_id, guild):
    channel = guild.get_channel(int(channel_id))
    if channel is None:
        return None
    else:
        try:
            message = await channel.fetch_message(int(message_id))
        except Exception:
            return None
        else:
            return message

async def trigger_raw_reaction(message=None, emojis=None, user_to_check=None, timeout=None, client=None):

    def check(payload):
        return (
            (message is None or message.id == payload.message.id) and
            (user_to_check is None or user_to_check.id == payload.user_id) and
            (emojis is None or payload.emoji in emojis)
        )
    
    try:
        payload = await client.wait_for("raw_reaction_add", check=check, timeout=timeout)
    
    except asyncio.TimeoutError:
        return None
    
    else:
        return payload

class custom:
    def __init__(self, client):
        self.client = client
    
    def emj(self, name):
        guild_id = 653160213607612426
        guild = self.client.get_guild(guild_id)
        emoji = discord.utils.get(guild.emojis, name=name)
        return emoji

class utility(commands.Cog):
    def __init__(self, client):
        self.client = client

    #========== Events ===========
    @commands.Cog.listener()
    async def on_ready(self):
        print(">> Utility cog is loaded")
    
    # If bot removed
    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        collection = db["reaction_roles"]
        collection.find_one_and_delete({"_id": guild.id})

    # Server stats
    @commands.Cog.listener()
    async def on_member_join(self, member):
        collection = db["levers"]
        result = collection.find_one(
            {"_id": member.guild.id}
        )
        stats_on = get_field(result, "stats_on")
        if stats_on is None:
            stats_on = False
        
        if stats_on:
            await refresh_counters(member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        collection = db["levers"]
        result = collection.find_one(
            {"_id": member.guild.id}
        )
        stats_on = get_field(result, "stats_on")
        if stats_on is None:
            stats_on = False
        
        if stats_on:
            await refresh_counters(member.guild)
    
    # Reaction roles
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        collection = db["reaction_roles"]
        result = collection.find_one(
            {
                "_id": payload.guild_id,
                f"{payload.message_id}.{payload.emoji}": {"$exists": True}
            },
            projection={f"{payload.message_id}.{payload.emoji}": True}
        )
        role_id = get_field(result, f"{payload.message_id}",  f"{payload.emoji}")
        if role_id is not None:
            guild = self.client.get_guild(payload.guild_id)
            role = guild.get_role(role_id)
            if role is not None:
                member = guild.get_member(payload.user_id)
                try:
                    await member.add_roles(role)
                except:
                    pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        collection = db["reaction_roles"]
        result = collection.find_one(
            {
                "_id": payload.guild_id,
                f"{payload.message_id}.{payload.emoji}": {"$exists": True}
            },
            projection={f"{payload.message_id}.{payload.emoji}": True}
        )
        role_id = get_field(result, f"{payload.message_id}",  f"{payload.emoji}")
        if role_id is not None:
            guild = self.client.get_guild(payload.guild_id)
            role = guild.get_role(role_id)
            if role is not None:
                member = guild.get_member(payload.user_id)
                if role in member.roles:
                    try:
                        await member.remove_roles(role)
                    except:
                        pass

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        collection = db["reaction_roles"]
        collection.find_one_and_update(
            {
                "_id": payload.guild_id,
                f"{payload.message_id}": {"$exists": True}
            },
            {
                "$unset": {f"{payload.message_id}": ""}
            }
        )

    #======== Commands ===========

    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command(aliases=["server-info", "serverinfo"])
    async def server(self, ctx):
        total = {
            "online": 0,
            "idle": 0,
            "dnd": 0,
            "offline": 0
        }
        total_members = ctx.guild.member_count
        total_bots = 0

        for m in ctx.guild.members:
            status = f"{m.status}"
            if status != "offline":
                total[status] += 1
            if m.bot:
                total_bots += 1
        total_humans = total_members - total_bots
        total["offline"] = total_members - total["online"] - total["idle"] - total["dnd"]
        
        eee = custom(self.client)

        stat_emb = discord.Embed(
            title=f"📚 О сервере {ctx.guild.name}",
            color=ctx.guild.me.color
        )
        stat_emb.add_field(
            name="**Численность**",
            value=(
                f"`👥` Участников: {total_members}\n"
                f"`🤖` Ботов: {total_bots}\n"
                f"`👪` Людей: {total_humans}"
            )
        )
        stat_emb.add_field(
            name="**Активность**",
            value=(
                f"{eee.emj('online')} Онлайн: {total['online']}\n"
                f"{eee.emj('idle')} Не активен: {total['idle']}\n"
                f"{eee.emj('dnd')} Не беспокоить: {total['dnd']}\n"
                f"{eee.emj('offline')} Не в сети: {total['offline']}"
            )
        )
        stat_emb.add_field(
            name="**Каналы**",
            value=(
                f"{eee.emj('text_channel')} Текстовых: {len(ctx.guild.text_channels)}\n"
                f"{eee.emj('voice_channel')} Голосовых: {len(ctx.guild.voice_channels)}"
            )
        )
        stat_emb.add_field(name=f"{eee.emj('crown')} **Владелец**", value=f"{ctx.guild.owner}")
        stat_emb.add_field(name="📆 **Дата создания**", value=f"{rus_timestamp(ctx.guild.created_at)}")
        stat_emb.set_thumbnail(url=f"{ctx.guild.icon_url}")

        await ctx.send(embed=stat_emb)

    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command(aliases=["user-info", "member-info", "whois", "user"])
    async def user_info(self, ctx, *, member_s=None):
        if member_s is None:
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
            eee = custom(self.client)
            desc = ""
            if member.id == ctx.guild.owner_id:
                desc = "Владелец сервера"

            reply = discord.Embed(
                title=f"{eee.emj(str(member.status))} {member}",
                description=desc,
                color=member.color
            )
            reply.set_thumbnail(url=f"{member.avatar_url}")
            reply.add_field(
                name=f"🎗 **Наивысшая роль**",
                value=f"> <@&{member.top_role.id}>",
                inline=False
            )
            reply.add_field(
                name=f"📑 **Всего ролей**",
                value=f"> {len(member.roles)}",
                inline=False
            )
            reply.add_field(
                name="📆 **Зашёл на сервер**",
                value=f"> {rus_timestamp(member.joined_at)}",
                inline=False
            )
            reply.add_field(
                name=f"📅 **Дата регистрации**",
                value=f"> {rus_timestamp(member.created_at)}",
                inline=False
            )

            await ctx.send(embed=reply)

    @commands.cooldown(1, 2, commands.BucketType.member)
    @commands.command()
    async def embed(self, ctx, *, raw_text):
        args = raw_text.split()
        mode="None"
        ID_str="None"
        if len(args)>0:
            mode=args[0]
        if len(args)>1:
            ID_str=args[1]
        
        head=detect_isolation(raw_text, "==")
        desc=detect_isolation(raw_text, "--")
        col=detect_isolation(raw_text, "##")
        thumb=detect_isolation(raw_text, "++")
        img=detect_isolation(raw_text, "&&")
        if col!=[]:
            col=col[0].lower()
        else:
            col = "default"
        
        colors={
            "default": discord.Color.default(),
            "red": discord.Color.red(),
            "blue": discord.Color.blue(),
            "green": discord.Color.green(),
            "gold": discord.Color.gold(),
            "teal": discord.Color.teal(),
            "magenta": discord.Color.magenta(),
            "purple": discord.Color.purple(),
            "blurple": discord.Color.blurple(),
            "dark_blue": discord.Color.dark_blue(),
            "dark_red": discord.Color.dark_red(),
            "black": discord.Color.from_rgb(0, 0, 0),
            "white": discord.Color.from_rgb(254, 254, 254)
        }

        if not col in colors:
            col = "default"
        col_chosen = colors[col]

        msg=discord.Embed(
            title=list_sum(head),
            description=list_sum(desc),
            color=col_chosen
        )
        if thumb!=[]:
            msg.set_thumbnail(url=thumb[0])
        if img!=[]:
            msg.set_image(url=img[0])
        
        wrong_syntax=False
        if mode.lower()!="edit":
            await ctx.send(embed=msg)
        else:
            if not has_permissions(ctx.author, ["manage_messages"]):
                wrong_syntax=True
                reply=discord.Embed(title="Ошибка", description="Недостаточно прав")
                await ctx.send(embed=reply)
            else:
                if not ID_str.isdigit():
                    wrong_syntax=True
                    reply=discord.Embed(title="Ошибка", description="Укажите **ID** сообщения в данном канале")
                    await ctx.send(embed=reply)
                else:
                    ID=int(ID_str)
                    message = await get_message(ctx.channel.id, ID, ctx.guild)
                    if message=="Error":
                        wrong_syntax=True
                        reply=discord.Embed(title="Ошибка", description=f"Сообщение с **ID** {ID} не найдено в этом канале")
                        await ctx.send(embed=reply)
                    else:
                        if message.author.id != self.client.user.id:
                            wrong_syntax=True
                            reply=discord.Embed(title="Ошибка", description=f"Я не могу редактировать это сообщение, так не я его автор")
                            await ctx.send(embed=reply)
                        else:
                            await message.edit(embed=msg)
                    
        if not wrong_syntax:
            backup_txt=f"Сырой текст команды, на всякий случай\n`{ctx.message.content}`"
            await ctx.message.delete()
            await ctx.author.send(backup_txt)

    @commands.cooldown(1, 2, commands.BucketType.member)
    @commands.command(aliases=['clear','del', 'delete'])
    async def clean(self, ctx, n="1"):
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
        
        elif not n.isdigit():
            reply = discord.Embed(
                title='💢 Упс',
                description=f"Кол-во сообщений ({n}), должно быть целым числом",
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        else:
            amount = int(n)+1
            if amount > 500:
                reply = discord.Embed(
                    title="💢 Лимит",
                    description="Разовый запрос на массовое удаление не должен превышать **500**",
                    color=col("dr")
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)

            else:
                await ctx.channel.purge(limit=amount)
                reply = discord.Embed(
                    title=f'🗑 Удалены сообщения :wastebasket:',
                    description=f'Удалено {n} последних сообщений',
                    color=discord.Color.light_grey()
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply, delete_after=3)

    @commands.cooldown(1, 2, commands.BucketType.member)
    @commands.command(aliases=["reaction-roles", "rr"])
    async def reaction_roles(self, ctx, *, role_s):
        role = detect.role(ctx.guild, role_s)
        if role is None:
            reply = discord.Embed(
                title="💢 Упс",
                description=f"Вы указали {role_s}, подразумевая роль, но она не была найдена",
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        elif role.position >= ctx.author.top_role.position and ctx.author.id != ctx.guild.owner_id:
            reply = discord.Embed(
                title="💢 Упс",
                description=f"Роль <@&{role.id}> не ниже Вашей",
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)

        else:
            reply = discord.Embed(
                title=f"🎗 Роль {role} за реакцию",
                description="Поставьте реакцию под нужным сообщением",
                color=ctx.guild.me.color
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            my_message = await ctx.send(embed=reply)
            await ctx.message.delete()

            payload = await trigger_raw_reaction(client=self.client, user_to_check=ctx.author, timeout=60)

            if payload is None:
                reply = discord.Embed(
                    title="⏳ Таймаут",
                    description=f"Вы слишком долго не ставили реакцию, истекло 60 секунд",
                    color=discord.Color.dark_blue()
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(f"{ctx.author.mention}", embed=reply)
                
            else:
                collection = db["reaction_roles"]
                result = collection.find_one(
                    {
                        "_id": ctx.guild.id,
                        f"{payload.message_id}.{payload.emoji}": {"$exists": True},
                    },
                    projection={f"{payload.message_id}.{payload.emoji}": True}
                )
                role_id = get_field(result, f"{payload.message_id}", f"{payload.emoji}")
                if role_id is not None:
                    reply = discord.Embed(
                        title="💢 Упс",
                        description=f"За реакцию {payload.emoji} уже выдаётся роль <@&{role_id}>",
                        color=col("dr")
                    )
                    reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                    await ctx.send(embed=reply)

                else:
                    collection.find_one_and_update(
                        {"_id": ctx.guild.id},
                        {"$set": {f"{payload.message_id}.{payload.emoji}": role.id}},
                        upsert=True
                    )
                    reply = discord.Embed(
                        title="✅ Настроено",
                        description=f"Теперь роль <@&{role.id}> выдаётся за нажатие на реакцию {payload.emoji}",
                        color=col("dg")
                    )
                    reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                    await my_message.edit(embed=reply, delete_after=4)

    @commands.cooldown(1, 2, commands.BucketType.member)
    @commands.command(aliases=["generate-invite", "gen-inv"])
    async def generate_invite(self, ctx, *, user_s):
        user = detect.user(user_s, self.client)
        if user is None:
            reply = discord.Embed(
                title="💢 Упс",
                description=f"Вы указали {member_s}, подразумевая пользователя, но он не был найден",
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        elif not user.bot:
            reply = discord.Embed(
                title="💢 Упс",
                description=f"{user} не является ботом",
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        else:
            await ctx.send(f"https://discordapp.com/api/oauth2/authorize?client_id={user.id}&permissions=8&scope=bot")

    #=======Errors=======
    @embed.error
    async def embed_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            p = ctx.prefix
            cmd = ctx.command.name
            reply = discord.Embed(
                title = f"❓ Об аргументах `{p}{cmd}`",
                description = ("**Описание:** позволяет отправить сообщение в рамке, имеет ряд настроек кастомизации такого сообщения.\n"
                    "**Применение:**\n"
                    "> `==Заголовок==` - *создаёт заголовок*\n"
                    "> `--Текст--` - *создаёт основной текст под заголовком*\n"
                    "> `++URL++` - *добавляет мал. картинку в правый верхний угол*\n"
                    "> `&&URL&&` - *добавляет большую картинку под текстом*\n"
                    "> `##Цвет из списка##` - *подкрашивает рамку цветом из списка*\n"
                    "**Список цветов:** `[red, blue, green, gold, teal, magenta, purple, blurple, dark_blue, dark_red, black, white]`\n"
                    "**Все эти опции не обязательны, можно отправить хоть пустую рамку**\n"
                    f"**Пример:** {p}embed\n"
                    "==Server update!==\n"
                    "--Added Moderator role!--\n"
                )
            )
            reply.set_footer(text = f"{ctx.author}", icon_url = f"{ctx.author.avatar_url}")
            await ctx.send(embed = reply)

    @reaction_roles.error
    async def reaction_roles_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            p = ctx.prefix
            cmd = ctx.command.name
            reply = discord.Embed(
                title = f"❓ Об аргументах `{p}{cmd}`",
                description = (
                    f"**Описание:** настраивает реакции под сообщением так, чтобы за них выдавались роли.\n"
                    f'**Использование:** `{p}{cmd} @Роль`\n'
                )
            )
            reply.set_footer(text = f"{ctx.author}", icon_url = f"{ctx.author.avatar_url}")
            await ctx.send(embed = reply)
    
    @generate_invite.error
    async def generate_invite_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            p = ctx.prefix
            cmd = ctx.command.name
            reply = discord.Embed(
                title = f"❓ Об аргументах `{p}{cmd}`",
                description = (
                    f"**Описание:** генерирует ссылку для приглашения выбранного бота\n"
                    f'**Использование:** `{p}{cmd} @Бот`\n'
                )
            )
            reply.set_footer(text = f"{ctx.author}", icon_url = f"{ctx.author.avatar_url}")
            await ctx.send(embed = reply)

def setup(client):
    client.add_cog(utility(client))
