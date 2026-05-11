import os, json, re, random
from datetime import datetime, timedelta

OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# ────────────────────────────────────────────────────────────
# КОНСТАНТЫ
# ────────────────────────────────────────────────────────────
CURRENCY = "монет"
START_BALANCE = 0
VIP_PRICE = 1000
HIDE_BALANCE_PRICE = 1500
ROULETTE_MIN = 50
PRIZE_AMOUNT = 25
PRIZE_COOLDOWN = 3600
DEPOSIT_DAYS = 10
DEPOSIT_RATE = 0.03

BUSINESS = {
    "завод": {
        "price": 5000,
        "income": 100,
        "products_per_day": 100,
        "product_price": 1,
    }
}

PROMO_MAX_AMOUNT = 50
PROMO_MAX_USES = 10

MONTH_NAMES = {
    "01": "January", "02": "February", "03": "March",
    "04": "April", "05": "May", "06": "June",
    "07": "July", "08": "August", "09": "September",
    "10": "October", "11": "November", "12": "December"
}

HIERARCHY = {
    "Специальный руководитель": 110,
    "Модератор": 20,
}

# ────────────────────────────────────────────────────────────
# SUPABASE
# ────────────────────────────────────────────────────────────
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
        import requests
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/bot_data?key=eq.main&select=value",
            headers=HEADERS
        )
        rows = r.json()
        if rows:
            data = json.loads(rows[0]["value"])
            defaults = ["bans", "gbans", "networks", "admins", "moderators",
                        "warnings", "messages", "chat_types", "mutes", "beer",
                        "economy", "duels", "promos", "charity", "silence", "active_chats"]
            for key in defaults:
                data.setdefault(key, {})
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
        import requests
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


# ────────────────────────────────────────────────────────────
# STORAGE
# ────────────────────────────────────────────────────────────
class Storage:
    def __init__(self):
        self.data = db_get()

    def _save(self):
        db_save(self.data)

    def _reload(self):
        self.data = db_get()

    def _eco(self, user_id: int) -> dict:
        uid = str(user_id)
        if uid not in self.data["economy"]:
            self.data["economy"][uid] = default_economy()
        return self.data["economy"][uid]

    # Сообщения (для статистики)
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
        if uid not in self.data["messages"]:
            return {"total": 0, "today": 0, "week": 0, "last_time": None}
        total = today_count = week_count = 0
        last_time = None
        for pid, counts in self.data["messages"][uid].items():
            if peer_ids is not None and int(pid) not in peer_ids:
                continue
            total += counts.get("total", 0)
            today_count += counts.get(today, 0)
            for d in week_days:
                week_count += counts.get(d, 0)
            lt = counts.get("last_time")
            if lt and (last_time is None or lt > last_time):
                last_time = lt
        return {"total": total, "today": today_count, "week": week_count, "last_time": last_time}

    # Модераторы
    def get_moderator(self, user_id: int):
        return self.data["moderators"].get(str(user_id))

    def set_moderator(self, user_id: int, nick: str, role: str, position: str):
        self.data["moderators"][str(user_id)] = {
            "nick": nick, "role": role, "position": position,
            "added": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        self._save()

    def remove_moderator(self, user_id: int):
        uid = str(user_id)
        if uid in self.data["moderators"]:
            del self.data["moderators"][uid]
            self._save()
            return True
        return False

    def get_all_moderators(self):
        return self.data["moderators"]

    # Администраторы (только владелец)
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

    # Экономика
    def get_balance(self, user_id: int) -> int:
        return self._eco(user_id)["balance"]

    def get_bank(self, user_id: int) -> int:
        return self._eco(user_id).get("bank", 0)

    def add_balance(self, user_id: int, amount: int):
        eco = self._eco(user_id)
        eco["balance"] = max(0, eco["balance"] + amount)
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
        eco["bank"] = eco.get("bank", 0) + amount
        self._save()
        return True

    def withdraw_from_bank(self, user_id: int, amount: int) -> bool:
        eco = self._eco(user_id)
        if eco.get("bank", 0) < amount:
            return False
        eco["bank"] -= amount
        eco["balance"] += amount
        self._save()
        return True

    def is_vip(self, user_id: int) -> bool:
        return self._eco(user_id).get("vip", False)

    def buy_vip(self, user_id: int, price: int) -> bool:
        eco = self._eco(user_id)
        if eco["balance"] < price or eco.get("vip"):
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
        eco.setdefault("businesses", []).append({
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
        bizs[biz_index]["products"] = bizs[biz_index].get("products", 0) + products
        self._save()
        return True

    def collect_business(self, user_id: int) -> int:
        eco = self._eco(user_id)
        total_income = 0
        now = datetime.now()
        for biz in eco.get("businesses", []):
            biz_info = BUSINESS.get(biz["type"])
            if not biz_info or biz.get("products", 0) <= 0:
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
        eco_to.setdefault("businesses", []).append(biz)
        eco_to["balance"] -= price
        eco_from["balance"] += price
        self._save()
        return True

    def roulette(self, user_id: int, bet: int) -> dict:
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
                  for uid, amt in self.data.get("charity", {}).items()]
        return sorted(result, key=lambda x: x["amount"], reverse=True)

    def create_promo(self, code: str, amount: int, max_uses: int, creator_id: int) -> bool:
        if code in self.data.get("promos", {}):
            return False
        self.data.setdefault("promos", {})[code] = {
            "amount": amount, "max_uses": max_uses, "uses": 0,
            "activated_by": [], "creator": creator_id,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self._save()
        return True

    def activate_promo(self, user_id: int, code: str) -> dict:
        promo = self.data.get("promos", {}).get(code)
        if not promo:
            return {"ok": False, "reason": "not_found"}
        if user_id in promo.get("activated_by", []):
            return {"ok": False, "reason": "already_used"}
        if promo.get("uses", 0) >= promo.get("max_uses", 0):
            return {"ok": False, "reason": "expired"}
        promo["uses"] = promo.get("uses", 0) + 1
        promo.setdefault("activated_by", []).append(user_id)
        self._eco(user_id)["balance"] += promo["amount"]
        self._save()
        return {"ok": True, "amount": promo["amount"]}

    def get_user_promos(self, user_id: int) -> list:
        return [{"code": c, "amount": p["amount"]}
                for c, p in self.data.get("promos", {}).items()
                if user_id in p.get("activated_by", [])]

    def get_eco(self, user_id: int) -> dict:
        return self._eco(user_id)

    def get_rich_top(self) -> list:
        result = []
        for uid, eco in self.data["economy"].items():
            total = eco.get("balance", 0) + eco.get("bank", 0)
            result.append({"user_id": int(uid), "total": total})
        return sorted(result, key=lambda x: x["total"], reverse=True)

    def create_duel(self, duel_id: str, creator_id: int, amount: int, peer_id: int):
        self.data.setdefault("duels", {})[duel_id] = {
            "creator": creator_id, "amount": amount, "peer_id": peer_id,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "active": True
        }
        self._save()

    def get_duel(self, duel_id: str):
        return self.data.get("duels", {}).get(duel_id)

    def close_duel(self, duel_id: str):
        if duel_id in self.data.get("duels", {}):
            self.data["duels"][duel_id]["active"] = False
            self._save()

    def add_kick(self, user_id: int):
        self._eco(user_id)["kicks"] = self._eco(user_id).get("kicks", 0) + 1
        self._save()

    def get_kicks(self, user_id: int) -> int:
        return self._eco(user_id).get("kicks", 0)

    # Пиво
    def add_beer(self, user_id: int, amount: float):
        uid = str(user_id)
        month = datetime.now().strftime("%Y-%m")
        self.data.setdefault("beer", {})
        self.data["beer"].setdefault(uid, {"total": 0, "month": {}, "last_time": None})
        self.data["beer"][uid]["total"] = round(self.data["beer"][uid].get("total", 0) + amount, 1)
        self.data["beer"][uid]["month"][month] = round(
            self.data["beer"][uid]["month"].get(month, 0) + amount, 1)
        self.data["beer"][uid]["last_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._save()

    def get_beer(self, user_id: int) -> dict:
        return self.data.get("beer", {}).get(str(user_id), {"total": 0, "month": {}, "last_time": None})

    def get_beer_last_time(self, user_id: int):
        return self.data.get("beer", {}).get(str(user_id), {}).get("last_time")

    def get_beer_top(self, month: str = None) -> list:
        if month is None:
            month = datetime.now().strftime("%Y-%m")
        result = []
        for uid, data in self.data.get("beer", {}).items():
            amount = data.get("month", {}).get(month, 0)
            if amount > 0:
                result.append({"user_id": int(uid), "amount": amount})
        return sorted(result, key=lambda x: x["amount"], reverse=True)

    def reset_beer(self):
        self.data["beer"] = {}
        self._save()

    # Сетки (для совместимости)
    def add_network(self, name: str, peer_id: int):
        self.data["networks"].setdefault(name, [])
        if peer_id not in self.data["networks"][name]:
            self.data["networks"][name].append(peer_id)
            self._save()
            return True
        return False

    def delete_network(self, name: str):
        if name in self.data["networks"]:
            del self.data["networks"][name]
            self._save()
            return True
        return False

    def get_all_networks(self):
        return self.data["networks"]

    def find_network_by_chat(self, peer_id: int):
        for name, chats in self.data["networks"].items():
            if peer_id in chats:
                return name, chats
        return None, None

    def set_chat_type(self, peer_id: int, chat_type: str):
        self.data["chat_types"][str(peer_id)] = chat_type
        self._save()

    def get_chat_type(self, peer_id: int) -> str:
        return self.data["chat_types"].get(str(peer_id), "chat")

    def get_all_chat_peer_ids(self) -> list:
        peer_ids = set()
        for uid, chats in self.data["messages"].items():
            for pid in chats.keys():
                peer_ids.add(int(pid))
        return list(peer_ids)

    # Баны (для совместимости)
    def add_ban(self, user_id: int, peer_id: int, reason: str, term: str, by: int, by_name: str, is_gban: bool = False):
        uid = str(user_id)
        self.data["bans"].setdefault(uid, []).append({
            "peer_id": peer_id, "reason": reason, "term": term,
            "by": by, "by_name": by_name,
            "date": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "active": True, "gban": is_gban
        })
        self._save()

    def get_bans_in_chat(self, user_id: int, peer_id: int):
        return [b for b in self.data["bans"].get(str(user_id), []) if b.get("active") and b["peer_id"] == peer_id]

    def count_banned_chats(self, user_id: int) -> int:
        peers = set(b["peer_id"] for b in self.data["bans"].get(str(user_id), []) if b.get("active") and not b.get("gban"))
        return len(peers)

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

    def get_gban(self, user_id: int):
        g = self.data["gbans"].get(str(user_id))
        if g and g.get("active"):
            return g
        return None

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

    def get_bans(self, user_id: int):
        return [b for b in self.data["bans"].get(str(user_id), []) if b.get("active")]

    # Выговоры (для совместимости)
    def add_warning(self, user_id: int, reason: str, issued_by: int, issued_by_name: str):
        uid = str(user_id)
        self.data["warnings"].setdefault(uid, []).append({
            "reason": reason, "issued_by": issued_by,
            "issued_by_name": issued_by_name,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "active": True
        })
        self._save()
        return len([w for w in self.data["warnings"][uid] if w.get("active")])

    def get_warnings(self, user_id: int):
        return self.data["warnings"].get(str(user_id), [])

    def get_active_warnings(self, user_id: int):
        return [w for w in self.get_warnings(user_id) if w.get("active")]

    def clear_warnings(self, user_id: int):
        for w in self.data["warnings"].get(str(user_id), []):
            w["active"] = False
        self._save()


# ────────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ────────────────────────────────────────────────────────────
def fmt(amount) -> str:
    return f"{int(amount):,}".replace(",", " ")


def format_time(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}ч {m}мин"
    elif m > 0:
        return f"{m}мин {s}сек"
    return f"{s}сек"


def make_mention(user_id: int, name: str = None) -> str:
    if name:
        return f"[id{user_id}|{name}]"
    return f"[id{user_id}|{user_id}]"


def send_keyboard(vk, peer_id: int, message: str, buttons: list):
    keyboard = {"inline": True, "buttons": buttons}
    try:
        vk.messages.send(
            peer_id=peer_id,
            message=message,
            keyboard=json.dumps(keyboard, ensure_ascii=False),
            random_id=int(datetime.now().timestamp() * 1000)
        )
    except Exception as e:
        print(f"[WARN] keyboard send: {e}")


# ────────────────────────────────────────────────────────────
# ОБРАБОТЧИК КОМАНД
# ────────────────────────────────────────────────────────────
def handle_game_command(text, from_user_id, peer_id, storage, vk, get_user_name, reply_user_id=None):
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""
    
    mod = storage.get_moderator(from_user_id)
    is_sr = mod and mod.get("position") == "Специальный руководитель"
    is_owner = from_user_id == OWNER_ID
    is_moder = is_sr or is_owner or (mod and mod.get("position") == "Модератор")

    def parse_target(target_args):
        m = re.match(r"\[id(\d+)\|[^\]]+\]\s*", target_args)
        if m:
            return int(m.group(1)), target_args[m.end():]
        m = re.match(r"(?:https?://)?vk\.com/id(\d+)\s*", target_args)
        if m:
            return int(m.group(1)), target_args[m.end():]
        m = re.match(r"(\d+)\s*", target_args)
        if m:
            return int(m.group(1)), target_args[m.end():]
        return None, target_args

    def resolve(arg_str, reply_id):
        if reply_id and not arg_str:
            return reply_id, ""
        target, rest = parse_target(arg_str)
        if target is None and reply_id:
            return reply_id, arg_str
        return target, rest

    # ────────────────────────────────────────────────────────
    # КИК (только для СР и владельца)
    # ────────────────────────────────────────────────────────
    if cmd in ("/kick", "!kick", "/кик", "!кик"):
        if not is_sr and not is_owner:
            return "⛔ Нет прав."
        target_id, rest = resolve(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        reason = rest.strip() or "Без причины"
        try:
            vk.messages.removeChatUser(chat_id=peer_id - 2000000000, user_id=target_id)
        except Exception as e:
            return f"❌ Ошибка: {e}"
        by_label = storage.get_moderator(from_user_id)["nick"] if storage.get_moderator(from_user_id) else get_user_name(from_user_id)
        target_mod = storage.get_moderator(target_id)
        target_label = target_mod["nick"] if target_mod else get_user_name(target_id)
        storage.add_kick(target_id)
        return (f"👢 {make_mention(target_id, target_label)} кикнут\n"
                f"Причина: {reason}\nВыдал: {by_label}")

    # ────────────────────────────────────────────────────────
    # МОДЕРАТОР (назначение, только для СР и владельца)
    # ────────────────────────────────────────────────────────
    if cmd in ("/модер", "!модер", "/moder", "!moder"):
        if not is_sr and not is_owner:
            return "⛔ Нет прав."
        target_id, _ = resolve(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        existing = storage.get_moderator(target_id)
        vk_name = get_user_name(target_id)
        nick = existing["nick"] if existing else vk_name
        role = existing["role"] if existing else "Сотрудник"
        storage.set_moderator(target_id, nick, role, "Модератор")
        return f"✅ {make_mention(target_id, nick)} назначен модератором!"

    # ────────────────────────────────────────────────────────
    # СР (только для владельца)
    # ────────────────────────────────────────────────────────
    if cmd in ("/ср", "!ср"):
        if not is_owner:
            return "⛔ Только владелец."
        target_id, _ = resolve(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        vk_name = get_user_name(target_id)
        storage.set_moderator(target_id, vk_name, "Владелец", "Специальный руководитель")
        return f"✅ {make_mention(target_id, vk_name)} назначен Специальным руководителем!"

    # ────────────────────────────────────────────────────────
    # УВОЛИТЬ (только для СР и владельца)
    # ────────────────────────────────────────────────────────
    if cmd in ("/уволить", "!уволить", "/delstaff", "!delstaff"):
        if not is_sr and not is_owner:
            return "⛔ Нет прав."
        target_id, _ = resolve(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        if storage.remove_moderator(target_id):
            return f"✅ {make_mention(target_id, get_user_name(target_id))} уволен."
        return "❌ Не найден."

    # ────────────────────────────────────────────────────────
    # ИГРОВЫЕ КОМАНДЫ
    # ────────────────────────────────────────────────────────

    if cmd in ("/баланс", "!баланс", "/balance", "!balance"):
        target_id, _ = resolve(args, reply_user_id)
        if not target_id:
            target_id = from_user_id
        eco = storage.get_eco(target_id)
        mod = storage.get_moderator(target_id)
        name = mod["nick"] if mod else get_user_name(target_id)
        if target_id != from_user_id and eco.get("hide_balance") and eco.get("hide_balance_active"):
            return f"💰 {make_mention(target_id, name)}: баланс скрыт 🙈"
        vip_str = " 👑 VIP" if eco.get("vip") else ""
        dep = eco.get("deposit")
        lines = [f"💰 Баланс {make_mention(target_id, name)}{vip_str}"]
        lines.append(f"На руках: {fmt(eco['balance'])} {CURRENCY}")
        lines.append(f"В банке: {fmt(eco.get('bank', 0))} {CURRENCY}")
        lines.append(f"Всего: {fmt(eco['balance'] + eco.get('bank', 0))} {CURRENCY}")
        if dep:
            lines.append(f"🏦 Депозит: {fmt(dep['amount'])} {CURRENCY} (до {dep['until'][:10]})")
        return "\n".join(lines)

    if cmd in ("/приз", "!приз", "/prize", "!prize"):
        last = storage.get_prize_last(from_user_id)
        if last:
            last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
            diff = (datetime.now() - last_dt).total_seconds()
            if diff < PRIZE_COOLDOWN:
                return f"⏳ Следующий приз через {format_time(int(PRIZE_COOLDOWN - diff))}"
        storage.claim_prize(from_user_id, PRIZE_AMOUNT)
        mod = storage.get_moderator(from_user_id)
        name = mod["nick"] if mod else get_user_name(from_user_id)
        return (f"🎁 {make_mention(from_user_id, name)} получил приз!\n"
                f"+{fmt(PRIZE_AMOUNT)} {CURRENCY}\n"
                f"Баланс: {fmt(storage.get_balance(from_user_id))} {CURRENCY}")

    if cmd in ("/передать", "!передать", "/transfer", "!transfer"):
        target_id, rest = resolve(args, reply_user_id)
        if not target_id or not rest.strip().isdigit():
            return "❌ Формат: /передать [цель] [сумма]"
        amount = int(rest.strip())
        if amount <= 0 or target_id == from_user_id:
            return "❌ Некорректная операция."
        if not storage.transfer(from_user_id, target_id, amount):
            return f"❌ Недостаточно {CURRENCY}."
        mod = storage.get_moderator(target_id)
        name = mod["nick"] if mod else get_user_name(target_id)
        return f"✅ Передано {fmt(amount)} {CURRENCY} → {make_mention(target_id, name)}"

    if cmd in ("/положить", "!положить"):
        if not args.isdigit():
            return "❌ Формат: /положить [сумма]"
        if not storage.deposit_to_bank(from_user_id, int(args)):
            return "❌ Недостаточно средств."
        return (f"✅ Положено: {fmt(args)} {CURRENCY}\n"
                f"В банке: {fmt(storage.get_bank(from_user_id))} {CURRENCY}")

    if cmd in ("/снять", "!снять"):
        if not args.isdigit():
            return "❌ Формат: /снять [сумма]"
        if not storage.withdraw_from_bank(from_user_id, int(args)):
            return "❌ Недостаточно в банке."
        return (f"✅ Снято: {fmt(args)} {CURRENCY}\n"
                f"Баланс: {fmt(storage.get_balance(from_user_id))} {CURRENCY}")

    if cmd in ("/топ", "!топ", "/top", "!top"):
        top = storage.get_rich_top()
        if not top:
            return "Список пуст."
        lines = ["💰 Топ богачей:\n"]
        for i, entry in enumerate(top[:15], 1):
            uid = entry["user_id"]
            eco = storage.get_eco(uid)
            if eco.get("hide_balance") and eco.get("hide_balance_active") and uid != from_user_id:
                name = get_user_name(uid)
                lines.append(f"{i}. {make_mention(uid, name)} — скрыт 🙈")
                continue
            mod = storage.get_moderator(uid)
            name = mod["nick"] if mod else get_user_name(uid)
            vip = " 👑" if eco.get("vip") else ""
            lines.append(f"{i}. {make_mention(uid, name)}{vip} — {fmt(entry['total'])} {CURRENCY}")
        return "\n".join(lines)

    if cmd in ("/buyvip", "!buyvip"):
        if storage.is_vip(from_user_id):
            return "✅ У тебя уже есть VIP 👑"
        if not storage.buy_vip(from_user_id, VIP_PRICE):
            return f"❌ Нужно {fmt(VIP_PRICE)} {CURRENCY}."
        return f"✅ VIP 👑 куплен! Потрачено: {fmt(VIP_PRICE)} {CURRENCY}"

    if cmd in ("/buyhidebalance", "!buyhidebalance"):
        if storage.has_hide_balance(from_user_id):
            return "✅ У тебя уже есть скрытый баланс."
        if not storage.buy_hide_balance(from_user_id, HIDE_BALANCE_PRICE):
            return f"❌ Нужно {fmt(HIDE_BALANCE_PRICE)} {CURRENCY}."
        return "✅ Скрытый баланс куплен! Используй /hidebalance."

    if cmd in ("/hidebalance", "!hidebalance"):
        if not storage.has_hide_balance(from_user_id):
            return f"❌ Сначала купи через /buyhidebalance за {fmt(HIDE_BALANCE_PRICE)} {CURRENCY}"
        state = storage.toggle_hide_balance(from_user_id)
        return f"✅ Скрытый баланс: {'включён 🙈' if state else 'выключен 👁'}"

    if cmd in ("/благо", "!благо"):
        if not args.isdigit() or int(args) <= 0:
            return "❌ Формат: /благо [сумма]"
        if not storage.donate_charity(from_user_id, int(args)):
            return "❌ Недостаточно средств."
        total = storage.get_eco(from_user_id)["charity_total"]
        mod = storage.get_moderator(from_user_id)
        name = mod["nick"] if mod else get_user_name(from_user_id)
        return (f"❤️ {make_mention(from_user_id, name)} пожертвовал {fmt(args)} {CURRENCY}!\n"
                f"Всего пожертвовано: {fmt(total)} {CURRENCY}")

    if cmd in ("/топблаго", "!топблаго"):
        top = storage.get_charity_top()
        if not top:
            return "Никто ещё не жертвовал."
        lines = ["❤️ Топ благотворителей:\n"]
        for i, entry in enumerate(top[:10], 1):
            uid = entry["user_id"]
            mod = storage.get_moderator(uid)
            name = mod["nick"] if mod else get_user_name(uid)
            lines.append(f"{i}. {make_mention(uid, name)} — {fmt(entry['amount'])} {CURRENCY}")
        return "\n".join(lines)

    if cmd in ("/открытьдепозит", "!открытьдепозит"):
        if not storage.is_vip(from_user_id):
            return f"❌ Депозит только для VIP 👑"
        if storage.get_deposit(from_user_id):
            return "❌ У тебя уже открыт депозит."
        if not args.isdigit():
            return "❌ Формат: /открытьдепозит [сумма]"
        if not storage.open_deposit(from_user_id, int(args), DEPOSIT_RATE, DEPOSIT_DAYS):
            return "❌ Недостаточно средств."
        earned = int(int(args) * DEPOSIT_RATE)
        until = (datetime.now() + timedelta(days=DEPOSIT_DAYS)).strftime("%d.%m.%Y")
        return (f"🏦 Депозит открыт!\nСумма: {fmt(args)} {CURRENCY}\n"
                f"Доход: +{fmt(earned)} {CURRENCY} (3%)\nЗакрыть: {until}")

    if cmd in ("/закрытьдепозит", "!закрытьдепозит"):
        result = storage.close_deposit(from_user_id)
        if not result:
            return "❌ Нет открытого депозита."
        if result["early"]:
            return (f"⚠️ Депозит закрыт досрочно!\n"
                    f"Возвращено: {fmt(result['amount'])} {CURRENCY}\nПроценты не начислены.")
        return (f"✅ Депозит закрыт!\nСумма: {fmt(result['amount'])} {CURRENCY}\n"
                f"Проценты: +{fmt(result['earned'])} {CURRENCY}\n"
                f"Итого: {fmt(result['amount'] + result['earned'])} {CURRENCY}")

    if cmd in ("/купитьбиз", "!купитьбиз"):
        biz_list = "\n".join(
            f"• {n}: {fmt(i['price'])} {CURRENCY} | {fmt(i['income'])} {CURRENCY}/сут"
            for n, i in BUSINESS.items())
        if not args.strip():
            return f"🏭 Бизнесы:\n{biz_list}\n\nФормат: /купитьбиз [название]"
        biz_type = args.strip().lower()
        if biz_type not in BUSINESS:
            return f"❌ Не найден.\n{biz_list}"
        biz_info = BUSINESS[biz_type]
        if not storage.buy_business(from_user_id, biz_type, biz_info["price"]):
            return f"❌ Нужно {fmt(biz_info['price'])} {CURRENCY}"
        return f"✅ Куплен {biz_type}!\nДоход: {fmt(biz_info['income'])} {CURRENCY}/сут"

    if cmd in ("/бизнес", "!бизнес"):
        bizs = storage.get_businesses(from_user_id)
        if not bizs:
            return "Нет бизнесов. Купи: /купитьбиз"
        lines = ["🏭 Мои бизнесы:"]
        for i, biz in enumerate(bizs):
            info = BUSINESS.get(biz["type"], {})
            prod_days = biz["products"] / info.get("products_per_day", 100) if biz["products"] > 0 else 0
            lines.append(f"{i+1}. {biz['type'].capitalize()}\n"
                         f"   Продукты: {biz['products']} (~{prod_days:.1f} дн.)\n"
                         f"   Накоплено: {fmt(biz.get('balance', 0))} {CURRENCY}")
        return "\n".join(lines)

    if cmd in ("/ппрод", "!ппрод"):
        m = re.match(r"(\d+)\s+(\d+)", args)
        if not m:
            return "❌ Формат: /ппрод [индекс] [кол-во]"
        biz_index = int(m.group(1)) - 1
        products = int(m.group(2))
        bizs = storage.get_businesses(from_user_id)
        if biz_index >= len(bizs):
            return "❌ Бизнес не найден."
        biz_info = BUSINESS.get(bizs[biz_index]["type"])
        cost = products * biz_info["product_price"]
        if not storage.add_products(from_user_id, biz_index, products, cost):
            return f"❌ Нужно {fmt(cost)} {CURRENCY}"
        return f"✅ Куплено {products} продуктов за {fmt(cost)} {CURRENCY}"

    if cmd in ("/снятьбиз", "!снятьбиз"):
        income = storage.collect_business(from_user_id)
        if income == 0:
            return "💰 Нечего снимать."
        return (f"✅ Снято: {fmt(income)} {CURRENCY}\n"
                f"Баланс: {fmt(storage.get_balance(from_user_id))} {CURRENCY}")

    if cmd in ("/топбиз", "!топбиз"):
        result = []
        for uid, eco in storage.data.get("economy", {}).items():
            count = len(eco.get("businesses", []))
            if count > 0:
                result.append({"user_id": int(uid), "count": count})
        result.sort(key=lambda x: x["count"], reverse=True)
        if not result:
            return "Никто не купил бизнес."
        lines = ["🏭 Топ бизнесменов:"]
        for i, entry in enumerate(result[:10], 1):
            uid = entry["user_id"]
            mod = storage.get_moderator(uid)
            name = mod["nick"] if mod else get_user_name(uid)
            lines.append(f"{i}. {make_mention(uid, name)} — {entry['count']} бизнесов")
        return "\n".join(lines)

    if cmd in ("/sellbiz", "!sellbiz"):
        bizs = storage.get_businesses(from_user_id)
        if not bizs:
            return "❌ Нет бизнесов."
        total = storage.sell_businesses(from_user_id)
        return (f"✅ Продано государству за {fmt(total)} {CURRENCY} (50%)\n"
                f"Баланс: {fmt(storage.get_balance(from_user_id))} {CURRENCY}")

    if cmd in ("/рулетка", "!рулетка"):
        if not args.isdigit():
            return f"❌ Формат: /рулетка [ставка]\nМин.: {fmt(ROULETTE_MIN)} {CURRENCY}"
        result = storage.roulette(from_user_id, int(args))
        if not result["ok"]:
            return f"❌ Недостаточно средств или ставка меньше {fmt(ROULETTE_MIN)} {CURRENCY}"
        mod = storage.get_moderator(from_user_id)
        name = mod["nick"] if mod else get_user_name(from_user_id)
        bal = storage.get_balance(from_user_id)
        if result["result"] == "джекпот":
            return (f"🎰 ДЖЕКПОТ! {make_mention(from_user_id, name)}\n"
                    f"Ставка: {fmt(result['bet'])} | Выигрыш: +{fmt(result['win'])} (x5) 🎉\n"
                    f"Баланс: {fmt(bal)} {CURRENCY}")
        elif result["result"] == "победа":
            return (f"🎰 Победа! {make_mention(from_user_id, name)}\n"
                    f"Ставка: {fmt(result['bet'])} | Выигрыш: +{fmt(result['win'])} (x2)\n"
                    f"Баланс: {fmt(bal)} {CURRENCY}")
        else:
            return (f"🎰 Не повезло... {make_mention(from_user_id, name)}\n"
                    f"Ставка: {fmt(result['bet'])} | Потеряно: -{fmt(result['bet'])}\n"
                    f"Баланс: {fmt(bal)} {CURRENCY}")

    if cmd in ("/дуэль", "!дуэль", "/duel", "!duel"):
        if not args.isdigit() or int(args) <= 0:
            return "❌ Формат: /дуэль [сумма]"
        amount = int(args)
        if storage.get_balance(from_user_id) < amount:
            return f"❌ Недостаточно средств."
        duel_id = f"{from_user_id}_{int(datetime.now().timestamp())}"
        storage.create_duel(duel_id, from_user_id, amount, peer_id)
        storage.add_balance(from_user_id, -amount)
        mod = storage.get_moderator(from_user_id)
        name = mod["nick"] if mod else get_user_name(from_user_id)
        send_keyboard(vk, peer_id,
            f"⚔️ {make_mention(from_user_id, name)} создал дуэль на {fmt(amount)} {CURRENCY}!\n"
            f"Нажми кнопку чтобы вступить.",
            [[{"action": {"type": "callback", "label": "⚔️ Вступить в дуэль",
                          "payload": f'{{"cmd":"duel_join","duel_id":"{duel_id}"}}'}, "color": "positive"}]])
        return None

    if cmd in ("/промо", "!промо", "/promo", "!promo"):
        if not args.strip():
            return "❌ Формат: /промо [код]"
        result = storage.activate_promo(from_user_id, args.strip().lower())
        if not result["ok"]:
            reasons = {"not_found": "Промокод не найден.",
                       "already_used": "Уже активирован.", "expired": "Промокод истёк."}
            return f"❌ {reasons.get(result['reason'], 'Ошибка.')}"
        return (f"✅ Промокод активирован!\n"
                f"+{fmt(result['amount'])} {CURRENCY}\n"
                f"Баланс: {fmt(storage.get_balance(from_user_id))} {CURRENCY}")

    if cmd in ("/addpromo", "!addpromo"):
        if not storage.is_vip(from_user_id) and not is_owner:
            return "❌ Только для VIP 👑"
        m = re.match(r"(\S+)\s+(\d+)(?:\s+(\d+))?", args)
        if not m:
            return "❌ Формат: /addpromo [код] [сумма] [активации]"
        code, amount, uses = m.group(1).lower(), int(m.group(2)), int(m.group(3) or PROMO_MAX_USES)
        if not is_owner:
            if amount > PROMO_MAX_AMOUNT:
                return f"❌ Макс. сумма VIP: {PROMO_MAX_AMOUNT} {CURRENCY}"
            if uses > PROMO_MAX_USES:
                return f"❌ Макс. активаций VIP: {PROMO_MAX_USES}"
            if storage.get_balance(from_user_id) < amount * uses:
                return f"❌ Нужно {fmt(amount * uses)} {CURRENCY}"
            storage.add_balance(from_user_id, -(amount * uses))
        if not storage.create_promo(code, amount, uses, from_user_id):
            return "❌ Промокод уже существует."
        return f"✅ Промокод {code} создан!\nСумма: {fmt(amount)} | Активаций: {uses}"

    if cmd in ("/топпромо", "!топпромо", "/promotop", "!promotop"):
        if not is_sr and not is_owner:
            return "⛔ Нет прав."
        promos = storage.data.get("promos", {})
        if not promos:
            return "Промокодов нет."
        lines = ["📋 Все промокоды:"]
        for code, p in promos.items():
            mod = storage.get_moderator(p["creator"])
            creator = mod["nick"] if mod else str(p["creator"])
            lines.append(f"• {code}: {fmt(p['amount'])} {CURRENCY} | {p['uses']}/{p['max_uses']} | создал: {creator}")
        return "\n".join(lines)

    if cmd in ("/пиво", "!пиво", "/beer", "!beer"):
        last = storage.get_beer_last_time(from_user_id)
        if last:
            last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M")
            diff = datetime.now() - last_dt
            if diff.total_seconds() < 3600:
                remaining = 3600 - int(diff.total_seconds())
                return f"🍺 Следующая попытка через {format_time(remaining)}"
        amount = round(random.uniform(0.1, 3.0), 1)
        storage.add_beer(from_user_id, amount)
        beer_data = storage.get_beer(from_user_id)
        month = datetime.now().strftime("%Y-%m")
        month_amount = beer_data["month"].get(month, 0)
        mod = storage.get_moderator(from_user_id)
        name = mod["nick"] if mod else get_user_name(from_user_id)
        return (f"🍺 {make_mention(from_user_id, name)} выпил {amount} литра пива!\n\n"
                f"Выпито за месяц — {month_amount} л. 🍺\nСледующая попытка через час.")

    if cmd in ("/пивозавры", "!пивозавры", "/beertop", "!beertop"):
        month = datetime.now().strftime("%Y-%m")
        month_num = month.split("-")[1]
        month_name = MONTH_NAMES.get(month_num, month)
        top = storage.get_beer_top(month)
        if not top:
            return "🍺 Никто ещё не пил пиво в этом месяце!"
        lines = [f"🍺 Топ пивозавров за {month_name} {datetime.now().year}:\n"]
        for i, entry in enumerate(top[:15], 1):
            uid = entry["user_id"]
            mod = storage.get_moderator(uid)
            name = mod["nick"] if mod else get_user_name(uid)
            lines.append(f"{i}. {make_mention(uid, name)}  Выпито — {entry['amount']} литров.")
        return "\n".join(lines)

    if cmd in ("/обнулитьпиво", "!обнулитьпиво"):
        if not is_owner:
            return "⛔ Только владелец."
        storage.reset_beer()
        return "✅ Статистика пива обнулена."

    if cmd in ("/gamehelp", "!gamehelp"):
        return (
            "🎮 ИГРОВЫЕ КОМАНДЫ:\n\n"
            "💰 /баланс — твой баланс\n"
            "🎁 /приз — получить 25 монет (раз в час)\n"
            "💸 /передать @id [сумма] — передать монеты\n"
            "🏦 /положить [сумма] | /снять [сумма]\n"
            "👑 /buyvip — купить VIP за 1000 монет\n"
            "🏦 /открытьдепозит [сумма] | /закрытьдепозит (VIP)\n"
            "🏭 /купитьбиз [завод] | /бизнес | /ппрод | /снятьбиз\n"
            "🎲 /рулетка [ставка] | /дуэль [сумма]\n"
            "📊 /топ | /топблаго | /топбиз\n"
            "❤️ /благо [сумма] — благотворительность\n"
            "🎫 /промо [код] | /addpromo [код] [сумма] (VIP)\n"
            "🙈 /buyhidebalance | /hidebalance\n"
            "🍺 /пиво | /пивозавры\n\n"
            "🔧 МОДЕРАЦИЯ:\n"
            "/кик @id [причина] | /модер @id | /уволить @id"
        )

    return None
