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
            data.setdefault("mutes", {})
            data.setdefault("beer", {})
            data.setdefault("economy", {})
            data.setdefault("duels", {})
            data.setdefault("promos", {})
            data.setdefault("charity", {})
            data.setdefault("silence", {})  # peer_id -> bool
            data.setdefault("active_chats", {})  # peer_id -> bool
            return data
    except Exception as e:
        print(f"[DB] get error: {e}")
    return {
        "messages": {}, "moderators": {}, "warnings": {},
        "networks": {}, "admins": {}, "bans": {}, "gbans": {},
        "chat_types": {}, "mutes": {}, "beer": {},
        "economy": {}, "duels": {}, "promos": {}, "charity": {},
        "silence": {}, "active_chats": {}
    }


def db_save(data):
    try:
        payload = {"key": "main", "value": json.dumps(data, ensure_ascii=False)}
        requests.post(
            f"{SUPABASE_URL}/rest/v1/bot_data",
            headers={**HEADERS, "Prefer": "resolution=merge-duplicates"},
            json=payload
        )
    except Exception as e:
        print(f"[DB] save error: {e}")


def default_economy():
    return {
        "balance": 0, "bank": 0, "vip": False, "vip_until": None,
        "hide_balance": False, "hide_balance_active": False,
        "prize_last": None, "deposit": None,
        "businesses": [], "charity_total": 0, "kicks": 0,
    }


class Storage:
    def __init__(self):
        self.data = db_get()

    def _reload(self):
        self.data = db_get()

    def _save(self):
        db_save(self.data)

    def _eco(self, user_id: int) -> dict:
        uid = str(user_id)
        if uid not in self.data["economy"]:
            self.data["economy"][uid] = default_economy()
        eco = self.data["economy"][uid]
        for k, v in default_economy().items():
            eco.setdefault(k, v)
        return eco

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
        return {"total": total, "today": today_count,
                "week": week_count, "month": month_count, "last_time": last_time}

    def get_user_stats_in_chat(self, user_id: int, peer_id: int):
        uid, pid = str(user_id), str(peer_id)
        today = datetime.now().strftime("%Y-%m-%d")
        if uid not in self.data["messages"] or pid not in self.data["messages"][uid]:
            return {"total": 0, "today": 0, "last_time": None}
        d = self.data["messages"][uid][pid]
        return {"total": d.get("total", 0), "today": d.get(today, 0),
                "last_time": d.get("last_time")}

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

    # ── Тишина ──
    def set_silence(self, peer_id: int, state: bool):
        self.data["silence"][str(peer_id)] = state
        self._save()

    def is_silence(self, peer_id: int) -> bool:
        return self.data["silence"].get(str(peer_id), False)

    # ── Активные беседы ──
    def set_chat_active(self, peer_id: int, state: bool):
        self.data["active_chats"][str(peer_id)] = state
        self._save()

    def is_chat_active(self, peer_id: int) -> bool:
        return self.data["active_chats"].get(str(peer_id), False)

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

    # ── Муты ──
    def add_mute(self, user_id: int, peer_id: int, until: str, reason: str, by_name: str):
        uid = str(user_id)
        self.data["mutes"].setdefault(uid, [])
        for m in self.data["mutes"][uid]:
            if m["peer_id"] == peer_id and m.get("active"):
                m["active"] = False
        self.data["mutes"][uid].append({
            "peer_id": peer_id, "until": until, "reason": reason,
            "by_name": by_name,
            "date": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "active": True
        })
        self._save()

    def remove_mute(self, user_id: int, peer_id: int):
        uid = str(user_id)
        changed = False
        for m in self.data["mutes"].get(uid, []):
            if m["peer_id"] == peer_id and m.get("active"):
                m["active"] = False
                changed = True
        if changed:
            self._save()
        return changed

    def get_mute(self, user_id: int, peer_id: int):
        uid = str(user_id)
        for m in self.data["mutes"].get(uid, []):
            if m["peer_id"] == peer_id and m.get("active"):
                return m
        return None

    # ── Пиво ──
    def add_beer(self, user_id: int, amount: float):
        uid = str(user_id)
        month = datetime.now().strftime("%Y-%m")
        self.data["beer"].setdefault(uid, {"total": 0, "month": {}, "last_time": None})
        self.data["beer"][uid]["total"] = round(self.data["beer"][uid].get("total", 0) + amount, 1)
        self.data["beer"][uid]["month"][month] = round(
            self.data["beer"][uid]["month"].get(month, 0) + amount, 1)
        self.data["beer"][uid]["last_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._save()

    def get_beer(self, user_id: int) -> dict:
        return self.data["beer"].get(str(user_id), {"total": 0, "month": {}, "last_time": None})

    def get_beer_last_time(self, user_id: int):
        return self.data["beer"].get(str(user_id), {}).get("last_time")

    def get_beer_top(self, month: str = None) -> list:
        if month is None:
            month = datetime.now().strftime("%Y-%m")
        result = []
        for uid, data in self.data["beer"].items():
            amount = data.get("month", {}).get(month, 0)
            if amount > 0:
                result.append({"user_id": int(uid), "amount": amount})
        return sorted(result, key=lambda x: x["amount"], reverse=True)

    def reset_beer(self):
        self.data["beer"] = {}
        self._save()

    # ── Экономика ──
    def get_balance(self, user_id: int) -> int:
        return self._eco(user_id)["balance"]

    def get_bank(self, user_id: int) -> int:
        return self._eco(user_id)["bank"]

    def add_balance(self, user_id: int, amount: int):
        eco = self._eco(user_id)
        eco["balance"] = max(0, eco["balance"] + amount)
        self._save()

    def set_balance(self, user_id: int, amount: int):
        self._eco(user_id)["balance"] = max(0, amount)
        self._save()

    def transfer(self, from_id: int, to_id: int, amount: int) -> bool:
        eco_from = self._eco(from_id)
        if eco_from["balance"] < amount:
            return False
        eco_from["balance"] -= amount
        self._eco(to_id)["balance"] += amount
        self._save()
        return True

    def deposit_to_bank(self, user_id: int, amount: int) -> bool:
        eco = self._eco(user_id)
        if eco["balance"] < amount:
            return False
        eco["balance"] -= amount
        eco["bank"] += amount
        self._save()
        return True

    def withdraw_from_bank(self, user_id: int, amount: int) -> bool:
        eco = self._eco(user_id)
        if eco["bank"] < amount:
            return False
        eco["bank"] -= amount
        eco["balance"] += amount
        self._save()
        return True

    def is_vip(self, user_id: int) -> bool:
        return self._eco(user_id).get("vip", False)

    def buy_vip(self, user_id: int, price: int) -> bool:
        eco = self._eco(user_id)
        if eco["balance"] < price:
            return False
        eco["balance"] -= price
        eco["vip"] = True
        self._save()
        return True

    def has_hide_balance(self, user_id: int) -> bool:
        return self._eco(user_id).get("hide_balance", False)

    def buy_hide_balance(self, user_id: int, price: int) -> bool:
        eco = self._eco(user_id)
        if eco["balance"] < price or eco.get("hide_balance"):
            return False
        eco["balance"] -= price
        eco["hide_balance"] = True
        self._save()
        return True

    def toggle_hide_balance(self, user_id: int) -> bool:
        eco = self._eco(user_id)
        if not eco.get("hide_balance"):
            return False
        eco["hide_balance_active"] = not eco.get("hide_balance_active", False)
        self._save()
        return eco["hide_balance_active"]

    def get_prize_last(self, user_id: int):
        return self._eco(user_id).get("prize_last")

    def claim_prize(self, user_id: int, amount: int):
        eco = self._eco(user_id)
        eco["prize_last"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        eco["balance"] += amount
        self._save()

    def open_deposit(self, user_id: int, amount: int, rate: float, days: int) -> bool:
        eco = self._eco(user_id)
        if eco["balance"] < amount or eco.get("deposit"):
            return False
        eco["balance"] -= amount
        until = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        eco["deposit"] = {"amount": amount, "rate": rate, "until": until,
                          "opened": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        self._save()
        return True

    def close_deposit(self, user_id: int):
        eco = self._eco(user_id)
        dep = eco.get("deposit")
        if not dep:
            return None
        until = datetime.strptime(dep["until"], "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        earned = int(dep["amount"] * dep["rate"]) if now >= until else 0
        eco["balance"] += dep["amount"] + earned
        eco["deposit"] = None
        self._save()
        return {"amount": dep["amount"], "earned": earned, "early": now < until}

    def get_deposit(self, user_id: int):
        return self._eco(user_id).get("deposit")

    def buy_business(self, user_id: int, biz_type: str, price: int) -> bool:
        eco = self._eco(user_id)
        if eco["balance"] < price:
            return False
        eco["balance"] -= price
        eco["businesses"].append({
            "type": biz_type, "bought": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "products": 0, "products_last": None, "balance": 0,
        })
        self._save()
        return True

    def get_businesses(self, user_id: int) -> list:
        return self._eco(user_id).get("businesses", [])

    def add_products(self, user_id: int, biz_index: int, products: int, cost: int) -> bool:
        eco = self._eco(user_id)
        bizs = eco.get("businesses", [])
        if biz_index >= len(bizs) or eco["balance"] < cost:
            return False
        eco["balance"] -= cost
        bizs[biz_index]["products"] += products
        self._save()
        return True

    def collect_business(self, user_id: int) -> int:
        from economy import BUSINESS
        eco = self._eco(user_id)
        total_income = 0
        now = datetime.now()
        for biz in eco.get("businesses", []):
            biz_info = BUSINESS.get(biz["type"])
            if not biz_info or biz["products"] <= 0:
                continue
            last = biz.get("products_last")
            if last:
                last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
                hours = (now - last_dt).total_seconds() / 3600
            else:
                hours = 0
            if hours >= 1:
                max_hours = biz["products"] / (biz_info["products_per_day"] / 24)
                worked_hours = min(hours, max_hours)
                income = int(biz_info["income"] / 24 * worked_hours)
                products_used = int(biz_info["products_per_day"] / 24 * worked_hours)
                biz["balance"] = biz.get("balance", 0) + income
                biz["products"] = max(0, biz["products"] - products_used)
                biz["products_last"] = now.strftime("%Y-%m-%d %H:%M:%S")
        for biz in eco.get("businesses", []):
            total_income += biz.get("balance", 0)
            biz["balance"] = 0
        eco["balance"] += total_income
        self._save()
        return total_income

    def sell_businesses(self, user_id: int) -> int:
        from economy import BUSINESS
        eco = self._eco(user_id)
        total = sum(BUSINESS.get(b["type"], {}).get("price", 0) // 2
                    for b in eco.get("businesses", []))
        eco["businesses"] = []
        eco["balance"] += total
        self._save()
        return total

    def sell_business_to_user(self, from_id: int, to_id: int, biz_index: int, price: int) -> bool:
        eco_from = self._eco(from_id)
        eco_to = self._eco(to_id)
        bizs = eco_from.get("businesses", [])
        if biz_index >= len(bizs) or eco_to["balance"] < price:
            return False
        biz = bizs.pop(biz_index)
        eco_to["businesses"].append(biz)
        eco_to["balance"] -= price
        eco_from["balance"] += price
        self._save()
        return True

    def roulette(self, user_id: int, bet: int) -> dict:
        import random
        from economy import ROULETTE_MIN
        eco = self._eco(user_id)
        if eco["balance"] < bet or bet < ROULETTE_MIN:
            return {"ok": False}
        eco["balance"] -= bet
        roll = random.random()
        if roll < 0.05:
            win = bet * 5
            result = "джекпот"
        elif roll < 0.45:
            win = bet * 2
            result = "победа"
        else:
            win = 0
            result = "проигрыш"
        eco["balance"] += win
        self._save()
        return {"ok": True, "bet": bet, "win": win, "result": result}

    def donate_charity(self, user_id: int, amount: int) -> bool:
        eco = self._eco(user_id)
        if eco["balance"] < amount:
            return False
        eco["balance"] -= amount
        eco["charity_total"] = eco.get("charity_total", 0) + amount
        self.data["charity"][str(user_id)] = eco["charity_total"]
        self._save()
        return True

    def get_charity_top(self) -> list:
        result = [{"user_id": int(uid), "amount": amt}
                  for uid, amt in self.data["charity"].items()]
        return sorted(result, key=lambda x: x["amount"], reverse=True)

    def create_promo(self, code: str, amount: int, max_uses: int, creator_id: int) -> bool:
        if code in self.data["promos"]:
            return False
        self.data["promos"][code] = {
            "amount": amount, "max_uses": max_uses, "uses": 0,
            "activated_by": [], "creator": creator_id,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self._save()
        return True

    def activate_promo(self, user_id: int, code: str) -> dict:
        promo = self.data["promos"].get(code)
        if not promo:
            return {"ok": False, "reason": "not_found"}
        if user_id in promo["activated_by"]:
            return {"ok": False, "reason": "already_used"}
        if promo["uses"] >= promo["max_uses"]:
            return {"ok": False, "reason": "expired"}
        promo["uses"] += 1
        promo["activated_by"].append(user_id)
        self._eco(user_id)["balance"] += promo["amount"]
        self._save()
        return {"ok": True, "amount": promo["amount"]}

    def get_user_promos(self, user_id: int) -> list:
        return [{"code": c, "amount": p["amount"]}
                for c, p in self.data["promos"].items()
                if user_id in p.get("activated_by", [])]

    def get_eco(self, user_id: int) -> dict:
        return self._eco(user_id)

    def get_rich_top(self) -> list:
        result = []
        for uid, eco in self.data["economy"].items():
            total = eco.get("balance", 0) + eco.get("bank", 0)
            result.append({"user_id": int(uid), "balance": eco.get("balance", 0),
                           "bank": eco.get("bank", 0), "total": total})
        return sorted(result, key=lambda x: x["total"], reverse=True)

    def create_duel(self, duel_id: str, creator_id: int, amount: int, peer_id: int):
        self.data["duels"][duel_id] = {
            "creator": creator_id, "amount": amount, "peer_id": peer_id,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "active": True
        }
        self._save()

    def get_duel(self, duel_id: str):
        return self.data["duels"].get(duel_id)

    def close_duel(self, duel_id: str):
        if duel_id in self.data["duels"]:
            self.data["duels"][duel_id]["active"] = False
            self._save()

    def add_kick(self, user_id: int):
        self._eco(user_id)["kicks"] = self._eco(user_id).get("kicks", 0) + 1
        self._save()

    def get_kicks(self, user_id: int) -> int:
        return self._eco(user_id).get("kicks", 0)
