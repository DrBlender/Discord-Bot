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

# ✅ Punkte anzeigen
@tree.command(name="punkte", description="Zeigt die aktuellen Punkte eines Streamers an.")
async def punkte(interaction: discord.Interaction, member: discord.Member):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT gesamt_punkte, monatliche_punkte, shopping_punkte FROM streamer_punkte WHERE discord_name = %s", (str(member),))
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

# ✅ Punkte durch Streamdauer & Peak-Zuschauer berechnen
@tree.command(name="streaminfo", description="Berechnet Punkte basierend auf Peak-Zuschauer und Streamdauer.")
async def streaminfo(interaction: discord.Interaction, member: discord.Member, peak: int, dauer: int):
    if peak < 0 or dauer < 0:
        await interaction.response.send_message("❌ Ungültige Werte! Bitte gib positive Zahlen ein.", ephemeral=True)
        return

    # 🔹 Korrigierte Punkte-Berechnung
    punkte_dauer = (dauer // 6)  # 1 Stunde = 10 Punkte
    punkte_peak = (peak // 5)  # 5 Zuschauer = 1 Punkt
    gesamt_punkte = punkte_dauer + punkte_peak

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE streamer_punkte SET gesamt_punkte = gesamt_punkte + %s, monatliche_punkte = monatliche_punkte + %s, shopping_punkte = shopping_punkte + %s WHERE discord_name = %s",
                   (gesamt_punkte, gesamt_punkte, gesamt_punkte, str(member)))
    conn.commit()
    conn.close()

    await interaction.response.send_message(f"✅ **{member.display_name}** hat **{gesamt_punkte}** Punkte erhalten! 🎉")

# ✅ Leaderboard abrufen & posten (Tägliche Aktualisierung)
async def update_leaderboard():
    await bot.wait_until_ready()
    channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
    if not channel:
        print("❌ Leaderboard-Kanal nicht gefunden!")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT discord_name, gesamt_punkte FROM streamer_punkte ORDER BY gesamt_punkte DESC LIMIT 10")
    results = cursor.fetchall()
    conn.close()

    if not results:
        await channel.send("⚠ Kein Leaderboard verfügbar.")
        return

    # 📌 Leaderboard Embed erstellen
    embed = discord.Embed(
        title="🏆 **Tägliches LiveFusion Leaderboard** 🏆",
        description=f"📅 **{datetime.datetime.now().strftime('%d.%m.%Y')}**\n\nHier sind die **Top 10 Streamer** mit den meisten Punkten!",
        color=discord.Color.gold()
    )

    for i, (name, punkte) in enumerate(results, start=1):
        rank_medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"#{i}"
        embed.add_field(name=f"{rank_medal} {name}", value=f"🔥 **{punkte} Punkte**", inline=False)

    embed.set_footer(text="LiveFusion • Bleib aktiv & sammel Punkte! 🚀")

    await channel.send(embed=embed)

# 🔹 Automatisches Leaderboard Update
async def leaderboard_task():
    while True:
        now = datetime.datetime.now()
        next_run = datetime.datetime.combine(now.date(), datetime.time(0, 0)) + datetime.timedelta(days=1)
        seconds_until_next_run = (next_run - now).total_seconds()
        await asyncio.sleep(seconds_until_next_run)
        await update_leaderboard()

@tree.command(name="addstreamer", description="Fügt einen neuen Streamer zur Datenbank hinzu.")
async def addstreamer(
    interaction: discord.Interaction,
    member: discord.Member,
    tiktok_name: str,
    email: str,
    handynummer: str,
    strasse: str,
    hausnummer: str,
    plz: str,
    ort: str,
    land: str
):
    print(f"📌 Befehl /addstreamer wurde von {interaction.user} aufgerufen!")  # Debugging-Ausgabe

    conn = get_db_connection()
    cursor = conn.cursor()

    # Prüfen, ob der Nutzer bereits existiert
    cursor.execute("SELECT id FROM streamer_punkte WHERE discord_id = %s", (member.id,))
    result = cursor.fetchone()

    if result:
        print(f"⚠ {member.display_name} ist bereits in der Datenbank!")  # Debugging-Ausgabe
        await interaction.response.send_message(f"⚠ **{member.display_name}** ist bereits in der Datenbank!", ephemeral=True)
    else:
        cursor.execute("""
            INSERT INTO streamer_punkte (discord_id, discord_name, tiktok_name, email, handynummer, strasse, hausnummer, plz, ort, land, start_datum, gesamt_punkte, monatliche_punkte, shopping_punkte)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), 0, 0, 0)
        """, (member.id, str(member), tiktok_name, email, handynummer, strasse, hausnummer, plz, ort, land))
        
        conn.commit()
        print(f"✅ {member.display_name} wurde in die Datenbank hinzugefügt!")  # Debugging-Ausgabe
        await interaction.response.send_message(f"✅ **{member.display_name}** wurde erfolgreich als Streamer hinzugefügt!", ephemeral=False)

    conn.close()


@bot.event
async def on_ready():
    global tree

    # 🔹 Debugging: Prüfen, ob GUILD_ID eine Zahl ist
    print(f"🔍 GUILD_ID ist: {GUILD_ID} (Typ: {type(GUILD_ID)})")

    try:
        guild = discord.Object(id=int(GUILD_ID))  # Sicherstellen, dass es eine Zahl ist
        await tree.sync(guild=guild)  
        print(f"✅ Slash-Befehle erfolgreich für Server-ID {GUILD_ID} synchronisiert!")

        # 🔹 Debugging: Registrierte Befehle ausgeben
        for command in tree.get_commands():
            print(f"📌 Registrierter Slash-Befehl: {command.name}")

    except Exception as e:
        print(f"❌ Fehler bei der Befehls-Registrierung: {e}")

    print(f"✅ Bot ist eingeloggt als {bot.user}!")
    #bot.loop.create_task(leaderboard_task())  # Startet die tägliche Leaderboard-Task

@tree.command(name="sync", description="Synchronisiert die Slash-Befehle mit Discord.")
async def sync(interaction: discord.Interaction):
    await tree.sync()
    await interaction.response.send_message("✅ Slash-Befehle wurden aktualisiert!", ephemeral=True)


bot.run(TOKEN)
