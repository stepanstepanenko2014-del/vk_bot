#!/usr/bin/env python3.11
from dotenv import load_dotenv
load_dotenv()

import vk_api
from vk_api.utils import get_random_id
import os
from datetime import datetime
from flask import Flask, request
from storage import Storage
from commands import handle_command

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
        vk.messages.send(
            peer_id=peer_id,
            message=message,
            random_id=get_random_id()
        )
    except Exception as e:
        print(f"[ERROR] send: {e}")


def kick_user(peer_id: int, user_id: int):
    try:
        vk.messages.removeChatUser(
            chat_id=peer_id - 2000000000,
            user_id=user_id
        )
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
            f"Причина: {gban['reason']}"
        )
        return

    chat_bans = storage.get_bans_in_chat(invited_id, peer_id)
    if chat_bans:
        if storage.is_admin(inviter_id, OWNER_ID):
            return
        kick_user(peer_id, invited_id)
        b = chat_bans[-1]
        send_message(peer_id,
            f"🚫 {get_user_name(invited_id)} заблокирован в этой беседе.\n"
            f"Причина: {b['reason']}"
        )


def check_mute(user_id: int, peer_id: int, msg: dict) -> bool:
    """
    Проверяет мут пользователя.
    Если замучен — удаляет сообщение и возвращает True.
    Если мут истёк — снимает и возвращает False.
    """
    mute = storage.get_mute(user_id, peer_id)
    if not mute:
        return False

    try:
        until = datetime.strptime(mute["until"], "%d/%m/%Y %H:%M:%S")
        if datetime.now() > until:
            storage.remove_mute(user_id, peer_id)
            return False

        # Удаляем сообщение
        msg_id = msg.get("id") or msg.get("conversation_message_id")
        if msg_id:
            try:
                vk.messages.delete(
                    message_ids=msg_id,
                    delete_for_all=1,
                    peer_id=peer_id
                )
            except Exception as e:
                print(f"[WARN] delete mute msg: {e}")
        return True

    except Exception as e:
        print(f"[WARN] mute check: {e}")
        return False


def process_message(data: dict):
    try:
        obj = data.get("object", {})
        msg = obj.get("message", obj)

        peer_id = msg.get("peer_id")
        user_id = msg.get("from_id")
        text = msg.get("text", "")

        if not peer_id or not user_id or user_id <= 0:
            return

        # Служебные действия
        action = msg.get("action", {})
        if action.get("type") == "chat_invite_user":
            invited_id = action.get("member_id", 0)
            if invited_id > 0 and peer_id > 2000000000:
                handle_invite(peer_id, invited_id, user_id)
            return

        # Считаем сообщения
        if peer_id > 2000000000:
            storage.count_message(user_id, peer_id)

        # Проверяем мут — если замучен, удаляем сообщение и не обрабатываем команды
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
                reply_user_id=reply_user_id
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
