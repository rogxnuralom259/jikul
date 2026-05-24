"""
Telethon-based Group OTP Provider System
টেলিগ্রাম অ্যাকাউন্ট থেকে সরাসরি OTP পান
"""

import asyncio
import sqlite3
import json
from datetime import datetime
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneNumberInvalidError
from telethon.tl.types import TypedDict

# Global Telethon clients storage
telethon_clients = {}
telethon_lock = asyncio.Lock()

# ─────────────────────────────────────────
# Database Functions
# ─────────────────────────────────────────

async def init_group_otp_db():
    """Group OTP Provider-এর জন্য ডাটাবেস টেবিল তৈরি করুন"""
    async with aiosqlite.connect("database.db") as db:
        # Telegram accounts table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS telegram_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number TEXT UNIQUE,
                api_id INTEGER,
                api_hash TEXT,
                session_string TEXT,
                status TEXT DEFAULT "Active",
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP
            )
        ''')
        
        # OTP Provider sessions
        await db.execute('''
            CREATE TABLE IF NOT EXISTS otp_provider_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number TEXT,
                verification_code TEXT,
                status TEXT DEFAULT "Pending",
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
        ''')
        
        # Group OTP logs
        await db.execute('''
            CREATE TABLE IF NOT EXISTS group_otp_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_phone TEXT,
                service TEXT,
                otp_code TEXT,
                received_from TEXT,
                received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        await db.commit()


# ─────────────────────────────────────────
# Telethon Client Management
# ─────────────────────────────────────────

async def initialize_telethon_provider(api_id: int, api_hash: str):
    """
    Telethon OTP Provider initialize করুন
    
    Args:
        api_id: আপনার Telegram API ID (my.telegram.org থেকে)
        api_hash: আপনার Telegram API Hash (my.telegram.org থেকে)
    """
    global telethon_clients
    
    print("🚀 Initializing Telethon OTP Provider...")
    
    # ডাটাবেস ইনিশিয়ালাইজ করুন
    await init_group_otp_db()
    
    # সব সংরক্ষিত অ্যাকাউন্ট লোড করুন
    async with aiosqlite.connect("database.db") as db:
        async with db.execute(
            'SELECT phone_number, session_string FROM telegram_accounts WHERE status = "Active"'
        ) as cursor:
            accounts = await cursor.fetchall()
    
    # প্রতিটি অ্যাকাউন্টের জন্য Telethon ক্লায়েন্ট তৈরি করুন
    for phone_number, session_string in accounts:
        try:
            client = TelegramClient(f"session_{phone_number}", api_id, api_hash)
            
            # সেশন স্ট্রিং থেকে লোড করুন
            if session_string:
                try:
                    # সেশন দেটা পার্স করুন
                    session_data = json.loads(session_string)
                    # ক্লায়েন্ট শুরু করুন
                    await client.start()
                except:
                    pass
            
            # OTP মনিটরিং শুরু করুন
            asyncio.create_task(monitor_otp_messages(client, phone_number, api_id, api_hash))
            
            telethon_clients[phone_number] = {
                "client": client,
                "status": "connected",
                "last_seen": datetime.now().isoformat()
            }
            
            print(f"✅ Connected to {phone_number}")
        except Exception as e:
            print(f"❌ Error connecting to {phone_number}: {e}")


async def add_telegram_account(phone_number: str, api_id: int, api_hash: str):
    """
    নতুন Telegram অ্যাকাউন্ট যোগ করুন
    
    Returns:
        success: True/False
        message: স্ট্যাটাস বার্তা
        session_string: সেশন স্ট্রিং
    """
    global telethon_clients
    
    try:
        # ফোন নম্বর ফরম্যাট করুন
        if not phone_number.startswith("+"):
            phone_number = "+" + phone_number
        
        # ফোন নম্বর ইতিমধ্যে বিদ্যমান কিনা চেক করুন
        async with aiosqlite.connect("database.db") as db:
            async with db.execute(
                'SELECT id FROM telegram_accounts WHERE phone_number = ?',
                (phone_number,)
            ) as cursor:
                if await cursor.fetchone():
                    return {
                        "success": False,
                        "message": "This phone number is already registered!"
                    }
        
        # Telethon ক্লায়েন্ট তৈরি করুন
        client = TelegramClient(f"session_{phone_number}", api_id, api_hash)
        
        # সংযোগ করুন এবং কোড অনুরোধ করুন
        await client.connect()
        
        # কোড অনুরোধ করুন
        result = await client.request_login_token(
            phone_number,
            max_attempts=3
        )
        
        # সেশন স্ট্রিং পান
        session_string = client.session.save()
        
        # ডাটাবেসে সংরক্ষণ করুন (Pending স্ট্যাটাস)
        async with aiosqlite.connect("database.db") as db:
            cursor = await db.execute('''
                INSERT INTO telegram_accounts 
                (phone_number, api_id, api_hash, session_string, status)
                VALUES (?, ?, ?, ?, "Pending")
            ''', (phone_number, api_id, api_hash, session_string))
            
            await db.commit()
        
        print(f"📱 Code request sent to {phone_number}")
        
        return {
            "success": True,
            "message": "Code sent to your Telegram app. Please check it.",
            "phone_number": phone_number,
            "session_string": session_string
        }
    
    except PhoneNumberInvalidError:
        return {
            "success": False,
            "message": "Invalid phone number format!"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


async def verify_telegram_code(phone_number: str, code: str, session_string: str, api_id: int, api_hash: str):
    """
    Telegram কোড যাচাই করুন
    
    Args:
        phone_number: Telegram ফোন নম্বর
        code: 5-digit কোড
        session_string: সেশন স্ট্রিং
        api_id: API ID
        api_hash: API Hash
    
    Returns:
        success: True/False
        message: স্ট্যাটাস বার্তা
    """
    global telethon_clients
    
    try:
        if not phone_number.startswith("+"):
            phone_number = "+" + phone_number
        
        # ক্লায়েন্ট তৈরি করুন
        client = TelegramClient(f"session_{phone_number}", api_id, api_hash)
        
        await client.connect()
        
        # কোড দিয়ে লগইন করুন
        try:
            await client.sign_in(phone_number, code)
        except SessionPasswordNeededError:
            # 2FA সক্ষম থাকলে
            return {
                "success": False,
                "message": "2FA is enabled. Please disable it and try again."
            }
        
        # Me অবজেক্ট পান
        me = await client.get_me()
        
        # নতুন সেশন স্ট্রিং পান
        new_session_string = client.session.save()
        
        # ডাটাবেসে আপডেট করুন
        async with aiosqlite.connect("database.db") as db:
            await db.execute('''
                UPDATE telegram_accounts 
                SET session_string = ?, status = "Active", updated_at = CURRENT_TIMESTAMP
                WHERE phone_number = ?
            ''', (new_session_string, phone_number))
            
            await db.commit()
        
        # Telethon ক্লায়েন্ট সংরক্ষণ করুন
        telethon_clients[phone_number] = {
            "client": client,
            "status": "connected",
            "last_seen": datetime.now().isoformat()
        }
        
        # OTP মনিটরিং শুরু করুন
        asyncio.create_task(monitor_otp_messages(client, phone_number, api_id, api_hash))
        
        print(f"✅ Account verified: {phone_number}")
        
        return {
            "success": True,
            "message": "Account verified successfully!",
            "phone_number": phone_number,
            "api_id": api_id,
            "api_hash": api_hash,
            "session_string": new_session_string,
            "username": me.username or "N/A"
        }
    
    except Exception as e:
        print(f"❌ Verification error: {e}")
        return {
            "success": False,
            "message": f"Verification failed: {str(e)}"
        }


async def get_telegram_accounts():
    """সব Telegram অ্যাকাউন্ট পান"""
    async with aiosqlite.connect("database.db") as db:
        async with db.execute(
            'SELECT id, phone_number, status, last_seen FROM telegram_accounts ORDER BY created_at DESC'
        ) as cursor:
            return await cursor.fetchall()


async def remove_telegram_account(phone_number: str):
    """Telegram অ্যাকাউন্ট সরান"""
    global telethon_clients
    
    try:
        # ক্লায়েন্ট বন্ধ করুন
        if phone_number in telethon_clients:
            await telethon_clients[phone_number]["client"].disconnect()
            del telethon_clients[phone_number]
        
        # ডাটাবেস থেকে সরান
        async with aiosqlite.connect("database.db") as db:
            await db.execute(
                'DELETE FROM telegram_accounts WHERE phone_number = ?',
                (phone_number,)
            )
            await db.commit()
        
        print(f"🗑️ Account removed: {phone_number}")
        
        return {
            "success": True,
            "message": f"Account {phone_number} removed successfully!"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error removing account: {str(e)}"
        }


# ─────────────────────────────────────────
# OTP Monitoring
# ─────────────────────────────────────────

async def monitor_otp_messages(client, phone_number: str, api_id: int, api_hash: str):
    """
    OTP বার্তা মনিটর করুন এবং সংরক্ষণ করুন
    """
    from telethon import events
    import re
    
    @client.on(events.NewMessage())
    async def handler(event):
        try:
            message_text = event.message.message
            
            if not message_text:
                return
            
            # OTP কোড খুঁজুন (4-6 ডিজিট)
            otp_pattern = r'\b([0-9]{4,6})\b'
            otp_codes = re.findall(otp_pattern, message_text)
            
            if otp_codes:
                for otp_code in otp_codes:
                    # সেবা সনাক্ত করুন
                    service = "Unknown"
                    if "facebook" in message_text.lower():
                        service = "Facebook"
                    elif "whatsapp" in message_text.lower():
                        service = "WhatsApp"
                    elif "telegram" in message_text.lower():
                        service = "Telegram"
                    elif "google" in message_text.lower():
                        service = "Google"
                    elif "twitter" in message_text.lower():
                        service = "Twitter"
                    elif "instagram" in message_text.lower():
                        service = "Instagram"
                    
                    # ডাটাবেসে লগ করুন
                    async with aiosqlite.connect("database.db") as db:
                        await db.execute('''
                            INSERT INTO group_otp_logs 
                            (account_phone, service, otp_code, received_from)
                            VALUES (?, ?, ?, ?)
                        ''', (phone_number, service, otp_code, event.sender_id or "Group"))
                        
                        await db.commit()
                    
                    print(f"📩 OTP received: {otp_code} for {service}")
        
        except Exception as e:
            print(f"Error in OTP handler: {e}")
    
    try:
        await client.run_until_disconnected()
    except Exception as e:
        print(f"Client disconnected: {e}")
        # পুনরায় সংযোগ করার চেষ্টা করুন
        await asyncio.sleep(30)
        await initialize_telethon_provider(api_id, api_hash)


async def get_otp_logs(limit: int = 20):
    """সাম্প্রতিক OTP লগ পান"""
    async with aiosqlite.connect("database.db") as db:
        async with db.execute('''
            SELECT account_phone, otp_code, received_from, received_at 
            FROM group_otp_logs 
            ORDER BY received_at DESC 
            LIMIT ?
        ''', (limit,)) as cursor:
            return await cursor.fetchall()


# ─────────────────────────────────────────
# Integration with Main Bot
# ─────────────────────────────────────────

async def send_otp_to_user(user_id: int, otp_code: str, service: str, account_phone: str):
    """ব্যবহারকারীর কাছে OTP পাঠান"""
    from telebot import AsyncTeleBot
    
    try:
        text = (
            f"📩 <b>OTP Received!</b>\n\n"
            f"📱 <b>Account:</b> {account_phone}\n"
            f"🔑 <b>Service:</b> {service}\n"
            f"🔐 <b>OTP Code:</b> <code>{otp_code}</code>\n\n"
            f"<i>This code will expire in 2 minutes.</i>"
        )
        
        # আপনার বট ব্যবহার করুন
        # await bot.send_message(user_id, text, parse_mode="HTML")
        
    except Exception as e:
        print(f"Error sending OTP: {e}")


# ─────────────────────────────────────────
# Export Functions
# ─────────────────────────────────────────

__all__ = [
    'initialize_telethon_provider',
    'add_telegram_account',
    'verify_telegram_code',
    'get_telegram_accounts',
    'remove_telegram_account',
    'monitor_otp_messages',
    'get_otp_logs',
    'send_otp_to_user',
    'init_group_otp_db'
]
