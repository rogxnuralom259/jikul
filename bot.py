import sys
import subprocess

def install_dependencies():
    import importlib.util
    import subprocess
    import sys

    packages = {
        'telebot': 'pyTelegramBotAPI',
        'aiosqlite': 'aiosqlite',
        'httpx': 'httpx'
    }

    missing = []

    for module, package in packages.items():
        if importlib.util.find_spec(module) is None:
            missing.append(package)

    if missing:
        print(f"🔄 Installing missing packages: {missing}...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", *missing]
            )
            print("✅ Successfully installed all dependencies.")
        except Exception as e:
            print(f"❌ Error installing dependencies: {e}")
            sys.exit(1)

# Run installer before core logic
install_dependencies()

import asyncio
import aiosqlite
import os
import json
import zipfile
import shutil
import httpx
from telebot.async_telebot import AsyncTeleBot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CopyTextButton

# --- Helper for Premium Buttons ---
class RawButton:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
    def to_dict(self):
        data = self.__dict__.copy()
        data.pop('icon_custom_emoji_id', None)
        data.pop('style', None)
        return data


# Place your bot token here
BOT_TOKEN = "8754398217:AAHHXFm_Z07CHuiRJ2dk1OF1S2-pwlzZEd8"
bot = AsyncTeleBot(BOT_TOKEN)

# Global logging trick for callbacks
@bot.callback_query_handler(func=lambda call: print(f"--- [GLOBAL CALLBACK RECEIVE] ---\nData: {call.data}\nFrom: {call.from_user.id}\n---------------------------------") or False)
async def log_callbacks_dummy(call):
    pass

# admin_states = {} # Moved to a more appropriate place or kept if needed globally
admin_states = {}
user_states = {}
user_cooldowns = {} # Track last request time per user
# Root admin ID who cannot be deleted
ROOT_ADMIN_ID = 8589946469

# --- High-Concurrency Worker Pools ---
get_number_queue = asyncio.Queue()
db_queue = asyncio.Queue()
general_queue = asyncio.Queue()

async def get_number_worker():
    """300 Workers dedicated to 'Get Number' button logic."""
    while True:
        user_id, message = await get_number_queue.get()
        try:
            await get_number_callback(message)
        except Exception as e:
            print(f"Get Number Worker Error: {e}")
        finally:
            get_number_queue.task_done()

async def db_worker():
    """100 Workers dedicated to Database Write operations."""
    while True:
        task_func, args = await db_queue.get()
        try:
            await task_func(*args)
        except Exception as e:
            print(f"DB Worker Error: {e}")
        finally:
            db_queue.task_done()

async def general_worker():
    """100 Workers for general bot tasks."""
    while True:
        task_func, args = await general_queue.get()
        try:
            await task_func(*args)
        except Exception as e:
            print(f"General Worker Error: {e}")
        finally:
            general_queue.task_done()

# --- Performance Optimization (Caching & Global DB) ---
db = None
settings_cache = {}
admin_cache = set()

# --- Mappings for Premium Mode ---
country_map = {
        "Venezuela": ("VE", "🇻🇪"), "Zimbabwe": ("ZW", "🇿🇼"), "Switzerland": ("CH", "🇨🇭"),
        "Bolivia": ("BO", "🇧🇴"), "Ivory Coast": ("CI", "🇨🇮"), "Guatemala": ("GT", "🇬🇹"),
        "Vietnam": ("VN", "🇻🇳"), "Afghanistan": ("AF", "🇦🇫"), "Albania": ("AL", "🇦🇱"),
        "Algeria": ("DZ", "🇩🇿"), "Andorra": ("AD", "🇦🇩"), "Angola": ("AO", "🇦🇴"),
        "Antigua and Barbuda": ("AG", "🇦🇬"), "Argentina": ("AR", "🇦🇷"), "Armenia": ("AM", "🇦🇲"),
        "Australia": ("AU", "🇦🇺"), "Austria": ("AT", "🇦🇹"), "Azerbaijan": ("AZ", "🇦🇿"),
        "Bahamas": ("BS", "🇧🇸"), "Bahrain": ("BH", "🇧🇭"), "Bangladesh": ("BD", "🇧🇩"),
        "Barbados": ("BB", "🇧🇧"), "Belarus": ("BY", "🇧🇾"), "Belgium": ("BE", "🇧🇪"),
        "Belize": ("BZ", "🇧🇿"), "Benin": ("BJ", "🇧🇯"), "Bhutan": ("BT", "🇧🇹"),
        "Bosnia and Herzegovina": ("BA", "🇧🇦"), "Botswana": ("BW", "🇧🇼"), "Brazil": ("BR", "🇧🇷"),
        "Brunei": ("BN", "🇧🇳"), "Bulgaria": ("BG", "🇧🇬"), "Burkina Faso": ("BF", "🇧🇫"),
        "Burundi": ("BI", "🇧🇮"), "Cabo Verde": ("CV", "🇨🇻"), "Cambodia": ("KH", "🇰🇭"),
        "Cameroon": ("CM", "🇨🇲"), "Canada": ("CA", "🇨🇦"), "Central African Republic": ("CF", "🇨🇫"),
        "Chad": ("TD", "🇹🇩"), "Chile": ("CL", "🇨🇱"), "China": ("CN", "🇨🇳"),
        "Colombia": ("CO", "🇨🇴"), "Comoros": ("KM", "🇰🇲"), "Congo": ("CG", "🇨🇬"),
        "Costa Rica": ("CR", "🇨🇷"), "Croatia": ("HR", "🇭🇷"), "Cuba": ("CU", "🇨🇺"),
        "Cyprus": ("CY", "🇨🇾"), "Czechia": ("CZ", "🇨🇿"), "Denmark": ("DK", "🇩🇰"),
        "Djibouti": ("DJ", "🇩🇯"), "Dominica": ("DM", "🇩🇲"), "Dominican Republic": ("DO", "🇩🇴"),
        "Ecuador": ("EC", "🇪🇨"), "Egypt": ("EG", "🇪🇬"), "El Salvador": ("SV", "🇸🇻"),
        "Equatorial Guinea": ("GQ", "🇬🇶"), "Eritrea": ("ER", "🇪🇷"), "Estonia": ("EE", "🇪🇪"),
        "Eswatini": ("SZ", "🇸🇿"), "Ethiopia": ("ET", "🇪🇹"), "Fiji": ("FJ", "🇫🇯"),
        "Finland": ("FI", "🇫🇮"), "France": ("FR", "🇫🇷"), "Gabon": ("GA", "🇬🇦"),
        "Gambia": ("GM", "🇬🇲"), "Georgia": ("GE", "🇬🇪"), "Germany": ("DE", "🇩🇪"),
        "Ghana": ("GH", "🇬🇭"), "Greece": ("GR", "🇬🇷"), "Grenada": ("GD", "🇬🇩"),
        "Guinea": ("GN", "🇬🇳"), "Guinea-Bissau": ("GW", "🇬🇼"), "Guyana": ("GY", "🇬🇾"),
        "Haiti": ("HT", "🇭🇹"), "Honduras": ("HN", "🇭🇳"), "Hungary": ("HU", "🇭🇺"),
        "Iceland": ("IS", "🇮🇸"), "India": ("IN", "🇮🇳"), "Indonesia": ("ID", "🇮🇩"),
        "Iran": ("IR", "🇮🇷"), "Iraq": ("IQ", "🇮🇶"), "Ireland": ("IE", "🇮🇪"),
        "Israel": ("IL", "🇮🇱"), "Italy": ("IT", "🇮🇹"), "Jamaica": ("JM", "🇯🇲"),
        "Japan": ("JP", "🇯🇵"), "Jordan": ("JO", "🇯🇴"), "Kazakhstan": ("KZ", "🇰🇿"),
        "Kenya": ("KE", "🇰🇪"), "Kiribati": ("KI", "🇰🇮"), "Korea, North": ("KP", "🇰🇵"),
        "Korea, South": ("KR", "🇰🇷"), "Kuwait": ("KW", "🇰🇼"), "Kyrgyzstan": ("KG", "🇰🇬"),
        "Laos": ("LA", "🇱🇦"), "Latvia": ("LV", "🇱🇻"), "Lebanon": ("LB", "🇱🇧"),
        "Lesotho": ("LS", "🇱🇸"), "Liberia": ("LR", "🇱🇷"), "Libya": ("LY", "🇱🇾"),
        "Liechtenstein": ("LI", "🇱🇮"), "Lithuania": ("LT", "🇱🇹"), "Luxembourg": ("LU", "🇱🇺"),
        "Madagascar": ("MG", "🇲🇬"), "Malawi": ("MW", "🇲🇼"), "Malaysia": ("MY", "🇲🇾"),
        "Maldives": ("MV", "🇲🇻"), "Mali": ("ML", "🇲🇱"), "Malta": ("MT", "🇲🇹"),
        "Marshall Islands": ("MH", "🇲🇭"), "Mauritania": ("MR", "🇲🇷"), "Mauritius": ("MU", "🇲🇺"),
        "Mexico": ("MX", "🇲🇽"), "Micronesia": ("FM", "🇫🇲"), "Moldova": ("MD", "🇲🇩"),
        "Monaco": ("MC", "🇲🇨"), "Mongolia": ("MN", "🇲🇳"), "Montenegro": ("ME", "🇲🇪"),
        "Morocco": ("MA", "🇲🇦"), "Mozambique": ("MZ", "🇲🇿"), "Myanmar": ("MM", "🇲🇲"),
        "Namibia": ("NA", "🇳🇦"), "Nauru": ("NR", "🇳🇷"), "Nepal": ("NP", "🇳🇵"),
        "Netherlands": ("NL", "🇳🇱"), "New Zealand": ("NZ", "🇳🇿"), "Nicaragua": ("NI", "🇳🇮"),
        "Niger": ("NE", "🇳🇪"), "Nigeria": ("NG", "🇳🇬"), "North Macedonia": ("MK", "🇲🇰"),
        "Norway": ("NO", "🇳🇴"), "Oman": ("OM", "🇴🇲"), "Pakistan": ("PK", "🇵🇰"),
        "Palau": ("PW", "🇵🇼"), "Panama": ("PA", "🇵🇦"), "Papua New Guinea": ("PG", "🇵🇬"),
        "Paraguay": ("PY", "🇵🇾"), "Peru": ("PE", "🇵🇪"), "Philippines": ("PH", "🇵🇭"),
        "Poland": ("PL", "🇵🇱"), "Portugal": ("PT", "🇵🇹"), "Qatar": ("QA", "🇶🇦"),
        "Romania": ("RO", "🇷🇴"), "Russia": ("RU", "🇷🇺"), "Rwanda": ("RW", "🇷🇼"),
        "Saint Kitts and Nevis": ("KN", "🇰🇳"), "Saint Lucia": ("LC", "🇱🇨"),
        "Saint Vincent and the Grenadines": ("VC", "🇻🇨"), "Samoa": ("WS", "🇼🇸"),
        "San Marino": ("SM", "🇸🇲"), "Sao Tome and Principe": ("ST", "🇸🇹"),
        "Saudi Arabia": ("SA", "🇸🇦"), "Senegal": ("SN", "🇸🇳"), "Serbia": ("RS", "🇷🇸"),
        "Seychelles": ("SC", "🇸🇨"), "Sierra Leone": ("SL", "🇸🇱"), "Singapore": ("SG", "🇸🇬"),
        "Slovakia": ("SK", "🇸🇰"), "Slovenia": ("SI", "🇸🇮"), "Solomon Islands": ("SB", "🇸🇧"),
        "Somalia": ("SO", "🇸🇴"), "South Africa": ("ZA", "🇿🇦"), "South Sudan": ("SS", "🇸🇸"),
        "Spain": ("ES", "🇪🇸"), "Sri Lanka": ("LK", "🇱🇰"), "Sudan": ("SD", "🇸🇩"),
        "Suriname": ("SR", "🇸🇷"), "Sweden": ("SE", "🇸🇪"), "Syria": ("SY", "🇸🇾"),
        "Taiwan": ("TW", "🇹🇼"), "Tajikistan": ("TJ", "🇹🇯"), "Tanzania": ("TZ", "🇹🇿"),
        "Thailand": ("TH", "🇹🇭"), "Timor-Leste": ("TL", "🇹🇱"), "Togo": ("TG", "🇹🇬"),
        "Tonga": ("TO", "🇹🇴"), "Trinidad and Tobago": ("TT", "🇹🇹"), "Tunisia": ("TN", "🇹🇳"),
        "Turkey": ("TR", "🇹🇷"), "Turkmenistan": ("TM", "🇹🇲"), "Tuvalu": ("TV", "🇹🇻"),
        "Uganda": ("UG", "🇺🇬"), "Ukraine": ("UA", "🇺🇦"), "United Arab Emirates": ("AE", "🇦🇪"),
        "United Kingdom": ("GB", "🇬🇧"), "United States": ("US", "🇺🇸"), "Uruguay": ("UY", "🇺🇾"),
        "Uzbekistan": ("UZ", "🇺🇿"), "Vanuatu": ("VU", "🇻🇺"), "Vatican City": ("VA", "🇻🇦"),
        "Yemen": ("YE", "🇾🇪"), "Zambia": ("ZM", "🇿🇲")
    }




async def get_setting(key, default=""):
    """Returns setting from memory cache or DB if missing."""
    if key in settings_cache:
        return settings_cache[key]
    
    async with db.execute('SELECT value FROM settings WHERE key = ?', (key,)) as cursor:
        row = await cursor.fetchone()
        val = row[0] if row else default
        settings_cache[key] = val
        return val

async def is_admin(user_id):
    """Checks if user is admin using memory cache."""
    return user_id in admin_cache or user_id == ROOT_ADMIN_ID

async def refresh_caches():
    """Updates memory caches from database."""
    global admin_cache, settings_cache
    # Refresh Admins
    async with db.execute('SELECT user_id FROM admins') as cursor:
        rows = await cursor.fetchall()
        admin_cache = {row[0] for row in rows}
    
    # Refresh Settings
    async with db.execute('SELECT key, value FROM settings') as cursor:
        rows = await cursor.fetchall()
        settings_cache = {row[0]: row[1] for row in rows}
    
    print("Caches refreshed successfully.")

if not os.path.exists("countries"):
    os.makedirs("countries")

import time
user_join_cache = {}

async def check_user_joined(user_id, bypass_cache=False):
    """Returns a list of active channels the user hasn't joined."""
    if await is_admin(user_id): return [] # Admins are exempt
    
    current_time = time.time()
    if not bypass_cache and user_id in user_join_cache:
        cached_data = user_join_cache[user_id]
        if current_time - cached_data['time'] < 60:
            return cached_data['not_joined']
    
    async with aiosqlite.connect("database.db") as db:
        try:
            async with db.execute('SELECT name, url, chat_id FROM channels WHERE is_active = 1') as cursor:
                channels = await cursor.fetchall()
        except:
            async with db.execute('SELECT name, url FROM channels WHERE is_active = 1') as cursor:
                channels = [(r[0], r[1], None) for r in await cursor.fetchall()]

    async def check_single_channel(name, url, db_chat_id):
        if db_chat_id:
            chat_id = db_chat_id
        else:
            chat_id = url.replace("https://t.me/", "@").replace("http://t.me/", "@")
            if not chat_id.startswith("@") and not chat_id.startswith("-100"):
                chat_id = "@" + chat_id
                
        try:
            member = await asyncio.wait_for(bot.get_chat_member(chat_id, user_id), timeout=5)
            if member.status in ['left', 'kicked']:
                return {"name": name, "url": url}
        except Exception as e:
            print(f"DEBUG: Error checking join for {name}: {e}")
            return {"name": name, "url": url}
        return None

    tasks = [check_single_channel(name, url, db_chat_id) for name, url, db_chat_id in channels]
    results = await asyncio.gather(*tasks)
    
    not_joined = [res for res in results if res is not None]
    
    user_join_cache[user_id] = {'time': current_time, 'not_joined': not_joined}
    return not_joined

async def show_force_join(chat_id, not_joined):
    text = "🛑 <b>Access Denied!</b>\n\nYou must join our channels below to use this bot:"
    markup = InlineKeyboardMarkup()
    for chan in not_joined:
        markup.add(InlineKeyboardButton(chan["name"], url=chan["url"]))
    markup.add(InlineKeyboardButton("✅ I Have Joined", callback_data="check_join"))
    await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "check_join")
async def check_join_callback(call):
    not_joined = await check_user_joined(call.from_user.id, bypass_cache=True)
    if not_joined:
        await bot.answer_callback_query(call.id, "❌ You haven't joined all channels yet!", show_alert=True)
        # We don't necessarily need to resend, but it's good to update
    else:
        await bot.answer_callback_query(call.id, "✅ Thank you! Access granted.")
        await bot.delete_message(call.message.chat.id, call.message.message_id)
        # Create a mock message to call send_welcome
        from telebot import types
        mock_msg = types.Message(
            message_id=0,
            from_user=call.from_user,
            date=0,
            chat=call.message.chat,
            content_type='text',
            options={},
            json_string=''
        )
        await send_welcome(mock_msg)

from telebot.asyncio_handler_backends import BaseMiddleware, CancelUpdate

class ForceJoinMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()
        self.update_types = ['message', 'callback_query']

    async def pre_process(self, message_or_call, data):
        if hasattr(message_or_call, 'data') and message_or_call.data == "check_join":
            return
            
        user_id = message_or_call.from_user.id
        if await is_admin(user_id):
            return
            
        not_joined = await check_user_joined(user_id)
        if not_joined:
            chat_id = message_or_call.message.chat.id if hasattr(message_or_call, 'data') else message_or_call.chat.id
            
            if hasattr(message_or_call, 'data'):
                try:
                    await bot.answer_callback_query(message_or_call.id, "❌ Please join all channels first!", show_alert=True)
                except:
                    pass
                
            await show_force_join(chat_id, not_joined)
            return CancelUpdate()

    async def post_process(self, message_or_call, data, exception):
        pass

bot.setup_middleware(ForceJoinMiddleware())

@bot.message_handler(commands=['start'])
async def send_welcome(message):
    user_id = message.from_user.id
    # Forced Join Check
    not_joined = await check_user_joined(user_id)
    if not_joined:
        await show_force_join(message.chat.id, not_joined)
        return

    # Maintenance Check
    if not await is_admin(user_id):
        status = await get_setting("bot_status", "Running")
        if status == "Maintenance":
            await bot.reply_to(message, "⚠️ *Bot is currently under maintenance.*\nPlease try again later.", parse_mode="Markdown")
            return

    # Register user in DB
    async with aiosqlite.connect("database.db") as db:
        await db.execute('INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)', (user_id, message.from_user.username))
        await db.commit()

    is_dev = (user_id == ROOT_ADMIN_ID)
    is_adm = await is_admin(user_id)
    
    # Premium buttons with custom attributes (IDs must be integers)
    def p_btn(text, emoji, style=None):
        return {"text": f"{emoji} {text}"}

    rows = [
        [p_btn("Get Number", "📞", "success"), p_btn("Stock Status", "📊", "success")],
        [p_btn("Download OTP", "📥", "success"), p_btn("Live Traffic", "📡", "success")]
    ]
    
    if is_adm:
        rows.append([p_btn("My Balance", "💰", "success"), p_btn("Admin Panel", "⚙️", "primary")])
        rows.append([p_btn("Withdraw", "💸", "success")])
        if is_dev:
            rows.append([p_btn("Bot Developer", "👨‍💻", "primary")])
    else:
        rows.append([p_btn("My Balance", "💰", "success"), p_btn("Withdraw", "💸", "success")])

    rows.append([p_btn("Support", "🎧", "success")])
        
    markup = {
        "keyboard": rows,
        "resize_keyboard": True,
        "is_persistent": False
    }
    
    # Convert to JSON string for safe delivery
    markup_json = json.dumps(markup)
    
    welcome_text = (
        "🌟 <b>Welcome to SMART Bot!</b> 🌟\n\n"
        "💬 <i>Main Menu</i>\n\n"
        "👇 <b>Please select an option below:</b>"
    )
    await bot.send_message(message.chat.id, welcome_text, reply_markup=markup_json, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "download_otp_start")
async def download_otp_start_callback(call):
    try:
        await bot.answer_callback_query(call.id)
    except: pass
    
    text = "❓ <b>Are you sure you want to download your OTP logs?</b>"
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ Yes, Download", callback_data="download_otp_confirm"),
        InlineKeyboardButton("❌ No, Cancel", callback_data="download_otp_cancel")
    )
    await bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "download_otp_cancel")
async def download_otp_cancel_callback(call):
    try:
        await bot.answer_callback_query(call.id, "❌ Download cancelled.")
    except: pass
    await bot.delete_message(call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "download_otp_confirm")
async def download_otp_confirm_callback(call):
    user_id = call.from_user.id
    from datetime import datetime, timedelta
    import io
    
    await bot.answer_callback_query(call.id, "🔄 Generating your file...")
    
    # Get last 24 hours logs
    time_limit = (datetime.now() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('''
            SELECT number, country, service, otp, timestamp 
            FROM otp_logs 
            WHERE user_id = ? AND timestamp >= ?
            ORDER BY timestamp DESC
        ''', (user_id, time_limit)) as cursor:
            logs = await cursor.fetchall()
    
    if not logs:
        await bot.edit_message_text("❌ <b>No OTP logs found for the last 24 hours.</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
        return
        
    # Create TXT content
    output = io.StringIO()
    output.write(f"--- OTP HISTORY (LAST 24 HOURS) ---\n")
    output.write(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    output.write(f"User ID: {user_id}\n")
    output.write(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n")
    
    for num, country, service, otp, ts in logs:
        formatted_num = num if str(num).startswith('+') else f"+{num}"
        output.write(f"{formatted_num} | {country} | {service} | OTP: {otp}\n")
        
    output.write(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    output.write(f"Thank you for using SMART Bot!")
    
    # Convert to bytes for sending
    file_data = output.getvalue().encode('utf-8')
    output.close()
    
    file_name = f"OTP_Logs_{user_id}.txt"
    
    # Delete the confirm message and send document
    await bot.delete_message(call.message.chat.id, call.message.message_id)
    
    await bot.send_document(
        call.message.chat.id, 
        file_data, 
        visible_file_name=file_name,
        caption=f"📂 <b>Your OTP History</b>\n✅ Total: {len(logs)} messages found.",
        parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_country")
async def add_country_callback(call):
    if not await is_admin(call.from_user.id):
        return
    admin_states[call.from_user.id] = {"state": "waiting_service_name"}
    text = (
        "🌍 Add New Country\n\n"
        "Step 1 — Service Name\n\n"
        "Which service is this country for? Enter the service name.\n\n"
        "Example: FACEBOOK, WHATSAPP, TELEGRAM, TIKTOK\n\n"
        "Type 'cancel' to cancel this operation."
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="global_cancel"))
    await bot.send_message(call.message.chat.id, text, reply_markup=markup)
    await bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_panel")
async def admin_panel_callback(call_or_msg):
    user_id = call_or_msg.from_user.id
    chat_id = call_or_msg.chat.id if hasattr(call_or_msg, 'chat') else call_or_msg.message.chat.id
    msg_id = None if hasattr(call_or_msg, 'chat') else call_or_msg.message.message_id
    
    # Answer callback immediately to prevent timeout errors
    if hasattr(call_or_msg, 'id'):
        try:
            await bot.answer_callback_query(call_or_msg.id)
        except Exception:
            pass
            
    if not await is_admin(user_id):
        return
        
    markup_list = []
    
    # Helper to create premium admin button
    def a_btn(text, emoji, callback, style=None):
        return {"text": f"{emoji} {text}", "callback_data": callback}

    # Row 1: Country Management
    markup_list.append([a_btn("Country Management", "🌍", "admin_country_mgmt", "primary")])
    
    # Row 2: Add Country & Update Stock
    markup_list.append([
        a_btn("Add Country", "➕", "admin_add_country", "success"),
        a_btn("Update Stock", "🔄", "admin_update_stock", "primary")
    ])
    
    # Row 3: User Management
    markup_list.append([a_btn("User Management", "👥", "admin_user_mgmt", "primary")])
    
    # Row 4: Withdrawals
    markup_list.append([
        a_btn("Withdrawals", "💸", "admin_withdrawals", "primary")
    ])
    
    # Row 5: System Settings
    markup_list.append([a_btn("System Settings", "⚙️", "admin_system_settings", "primary")])
    
    # Row 6: Groups & Channels
    markup_list.append([
        a_btn("Groups", "👥", "admin_groups", "primary"),
        a_btn("Channels", "📢", "admin_channels", "primary")
    ])
    # Row 7: Admins & OTP Providers
    markup_list.append([
        a_btn("Admins", "👑", "admin_admins", "primary"),
        a_btn("OTP Providers", "📡", "admin_otp_providers", "primary")
    ])
    
    # Row: Add Admin directly
    markup_list.append([a_btn("➕ Add New Admin", "👤", "add_new_admin", "success")])
    
    # Row 8: Backup Users & Import Users
    markup_list.append([
        a_btn("Backup Users", "💾", "admin_backup_menu", "primary"),
        a_btn("Import Users", "📤", "admin_import_menu", "primary")
    ])
    
    # Row 9: Ban/Unban Users
    markup_list.append([
        a_btn("Ban/Unban Users", "🚫", "admin_ban_unban", "danger")
    ])

    # Row 10: Broadcast
    markup_list.append([
        a_btn("Broadcast", "📢", "admin_broadcast", "success")
    ])
    
    admin_markup_json = json.dumps({"inline_keyboard": markup_list})
    
    text = "🛠️ <b>Admin Panel</b>\n\n👇 <i>Select an option below:</i> "
    
    if msg_id:
        await bot.edit_message_text(text=text, chat_id=chat_id, message_id=msg_id, reply_markup=admin_markup_json, parse_mode="HTML")
    else:
        await bot.send_message(chat_id, text, reply_markup=admin_markup_json, parse_mode="HTML")


# ═══════════════════════════════════════════════════
# BROADCAST SYSTEM
# ═══════════════════════════════════════════════════

async def _broadcast_get_users():
    """Fetch all user IDs from the DB."""
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('SELECT user_id FROM users') as cursor:
            rows = await cursor.fetchall()
    return [row[0] for row in rows]

async def _do_broadcast_text(admin_id, text, target_users):
    """Worker: send a text broadcast to all target_users."""
    total = len(target_users)
    success = 0
    failed = 0
    BATCH = 25

    # Send ONE progress message — all updates will edit this single message
    prog = await bot.send_message(
        admin_id,
        f"<b>📊 Broadcast Progress:</b> 0/{total} (0%)\n<b>✅ Sent:</b> 0 | <b>❌ Failed:</b> 0",
        parse_mode="HTML"
    )
    prog_id = prog.message_id

    for i in range(0, total, BATCH):
        batch = target_users[i:i + BATCH]
        tasks = [_safe_send_text(uid, text) for uid in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if r is True:
                success += 1
            else:
                failed += 1
        done = i + len(batch)
        pct = done / total * 100
        try:
            await bot.edit_message_text(
                f"<b>📊 Broadcast Progress:</b> {done}/{total} ({pct:.0f}%)\n"
                f"<b>✅ Sent:</b> {success} | <b>❌ Failed:</b> {failed}",
                admin_id, prog_id, parse_mode="HTML"
            )
        except Exception:
            pass
        await asyncio.sleep(0.3)

    # Final edit — replace progress with completion report
    report = (
        f"<b>✅ Broadcast Completed!</b>\n\n"
        f"<b>📊 Results:</b>\n"
        f"<b>✅ Sent:</b> {success}\n"
        f"<b>❌ Failed:</b> {failed}\n"
        f"<b>👥 Total:</b> {total}\n"
        f"<b>📈 Success Rate:</b> {success/total*100:.1f}%\n\n"
        f"<b>📝 Preview:</b> {text[:60]}{'...' if len(text) > 60 else ''}"
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel"))
    try:
        await bot.edit_message_text(report, admin_id, prog_id, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass

async def _safe_send_text(uid, text):
    try:
        msg = f"<b>📢 Admin Broadcast</b>\n\n{text}"
        await bot.send_message(uid, msg, parse_mode="HTML")
        return True
    except Exception:
        return False

async def _do_broadcast_photo(admin_id, file_id, caption, target_users):
    """Worker: send a photo broadcast."""
    total = len(target_users)
    success = 0
    failed = 0
    broadcast_caption = f"<b>📢 Admin Broadcast</b>\n\n{caption}" if caption else "<b>📢 Admin Broadcast</b>"
    BATCH = 25

    prog = await bot.send_message(
        admin_id,
        f"<b>📸 Photo Broadcast Progress:</b> 0/{total} (0%)\n<b>✅ Sent:</b> 0 | <b>❌ Failed:</b> 0",
        parse_mode="HTML"
    )
    prog_id = prog.message_id

    for i in range(0, total, BATCH):
        batch = target_users[i:i + BATCH]
        tasks = [_safe_send_photo(uid, file_id, broadcast_caption) for uid in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if r is True:
                success += 1
            else:
                failed += 1
        done = i + len(batch)
        pct = done / total * 100
        try:
            await bot.edit_message_text(
                f"<b>📸 Photo Broadcast Progress:</b> {done}/{total} ({pct:.0f}%)\n"
                f"<b>✅ Sent:</b> {success} | <b>❌ Failed:</b> {failed}",
                admin_id, prog_id, parse_mode="HTML"
            )
        except Exception:
            pass
        await asyncio.sleep(0.3)
    report = (
        f"<b>✅ Photo Broadcast Completed!</b>\n\n"
        f"<b>✅ Sent:</b> {success}\n"
        f"<b>❌ Failed:</b> {failed}\n"
        f"<b>👥 Total:</b> {total}\n"
        f"<b>📈 Success Rate:</b> {success/total*100:.1f}%"
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel"))
    try:
        await bot.edit_message_text(report, admin_id, prog_id, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass

async def _safe_send_photo(uid, file_id, caption):
    try:
        await bot.send_photo(uid, file_id, caption=caption, parse_mode="HTML")
        return True
    except Exception:
        return False

async def _do_broadcast_forward(admin_id, from_chat_id, message_id, target_users):
    """Worker: copy-forward a message broadcast."""
    total = len(target_users)
    success = 0
    failed = 0
    BATCH = 25

    prog = await bot.send_message(
        admin_id,
        f"<b>🔄 Forward Broadcast Progress:</b> 0/{total} (0%)\n<b>✅ Sent:</b> 0 | <b>❌ Failed:</b> 0",
        parse_mode="HTML"
    )
    prog_id = prog.message_id

    for i in range(0, total, BATCH):
        batch = target_users[i:i + BATCH]
        tasks = [_safe_copy_message(uid, from_chat_id, message_id) for uid in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if r is True:
                success += 1
            else:
                failed += 1
        done = i + len(batch)
        if done < total:
            pct = done / total * 100
            try:
                await bot.send_message(admin_id, f"<b>🔄 Forward Broadcast:</b> {done}/{total} ({pct:.0f}%)", parse_mode="HTML")
            except Exception:
                pass
        await asyncio.sleep(0.3)
    report = (
        f"<b>✅ Forward Broadcast Completed!</b>\n\n"
        f"<b>✅ Sent:</b> {success} | <b>❌ Failed:</b> {failed}\n"
        f"<b>👥 Total:</b> {total}\n"
        f"<b>📈 Success Rate:</b> {success/total*100:.1f}%"
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel"))
    try:
        await bot.send_message(admin_id, report, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass

async def _safe_copy_message(uid, from_chat_id, message_id):
    try:
        await bot.copy_message(uid, from_chat_id, message_id)
        return True
    except Exception:
        return False

async def show_broadcast_menu(chat_id, message_id=None):
    """Show the broadcast selection menu."""
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('SELECT COUNT(*) FROM users') as cursor:
            total = (await cursor.fetchone())[0]
    text = (
        f"<b>📢 Broadcast Message</b>\n\n"
        f"<b>👥 Total Users:</b> {total}\n\n"
        "Select broadcast type:"
    )
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(f"✉️ Text Broadcast ({total} users)", callback_data="broadcast_text"),
        InlineKeyboardButton("📸 Photo Broadcast", callback_data="broadcast_photo"),
        InlineKeyboardButton("🔄 Forward/Copy Broadcast", callback_data="broadcast_forward"),
        InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel")
    )
    if message_id:
        try:
            await bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="HTML")
        except Exception:
            await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
    else:
        await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast")
async def admin_broadcast_callback(call):
    if not await is_admin(call.from_user.id): return
    await bot.answer_callback_query(call.id)
    await show_broadcast_menu(call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "broadcast_text")
async def broadcast_text_callback(call):
    if not await is_admin(call.from_user.id): return
    await bot.answer_callback_query(call.id)
    admin_states[call.from_user.id] = {"state": "waiting_broadcast_text", "msg_id": call.message.message_id}
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="admin_broadcast"))
    await bot.edit_message_text(
        "<b>✉️ Text Broadcast</b>\n\nType your broadcast message below.\n\n<i>Type 'cancel' to cancel.</i>",
        call.message.chat.id, call.message.message_id,
        reply_markup=markup, parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data == "broadcast_photo")
async def broadcast_photo_callback(call):
    if not await is_admin(call.from_user.id): return
    await bot.answer_callback_query(call.id)
    admin_states[call.from_user.id] = {"state": "waiting_broadcast_photo", "msg_id": call.message.message_id}
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="admin_broadcast"))
    await bot.edit_message_text(
        "<b>📸 Photo Broadcast</b>\n\nSend a photo (with optional caption). It will be sent to all users.\n\n<i>Type 'cancel' to cancel.</i>",
        call.message.chat.id, call.message.message_id,
        reply_markup=markup, parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data == "broadcast_forward")
async def broadcast_forward_callback(call):
    if not await is_admin(call.from_user.id): return
    await bot.answer_callback_query(call.id)
    admin_states[call.from_user.id] = {"state": "waiting_broadcast_forward", "msg_id": call.message.message_id}
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="admin_broadcast"))
    await bot.edit_message_text(
        "<b>🔄 Forward Broadcast</b>\n\nForward any message/post to me. It will be copied to all users.\n\n<i>Type 'cancel' to cancel.</i>",
        call.message.chat.id, call.message.message_id,
        reply_markup=markup, parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data == "broadcast_confirm")
async def broadcast_confirm_callback(call):
    if not await is_admin(call.from_user.id): return
    await bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    state_data = admin_states.get(user_id, {})
    if state_data.get("state") != "waiting_broadcast_confirm":
        return
    broadcast_text = state_data.get("broadcast_text", "")
    del admin_states[user_id]
    try:
        await bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    target_users = await _broadcast_get_users()
    total = len(target_users)
    await bot.send_message(
        user_id,
        f"<b>📢 Broadcast Started!</b>\n\n<b>👥 Users:</b> {total}\n<b>⚡ Sending in batches...</b>",
        parse_mode="HTML"
    )
    asyncio.create_task(_do_broadcast_text(user_id, broadcast_text, target_users))

@bot.callback_query_handler(func=lambda call: call.data == "broadcast_cancel")
async def broadcast_cancel_callback(call):
    if not await is_admin(call.from_user.id): return
    await bot.answer_callback_query(call.id, "Broadcast cancelled.")
    if call.from_user.id in admin_states:
        del admin_states[call.from_user.id]
    await show_broadcast_menu(call.message.chat.id, call.message.message_id)

# ═══════════════════════════════════════════════════
# END BROADCAST SYSTEM
# ═══════════════════════════════════════════════════

@bot.callback_query_handler(func=lambda call: call.data == "admin_otp_providers")
async def admin_otp_providers_callback(call):
    if not await is_admin(call.from_user.id): return
    await bot.answer_callback_query(call.id)
    
    status = await get_setting("api_system_status", "Disabled")
    status_emoji = "🟢" if status == "Enabled" else "🔴"
    status_text = "Running" if status == "Enabled" else "Stopped"
    
    text = (
        "⚙️ <b>OTP Providers Management</b>\n\n"
        "<b>Current System:</b> All Panel API\n"
        f"<b>Status:</b> {status_emoji} {status_text}\n\n"
        "Select a system to manage:"
    )
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton(f"      {status_emoji} API System Settings", callback_data="admin_api_settings"))
    markup.row(InlineKeyboardButton("📊 Live View SMS", callback_data="admin_live_view_sms"))
    markup.row(InlineKeyboardButton("Group OTP Provider — 🔴 Not Configured", callback_data="admin_group_otp"))
    markup.row(InlineKeyboardButton("Back to Admin", callback_data="admin_panel"))
    
    await bot.edit_message_text(text=text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
    


@bot.callback_query_handler(func=lambda call: call.data == "admin_group_otp")
async def admin_group_otp_callback(call):
    if not await is_admin(call.from_user.id): return
    try:
        await bot.answer_callback_query(call.id)
    except: pass
    text = (
        "📡 <b>Group OTP Provider</b>\n\n"
        "🔴 <b>Status:</b> Not Configured\n\n"
        "This feature allows receiving OTPs via a Telegram Group.\n"
        "To configure, add the bot to a group and set it as the OTP source.\n\n"
        "<i>Feature coming soon or configure manually.</i>"
    )
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("↩️ Back to Providers", callback_data="admin_otp_providers"))
    await bot.edit_message_text(text=text, chat_id=call.message.chat.id,
        message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_api_settings")
async def admin_api_settings_callback(call, answer=True):
    if not await is_admin(call.from_user.id): return
    if answer:
        try:
            await bot.answer_callback_query(call.id)
        except: pass
    
    status = await get_setting("api_system_status", "Disabled")
    url = await get_setting("api_url", "http://127.0.0.1:8080/api/get_sms")
    key = await get_setting("api_key", "b98d92b7faa525364aadc5fbea392a2b")
    
    status_emoji = "🟢" if status == "Enabled" else "🔴"
    toggle_text = "Turn OFF" if status == "Enabled" else "Turn ON"
    toggle_emoji = "🔴" if status == "Enabled" else "🟢"
    
    text = (
        f"📡 <b>All Panel API Settings</b>\n\n"
        f"<b>System Status:</b> {status_emoji} {status}\n"
        f"<b>API URL:</b> {url}\n"
        f"<b>API Key:</b> <code>{key}</code>\n\n"
        "Use buttons below to configure the API system."
    )
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton(f"{toggle_emoji} {toggle_text}", callback_data="api_toggle"))
    markup.row(InlineKeyboardButton("🔗 Set API URL", callback_data="api_set_url"))
    markup.row(InlineKeyboardButton("🔑 Set API Token", callback_data="api_set_token"))
    markup.row(InlineKeyboardButton("📊 Live View SMS", callback_data="admin_live_view_sms"))
    markup.row(InlineKeyboardButton("🔙 Back to Providers", callback_data="admin_otp_providers"))
    
    try:
        await bot.edit_message_text(text=text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        if "message is not modified" not in str(e):
            print(f"DEBUG: Refresh API Settings Error: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "api_toggle")
async def api_toggle_callback(call):
    if not await is_admin(call.from_user.id): return
    
    current = await get_setting("api_system_status", "Disabled")
    new_status = "Enabled" if current == "Disabled" else "Disabled"
    
    async with aiosqlite.connect("database.db") as db:
        await db.execute('UPDATE settings SET value = ? WHERE key = "api_system_status"', (new_status,))
        await db.commit()
    
    # CRITICAL: Update memory cache so the UI refresh sees the new value
    settings_cache["api_system_status"] = new_status
    
    try:
        await bot.answer_callback_query(call.id, f"✅ API System {new_status}!")
    except: pass
    
    await admin_api_settings_callback(call, answer=False)


@bot.callback_query_handler(func=lambda call: call.data == "admin_live_view_sms")
async def admin_live_view_sms_callback(call):
    if not await is_admin(call.from_user.id): return
    await bot.answer_callback_query(call.id, "🔍 Fetching last 3 OTPs...")
    
    api_url = await get_setting("api_url", "http://127.0.0.1:8080/api/get_sms")
    api_key = await get_setting("api_key", "")
    
    # Simple request logic (assuming the API returns a list of SMS)
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            # Add API key if needed (customize based on your API structure)
            params = {"api_key": api_key} if api_key else {}
            async with session.get(api_url, params=params, timeout=10) as response:
                if response.status == 200:
                    json_resp = await response.json()
                    data = json_resp.get("data", [])
                    
                    if isinstance(data, list) and len(data) > 0:
                        last_3 = data[:3]
                        
                        table_text = "📊 <b>Live OTP View (Last 3)</b>\n\n"
                        # Header with standard spacing
                        table_text += "F | S | <code>Number     | OTP  </code>\n"
                        table_text += "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        
                        for sms in last_3:
                            raw_num = str(sms.get("number", "N/A"))
                            clean_num = raw_num[-10:]
                            svc_name = str(sms.get("service", "N/A"))
                            otp_val = str(sms.get("otp", "N/A"))[:6]
                            
                            country_iso = "🌍"
                            sms_country = str(sms.get("country", "")).upper()
                            if len(sms_country) == 2:
                                country_iso = sms_country
                            else:
                                for c_name, c_data in country_map.items():
                                    if c_name.upper() in sms_country:
                                        country_iso = c_data[0]
                                        break
                            
                            f_html = next((v[1] for k, v in country_map.items() if v[0] == country_iso), "🌍")

                            sms_text = str(sms.get("sms", "")).upper()
                            svc_name = str(sms.get("service", "PANEL")).upper()
                            
                            if svc_name == "PANEL":
                                if "TIKTOK" in sms_text: svc_name = "TIKTOK"
                                elif "FACEBOOK" in sms_text or "FB" in sms_text: svc_name = "FACEBOOK"
                                elif "WHATSAPP" in sms_text or "WA" in sms_text: svc_name = "WHATSAPP"
                                elif "TELEGRAM" in sms_text or "TG" in sms_text: svc_name = "TELEGRAM"
                                elif "GOOGLE" in sms_text or "G-" in sms_text: svc_name = "GOOGLE"
                            
                            s_id = "📱"
                            s_html = "📱"
                            
                            table_text += f"{f_html} | {s_html} | <code>{clean_num:<10} | {otp_val:<6}</code>\n"
                        
                        table_text += "━━━━━━━━━━━━━━━━━━━━━━━━━"
                    else:
                        table_text = "📊 <b>Live OTP View</b>\n\n❌ No recent OTPs found in API."
                else:
                    table_text = f"📊 <b>Live OTP View</b>\n\n❌ API Error: Status {response.status}"
    except Exception as e:
        table_text = f"📊 <b>Live OTP View</b>\n\n❌ Connection Error: {e}"
    
    import datetime
    now_time = datetime.datetime.now().strftime("%H:%M:%S")
    table_text += f"\n\n⏱ <b>Last Update:</b> {now_time}"

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Refresh", callback_data="admin_live_view_sms"))
    markup.add(InlineKeyboardButton("Back", callback_data="admin_otp_providers"))

    try:
        await bot.edit_message_text(table_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        if "message is not modified" not in str(e):
            print(f"Error updating live view: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "api_set_url")
async def api_set_url_callback(call):
    if not await is_admin(call.from_user.id): return
    await bot.answer_callback_query(call.id)
    admin_states[call.from_user.id] = {"state": "waiting_api_url", "msg_id": call.message.message_id}
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✖️ Cancel", callback_data="admin_api_settings"))
    await bot.send_message(call.message.chat.id, "🔗 Please send the new **API URL**:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "api_set_token")
async def api_set_token_callback(call):
    if not await is_admin(call.from_user.id): return
    await bot.answer_callback_query(call.id)
    admin_states[call.from_user.id] = {"state": "waiting_api_key", "msg_id": call.message.message_id}
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✖️ Cancel", callback_data="admin_api_settings"))
    await bot.send_message(call.message.chat.id, "🔑 Please send the new **API Token/Key**:", reply_markup=markup, parse_mode="Markdown")





@bot.callback_query_handler(func=lambda call: call.data in ["admin_backup_menu", "admin_import_menu"])
async def admin_backup_import_menus(call):
    print(f"DEBUG: Admin Menu Callback -> {call.data} from {call.from_user.id}")
    if not await is_admin(call.from_user.id): 
        print(f"DEBUG: Permission Denied for {call.from_user.id}")
        return
    if call.data == "admin_backup_menu":
        await admin_backup_menu_callback(call)
    else:
        await admin_import_menu_callback(call)

@bot.callback_query_handler(func=lambda call: call.data.startswith("backup_") or call.data.startswith("import_"))
async def admin_process_backup_import(call):
    print(f"DEBUG: Backup/Import Action -> {call.data} from {call.from_user.id}")
    if not await is_admin(call.from_user.id): return
    if call.data.startswith("backup_"):
        await process_backup_callback(call)
    else:
        await process_import_callback(call)

@bot.callback_query_handler(func=lambda call: call.data == "admin_withdrawals")
async def admin_withdrawals_callback(call):
    if not await is_admin(call.from_user.id): return
    
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('SELECT id, user_id, method, account, amount FROM withdrawals WHERE status = "Pending" ORDER BY timestamp DESC') as cursor:
            withdrawals = await cursor.fetchall()
            
    if not withdrawals:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel"))
        await bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="📥 *No Pending Withdrawals*",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        return
        
    text = f"📥 *Pending Withdrawals ({len(withdrawals)})*\n\n"
    markup = InlineKeyboardMarkup()
    
    for req_id, u_id, method, account, amount in withdrawals:
        btn_text = f"#{req_id} | ${amount:.2f} | {method}"
        markup.row(InlineKeyboardButton(btn_text, callback_data=f"adm_view_w_{req_id}"))
        
    markup.add(InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel"))
    
    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_view_w_"))
async def admin_view_withdrawal_callback(call):
    if not await is_admin(call.from_user.id): return
    
    req_id = call.data.replace("adm_view_w_", "")
    
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('SELECT user_id, method, account, amount, timestamp FROM withdrawals WHERE id = ?', (req_id,)) as cursor:
            row = await cursor.fetchone()
            
    if not row:
        await bot.answer_callback_query(call.id, "Request not found.", show_alert=True)
        await admin_withdrawals_callback(call)
        return
        
    u_id, method, account, amount, ts = row
    
    text = (
        f"📥 *Withdrawal Request #{req_id}*\n\n"
        f"👤 *User ID:* `{u_id}`\n"
        f"💳 *Method:* {method}\n"
        f"📱 *Account:* `{account}`\n"
        f"💰 *Amount:* ${amount:.4f}\n"
        f"🕒 *Time:* {ts}\n"
        "━━━━━━━━━━━━━━━━━━━"
    )
    
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ Approve", callback_data=f"adm_approve_w_{req_id}"),
        InlineKeyboardButton("❌ Cancel", callback_data=f"adm_cancel_w_{req_id}")
    )
    markup.row(InlineKeyboardButton("↩️ Back to List", callback_data="admin_withdrawals"))
    
    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin_user_mgmt")
async def admin_user_mgmt_callback(call):
    if not await is_admin(call.from_user.id):
        return
        
    async with aiosqlite.connect("database.db") as db:
        # Total Users
        async with db.execute('SELECT COUNT(*) FROM users') as cursor:
            total_users = (await cursor.fetchone())[0]
            
        # 24H OTPs
        async with db.execute("SELECT COUNT(*) FROM otp_logs WHERE timestamp >= datetime('now', '-1 day')") as cursor:
            otp_24h = (await cursor.fetchone())[0]
            
        # Total User Balance
        async with db.execute('SELECT SUM(balance) FROM users') as cursor:
            total_balance = (await cursor.fetchone())[0] or 0.0
            
        # Today's User Balance (Placeholder: users who joined today or balance added today)
        # For now, we'll just show 0 or calculate if possible.
        # Let's show balance of users who joined today as a proxy if no deposit table.
        async with db.execute("SELECT SUM(balance) FROM users WHERE joined_at >= date('now')") as cursor:
            today_balance = (await cursor.fetchone())[0] or 0.0

    import datetime
    now = datetime.datetime.now().strftime("%H:%M:%S")
    
    text = (
        "<b>📊 Bot Statistics</b>\n\n"
        "<b>📊 SMS Statistics</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "<b>📩 24H OTP Stats:</b>\n"
        f"┣ Received: {otp_24h}\n"
        f"┗ Delivered: {otp_24h}\n\n"
        "<b>💰 Balance Stats:</b>\n"
        f"┣ Total User Balance: ${total_balance:.2f}\n"
        f"┗ Today User Balance: ${today_balance:.2f}\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Users:</b> {total_users}\n"
        f"⏱️ <b>Last Update:</b> {now}"
    )
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel"))
    
    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=markup,
        parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin_system_settings")
async def admin_system_settings_callback(call):
    if not await is_admin(call.from_user.id):
        return
        
    markup = InlineKeyboardMarkup()
    btn_stats = InlineKeyboardButton("Bot Statistics", callback_data="admin_user_mgmt")
    btn_edit = InlineKeyboardButton("System Edit", callback_data="admin_system_edit")
    btn_back = InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel")
    
    markup.row(btn_stats)
    markup.row(btn_edit)
    markup.row(btn_back)
    
    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="⚙️ *Bot Settings*\n\nSelect an option to configure bot settings:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

async def render_system_edit(chat_id, message_id):
    settings = {}
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('SELECT key, value FROM settings') as cursor:
            rows = await cursor.fetchall()
            for key, val in rows:
                settings[key] = val
                
    bot_status = settings.get("bot_status", "Running")
    withdraw_status = settings.get("withdrawal_status", "Disabled")
    min_withdraw = settings.get("min_withdraw", "1.0000")
    main_channel = settings.get("main_channel", "https://t.me/SMART_TECH")
    cooldown = settings.get("cooldown", "6")
    otp_link = settings.get("otp_view_link", "https://t.me/SMART_TECH")
    nums_per_req = settings.get("numbers_per_request", "2")
    support_username = settings.get("support_username", "")
    support_name = settings.get("support_name", "Support")
    
    bot_emoji = "🟢" if bot_status == "Running" else "🔴"
    withdraw_emoji = "🟢" if withdraw_status == "Enabled" else "🔴"
    support_display = f"@{support_username}" if support_username else "❌ Not Set"
    
    text = (
        "⚙️ <b>System Edit</b>\n\n"
        f"🤖 <b>Bot Status:</b> {bot_emoji} {bot_status}\n"
        f"💸 <b>Withdrawal:</b> {withdraw_emoji} {withdraw_status}\n"
        f"💰 <b>Min Withdraw:</b> ${min_withdraw}\n"
        f"📢 <b>Main Channel:</b> {main_channel}\n"
        f"⏱ <b>Cooldown:</b> {cooldown} seconds\n"
        f"🔗 <b>OTP View Link:</b>\n{otp_link}\n"
        f"🔢 <b>Numbers Per Request:</b> {nums_per_req}\n"
        f"🎧 <b>Support:</b> {support_display} ({support_name})\n\n"
        "Select system setting to edit:"
    )
    
    markup = InlineKeyboardMarkup()
    
    maintenance_btn_text = "Maintenance Turn OFF" if bot_status == "Maintenance" else "Maintenance Turn ON"
    markup.row(InlineKeyboardButton(maintenance_btn_text, callback_data="toggle_maintenance"))
    
    withdraw_btn_text = "Withdrawal Turn OFF" if withdraw_status == "Enabled" else "Withdrawal Turn ON"
    markup.row(InlineKeyboardButton(withdraw_btn_text, callback_data="toggle_withdrawal"))
    
    markup.row(InlineKeyboardButton("Min Withdraw", callback_data="edit_setting_min_withdraw"))
    markup.row(InlineKeyboardButton("👑 Manage Admins", callback_data="admin_admins"))
    markup.row(InlineKeyboardButton("Cooldown Timer", callback_data="edit_setting_cooldown"))
    markup.row(InlineKeyboardButton("Edit OTP View Link", callback_data="edit_setting_otp_link"))
    markup.row(InlineKeyboardButton("Numbers Per Request", callback_data="edit_setting_nums_per_req"))
    markup.row(InlineKeyboardButton("🎧 Set Support Username", callback_data="edit_setting_support_username"))
    markup.row(InlineKeyboardButton("✏️ Set Support Name", callback_data="edit_setting_support_name"))
    markup.row(InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel"))
    
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=markup,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception:
        await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)

@bot.callback_query_handler(func=lambda call: call.data == "admin_system_edit")
async def admin_system_edit_callback(call):
    if not await is_admin(call.from_user.id):
        return
    await render_system_edit(call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_setting_"))
async def edit_setting_callback(call):
    if not await is_admin(call.from_user.id): return
    
    setting_key = call.data.replace("edit_setting_", "")
    
    prompts = {
        "min_withdraw": "💰 Please enter the new Minimum Withdrawal amount:",
        "cooldown": "⏱ Please enter the new Cooldown Timer (in seconds):",
        "otp_link": "🔗 Please enter the new OTP View Link:",
        "nums_per_req": "🔢 Please enter the number of numbers per request (e.g. 2):",
        "support_username": "🎧 Enter the support Telegram username (without @):\n\n<i>Example: durov</i>",
        "support_name": "✏️ Enter the support display name:\n\n<i>Example: SmartTech Support</i>"
    }
    
    admin_states[call.from_user.id] = {
        "state": f"waiting_setting_{setting_key}",
        "msg_id": call.message.message_id
    }
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✖️ Cancel", callback_data="global_cancel"))
    
    await bot.send_message(call.message.chat.id, prompts.get(setting_key, "Enter new value:"), reply_markup=markup, parse_mode="HTML")
    await bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data in ["toggle_maintenance", "toggle_withdrawal"])
async def toggle_settings_callback(call):
    if not await is_admin(call.from_user.id): return
    
    key = "bot_status" if call.data == "toggle_maintenance" else "withdrawal_status"
    
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('SELECT value FROM settings WHERE key = ?', (key,)) as cursor:
            row = await cursor.fetchone()
            if row:
                current_val = row[0]
                if key == "bot_status":
                    new_val = "Maintenance" if current_val == "Running" else "Running"
                else:
                    new_val = "Enabled" if current_val == "Disabled" else "Disabled"
                
                await db.execute('UPDATE settings SET value = ? WHERE key = ?', (new_val, key))
                await db.commit()
    await refresh_caches()
    
    await render_system_edit(call.message.chat.id, call.message.message_id)
    await bot.answer_callback_query(call.id, "Setting updated!")

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_num_req_"))
async def set_num_req_callback(call):
    if not await is_admin(call.from_user.id): return
    
    new_val = call.data.replace("set_num_req_", "")
    
    async with aiosqlite.connect("database.db") as db:
        await db.execute('UPDATE settings SET value = ? WHERE key = "numbers_per_request"', (new_val,))
        await db.commit()
    await refresh_caches()
        
    await bot.answer_callback_query(call.id, f"Set to {new_val} numbers per request!")
    
    # Premium Header Format
    f_icon = next((v[1] for v in country_map.values() if v[0] == country_name.upper()), "🌍")
    s_key = service_name.upper()
    s_icon = "📱"
    
    text = (
        f"{f_icon} {country_name} | {s_icon} {service_name} | ${price:.4f}/OTP\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "👇 <b>Please select a service:</b>"
    )
    
    await render_system_edit(call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_admins")
async def admin_admins_callback(call_or_msg):
    # This can be called from a callback or a message (after adding admin)
    user_id = call_or_msg.from_user.id
    chat_id = call_or_msg.chat.id if hasattr(call_or_msg, 'chat') else call_or_msg.message.chat.id
    msg_id = None if hasattr(call_or_msg, 'chat') else call_or_msg.message.message_id

    if not await is_admin(user_id): return
    
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('SELECT user_id FROM admins') as cursor:
            admins = await cursor.fetchall()
            
    markup = InlineKeyboardMarkup(row_width=1)
    text = "👑 <b>Bot Administrators</b>\n\n"
    
    for (a_id,) in admins:
        # Try to find username from users table
        async with aiosqlite.connect("database.db") as db:
            async with db.execute('SELECT username FROM users WHERE user_id = ?', (a_id,)) as cursor:
                u_row = await cursor.fetchone()
                uname = u_row[0] if u_row and u_row[0] else "No Username"
        
        btn_text = f"👤 {uname} ({a_id})"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"view_admin_{a_id}"))
        
    markup.add(InlineKeyboardButton("✨ Add New Admin", callback_data="add_new_admin"))
    markup.add(InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel"))
    
    if msg_id:
        await bot.edit_message_text(text=text, chat_id=chat_id, message_id=msg_id, reply_markup=markup, parse_mode="HTML")
    else:
        await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
        
    if hasattr(call_or_msg, 'id'):
        await bot.answer_callback_query(call_or_msg.id)

@bot.callback_query_handler(func=lambda call: call.data == "add_new_admin")
async def add_new_admin_callback(call):
    if not await is_admin(call.from_user.id): return
    
    admin_states[call.from_user.id] = {"state": "waiting_new_admin_id", "msg_id": call.message.message_id}
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✖️ Cancel", callback_data="global_cancel"))
    
    await bot.send_message(call.message.chat.id, "🆔 Please enter the <b>Chat ID</b> of the new admin:", reply_markup=markup, parse_mode="HTML")
    await bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("view_admin_"))
async def view_admin_callback(call):
    if not await is_admin(call.from_user.id): return
    
    a_id = int(call.data.replace("view_admin_", ""))
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🗑️ Remove Admin", callback_data=f"del_admin_{a_id}"))
    markup.row(InlineKeyboardButton("↩️ Back to List", callback_data="admin_admins"))
    
    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"👑 <b>Admin Details</b>\n\n🆔 <b>Chat ID:</b> <code>{a_id}</code>\n\nDo you want to remove this admin?",
        reply_markup=markup,
        parse_mode="HTML"
    )
    await bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("del_admin_"))
async def del_admin_callback(call):
    if not await is_admin(call.from_user.id): return
    
    a_id = int(call.data.replace("del_admin_", ""))
    
    # Prevent deleting the root admin
    if a_id == ROOT_ADMIN_ID:
        await bot.answer_callback_query(call.id, "❌ This is the Main Root Admin. It cannot be deleted!", show_alert=True)
        return

    async with aiosqlite.connect("database.db") as db:
        await db.execute('DELETE FROM admins WHERE user_id = ?', (a_id,))
        await db.commit()
    await refresh_caches()
    
    await bot.answer_callback_query(call.id, "Admin removed successfully.")
    await admin_admins_callback(call)

@bot.callback_query_handler(func=lambda call: call.data == "admin_groups")
async def admin_groups_callback(call_or_msg):
    user_id = call_or_msg.from_user.id
    chat_id = call_or_msg.chat.id if hasattr(call_or_msg, 'chat') else call_or_msg.message.chat.id
    msg_id = None if hasattr(call_or_msg, 'chat') else call_or_msg.message.message_id
    
    if not await is_admin(user_id): return
    
    otp_link = await get_setting("otp_view_link", "Not Set")
    
    text = (
        "💬 <b>Group Settings</b>\n\n"
        "🔗 <b>Current OTP View Group:</b>\n"
        f"<code>{otp_link}</code>\n\n"
        "This is the group/channel where users are redirected when they click 🔔 <b>View OTP</b>."
    )
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("➕ Add New Group", callback_data="add_new_group"))
    markup.row(InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel"))
    
    if msg_id:
        await bot.edit_message_text(text=text, chat_id=chat_id, message_id=msg_id, reply_markup=markup, parse_mode="HTML")
    else:
        await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
        
    if hasattr(call_or_msg, 'id'):
        await bot.answer_callback_query(call_or_msg.id)

@bot.callback_query_handler(func=lambda call: call.data == "add_new_group")
async def add_new_group_callback(call):
    if not await is_admin(call.from_user.id): return
    
    admin_states[call.from_user.id] = {"state": "waiting_new_group_link", "msg_id": call.message.message_id}
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✖️ Cancel", callback_data="global_cancel"))
    
    await bot.send_message(call.message.chat.id, "🔗 Please send the <b>Link</b> for the new OTP View Group:", reply_markup=markup, parse_mode="HTML")
    await bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_channels")
async def admin_channels_callback(call_or_msg):
    user_id = call_or_msg.from_user.id
    chat_id = call_or_msg.chat.id if hasattr(call_or_msg, 'chat') else call_or_msg.message.chat.id
    msg_id = None if hasattr(call_or_msg, 'chat') else call_or_msg.message.message_id
    
    if not await is_admin(user_id): return
    
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('SELECT id, name, url, is_active FROM channels') as cursor:
            channels = await cursor.fetchall()
            
    text = "📢 <b>Channel Settings (Forced Join)</b>\n\nManage the channels users must join before using the bot."
    markup = InlineKeyboardMarkup(row_width=1)
    
    for c_id, c_name, c_url, is_active in channels:
        status_emoji = "🟢 ON" if is_active else "🔴 OFF"
        btn_text = f"{c_name} | {status_emoji}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"view_chan_{c_id}"))
        
    markup.add(InlineKeyboardButton("➕ Add New Channel", callback_data="add_new_channel"))
    markup.add(InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel"))
    
    if msg_id:
        await bot.edit_message_text(text=text, chat_id=chat_id, message_id=msg_id, reply_markup=markup, parse_mode="HTML")
    else:
        await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
        
    if hasattr(call_or_msg, 'id'):
        await bot.answer_callback_query(call_or_msg.id)

@bot.callback_query_handler(func=lambda call: call.data == "add_new_channel")
async def add_new_channel_callback(call):
    if not await is_admin(call.from_user.id): return
    admin_states[call.from_user.id] = {"state": "waiting_channel_name"}
    await bot.send_message(call.message.chat.id, "📛 Please send the <b>Name</b> for the new channel (e.g. ✅ Main Channel):", parse_mode="HTML")
    await bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "confirm_add_channel")
async def confirm_add_channel_callback(call):
    if not await is_admin(call.from_user.id): return
    state = admin_states.get(call.from_user.id)
    if not state or state["state"] != "confirming_channel": return
    
    name = state["channel_name"]
    c_id = state.get("channel_id")
    link = state["channel_link"]
    
    async with aiosqlite.connect("database.db") as db:
        try:
            await db.execute('INSERT INTO channels (name, url, chat_id) VALUES (?, ?, ?)', (name, link, c_id))
        except:
            await db.execute('INSERT INTO channels (name, url) VALUES (?, ?)', (name, link))
        await db.commit()
        
    del admin_states[call.from_user.id]
    await bot.answer_callback_query(call.id, "✅ Channel added!")
    await admin_channels_callback(call)

@bot.callback_query_handler(func=lambda call: call.data.startswith("view_chan_"))
async def view_chan_callback(call):
    if not await is_admin(call.from_user.id): return
    c_id = int(call.data.replace("view_chan_", ""))
    
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('SELECT name, url, is_active FROM channels WHERE id = ?', (c_id,)) as cursor:
            row = await cursor.fetchone()
            
    if not row: return
    name, url, is_active = row
    status_text = "🟢 Active" if is_active else "🔴 Inactive"
    
    text = (
        f"📢 <b>Channel Details</b>\n\n"
        f"📛 <b>Name:</b> {name}\n"
        f"🔗 <b>Link:</b> {url}\n"
        f"📊 <b>Status:</b> {status_text}"
    )
    
    markup = InlineKeyboardMarkup()
    toggle_text = "🔴 Turn OFF" if is_active else "🟢 Turn ON"
    markup.row(InlineKeyboardButton(toggle_text, callback_data=f"toggle_chan_{c_id}"))
    markup.row(InlineKeyboardButton("🗑️ Delete Channel", callback_data=f"del_chan_{c_id}"))
    markup.row(InlineKeyboardButton("↩️ Back to List", callback_data="admin_channels"))
    
    await bot.edit_message_text(text=text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
    await bot.answer_callback_query(call.id)

async def admin_backup_menu_callback(call):
    if not await is_admin(call.from_user.id): return
    
    text = "💾 <b>Backup Management</b>\n\nSelect the data you want to backup:"
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("👤 Users List (.txt)", callback_data="backup_users_txt"),
        InlineKeyboardButton("📦 Stock/Countries (.zip)", callback_data="backup_stock_zip"),
        InlineKeyboardButton("📂 Full Database (.db)", callback_data="backup_db_full"),
        InlineKeyboardButton("📦 All Data (.zip)", callback_data="backup_all_zip"),
        InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel")
    )
    await bot.edit_message_text(text=text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
    await bot.answer_callback_query(call.id)

async def admin_import_menu_callback(call):
    if not await is_admin(call.from_user.id): return
    
    text = "📤 <b>Import Management</b>\n\nSelect what you want to import:"
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("👤 Import Users (.txt)", callback_data="import_users_txt"),
        InlineKeyboardButton("📦 Import Stock (.zip)", callback_data="import_stock_zip"),
        InlineKeyboardButton("📂 Import Database (.db)", callback_data="import_db_full"),
        InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel")
    )
    await bot.edit_message_text(text=text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
    await bot.answer_callback_query(call.id)

async def process_backup_callback(call):
    if not await is_admin(call.from_user.id): return
    action = call.data.replace("backup_", "")
    chat_id = call.message.chat.id
    
    await bot.answer_callback_query(call.id, "Processing backup...")
    
    if action == "users_txt":
        async with aiosqlite.connect("database.db") as db:
            async with db.execute('SELECT user_id, username FROM users') as cursor:
                users = await cursor.fetchall()
        
        file_path = "users_backup.txt"
        with open(file_path, "w", encoding="utf-8") as f:
            for u_id, u_name in users:
                name = u_name if u_name else "N/A"
                f.write(f"{u_id}:{name}\n")
        
        with open(file_path, "rb") as f:
            await bot.send_document(chat_id, f, caption="👤 Users Backup List")
        os.remove(file_path)
        
    elif action == "stock_zip":
        shutil.make_archive("stock_backup", 'zip', "countries")
        with open("stock_backup.zip", "rb") as f:
            await bot.send_document(chat_id, f, caption="📦 Stock/Countries Backup")
        os.remove("stock_backup.zip")
        
    elif action == "db_full":
        with open("database.db", "rb") as f:
            await bot.send_document(chat_id, f, caption="📂 Full SQLite Database Backup")
            
    elif action == "all_zip":
        # Create a temp folder
        if not os.path.exists("temp_backup"): os.makedirs("temp_backup")
        # Copy DB
        shutil.copy("database.db", "temp_backup/database.db")
        # Copy Stock
        if os.path.exists("countries"):
            shutil.copytree("countries", "temp_backup/countries")
        
        shutil.make_archive("all_data_backup", 'zip', "temp_backup")
        with open("all_data_backup.zip", "rb") as f:
            await bot.send_document(chat_id, f, caption="📦 All Data Backup (DB + Stock)")
        
        # Cleanup
        os.remove("all_data_backup.zip")
        shutil.rmtree("temp_backup")

async def process_import_callback(call):
    if not await is_admin(call.from_user.id): return
    action = call.data.replace("import_", "")
    
    admin_states[call.from_user.id] = {"state": f"waiting_import_{action}"}
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✖️ Cancel", callback_data="admin_import_menu"))
    
    await bot.send_message(call.message.chat.id, f"📤 Please upload the <b>{action.upper()}</b> file to import:", reply_markup=markup, parse_mode="HTML")
    await bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_chan_"))
async def toggle_chan_callback(call):
    if not await is_admin(call.from_user.id): return
    c_id = int(call.data.replace("toggle_chan_", ""))
    
    async with aiosqlite.connect("database.db") as db:
        await db.execute('UPDATE channels SET is_active = 1 - is_active WHERE id = ?', (c_id,))
        await db.commit()
        
    await bot.answer_callback_query(call.id, "Status toggled!")
    await view_chan_callback(call)

@bot.callback_query_handler(func=lambda call: call.data == "admin_ban_unban")
async def admin_ban_unban_callback(call):
    if not await is_admin(call.from_user.id): return
    await bot.answer_callback_query(call.id)
    
    text = "🚫 <b>Ban Management</b>\n\nSelect an action:"
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🚫 Ban User", callback_data="ban_user_start"))
    markup.row(InlineKeyboardButton("✅ Unban User", callback_data="unban_user_start"))
    markup.row(InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel"))
    
    await bot.edit_message_text(text=text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data in ["ban_user_start", "unban_user_start"])
async def start_ban_unban_action(call):
    if not await is_admin(call.from_user.id): return
    await bot.answer_callback_query(call.id)
    
    action = "ban" if "ban_user" in call.data else "unban"
    admin_states[call.from_user.id] = {"state": f"waiting_{action}_id"}
    
    text = f"📝 Please enter the <b>User ID</b> you want to {action}:"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✖️ Cancel", callback_data="admin_ban_unban"))
    
    await bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_ban_") or call.data.startswith("confirm_unban_"))
async def finalize_ban_unban(call):
    if not await is_admin(call.from_user.id): return
    
    parts = call.data.split("_")
    action = parts[1] # ban or unban
    status = parts[2] # yes or no
    target_id = int(parts[3])
    
    if status == "no":
        await bot.answer_callback_query(call.id, "Operation cancelled.")
        await admin_ban_unban_callback(call)
        return
    
    async with aiosqlite.connect("database.db") as db:
        if action == "ban":
            await db.execute('INSERT OR IGNORE INTO banned_users (user_id) VALUES (?)', (target_id,))
            msg = f"🚫 User <code>{target_id}</code> has been BANNED."
        else:
            await db.execute('DELETE FROM banned_users WHERE user_id = ?', (target_id,))
            msg = f"✅ User <code>{target_id}</code> has been UNBANNED."
        await db.commit()
        
    await bot.answer_callback_query(call.id, "Success!")
    await bot.edit_message_text(msg, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
    await admin_ban_unban_callback(call)

@bot.callback_query_handler(func=lambda call: call.data == "admin_bot_mode")
async def admin_bot_mode_callback(call):
    if not await is_admin(call.from_user.id): return
    await bot.answer_callback_query(call.id)
    
    current_mode = await get_setting("bot_mode", "Normal")
    
    text = f"🤖 <b>Bot Mode Switch</b>\n\n<b>Current Mode:</b> {current_mode}\n\nSelect a mode below:"
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🌟 Normal Mode", callback_data="set_mode_Normal"))
    markup.row(InlineKeyboardButton("💎 Premium Mode", callback_data="set_mode_Premium"))
    markup.row(InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel"))
    
    await bot.edit_message_text(text=text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_mode_"))
async def set_bot_mode_callback(call):
    if not await is_admin(call.from_user.id): return
    new_mode = call.data.replace("set_mode_", "")
    
    async with aiosqlite.connect("database.db") as db:
        await db.execute('UPDATE settings SET value = ? WHERE key = "bot_mode"', (new_mode,))
        await db.commit()
        
    await bot.answer_callback_query(call.id, f"Mode set to {new_mode}!")
    try:
        await admin_bot_mode_callback(call)
    except:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("del_chan_"))
async def del_chan_callback(call):
    if not await is_admin(call.from_user.id): return
    c_id = int(call.data.replace("del_chan_", ""))
    
    async with aiosqlite.connect("database.db") as db:
        await db.execute('DELETE FROM channels WHERE id = ?', (c_id,))
        await db.commit()
        
    await bot.answer_callback_query(call.id, "Channel deleted!")
    await admin_channels_callback(call)

@bot.callback_query_handler(func=lambda call: call.data == "admin_country_mgmt")
async def admin_country_mgmt_callback(call):
    if not await is_admin(call.from_user.id):
        return
        
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('SELECT id, country_name, flag, stock FROM countries') as cursor:
            countries = await cursor.fetchall()
            
    markup = InlineKeyboardMarkup(row_width=1)
    if not countries:
        markup.add(InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel"))
        await bot.edit_message_text("No countries added yet.", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
        return
        
    for c_id, c_name, c_flag, c_stock in countries:
        btn_text = f"{c_flag} {c_name} (Stock: {c_stock})"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"edit_country_{c_id}"))
        
    markup.add(InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel"))
    
    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="🌍 *Country Management*\n\nSelect a country to edit:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin_update_stock")
async def admin_update_stock_callback(call):
    if not await is_admin(call.from_user.id):
        return
        
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('SELECT id, country_name, flag, stock FROM countries') as cursor:
            countries = await cursor.fetchall()
            
    markup = InlineKeyboardMarkup(row_width=1)
    if not countries:
        markup.add(InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel"))
        await bot.edit_message_text("No countries added yet.", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
        return
        
    for c_id, c_name, c_flag, c_stock in countries:
        btn_text = f"{c_flag} {c_name} (Stock: {c_stock})"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"start_update_stock_{c_id}"))
        
    markup.add(InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel"))
    
    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="📁 *Update Stock*\n\nSelect a country to update its stock:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("start_update_stock_"))
async def start_update_stock_callback(call):
    if not await is_admin(call.from_user.id):
        return
        
    country_id = call.data.replace("start_update_stock_", "")
    
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('SELECT country_name, flag, stock, country_code FROM countries WHERE id = ?', (country_id,)) as cursor:
            row = await cursor.fetchone()
            
    if not row:
        await bot.answer_callback_query(call.id, "Country not found.", show_alert=True)
        return
        
    c_name, c_flag, c_stock, c_code = row
    
    admin_states[call.from_user.id] = {
        "state": "waiting_update_stock_file",
        "country_id": country_id,
        "country_name": c_name
    }
    
    msg_text = (
        f"📦 *Update Stock: {c_flag} {c_name}*\n\n"
        f"📊 *Current Status:*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🔢 *Current Stock:* {c_stock} numbers\n"
        f"🆔 *Country Code:* {c_code}\n\n"
        f"📁 *Upload Instructions:*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"1️⃣ Create a text file (.txt)\n"
        f"2️⃣ Add one phone number per line\n"
        f"3️⃣ Numbers should be digits only (7+ digits)\n"
        f"4️⃣ Upload the file here\n\n"
        f"📋 *Example file format:*\n"
        f"`255123456789` \n"
        f"`255987654321` \n"
        f"`255555555555` \n\n"
        f"⚠️ *Old stock will be REPLACED with the new numbers*\n\n"
        f"Type `cancel` to abort."
    )
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="admin_country_mgmt")) # Going back to mgmt or panel
    
    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=msg_text,
        reply_markup=markup,
        parse_mode="Markdown"
    )

async def render_edit_country(chat_id, message_id, country_id, call_id=None):
    async with aiosqlite.connect("database.db") as db:
        try:
            async with db.execute('SELECT country_name, country_code, flag, country_emoji_id, per_otp_earn, stock, status FROM countries WHERE id = ?', (country_id,)) as cursor:
                row = await cursor.fetchone()
        except:
            async with db.execute('SELECT country_name, country_code, flag, country_emoji_id, per_otp_earn, stock FROM countries WHERE id = ?', (country_id,)) as cursor:
                row_temp = await cursor.fetchone()
                if row_temp:
                    row = (*row_temp, "Enabled")
                else:
                    row = None
            
    if not row:
        if call_id:
            await bot.answer_callback_query(call_id, "Country not found.", show_alert=True)
        return
        
    c_name, c_code, c_flag, c_emoji_id, c_earn, c_stock, c_status = row
    
    c_emoji_id_display = c_emoji_id if c_emoji_id and c_emoji_id != "Not Set" else "Not Set"
    
    msg_text = (
        f"✏️ *Edit Country: {c_name}*\n\n"
        f"🆔 Code: {c_code}\n"
        f"🔑 ID: {c_name}\n"
        f"🎌 Flag: {c_flag}\n"
        f"Emoji: {c_emoji_id_display}\n"
        f"💰 Per OTP Earn: ${c_earn:.4f}\n"
        f"📦 Stock: {c_stock}\n"
        f"📊 Status: {c_status}\n\n"
        f"Select what you want to edit:"
    )
    
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Edit Name", callback_data=f"admin_edit_name_{country_id}"),
        InlineKeyboardButton("Edit Flag", callback_data=f"admin_edit_flag_{country_id}")
    )
    markup.row(
        InlineKeyboardButton("Edit Code", callback_data=f"admin_edit_code_{country_id}"),
        InlineKeyboardButton("Toggle Status", callback_data=f"admin_toggle_status_{country_id}")
    )
    markup.row(
        InlineKeyboardButton("Edit Premium Emoji ID", callback_data=f"admin_edit_emoji_{country_id}")
    )
    markup.row(
        InlineKeyboardButton(f"💰 Per OTP: ${c_earn:.4f}", callback_data=f"admin_edit_otp_{country_id}")
    )
    markup.row(
        InlineKeyboardButton("🗑 Clear Numbers", callback_data=f"admin_clear_nums_{country_id}"),
        InlineKeyboardButton("Delete Country", callback_data=f"admin_delete_c_{country_id}")
    )
    markup.row(
        InlineKeyboardButton("↩️ Back to Countries", callback_data="admin_country_mgmt")
    )
    
    await bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=msg_text,
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_country_"))
async def edit_country_callback(call):
    if not await is_admin(call.from_user.id): return
    country_id = call.data.split("edit_country_")[1]
    await render_edit_country(call.message.chat.id, call.message.message_id, country_id, call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_toggle_status_") or 
                                             call.data.startswith("admin_clear_nums_") or
                                             call.data.startswith("admin_delete_c_"))
async def admin_immediate_edit_actions(call):
    if not await is_admin(call.from_user.id): return
    
    action = ""
    country_id = ""
    if call.data.startswith("admin_toggle_status_"):
        action = "toggle"
        country_id = call.data.replace("admin_toggle_status_", "")
    elif call.data.startswith("admin_clear_nums_"):
        action = "clear"
        country_id = call.data.replace("admin_clear_nums_", "")
    elif call.data.startswith("admin_delete_c_"):
        action = "delete"
        country_id = call.data.replace("admin_delete_c_", "")
        
    async with aiosqlite.connect("database.db") as db:
        if action == "toggle":
            try:
                async with db.execute('SELECT status FROM countries WHERE id = ?', (country_id,)) as cursor:
                    row = await cursor.fetchone()
                if row:
                    new_status = "Disabled" if row[0] == "Enabled" else "Enabled"
                    await db.execute('UPDATE countries SET status = ? WHERE id = ?', (new_status, country_id))
                    await db.commit()
            except Exception:
                pass 
            await render_edit_country(call.message.chat.id, call.message.message_id, country_id, call.id)
            
        elif action == "clear":
            async with db.execute('SELECT country_name FROM countries WHERE id = ?', (country_id,)) as cursor:
                row = await cursor.fetchone()
            if row:
                c_name = row[0]
                file_path = f"countries/{c_name}.json"
                if os.path.exists(file_path):
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump([], f)
                await db.execute('UPDATE countries SET stock = 0 WHERE id = ?', (country_id,))
                await db.commit()
            await render_edit_country(call.message.chat.id, call.message.message_id, country_id, call.id)
            await bot.answer_callback_query(call.id, "Numbers cleared!")
            
        elif action == "delete":
            async with db.execute('SELECT country_name FROM countries WHERE id = ?', (country_id,)) as cursor:
                row = await cursor.fetchone()
            if row:
                c_name = row[0]
                file_path = f"countries/{c_name}.json"
                if os.path.exists(file_path):
                    os.remove(file_path)
                await db.execute('DELETE FROM countries WHERE id = ?', (country_id,))
                await db.commit()
            await bot.answer_callback_query(call.id, "Country deleted!", show_alert=True)
            await admin_country_mgmt_callback(call)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_edit_name_") or 
                                             call.data.startswith("admin_edit_flag_") or
                                             call.data.startswith("admin_edit_code_") or
                                             call.data.startswith("admin_edit_emoji_") or
                                             call.data.startswith("admin_edit_otp_"))
async def admin_text_edit_actions(call):
    if not await is_admin(call.from_user.id): return
    action_and_id = call.data.replace("admin_edit_", "")
    parts = action_and_id.split("_")
    field = parts[0]
    country_id = parts[1]
    
    admin_states[call.from_user.id] = {
        "state": f"waiting_edit_{field}",
        "edit_id": country_id,
        "msg_id": call.message.message_id
    }
    
    prompts = {
        "name": "📝 Please enter the new Country Name:",
        "flag": "🎌 Please enter the new Country Flag:",
        "code": "🆔 Please enter the new Country Code (e.g. +95):",
        "emoji": "⭐ Please enter the new Premium Emoji ID (or 'Not Set' to remove):",
        "otp": "💰 Please enter the new Per OTP Earn amount (e.g. 0.001):"
    }
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="global_cancel"))
    
    msg = await bot.send_message(call.message.chat.id, prompts[field], reply_markup=markup)
    admin_states[call.from_user.id]["prompt_msg_id"] = msg.message_id
    await bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data in ["premium_yes", "premium_no"])
async def premium_emoji_callback(call):
    user_id = call.from_user.id
    if user_id not in admin_states or admin_states[user_id].get("state") != "waiting_premium_choice":
        await bot.answer_callback_query(call.id, "Operation expired.", show_alert=True)
        return
        
    state_data = admin_states[user_id]
    flag = state_data["flag"]
    country_name = state_data["country_name"]
    service_name = state_data["service_name"]
    stock = state_data["stock"]
    stock_formatted = f"{stock/1000:.1f}k" if stock >= 1000 else str(stock)
    if stock_formatted.endswith(".0k"):
        stock_formatted = stock_formatted.replace(".0k", "k")
    
    if call.data == "premium_no":
        final_text = f"{flag} {country_name} 📱 {service_name} {stock_formatted} Added Good Access✔️✔️✔️✔️"
        await bot.send_message(call.message.chat.id, final_text)
        del admin_states[user_id]
    else:
        admin_states[user_id]["state"] = "waiting_service_emoji_id"
        await bot.send_message(call.message.chat.id, "📝 Please enter the Service Emoji ID:")
        
    await bot.answer_callback_query(call.id)
    try:
        await bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("withdraw_method_"))
async def withdraw_method_callback(call):
    method = call.data.replace("withdraw_method_", "")
    user_id = call.from_user.id
    
    user_states[user_id] = {"state": "waiting_withdrawal_account", "method": method}
    
    prompts = {
        "Bkash": "📱 *Please enter your Bkash Number:*",
        "Nogad": "📱 *Please enter your Nogad Number:*",
        "Binance": "🆔 *Please enter your Binance UID:*"
    }
    
    text = (
        f"💳 *Method:* {method}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"{prompts.get(method, 'Enter your account details:')}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "Type `cancel` to abort."
    )
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="global_cancel"))
    
    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=markup,
        parse_mode="Markdown"
    )
    await bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "withdraw_cancel")
async def withdraw_cancel_callback(call):
    user_id = call.from_user.id
    if user_id in user_states:
        del user_states[user_id]
    
    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="❌ *Withdrawal cancelled.*",
        parse_mode="Markdown"
    )
    await bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "confirm_withdraw")
async def confirm_withdraw_callback(call):
    user_id = call.from_user.id
    if user_id not in user_states or user_states[user_id].get("state") != "waiting_withdrawal_confirm":
        await bot.answer_callback_query(call.id, "Operation expired.", show_alert=True)
        return
        
    data = user_states[user_id]
    method = data["method"]
    account = data["account"]
    amount = data["amount"]
    
    # Save to DB
    async with aiosqlite.connect("database.db") as db:
        cursor = await db.execute('''
            INSERT INTO withdrawals (user_id, method, account, amount) 
            VALUES (?, ?, ?, ?)
        ''', (user_id, method, account, amount))
        request_id = cursor.lastrowid
        await db.commit()
        
    # Notify Admin
    admin_text = (
        "📥 *New Withdrawal Request*\n\n"
        f"👤 *User ID:* `{user_id}`\n"
        f"💳 *Method:* {method}\n"
        f"📱 *Account:* `{account}`\n"
        f"💰 *Amount:* ${amount:.4f}\n"
        f"🆔 *Request ID:* #{request_id}\n\n"
        "Please manage this in the Admin Panel."
    )
    
    # Send to all admins
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('SELECT user_id FROM admins') as cursor:
            admin_ids = [row[0] for row in (await cursor.fetchall())]
            
    for admin_id in admin_ids:
        try:
            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("✅ Approve", callback_data=f"adm_approve_w_{request_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"adm_cancel_w_{request_id}")
            )
            await bot.send_message(admin_id, admin_text, reply_markup=markup, parse_mode="Markdown")
        except:
            pass
            
    # Notify User
    user_text = (
        "✅ *Withdrawal Request Sent!*\n\n"
        f"💳 *Method:* {method}\n"
        f"💰 *Amount:* ${amount:.4f}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "⏳ *Wait 24 Hours for Processing.*\n"
        "Admin will review and approve your request shortly.\n"
        "━━━━━━━━━━━━━━━━━━━"
    )
    
    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=user_text,
        parse_mode="Markdown"
    )
    
    del user_states[user_id]
    await bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_approve_w_") or call.data.startswith("adm_cancel_w_"))
async def admin_withdrawal_action_callback(call):
    if not await is_admin(call.from_user.id): return
    
    parts = call.data.split("_")
    action = parts[1] # approve or cancel
    req_id = parts[3]
    
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('SELECT user_id, amount, method, account, status FROM withdrawals WHERE id = ?', (req_id,)) as cursor:
            row = await cursor.fetchone()
            
    if not row:
        await bot.answer_callback_query(call.id, "Request not found.", show_alert=True)
        try:
            await bot.delete_message(call.message.chat.id, call.message.message_id)
        except: pass
        return
        
    u_id, amount, method, account, status = row
    
    if status != "Pending":
        await bot.answer_callback_query(call.id, f"Request already {status}.", show_alert=True)
        return

    if action == "approve":
        # Check balance
        async with aiosqlite.connect("database.db") as db:
            async with db.execute('SELECT balance FROM users WHERE user_id = ?', (u_id,)) as cursor:
                u_row = await cursor.fetchone()
                current_balance = u_row[0] if u_row else 0
                
            if current_balance < amount:
                await bot.answer_callback_query(call.id, "❌ User has insufficient balance now!", show_alert=True)
                return
                
            # Deduct balance and update status
            await db.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (amount, u_id))
            await db.execute('UPDATE withdrawals SET status = "Approved" WHERE id = ?', (req_id,))
            await db.commit()
            
        # Notify User
        success_text = (
            "🎉 *Withdrawal Approved!*\n\n"
            f"💰 *Amount:* ${amount:.4f}\n"
            f"💳 *Method:* {method}\n"
            f"📱 *Account:* `{account}`\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "✅ Your payment has been processed successfully. Please check your account.\n"
            "━━━━━━━━━━━━━━━━━━━"
        )
        try:
            await bot.send_message(u_id, success_text, parse_mode="Markdown")
        except: pass
        
        # Update Admin Message
        await bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"✅ *Request #{req_id} Approved*\n\nUser: `{u_id}`\nAmount: ${amount:.4f}\nMethod: {method}",
            parse_mode="Markdown"
        )
        await bot.answer_callback_query(call.id, "Withdrawal Approved!")

    elif action == "cancel":
        # Delete from DB
        async with aiosqlite.connect("database.db") as db:
            await db.execute('DELETE FROM withdrawals WHERE id = ?', (req_id,))
            await db.commit()
            
        # Notify User
        cancel_text = (
            "❌ *Withdrawal Cancelled*\n\n"
            f"💰 *Amount:* ${amount:.4f}\n"
            f"💳 *Method:* {method}\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ Your withdrawal request was cancelled by admin.\n"
            "━━━━━━━━━━━━━━━━━━━"
        )
        try:
            await bot.send_message(u_id, cancel_text, parse_mode="Markdown")
        except: pass
        
        # Delete Admin Message
        try:
            await bot.delete_message(call.message.chat.id, call.message.message_id)
        except: pass
        
        await bot.answer_callback_query(call.id, "Request Cancelled & Deleted")

@bot.callback_query_handler(func=lambda call: call.data == "global_cancel")
async def global_cancel_callback(call):
    user_id = call.from_user.id
    if user_id in admin_states: del admin_states[user_id]
    if user_id in user_states: del user_states[user_id]
    
    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="❌ *Process Cancelled.*",
        parse_mode="Markdown"
    )
    await bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
async def back_to_main_callback(call):
    try:
        await bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data == "back_to_services")
async def back_to_services_callback(call):
    try:
        await bot.answer_callback_query(call.id)
    except Exception:
        pass
        
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('SELECT DISTINCT service_name, service_emoji_id FROM countries WHERE stock > 0') as cursor:
            services = await cursor.fetchall()
            
    if not services:
        await bot.edit_message_text("No services available.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        return
        
    markup_list = []
    for service_name, emoji_id in services:
        s_key = service_name.upper()
        # Auto-detect service icon
        btn_icon = emoji_id if emoji_id and not emoji_id.isdigit() else "📱"
        
        btn_data = {
            "text": f"{btn_icon} {service_name}",
            "callback_data": f"service_{service_name}"
        }
        markup_list.append([btn_data])
        
    # Add Main Menu button with premium icon
    markup_list.append([{
        "text": "🏠 Main Menu",
        "callback_data": "back_to_main"
    }])
    
    reply_markup_json = json.dumps({"inline_keyboard": markup_list})
    
    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="👇 <b>Please select a service:</b>",
        reply_markup=reply_markup_json,
        parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("copy_otp_"))
async def copy_otp_callback(call):
    otp_code = call.data.replace("copy_otp_", "")
    await bot.answer_callback_query(call.id, text=f"🔑 Your OTP is: {otp_code}\n\nCopy it from the message code block.", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("service_"))
async def service_selected_callback(call):
    try:
        await bot.answer_callback_query(call.id)
    except Exception:
        pass
        
    service_name = call.data.split("service_")[1]
    
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('SELECT id, country_name, country_code, flag, per_otp_earn, stock, service_emoji_id FROM countries WHERE service_name = ? AND stock > 0', (service_name,)) as cursor:
            countries = await cursor.fetchall()
            
    if not countries:
        await bot.answer_callback_query(call.id, "No countries available for this service.", show_alert=True)
        return

    markup_list = []
    is_user_admin = await is_admin(call.from_user.id)
    s_key = service_name.upper()

    for c_id, c_name, c_code, c_flag, c_earn, c_stock, c_emoji_id in countries:
        c_key = ""
        
        # ১ম চেষ্টা: নাম দিয়ে ডিকশনারি থেকে ISO কোড বের করা
        for m_name, (m_iso, _) in country_map.items():
            if str(m_name).lower() in str(c_name).lower() or str(c_name).lower() in str(m_name).lower():
                c_key = str(m_iso).upper()
                break
                
        # ২য় চেষ্টা (টুলব্যাক): নাম না মিললে কান্ট্রি কোড (যেমন: 216) দিয়ে খুঁজে বের করা
        if not c_key and c_code:
            clean_code = str(c_code).replace("+", "").strip()
            if clean_code == "216":  # তিউনিসিয়ার জন্য সরাসরি ফোর্সড অ্যাসাইন
                c_key = "TN"
            elif clean_code == "213": # আলজেরিয়া
                c_key = "DZ"
            elif clean_code == "95":  # মায়ানমার
                c_key = "MM"
            elif clean_code == "880": # বাংলাদেশ
                c_key = "BD"
            elif clean_code == "91":  # ইন্ডিয়া
                c_key = "IN"
            
        btn_icon = next((v[1] for v in country_map.values() if v[0] == c_key), c_flag or "🌍")
        
        s_display = "SVC"
        if s_key == "FACEBOOK": s_display = "FB"
        elif s_key == "WHATSAPP": s_display = "WA"
        elif s_key == "TELEGRAM": s_display = "TG"
        elif s_key == "TIKTOK": s_display = "TT"
        elif s_key == "INSTAGRAM": s_display = "IG"

        display_text = f"{c_name} | {s_display} | ${c_earn:.4f}/OTP"
        if is_user_admin: display_text += f" ({c_stock})"
        
        btn_data = {
            "text": f"{btn_icon} {display_text}",
            "callback_data": f"country_{c_id}"
        }
        markup_list.append([btn_data])
        
    markup_list.append([{
        "text": "◀️ Back To Services",
        "callback_data": "back_to_services"
    }])
    
    reply_markup_json = json.dumps({"inline_keyboard": markup_list})
    
    header_text = f"📱 <b>Select country for {service_name}:</b>"

    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=header_text,
        reply_markup=reply_markup_json,
        parse_mode="HTML"
    )

import random

@bot.callback_query_handler(func=lambda call: call.data.startswith("country_"))
async def country_selected_callback(call):
    user_id = call.from_user.id
    print(f"DEBUG: Country selected -> {call.data} from {user_id}")
    country_id = call.data.split("country_")[1]
    
    # Check cooldown
    now = asyncio.get_event_loop().time()
    last_req = user_cooldowns.get(user_id, 0)
    cooldown_seconds = int(await get_setting("cooldown", "6"))

    if now - last_req < cooldown_seconds:
        remaining = int(cooldown_seconds - (now - last_req))
        await bot.answer_callback_query(call.id, f"⏱️ Cooldown active! Please wait {remaining} seconds.", show_alert=True)
        return
        
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('SELECT service_name, country_name, country_code, flag, service_emoji_id, country_emoji_id, per_otp_earn FROM countries WHERE id = ?', (country_id,)) as cursor:
            row = await cursor.fetchone()
            
    if not row:
        await bot.answer_callback_query(call.id, "Country not found.", show_alert=True)
        return
        
    service_name, country_name, country_code, flag, s_emoji, c_emoji, price = row
    
    file_path = f"countries/{country_name}.json"
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            numbers = json.load(f)
    except Exception:
        numbers = []
        
    if not numbers:
        await bot.answer_callback_query(call.id, "No numbers available for this country.", show_alert=True)
        return
        
    # Get numbers per request setting
    nums_per_req = int(await get_setting("numbers_per_request", "2"))
    num_to_take = min(nums_per_req, len(numbers))
    selected_numbers = random.sample(numbers, num_to_take)
    
    for num in selected_numbers:
        numbers.remove(num)
        
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(numbers, f)
        
    new_stock = len(numbers)
    
    # Register active sessions for OTP polling and update stock
    async with aiosqlite.connect("database.db") as db:
        # CRITICAL: Clear any existing active sessions for this user and service before adding new ones
        # This prevents the "multiple users getting OTP" bug when changing numbers
        await db.execute('DELETE FROM active_sessions WHERE user_id = ? AND service = ?', (user_id, service_name))
        
        for num in selected_numbers:
            await db.execute('''
                INSERT INTO active_sessions (user_id, number, service, country, price, flag, s_emoji_id, c_emoji_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, num, service_name, country_name, price, flag, s_emoji, c_emoji))
        
        await db.execute('UPDATE countries SET stock = ? WHERE id = ?', (new_stock, country_id))
        await db.commit()
    
    # Update cooldown time AFTER successful number delivery
    user_cooldowns[user_id] = asyncio.get_event_loop().time()
    
    bot_mode = await get_setting("bot_mode", "Normal")
    
    service_emoji_html = ""
    btn_service_emoji = ""
    if s_emoji and s_emoji != "Not Set":
        if s_emoji.isdigit():
            service_emoji_html = f'📱'
        else:
            service_emoji_html = s_emoji
            btn_service_emoji = s_emoji
            
    # Robust ISO code detection (handles suffixes like M1, M2, etc.)
    iso_code = ""
    c_name_lower = country_name.lower()
    for m_name, (m_iso, _) in country_map.items():
        if m_name.lower() in c_name_lower:
            iso_code = m_iso
            break
            
    country_emoji_html = flag or next((v[1] for k, v in country_map.items() if v[0] == iso_code.upper()), "🌍")
            
    markup_list = []
    for num in selected_numbers:
        formatted_num = num if num.startswith('+') else f"+{num}"
        # Add leading spaces to push text right and align with the premium icon
        btn_text = f"      {formatted_num}"
        
        # Premium Number Button with Flag Icon
        btn_data = {
            "text": btn_text,
            "copy_text": {"text": formatted_num} # Blue color for numbers
        }
        markup_list.append([btn_data])
        
    otp_link = await get_setting("otp_view_link", "https://t.me/SMART_TECH")
    
    # Navigation Buttons (All Green/Success for unified look)
    markup_list.append([{
        "text": "Chenge Number", 
        "callback_data": f"country_{country_id}"
    }])
    markup_list.append([{
        "text": "Change Country", 
        "callback_data": f"service_{service_name}"
    }])
    markup_list.append([{
        "text": "View OTP", 
        "url": otp_link
    }])
    markup_list.append([{
        "text": "◀️ Back To Services", 
        "callback_data": "back_to_services"
    }])
    
    reply_markup_json = json.dumps({"inline_keyboard": markup_list})
    
    msg_text = f"{country_emoji_html}"
    if service_emoji_html:
        msg_text += f" {service_emoji_html}"
    msg_text += f" <b>{country_name} Number:</b>\n⏳ Waiting for OTP..."
    
    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=msg_text,
        reply_markup=reply_markup_json,
        parse_mode="HTML"
    )


# Sample responses for button clicks and state handling
@bot.message_handler(content_types=['text', 'document', 'photo', 'video', 'audio', 'voice', 'animation', 'sticker', 'video_note', 'location', 'contact'], func=lambda message: True)
async def handle_buttons(message):
    user_id = message.from_user.id
    
    # Banned Check
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('SELECT 1 FROM banned_users WHERE user_id = ?', (user_id,)) as cursor:
            if await cursor.fetchone():
                await bot.reply_to(message, "🚫 <b>You are BANNED from using this bot.</b>", parse_mode="HTML")
                return

    if message.text:
        print(f"DEBUG: Message received -> '{message.text}' from {user_id}")
    if message.document:
        print(f"DEBUG: Document received -> '{message.document.file_name}' from {user_id}")
    
    # Forced Join Check
    not_joined = await check_user_joined(user_id)
    if not_joined:
        await show_force_join(message.chat.id, not_joined)
        return

    # Handle cancellation
    if message.text and message.text.lower() == 'cancel':
        if user_id in admin_states:
            del admin_states[user_id]
            await bot.reply_to(message, "🚫 *Operation cancelled.*", parse_mode="Markdown")
        if user_id in user_states:
            del user_states[user_id]
            await bot.reply_to(message, "🚫 *Operation cancelled.*", parse_mode="Markdown")
        return

    # List of main menu buttons to auto-clear states
    main_menu_buttons = ["📞 Get Number", "📲 Get Number", "🌎 Stock Status", "📊 Stock Status", "📥 Download OTP", "💰 My Balance", "💳 My Balance", "💸 Withdraw", "📡 Live Traffic", "📊 Live Traffic", "⚙️ Admin Panel", "🛠 Admin Panel", "👨‍💻 Bot Developer", "🎧 Support"]
    if message.text in main_menu_buttons:
        if user_id in admin_states: del admin_states[user_id]
        if user_id in user_states: del user_states[user_id]

    # Check if admin is adding country
    if user_id in admin_states:
        state_data = admin_states[user_id]
        
        if state_data["state"] == "waiting_service_name":
            if not message.text: return
            service_name = message.text.upper()
            admin_states[user_id]["service_name"] = service_name
            admin_states[user_id]["state"] = "waiting_country_name"
            
            text = (
                f"🛠 Service: {service_name}\n"
                f"⭐ Service Emoji ID: 959659042400\n\n"
                f"Step 3 — Country Name\n\n"
                f"Now enter the country name.\n\n"
                f"Example: Tanzania, Bangladesh, Kenya\n\n"
                f"Type 'cancel' to cancel this operation."
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("❌ Cancel", callback_data="global_cancel"))
            await bot.reply_to(message, text, reply_markup=markup)
            return
            
        elif state_data["state"] == "waiting_country_name":
            if not message.text: return
            country_name = message.text.title()
            admin_states[user_id]["country_name"] = country_name
            admin_states[user_id]["state"] = "waiting_country_code"
            
            service_name = state_data["service_name"]
            text = (
                f"🛠 Service: {service_name}\n"
                f"Country Name: {country_name}\n\n"
                f"Step 4 — Country Code\n\n"
                f"Example: +255, +880, +254\n\n"
                f"Type 'cancel' to cancel this operation."
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("❌ Cancel", callback_data="global_cancel"))
            await bot.reply_to(message, text, reply_markup=markup)
            return

        elif state_data["state"] == "waiting_country_code":
            if not message.text: return
            country_code = message.text
            if not country_code.startswith('+'):
                country_code = '+' + country_code
            admin_states[user_id]["country_code"] = country_code
            admin_states[user_id]["state"] = "waiting_country_flag"
            
            country_name = state_data["country_name"]
            
            text = (
                f"🌍 Country: {country_name}\n"
                f"🆔 Code: {country_code}\n"
                f"🔑 ID: {country_name}\n\n"
                f"ℹ️ Note: Country code {country_code} already has 1 entry(ies).\n"
                f"This will be entry #2 (ID: {country_name})\n\n"
                f"Now please send the country flag\n\n"
                f"Example: 🇹🇿, 🇧🇩, 🇰🇪\n\n"
                f"Type 'cancel' to cancel this operation."
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("❌ Cancel", callback_data="global_cancel"))
            await bot.reply_to(message, text, reply_markup=markup)
            return
            
        elif state_data["state"] == "waiting_country_flag":
            if not message.text: return
            flag = message.text
            admin_states[user_id]["flag"] = flag
            admin_states[user_id]["state"] = "waiting_otp_earn"
            
            service_name = state_data["service_name"]
            country_name = state_data["country_name"]
            country_code = state_data["country_code"]
            
            text = (
                f"🛠 Service: {service_name}\n"
                f"🌍 Country: {country_name}\n"
                f"🆔 Code: {country_code}\n"
                f"🎌 Flag: {flag}\n"
                f"⭐ Premium Emoji ID: 959659042400\n\n"
                f"💸 Step 6 — Per OTP Earn\n\n"
                f"Enter how much USD the user earns per OTP received.\n\n"
                f"Example: 0.003\n\n"
                f"Enter 0 for no earnings.\n\n"
                f"Type 'cancel' to cancel."
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("❌ Cancel", callback_data="global_cancel"))
            await bot.reply_to(message, text, reply_markup=markup)
            return

        elif state_data["state"] == "waiting_otp_earn":
            if not message.text: return
            try:
                per_otp = float(message.text)
            except ValueError:
                await bot.reply_to(message, "Please enter a valid number. Type 'cancel' to cancel.")
                return
                
            admin_states[user_id]["per_otp"] = per_otp
            admin_states[user_id]["state"] = "waiting_numbers_file"
            
            service_name = state_data["service_name"]
            country_name = state_data["country_name"]
            country_code = state_data["country_code"]
            flag = state_data["flag"]
            
            text = (
                f"🛠 Service: {service_name}\n"
                f"🌍 Country: {country_name}\n"
                f"🆔 Code: {country_code}\n"
                f"🎌 Flag: {flag}\n"
                f"⭐ Premium Emoji ID: 959659042400\n"
                f"💸 Per OTP: ${per_otp:.4f}\n\n"
                f"📁 Step 7 — Upload Numbers File\n\n"
                f"Please upload a .txt file with one phone number per line.\n\n"
                f"Example:\n"
                f"1234567890\n"
                f"9876543210\n"
                f"5555555555\n\n"
                f"Type 'cancel' to cancel."
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("❌ Cancel", callback_data="global_cancel"))
            await bot.reply_to(message, text, reply_markup=markup)
            return
            
        elif state_data["state"] == "waiting_numbers_file":
            if not message.document:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("❌ Cancel", callback_data="global_cancel"))
                await bot.reply_to(message, "Please upload a .txt document file. Type 'cancel' to cancel.", reply_markup=markup)
                return
                
            file_info = await bot.get_file(message.document.file_id)
            downloaded_file = await bot.download_file(file_info.file_path)
            
            service_name = state_data["service_name"]
            country_name = state_data["country_name"]
            country_code = state_data["country_code"]
            flag = state_data["flag"]
            per_otp = state_data["per_otp"]
            
            # Read numbers
            try:
                content = downloaded_file.decode('utf-8')
                numbers = [line.strip() for line in content.split('\n') if line.strip()]
                stock = len(numbers)
            except Exception:
                numbers = []
                stock = 0

            # Save the file as json
            file_path = f"countries/{country_name}.json"
            with open(file_path, 'w', encoding='utf-8') as new_file:
                json.dump(numbers, new_file)
            
            # Save to db
            async with aiosqlite.connect("database.db") as db:
                # Altering table logic is handled by init_db (we will just drop and recreate it)
                cursor = await db.execute('''
                    INSERT INTO countries (service_name, country_name, country_code, flag, per_otp_earn, stock) 
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (service_name, country_name, country_code, flag, per_otp, stock))
                inserted_id = cursor.lastrowid
                await db.commit()
                
            admin_states[user_id]["db_id"] = inserted_id
            admin_states[user_id]["stock"] = stock
            
            # Success Message
            preview_lines = '\n'.join(numbers[:5])
            more_count = max(0, stock - 5)
            more_text = f"\n... and {more_count} more" if more_count > 0 else ""
            
            success_text = (
                f"✅ Country Added Successfully!\n\n"
                f"🛠 Service: {service_name}\n"
                f"⭐ Service Emoji ID: Not Set\n"
                f"🌍 {flag} {country_name} ({country_code})\n"
                f"🔑 ID: {country_name}\n"
                f"📁 File: {file_path}\n"
                f"📦 Stock: {stock} numbers\n"
                f"⭐ Country Emoji ID: Not Set\n"
                f"💸 Per OTP: ${per_otp:.4f}\n"
                f"📊 Status: Enabled\n\n"
                f"📋 Numbers Preview:\n"
                f"{preview_lines}{more_text}\n\n"
                f"Country is now available for users!"
            )
                            
            await bot.reply_to(message, success_text)
            
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("✅ Yes", callback_data="premium_yes"),
                InlineKeyboardButton("❌ No", callback_data="premium_no")
            )
            admin_states[user_id]["state"] = "waiting_premium_choice"
            await bot.send_message(message.chat.id, "💎 *Do you want to add Premium Emojis?*", reply_markup=markup, parse_mode="Markdown")
            return
            
        elif state_data["state"] == "waiting_service_emoji_id":
            if not message.text: return
            admin_states[user_id]["service_emoji_id"] = message.text
            admin_states[user_id]["state"] = "waiting_country_emoji_id"
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("❌ Cancel", callback_data="global_cancel"))
            await bot.reply_to(message, "📝 Please enter the Country Emoji ID:", reply_markup=markup)
            return
            
        elif state_data["state"] == "waiting_country_emoji_id":
            if not message.text: return
            country_emoji_id = message.text
            service_emoji_id = state_data["service_emoji_id"]
            db_id = state_data["db_id"]
            
            # Update DB
            async with aiosqlite.connect("database.db") as db:
                await db.execute('''
                    UPDATE countries 
                    SET service_emoji_id = ?, country_emoji_id = ? 
                    WHERE id = ?
                ''', (service_emoji_id, country_emoji_id, db_id))
                await db.commit()
            
            flag = state_data["flag"]
            country_name = state_data["country_name"]
            service_name = state_data["service_name"]
            stock = state_data["stock"]
            stock_formatted = f"{stock/1000:.1f}k" if stock >= 1000 else str(stock)
            if stock_formatted.endswith(".0k"):
                stock_formatted = stock_formatted.replace(".0k", "k")
            
            final_text = f"{flag} {country_name} 📱 {service_name} {stock_formatted} Added Good Access✔️✔️✔️✔️"
            await bot.reply_to(message, final_text)
            
            del admin_states[user_id]
            return

        elif state_data["state"].startswith("waiting_edit_"):
            if not message.text: return
            field = state_data["state"].replace("waiting_edit_", "")
            c_id = state_data["edit_id"]
            msg_id = state_data["msg_id"]
            prompt_msg_id = state_data.get("prompt_msg_id")
            new_val = message.text
            
            async with aiosqlite.connect("database.db") as db:
                if field == "name":
                    await db.execute('UPDATE countries SET country_name = ? WHERE id = ?', (new_val.title(), c_id))
                elif field == "flag":
                    await db.execute('UPDATE countries SET flag = ? WHERE id = ?', (new_val, c_id))
                elif field == "code":
                    new_val = new_val if new_val.startswith('+') else f"+{new_val}"
                    await db.execute('UPDATE countries SET country_code = ? WHERE id = ?', (new_val, c_id))
                elif field == "emoji":
                    await db.execute('UPDATE countries SET country_emoji_id = ? WHERE id = ?', (new_val, c_id))
                elif field == "otp":
                    try:
                        val = float(new_val)
                        await db.execute('UPDATE countries SET per_otp_earn = ? WHERE id = ?', (val, c_id))
                    except:
                        await bot.reply_to(message, "Invalid number. Edit cancelled.")
                        del admin_states[user_id]
                        return
                
                await db.commit()
            
            try:
                await bot.delete_message(message.chat.id, message.message_id)
                if prompt_msg_id:
                    await bot.delete_message(message.chat.id, prompt_msg_id)
            except:
                pass
                
            del admin_states[user_id]
            await render_edit_country(message.chat.id, msg_id, c_id)
            return

        elif state_data["state"] == "waiting_import_users_txt":
            if not message.document: return
            file_info = await bot.get_file(message.document.file_id)
            downloaded_file = await bot.download_file(file_info.file_path)
            
            content = downloaded_file.decode('utf-8')
            lines = content.splitlines()
            count = 0
            async with aiosqlite.connect("database.db") as db:
                for line in lines:
                    if ":" in line:
                        u_id, u_name = line.split(":", 1)
                        try:
                            await db.execute('INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)', (int(u_id), u_name))
                            count += 1
                        except: continue
                await db.commit()
            
            del admin_states[user_id]
            await bot.reply_to(message, f"✅ Successfully imported {count} users!")
            await admin_import_menu_callback(message)
            return

        elif state_data["state"] == "waiting_import_stock_zip":
            if not message.document: return
            file_info = await bot.get_file(message.document.file_id)
            downloaded_file = await bot.download_file(file_info.file_path)
            
            with open("import_stock.zip", "wb") as f:
                f.write(downloaded_file)
            
            # Extract
            if not os.path.exists("countries"): os.makedirs("countries")
            with zipfile.ZipFile("import_stock.zip", 'r') as zip_ref:
                zip_ref.extractall("countries")
            
            os.remove("import_stock.zip")
            
            del admin_states[user_id]
            await bot.reply_to(message, "✅ Stock imported successfully!")
            await admin_import_menu_callback(message)
            return



        elif state_data["state"] in ["waiting_ban_id", "waiting_unban_id"]:
            if not message.text: return
            try:
                target_id = int(message.text)
            except ValueError:
                await bot.reply_to(message, "❌ *Invalid ID.* Please enter a numeric Chat ID.")
                return
            
            action = "ban" if "ban" in state_data["state"] else "unban"
            confirm_data = f"confirm_{action}_yes_{target_id}"
            cancel_data = f"confirm_{action}_no_{target_id}"
            
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("✅ Yes, Confirm", callback_data=confirm_data),
                       InlineKeyboardButton("❌ No, Cancel", callback_data=cancel_data))
            
            text = f"❓ <b>Are you sure you want to {action.upper()} user <code>{target_id}</code>?</b>"
            await bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="HTML")
            return

        elif state_data["state"] == "waiting_channel_name":
            if not message.text: return
            admin_states[user_id]["channel_name"] = message.text
            admin_states[user_id]["state"] = "waiting_channel_id"
            await bot.reply_to(message, "🆔 Please send the <b>Numeric Chat ID</b> (e.g. -100123456789) OR <b>Public Username</b> (e.g. @username) for this channel/group:\n\n<i>(Private invite links will not work here. To get a numeric ID, you can use a bot like @RawDataBot in your group.)</i>", parse_mode="HTML")
            return
            
        elif state_data["state"] == "waiting_channel_id":
            if not message.text: return
            admin_states[user_id]["channel_id"] = message.text
            admin_states[user_id]["state"] = "waiting_channel_link"
            await bot.reply_to(message, "🔗 Please send the <b>URL/Invite Link</b> for this channel (this is the button link users will click):", parse_mode="HTML")
            return
            
        elif state_data["state"] == "waiting_channel_link":
            if not message.text: return
            link = message.text
            if not (link.startswith("http") or link.startswith("t.me/")):
                await bot.reply_to(message, "❌ Invalid link. Please send a valid URL.")
                return
            
            name = state_data["channel_name"]
            c_id = state_data.get("channel_id", "N/A")
            admin_states[user_id]["channel_link"] = link
            admin_states[user_id]["state"] = "confirming_channel"
            
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("✅ Yes, Add It", callback_data="confirm_add_channel"),
                       InlineKeyboardButton("❌ No, Cancel", callback_data="admin_channels"))
            
            await bot.reply_to(message, f"❓ <b>Confirm Channel Details:</b>\n\n📛 <b>Name:</b> {name}\n🆔 <b>Chat ID:</b> {c_id}\n🔗 <b>Link:</b> {link}\n\nDo you want to add this channel?", reply_markup=markup, parse_mode="HTML")
            return
            
        elif state_data["state"] == "waiting_new_group_link":
            if not message.text: return
            new_link = message.text
            if not (new_link.startswith("http://") or new_link.startswith("https://") or new_link.startswith("t.me/")):
                await bot.reply_to(message, "❌ *Invalid Link.* Please send a valid Telegram group or channel link.")
                return
                
            async with aiosqlite.connect("database.db") as db:
                await db.execute('UPDATE settings SET value = ? WHERE key = "otp_view_link"', (new_link,))
                await db.commit()
            await refresh_caches()
                
            del admin_states[user_id]
            await bot.reply_to(message, f"✅ *Success!* OTP View Group updated to:\n`{new_link}`", parse_mode="Markdown")
            await admin_groups_callback(message)
            return
            
        elif state_data["state"] == "waiting_new_admin_id":
            if not message.text: return
            try:
                new_admin_id = int(message.text)
            except ValueError:
                await bot.reply_to(message, "❌ *Invalid ID.* Please enter a numeric Chat ID.")
                return
                
            async with aiosqlite.connect("database.db") as db:
                await db.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (new_admin_id,))
                await db.commit()
            await refresh_caches()
                
            del admin_states[user_id]
            await bot.reply_to(message, f"✅ User `{new_admin_id}` is now an Admin!", parse_mode="Markdown")
            # Return to admin management
            await admin_admins_callback(message)
            return
            
        elif state_data["state"] == "waiting_api_url":
            if not message.text: return
            new_url = message.text
            msg_id = state_data["msg_id"]
            
            async with aiosqlite.connect("database.db") as db:
                await db.execute('UPDATE settings SET value = ? WHERE key = "api_url"', (new_url,))
                await db.commit()
            await refresh_caches()
            
            del admin_states[user_id]
            await bot.reply_to(message, f"✅ API URL updated to:\n`{new_url}`", parse_mode="Markdown")
            
            # Refresh menu
            from telebot import types
            mock_call = types.CallbackQuery(id='0', from_user=message.from_user, chat_instance='0', message=message, data="admin_api_settings")
            mock_call.message.message_id = msg_id
            await admin_api_settings_callback(mock_call)
            return

        elif state_data["state"] == "waiting_api_key":
            if not message.text: return
            new_key = message.text
            msg_id = state_data["msg_id"]
            
            async with aiosqlite.connect("database.db") as db:
                await db.execute('UPDATE settings SET value = ? WHERE key = "api_key"', (new_key,))
                await db.commit()
            await refresh_caches()
            
            del admin_states[user_id]
            await bot.reply_to(message, f"✅ API Key updated to:\n`{new_key}`", parse_mode="Markdown")
            
            # Refresh menu
            from telebot import types
            mock_call = types.CallbackQuery(id='0', from_user=message.from_user, chat_instance='0', message=message, data="admin_api_settings")
            mock_call.message.message_id = msg_id
            await admin_api_settings_callback(mock_call)
            return

        elif state_data["state"].startswith("waiting_setting_"):

            if not message.text: return
            setting_key = state_data["state"].replace("waiting_setting_", "")
            msg_id = state_data["msg_id"]
            new_val = message.text
            
            if setting_key == "nums_per_req":
                try:
                    val = int(new_val)
                    if not (1 <= val <= 50):
                        await bot.reply_to(message, "⚠️ *Error:* Please enter a number between 1 and 50.", parse_mode="Markdown")
                        return
                except:
                    await bot.reply_to(message, "⚠️ *Error:* Please enter a valid whole number.", parse_mode="Markdown")
                    return
            
            # Map keys to db keys if needed
            db_key = setting_key
            if setting_key == "otp_link": db_key = "otp_view_link"
            if setting_key == "nums_per_req": db_key = "numbers_per_request"
            
            async with aiosqlite.connect("database.db") as db:
                await db.execute('UPDATE settings SET value = ? WHERE key = ?', (new_val, db_key))
                await db.commit()
            await refresh_caches()
            
            del admin_states[user_id]
            await bot.reply_to(message, f"✅ Setting updated to: `{new_val}`", parse_mode="Markdown")
            await render_system_edit(message.chat.id, msg_id)
            return

        # ── Broadcast text input ──
        elif state_data["state"] == "waiting_broadcast_text":
            if not message.text: return
            broadcast_text = message.text
            target_users = await _broadcast_get_users()
            total = len(target_users)
            admin_states[user_id] = {
                "state": "waiting_broadcast_confirm",
                "broadcast_text": broadcast_text
            }
            preview = broadcast_text[:200] + ('...' if len(broadcast_text) > 200 else '')
            confirm_markup = InlineKeyboardMarkup()
            confirm_markup.row(
                InlineKeyboardButton("✅ Confirm & Send", callback_data="broadcast_confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="broadcast_cancel")
            )
            await bot.reply_to(
                message,
                f"<b>📢 Broadcast Confirmation</b>\n\n"
                f"<b>👥 Recipients:</b> {total} users\n\n"
                f"<b>📝 Preview:</b>\n「{preview}」\n\n"
                f"<b>Send this to all users?</b>",
                reply_markup=confirm_markup,
                parse_mode="HTML"
            )
            return

        # ── Broadcast photo input ──
        elif state_data["state"] == "waiting_broadcast_photo":
            if message.text and message.text.lower() == 'cancel':
                del admin_states[user_id]
                await show_broadcast_menu(message.chat.id)
                return
            if not message.photo:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("❌ Cancel", callback_data="admin_broadcast"))
                await bot.reply_to(message, "<b>📸 Please send a photo, not text.</b>\n\n<i>Type 'cancel' to cancel.</i>", reply_markup=markup, parse_mode="HTML")
                return
            photo = message.photo[-1]
            file_id = photo.file_id
            caption = message.caption or ""
            del admin_states[user_id]
            target_users = await _broadcast_get_users()
            total = len(target_users)
            await bot.reply_to(
                message,
                f"<b>📸 Photo Broadcast Started!</b>\n\n<b>👥 Users:</b> {total}\n<b>⚡ Sending...</b>",
                parse_mode="HTML"
            )
            asyncio.create_task(_do_broadcast_photo(user_id, file_id, caption, target_users))
            return

        # ── Broadcast forward input ──
        elif state_data["state"] == "waiting_broadcast_forward":
            if message.text and message.text.lower() == 'cancel':
                del admin_states[user_id]
                await show_broadcast_menu(message.chat.id)
                return
            from_chat_id = message.chat.id
            msg_id_to_copy = message.message_id
            del admin_states[user_id]
            target_users = await _broadcast_get_users()
            total = len(target_users)
            await bot.reply_to(
                message,
                f"<b>🔄 Forward Broadcast Started!</b>\n\n<b>👥 Users:</b> {total}\n<b>⚡ Sending...</b>",
                parse_mode="HTML"
            )
            asyncio.create_task(_do_broadcast_forward(user_id, from_chat_id, msg_id_to_copy, target_users))
            return

        elif state_data["state"] == "waiting_update_stock_file":
            if not message.document:
                return # Only handle documents here
                
            c_id = state_data["country_id"]
            c_name = state_data["country_name"]
            
            file_info = await bot.get_file(message.document.file_id)
            downloaded_file = await bot.download_file(file_info.file_path)
            
            # Parse new numbers
            try:
                content = downloaded_file.decode('utf-8')
                new_numbers = [line.strip() for line in content.split('\n') if line.strip()]
            except Exception:
                await bot.reply_to(message, "❌ Invalid file format. Please upload a .txt file.")
                return

            # Load existing numbers
            file_path = f"countries/{c_name}.json"
            existing_numbers = []
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        existing_numbers = json.load(f)
                except Exception:
                    existing_numbers = []
            
            # Combine
            combined_numbers = existing_numbers + new_numbers
            total_stock = len(combined_numbers)
            
            # Save back
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(combined_numbers, f)
            
            # Update DB
            async with aiosqlite.connect("database.db") as db:
                await db.execute('UPDATE countries SET stock = ? WHERE id = ?', (total_stock, c_id))
                await db.commit()
            
            del admin_states[user_id]
            
            stock_formatted = f"{total_stock/1000:.1f}k" if total_stock >= 1000 else str(total_stock)
            if stock_formatted.endswith(".0k"):
                stock_formatted = stock_formatted.replace(".0k", "k")
                
            await bot.reply_to(message, f"✅ *Stock Updated Successfully!*\n\n🌍 Country: {c_name}\n📦 New Total Stock: {stock_formatted} numbers", parse_mode="Markdown")
            return

    # Check if user is in withdrawal state
    if user_id in user_states:
        state_data = user_states[user_id]
        
        if state_data["state"] == "waiting_withdrawal_account":
            if not message.text: return
            account = message.text
            user_states[user_id]["account"] = account
            user_states[user_id]["state"] = "waiting_withdrawal_amount"
            
            text = (
                f"💳 *Method:* {state_data['method']}\n"
                f"📱 *Account:* `{account}`\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                "💰 *Enter Withdrawal Amount (USD):*\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                "Type `cancel` to abort."
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("❌ Cancel", callback_data="global_cancel"))
            await bot.reply_to(message, text, reply_markup=markup, parse_mode="Markdown")
            return
            
        elif state_data["state"] == "waiting_withdrawal_amount":
            if not message.text: return
            try:
                amount = float(message.text)
                if amount <= 0: raise ValueError
            except ValueError:
                await bot.reply_to(message, "❌ *Invalid amount.* Please enter a positive number.")
                return
                
            # Check balance using fresh connection
            async with aiosqlite.connect("database.db") as db:
                async with db.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,)) as cursor:
                    row = await cursor.fetchone()
                    balance = row[0] if row else 0
            
            min_withdraw = float(await get_setting("min_withdraw", "1.0000"))
            
            if amount < min_withdraw:
                await bot.reply_to(message, f"❌ *Minimum withdrawal is ${min_withdraw:.4f}.*\nPlease enter a larger amount.")
                return
                
            if amount > balance:
                await bot.reply_to(message, f"❌ *Insufficient Balance!*\n💰 Your Balance: ${balance:.4f}\n\nPlease enter an amount within your balance.")
                return
                
            user_states[user_id]["amount"] = amount
            user_states[user_id]["state"] = "waiting_withdrawal_confirm"
            
            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("✅ Confirm", callback_data="confirm_withdraw"),
                InlineKeyboardButton("❌ Cancel", callback_data="withdraw_cancel")
            )
            
            text = (
                "📝 *Withdrawal Confirmation*\n\n"
                f"💳 *Method:* {state_data['method']}\n"
                f"📱 *Account:* `{state_data['account']}`\n"
                f"💰 *Amount:* ${amount:.4f}\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ *Note:* Processing takes up to 24 hours.\n"
                "━━━━━━━━━━━━━━━━━━━"
            )
            await bot.reply_to(message, text, reply_markup=markup, parse_mode="Markdown")
            return

    # Normal text buttons
    text = message.text
    if not text:
        return
        
    if text in ["📞 Get Number", "📲 Get Number", "Get Number"]:
        async with aiosqlite.connect("database.db") as db:
            async with db.execute('SELECT DISTINCT service_name, service_emoji_id FROM countries WHERE stock > 0') as cursor:
                services = await cursor.fetchall()
                
        if not services:
            await bot.reply_to(message, "🚫 No services available at the moment.", parse_mode="Markdown")
            return
            
        markup_list = []
        for service_name, emoji_id in services:
            s_key = service_name.upper()
            btn_icon = emoji_id if emoji_id and not emoji_id.isdigit() else "📱"
            
            btn_data = {
                "text": f"{btn_icon} {service_name}",
                "callback_data": f"service_{service_name}"
            }
            markup_list.append([btn_data])
            
        # Main Menu button with premium icon
        markup_list.append([{
            "text": "Main Menu", 
            "callback_data": "back_to_main"
        }])
        
        reply_markup_json = json.dumps({"inline_keyboard": markup_list})
        await bot.reply_to(message, "👇 <b>Please select a service:</b>", reply_markup=reply_markup_json, parse_mode="HTML")
    elif text in ["📊 Stock Status", "🌎 Stock Status", "Stock Status", "Available Country"]:
        async with aiosqlite.connect("database.db") as db:
            # Fetch all enabled countries with stock
            query = '''
                SELECT service_name, country_name, flag, stock, service_emoji_id, country_emoji_id, country_code
                FROM countries 
                WHERE status = "Enabled" AND stock > 0
                ORDER BY service_name, country_name
            '''
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
        
        if not rows:
            await bot.reply_to(message, "⚠️ <b>Stock is currently empty.</b>\nPlease check back later!", parse_mode="HTML")
            return

        bot_mode = await get_setting("bot_mode", "Normal")
        
        # Grouping by Service
        services_data = {}
        for s_name, c_name, c_flag, c_stock, s_emoji, c_emoji, c_code in rows:
            if s_name not in services_data:
                services_data[s_name] = {"emoji": s_emoji, "items": []}
            services_data[s_name]["items"].append({
                "name": c_name,
                "flag": c_flag,
                "stock": c_stock,
                "c_emoji": c_emoji,
                "c_code": c_code
            })

        text_parts = ["🌎 <b>Global Stock Status</b>\n━━━━━━━━━━━━━━━━━━━"]
        
        # Check if requester is admin to show stock
        is_requester_admin = await is_admin(user_id)
        
        for s_name, data in services_data.items():
            # ... (omitted same lines for brevity in instruction, but I will provide full block) ...
            s_icon = "📱"
            if data["emoji"] and data["emoji"] != "Not Set":
                s_icon = data["emoji"] if not data["emoji"].isdigit() else "📱"
            
            text_parts.append(f"\n{s_icon} <b>Service: {s_name}</b>")
            
            for item in data["items"]:
                c_icon = item["flag"] or "🌍"
                if item["c_emoji"] and item["c_emoji"] != "Not Set":
                    if not item["c_emoji"].isdigit():
                        c_icon = item["c_emoji"]
                
                stock_info = ""
                if is_requester_admin:
                    stock_num = item["stock"]
                    stock_fmt = f"{stock_num/1000:.1f}k" if stock_num >= 1000 else str(stock_num)
                    if stock_fmt.endswith(".0k"): stock_fmt = stock_fmt.replace(".0k", "k")
                    stock_info = f": <code>{stock_fmt}</code>"
                
                text_parts.append(f"┣ {c_icon} {item['name']}{stock_info}")
            
            # Close the branch for the last item
            if text_parts[-1].startswith("┣"):
                text_parts[-1] = text_parts[-1].replace("┣", "┗")

        text_parts.append("\n━━━━━━━━━━━━━━━━━━━")
        text_parts.append("✨ <i>Select 'Get Number' to start!</i>")

        final_text = "\n".join(text_parts)
        
        # Split message if it's too long
        if len(final_text) > 4000:
            chunks = [final_text[i:i+4000] for i in range(0, len(final_text), 4000)]
            for chunk in chunks:
                await bot.send_message(message.chat.id, chunk, parse_mode="HTML")
        else:
            await bot.reply_to(message, final_text, parse_mode="HTML")
    elif text in ["📥 Download OTP", "Download OTP"]:
        text = (
            "📥 <b>OTP Download Center</b>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "📊 <b>File Information:</b>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "📝 <b>Format:</b> .txt (Text File)\n"
            "📅 <b>Period:</b> Last 24 Hours\n"
            "📁 <b>Content:</b> Number | Country | Service | OTP\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "<i>Click the button below to generate your report.</i>"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📥 Download Now", callback_data="download_otp_start"))
        await bot.reply_to(message, text, reply_markup=markup, parse_mode="HTML")
    elif text in ["💰 My Balance", "💳 My Balance", "My Balance", "Balance"]:
        async with aiosqlite.connect("database.db") as db:
            async with db.execute('SELECT balance, joined_at FROM users WHERE user_id = ?', (user_id,)) as cursor:
                row = await cursor.fetchone()
                balance = row[0] if row else 0
                joined = row[1] if row else "Unknown"
        
        text = (
            "💰 *My Balance*\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *User ID:* `{user_id}`\n"
            f"💵 *Balance:* ${balance:.4f}\n"
            f"📅 *Joined:* {joined}\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "📈 _Keep using the bot to earn more!_"
        )
        await bot.reply_to(message, text, parse_mode="Markdown")
    elif text in ["💸 Withdraw", "Withdraw"]:
        withdraw_status = await get_setting("withdrawal_status", "Disabled")
        if withdraw_status == "Disabled":
            await bot.reply_to(message, "⚠️ *Withdrawal system is currently disabled by admin.*", parse_mode="Markdown")
            return
            
        async with aiosqlite.connect("database.db") as db:
            async with db.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,)) as cursor:
                row = await cursor.fetchone()
                balance = row[0] if row else 0
                
        min_withdraw = float(await get_setting("min_withdraw", "1.0000"))
        
        if balance < min_withdraw:
            await bot.reply_to(message, f"❌ *Insufficient Balance!*\n\n💰 Your Balance: ${balance:.4f}\n📉 Minimum Withdraw: ${min_withdraw:.4f}\n\n_Please earn more to withdraw._", parse_mode="Markdown")
            return
            
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("🇧🇩 Bkash", callback_data="withdraw_method_Bkash"))
        markup.row(InlineKeyboardButton("🇧🇩 Nogad", callback_data="withdraw_method_Nogad"))
        markup.row(InlineKeyboardButton("🔶 Binance (UID)", callback_data="withdraw_method_Binance"))
        markup.add(InlineKeyboardButton("✖️ Cancel", callback_data="withdraw_cancel"))
        await bot.reply_to(message, "💸 *Select withdrawal method:*", reply_markup=markup, parse_mode="Markdown")

    elif text in ["📡 Live Traffic", "📊 Live Traffic", "Live Traffic", "Status"]:
        async with aiosqlite.connect("database.db") as db:
            # Calculate total stock across all active countries
            async with db.execute('SELECT SUM(stock) FROM countries WHERE status="Enabled" AND stock > 0') as cursor:
                total_row = await cursor.fetchone()
                total_count = total_row[0] if total_row and total_row[0] else 0
                
            if total_count == 0:
                await bot.reply_to(message, "📊 <b>Live Traffic</b>\n\n📉 No stock currently available in the bot.", parse_mode="HTML")
                return
                
            # Fetch stock distribution
            query = 'SELECT country_name, stock, flag FROM countries WHERE status="Enabled" AND stock > 0 ORDER BY stock DESC LIMIT 10'
            async with db.execute(query) as cursor:
                traffic_data = await cursor.fetchall()
        
        text = (
            "📊 <b>Live Inventory Status</b>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <b>Status:</b> Current Stock\n"
            "━━━━━━━━━━━━━━━━━━━\n\n"
        )
        
        for country, count, flag_val in traffic_data:
            percent = (count / total_count) * 100
            flag = flag_val or "🌍"
            
            # Create a simple progress bar
            bar_length = 8
            filled = int(bar_length * count / total_count)
            bar = "🟢" * filled + "⚪" * (bar_length - filled)
            
            text += (
                f"{flag} <b>{country}</b>\n"
                f"<code>{bar}</code> {percent:.1f}%\n\n"
            )
            
        text += "━━━━━━━━━━━━━━━━━━━\n<i>Real-time inventory analysis from our global nodes.</i>"
        await bot.reply_to(message, text, parse_mode="HTML")
    elif text in ["⚙️ Admin Panel", "🛠 Admin Panel", "Admin Panel"]:
        if await is_admin(user_id):
            await admin_panel_callback(message)
        else:
            await bot.reply_to(message, "❌ *Access Denied.* Only administrators can use this command.", parse_mode="Markdown")
    elif text in ["🎧 Support", "Support"]:
        support_username = await get_setting("support_username")
        support_name = await get_setting("support_name") or "Support"

        info_text = (
            "╔══════════════════════╗\n"
            "     🎧  <b>Support Center</b>     \n"
            "╚══════════════════════╝\n\n"
            "┌─────────────────────────┐\n"
            f"│  👤 <b>Name:</b>  {support_name}\n"
            "│  🕐 <b>Hours:</b>  24/7 Available\n"
            "│  💬 <b>Response:</b>  Within minutes\n"
            "│  🌐 <b>Language:</b>  Bengali & English\n"
            "└─────────────────────────┘\n\n"
            "📌 <i>Click the button below to contact support directly.</i>"
        )

        markup = InlineKeyboardMarkup()
        if support_username:
            markup.add(InlineKeyboardButton(
                f"💬 Contact {support_name}",
                url=f"https://t.me/{support_username}"
            ))
        else:
            info_text += "\n\n⚠️ <i>Support contact not configured yet.</i>"

        await bot.reply_to(message, info_text, parse_mode="HTML", reply_markup=markup)
    else:
        pass

async def init_db():
    global db
    db = await aiosqlite.connect("database.db")
    
    # Optimize SQLite for high performance
    await db.execute('PRAGMA journal_mode=WAL')
    await db.execute('PRAGMA synchronous=NORMAL')
    await db.execute('PRAGMA cache_size=-64000') # 64MB cache
    
    # Countries table
    await db.execute('''
        CREATE TABLE IF NOT EXISTS countries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name TEXT,
            country_name TEXT,
            country_code TEXT,
            flag TEXT,
            per_otp_earn REAL,
            stock INTEGER,
            service_emoji_id TEXT,
            country_emoji_id TEXT,
            status TEXT DEFAULT "Enabled"
        )
    ''')
    await db.execute('CREATE INDEX IF NOT EXISTS idx_countries_service ON countries(service_name)')
    await db.execute('CREATE INDEX IF NOT EXISTS idx_countries_stock ON countries(stock)')
    
    # Users table
    await db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # OTP Logs table
    await db.execute('''
        CREATE TABLE IF NOT EXISTS otp_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            service TEXT,
            country TEXT,
            number TEXT,
            otp TEXT,
            price REAL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    await db.execute('CREATE INDEX IF NOT EXISTS idx_otp_logs_user ON otp_logs(user_id)')
    await db.execute('CREATE INDEX IF NOT EXISTS idx_otp_logs_timestamp ON otp_logs(timestamp)')
    
    # Withdrawals table
    await db.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            method TEXT,
            account TEXT,
            amount REAL,
            status TEXT DEFAULT "Pending",
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Active Sessions table
    await db.execute('''
        CREATE TABLE IF NOT EXISTS active_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            number TEXT,
            service TEXT,
            country TEXT,
            price REAL,
            flag TEXT,
            s_emoji_id TEXT,
            c_emoji_id TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    await db.execute('CREATE INDEX IF NOT EXISTS idx_active_sessions_number ON active_sessions(number)')

    # Settings table
    await db.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Initialize default settings
    default_settings = {
        "bot_status": "Running",
        "withdrawal_status": "Disabled",
        "min_withdraw": "1.0000",
        "main_channel": "https://t.me/SMART_TECH",
        "cooldown": "6",
        "otp_view_link": "https://t.me/SMART_TECH",
        "numbers_per_request": "2",
        "bot_mode": "Normal",
        "api_system_status": "Enabled",
        "api_url": "http://127.0.0.1:8080/api/get_sms",
        "api_key": "b8212b67b099950167914958bffd5fcc",
        "support_username": "",
        "support_name": "Support"
    }
    for key, val in default_settings.items():
        await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, val))
    
    # Admins table
    await db.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY
        )
    ''')
    await db.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (8589946469,))
    
    # Banned Users table
    await db.execute('''
        CREATE TABLE IF NOT EXISTS banned_users (
            user_id INTEGER PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Channels table
    await db.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            url TEXT,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    # Migrations for existing tables
    try: await db.execute('ALTER TABLE channels ADD COLUMN chat_id TEXT')
    except: pass
    try: await db.execute('ALTER TABLE countries ADD COLUMN status TEXT DEFAULT "Enabled"')
    except: pass
    try: await db.execute('ALTER TABLE active_sessions ADD COLUMN flag TEXT')
    except: pass
    try: await db.execute('ALTER TABLE active_sessions ADD COLUMN s_emoji_id TEXT')
    except: pass
    try: await db.execute('ALTER TABLE active_sessions ADD COLUMN c_emoji_id TEXT')
    except: pass

    await db.commit()
    await refresh_caches()

async def otp_fetcher_task():
    """Background task to poll API for OTPs and deliver to users."""
    print("OTP Fetcher Task started...")
    error_count = 0 # To limit admin notifications
    while True:
        try:
            status = await get_setting("api_system_status", "Disabled")
            if status == "Enabled":
                url = await get_setting("api_url", "http://127.0.0.1:8080/api/get_sms")
                key = await get_setting("api_key", "b8212b67b099950167914958bffd5fcc")
                
                async with httpx.AsyncClient() as client:
                    try:
                        # Call API
                        response = await client.get(f"{url}?api_key={key}", timeout=5)
                        if response.status_code == 200:
                            data = response.json()
                            
                            # Support both list and dict formats
                            sms_list = []
                            if isinstance(data, list):
                                sms_list = data
                            elif isinstance(data, dict):
                                sms_list = data.get("sms", []) or data.get("data", [])
                                
                            if sms_list:
                                async with aiosqlite.connect("database.db") as db:
                                    for sms in sms_list:
                                        # Normalize number
                                        raw_num = str(sms.get("number", "")).strip()
                                        clean_num = raw_num.replace("+", "").replace(" ", "")
                                        otp_code = sms.get("otp") or sms.get("sms") or sms.get("text")
                                        
                                        if not clean_num or not otp_code: continue
                                        
                                        # Check if this specific OTP for this number has already been delivered (Deduplication)
                                        async with db.execute('SELECT 1 FROM otp_logs WHERE number = ? AND otp = ?', (clean_num, otp_code)) as check_cursor:
                                            if await check_cursor.fetchone():
                                                continue # Already delivered this exact OTP, skip
                                                
                                        # Check if this number is active for any user
                                        # Try both with and without '+' prefix
                                        async with db.execute('''
                                            SELECT id, user_id, service, country, price, flag, s_emoji_id, c_emoji_id
                                            FROM active_sessions 
                                            WHERE number = ? OR number = ? OR number = ?
                                        ''', (clean_num, "+" + clean_num, raw_num)) as cursor:
                                            session = await cursor.fetchone()
                                            
                                        if session:
                                            s_id, u_id, service, country, price, flag_val, s_emoji_id, c_emoji_id = session
                                            
                                            # Determine bot mode and emojis
                                            bot_mode = await get_setting("bot_mode", "Normal")
                                            
                                            # Service Emoji
                                            s_emoji_html = "💬"
                                            if s_emoji_id and s_emoji_id != "Not Set":
                                                s_emoji_html = s_emoji_id if not s_emoji_id.isdigit() else "📱"

                                            # Country Flag/Emoji
                                            c_flag_html = flag_val or "🌍"
                                            if c_emoji_id and c_emoji_id != "Not Set":
                                                if not c_emoji_id.isdigit():
                                                    c_flag_html = c_emoji_id

                                            # Deliver OTP instantly
                                            delivery_text = (
                                                f"📩 <b>OTP Received!</b>\n\n"
                                                f"📱 <b>Number:</b> <code>+{clean_num}</code>\n"
                                                f"{s_emoji_html} <b>Service:</b> {service}\n"
                                                f"{c_flag_html} <b>Country:</b> {country}\n"
                                                f"━━━━━━━━━━━━━━━━━━━\n"
                                                f"🔑 <b>OTP:</b> <code>{otp_code}</code>\n"
                                                f"━━━━━━━━━━━━━━━━━━━\n"
                                                f"💰 <b>Earned:</b> ${price:.4f}\n"
                                                f"🕒 Received at: {sms.get('timestamp', 'Just now')}"
                                            )
                                            
                                            try:
                                                markup = InlineKeyboardMarkup()
                                                # Button with 6 spaces, premium icon, and one-click copy feature
                                                btn_data = {
                                                    "text": "Copy OTP: {otp_code}",
                                                    "copy_text": CopyTextButton(text=otp_code)
                                                }
                                                markup.add(InlineKeyboardButton(**btn_data))
                                                
                                                await bot.send_message(u_id, delivery_text, reply_markup=markup, parse_mode="HTML")
                                                
                                                # Update user balance
                                                await db.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (price, u_id))
                                                
                                                # Log the OTP
                                                await db.execute('''
                                                    INSERT INTO otp_logs (user_id, service, country, number, otp, price)
                                                    VALUES (?, ?, ?, ?, ?, ?)
                                                ''', (u_id, service, country, clean_num, otp_code, price))
                                                
                                                # CRITICAL: Clear the active session so the user doesn't get the same OTP again
                                                # and to prevent conflicts if another user gets this number later
                                                await db.execute('DELETE FROM active_sessions WHERE id = ?', (s_id,))
                                                
                                                await db.commit()
                                                print(f"OTP Delivered & Session Cleared: User {u_id}, Num {clean_num}")
                                            except Exception as e:
                                                import traceback
                                                traceback.print_exc()
                                                print(f"Failed to deliver OTP to {u_id}: {e}")
                            
                            # Reset error count on successful API response
                            error_count = 0
                    except Exception as e:
                        error_count += 1
                        print(f"API Request Error: {e}")
                        if error_count <= 3:
                            # Notify Admins
                            try:
                                # Use admin_cache directly for speed
                                for a_id in admin_cache:
                                    await bot.send_message(a_id, f"⚠️ <b>API Error ({error_count}/3):</b>\n<code>{str(e)}</code>", parse_mode="HTML")
                            except: pass
        except Exception as e:
            print(f"Error in otp_fetcher_task: {e}")
            
        await asyncio.sleep(1) # Poll every 1 second

async def main():
    await init_db()
    

        
    # Start 300 Get Number workers
    for _ in range(300):
        asyncio.create_task(get_number_worker())
        
    # Start 100 DB workers
    for _ in range(100):
        asyncio.create_task(db_worker())
        
    # Start 100 General workers
    for _ in range(100):
        asyncio.create_task(general_worker())
        
    # Start OTP Fetcher background task
    asyncio.create_task(otp_fetcher_task())
    
    print("Bot is starting...")
    while True:
        try:
            # lower timeouts sometimes help with unstable connections to reconnect faster
            await bot.infinity_polling(timeout=20, request_timeout=30)
        except Exception as e:
            print(f"Network error: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    # If you are in a country where Telegram is blocked, you might need a proxy:
    # from telebot import apihelper
    # apihelper.proxy = {'https': 'http://username:password@proxy_address:port'}
    
    asyncio.run(main())
