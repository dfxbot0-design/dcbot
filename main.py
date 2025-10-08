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

# ------------------------------
# WHITELIST YÜKLEME
# ------------------------------
try:
    with open("whitelist.json", "r", encoding="utf-8") as f:
        whitelist = json.load(f)
        OWNER_IDS = whitelist.get("owners", [])
except FileNotFoundError:
    OWNER_IDS = []

# ------------------------------
# EMOJI → DİL HARİTALAMA
# ------------------------------
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
# MESAJ + EMOJI + USER KİLİT TAKİBİ
# ------------------------------
active_reactions = set()  # (message.id, emoji, user.id)

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
# GLOBAL KOMUT KONTROLÜ (Whitelist)
# ------------------------------
@bot.check
async def globally_block_dms_and_non_whitelisted(ctx):
    if ctx.guild is None:
        return False  # DM'den komut kullanılmasın
    if ctx.author.id not in OWNER_IDS:
        await ctx.send("🚫 Bu komutu kullanma yetkiniz yok.")
        return False
    return True

# ------------------------------
# GPT ÇEVİRİSİ (yedek olarak Deepl kullanır)
# ------------------------------
async def translate_with_gpt(text, target_lang):
    prompt = (
        f"Lütfen aşağıdaki metni yalnızca {target_lang} diline çevir. "
        f"Yorum ekleme, sadece çeviriyi ver.\n\n"
        f"{text}"
    )
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.warning(f"GPT hata verdi, Deepl'e düşülüyor: {e}")
        return translate_text(text, target_lang)

# ------------------------------
# MESAJ REAKSİYONLARINI İŞLEME
# ------------------------------
async def process_message_reactions(message, user, emoji_str):
    if user.bot:
        return

    key = (message.id, emoji_str, user.id)
    if key in active_reactions:
        return
    active_reactions.add(key)

    try:
        config_data = load_channel_config()
        channel_id = str(message.channel.id)
        category_id = str(message.channel.category_id) if message.channel.category else None

        active = False
        send_dm = False

        # Kategori ayarları
        if category_id and category_id in config_data.get("categories", {}):
            cat_conf = config_data["categories"][category_id]
            active = cat_conf["active"]
            send_dm = cat_conf["send_dm"]

        # Kanal ayarları
        if channel_id in config_data.get("channels", {}):
            chan_conf = config_data["channels"][channel_id]
            active = chan_conf["active"]
            send_dm = chan_conf["send_dm"]

        if not active:
            return

        if emoji_str in emoji_to_lang:
            target_lang = emoji_to_lang[emoji_str]
            translated = await translate_with_gpt(message.content, target_lang)

            if send_dm:
                try:
                    await user.send(translated)
                except Exception as e:
                    logging.warning(f"DM gönderilemedi: {e}")

                # Kanal üzerindeki emojiyi kaldır
                try:
                    if message.guild:
                        perms = message.channel.permissions_for(message.guild.me)
                        if perms.manage_messages:
                            await message.remove_reaction(emoji_str, user)
                    else:
                        await message.remove_reaction(emoji_str, user)
                except Exception as e:
                    logging.warning(f"Emoji kaldırılamadı (DM): {e}")

            else:
                try:
                    reply_msg = await message.reply(translated)
                except Exception as e:
                    logging.error(f"Çeviri gönderilemedi: {e}")
                    return

                try:
                    if message.guild:
                        perms = message.channel.permissions_for(message.guild.me)
                        if perms.manage_messages:
                            await message.remove_reaction(emoji_str, user)
                    else:
                        await message.remove_reaction(emoji_str, user)
                except Exception as e:
                    logging.warning(f"Emoji kaldırılamadı (kanal): {e}")

                async def delete_later(msg):
                    await asyncio.sleep(60)
                    try:
                        await msg.delete()
                    except:
                        pass

                asyncio.create_task(delete_later(reply_msg))
    finally:
        if key in active_reactions:
            active_reactions.remove(key)

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
# KOMUTLAR
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

@bot.command()
async def addowner(ctx, user: discord.User):
    if ctx.author.id not in OWNER_IDS:
        await ctx.send("🚫 Bu komutu sadece mevcut sahipler kullanabilir.")
        return

    if user.id in OWNER_IDS:
        await ctx.send(f"{user.name} zaten whitelist'te.")
        return

    OWNER_IDS.append(user.id)
    with open("whitelist.json", "w", encoding="utf-8") as f:
        json.dump({"owners": OWNER_IDS}, f, indent=4)
    await ctx.send(f"✅ {user.name} whitelist'e eklendi.")

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
`-addowner @kullanıcı` → Whitelist'e yeni kullanıcı ekler  
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
