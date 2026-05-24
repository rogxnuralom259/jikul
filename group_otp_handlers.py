"""
Group OTP Provider Bot Handlers
Admin প্যানেল থেকে Telegram অ্যাকাউন্ট ম্যানেজ করুন
"""

from telethon_group_otp import (
    add_telegram_account,
    verify_telegram_code,
    get_telegram_accounts,
    remove_telegram_account,
    get_otp_logs,
    initialize_telethon_provider
)

# ─────────────────────────────────────────
# Group OTP Provider Callback Handlers
# ─────────────────────────────────────────

@bot.callback_query_handler(func=lambda call: call.data == "admin_group_otp")
async def admin_group_otp_callback(call):
    if not await is_admin(call.from_user.id):
        return
    try:
        await bot.answer_callback_query(call.id)
    except:
        pass
    
    # সব সংরক্ষিত অ্যাকাউন্ট পান
    accounts = await get_telegram_accounts()
    account_count = len(accounts)
    
    status_emoji = "🟢" if account_count > 0 else "🔴"
    status_text = f"Active ({account_count})" if account_count > 0 else "Not Configured"
    
    text = (
        "📡 <b>Group OTP Provider</b>\n\n"
        f"<b>Status:</b> {status_emoji} {status_text}\n\n"
        "This feature allows receiving OTPs directly from Telegram accounts.\n"
        "Configure your own Telegram accounts to receive OTP codes.\n\n"
        "<i>How it works:</i>\n"
        "1. Add a Telegram account\n"
        "2. Verify with code\n"
        "3. Bot monitors messages for OTPs\n"
        "4. OTPs are forwarded to users"
    )
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("➕ Add New Account", callback_data="add_group_otp_account"))
    markup.row(InlineKeyboardButton("📋 View Accounts", callback_data="view_group_otp_accounts"))
    markup.row(InlineKeyboardButton("📊 View OTP Logs", callback_data="view_group_otp_logs"))
    markup.row(InlineKeyboardButton("↩️ Back to Providers", callback_data="admin_otp_providers"))
    
    await bot.edit_message_text(
        text=text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode="HTML"
    )


@bot.callback_query_handler(func=lambda call: call.data == "add_group_otp_account")
async def add_group_otp_account_callback(call):
    if not await is_admin(call.from_user.id):
        return
    
    admin_states[call.from_user.id] = {
        "state": "waiting_telegram_phone",
        "msg_id": call.message.message_id
    }
    
    text = (
        "📱 <b>Add New Telegram Account</b>\n\n"
        "<b>Step 1 - Phone Number</b>\n\n"
        "Please enter the Telegram phone number with country code.\n\n"
        "<b>Example:</b> +880XXXXXXXXXX\n\n"
        "Type 'cancel' to abort."
    )
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="admin_group_otp"))
    
    await bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="HTML")
    await bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "view_group_otp_accounts")
async def view_group_otp_accounts_callback(call):
    if not await is_admin(call.from_user.id):
        return
    
    accounts = await get_telegram_accounts()
    
    text = "📋 <b>Telegram Accounts</b>\n\n"
    
    if not accounts:
        text += "No accounts configured yet."
    else:
        for acc_id, phone, status, last_seen in accounts:
            status_emoji = "🟢" if status == "Active" else "🔴"
            text += f"{status_emoji} {phone}\n"
            if last_seen:
                text += f"  <i>Last seen: {last_seen}</i>\n"
            text += f"  <code>ID: {acc_id}</code>\n"
            text += f"  [Remove] • [Details]\n\n"
    
    markup = InlineKeyboardMarkup()
    if accounts:
        markup.row(InlineKeyboardButton("🗑️ Remove Account", callback_data="remove_group_otp_account"))
    markup.row(InlineKeyboardButton("➕ Add New", callback_data="add_group_otp_account"))
    markup.row(InlineKeyboardButton("↩️ Back", callback_data="admin_group_otp"))
    
    await bot.edit_message_text(
        text=text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode="HTML"
    )


@bot.callback_query_handler(func=lambda call: call.data == "view_group_otp_logs")
async def view_group_otp_logs_callback(call):
    if not await is_admin(call.from_user.id):
        return
    
    logs = await get_otp_logs(limit=20)
    
    text = "📊 <b>OTP Logs (Last 20)</b>\n\n"
    
    if not logs:
        text += "No logs yet."
    else:
        for account_phone, otp_code, received_from, received_at in logs:
            text += (
                f"📱 <b>Account:</b> {account_phone}\n"
                f"🔑 <b>OTP:</b> <code>{otp_code}</code>\n"
                f"📨 <b>From:</b> {received_from}\n"
                f"🕒 <b>Time:</b> {received_at}\n"
                "━━━━━━━━━━━━━━━━━━━\n"
            )
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🔄 Refresh", callback_data="view_group_otp_logs"))
    markup.row(InlineKeyboardButton("↩️ Back", callback_data="admin_group_otp"))
    
    await bot.edit_message_text(
        text=text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode="HTML"
    )


# ─────────────────────────────────────────
# Message Handlers for OTP Provider
# ─────────────────────────────────────────

async def handle_telegram_phone_input(message):
    """টেলিগ্রাম ফোন নম্বর ইনপুট হ্যান্ডলার"""
    user_id = message.from_user.id
    
    if user_id not in admin_states:
        return False
    
    state = admin_states[user_id]
    if state.get("state") != "waiting_telegram_phone":
        return False
    
    phone = message.text.strip()
    
    # ফোন নম্বর ফরম্যাট যাচাই করুন
    if not phone.startswith("+"):
        phone = "+" + phone
    
    # সংক্ষিপ্ত বৈধতা
    if len(phone) < 10:
        await bot.reply_to(message, "❌ Invalid phone number format. Please try again.")
        return True
    
    # Telegram API ক্রেডেনশিয়াল প্রয়োজন
    # এখানে আপনার নিজস্ব API ID এবং HASH ব্যবহার করুন
    API_ID = YOUR_API_ID  # আপনার API ID
    API_HASH = "YOUR_API_HASH"  # আপনার API Hash
    
    # অ্যাকাউন্ট যোগ করার চেষ্টা করুন
    result = await add_telegram_account(phone, API_ID, API_HASH)
    
    if result["success"]:
        admin_states[user_id]["state"] = "waiting_telegram_code"
        admin_states[user_id]["phone_number"] = phone
        admin_states[user_id]["session_string"] = result.get("session_string")
        
        text = (
            f"✅ <b>Code Sent!</b>\n\n"
            f"📱 <b>Phone:</b> {phone}\n\n"
            "Please check your Telegram app for the verification code.\n"
            "You have 2-5 minutes to receive it.\n\n"
            "<b>Enter the code below:</b>"
        )
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("❌ Cancel", callback_data="admin_group_otp"))
        
        await bot.reply_to(message, text, reply_markup=markup, parse_mode="HTML")
    else:
        await bot.reply_to(
            message,
            f"❌ <b>Error:</b> {result['message']}\n\nPlease try again.",
            parse_mode="HTML"
        )
    
    return True


async def handle_telegram_code_input(message):
    """টেলিগ্রাম কোড ইনপুট হ্যান্ডলার"""
    user_id = message.from_user.id
    
    if user_id not in admin_states:
        return False
    
    state = admin_states[user_id]
    if state.get("state") != "waiting_telegram_code":
        return False
    
    code = message.text.strip()
    
    # কোড ফরম্যাট যাচাই করুন
    if not code.isdigit() or len(code) != 5:
        await bot.reply_to(message, "❌ Invalid code format. Please enter a 5-digit code.")
        return True
    
    # কোড যাচাই করুন
    API_ID = YOUR_API_ID
    API_HASH = "YOUR_API_HASH"
    
    result = await verify_telegram_code(
        state["phone_number"],
        code,
        state["session_string"],
        API_ID,
        API_HASH
    )
    
    if result["success"]:
        text = (
            "✅ <b>Account Connected Successfully!</b>\n\n"
            f"📱 <b>Phone:</b> {result['phone_number']}\n"
            f"🔑 <b>API ID:</b> <code>{result['api_id']}</code>\n"
            f"🆔 <b>API Hash:</b> <code>{result['api_hash']}</code>\n\n"
            "<b>Session String:</b>\n"
            f"<code>{result['session_string'][:50]}...</code>\n\n"
            "✅ The account is now active and monitoring for OTPs."
        )
        
        await bot.reply_to(message, text, parse_mode="HTML")
        
        # অ্যাকাউন্ট দেখান
        del admin_states[user_id]
        await asyncio.sleep(1)  # সংরক্ষণের জন্য অপেক্ষা করুন
        
        # আপডেট করা অ্যাকাউন্ট তালিকা দেখান
        from telebot import types
        mock_call = types.CallbackQuery(
            id='0',
            from_user=message.from_user,
            chat_instance='0',
            message=message,
            data="view_group_otp_accounts"
        )
        mock_call.message.message_id = state.get("msg_id")
        await view_group_otp_accounts_callback(mock_call)
    else:
        await bot.reply_to(
            message,
            f"❌ <b>Verification Failed:</b> {result['message']}\n\nPlease try again.",
            parse_mode="HTML"
        )
        admin_states[user_id]["state"] = "waiting_telegram_phone"
    
    return True


# ─────────────────────────────────────────
# Integration in handle_buttons
# ─────────────────────────────────────────

# handle_buttons() function-এ এটি যুক্ত করুন:
"""
    # Check if admin is setting up Group OTP Provider
    if user_id in admin_states:
        state_data = admin_states[user_id]
        
        elif state_data["state"] == "waiting_telegram_phone":
            if await handle_telegram_phone_input(message):
                return
        
        elif state_data["state"] == "waiting_telegram_code":
            if await handle_telegram_code_input(message):
                return
"""
