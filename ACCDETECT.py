"""
================================================================================
  BOT DISCORD - DETECTION DE COMPTES RARES (version enrichie)
  buyer/owner · SQLite · !set/!scan par categorie · boost · niveau de rarete
  + MODERATION : ban / unban / mute / unmute / tempmute (par ID ou mention,
    meme si la personne n'est PAS sur le serveur)
================================================================================
NOTE: les badges Nitro (Bronze..Opale) ne sont PAS exposes par l'API Discord et
ne peuvent donc pas etre detectes par un bot. On detecte uniquement le BOOST de
ce serveur (via premium_since).
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
#  REGLAGES DE BASE
# ==============================================================================

BUYER_ID = 142365250803466240
TOKEN = os.environ.get("DISCORD_TOKEN", "COLLE_TON_TOKEN_ICI_SI_TU_VEUX")
DB_PATH = os.environ.get("DB_PATH", "bot.db")
SEUIL_MOT = 2.5

OG_SEUILS = [
    ("og2016", datetime.datetime(2016, 1, 1, tzinfo=datetime.timezone.utc)),
    ("og2017", datetime.datetime(2017, 1, 1, tzinfo=datetime.timezone.utc)),
    ("og2018", datetime.datetime(2018, 1, 1, tzinfo=datetime.timezone.utc)),
]

# Paliers de boost (mois -> cle), du plus haut au plus bas.
BOOST_PALIERS = [(24, "boost24"), (18, "boost18"), (15, "boost15"), (12, "boost12"),
                 (9, "boost9"), (6, "boost6"), (3, "boost3"), (2, "boost2"), (1, "boost1")]
BOOST_MOIS = {k: m for m, k in BOOST_PALIERS}

# ==============================================================================
#  CATALOGUE
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
    "partner":    {"label": "Partenaire Discord",         "type": "role"},
    "staff":      {"label": "Staff Discord",              "type": "role"},
    "boost1":     {"label": "Boost 1 mois",               "type": "role"},
    "boost2":     {"label": "Boost 2 mois",               "type": "role"},
    "boost3":     {"label": "Boost 3 mois",               "type": "role"},
    "boost6":     {"label": "Boost 6 mois",               "type": "role"},
    "boost9":     {"label": "Boost 9 mois",               "type": "role"},
    "boost12":    {"label": "Boost 12 mois",              "type": "role"},
    "boost15":    {"label": "Boost 15 mois",              "type": "role"},
    "boost18":    {"label": "Boost 18 mois",              "type": "role"},
    "boost24":    {"label": "Boost 24 mois",              "type": "role"},
    "og2016":     {"label": "OG - avant 2016",            "type": "role"},
    "og2017":     {"label": "OG - avant 2017",            "type": "role"},
    "og2018":     {"label": "OG - avant 2018",            "type": "role"},
    "pseudo2":    {"label": "Pseudo de 2 caracteres",     "type": "role"},
    "pseudo3":    {"label": "Pseudo de 3 caracteres",     "type": "role"},
    "mot":        {"label": "Pseudo : vrai mot (FR/EN)",  "type": "role"},
    "chiffres":   {"label": "Pseudo : que des chiffres",  "type": "role"},
    "alertrole":  {"label": "Role a ping (alertes)",      "type": "role"},
    "logs":       {"label": "Salon de logs (joins)",      "type": "channel"},
    "scanlog":    {"label": "Salon de scan",              "type": "channel"},
}

CATEGORIES = {
    "🏅 Badges":        ["early", "hypesquad", "bravery", "brilliance", "balance",
                         "bughunter", "bughunter2", "botdev", "mod", "partner", "staff"],
    "🚀 Boost":         ["boost1", "boost2", "boost3", "boost6", "boost9",
                         "boost12", "boost15", "boost18", "boost24"],
    "📅 Anciennete":    ["og2016", "og2017", "og2018"],
    "✨ Pseudo":        ["pseudo2", "pseudo3", "mot", "chiffres"],
    "🚨 Alerte":        ["alertrole"],
    "📋 Salons":        ["logs", "scanlog"],
}

# Cles que l'on sait detecter (pour scan/list/stats/top).
DETECT_KEYS = [k for k, v in SET_ITEMS.items() if v["type"] == "role" and k != "alertrole"]

DEFAULT_EMOJIS = {
    "early": "🥇", "hypesquad": "🎉", "bravery": "🛡️", "brilliance": "🔮", "balance": "⚖️",
    "bughunter": "🐛", "bughunter2": "🐛", "botdev": "🤖", "mod": "🛡️", "partner": "🤝", "staff": "👑",
    "boost1": "🚀", "boost2": "🚀", "boost3": "🚀", "boost6": "🚀", "boost9": "🚀",
    "boost12": "🚀", "boost15": "🚀", "boost18": "🚀", "boost24": "🚀",
    "og2016": "📅", "og2017": "📅", "og2018": "📅",
    "pseudo2": "✨", "pseudo3": "✨", "mot": "🔤", "chiffres": "🔢",
}

JOIN_TITRE_DEFAUT = "🌟 Un compte rare a rejoint le serveur !"

# --- Bareme de rarete (revu) ---
POIDS = {
    # Badges (du plus prestigieux au plus commun)
    "staff": 10, "partner": 8, "botdev": 6, "bughunter2": 6, "mod": 5, "bughunter": 4,
    "hypesquad": 3, "early": 3, "bravery": 1, "brilliance": 1, "balance": 1,
    # Anciennete
    "og2016": 5, "og2017": 3, "og2018": 2,
    # Pseudo
    "pseudo2": 5, "pseudo3": 3, "mot": 2, "chiffres": 1,
    # Boost (bonus, faible poids)
    "boost1": 1, "boost2": 1, "boost3": 2, "boost6": 2, "boost9": 3,
    "boost12": 3, "boost15": 4, "boost18": 4, "boost24": 5,
}

# Paliers : (score minimum, nom, emoji, couleur)
NIVEAUX = [
    (0,  "Commun",      "⚪", discord.Color.light_grey()),
    (2,  "Peu commun",  "🟢", discord.Color.green()),
    (5,  "Rare",        "🔵", discord.Color.blue()),
    (9,  "Epique",      "🟣", discord.Color.purple()),
    (14, "Legendaire",  "🟡", discord.Color.gold()),
    (20, "Mythique",    "🔴", discord.Color.red()),
]

# ==============================================================================
#  BASE DE DONNEES
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
    # Mutes persistants (survivent au redemarrage)
    conn.execute("CREATE TABLE IF NOT EXISTS mutes (guild_id INTEGER, user_id INTEGER, "
                 "until INTEGER, reason TEXT, PRIMARY KEY (guild_id, user_id))")
    conn.commit(); conn.close()


def _charger(table, c1, c2):
    conn = db()
    rows = conn.execute(f"SELECT {c1}, {c2} FROM {table}").fetchall()
    conn.close()
    return {k: v for k, v in rows}


def definir_config(key, value):
    CONFIG[key] = value
    conn = db()
    conn.execute("INSERT INTO config (key,value) VALUES (?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit(); conn.close()


def definir_emoji(key, emoji):
    EMOJIS[key] = emoji
    conn = db()
    conn.execute("INSERT INTO emojis (key,emoji) VALUES (?,?) "
                 "ON CONFLICT(key) DO UPDATE SET emoji=excluded.emoji", (key, emoji))
    conn.commit(); conn.close()


def definir_message(key, contenu):
    MESSAGES[key] = contenu
    conn = db()
    conn.execute("INSERT INTO messages (key,contenu) VALUES (?,?) "
                 "ON CONFLICT(key) DO UPDATE SET contenu=excluded.contenu", (key, contenu))
    conn.commit(); conn.close()


def charger_owners():
    conn = db(); rows = conn.execute("SELECT user_id FROM owners").fetchall(); conn.close()
    return {r[0] for r in rows}


def ajouter_owner(uid):
    conn = db(); conn.execute("INSERT OR IGNORE INTO owners (user_id) VALUES (?)", (uid,))
    conn.commit(); conn.close(); OWNERS.add(uid)


def retirer_owner(uid):
    conn = db(); conn.execute("DELETE FROM owners WHERE user_id=?", (uid,))
    conn.commit(); conn.close(); OWNERS.discard(uid)


def charger_fond():
    conn = db()
    row = conn.execute("SELECT data FROM fond WHERE id=1").fetchone()
    conn.close()
    return row[0] if row else None


def definir_fond(data):
    global FOND_DATA
    FOND_DATA = data
    conn = db()
    conn.execute("DELETE FROM fond")
    if data is not None:
        conn.execute("INSERT INTO fond (id, data) VALUES (1, ?)", (data,))
    conn.commit(); conn.close()


def charger_salons_public():
    conn = db(); rows = conn.execute("SELECT channel_id FROM salons_public").fetchall(); conn.close()
    return {r[0] for r in rows}


def ajouter_salon_public(cid):
    conn = db(); conn.execute("INSERT OR IGNORE INTO salons_public (channel_id) VALUES (?)", (cid,))
    conn.commit(); conn.close(); SALONS_PUBLIC.add(cid)


def retirer_salon_public(cid):
    conn = db(); conn.execute("DELETE FROM salons_public WHERE channel_id=?", (cid,))
    conn.commit(); conn.close(); SALONS_PUBLIC.discard(cid)


def enregistrer_vue(profil_id, viewer_id):
    """Ajoute une vue unique (viewer -> profil) et renvoie le total de vues du profil."""
    conn = db()
    conn.execute("INSERT OR IGNORE INTO vues (profil_id, viewer_id) VALUES (?, ?)", (profil_id, viewer_id))
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM vues WHERE profil_id=?", (profil_id,)).fetchone()[0]
    conn.close()
    return n


def compter_vues(profil_id):
    conn = db()
    n = conn.execute("SELECT COUNT(*) FROM vues WHERE profil_id=?", (profil_id,)).fetchone()[0]
    conn.close()
    return n


def vues_par_profil():
    """Renvoie {profil_id: nombre_de_vues} pour tous les profils vus."""
    conn = db()
    rows = conn.execute("SELECT profil_id, COUNT(*) FROM vues GROUP BY profil_id").fetchall()
    conn.close()
    return dict(rows)


def definir_bio(uid, texte):
    conn = db()
    if texte:
        BIOS[uid] = texte
        conn.execute("INSERT INTO bios (user_id, texte) VALUES (?,?) "
                     "ON CONFLICT(user_id) DO UPDATE SET texte=excluded.texte", (uid, texte))
    else:
        BIOS.pop(uid, None)
        conn.execute("DELETE FROM bios WHERE user_id=?", (uid,))
    conn.commit(); conn.close()


def definir_couleur(uid, couleur):
    conn = db()
    if couleur:
        COULEURS[uid] = couleur
        conn.execute("INSERT INTO couleurs (user_id, couleur) VALUES (?,?) "
                     "ON CONFLICT(user_id) DO UPDATE SET couleur=excluded.couleur", (uid, couleur))
    else:
        COULEURS.pop(uid, None)
        conn.execute("DELETE FROM couleurs WHERE user_id=?", (uid,))
    conn.commit(); conn.close()


def definir_fond_membre(uid, data):
    conn = db()
    conn.execute("DELETE FROM fonds_membres WHERE user_id=?", (uid,))
    if data is not None:
        conn.execute("INSERT INTO fonds_membres (user_id, data) VALUES (?,?)", (uid, data))
    conn.commit(); conn.close()


def fond_membre(uid):
    conn = db()
    row = conn.execute("SELECT data FROM fonds_membres WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    return row[0] if row else None


def couleur_membre(uid):
    """Renvoie un tuple RGB si l'utilisateur a defini une couleur, sinon None."""
    hexa = COULEURS.get(uid)
    if not hexa:
        return None
    try:
        h = hexa.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return None


# --- Mutes (base) ---
def db_ajouter_mute(gid, uid, until, reason):
    conn = db()
    conn.execute("INSERT INTO mutes (guild_id,user_id,until,reason) VALUES (?,?,?,?) "
                 "ON CONFLICT(guild_id,user_id) DO UPDATE SET until=excluded.until, reason=excluded.reason",
                 (gid, uid, until, reason))
    conn.commit(); conn.close()


def db_retirer_mute(gid, uid):
    conn = db(); conn.execute("DELETE FROM mutes WHERE guild_id=? AND user_id=?", (gid, uid))
    conn.commit(); conn.close()


def db_info_mute(gid, uid):
    conn = db()
    row = conn.execute("SELECT until, reason FROM mutes WHERE guild_id=? AND user_id=?", (gid, uid)).fetchone()
    conn.close()
    return row  # (until, reason) ou None


def db_tous_mutes():
    conn = db()
    rows = conn.execute("SELECT guild_id, user_id, until, reason FROM mutes").fetchall()
    conn.close()
    return rows


def db_mutes_guild(gid):
    conn = db()
    rows = conn.execute("SELECT user_id, until, reason FROM mutes WHERE guild_id=?", (gid,)).fetchall()
    conn.close()
    return rows


FAME_PALIERS = [(100, "Icône"), (40, "Légende"), (15, "Star"), (5, "Populaire"), (1, "Connu"), (0, "Inconnu")]


def fame_titre(v):
    for seuil, nom in FAME_PALIERS:
        if v >= seuil:
            return nom
    return "Inconnu"


def fame_rang(guild, uid):
    """Rang (1 = le plus vu) de l'utilisateur parmi les membres du serveur. 0 si aucune vue / non-membre."""
    compte = vues_par_profil()
    mes_vues = compte.get(uid, 0)
    if mes_vues <= 0:
        return 0
    ids = {m.id for m in guild.members}
    if uid not in ids:
        return 0
    meilleurs = sorted((v for pid, v in compte.items() if pid in ids), reverse=True)
    return meilleurs.index(mes_vues) + 1 if mes_vues in meilleurs else 0


init_db()
CONFIG = _charger("config", "key", "value")
EMOJIS = _charger("emojis", "key", "emoji")
MESSAGES = _charger("messages", "key", "contenu")
OWNERS = charger_owners()
FOND_DATA = charger_fond()
SALONS_PUBLIC = charger_salons_public()
BIOS = _charger("bios", "user_id", "texte")
COULEURS = _charger("couleurs", "user_id", "couleur")


def emoji_de(key):
    return EMOJIS.get(key) or DEFAULT_EMOJIS.get(key, "•")


def message_de(key, defaut):
    return MESSAGES.get(key, defaut)


# ==============================================================================
#  PERMISSIONS
# ==============================================================================

def est_buyer(uid): return uid == BUYER_ID
def est_owner(uid): return uid == BUYER_ID or uid in OWNERS


def check_buyer():
    async def predicate(ctx): return est_buyer(ctx.author.id)
    return commands.check(predicate)


def check_owner():
    async def predicate(ctx): return est_owner(ctx.author.id)
    return commands.check(predicate)


def check_public():
    """Owner partout, OU n'importe qui dans un salon autorise via !allow."""
    async def predicate(ctx):
        return est_owner(ctx.author.id) or (ctx.guild is not None and ctx.channel.id in SALONS_PUBLIC)
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

def detecter_badges(user):
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


def detecter_anciennete(user):
    for key, limite in OG_SEUILS:
        if user.created_at < limite:
            return key
    return None


def est_mot(nom):
    if not WORDFREQ_OK or not nom.isalpha() or len(nom) < 3:
        return False
    return zipf_frequency(nom, "fr") >= SEUIL_MOT or zipf_frequency(nom, "en") >= SEUIL_MOT


def detecter_pseudo(user):
    nom = user.name
    out = []
    if len(nom) == 2:
        out.append("pseudo2")
    elif len(nom) == 3:
        out.append("pseudo3")
    if est_mot(nom):
        out.append("mot")
    if nom.isdigit():
        out.append("chiffres")
    return out


def mois_de_boost(member):
    """Nombre de mois de boost de CE serveur, ou None si le membre ne boost pas."""
    since = getattr(member, "premium_since", None)
    if not since:
        return None
    delta = datetime.datetime.now(datetime.timezone.utc) - since
    return delta.days / 30.44


def detecter_boost(member):
    mois = mois_de_boost(member)
    if mois is None:
        return None
    for seuil, key in BOOST_PALIERS:
        if mois >= seuil:
            return key
    return "boost1"  # boost depuis moins d'un mois


def collecter_infos(member):
    return {
        "badges": detecter_badges(member),
        "pseudo": detecter_pseudo(member),
        "anciennete": detecter_anciennete(member),
        "boost": detecter_boost(member),
        "erreurs": [],
    }


async def recuperer_user(member):
    """Recupere l'utilisateur complet (pour afficher sa banniere dans l'embed)."""
    try:
        return await bot.fetch_user(member.id)
    except Exception:
        return None


async def resoudre_cible(ctx, ref):
    """Resout une reference (mention, ID, nom, ou None).
    Renvoie un Member si la personne est dans le serveur, sinon un User global (meme hors serveur).
    Renvoie None si introuvable."""
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
            membre = ctx.guild.get_member(uid)
            if membre:
                return membre
        try:
            return await bot.fetch_user(uid)
        except Exception:
            return None
    # Recherche par nom / surnom dans le serveur
    if ctx.guild:
        bas = s.lower().lstrip("@")
        for mm in ctx.guild.members:
            if mm.name.lower() == bas or mm.display_name.lower() == bas or (mm.nick and mm.nick.lower() == bas):
                return mm
    return None


OG_THRESHOLDS = dict(OG_SEUILS)


def membre_a_cle(member, key):
    if key in OG_THRESHOLDS:
        return member.created_at < OG_THRESHOLDS[key]
    if key in BOOST_MOIS:
        mois = mois_de_boost(member)
        return mois is not None and mois >= BOOST_MOIS[key]
    if key in ("pseudo2", "pseudo3", "mot", "chiffres"):
        return key in detecter_pseudo(member)
    return key in detecter_badges(member)


def membres_avec(guild, key):
    return [m for m in guild.members if not m.bot and membre_a_cle(m, key)]


async def attribuer_roles_depuis(member, infos):
    cles = list(infos["badges"]) + list(infos["pseudo"])
    for extra in (infos["anciennete"], infos["boost"]):
        if extra:
            cles.append(extra)
    role_ids = {CONFIG.get(c, 0) for c in cles}
    role_ids.discard(0)
    roles = [r for rid in role_ids if (r := member.guild.get_role(rid)) and r not in member.roles]
    if roles:
        try:
            await member.add_roles(*roles, reason="Compte rare detecte")
        except discord.Forbidden:
            infos["erreurs"].append("Permission 'Gerer les roles' manquante, ou role du bot trop bas.")
        except discord.HTTPException as e:
            infos["erreurs"].append(f"Erreur API : {e}")


async def appliquer_roles(member):
    infos = collecter_infos(member)
    await attribuer_roles_depuis(member, infos)
    return infos


def est_notable(infos):
    return bool(infos["badges"] or infos["pseudo"] or infos["anciennete"] or infos["boost"])


# ==============================================================================
#  RARETE
# ==============================================================================

def score_rarete(infos):
    s = sum(POIDS.get(b, 0) for b in infos["badges"])
    s += sum(POIDS.get(p, 0) for p in infos["pseudo"])
    if infos["anciennete"]:
        s += POIDS.get(infos["anciennete"], 0)
    if infos["boost"]:
        s += POIDS.get(infos["boost"], 0)
    return s


def niveau_rarete(infos):
    s = score_rarete(infos)
    nom, emo, couleur = NIVEAUX[0][1], NIVEAUX[0][2], NIVEAUX[0][3]
    for seuil, n, e, c in NIVEAUX:
        if s >= seuil:
            nom, emo, couleur = n, e, c
    return s, nom, emo, couleur


def exceptionnel(infos):
    _, niveau, _, _ = niveau_rarete(infos)
    if niveau in ("Legendaire", "Mythique"):
        return True
    return any(b in infos["badges"] for b in ("staff", "partner", "bughunter2"))


# ==============================================================================
#  EMBED PROFIL (join + profil)
# ==============================================================================

def embed_profil(member, infos, titre):
    score, niveau, emo, couleur = niveau_rarete(infos)
    maintenant = datetime.datetime.now(datetime.timezone.utc)
    age = maintenant - member.created_at
    annees, jours = age.days // 365, age.days % 365

    embed = discord.Embed(title=titre, color=couleur, timestamp=maintenant)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Utilisateur", value=f"{member.mention}\n`{member.name}`", inline=True)
    embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
    embed.add_field(name="💎 Niveau", value=f"{emo} **{niveau}** ({score} pts)", inline=True)
    embed.add_field(name="📅 Compte cree",
                    value=f"<t:{int(member.created_at.timestamp())}:D>\n(il y a {annees} an(s) et {jours} j)",
                    inline=True)
    j = getattr(member, "joined_at", None)
    if j:
        embed.add_field(name="📥 A rejoint", value=f"<t:{int(j.timestamp())}:R>", inline=True)

    # Badges = emojis seuls (badges + pseudo + anciennete + boost), sans texte.
    cles = list(infos["badges"]) + list(infos["pseudo"])
    for extra in (infos["anciennete"], infos["boost"]):
        if extra:
            cles.append(extra)
    ligne = "  ".join(emoji_de(k) for k in cles) if cles else "—"
    embed.add_field(name="🏅 Badges", value=ligne, inline=False)

    if infos["erreurs"]:
        embed.add_field(name="⚠️ Attention", value="\n".join(infos["erreurs"]), inline=False)
    return embed


async def envoyer_log_join(guild, member, infos, user=None):
    salon = guild.get_channel(CONFIG.get("logs", 0))
    if salon is None:
        return
    embed = embed_profil(member, infos, message_de("join", JOIN_TITRE_DEFAUT))
    embed.set_footer(text=guild.name)
    if user and user.banner:
        embed.set_image(url=user.banner.url)
    content = None
    if exceptionnel(infos):
        rid = CONFIG.get("alertrole", 0)
        if rid:
            content = f"<@&{rid}>"
    try:
        await salon.send(content=content, embed=embed)
    except discord.HTTPException:
        pass


# ==============================================================================
#  CARTE PROFIL EN IMAGE (Pillow)
# ==============================================================================

# --- Polices : Poppins (telechargee au demarrage), repli sur les polices systeme ---
DOSSIER_POLICES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
POLICES_URLS = {
    "Poppins-ExtraBold.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-ExtraBold.ttf",
    "Poppins-Bold.ttf":      "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-Bold.ttf",
    "Poppins-SemiBold.ttf":  "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-SemiBold.ttf",
    "Poppins-Medium.ttf":    "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-Medium.ttf",
    "Poppins-Regular.ttf":   "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-Regular.ttf",
}
_REPLI_SYS = {
    "ExtraBold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "Bold":      "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "SemiBold":  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "Medium":    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "Regular":   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
}


def assurer_polices():
    """Telecharge Poppins une fois (si absente). Echec silencieux -> repli systeme."""
    if not PIL_OK:
        return
    try:
        os.makedirs(DOSSIER_POLICES, exist_ok=True)
    except Exception:
        return
    import urllib.request
    for nom, url in POLICES_URLS.items():
        chemin = os.path.join(DOSSIER_POLICES, nom)
        if os.path.exists(chemin):
            continue
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                data = r.read()
            with open(chemin, "wb") as f:
                f.write(data)
        except Exception:
            pass


def _police(taille, poids="Regular"):
    chemin = os.path.join(DOSSIER_POLICES, f"Poppins-{poids}.ttf")
    if os.path.exists(chemin):
        try:
            return ImageFont.truetype(chemin, taille)
        except Exception:
            pass
    try:
        return ImageFont.truetype(_REPLI_SYS.get(poids, _REPLI_SYS["Regular"]), taille)
    except Exception:
        return ImageFont.load_default()


def _ajuster(draw, texte, font, maxw):
    if draw.textlength(texte, font=font) <= maxw:
        return texte
    while texte and draw.textlength(texte + "…", font=font) > maxw:
        texte = texte[:-1]
    return texte + "…"


def _ombre(draw, pos, texte, font, fill, anchor=None, dx=2, dy=3, alpha=170):
    """Texte avec ombre portee simple (lisibilite sur fond charge)."""
    draw.text((pos[0] + dx, pos[1] + dy), texte, font=font, fill=(0, 0, 0, alpha), anchor=anchor)
    draw.text(pos, texte, font=font, fill=fill, anchor=anchor)


def _melange(c, rgb, f):
    return tuple(int(c[i] + (rgb[i] - c[i]) * f) for i in range(3))


async def _telecharger(url):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    return await r.read()
    except Exception:
        pass
    return None


def _couvrir(img, L, H):
    """Redimensionne en 'cover' (remplit L x H, recadre le surplus au centre)."""
    iw, ih = img.size
    echelle = max(L / iw, H / ih)
    nw, nh = max(1, int(iw * echelle)), max(1, int(ih * echelle))
    img = img.resize((nw, nh))
    gx, gy = (nw - L) // 2, (nh - H) // 2
    return img.crop((gx, gy, gx + L, gy + H))


def _fond_degrade(L, H, c1, c2):
    base = Image.new("RGBA", (L, H))
    d = ImageDraw.Draw(base)
    for y in range(H):
        t = y / max(1, H - 1)
        col = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)) + (255,)
        d.line([(0, y), (L, y)], fill=col)
    return base


def _voile_gauche(L, H, force=225, fin=0.74):
    """Voile sombre degradant de gauche (opaque) vers la droite (transparent)."""
    ov = Image.new("RGBA", (L, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    xfin = max(1, int(L * fin))
    for x in range(L):
        a = int(force * (1 - x / xfin)) if x < xfin else 0
        d.line([(x, 0), (x, H)], fill=(8, 10, 12, max(0, min(255, a))))
    return ov


# Couleurs vives par niveau (rendu carte)
CARTE_COULEURS = {
    "Commun": (149, 165, 166), "Peu commun": (46, 204, 113), "Rare": (52, 152, 219),
    "Epique": (155, 89, 182), "Legendaire": (241, 196, 15), "Mythique": (231, 76, 60),
}


def _progression(score):
    """Renvoie (fraction 0..1 vers le palier suivant, score du palier suivant ou None)."""
    idx = 0
    for i, (s, *_rest) in enumerate(NIVEAUX):
        if score >= s:
            idx = i
    cur = NIVEAUX[idx][0]
    if idx + 1 < len(NIVEAUX):
        nxt = NIVEAUX[idx + 1][0]
        frac = (score - cur) / (nxt - cur) if nxt > cur else 1.0
        return max(0.0, min(1.0, frac)), nxt
    return 1.0, None


def _oeil(draw, cx, cy, w):
    """Dessine une petite icone d'oeil (vectorielle)."""
    h = int(w * 0.66)
    draw.ellipse([cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2], fill=(238, 240, 243))
    ir = int(h * 0.46)
    draw.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], fill=(64, 96, 168))
    pp = max(2, int(ir * 0.52))
    draw.ellipse([cx - pp, cy - pp, cx + pp, cy + pp], fill=(16, 16, 22))
    rf = max(1, pp // 2)
    draw.ellipse([cx - pp, cy - pp, cx - pp + rf, cy - pp + rf], fill=(255, 255, 255))


def _dessiner_vues(carte, x, y, vues, police, hauteur=42):
    """Pastille translucide : icone oeil + compteur de vues. Renvoie sa largeur."""
    d = ImageDraw.Draw(carte)
    txt = str(vues)
    ew = int(hauteur * 0.62)
    tw = d.textlength(txt, font=police)
    pad = 14
    largeur = int(pad + ew + 8 + tw + pad)
    pill = Image.new("RGBA", carte.size, (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle([x, y, x + largeur, y + hauteur], radius=hauteur // 2, fill=(10, 12, 16, 175))
    carte.alpha_composite(pill)
    d = ImageDraw.Draw(carte)
    _oeil(d, int(x + pad + ew / 2), int(y + hauteur / 2), ew)
    d.text((x + pad + ew + 8, y + hauteur // 2), txt, font=police, fill=(240, 242, 245), anchor="lm")
    return largeur


def _gif_en_frames(data, max_frames=30):
    """Decoupe des bytes GIF/anime en frames RGB en composant correctement les frames."""
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
    voulues = set([int(i * n / max_frames) for i in range(max_frames)] if n > max_frames else range(n))
    frames, canvas = [], None
    try:
        for idx in range(n):
            im.seek(idx)
            cur = im.convert("RGBA")
            canvas = cur if canvas is None else Image.alpha_composite(canvas, cur)
            if idx in voulues:
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


async def _lire_asset(asset):
    """Lit un asset Discord en bytes, avec repli direct (aiohttp) sur son URL."""
    try:
        data = await asset.read()
        if data:
            return data
    except Exception:
        pass
    try:
        return await _telecharger(str(asset.url))
    except Exception:
        return None


async def _charger_frames_avatar(member, taille=256, max_frames=30):
    """Renvoie (frames RGB, est_anime). Avatars GIF animes geres, avec replis robustes."""
    av = member.display_avatar
    try:
        anime = bool(av.is_animated())
    except Exception:
        anime = False

    if anime:
        for variante in (
            lambda: av.replace(size=taille, format="gif"),
            lambda: av.with_size(taille).with_format("gif"),
            lambda: av,
        ):
            try:
                data = await _lire_asset(variante())
            except Exception:
                data = None
            if data:
                frames = _gif_en_frames(data, max_frames)
                if frames:
                    return frames, len(frames) > 1

    for variante in (
        lambda: av.replace(size=taille, static_format="png"),
        lambda: av.replace(size=taille, format="png"),
        lambda: av,
    ):
        try:
            data = await _lire_asset(variante())
        except Exception:
            data = None
        if data:
            try:
                img = Image.open(BytesIO(data))
            except Exception:
                continue
            if getattr(img, "is_animated", False):
                fr = _gif_en_frames(data, max_frames)
                if fr:
                    return fr, len(fr) > 1
            try:
                return [img.convert("RGB")], False
            except Exception:
                continue
    return [Image.new("RGB", (taille, taille), (40, 42, 50))], False


def _carte_couronne(draw, cx, cy, w, col):
    h = w * 0.8
    x0 = cx - w / 2
    y1 = cy + h / 2
    pts = [(x0, y1), (x0, cy - h / 2), (x0 + w * 0.25, cy), (cx, cy - h * 0.6),
           (x0 + w * 0.75, cy), (x0 + w, cy - h / 2), (x0 + w, y1)]
    draw.polygon(pts, fill=col)


def _carte_etoile(draw, cx, cy, r, fill):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    draw.polygon(pts, fill=fill)


def _carte_medaille(draw, cx, cy, r, col):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    draw.ellipse([cx - r + 3, cy - r + 3, cx + r - 3, cy + r - 3], outline=(255, 255, 255, 170), width=1)


def _carte_cluster_fame(carte, W, vues, rang, rgb):
    """Bloc fame homogene en haut a droite : vues + rang + titre (ou Star du serveur)."""
    draw = ImageDraw.Draw(carte)
    f = _police(22, "SemiBold")
    fb = _police(15, "Bold")
    h, gap, y = 40, 10, 26
    specs = [("eye", str(vues))]
    if rang > 0:
        specs.append(("rank", f"#{rang}"))
    specs.append(("star", "STAR DU SERVEUR") if rang == 1 else ("title", fame_titre(vues).upper()))
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
            _carte_etoile(draw, x + 18, y + h // 2, 9, (20, 20, 20))
            draw.text((x + 34, y + h // 2), txt, font=fb, fill=(20, 20, 20), anchor="lm")
        else:
            layer = Image.new("RGBA", carte.size, (0, 0, 0, 0))
            ImageDraw.Draw(layer).rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=(12, 14, 18, 190))
            carte.alpha_composite(layer)
            draw = ImageDraw.Draw(carte)
            draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, outline=rgb + (255,), width=2)
            if kind == "eye":
                _oeil(draw, int(x + 14 + 12), y + h // 2, 24)
                draw.text((x + 14 + 24 + 9, y + h // 2), txt, font=f, fill=(240, 242, 245), anchor="lm")
            elif kind == "rank":
                _carte_medaille(draw, x + 14 + 9, y + h // 2, 9, rgb)
                draw.text((x + 14 + 18 + 8, y + h // 2), txt, font=f, fill=(255, 255, 255), anchor="lm")
            else:
                draw.text((x + 18, y + h // 2), txt, font=f, fill=rgb + (255,), anchor="lm")
        x += w + gap


async def generer_carte(member, infos, vues=0, rang=0, bio=None, accent=None):
    """Carte de profil premium. Renvoie (buffer, ext) ; ext='gif' si avatar anime, sinon 'png'."""
    score, niveau, _, _ = niveau_rarete(infos)
    rgb = accent or CARTE_COULEURS.get(niveau, (149, 165, 166))
    W = 900
    f_nom = _police(50, "ExtraBold"); f_sur = _police(23, "Medium"); f_id = _police(19, "Medium")
    f_date = _police(20, "Medium"); f_pill = _police(25, "SemiBold"); f_pet = _police(21, "Medium")
    f_chip = _police(22, "SemiBold"); f_bio = _police(23, "Medium")
    blanc, gris = (255, 255, 255, 255), (206, 211, 218, 255)

    frames_av, anime = await _charger_frames_avatar(member, 256)
    avatar0 = frames_av[0]
    perso = fond_membre(member.id)
    banner = None
    try:
        u = await bot.fetch_user(member.id)
        if u and u.banner:
            banner = Image.open(BytesIO(await u.banner.replace(size=600, static_format="png").read())).convert("RGB")
    except Exception:
        pass

    cles = list(infos["badges"]) + list(infos["pseudo"])
    for extra in (infos["anciennete"], infos["boost"]):
        if extra:
            cles.append(extra)
    labels = [SET_ITEMS[k]["label"] for k in cles] or ["Compte standard"]

    mes = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    pad, gap, ch = 20, 12, 40
    x0, maxx = 44, W - 44
    chip_w = [mes.textlength(l, font=f_chip) + pad * 2 for l in labels]
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

    # Fond du corps : perso > global > degrade
    def _fond_image(data):
        return _couvrir(Image.open(BytesIO(data)).convert("RGB"), W, H).convert("RGBA")
    base, custom_bg = None, False
    for src in (perso, FOND_DATA):
        if src:
            try:
                base = _fond_image(src); custom_bg = True; break
            except Exception:
                base = None
    if base is None:
        base = _fond_degrade(W, H, _melange(rgb, (26, 27, 32), 0.80), (13, 14, 17))
    if custom_bg:
        base = Image.alpha_composite(base, Image.new("RGBA", (W, H), (0, 0, 0, 120)))
    draw = ImageDraw.Draw(base)

    # Header en fondu : banniere bien visible en haut, fondue en degrade vers le fond
    Hh = 200
    if banner is not None:
        head = _couvrir(banner, W, Hh).convert("RGBA")
        sombre = 55
    else:
        head = _couvrir(avatar0, W, Hh).filter(ImageFilter.GaussianBlur(16)).convert("RGBA")
        sombre = 95
    head = Image.alpha_composite(head, Image.new("RGBA", (W, Hh), (0, 0, 0, sombre)))
    fade = Image.new("L", (W, Hh), 0)
    fdd = ImageDraw.Draw(fade)
    debut = Hh - 135
    for y in range(Hh):
        a = 255 if y < debut else int(255 * (1 - (y - debut) / 135))
        fdd.line([(0, y), (W, y)], fill=max(0, a))
    base.paste(head, (0, 0), fade)
    draw = ImageDraw.Draw(base)

    # Avatar : lueur + anneau (image posee plus tard, par frame)
    ax, ay, ad, ring = 44, 90, 152, 6
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([ax - ring - 16, ay - ring - 16, ax + ad + ring + 16, ay + ad + ring + 16], fill=rgb + (120,))
    base = Image.alpha_composite(base, glow.filter(ImageFilter.GaussianBlur(18)))
    draw = ImageDraw.Draw(base)
    draw.ellipse([ax - ring, ay - ring, ax + ad + ring, ay + ad + ring], fill=rgb + (255,))

    # Identite
    x = 224
    maxw = W - x - 44
    nm = _ajuster(draw, member.name, f_nom, maxw - 44)
    _ombre(draw, (x, 96), nm, f_nom, blanc, dx=2, dy=3, alpha=185)
    nw = draw.textlength(nm, font=f_nom)
    ex = x + nw + 18
    if niveau in ("Legendaire", "Mythique"):
        _carte_couronne(draw, int(ex + 14), 122, 28, rgb)
    elif niveau in ("Rare", "Epique"):
        _carte_etoile(draw, int(ex + 14), 122, 15, rgb)
    yy = 168
    surnom = member.display_name
    if surnom and surnom != member.name:
        _ombre(draw, (x, yy), f"@{surnom}", f_sur, gris, dx=1, dy=2, alpha=150); yy += 31
    _ombre(draw, (x, yy), f"ID {member.id}", f_id, gris, dx=1, dy=2, alpha=150); yy += 29
    cree = member.created_at.strftime("%d/%m/%Y")
    age = (datetime.datetime.now(datetime.timezone.utc) - member.created_at).days // 365
    j = getattr(member, "joined_at", None)
    if j:
        ligne_dates = f"Créé {cree} ({age} ans)   ·   Arrivé {j.strftime('%m/%Y')}"
    else:
        ligne_dates = f"Créé {cree} ({age} ans)   ·   Hors serveur"
    _ombre(draw, (x, yy), ligne_dates, f_date, gris, dx=1, dy=2, alpha=150)

    # Pastille de niveau
    txt = f"{niveau.upper()}   {score} PTS"
    tw = draw.textlength(txt, font=f_pill)
    pillw = tw + 44
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([x0, y_pillrow + 4, x0 + pillw, y_pillrow + 50], radius=24, fill=(0, 0, 0, 110))
    base = Image.alpha_composite(base, sh.filter(ImageFilter.GaussianBlur(6)))
    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle([x0, y_pillrow, x0 + pillw, y_pillrow + 46], radius=23, fill=rgb + (255,))
    draw.text((x0 + 22, y_pillrow + 23), txt, font=f_pill, fill=(14, 15, 18), anchor="lm")

    if bio:
        draw.text((x0, y_bio), _ajuster(draw, f"\u00ab {bio} \u00bb", f_bio, W - 88), font=f_bio, fill=(226, 228, 233), anchor="lm")

    # Barre de progression (degradee)
    frac, nxt = _progression(score)
    bx, by, bw2, bh = x0, y_prog, W - 88, 22
    draw.rounded_rectangle([bx, by, bx + bw2, by + bh], radius=bh // 2, fill=(255, 255, 255, 40))
    if frac > 0:
        fw = max(bh, int(bw2 * frac))
        grad = _fond_degrade(fw, bh, _melange(rgb, (255, 255, 255), 0.25), rgb)
        gm = Image.new("L", (fw, bh), 0)
        ImageDraw.Draw(gm).rounded_rectangle([0, 0, fw - 1, bh - 1], radius=bh // 2, fill=255)
        base.paste(grad, (bx, by), gm)
        draw = ImageDraw.Draw(base)
    draw.text((bx, by + bh + 12), (f"Plus que {nxt - score} pts pour le palier suivant" if nxt else "Palier maximum atteint"),
              font=f_pet, fill=gris, anchor="lt")

    # Pastilles d'attributs
    cxx, cyy = x0, y_chips
    for l, w in zip(labels, chip_w):
        if cxx + w > maxx and cxx > x0:
            cxx, cyy = x0, cyy + ch + gap
        couche = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(couche).rounded_rectangle([cxx, cyy, cxx + w, cyy + ch], radius=ch // 2, fill=(10, 12, 14, 170))
        base = Image.alpha_composite(base, couche)
        draw = ImageDraw.Draw(base)
        draw.rounded_rectangle([cxx, cyy, cxx + w, cyy + ch], radius=ch // 2, outline=rgb + (255,), width=2)
        draw.text((cxx + pad, cyy + ch // 2), l, font=f_chip, fill=(235, 237, 240), anchor="lm")
        cxx += w + gap

    # Cluster fame (haut-droite, unique)
    _carte_cluster_fame(base, W, vues, rang, rgb)

    # Composition avatar + coins arrondis
    am = Image.new("L", (ad, ad), 0)
    ImageDraw.Draw(am).ellipse([0, 0, ad, ad], fill=255)
    corner = Image.new("L", (W, H), 0)
    ImageDraw.Draw(corner).rounded_rectangle([0, 0, W - 1, H - 1], radius=34, fill=255)

    def _composer(avimg):
        c = base.copy()
        c.paste(_couvrir(avimg, ad, ad).convert("RGBA"), (ax, ay), am)
        return c

    if not anime:
        final = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        final.paste(_composer(avatar0), (0, 0), corner)
        buf = BytesIO()
        final.save(buf, format="PNG")
        buf.seek(0)
        return buf, "png"

    fond = (30, 31, 34)
    imgs = []
    for fr in frames_av:
        plein = Image.new("RGB", (W, H), fond)
        plein.paste(_composer(fr).convert("RGB"), (0, 0), corner)
        imgs.append(plein)
    buf = BytesIO()
    imgs[0].save(buf, format="GIF", save_all=True, append_images=imgs[1:], duration=90, loop=0, optimize=True, disposal=2)
    buf.seek(0)
    return buf, "gif"



# ==============================================================================
#  CARTE TCG HOLOGRAPHIQUE
# ==============================================================================

# Style par palier : couleur, intensite holographique, nombre d'etoiles.
TIERS_TCG = {
    "Commun":     {"c": (150, 160, 170), "holo": 0.0,  "et": 1},
    "Peu commun": {"c": (46, 204, 113),  "holo": 0.0,  "et": 2},
    "Rare":       {"c": (52, 152, 219),  "holo": 0.13, "et": 3},
    "Epique":     {"c": (155, 89, 182),  "holo": 0.22, "et": 4},
    "Legendaire": {"c": (241, 196, 15),  "holo": 0.32, "et": 5},
    "Mythique":   {"c": (231, 76, 60),   "holo": 0.46, "et": 6},
}


def _tcg_degrade(L, H, c1, c2):
    base = Image.new("RGB", (L, H))
    d = ImageDraw.Draw(base)
    for y in range(H):
        d.line([(0, y), (L, y)], fill=_melange(c1, c2, y / max(1, H - 1)))
    return base


def _tcg_rainbow(W, H, sat=0.6, periodes=2.2, decalage=0.0, scale=3):
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
            hh = int((((x + y) / maxd * periodes + decalage) % 1.0) * N) % N
            r, g, b = pal[hh]
            idx = (y * w + x) * 3
            data[idx] = r; data[idx + 1] = g; data[idx + 2] = b
    return Image.frombytes("RGB", (w, h), bytes(data)).resize((W, H))


def _tcg_stries(W, H, uid, larg=60, n=4):
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    rng = random.Random(uid)
    for _ in range(n):
        cx = rng.randint(0, int(W * 1.15))
        val = rng.randint(160, 235)
        d.polygon([(cx - larg, 0), (cx + larg, 0), (cx + larg - H, H), (cx - larg - H, H)], fill=val)
    return m.filter(ImageFilter.GaussianBlur(30))


def _tcg_paillettes(W, H, uid, box, n):
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


def _tcg_etoile(draw, cx, cy, r, fill):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    draw.polygon(pts, fill=fill)


async def generer_carte_tcg(member, infos, vues=0):
    """Genere une carte a collectionner holographique (PNG) -> buffer BytesIO."""
    score, niveau, _, _ = niveau_rarete(infos)
    st = TIERS_TCG.get(niveau, TIERS_TCG["Commun"])
    col = st["c"]
    uid = member.id
    W, H = 744, 1040
    dark = _melange(col, (12, 12, 16), 0.82)
    mid = _melange(col, (20, 20, 26), 0.6)

    # Avatar
    try:
        adata = await member.display_avatar.replace(size=256, static_format="png").read()
        avatar = Image.open(BytesIO(adata)).convert("RGB")
    except Exception:
        avatar = Image.new("RGB", (256, 256), (40, 42, 50))

    # Labels
    cles = list(infos["badges"]) + list(infos["pseudo"])
    for extra in (infos["anciennete"], infos["boost"]):
        if extra:
            cles.append(extra)
    labels = [SET_ITEMS[k]["label"] for k in cles] or ["Compte standard"]

    # Fond + cadre metallique
    carte = _tcg_degrade(W, H, _melange(col, (18, 18, 24), 0.7), (8, 8, 11)).convert("RGBA")
    draw = ImageDraw.Draw(carte)
    frame = _tcg_degrade(W, H, _melange(col, (255, 255, 255), 0.4), _melange(col, (0, 0, 0), 0.5)).convert("RGBA")
    fmask = Image.new("L", (W, H), 0)
    fd = ImageDraw.Draw(fmask)
    fd.rounded_rectangle([6, 6, W - 6, H - 6], radius=42, fill=255)
    fd.rounded_rectangle([30, 30, W - 30, H - 30], radius=32, fill=0)
    carte.paste(frame, (0, 0), fmask)
    draw.rounded_rectangle([30, 30, W - 30, H - 30], radius=32, fill=dark)

    M = 46
    # Plaque nom + gemme score
    draw.rounded_rectangle([M, 46, W - M, 120], radius=20, fill=_melange(mid, (0, 0, 0), 0.2), outline=col, width=2)
    fn = _police(40, "ExtraBold")
    nm = member.name
    while draw.textlength(nm, font=fn) > W - M - 170 and len(nm) > 1:
        nm = nm[:-1]
    if nm != member.name:
        nm = nm[:-1] + "…"
    draw.text((M + 22, 83), nm, font=fn, fill=(255, 255, 255), anchor="lm")
    gx, gy, gr = W - M - 40, 83, 34
    draw.ellipse([gx - gr - 4, gy - gr - 4, gx + gr + 4, gy + gr + 4], fill=_melange(col, (0, 0, 0), 0.4))
    draw.ellipse([gx - gr, gy - gr, gx + gr, gy + gr], fill=col, outline=(255, 255, 255), width=3)
    draw.text((gx, gy), str(score), font=_police(30, "ExtraBold"), fill=(15, 15, 18), anchor="mm")

    # Fenetre illustration
    ax0, ay0, ax1, ay1 = M, 138, W - M, 612
    aw, ah = ax1 - ax0, ay1 - ay0
    art = _couvrir(avatar, aw, ah).convert("RGBA")
    amask = Image.new("L", (aw, ah), 0)
    ImageDraw.Draw(amask).rounded_rectangle([0, 0, aw - 1, ah - 1], radius=18, fill=255)
    carte.paste(art, (ax0, ay0), amask)
    draw = ImageDraw.Draw(carte)
    draw.rounded_rectangle([ax0, ay0, ax1, ay1], radius=18, outline=col, width=3)

    # Ligne de type
    draw.rounded_rectangle([M, 628, W - M, 684], radius=14, fill=_melange(mid, (0, 0, 0), 0.25), outline=col, width=2)
    draw.text((W // 2, 656), niveau.upper(), font=_police(26, "SemiBold"), fill=(255, 255, 255), anchor="mm")

    # Bloc stats
    draw.rounded_rectangle([M, 700, W - M, 958], radius=18, fill=_melange((10, 10, 14), col, 0.06), outline=col, width=2)
    fl = _police(24, "Medium")
    y = 730
    for lab in labels[:7]:
        draw.ellipse([M + 24, y - 6, M + 36, y + 6], fill=col)
        draw.text((M + 50, y), lab, font=fl, fill=(232, 234, 238), anchor="lm")
        y += 33

    # Bas : etoiles / serie / score
    for i in range(st["et"]):
        _tcg_etoile(draw, M + 24 + i * 30, 1000, 11, col)
    draw.text((W // 2, 1000), f"N° {int(str(uid)[-4:]):04d}", font=_police(22, "Medium"), fill=(200, 205, 212), anchor="mm")
    draw.text((W - M - 10, 1000), f"{score} PTS", font=_police(24, "Bold"), fill=col, anchor="rm")

    # --- Holographie ---
    if st["holo"] > 0:
        rb = _tcg_rainbow(W, H, decalage=(uid % 100) / 100).convert("RGB")
        sr = _tcg_stries(W, H, uid)
        frame_reg = Image.new("L", (W, H), 0)
        fr = ImageDraw.Draw(frame_reg)
        fr.rounded_rectangle([6, 6, W - 6, H - 6], radius=42, fill=255)
        fr.rounded_rectangle([30, 30, W - 30, H - 30], radius=32, fill=0)
        art_reg = Image.new("L", (W, H), 0)
        ImageDraw.Draw(art_reg).rounded_rectangle([ax0, ay0, ax1, ay1], radius=18, fill=255)
        mframe = ImageChops.multiply(frame_reg, sr).point(lambda p: int(min(255, p * st["holo"] * 2.6)))
        mart = ImageChops.multiply(art_reg, sr).point(lambda p: int(min(255, p * st["holo"] * 1.35)))
        rgb = carte.convert("RGB")
        rgb = Image.composite(ImageChops.screen(rgb, rb), rgb, mframe)
        rgb = Image.composite(ImageChops.overlay(rgb, rb), rgb, mart)
        carte = rgb.convert("RGBA")
        # Reflet de verre sur l'illustration
        gl = ImageChops.multiply(_tcg_gloss(W, H, (ax0, ay0, ax1, ay1)), art_reg)
        carte = Image.alpha_composite(carte, Image.merge("RGBA", (Image.new("L", (W, H), 255),) * 3 + (gl,)))
        # Paillettes (paliers eleves)
        if st["et"] >= 4:
            pa = _tcg_paillettes(W, H, uid, (ax0, ay0, ax1, ay1), st["et"] * 5)
            pa = Image.composite(pa, Image.new("RGBA", (W, H), (0, 0, 0, 0)), art_reg)
            carte = Image.alpha_composite(carte, pa)

    # Pastille de vues (coin haut-gauche de l'illustration)
    _dessiner_vues(carte, ax0 + 14, ay0 + 14, vues, _police(24, "SemiBold"), hauteur=40)

    # Coins arrondis
    out = Image.new("L", (W, H), 0)
    ImageDraw.Draw(out).rounded_rectangle([0, 0, W - 1, H - 1], radius=44, fill=255)
    final = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    final.paste(carte, (0, 0), out)

    buf = BytesIO()
    final.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ==============================================================================
#  CARTE TCG HOLOGRAPHIQUE ANIMEE (GIF)
# ==============================================================================

# Intensite holo pour l'animation : CHAQUE palier scintille (meme Commun).
HOLO_ANIM = {
    "Commun": 0.10, "Peu commun": 0.14, "Rare": 0.20,
    "Epique": 0.28, "Legendaire": 0.38, "Mythique": 0.52,
}


def _tcg_hue_index(W, H, periodes=2, scale=3):
    """Image L ou chaque pixel = indice de teinte (0-255). Generee une seule fois."""
    w, h = W // scale, H // scale
    data = bytearray(w * h)
    maxd = w + h
    for y in range(h):
        for x in range(w):
            data[y * w + x] = int((((x + y) / maxd * periodes) % 1.0) * 255)
    return Image.frombytes("L", (w, h), bytes(data)).resize((W, H))


def _tcg_palette_rb(shift, sat=0.6):
    pal = []
    for i in range(256):
        r, g, b = colorsys.hsv_to_rgb(((i + shift) % 256) / 256, sat, 1.0)
        pal += [int(r * 255), int(g * 255), int(b * 255)]
    return pal


def _tcg_bandes_anim(W, H, phase, n=2.4, scale=5):
    w, h = W // scale, H // scale
    data = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            v = math.sin(((x - y) / w) * math.pi * 2 * n + phase) * 0.5 + 0.5
            data[y * w + x] = int((v ** 4) * 255)
    return Image.frombytes("L", (w, h), bytes(data)).resize((W, H)).filter(ImageFilter.GaussianBlur(6))


def _tcg_base_anim(member, infos, vues):
    """Construit la carte TCG SANS l'avatar (pose par frame). Renvoie base + masques + overlays."""
    score, niveau, _, _ = niveau_rarete(infos)
    col = TIERS_TCG.get(niveau, TIERS_TCG["Commun"])["c"]
    et = TIERS_TCG.get(niveau, TIERS_TCG["Commun"])["et"]
    uid = member.id
    W, H = 744, 1040
    dark = _melange(col, (12, 12, 16), 0.82)
    mid = _melange(col, (20, 20, 26), 0.6)

    carte = _tcg_degrade(W, H, _melange(col, (18, 18, 24), 0.7), (8, 8, 11)).convert("RGBA")
    draw = ImageDraw.Draw(carte)
    frame = _tcg_degrade(W, H, _melange(col, (255, 255, 255), 0.4), _melange(col, (0, 0, 0), 0.5)).convert("RGBA")
    fmask = Image.new("L", (W, H), 0)
    fd = ImageDraw.Draw(fmask)
    fd.rounded_rectangle([6, 6, W - 6, H - 6], radius=42, fill=255)
    fd.rounded_rectangle([30, 30, W - 30, H - 30], radius=32, fill=0)
    carte.paste(frame, (0, 0), fmask)
    draw.rounded_rectangle([30, 30, W - 30, H - 30], radius=32, fill=dark)

    M = 46
    draw.rounded_rectangle([M, 46, W - M, 120], radius=20, fill=_melange(mid, (0, 0, 0), 0.2), outline=col, width=2)
    fn = _police(40, "ExtraBold")
    nm = member.name
    while draw.textlength(nm, font=fn) > W - M - 170 and len(nm) > 1:
        nm = nm[:-1]
    if nm != member.name:
        nm = nm[:-1] + "…"
    draw.text((M + 22, 83), nm, font=fn, fill=(255, 255, 255), anchor="lm")
    gx, gy, gr = W - M - 40, 83, 34
    draw.ellipse([gx - gr - 4, gy - gr - 4, gx + gr + 4, gy + gr + 4], fill=_melange(col, (0, 0, 0), 0.4))
    draw.ellipse([gx - gr, gy - gr, gx + gr, gy + gr], fill=col, outline=(255, 255, 255), width=3)
    draw.text((gx, gy), str(score), font=_police(30, "ExtraBold"), fill=(15, 15, 18), anchor="mm")

    ax0, ay0, ax1, ay1 = M, 138, W - M, 612
    # fond sombre de la fenetre (au cas ou) + cadre
    draw.rounded_rectangle([ax0, ay0, ax1, ay1], radius=18, fill=_melange(col, (0, 0, 0), 0.55))
    draw.rounded_rectangle([ax0, ay0, ax1, ay1], radius=18, outline=col, width=3)

    draw.rounded_rectangle([M, 628, W - M, 684], radius=14, fill=_melange(mid, (0, 0, 0), 0.25), outline=col, width=2)
    draw.text((W // 2, 656), niveau.upper(), font=_police(26, "SemiBold"), fill=(255, 255, 255), anchor="mm")
    draw.rounded_rectangle([M, 700, W - M, 958], radius=18, fill=_melange((10, 10, 14), col, 0.06), outline=col, width=2)
    fl = _police(24, "Medium")
    y = 730
    cles = list(infos["badges"]) + list(infos["pseudo"])
    for extra in (infos["anciennete"], infos["boost"]):
        if extra:
            cles.append(extra)
    labels = [SET_ITEMS[k]["label"] for k in cles] or ["Compte standard"]
    for lab in labels[:7]:
        draw.ellipse([M + 24, y - 6, M + 36, y + 6], fill=col)
        draw.text((M + 50, y), lab, font=fl, fill=(232, 234, 238), anchor="lm")
        y += 33
    for i in range(et):
        _tcg_etoile(draw, M + 24 + i * 30, 1000, 11, col)
    draw.text((W // 2, 1000), f"N° {int(str(uid)[-4:]):04d}", font=_police(22, "Medium"), fill=(200, 205, 212), anchor="mm")
    draw.text((W - M - 10, 1000), f"{score} PTS", font=_police(24, "Bold"), fill=col, anchor="rm")

    art_box = (ax0, ay0, ax1, ay1)
    art_reg = Image.new("L", (W, H), 0)
    ImageDraw.Draw(art_reg).rounded_rectangle([ax0, ay0, ax1, ay1], radius=18, fill=255)

    # Overlays (gloss + paillettes + pastille vues) -> poses PAR-DESSUS l'avatar a chaque frame
    overlays = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gl = ImageChops.multiply(_tcg_gloss(W, H, art_box), art_reg)
    overlays = Image.alpha_composite(overlays, Image.merge("RGBA", (Image.new("L", (W, H), 255),) * 3 + (gl,)))
    if et >= 4:
        pa = _tcg_paillettes(W, H, uid, art_box, et * 5)
        pa = Image.composite(pa, Image.new("RGBA", (W, H), (0, 0, 0, 0)), art_reg)
        overlays = Image.alpha_composite(overlays, pa)
    _dessiner_vues(overlays, ax0 + 14, ay0 + 14, vues, _police(24, "SemiBold"), hauteur=40)

    frame_reg = Image.new("L", (W, H), 0)
    fr = ImageDraw.Draw(frame_reg)
    fr.rounded_rectangle([6, 6, W - 6, H - 6], radius=42, fill=255)
    fr.rounded_rectangle([30, 30, W - 30, H - 30], radius=32, fill=0)
    return carte.convert("RGB"), frame_reg, art_reg, art_box, overlays, niveau


async def generer_carte_tcg_anim(member, infos, vues=0, frames=16):
    """Carte TCG holographique animee (GIF). L'avatar anime (si GIF) bouge avec l'holo."""
    frames_av, _anime = await _charger_frames_avatar(member, 256)
    n_av = len(frames_av)

    base, frame_reg, art_reg, art_box, overlays, niveau = _tcg_base_anim(member, infos, vues)
    W, H = base.size
    ax0, ay0, ax1, ay1 = art_box
    aw, ah = ax1 - ax0, ay1 - ay0
    amask = Image.new("L", (aw, ah), 0)
    ImageDraw.Draw(amask).rounded_rectangle([0, 0, aw - 1, ah - 1], radius=18, fill=255)

    # pre-decoupe des frames d'avatar a la taille de la fenetre
    av_window = [_couvrir(fr, aw, ah).convert("RGBA") for fr in frames_av]

    inten = HOLO_ANIM.get(niveau, 0.12)
    hue = _tcg_hue_index(W, H)
    corner = Image.new("L", (W, H), 0)
    ImageDraw.Draw(corner).rounded_rectangle([0, 0, W - 1, H - 1], radius=44, fill=255)
    fond = (30, 31, 34)

    imgs = []
    for f in range(frames):
        ph = f / frames
        # avatar (echantillonne sur la duree -> boucle propre)
        av = av_window[int(f * n_av / frames) % n_av]
        canvas = base.convert("RGBA")
        canvas.paste(av, (ax0, ay0), amask)
        canvas = Image.alpha_composite(canvas, overlays)
        rgb = canvas.convert("RGB")
        # holo
        p = hue.copy().convert("P")
        p.putpalette(_tcg_palette_rb(int(ph * 256)))
        rb = p.convert("RGB")
        bd = _tcg_bandes_anim(W, H, ph * 2 * math.pi)
        mframe = ImageChops.multiply(frame_reg, bd).point(lambda v: int(min(255, v * inten * 2.4)))
        mart = ImageChops.multiply(art_reg, bd).point(lambda v: int(min(255, v * inten * 1.3)))
        rgb = Image.composite(ImageChops.screen(rgb, rb), rgb, mframe)
        rgb = Image.composite(ImageChops.overlay(rgb, rb), rgb, mart)
        plein = Image.new("RGB", (W, H), fond)
        plein.paste(rgb, (0, 0), corner)
        imgs.append(plein)

    buf = BytesIO()
    imgs[0].save(buf, format="GIF", save_all=True, append_images=imgs[1:],
                 duration=80, loop=0, optimize=True, disposal=2)
    buf.seek(0)
    return buf



# ==============================================================================
#  VUES
# ==============================================================================

class AuthorView(discord.ui.View):
    def __init__(self, author, guild, timeout=180):
        super().__init__(timeout=timeout)
        self.author = author
        self.guild = guild

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Ce menu n'est pas pour toi 🙂", ephemeral=True)
            return False
        return True


def valeur_affichee(guild, key):
    rid = CONFIG.get(key, 0)
    if not rid:
        return "*non defini*"
    if SET_ITEMS[key]["type"] == "channel":
        ch = guild.get_channel(rid)
        return ch.mention if ch else "*introuvable*"
    role = guild.get_role(rid)
    return role.mention if role else "*introuvable*"


def embed_config(guild):
    embed = discord.Embed(title="⚙️ Configuration",
                          description="Choisis une categorie, puis l'element a regler.",
                          color=discord.Color.blurple())
    for cat, keys in CATEGORIES.items():
        lignes = []
        for k in keys:
            pref = emoji_de(k) + " " if k in DEFAULT_EMOJIS else ""
            lignes.append(f"{pref}**{SET_ITEMS[k]['label']}** → {valeur_affichee(guild, k)}")
        embed.add_field(name=cat, value="\n".join(lignes), inline=False)
    return embed


def embed_config_accueil():
    e = discord.Embed(title="⚙️ Configuration",
                      description="Choisis la categorie a configurer dans le menu ci-dessous.",
                      color=discord.Color.blurple())
    e.add_field(name="Categories", value="\n".join(f"• {c}" for c in CATEGORIES), inline=False)
    return e


def embed_config_cat(guild, cat):
    e = discord.Embed(title=f"⚙️ {cat}",
                      description="Choisis l'element a definir ci-dessous.",
                      color=discord.Color.blurple())
    lignes = []
    for k in CATEGORIES[cat]:
        pref = emoji_de(k) + " " if k in DEFAULT_EMOJIS else ""
        lignes.append(f"{pref}**{SET_ITEMS[k]['label']}** → {valeur_affichee(guild, k)}")
    e.add_field(name="Etat actuel", value="\n".join(lignes), inline=False)
    return e


# --- !set : categorie -> element -> role/salon ---

class SetCategorySelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Choisis une categorie…",
                         options=[discord.SelectOption(label=c, value=c) for c in CATEGORIES])

    async def callback(self, interaction):
        await interaction.response.edit_message(
            embed=embed_config_cat(self.view.guild, self.values[0]),
            view=SetItemView(self.view.author, self.view.guild, self.values[0]))


class ConfigView(AuthorView):
    def __init__(self, author, guild):
        super().__init__(author, guild)
        self.add_item(SetCategorySelect())


class SetItemSelect(discord.ui.Select):
    def __init__(self, cat):
        super().__init__(placeholder=f"{cat} — choisis l'element…",
                         options=[discord.SelectOption(label=SET_ITEMS[k]["label"], value=k)
                                  for k in CATEGORIES[cat]])

    async def callback(self, interaction):
        key = self.values[0]
        it = SET_ITEMS[key]
        if it["type"] == "channel":
            view = ChannelPickView(self.view.author, self.view.guild, key)
            desc = "Choisis le salon (tape pour rechercher)."
        else:
            view = RolePickView(self.view.author, self.view.guild, key)
            desc = "Choisis le role (tape pour rechercher)."
        embed = discord.Embed(title=f"Configurer : {it['label']}", description=desc, color=discord.Color.blurple())
        await interaction.response.edit_message(embed=embed, view=view)


class RetourConfig(discord.ui.Button):
    def __init__(self):
        super().__init__(label="◀ Retour", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction):
        await interaction.response.edit_message(embed=embed_config_accueil(),
                                                view=ConfigView(self.view.author, self.view.guild))


class SetItemView(AuthorView):
    def __init__(self, author, guild, cat):
        super().__init__(author, guild)
        self.add_item(SetItemSelect(cat))
        self.add_item(RetourConfig())


class RolePicker(discord.ui.RoleSelect):
    def __init__(self, key):
        self.key = key
        super().__init__(placeholder="Recherche un role…", min_values=1, max_values=1)

    async def callback(self, interaction):
        role = self.values[0]
        definir_config(self.key, role.id)
        await interaction.response.edit_message(
            embed=discord.Embed(title="✅ Effectue",
                                description=f"**{SET_ITEMS[self.key]['label']}** → {role.mention}",
                                color=discord.Color.green()),
            view=RetourView(self.view.author, self.view.guild))


class RolePickView(AuthorView):
    def __init__(self, author, guild, key):
        super().__init__(author, guild)
        self.add_item(RolePicker(key))
        self.add_item(RetourConfig())


class ChannelPicker(discord.ui.ChannelSelect):
    def __init__(self, key):
        self.key = key
        super().__init__(placeholder="Recherche un salon…",
                         channel_types=[discord.ChannelType.text], min_values=1, max_values=1)

    async def callback(self, interaction):
        salon = self.values[0]
        definir_config(self.key, salon.id)
        await interaction.response.edit_message(
            embed=discord.Embed(title="✅ Effectue",
                                description=f"**{SET_ITEMS[self.key]['label']}** → {salon.mention}",
                                color=discord.Color.green()),
            view=RetourView(self.view.author, self.view.guild))


class ChannelPickView(AuthorView):
    def __init__(self, author, guild, key):
        super().__init__(author, guild)
        self.add_item(ChannelPicker(key))
        self.add_item(RetourConfig())


class RetourView(AuthorView):
    def __init__(self, author, guild):
        super().__init__(author, guild)
        self.add_item(RetourConfig())


# --- Pagination generique (list + top) ---

class PrevButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="◀ Precedent", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction):
        await self.view.changer_page(interaction, -1)


class NextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Suivant ▶", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction):
        await self.view.changer_page(interaction, +1)


class PageView(AuthorView):
    PAR_PAGE = 10

    def __init__(self, author, guild, titre, lignes, couleur=None):
        super().__init__(author, guild)
        self.titre = titre
        self.lignes = lignes
        self.couleur = couleur or discord.Color.blurple()
        self.page = 0
        self.total_pages = max(1, (len(lignes) + self.PAR_PAGE - 1) // self.PAR_PAGE)
        self.prev = PrevButton(); self.next = NextButton()
        self.add_item(self.prev); self.add_item(self.next)
        self._maj()

    def _maj(self):
        self.prev.disabled = self.page == 0
        self.next.disabled = self.page >= self.total_pages - 1

    def embed_courant(self):
        debut = self.page * self.PAR_PAGE
        lot = self.lignes[debut:debut + self.PAR_PAGE]
        embed = discord.Embed(title=self.titre, description="\n".join(lot) or "Vide.", color=self.couleur)
        embed.set_footer(text=f"Page {self.page + 1}/{self.total_pages} — {len(self.lignes)} au total")
        return embed

    async def changer_page(self, interaction, delta):
        self.page = max(0, min(self.total_pages - 1, self.page + delta))
        self._maj()
        await interaction.response.edit_message(embed=self.embed_courant(), view=self)


# --- !scan : categorie -> element -> resultat ---

SCAN_CATEGORIES = {c: [k for k in keys if k in DETECT_KEYS]
                   for c, keys in CATEGORIES.items()
                   if any(k in DETECT_KEYS for k in keys)}


class ScanCategorySelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Choisis une categorie a scanner…",
                         options=[discord.SelectOption(label=c, value=c) for c in SCAN_CATEGORIES])

    async def callback(self, interaction):
        await interaction.response.edit_message(
            embed=embed_scan_accueil(),
            view=ScanItemView(self.view.author, self.view.guild, self.values[0]))


class ScanItemSelect(discord.ui.Select):
    def __init__(self, cat):
        super().__init__(placeholder=f"{cat} — choisis le critere…",
                         options=[discord.SelectOption(label=SET_ITEMS[k]["label"], value=k)
                                  for k in SCAN_CATEGORIES[cat]])

    async def callback(self, interaction):
        key = self.values[0]
        membres = membres_avec(self.view.guild, key)
        if not membres:
            await interaction.response.edit_message(
                embed=discord.Embed(description=f"Personne pour **{SET_ITEMS[key]['label']}**.",
                                    color=discord.Color.orange()),
                view=ScanView(self.view.author, self.view.guild))
            return
        lignes = [f"{m.mention} / `{m.id}`" for m in membres]
        titre = f"{emoji_de(key)} {SET_ITEMS[key]['label']}"
        vue_liste = PageView(self.view.author, self.view.guild, titre, lignes)
        salon = self.view.guild.get_channel(CONFIG.get("scanlog", 0))
        if salon:
            await salon.send(embed=vue_liste.embed_courant(), view=vue_liste if vue_liste.total_pages > 1 else None)
            await interaction.response.edit_message(
                embed=discord.Embed(description=f"✅ {len(membres)} resultat(s) envoye(s) dans {salon.mention}.",
                                    color=discord.Color.green()),
                view=ScanView(self.view.author, self.view.guild))
        else:
            await interaction.response.edit_message(
                embed=vue_liste.embed_courant(), view=vue_liste if vue_liste.total_pages > 1 else None)


class ScanView(AuthorView):
    def __init__(self, author, guild):
        super().__init__(author, guild)
        self.add_item(ScanCategorySelect())


class ScanItemView(AuthorView):
    def __init__(self, author, guild, cat):
        super().__init__(author, guild)
        self.add_item(ScanItemSelect(cat))


def embed_scan_accueil():
    return discord.Embed(title="🔍 Scan par categorie",
                         description="Choisis une categorie puis un critere. Le resultat va dans le salon de scan.",
                         color=discord.Color.blurple())


# --- !help ---

HELP_CATEGORIES = {
    "🔍 Detection": [
        ("!scan", "Lister les membres d'un critere (vers le salon de scan)."),
        ("!profil @membre", "Profil complet d'un membre."),
        ("!carte @membre", "Carte de profil premium (image, ou GIF si avatar anime)."),
        ("!tcg @membre", "Carte a collectionner holographique ANIMEE (GIF)."),
        ("!list", "Liste des membres d'un critere (menu deroulant)."),
        ("!stats", "Tableau de bord global du serveur."),
        ("!top", "Classement des comptes les plus rares."),
        ("!fame", "Classement des profils les plus vus (vues uniques)."),
        ("!bareme", "Bareme de rarete (menu par categorie)."),
    ],
    "🎨 Personnalisation": [
        ("!carte → Modifier", "Sous ta propre carte, le bouton Modifier change couleur / fond / description."),
    ],
    "⚙️ Configuration": [
        ("!set", "Panneau interactif (roles, salons, alertes)."),
        ("!config", "Affiche la configuration."),
        ("!setlog #salon", "Salon des joins."),
        ("!setscan #salon", "Salon des scans."),
        ("!setemoji", "Gerer les emojis des criteres (menu)."),
        ("!create <emojis>", "Cree des emojis sur le serveur (depuis d'autres serveurs)."),
        ("!setmsg <texte>", "Titre du message de join."),
        ("!setfond <url|image>", "Fond personnalise des cartes (`reset` pour enlever)."),
    ],
    "👑 Gestion": [
        ("!owner @membre", "Ajoute un owner (buyer)."),
        ("!unowner @membre", "Retire un owner (buyer)."),
        ("!owners", "Buyer + owners."),
    ],
    "🛠️ Moderation": [
        ("!ban <@/id> [raison]", "Bannit (par ID, marche meme si la personne n'est pas sur le serveur)."),
        ("!unban <id> [raison]", "Debannit par ID (ou pseudo exact d'un banni)."),
        ("!mute <@/id> [raison]", "Mute permanent (s'applique a l'arrivee si la personne est absente)."),
        ("!tempmute <@/id> <duree> [raison]", "Mute temporaire (30s, 10m, 2h, 1j, 1sem, ou 1h30m)."),
        ("!unmute <@/id>", "Retire le mute (permanent ou temporaire)."),
        ("!mutes", "Liste des personnes actuellement mute."),
        ("!setmute [@role]", "Definit (ou cree) le role de mute."),
        ("!nuke", "Supprime et recree le salon a l'identique (renew)."),
        ("!clear [n|@membre]", "Purge : 100 derniers, un nombre (1-100), ou les messages d'un membre."),
        ("!allow [#salon]", "Ouvre un salon aux commandes publiques."),
        ("!unallow [#salon]", "Referme un salon (owners seulement)."),
    ],
}


def embed_help_accueil():
    e = discord.Embed(title="📖 Aide du bot",
                      description="Detecte les comptes rares et attribue des roles.\nChoisis une categorie ci-dessous.",
                      color=discord.Color.blurple())
    e.add_field(name="Categories", value="\n".join(f"• {c}" for c in HELP_CATEGORIES), inline=False)
    return e


def embed_help_categorie(cat):
    e = discord.Embed(title=f"📖 Aide — {cat}", color=discord.Color.blurple())
    for nom, desc in HELP_CATEGORIES[cat]:
        e.add_field(name=nom, value=desc, inline=False)
    return e


class HelpSelect(discord.ui.Select):
    def __init__(self):
        opts = [discord.SelectOption(label="Accueil", value="accueil", emoji="🏠")]
        opts += [discord.SelectOption(label=c, value=c) for c in HELP_CATEGORIES]
        super().__init__(placeholder="Choisis une categorie…", options=opts)

    async def callback(self, interaction):
        v = self.values[0]
        embed = embed_help_accueil() if v == "accueil" else embed_help_categorie(v)
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(AuthorView):
    def __init__(self, author, guild):
        super().__init__(author, guild)
        self.add_item(HelpSelect())


# --- !list : categorie -> critere -> liste paginee ---

def embed_list_accueil():
    return discord.Embed(title="📋 Liste par critere",
                         description="Choisis une categorie puis un critere pour lister les membres.",
                         color=discord.Color.blurple())


class ListCategorySelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Choisis une categorie…",
                         options=[discord.SelectOption(label=c, value=c) for c in SCAN_CATEGORIES])

    async def callback(self, interaction):
        await interaction.response.edit_message(
            embed=embed_list_accueil(),
            view=ListItemView(self.view.author, self.view.guild, self.values[0]))


class ListItemSelect(discord.ui.Select):
    def __init__(self, cat):
        super().__init__(placeholder=f"{cat} — choisis le critere…",
                         options=[discord.SelectOption(label=SET_ITEMS[k]["label"], value=k)
                                  for k in SCAN_CATEGORIES[cat]])

    async def callback(self, interaction):
        key = self.values[0]
        membres = membres_avec(self.view.guild, key)
        if not membres:
            await interaction.response.edit_message(
                embed=discord.Embed(description=f"Personne pour **{SET_ITEMS[key]['label']}**.",
                                    color=discord.Color.orange()),
                view=ListRootView(self.view.author, self.view.guild))
            return
        lignes = [f"{m.mention} / `{m.id}`" for m in membres]
        vue = PageView(self.view.author, self.view.guild, f"{emoji_de(key)} {SET_ITEMS[key]['label']}", lignes)
        await interaction.response.edit_message(embed=vue.embed_courant(),
                                                view=vue if vue.total_pages > 1 else None)


class ListRootView(AuthorView):
    def __init__(self, author, guild):
        super().__init__(author, guild)
        self.add_item(ListCategorySelect())


class ListItemView(AuthorView):
    def __init__(self, author, guild, cat):
        super().__init__(author, guild)
        self.add_item(ListItemSelect(cat))


# --- !bareme : par categorie ---

BAREME_CATS = ["🏅 Badges", "🚀 Boost", "📅 Anciennete", "✨ Pseudo"]


def embed_bareme_accueil():
    e = discord.Embed(title="📐 Bareme de rarete",
                      description="Choisis une categorie pour voir les points.",
                      color=discord.Color.blurple())
    e.add_field(name="Niveaux (score minimum)",
                value="\n".join(f"{e} {n} : {s}+ pts" for s, n, e, _ in NIVEAUX), inline=False)
    return e


def embed_bareme_cat(cat):
    lignes = [f"{SET_ITEMS[k]['label']} : **{POIDS[k]}**" for k in CATEGORIES[cat] if k in POIDS]
    return discord.Embed(title=f"📐 Bareme — {cat}", description="\n".join(lignes),
                         color=discord.Color.blurple())


class BaremeSelect(discord.ui.Select):
    def __init__(self):
        opts = [discord.SelectOption(label="Accueil (niveaux)", value="accueil", emoji="🏠")]
        opts += [discord.SelectOption(label=c, value=c) for c in BAREME_CATS]
        super().__init__(placeholder="Choisis une categorie…", options=opts)

    async def callback(self, interaction):
        v = self.values[0]
        embed = embed_bareme_accueil() if v == "accueil" else embed_bareme_cat(v)
        await interaction.response.edit_message(embed=embed, view=self.view)


class BaremeView(AuthorView):
    def __init__(self, author, guild):
        super().__init__(author, guild)
        self.add_item(BaremeSelect())


# --- !setemoji : categorie -> element -> fenetre (modal) ---

EMOJI_CATEGORIES = {c: [k for k in keys if k in DEFAULT_EMOJIS]
                    for c, keys in CATEGORIES.items() if any(k in DEFAULT_EMOJIS for k in keys)}


def embed_emoji_accueil():
    return discord.Embed(title="😀 Emojis des criteres",
                         description="Choisis une categorie, puis l'element dont tu veux changer l'emoji.",
                         color=discord.Color.blurple())


def embed_emoji_cat(cat):
    e = discord.Embed(title=f"😀 Emojis — {cat}", description="Choisis l'element a modifier.",
                      color=discord.Color.blurple())
    lignes = [f"{emoji_de(k)} {SET_ITEMS[k]['label']}" for k in EMOJI_CATEGORIES[cat]]
    e.add_field(name="Emojis actuels", value="\n".join(lignes), inline=False)
    return e


def embed_emoji_item(key):
    e = discord.Embed(title=f"😀 {SET_ITEMS[key]['label']}", color=discord.Color.blurple())
    e.add_field(name="Emoji actuel", value=emoji_de(key), inline=False)
    e.set_footer(text="Clique sur Modifier pour le changer.")
    return e


class EmojiModal(discord.ui.Modal):
    def __init__(self, author, guild, key):
        super().__init__(title="Definir l'emoji")
        self.author = author
        self.guild = guild
        self.key = key
        self.champ = discord.ui.TextInput(label=SET_ITEMS[key]["label"][:45],
                                          placeholder="Colle ton emoji ici", max_length=100)
        self.add_item(self.champ)

    async def on_submit(self, interaction):
        definir_emoji(self.key, str(self.champ.value).strip())
        await interaction.response.edit_message(
            embed=embed_emoji_item(self.key),
            view=EmojiItemActionsView(self.author, self.guild, self.key))


class ModifierEmojiBouton(discord.ui.Button):
    def __init__(self, key):
        super().__init__(label="✏️ Modifier", style=discord.ButtonStyle.primary)
        self.key = key

    async def callback(self, interaction):
        await interaction.response.send_modal(EmojiModal(self.view.author, self.view.guild, self.key))


class RetourEmojiBouton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="◀ Retour", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction):
        await interaction.response.edit_message(embed=embed_emoji_accueil(),
                                                view=EmojiRootView(self.view.author, self.view.guild))


class EmojiItemActionsView(AuthorView):
    def __init__(self, author, guild, key):
        super().__init__(author, guild)
        self.add_item(ModifierEmojiBouton(key))
        self.add_item(RetourEmojiBouton())


class EmojiCategorySelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Choisis une categorie…",
                         options=[discord.SelectOption(label=c, value=c) for c in EMOJI_CATEGORIES])

    async def callback(self, interaction):
        cat = self.values[0]
        await interaction.response.edit_message(embed=embed_emoji_cat(cat),
                                                view=EmojiItemView(self.view.author, self.view.guild, cat))


class EmojiItemSelect(discord.ui.Select):
    def __init__(self, cat):
        super().__init__(placeholder=f"{cat} — choisis l'element…",
                         options=[discord.SelectOption(label=SET_ITEMS[k]["label"], value=k)
                                  for k in EMOJI_CATEGORIES[cat]])

    async def callback(self, interaction):
        key = self.values[0]
        await interaction.response.edit_message(embed=embed_emoji_item(key),
                                                view=EmojiItemActionsView(self.view.author, self.view.guild, key))


class EmojiRootView(AuthorView):
    def __init__(self, author, guild):
        super().__init__(author, guild)
        self.add_item(EmojiCategorySelect())


class EmojiItemView(AuthorView):
    def __init__(self, author, guild, cat):
        super().__init__(author, guild)
        self.add_item(EmojiItemSelect(cat))
        self.add_item(RetourEmojiBouton())


# ==============================================================================
#  MODERATION : OUTILS (ban / mute / tempmute)
# ==============================================================================

def _now_ts():
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp())


def parse_duree(s):
    """'30s' '10m' '2h' '1j' '1sem' ou combine '1h30m'. Un nombre seul = minutes. -> secondes ou None."""
    if not s:
        return None
    s = s.strip().lower()
    if s.isdigit():
        return int(s) * 60
    unites = {"sem": 604800, "w": 604800, "j": 86400, "d": 86400, "h": 3600, "m": 60, "s": 1}
    total = 0
    for n, u in re.findall(r"(\d+)\s*(sem|w|j|d|h|m|s)", s):
        total += int(n) * unites[u]
    return total or None


def format_duree(sec):
    sec = int(sec)
    if sec <= 0:
        return "0s"
    parts = []
    for nom, val in (("j", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if sec >= val:
            q, sec = divmod(sec, val)
            parts.append(f"{q}{nom}")
    return " ".join(parts)


def extraire_id(ref):
    """Renvoie l'ID depuis une mention <@123> ou un ID brut, sinon None."""
    if ref is None:
        return None
    s = str(ref).strip()
    m = re.match(r"^<@!?(\d+)>$", s)
    if m:
        return int(m.group(1))
    if s.isdigit():
        return int(s)
    return None


async def resoudre_id_ou_user(ctx, ref):
    """Renvoie (uid, member_ou_user_ou_None). L'uid peut etre valide meme si la personne
    n'est pas sur le serveur (resolu via fetch_user). Accepte mention / ID / pseudo (membres)."""
    uid = extraire_id(ref)
    if uid is not None:
        membre = ctx.guild.get_member(uid) if ctx.guild else None
        if membre:
            return uid, membre
        try:
            return uid, await bot.fetch_user(uid)
        except Exception:
            return uid, None
    membre = await resoudre_cible(ctx, ref)
    if membre:
        return membre.id, membre
    return None, None


async def obtenir_role_mute(guild):
    """Recupere le role de mute configure, sinon le cree (et coupe la parole partout)."""
    rid = CONFIG.get("muterole", 0)
    role = guild.get_role(rid) if rid else None
    if role:
        return role
    role = discord.utils.get(guild.roles, name="Muted")
    if role is None:
        try:
            role = await guild.create_role(name="Muted", colour=discord.Color.dark_grey(),
                                           reason="Role de mute (auto)")
        except discord.Forbidden:
            return None
        for ch in guild.channels:
            try:
                await ch.set_permissions(role, send_messages=False, add_reactions=False, speak=False,
                                         create_public_threads=False, create_private_threads=False,
                                         send_messages_in_threads=False)
            except Exception:
                pass
    definir_config("muterole", role.id)
    return role


_taches_unmute = {}


def _annuler_tache(gid, uid):
    t = _taches_unmute.pop((gid, uid), None)
    if t and not t.done():
        t.cancel()


async def _appliquer_mute(member, until):
    """Pose le role Muted. Si tempmute <= 28j, ajoute aussi le timeout natif Discord."""
    role = await obtenir_role_mute(member.guild)
    if role and role not in member.roles:
        try:
            await member.add_roles(role, reason="Mute")
        except discord.HTTPException:
            pass
    if until:
        restant = until - _now_ts()
        if 0 < restant <= 28 * 86400:
            try:
                fin = datetime.datetime.fromtimestamp(until, datetime.timezone.utc)
                await member.timeout(fin, reason="Tempmute")
            except Exception:
                pass


async def _retirer_mute(guild, uid):
    db_retirer_mute(guild.id, uid)
    _annuler_tache(guild.id, uid)
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


def _planifier_unmute(guild_id, uid, until):
    _annuler_tache(guild_id, uid)

    async def _job():
        try:
            await asyncio.sleep(max(0, until - _now_ts()))
            guild = bot.get_guild(guild_id)
            if guild:
                await _retirer_mute(guild, uid)
            else:
                db_retirer_mute(guild_id, uid)
        except asyncio.CancelledError:
            pass

    _taches_unmute[(guild_id, uid)] = bot.loop.create_task(_job())


# ==============================================================================
#  COMMANDES
# ==============================================================================

@bot.command(name="set")
@check_owner()
async def set_config(ctx):
    await ctx.send(embed=embed_config_accueil(), view=ConfigView(ctx.author, ctx.guild))


@bot.command(name="config")
@check_owner()
async def afficher_config(ctx):
    await ctx.send(embed=embed_config(ctx.guild))


@bot.command(name="setlog")
@check_owner()
async def setlog(ctx, salon: discord.TextChannel = None):
    salon = salon or ctx.channel
    definir_config("logs", salon.id)
    await ctx.send(f"✅ Salon de logs (joins) : {salon.mention}")


@bot.command(name="setscan")
@check_owner()
async def setscan(ctx, salon: discord.TextChannel = None):
    salon = salon or ctx.channel
    definir_config("scanlog", salon.id)
    await ctx.send(f"✅ Salon de scan : {salon.mention}")


@bot.command(name="setalert")
@check_owner()
async def setalert(ctx, role: discord.Role):
    definir_config("alertrole", role.id)
    await ctx.send(f"✅ Role ping lors d'un compte exceptionnel : {role.mention}")


@bot.command(name="setemoji")
@check_owner()
async def setemoji(ctx):
    await ctx.send(embed=embed_emoji_accueil(), view=EmojiRootView(ctx.author, ctx.guild))


@bot.command(name="create")
@check_owner()
async def create(ctx, emojis: commands.Greedy[discord.PartialEmoji]):
    """Cree un ou plusieurs emojis sur le serveur depuis d'autres serveurs.
    Ex: !create <:foo:123> <:bar:456> ..."""
    if not emojis:
        await ctx.send("Utilisation : `!create <emoji1> <emoji2> ...` "
                       "(des emojis personnalises d'autres serveurs).")
        return
    crees, echecs = [], []
    for em in emojis:
        if not em.id:  # emoji standard (unicode) -> non creable
            echecs.append(f"{em} (emoji standard)")
            continue
        try:
            data = await em.read()
            nouvel = await ctx.guild.create_custom_emoji(
                name=em.name, image=data, reason=f"!create par {ctx.author}")
            crees.append(str(nouvel))
        except discord.Forbidden:
            echecs.append(f"`{em.name}` (permission 'Gerer les emojis' manquante)")
        except discord.HTTPException as e:
            echecs.append(f"`{em.name}` ({getattr(e, 'text', 'erreur / limite atteinte')})")
    embed = discord.Embed(title="✨ Creation d'emojis", color=discord.Color.green())
    if crees:
        embed.add_field(name=f"✅ Crees ({len(crees)})", value=" ".join(crees)[:1024], inline=False)
    if echecs:
        embed.add_field(name=f"❌ Echecs ({len(echecs)})", value="\n".join(echecs)[:1024], inline=False)
    await ctx.send(embed=embed)


@bot.command(name="setmsg")
@check_owner()
async def setmsg(ctx, *, texte: str = None):
    if not texte:
        await ctx.send("Utilisation : `!setmsg <texte>`"); return
    definir_message("join", texte)
    await ctx.send(f"✅ Titre de join : {texte}")


@bot.command(name="setfond", aliases=["setbg", "setbackground"])
@check_owner()
async def setfond(ctx, url: str = None):
    """Definit le fond des cartes. Joins une image OU donne une URL. `!setfond reset` pour enlever."""
    if not PIL_OK:
        await ctx.send("Pillow n'est pas installe."); return

    if url and url.lower() in ("reset", "clear", "off", "none"):
        definir_fond(None)
        await ctx.send("✅ Fond personnalise retire. Les cartes reprennent le fond par defaut.")
        return

    if ctx.message.attachments:
        url = ctx.message.attachments[0].url
    if not url:
        await ctx.send("Donne une image : `!setfond <url>` ou **joins une image** au message.\n"
                       "Pour enlever : `!setfond reset`.")
        return

    async with ctx.typing():
        data = await _telecharger(url)
        if not data:
            await ctx.send("❌ Impossible de telecharger cette image (lien invalide ou expire ?)."); return
        try:
            img = Image.open(BytesIO(data)).convert("RGB")
        except Exception:
            await ctx.send("❌ Ce fichier n'est pas une image valide."); return
        # Re-encode en taille bornee pour garder la base legere (et eviter les liens qui expirent)
        img = _couvrir(img, 900, 520)
        buf = BytesIO(); img.save(buf, format="JPEG", quality=85)
        definir_fond(buf.getvalue())

    apercu = discord.File(BytesIO(buf.getvalue()), filename="fond.jpg")
    await ctx.send("✅ Fond de carte enregistre ! Voici l'apercu (utilise `!carte` pour voir le rendu final) :",
                   file=apercu)


@bot.command(name="scan")
@check_owner()
async def scan(ctx):
    await ctx.send(embed=embed_scan_accueil(), view=ScanView(ctx.author, ctx.guild))


def comptabiliser_vue(viewer, cible):
    """Enregistre une vue unique (viewer -> cible) sauf auto-vue/bot. Renvoie le total."""
    if cible.bot:
        return compter_vues(cible.id)
    if viewer.id == cible.id:
        return compter_vues(cible.id)
    return enregistrer_vue(cible.id, viewer.id)


def embed_fame(guild):
    compte = vues_par_profil()
    classement = []
    for m in guild.members:
        if m.bot:
            continue
        v = compte.get(m.id, 0)
        if v > 0:
            classement.append((v, m))
    classement.sort(key=lambda x: x[0], reverse=True)
    medailles = {1: "🥇", 2: "🥈", 3: "🥉"}
    if not classement:
        return discord.Embed(title="🏆 Classement Fame",
                             description="Personne n'a encore de vues. Faites `!carte @membre` !",
                             color=discord.Color.gold())
    lignes = [f"{medailles.get(i, f'**{i}.**')} {m.mention} — 👁 {v} vue(s)"
              for i, (v, m) in enumerate(classement[:20], 1)]
    return discord.Embed(title="🏆 Classement Fame", description="\n".join(lignes), color=discord.Color.gold())


class CouleurModal(discord.ui.Modal, title="Couleur d'accent"):
    valeur = discord.ui.TextInput(label="Couleur hex", placeholder="#9B59B6   (ou « rien » pour enlever)",
                                  required=False, max_length=7)

    def __init__(self, uid):
        super().__init__()
        self.uid = uid

    async def on_submit(self, interaction: discord.Interaction):
        v = str(self.valeur).strip()
        if not v or v.lower() == "rien":
            definir_couleur(self.uid, None)
            await interaction.response.send_message("🗑️ Couleur retiree (retour a la couleur de rarete).", ephemeral=True)
            return
        h = v.lstrip("#")
        if len(h) != 6 or any(c not in "0123456789abcdefABCDEF" for c in h):
            await interaction.response.send_message("❌ Couleur invalide. Exemple : #9B59B6", ephemeral=True)
            return
        definir_couleur(self.uid, "#" + h.upper())
        await interaction.response.send_message(f"✅ Couleur enregistree : #{h.upper()}. Refais `!carte`.", ephemeral=True)


class BioModal(discord.ui.Modal, title="Description"):
    valeur = discord.ui.TextInput(label="Ta description", style=discord.TextStyle.paragraph,
                                  placeholder="Ecris ta phrase (ou « rien » pour enlever)", required=False, max_length=120)

    def __init__(self, uid):
        super().__init__()
        self.uid = uid

    async def on_submit(self, interaction: discord.Interaction):
        v = str(self.valeur).strip()
        if not v or v.lower() == "rien":
            definir_bio(self.uid, None)
            await interaction.response.send_message("🗑️ Description retiree.", ephemeral=True)
            return
        definir_bio(self.uid, " ".join(v.split())[:120])
        await interaction.response.send_message("✅ Description enregistree. Refais `!carte`.", ephemeral=True)


class ModifierActionsView(discord.ui.View):
    """Menu ephemere : choisir quoi modifier sur sa carte."""
    def __init__(self, uid):
        super().__init__(timeout=180)
        self.uid = uid

    @discord.ui.button(label="Couleur", emoji="🎨", style=discord.ButtonStyle.secondary)
    async def b_couleur(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CouleurModal(self.uid))

    @discord.ui.button(label="Description", emoji="📝", style=discord.ButtonStyle.secondary)
    async def b_desc(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BioModal(self.uid))

    @discord.ui.button(label="Fond", emoji="🖼️", style=discord.ButtonStyle.secondary)
    async def b_fond(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not PIL_OK:
            await interaction.response.send_message("Pillow n'est pas installe.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Envoie ton **image de fond** ici (en piece jointe), ou ecris **rien** pour annuler.\n"
            "_Ton message sera supprime aussitot pour que personne ne le voie._", ephemeral=True)

        def check(m):
            return m.author.id == self.uid and m.channel.id == interaction.channel.id

        try:
            msg = await bot.wait_for("message", check=check, timeout=120)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏱️ Temps ecoule, fond non modifie.", ephemeral=True)
            return

        contenu = (msg.content or "").strip().lower()
        data = await _telecharger(msg.attachments[0].url) if msg.attachments else None
        try:
            await msg.delete()
            supprime = True
        except Exception:
            supprime = False

        if contenu == "rien":
            await interaction.followup.send("Annule." + ("" if supprime else " (je n'ai pas pu supprimer ton message)"), ephemeral=True)
            return
        if not data:
            await interaction.followup.send("❌ Aucune image valide trouvee. Reessaie via Modifier.", ephemeral=True)
            return
        try:
            img = Image.open(BytesIO(data)).convert("RGB")
            img = _couvrir(img, 900, 560)
            buf = BytesIO(); img.save(buf, format="JPEG", quality=85)
            definir_fond_membre(self.uid, buf.getvalue())
        except Exception:
            await interaction.followup.send("❌ Ce fichier n'est pas une image valide.", ephemeral=True)
            return
        rep = "✅ Fond enregistre ! Refais `!carte`."
        if not supprime:
            rep += "\n⚠️ Je n'ai pas pu supprimer ton message (permission « Gerer les messages » manquante)."
        await interaction.followup.send(rep, ephemeral=True)


class CarteModifierView(discord.ui.View):
    """Bouton 'Modifier' sous sa propre carte."""
    def __init__(self, owner_id):
        super().__init__(timeout=600)
        self.owner_id = owner_id

    @discord.ui.button(label="Modifier", emoji="✏️", style=discord.ButtonStyle.secondary)
    async def b_modifier(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Tu ne peux modifier que ta propre carte.", ephemeral=True)
            return
        await interaction.response.send_message("Que veux-tu modifier ?", view=ModifierActionsView(self.owner_id), ephemeral=True)


@bot.command(name="profil", aliases=["check"])
@check_public()
async def profil(ctx, *, ref: str = None):
    member = await resoudre_cible(ctx, ref)
    if member is None:
        await ctx.send("❌ Utilisateur introuvable. Donne une **mention**, un **ID**, ou un **pseudo** valide.")
        return
    infos = collecter_infos(member)
    vues = comptabiliser_vue(ctx.author, member)
    u = await recuperer_user(member)
    embed = embed_profil(member, infos, f"🔎 Profil de {member.name}")
    embed.add_field(name="👁 Fame", value=f"{vues} vue(s)", inline=True)
    if u and u.banner:
        embed.set_image(url=u.banner.url)
    await ctx.send(embed=embed)


@bot.command(name="carte", aliases=["card"])
@check_public()
async def carte(ctx, *, ref: str = None):
    """Genere une carte de profil (image, ou GIF si avatar anime). Ex: !carte @membre / !carte <id>"""
    if not PIL_OK:
        await ctx.send("La librairie Pillow n'est pas installee (ajoute `Pillow` aux dependances).")
        return
    member = await resoudre_cible(ctx, ref)
    if member is None:
        await ctx.send("❌ Utilisateur introuvable. Donne une **mention**, un **ID**, ou un **pseudo** valide.")
        return
    infos = collecter_infos(member)
    vues = comptabiliser_vue(ctx.author, member)
    rang = fame_rang(ctx.guild, member.id) if ctx.guild else 0
    bio = BIOS.get(member.id)
    accent = couleur_membre(member.id)
    async with ctx.typing():
        buf, ext = await generer_carte(member, infos, vues, rang, bio, accent)
    vue = CarteModifierView(member.id) if member.id == ctx.author.id else None
    await ctx.send(content=f"👁 **{vues}** vue(s)",
                   file=discord.File(buf, filename=f"carte.{ext}"), view=vue)


@bot.command(name="tcg", aliases=["tcgcard", "collec", "holo", "anim"])
@check_public()
async def tcg(ctx, *, ref: str = None):
    """Genere une carte a collectionner holographique ANIMEE (GIF). Ex: !tcg @membre / !tcg <id>"""
    if not PIL_OK:
        await ctx.send("La librairie Pillow n'est pas installee (ajoute `Pillow` aux dependances).")
        return
    member = await resoudre_cible(ctx, ref)
    if member is None:
        await ctx.send("❌ Utilisateur introuvable. Donne une **mention**, un **ID**, ou un **pseudo** valide.")
        return
    infos = collecter_infos(member)
    vues = comptabiliser_vue(ctx.author, member)
    async with ctx.typing():
        buf = await generer_carte_tcg_anim(member, infos, vues)
    await ctx.send(content=f"👁 **{vues}** vue(s)",
                   file=discord.File(buf, filename="carte_tcg.gif"))


@bot.command(name="list")
@check_public()
async def list_cmd(ctx):
    await ctx.send(embed=embed_list_accueil(), view=ListRootView(ctx.author, ctx.guild))


@bot.command(name="top")
@check_public()
async def top(ctx):
    classement = []
    for m in ctx.guild.members:
        if m.bot:
            continue
        infos = collecter_infos(m)
        s, niv, emo, _ = niveau_rarete(infos)
        if s > 0:
            classement.append((s, niv, emo, m))
    classement.sort(key=lambda x: x[0], reverse=True)
    if not classement:
        await ctx.send("Aucun compte rare trouve."); return
    medailles = {1: "🥇", 2: "🥈", 3: "🥉"}
    lignes = []
    for i, (s, niv, emo, m) in enumerate(classement, 1):
        rang = medailles.get(i, f"**{i}.**")
        lignes.append(f"{rang} {m.mention} — {emo} {niv} ({s} pts)")
    view = PageView(ctx.author, ctx.guild, "🏆 Classement des comptes rares", lignes, discord.Color.gold())
    await ctx.send(embed=view.embed_courant(), view=view if view.total_pages > 1 else None)


class FameView(discord.ui.View):
    """Menu deroulant : afficher la fame en version Carte ou TCG."""
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.select(placeholder="Choisis l'affichage…", options=[
        discord.SelectOption(label="Fame Carte", value="carte", emoji="🖼️", description="Classement + carte du n°1"),
        discord.SelectOption(label="Fame TCG", value="tcg", emoji="🎴", description="Classement + TCG anime du n°1"),
    ])
    async def choisir(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer()
        guild = interaction.guild
        compte = vues_par_profil()
        classement = []
        for m in guild.members:
            if m.bot:
                continue
            v = compte.get(m.id, 0)
            if v > 0:
                classement.append((v, m))
        classement.sort(key=lambda x: x[0], reverse=True)
        embed = embed_fame(guild)
        if not classement or not PIL_OK:
            await interaction.followup.send(embed=embed)
            return
        top_m = classement[0][1]
        infos = collecter_infos(top_m)
        vues = compter_vues(top_m.id)
        try:
            if select.values[0] == "carte":
                buf, ext = await generer_carte(top_m, infos, vues, fame_rang(guild, top_m.id),
                                               BIOS.get(top_m.id), couleur_membre(top_m.id))
                fichier = discord.File(buf, filename=f"fame_carte.{ext}")
            else:
                buf = await generer_carte_tcg_anim(top_m, infos, vues)
                fichier = discord.File(buf, filename="fame_tcg.gif")
            await interaction.followup.send(content=f"👑 **N°1 Fame** : {top_m.mention}", embed=embed, file=fichier)
        except Exception:
            await interaction.followup.send(embed=embed)


@bot.command(name="fame", aliases=["fames", "celebrite", "vues"])
@check_public()
async def fame(ctx):
    """Classement des profils les plus vus (menu Carte / TCG)."""
    await ctx.send("🏆 **Fame** — choisis l'affichage :", view=FameView())


@bot.command(name="stats")
@check_public()
async def stats(ctx):
    compteur = {k: 0 for k in DETECT_KEYS}
    niveaux_count = {n: 0 for _, n, _, _ in NIVEAUX}
    total_rares = 0
    membres = [m for m in ctx.guild.members if not m.bot]
    for m in membres:
        infos = collecter_infos(m)
        if est_notable(infos):
            total_rares += 1
        for b in infos["badges"]:
            compteur[b] += 1
        for p in infos["pseudo"]:
            compteur[p] += 1
        for extra in (infos["anciennete"], infos["boost"]):
            if extra:
                compteur[extra] += 1
        _, niv, _, _ = niveau_rarete(infos)
        niveaux_count[niv] += 1

    embed = discord.Embed(title="📊 Statistiques du serveur", color=discord.Color.blurple())
    embed.add_field(name="Vue d'ensemble",
                    value=f"{len(membres)} membres · **{total_rares}** comptes notables", inline=False)
    embed.add_field(name="Niveaux",
                    value="\n".join(f"{e} {n} : {niveaux_count[n]}" for _, n, e, _ in NIVEAUX), inline=True)
    badges_txt = "\n".join(f"{emoji_de(k)} {SET_ITEMS[k]['label']} : {compteur[k]}"
                           for k in CATEGORIES["🏅 Badges"] if compteur[k]) or "—"
    embed.add_field(name="Badges", value=badges_txt, inline=True)
    autres = []
    for cat in ("🚀 Boost", "📅 Anciennete", "✨ Pseudo"):
        for k in CATEGORIES[cat]:
            if k in compteur and compteur[k]:
                autres.append(f"{emoji_de(k)} {SET_ITEMS[k]['label']} : {compteur[k]}")
    embed.add_field(name="Autres criteres", value="\n".join(autres) or "—", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="bareme")
@check_public()
async def bareme(ctx):
    await ctx.send(embed=embed_bareme_accueil(), view=BaremeView(ctx.author, ctx.guild))


# ==============================================================================
#  COMMANDES MODERATION : BAN / UNBAN / MUTE / UNMUTE / TEMPMUTE
# ==============================================================================

@bot.command(name="ban")
@check_owner()
async def ban_cmd(ctx, cible: str = None, *, raison: str = "Aucune raison fournie."):
    """!ban <@membre|id> [raison] — marche meme si la personne n'est PAS sur le serveur (via ID)."""
    if cible is None:
        await ctx.send("Utilisation : `!ban <@membre|id> [raison]`"); return
    uid, user = await resoudre_id_ou_user(ctx, cible)
    if uid is None:
        await ctx.send("❌ Cible introuvable. Donne une **mention**, un **ID** ou un **pseudo** (membre present)."); return
    if uid == BUYER_ID or uid in OWNERS:
        await ctx.send("⛔ Impossible de bannir un owner/buyer."); return
    if uid == ctx.author.id:
        await ctx.send("Tu ne peux pas te bannir toi-meme."); return
    nom = str(user) if user else f"ID {uid}"
    try:
        await ctx.guild.ban(discord.Object(id=uid), reason=f"{raison} — par {ctx.author}", delete_message_days=0)
    except discord.Forbidden:
        await ctx.send("⛔ Permission **Bannir des membres** manquante, ou role du bot trop bas."); return
    except discord.HTTPException as e:
        await ctx.send(f"Erreur API : {e}"); return
    db_retirer_mute(ctx.guild.id, uid); _annuler_tache(ctx.guild.id, uid)
    e = discord.Embed(title="🔨 Membre banni", color=discord.Color.red(),
                      description=f"**{nom}** (`{uid}`)\n**Raison :** {raison}")
    if not user or ctx.guild.get_member(uid) is None:
        e.set_footer(text="Ban par ID (la personne n'etait pas forcement sur le serveur).")
    await ctx.send(embed=e)


@bot.command(name="unban")
@check_owner()
async def unban_cmd(ctx, cible: str = None, *, raison: str = "Aucune raison fournie."):
    """!unban <id> (recommande) ou pseudo exact / pseudo#0000 d'un membre banni."""
    if cible is None:
        await ctx.send("Utilisation : `!unban <id>` (ou pseudo exact d'un banni)"); return
    uid = extraire_id(cible)
    if uid is None:
        s = cible.strip().lower()
        try:
            async for ban_entry in ctx.guild.bans():
                u = ban_entry.user
                if str(u).lower() == s or u.name.lower() == s or str(u.id) == s:
                    uid = u.id; break
        except discord.Forbidden:
            await ctx.send("⛔ Permission **Bannir des membres** manquante (lecture des bans)."); return
    if uid is None:
        await ctx.send("❌ Donne un **ID** valide (recommande) ou le pseudo exact d'un membre banni."); return
    try:
        await ctx.guild.unban(discord.Object(id=uid), reason=f"{raison} — par {ctx.author}")
    except discord.NotFound:
        await ctx.send("ℹ️ Cet utilisateur n'est pas banni."); return
    except discord.Forbidden:
        await ctx.send("⛔ Permission **Bannir des membres** manquante."); return
    except discord.HTTPException as e:
        await ctx.send(f"Erreur API : {e}"); return
    await ctx.send(embed=discord.Embed(title="♻️ Debannissement",
                   description=f"<@{uid}> (`{uid}`) a ete debanni.", color=discord.Color.green()))


@bot.command(name="setmute", aliases=["setmuterole"])
@check_owner()
async def setmute_cmd(ctx, role: discord.Role = None):
    """Definit (ou cree) le role de mute. !setmute @role, ou !setmute seul pour auto-creer."""
    if role is None:
        r = await obtenir_role_mute(ctx.guild)
        if r is None:
            await ctx.send("⛔ Je ne peux pas creer le role **Muted** (permission **Gerer les roles** manquante).\n"
                           "Cree-le a la main puis fais `!setmute @role`."); return
        await ctx.send(f"✅ Role de mute : {r.mention} (auto). Tu peux le changer avec `!setmute @role`."); return
    definir_config("muterole", role.id)
    await ctx.send(f"✅ Role de mute defini : {role.mention}")


@bot.command(name="mute")
@check_owner()
async def mute_cmd(ctx, cible: str = None, *, raison: str = "Aucune raison fournie."):
    """!mute <@membre|id> [raison] — mute permanent. S'applique aussi a une personne hors serveur (a son arrivee)."""
    if cible is None:
        await ctx.send("Utilisation : `!mute <@membre|id> [raison]`"); return
    uid, user = await resoudre_id_ou_user(ctx, cible)
    if uid is None:
        await ctx.send("❌ Cible introuvable. Donne une **mention**, un **ID** ou un **pseudo**."); return
    if uid == BUYER_ID or uid in OWNERS:
        await ctx.send("⛔ Impossible de mute un owner/buyer."); return
    db_ajouter_mute(ctx.guild.id, uid, None, raison)
    _annuler_tache(ctx.guild.id, uid)
    member = ctx.guild.get_member(uid)
    if member:
        await _appliquer_mute(member, None)
        cible_txt = member.mention
    else:
        cible_txt = f"<@{uid}> (`{uid}`)"
    e = discord.Embed(title="🔇 Membre mute", color=discord.Color.dark_grey(),
                      description=f"{cible_txt}\n**Duree :** permanent\n**Raison :** {raison}")
    if not member:
        e.set_footer(text="Pas sur le serveur : le mute s'appliquera des son arrivee.")
    await ctx.send(embed=e)


@bot.command(name="tempmute", aliases=["mutetemp"])
@check_owner()
async def tempmute_cmd(ctx, cible: str = None, duree: str = None, *, raison: str = "Aucune raison fournie."):
    """!tempmute <@membre|id> <duree> [raison]. Durees : 30s, 10m, 2h, 1j, 1sem, ou combine 1h30m."""
    if cible is None or duree is None:
        await ctx.send("Utilisation : `!tempmute <@membre|id> <duree> [raison]`\n"
                       "Durees : `30s`, `10m`, `2h`, `1j`, `1sem`, ou combine `1h30m`."); return
    sec = parse_duree(duree)
    if not sec:
        await ctx.send("❌ Duree invalide. Ex : `10m`, `2h`, `1j`, `1h30m`."); return
    uid, user = await resoudre_id_ou_user(ctx, cible)
    if uid is None:
        await ctx.send("❌ Cible introuvable."); return
    if uid == BUYER_ID or uid in OWNERS:
        await ctx.send("⛔ Impossible de mute un owner/buyer."); return
    until = _now_ts() + sec
    db_ajouter_mute(ctx.guild.id, uid, until, raison)
    member = ctx.guild.get_member(uid)
    if member:
        await _appliquer_mute(member, until)
        cible_txt = member.mention
    else:
        cible_txt = f"<@{uid}> (`{uid}`)"
    _planifier_unmute(ctx.guild.id, uid, until)
    e = discord.Embed(title="🔇 Membre mute (temporaire)", color=discord.Color.dark_grey(),
                      description=f"{cible_txt}\n**Duree :** {format_duree(sec)}\n"
                                  f"**Fin :** <t:{until}:R>\n**Raison :** {raison}")
    if not member:
        e.set_footer(text="Pas sur le serveur : le mute s'appliquera des son arrivee.")
    await ctx.send(embed=e)


@bot.command(name="unmute", aliases=["demute", "untempmute"])
@check_owner()
async def unmute_cmd(ctx, cible: str = None):
    """!unmute <@membre|id> — retire le mute (permanent ou temporaire)."""
    if cible is None:
        await ctx.send("Utilisation : `!unmute <@membre|id>`"); return
    uid, _user = await resoudre_id_ou_user(ctx, cible)
    if uid is None:
        uid = extraire_id(cible)
    if uid is None:
        await ctx.send("❌ Cible introuvable."); return
    avait = db_info_mute(ctx.guild.id, uid) is not None
    await _retirer_mute(ctx.guild, uid)
    if avait:
        await ctx.send(embed=discord.Embed(title="🔊 Mute retire",
                       description=f"<@{uid}> n'est plus mute.", color=discord.Color.green()))
    else:
        await ctx.send(f"ℹ️ <@{uid}> n'etait pas enregistre comme mute (j'ai quand meme nettoye le role/timeout si present).")


@bot.command(name="mutes")
@check_owner()
async def mutes_cmd(ctx):
    """Liste les personnes actuellement mute sur ce serveur."""
    rows = db_mutes_guild(ctx.guild.id)
    if not rows:
        await ctx.send("Aucune personne mute actuellement."); return
    lignes = []
    for uid, until, raison in rows:
        if until:
            duree = f"jusqu'a <t:{until}:R>"
        else:
            duree = "permanent"
        rs = f" — {raison}" if raison else ""
        lignes.append(f"<@{uid}> (`{uid}`) — {duree}{rs}")
    view = PageView(ctx.author, ctx.guild, "🔇 Personnes mute", lignes, discord.Color.dark_grey())
    await ctx.send(embed=view.embed_courant(), view=view if view.total_pages > 1 else None)


# ==============================================================================
#  MODERATION / SALONS
# ==============================================================================

@bot.command(name="nuke", aliases=["renew"])
@check_owner()
async def nuke(ctx):
    """Supprime le salon et le recree a l'identique (renew)."""
    salon = ctx.channel
    if not isinstance(salon, discord.TextChannel):
        await ctx.send("Cette commande s'utilise dans un salon textuel."); return
    me = ctx.guild.me
    if not salon.permissions_for(me).manage_channels:
        await ctx.send("⛔ Il me manque la permission **Gerer les salons**."); return
    pos = salon.position
    try:
        nouveau = await salon.clone(reason=f"Nuke par {ctx.author}")
        await nouveau.edit(position=pos)
        await salon.delete(reason=f"Nuke par {ctx.author}")
    except discord.Forbidden:
        await ctx.send("⛔ Permissions insuffisantes pour recreer le salon."); return
    except discord.HTTPException as e:
        await ctx.send(f"Erreur : {e}"); return
    embed = discord.Embed(
        title="💥 Salon renouvele",
        description=f"Ce salon a ete nettoye et recree par {ctx.author.mention}.",
        color=discord.Color.orange(),
    )
    try:
        await nouveau.send(embed=embed)
    except discord.HTTPException:
        pass


@bot.command(name="clear", aliases=["purge", "clean"])
@check_owner()
async def clear(ctx, cible: str = None):
    """!clear (100 derniers) · !clear <1-100> · !clear @membre (ses 100 derniers messages)."""
    salon = ctx.channel
    if not salon.permissions_for(ctx.guild.me).manage_messages:
        await ctx.send("⛔ Il me manque la permission **Gerer les messages**."); return

    membre = None
    nombre = None
    if cible is not None:
        try:
            membre = await commands.MemberConverter().convert(ctx, cible)
        except Exception:
            try:
                nombre = max(1, min(100, int(cible)))
            except ValueError:
                await ctx.send("Usage : `!clear`, `!clear <1-100>` ou `!clear @membre`."); return

    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass

    try:
        if membre is not None:
            supprimes = await salon.purge(limit=100, check=lambda m: m.author.id == membre.id)
            txt = f"🧹 {len(supprimes)} message(s) de {membre.mention} supprime(s)."
        else:
            n = nombre if nombre is not None else 100
            supprimes = await salon.purge(limit=n)
            txt = f"🧹 {len(supprimes)} message(s) supprime(s)."
    except discord.Forbidden:
        await ctx.send("⛔ Permissions insuffisantes."); return
    except discord.HTTPException as e:
        await ctx.send(f"Erreur : {e}"); return

    await ctx.send(txt, delete_after=4)


@bot.command(name="allow")
@check_owner()
async def allow(ctx, salon: discord.TextChannel = None):
    """Autorise les commandes publiques dans un salon. !allow ou !allow #salon."""
    salon = salon or ctx.channel
    ajouter_salon_public(salon.id)
    embed = discord.Embed(
        title="✅ Salon ouvert aux commandes",
        description=("Tout le monde peut desormais utiliser les commandes publiques ici :\n"
                     "`!profil` · `!carte` · `!bareme` · `!top` · `!list` · `!stats`\n\n"
                     "Les commandes de gestion restent reservees aux owners."),
        color=discord.Color.green(),
    )
    try:
        await salon.send(embed=embed)
    except discord.HTTPException:
        pass
    if salon.id != ctx.channel.id:
        await ctx.send(f"✅ Commandes publiques activees dans {salon.mention}.")


@bot.command(name="unallow", aliases=["disallow"])
@check_owner()
async def unallow(ctx, salon: discord.TextChannel = None):
    """Retire l'autorisation des commandes publiques. !unallow ou !unallow #salon."""
    salon = salon or ctx.channel
    retirer_salon_public(salon.id)
    await ctx.send(f"🚫 Commandes publiques desactivees dans {salon.mention}. "
                   "Seuls les owners peuvent y faire des commandes.")


@bot.command(name="owner")
@check_buyer()
async def owner_cmd(ctx, *, ref: str = None):
    if not ref:
        await ctx.send("Donne une **mention** ou un **ID**. Ex: `!owner 425450624461701130`"); return
    membre = await resoudre_cible(ctx, ref)
    if membre is None:
        await ctx.send("❌ Utilisateur introuvable."); return
    if membre.id == BUYER_ID:
        await ctx.send("Tu es le buyer."); return
    if membre.id in OWNERS:
        await ctx.send(f"{membre.mention} est deja owner."); return
    ajouter_owner(membre.id)
    await ctx.send(f"✅ {membre.mention} (`{membre.id}`) est owner.")


@bot.command(name="unowner")
@check_buyer()
async def unowner_cmd(ctx, *, ref: str = None):
    membre = await resoudre_cible(ctx, ref) if ref else None
    if membre is None:
        await ctx.send("Donne une **mention** ou un **ID**. Ex: `!unowner 425450624461701130`"); return
    if membre.id == BUYER_ID:
        await ctx.send("Le buyer ne peut pas etre retire."); return
    if membre.id not in OWNERS:
        await ctx.send(f"{membre.mention} n'est pas owner."); return
    retirer_owner(membre.id)
    await ctx.send(f"✅ {membre.mention} n'est plus owner.")


@bot.command(name="owners")
@check_owner()
async def owners_cmd(ctx):
    lignes = [f"👑 <@{BUYER_ID}> — **Buyer**"] + ([f"• <@{u}>" for u in OWNERS] or ["*(aucun owner)*"])
    await ctx.send(embed=discord.Embed(title="Hierarchie", description="\n".join(lignes),
                                       color=discord.Color.blurple()))


@bot.command(name="help")
async def help_cmd(ctx):
    await ctx.send(embed=embed_help_accueil(), view=HelpView(ctx.author, ctx.guild))


# ==============================================================================
#  ERREURS / EVENEMENTS
# ==============================================================================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("⛔ Tu n'as pas l'autorisation.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Argument manquant.")
    elif isinstance(error, (commands.UserNotFound, commands.MemberNotFound,
                            commands.ChannelNotFound, commands.RoleNotFound, commands.BadArgument)):
        await ctx.send("Argument invalide.")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        raise error


@bot.event
async def on_ready():
    print(f"Bot connecte : {bot.user} (id {bot.user.id})")
    if not WORDFREQ_OK:
        print("/!\\ wordfreq non installe : detection des mots desactivee.")
    print(f"Buyer : {BUYER_ID} | Owners : {len(OWNERS)}")
    # Reprise des mutes : nettoie les expires, replanifie les fins en cours.
    for gid, uid, until, _ in db_tous_mutes():
        if until and until <= _now_ts():
            guild = bot.get_guild(gid)
            if guild:
                await _retirer_mute(guild, uid)
            else:
                db_retirer_mute(gid, uid)
        elif until:
            _planifier_unmute(gid, uid, until)


@bot.event
async def on_member_join(member):
    if member.bot:
        return
    infos = collecter_infos(member)
    u = await recuperer_user(member)                 # pour la banniere dans le log
    await attribuer_roles_depuis(member, infos)      # attribue les roles
    if est_notable(infos):
        await envoyer_log_join(member.guild, member, infos, u)
    # Re-applique un mute en attente si la personne etait mute (meme en etant partie/absente).
    info_mute = db_info_mute(member.guild.id, member.id)
    if info_mute:
        until, _ = info_mute
        if until and until <= _now_ts():
            await _retirer_mute(member.guild, member.id)
        else:
            await _appliquer_mute(member, until)
            if until:
                _planifier_unmute(member.guild.id, member.id, until)


@bot.event
async def on_member_update(before, after):
    # Re-detection auto (ex: changement de boost).
    if not after.bot:
        await appliquer_roles(after)


@bot.event
async def on_user_update(before, after):
    # Re-detection auto (ex: changement de pseudo) sur tous les serveurs partages.
    for g in bot.guilds:
        m = g.get_member(after.id)
        if m and not m.bot:
            await appliquer_roles(m)


if __name__ == "__main__":
    if not TOKEN or TOKEN == "COLLE_TON_TOKEN_ICI_SI_TU_VEUX":
        raise SystemExit("Aucun token. Definis DISCORD_TOKEN ou colle-le dans TOKEN.")
    assurer_polices()   # telecharge Poppins une fois (repli sur police systeme si echec)
    bot.run(TOKEN)
