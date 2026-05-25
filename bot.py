import logging
import json
import base64
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ========================= CONFIG =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USERNAME = "@OfficialLavishz"
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

PAYMENT_PROCESSING_MSG = "⏳ Payment processing. Admin will verify your payment shortly."

# ==================== PAYMENT LINKS ====================
PRICE_LINKS = {
    30: "https://www.g2a.com/rewarble-crypto-gift-card-30-usd-by-rewarble-key-global-i10000505309025",
    40: "https://www.g2a.com/rewarble-crypto-gift-card-40-usd-by-rewarble-key-global-i10000505309069",
    50: "https://www.g2a.com/rewarble-crypto-gift-card-50-usd-by-rewarble-key-global-i10000505309003",
    60: "https://www.g2a.com/rewarble-crypto-gift-card-60-usd-by-rewarble-key-global-i10000505309071",
    70: "https://www.g2a.com/rewarble-crypto-gift-card-70-usd-by-rewarble-key-global-i10000505309092",
    80: "https://www.g2a.com/rewarble-crypto-gift-card-80-usd-by-rewarble-key-global-i10000505309093",
    90: "https://www.g2a.com/rewarble-crypto-gift-card-90-usd-by-rewarble-key-global-i10000505309094",
    100: "https://www.g2a.com/rewarble-crypto-gift-card-100-usd-by-rewarble-key-global-i10000505309004",
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

orders = {}
order_counter = 1000
user_states = {}  # To track users who are entering total

def generate_order_id():
    global order_counter
    order_counter += 1
    return f"#{order_counter}"

def get_payment_split(total: int):
    if total in PRICE_LINKS:
        return [total]
    
    amounts = sorted(PRICE_LINKS.keys(), reverse=True)
    split = []
    remaining = total
    
    while remaining > 0:
        for amt in amounts:
            if amt <= remaining:
                split.append(amt)
                remaining -= amt
                break
        else:
            break
            
    if remaining > 0 and split:
        split[-1] += remaining
    return split

# ======================= MAIN MENU =======================
async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
    keyboard = [
        [InlineKeyboardButton("💳 Checkout", callback_data="checkout")],
        [InlineKeyboardButton("⚠️ Support", callback_data="support")]
    ]
    text = "👋 Welcome to **Lavish Checkout**!\n\nWhat would you like to do?"

    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ======================= START =======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    # Deep link from website
    if args and len(args) > 0 and args[0].startswith("cart_"):
        try:
            encoded = args[0][5:]
            decoded = base64.urlsafe_b64decode(encoded).decode('utf-8')
            cart_data = json.loads(decoded)
            subtotal = round(float(cart_data.get("subtotal", 0)))

            orders[user_id] = {
                "order_id": generate_order_id(),
                "items": cart_data.get("items", []),
                "subtotal": subtotal,
            }
            await show_cart(update, context)
            return
        except Exception as e:
            logger.error(f"Cart decode error: {e}")

    await send_main_menu(update, context)

async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    order = orders.get(user_id)
    if not order:
        await send_main_menu(update, context)
        return

    text = f"🛒 **Order {order['order_id']}**\n\n"
    for item in order.get("items", []):
        total = item.get('price', 0) * item.get('qty', 1)
        text += f"• {item.get('name')} ×{item.get('qty')} — ${total:.2f}\n"
    text += f"\n**Total: ${order['subtotal']}**"

    keyboard = [
        [InlineKeyboardButton("✅ Proceed to Payment", callback_data="checkout")],
        [InlineKeyboardButton("🔙 Back", callback_data="back")]
    ]

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ======================= BUTTON HANDLER =======================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    await query.answer()

    if data == "support":
        await query.edit_message_text(f"🛠 Contact Admin:\n**{ADMIN_USERNAME}**", parse_mode='Markdown')
        return

    if data == "checkout":
        if user_id in orders:
            await show_payment_options(update, context)
        else:
            user_states[user_id] = "waiting_for_total"
            await query.edit_message_text(
                "💳 **Enter Cart Total**\n\n"
                "Please type your total amount (e.g. `85` or `125.50`):",
                parse_mode='Markdown'
            )
    elif data == "back":
        await send_main_menu(update, context, edit=True)
    elif data.startswith("pay_"):
        await handle_payment_selection(update, context, data)

# ======================= PAYMENT OPTIONS =======================
async def show_payment_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    order = orders.get(user_id)
    if not order:
        await query.edit_message_text("❌ No active order found.")
        return

    total = order['subtotal']
    split = get_payment_split(total)

    text = f"🛍 **Order {order['order_id']}**\n**Total: ${total}**\n\n"
    if len(split) == 1:
        text += "Pay using the link below:"
    else:
        text += "Please pay the following amounts:\n"

    keyboard = []
    for amt in split:
        if amt in PRICE_LINKS:
            keyboard.append([InlineKeyboardButton(f"💳 Pay ${amt}", callback_data=f"pay_{amt}")])

    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def handle_payment_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    user_id = query.from_user.id
    order = orders.get(user_id)

    try:
        _, amount_str = data.split("_")
        amount = int(amount_str)
        link = PRICE_LINKS[amount]
    except:
        await query.edit_message_text("❌ Invalid option.")
        return

    text = f"💳 **Payment for Order {order['order_id']}**\n\n"
    text += f"Pay **${amount}** here:\n\n{link}\n\n"
    text += "After payment, send the proof (screenshot or receipt)."

    await query.edit_message_text(text)

# ======================= MESSAGE HANDLER =======================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id in user_states and user_states[user_id] == "waiting_for_total":
        try:
            total = round(float(text.replace(",", "")))
            if total <= 0:
                raise ValueError

            orders[user_id] = {
                "order_id": generate_order_id(),
                "items": [{"name": "Manual Order", "price": total, "qty": 1}],
                "subtotal": total,
            }
            del user_states[user_id]
            await show_cart(update, context)
        except:
            await update.message.reply_text("❌ Please send a valid number (e.g. 85 or 120.50)")
    else:
        # Proof detection
        if any(word in text.lower() for word in ["paid", "receipt", "screenshot", "done", "proof"]):
            if user_id in orders:
                order = orders[user_id]
                await update.message.reply_text(f"✅ Proof received for **Order {order['order_id']}**.\n\n{PAYMENT_PROCESSING_MSG}")
                
                if ADMIN_USER_ID:
                    try:
                        await context.bot.send_message(
                            chat_id=ADMIN_USER_ID,
                            text=f"🛎 **New Proof!**\nOrder: {order['order_id']}\nUser: @{update.effective_user.username or user_id}\nTotal: ${order['subtotal']}"
                        )
                    except:
                        pass
            else:
                await update.message.reply_text("Please start checkout first.")

# ======================= MAIN =======================
def main():
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not set!")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Lavish Checkout Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
