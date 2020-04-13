import discord
from discord.ext import commands
from discord.ext.commands import Bot
import asyncio, os, datetime

import pymongo

from box.db_worker import cluster
from functions import detect, get_field, has_permissions

db = cluster["guilds"]

mute_role_name = "Мут"

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

def switch(text, from_word, to_word):
    wid = len(from_word)
    length = len(text)
    i = 0
    out = ""
    while i < length:
        if text[i:i + wid] == from_word:
            out += to_word
            i += wid - 1
        else:
            out += text[i]
        i += 1
    return out

def find_alias(table, word):
    out = None
    for key in table:
        if word in table[key]:
            out = key
            break
    return out

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

class settings(commands.Cog):
    def __init__(self, client):
        self.client = client

    #========Events=========

    @commands.Cog.listener()
    async def on_ready(self):
        print(">> Settings cog is loaded")
    
    # If bot removed
    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        collection = db["channels"]
        collection.find_one_and_delete({"_id": guild.id})
        collection = db["levers"]
        collection.find_one_and_delete({"_id": guild.id})
        collection = db["welcome"]
        collection.find_one_and_delete({"_id": guild.id})

    # Send welcome and give roles
    @commands.Cog.listener()
    async def on_member_join(self, member):
        collection = db["welcome"]
        data = collection.find_one(
            {"_id": member.guild.id}
        )
        if data != None:
            channel_id = get_field(data, "channel_id")
            text = get_field(data, "message")
            role_ids = get_field(data, "roles")

            if channel_id != None and text != None:
                channel = member.guild.get_channel(channel_id)
                if channel != None:
                    msg = switch(text, "{user}", f"{member.mention}")
                    
                    await channel.send(msg)
            
            if role_ids != None:
                stored_roles = [member.guild.get_role(ID) for ID in role_ids]
                roles = []
                my_pos = member.guild.me.top_role.position

                for role in stored_roles:
                    if role != None and role.position < my_pos:
                        roles.append(role)
                del stored_roles

                await member.add_roles(*roles)

    #=======Commands==========
    
    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command(aliases = ["set-log-channel", "log-channel", "slc", "lc"])
    async def log_channel(self, ctx, c_search):
        channel = detect.channel(ctx.guild, c_search)

        args_passed = False
        if not has_permissions(ctx.author, ["administrator"]):
            reply = discord.Embed(
                title="❌ Недостаточно прав",
                description=(
                    "**Необходимые права:**\n"
                    f"> Администратор"
                ),
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        elif c_search.lower() == "delete":
            args_passed = True
            value = None
        
        elif channel == None:
            reply = discord.Embed(
                title="💢 Ошибка",
                description=f"Вы ввели {c_search}, подразумевая канал, но он не был найден",
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        else:
            args_passed = True
            value = channel.id
        
        if args_passed:
            collection = db["channels"]
            collection.find_one_and_update(
                {"_id": ctx.guild.id},
                {"$set": {"mod_log": value}},
                upsert=True
            )
            if value == None:
                text = "Канал для отчётов удалён"
            else:
                text = f"Канал для отчётов настроен как {channel.mention}"
            
            reply = discord.Embed(
                title="✅ Выполнено",
                description=text,
                color=col("dg")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)

    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command()
    async def welcome(self, ctx, param, *, text=None):
        p, cmd = ctx.prefix, ctx.command.name

        params = {
            "message": ["message", "msg", "m"],
            "channel": ["channel", "c"],
            "roles": ["roles", "role", "r"]
        }
        
        key = find_alias(params, param.lower())

        if not has_permissions(ctx.author, ["administrator"]):
            reply = discord.Embed(
                title="❌ Недостаточно прав",
                description=(
                    "**Необходимые права:**\n"
                    f"> Администратор"
                ),
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)

        elif key == None:
            reply = discord.Embed(
                title="💢 Параметр не найден",
                description=(
                    f"Параметр `{param}` не найден. Параметры:\n"
                    "> `message`\n"
                    "> `channel`\n"
                    "> `roles`\n"
                    "Подробнее о параметре:\n"
                    f"`{p}{cmd} message / channel / roles`\n"
                ),
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        elif key == "message":
            if text == None:
                reply = discord.Embed(
                    title=f"💬 `{p}{cmd}`: сообщение",
                    description=(
                        "**Описание:** настраивает приветственное сообщение.\n"
                        "-> Если хотите упомянуть зашедшего, впишите `{user}`\n"
                        f"**Использование:** `{p}{cmd} {key} Текст сообщения`\n"
                        f"**Сброс:** `{p}{cmd} {key} delete`\n"
                        f"**Пример:** `{p}{cmd} {key} Добро пожаловать, " + "{user}`"
                    )
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)
            
            else:
                if text.lower() == "delete":
                    value = None
                    desc = "Сообщение удалено"
                else:
                    value = text[:+500]
                    desc = f"**Новое сообщение:** {value}"
                
                collection = db["welcome"]
                collection.find_one_and_update(
                    {"_id": ctx.guild.id},
                    {"$set": {"message": value}},
                    upsert=True
                )

                reply = discord.Embed(
                    title="✅ Настроено",
                    description=desc,
                    color=col("dg")
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)

        elif key == "channel":
            if text == None:
                reply = discord.Embed(
                    title=f"#️⃣ `{p}{cmd}`: канал",
                    description=(
                        "**Описание:** настраивает канал для приветствий.\n"
                        f"**Использование:** `{p}{cmd} {key} #канал`\n"
                        f"**Сброс:** `{p}{cmd} {key} delete`\n"
                        f"**Пример:** {p}{cmd} {key} {ctx.channel.mention}"
                    )
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)
            
            else:
                channel = detect.channel(ctx.guild, text)

                if text.lower() != "delete" and channel == None:
                    reply = discord.Embed(
                        title="💢 Ошибка",
                        description=f"Вы указали {text}, подразумевая канал, но он не был найден",
                        color=col("dr")
                    )
                    reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                    await ctx.send(embed=reply)

                else:
                    if text.lower() == "delete":
                        value = None
                        desc = "Канал сброшен"

                    else:
                        value = channel.id
                        desc = f"**Канал:** {channel.mention}"
                    
                    collection = db["welcome"]
                    collection.find_one_and_update(
                        {"_id": ctx.guild.id},
                        {"$set": {"channel_id": value}},
                        upsert=True
                    )

                    reply = discord.Embed(
                        title="✅ Настроено",
                        description=desc,
                        color=col("dg")
                    )
                    reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                    await ctx.send(embed=reply)

        elif key == "roles":
            if text == None:
                reply = discord.Embed(
                    title=f"🎗 `{p}{cmd}`: роли",
                    description=(
                        "**Описание:** настраивает роли, дающиеся при входе.\n"
                        f"**Использование:** `{p}{cmd} {key} @Роль1 @Роль2 ...`\n"
                        f"**Сброс:** `{p}{cmd} {key} delete`\n"
                        f"**Пример:** `{p}{cmd} {key} @Новичёк`"
                    )
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)
            
            else:
                raw_roles = text.split()
                roles = [detect.role(ctx.guild, rs) for rs in raw_roles]

                if text.lower() != "delete" and None in roles:
                    reply = discord.Embed(
                        title="💢 Ошибка",
                        description=f"Среди указанных ролей есть те, которые не удалось найти",
                        color=col("dr")
                    )
                    reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                    await ctx.send(embed=reply)

                else:
                    if text.lower() == "delete":
                        value = None
                        desc = "Роли сброшены"

                    else:
                        value = [r.id for r in roles]
                        
                        desc = "**Роли:**"
                        for ID in value:
                            desc += f"\n> <@&{ID}>"
                    
                    collection = db["welcome"]
                    collection.find_one_and_update(
                        {"_id": ctx.guild.id},
                        {"$set": {"roles": value}},
                        upsert=True
                    )

                    reply = discord.Embed(
                        title="✅ Настроено",
                        description=desc,
                        color=col("dg")
                    )
                    reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                    await ctx.send(embed=reply)

    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command(aliases=["how-set", "config"])
    async def how_set(self, ctx):
        p = ctx.prefix
        if not has_permissions(ctx.author, ["administrator"]):
            reply = discord.Embed(
                title="❌ Недостаточно прав",
                description=(
                    "**Необходимые права:**\n"
                    f"> Администратор"
                ),
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        else:
            collection = db["welcome"]
            w_data = collection.find_one(
                {"_id": ctx.guild.id}
            )

            collection = db["levers"]
            on_off = collection.find_one(
                {"_id": ctx.guild.id}
            )

            wc_id = get_field(w_data, "channel_id")
            wm = get_field(w_data, "message")
            wr = get_field(w_data, "roles")

            antis_on = get_field(on_off, "antispam")
            if antis_on == None:
                antis_on = False
            stats_on = get_field(on_off, "stats_on")
            if stats_on == None:
                stats_on = False

            if wc_id == None:
                wc_desc = "Отключен"
            else:
                wc_desc = f"<#{wc_id}>"
            if wm == None:
                wm_desc = "Отсутствует"
            else:
                wm_desc = wm
            if wr == None:
                wr_desc = "> Отключены\n"
            else:
                wr_desc = ""
                for r_id in wr:
                    wr_desc += f"> <@&{r_id}>\n"
            
            if antis_on:
                antis_desc = "✅ Включен"
            else:
                antis_desc = "❌ Выключен"
            if stats_on:
                stats_desc = "✅ Включена"
            else:
                stats_desc = "❌ Выключена"
            
            reply = discord.Embed(
                title="Текущие настройки бота",
                description=(
                    "**Действия с новичками**\n"
                    "Сообщение:\n"
                    f"> {wm_desc}\n"
                    "Канал:\n"
                    f"> {wc_desc}\n"
                    "Роли:\n"
                    f"{wr_desc}\n"
                    "**Статистика сервера:**\n"
                    f"> {stats_desc}\n\n"
                    "**Антиспам:**\n"
                    f"> {antis_desc}\n\n"
                    f"Таблица ролей за токены: `{p}auto-role-info`"
                ),
                color=col(30, 30, 130)
            )
            reply.set_thumbnail(url=f"{ctx.guild.icon_url}")
            await ctx.send(embed=reply)

    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command(aliases=["turn-antispam", "ats"])
    async def antispam(self, ctx, option="None"):
        p = ctx.prefix
        option = option.lower()
        true_options = ["on", "вкл", "1"]
        false_options = ["off", "выкл", "0"]

        if not has_permissions(ctx.author, ["administrator"]):
            reply = discord.Embed(
                title="❌ Недостаточно прав",
                description=(
                    "**Необходимые права:**\n"
                    f"> Администратор"
                ),
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        elif option not in true_options and option not in false_options:
            reply = discord.Embed(
                title="⚙ Антиспам",
                description=(
                    f"• Включить: `{p}antispam on`\n"
                    f"• Выключить: `{p}antispam off`\n"
                    "Введите один из параметров `on`, `off`"
                )
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)

        else:
            if option in true_options:
                option = True
                desc = "Антиспам включен ✅"
            else:
                option = False
                desc = "Антиспам выключен ❎"
            collection = db["levers"]

            collection.find_one_and_update(
                {"_id": ctx.guild.id},
                {"$set": {"antispam": option}},
                upsert=True
            )
            reply = discord.Embed(
                title="⚙ Выполнено",
                description=(
                    f"{desc}\n"
                    f"-> Текущие настройки: `{p}how-set`"
                ),
                color=col("dg")
            )
            await ctx.send(embed=reply)

    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command(aliases = ["server-stats", "stats", "statistics", "ss"])
    async def server_stats(self, ctx, option="None"):
        p = ctx.prefix
        option = option.lower()
        true_options = ["on", "вкл", "1"]
        false_options = ["off", "выкл", "0"]

        if not has_permissions(ctx.author, ["administrator"]):
            reply = discord.Embed(
                title="❌ Недостаточно прав",
                description=(
                    "**Необходимые права:**\n"
                    f"> Администратор"
                ),
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        elif option not in true_options and option not in false_options:
            reply = discord.Embed(
                title="⚙ Отображение статистики сервера",
                description=(
                    f"• Включить: `{p}server-stats on`\n"
                    f"• Выключить: `{p}server-stats off`\n"
                    "Введите один из параметров `on`, `off`"
                )
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)

        else:
            if option in true_options:
                option = True
                desc = "Отображение статистики сервера включено ✅"
            else:
                option = False
                desc = "Отображение статистики сервера выключено ❎"
            collection = db["levers"]

            collection.find_one_and_update(
                {"_id": ctx.guild.id},
                {"$set": {"stats_on": option}},
                upsert=True
            )
            reply = discord.Embed(
                title="⚙ Выполнено",
                description=(
                    f"{desc}\n"
                    f"-> Текущие настройки: `{p}how-set`"
                ),
                color=col("dg")
            )
            await ctx.send(embed=reply)

    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command(aliases=["token-operator"])
    async def token_operator(self, ctx, *, role_s):
        if not has_permissions(ctx.author, ["administrator"]):
            reply = discord.Embed(
                title="❌ Недостаточно прав",
                description=(
                    "**Необходимые права:**\n"
                    f"> Администратор"
                ),
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        else:
            correct_role_arg = True
            if role_s.lower() == "delete":
                role = None
                desc = "Роль переводчика токенов удалена"
            else:
                role = detect.role(ctx.guild, role_s)
                if role is None:
                    correct_role_arg = False

                    reply = discord.Embed(
                        title="💢 Упс",
                        description=f"Вы ввели {role_s}, подразумевая роль, но она не была найдена.",
                        color=col("dr")
                    )
                    reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                    await ctx.send(embed=reply)
                else:
                    desc = f"Роль переводчика токенов настроена как <@&{role.id}>"
            
            if correct_role_arg:
                collection = db["tokens"]
                collection.find_one_and_update(
                    {"_id": ctx.guild.id},
                    {"$set": {"master_role": role.id}},
                    upsert=True
                )
                reply = discord.Embed(
                    title="✅ Выполнено",
                    description=desc,
                    color=col("dg")
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)

    #=======Errors==========
    @welcome.error
    async def welcome_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            p = ctx.prefix
            cmd = ctx.command.name
            reply = discord.Embed(
                title = f"❓ Об аргументах `{p}{cmd}`",
                description = (
                    f"**Описание:** настраивает действия с новичками, имеет 3 раздела.\n"
                    f"`{p}{cmd} message` - приветствие\n"
                    f"`{p}{cmd} channel` - канал для приветствия\n"
                    f"`{p}{cmd} roles` - роли для новичков\n"
                    f'**Назначение:** `{p}{cmd} Раздел Значение`\n'
                    f"**Удаление:** `{p}{cmd} Раздел delete`\n"
                )
            )
            reply.set_footer(text = f"{ctx.author}", icon_url = f"{ctx.author.avatar_url}")
            await ctx.send(embed = reply)


    @log_channel.error
    async def log_channel_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            p = ctx.prefix
            cmd = ctx.command.name
            reply = discord.Embed(
                title = f"❓ Об аргументах `{p}{cmd}`",
                description = (
                    f"**Описание:** настраивает канал для логов и отчётов\n"
                    f'**Назначение:** `{p}{cmd} #канал`\n'
                    f"**Удаление:** `{p}{cmd} delete`\n"
                )
            )
            reply.set_footer(text = f"{ctx.author}", icon_url = f"{ctx.author.avatar_url}")
            await ctx.send(embed = reply)

    @token_operator.error
    async def token_operator_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            p = ctx.prefix
            cmd = ctx.command.name
            reply = discord.Embed(
                title = f"❓ Об аргументах `{p}{cmd}`",
                description = (
                    f"**Описание:** настраивает роль, дающую права на начисление токенов\n"
                    f'**Назначение:** `{p}{cmd} @Роль`\n'
                    f"**Удаление:** `{p}{cmd} delete`\n"
                )
            )
            reply.set_footer(text = f"{ctx.author}", icon_url = f"{ctx.author.avatar_url}")
            await ctx.send(embed = reply)

def setup(client):
    client.add_cog(settings(client))