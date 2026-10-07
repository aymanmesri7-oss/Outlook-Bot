import discord
from discord.ext import commands
from discord import ui
import json
import os

TOKEN = os.getenv("DISCORD_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
ACCOUNTS_FILE = "accounts.json"


def load_accounts():
    with open(ACCOUNTS_FILE, "r") as f:
        return json.load(f)


def save_accounts(accounts):
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(accounts, f, indent=2)


class GetAccountButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="📧 Recevoir une adresse email",
        style=discord.ButtonStyle.green,
        custom_id="get_account_btn",
    )
    async def get_account(self, interaction: discord.Interaction, button: ui.Button):
        accounts = load_accounts()

        if not accounts:
            await interaction.response.send_message(
                "❌ Plus d'adresses disponibles pour le moment. Contacte un admin.",
                ephemeral=True,
            )
            return

        # Take the first available account
        account = accounts.pop(0)
        save_accounts(accounts)

        # Format the account info
        parts = account.split(":")
        if len(parts) == 4:
            login, password, refresh_token, client_id = parts
            msg = (
                f"📧 **Ton adresse Outlook**\n\n"
                f"```\n{account}\n```\n\n"
                f"**Login :** `{login}`\n"
                f"**Password :** `{password}`\n"
                f"**Refresh Token :** `{refresh_token}`\n"
                f"**Client ID :** `{client_id}`\n\n"
                f"➡️ Va sur **outlook.com** et connecte-toi avec le login + mot de passe.\n"
                f"C'est sur cette boîte mail que tu recevras les mails / codes de vérification."
            )
        else:
            msg = (
                f"📧 **Ton adresse Outlook**\n\n"
                f"```\n{account}\n```\n\n"
                f"➡️ Va sur **outlook.com** et connecte-toi avec ces identifiants."
            )

        try:
            await interaction.user.send(msg)
            await interaction.response.send_message(
                "✅ Adresse envoyée en message privé ! Vérifie tes DMs.",
                ephemeral=True,
            )
        except discord.Forbidden:
            # User has DMs disabled
            accounts.insert(0, account)
            save_accounts(accounts)
            await interaction.response.send_message(
                "⚠️ Impossible de t'envoyer un DM. Active tes messages privés "
                "(Paramètres du serveur → Confidentialité) puis réessaie.",
                ephemeral=True,
            )


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    bot.add_view(GetAccountButton())
    print(f"Bot connecté : {bot.user}")


@bot.command(name="panel")
async def send_panel(ctx):
    """Envoie le panel avec le bouton (admin only)"""
    if ctx.author.id not in ADMIN_IDS:
        return

    embed = discord.Embed(
        title="📧 Adresse Email Outlook",
        description=(
            "Clique sur 📧 **Recevoir une adresse email** "
            "pour recevoir une adresse Outlook **en message privé** 📩\n\n"
            "Tu recevras une ligne au format "
            "`login:password:refresh_token:client_id`.\n\n"
            "**Quoi faire :**\n"
            "1️⃣ Va sur **outlook.com** et connecte-toi avec le **login + mot de passe**.\n"
            "2️⃣ C'est **sur cette boîte mail** que tu reçois les **mails / codes de vérification** de tes comptes.\n\n"
            "⚠️ **Active tes messages privés** "
            "(Paramètres du serveur → Confidentialité) pour recevoir l'adresse."
        ),
        color=0x0078D4,
    )
    await ctx.send(embed=embed, view=GetAccountButton())
    await ctx.message.delete()


@bot.command(name="stock")
async def check_stock(ctx):
    """Vérifie le stock d'adresses (admin only)"""
    if ctx.author.id not in ADMIN_IDS:
        return
    accounts = load_accounts()
    await ctx.send(f"📦 Stock actuel : **{len(accounts)}** adresses", delete_after=10)


@bot.command(name="add")
async def add_accounts(ctx, *, data: str = None):
    """Ajoute des comptes (admin only). Coller les lignes login:pass:token:client_id"""
    if ctx.author.id not in ADMIN_IDS:
        return

    if not data:
        await ctx.send("Utilisation : `!add login:pass:token:id` (une ligne par compte)", delete_after=10)
        return

    accounts = load_accounts()
    new_lines = [line.strip() for line in data.strip().split("\n") if line.strip()]
    accounts.extend(new_lines)
    save_accounts(accounts)
    await ctx.send(f"✅ **{len(new_lines)}** compte(s) ajouté(s). Stock total : **{len(accounts)}**", delete_after=10)
    await ctx.message.delete()


bot.run(TOKEN)
