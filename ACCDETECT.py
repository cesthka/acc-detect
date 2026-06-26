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
import math
import random
import colorsys
import asyncio
import re
from io import BytesIO
import aiohttp
import discord
from discord.ext import commands

try:
    from wordfreq import zipf_frequency
    WORDFREQ_OK = True
except ImportError:
    WORDFREQ_OK = False

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
    PIL_OK = True
except ImportError:
    PIL_OK = False

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
#  PROFILE CARD IMAGE (Pillow)
# ==============================================================================

# --- Fonts: Poppins (downloaded at startup), fallback to system fonts ---
FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FONT_URLS = {
    "Poppins-ExtraBold.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-ExtraBold.ttf",
    "Poppins-Bold.ttf":      "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-Bold.ttf",
    "Poppins-SemiBold.ttf":  "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-SemiBold.ttf",
    "Poppins-Medium.ttf":    "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-Medium.ttf",
    "Poppins-Regular.ttf":   "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-Regular.ttf",
}
_SYS_FALLBACK = {
    "ExtraBold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "Bold":      "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "SemiBold":  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "Medium":    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "Regular":   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
}


def ensure_fonts():
    """Download Poppins once (if missing). Silent failure -> system fallback."""
    if not PIL_OK:
        return
    try:
        os.makedirs(FONTS_DIR, exist_ok=True)
    except Exception:
        return
    import urllib.request
    for name, url in FONT_URLS.items():
        path = os.path.join(FONTS_DIR, name)
        if os.path.exists(path):
            continue
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                data = r.read()
            with open(path, "wb") as f:
                f.write(data)
        except Exception:
            pass


def _font(size, weight="Regular"):
    path = os.path.join(FONTS_DIR, f"Poppins-{weight}.ttf")
    if os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    try:
        return ImageFont.truetype(_SYS_FALLBACK.get(weight, _SYS_FALLBACK["Regular"]), size)
    except Exception:
        return ImageFont.load_default()


def _fit(draw, text, font, maxw):
    if draw.textlength(text, font=font) <= maxw:
        return text
    while text and draw.textlength(text + "…", font=font) > maxw:
        text = text[:-1]
    return text + "…"


def _shadow(draw, pos, text, font, fill, anchor=None, dx=2, dy=3, alpha=170):
    """Text with a simple drop shadow (readability over a busy background)."""
    draw.text((pos[0] + dx, pos[1] + dy), text, font=font, fill=(0, 0, 0, alpha), anchor=anchor)
    draw.text(pos, text, font=font, fill=fill, anchor=anchor)


def _mix(c, rgb, f):
    return tuple(int(c[i] + (rgb[i] - c[i]) * f) for i in range(3))


async def _download(url):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    return await r.read()
    except Exception:
        pass
    return None


def _cover(img, L, H):
    """Resize as 'cover' (fill L x H, crop the overflow at center)."""
    iw, ih = img.size
    scale = max(L / iw, H / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    img = img.resize((nw, nh))
    gx, gy = (nw - L) // 2, (nh - H) // 2
    return img.crop((gx, gy, gx + L, gy + H))


def _gradient(L, H, c1, c2):
    base = Image.new("RGBA", (L, H))
    d = ImageDraw.Draw(base)
    for y in range(H):
        t = y / max(1, H - 1)
        col = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)) + (255,)
        d.line([(0, y), (L, y)], fill=col)
    return base


def _left_veil(L, H, strength=225, end=0.74):
    """Dark veil fading from left (opaque) to right (transparent)."""
    ov = Image.new("RGBA", (L, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    xend = max(1, int(L * end))
    for x in range(L):
        a = int(strength * (1 - x / xend)) if x < xend else 0
        d.line([(x, 0), (x, H)], fill=(8, 10, 12, max(0, min(255, a))))
    return ov


# Vivid colors per level (card rendering)
CARD_COLORS = {
    "Common": (149, 165, 166), "Uncommon": (46, 204, 113), "Rare": (52, 152, 219),
    "Epic": (155, 89, 182), "Legendary": (241, 196, 15), "Mythic": (231, 76, 60),
}


def _progress(score):
    """Return (fraction 0..1 toward the next tier, next tier score or None)."""
    idx = 0
    for i, (s, *_rest) in enumerate(LEVELS):
        if score >= s:
            idx = i
    cur = LEVELS[idx][0]
    if idx + 1 < len(LEVELS):
        nxt = LEVELS[idx + 1][0]
        frac = (score - cur) / (nxt - cur) if nxt > cur else 1.0
        return max(0.0, min(1.0, frac)), nxt
    return 1.0, None


def _eye(draw, cx, cy, w):
    """Draw a small eye icon (vector)."""
    h = int(w * 0.66)
    draw.ellipse([cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2], fill=(238, 240, 243))
    ir = int(h * 0.46)
    draw.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], fill=(64, 96, 168))
    pp = max(2, int(ir * 0.52))
    draw.ellipse([cx - pp, cy - pp, cx + pp, cy + pp], fill=(16, 16, 22))
    rf = max(1, pp // 2)
    draw.ellipse([cx - pp, cy - pp, cx - pp + rf, cy - pp + rf], fill=(255, 255, 255))


def _draw_views(card, x, y, views, font, height=42):
    """Translucent pill: eye icon + view counter. Returns its width."""
    d = ImageDraw.Draw(card)
    txt = str(views)
    ew = int(height * 0.62)
    tw = d.textlength(txt, font=font)
    pad = 14
    width = int(pad + ew + 8 + tw + pad)
    pill = Image.new("RGBA", card.size, (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle([x, y, x + width, y + height], radius=height // 2, fill=(10, 12, 16, 175))
    card.alpha_composite(pill)
    d = ImageDraw.Draw(card)
    _eye(d, int(x + pad + ew / 2), int(y + height / 2), ew)
    d.text((x + pad + ew + 8, y + height // 2), txt, font=font, fill=(240, 242, 245), anchor="lm")
    return width


def _gif_to_frames(data, max_frames=30):
    """Split GIF/animated bytes into RGB frames by compositing frames correctly."""
    try:
        im = Image.open(BytesIO(data))
    except Exception:
        return []
    try:
        n = int(getattr(im, "n_frames", 1) or 1)
    except Exception:
        n = 1
    if n <= 1:
        try:
            return [im.convert("RGB")]
        except Exception:
            return []
    wanted = set([int(i * n / max_frames) for i in range(max_frames)] if n > max_frames else range(n))
    frames, canvas = [], None
    try:
        for idx in range(n):
            im.seek(idx)
            cur = im.convert("RGBA")
            canvas = cur if canvas is None else Image.alpha_composite(canvas, cur)
            if idx in wanted:
                frames.append(canvas.convert("RGB"))
    except Exception:
        pass
    if not frames:
        try:
            im.seek(0)
            frames = [im.convert("RGB")]
        except Exception:
            frames = []
    return frames


async def _read_asset(asset):
    """Read a Discord asset into bytes, with a direct fallback (aiohttp) on its URL."""
    try:
        data = await asset.read()
        if data:
            return data
    except Exception:
        pass
    try:
        return await _download(str(asset.url))
    except Exception:
        return None


async def _load_avatar_frames(member, size=256, max_frames=30):
    """Return (RGB frames, is_animated). Animated GIF avatars handled, with robust fallbacks."""
    av = member.display_avatar
    try:
        animated = bool(av.is_animated())
    except Exception:
        animated = False

    if animated:
        for variant in (
            lambda: av.replace(size=size, format="gif"),
            lambda: av.with_size(size).with_format("gif"),
            lambda: av,
        ):
            try:
                data = await _read_asset(variant())
            except Exception:
                data = None
            if data:
                frames = _gif_to_frames(data, max_frames)
                if frames:
                    return frames, len(frames) > 1

    for variant in (
        lambda: av.replace(size=size, static_format="png"),
        lambda: av.replace(size=size, format="png"),
        lambda: av,
    ):
        try:
            data = await _read_asset(variant())
        except Exception:
            data = None
        if data:
            try:
                img = Image.open(BytesIO(data))
            except Exception:
                continue
            if getattr(img, "is_animated", False):
                fr = _gif_to_frames(data, max_frames)
                if fr:
                    return fr, len(fr) > 1
            try:
                return [img.convert("RGB")], False
            except Exception:
                continue
    return [Image.new("RGB", (size, size), (40, 42, 50))], False


def _crown(draw, cx, cy, w, col):
    h = w * 0.8
    x0 = cx - w / 2
    y1 = cy + h / 2
    pts = [(x0, y1), (x0, cy - h / 2), (x0 + w * 0.25, cy), (cx, cy - h * 0.6),
           (x0 + w * 0.75, cy), (x0 + w, cy - h / 2), (x0 + w, y1)]
    draw.polygon(pts, fill=col)


def _star(draw, cx, cy, r, fill):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    draw.polygon(pts, fill=fill)


def _medal(draw, cx, cy, r, col):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    draw.ellipse([cx - r + 3, cy - r + 3, cx + r - 3, cy + r - 3], outline=(255, 255, 255, 170), width=1)


def _fame_cluster(card, W, views, rank, rgb):
    """Uniform fame block top-right: views + rank + title (or Server Star)."""
    draw = ImageDraw.Draw(card)
    f = _font(22, "SemiBold")
    fb = _font(15, "Bold")
    h, gap, y = 40, 10, 26
    specs = [("eye", str(views))]
    if rank > 0:
        specs.append(("rank", f"#{rank}"))
    specs.append(("star", "SERVER STAR") if rank == 1 else ("title", fame_title(views).upper()))
    widths = []
    for kind, txt in specs:
        if kind == "eye":
            w = 14 + 24 + 9 + draw.textlength(txt, font=f) + 16
        elif kind == "rank":
            w = 14 + 18 + 8 + draw.textlength(txt, font=f) + 16
        elif kind == "star":
            w = 16 + 18 + 9 + draw.textlength(txt, font=fb) + 16
        else:
            w = 18 + draw.textlength(txt, font=f) + 18
        widths.append(int(w))
    x = W - 30 - (sum(widths) + gap * (len(specs) - 1))
    for (kind, txt), w in zip(specs, widths):
        if kind == "star":
            draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=(241, 196, 15))
            _star(draw, x + 18, y + h // 2, 9, (20, 20, 20))
            draw.text((x + 34, y + h // 2), txt, font=fb, fill=(20, 20, 20), anchor="lm")
        else:
            layer = Image.new("RGBA", card.size, (0, 0, 0, 0))
            ImageDraw.Draw(layer).rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=(12, 14, 18, 190))
            card.alpha_composite(layer)
            draw = ImageDraw.Draw(card)
            draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, outline=rgb + (255,), width=2)
            if kind == "eye":
                _eye(draw, int(x + 14 + 12), y + h // 2, 24)
                draw.text((x + 14 + 24 + 9, y + h // 2), txt, font=f, fill=(240, 242, 245), anchor="lm")
            elif kind == "rank":
                _medal(draw, x + 14 + 9, y + h // 2, 9, rgb)
                draw.text((x + 14 + 18 + 8, y + h // 2), txt, font=f, fill=(255, 255, 255), anchor="lm")
            else:
                draw.text((x + 18, y + h // 2), txt, font=f, fill=rgb + (255,), anchor="lm")
        x += w + gap


async def generate_card(member, info, views=0, rank=0, bio=None, accent=None):
    """Premium profile card. Returns (buffer, ext); ext='gif' if animated avatar, else 'png'."""
    score, level, _, _ = rarity_level(info)
    rgb = accent or CARD_COLORS.get(level, (149, 165, 166))
    W = 900
    f_name = _font(50, "ExtraBold"); f_sub = _font(23, "Medium"); f_id = _font(19, "Medium")
    f_date = _font(20, "Medium"); f_pill = _font(25, "SemiBold"); f_small = _font(21, "Medium")
    f_chip = _font(22, "SemiBold"); f_bio = _font(23, "Medium")
    white, gray = (255, 255, 255, 255), (206, 211, 218, 255)

    av_frames, animated = await _load_avatar_frames(member, 256)
    avatar0 = av_frames[0]
    personal = member_background(member.id)
    banner = None
    try:
        u = await bot.fetch_user(member.id)
        if u and u.banner:
            banner = Image.open(BytesIO(await u.banner.replace(size=600, static_format="png").read())).convert("RGB")
    except Exception:
        pass

    keys = list(info["badges"]) + list(info["pseudo"])
    for extra in (info["anciennete"], info["boost"]):
        if extra:
            keys.append(extra)
    labels = [SET_ITEMS[k]["label"] for k in keys] or ["Standard account"]

    meas = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    pad, gap, ch = 20, 12, 40
    x0, maxx = 44, W - 44
    chip_w = [meas.textlength(l, font=f_chip) + pad * 2 for l in labels]
    cur, rows = x0, 1
    for w in chip_w:
        if cur + w > maxx and cur > x0:
            rows += 1
            cur = x0
        cur += w + gap
    y_pillrow, y_bio = 270, 326
    y_prog = y_bio + (44 if bio else 0)
    y_chips = y_prog + 72
    H = y_chips + rows * ch + (rows - 1) * gap + 24

    # Body background: personal > global > gradient
    def _bg_image(data):
        return _cover(Image.open(BytesIO(data)).convert("RGB"), W, H).convert("RGBA")
    base, custom_bg = None, False
    for src in (personal, BG_DATA):
        if src:
            try:
                base = _bg_image(src); custom_bg = True; break
            except Exception:
                base = None
    if base is None:
        base = _gradient(W, H, _mix(rgb, (26, 27, 32), 0.80), (13, 14, 17))
    if custom_bg:
        base = Image.alpha_composite(base, Image.new("RGBA", (W, H), (0, 0, 0, 120)))
    draw = ImageDraw.Draw(base)

    # Faded header: banner clearly visible at top, fading into the background
    Hh = 200
    if banner is not None:
        head = _cover(banner, W, Hh).convert("RGBA")
        dark = 55
    else:
        head = _cover(avatar0, W, Hh).filter(ImageFilter.GaussianBlur(16)).convert("RGBA")
        dark = 95
    head = Image.alpha_composite(head, Image.new("RGBA", (W, Hh), (0, 0, 0, dark)))
    fade = Image.new("L", (W, Hh), 0)
    fdd = ImageDraw.Draw(fade)
    start = Hh - 135
    for y in range(Hh):
        a = 255 if y < start else int(255 * (1 - (y - start) / 135))
        fdd.line([(0, y), (W, y)], fill=max(0, a))
    base.paste(head, (0, 0), fade)
    draw = ImageDraw.Draw(base)

    # Avatar: glow + ring (image placed later, per frame)
    ax, ay, ad, ring = 44, 90, 152, 6
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([ax - ring - 16, ay - ring - 16, ax + ad + ring + 16, ay + ad + ring + 16], fill=rgb + (120,))
    base = Image.alpha_composite(base, glow.filter(ImageFilter.GaussianBlur(18)))
    draw = ImageDraw.Draw(base)
    draw.ellipse([ax - ring, ay - ring, ax + ad + ring, ay + ad + ring], fill=rgb + (255,))

    # Identity
    x = 224
    maxw = W - x - 44
    nm = _fit(draw, member.name, f_name, maxw - 44)
    _shadow(draw, (x, 96), nm, f_name, white, dx=2, dy=3, alpha=185)
    nw = draw.textlength(nm, font=f_name)
    ex = x + nw + 18
    if level in ("Legendary", "Mythic"):
        _crown(draw, int(ex + 14), 122, 28, rgb)
    elif level in ("Rare", "Epic"):
        _star(draw, int(ex + 14), 122, 15, rgb)
    yy = 168
    nick = member.display_name
    if nick and nick != member.name:
        _shadow(draw, (x, yy), f"@{nick}", f_sub, gray, dx=1, dy=2, alpha=150); yy += 31
    _shadow(draw, (x, yy), f"ID {member.id}", f_id, gray, dx=1, dy=2, alpha=150); yy += 29
    created = member.created_at.strftime("%m/%d/%Y")
    age = (datetime.datetime.now(datetime.timezone.utc) - member.created_at).days // 365
    j = getattr(member, "joined_at", None)
    if j:
        date_line = f"Created {created} ({age} yrs)   ·   Joined {j.strftime('%m/%Y')}"
    else:
        date_line = f"Created {created} ({age} yrs)   ·   Off server"
    _shadow(draw, (x, yy), date_line, f_date, gray, dx=1, dy=2, alpha=150)

    # Level pill
    txt = f"{level.upper()}   {score} PTS"
    tw = draw.textlength(txt, font=f_pill)
    pillw = tw + 44
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([x0, y_pillrow + 4, x0 + pillw, y_pillrow + 50], radius=24, fill=(0, 0, 0, 110))
    base = Image.alpha_composite(base, sh.filter(ImageFilter.GaussianBlur(6)))
    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle([x0, y_pillrow, x0 + pillw, y_pillrow + 46], radius=23, fill=rgb + (255,))
    draw.text((x0 + 22, y_pillrow + 23), txt, font=f_pill, fill=(14, 15, 18), anchor="lm")

    if bio:
        draw.text((x0, y_bio), _fit(draw, f"\u00ab {bio} \u00bb", f_bio, W - 88), font=f_bio, fill=(226, 228, 233), anchor="lm")

    # Progress bar (gradient)
    frac, nxt = _progress(score)
    bx, by, bw2, bh = x0, y_prog, W - 88, 22
    draw.rounded_rectangle([bx, by, bx + bw2, by + bh], radius=bh // 2, fill=(255, 255, 255, 40))
    if frac > 0:
        fw = max(bh, int(bw2 * frac))
        grad = _gradient(fw, bh, _mix(rgb, (255, 255, 255), 0.25), rgb)
        gm = Image.new("L", (fw, bh), 0)
        ImageDraw.Draw(gm).rounded_rectangle([0, 0, fw - 1, bh - 1], radius=bh // 2, fill=255)
        base.paste(grad, (bx, by), gm)
        draw = ImageDraw.Draw(base)
    draw.text((bx, by + bh + 12), (f"{nxt - score} pts to the next tier" if nxt else "Maximum tier reached"),
              font=f_small, fill=gray, anchor="lt")

    # Attribute chips
    cxx, cyy = x0, y_chips
    for l, w in zip(labels, chip_w):
        if cxx + w > maxx and cxx > x0:
            cxx, cyy = x0, cyy + ch + gap
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle([cxx, cyy, cxx + w, cyy + ch], radius=ch // 2, fill=(10, 12, 14, 170))
        base = Image.alpha_composite(base, layer)
        draw = ImageDraw.Draw(base)
        draw.rounded_rectangle([cxx, cyy, cxx + w, cyy + ch], radius=ch // 2, outline=rgb + (255,), width=2)
        draw.text((cxx + pad, cyy + ch // 2), l, font=f_chip, fill=(235, 237, 240), anchor="lm")
        cxx += w + gap

    # Fame cluster (top-right, unique)
    _fame_cluster(base, W, views, rank, rgb)

    # Avatar composition + rounded corners
    am = Image.new("L", (ad, ad), 0)
    ImageDraw.Draw(am).ellipse([0, 0, ad, ad], fill=255)
    corner = Image.new("L", (W, H), 0)
    ImageDraw.Draw(corner).rounded_rectangle([0, 0, W - 1, H - 1], radius=34, fill=255)

    def _compose(avimg):
        c = base.copy()
        c.paste(_cover(avimg, ad, ad).convert("RGBA"), (ax, ay), am)
        return c

    if not animated:
        final = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        final.paste(_compose(avatar0), (0, 0), corner)
        buf = BytesIO()
        final.save(buf, format="PNG")
        buf.seek(0)
        return buf, "png"

    bg = (30, 31, 34)
    imgs = []
    for fr in av_frames:
        full = Image.new("RGB", (W, H), bg)
        full.paste(_compose(fr).convert("RGB"), (0, 0), corner)
        imgs.append(full)
    buf = BytesIO()
    imgs[0].save(buf, format="GIF", save_all=True, append_images=imgs[1:], duration=90, loop=0, optimize=True, disposal=2)
    buf.seek(0)
    return buf, "gif"



# ==============================================================================
#  HOLOGRAPHIC TCG CARD
# ==============================================================================

# Style per tier: color, holo intensity, number of stars.
TIERS_TCG = {
    "Common":    {"c": (150, 160, 170), "holo": 0.0,  "et": 1},
    "Uncommon":  {"c": (46, 204, 113),  "holo": 0.0,  "et": 2},
    "Rare":      {"c": (52, 152, 219),  "holo": 0.13, "et": 3},
    "Epic":      {"c": (155, 89, 182),  "holo": 0.22, "et": 4},
    "Legendary": {"c": (241, 196, 15),  "holo": 0.32, "et": 5},
    "Mythic":    {"c": (231, 76, 60),   "holo": 0.46, "et": 6},
}


def _tcg_gradient(L, H, c1, c2):
    base = Image.new("RGB", (L, H))
    d = ImageDraw.Draw(base)
    for y in range(H):
        d.line([(0, y), (L, y)], fill=_mix(c1, c2, y / max(1, H - 1)))
    return base


def _tcg_rainbow(W, H, sat=0.6, periods=2.2, offset=0.0, scale=3):
    w, h = max(1, W // scale), max(1, H // scale)
    data = bytearray(w * h * 3)
    N = 360
    pal = []
    for i in range(N):
        r, g, b = colorsys.hsv_to_rgb(i / N, sat, 1.0)
        pal.append((int(r * 255), int(g * 255), int(b * 255)))
    maxd = w + h
    for y in range(h):
        for x in range(w):
            hh = int((((x + y) / maxd * periods + offset) % 1.0) * N) % N
            r, g, b = pal[hh]
            idx = (y * w + x) * 3
            data[idx] = r; data[idx + 1] = g; data[idx + 2] = b
    return Image.frombytes("RGB", (w, h), bytes(data)).resize((W, H))


def _tcg_streaks(W, H, uid, wide=60, n=4):
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    rng = random.Random(uid)
    for _ in range(n):
        cx = rng.randint(0, int(W * 1.15))
        val = rng.randint(160, 235)
        d.polygon([(cx - wide, 0), (cx + wide, 0), (cx + wide - H, H), (cx - wide - H, H)], fill=val)
    return m.filter(ImageFilter.GaussianBlur(30))


def _tcg_sparkles(W, H, uid, box, n):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rng = random.Random(uid * 3 + 1)
    x0, y0, x1, y1 = box
    for _ in range(n):
        x = rng.randint(x0, x1); y = rng.randint(y0, y1)
        r = rng.uniform(1.5, 4.5); a = rng.randint(120, 235)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, a))
        if rng.random() < 0.4:
            ln = r * rng.uniform(3, 6)
            d.line([(x - ln, y), (x + ln, y)], fill=(255, 255, 255, a // 2), width=1)
            d.line([(x, y - ln), (x, y + ln)], fill=(255, 255, 255, a // 2), width=1)
    return layer.filter(ImageFilter.GaussianBlur(0.6))


def _tcg_gloss(W, H, box):
    x0, y0, x1, y1 = box
    g = Image.new("L", (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(g).polygon([(0, 0), ((x1 - x0) * 0.6, 0), (0, (y1 - y0) * 0.6)], fill=70)
    g = g.filter(ImageFilter.GaussianBlur(40))
    full = Image.new("L", (W, H), 0)
    full.paste(g, (x0, y0))
    return full


def _tcg_star(draw, cx, cy, r, fill):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    draw.polygon(pts, fill=fill)


async def generate_tcg(member, info, views=0):
    """Generate a holographic collectible card (PNG) -> BytesIO buffer."""
    score, level, _, _ = rarity_level(info)
    st = TIERS_TCG.get(level, TIERS_TCG["Common"])
    col = st["c"]
    uid = member.id
    W, H = 744, 1040
    dark = _mix(col, (12, 12, 16), 0.82)
    mid = _mix(col, (20, 20, 26), 0.6)

    # Avatar
    try:
        adata = await member.display_avatar.replace(size=256, static_format="png").read()
        avatar = Image.open(BytesIO(adata)).convert("RGB")
    except Exception:
        avatar = Image.new("RGB", (256, 256), (40, 42, 50))

    # Labels
    keys = list(info["badges"]) + list(info["pseudo"])
    for extra in (info["anciennete"], info["boost"]):
        if extra:
            keys.append(extra)
    labels = [SET_ITEMS[k]["label"] for k in keys] or ["Standard account"]

    # Background + metallic frame
    card = _tcg_gradient(W, H, _mix(col, (18, 18, 24), 0.7), (8, 8, 11)).convert("RGBA")
    draw = ImageDraw.Draw(card)
    frame = _tcg_gradient(W, H, _mix(col, (255, 255, 255), 0.4), _mix(col, (0, 0, 0), 0.5)).convert("RGBA")
    fmask = Image.new("L", (W, H), 0)
    fd = ImageDraw.Draw(fmask)
    fd.rounded_rectangle([6, 6, W - 6, H - 6], radius=42, fill=255)
    fd.rounded_rectangle([30, 30, W - 30, H - 30], radius=32, fill=0)
    card.paste(frame, (0, 0), fmask)
    draw.rounded_rectangle([30, 30, W - 30, H - 30], radius=32, fill=dark)

    M = 46
    # Name plate + score gem
    draw.rounded_rectangle([M, 46, W - M, 120], radius=20, fill=_mix(mid, (0, 0, 0), 0.2), outline=col, width=2)
    fn = _font(40, "ExtraBold")
    nm = member.name
    while draw.textlength(nm, font=fn) > W - M - 170 and len(nm) > 1:
        nm = nm[:-1]
    if nm != member.name:
        nm = nm[:-1] + "…"
    draw.text((M + 22, 83), nm, font=fn, fill=(255, 255, 255), anchor="lm")
    gx, gy, gr = W - M - 40, 83, 34
    draw.ellipse([gx - gr - 4, gy - gr - 4, gx + gr + 4, gy + gr + 4], fill=_mix(col, (0, 0, 0), 0.4))
    draw.ellipse([gx - gr, gy - gr, gx + gr, gy + gr], fill=col, outline=(255, 255, 255), width=3)
    draw.text((gx, gy), str(score), font=_font(30, "ExtraBold"), fill=(15, 15, 18), anchor="mm")

    # Artwork window
    ax0, ay0, ax1, ay1 = M, 138, W - M, 612
    aw, ah = ax1 - ax0, ay1 - ay0
    art = _cover(avatar, aw, ah).convert("RGBA")
    amask = Image.new("L", (aw, ah), 0)
    ImageDraw.Draw(amask).rounded_rectangle([0, 0, aw - 1, ah - 1], radius=18, fill=255)
    card.paste(art, (ax0, ay0), amask)
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle([ax0, ay0, ax1, ay1], radius=18, outline=col, width=3)

    # Type line
    draw.rounded_rectangle([M, 628, W - M, 684], radius=14, fill=_mix(mid, (0, 0, 0), 0.25), outline=col, width=2)
    draw.text((W // 2, 656), level.upper(), font=_font(26, "SemiBold"), fill=(255, 255, 255), anchor="mm")

    # Stats block
    draw.rounded_rectangle([M, 700, W - M, 958], radius=18, fill=_mix((10, 10, 14), col, 0.06), outline=col, width=2)
    fl = _font(24, "Medium")
    y = 730
    for lab in labels[:7]:
        draw.ellipse([M + 24, y - 6, M + 36, y + 6], fill=col)
        draw.text((M + 50, y), lab, font=fl, fill=(232, 234, 238), anchor="lm")
        y += 33

    # Bottom: stars / serial / score
    for i in range(st["et"]):
        _tcg_star(draw, M + 24 + i * 30, 1000, 11, col)
    draw.text((W // 2, 1000), f"No. {int(str(uid)[-4:]):04d}", font=_font(22, "Medium"), fill=(200, 205, 212), anchor="mm")
    draw.text((W - M - 10, 1000), f"{score} PTS", font=_font(24, "Bold"), fill=col, anchor="rm")

    # --- Holography ---
    if st["holo"] > 0:
        rb = _tcg_rainbow(W, H, offset=(uid % 100) / 100).convert("RGB")
        sr = _tcg_streaks(W, H, uid)
        frame_reg = Image.new("L", (W, H), 0)
        fr = ImageDraw.Draw(frame_reg)
        fr.rounded_rectangle([6, 6, W - 6, H - 6], radius=42, fill=255)
        fr.rounded_rectangle([30, 30, W - 30, H - 30], radius=32, fill=0)
        art_reg = Image.new("L", (W, H), 0)
        ImageDraw.Draw(art_reg).rounded_rectangle([ax0, ay0, ax1, ay1], radius=18, fill=255)
        mframe = ImageChops.multiply(frame_reg, sr).point(lambda p: int(min(255, p * st["holo"] * 2.6)))
        mart = ImageChops.multiply(art_reg, sr).point(lambda p: int(min(255, p * st["holo"] * 1.35)))
        rgb = card.convert("RGB")
        rgb = Image.composite(ImageChops.screen(rgb, rb), rgb, mframe)
        rgb = Image.composite(ImageChops.overlay(rgb, rb), rgb, mart)
        card = rgb.convert("RGBA")
        # Glass reflection over the artwork
        gl = ImageChops.multiply(_tcg_gloss(W, H, (ax0, ay0, ax1, ay1)), art_reg)
        card = Image.alpha_composite(card, Image.merge("RGBA", (Image.new("L", (W, H), 255),) * 3 + (gl,)))
        # Sparkles (high tiers)
        if st["et"] >= 4:
            pa = _tcg_sparkles(W, H, uid, (ax0, ay0, ax1, ay1), st["et"] * 5)
            pa = Image.composite(pa, Image.new("RGBA", (W, H), (0, 0, 0, 0)), art_reg)
            card = Image.alpha_composite(card, pa)

    # Views pill (top-left corner of the artwork)
    _draw_views(card, ax0 + 14, ay0 + 14, views, _font(24, "SemiBold"), height=40)

    # Rounded corners
    out = Image.new("L", (W, H), 0)
    ImageDraw.Draw(out).rounded_rectangle([0, 0, W - 1, H - 1], radius=44, fill=255)
    final = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    final.paste(card, (0, 0), out)

    buf = BytesIO()
    final.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ==============================================================================
#  ANIMATED HOLOGRAPHIC TCG CARD (GIF)
# ==============================================================================

# Holo intensity for animation: EVERY tier shimmers (even Common).
HOLO_ANIM = {
    "Common": 0.10, "Uncommon": 0.14, "Rare": 0.20,
    "Epic": 0.28, "Legendary": 0.38, "Mythic": 0.52,
}


def _tcg_hue_index(W, H, periods=2, scale=3):
    """L image where each pixel = hue index (0-255). Generated once."""
    w, h = W // scale, H // scale
    data = bytearray(w * h)
    maxd = w + h
    for y in range(h):
        for x in range(w):
            data[y * w + x] = int((((x + y) / maxd * periods) % 1.0) * 255)
    return Image.frombytes("L", (w, h), bytes(data)).resize((W, H))


def _tcg_palette_rb(shift, sat=0.6):
    pal = []
    for i in range(256):
        r, g, b = colorsys.hsv_to_rgb(((i + shift) % 256) / 256, sat, 1.0)
        pal += [int(r * 255), int(g * 255), int(b * 255)]
    return pal


def _tcg_bands_anim(W, H, phase, n=2.4, scale=5):
    w, h = W // scale, H // scale
    data = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            v = math.sin(((x - y) / w) * math.pi * 2 * n + phase) * 0.5 + 0.5
            data[y * w + x] = int((v ** 4) * 255)
    return Image.frombytes("L", (w, h), bytes(data)).resize((W, H)).filter(ImageFilter.GaussianBlur(6))


def _tcg_base_anim(member, info, views):
    """Build the TCG card WITHOUT the avatar (placed per frame). Returns base + masks + overlays."""
    score, level, _, _ = rarity_level(info)
    col = TIERS_TCG.get(level, TIERS_TCG["Common"])["c"]
    et = TIERS_TCG.get(level, TIERS_TCG["Common"])["et"]
    uid = member.id
    W, H = 744, 1040
    dark = _mix(col, (12, 12, 16), 0.82)
    mid = _mix(col, (20, 20, 26), 0.6)

    card = _tcg_gradient(W, H, _mix(col, (18, 18, 24), 0.7), (8, 8, 11)).convert("RGBA")
    draw = ImageDraw.Draw(card)
    frame = _tcg_gradient(W, H, _mix(col, (255, 255, 255), 0.4), _mix(col, (0, 0, 0), 0.5)).convert("RGBA")
    fmask = Image.new("L", (W, H), 0)
    fd = ImageDraw.Draw(fmask)
    fd.rounded_rectangle([6, 6, W - 6, H - 6], radius=42, fill=255)
    fd.rounded_rectangle([30, 30, W - 30, H - 30], radius=32, fill=0)
    card.paste(frame, (0, 0), fmask)
    draw.rounded_rectangle([30, 30, W - 30, H - 30], radius=32, fill=dark)

    M = 46
    draw.rounded_rectangle([M, 46, W - M, 120], radius=20, fill=_mix(mid, (0, 0, 0), 0.2), outline=col, width=2)
    fn = _font(40, "ExtraBold")
    nm = member.name
    while draw.textlength(nm, font=fn) > W - M - 170 and len(nm) > 1:
        nm = nm[:-1]
    if nm != member.name:
        nm = nm[:-1] + "…"
    draw.text((M + 22, 83), nm, font=fn, fill=(255, 255, 255), anchor="lm")
    gx, gy, gr = W - M - 40, 83, 34
    draw.ellipse([gx - gr - 4, gy - gr - 4, gx + gr + 4, gy + gr + 4], fill=_mix(col, (0, 0, 0), 0.4))
    draw.ellipse([gx - gr, gy - gr, gx + gr, gy + gr], fill=col, outline=(255, 255, 255), width=3)
    draw.text((gx, gy), str(score), font=_font(30, "ExtraBold"), fill=(15, 15, 18), anchor="mm")

    ax0, ay0, ax1, ay1 = M, 138, W - M, 612
    # dark fill of the window (just in case) + frame
    draw.rounded_rectangle([ax0, ay0, ax1, ay1], radius=18, fill=_mix(col, (0, 0, 0), 0.55))
    draw.rounded_rectangle([ax0, ay0, ax1, ay1], radius=18, outline=col, width=3)

    draw.rounded_rectangle([M, 628, W - M, 684], radius=14, fill=_mix(mid, (0, 0, 0), 0.25), outline=col, width=2)
    draw.text((W // 2, 656), level.upper(), font=_font(26, "SemiBold"), fill=(255, 255, 255), anchor="mm")
    draw.rounded_rectangle([M, 700, W - M, 958], radius=18, fill=_mix((10, 10, 14), col, 0.06), outline=col, width=2)
    fl = _font(24, "Medium")
    y = 730
    keys = list(info["badges"]) + list(info["pseudo"])
    for extra in (info["anciennete"], info["boost"]):
        if extra:
            keys.append(extra)
    labels = [SET_ITEMS[k]["label"] for k in keys] or ["Standard account"]
    for lab in labels[:7]:
        draw.ellipse([M + 24, y - 6, M + 36, y + 6], fill=col)
        draw.text((M + 50, y), lab, font=fl, fill=(232, 234, 238), anchor="lm")
        y += 33
    for i in range(et):
        _tcg_star(draw, M + 24 + i * 30, 1000, 11, col)
    draw.text((W // 2, 1000), f"No. {int(str(uid)[-4:]):04d}", font=_font(22, "Medium"), fill=(200, 205, 212), anchor="mm")
    draw.text((W - M - 10, 1000), f"{score} PTS", font=_font(24, "Bold"), fill=col, anchor="rm")

    art_box = (ax0, ay0, ax1, ay1)
    art_reg = Image.new("L", (W, H), 0)
    ImageDraw.Draw(art_reg).rounded_rectangle([ax0, ay0, ax1, ay1], radius=18, fill=255)

    # Overlays (gloss + sparkles + views pill) -> placed OVER the avatar each frame
    overlays = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gl = ImageChops.multiply(_tcg_gloss(W, H, art_box), art_reg)
    overlays = Image.alpha_composite(overlays, Image.merge("RGBA", (Image.new("L", (W, H), 255),) * 3 + (gl,)))
    if et >= 4:
        pa = _tcg_sparkles(W, H, uid, art_box, et * 5)
        pa = Image.composite(pa, Image.new("RGBA", (W, H), (0, 0, 0, 0)), art_reg)
        overlays = Image.alpha_composite(overlays, pa)
    _draw_views(overlays, ax0 + 14, ay0 + 14, views, _font(24, "SemiBold"), height=40)

    frame_reg = Image.new("L", (W, H), 0)
    fr = ImageDraw.Draw(frame_reg)
    fr.rounded_rectangle([6, 6, W - 6, H - 6], radius=42, fill=255)
    fr.rounded_rectangle([30, 30, W - 30, H - 30], radius=32, fill=0)
    return card.convert("RGB"), frame_reg, art_reg, art_box, overlays, level


async def generate_tcg_anim(member, info, views=0, frames=16):
    """Animated holographic TCG card (GIF). The animated avatar (if GIF) moves with the holo."""
    av_frames, _animated = await _load_avatar_frames(member, 256)
    n_av = len(av_frames)

    base, frame_reg, art_reg, art_box, overlays, level = _tcg_base_anim(member, info, views)
    W, H = base.size
    ax0, ay0, ax1, ay1 = art_box
    aw, ah = ax1 - ax0, ay1 - ay0
    amask = Image.new("L", (aw, ah), 0)
    ImageDraw.Draw(amask).rounded_rectangle([0, 0, aw - 1, ah - 1], radius=18, fill=255)

    # pre-cut avatar frames to the window size
    av_window = [_cover(fr, aw, ah).convert("RGBA") for fr in av_frames]

    inten = HOLO_ANIM.get(level, 0.12)
    hue = _tcg_hue_index(W, H)
    corner = Image.new("L", (W, H), 0)
    ImageDraw.Draw(corner).rounded_rectangle([0, 0, W - 1, H - 1], radius=44, fill=255)
    bg = (30, 31, 34)

    imgs = []
    for f in range(frames):
        ph = f / frames
        # avatar (sampled over the duration -> clean loop)
        av = av_window[int(f * n_av / frames) % n_av]
        canvas = base.convert("RGBA")
        canvas.paste(av, (ax0, ay0), amask)
        canvas = Image.alpha_composite(canvas, overlays)
        rgb = canvas.convert("RGB")
        # holo
        p = hue.copy().convert("P")
        p.putpalette(_tcg_palette_rb(int(ph * 256)))
        rb = p.convert("RGB")
        bd = _tcg_bands_anim(W, H, ph * 2 * math.pi)
        mframe = ImageChops.multiply(frame_reg, bd).point(lambda v: int(min(255, v * inten * 2.4)))
        mart = ImageChops.multiply(art_reg, bd).point(lambda v: int(min(255, v * inten * 1.3)))
        rgb = Image.composite(ImageChops.screen(rgb, rb), rgb, mframe)
        rgb = Image.composite(ImageChops.overlay(rgb, rb), rgb, mart)
        full = Image.new("RGB", (W, H), bg)
        full.paste(rgb, (0, 0), corner)
        imgs.append(full)

    buf = BytesIO()
    imgs[0].save(buf, format="GIF", save_all=True, append_images=imgs[1:],
                 duration=80, loop=0, optimize=True, disposal=2)
    buf.seek(0)
    return buf



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
        ("!carte @member", "Premium profile card (image, or GIF if animated avatar)."),
        ("!tcg @member", "Holographic ANIMATED collectible card (GIF)."),
        ("!list", "List members for a criterion (dropdown menu)."),
        ("!stats", "Global server dashboard."),
        ("!top", "Ranking of the rarest accounts."),
        ("!fame", "Ranking of the most viewed profiles (unique views)."),
        ("!bareme", "Rarity scale (menu by category)."),
    ],
    "🎨 Customization": [
        ("!carte → Edit", "Under your own card, the Edit button changes color / background / description."),
    ],
}

# Full help, owners only (includes everything above + management & moderation).
HELP_OWNER = {
    "🔍 Detection": [
        ("!scan", "List members for a criterion (to the scan channel)."),
        ("!profil @member", "Full profile of a member."),
        ("!carte @member", "Premium profile card (image, or GIF if animated avatar)."),
        ("!tcg @member", "Holographic ANIMATED collectible card (GIF)."),
        ("!list", "List members for a criterion (dropdown menu)."),
        ("!stats", "Global server dashboard."),
        ("!top", "Ranking of the rarest accounts."),
        ("!fame", "Ranking of the most viewed profiles (unique views)."),
        ("!bareme", "Rarity scale (menu by category)."),
    ],
    "🎨 Customization": [
        ("!carte → Edit", "Under your own card, the Edit button changes color / background / description."),
    ],
    "⚙️ Configuration": [
        ("!set", "Interactive panel (roles, channels, alerts)."),
        ("!config", "Show the configuration."),
        ("!setlog #channel", "Joins channel."),
        ("!setscan #channel", "Scans channel."),
        ("!setemoji", "Manage the criteria emojis (menu)."),
        ("!create <emojis>", "Create emojis on the server (from other servers)."),
        ("!setmsg <text>", "Join message title."),
        ("!setfond <url|image>", "Custom card background (`reset` to remove)."),
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


@bot.command(name="setfond", aliases=["setbg", "setbackground"])
@check_owner()
async def setfond(ctx, url: str = None):
    """Set the card background. Attach an image OR give a URL. `!setfond reset` to remove."""
    if not PIL_OK:
        await ctx.send("Pillow isn't installed."); return

    if url and url.lower() in ("reset", "clear", "off", "none"):
        set_background(None)
        await ctx.send("✅ Custom background removed. Cards revert to the default background.")
        return

    if ctx.message.attachments:
        url = ctx.message.attachments[0].url
    if not url:
        await ctx.send("Give an image: `!setfond <url>` or **attach an image** to the message.\n"
                       "To remove: `!setfond reset`.")
        return

    async with ctx.typing():
        data = await _download(url)
        if not data:
            await ctx.send("❌ Couldn't download this image (invalid or expired link?)."); return
        try:
            img = Image.open(BytesIO(data)).convert("RGB")
        except Exception:
            await ctx.send("❌ This file isn't a valid image."); return
        # Re-encode at a bounded size to keep the DB light (and avoid expiring links)
        img = _cover(img, 900, 520)
        buf = BytesIO(); img.save(buf, format="JPEG", quality=85)
        set_background(buf.getvalue())

    preview = discord.File(BytesIO(buf.getvalue()), filename="background.jpg")
    await ctx.send("✅ Card background saved! Here's the preview (use `!carte` to see the final render):",
                   file=preview)


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
                             description="Nobody has views yet. Try `!carte @member`!",
                             color=discord.Color.gold())
    lines = [f"{medals.get(i, f'**{i}.**')} {m.mention} — 👁 {v} view(s)"
             for i, (v, m) in enumerate(ranking[:20], 1)]
    return discord.Embed(title="🏆 Fame Ranking", description="\n".join(lines), color=discord.Color.gold())


class ColorModal(discord.ui.Modal, title="Accent color"):
    value = discord.ui.TextInput(label="Hex color", placeholder="#9B59B6   (or « none » to remove)",
                                 required=False, max_length=7)

    def __init__(self, uid):
        super().__init__()
        self.uid = uid

    async def on_submit(self, interaction: discord.Interaction):
        v = str(self.value).strip()
        if not v or v.lower() in ("none", "rien"):
            set_color(self.uid, None)
            await interaction.response.send_message("🗑️ Color removed (back to the rarity color).", ephemeral=True)
            return
        h = v.lstrip("#")
        if len(h) != 6 or any(c not in "0123456789abcdefABCDEF" for c in h):
            await interaction.response.send_message("❌ Invalid color. Example: #9B59B6", ephemeral=True)
            return
        set_color(self.uid, "#" + h.upper())
        await interaction.response.send_message(f"✅ Color saved: #{h.upper()}. Run `!carte` again.", ephemeral=True)


class BioModal(discord.ui.Modal, title="Description"):
    value = discord.ui.TextInput(label="Your description", style=discord.TextStyle.paragraph,
                                 placeholder="Write your sentence (or « none » to remove)", required=False, max_length=120)

    def __init__(self, uid):
        super().__init__()
        self.uid = uid

    async def on_submit(self, interaction: discord.Interaction):
        v = str(self.value).strip()
        if not v or v.lower() in ("none", "rien"):
            set_bio(self.uid, None)
            await interaction.response.send_message("🗑️ Description removed.", ephemeral=True)
            return
        set_bio(self.uid, " ".join(v.split())[:120])
        await interaction.response.send_message("✅ Description saved. Run `!carte` again.", ephemeral=True)


class EditActionsView(discord.ui.View):
    """Ephemeral menu: pick what to edit on your card."""
    def __init__(self, uid):
        super().__init__(timeout=180)
        self.uid = uid

    @discord.ui.button(label="Color", emoji="🎨", style=discord.ButtonStyle.secondary)
    async def b_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ColorModal(self.uid))

    @discord.ui.button(label="Description", emoji="📝", style=discord.ButtonStyle.secondary)
    async def b_desc(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BioModal(self.uid))

    @discord.ui.button(label="Background", emoji="🖼️", style=discord.ButtonStyle.secondary)
    async def b_bg(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not PIL_OK:
            await interaction.response.send_message("Pillow isn't installed.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Send your **background image** here (as an attachment), or type **none** to cancel.\n"
            "_Your message will be deleted right away so nobody sees it._", ephemeral=True)

        def check(m):
            return m.author.id == self.uid and m.channel.id == interaction.channel.id

        try:
            msg = await bot.wait_for("message", check=check, timeout=120)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏱️ Time's up, background not changed.", ephemeral=True)
            return

        content = (msg.content or "").strip().lower()
        data = await _download(msg.attachments[0].url) if msg.attachments else None
        try:
            await msg.delete()
            deleted = True
        except Exception:
            deleted = False

        if content in ("none", "rien"):
            await interaction.followup.send("Cancelled." + ("" if deleted else " (couldn't delete your message)"), ephemeral=True)
            return
        if not data:
            await interaction.followup.send("❌ No valid image found. Try again via Edit.", ephemeral=True)
            return
        try:
            img = Image.open(BytesIO(data)).convert("RGB")
            img = _cover(img, 900, 560)
            buf = BytesIO(); img.save(buf, format="JPEG", quality=85)
            set_member_background(self.uid, buf.getvalue())
        except Exception:
            await interaction.followup.send("❌ This file isn't a valid image.", ephemeral=True)
            return
        rep = "✅ Background saved! Run `!carte` again."
        if not deleted:
            rep += "\n⚠️ I couldn't delete your message (missing 'Manage Messages' permission)."
        await interaction.followup.send(rep, ephemeral=True)


class CardEditView(discord.ui.View):
    """'Edit' button under your own card."""
    def __init__(self, owner_id):
        super().__init__(timeout=600)
        self.owner_id = owner_id

    @discord.ui.button(label="Edit", emoji="✏️", style=discord.ButtonStyle.secondary)
    async def b_edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("You can only edit your own card.", ephemeral=True)
            return
        await interaction.response.send_message("What do you want to edit?", view=EditActionsView(self.owner_id), ephemeral=True)


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


@bot.command(name="carte", aliases=["card"])
@check_public()
async def carte(ctx, *, ref: str = None):
    """Generate a profile card (image, or GIF if animated avatar). Ex: !carte @member / !carte <id>"""
    if not PIL_OK:
        await ctx.send("The Pillow library isn't installed (add `Pillow` to your dependencies).")
        return
    member = await resolve_target(ctx, ref)
    if member is None:
        await ctx.send("❌ User not found. Give a valid **mention**, **ID**, or **username**.")
        return
    info = collect_info(member)
    views = record_unique_view(ctx.author, member)
    rank = fame_rank(ctx.guild, member.id) if ctx.guild else 0
    bio = BIOS.get(member.id)
    accent = member_color(member.id)
    async with ctx.typing():
        buf, ext = await generate_card(member, info, views, rank, bio, accent)
    view = CardEditView(member.id) if member.id == ctx.author.id else None
    await ctx.send(content=f"👁 **{views}** view(s)",
                   file=discord.File(buf, filename=f"card.{ext}"), view=view)


@bot.command(name="tcg", aliases=["tcgcard", "collec", "holo", "anim"])
@check_public()
async def tcg(ctx, *, ref: str = None):
    """Generate an ANIMATED holographic collectible card (GIF). Ex: !tcg @member / !tcg <id>"""
    if not PIL_OK:
        await ctx.send("The Pillow library isn't installed (add `Pillow` to your dependencies).")
        return
    member = await resolve_target(ctx, ref)
    if member is None:
        await ctx.send("❌ User not found. Give a valid **mention**, **ID**, or **username**.")
        return
    info = collect_info(member)
    views = record_unique_view(ctx.author, member)
    async with ctx.typing():
        buf = await generate_tcg_anim(member, info, views)
    await ctx.send(content=f"👁 **{views}** view(s)",
                   file=discord.File(buf, filename="tcg_card.gif"))


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


class FameView(discord.ui.View):
    """Dropdown: show the fame as a Card or TCG."""
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.select(placeholder="Choose the display…", options=[
        discord.SelectOption(label="Fame Card", value="carte", emoji="🖼️", description="Ranking + card of #1"),
        discord.SelectOption(label="Fame TCG", value="tcg", emoji="🎴", description="Ranking + animated TCG of #1"),
    ])
    async def choose(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer()
        guild = interaction.guild
        counts = views_per_profile()
        ranking = []
        for m in guild.members:
            if m.bot:
                continue
            v = counts.get(m.id, 0)
            if v > 0:
                ranking.append((v, m))
        ranking.sort(key=lambda x: x[0], reverse=True)
        embed = fame_embed(guild)
        if not ranking or not PIL_OK:
            await interaction.followup.send(embed=embed)
            return
        top_m = ranking[0][1]
        info = collect_info(top_m)
        views = count_views(top_m.id)
        try:
            if select.values[0] == "carte":
                buf, ext = await generate_card(top_m, info, views, fame_rank(guild, top_m.id),
                                               BIOS.get(top_m.id), member_color(top_m.id))
                file = discord.File(buf, filename=f"fame_card.{ext}")
            else:
                buf = await generate_tcg_anim(top_m, info, views)
                file = discord.File(buf, filename="fame_tcg.gif")
            await interaction.followup.send(content=f"👑 **Fame #1**: {top_m.mention}", embed=embed, file=file)
        except Exception:
            await interaction.followup.send(embed=embed)


@bot.command(name="fame", aliases=["fames", "celebrite", "vues"])
@check_public()
async def fame(ctx):
    """Ranking of the most viewed profiles (Card / TCG menu)."""
    await ctx.send("🏆 **Fame** — choose the display:", view=FameView())


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
                     "`!profil` · `!carte` · `!bareme` · `!top` · `!list` · `!stats`\n\n"
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
    ensure_fonts()   # download Poppins once (system font fallback on failure)
    bot.run(TOKEN)
