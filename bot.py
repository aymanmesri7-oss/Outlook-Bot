import discord
from discord.ext import commands
from discord import ui
import json
import os
from datetime import datetime, timezone

TOKEN = os.getenv("DISCORD_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
ACCOUNTS_FILE = "accounts.json"
ASSIGNMENTS_FILE = "assignments.json"
LOG_CHANNEL_ID = 1557641355767844944


def load_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        return []
    with open(ACCOUNTS_FILE, "r") as f:
        return json.load(f)


def save_accounts(accounts):
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(accounts, f, indent=2)


def load_assignments():
    """Load user->accounts assignments {discord_user_id: [account_string, ...]}"""
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
        accounts = load_accounts()

        if not accounts:
            await interaction.response.send_message(
                "❌ Plus d'adresses disponibles pour le moment. Contacte un admin.",
                ephemeral=True,
            )
            return

        # Take next account from stock
        account_str = accounts.pop(0)
        save_accounts(accounts)

        # Add to user's list of accounts (no limit)
        if user_id not in assignments:
            assignments[user_id] = []
        assignments[user_id].append(account_str)
        save_assignments(assignments)

        account_data = parse_account(account_str)
        user_total = len(assignments[user_id])

        msg = (
            f"📧 **Ton adresse Outlook** (n°{user_total})\n\n"
            f"**Email :** `{account_data['email']}`\n"
            f"**Mot de passe :** `{account_data['password']}`\n\n"
            f"📌 **Utilise cet email** pour t'inscrire sur les sites (Twitter, Instagram…)\n\n"
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
                    name="Adresses prises",
                    value=f"**{user_total}** (par ce VA)",
                    inline=True,
                )
                log_embed.add_field(
                    name="Stock restant",
                    value=f"**{remaining}** adresses",
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
            assignments[user_id].pop()
            if not assignments[user_id]:
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
    total_accounts = sum(len(v) for v in assignments.values())
    print(f"Comptes attribués : {total_accounts} (à {len(assignments)} utilisateurs)")


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
            "**1️⃣ Clique sur le bouton vert** pour recevoir une adresse email\n\n"
            "**2️⃣ Utilise cet email** pour t'inscrire sur Twitter, Instagram…\n\n"
            "**3️⃣ Va sur outlook.com** pour lire tes codes de vérification\n\n"
            "💡 Tu peux prendre **plusieurs adresses** en recliquant sur le bouton vert\n\n"
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
    total_distributed = sum(len(v) for v in assignments.values())
    await ctx.send(
        f"📦 **Stock :** {len(accounts)} adresses disponibles\n"
        f"📊 **Distribués :** {total_distributed} adresses (à {len(assignments)} VAs)",
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
    """Admin: supprime toutes les adresses d'un utilisateur"""
    if ctx.author.id not in ADMIN_IDS:
        return
    if not user:
        await ctx.send("Utilisation : `!reset @utilisateur`", delete_after=10)
        return

    assignments = load_assignments()
    user_id = str(user.id)
    if user_id in assignments:
        count = len(assignments[user_id])
        del assignments[user_id]
        save_assignments(assignments)
        await ctx.send(f"✅ {count} adresse(s) de {user.mention} supprimée(s).", delete_after=10)
    else:
        await ctx.send(f"ℹ️ {user.mention} n'a aucune adresse.", delete_after=10)
    await ctx.message.delete()


bot.run(TOKEN)
