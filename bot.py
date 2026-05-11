#!/usr/bin/env python3.11
from dotenv import load_dotenv
load_dotenv()

import vk_api
from vk_api.utils import get_random_id
import os, json, random
from datetime import datetime
from flask import Flask, request
from storage import Storage, db_get
from commands import handle_command, make_mention, HIERARCHY
from economy import fmt, CURRENCY

TOKEN = os.getenv("VK_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
CONFIRMATION_CODE = os.getenv("CONFIRMATION_CODE", "")

vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
storage = Storage()

app = Flask(__name__)


def get_user_name(user_id: int) -> str:
    try:
        u = vk.users.get(user_ids=user_id)[0]
        return f"{u['first_name']} {u['last_name']}"
    except Exception:
        return f"ID{user_id}"


def send_message(peer_id: int, message: str):
    try:
        vk.messages.send(peer_id=peer_id, message=message, random_id=get_random_id())
    except Exception as e:
        print(f"[ERROR] send: {e}")


def delete_message(peer_id: int, msg: dict):
    cmid = msg.get("conversation_message_id")
    msg_id = msg.get("id")
    try:
        if cmid:
            vk.messages.delete(
                conversation_message_ids=cmid,
                peer_id=peer_id,
                delete_for_all=1
            )
        elif msg_id:
            vk.messages.delete(
                message_ids=msg_id,
                delete_for_all=1
            )
    except Exception as e:
        print(f"[WARN] delete_message: {e}")


def kick_user(peer_id: int, user_id: int):
    try:
        vk.messages.removeChatUser(chat_id=peer_id - 2000000000, user_id=user_id)
        return True
    except Exception:
        return False


def handle_invite(peer_id: int, invited_id: int, inviter_id: int):
    gban = storage.get_gban(invited_id)
    if gban:
        if storage.is_admin(inviter_id, OWNER_ID):
            return
        kick_user(peer_id, invited_id)
        send_message(peer_id,
            f"🚫 {get_user_name(invited_id)} имеет глобальную блокировку JORDANS.\n"
            f"Причина: {gban['reason']}")
        return
    chat_bans = storage.get_bans_in_chat(invited_id, peer_id)
    if chat_bans:
        if storage.is_admin(inviter_id, OWNER_ID):
            return
        kick_user(peer_id, invited_id)
        b = chat_bans[-1]
        send_message(peer_id,
            f"🚫 {get_user_name(invited_id)} заблокирован в этой беседе.\n"
            f"Причина: {b['reason']}")


def check_mute(user_id: int, peer_id: int, msg: dict) -> bool:
    mute = storage.get_mute(user_id, peer_id)
    if not mute:
        return False
    try:
        until = datetime.strptime(mute["until"], "%d/%m/%Y %H:%M:%S")
        if datetime.now() > until:
            storage.remove_mute(user_id, peer_id)
            return False
        delete_message(peer_id, msg)
        return True
    except Exception as e:
        print(f"[WARN] mute check: {e}")
        return False


def get_user_priority(user_id: int) -> int:
    if user_id == OWNER_ID:
        return 999
    mod = storage.get_moderator(user_id)
    if not mod:
        return 0
    return HIERARCHY.get(mod.get("position", ""), 0)


def handle_callback(data: dict):
    try:
        obj = data.get("object", {})
        payload = obj.get("payload", {})
        if isinstance(payload, str):
            payload = json.loads(payload)

        cmd = payload.get("cmd")
        user_id = obj.get("user_id")
        peer_id = obj.get("peer_id")
        event_id = obj.get("event_id")

        try:
            vk.messages.sendMessageEventAnswer(
                event_id=event_id,
                user_id=user_id,
                peer_id=peer_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "✅"})
            )
        except Exception as e:
            print(f"[WARN] event answer: {e}")

        if cmd == "duel_join":
            duel_id = payload.get("duel_id")
            duel = storage.get_duel(duel_id)
            if not duel or not duel.get("active"):
                send_message(peer_id, "❌ Дуэль уже завершена.")
                return
            if duel["creator"] == user_id:
                send_message(peer_id, "❌ Нельзя вступить в свою дуэль.")
                return
            if storage.get_balance(user_id) < duel["amount"]:
                send_message(peer_id, "❌ Недостаточно монет.")
                return
            storage.add_balance(user_id, -duel["amount"])
            storage.close_duel(duel_id)
            winner_id = random.choice([duel["creator"], user_id])
            loser_id = user_id if winner_id == duel["creator"] else duel["creator"]
            prize = duel["amount"] * 2
            storage.add_balance(winner_id, prize)
            mod_w = storage.get_moderator(winner_id)
            name_w = mod_w["nick"] if mod_w else get_user_name(winner_id)
            mod_l = storage.get_moderator(loser_id)
            name_l = mod_l["nick"] if mod_l else get_user_name(loser_id)
            send_message(peer_id,
                f"⚔️ Дуэль завершена!\n\n"
                f"🏆 Победитель: {make_mention(winner_id, name_w)}\n"
                f"💀 Проигравший: {make_mention(loser_id, name_l)}\n"
                f"💰 Приз: {fmt(prize)} {CURRENCY}")
    except Exception as e:
        print(f"[ERROR] handle_callback: {e}")


def process_message(data: dict):
    try:
        obj = data.get("object", {})
        msg = obj.get("message", obj)

        peer_id = msg.get("peer_id")
        user_id = msg.get("from_id")
        text = msg.get("text", "")

        if not peer_id or not user_id or user_id <= 0:
            return

        # Служебные действия — до перезагрузки БД
        action = msg.get("action", {})
        if action.get("type") == "chat_invite_user":
            storage.data = db_get()
            invited_id = action.get("member_id", 0)
            if invited_id > 0 and peer_id > 2000000000:
                handle_invite(peer_id, invited_id, user_id)
            return

        # Перезагружаем данные из БД перед обработкой
        storage.data = db_get()

        # Проверяем активна ли беседа
        if peer_id > 2000000000 and not storage.is_chat_active(peer_id):
            if text.strip().lower() in ("/start", "!start"):
                priority = get_user_priority(user_id)
                if priority >= HIERARCHY.get("Руководитель сообщества", 90) or user_id == OWNER_ID:
                    storage.set_chat_active(peer_id, True)
                    send_message(peer_id, "✅ Бот активирован в этой беседе!")
                else:
                    send_message(peer_id, "⛔ Активация доступна с должности Руководитель сообщества.")

        # Считаем сообщения
        if peer_id > 2000000000:
            storage.count_message(user_id, peer_id)

        # Тишина
        if peer_id > 2000000000 and storage.is_silence(peer_id):
            priority = get_user_priority(user_id)
            if priority == 0:
                delete_message(peer_id, msg)
                return

        # Мут
        if peer_id > 2000000000:
            if check_mute(user_id, peer_id, msg):
                return

        # Reply
        reply_user_id = None
        reply = msg.get("reply_message")
        if reply:
            reply_user_id = reply.get("from_id")

        # Команды
        if text.startswith("/") or text.startswith("!"):
            response = handle_command(
                text=text,
                from_user_id=user_id,
                peer_id=peer_id,
                storage=storage,
                vk=vk,
                get_user_name=get_user_name,
                stats_chat_id=0,
                reply_user_id=reply_user_id,
                msg=msg
            )
            if response:
                send_message(peer_id, response)

    except Exception as e:
        print(f"[ERROR] process_message: {e}")


@app.route("/", methods=["POST"])
def webhook():
    try:
        data = request.json
        if not data:
            return "ok"
        event_type = data.get("type")
        if event_type == "confirmation":
            return CONFIRMATION_CODE
        if event_type == "message_new":
            process_message(data)
        if event_type == "message_event":
            storage.data = db_get()
            handle_callback(data)
        return "ok"
    except Exception as e:
        print(f"[ERROR] webhook: {e}")
        return "ok"


@app.route("/ping", methods=["GET"])
def ping():
    return "pong", 200


@app.route("/", methods=["GET"])
def health():
    return "Bot is running", 200


if __name__ == "__main__":
    print("[BOT] Starting (Callback)...")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
