import discord
from discord.ext import commands
from discord import ui
import json
import os
import aiohttp
import re
from datetime import datetime, timezone

TOKEN = os.getenv("DISCORD_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
ACCOUNTS_FILE = "accounts.json"
ASSIGNMENTS_FILE = "assignments.json"
LOG_CHANNEL_ID = 1557641355767844944

# Microsoft OAuth endpoints
MS_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
MS_GRAPH_URL = "https://graph.microsoft.com/v1.0"


def load_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        return []
    with open(ACCOUNTS_FILE, "r") as f:
        return json.load(f)


def save_accounts(accounts):
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(accounts, f, indent=2)


def load_assignments():
    """Load user->account assignments {discord_user_id: account_string}"""
    if not os.path.exists(ASSIGNMENTS_FILE):
        return {}
    with open(ASSIGNMENTS_FILE, "r") as f:
        return json.load(f)


def save_assignments(assignments):
    with open(ASSIGNMENTS_FILE, "w") as f:
        json.dump(assignments, f, indent=2)


def parse_account(account_str):
    """Parse account string into components"""
    parts = account_str.split(":")
    return {
        "email": parts[0] if len(parts) > 0 else "",
        "password": parts[1] if len(parts) > 1 else "",
        "refresh_token": parts[2] if len(parts) > 2 else "",
        "client_id": parts[3] if len(parts) > 3 else "",
        "recovery": parts[4] if len(parts) > 4 else "",
    }


async def get_access_token(refresh_token, client_id):
    """Exchange refresh token for access token"""
    data = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": "https://graph.microsoft.com/Mail.Read",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(MS_TOKEN_URL, data=data) as resp:
            result = await resp.json()
            if "access_token" in result:
                return result["access_token"], result.get("refresh_token", refresh_token)
            else:
                return None, None


async def read_latest_emails(access_token, count=5):
    """Read latest emails from inbox using Graph API"""
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{MS_GRAPH_URL}/me/messages?$top={count}&$orderby=receivedDateTime desc&$select=subject,from,receivedDateTime,bodyPreview"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                result = await resp.json()
                return result.get("value", [])
            else:
                return None


def extract_code(text):
    """Try to extract a verification code from email text"""
    # Common patterns for verification codes (4-8 digits)
    patterns = [
        r'\b(\d{6})\b',  # 6 digits (most common)
        r'\b(\d{4})\b',  # 4 digits
        r'\b(\d{5})\b',  # 5 digits
        r'\b(\d{7})\b',  # 7 digits
        r'\b(\d{8})\b',  # 8 digits
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            return matches[0]
    return None


class OutlookPanel(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="📧 Recevoir une adresse email",
        style=discord.ButtonStyle.green,
        custom_id="get_account_btn",
    )
    async def get_account(self, interaction: discord.Interaction, button: ui.Button):
        user_id = str(interaction.user.id)
        assignments = load_assignments()

        # Check if user already has an account
        if user_id in assignments:
            account_data = parse_account(assignments[user_id])
            msg = (
                f"📧 **Ton adresse Outlook**\n\n"
                f"**Email :** `{account_data['email']}`\n"
                f"**Mot de passe :** `{account_data['password']}`\n\n"
                f"💡 Tu as déjà reçu cette adresse. La voici à nouveau."
            )
            try:
                await interaction.user.send(msg)
                await interaction.response.send_message(
                    "📨 Tu as déjà une adresse ! Je te l'ai renvoyée en DM.",
                    ephemeral=True,
                )
            except discord.Forbidden:
                await interaction.response.send_message(
                    "⚠️ Impossible de t'envoyer un DM. Active tes messages privés.",
                    ephemeral=True,
                )
            return

        # Assign new account
        accounts = load_accounts()
        if not accounts:
            await interaction.response.send_message(
                "❌ Plus d'adresses disponibles pour le moment. Contacte un admin.",
                ephemeral=True,
            )
            return

        account_str = accounts.pop(0)
        save_accounts(accounts)

        # Save assignment
        assignments[user_id] = account_str
        save_assignments(assignments)

        account_data = parse_account(account_str)
        has_token = bool(account_data["refresh_token"] and account_data["client_id"])

        msg = (
            f"📧 **Ton adresse Outlook**\n\n"
            f"**Email :** `{account_data['email']}`\n"
            f"**Mot de passe :** `{account_data['password']}`\n\n"
            f"📌 **Utilise cet email** pour t'inscrire sur les sites (Twitter, Instagram…)\n\n"
        )

        if has_token:
            msg += (
                f"📩 **Pour recevoir tes codes de vérification :**\n"
                f"Retourne sur le serveur et clique sur **\"📩 Recevoir mon code\"**\n"
                f"Le bot ira lire ta boîte mail et t'enverra le code ici !\n\n"
                f"⚠️ **Tu n'as PAS besoin d'aller sur outlook.com**"
            )
        else:
            msg += (
                f"➡️ Va sur **outlook.com** pour lire tes codes de vérification.\n\n"
                f"⚠️ **Si Microsoft te demande une vérification :**\n"
                f"1️⃣ Clique sur **\"Je ne les ai plus\"**\n"
                f"2️⃣ Puis clique sur **\"Utiliser mon mot de passe\"** si proposé\n"
                f"3️⃣ Entre le mot de passe donné ci-dessus"
            )

        try:
            await interaction.user.send(msg)
            await interaction.response.send_message(
                "✅ Adresse envoyée en message privé ! Vérifie tes DMs.",
                ephemeral=True,
            )
            # Log
            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                remaining = len(accounts)
                log_embed = discord.Embed(
                    title="📤 Compte distribué",
                    color=0x2ECC71,
                )
                log_embed.add_field(
                    name="VA",
                    value=f"{interaction.user.mention}\n{interaction.user}",
                    inline=True,
                )
                log_embed.add_field(
                    name="Email donné",
                    value=f"`{account_data['email']}`",
                    inline=True,
                )
                log_embed.add_field(
                    name="Stock restant",
                    value=f"**{remaining}** adresses",
                    inline=True,
                )
                log_embed.add_field(
                    name="Refresh Token",
                    value="✅ Oui" if has_token else "❌ Non",
                    inline=True,
                )
                log_embed.add_field(
                    name="Info",
                    value=f"ID Discord : {interaction.user.id} • {datetime.now(timezone.utc).strftime('%d/%m/%Y à %H:%M')}",
                    inline=False,
                )
                await log_channel.send(embed=log_embed)

        except discord.Forbidden:
            # Put account back
            accounts.insert(0, account_str)
            save_accounts(accounts)
            del assignments[user_id]
            save_assignments(assignments)

            await interaction.response.send_message(
                "⚠️ Impossible de t'envoyer un DM. Active tes messages privés "
                "(Paramètres du serveur → Confidentialité) puis réessaie.",
                ephemeral=True,
            )
            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                log_embed = discord.Embed(
                    title="❌ Échec distribution",
                    color=0xE74C3C,
                )
                log_embed.add_field(
                    name="VA",
                    value=f"{interaction.user.mention}\n{interaction.user}",
                    inline=True,
                )
                log_embed.add_field(
                    name="Raison",
                    value="DMs fermés",
                    inline=True,
                )
                await log_channel.send(embed=log_embed)

    @ui.button(
        label="📩 Recevoir mon code",
        style=discord.ButtonStyle.blurple,
        custom_id="get_code_btn",
    )
    async def get_code(self, interaction: discord.Interaction, button: ui.Button):
        user_id = str(interaction.user.id)
        assignments = load_assignments()

        if user_id not in assignments:
            await interaction.response.send_message(
                "❌ Tu n'as pas encore d'adresse email. Clique d'abord sur le bouton vert.",
                ephemeral=True,
            )
            return

        account_data = parse_account(assignments[user_id])

        if not account_data["refresh_token"] or not account_data["client_id"]:
            await interaction.response.send_message(
                "⚠️ Ton compte ne supporte pas la lecture automatique. "
                "Va sur **outlook.com** avec ton email + mot de passe pour lire tes codes.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Get access token
            access_token, new_refresh = await get_access_token(
                account_data["refresh_token"], account_data["client_id"]
            )

            if not access_token:
                await interaction.followup.send(
                    "❌ Impossible d'accéder à la boîte mail. Le token a peut-être expiré. Contacte un admin.",
                    ephemeral=True,
                )
                # Log failure
                log_channel = bot.get_channel(LOG_CHANNEL_ID)
                if log_channel:
                    log_embed = discord.Embed(
                        title="❌ Échec lecture mail",
                        color=0xE74C3C,
                    )
                    log_embed.add_field(
                        name="VA",
                        value=f"{interaction.user.mention}\n{interaction.user}",
                        inline=True,
                    )
                    log_embed.add_field(
                        name="Email",
                        value=f"`{account_data['email']}`",
                        inline=True,
                    )
                    log_embed.add_field(
                        name="Raison",
                        value="Token expiré / invalide",
                        inline=True,
                    )
                    await log_channel.send(embed=log_embed)
                return

            # Update refresh token if it changed
            if new_refresh and new_refresh != account_data["refresh_token"]:
                parts = assignments[user_id].split(":")
                parts[2] = new_refresh
                assignments[user_id] = ":".join(parts)
                save_assignments(assignments)

            # Read latest emails
            emails = await read_latest_emails(access_token)

            if emails is None:
                await interaction.followup.send(
                    "❌ Erreur lors de la lecture des mails. Réessaie dans quelques secondes.",
                    ephemeral=True,
                )
                return

            if not emails:
                await interaction.followup.send(
                    "📭 Aucun mail reçu pour le moment. Attends quelques secondes et réessaie.",
                    ephemeral=True,
                )
                return

            # Build message with latest emails
            msg = f"📬 **Derniers mails de** `{account_data['email']}`\n\n"
            code_found = None

            for i, email in enumerate(emails[:5], 1):
                sender = email.get("from", {}).get("emailAddress", {}).get("address", "?")
                subject = email.get("subject", "(sans objet)")
                preview = email.get("bodyPreview", "")[:200]
                received = email.get("receivedDateTime", "")

                # Try to extract code
                code = extract_code(subject + " " + preview)
                if code and not code_found:
                    code_found = code

                msg += f"**{i}.** De : `{sender}`\n"
                msg += f"📌 **{subject}**\n"
                if preview:
                    msg += f"```{preview}```\n"

            if code_found:
                msg += f"\n🔑 **Code détecté : `{code_found}`**\n"
                msg += f"Copie ce code et colle-le sur le site."

            try:
                await interaction.user.send(msg)
                await interaction.followup.send(
                    "✅ Tes derniers mails ont été envoyés en DM !",
                    ephemeral=True,
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    "⚠️ Impossible de t'envoyer un DM. Active tes messages privés.",
                    ephemeral=True,
                )
                return

            # Log the code retrieval
            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                log_embed = discord.Embed(
                    title="✅ Code reçu" if code_found else "📬 Mails lus",
                    color=0x3498DB,
                )
                log_embed.add_field(
                    name="VA",
                    value=f"{interaction.user.mention}\n{interaction.user}",
                    inline=True,
                )
                log_embed.add_field(
                    name="Email",
                    value=f"`{account_data['email']}`",
                    inline=True,
                )
                if code_found:
                    log_embed.add_field(
                        name="Code",
                        value=f"**{code_found}**",
                        inline=True,
                    )
                log_embed.add_field(
                    name="Mails trouvés",
                    value=f"{len(emails)}",
                    inline=True,
                )
                log_embed.add_field(
                    name="Info",
                    value=f"ID Discord : {interaction.user.id} • {datetime.now(timezone.utc).strftime('%d/%m/%Y à %H:%M')}",
                    inline=False,
                )
                await log_channel.send(embed=log_embed)

        except Exception as e:
            await interaction.followup.send(
                f"❌ Erreur : {str(e)[:100]}. Réessaie ou contacte un admin.",
                ephemeral=True,
            )


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    bot.add_view(OutlookPanel())
    print(f"Bot connecté : {bot.user}")
    print(f"ADMIN_IDS = {ADMIN_IDS}")
    print(f"Serveurs : {[g.name for g in bot.guilds]}")
    assignments = load_assignments()
    print(f"Comptes attribués : {len(assignments)}")


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)


@bot.command(name="panel")
async def send_panel(ctx):
    if ctx.author.id not in ADMIN_IDS:
        await ctx.send("❌ Tu n'es pas admin.", delete_after=5)
        return

    embed = discord.Embed(
        title="📧 Adresse Email Outlook",
        description=(
            "**1️⃣ Clique sur le bouton vert** pour recevoir ton adresse email\n\n"
            "**2️⃣ Utilise cet email** pour t'inscrire sur Twitter, Instagram…\n\n"
            "**3️⃣ Clique sur le bouton bleu** pour recevoir tes codes de vérification\n\n"
            "⚠️ **Active tes messages privés** "
            "(Paramètres du serveur → Confidentialité)"
        ),
        color=0x0078D4,
    )
    await ctx.send(embed=embed, view=OutlookPanel())
    await ctx.message.delete()


@bot.command(name="stock")
async def check_stock(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return
    accounts = load_accounts()
    assignments = load_assignments()
    await ctx.send(
        f"📦 **Stock :** {len(accounts)} adresses disponibles\n"
        f"📊 **Distribués :** {len(assignments)} adresses attribuées",
        delete_after=15,
    )


@bot.command(name="add")
async def add_accounts(ctx, *, data: str = None):
    if ctx.author.id not in ADMIN_IDS:
        return

    if not data:
        await ctx.send(
            "Utilisation : `!add email:pass:token:clientid` (une ligne par compte)",
            delete_after=10,
        )
        return

    accounts = load_accounts()
    new_lines = [line.strip() for line in data.strip().split("\n") if line.strip()]
    accounts.extend(new_lines)
    save_accounts(accounts)
    await ctx.send(
        f"✅ **{len(new_lines)}** compte(s) ajouté(s). Stock total : **{len(accounts)}**",
        delete_after=10,
    )
    await ctx.message.delete()


@bot.command(name="reset")
async def reset_user(ctx, user: discord.Member = None):
    """Admin: reset a user's assignment so they can get a new account"""
    if ctx.author.id not in ADMIN_IDS:
        return
    if not user:
        await ctx.send("Utilisation : `!reset @utilisateur`", delete_after=10)
        return

    assignments = load_assignments()
    user_id = str(user.id)
    if user_id in assignments:
        del assignments[user_id]
        save_assignments(assignments)
        await ctx.send(f"✅ {user.mention} peut maintenant reprendre une nouvelle adresse.", delete_after=10)
    else:
        await ctx.send(f"ℹ️ {user.mention} n'a pas d'adresse attribuée.", delete_after=10)
    await ctx.message.delete()


bot.run(TOKEN)
