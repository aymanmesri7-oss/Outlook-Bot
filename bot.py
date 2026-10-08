import discord
from discord.ext import commands
from discord import ui
import json
import os

TOKEN = os.getenv("DISCORD_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
ACCOUNTS_FILE = "accounts.json"
LOG_CHANNEL_ID = 1557641355767844944


def load_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        return []
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

        account = accounts.pop(0)
        save_accounts(accounts)

        parts = account.split(":")
        login = parts[0]
        password = parts[1] if len(parts) > 1 else ""
        msg = (
            f"📧 **Ton adresse Outlook**\n\n"
            f"**Email :** `{login}`\n"
            f"**Mot de passe :** `{password}`\n\n"
            f"➡️ Va sur **outlook.com** et connecte-toi avec l'email + mot de passe.\n"
            f"C'est sur cette boîte mail que tu recevras les mails / codes de vérification.\n\n"
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
            # Log dans le salon logs
            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                remaining = len(accounts)
                log_embed = discord.Embed(
                    title="📤 Compte distribué",
                    description=(
                        f"**Utilisateur :** {interaction.user.mention} (`{interaction.user}`)\n"
                        f"**Email donné :** `{login}`\n"
                        f"**Stock restant :** {remaining} adresses"
                    ),
                    color=0x2ECC71,
                )
                log_embed.set_footer(text=f"ID: {interaction.user.id}")
                await log_channel.send(embed=log_embed)
        except discord.Forbidden:
            accounts.insert(0, account)
            save_accounts(accounts)
            await interaction.response.send_message(
                "⚠️ Impossible de t'envoyer un DM. Active tes messages privés "
                "(Paramètres du serveur → Confidentialité) puis réessaie.",
                ephemeral=True,
            )
            # Log l'échec aussi
            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                log_embed = discord.Embed(
                    title="❌ Échec distribution",
                    description=(
                        f"**Utilisateur :** {interaction.user.mention} (`{interaction.user}`)\n"
                        f"**Raison :** DMs fermés"
                    ),
                    color=0xE74C3C,
                )
                await log_channel.send(embed=log_embed)


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    bot.add_view(GetAccountButton())
    print(f"Bot connecté : {bot.user}")
    print(f"ADMIN_IDS = {ADMIN_IDS}")
    print(f"Serveurs : {[g.name for g in bot.guilds]}")


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    print(f"[MSG] {message.author} dans #{message.channel}: {message.content[:50]}")
    await bot.process_commands(message)


@bot.command(name="panel")
async def send_panel(ctx):
    if ctx.author.id not in ADMIN_IDS:
        await ctx.send("❌ Tu n'es pas admin.", delete_after=5)
        return

    embed = discord.Embed(
        title="📧 Adresse Email Outlook",
        description=(
            "Clique sur le bouton vert pour recevoir "
            "une adresse Outlook **en message privé** 📩\n\n"
            "**Tu recevras :**\n"
            "• Un **email** et un **mot de passe**\n\n"
            "**Quoi faire :**\n"
            "1️⃣ Va sur **outlook.com**\n"
            "2️⃣ Connecte-toi avec l'email + mot de passe\n"
            "3️⃣ C'est sur cette boîte mail que tu reçois tes **codes de vérification**\n\n"
            "⚠️ **Active tes messages privés** "
            "(Paramètres du serveur → Confidentialité) pour recevoir l'adresse."
        ),
        color=0x0078D4,
    )
    await ctx.send(embed=embed, view=GetAccountButton())
    await ctx.message.delete()


@bot.command(name="stock")
async def check_stock(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return
    accounts = load_accounts()
    await ctx.send(f"📦 Stock actuel : **{len(accounts)}** adresses", delete_after=10)


@bot.command(name="add")
async def add_accounts(ctx, *, data: str = None):
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
