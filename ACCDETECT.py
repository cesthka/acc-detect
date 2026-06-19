"""
================================================================================
  BOT DISCORD - DETECTION DE COMPTES RARES (version enrichie)
  buyer/owner · SQLite · !set/!scan par categorie · boost · niveau de rarete
================================================================================
NOTE: les badges Nitro (Bronze..Opale) ne sont PAS exposes par l'API Discord et
ne peuvent donc pas etre detectes par un bot. On detecte a la place le BOOST de
ce serveur (via premium_since) et un "Nitro probable" (avatar anime/banniere).
================================================================================
"""

import os
import datetime
import sqlite3
import discord
from discord.ext import commands

try:
    from wordfreq import zipf_frequency
    WORDFREQ_OK = True
except ImportError:
    WORDFREQ_OK = False

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
    "nitro":      {"label": "Nitro (probable)",           "type": "role"},
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
    "💎 Nitro & Boost": ["nitro", "boost1", "boost2", "boost3", "boost6", "boost9",
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
    "nitro": "💎", "boost1": "🚀", "boost2": "🚀", "boost3": "🚀", "boost6": "🚀", "boost9": "🚀",
    "boost12": "🚀", "boost15": "🚀", "boost18": "🚀", "boost24": "🚀",
    "og2016": "📅", "og2017": "📅", "og2018": "📅",
    "pseudo2": "✨", "pseudo3": "✨", "mot": "🔤", "chiffres": "🔢",
}

JOIN_TITRE_DEFAUT = "🌟 Un compte rare a rejoint le serveur !"

# --- Bareme de rarete ---
POIDS = {
    "staff": 8, "partner": 6, "botdev": 5, "bughunter2": 5, "mod": 4, "bughunter": 4,
    "hypesquad": 3, "early": 3, "bravery": 1, "brilliance": 1, "balance": 1,
    "og2016": 4, "og2017": 3, "og2018": 2,
    "pseudo2": 4, "pseudo3": 3, "mot": 2, "chiffres": 1,
    "nitro": 1,
    "boost1": 1, "boost2": 1, "boost3": 2, "boost6": 2, "boost9": 3,
    "boost12": 3, "boost15": 4, "boost18": 4, "boost24": 5,
}

NIVEAUX = [
    (0,  "Commun",      discord.Color.light_grey()),
    (2,  "Peu commun",  discord.Color.green()),
    (4,  "Rare",        discord.Color.blue()),
    (7,  "Epique",      discord.Color.purple()),
    (11, "Legendaire",  discord.Color.gold()),
    (16, "Mythique",    discord.Color.red()),
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


init_db()
CONFIG = _charger("config", "key", "value")
EMOJIS = _charger("emojis", "key", "emoji")
MESSAGES = _charger("messages", "key", "contenu")
OWNERS = charger_owners()


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


def detecter_nitro_probable(member):
    """Indices de Nitro lisibles par un bot (pas le palier exact)."""
    try:
        if member.display_avatar and member.display_avatar.is_animated():
            return True
    except Exception:
        pass
    if getattr(member, "avatar_decoration", None):
        return True
    return False


def collecter_infos(member):
    return {
        "badges": detecter_badges(member),
        "pseudo": detecter_pseudo(member),
        "anciennete": detecter_anciennete(member),
        "boost": detecter_boost(member),
        "nitro": detecter_nitro_probable(member),
        "erreurs": [],
    }


OG_THRESHOLDS = dict(OG_SEUILS)


def membre_a_cle(member, key):
    if key in OG_THRESHOLDS:
        return member.created_at < OG_THRESHOLDS[key]
    if key in BOOST_MOIS:
        mois = mois_de_boost(member)
        return mois is not None and mois >= BOOST_MOIS[key]
    if key == "nitro":
        return detecter_nitro_probable(member)
    if key in ("pseudo2", "pseudo3", "mot", "chiffres"):
        return key in detecter_pseudo(member)
    return key in detecter_badges(member)


def membres_avec(guild, key):
    return [m for m in guild.members if not m.bot and membre_a_cle(m, key)]


async def appliquer_roles(member):
    infos = collecter_infos(member)
    cles = list(infos["badges"]) + list(infos["pseudo"])
    for extra in (infos["anciennete"], infos["boost"]):
        if extra:
            cles.append(extra)
    if infos["nitro"]:
        cles.append("nitro")
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
    return infos


def est_notable(infos):
    return bool(infos["badges"] or infos["pseudo"] or infos["anciennete"] or infos["boost"] or infos["nitro"])


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
    if infos["nitro"]:
        s += POIDS.get("nitro", 0)
    return s


def niveau_rarete(infos):
    s = score_rarete(infos)
    nom, couleur = NIVEAUX[0][1], NIVEAUX[0][2]
    for seuil, n, c in NIVEAUX:
        if s >= seuil:
            nom, couleur = n, c
    return s, nom, couleur


def exceptionnel(infos):
    _, niveau, _ = niveau_rarete(infos)
    if niveau in ("Legendaire", "Mythique"):
        return True
    return any(b in infos["badges"] for b in ("staff", "partner", "bughunter2"))


# ==============================================================================
#  EMBED PROFIL (join + profil)
# ==============================================================================

def embed_profil(member, infos, titre):
    score, niveau, couleur = niveau_rarete(infos)
    maintenant = datetime.datetime.now(datetime.timezone.utc)
    age = maintenant - member.created_at
    annees, jours = age.days // 365, age.days % 365

    embed = discord.Embed(title=titre, color=couleur, timestamp=maintenant)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Utilisateur", value=f"{member.mention}\n`{member.name}`", inline=True)
    embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
    embed.add_field(name="💎 Niveau", value=f"**{niveau}** ({score} pts)", inline=True)
    embed.add_field(name="📅 Compte cree",
                    value=f"<t:{int(member.created_at.timestamp())}:D>\n(il y a {annees} an(s) et {jours} j)",
                    inline=True)
    if member.joined_at:
        embed.add_field(name="📥 A rejoint", value=f"<t:{int(member.joined_at.timestamp())}:R>", inline=True)

    # Badges = emojis seuls (badges + pseudo + anciennete + boost + nitro), sans texte.
    cles = list(infos["badges"]) + list(infos["pseudo"])
    for extra in (infos["anciennete"], infos["boost"]):
        if extra:
            cles.append(extra)
    if infos["nitro"]:
        cles.append("nitro")
    ligne = "  ".join(emoji_de(k) for k in cles) if cles else "—"
    embed.add_field(name="🏅 Badges", value=ligne, inline=False)

    if infos["erreurs"]:
        embed.add_field(name="⚠️ Attention", value="\n".join(infos["erreurs"]), inline=False)
    return embed


async def ajouter_banniere(embed, member):
    try:
        u = await bot.fetch_user(member.id)
        if u.banner:
            embed.set_image(url=u.banner.url)
    except Exception:
        pass


async def envoyer_log_join(guild, member, infos):
    salon = guild.get_channel(CONFIG.get("logs", 0))
    if salon is None:
        return
    embed = embed_profil(member, infos, message_de("join", JOIN_TITRE_DEFAUT))
    embed.set_footer(text=guild.name)
    await ajouter_banniere(embed, member)
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
        ("!list", "Liste des membres d'un critere (menu deroulant)."),
        ("!stats", "Tableau de bord global du serveur."),
        ("!top", "Classement des comptes les plus rares."),
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
    ],
    "👑 Gestion": [
        ("!owner @membre", "Ajoute un owner (buyer)."),
        ("!unowner @membre", "Retire un owner (buyer)."),
        ("!owners", "Buyer + owners."),
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

BAREME_CATS = ["🏅 Badges", "💎 Nitro & Boost", "📅 Anciennete", "✨ Pseudo"]


def embed_bareme_accueil():
    e = discord.Embed(title="📐 Bareme de rarete",
                      description="Choisis une categorie pour voir les points.",
                      color=discord.Color.blurple())
    e.add_field(name="Niveaux (score minimum)",
                value="\n".join(f"{n} : {s}+ pts" for s, n, _ in NIVEAUX), inline=False)
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


@bot.command(name="scan")
@check_owner()
async def scan(ctx):
    await ctx.send(embed=embed_scan_accueil(), view=ScanView(ctx.author, ctx.guild))


@bot.command(name="profil", aliases=["check"])
@check_owner()
async def profil(ctx, member: discord.Member = None):
    member = member or ctx.author
    infos = collecter_infos(member)
    embed = embed_profil(member, infos, f"🔎 Profil de {member.name}")
    await ajouter_banniere(embed, member)
    await ctx.send(embed=embed)


@bot.command(name="list")
@check_owner()
async def list_cmd(ctx):
    await ctx.send(embed=embed_list_accueil(), view=ListRootView(ctx.author, ctx.guild))


@bot.command(name="top")
@check_owner()
async def top(ctx):
    classement = []
    for m in ctx.guild.members:
        if m.bot:
            continue
        infos = collecter_infos(m)
        s, niv, _ = niveau_rarete(infos)
        if s > 0:
            classement.append((s, niv, m))
    classement.sort(key=lambda x: x[0], reverse=True)
    if not classement:
        await ctx.send("Aucun compte rare trouve."); return
    lignes = [f"**{i}.** {m.mention} — {niv} ({s} pts)" for i, (s, niv, m) in enumerate(classement, 1)]
    view = PageView(ctx.author, ctx.guild, "🏆 Classement des comptes rares", lignes, discord.Color.gold())
    await ctx.send(embed=view.embed_courant(), view=view if view.total_pages > 1 else None)


@bot.command(name="stats")
@check_owner()
async def stats(ctx):
    compteur = {k: 0 for k in DETECT_KEYS}
    niveaux_count = {n: 0 for _, n, _ in NIVEAUX}
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
        if infos["nitro"]:
            compteur["nitro"] += 1
        _, niv, _ = niveau_rarete(infos)
        niveaux_count[niv] += 1

    embed = discord.Embed(title="📊 Statistiques du serveur", color=discord.Color.blurple())
    embed.add_field(name="Vue d'ensemble",
                    value=f"{len(membres)} membres · **{total_rares}** comptes notables", inline=False)
    embed.add_field(name="Niveaux",
                    value="\n".join(f"{n} : {niveaux_count[n]}" for _, n, _ in NIVEAUX), inline=True)
    badges_txt = "\n".join(f"{emoji_de(k)} {SET_ITEMS[k]['label']} : {compteur[k]}"
                           for k in CATEGORIES["🏅 Badges"] if compteur[k]) or "—"
    embed.add_field(name="Badges", value=badges_txt, inline=True)
    autres = []
    for cat in ("💎 Nitro & Boost", "📅 Anciennete", "✨ Pseudo"):
        for k in CATEGORIES[cat]:
            if k in compteur and compteur[k]:
                autres.append(f"{emoji_de(k)} {SET_ITEMS[k]['label']} : {compteur[k]}")
    embed.add_field(name="Autres criteres", value="\n".join(autres) or "—", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="bareme")
@check_owner()
async def bareme(ctx):
    await ctx.send(embed=embed_bareme_accueil(), view=BaremeView(ctx.author, ctx.guild))


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
    infos = await appliquer_roles(member)
    if est_notable(infos):
        await envoyer_log_join(member.guild, member, infos)


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
    bot.run(TOKEN)
