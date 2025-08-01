import logging
import csv
import os
from datetime import datetime
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

FILENAME = "medicines.csv"
GROUPS_FILE = "groups.csv"

if not os.path.exists(FILENAME):
    with open(FILENAME, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["group_id", "name", "expiry_date", "quantity", "symptom"])

if not os.path.exists(GROUPS_FILE):
    with open(GROUPS_FILE, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["user_id", "group_id"])

def get_user_group(user_id):
    with open(GROUPS_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['user_id'] == str(user_id):
                return row['group_id']
    return None

def set_user_group(user_id, group_id):
    lines = []
    found = False
    with open(GROUPS_FILE, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        lines = list(reader)

    for line in lines:
        if line and line[0] == str(user_id):
            line[1] = group_id
            found = True
            break

    if not found:
        lines.append([str(user_id), group_id])

    with open(GROUPS_FILE, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(lines)

def set_group(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        update.message.reply_text("Использование: /group <название группы>")
        return
    group_id = context.args[0]
    user_id = update.message.chat_id
    set_user_group(user_id, group_id)
    update.message.reply_text(f"Теперь вы используете аптечку группы: *{group_id}*", parse_mode='Markdown')

def add_medicine(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    group_id = get_user_group(user_id)
    if not group_id:
        update.message.reply_text("Сначала установите аптечку через /group <имя>")
        return

    if len(context.args) < 4:
        update.message.reply_text("Использование: /add <название> <годен до: ГГГГ-ММ-ДД> <кол-во> <симптомы>")
        return

    try:
        name = context.args[0].lower()
        expiry = context.args[1]
        qty = int(context.args[2])
        symptom = ' '.join(context.args[3:]).lower()
        datetime.strptime(expiry, "%Y-%m-%d")
    except ValueError:
        update.message.reply_text("Ошибка в параметрах. Используйте: /add <название> <годен до: ГГГГ-ММ-ДД> <кол-во> <симптомы>")
        return

    rows = []
    found = False

    with open(FILENAME, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['group_id'] == group_id and row['name'] == name:
                row['quantity'] = str(int(row['quantity']) + qty)
                if expiry > row['expiry_date']:
                    row['expiry_date'] = expiry
                existing_symptoms = row.get('symptom', '').lower()
                # Добавляем симптом, если его нет (разделяем через ;)
                existing_set = set(map(str.strip, existing_symptoms.split(';'))) if existing_symptoms else set()
                new_set = set(map(str.strip, symptom.split(';')))
                all_symptoms = existing_set.union(new_set)
                row['symptom'] = '; '.join(sorted(all_symptoms))
                found = True
            rows.append(row)

    if not found:
        rows.append({
            "group_id": group_id,
            "name": name,
            "expiry_date": expiry,
            "quantity": str(qty),
            "symptom": symptom
        })

    with open(FILENAME, 'w', encoding='utf-8', newline='') as f:
        fieldnames = ["group_id", "name", "expiry_date", "quantity", "symptom"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    update.message.reply_text(f"Добавлено: {name.capitalize()} — {qty} шт., годен до {expiry}\nСимптомы: {symptom}")

def use_medicine(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    group_id = get_user_group(user_id)
    if not group_id:
        update.message.reply_text("Сначала установите аптечку через /group <имя>")
        return

    try:
        name = context.args[0].lower()
        used_qty = int(context.args[1])
    except (IndexError, ValueError):
        update.message.reply_text("Использование: /use <название> <кол-во>")
        return

    rows = []
    updated = False

    with open(FILENAME, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['group_id'] == group_id and row['name'] == name:
                current_qty = int(row['quantity'])
                if used_qty > current_qty:
                    update.message.reply_text("Недостаточно лекарства.")
                    return
                row['quantity'] = str(current_qty - used_qty)
                updated = True
            rows.append(row)

    with open(FILENAME, 'w', encoding='utf-8', newline='') as f:
        fieldnames = ["group_id", "name", "expiry_date", "quantity", "symptom"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    if updated:
        update.message.reply_text(f"Использовано: {name.capitalize()} — {used_qty} шт.")
    else:
        update.message.reply_text("Лекарство не найдено.")

def remove_medicine(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    group_id = get_user_group(user_id)
    if not group_id:
        update.message.reply_text("Сначала установите аптечку через /group <имя>")
        return

    try:
        name = context.args[0].lower()
    except IndexError:
        update.message.reply_text("Использование: /remove <название>")
        return

    rows = []
    removed = False

    with open(FILENAME, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not (row['group_id'] == group_id and row['name'] == name):
                rows.append(row)
            else:
                removed = True

    with open(FILENAME, 'w', encoding='utf-8', newline='') as f:
        fieldnames = ["group_id", "name", "expiry_date", "quantity", "symptom"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    if removed:
        update.message.reply_text(f"Удалено: {name.capitalize()}")
    else:
        update.message.reply_text("Лекарство не найдено.")

def clear_medicines(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    group_id = get_user_group(user_id)
    if not group_id:
        update.message.reply_text("Сначала установите аптечку через /group <имя>")
        return

    rows = []
    changed = False

    with open(FILENAME, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['group_id'] != group_id:
                rows.append(row)
            else:
                changed = True

    if not changed:
        update.message.reply_text("Аптечка уже пуста.")
        return

    with open(FILENAME, 'w', encoding='utf-8', newline='') as f:
        fieldnames = ["group_id", "name", "expiry_date", "quantity", "symptom"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    update.message.reply_text("Вся аптечка очищена.")

def list_medicines(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    group_id = get_user_group(user_id)
    if not group_id:
        update.message.reply_text("Сначала установите аптечку через /group <имя>")
        return

    output = []

    with open(FILENAME, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['group_id'] == group_id:
                symptoms = row.get('symptom', '')
                output.append(f"• {row['name'].capitalize()} — {row['quantity']} шт. (до {row['expiry_date']})\n  Симптомы: {symptoms}")

    if output:
        update.message.reply_text("🧰 Ваша аптечка:\n\n" + "\n".join(output))
    else:
        update.message.reply_text("📭 Аптечка пуста.")

def search_medicine(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    group_id = get_user_group(user_id)
    if not group_id:
        update.message.reply_text("Сначала установите аптечку через /group <имя>")
        return

    try:
        name = context.args[0].lower()
    except IndexError:
        update.message.reply_text("Использование: /find <название>")
        return

    found = False

    with open(FILENAME, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['group_id'] == group_id and name in row['name']:
                symptoms = row.get('symptom', '')
                update.message.reply_text(
                    f"Лекарство: {row['name'].capitalize()}\n"
                    f"Количество: {row['quantity']} шт.\n"
                    f"Годен до: {row['expiry_date']}\n"
                    f"Симптомы: {symptoms}"
                )
                found = True
                break

    if not found:
        update.message.reply_text("Лекарство не найдено.")

def search_by_symptom(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    group_id = get_user_group(user_id)
    if not group_id:
        update.message.reply_text("Сначала установите аптечку через /group <имя>")
        return

    if not context.args:
        update.message.reply_text("Использование: /symptom <симптом>")
        return

    symptom_query = ' '.join(context.args).lower().strip()

    matched = []

    with open(FILENAME, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['group_id'] == group_id and int(row['quantity']) > 0:
                symptoms = row.get('symptom', '').lower()
                # Симптомы могут быть через ';', ищем по частичному совпадению
                symptom_list = [s.strip() for s in symptoms.split(';') if s.strip()]
                if any(symptom_query in s for s in symptom_list):
                    matched.append(f"{row['name'].capitalize()} — {row['quantity']} шт. (до {row['expiry_date']})")

    if matched:
        update.message.reply_text("Лекарства, подходящие для симптома '{}':\n{}".format(symptom_query, '\n'.join(matched)))
    else:
        update.message.reply_text(f"Лекарства с симптомом '{symptom_query}' не найдены.")

def check_expired(context: CallbackContext):
    logger.info("Проверка сроков годности...")
    now = datetime.now().strftime("%Y-%m-%d")
    expired = {}

    with open(FILENAME, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['expiry_date'] < now and int(row['quantity']) > 0:
                group_id = row['group_id']
                if group_id not in expired:
                    expired[group_id] = []
                expired[group_id].append(f"{row['name'].capitalize()} (годен до {row['expiry_date']})")

    for group_id, meds in expired.items():
        with open(GROUPS_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['group_id'] == group_id:
                    chat_id = int(row['user_id'])
                    context.bot.send_message(chat_id=chat_id,
                                             text="⚠️ Внимание! Просрочены лекарства:\n" + "\n".join(meds))

def manual_check(update: Update, context: CallbackContext):
    # Команда /check для ручной проверки просроченных лекарств
    check_expired(context)
    update.message.reply_text("Проверка просроченных лекарств завершена.")

def main():
    # Telegram bot
    TOKEN = "8030082684:AAHZXl3DJsn5MMambFnCYKIDcfKONDxppzA"
    updater = Updater(TOKEN)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("group", set_group))
    dp.add_handler(CommandHandler("add", add_medicine))
    dp.add_handler(CommandHandler("use", use_medicine))
    dp.add_handler(CommandHandler("remove", remove_medicine))  # можно оставить и /delete с алиасом
    dp.add_handler(CommandHandler("delete", remove_medicine))
    dp.add_handler(CommandHandler("clear", clear_medicines))
    dp.add_handler(CommandHandler("list", list_medicines))
    dp.add_handler(CommandHandler("find", search_medicine))
    dp.add_handler(CommandHandler("symptom", search_by_symptom))
    dp.add_handler(CommandHandler("check", manual_check))

    scheduler = BackgroundScheduler(timezone=pytz.timezone("Europe/Moscow"))
    scheduler.add_job(check_expired, 'cron', hour=9, minute=0, args=(updater.bot,))
    scheduler.start()

    # ❗️Запускаем бота в ГЛАВНОМ потоке, чтобы программа не завершалась
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
# Добавление сервера проверки активности Flask для Render

from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "I'm alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

