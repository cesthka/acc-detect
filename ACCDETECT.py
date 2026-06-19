"""
================================================================================
  BOT DISCORD - DETECTION DE COMPTES RARES
  buyer/owner · base SQLite · !set interactif · emojis perso · niveau de rarete
================================================================================
"""

import os
import datetime
import sqlite3
import discord
from discord.ext import commands

# Detection de vrais mots (FR/EN) via wordfreq. Si la lib manque, on desactive
# juste ce critere sans planter le bot.
try:
    from wordfreq import zipf_frequency
    WORDFREQ_OK = True
except ImportError:
    WORDFREQ_OK = False

# ==============================================================================
#  REGLAGES DE BASE  --  A MODIFIER
# ==============================================================================

BUYER_ID = 142365250803466240
TOKEN = os.environ.get("DISCORD_TOKEN", "COLLE_TON_TOKEN_ICI_SI_TU_VEUX")
DB_PATH = os.environ.get("DB_PATH", "bot.db")

# Seuil au-dessus duquel un pseudo est considere comme un "vrai mot".
SEUIL_MOT = 2.5

OG_SEUILS = [
    ("og2016", datetime.datetime(2016, 1, 1, tzinfo=datetime.timezone.utc)),
    ("og2017", datetime.datetime(2017, 1, 1, tzinfo=datetime.timezone.utc)),
    ("og2018", datetime.datetime(2018, 1, 1, tzinfo=datetime.timezone.utc)),
]

# ==============================================================================
#  CATALOGUE DES ELEMENTS
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
    "og2016":     {"label": "OG - compte avant 2016",     "type": "role"},
    "og2017":     {"label": "OG - compte avant 2017",     "type": "role"},
    "og2018":     {"label": "OG - compte avant 2018",     "type": "role"},
    "pseudo2":    {"label": "Pseudo de 2 caracteres",     "type": "role"},
    "pseudo3":    {"label": "Pseudo de 3 caracteres",     "type": "role"},
    "mot":        {"label": "Pseudo : vrai mot (FR/EN)",  "type": "role"},
    "chiffres":   {"label": "Pseudo : que des chiffres",  "type": "role"},
    "logs":       {"label": "Salon de logs (joins)",      "type": "channel"},
    "scanlog":    {"label": "Salon de scan",              "type": "channel"},
}

CATEGORIES = {
    "🏅 Badges":     ["early", "hypesquad", "bravery", "brilliance", "balance",
                      "bughunter", "bughunter2", "botdev", "mod", "partner", "staff"],
    "📅 Anciennete": ["og2016", "og2017", "og2018"],
    "✨ Pseudo":     ["pseudo2", "pseudo3", "mot", "chiffres"],
    "📋 Salons":     ["logs", "scanlog"],
}

# Cles "detectables" (utilisables pour scan/list/emoji) = tout sauf les salons.
DETECT_KEYS = [k for k, v in SET_ITEMS.items() if v["type"] == "role"]

# Emojis par defaut (remplaçables par !setemoji avec tes propres emojis).
DEFAULT_EMOJIS = {
    "early": "🥇", "hypesquad": "🎉", "bravery": "🛡️", "brilliance": "🔮",
    "balance": "⚖️", "bughunter": "🐛", "bughunter2": "🐛", "botdev": "🤖",
    "mod": "🛡️", "partner": "🤝", "staff": "👑",
    "og2016": "📅", "og2017": "📅", "og2018": "📅",
    "pseudo2": "✨", "pseudo3": "✨", "mot": "🔤", "chiffres": "🔢",
}

JOIN_TITRE_DEFAUT = "🌟 Un compte rare a rejoint le serveur !"

# Poids pour le calcul du niveau de rarete.
POIDS = {
    "staff": 6, "partner": 5, "botdev": 4, "bughunter2": 4, "mod": 3, "bughunter": 3,
    "hypesquad": 2, "early": 2, "bravery": 1, "brilliance": 1, "balance": 1,
    "og2016": 3, "og2017": 2, "og2018": 1,
    "pseudo2": 3, "pseudo3": 2, "mot": 2, "chiffres": 1,
}

# Paliers de niveau : (score minimum, nom, couleur).
NIVEAUX = [
    (0,  "Commun",      discord.Color.light_grey()),
    (1,  "Peu commun",  discord.Color.green()),
    (3,  "Rare",        discord.Color.blue()),
    (5,  "Epique",      discord.Color.purple()),
    (8,  "Legendaire",  discord.Color.gold()),
    (12, "Mythique",    discord.Color.red()),
]

# ==============================================================================
#  BASE DE DONNEES (SQLite)
# ==============================================================================

def db():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = db()
    conn.execute("CREATE TABLE IF NOT EXISTS config   (key TEXT PRIMARY KEY, value INTEGER)")
    conn.execute("CREATE TABLE IF NOT EXISTS owners   (user_id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS emojis   (key TEXT PRIMARY KEY, emoji TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS messages (key TEXT PRIMARY KEY, contenu TEXT)")
    conn.commit()
    conn.close()


def _charger(table, cols):
    conn = db()
    rows = conn.execute(f"SELECT {cols[0]}, {cols[1]} FROM {table}").fetchall()
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
    conn = db()
    rows = conn.execute("SELECT user_id FROM owners").fetchall()
    conn.close()
    return {r[0] for r in rows}


def ajouter_owner(uid):
    conn = db(); conn.execute("INSERT OR IGNORE INTO owners (user_id) VALUES (?)", (uid,))
    conn.commit(); conn.close(); OWNERS.add(uid)


def retirer_owner(uid):
    conn = db(); conn.execute("DELETE FROM owners WHERE user_id = ?", (uid,))
    conn.commit(); conn.close(); OWNERS.discard(uid)


init_db()
CONFIG = _charger("config", ("key", "value"))
EMOJIS = _charger("emojis", ("key", "emoji"))
MESSAGES = _charger("messages", ("key", "contenu"))
OWNERS = charger_owners()


def emoji_de(key):
    return EMOJIS.get(key) or DEFAULT_EMOJIS.get(key, "•")


def message_de(key, defaut):
    return MESSAGES.get(key, defaut)


# ==============================================================================
#  HIERARCHIE / PERMISSIONS
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
    cree = user.created_at
    for key, limite in OG_SEUILS:
        if cree < limite:
            return key
    return None


def est_mot(nom):
    if not WORDFREQ_OK or not nom.isalpha() or len(nom) < 3:
        return False
    return zipf_frequency(nom, "fr") >= SEUIL_MOT or zipf_frequency(nom, "en") >= SEUIL_MOT


def detecter_pseudo(user):
    """Pseudo rare = 2 ou 3 caracteres, OU un vrai mot, OU que des chiffres.
    (Un pseudo "que des lettres" sans etre un mot n'est PAS considere rare.)"""
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


OG_THRESHOLDS = dict(OG_SEUILS)


def membre_a_cle(member, key):
    if key in OG_THRESHOLDS:
        return member.created_at < OG_THRESHOLDS[key]
    if key in ("pseudo2", "pseudo3", "mot", "chiffres"):
        return key in detecter_pseudo(member)
    return key in detecter_badges(member)


def membres_avec(guild, key):
    return [m for m in guild.members if not m.bot and membre_a_cle(m, key)]


async def appliquer_roles(member):
    infos = {
        "badges": detecter_badges(member),
        "pseudo": detecter_pseudo(member),
        "anciennete": detecter_anciennete(member),
        "erreurs": [],
    }
    cles = list(infos["badges"]) + list(infos["pseudo"])
    if infos["anciennete"]:
        cles.append(infos["anciennete"])
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


# ==============================================================================
#  NIVEAU DE RARETE
# ==============================================================================

def score_rarete(infos):
    s = sum(POIDS.get(b, 0) for b in infos["badges"])
    s += sum(POIDS.get(p, 0) for p in infos["pseudo"])
    if infos["anciennete"]:
        s += POIDS.get(infos["anciennete"], 0)
    return s


def niveau_rarete(infos):
    s = score_rarete(infos)
    nom, couleur = NIVEAUX[0][1], NIVEAUX[0][2]
    for seuil, n, c in NIVEAUX:
        if s >= seuil:
            nom, couleur = n, c
    return s, nom, couleur


# ==============================================================================
#  CONSTRUCTION DES EMBEDS DE PROFIL (join + check)
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
                    inline=False)

    if infos["badges"]:
        liste = "\n".join(f"{emoji_de(b)} {SET_ITEMS[b]['label']}" for b in infos["badges"])
    else:
        liste = "Aucun badge rare"
    embed.add_field(name="🏅 Badges", value=liste, inline=False)

    elements_pseudo = list(infos["pseudo"])
    if infos["anciennete"]:
        elements_pseudo.append(infos["anciennete"])
    if elements_pseudo:
        details = ", ".join(f"{emoji_de(k)} {SET_ITEMS[k]['label']}" for k in elements_pseudo)
        embed.add_field(name="✨ Particularites", value=details, inline=False)

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
    log_id = CONFIG.get("logs", 0)
    if not log_id:
        return
    salon = guild.get_channel(log_id)
    if salon is None:
        return
    titre = message_de("join", JOIN_TITRE_DEFAUT)
    embed = embed_profil(member, infos, titre)
    embed.set_footer(text=guild.name)
    await ajouter_banniere(embed, member)
    try:
        await salon.send(embed=embed)
    except discord.HTTPException:
        pass


# ==============================================================================
#  VUES INTERACTIVES
# ==============================================================================

def valeur_affichee(guild, key):
    rid = CONFIG.get(key, 0)
    if not rid:
        return "*non defini*"
    if SET_ITEMS[key]["type"] == "channel":
        ch = guild.get_channel(rid)
        return ch.mention if ch else "*salon introuvable*"
    role = guild.get_role(rid)
    return role.mention if role else "*role introuvable*"


def embed_config(guild):
    embed = discord.Embed(title="⚙️ Configuration du bot",
                          description="Choisis un element dans le menu, puis le role/salon a lui associer.",
                          color=discord.Color.blurple())
    for cat, keys in CATEGORIES.items():
        lignes = []
        for k in keys:
            prefixe = emoji_de(k) + " " if k in DEFAULT_EMOJIS else ""
            lignes.append(f"{prefixe}**{SET_ITEMS[k]['label']}** → {valeur_affichee(guild, k)}")
        embed.add_field(name=cat, value="\n".join(lignes), inline=False)
    embed.set_footer(text="Reglages sauvegardes dans la base de donnees")
    return embed


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


# --- !set --------------------------------------------------------------------

class ItemSelect(discord.ui.Select):
    def __init__(self):
        options = []
        for cat, keys in CATEGORIES.items():
            for key in keys:
                options.append(discord.SelectOption(label=SET_ITEMS[key]["label"], value=key, description=cat))
        super().__init__(placeholder="Choisis l'element a configurer…", options=options)

    async def callback(self, interaction):
        await self.view.ouvrir_selection(interaction, self.values[0])


class ConfigView(AuthorView):
    def __init__(self, author, guild):
        super().__init__(author, guild)
        self.add_item(ItemSelect())

    async def ouvrir_selection(self, interaction, key):
        it = SET_ITEMS[key]
        if it["type"] == "channel":
            view = ChannelPickView(self.author, self.guild, key)
            desc = "Choisis le salon ci-dessous (tape pour rechercher)."
        else:
            view = RolePickView(self.author, self.guild, key)
            desc = "Choisis le role ci-dessous (tape pour rechercher)."
        embed = discord.Embed(title=f"Configurer : {it['label']}", description=desc, color=discord.Color.blurple())
        await interaction.response.edit_message(embed=embed, view=view)


class RetourBouton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="◀ Retour a la config", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction):
        await interaction.response.edit_message(embed=embed_config(self.view.guild),
                                                view=ConfigView(self.view.author, self.view.guild))


class RolePicker(discord.ui.RoleSelect):
    def __init__(self, key):
        self.key = key
        super().__init__(placeholder="Recherche et choisis un role…", min_values=1, max_values=1)

    async def callback(self, interaction):
        role = self.values[0]
        definir_config(self.key, role.id)
        embed = discord.Embed(title="✅ Effectue",
                              description=f"**{SET_ITEMS[self.key]['label']}** est lie a {role.mention}.",
                              color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=RetourView(self.view.author, self.view.guild))


class RolePickView(AuthorView):
    def __init__(self, author, guild, key):
        super().__init__(author, guild)
        self.add_item(RolePicker(key))
        self.add_item(RetourBouton())


class ChannelPicker(discord.ui.ChannelSelect):
    def __init__(self, key):
        self.key = key
        super().__init__(placeholder="Recherche et choisis un salon…",
                         channel_types=[discord.ChannelType.text], min_values=1, max_values=1)

    async def callback(self, interaction):
        salon = self.values[0]
        definir_config(self.key, salon.id)
        embed = discord.Embed(title="✅ Effectue",
                              description=f"**{SET_ITEMS[self.key]['label']}** est lie a {salon.mention}.",
                              color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=RetourView(self.view.author, self.view.guild))


class ChannelPickView(AuthorView):
    def __init__(self, author, guild, key):
        super().__init__(author, guild)
        self.add_item(ChannelPicker(key))
        self.add_item(RetourBouton())


class RetourView(AuthorView):
    def __init__(self, author, guild):
        super().__init__(author, guild)
        self.add_item(RetourBouton())


# --- Pagination (list + scan) ------------------------------------------------

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


class ListView(AuthorView):
    PAR_PAGE = 10

    def __init__(self, author, guild, key, membres):
        super().__init__(author, guild)
        self.key = key
        self.membres = membres
        self.page = 0
        self.total_pages = max(1, (len(membres) + self.PAR_PAGE - 1) // self.PAR_PAGE)
        self.prev = PrevButton()
        self.next = NextButton()
        self.add_item(self.prev)
        self.add_item(self.next)
        self._maj()

    def _maj(self):
        self.prev.disabled = self.page == 0
        self.next.disabled = self.page >= self.total_pages - 1

    def embed_courant(self):
        debut = self.page * self.PAR_PAGE
        lot = self.membres[debut:debut + self.PAR_PAGE]
        lignes = [f"{m.mention} / `{m.id}`" for m in lot]
        embed = discord.Embed(
            title=f"{emoji_de(self.key)} {SET_ITEMS[self.key]['label']} — {len(self.membres)} personne(s)",
            description="\n".join(lignes) if lignes else "Personne.",
            color=discord.Color.blurple())
        embed.set_footer(text=f"Page {self.page + 1}/{self.total_pages}")
        return embed

    async def changer_page(self, interaction, delta):
        self.page = max(0, min(self.total_pages - 1, self.page + delta))
        self._maj()
        await interaction.response.edit_message(embed=self.embed_courant(), view=self)


# --- !scan interactif --------------------------------------------------------

class ScanSelect(discord.ui.Select):
    def __init__(self):
        options = []
        for cat, keys in CATEGORIES.items():
            for key in keys:
                if SET_ITEMS[key]["type"] == "role":  # on ne scanne pas les salons
                    options.append(discord.SelectOption(label=SET_ITEMS[key]["label"], value=key, description=cat))
        super().__init__(placeholder="Choisis une categorie a scanner…", options=options)

    async def callback(self, interaction):
        key = self.values[0]
        membres = membres_avec(self.view.guild, key)
        if not membres:
            await interaction.response.edit_message(
                embed=discord.Embed(description=f"Personne ne correspond a **{SET_ITEMS[key]['label']}**.",
                                    color=discord.Color.orange()),
                view=ScanView(self.view.author, self.view.guild))
            return

        liste = ListView(self.view.author, self.view.guild, key, membres)
        scan_id = CONFIG.get("scanlog", 0)
        salon = self.view.guild.get_channel(scan_id) if scan_id else None

        if salon:
            await salon.send(embed=liste.embed_courant(), view=liste if liste.total_pages > 1 else None)
            await interaction.response.edit_message(
                embed=discord.Embed(description=f"✅ Resultat ({len(membres)}) envoye dans {salon.mention}.",
                                    color=discord.Color.green()),
                view=ScanView(self.view.author, self.view.guild))
        else:
            # Pas de salon de scan defini : on affiche directement ici.
            await interaction.response.edit_message(embed=liste.embed_courant(),
                                                    view=liste if liste.total_pages > 1 else None)


class ScanView(AuthorView):
    def __init__(self, author, guild):
        super().__init__(author, guild)
        self.add_item(ScanSelect())


def embed_scan_accueil():
    return discord.Embed(
        title="🔍 Scan par categorie",
        description=("Choisis une categorie dans le menu : le bot listera tous les membres concernes.\n"
                     "Le resultat est envoye dans le salon de scan (definis-le avec `!set` ou `!setscan`)."),
        color=discord.Color.blurple())


# --- !help -------------------------------------------------------------------

HELP_CATEGORIES = {
    "🔍 Detection": [
        ("!scan", "Menu pour lister les membres d'une categorie (vers le salon de scan)."),
        ("!check @membre", "Profil detaille d'un membre : badges, niveau, particularites."),
        ("!list <categorie>", "Liste les membres d'une categorie, par pages de 10."),
    ],
    "⚙️ Configuration": [
        ("!set", "Panneau interactif pour associer roles et salons."),
        ("!config", "Affiche la configuration actuelle."),
        ("!setlog #salon", "Definit le salon des logs (joins)."),
        ("!setscan #salon", "Definit le salon des resultats de scan."),
        ("!setemoji <cle> <emoji>", "Associe ton emoji perso a une categorie."),
        ("!setmsg <texte>", "Personnalise le titre du message de join."),
    ],
    "👑 Gestion": [
        ("!owner @membre", "Ajoute un owner. **Buyer uniquement.**"),
        ("!unowner @membre", "Retire un owner. **Buyer uniquement.**"),
        ("!owners", "Affiche le buyer et les owners."),
    ],
}


def embed_help_accueil():
    embed = discord.Embed(title="📖 Aide du bot",
                          description="Detecte les comptes rares et leur attribue des roles.\n\n"
                                      "Choisis une categorie dans le menu deroulant ci-dessous.",
                          color=discord.Color.blurple())
    embed.add_field(name="Categories", value="\n".join(f"• {c}" for c in HELP_CATEGORIES), inline=False)
    embed.set_footer(text="Les commandes de gestion sont reservees au buyer / aux owners.")
    return embed


def embed_help_categorie(cat):
    embed = discord.Embed(title=f"📖 Aide — {cat}", color=discord.Color.blurple())
    for nom, desc in HELP_CATEGORIES[cat]:
        embed.add_field(name=nom, value=desc, inline=False)
    return embed


class HelpSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label="Accueil", value="accueil", emoji="🏠")]
        for cat in HELP_CATEGORIES:
            options.append(discord.SelectOption(label=cat, value=cat))
        super().__init__(placeholder="Choisis une categorie…", options=options)

    async def callback(self, interaction):
        choix = self.values[0]
        embed = embed_help_accueil() if choix == "accueil" else embed_help_categorie(choix)
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(AuthorView):
    def __init__(self, author, guild):
        super().__init__(author, guild)
        self.add_item(HelpSelect())


# ==============================================================================
#  COMMANDES
# ==============================================================================

@bot.command(name="set")
@check_owner()
async def set_config(ctx):
    await ctx.send(embed=embed_config(ctx.guild), view=ConfigView(ctx.author, ctx.guild))


@bot.command(name="config")
@check_owner()
async def afficher_config(ctx):
    await ctx.send(embed=embed_config(ctx.guild))


@bot.command(name="setlog")
@check_owner()
async def setlog(ctx, salon: discord.TextChannel = None):
    salon = salon or ctx.channel
    definir_config("logs", salon.id)
    await ctx.send(embed=discord.Embed(title="✅ Salon de logs (joins) defini",
                                       description=f"Les joins rares seront annonces dans {salon.mention}.",
                                       color=discord.Color.green()))


@bot.command(name="setscan")
@check_owner()
async def setscan(ctx, salon: discord.TextChannel = None):
    salon = salon or ctx.channel
    definir_config("scanlog", salon.id)
    await ctx.send(embed=discord.Embed(title="✅ Salon de scan defini",
                                       description=f"Les resultats de scan seront envoyes dans {salon.mention}.",
                                       color=discord.Color.green()))


@bot.command(name="setemoji")
@check_owner()
async def setemoji(ctx, cle: str = None, emoji: str = None):
    if cle not in DEFAULT_EMOJIS or emoji is None:
        dispo = ", ".join(f"`{k}`" for k in DEFAULT_EMOJIS)
        await ctx.send(f"Utilisation : `!setemoji <cle> <emoji>`\nCles : {dispo}")
        return
    definir_emoji(cle, emoji)
    await ctx.send(embed=discord.Embed(title="✅ Emoji defini",
                                       description=f"**{SET_ITEMS[cle]['label']}** utilise maintenant {emoji}.",
                                       color=discord.Color.green()))


@bot.command(name="setmsg")
@check_owner()
async def setmsg(ctx, *, texte: str = None):
    if not texte:
        await ctx.send("Utilisation : `!setmsg <texte>` (titre du message de join).")
        return
    definir_message("join", texte)
    await ctx.send(embed=discord.Embed(title="✅ Message de join mis a jour",
                                       description=f"Nouveau titre : {texte}",
                                       color=discord.Color.green()))


@bot.command(name="scan")
@check_owner()
async def scan(ctx):
    await ctx.send(embed=embed_scan_accueil(), view=ScanView(ctx.author, ctx.guild))


@bot.command(name="check")
@check_owner()
async def check(ctx, member: discord.Member = None):
    member = member or ctx.author
    infos = {
        "badges": detecter_badges(member),
        "pseudo": detecter_pseudo(member),
        "anciennete": detecter_anciennete(member),
        "erreurs": [],
    }
    embed = embed_profil(member, infos, f"🔎 Analyse de {member.name}")
    await ajouter_banniere(embed, member)
    await ctx.send(embed=embed)


@bot.command(name="list")
@check_owner()
async def list_cmd(ctx, cle: str = None):
    if cle not in DETECT_KEYS:
        dispo = ", ".join(f"`{k}`" for k in DETECT_KEYS)
        await ctx.send(f"Utilisation : `!list <categorie>`\nCategories : {dispo}")
        return
    membres = membres_avec(ctx.guild, cle)
    if not membres:
        await ctx.send(f"Personne ne correspond a **{SET_ITEMS[cle]['label']}**.")
        return
    view = ListView(ctx.author, ctx.guild, cle, membres)
    if view.total_pages == 1:
        await ctx.send(embed=view.embed_courant())
    else:
        await ctx.send(embed=view.embed_courant(), view=view)


@bot.command(name="owner")
@check_buyer()
async def owner_cmd(ctx, membre: discord.User):
    if membre.id == BUYER_ID:
        await ctx.send("Tu es le buyer : tu as deja tous les droits."); return
    if membre.id in OWNERS:
        await ctx.send(f"{membre.mention} est deja owner."); return
    ajouter_owner(membre.id)
    await ctx.send(embed=discord.Embed(title="✅ Owner ajoute",
                                       description=f"{membre.mention} (`{membre.id}`) est maintenant owner.",
                                       color=discord.Color.green()))


@bot.command(name="unowner")
@check_buyer()
async def unowner_cmd(ctx, membre: discord.User):
    if membre.id == BUYER_ID:
        await ctx.send("Le buyer ne peut pas etre retire."); return
    if membre.id not in OWNERS:
        await ctx.send(f"{membre.mention} n'est pas owner."); return
    retirer_owner(membre.id)
    await ctx.send(embed=discord.Embed(title="✅ Owner retire",
                                       description=f"{membre.mention} n'est plus owner.",
                                       color=discord.Color.orange()))


@bot.command(name="owners")
@check_owner()
async def owners_cmd(ctx):
    lignes = [f"👑 <@{BUYER_ID}> — **Buyer**"]
    lignes += [f"• <@{uid}>" for uid in OWNERS] or ["*(aucun owner)*"]
    await ctx.send(embed=discord.Embed(title="Hierarchie du bot", description="\n".join(lignes),
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
        await ctx.send("⛔ Tu n'as pas l'autorisation d'utiliser cette commande.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Argument manquant. Ex : `!owner @membre`.")
    elif isinstance(error, (commands.UserNotFound, commands.MemberNotFound,
                            commands.ChannelNotFound, commands.BadArgument)):
        await ctx.send("Argument invalide (utilisateur/salon introuvable).")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        raise error


@bot.event
async def on_ready():
    print(f"Bot connecte en tant que {bot.user} (id {bot.user.id})")
    if not WORDFREQ_OK:
        print("/!\\ wordfreq non installe : la detection des vrais mots est desactivee.")
    print(f"Buyer : {BUYER_ID} | Owners : {len(OWNERS)}")


@bot.event
async def on_member_join(member):
    if member.bot:
        return
    infos = await appliquer_roles(member)
    if infos["badges"] or infos["pseudo"] or infos["anciennete"]:
        await envoyer_log_join(member.guild, member, infos)


if __name__ == "__main__":
    if not TOKEN or TOKEN == "COLLE_TON_TOKEN_ICI_SI_TU_VEUX":
        raise SystemExit("Aucun token. Definis DISCORD_TOKEN ou colle-le dans TOKEN.")
    bot.run(TOKEN)
