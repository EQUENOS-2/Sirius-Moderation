owner_ids = [301295716066787332]


def visual_delta(delta):
    if "int" in f"{type(delta)}".lower():
        seconds = delta
        t_days = 0
    else:
        seconds = delta.seconds
        t_days = delta.days
    
    expanded_delta = {
        "сек": seconds % 60,
        "мин": seconds // 60 % 60,
        "ч": seconds // 3600 % 24,
        "дн": t_days % 7,
        "нед": t_days // 7
    }

    out = ""
    for key in expanded_delta:
        num = expanded_delta[key]
        if num > 0:
            out = f"{num} {key} " + out
    if out == "":
        out = "0 сек"
    out.strip()
    return out


def rus_timestamp(datetime):
    months = [
        "января", "февраля",
        "марта", "апреля", "мая",
        "июня", "июля", "августа",
        "сентября", "октября", "ноября",
        "декабря"
    ]
    date = f"{datetime.day} {months[datetime.month - 1]} {datetime.year}"
    time = f"{datetime}"[-15:][:+8]
    return f"{date}, {time}"


def get_field(Dict, *key_words):
    if Dict is not None:
        for key in key_words:
            if key in Dict:
                Dict = Dict[key]
            else:
                Dict = None
                break
    return Dict


def carve_int(string):
    nums = [str(i) for i in range(10)]
    out = ""
    found = False
    for letter in string:
        if letter in nums:
            found = True
            out += letter
        elif found:
            break
    if out == "":
        out = None
    else:
        out = int(out)
    return out


def perms_for(role):
    owned = {
    "create_instant_invite": role.permissions.create_instant_invite,
    "kick_members": role.permissions.kick_members,
    "ban_members": role.permissions.ban_members,
    "administrator": role.permissions.administrator,
    "manage_channels": role.permissions.manage_channels,
    "manage_roles": role.permissions.manage_roles,
    "manage_guild": role.permissions.manage_guild,
    "view_audit_log": role.permissions.view_audit_log,
    "change_nickname": role.permissions.change_nickname,
    "manage_nicknames": role.permissions.manage_nicknames,
    "manage_webhooks": role.permissions.manage_webhooks,
    "manage_messages": role.permissions.manage_messages,
    "manage_emojis": role.permissions.manage_emojis,
    "mention_everyone": role.permissions.mention_everyone
    }
    return owned


def has_permissions(member, perm_array):
    to_have = len(perm_array)
    if member.id == member.guild.owner_id or member.id in owner_ids:
        return True
    else:
        found_num = 0
        found = []
        for role in member.roles:
            owned = perms_for(role)
            if owned["administrator"]:
                found_num = to_have
            else:
                for perm in perm_array:
                    if not perm in found and owned[perm]:
                        found.append(perm)
                        found_num += 1
            if found_num >= to_have:
                break
                    
        return True if found_num >= to_have else False


def has_roles(member, role_array):
    has_them = True
    if not has_permissions(member, ["administrator"]):
        for role in role_array:
            if "int" in f"{type(role)}".lower():
                role = member.guild.get_role(role)
            if not role in member.roles:
                has_them = False
                break
    return has_them


class detect:
    @staticmethod
    def member(guild, search):
        ID = carve_int(search)
        if ID is None:
            ID = 0
        member = guild.get_member(ID)
        if member is None:
            member = guild.get_member_named(search)
        return member
    
    @staticmethod
    def channel(guild, search):
        ID = carve_int(search)
        if ID is None:
            ID = 0
        channel = guild.get_channel(ID)
        if channel is None:
            for c in guild.channels:
                if c.name == search:
                    channel = c
                    break
        return channel
    
    @staticmethod
    def role(guild, search):
        ID = carve_int(search)
        if ID is None:
            ID = 0
        role = guild.get_role(ID)
        if role is None:
            for r in guild.roles:
                if r.name == search:
                    role = r
                    break
        return role
    
    @staticmethod
    def user(search, client):
        ID = carve_int(search)
        user = None
        if ID is not None:
            user = client.get_user(ID)
        return user