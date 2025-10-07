import discord
from discord.ext import commands
import json
import requests
import logging
import asyncio
import openai

logging.basicConfig(level=logging.INFO)

# ------------------------------
# CONFIG DOSYALARI
# ------------------------------
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

TOKEN = config["token"]
DEEPL_API_KEY = config["deepl_api_key"]
GPT_API_KEY = config["gpt_api_key"]

openai.api_key = GPT_API_KEY

# Emoji -> Dil eşlemesini JSON üzerinden yükle
with open("emoji_config.json", "r", encoding="utf-8") as f:
    emoji_to_lang = json.load(f)

CONFIG_FILE = "channel_config.json"

def load_channel_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"channels": {}, "categories": {}}

def save_channel_config(config_data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=4, ensure_ascii=False)

# ------------------------------
# MESAJ TAKİP SETİ
# ------------------------------
active_messages = set()

# ------------------------------
# DEEPL ÇEVİRİ FONKSİYONU
# ------------------------------
def translate_text(text, target_lang):
    url = "https://api-free.deepl.com/v2/translate"
    data = {
        "auth_key": DEEPL_API_KEY,
        "text": text,
        "target_lang": target_lang.upper()
    }
    response = requests.post(url, data=data)
    if response.status_code != 200:
        return f"Çeviri başarısız oldu. Hata kodu: {response.status_code}"
    result = response.json()
    return result["translations"][0]["text"]

# ------------------------------
# BOT TANIMLAMASI
# ------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="-", intents=intents, help_command=None)

# ------------------------------
# GPT İLE ÇEVİRİ
# ------------------------------
async def translate_with_gpt(text, target_lang):
    prompt = f"Lütfen aşağıdaki metni sadece {target_lang} diline çevir. Hiçbir yorum ekleme. Ancak metinin çevirildiğinden emin ol. Merhaba gibi kısa mesajları, Hello haline getirirken çekinme. Argoları çevirirken çekinme.:\n{text}"
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        gpt_result = response.choices[0].message.content
        return gpt_result
    except Exception as e:
        # GPT başarısız olursa DeepL çevirisi
        return translate_text(text, target_lang)

# ------------------------------
# MESAJ VE REAKSİYON İŞLEME
# ------------------------------
async def process_message_reactions(message, user, emoji_str):
    if user.bot:
        return

    if message.id in active_messages:
        return
    active_messages.add(message.id)

    try:
        config_data = load_channel_config()
        channel_id = str(message.channel.id)
        category_id = str(message.channel.category_id) if message.channel.category else None

        active = False
        send_dm = False

        if category_id and category_id in config_data.get("categories", {}):
            cat_conf = config_data["categories"][category_id]
            active = cat_conf["active"]
            send_dm = cat_conf["send_dm"]

        if channel_id in config_data.get("channels", {}):
            chan_conf = config_data["channels"][channel_id]
            active = chan_conf["active"]
            send_dm = chan_conf["send_dm"]

        if not active:
            return

        # Sadece tıklanan emojiye tepki ver
        if emoji_str in emoji_to_lang:
            target_lang = emoji_to_lang[emoji_str]
            translated = await translate_with_gpt(message.content, target_lang)

            try:
                if send_dm:
                    await user.send(translated)
                else:
                    reply_msg = await message.reply(translated)

                # Emojiyi hemen kaldır
                try:
                    await message.remove_reaction(emoji_str, user)
                except Exception as e:
                    print(f"Emoji kaldırılamadı: {e}")

                # 60 saniye sonra çeviri mesajını sil
                await asyncio.sleep(60)
                try:
                    await reply_msg.delete()
                except:
                    pass

            except Exception as e:
                await message.channel.send(f"{user.mention}, DM gönderilemedi: {e}")

    finally:
        if message.id in active_messages:
            active_messages.remove(message.id)

# ------------------------------
# RAW REACTION EVENT
# ------------------------------
@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    channel = bot.get_channel(payload.channel_id)
    if not channel:
        return

    try:
        message = await channel.fetch_message(payload.message_id)
    except:
        return

    try:
        user = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
    except:
        return

    emoji_str = str(payload.emoji)
    await process_message_reactions(message, user, emoji_str)

# ------------------------------
# KOMUTLAR: Kanal / Kategori
# ------------------------------
@bot.command()
async def setchannel(ctx, channel: discord.TextChannel, active: str, send_dm: str):
    active_bool = active.lower() == "aktif"
    send_dm_bool = send_dm.lower() == "dm"
    config_data = load_channel_config()
    config_data["channels"][str(channel.id)] = {
        "active": active_bool,
        "send_dm": send_dm_bool
    }
    save_channel_config(config_data)
    await ctx.send(f"{channel.mention} için çeviri ayarlandı: Active={active_bool}, DM={send_dm_bool}")

@bot.command()
async def setcategory(ctx, category: discord.CategoryChannel, active: str, send_dm: str):
    active_bool = active.lower() == "aktif"
    send_dm_bool = send_dm.lower() == "dm"
    config_data = load_channel_config()
    config_data["categories"][str(category.id)] = {
        "active": active_bool,
        "send_dm": send_dm_bool
    }
    save_channel_config(config_data)
    await ctx.send(f"{category.name} kategorisi için çeviri ayarlandı: Active={active_bool}, DM={send_dm_bool}")

# ------------------------------
# DİĞER KOMUTLAR
# ------------------------------
@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong! Bot çalışıyor.")

@bot.command()
async def help(ctx):
    help_text = """
**💡 Mevcut Komutlar:**

`-ping` → Botun çalışıp çalışmadığını test eder  
`-setchannel #kanal aktif/dm` → Kanal için çeviri ayarı yapar  
`-setcategory #kategori aktif/dm` → Kategori için çeviri ayarı yapar  
`-help` → Bu mesajı gösterir
"""
    msg = await ctx.send(f"{ctx.author.mention}\n{help_text}")
    await ctx.message.add_reaction("✅")
    await asyncio.sleep(30)
    try:
        await msg.delete()
    except:
        pass

# ------------------------------
# BOTU ÇALIŞTIR
# ------------------------------
@bot.event
async def on_ready():
    print(f"✅ {bot.user} olarak giriş yapıldı!")
    await bot.change_presence(activity=discord.Game(name="Preparing for Translate..."))

bot.run(TOKEN)
