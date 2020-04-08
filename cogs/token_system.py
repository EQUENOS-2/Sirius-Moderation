import discord
from discord.ext import commands
from discord.ext.commands import Bot
import asyncio, os, datetime

import pymongo
from box.db_worker import cluster
from functions import get_field, detect, has_permissions, has_roles

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

def try_int(string):
    try:
        return int(string)
    except ValueError:
        return None

async def process_auto_roles(member, data=None):
    if data is None:
        collection = db["tokens"]
        data = collection.find_one(
            {"_id": member.guild.id},
            projection={
                "add": True,
                "remove":True,
                f"members.{member.id}": True
            }
        )
    to_add = get_field(data, "add")
    to_remove = get_field(data, "remove")
    bal = get_field(data, "members", f"{member.id}")
    if to_add is None:
        to_add = {}
    if to_remove is None:
        to_remove = {}
    if bal is None:
        bal = 0
    
    can_be_added = []
    can_be_removed = []
    for id_key in to_add:
        if to_add[id_key] <= bal:
            if not (id_key in to_remove and to_remove[id_key] <= bal and to_remove[id_key] >= to_add[id_key]):
                can_be_added.append(int(id_key))
    for id_key in to_remove:
        if to_remove[id_key] <= bal:
            can_be_removed.append(int(id_key))
    
    to_remove = []
    to_add = []
    for role_id in can_be_removed:
        role = member.guild.get_role(role_id)
        if role in member.roles:
            to_remove.append(role)
    for role_id in can_be_added:
        role = member.guild.get_role(role_id)
        if role is not None and role not in member.roles:
            to_add.append(role)
    
    await member.remove_roles(*to_remove)
    await member.add_roles(*to_add)

class token_system(commands.Cog):
    def __init__(self, client):
        self.client = client

    #========== Events ===========
    # On ready
    @commands.Cog.listener()
    async def on_ready(self):
        print(">> Token system cog is loaded")
    
    # If bot removed
    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        collection = db["tokens"]
        collection.find_one_and_delete({"_id": guild.id})

    # Refresh token roles
    @commands.Cog.listener()
    async def on_member_join(self, member):
        await process_auto_roles(member)

    #========= Commands ==========
    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command(aliases=["change-tokens", "ct", "change", "add-tokens", "addt"])
    async def change_tokens(self, ctx, amount, *, member_s=None):
        collection = db["tokens"]
        if member_s is None:
            member = ctx.author
        else:
            member = detect.member(ctx.guild, member_s)
        
        result = collection.find_one(
            {"_id": ctx.guild.id},
            projection={"master_role": True}
        )
        mr_id = get_field(result, "master_role")

        if not has_roles(ctx.author, [mr_id]):
            reply = discord.Embed(
                title="❌ Недостаточно прав",
                description=(
                    "**Необходимые права:**\n"
                    "> Администратор\n"
                    "или\n"
                    "> Роль переводчика токенов"
                ),
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        elif member is None:
            reply = discord.Embed(
                title="💢 Упс",
                description=f"Вы указали {member_s}, подразумевая участника, но он не был найден",
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        elif try_int(amount) is None:
            reply = discord.Embed(
                title="💢 Упс",
                description=f"Аргумент \"{amount}\" должен быть целым числом, как `5` или `-5`",
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        else:
            amount = int(amount)
            amount_desc = f"{amount}"
            if amount_desc[0] != "-":
                amount_desc = f"+{amount_desc}"

            collection.find_one_and_update(
                {"_id": ctx.guild.id},
                {"$inc": {f"members.{member.id}": amount}},
                projection={f"members.{member.id}": True, "add": True, "remove": True},
                upsert=True
            )
            reply = discord.Embed(
                title="♻ Выполнено",
                description=f"{amount_desc} 💰 участнику **{member}**",
                color=col("dg")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)

            await process_auto_roles(member)

    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command(aliases=["bal"])
    async def balance(self, ctx, *, member_s=None):
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
            collection = db["tokens"]
            result = collection.find_one(
                {"_id": ctx.guild.id, f"members.{member.id}": {"$exists": True}},
                projection={f"members.{member.id}": True}
            )
            amount = get_field(result, "members", f"{member.id}")
            if amount is None:
                amount = 0
            
            reply = discord.Embed(
                title=f"Баланс {member}",
                description=f"**{amount}** 💰",
                color=member.color
            )
            reply.set_thumbnail(url=f"{member.avatar_url}")
            await ctx.send(embed=reply)

    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command(aliases=["leaderboard", "leaders", "lb"])
    async def top(self, ctx, page="1"):
        interval = 10

        if not page.isdigit():
            reply = discord.Embed(
                title="💢 Упс",
                description=f"Номер страницы ({page}) должен быть целым числом",
                color=col("dg")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        else:
            page = int(page)
            collection = db["tokens"]
            result = collection.find_one(
                {"_id": ctx.guild.id},
                projection={"members": True}
            )
            member_list = get_field(result, "members")

            if member_list is None or member_list == {}:
                reply = discord.Embed(
                    title="📊 Топ участников",
                    description="🚕 🚗 🚓",
                    color=ctx.guild.me.color
                )
                reply.set_thumbnail(url=f"{ctx.guild.icon_url}")
                await ctx.send(embed=reply)
            
            else:
                total_pairs = len(member_list)
                total_pages = (total_pairs - 1) // interval + 1
                if page > total_pages or page < 1:
                    reply = discord.Embed(
                        title="📖 Страница не найдена",
                        description=f"Всего страниц: {total_pages}"
                    )
                    reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                    await ctx.send(embed=reply)
                
                else:
                    member_list = [(int(key), member_list[key]) for key in member_list]
                    member_list.sort(reverse=True, key=lambda pair: pair[1])
                    lower_bound = (page - 1) * interval
                    upper_bound = min(page * interval, total_pairs)

                    desc = ""
                    for i in range(lower_bound, upper_bound):
                        pair = member_list[i]
                        member = ctx.guild.get_member(pair[0])
                        desc += f"**{i+1})** {member} • **{pair[1]}** 💰\n"
                    
                    reply = discord.Embed(
                        title="📊 Топ участников",
                        description=desc,
                        color=ctx.guild.me.color
                    )
                    reply.set_thumbnail(url=f"{ctx.guild.icon_url}")
                    await ctx.send(embed=reply)

    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command(aliases=["auto-role-add", "auto-role", "ara"])
    async def auto_role_add(self, ctx, bound, role_s):
        bound = bound.lower()
        if not has_permissions(ctx.author, ["administrator"]):
            reply = discord.Embed(
                title="❌ Недостаточно прав",
                description=(
                    "**Необходимые права:**\n"
                    "> Администратор"
                ),
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        elif bound != "delete" and not bound.isdigit():
            reply = discord.Embed(
                title="💢 Упс",
                description=f"Аргумент \"{bound}\" должен быть целым числом или параметром `delete`",
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)

        else:
            role = detect.role(ctx.guild, role_s)
            if role is None:
                reply = discord.Embed(
                    title="💢 Упс",
                    description=f"Вы ввели {role_s}, подразумевая роль, но она не была найдена.",
                    color=col("dr")
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)
            
            else:
                collection = db["tokens"]
                if bound == "delete":
                    collection.find_one_and_update(
                        {"_id": ctx.guild.id},
                        {"$unset": {f"add.{role.id}": ""}}
                    )
                    desc = f"Роль <@&{role.id}> больше не выдаётся автоматически"
                else:
                    collection.find_one_and_update(
                        {"_id": ctx.guild.id},
                        {"$set": {f"add.{role.id}": int(bound)}},
                        upsert=True
                    )
                    desc = f"Роль <@&{role.id}> теперь выдаётся за {bound}+ токенов"
                
                reply = discord.Embed(
                    title="✅ Выполнено",
                    description=desc,
                    color=col("dg")
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)

    @commands.cooldown(1, 3, commands.BucketType.member)
    @commands.command(aliases=["auto-role-remove", "arr"])
    async def auto_role_remove(self, ctx, bound, role_s):
        bound = bound.lower()
        if not has_permissions(ctx.author, ["administrator"]):
            reply = discord.Embed(
                title="❌ Недостаточно прав",
                description=(
                    "**Необходимые права:**\n"
                    "> Администратор"
                ),
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)
        
        elif bound != "delete" and not bound.isdigit():
            reply = discord.Embed(
                title="💢 Упс",
                description=f"Аргумент \"{bound}\" должен быть целым числом или параметром `delete`",
                color=col("dr")
            )
            reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
            await ctx.send(embed=reply)

        else:
            role = detect.role(ctx.guild, role_s)
            if role is None:
                reply = discord.Embed(
                    title="💢 Упс",
                    description=f"Вы ввели {role_s}, подразумевая роль, но она не была найдена.",
                    color=col("dr")
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)
            
            else:
                collection = db["tokens"]
                if bound == "delete":
                    collection.find_one_and_update(
                        {"_id": ctx.guild.id},
                        {"$unset": {f"remove.{role.id}": ""}}
                    )
                    desc = f"Роль <@&{role.id}> больше не снимается автоматически"
                else:
                    collection.find_one_and_update(
                        {"_id": ctx.guild.id},
                        {"$set": {f"remove.{role.id}": int(bound)}},
                        upsert=True
                    )
                    desc = f"Роль <@&{role.id}> теперь снимается при достижении {bound}+ токенов"
                
                reply = discord.Embed(
                    title="✅ Выполнено",
                    description=desc,
                    color=col("dg")
                )
                reply.set_footer(text=f"{ctx.author}", icon_url=f"{ctx.author.avatar_url}")
                await ctx.send(embed=reply)

    @commands.cooldown(1, 5, commands.BucketType.member)
    @commands.command(aliases=["auto-role-info", "ari", "token-roles"])
    async def auto_role_info(self, ctx):
        collection = db["tokens"]
        result = collection.find_one(
            {"_id": ctx.guild.id},
            projection={"add": True, "remove": True}
        )
        to_add = get_field(result, "add")
        to_remove = get_field(result, "remove")

        if to_add is None or to_add == {}:
            add_desc = "Отсутствуют"
        else:
            add_desc = ""
            for id_key in to_add:
                add_desc += f"**->** <@&{id_key}> • {to_add[id_key]}+ 💰\n"
        
        if to_remove is None or to_remove == {}:
            remove_desc = "Отсутствуют"
        else:
            remove_desc = ""
            for id_key in to_remove:
                remove_desc += f"**<-** <@&{id_key}> • {to_remove[id_key]}+ 💰\n"
        
        reply = discord.Embed(
            title="🎫 Действия с ролями",
            color=ctx.guild.me.color
        )
        reply.add_field(name="**Выдаются за токены**", value=add_desc, inline=False)
        reply.add_field(name="**Снимаются за токены**", value=remove_desc, inline=False)
        reply.set_thumbnail(url=f"{ctx.guild.icon_url}")
        await ctx.send(embed=reply)

    #======== Errors ==========
    @change_tokens.error
    async def change_tokens_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            p = ctx.prefix
            cmd = ctx.command.name
            reply = discord.Embed(
                title = f"❓ Об аргументах `{p}{cmd}`",
                description = (
                    f"**Описание:** начисляет токены участнику\n"
                    f'**Использование:** `{p}{cmd} Кол-во @Участник`\n'
                    f"**Примеры:** `{p}{cmd} -6 @User#1234`\n"
                    f">> `{p}{cmd} +4`"
                )
            )
            reply.set_footer(text = f"{ctx.author}", icon_url = f"{ctx.author.avatar_url}")
            await ctx.send(embed = reply)

    @auto_role_add.error
    async def auto_role_add_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            p = ctx.prefix
            cmd = ctx.command.name
            reply = discord.Embed(
                title = f"❓ Об аргументах `{p}{cmd}`",
                description = (
                    f"**Описание:** настраивает автоматическую выдачу роли за достижение указанной планки баланса.\n"
                    f'**Использование:** `{p}{cmd} Планка @Роль`\n'
                    f"**Удаление:** `{p}{cmd} delete @Роль`\n"
                    f"**Пример:** `{p}{cmd} 5 @Роль`"
                )
            )
            reply.set_footer(text = f"{ctx.author}", icon_url = f"{ctx.author.avatar_url}")
            await ctx.send(embed = reply)
    
    @auto_role_remove.error
    async def auto_role_remove_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            p = ctx.prefix
            cmd = ctx.command.name
            reply = discord.Embed(
                title = f"❓ Об аргументах `{p}{cmd}`",
                description = (
                    f"**Описание:** настраивает автоматическое снятие роли за достижение указанной планки баланса.\n"
                    f'**Использование:** `{p}{cmd} Планка @Роль`\n'
                    f"**Удаление:** `{p}{cmd} delete @Роль`\n"
                    f"**Пример:** `{p}{cmd} 10 @Роль`"
                )
            )
            reply.set_footer(text = f"{ctx.author}", icon_url = f"{ctx.author.avatar_url}")
            await ctx.send(embed = reply)

def setup(client):
    client.add_cog(token_system(client))