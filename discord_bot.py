import discord
from discord import app_commands
import mysql.connector
import asyncio
import datetime
import os
from dotenv import load_dotenv

# 🔹 Lade .env-Datei für Token & Datenbank-Zugangsdaten
load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID"))
LEADERBOARD_CHANNEL_ID = int(os.getenv("LEADERBOARD_CHANNEL_ID"))

# 🔹 Discord Bot Setup
intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# 🔹 MariaDB Verbindung
db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

# 🔹 Hilfsfunktion zur Rollenprüfung
def is_admin(user: discord.Member):
    return any(role.name == "🔧 Admin" for role in user.roles)

def is_active_streamer(user: discord.Member):
    return any(role.name == "🔥 Aktive Streamer" for role in user.roles)

# ✅ Punkte anzeigen
@tree.command(name="punkte", description="Zeigt die aktuellen Punkte eines Streamers an.")
async def punkte(interaction: discord.Interaction, member: discord.Member):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT gesamt_punkte, monatliche_punkte, shopping_punkte FROM streamer_punkte WHERE discord_id = %s", (member.id,))
    result = cursor.fetchone()
    conn.close()

    if result:
        await interaction.response.send_message(
            f"🎯 **{member.display_name}** hat:\n"
            f"🏆 **{result[0]}** Gesamtpunkte\n"
            f"📅 **{result[1]}** Monats-Punkte\n"
            f"🛒 **{result[2]}** Shopping-Punkte."
        )
    else:
        await interaction.response.send_message(f"⚠ **{member.display_name}** ist nicht in der Datenbank!", ephemeral=True)

# ✅ Punkte durch Streamdauer & Peak-Zuschauer berechnen (Nur für Admins)
@tree.command(name="streaminfo", description="Admin: Berechnet Punkte basierend auf Peak-Zuschauer und Streamdauer.")
async def streaminfo(interaction: discord.Interaction, member: discord.Member, peak: int, dauer: int):
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ Du hast keine Berechtigung für diesen Befehl!", ephemeral=True)
        return
    
    if peak < 0 or dauer < 0:
        await interaction.response.send_message("❌ Ungültige Werte! Bitte gib positive Zahlen ein.", ephemeral=True)
        return
    
    punkte_dauer = (dauer // 6)
    punkte_peak = (peak // 5)
    gesamt_punkte = punkte_dauer + punkte_peak
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE streamer_punkte SET gesamt_punkte = gesamt_punkte + %s, monatliche_punkte = monatliche_punkte + %s, shopping_punkte = shopping_punkte + %s WHERE discord_id = %s",
                   (gesamt_punkte, gesamt_punkte, gesamt_punkte, member.id))
    conn.commit()
    conn.close()

    await interaction.response.send_message(f"✅ **{member.display_name}** hat **{gesamt_punkte}** Punkte erhalten! 🎉")

# ✅ Leaderboard abrufen & posten (Nur Admins)
@tree.command(name="leaderboard", description="Admin: Zeigt das Leaderboard der besten Streamer.")
async def leaderboard(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ Du hast keine Berechtigung für diesen Befehl!", ephemeral=True)
        return
    
    await update_leaderboard()
    await interaction.response.send_message("✅ Leaderboard wurde aktualisiert!")

# 🔹 Automatisches Leaderboard Update (Täglich um 00:00 Uhr)
async def leaderboard_task():
    while True:
        now = datetime.datetime.now()
        next_run = datetime.datetime.combine(now.date(), datetime.time(0, 0)) + datetime.timedelta(days=1)
        seconds_until_next_run = (next_run - now).total_seconds()
        await asyncio.sleep(seconds_until_next_run)
        await update_leaderboard()

# ✅ Shop anzeigen (Nur "🔥 Aktive Streamer")
@tree.command(name="shop", description="Zeigt alle verfügbaren Belohnungen im Punkteshop.")
async def shop(interaction: discord.Interaction):
    if not is_active_streamer(interaction.user):
        await interaction.response.send_message("❌ Du hast keine Berechtigung für diesen Befehl!", ephemeral=True)
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT belohnung, kosten FROM streamer_belohnungen ORDER BY kosten ASC")
    results = cursor.fetchall()
    conn.close()

    if not results:
        await interaction.response.send_message("⚠ Der Shop ist derzeit leer!", ephemeral=True)
        return

    shop_text = "**🎁 LiveFusion Punkteshop 🎁**\n\n"
    for belohnung, kosten in results:
        shop_text += f"🔹 **{belohnung}** ➝ `{kosten} Punkte`\n"

    await interaction.response.send_message(shop_text)

@bot.event
async def on_ready():
    global tree
    print(f"✅ Bot ist eingeloggt als {bot.user}!")

    try:
        guild = discord.Object(id=int(GUILD_ID))  # Sicherstellen, dass es eine Zahl ist
        await tree.sync(guild=guild)  # Synchronisiert die Slash-Befehle
        print(f"✅ Slash-Befehle erfolgreich für Server-ID {GUILD_ID} synchronisiert!")

    except Exception as e:
        print(f"❌ Fehler bei der Befehls-Registrierung: {e}")

    print("📌 Registrierte Befehle:")
    for command in tree.get_commands():
        print(f"🔹 {command.name}")

    bot.loop.create_task(leaderboard_task())  # Startet Leaderboard-Update


bot.run(TOKEN)