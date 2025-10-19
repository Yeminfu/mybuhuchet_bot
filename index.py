import requests
import time
import logging
import psycopg2
import os
from dotenv import load_dotenv
load_dotenv()  # загружает переменные из .env в окружение
# from psycopg2.extras import RealDictCursor

value = os.getenv('BOT_TOKEN')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === НАСТРОЙКИ ===
BOT_TOKEN = "8394525241:AAER54NxBA_6s9E2EazWGFc1z5soKPV-d7I"
API = f"https://api.telegram.org/bot{BOT_TOKEN}"




# Настройки БД
DB_CONFIG = {
    'dbname': 'chbfs_transactions',
    'user': 'admin',
    'password': '1234qwer',
    'host': 'localhost',
    'port': 5432
}

# Состояния пользователей
user_states = {}



# === Функция сохранения транзакции ===
def save_transaction(chat_id: int, operation: str, amount: float, comment: str) -> bool:
    print(chat_id,operation,amount,comment)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        # Преобразуем '+' в 'income', '-' в 'expense'
        trans_type = 'income' if operation == '+' else 'expense'
        cur.execute("""
            INSERT INTO chbfs_transactions (user_id, amount, type, description)
            VALUES (%s, %s, %s, %s)
        """, (chat_id, abs(amount), trans_type, comment))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения транзакции в БД: {e}")
        return False

save_transaction(5050441344, "+", 100.0, "H")

# === Остальные функции (без изменений, кроме вызова save_transaction) ===

def fetch_updates(offset: int | None = None) -> list:
    url = f"{API}/getUpdates"
    params = {"timeout": 30}
    if offset is not None:
        params["offset"] = offset

    try:
        response = requests.get(url, params=params, timeout=35)
        if response.status_code == 200:
            data = response.json()
            return data.get("result", [])
        else:
            logger.warning(f"Неудачный ответ от Telegram API: {response.status_code}")
            return []
    except requests.RequestException as e:
        logger.error(f"Ошибка при получении обновлений: {e}")
        return []


def send_message(chat_id: int | str, text: str, buttons: list[list[str]] | None = None) -> bool:
    url = f"{API}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if buttons:
        payload["reply_markup"] = {
            "keyboard": buttons,
            "resize_keyboard": True,
            "one_time_keyboard": False
        }
    else:
        payload["reply_markup"] = {"remove_keyboard": True}

    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except requests.RequestException as e:
        logger.error(f"Ошибка отправки сообщения: {e}")
        return False


def is_valid_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def handle_update(update: dict):
    message = update.get("message")
    if not message or "text" not in message:
        return

    chat_id = message["chat"]["id"]
    text = message["text"].strip()

    state = user_states.get(chat_id, {"step": "start"})

    if text == "/start":
        user_states[chat_id] = {"step": "awaiting_operation"}
        send_message(chat_id, "Выберите операцию:", [["+", "-"]])

    elif state["step"] == "awaiting_operation":
        if text in ("+", "-"):
            user_states[chat_id] = {
                "step": "awaiting_amount",
                "operation": text
            }
            send_message(chat_id, f"Вы выбрали: {text}\nВведите сумму:", None)
        else:
            send_message(chat_id, "Пожалуйста, нажмите + или -.", [["+", "-"]])

    elif state["step"] == "awaiting_amount":
        if is_valid_number(text):
            amount = float(text)
            user_states[chat_id] = {
                "step": "awaiting_comment",
                "operation": state["operation"],
                "amount": amount
            }
            send_message(chat_id, "Введите комментарий:", None)
        else:
            send_message(chat_id, "Это не число. Пожалуйста, введите сумму (например: 100.5):", None)

    elif state["step"] == "awaiting_comment":
        comment = text
        op = state["operation"]
        amount = state["amount"]

        # === Сохраняем транзакцию в БД ===
        if save_transaction(chat_id, op, amount, comment):
            logger.info(f"Транзакция сохранена: {chat_id}, {op}, {amount}, {comment}")
        else:
            send_message(chat_id, "⚠️ Ошибка сохранения данных. Попробуйте позже.", [["/start"]])
            del user_states[chat_id]
            return

        # Формируем итоговое сообщение
        summary = (
            f"✅ Ваши данные:\n"
            f"Операция: {op}\n"
            f"Сумма: {amount}\n"
            f"Комментарий: {comment}"
        )
        send_message(chat_id, summary, [["/start"]])
        del user_states[chat_id]

    else:
        user_states[chat_id] = {"step": "start"}
        send_message(chat_id, "Начните с команды /start", [["/start"]])


def poll():
    offset = None
    while True:
        try:
            updates = fetch_updates(offset)
            if updates:
                for update in updates:
                    offset = update["update_id"] + 1
                    handle_update(update)
            else:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Остановка бота по запросу пользователя.")
            break
        except Exception as e:
            logger.exception(f"Необработанная ошибка в цикле опроса: {e}")
            time.sleep(5)


if __name__ == "__main__":
    poll()