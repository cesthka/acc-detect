"""
================================================================================
  DISCORD BOT - RARE ACCOUNT DETECTION (enriched version)
  buyer/owner - SQLite - !set/!scan by category - boost - rarity level
  + MODERATION: ban / unban / mute / unmute / tempmute (by ID or mention,
    works even if the person is NOT on the server)
================================================================================
NOTE: Nitro badges (Bronze..Opal) are NOT exposed by the Discord API and
therefore cannot be detected by a bot. We only detect THIS server's BOOST
(via premium_since).
================================================================================
"""

import os
import datetime
import sqlite3
import asyncio
import re
import discord
from discord.ext import commands

try:
    from wordfreq import zipf_frequency
    WORDFREQ_OK = True
except ImportError:
    WORDFREQ_OK = False

# ==============================================================================
#  BASIC SETTINGS
# ==============================================================================

BUYER_ID = 142365250803466240
TOKEN = os.environ.get("DISCORD_TOKEN", "PASTE_YOUR_TOKEN_HERE_IF_YOU_WANT")
DB_PATH = os.environ.get("DB_PATH", "bot.db")
WORD_THRESHOLD = 2.5

OG_THRESHOLDS_LIST = [
    ("og2016", datetime.datetime(2016, 1, 1, tzinfo=datetime.timezone.utc)),
    ("og2017", datetime.datetime(2017, 1, 1, tzinfo=datetime.timezone.utc)),
    ("og2018", datetime.datetime(2018, 1, 1, tzinfo=datetime.timezone.utc)),
]

# Boost tiers (months -> key), highest to lowest.
BOOST_TIERS = [(24, "boost24"), (18, "boost18"), (15, "boost15"), (12, "boost12"),
               (9, "boost9"), (6, "boost6"), (3, "boost3"), (2, "boost2"), (1, "boost1")]
BOOST_MONTHS = {k: m for m, k in BOOST_TIERS}

# ==============================================================================
#  CATALOG
# ==============================================================================

SET_ITEMS = {
    "early":      {"label": "Early Supporter",            "type": "role"},
    "hypesquad":  {"label": "HypeSquad Events",           "type": "role"},
    "bravery":    {"label": "HypeSquad Bravery",          "type": "role"},
    "brilliance": {"label": "HypeSquad Brilliance",       "type": "role"},
    "balance":    {"label": "HypeSquad Balance",          "type": "role"},
    "bughunter":  {"label": "Bug Hunter",                 "type": "role"},
    "bughunter2": {"label": "Bug Hunter (Gold)",          "type": "role"},
    "botdev":     {"label": "Early Verified Bot Dev",     "type": "role"},
    "mod":        {"label": "Moderator Programs Alumni",  "type": "role"},
    "partner":    {"label": "Discord Partner",            "type": "role"},
    "staff":      {"label": "Discord Staff",              "type": "role"},
    "boost1":     {"label": "Boost 1 month",              "type": "role"},
    "boost2":     {"label": "Boost 2 months",             "type": "role"},
    "boost3":     {"label": "Boost 3 months",             "type": "role"},
    "boost6":     {"label": "Boost 6 months",             "type": "role"},
    "boost9":     {"label": "Boost 9 months",             "type": "role"},
    "boost12":    {"label": "Boost 12 months",            "type": "role"},
    "boost15":    {"label": "Boost 15 months",            "type": "role"},
    "boost18":    {"label": "Boost 18 months",            "type": "role"},
    "boost24":    {"label": "Boost 24 months",            "type": "role"},
    "og2016":     {"label": "OG - before 2016",           "type": "role"},
    "og2017":     {"label": "OG - before 2017",           "type": "role"},
    "og2018":     {"label": "OG - before 2018",           "type": "role"},
    "pseudo2":    {"label": "2-character username",       "type": "role"},
    "pseudo3":    {"label": "3-character username",       "type": "role"},
    "mot":        {"label": "Username: real word (FR/EN)", "type": "role"},
    "chiffres":   {"label": "Username: digits only",      "type": "role"},
    "alertrole":  {"label": "Ping role (alerts)",         "type": "role"},
    "logs":       {"label": "Logs channel (joins)",       "type": "channel"},
    "scanlog":    {"label": "Scan channel",               "type": "channel"},
}

CATEGORIES = {
    "🏅 Badges":       ["early", "hypesquad", "bravery", "brilliance", "balance",
                        "bughunter", "bughunter2", "botdev", "mod", "partner", "staff"],
    "🚀 Boost":        ["boost1", "boost2", "boost3", "boost6", "boost9",
                        "boost12", "boost15", "boost18", "boost24"],
    "📅 Account age":  ["og2016", "og2017", "og2018"],
    "✨ Username":     ["pseudo2", "pseudo3", "mot", "chiffres"],
    "🚨 Alert":        ["alertrole"],
    "📋 Channels":     ["logs", "scanlog"],
}

# Keys we can actually detect (for scan/list/stats/top).
DETECT_KEYS = [k for k, v in SET_ITEMS.items() if v["type"] == "role" and k != "alertrole"]

DEFAULT_EMOJIS = {
    "early": "🥇", "hypesquad": "🎉", "bravery": "🛡️", "brilliance": "🔮", "balance": "⚖️",
    "bughunter": "🐛", "bughunter2": "🐛", "botdev": "🤖", "mod": "🛡️", "partner": "🤝", "staff": "👑",
    "boost1": "🚀", "boost2": "🚀", "boost3": "🚀", "boost6": "🚀", "boost9": "🚀",
    "boost12": "🚀", "boost15": "🚀", "boost18": "🚀", "boost24": "🚀",
    "og2016": "📅", "og2017": "📅", "og2018": "📅",
    "pseudo2": "✨", "pseudo3": "✨", "mot": "🔤", "chiffres": "🔢",
}

JOIN_TITLE_DEFAULT = "🌟 A rare account joined the server!"

# --- Rarity scale ---
WEIGHTS = {
    # Badges (most prestigious to most common)
    "staff": 10, "partner": 8, "botdev": 6, "bughunter2": 6, "mod": 5, "bughunter": 4,
    "hypesquad": 3, "early": 3, "bravery": 1, "brilliance": 1, "balance": 1,
    # Account age
    "og2016": 5, "og2017": 3, "og2018": 2,
    # Username
    "pseudo2": 5, "pseudo3": 3, "mot": 2, "chiffres": 1,
    # Boost (bonus, low weight)
    "boost1": 1, "boost2": 1, "boost3": 2, "boost6": 2, "boost9": 3,
    "boost12": 3, "boost15": 4, "boost18": 4, "boost24": 5,
}

# Tiers: (minimum score, name, emoji, color)
LEVELS = [
    (0,  "Common",     "⚪", discord.Color.light_grey()),
    (2,  "Uncommon",   "🟢", discord.Color.green()),
    (5,  "Rare",       "🔵", discord.Color.blue()),
    (9,  "Epic",       "🟣", discord.Color.purple()),
    (14, "Legendary",  "🟡", discord.Color.gold()),
    (20, "Mythic",     "🔴", discord.Color.red()),
]

# ==============================================================================
#  DATABASE
# ==============================================================================

def db():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = db()
    conn.execute("CREATE TABLE IF NOT EXISTS config   (key TEXT PRIMARY KEY, value INTEGER)")
    conn.execute("CREATE TABLE IF NOT EXISTS owners   (user_id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS emojis   (key TEXT PRIMARY KEY, emoji TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS messages (key TEXT PRIMARY KEY, contenu TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS fond     (id INTEGER PRIMARY KEY, data BLOB)")
    conn.execute("CREATE TABLE IF NOT EXISTS salons_public (channel_id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS vues (profil_id INTEGER, viewer_id INTEGER, "
                 "PRIMARY KEY (profil_id, viewer_id))")
    conn.execute("CREATE TABLE IF NOT EXISTS bios     (user_id INTEGER PRIMARY KEY, texte TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS couleurs (user_id INTEGER PRIMARY KEY, couleur TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS fonds_membres (user_id INTEGER PRIMARY KEY, data BLOB)")
    # Persistent mutes (survive restart)
    conn.execute("CREATE TABLE IF NOT EXISTS mutes (guild_id INTEGER, user_id INTEGER, "
                 "until INTEGER, reason TEXT, PRIMARY KEY (guild_id, user_id))")
    conn.commit(); conn.close()


def _load(table, c1, c2):
    conn = db()
    rows = conn.execute(f"SELECT {c1}, {c2} FROM {table}").fetchall()
    conn.close()
    return {k: v for k, v in rows}


def set_config(key, value):
    CONFIG[key] = value
    conn = db()
    conn.execute("INSERT INTO config (key,value) VALUES (?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit(); conn.close()


def set_emoji(key, emoji):
    EMOJIS[key] = emoji
    conn = db()
    conn.execute("INSERT INTO emojis (key,emoji) VALUES (?,?) "
                 "ON CONFLICT(key) DO UPDATE SET emoji=excluded.emoji", (key, emoji))
    conn.commit(); conn.close()


def set_message(key, contenu):
    MESSAGES[key] = contenu
    conn = db()
    conn.execute("INSERT INTO messages (key,contenu) VALUES (?,?) "
                 "ON CONFLICT(key) DO UPDATE SET contenu=excluded.contenu", (key, contenu))
    conn.commit(); conn.close()


def load_owners():
    conn = db(); rows = conn.execute("SELECT user_id FROM owners").fetchall(); conn.close()
    return {r[0] for r in rows}


def add_owner(uid):
    conn = db(); conn.execute("INSERT OR IGNORE INTO owners (user_id) VALUES (?)", (uid,))
    conn.commit(); conn.close(); OWNERS.add(uid)


def remove_owner(uid):
    conn = db(); conn.execute("DELETE FROM owners WHERE user_id=?", (uid,))
    conn.commit(); conn.close(); OWNERS.discard(uid)


def load_background():
    conn = db()
    row = conn.execute("SELECT data FROM fond WHERE id=1").fetchone()
    conn.close()
    return row[0] if row else None


def set_background(data):
    global BG_DATA
    BG_DATA = data
    conn = db()
    conn.execute("DELETE FROM fond")
    if data is not None:
        conn.execute("INSERT INTO fond (id, data) VALUES (1, ?)", (data,))
    conn.commit(); conn.close()


def load_public_channels():
    conn = db(); rows = conn.execute("SELECT channel_id FROM salons_public").fetchall(); conn.close()
    return {r[0] for r in rows}


def add_public_channel(cid):
    conn = db(); conn.execute("INSERT OR IGNORE INTO salons_public (channel_id) VALUES (?)", (cid,))
    conn.commit(); conn.close(); PUBLIC_CHANNELS.add(cid)


def remove_public_channel(cid):
    conn = db(); conn.execute("DELETE FROM salons_public WHERE channel_id=?", (cid,))
    conn.commit(); conn.close(); PUBLIC_CHANNELS.discard(cid)


def record_view(profil_id, viewer_id):
    """Add a unique view (viewer -> profile) and return the profile's total views."""
    conn = db()
    conn.execute("INSERT OR IGNORE INTO vues (profil_id, viewer_id) VALUES (?, ?)", (profil_id, viewer_id))
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM vues WHERE profil_id=?", (profil_id,)).fetchone()[0]
    conn.close()
    return n


def count_views(profil_id):
    conn = db()
    n = conn.execute("SELECT COUNT(*) FROM vues WHERE profil_id=?", (profil_id,)).fetchone()[0]
    conn.close()
    return n


def views_per_profile():
    """Return {profile_id: number_of_views} for every viewed profile."""
    conn = db()
    rows = conn.execute("SELECT profil_id, COUNT(*) FROM vues GROUP BY profil_id").fetchall()
    conn.close()
    return dict(rows)


def set_bio(uid, texte):
    conn = db()
    if texte:
        BIOS[uid] = texte
        conn.execute("INSERT INTO bios (user_id, texte) VALUES (?,?) "
                     "ON CONFLICT(user_id) DO UPDATE SET texte=excluded.texte", (uid, texte))
    else:
        BIOS.pop(uid, None)
        conn.execute("DELETE FROM bios WHERE user_id=?", (uid,))
    conn.commit(); conn.close()


def set_color(uid, couleur):
    conn = db()
    if couleur:
        COLORS[uid] = couleur
        conn.execute("INSERT INTO couleurs (user_id, couleur) VALUES (?,?) "
                     "ON CONFLICT(user_id) DO UPDATE SET couleur=excluded.couleur", (uid, couleur))
    else:
        COLORS.pop(uid, None)
        conn.execute("DELETE FROM couleurs WHERE user_id=?", (uid,))
    conn.commit(); conn.close()


def set_member_background(uid, data):
    conn = db()
    conn.execute("DELETE FROM fonds_membres WHERE user_id=?", (uid,))
    if data is not None:
        conn.execute("INSERT INTO fonds_membres (user_id, data) VALUES (?,?)", (uid, data))
    conn.commit(); conn.close()


def member_background(uid):
    conn = db()
    row = conn.execute("SELECT data FROM fonds_membres WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    return row[0] if row else None


def member_color(uid):
    """Return an RGB tuple if the user set a color, otherwise None."""
    hexa = COLORS.get(uid)
    if not hexa:
        return None
    try:
        h = hexa.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return None


# --- Mutes (database) ---
def db_add_mute(gid, uid, until, reason):
    conn = db()
    conn.execute("INSERT INTO mutes (guild_id,user_id,until,reason) VALUES (?,?,?,?) "
                 "ON CONFLICT(guild_id,user_id) DO UPDATE SET until=excluded.until, reason=excluded.reason",
                 (gid, uid, until, reason))
    conn.commit(); conn.close()


def db_remove_mute(gid, uid):
    conn = db(); conn.execute("DELETE FROM mutes WHERE guild_id=? AND user_id=?", (gid, uid))
    conn.commit(); conn.close()


def db_mute_info(gid, uid):
    conn = db()
    row = conn.execute("SELECT until, reason FROM mutes WHERE guild_id=? AND user_id=?", (gid, uid)).fetchone()
    conn.close()
    return row  # (until, reason) or None


def db_all_mutes():
    conn = db()
    rows = conn.execute("SELECT guild_id, user_id, until, reason FROM mutes").fetchall()
    conn.close()
    return rows


def db_guild_mutes(gid):
    conn = db()
    rows = conn.execute("SELECT user_id, until, reason FROM mutes WHERE guild_id=?", (gid,)).fetchall()
    conn.close()
    return rows


FAME_TIERS = [(100, "Icon"), (40, "Legend"), (15, "Star"), (5, "Popular"), (1, "Known"), (0, "Unknown")]


def fame_title(v):
    for threshold, name in FAME_TIERS:
        if v >= threshold:
            return name
    return "Unknown"


def fame_rank(guild, uid):
    """Rank (1 = most viewed) of the user among server members. 0 if no views / non-member."""
    counts = views_per_profile()
    my_views = counts.get(uid, 0)
    if my_views <= 0:
        return 0
    ids = {m.id for m in guild.members}
    if uid not in ids:
        return 0
    best = sorted((v for pid, v in counts.items() if pid in ids), reverse=True)
    return best.index(my_views) + 1 if my_views in best else 0


init_db()
CONFIG = _load("config", "key", "value")
EMOJIS = _load("emojis", "key", "emoji")
MESSAGES = _load("messages", "key", "contenu")
OWNERS = load_owners()
BG_DATA = load_background()
PUBLIC_CHANNELS = load_public_channels()
BIOS = _load("bios", "user_id", "texte")
COLORS = _load("couleurs", "user_id", "couleur")


def emoji_of(key):
    return EMOJIS.get(key) or DEFAULT_EMOJIS.get(key, "•")


def message_of(key, default):
    return MESSAGES.get(key, default)


# ==============================================================================
#  PERMISSIONS
# ==============================================================================

def is_buyer(uid): return uid == BUYER_ID
def is_owner(uid): return uid == BUYER_ID or uid in OWNERS


def check_buyer():
    async def predicate(ctx): return is_buyer(ctx.author.id)
    return commands.check(predicate)


def check_owner():
    async def predicate(ctx): return is_owner(ctx.author.id)
    return commands.check(predicate)


def check_public():
    """Owner everywhere, OR anyone in a channel allowed via !allow."""
    async def predicate(ctx):
        return is_owner(ctx.author.id) or (ctx.guild is not None and ctx.channel.id in PUBLIC_CHANNELS)
    return commands.check(predicate)


# ==============================================================================
#  BOT
# ==============================================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


# ==============================================================================
#  DETECTION
# ==============================================================================

def detect_badges(user):
    f = user.public_flags
    out = []
    if f.hypesquad:                   out.append("hypesquad")
    if f.hypesquad_bravery:           out.append("bravery")
    if f.hypesquad_brilliance:        out.append("brilliance")
    if f.hypesquad_balance:           out.append("balance")
    if f.early_supporter:             out.append("early")
    if f.bug_hunter:                  out.append("bughunter")
    if f.bug_hunter_level_2:          out.append("bughunter2")
    if f.verified_bot_developer:      out.append("botdev")
    if f.discord_certified_moderator: out.append("mod")
    if f.partner:                     out.append("partner")
    if f.staff:                       out.append("staff")
    return out


def detect_age(user):
    for key, limit in OG_THRESHOLDS_LIST:
        if user.created_at < limit:
            return key
    return None


def is_word(name):
    if not WORDFREQ_OK or not name.isalpha() or len(name) < 3:
        return False
    return zipf_frequency(name, "fr") >= WORD_THRESHOLD or zipf_frequency(name, "en") >= WORD_THRESHOLD


def detect_username(user):
    name = user.name
    out = []
    if len(name) == 2:
        out.append("pseudo2")
    elif len(name) == 3:
        out.append("pseudo3")
    if is_word(name):
        out.append("mot")
    if name.isdigit():
        out.append("chiffres")
    return out


def boost_months(member):
    """Number of boost months for THIS server, or None if the member isn't boosting."""
    since = getattr(member, "premium_since", None)
    if not since:
        return None
    delta = datetime.datetime.now(datetime.timezone.utc) - since
    return delta.days / 30.44


def detect_boost(member):
    months = boost_months(member)
    if months is None:
        return None
    for threshold, key in BOOST_TIERS:
        if months >= threshold:
            return key
    return "boost1"  # boosting for less than a month


def collect_info(member):
    return {
        "badges": detect_badges(member),
        "pseudo": detect_username(member),
        "anciennete": detect_age(member),
        "boost": detect_boost(member),
        "erreurs": [],
    }


async def fetch_full_user(member):
    """Fetch the full user object (to show their banner in the embed)."""
    try:
        return await bot.fetch_user(member.id)
    except Exception:
        return None


async def resolve_target(ctx, ref):
    """Resolve a reference (mention, ID, name, or None).
    Returns a Member if the person is on the server, otherwise a global User (even off-server).
    Returns None if not found."""
    if ref is None:
        return ctx.author
    s = str(ref).strip()
    uid = None
    m = re.match(r"^<@!?(\d+)>$", s)
    if m:
        uid = int(m.group(1))
    elif s.isdigit():
        uid = int(s)
    if uid is not None:
        if ctx.guild:
            member = ctx.guild.get_member(uid)
            if member:
                return member
        try:
            return await bot.fetch_user(uid)
        except Exception:
            return None
    # Search by name / nickname on the server
    if ctx.guild:
        low = s.lower().lstrip("@")
        for mm in ctx.guild.members:
            if mm.name.lower() == low or mm.display_name.lower() == low or (mm.nick and mm.nick.lower() == low):
                return mm
    return None


OG_THRESHOLDS = dict(OG_THRESHOLDS_LIST)


def member_has_key(member, key):
    if key in OG_THRESHOLDS:
        return member.created_at < OG_THRESHOLDS[key]
    if key in BOOST_MONTHS:
        months = boost_months(member)
        return months is not None and months >= BOOST_MONTHS[key]
    if key in ("pseudo2", "pseudo3", "mot", "chiffres"):
        return key in detect_username(member)
    return key in detect_badges(member)


def members_with(guild, key):
    return [m for m in guild.members if not m.bot and member_has_key(m, key)]


async def assign_roles_from(member, info):
    keys = list(info["badges"]) + list(info["pseudo"])
    for extra in (info["anciennete"], info["boost"]):
        if extra:
            keys.append(extra)
    role_ids = {CONFIG.get(c, 0) for c in keys}
    role_ids.discard(0)
    roles = [r for rid in role_ids if (r := member.guild.get_role(rid)) and r not in member.roles]
    if roles:
        try:
            await member.add_roles(*roles, reason="Rare account detected")
        except discord.Forbidden:
            info["erreurs"].append("Missing 'Manage Roles' permission, or the bot's role is too low.")
        except discord.HTTPException as e:
            info["erreurs"].append(f"API error: {e}")


async def apply_roles(member):
    info = collect_info(member)
    await assign_roles_from(member, info)
    return info


def is_notable(info):
    return bool(info["badges"] or info["pseudo"] or info["anciennete"] or info["boost"])


# ==============================================================================
#  RARITY
# ==============================================================================

def rarity_score(info):
    s = sum(WEIGHTS.get(b, 0) for b in info["badges"])
    s += sum(WEIGHTS.get(p, 0) for p in info["pseudo"])
    if info["anciennete"]:
        s += WEIGHTS.get(info["anciennete"], 0)
    if info["boost"]:
        s += WEIGHTS.get(info["boost"], 0)
    return s


def rarity_level(info):
    s = rarity_score(info)
    name, emo, color = LEVELS[0][1], LEVELS[0][2], LEVELS[0][3]
    for threshold, n, e, c in LEVELS:
        if s >= threshold:
            name, emo, color = n, e, c
    return s, name, emo, color


def is_exceptional(info):
    _, level, _, _ = rarity_level(info)
    if level in ("Legendary", "Mythic"):
        return True
    return any(b in info["badges"] for b in ("staff", "partner", "bughunter2"))


# ==============================================================================
#  PROFILE EMBED (join + profile)
# ==============================================================================

def profile_embed(member, info, title):
    score, level, emo, color = rarity_level(info)
    now = datetime.datetime.now(datetime.timezone.utc)
    age = now - member.created_at
    years, days = age.days // 365, age.days % 365

    embed = discord.Embed(title=title, color=color, timestamp=now)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="User", value=f"{member.mention}\n`{member.name}`", inline=True)
    embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
    embed.add_field(name="💎 Level", value=f"{emo} **{level}** ({score} pts)", inline=True)
    embed.add_field(name="📅 Account created",
                    value=f"<t:{int(member.created_at.timestamp())}:D>\n({years} year(s) and {days} day(s) ago)",
                    inline=True)
    j = getattr(member, "joined_at", None)
    if j:
        embed.add_field(name="📥 Joined", value=f"<t:{int(j.timestamp())}:R>", inline=True)

    # Badges = emojis only (badges + username + age + boost), no text.
    keys = list(info["badges"]) + list(info["pseudo"])
    for extra in (info["anciennete"], info["boost"]):
        if extra:
            keys.append(extra)
    line = "  ".join(emoji_of(k) for k in keys) if keys else "—"
    embed.add_field(name="🏅 Badges", value=line, inline=False)

    if info["erreurs"]:
        embed.add_field(name="⚠️ Warning", value="\n".join(info["erreurs"]), inline=False)
    return embed


async def send_join_log(guild, member, info, user=None):
    channel = guild.get_channel(CONFIG.get("logs", 0))
    if channel is None:
        return
    embed = profile_embed(member, info, message_of("join", JOIN_TITLE_DEFAULT))
    embed.set_footer(text=guild.name)
    if user and user.banner:
        embed.set_image(url=user.banner.url)
    content = None
    if is_exceptional(info):
        rid = CONFIG.get("alertrole", 0)
        if rid:
            content = f"<@&{rid}>"
    try:
        await channel.send(content=content, embed=embed)
    except discord.HTTPException:
        pass


# ==============================================================================
#  VIEWS (UI)
# ==============================================================================

class AuthorView(discord.ui.View):
    def __init__(self, author, guild, timeout=180):
        super().__init__(timeout=timeout)
        self.author = author
        self.guild = guild

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This menu isn't for you 🙂", ephemeral=True)
            return False
        return True


def display_value(guild, key):
    rid = CONFIG.get(key, 0)
    if not rid:
        return "*not set*"
    if SET_ITEMS[key]["type"] == "channel":
        ch = guild.get_channel(rid)
        return ch.mention if ch else "*not found*"
    role = guild.get_role(rid)
    return role.mention if role else "*not found*"


def config_embed(guild):
    embed = discord.Embed(title="⚙️ Configuration",
                          description="Pick a category, then the item to set.",
                          color=discord.Color.blurple())
    for cat, keys in CATEGORIES.items():
        lines = []
        for k in keys:
            pref = emoji_of(k) + " " if k in DEFAULT_EMOJIS else ""
            lines.append(f"{pref}**{SET_ITEMS[k]['label']}** → {display_value(guild, k)}")
        embed.add_field(name=cat, value="\n".join(lines), inline=False)
    return embed


def config_home_embed():
    e = discord.Embed(title="⚙️ Configuration",
                      description="Choose the category to configure from the menu below.",
                      color=discord.Color.blurple())
    e.add_field(name="Categories", value="\n".join(f"• {c}" for c in CATEGORIES), inline=False)
    return e


def config_cat_embed(guild, cat):
    e = discord.Embed(title=f"⚙️ {cat}",
                      description="Choose the item to set below.",
                      color=discord.Color.blurple())
    lines = []
    for k in CATEGORIES[cat]:
        pref = emoji_of(k) + " " if k in DEFAULT_EMOJIS else ""
        lines.append(f"{pref}**{SET_ITEMS[k]['label']}** → {display_value(guild, k)}")
    e.add_field(name="Current state", value="\n".join(lines), inline=False)
    return e


# --- !set : category -> item -> role/channel ---

class SetCategorySelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Choose a category…",
                         options=[discord.SelectOption(label=c, value=c) for c in CATEGORIES])

    async def callback(self, interaction):
        await interaction.response.edit_message(
            embed=config_cat_embed(self.view.guild, self.values[0]),
            view=SetItemView(self.view.author, self.view.guild, self.values[0]))


class ConfigView(AuthorView):
    def __init__(self, author, guild):
        super().__init__(author, guild)
        self.add_item(SetCategorySelect())


class SetItemSelect(discord.ui.Select):
    def __init__(self, cat):
        super().__init__(placeholder=f"{cat} — choose the item…",
                         options=[discord.SelectOption(label=SET_ITEMS[k]["label"], value=k)
                                  for k in CATEGORIES[cat]])

    async def callback(self, interaction):
        key = self.values[0]
        it = SET_ITEMS[key]
        if it["type"] == "channel":
            view = ChannelPickView(self.view.author, self.view.guild, key)
            desc = "Choose the channel (type to search)."
        else:
            view = RolePickView(self.view.author, self.view.guild, key)
            desc = "Choose the role (type to search)."
        embed = discord.Embed(title=f"Configure: {it['label']}", description=desc, color=discord.Color.blurple())
        await interaction.response.edit_message(embed=embed, view=view)


class BackToConfig(discord.ui.Button):
    def __init__(self):
        super().__init__(label="◀ Back", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction):
        await interaction.response.edit_message(embed=config_home_embed(),
                                                view=ConfigView(self.view.author, self.view.guild))


class SetItemView(AuthorView):
    def __init__(self, author, guild, cat):
        super().__init__(author, guild)
        self.add_item(SetItemSelect(cat))
        self.add_item(BackToConfig())


class RolePicker(discord.ui.RoleSelect):
    def __init__(self, key):
        self.key = key
        super().__init__(placeholder="Search a role…", min_values=1, max_values=1)

    async def callback(self, interaction):
        role = self.values[0]
        set_config(self.key, role.id)
        await interaction.response.edit_message(
            embed=discord.Embed(title="✅ Done",
                                description=f"**{SET_ITEMS[self.key]['label']}** → {role.mention}",
                                color=discord.Color.green()),
            view=BackView(self.view.author, self.view.guild))


class RolePickView(AuthorView):
    def __init__(self, author, guild, key):
        super().__init__(author, guild)
        self.add_item(RolePicker(key))
        self.add_item(BackToConfig())


class ChannelPicker(discord.ui.ChannelSelect):
    def __init__(self, key):
        self.key = key
        super().__init__(placeholder="Search a channel…",
                         channel_types=[discord.ChannelType.text], min_values=1, max_values=1)

    async def callback(self, interaction):
        channel = self.values[0]
        set_config(self.key, channel.id)
        await interaction.response.edit_message(
            embed=discord.Embed(title="✅ Done",
                                description=f"**{SET_ITEMS[self.key]['label']}** → {channel.mention}",
                                color=discord.Color.green()),
            view=BackView(self.view.author, self.view.guild))


class ChannelPickView(AuthorView):
    def __init__(self, author, guild, key):
        super().__init__(author, guild)
        self.add_item(ChannelPicker(key))
        self.add_item(BackToConfig())


class BackView(AuthorView):
    def __init__(self, author, guild):
        super().__init__(author, guild)
        self.add_item(BackToConfig())


# --- Generic pagination (list + top) ---

class PrevButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="◀ Previous", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction):
        await self.view.change_page(interaction, -1)


class NextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Next ▶", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction):
        await self.view.change_page(interaction, +1)


class PageView(AuthorView):
    PER_PAGE = 10

    def __init__(self, author, guild, title, lines, color=None):
        super().__init__(author, guild)
        self.title = title
        self.lines = lines
        self.color = color or discord.Color.blurple()
        self.page = 0
        self.total_pages = max(1, (len(lines) + self.PER_PAGE - 1) // self.PER_PAGE)
        self.prev = PrevButton(); self.next = NextButton()
        self.add_item(self.prev); self.add_item(self.next)
        self._update()

    def _update(self):
        self.prev.disabled = self.page == 0
        self.next.disabled = self.page >= self.total_pages - 1

    def current_embed(self):
        start = self.page * self.PER_PAGE
        chunk = self.lines[start:start + self.PER_PAGE]
        embed = discord.Embed(title=self.title, description="\n".join(chunk) or "Empty.", color=self.color)
        embed.set_footer(text=f"Page {self.page + 1}/{self.total_pages} — {len(self.lines)} total")
        return embed

    async def change_page(self, interaction, delta):
        self.page = max(0, min(self.total_pages - 1, self.page + delta))
        self._update()
        await interaction.response.edit_message(embed=self.current_embed(), view=self)


# --- !scan : category -> item -> result ---

SCAN_CATEGORIES = {c: [k for k in keys if k in DETECT_KEYS]
                   for c, keys in CATEGORIES.items()
                   if any(k in DETECT_KEYS for k in keys)}


class ScanCategorySelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Choose a category to scan…",
                         options=[discord.SelectOption(label=c, value=c) for c in SCAN_CATEGORIES])

    async def callback(self, interaction):
        await interaction.response.edit_message(
            embed=scan_home_embed(),
            view=ScanItemView(self.view.author, self.view.guild, self.values[0]))


class ScanItemSelect(discord.ui.Select):
    def __init__(self, cat):
        super().__init__(placeholder=f"{cat} — choose the criterion…",
                         options=[discord.SelectOption(label=SET_ITEMS[k]["label"], value=k)
                                  for k in SCAN_CATEGORIES[cat]])

    async def callback(self, interaction):
        key = self.values[0]
        members = members_with(self.view.guild, key)
        if not members:
            await interaction.response.edit_message(
                embed=discord.Embed(description=f"Nobody for **{SET_ITEMS[key]['label']}**.",
                                    color=discord.Color.orange()),
                view=ScanView(self.view.author, self.view.guild))
            return
        lines = [f"{m.mention} / `{m.id}`" for m in members]
        title = f"{emoji_of(key)} {SET_ITEMS[key]['label']}"
        list_view = PageView(self.view.author, self.view.guild, title, lines)
        channel = self.view.guild.get_channel(CONFIG.get("scanlog", 0))
        if channel:
            await channel.send(embed=list_view.current_embed(), view=list_view if list_view.total_pages > 1 else None)
            await interaction.response.edit_message(
                embed=discord.Embed(description=f"✅ {len(members)} result(s) sent to {channel.mention}.",
                                    color=discord.Color.green()),
                view=ScanView(self.view.author, self.view.guild))
        else:
            await interaction.response.edit_message(
                embed=list_view.current_embed(), view=list_view if list_view.total_pages > 1 else None)


class ScanView(AuthorView):
    def __init__(self, author, guild):
        super().__init__(author, guild)
        self.add_item(ScanCategorySelect())


class ScanItemView(AuthorView):
    def __init__(self, author, guild, cat):
        super().__init__(author, guild)
        self.add_item(ScanItemSelect(cat))


def scan_home_embed():
    return discord.Embed(title="🔍 Scan by category",
                         description="Choose a category then a criterion. The result goes to the scan channel.",
                         color=discord.Color.blurple())


# --- !help (permission-aware) ---

# Commands ANY member can use (public commands + customization).
HELP_PUBLIC = {
    "🔍 Detection": [
        ("!profil @member", "Full profile of a member."),
        ("!list", "List members for a criterion (dropdown menu)."),
        ("!stats", "Global server dashboard."),
        ("!top", "Ranking of the rarest accounts."),
        ("!fame", "Ranking of the most viewed profiles (unique views)."),
        ("!bareme", "Rarity scale (menu by category)."),
    ],
}

# Full help, owners only (includes everything above + management & moderation).
HELP_OWNER = {
    "🔍 Detection": [
        ("!scan", "List members for a criterion (to the scan channel)."),
        ("!profil @member", "Full profile of a member."),
        ("!list", "List members for a criterion (dropdown menu)."),
        ("!stats", "Global server dashboard."),
        ("!top", "Ranking of the rarest accounts."),
        ("!fame", "Ranking of the most viewed profiles (unique views)."),
        ("!bareme", "Rarity scale (menu by category)."),
    ],
    "⚙️ Configuration": [
        ("!set", "Interactive panel (roles, channels, alerts)."),
        ("!config", "Show the configuration."),
        ("!setlog #channel", "Joins channel."),
        ("!setscan #channel", "Scans channel."),
        ("!setemoji", "Manage the criteria emojis (menu)."),
        ("!create <emojis>", "Create emojis on the server (from other servers)."),
        ("!setmsg <text>", "Join message title."),
    ],
    "👑 Management": [
        ("!owner @member", "Add an owner (buyer only)."),
        ("!unowner @member", "Remove an owner (buyer only)."),
        ("!owners", "Buyer + owners."),
    ],
    "🛠️ Moderation": [
        ("!ban <@/id> [reason]", "Ban (by ID, works even if the person isn't on the server)."),
        ("!unban <id> [reason]", "Unban by ID (or exact name of a banned user)."),
        ("!mute <@/id> [reason]", "Permanent mute (applies on arrival if the person is absent)."),
        ("!tempmute <@/id> <duration> [reason]", "Temporary mute (30s, 10m, 2h, 1d, 1w, or 1h30m)."),
        ("!unmute <@/id>", "Remove the mute (permanent or temporary)."),
        ("!mutes", "List currently muted people."),
        ("!setmute [@role]", "Set (or create) the mute role."),
        ("!nuke", "Delete and recreate the channel identically (renew)."),
        ("!clear [n|@member]", "Purge: last 100, a number (1-100), or a member's messages."),
        ("!allow [#channel]", "Open a channel to public commands."),
        ("!unallow [#channel]", "Close a channel (owners only)."),
    ],
}


def help_home_embed(cats, owner=False):
    if owner:
        intro = "You're an **owner** — you can see every command.\n"
    else:
        intro = "Here are the commands **you** can use.\n"
    e = discord.Embed(title="📖 Bot help",
                      description="Detects rare accounts and assigns roles.\n" + intro +
                                  "Pick a category below.",
                      color=discord.Color.blurple())
    e.add_field(name="Categories", value="\n".join(f"• {c}" for c in cats), inline=False)
    return e


def help_category_embed(cats, cat):
    e = discord.Embed(title=f"📖 Help — {cat}", color=discord.Color.blurple())
    for name, desc in cats[cat]:
        e.add_field(name=name, value=desc, inline=False)
    return e


class HelpSelect(discord.ui.Select):
    def __init__(self, cats):
        self.cats = cats
        opts = [discord.SelectOption(label="Home", value="home", emoji="🏠")]
        opts += [discord.SelectOption(label=c, value=c) for c in cats]
        super().__init__(placeholder="Choose a category…", options=opts)

    async def callback(self, interaction):
        v = self.values[0]
        embed = help_home_embed(self.cats, self.view.owner) if v == "home" else help_category_embed(self.cats, v)
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(AuthorView):
    def __init__(self, author, guild, cats, owner=False):
        super().__init__(author, guild)
        self.cats = cats
        self.owner = owner
        self.add_item(HelpSelect(cats))


# --- !list : category -> criterion -> paginated list ---

def list_home_embed():
    return discord.Embed(title="📋 List by criterion",
                         description="Choose a category then a criterion to list members.",
                         color=discord.Color.blurple())


class ListCategorySelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Choose a category…",
                         options=[discord.SelectOption(label=c, value=c) for c in SCAN_CATEGORIES])

    async def callback(self, interaction):
        await interaction.response.edit_message(
            embed=list_home_embed(),
            view=ListItemView(self.view.author, self.view.guild, self.values[0]))


class ListItemSelect(discord.ui.Select):
    def __init__(self, cat):
        super().__init__(placeholder=f"{cat} — choose the criterion…",
                         options=[discord.SelectOption(label=SET_ITEMS[k]["label"], value=k)
                                  for k in SCAN_CATEGORIES[cat]])

    async def callback(self, interaction):
        key = self.values[0]
        members = members_with(self.view.guild, key)
        if not members:
            await interaction.response.edit_message(
                embed=discord.Embed(description=f"Nobody for **{SET_ITEMS[key]['label']}**.",
                                    color=discord.Color.orange()),
                view=ListRootView(self.view.author, self.view.guild))
            return
        lines = [f"{m.mention} / `{m.id}`" for m in members]
        view = PageView(self.view.author, self.view.guild, f"{emoji_of(key)} {SET_ITEMS[key]['label']}", lines)
        await interaction.response.edit_message(embed=view.current_embed(),
                                                view=view if view.total_pages > 1 else None)


class ListRootView(AuthorView):
    def __init__(self, author, guild):
        super().__init__(author, guild)
        self.add_item(ListCategorySelect())


class ListItemView(AuthorView):
    def __init__(self, author, guild, cat):
        super().__init__(author, guild)
        self.add_item(ListItemSelect(cat))


# --- !bareme : by category ---

SCALE_CATS = ["🏅 Badges", "🚀 Boost", "📅 Account age", "✨ Username"]


def scale_home_embed():
    e = discord.Embed(title="📐 Rarity scale",
                      description="Choose a category to see the points.",
                      color=discord.Color.blurple())
    e.add_field(name="Levels (minimum score)",
                value="\n".join(f"{e} {n} : {s}+ pts" for s, n, e, _ in LEVELS), inline=False)
    return e


def scale_cat_embed(cat):
    lines = [f"{SET_ITEMS[k]['label']} : **{WEIGHTS[k]}**" for k in CATEGORIES[cat] if k in WEIGHTS]
    return discord.Embed(title=f"📐 Scale — {cat}", description="\n".join(lines),
                         color=discord.Color.blurple())


class ScaleSelect(discord.ui.Select):
    def __init__(self):
        opts = [discord.SelectOption(label="Home (levels)", value="home", emoji="🏠")]
        opts += [discord.SelectOption(label=c, value=c) for c in SCALE_CATS]
        super().__init__(placeholder="Choose a category…", options=opts)

    async def callback(self, interaction):
        v = self.values[0]
        embed = scale_home_embed() if v == "home" else scale_cat_embed(v)
        await interaction.response.edit_message(embed=embed, view=self.view)


class ScaleView(AuthorView):
    def __init__(self, author, guild):
        super().__init__(author, guild)
        self.add_item(ScaleSelect())


# --- !setemoji : category -> item -> modal ---

EMOJI_CATEGORIES = {c: [k for k in keys if k in DEFAULT_EMOJIS]
                    for c, keys in CATEGORIES.items() if any(k in DEFAULT_EMOJIS for k in keys)}


def emoji_home_embed():
    return discord.Embed(title="😀 Criteria emojis",
                         description="Choose a category, then the item whose emoji you want to change.",
                         color=discord.Color.blurple())


def emoji_cat_embed(cat):
    e = discord.Embed(title=f"😀 Emojis — {cat}", description="Choose the item to edit.",
                      color=discord.Color.blurple())
    lines = [f"{emoji_of(k)} {SET_ITEMS[k]['label']}" for k in EMOJI_CATEGORIES[cat]]
    e.add_field(name="Current emojis", value="\n".join(lines), inline=False)
    return e


def emoji_item_embed(key):
    e = discord.Embed(title=f"😀 {SET_ITEMS[key]['label']}", color=discord.Color.blurple())
    e.add_field(name="Current emoji", value=emoji_of(key), inline=False)
    e.set_footer(text="Click Edit to change it.")
    return e


class EmojiModal(discord.ui.Modal):
    def __init__(self, author, guild, key):
        super().__init__(title="Set the emoji")
        self.author = author
        self.guild = guild
        self.key = key
        self.field = discord.ui.TextInput(label=SET_ITEMS[key]["label"][:45],
                                          placeholder="Paste your emoji here", max_length=100)
        self.add_item(self.field)

    async def on_submit(self, interaction):
        set_emoji(self.key, str(self.field.value).strip())
        await interaction.response.edit_message(
            embed=emoji_item_embed(self.key),
            view=EmojiItemActionsView(self.author, self.guild, self.key))


class EditEmojiButton(discord.ui.Button):
    def __init__(self, key):
        super().__init__(label="✏️ Edit", style=discord.ButtonStyle.primary)
        self.key = key

    async def callback(self, interaction):
        await interaction.response.send_modal(EmojiModal(self.view.author, self.view.guild, self.key))


class BackEmojiButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="◀ Back", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction):
        await interaction.response.edit_message(embed=emoji_home_embed(),
                                                view=EmojiRootView(self.view.author, self.view.guild))


class EmojiItemActionsView(AuthorView):
    def __init__(self, author, guild, key):
        super().__init__(author, guild)
        self.add_item(EditEmojiButton(key))
        self.add_item(BackEmojiButton())


class EmojiCategorySelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Choose a category…",
                         options=[discord.SelectOption(label=c, value=c) for c in EMOJI_CATEGORIES])

    async def callback(self, interaction):
        cat = self.values[0]
        await interaction.response.edit_message(embed=emoji_cat_embed(cat),
                                                view=EmojiItemView(self.view.author, self.view.guild, cat))


class EmojiItemSelect(discord.ui.Select):
    def __init__(self, cat):
        super().__init__(placeholder=f"{cat} — choose the item…",
                         options=[discord.SelectOption(label=SET_ITEMS[k]["label"], value=k)
                                  for k in EMOJI_CATEGORIES[cat]])

    async def callback(self, interaction):
        key = self.values[0]
        await interaction.response.edit_message(embed=emoji_item_embed(key),
                                                view=EmojiItemActionsView(self.view.author, self.view.guild, key))


class EmojiRootView(AuthorView):
    def __init__(self, author, guild):
        super().__init__(author, guild)
        self.add_item(EmojiCategorySelect())


class EmojiItemView(AuthorView):
    def __init__(self, author, guild, cat):
        super().__init__(author, guild)
        self.add_item(EmojiItemSelect(cat))
        self.add_item(BackEmojiButton())


# ==============================================================================
#  MODERATION: TOOLS (ban / mute / tempmute)
# ==============================================================================

def _now_ts():
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp())


def parse_duration(s):
    """'30s' '10m' '2h' '1d' '1w' or combined '1h30m'. A bare number = minutes. -> seconds or None.
    Also accepts French suffixes: 'j' (day), 'sem' (week)."""
    if not s:
        return None
    s = s.strip().lower()
    if s.isdigit():
        return int(s) * 60
    units = {"sem": 604800, "w": 604800, "j": 86400, "d": 86400, "h": 3600, "m": 60, "s": 1}
    total = 0
    for n, u in re.findall(r"(\d+)\s*(sem|w|j|d|h|m|s)", s):
        total += int(n) * units[u]
    return total or None


def format_duration(sec):
    sec = int(sec)
    if sec <= 0:
        return "0s"
    parts = []
    for name, val in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if sec >= val:
            q, sec = divmod(sec, val)
            parts.append(f"{q}{name}")
    return " ".join(parts)


def extract_id(ref):
    """Return the ID from a mention <@123> or a raw ID, otherwise None."""
    if ref is None:
        return None
    s = str(ref).strip()
    m = re.match(r"^<@!?(\d+)>$", s)
    if m:
        return int(m.group(1))
    if s.isdigit():
        return int(s)
    return None


async def resolve_id_or_user(ctx, ref):
    """Return (uid, member_or_user_or_None). The uid can be valid even if the person isn't
    on the server (resolved via fetch_user). Accepts mention / ID / name (members)."""
    uid = extract_id(ref)
    if uid is not None:
        member = ctx.guild.get_member(uid) if ctx.guild else None
        if member:
            return uid, member
        try:
            return uid, await bot.fetch_user(uid)
        except Exception:
            return uid, None
    member = await resolve_target(ctx, ref)
    if member:
        return member.id, member
    return None, None


async def get_mute_role(guild):
    """Get the configured mute role, otherwise create it (and mute speech everywhere)."""
    rid = CONFIG.get("muterole", 0)
    role = guild.get_role(rid) if rid else None
    if role:
        return role
    role = discord.utils.get(guild.roles, name="Muted")
    if role is None:
        try:
            role = await guild.create_role(name="Muted", colour=discord.Color.dark_grey(),
                                           reason="Mute role (auto)")
        except discord.Forbidden:
            return None
        for ch in guild.channels:
            try:
                await ch.set_permissions(role, send_messages=False, add_reactions=False, speak=False,
                                         create_public_threads=False, create_private_threads=False,
                                         send_messages_in_threads=False)
            except Exception:
                pass
    set_config("muterole", role.id)
    return role


_unmute_tasks = {}


def _cancel_task(gid, uid):
    t = _unmute_tasks.pop((gid, uid), None)
    if t and not t.done():
        t.cancel()


async def _apply_mute(member, until):
    """Add the Muted role. If tempmute <= 28d, also add the native Discord timeout."""
    role = await get_mute_role(member.guild)
    if role and role not in member.roles:
        try:
            await member.add_roles(role, reason="Mute")
        except discord.HTTPException:
            pass
    if until:
        remaining = until - _now_ts()
        if 0 < remaining <= 28 * 86400:
            try:
                end = datetime.datetime.fromtimestamp(until, datetime.timezone.utc)
                await member.timeout(end, reason="Tempmute")
            except Exception:
                pass


async def _remove_mute(guild, uid):
    db_remove_mute(guild.id, uid)
    _cancel_task(guild.id, uid)
    member = guild.get_member(uid)
    if member:
        role = guild.get_role(CONFIG.get("muterole", 0))
        if role and role in member.roles:
            try:
                await member.remove_roles(role, reason="Unmute")
            except discord.HTTPException:
                pass
        try:
            if member.is_timed_out():
                await member.timeout(None, reason="Unmute")
        except Exception:
            pass


def _schedule_unmute(guild_id, uid, until):
    _cancel_task(guild_id, uid)

    async def _job():
        try:
            await asyncio.sleep(max(0, until - _now_ts()))
            guild = bot.get_guild(guild_id)
            if guild:
                await _remove_mute(guild, uid)
            else:
                db_remove_mute(guild_id, uid)
        except asyncio.CancelledError:
            pass

    _unmute_tasks[(guild_id, uid)] = bot.loop.create_task(_job())


# ==============================================================================
#  COMMANDS
# ==============================================================================

@bot.command(name="set")
@check_owner()
async def set_cmd(ctx):
    await ctx.send(embed=config_home_embed(), view=ConfigView(ctx.author, ctx.guild))


@bot.command(name="config")
@check_owner()
async def config_cmd(ctx):
    await ctx.send(embed=config_embed(ctx.guild))


@bot.command(name="setlog")
@check_owner()
async def setlog(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    set_config("logs", channel.id)
    await ctx.send(f"✅ Logs channel (joins): {channel.mention}")


@bot.command(name="setscan")
@check_owner()
async def setscan(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    set_config("scanlog", channel.id)
    await ctx.send(f"✅ Scan channel: {channel.mention}")


@bot.command(name="setalert")
@check_owner()
async def setalert(ctx, role: discord.Role):
    set_config("alertrole", role.id)
    await ctx.send(f"✅ Role pinged on an exceptional account: {role.mention}")


@bot.command(name="setemoji")
@check_owner()
async def setemoji(ctx):
    await ctx.send(embed=emoji_home_embed(), view=EmojiRootView(ctx.author, ctx.guild))


@bot.command(name="create")
@check_owner()
async def create(ctx, emojis: commands.Greedy[discord.PartialEmoji]):
    """Create one or more emojis on the server from other servers.
    Ex: !create <:foo:123> <:bar:456> ..."""
    if not emojis:
        await ctx.send("Usage: `!create <emoji1> <emoji2> ...` "
                       "(custom emojis from other servers).")
        return
    created, failed = [], []
    for em in emojis:
        if not em.id:  # standard (unicode) emoji -> not creatable
            failed.append(f"{em} (standard emoji)")
            continue
        try:
            data = await em.read()
            new = await ctx.guild.create_custom_emoji(
                name=em.name, image=data, reason=f"!create by {ctx.author}")
            created.append(str(new))
        except discord.Forbidden:
            failed.append(f"`{em.name}` (missing 'Manage Emojis' permission)")
        except discord.HTTPException as e:
            failed.append(f"`{em.name}` ({getattr(e, 'text', 'error / limit reached')})")
    embed = discord.Embed(title="✨ Emoji creation", color=discord.Color.green())
    if created:
        embed.add_field(name=f"✅ Created ({len(created)})", value=" ".join(created)[:1024], inline=False)
    if failed:
        embed.add_field(name=f"❌ Failed ({len(failed)})", value="\n".join(failed)[:1024], inline=False)
    await ctx.send(embed=embed)


@bot.command(name="setmsg")
@check_owner()
async def setmsg(ctx, *, text: str = None):
    if not text:
        await ctx.send("Usage: `!setmsg <text>`"); return
    set_message("join", text)
    await ctx.send(f"✅ Join title: {text}")


@bot.command(name="scan")
@check_owner()
async def scan(ctx):
    await ctx.send(embed=scan_home_embed(), view=ScanView(ctx.author, ctx.guild))


def record_unique_view(viewer, target):
    """Record a unique view (viewer -> target) except self-view/bot. Return the total."""
    if target.bot:
        return count_views(target.id)
    if viewer.id == target.id:
        return count_views(target.id)
    return record_view(target.id, viewer.id)


def fame_embed(guild):
    counts = views_per_profile()
    ranking = []
    for m in guild.members:
        if m.bot:
            continue
        v = counts.get(m.id, 0)
        if v > 0:
            ranking.append((v, m))
    ranking.sort(key=lambda x: x[0], reverse=True)
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    if not ranking:
        return discord.Embed(title="🏆 Fame Ranking",
                             description="Nobody has views yet. Try `!profil @member`!",
                             color=discord.Color.gold())
    lines = [f"{medals.get(i, f'**{i}.**')} {m.mention} — 👁 {v} view(s)"
             for i, (v, m) in enumerate(ranking[:20], 1)]
    return discord.Embed(title="🏆 Fame Ranking", description="\n".join(lines), color=discord.Color.gold())


@bot.command(name="profil", aliases=["check"])
@check_public()
async def profil(ctx, *, ref: str = None):
    member = await resolve_target(ctx, ref)
    if member is None:
        await ctx.send("❌ User not found. Give a valid **mention**, **ID**, or **username**.")
        return
    info = collect_info(member)
    views = record_unique_view(ctx.author, member)
    u = await fetch_full_user(member)
    embed = profile_embed(member, info, f"🔎 Profile of {member.name}")
    embed.add_field(name="👁 Fame", value=f"{views} view(s)", inline=True)
    if u and u.banner:
        embed.set_image(url=u.banner.url)
    await ctx.send(embed=embed)


@bot.command(name="list")
@check_public()
async def list_cmd(ctx):
    await ctx.send(embed=list_home_embed(), view=ListRootView(ctx.author, ctx.guild))


@bot.command(name="top")
@check_public()
async def top(ctx):
    ranking = []
    for m in ctx.guild.members:
        if m.bot:
            continue
        info = collect_info(m)
        s, lvl, emo, _ = rarity_level(info)
        if s > 0:
            ranking.append((s, lvl, emo, m))
    ranking.sort(key=lambda x: x[0], reverse=True)
    if not ranking:
        await ctx.send("No rare account found."); return
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = []
    for i, (s, lvl, emo, m) in enumerate(ranking, 1):
        rank = medals.get(i, f"**{i}.**")
        lines.append(f"{rank} {m.mention} — {emo} {lvl} ({s} pts)")
    view = PageView(ctx.author, ctx.guild, "🏆 Rarest accounts ranking", lines, discord.Color.gold())
    await ctx.send(embed=view.current_embed(), view=view if view.total_pages > 1 else None)


@bot.command(name="fame", aliases=["fames", "celebrite", "vues"])
@check_public()
async def fame(ctx):
    """Ranking of the most viewed profiles (unique views)."""
    await ctx.send(embed=fame_embed(ctx.guild))


@bot.command(name="stats")
@check_public()
async def stats(ctx):
    counter = {k: 0 for k in DETECT_KEYS}
    levels_count = {n: 0 for _, n, _, _ in LEVELS}
    total_rare = 0
    members = [m for m in ctx.guild.members if not m.bot]
    for m in members:
        info = collect_info(m)
        if is_notable(info):
            total_rare += 1
        for b in info["badges"]:
            counter[b] += 1
        for p in info["pseudo"]:
            counter[p] += 1
        for extra in (info["anciennete"], info["boost"]):
            if extra:
                counter[extra] += 1
        _, lvl, _, _ = rarity_level(info)
        levels_count[lvl] += 1

    embed = discord.Embed(title="📊 Server statistics", color=discord.Color.blurple())
    embed.add_field(name="Overview",
                    value=f"{len(members)} members · **{total_rare}** notable accounts", inline=False)
    embed.add_field(name="Levels",
                    value="\n".join(f"{e} {n} : {levels_count[n]}" for _, n, e, _ in LEVELS), inline=True)
    badges_txt = "\n".join(f"{emoji_of(k)} {SET_ITEMS[k]['label']} : {counter[k]}"
                           for k in CATEGORIES["🏅 Badges"] if counter[k]) or "—"
    embed.add_field(name="Badges", value=badges_txt, inline=True)
    others = []
    for cat in ("🚀 Boost", "📅 Account age", "✨ Username"):
        for k in CATEGORIES[cat]:
            if k in counter and counter[k]:
                others.append(f"{emoji_of(k)} {SET_ITEMS[k]['label']} : {counter[k]}")
    embed.add_field(name="Other criteria", value="\n".join(others) or "—", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="bareme")
@check_public()
async def bareme(ctx):
    await ctx.send(embed=scale_home_embed(), view=ScaleView(ctx.author, ctx.guild))


# ==============================================================================
#  MODERATION COMMANDS: BAN / UNBAN / MUTE / UNMUTE / TEMPMUTE
# ==============================================================================

@bot.command(name="ban")
@check_owner()
async def ban_cmd(ctx, target: str = None, *, reason: str = "No reason provided."):
    """!ban <@member|id> [reason] — works even if the person is NOT on the server (via ID)."""
    if target is None:
        await ctx.send("Usage: `!ban <@member|id> [reason]`"); return
    uid, user = await resolve_id_or_user(ctx, target)
    if uid is None:
        await ctx.send("❌ Target not found. Give a **mention**, an **ID** or a **username** (member present)."); return
    if uid == BUYER_ID or uid in OWNERS:
        await ctx.send("⛔ Can't ban an owner/buyer."); return
    if uid == ctx.author.id:
        await ctx.send("You can't ban yourself."); return
    name = str(user) if user else f"ID {uid}"
    try:
        await ctx.guild.ban(discord.Object(id=uid), reason=f"{reason} — by {ctx.author}", delete_message_days=0)
    except discord.Forbidden:
        await ctx.send("⛔ Missing **Ban Members** permission, or the bot's role is too low."); return
    except discord.HTTPException as e:
        await ctx.send(f"API error: {e}"); return
    db_remove_mute(ctx.guild.id, uid); _cancel_task(ctx.guild.id, uid)
    e = discord.Embed(title="🔨 Member banned", color=discord.Color.red(),
                      description=f"**{name}** (`{uid}`)\n**Reason:** {reason}")
    if not user or ctx.guild.get_member(uid) is None:
        e.set_footer(text="Ban by ID (the person wasn't necessarily on the server).")
    await ctx.send(embed=e)


@bot.command(name="unban")
@check_owner()
async def unban_cmd(ctx, target: str = None, *, reason: str = "No reason provided."):
    """!unban <id> (recommended) or exact name / name#0000 of a banned member."""
    if target is None:
        await ctx.send("Usage: `!unban <id>` (or exact name of a banned user)"); return
    uid = extract_id(target)
    if uid is None:
        s = target.strip().lower()
        try:
            async for ban_entry in ctx.guild.bans():
                u = ban_entry.user
                if str(u).lower() == s or u.name.lower() == s or str(u.id) == s:
                    uid = u.id; break
        except discord.Forbidden:
            await ctx.send("⛔ Missing **Ban Members** permission (reading bans)."); return
    if uid is None:
        await ctx.send("❌ Give a valid **ID** (recommended) or the exact name of a banned member."); return
    try:
        await ctx.guild.unban(discord.Object(id=uid), reason=f"{reason} — by {ctx.author}")
    except discord.NotFound:
        await ctx.send("ℹ️ This user isn't banned."); return
    except discord.Forbidden:
        await ctx.send("⛔ Missing **Ban Members** permission."); return
    except discord.HTTPException as e:
        await ctx.send(f"API error: {e}"); return
    await ctx.send(embed=discord.Embed(title="♻️ Unban",
                   description=f"<@{uid}> (`{uid}`) has been unbanned.", color=discord.Color.green()))


@bot.command(name="setmute", aliases=["setmuterole"])
@check_owner()
async def setmute_cmd(ctx, role: discord.Role = None):
    """Set (or create) the mute role. !setmute @role, or !setmute alone to auto-create."""
    if role is None:
        r = await get_mute_role(ctx.guild)
        if r is None:
            await ctx.send("⛔ I can't create the **Muted** role (missing **Manage Roles** permission).\n"
                           "Create it manually then run `!setmute @role`."); return
        await ctx.send(f"✅ Mute role: {r.mention} (auto). You can change it with `!setmute @role`."); return
    set_config("muterole", role.id)
    await ctx.send(f"✅ Mute role set: {role.mention}")


@bot.command(name="mute")
@check_owner()
async def mute_cmd(ctx, target: str = None, *, reason: str = "No reason provided."):
    """!mute <@member|id> [reason] — permanent mute. Also applies to someone off-server (on arrival)."""
    if target is None:
        await ctx.send("Usage: `!mute <@member|id> [reason]`"); return
    uid, user = await resolve_id_or_user(ctx, target)
    if uid is None:
        await ctx.send("❌ Target not found. Give a **mention**, an **ID** or a **username**."); return
    if uid == BUYER_ID or uid in OWNERS:
        await ctx.send("⛔ Can't mute an owner/buyer."); return
    db_add_mute(ctx.guild.id, uid, None, reason)
    _cancel_task(ctx.guild.id, uid)
    member = ctx.guild.get_member(uid)
    if member:
        await _apply_mute(member, None)
        target_txt = member.mention
    else:
        target_txt = f"<@{uid}> (`{uid}`)"
    e = discord.Embed(title="🔇 Member muted", color=discord.Color.dark_grey(),
                      description=f"{target_txt}\n**Duration:** permanent\n**Reason:** {reason}")
    if not member:
        e.set_footer(text="Not on the server: the mute will apply as soon as they arrive.")
    await ctx.send(embed=e)


@bot.command(name="tempmute", aliases=["mutetemp"])
@check_owner()
async def tempmute_cmd(ctx, target: str = None, duration: str = None, *, reason: str = "No reason provided."):
    """!tempmute <@member|id> <duration> [reason]. Durations: 30s, 10m, 2h, 1d, 1w, or combined 1h30m."""
    if target is None or duration is None:
        await ctx.send("Usage: `!tempmute <@member|id> <duration> [reason]`\n"
                       "Durations: `30s`, `10m`, `2h`, `1d`, `1w`, or combined `1h30m`."); return
    sec = parse_duration(duration)
    if not sec:
        await ctx.send("❌ Invalid duration. Ex: `10m`, `2h`, `1d`, `1h30m`."); return
    uid, user = await resolve_id_or_user(ctx, target)
    if uid is None:
        await ctx.send("❌ Target not found."); return
    if uid == BUYER_ID or uid in OWNERS:
        await ctx.send("⛔ Can't mute an owner/buyer."); return
    until = _now_ts() + sec
    db_add_mute(ctx.guild.id, uid, until, reason)
    member = ctx.guild.get_member(uid)
    if member:
        await _apply_mute(member, until)
        target_txt = member.mention
    else:
        target_txt = f"<@{uid}> (`{uid}`)"
    _schedule_unmute(ctx.guild.id, uid, until)
    e = discord.Embed(title="🔇 Member muted (temporary)", color=discord.Color.dark_grey(),
                      description=f"{target_txt}\n**Duration:** {format_duration(sec)}\n"
                                  f"**Ends:** <t:{until}:R>\n**Reason:** {reason}")
    if not member:
        e.set_footer(text="Not on the server: the mute will apply as soon as they arrive.")
    await ctx.send(embed=e)


@bot.command(name="unmute", aliases=["demute", "untempmute"])
@check_owner()
async def unmute_cmd(ctx, target: str = None):
    """!unmute <@member|id> — remove the mute (permanent or temporary)."""
    if target is None:
        await ctx.send("Usage: `!unmute <@member|id>`"); return
    uid, _user = await resolve_id_or_user(ctx, target)
    if uid is None:
        uid = extract_id(target)
    if uid is None:
        await ctx.send("❌ Target not found."); return
    had = db_mute_info(ctx.guild.id, uid) is not None
    await _remove_mute(ctx.guild, uid)
    if had:
        await ctx.send(embed=discord.Embed(title="🔊 Mute removed",
                       description=f"<@{uid}> is no longer muted.", color=discord.Color.green()))
    else:
        await ctx.send(f"ℹ️ <@{uid}> wasn't registered as muted (I still cleaned up the role/timeout if present).")


@bot.command(name="mutes")
@check_owner()
async def mutes_cmd(ctx):
    """List people currently muted on this server."""
    rows = db_guild_mutes(ctx.guild.id)
    if not rows:
        await ctx.send("Nobody is muted right now."); return
    lines = []
    for uid, until, reason in rows:
        if until:
            dur = f"until <t:{until}:R>"
        else:
            dur = "permanent"
        rs = f" — {reason}" if reason else ""
        lines.append(f"<@{uid}> (`{uid}`) — {dur}{rs}")
    view = PageView(ctx.author, ctx.guild, "🔇 Muted people", lines, discord.Color.dark_grey())
    await ctx.send(embed=view.current_embed(), view=view if view.total_pages > 1 else None)


# ==============================================================================
#  MODERATION / CHANNELS
# ==============================================================================

@bot.command(name="nuke", aliases=["renew"])
@check_owner()
async def nuke(ctx):
    """Delete the channel and recreate it identically (renew)."""
    channel = ctx.channel
    if not isinstance(channel, discord.TextChannel):
        await ctx.send("This command is used in a text channel."); return
    me = ctx.guild.me
    if not channel.permissions_for(me).manage_channels:
        await ctx.send("⛔ I'm missing the **Manage Channels** permission."); return
    pos = channel.position
    try:
        new = await channel.clone(reason=f"Nuke by {ctx.author}")
        await new.edit(position=pos)
        await channel.delete(reason=f"Nuke by {ctx.author}")
    except discord.Forbidden:
        await ctx.send("⛔ Insufficient permissions to recreate the channel."); return
    except discord.HTTPException as e:
        await ctx.send(f"Error: {e}"); return
    embed = discord.Embed(
        title="💥 Channel renewed",
        description=f"This channel was cleaned and recreated by {ctx.author.mention}.",
        color=discord.Color.orange(),
    )
    try:
        await new.send(embed=embed)
    except discord.HTTPException:
        pass


@bot.command(name="clear", aliases=["purge", "clean"])
@check_owner()
async def clear(ctx, target: str = None):
    """!clear (last 100) · !clear <1-100> · !clear @member (their last 100 messages)."""
    channel = ctx.channel
    if not channel.permissions_for(ctx.guild.me).manage_messages:
        await ctx.send("⛔ I'm missing the **Manage Messages** permission."); return

    member = None
    number = None
    if target is not None:
        try:
            member = await commands.MemberConverter().convert(ctx, target)
        except Exception:
            try:
                number = max(1, min(100, int(target)))
            except ValueError:
                await ctx.send("Usage: `!clear`, `!clear <1-100>` or `!clear @member`."); return

    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass

    try:
        if member is not None:
            deleted = await channel.purge(limit=100, check=lambda m: m.author.id == member.id)
            txt = f"🧹 {len(deleted)} message(s) from {member.mention} deleted."
        else:
            n = number if number is not None else 100
            deleted = await channel.purge(limit=n)
            txt = f"🧹 {len(deleted)} message(s) deleted."
    except discord.Forbidden:
        await ctx.send("⛔ Insufficient permissions."); return
    except discord.HTTPException as e:
        await ctx.send(f"Error: {e}"); return

    await ctx.send(txt, delete_after=4)


@bot.command(name="allow")
@check_owner()
async def allow(ctx, channel: discord.TextChannel = None):
    """Allow public commands in a channel. !allow or !allow #channel."""
    channel = channel or ctx.channel
    add_public_channel(channel.id)
    embed = discord.Embed(
        title="✅ Channel opened to commands",
        description=("Everyone can now use the public commands here:\n"
                     "`!profil` · `!bareme` · `!top` · `!list` · `!stats` · `!fame`\n\n"
                     "Management commands stay owner-only."),
        color=discord.Color.green(),
    )
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass
    if channel.id != ctx.channel.id:
        await ctx.send(f"✅ Public commands enabled in {channel.mention}.")


@bot.command(name="unallow", aliases=["disallow"])
@check_owner()
async def unallow(ctx, channel: discord.TextChannel = None):
    """Remove the public-commands allowance. !unallow or !unallow #channel."""
    channel = channel or ctx.channel
    remove_public_channel(channel.id)
    await ctx.send(f"🚫 Public commands disabled in {channel.mention}. "
                   "Only owners can run commands there.")


@bot.command(name="owner")
@check_buyer()
async def owner_cmd(ctx, *, ref: str = None):
    if not ref:
        await ctx.send("Give a **mention** or an **ID**. Ex: `!owner 425450624461701130`"); return
    member = await resolve_target(ctx, ref)
    if member is None:
        await ctx.send("❌ User not found."); return
    if member.id == BUYER_ID:
        await ctx.send("You are the buyer."); return
    if member.id in OWNERS:
        await ctx.send(f"{member.mention} is already an owner."); return
    add_owner(member.id)
    await ctx.send(f"✅ {member.mention} (`{member.id}`) is now an owner.")


@bot.command(name="unowner")
@check_buyer()
async def unowner_cmd(ctx, *, ref: str = None):
    member = await resolve_target(ctx, ref) if ref else None
    if member is None:
        await ctx.send("Give a **mention** or an **ID**. Ex: `!unowner 425450624461701130`"); return
    if member.id == BUYER_ID:
        await ctx.send("The buyer can't be removed."); return
    if member.id not in OWNERS:
        await ctx.send(f"{member.mention} isn't an owner."); return
    remove_owner(member.id)
    await ctx.send(f"✅ {member.mention} is no longer an owner.")


@bot.command(name="owners")
@check_owner()
async def owners_cmd(ctx):
    lines = [f"👑 <@{BUYER_ID}> — **Buyer**"] + ([f"• <@{u}>" for u in OWNERS] or ["*(no owner)*"])
    await ctx.send(embed=discord.Embed(title="Hierarchy", description="\n".join(lines),
                                       color=discord.Color.blurple()))


@bot.command(name="help")
async def help_cmd(ctx):
    owner = is_owner(ctx.author.id)
    cats = HELP_OWNER if owner else HELP_PUBLIC
    await ctx.send(embed=help_home_embed(cats, owner), view=HelpView(ctx.author, ctx.guild, cats, owner))


# ==============================================================================
#  ERRORS / EVENTS
# ==============================================================================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("⛔ You don't have permission.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Missing argument.")
    elif isinstance(error, (commands.UserNotFound, commands.MemberNotFound,
                            commands.ChannelNotFound, commands.RoleNotFound, commands.BadArgument)):
        await ctx.send("Invalid argument.")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        raise error


@bot.event
async def on_ready():
    print(f"Bot connected: {bot.user} (id {bot.user.id})")
    if not WORDFREQ_OK:
        print("/!\\ wordfreq not installed: word detection disabled.")
    print(f"Buyer: {BUYER_ID} | Owners: {len(OWNERS)}")
    # Mute recovery: clean up expired ones, reschedule the ones still running.
    for gid, uid, until, _ in db_all_mutes():
        if until and until <= _now_ts():
            guild = bot.get_guild(gid)
            if guild:
                await _remove_mute(guild, uid)
            else:
                db_remove_mute(gid, uid)
        elif until:
            _schedule_unmute(gid, uid, until)


@bot.event
async def on_member_join(member):
    if member.bot:
        return
    info = collect_info(member)
    u = await fetch_full_user(member)              # for the banner in the log
    await assign_roles_from(member, info)          # assign roles
    if is_notable(info):
        await send_join_log(member.guild, member, info, u)
    # Re-apply a pending mute if the person was muted (even if they had left / were absent).
    mute_info = db_mute_info(member.guild.id, member.id)
    if mute_info:
        until, _ = mute_info
        if until and until <= _now_ts():
            await _remove_mute(member.guild, member.id)
        else:
            await _apply_mute(member, until)
            if until:
                _schedule_unmute(member.guild.id, member.id, until)


@bot.event
async def on_member_update(before, after):
    # Auto re-detection (e.g. boost change).
    if not after.bot:
        await apply_roles(after)


@bot.event
async def on_user_update(before, after):
    # Auto re-detection (e.g. username change) across all shared servers.
    for g in bot.guilds:
        m = g.get_member(after.id)
        if m and not m.bot:
            await apply_roles(m)


if __name__ == "__main__":
    if not TOKEN or TOKEN == "PASTE_YOUR_TOKEN_HERE_IF_YOU_WANT":
        raise SystemExit("No token. Set DISCORD_TOKEN or paste it into TOKEN.")
    bot.run(TOKEN)
