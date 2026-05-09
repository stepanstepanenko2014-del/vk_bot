#!/usr/bin/env python3.11
from dotenv import load_dotenv
load_dotenv()

import vk_api
from vk_api.utils import get_random_id
import os
import json
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
        send_message(peer_id, f"🚫 {get_user_name(invited_id)} под глобальным баном")
        return

    chat_bans = storage.get_bans_in_chat(invited_id, peer_id)
    if chat_bans:
        if storage.is_admin(inviter_id, OWNER_ID):
            return
        kick_user(peer_id, invited_id)
        send_message(peer_id, f"🚫 {get_user_name(invited_id)} заблокирован в этой беседе")


def process_message(obj):
    try:
        if "message" in obj:
            msg = obj["message"]
        elif "object" in obj and "message" in obj["object"]:
            msg = obj["object"]["message"]
        else:
            return "ok"
        
        peer_id = msg.get("peer_id")
        user_id = msg.get("from_id")
        text = msg.get("text", "")
        
        if not peer_id or user_id <= 0:
            return "ok"
        
        action = msg.get("action", {})
        if action.get("type") == "chat_invite_user":
            invited_id = action.get("member_id", 0)
            if invited_id > 0 and peer_id > 2000000000:
                handle_invite(peer_id, invited_id, user_id)
            return "ok"
        
        if peer_id > 2000000000:
            storage.count_message(user_id, peer_id)
        
        reply_user_id = None
        reply = msg.get("reply_message")
        if reply:
            reply_user_id = reply.get("from_id")
        
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
        
        return "ok"
    except Exception as e:
        print(f"[ERROR] {e}")
        return "ok"


@app.route("/", methods=["POST"])
def webhook():
    data = request.json
    print(f"[DEBUG] {data}")
    
    if data.get("type") == "confirmation":
        return CONFIRMATION_CODE
    
    if data.get("type") == "message_new":
        process_message(data)
        return "ok"
    
    return "ok"


@app.route("/", methods=["GET"])
def health():
    return "Bot is running", 200


if __name__ == "__main__":
    print("[BOT] Starting...")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
