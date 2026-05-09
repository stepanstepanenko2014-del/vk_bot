import os
import json
import requests
from datetime import datetime, timedelta

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}


def db_get():
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/bot_data?key=eq.main&select=value",
            headers=HEADERS
        )
        rows = r.json()
        if rows:
            data = json.loads(rows[0]["value"])
            data.setdefault("bans", {})
            data.setdefault("gbans", {})
            data.setdefault("networks", {})
            data.setdefault("admins", {})
            data.setdefault("moderators", {})
            data.setdefault("warnings", {})
            data.setdefault("messages", {})
            data.setdefault("chat_types", {})
            return data
    except Exception as e:
        print(f"[DB] get error: {e}")
    return {
        "messages": {}, "moderators": {}, "warnings": {},
        "networks": {}, "admins": {}, "bans": {}, "gbans": {}, "chat_types": {}
    }


def db_save(data):
    try:
        payload = {"key": "main", "value": json.dumps(data, ensure_ascii=False)}
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/bot_data",
            headers={**HEADERS, "Prefer": "resolution=merge-duplicates"},
            json=payload
        )
    except Exception as e:
        print(f"[DB] save error: {e}")


class Storage:
    def __init__(self):
        self.data = db_get()

    def _save(self):
        db_save(self.data)

    # ── Сообщения ──
    def count_message(self, user_id: int, peer_id: int):
        uid, pid = str(user_id), str(peer_id)
        today = datetime.now().strftime("%Y-%m-%d")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.data["messages"].setdefault(uid, {}).setdefault(pid, {})
        d = self.data["messages"][uid][pid]
        d["total"] = d.get("total", 0) + 1
        d[today] = d.get(today, 0) + 1
        d["last_time"] = now_str
        self._save()

    def get_user_stats(self, user_id: int, peer_ids: list = None):
        uid = str(user_id)
        today = datetime.now().strftime("%Y-%m-%d")
        week_days = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        month_days = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)]

        if uid not in self.data["messages"]:
            return {"total": 0, "today": 0, "week": 0, "month": 0, "last_time": None}

        total = today_count = week_count = month_count = 0
        last_time = None

        for pid, counts in self.data["messages"][uid].items():
            if peer_ids is not None and int(pid) not in peer_ids:
                continue
            total += counts.get("total", 0)
            today_count += counts.get(today, 0)
            for d in week_days:
                week_count += counts.get(d, 0)
            for d in month_days:
                month_count += counts.get(d, 0)
            lt = counts.get("last_time")
            if lt and (last_time is None or lt > last_time):
                last_time = lt

        return {
            "total": total, "today": today_count,
            "week": week_count, "month": month_count, "last_time": last_time
        }

    def get_user_stats_in_chat(self, user_id: int, peer_id: int):
        uid, pid = str(user_id), str(peer_id)
        today = datetime.now().strftime("%Y-%m-%d")
        if uid not in self.data["messages"] or pid not in self.data["messages"][uid]:
            return {"total": 0, "today": 0, "last_time": None}
        d = self.data["messages"][uid][pid]
        return {
            "total": d.get("total", 0),
            "today": d.get(today, 0),
            "last_time": d.get("last_time")
        }

    def get_chat_stats(self, peer_id: int, days: int = 7):
        pid = str(peer_id)
        date_range = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
        result = []
        for uid, chats in self.data["messages"].items():
            if pid not in chats:
                continue
            count = sum(chats[pid].get(d, 0) for d in date_range)
            total = chats[pid].get("total", 0)
            if count > 0 or total > 0:
                result.append({"user_id": int(uid), "period": count, "total": total})
        return sorted(result, key=lambda x: x["period"], reverse=True)

    # ── Сетки ──
    def add_network(self, name: str, peer_id: int):
        self.data["networks"].setdefault(name, [])
        if peer_id not in self.data["networks"][name]:
            self.data["networks"][name].append(peer_id)
            self._save()
            return True
        return False

    def remove_network_chat(self, name: str, peer_id: int):
        if name in self.data["networks"] and peer_id in self.data["networks"][name]:
            self.data["networks"][name].remove(peer_id)
            if not self.data["networks"][name]:
                del self.data["networks"][name]
            self._save()
            return True
        return False

    def delete_network(self, name: str):
        if name in self.data["networks"]:
            del self.data["networks"][name]
            self._save()
            return True
        return False

    def get_network(self, name: str):
        return self.data["networks"].get(name)

    def get_all_networks(self):
        return self.data["networks"]

    def find_network_by_chat(self, peer_id: int):
        for name, chats in self.data["networks"].items():
            if peer_id in chats:
                return name, chats
        return None, None

    def get_all_chat_peer_ids(self) -> list:
        peer_ids = set()
        for uid, chats in self.data["messages"].items():
            for pid in chats.keys():
                peer_ids.add(int(pid))
        return list(peer_ids)

    # ── Типы бесед ──
    def set_chat_type(self, peer_id: int, chat_type: str):
        self.data["chat_types"][str(peer_id)] = chat_type
        self._save()

    def get_chat_type(self, peer_id: int) -> str:
        return self.data["chat_types"].get(str(peer_id), "chat")

    def get_moder_chats_in_network(self, peer_id: int) -> list:
        _, net_chats = self.find_network_by_chat(peer_id)
        if not net_chats:
            return []
        return [p for p in net_chats if self.get_chat_type(p) == "moder"]

    # ── Модераторы ──
    def set_moderator(self, user_id: int, nick: str, role: str, position: str):
        self.data["moderators"][str(user_id)] = {
            "nick": nick, "role": role, "position": position,
            "added": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        self._save()

    def get_moderator(self, user_id: int):
        return self.data["moderators"].get(str(user_id))

    def get_all_moderators(self):
        return self.data["moderators"]

    def remove_moderator(self, user_id: int):
        uid = str(user_id)
        if uid in self.data["moderators"]:
            del self.data["moderators"][uid]
            self._save()
            return True
        return False

    # ── Администраторы ──
    def add_admin(self, user_id: int, nick: str, added_by: int):
        self.data["admins"][str(user_id)] = {
            "nick": nick, "added_by": added_by,
            "added": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        self._save()

    def remove_admin(self, user_id: int):
        uid = str(user_id)
        if uid in self.data["admins"]:
            del self.data["admins"][uid]
            self._save()
            return True
        return False

    def is_admin(self, user_id: int, owner_id: int):
        return user_id == owner_id or str(user_id) in self.data["admins"]

    def get_all_admins(self):
        return self.data["admins"]

    # ── Выговоры ──
    def add_warning(self, user_id: int, reason: str, issued_by: int, issued_by_name: str):
        uid = str(user_id)
        self.data["warnings"].setdefault(uid, []).append({
            "reason": reason, "issued_by": issued_by,
            "issued_by_name": issued_by_name,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "active": True
        })
        self._save()
        return sum(1 for w in self.data["warnings"][uid] if w.get("active"))

    def get_warnings(self, user_id: int):
        return self.data["warnings"].get(str(user_id), [])

    def get_active_warnings(self, user_id: int):
        return [w for w in self.get_warnings(user_id) if w.get("active")]

    def clear_warnings(self, user_id: int):
        for w in self.data["warnings"].get(str(user_id), []):
            w["active"] = False
        self._save()

    # ── Баны ──
    def add_ban(self, user_id: int, peer_id: int, reason: str,
                term: str, by: int, by_name: str, is_gban: bool = False):
        uid = str(user_id)
        self.data["bans"].setdefault(uid, []).append({
            "peer_id": peer_id, "reason": reason,
            "term": term or "Навсегда", "by": by, "by_name": by_name,
            "date": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "active": True, "gban": is_gban
        })
        self._save()

    def add_gban(self, user_id: int, reason: str, by_name: str):
        self.data["gbans"][str(user_id)] = {
            "reason": reason, "by_name": by_name,
            "date": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "active": True
        }
        self._save()

    def remove_gban(self, user_id: int):
        uid = str(user_id)
        if uid in self.data["gbans"]:
            self.data["gbans"][uid]["active"] = False
            self._save()
            return True
        return False

    def get_gban(self, user_id: int):
        g = self.data["gbans"].get(str(user_id))
        if g and g.get("active"):
            return g
        return None

    def get_bans(self, user_id: int):
        return [b for b in self.data["bans"].get(str(user_id), []) if b.get("active")]

    def get_bans_in_chat(self, user_id: int, peer_id: int):
        return [b for b in self.get_bans(user_id) if b["peer_id"] == peer_id]

    def unban(self, user_id: int, peer_id: int):
        uid = str(user_id)
        changed = False
        for b in self.data["bans"].get(uid, []):
            if b["peer_id"] == peer_id and b.get("active"):
                b["active"] = False
                changed = True
        if changed:
            self._save()
        return changed

    def count_banned_chats(self, user_id: int) -> int:
        peers = set(b["peer_id"] for b in self.get_bans(user_id) if not b.get("gban"))
        return len(peers)
