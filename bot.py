# bot.py
import os
import re
import time
import json
import logging
from pathlib import Path
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    Filters,
    CallbackContext,
)

# === НАСТРОЙКИ ===
TOKEN = "8180631848:AAHEmgLPC91kIktbkv6p3GPydWV7BTuqT7k"
CHECK_INTERVAL = 30  # секунд между автоматическими проверками
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# Состояния
ADD_LINK, SET_PRICE_RANGE, SET_KEYWORD = range(3)

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# === ФАЙЛОВОЕ ХРАНЕНИЕ ===
def get_user_file(user_id):
    return DATA_DIR / f"{user_id}.json"

def load_user_data(user_id):
    file = get_user_file(user_id)
    if file.exists():
        try:
            with open(file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"links": [], "min_price": None, "max_price": None, "keyword": None, "sent_ads": []}

def save_user_data(user_id, data):
    file = get_user_file(user_id)
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# === ПАРСИНГ ===
def extract_product_info(soup):
    items = []
    for card in soup.select("section[data-name='list'] a[href^='https://kufar.by/item/']"):
        try:
            title = card.select_one("h3").get_text(strip=True) if card.select_one("h3") else "Без названия"
            price_tag = card.select_one("p[font-weight='700']")
            price = price_tag.get_text(strip=True) if price_tag else "Цена не указана"
            link = card["href"].split("?")[0]
            desc = " ".join([p.get_text(strip=True) for p in card.select("p")])
            items.append({"title": title, "price": price, "link": link, "desc": desc})
        except Exception as e:
            logger.warning(f"Ошибка при парсинге карточки: {e}")
    return items

def parse_kufar(url, min_price=None, max_price=None, keyword=None):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        items = extract_product_info(soup)

        filtered = []
        for item in items:
            # Цена
            try:
                price_clean = re.sub(r"[^\d]", "", item["price"])
                price_num = int(price_clean) if price_clean else 0
                if min_price is not None and price_num < min_price: continue
                if max_price is not None and price_num > max_price: continue
            except:
                pass

            # Ключевое слово
            text = (item["title"] + " " + item["desc"]).lower()
            if keyword and keyword.lower() not in text:
                continue

            filtered.append(item)
        return filtered
    except Exception as e:
        logger.error(f"Ошибка парсинга {url}: {e}")
        return []


# === ОБРАБОТЧИКИ ===
def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    data = load_user_data(user_id)
    save_user_data(user_id, data)

    keyboard = [
        [KeyboardButton("🔗 Добавить ссылку"), KeyboardButton("💰 Указать цену")],
        [KeyboardButton("🔍 Задать ключевое слово"), KeyboardButton("📊 Статус")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    update.message.reply_text(
        "✅ Бот запущен! Автоматический парсинг каждые 30 сек.\n\n"
        "Настройте фильтры ниже 👇", reply_markup=reply_markup
    )

def add_link(update: Update, context: CallbackContext):
    update.message.reply_text("Отправьте ссылку с Kufar.by для отслеживания 🔗")
    return ADD_LINK

def save_link(update: Update, context: CallbackContext):
    url = update.message.text.strip()
    if not url.startswith("https://kufar.by/"):
        update.message.reply_text("❌ Это не ссылка Kufar.by!")
        return ADD_LINK

    user_id = update.effective_user.id
    data = load_user_data(user_id)
    if url not in data["links"]:
        data["links"].append(url)
    save_user_data(user_id, data)
    update.message.reply_text("✅ Ссылка добавлена!")
    return ConversationHandler.END

def set_price(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Формат: `мин макс` (например: `100 5000`)\n"
        "Только мин: `100 -`\nТолько макс: `- 10000`", parse_mode="Markdown"
    )
    return SET_PRICE_RANGE

def save_price(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    data = load_user_data(user_id)

    try:
        parts = text.split()
        if len(parts) == 2:
            min_str, max_str = parts
            min_p = int(min_str) if min_str != "-" else None
            max_p = int(max_str) if max_str != "-" else None
            data["min_price"] = min_p
            data["max_price"] = max_p
            save_user_data(user_id, data)
            update.message.reply_text("✅ Диапазон цен сохранён!")
        else:
            raise ValueError
    except:
        update.message.reply_text("❌ Неверный формат!")
        return SET_PRICE_RANGE

    return ConversationHandler.END

def set_keyword(update: Update, context: CallbackContext):
    update.message.reply_text("Введите ключевое слово 🔍")
    return SET_KEYWORD

def save_keyword(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    data = load_user_data(user_id)
    data["keyword"] = update.message.text.strip()
    save_user_data(user_id, data)
    update.message.reply_text("✅ Ключевое слово сохранено!")
    return ConversationHandler.END

def show_status(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    data = load_user_data(user_id)
    links = "\n".join(data["links"]) if data["links"] else "Нет"
    min_p = data["min_price"] if data["min_price"] is not None else "—"
    max_p = data["max_price"] if data["max_price"] is not None else "—"
    kw = data["keyword"] if data["keyword"] else "—"
    update.message.reply_text(
        f"📋 Настройки:\n🔗 Ссылки:\n{links}\n\n"
        f"💰 Цена: от {min_p} до {max_p}\n🔍 Ключ: {kw}"
    )

# === АВТОМАТИЧЕСКИЙ ПАРСИНГ ===
def auto_parse_job(context: CallbackContext):
    for file in DATA_DIR.glob("*.json"):
        user_id = int(file.stem)
        try:
            data = load_user_data(user_id)
            if not data["links"]:
                continue

            new_ads = []
            for url in data["links"]:
                ads = parse_kufar(url, data["min_price"], data["max_price"], data["keyword"])
                for ad in ads:
                    if ad["link"] not in data["sent_ads"]:
                        new_ads.append(ad)
                        data["sent_ads"].append(ad["link"])

            if new_ads:
                save_user_data(user_id, data)
                for ad in new_ads[:5]:  # максимум 5 новых
                    context.bot.send_message(
                        chat_id=user_id,
                        text=f"🆕 Новое объявление!\n\n"
                             f"📌 {ad['title']}\n"
                             f"💵 {ad['price']}\n"
                             f"🔗 {ad['link']}"
                    )
                logger.info(f"Отправлено {len(new_ads)} новых объявлений пользователю {user_id}")
        except Exception as e:
            logger.error(f"Ошибка при авто-парсинге для {user_id}: {e}")

# === ЗАПУСК ===
def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Conversation handlers
    conv_link = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex("^🔗 Добавить ссылку$"), add_link)],
        states={ADD_LINK: [MessageHandler(Filters.text & ~Filters.command, save_link)]},
        fallbacks=[CommandHandler("start", start)],
    )
    conv_price = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex("^💰 Указать цену$"), set_price)],
        states={SET_PRICE_RANGE: [MessageHandler(Filters.text & ~Filters.command, save_price)]},
        fallbacks=[CommandHandler("start", start)],
    )
    conv_keyword = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex("^🔍 Задать ключевое слово$"), set_keyword)],
        states={SET_KEYWORD: [MessageHandler(Filters.text & ~Filters.command, save_keyword)]},
        fallbacks=[CommandHandler("start", start)],
    )

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(conv_link)
    dp.add_handler(conv_price)
    dp.add_handler(conv_keyword)
    dp.add_handler(MessageHandler(Filters.regex("^📊 Статус$"), show_status))

    # Запуск автоматической проверки каждые 30 секунд
    j = updater.job_queue
    j.run_repeating(auto_parse_job, interval=CHECK_INTERVAL, first=10)

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
