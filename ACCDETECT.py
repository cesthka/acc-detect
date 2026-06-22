"""
================================================================================
  BOT DISCORD - DETECTION DE COMPTES RARES (version enrichie)
  buyer/owner · SQLite · !set/!scan par categorie · boost · niveau de rarete
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


init_db()
CONFIG = _charger("config", "key", "value")
EMOJIS = _charger("emojis", "key", "emoji")
MESSAGES = _charger("messages", "key", "contenu")
OWNERS = charger_owners()
FOND_DATA = charger_fond()
SALONS_PUBLIC = charger_salons_public()


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
    if member.joined_at:
        embed.add_field(name="📥 A rejoint", value=f"<t:{int(member.joined_at.timestamp())}:R>", inline=True)

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


async def generer_carte(member, infos, vues=0):
    """Genere une carte de profil en image (PNG) premium, renvoie un buffer BytesIO."""
    score, niveau, _, _ = niveau_rarete(infos)
    rgb = CARTE_COULEURS.get(niveau, (149, 165, 166))
    L = 900

    f_nom = _police(58, "ExtraBold")
    f_id = _police(24, "Medium")
    f_pill = _police(27, "SemiBold")
    f_pet = _police(22, "Medium")
    f_chip = _police(23, "SemiBold")
    blanc, gris = (255, 255, 255, 255), (202, 207, 214, 255)

    # Attributs -> pastilles
    cles = list(infos["badges"]) + list(infos["pseudo"])
    for extra in (infos["anciennete"], infos["boost"]):
        if extra:
            cles.append(extra)
    labels = [SET_ITEMS[k]["label"] for k in cles] or ["Compte standard"]

    # Mesure prealable -> hauteur dynamique
    mes = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    pad, gap, ch = 20, 12, 42
    x_chip, maxx = 55, L - 45
    chip_w = [mes.textlength(lab, font=f_chip) + pad * 2 for lab in labels]
    cur, rows = x_chip, 1
    for w in chip_w:
        if cur + w > maxx and cur > x_chip:
            rows += 1
            cur = x_chip
        cur += w + gap
    cy0 = 392
    H = cy0 + rows * ch + (rows - 1) * gap + 24

    # --- Fond : 1) perso  2) banniere  3) degrade ---
    carte = _fond_degrade(L, H, _melange((38, 40, 48), rgb, 0.12), (16, 17, 20))
    image_fond = False
    if FOND_DATA:
        try:
            img = Image.open(BytesIO(FOND_DATA)).convert("RGBA")
            carte = _couvrir(img, L, H)
            image_fond = True
        except Exception:
            pass
    if not image_fond:
        u = await recuperer_user(member)
        if u and u.banner:
            try:
                bdata = await u.banner.replace(size=600, static_format="png").read()
                carte = _couvrir(Image.open(BytesIO(bdata)).convert("RGBA"), L, H).filter(ImageFilter.GaussianBlur(8))
                image_fond = True
            except Exception:
                pass

    # Assombrissement + voile gauche pour la lisibilite (seulement si image de fond)
    if image_fond:
        carte = Image.alpha_composite(carte, Image.new("RGBA", (L, H), (0, 0, 0, 70)))
        carte = Image.alpha_composite(carte, _voile_gauche(L, H))

    # --- Lueur autour de l'avatar ---
    ax, ay, ad, ring = 55, 128, 205, 6
    glow = Image.new("RGBA", (L, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([ax - ring - 22, ay - ring - 22, ax + ad + ring + 22, ay + ad + ring + 22],
                                 fill=rgb + (135,))
    carte = Image.alpha_composite(carte, glow.filter(ImageFilter.GaussianBlur(20)))
    draw = ImageDraw.Draw(carte)

    # --- Avatar + anneau ---
    draw.ellipse([ax - ring, ay - ring, ax + ad + ring, ay + ad + ring], fill=rgb + (255,))
    try:
        adata = await member.display_avatar.replace(size=256, static_format="png").read()
        av = Image.open(BytesIO(adata)).convert("RGBA").resize((ad, ad))
        m = Image.new("L", (ad, ad), 0)
        ImageDraw.Draw(m).ellipse([0, 0, ad, ad], fill=255)
        carte.paste(av, (ax, ay), m)
    except Exception:
        draw.ellipse([ax, ay, ax + ad, ay + ad], fill=(40, 42, 50, 255))

    x = 300
    maxw = L - x - 45
    _ombre(draw, (x, 116), _ajuster(draw, member.name, f_nom, maxw), f_nom, blanc, dx=2, dy=3, alpha=170)
    _ombre(draw, (x, 188), f"ID  {member.id}", f_id, gris, dx=1, dy=2, alpha=150)

    # --- Pastille de niveau (avec ombre floue) ---
    txt = f"{niveau.upper()}   {score} PTS"
    tw = draw.textlength(txt, font=f_pill)
    py, pillw = 228, tw + 48
    sh = Image.new("RGBA", (L, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([x, py + 5, x + pillw, py + 55], radius=26, fill=(0, 0, 0, 120))
    carte = Image.alpha_composite(carte, sh.filter(ImageFilter.GaussianBlur(6)))
    draw = ImageDraw.Draw(carte)
    draw.rounded_rectangle([x, py, x + pillw, py + 50], radius=25, fill=rgb + (255,))
    draw.text((x + 24, py + 25), txt, font=f_pill, fill=(12, 14, 16, 255), anchor="lm")

    # --- Barre de progression ---
    frac, nxt = _progression(score)
    bx, by, bw, bh = x, 308, maxw, 22
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=bh // 2, fill=(255, 255, 255, 45))
    if frac > 0:
        draw.rounded_rectangle([bx, by, bx + max(bh, int(bw * frac)), by + bh], radius=bh // 2, fill=rgb + (255,))
    label = f"Plus que {nxt - score} pts pour le palier suivant" if nxt else "Palier maximum atteint"
    _ombre(draw, (bx, by + bh + 12), label, f_pet, gris, dx=1, dy=2, alpha=150)

    # --- Pastilles d'attributs (translucides, multi-lignes) ---
    cxx, cyy = x_chip, cy0
    for lab, w in zip(labels, chip_w):
        if cxx + w > maxx and cxx > x_chip:
            cxx, cyy = x_chip, cyy + ch + gap
        couche = Image.new("RGBA", (L, H), (0, 0, 0, 0))
        ImageDraw.Draw(couche).rounded_rectangle([cxx, cyy, cxx + w, cyy + ch], radius=ch // 2, fill=(10, 12, 14, 165))
        carte = Image.alpha_composite(carte, couche)
        draw = ImageDraw.Draw(carte)
        draw.rounded_rectangle([cxx, cyy, cxx + w, cyy + ch], radius=ch // 2, outline=rgb + (255,), width=2)
        draw.text((cxx + pad, cyy + ch // 2), lab, font=f_chip, fill=(236, 238, 241, 255), anchor="lm")
        cxx += w + gap

    # --- Pastille de vues (haut-droite) ---
    fv = _police(24, "SemiBold")
    largeur_v = int(14 + int(42 * 0.62) + 8 + draw.textlength(str(vues), font=fv) + 14)
    _dessiner_vues(carte, L - 30 - largeur_v, 28, vues, fv)

    # --- Coins arrondis ---
    masque = Image.new("L", (L, H), 0)
    ImageDraw.Draw(masque).rounded_rectangle([0, 0, L - 1, H - 1], radius=36, fill=255)
    final = Image.new("RGBA", (L, H), (0, 0, 0, 0))
    final.paste(carte, (0, 0), masque)

    buf = BytesIO()
    final.save(buf, format="PNG")
    buf.seek(0)
    return buf


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
        ("!carte @membre", "Carte de profil en image (avatar, niveau, badges)."),
        ("!tcg @membre", "Carte a collectionner holographique (rendu premium)."),
        ("!list", "Liste des membres d'un critere (menu deroulant)."),
        ("!stats", "Tableau de bord global du serveur."),
        ("!top", "Classement des comptes les plus rares."),
        ("!fame", "Classement des profils les plus vus (vues uniques)."),
        ("!bareme", "Bareme de rarete (menu par categorie)."),
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


class CarteView(discord.ui.View):
    """Bouton sous une carte pour ouvrir le classement Fame."""
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Classement Fame", emoji="🏆", style=discord.ButtonStyle.secondary)
    async def fame_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=embed_fame(interaction.guild), ephemeral=True)


@bot.command(name="profil", aliases=["check"])
@check_public()
async def profil(ctx, member: discord.Member = None):
    member = member or ctx.author
    infos = collecter_infos(member)
    vues = comptabiliser_vue(ctx.author, member)
    u = await recuperer_user(member)
    embed = embed_profil(member, infos, f"🔎 Profil de {member.name}")
    embed.add_field(name="👁 Fame", value=f"{vues} vue(s)", inline=True)
    if u and u.banner:
        embed.set_image(url=u.banner.url)
    await ctx.send(embed=embed, view=CarteView())


@bot.command(name="carte", aliases=["card"])
@check_public()
async def carte(ctx, member: discord.Member = None):
    """Genere une carte de profil en image. Ex: !carte @membre"""
    if not PIL_OK:
        await ctx.send("La librairie Pillow n'est pas installee (ajoute `Pillow` aux dependances).")
        return
    member = member or ctx.author
    infos = collecter_infos(member)
    vues = comptabiliser_vue(ctx.author, member)
    async with ctx.typing():
        buf = await generer_carte(member, infos, vues)
    await ctx.send(content=f"👁 **{vues}** vue(s)",
                   file=discord.File(buf, filename="profil.png"), view=CarteView())


@bot.command(name="tcg", aliases=["tcgcard", "collec"])
@check_public()
async def tcg(ctx, member: discord.Member = None):
    """Genere une carte a collectionner holographique. Ex: !tcg @membre"""
    if not PIL_OK:
        await ctx.send("La librairie Pillow n'est pas installee (ajoute `Pillow` aux dependances).")
        return
    member = member or ctx.author
    infos = collecter_infos(member)
    vues = comptabiliser_vue(ctx.author, member)
    async with ctx.typing():
        buf = await generer_carte_tcg(member, infos, vues)
    await ctx.send(content=f"👁 **{vues}** vue(s)",
                   file=discord.File(buf, filename="carte_tcg.png"), view=CarteView())


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


@bot.command(name="fame", aliases=["fames", "celebrite", "vues"])
@check_public()
async def fame(ctx):
    """Classement des profils les plus vus (fame)."""
    compte = vues_par_profil()
    classement = []
    for m in ctx.guild.members:
        if m.bot:
            continue
        v = compte.get(m.id, 0)
        if v > 0:
            classement.append((v, m))
    classement.sort(key=lambda x: x[0], reverse=True)
    if not classement:
        await ctx.send("Personne n'a encore de vues. Faites `!carte @membre` pour lancer la fame !")
        return
    medailles = {1: "🥇", 2: "🥈", 3: "🥉"}
    lignes = [f"{medailles.get(i, f'**{i}.**')} {m.mention} — 👁 {v} vue(s)"
              for i, (v, m) in enumerate(classement, 1)]
    view = PageView(ctx.author, ctx.guild, "🏆 Classement Fame", lignes, discord.Color.gold())
    await ctx.send(embed=view.embed_courant(), view=view if view.total_pages > 1 else None)
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
async def owner_cmd(ctx, membre: discord.User):
    if membre.id == BUYER_ID:
        await ctx.send("Tu es le buyer."); return
    if membre.id in OWNERS:
        await ctx.send(f"{membre.mention} est deja owner."); return
    ajouter_owner(membre.id)
    await ctx.send(f"✅ {membre.mention} (`{membre.id}`) est owner.")


@bot.command(name="unowner")
@check_buyer()
async def unowner_cmd(ctx, membre: discord.User):
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


@bot.event
async def on_member_join(member):
    if member.bot:
        return
    infos = collecter_infos(member)
    u = await recuperer_user(member)                 # pour la banniere dans le log
    await attribuer_roles_depuis(member, infos)      # attribue les roles
    if est_notable(infos):
        await envoyer_log_join(member.guild, member, infos, u)


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
