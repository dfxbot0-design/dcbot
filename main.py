import sys
import types
sys.modules['audioop'] = types.ModuleType('audioop')

import discord
from discord.ext import commands
from discord.ui import View, Button
import json
import os

# -------------------------
# CONFIG
# -------------------------
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

TOKEN = config["TOKEN"]
OWNER_ID = config["OWNER_ID"]
USER_INFO_CHANNEL_ID = config.get("USER_INFO_CHANNEL_ID")
LOG_CHANNEL_ID = config.get("LOG_CHANNEL_ID")
MOD_CHANNEL_ID = config.get("MOD_CHANNEL_ID")
ADMIN_ROLE_IDS = config.get("ADMIN_ROLE_IDS", [])

# -------------------------
# WHITELIST
# -------------------------
WHITELIST_FILE = "whitelist.json"

def load_whitelist():
    if not os.path.exists(WHITELIST_FILE):
        with open(WHITELIST_FILE, "w") as f:
            json.dump([], f)
    with open(WHITELIST_FILE, "r") as f:
        return json.load(f)

def save_whitelist(data):
    with open(WHITELIST_FILE, "w") as f:
        json.dump(data, f, indent=4)

def is_whitelisted():
    async def predicate(ctx):
        whitelist = load_whitelist()
        return ctx.author.id == OWNER_ID or ctx.author.id in whitelist
    return commands.check(predicate)

# -------------------------
# USER LOGS
# -------------------------
USER_LOGS_FILE = "user_logs.json"
if not os.path.exists(USER_LOGS_FILE):
    with open(USER_LOGS_FILE, "w") as f:
        json.dump({}, f)

with open(USER_LOGS_FILE, "r") as f:
    user_logs = json.load(f)

def save_user_logs():
    with open(USER_LOGS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_logs, f, indent=4)

# -------------------------
# BOT SETUP
# -------------------------
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix="u!", intents=intents)

# -------------------------
# UTILITY
# -------------------------
def save_config():
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

# -------------------------
# CHANNEL SET COMMANDS
# -------------------------
@bot.command(name="setchannel-info")
@is_whitelisted()
async def set_channel_info(ctx, channel: discord.TextChannel):
    config["USER_INFO_CHANNEL_ID"] = channel.id
    save_config()
    await ctx.send(f"✅ User Info channel set: {channel.mention}")

@bot.command(name="setchannel-log")
@is_whitelisted()
async def set_channel_log(ctx, channel: discord.TextChannel):
    config["LOG_CHANNEL_ID"] = channel.id
    save_config()
    await ctx.send(f"✅ Log channel set: {channel.mention}")

@bot.command(name="setchannel-mod")
@is_whitelisted()
async def set_channel_mod(ctx, channel: discord.TextChannel):
    config["MOD_CHANNEL_ID"] = channel.id
    save_config()
    await ctx.send(f"✅ Mod control channel set: {channel.mention}")

# -------------------------
# WHITELIST COMMAND (OWNER ONLY)
# -------------------------
@bot.command(name="whitelist")
async def add_whitelist(ctx, member: discord.Member):
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ Only owner can use this command.")
        return
    whitelist = load_whitelist()
    if member.id in whitelist:
        await ctx.send(f"{member.mention} is already whitelisted.")
        return
    whitelist.append(member.id)
    save_whitelist(whitelist)
    await ctx.send(f"{member.mention} has been added to whitelist.")

# -------------------------
# MOD INFO COMMAND
# -------------------------
@bot.command(name="info")
@is_whitelisted()
async def info(ctx, member: discord.Member):
    if not MOD_CHANNEL_ID or ctx.channel.id != MOD_CHANNEL_ID:
        await ctx.send("❌ This command can only be used in the Mod control channel.")
        return

    data = user_logs.get(str(member.id))
    if not data:
        await ctx.send(f"❌ No info found for {member.mention}.")
        return

    embed = discord.Embed(title=f"{member.name} Current Info", color=discord.Color.green())
    embed.add_field(name="Watch Tower Level", value=data.get("watchtower", "N/A"), inline=False)
    embed.add_field(name="Rally Cap", value=data.get("rally", "N/A"), inline=False)
    embed.add_field(name="Car Power", value=data.get("power", "N/A"), inline=False)
    embed.add_field(name="In-Game Username", value=data.get("username", "N/A"), inline=False)
    embed.set_footer(text=f"Requested by: {ctx.author}")

    await ctx.send(embed=embed)

# -------------------------
# INFO ALL COMMAND
# -------------------------
@bot.command(name="info-all")
@is_whitelisted()
async def info_all(ctx):
    if not user_logs:
        await ctx.send("❌ No user info stored yet.")
        return

    embed = discord.Embed(title="All User Infos", color=discord.Color.gold())
    for user_id, data in user_logs.items():
        member = ctx.guild.get_member(int(user_id))
        name = member.name if member else f"User ID {user_id}"
        embed.add_field(
            name=name,
            value=f"Watch Tower: {data.get('watchtower', 'N/A')}\n"
                  f"Rally Cap: {data.get('rally', 'N/A')}\n"
                  f"Car Power: {data.get('power', 'N/A')}\n"
                  f"In-Game Username: {data.get('username', 'N/A')}",
            inline=False
        )
    await ctx.send(embed=embed)

# -------------------------
# REMIND COMMAND
# -------------------------
@bot.command(name="remind")
@is_whitelisted()
async def remind(ctx, role: discord.Role):
    for member in role.members:
        try:
            await member.send(f"📢 Weekly reminder: please update your stats in the <#{USER_INFO_CHANNEL_ID}> channel.")
        except:
            pass
    await ctx.send(f"✅ Reminder sent to all members with role {role.name}.")

# -------------------------
# UPDATE INFO & SHOW INFO BUTTONS
# -------------------------
class UpdateInfoView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="Update Info", style=discord.ButtonStyle.green, custom_id="update_info"))
        self.add_item(Button(label="Show Current Info", style=discord.ButtonStyle.blurple, custom_id="show_info"))

class WatchTowerView(View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        for lvl in range(19, 31):
            self.add_item(Button(label=str(lvl), style=discord.ButtonStyle.blurple, custom_id=f"wt_{lvl}_{user_id}"))

class RallyCapView(View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        for val in range(27000, 60001, 3000):
            self.add_item(Button(label=str(val), style=discord.ButtonStyle.blurple, custom_id=f"rally_{val}_{user_id}"))

class DoneView(View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.add_item(Button(label="Done", style=discord.ButtonStyle.green, custom_id=f"done_{user_id}"))

user_sessions = {}  # user_id -> session data

# -------------------------
# ON READY
# -------------------------
@bot.event
async def on_ready():
    print(f"Bot aktif: {bot.user}")
    await bot.change_presence(activity=discord.Game(name="Created by Direnc"))

    if not USER_INFO_CHANNEL_ID:
        print("User Info channel ID not set.")
        return
    channel = bot.get_channel(USER_INFO_CHANNEL_ID)
    if not channel:
        print("User Info channel not found.")
        return

    # Check if button message exists
    found = False
    async for msg in channel.history(limit=50):
        if msg.author == bot.user and msg.components:
            for row in msg.components:
                for btn in row.children:
                    if btn.custom_id in ["update_info", "show_info"]:
                        found = True
                        break
    if not found:
        await channel.send("Click below to update or view your info:", view=UpdateInfoView())

# -------------------------
# INTERACTIONS
# -------------------------
@bot.event
async def on_interaction(interaction: discord.Interaction):
    custom_id = interaction.data.get("custom_id", "")
    user_id = interaction.user.id

    # --- Update Info Button ---
    if custom_id == "update_info":
        # Kullanıcının zaten aktif bir session’ı var mı?
        if user_id in user_sessions:
            existing_channel = user_sessions[user_id]["channel"]
            await interaction.response.send_message(
                f"⚠️ A channel has already been created for you. Please continue in {existing_channel.mention}.",
                ephemeral=True
            )
            return

        guild = interaction.guild
        bot_member = guild.me
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True),
            bot_member: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        temp_channel = await guild.create_text_channel(
            name=f"info-{interaction.user.name}",
            overwrites=overwrites,
            reason="Temporary user info channel"
        )
        user_sessions[user_id] = {
            "channel": temp_channel,
            "step": "watchtower",
            "answers": {},
            "wt_view": WatchTowerView(user_id),
            "rally_view": RallyCapView(user_id),
            "done_view": DoneView(user_id)
        }
        await temp_channel.send(f"{interaction.user.mention} Please select your **Watch Tower Level**:", view=user_sessions[user_id]["wt_view"])
        await interaction.response.send_message("✅ Temporary channel created. Check it to answer questions.", ephemeral=True)
        return

    # --- Show Current Info Button ---
    if custom_id == "show_info":
        data = user_logs.get(str(user_id))
        if not data:
            await interaction.response.send_message("❌ No info found.", ephemeral=True)
            return
        embed = discord.Embed(title=f"{interaction.user.name} Current Info", color=discord.Color.green())
        embed.add_field(name="Watch Tower Level", value=data.get("watchtower", "N/A"), inline=False)
        embed.add_field(name="Rally Cap", value=data.get("rally", "N/A"), inline=False)
        embed.add_field(name="Car Power", value=data.get("power", "N/A"), inline=False)
        embed.add_field(name="In-Game Username", value=data.get("username", "N/A"), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # --- Watch Tower Selection ---
    if custom_id.startswith("wt_") and str(user_id) in custom_id:
        session = user_sessions.get(user_id)
        if not session or session["step"] != "watchtower":
            return
        level = custom_id.split("_")[1]
        session["answers"]["watchtower"] = level
        session["step"] = "rally"
        await session["channel"].send("Please select your **Rally Cap**:", view=session["rally_view"])
        await interaction.response.defer()
        return

    # --- Rally Cap Selection ---
    if custom_id.startswith("rally_") and str(user_id) in custom_id:
        session = user_sessions.get(user_id)
        if not session or session["step"] != "rally":
            return
        val = custom_id.split("_")[1]
        session["answers"]["rally"] = val
        session["step"] = "power"
        await session["channel"].send(f"{interaction.user.mention} Enter your **Car Power**:", view=session["done_view"])
        await interaction.response.defer()
        return

    # --- Done Button ---
    if custom_id.startswith("done_") and str(user_id) in custom_id:
        session = user_sessions.get(user_id)
        if not session:
            return

        temp_channel = session["channel"]

        if session["step"] == "power":
            messages = [msg async for msg in temp_channel.history(limit=20)]
            power_text = None
            for msg in messages:
                if msg.author.id == user_id and msg.content.strip() != "":
                    power_text = msg.content.strip()
                    break

            if not power_text:
                await temp_channel.send("❌ Please enter your car power first.")
                await interaction.response.defer()
                return

            session["answers"]["power"] = power_text
            session["step"] = "username"
            await temp_channel.send(f"{interaction.user.mention} Enter your **in-game username**:", view=session["done_view"])
            await interaction.response.defer()
            return

        elif session["step"] == "username":
            # Kullanıcı adını girmeden Done basıldı
            await temp_channel.send("❌ Please enter your **in-game username** first.")
            await interaction.response.defer()
            return

# -------------------------
# ON MESSAGE for Username step
# -------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    user_id = message.author.id
    session = user_sessions.get(user_id)
    if not session or session["step"] != "username":
        await bot.process_commands(message)
        return

    session["answers"]["username"] = message.content.strip()

    # prepare embed
    embed = discord.Embed(title=f"{message.author.name} Current Info", color=discord.Color.blue())
    embed.add_field(name="Watch Tower Level", value=session["answers"]["watchtower"], inline=False)
    embed.add_field(name="Rally Cap", value=session["answers"]["rally"], inline=False)
    embed.add_field(name="Car Power", value=session["answers"]["power"], inline=False)
    embed.add_field(name="In-Game Username", value=session["answers"]["username"], inline=False)
    embed.set_footer(text=f"User: {message.author}")

    # send to log channel
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        admin_mentions = " ".join([f"<@&{rid}>" for rid in ADMIN_ROLE_IDS])
        await log_channel.send(embed=embed, content=f"{admin_mentions} {message.author.mention} updated info.")

    # save/update user log
    user_logs[str(user_id)] = session["answers"]
    save_user_logs()

    # delete temp channel
    await session["channel"].delete()
    user_sessions.pop(user_id, None)

# -------------------------
bot.run(TOKEN)
