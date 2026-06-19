"""
================================================================================
  BOT DISCORD - DETECTION DE COMPTES RARES
  + systeme !set interactif  + systeme buyer/owner  + base SQLite persistante
================================================================================
- Detecte les comptes rares (badges, anciennete, pseudos rares) et attribue des
  roles automatiquement.
- Se configure depuis Discord avec !set (menu deroulant + selecteur de role).
- Hierarchie : 1 BUYER (toi, en dur dans le code, immuable) > des OWNERS (ajoutes
  par le buyer uniquement) > tout le monde.
- Toutes les donnees (config + owners) sont stockees dans une base SQLite, afin
  de survivre aux redeploiements (notamment sur Railway via un Volume).

------------------------------------------------------------------------------
  A FAIRE AVANT DE LANCER :
    1. Remplace BUYER_ID ci-dessous par TON identifiant Discord.
    2. pip install -U discord.py        (2.1 minimum, pour RoleSelect)
    3. Active "SERVER MEMBERS INTENT" dans le portail developpeur.
    4. Fournis le token via la variable d'environnement DISCORD_TOKEN.
    5. (Hosting Railway) cree un Volume, monte-le sur /data, et mets la variable
       d'environnement DB_PATH = /data/bot.db  (voir le README).
    6. python bot_comptes_rares.py
================================================================================
"""

import os
import datetime
import sqlite3
import discord
from discord.ext import commands

# ==============================================================================
#  REGLAGES DE BASE  --  A MODIFIER
# ==============================================================================

# >>> REMPLACE ce nombre par TON identifiant Discord. Toi seul es le buyer. <<<
# (Mode developpeur active > clic droit sur ton profil > Copier l'identifiant)
BUYER_ID = 123456789012345678

# Token : laisse-le dans la variable d'environnement DISCORD_TOKEN (recommande,
# surtout si tu mets le code sur GitHub : ne JAMAIS commit ton token).
TOKEN = os.environ.get("DISCORD_TOKEN", "COLLE_TON_TOKEN_ICI_SI_TU_VEUX")

# Chemin de la base de donnees. En local "bot.db" suffit. Sur Railway, pointe-le
# vers ton volume (ex: DB_PATH=/data/bot.db) pour que les donnees persistent.
DB_PATH = os.environ.get("DB_PATH", "bot.db")

# Seuils de date pour l'anciennete (le role associe se regle via !set).
OG_SEUILS = [
    ("og2016", datetime.datetime(2016, 1, 1, tzinfo=datetime.timezone.utc)),
    ("og2017", datetime.datetime(2017, 1, 1, tzinfo=datetime.timezone.utc)),
    ("og2018", datetime.datetime(2018, 1, 1, tzinfo=datetime.timezone.utc)),
]

# ==============================================================================
#  CATALOGUE DES ELEMENTS CONFIGURABLES
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
    "lettres":    {"label": "Pseudo : que des lettres",   "type": "role"},
    "chiffres":   {"label": "Pseudo : que des chiffres",  "type": "role"},
    "logs":       {"label": "Salon de logs",              "type": "channel"},
}

CATEGORIES = {
    "🏅 Badges":     ["early", "hypesquad", "bravery", "brilliance", "balance",
                      "bughunter", "bughunter2", "botdev", "mod", "partner", "staff"],
    "📅 Anciennete": ["og2016", "og2017", "og2018"],
    "✨ Pseudo":     ["pseudo2", "pseudo3", "lettres", "chiffres"],
    "📋 Salon":      ["logs"],
}

BADGE_EMOJIS = {
    "early": "🥇", "hypesquad": "🎉", "bravery": "🛡️", "brilliance": "🔮",
    "balance": "⚖️", "bughunter": "🐛", "bughunter2": "🐛", "botdev": "🤖",
    "mod": "🛡️", "partner": "🤝", "staff": "👑",
}

# ==============================================================================
#  BASE DE DONNEES (SQLite)
# ==============================================================================

def db():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = db()
    conn.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value INTEGER)")
    conn.execute("CREATE TABLE IF NOT EXISTS owners (user_id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()


def charger_config() -> dict:
    conn = db()
    rows = conn.execute("SELECT key, value FROM config").fetchall()
    conn.close()
    return {k: v for k, v in rows}


def definir_config(key: str, value: int):
    CONFIG[key] = value
    conn = db()
    conn.execute(
        "INSERT INTO config (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def charger_owners() -> set:
    conn = db()
    rows = conn.execute("SELECT user_id FROM owners").fetchall()
    conn.close()
    return {r[0] for r in rows}


def ajouter_owner(uid: int):
    conn = db()
    conn.execute("INSERT OR IGNORE INTO owners (user_id) VALUES (?)", (uid,))
    conn.commit()
    conn.close()
    OWNERS.add(uid)


def retirer_owner(uid: int):
    conn = db()
    conn.execute("DELETE FROM owners WHERE user_id = ?", (uid,))
    conn.commit()
    conn.close()
    OWNERS.discard(uid)


init_db()
CONFIG = charger_config()   # { "early": role_id, ..., "logs": channel_id }
OWNERS = charger_owners()   # { user_id, ... }  (le buyer n'y figure pas, il est en dur)


# ==============================================================================
#  HIERARCHIE / PERMISSIONS
# ==============================================================================

def est_buyer(uid: int) -> bool:
    return uid == BUYER_ID


def est_owner(uid: int) -> bool:
    return uid == BUYER_ID or uid in OWNERS


def check_buyer():
    async def predicate(ctx: commands.Context) -> bool:
        return est_buyer(ctx.author.id)
    return commands.check(predicate)


def check_owner():
    async def predicate(ctx: commands.Context) -> bool:
        return est_owner(ctx.author.id)
    return commands.check(predicate)


# ==============================================================================
#  BOT
# ==============================================================================

intents = discord.Intents.default()
intents.members = True          # OBLIGATOIRE (Server Members Intent)
intents.message_content = True  # OBLIGATOIRE pour lire les commandes en "!" (Message Content Intent)

bot = commands.Bot(command_prefix="!", intents=intents)


# ==============================================================================
#  DETECTION
# ==============================================================================

def detecter_badges(user: discord.User) -> list[str]:
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


def detecter_anciennete(user: discord.User) -> str | None:
    cree = user.created_at
    for key, limite in OG_SEUILS:
        if cree < limite:
            return key
    return None


def detecter_pseudo(user: discord.User) -> list[str]:
    nom = user.name
    out = []
    if len(nom) == 2:
        out.append("pseudo2")
    elif len(nom) == 3:
        out.append("pseudo3")
    if nom.isalpha():
        out.append("lettres")
    if nom.isdigit():
        out.append("chiffres")
    return out


# Seuils d'anciennete sous forme de dictionnaire { "og2016": datetime, ... }
OG_THRESHOLDS = dict(OG_SEUILS)

# Cles utilisables avec !list (tout sauf le salon de logs).
DETECT_KEYS = [k for k in SET_ITEMS if k != "logs"]


def membre_a_cle(member: discord.Member, key: str) -> bool:
    """Dit si un membre correspond a une categorie donnee.
    Pour l'anciennete, c'est cumulatif : og2018 = tout compte cree avant 2018."""
    if key in OG_THRESHOLDS:
        return member.created_at < OG_THRESHOLDS[key]
    if key in ("pseudo2", "pseudo3", "lettres", "chiffres"):
        return key in detecter_pseudo(member)
    return key in detecter_badges(member)


def membres_avec(guild: discord.Guild, key: str) -> list[discord.Member]:
    return [m for m in guild.members if not m.bot and membre_a_cle(m, key)]


async def appliquer_roles(member: discord.Member) -> dict:
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

    roles_objets = []
    for rid in role_ids:
        role = member.guild.get_role(rid)
        if role and role not in member.roles:
            roles_objets.append(role)

    if roles_objets:
        try:
            await member.add_roles(*roles_objets, reason="Compte rare detecte")
        except discord.Forbidden:
            infos["erreurs"].append(
                "Le bot n'a pas la permission 'Gerer les roles', ou son role est trop bas."
            )
        except discord.HTTPException as e:
            infos["erreurs"].append(f"Erreur API : {e}")
    return infos


# ==============================================================================
#  LOGS
# ==============================================================================

async def envoyer_log(guild: discord.Guild, member: discord.Member, infos: dict):
    log_id = CONFIG.get("logs", 0)
    if not log_id:
        return
    salon = guild.get_channel(log_id)
    if salon is None:
        return

    nb_badges = len(infos["badges"])
    if nb_badges >= 2 or "staff" in infos["badges"] or "partner" in infos["badges"]:
        couleur = discord.Color.gold()
    elif nb_badges == 1:
        couleur = discord.Color.purple()
    elif infos["pseudo"]:
        couleur = discord.Color.green()
    else:
        couleur = discord.Color.blue()

    maintenant = datetime.datetime.now(datetime.timezone.utc)
    age = maintenant - member.created_at
    annees, jours = age.days // 365, age.days % 365
    cree_ts = int(member.created_at.timestamp())

    embed = discord.Embed(title="🌟 Un compte rare a rejoint le serveur !",
                          color=couleur, timestamp=maintenant)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Utilisateur", value=f"{member.mention}\n`{member.name}`", inline=True)
    embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)
    embed.add_field(name="📅 Compte cree",
                    value=f"<t:{cree_ts}:D>\n(il y a {annees} an(s) et {jours} jour(s))", inline=True)
    if member.joined_at:
        embed.add_field(name="📥 A rejoint", value=f"<t:{int(member.joined_at.timestamp())}:R>", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    if infos["badges"]:
        liste = "\n".join(f"{BADGE_EMOJIS.get(b, '•')} {SET_ITEMS[b]['label']}" for b in infos["badges"])
    else:
        liste = "Aucun badge rare"
    embed.add_field(name="🏅 Badges", value=liste, inline=False)

    if infos["pseudo"]:
        details = ", ".join(SET_ITEMS[p]["label"] for p in infos["pseudo"])
        embed.add_field(name="✨ Pseudo rare", value=f"✅ OUI — {details}", inline=False)
    else:
        embed.add_field(name="✨ Pseudo rare", value="❌ Non", inline=False)

    if infos["erreurs"]:
        embed.add_field(name="⚠️ Attention", value="\n".join(infos["erreurs"]), inline=False)

    embed.set_footer(text=guild.name)
    try:
        user_complet = await bot.fetch_user(member.id)
        if user_complet.banner:
            embed.set_image(url=user_complet.banner.url)
    except Exception:
        pass
    try:
        await salon.send(embed=embed)
    except discord.HTTPException:
        pass


# ==============================================================================
#  SYSTEME !set INTERACTIF
# ==============================================================================

def valeur_affichee(guild: discord.Guild, key: str) -> str:
    rid = CONFIG.get(key, 0)
    if not rid:
        return "*non defini*"
    if SET_ITEMS[key]["type"] == "channel":
        ch = guild.get_channel(rid)
        return ch.mention if ch else "*salon introuvable*"
    role = guild.get_role(rid)
    return role.mention if role else "*role introuvable*"


def embed_config(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="⚙️ Configuration du bot",
        description="Choisis un element dans le menu, puis selectionne le role (ou le salon) a lui associer.",
        color=discord.Color.blurple(),
    )
    for cat, keys in CATEGORIES.items():
        lignes = [f"**{SET_ITEMS[k]['label']}** → {valeur_affichee(guild, k)}" for k in keys]
        embed.add_field(name=cat, value="\n".join(lignes), inline=False)
    embed.set_footer(text="Reglages sauvegardes dans la base de donnees")
    return embed


class AuthorView(discord.ui.View):
    def __init__(self, author, guild, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.author = author
        self.guild = guild

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Ce menu n'est pas pour toi 🙂", ephemeral=True)
            return False
        return True


class ItemSelect(discord.ui.Select):
    def __init__(self):
        options = []
        for cat, keys in CATEGORIES.items():
            for key in keys:
                options.append(discord.SelectOption(
                    label=SET_ITEMS[key]["label"], value=key, description=cat))
        super().__init__(placeholder="Choisis l'element a configurer…", options=options,
                         min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        await self.view.ouvrir_selection(interaction, self.values[0])


class ConfigView(AuthorView):
    def __init__(self, author, guild):
        super().__init__(author, guild)
        self.add_item(ItemSelect())

    async def ouvrir_selection(self, interaction: discord.Interaction, key: str):
        it = SET_ITEMS[key]
        if it["type"] == "channel":
            view = ChannelPickView(self.author, self.guild, key)
            desc = "Choisis le salon ci-dessous (tape pour rechercher)."
        else:
            view = RolePickView(self.author, self.guild, key)
            desc = "Choisis le role ci-dessous (tape pour rechercher)."
        embed = discord.Embed(title=f"Configurer : {it['label']}", description=desc,
                              color=discord.Color.blurple())
        await interaction.response.edit_message(embed=embed, view=view)


class RetourBouton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="◀ Retour a la config", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=embed_config(self.view.guild),
            view=ConfigView(self.view.author, self.view.guild),
        )


class RolePicker(discord.ui.RoleSelect):
    def __init__(self, key: str):
        self.key = key
        super().__init__(placeholder="Recherche et choisis un role…", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        definir_config(self.key, role.id)
        embed = discord.Embed(title="✅ Effectue",
                              description=f"**{SET_ITEMS[self.key]['label']}** est lie a {role.mention}.",
                              color=discord.Color.green())
        await interaction.response.edit_message(
            embed=embed, view=RetourView(self.view.author, self.view.guild))


class RolePickView(AuthorView):
    def __init__(self, author, guild, key):
        super().__init__(author, guild)
        self.add_item(RolePicker(key))
        self.add_item(RetourBouton())


class ChannelPicker(discord.ui.ChannelSelect):
    def __init__(self, key: str):
        self.key = key
        super().__init__(placeholder="Recherche et choisis un salon…",
                         channel_types=[discord.ChannelType.text], min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        salon = self.values[0]
        definir_config(self.key, salon.id)
        embed = discord.Embed(title="✅ Effectue",
                              description=f"**{SET_ITEMS[self.key]['label']}** est lie a {salon.mention}.",
                              color=discord.Color.green())
        await interaction.response.edit_message(
            embed=embed, view=RetourView(self.view.author, self.view.guild))


class ChannelPickView(AuthorView):
    def __init__(self, author, guild, key):
        super().__init__(author, guild)
        self.add_item(ChannelPicker(key))
        self.add_item(RetourBouton())


class RetourView(AuthorView):
    def __init__(self, author, guild):
        super().__init__(author, guild)
        self.add_item(RetourBouton())


# --- Pagination pour !list ---------------------------------------------------

class PrevButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="◀ Precedent", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        await self.view.changer_page(interaction, -1)


class NextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Suivant ▶", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
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
        self._maj_boutons()

    def _maj_boutons(self):
        self.prev.disabled = self.page == 0
        self.next.disabled = self.page >= self.total_pages - 1

    def embed_courant(self) -> discord.Embed:
        debut = self.page * self.PAR_PAGE
        lot = self.membres[debut:debut + self.PAR_PAGE]
        lignes = [f"{m.mention} / `{m.id}`" for m in lot]
        embed = discord.Embed(
            title=f"{SET_ITEMS[self.key]['label']} — {len(self.membres)} personne(s)",
            description="\n".join(lignes) if lignes else "Personne.",
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"Page {self.page + 1}/{self.total_pages}")
        return embed

    async def changer_page(self, interaction: discord.Interaction, delta: int):
        self.page = max(0, min(self.total_pages - 1, self.page + delta))
        self._maj_boutons()
        await interaction.response.edit_message(embed=self.embed_courant(), view=self)


# ==============================================================================
#  COMMANDES - CONFIGURATION (owners)
# ==============================================================================

@bot.command(name="set")
@check_owner()
async def set_config(ctx: commands.Context):
    """Panneau de configuration interactif. Reserve aux owners (et au buyer)."""
    await ctx.send(embed=embed_config(ctx.guild), view=ConfigView(ctx.author, ctx.guild))


@bot.command(name="config")
@check_owner()
async def afficher_config(ctx: commands.Context):
    """Affiche la configuration actuelle (lecture seule)."""
    await ctx.send(embed=embed_config(ctx.guild))


@bot.command(name="scan")
@check_owner()
async def scan(ctx: commands.Context):
    """Re-analyse tous les membres deja presents."""
    await ctx.send("Scan en cours...")
    compte = 0
    for member in ctx.guild.members:
        if member.bot:
            continue
        infos = await appliquer_roles(member)
        if infos["badges"] or infos["pseudo"] or infos["anciennete"]:
            compte += 1
            await envoyer_log(ctx.guild, member, infos)
    await ctx.send(f"Scan termine. {compte} compte(s) rare(s) trouve(s).")


@bot.command(name="check")
@check_owner()
async def check(ctx: commands.Context, member: discord.Member = None):
    """Affiche la detection pour un membre, sans attribuer de role."""
    member = member or ctx.author
    badges = detecter_badges(member)
    pseudo = detecter_pseudo(member)
    embed = discord.Embed(title=f"Analyse de {member.name}", color=discord.Color.blurple())
    embed.add_field(name="Cree le", value=str(member.created_at.date()), inline=False)
    embed.add_field(name="Badges", value=", ".join(SET_ITEMS[b]["label"] for b in badges) or "aucun", inline=False)
    embed.add_field(name="Pseudo", value=", ".join(SET_ITEMS[p]["label"] for p in pseudo) or "rien", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="setlog")
@check_owner()
async def setlog(ctx: commands.Context, salon: discord.TextChannel = None):
    """Definit le salon de logs. Ex: !setlog #salon  (ou !setlog dans le salon voulu)."""
    salon = salon or ctx.channel
    definir_config("logs", salon.id)
    embed = discord.Embed(
        title="✅ Salon de logs defini",
        description=f"Les comptes rares seront annonces dans {salon.mention}.",
        color=discord.Color.green(),
    )
    await ctx.send(embed=embed)


@bot.command(name="list")
@check_owner()
async def list_cmd(ctx: commands.Context, cle: str = None):
    """Liste les membres d'une categorie, par pages de 10. Ex: !list early"""
    if cle not in DETECT_KEYS:
        dispo = ", ".join(f"`{k}`" for k in DETECT_KEYS)
        await ctx.send(f"Utilisation : `!list <categorie>`\nCategories possibles : {dispo}")
        return

    membres = membres_avec(ctx.guild, cle)
    if not membres:
        await ctx.send(f"Personne ne correspond a **{SET_ITEMS[cle]['label']}**.")
        return

    view = ListView(ctx.author, ctx.guild, cle, membres)
    if view.total_pages == 1:
        await ctx.send(embed=view.embed_courant())  # une seule page : pas besoin de boutons
    else:
        await ctx.send(embed=view.embed_courant(), view=view)


# ==============================================================================
#  COMMANDES - GESTION DES OWNERS (buyer uniquement)
# ==============================================================================

@bot.command(name="owner")
@check_buyer()
async def owner_cmd(ctx: commands.Context, membre: discord.User):
    """Ajoute un owner. Reserve au buyer. Ex: !owner @membre  ou  !owner 123456789"""
    if membre.id == BUYER_ID:
        await ctx.send("Tu es le buyer : tu as deja tous les droits.")
        return
    if membre.id in OWNERS:
        await ctx.send(f"{membre.mention} est deja owner.")
        return
    ajouter_owner(membre.id)
    embed = discord.Embed(title="✅ Owner ajoute",
                          description=f"{membre.mention} (`{membre.id}`) est maintenant owner.",
                          color=discord.Color.green())
    await ctx.send(embed=embed)


@bot.command(name="unowner")
@check_buyer()
async def unowner_cmd(ctx: commands.Context, membre: discord.User):
    """Retire un owner. Reserve au buyer. Ex: !unowner @membre"""
    if membre.id == BUYER_ID:
        await ctx.send("Le buyer ne peut pas etre retire.")
        return
    if membre.id not in OWNERS:
        await ctx.send(f"{membre.mention} n'est pas owner.")
        return
    retirer_owner(membre.id)
    embed = discord.Embed(title="✅ Owner retire",
                          description=f"{membre.mention} (`{membre.id}`) n'est plus owner.",
                          color=discord.Color.orange())
    await ctx.send(embed=embed)


@bot.command(name="owners")
@check_owner()
async def owners_cmd(ctx: commands.Context):
    """Liste le buyer et les owners."""
    lignes = [f"👑 <@{BUYER_ID}> — **Buyer**"]
    if OWNERS:
        lignes += [f"• <@{uid}>" for uid in OWNERS]
    else:
        lignes.append("*(aucun owner pour l'instant)*")
    embed = discord.Embed(title="Hierarchie du bot", description="\n".join(lignes),
                          color=discord.Color.blurple())
    await ctx.send(embed=embed)


# ==============================================================================
#  GESTION DES ERREURS DE COMMANDES
# ==============================================================================

@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("⛔ Tu n'as pas l'autorisation d'utiliser cette commande.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Argument manquant. Exemple : `!owner @membre` ou `!owner 123456789`.")
    elif isinstance(error, (commands.UserNotFound, commands.MemberNotFound, commands.BadArgument)):
        await ctx.send("Utilisateur introuvable. Mentionne la personne ou donne son ID.")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        raise error


# ==============================================================================
#  EVENEMENTS
# ==============================================================================

@bot.event
async def on_ready():
    print(f"Bot connecte en tant que {bot.user} (id {bot.user.id})")
    if BUYER_ID == 123456789012345678:
        print("/!\\ ATTENTION : tu n'as pas remplace BUYER_ID par ton vrai identifiant Discord.")
    print(f"Buyer : {BUYER_ID} | Owners : {len(OWNERS)}")


@bot.event
async def on_member_join(member: discord.Member):
    if member.bot:
        return
    infos = await appliquer_roles(member)
    if infos["badges"] or infos["pseudo"] or infos["anciennete"]:
        await envoyer_log(member.guild, member, infos)


if __name__ == "__main__":
    if not TOKEN or TOKEN == "COLLE_TON_TOKEN_ICI_SI_TU_VEUX":
        raise SystemExit("Aucun token. Definis DISCORD_TOKEN ou colle-le dans TOKEN.")
    bot.run(TOKEN)
