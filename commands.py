import re, os, random
from datetime import datetime, timedelta
from economy import (CURRENCY, VIP_PRICE, HIDE_BALANCE_PRICE, ROULETTE_MIN,
                     PRIZE_AMOUNT, PRIZE_COOLDOWN, DEPOSIT_DAYS, DEPOSIT_RATE,
                     BUSINESS, PROMO_MAX_AMOUNT, PROMO_MAX_USES, fmt, format_time)

OWNER_ID = int(os.getenv("OWNER_ID", "0"))

HIERARCHY = {
    "Специальный руководитель": 110,
    "Заместитель специального руководителя": 100,
    "Руководитель сообщества": 90,
    "Руководитель модерации": 80,
    "Заместитель руководителя модерации": 70,
    "Главный модератор": 60,
    "Заместитель главного модератора": 50,
    "Куратор модерации": 40,
    "Старший администратор": 30,
    "Модератор": 20,
    "Младший модератор": 10,
}

GSTAFF_POSITIONS = [
    "Специальный руководитель",
    "Заместитель специального руководителя",
    "Руководитель сообщества",
]

MSTAFF_POSITIONS = [
    "Руководитель модерации",
    "Заместитель руководителя модерации",
    "Главный модератор",
    "Заместитель главного модератора",
    "Куратор модерации",
]

STAFF_POSITIONS = [
    "Руководитель модерации",
    "Заместитель руководителя модерации",
    "Главный модератор",
    "Заместитель главного модератора",
    "Куратор модерации",
    "Старший администратор",
    "Модератор",
    "Младший модератор",
]

MONTH_NAMES = {
    "01": "January", "02": "February", "03": "March",
    "04": "April", "05": "May", "06": "June",
    "07": "July", "08": "August", "09": "September",
    "10": "October", "11": "November", "12": "December"
}


def make_mention(user_id: int, name: str = None) -> str:
    if name:
        return f"[id{user_id}|{name}]"
    return f"[id{user_id}|{user_id}]"


def parse_target(args: str):
    m = re.match(r"\[id(\d+)\|[^\]]+\]\s*", args)
    if m:
        return int(m.group(1)), args[m.end():]
    m = re.match(r"(?:https?://)?vk\.com/id(\d+)\s*", args)
    if m:
        return int(m.group(1)), args[m.end():]
    m = re.match(r"(\d+)\s*", args)
    if m:
        return int(m.group(1)), args[m.end():]
    return None, args


def resolve_target(args: str, reply_user_id: int = None):
    if reply_user_id and not args:
        return reply_user_id, ""
    target_id, rest = parse_target(args)
    if target_id is None and reply_user_id:
        return reply_user_id, args
    return target_id, rest


def get_priority(user_id: int, storage, owner_id: int) -> int:
    if user_id == owner_id:
        return 999
    mod = storage.get_moderator(user_id)
    if not mod:
        return 0
    return HIERARCHY.get(mod.get("position", ""), 0)


def can_assign(from_user_id: int, target_position: str, storage, owner_id: int) -> bool:
    from_priority = get_priority(from_user_id, storage, owner_id)
    target_priority = HIERARCHY.get(target_position, 0)
    return from_priority > target_priority and target_priority > 0


def parse_duration(text: str):
    m = re.match(
        r"^(\d+)\s*(мин|минут|минуты|м|ч|час|часов|д|день|дней|дн)\s*",
        text.strip(), re.IGNORECASE
    )
    if not m:
        return None, None, text
    amount = int(m.group(1))
    unit = m.group(2).lower()
    rest = text[m.end():].strip()
    if unit in ("мин", "минут", "минуты", "м"):
        minutes = amount
        label = f"{amount} мин."
    elif unit in ("ч", "час", "часов"):
        minutes = amount * 60
        label = f"{amount} ч."
    elif unit in ("д", "день", "дней", "дн"):
        minutes = amount * 60 * 24
        label = f"{amount} дн."
    else:
        return None, None, text
    return minutes, label, rest


def send_keyboard(vk, peer_id: int, message: str, buttons: list):
    """Отправляет сообщение с inline-кнопками."""
    import json
    keyboard = {
        "inline": True,
        "buttons": buttons
    }
    try:
        vk.messages.send(
            peer_id=peer_id,
            message=message,
            keyboard=json.dumps(keyboard, ensure_ascii=False),
            random_id=int(datetime.now().timestamp() * 1000)
        )
    except Exception as e:
        print(f"[WARN] keyboard send: {e}")


def handle_command(text, from_user_id, peer_id, storage, vk, get_user_name,
                   stats_chat_id, reply_user_id=None):
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""
    is_moder = storage.get_moderator(from_user_id) is not None
    is_owner = from_user_id == OWNER_ID
    is_vip = storage.is_vip(from_user_id)

    def no_access():
        return "⛔ Нет прав."

    def set_user_position(user_id: int, position: str):
        existing = storage.get_moderator(user_id)
        vk_name = get_user_name(user_id)
        nick = existing["nick"] if existing else vk_name
        role = existing["role"] if existing else "Сотрудник"
        storage.set_moderator(user_id, nick, role, position)
        return f"✅ {make_mention(user_id, nick)} назначен: {position}"

    # ══════════════════════════════════════
    #   ЭКОНОМИКА
    # ══════════════════════════════════════

    # /баланс
    if cmd in ("/баланс", "!баланс", "/balance", "!balance"):
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            target_id = from_user_id

        eco = storage.get_eco(target_id)
        mod = storage.get_moderator(target_id)
        name = mod["nick"] if mod else get_user_name(target_id)

        # Скрытый баланс
        if target_id != from_user_id and eco.get("hide_balance") and eco.get("hide_balance_active"):
            return f"💰 {make_mention(target_id, name)}: баланс скрыт 🙈"

        vip_str = " 👑 VIP" if eco.get("vip") else ""
        dep = eco.get("deposit")
        dep_str = f"\n🏦 Депозит: {fmt(dep['amount'])} {CURRENCY} (до {dep['until'][:10]})" if dep else ""

        lines = [f"💰 Баланс {make_mention(target_id, name)}{vip_str}"]
        lines.append(f"На руках: {fmt(eco['balance'])} {CURRENCY}")
        lines.append(f"В банке: {fmt(eco['bank'])} {CURRENCY}")
        lines.append(f"Всего: {fmt(eco['balance'] + eco['bank'])} {CURRENCY}")
        if dep_str:
            lines.append(dep_str)
        return "\n".join(lines)

    # /приз
    if cmd in ("/приз", "!приз", "/prize", "!prize"):
        last = storage.get_prize_last(from_user_id)
        if last:
            last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
            diff = (datetime.now() - last_dt).total_seconds()
            if diff < PRIZE_COOLDOWN:
                remaining = PRIZE_COOLDOWN - int(diff)
                return f"⏳ Следующий приз через {format_time(remaining)}"
        storage.claim_prize(from_user_id, PRIZE_AMOUNT)
        mod = storage.get_moderator(from_user_id)
        name = mod["nick"] if mod else get_user_name(from_user_id)
        return (f"🎁 {make_mention(from_user_id, name)} получил ежечасный приз!\n"
                f"+{fmt(PRIZE_AMOUNT)} {CURRENCY}\n"
                f"Баланс: {fmt(storage.get_balance(from_user_id))} {CURRENCY}")

    # /передать
    if cmd in ("/передать", "!передать", "/transfer", "!transfer"):
        target_id, rest = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        if not rest.strip().isdigit():
            return "❌ Формат: /передать [цель] [сумма]"
        amount = int(rest.strip())
        if amount <= 0:
            return "❌ Сумма должна быть больше 0."
        if target_id == from_user_id:
            return "❌ Нельзя передать себе."
        if not storage.transfer(from_user_id, target_id, amount):
            return f"❌ Недостаточно {CURRENCY}. Баланс: {fmt(storage.get_balance(from_user_id))}"
        mod = storage.get_moderator(target_id)
        name = mod["nick"] if mod else get_user_name(target_id)
        return f"✅ Передано {fmt(amount)} {CURRENCY} → {make_mention(target_id, name)}"

    # /положить
    if cmd in ("/положить", "!положить"):
        if not args.isdigit():
            return "❌ Формат: /положить [сумма]"
        amount = int(args)
        if not storage.deposit_to_bank(from_user_id, amount):
            return f"❌ Недостаточно средств."
        return (f"✅ Положено в банк: {fmt(amount)} {CURRENCY}\n"
                f"Баланс: {fmt(storage.get_balance(from_user_id))} {CURRENCY}\n"
                f"В банке: {fmt(storage.get_bank(from_user_id))} {CURRENCY}")

    # /снять
    if cmd in ("/снять", "!снять"):
        if not args.isdigit():
            return "❌ Формат: /снять [сумма]"
        amount = int(args)
        if not storage.withdraw_from_bank(from_user_id, amount):
            return f"❌ Недостаточно в банке."
        return (f"✅ Снято из банка: {fmt(amount)} {CURRENCY}\n"
                f"Баланс: {fmt(storage.get_balance(from_user_id))} {CURRENCY}")

    # /топ
    if cmd in ("/топ", "!топ", "/top", "!top"):
        top = storage.get_rich_top()
        if not top:
            return "Список пуст."
        lines = [f"💰 Топ богачей:\n"]
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

    # /buyvip
    if cmd in ("/buyvip", "!buyvip", "/випка", "!випка"):
        if storage.is_vip(from_user_id):
            return "✅ У тебя уже есть VIP 👑"
        if not storage.buy_vip(from_user_id, VIP_PRICE):
            return f"❌ Нужно {fmt(VIP_PRICE)} {CURRENCY}. У тебя: {fmt(storage.get_balance(from_user_id))}"
        return f"✅ VIP 👑 куплен!\nПотрачено: {fmt(VIP_PRICE)} {CURRENCY}"

    # /buyhidebalance
    if cmd in ("/buyhidebalance", "!buyhidebalance"):
        if storage.has_hide_balance(from_user_id):
            return "✅ У тебя уже есть скрытый баланс."
        if not storage.buy_hide_balance(from_user_id, HIDE_BALANCE_PRICE):
            return f"❌ Нужно {fmt(HIDE_BALANCE_PRICE)} {CURRENCY}."
        return f"✅ Скрытый баланс куплен! Используй /hidebalance для включения/выключения."

    # /hidebalance
    if cmd in ("/hidebalance", "!hidebalance"):
        if not storage.has_hide_balance(from_user_id):
            return f"❌ Сначала купи через /buyhidebalance за {fmt(HIDE_BALANCE_PRICE)} {CURRENCY}"
        state = storage.toggle_hide_balance(from_user_id)
        return f"✅ Скрытый баланс: {'включён 🙈' if state else 'выключен 👁'}"

    # /благо
    if cmd in ("/благо", "!благо"):
        if not args.isdigit():
            return "❌ Формат: /благо [сумма]"
        amount = int(args)
        if amount <= 0:
            return "❌ Сумма должна быть больше 0."
        if not storage.donate_charity(from_user_id, amount):
            return f"❌ Недостаточно средств."
        mod = storage.get_moderator(from_user_id)
        name = mod["nick"] if mod else get_user_name(from_user_id)
        total = storage.get_eco(from_user_id)["charity_total"]
        return (f"❤️ {make_mention(from_user_id, name)} пожертвовал {fmt(amount)} {CURRENCY}!\n"
                f"Всего пожертвовано: {fmt(total)} {CURRENCY}")

    # /топблаго
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

    # /открытьдепозит
    if cmd in ("/открытьдепозит", "!открытьдепозит"):
        if not is_vip:
            return f"❌ Депозит только для VIP 👑 (/buyvip за {fmt(VIP_PRICE)} {CURRENCY})"
        if storage.get_deposit(from_user_id):
            return "❌ У тебя уже открыт депозит."
        if not args.isdigit():
            return "❌ Формат: /открытьдепозит [сумма]"
        amount = int(args)
        if not storage.open_deposit(from_user_id, amount, DEPOSIT_RATE, DEPOSIT_DAYS):
            return f"❌ Недостаточно средств или депозит уже открыт."
        earned = int(amount * DEPOSIT_RATE)
        until = (datetime.now() + timedelta(days=DEPOSIT_DAYS)).strftime("%d.%m.%Y")
        return (f"🏦 Депозит открыт!\nСумма: {fmt(amount)} {CURRENCY}\n"
                f"Доход: +{fmt(earned)} {CURRENCY} ({int(DEPOSIT_RATE*100)}%)\n"
                f"Закрыть: {until}")

    # /закрытьдепозит
    if cmd in ("/закрытьдепозит", "!закрытьдепозит"):
        result = storage.close_deposit(from_user_id)
        if not result:
            return "❌ У тебя нет открытого депозита."
        if result["early"]:
            return (f"⚠️ Депозит закрыт досрочно!\n"
                    f"Возвращено: {fmt(result['amount'])} {CURRENCY}\n"
                    f"Проценты не начислены.")
        return (f"✅ Депозит закрыт!\n"
                f"Сумма: {fmt(result['amount'])} {CURRENCY}\n"
                f"Проценты: +{fmt(result['earned'])} {CURRENCY}\n"
                f"Итого: {fmt(result['amount'] + result['earned'])} {CURRENCY}")

    # /рулетка
    if cmd in ("/рулетка", "!рулетка"):
        if not args.isdigit():
            return f"❌ Формат: /рулетка [ставка]\nМин. ставка: {fmt(ROULETTE_MIN)} {CURRENCY}"
        bet = int(args)
        result = storage.roulette(from_user_id, bet)
        if not result["ok"]:
            return (f"❌ Недостаточно средств или ставка меньше минимума ({fmt(ROULETTE_MIN)} {CURRENCY}).\n"
                    f"Баланс: {fmt(storage.get_balance(from_user_id))} {CURRENCY}")
        mod = storage.get_moderator(from_user_id)
        name = mod["nick"] if mod else get_user_name(from_user_id)
        if result["result"] == "джекпот":
            return (f"🎰 ДЖЕКПОТ! {make_mention(from_user_id, name)}\n"
                    f"Ставка: {fmt(bet)} {CURRENCY}\n"
                    f"Выигрыш: +{fmt(result['win'])} {CURRENCY} (x5) 🎉\n"
                    f"Баланс: {fmt(storage.get_balance(from_user_id))} {CURRENCY}")
        elif result["result"] == "победа":
            return (f"🎰 Победа! {make_mention(from_user_id, name)}\n"
                    f"Ставка: {fmt(bet)} {CURRENCY}\n"
                    f"Выигрыш: +{fmt(result['win'])} {CURRENCY} (x2)\n"
                    f"Баланс: {fmt(storage.get_balance(from_user_id))} {CURRENCY}")
        else:
            return (f"🎰 Не повезло... {make_mention(from_user_id, name)}\n"
                    f"Ставка: {fmt(bet)} {CURRENCY}\n"
                    f"Потеряно: -{fmt(bet)} {CURRENCY}\n"
                    f"Баланс: {fmt(storage.get_balance(from_user_id))} {CURRENCY}")

    # /promo
    if cmd in ("/promo", "!promo", "/промо", "!промо"):
        if not args.strip():
            return "❌ Формат: /promo [код]"
        code = args.strip().lower()
        result = storage.activate_promo(from_user_id, code)
        if not result["ok"]:
            reasons = {
                "not_found": "Промокод не найден.",
                "already_used": "Ты уже активировал этот промокод.",
                "expired": "Промокод больше не активен."
            }
            return f"❌ {reasons.get(result['reason'], 'Ошибка.')}"
        return (f"✅ Промокод активирован!\n"
                f"+{fmt(result['amount'])} {CURRENCY}\n"
                f"Баланс: {fmt(storage.get_balance(from_user_id))} {CURRENCY}")

    # /addpromo (только VIP)
    if cmd in ("/addpromo", "!addpromo"):
        if not is_vip and not is_owner:
            return f"❌ Только для VIP 👑"
        m = re.match(r"(\S+)\s+(\d+)(?:\s+(\d+))?", args)
        if not m:
            return "❌ Формат: /addpromo [код] [сумма] [активации]\nПример: /addpromo хз 10 5"
        code = m.group(1).lower()
        amount = int(m.group(2))
        uses = int(m.group(3)) if m.group(3) else PROMO_MAX_USES

        if not is_owner:
            if amount > PROMO_MAX_AMOUNT:
                return f"❌ Максимальная сумма для VIP: {PROMO_MAX_AMOUNT} {CURRENCY}"
            if uses > PROMO_MAX_USES:
                return f"❌ Максимум активаций для VIP: {PROMO_MAX_USES}"
            if storage.get_balance(from_user_id) < amount * uses:
                return f"❌ Нужно {fmt(amount * uses)} {CURRENCY} для создания промокода."
            storage.add_balance(from_user_id, -(amount * uses))

        if not storage.create_promo(code, amount, uses, from_user_id):
            return "❌ Промокод уже существует."
        return (f"✅ Промокод создан: {code}\n"
                f"Сумма: {fmt(amount)} {CURRENCY}\n"
                f"Активаций: {uses}")

    # /mypromo
    if cmd in ("/mypromo", "!mypromo"):
        promos = storage.get_user_promos(from_user_id)
        if not promos:
            return "У тебя нет активированных промокодов."
        lines = ["🎫 Мои промокоды:\n"]
        for p in promos:
            lines.append(f"• {p['code']} — +{fmt(p['amount'])} {CURRENCY}")
        return "\n".join(lines)

    # /promolist
    if cmd in ("/promolist", "!promolist"):
        if not is_owner:
            return no_access()
        promos = storage.data.get("promos", {})
        if not promos:
            return "Промокодов нет."
        lines = ["📋 Все промокоды:\n"]
        for code, p in promos.items():
            lines.append(f"• {code}: {fmt(p['amount'])} {CURRENCY} | {p['uses']}/{p['max_uses']} активаций")
        return "\n".join(lines)

    # /купитьбиз
    if cmd in ("/купитьбиз", "!купитьбиз"):
        biz_list = "\n".join(
            f"• {name}: {fmt(info['price'])} {CURRENCY} | доход {fmt(info['income'])} {CURRENCY}/сут"
            for name, info in BUSINESS.items()
        )
        if not args.strip():
            return f"🏭 Доступные бизнесы:\n{biz_list}\n\nФормат: /купитьбиз [название]"
        biz_type = args.strip().lower()
        if biz_type not in BUSINESS:
            return f"❌ Бизнес не найден.\n{biz_list}"
        biz_info = BUSINESS[biz_type]
        if not storage.buy_business(from_user_id, biz_type, biz_info["price"]):
            return f"❌ Недостаточно средств. Нужно: {fmt(biz_info['price'])} {CURRENCY}"
        return (f"✅ Куплен {biz_type}!\n"
                f"Доход: {fmt(biz_info['income'])} {CURRENCY}/сут\n"
                f"Нужны продукты: /ппрод [индекс] [кол-во]")

    # /бизнес
    if cmd in ("/бизнес", "!бизнес"):
        bizs = storage.get_businesses(from_user_id)
        if not bizs:
            return "У тебя нет бизнесов. Купи: /купитьбиз"
        lines = ["🏭 Мои бизнесы:\n"]
        for i, biz in enumerate(bizs):
            info = BUSINESS.get(biz["type"], {})
            prod_days = biz["products"] / info.get("products_per_day", 100) if biz["products"] > 0 else 0
            lines.append(
                f"{i+1}. {biz['type'].capitalize()}\n"
                f"   Продукты: {biz['products']} (хватит на {prod_days:.1f} дн.)\n"
                f"   Доход: {fmt(info.get('income', 0))} {CURRENCY}/сут\n"
                f"   Накоплено: {fmt(biz.get('balance', 0))} {CURRENCY}"
            )
        return "\n".join(lines)

    # /ппрод
    if cmd in ("/ппрод", "!ппрод"):
        m = re.match(r"(\d+)\s+(\d+)", args)
        if not m:
            return "❌ Формат: /ппрод [индекс бизнеса] [кол-во продуктов]\nПример: /ппрод 1 100"
        biz_index = int(m.group(1)) - 1
        products = int(m.group(2))
        biz_type_info = None
        bizs = storage.get_businesses(from_user_id)
        if biz_index < len(bizs):
            biz_type_info = BUSINESS.get(bizs[biz_index]["type"])
        if not biz_type_info:
            return "❌ Бизнес не найден."
        cost = products * biz_type_info["product_price"]
        if not storage.add_products(from_user_id, biz_index, products, cost):
            return f"❌ Недостаточно средств. Нужно: {fmt(cost)} {CURRENCY}"
        return (f"✅ Куплено {products} продуктов за {fmt(cost)} {CURRENCY}\n"
                f"Хватит на {products / biz_type_info['products_per_day']:.1f} дн.")

    # /снятьбиз
    if cmd in ("/снятьбиз", "!снятьбиз"):
        income = storage.collect_business(from_user_id)
        if income == 0:
            return "💰 Нечего снимать — продукты закончились или нет бизнесов."
        return (f"✅ Снято с бизнесов: {fmt(income)} {CURRENCY}\n"
                f"Баланс: {fmt(storage.get_balance(from_user_id))} {CURRENCY}")

    # /топбиз
    if cmd in ("/топбиз", "!топбиз"):
        all_eco = storage.data.get("economy", {})
        result = []
        for uid, eco in all_eco.items():
            biz_count = len(eco.get("businesses", []))
            if biz_count > 0:
                result.append({"user_id": int(uid), "count": biz_count})
        result.sort(key=lambda x: x["count"], reverse=True)
        if not result:
            return "Никто ещё не купил бизнес."
        lines = ["🏭 Топ бизнесменов:\n"]
        for i, entry in enumerate(result[:10], 1):
            uid = entry["user_id"]
            mod = storage.get_moderator(uid)
            name = mod["nick"] if mod else get_user_name(uid)
            lines.append(f"{i}. {make_mention(uid, name)} — {entry['count']} бизнесов")
        return "\n".join(lines)

    # /sellbiz
    if cmd in ("/sellbiz", "!sellbiz"):
        bizs = storage.get_businesses(from_user_id)
        if not bizs:
            return "❌ У тебя нет бизнесов."
        total = storage.sell_businesses(from_user_id)
        return (f"✅ Все бизнесы проданы государству за {fmt(total)} {CURRENCY} (50% стоимости)\n"
                f"Баланс: {fmt(storage.get_balance(from_user_id))} {CURRENCY}")

    # /sellmybiz
    if cmd in ("/sellmybiz", "!sellmybiz"):
        m = re.match(r"(\d+)\s+(.+)\s+(\d+)", args)
        if not m:
            return "❌ Формат: /sellmybiz [индекс] [@покупатель] [цена]"
        biz_index = int(m.group(1)) - 1
        target_args = m.group(2).strip()
        price = int(m.group(3))
        target_id, _ = parse_target(target_args)
        if not target_id:
            return "❌ Укажи покупателя."
        if not storage.sell_business_to_user(from_user_id, target_id, biz_index, price):
            return "❌ Ошибка. Проверь индекс бизнеса и баланс покупателя."
        mod = storage.get_moderator(target_id)
        name = mod["nick"] if mod else get_user_name(target_id)
        return f"✅ Бизнес продан {make_mention(target_id, name)} за {fmt(price)} {CURRENCY}"

    # /дуэль
    if cmd in ("/дуэль", "!дуэль", "/duel", "!duel"):
        if not args.isdigit():
            return "❌ Формат: /дуэль [сумма]"
        amount = int(args)
        if amount <= 0:
            return "❌ Сумма должна быть больше 0."
        if storage.get_balance(from_user_id) < amount:
            return f"❌ Недостаточно средств. Баланс: {fmt(storage.get_balance(from_user_id))} {CURRENCY}"

        duel_id = f"{from_user_id}_{int(datetime.now().timestamp())}"
        storage.create_duel(duel_id, from_user_id, amount, peer_id)
        storage.add_balance(from_user_id, -amount)

        mod = storage.get_moderator(from_user_id)
        name = mod["nick"] if mod else get_user_name(from_user_id)

        send_keyboard(vk, peer_id,
            f"⚔️ {make_mention(from_user_id, name)} создал дуэль на {fmt(amount)} {CURRENCY}!\n"
            f"Нажми кнопку чтобы вступить.",
            [[{
                "action": {
                    "type": "callback",
                    "label": f"⚔️ Вступить в дуэль",
                    "payload": f'{{"cmd":"duel_join","duel_id":"{duel_id}"}}'
                },
                "color": "positive"
            }]]
        )
        return None

    # /пнуть
    if cmd in ("/пнуть", "!пнуть", "/kick_fun", "!kick_fun"):
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        if target_id == from_user_id:
            return "❌ Нельзя пнуть себя!"
        storage.add_kick(target_id)
        kicks = storage.get_kicks(target_id)
        mod_from = storage.get_moderator(from_user_id)
        name_from = mod_from["nick"] if mod_from else get_user_name(from_user_id)
        mod_target = storage.get_moderator(target_id)
        name_target = mod_target["nick"] if mod_target else get_user_name(target_id)
        return (f"👟 {make_mention(from_user_id, name_from)} пнул {make_mention(target_id, name_target)}!\n"
                f"Всего пинков: {kicks}")

    # /give (только owner)
    if cmd in ("/give", "!give"):
        if not is_owner:
            return no_access()
        target_id, rest = resolve_target(args, reply_user_id)
        if not target_id or not rest.strip().isdigit():
            return "❌ Формат: /give [цель] [сумма]"
        amount = int(rest.strip())
        storage.add_balance(target_id, amount)
        mod = storage.get_moderator(target_id)
        name = mod["nick"] if mod else get_user_name(target_id)
        return f"✅ {make_mention(target_id, name)} выдано {fmt(amount)} {CURRENCY}"

    # /givebiz (только owner)
    if cmd in ("/givebiz", "!givebiz"):
        if not is_owner:
            return no_access()
        target_id, rest = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Формат: /givebiz [цель] [тип бизнеса]"
        biz_type = rest.strip().lower()
        if biz_type not in BUSINESS:
            return f"❌ Бизнес не найден. Доступные: {', '.join(BUSINESS.keys())}"
        eco = storage.get_eco(target_id)
        eco["businesses"].append({
            "type": biz_type, "bought": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "products": 0, "products_last": None, "balance": 0
        })
        storage._save()
        mod = storage.get_moderator(target_id)
        name = mod["nick"] if mod else get_user_name(target_id)
        return f"✅ {make_mention(target_id, name)} выдан бизнес: {biz_type}"

    # /gamehelp
    if cmd in ("/gamehelp", "!gamehelp"):
        return (
            "🎮 Игровые команды:\n\n"
            "💰 Баланс и банк:\n"
            "/баланс [цель] — посмотреть баланс\n"
            "/положить [сумма] — в банк\n"
            "/снять [сумма] — из банка\n"
            "/передать [цель] [сумма] — перевести\n\n"
            "🎁 Ежечасно:\n"
            "/приз — получить 25 монет (раз в час)\n\n"
            "💎 VIP (1000 монет):\n"
            "/buyvip — купить VIP\n"
            "/открытьдепозит [сумма] — депозит 3% на 10 дн.\n"
            "/закрытьдепозит — закрыть депозит\n"
            "/addpromo [код] [сумма] [активации] — создать промо\n\n"
            "🏭 Бизнес:\n"
            "/купитьбиз [тип] — купить бизнес\n"
            "/бизнес — статистика\n"
            "/ппрод [индекс] [кол-во] — пополнить продукты\n"
            "/снятьбиз — снять доход\n"
            "/топбиз — топ бизнесменов\n"
            "/sellbiz — продать государству (50%)\n"
            "/sellmybiz [индекс] [цель] [цена] — продать игроку\n\n"
            "🎲 Игры:\n"
            "/рулетка [ставка] — мин. 50 монет\n"
            "/дуэль [сумма] — дуэль с кнопкой\n\n"
            "📊 Прочее:\n"
            "/топ — богачи\n"
            "/топблаго — благотворители\n"
            "/благо [сумма] — пожертвовать\n"
            "/promo [код] — активировать промокод\n"
            "/mypromo — мои промокоды\n"
            "/buyhidebalance — скрытый баланс (1500)\n"
            "/hidebalance — вкл/выкл скрытый баланс\n"
            "/пнуть [цель] — пнуть пользователя\n"
        )

    # ══════════════════════════════════════
    #   ПИВО
    # ══════════════════════════════════════
    if cmd in ("/пиво", "!пиво", "/beer", "!beer"):
        last = storage.get_beer_last_time(from_user_id)
        if last:
            last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M")
            diff = datetime.now() - last_dt
            if diff.total_seconds() < 3600:
                remaining = 3600 - int(diff.total_seconds())
                mins = remaining // 60
                secs = remaining % 60
                return f"🍺 Ещё не время! Следующая попытка через {mins} мин. {secs} сек."
        amount = round(random.uniform(0.1, 3.0), 1)
        storage.add_beer(from_user_id, amount)
        beer_data = storage.get_beer(from_user_id)
        month = datetime.now().strftime("%Y-%m")
        month_amount = beer_data["month"].get(month, 0)
        mod = storage.get_moderator(from_user_id)
        name = mod["nick"] if mod else get_user_name(from_user_id)
        return (f"🍺 {make_mention(from_user_id, name)}, ты выпил {amount} литра пива!\n\n"
                f"Выпито за месяц — {month_amount} л. 🍺\n"
                f"Следующая попытка через час.")

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
            return no_access()
        storage.reset_beer()
        return "✅ Статистика пива обнулена."

    # ══════════════════════════════════════
    #   МУТ / РАЗМУТ
    # ══════════════════════════════════════
    if cmd in ("/мут", "!мут", "/mute", "!mute"):
        if not is_moder and not is_owner:
            return no_access()
        target_id, rest = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        minutes, label, reason = parse_duration(rest)
        if not minutes:
            return "❌ Формат: /мут [цель] [срок] [причина]"
        reason = reason.strip() or "Без причины"
        until = (datetime.now() + timedelta(minutes=minutes)).strftime("%d/%m/%Y %H:%M:%S")
        mod = storage.get_moderator(from_user_id)
        by_label = mod["nick"] if mod else get_user_name(from_user_id)
        target_mod = storage.get_moderator(target_id)
        target_label = target_mod["nick"] if target_mod else get_user_name(target_id)
        storage.add_mute(target_id, peer_id, until, reason, by_label)
        return (f"🔇 {make_mention(target_id, target_label)} замучен\n"
                f"Причина: {reason}\nМут до: {until}\nВыдал: {by_label}")

    if cmd in ("/размут", "!размут", "/unmute", "!unmute"):
        if not is_moder and not is_owner:
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        if storage.remove_mute(target_id, peer_id):
            target_mod = storage.get_moderator(target_id)
            name = target_mod["nick"] if target_mod else get_user_name(target_id)
            return f"✅ {make_mention(target_id, name)} размучен"
        return "❌ Активный мут не найден"

    # ══════════════════════════════════════
    #   SNICK / RNICK / DELSTAFF
    # ══════════════════════════════════════
    if cmd in ("/snick", "!snick"):
        if not is_moder and not is_owner:
            return no_access()
        target_id, rest = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        nick = rest.strip()
        if not nick:
            return "❌ Укажи никнейм."
        existing = storage.get_moderator(target_id)
        if not existing:
            return "❌ Пользователь не в системе."
        storage.set_moderator(target_id, nick, existing["role"], existing["position"])
        return f"✅ Ник изменён на: {nick}"

    if cmd in ("/rnick", "!rnick"):
        if not is_moder and not is_owner:
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        existing = storage.get_moderator(target_id)
        if not existing:
            return "❌ Пользователь не в системе."
        vk_name = get_user_name(target_id)
        storage.set_moderator(target_id, vk_name, existing["role"], existing["position"])
        return "✅ Ник сброшен"

    if cmd in ("/delstaff", "!delstaff"):
        if not is_owner:
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        if storage.remove_moderator(target_id):
            return "✅ Сотрудник удалён."
        return "❌ Не найден."

    # ══════════════════════════════════════
    #   НАЗНАЧЕНИЕ ДОЛЖНОСТЕЙ
    # ══════════════════════════════════════
    position_commands = {
        "/ср": "Специальный руководитель",
        "/зср": "Заместитель специального руководителя",
        "/рс": "Руководитель сообщества",
        "/рм": "Руководитель модерации",
        "/зрм": "Заместитель руководителя модерации",
        "/гм": "Главный модератор",
        "/згм": "Заместитель главного модератора",
        "/км": "Куратор модерации",
        "/са": "Старший администратор",
        "/мод": "Модератор",
        "/мм": "Младший модератор",
    }
    if cmd in position_commands:
        position = position_commands[cmd]
        if not can_assign(from_user_id, position, storage, OWNER_ID):
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        return set_user_position(target_id, position)

    # ══════════════════════════════════════
    #   БАН / АНБАН / КИК
    # ══════════════════════════════════════
    if cmd in ("/ban", "!ban"):
        if not is_moder and not is_owner:
            return no_access()
        target_id, rest = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        term = "Навсегда"
        reason = rest.strip()
        term_match = re.match(
            r"^(\d+\s*(?:дн|день|дней|д|h|ч|часов|час|мин|минут|w|нед|недель|месяц|мес)\.?)\s*",
            rest, re.IGNORECASE)
        if term_match:
            term = term_match.group(1).strip()
            reason = rest[term_match.end():].strip()
        if not reason:
            return "❌ Укажи причину бана."
        mod = storage.get_moderator(from_user_id)
        by_label = mod["nick"] if mod else get_user_name(from_user_id)
        try:
            vk.messages.removeChatUser(chat_id=peer_id - 2000000000, user_id=target_id)
        except Exception as e:
            print(f"[WARN] kick: {e}")
        storage.add_ban(target_id, peer_id, reason, term, from_user_id, by_label)
        target_mod = storage.get_moderator(target_id)
        target_label = target_mod["nick"] if target_mod else get_user_name(target_id)
        return (f"🔨 {make_mention(target_id, target_label)} заблокирован\n"
                f"Причина: {reason}\nСрок: {term}\nВыдал: {by_label}")

    if cmd in ("/unban", "!unban"):
        if not is_moder and not is_owner:
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        storage.unban(target_id, peer_id)
        return f"✅ {make_mention(target_id, get_user_name(target_id))} разбанен"

    if cmd in ("/kick", "!kick", "/кик", "!кик"):
        if not is_moder and not is_owner:
            return no_access()
        target_id, rest = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        reason = rest.strip() or "Без причины"
        try:
            vk.messages.removeChatUser(chat_id=peer_id - 2000000000, user_id=target_id)
        except Exception as e:
            return f"❌ Ошибка: {e}"
        mod = storage.get_moderator(from_user_id)
        by_label = mod["nick"] if mod else get_user_name(from_user_id)
        target_mod = storage.get_moderator(target_id)
        target_label = target_mod["nick"] if target_mod else get_user_name(target_id)
        return (f"👢 {make_mention(target_id, target_label)} кикнут\n"
                f"Причина: {reason}\nВыдал: {by_label}")

    if cmd in ("/gban", "!gban"):
        if not is_owner:
            return no_access()
        target_id, rest = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        reason = rest.strip()
        if not reason:
            return "❌ Укажи причину"
        by_name = get_user_name(from_user_id)
        all_peers = storage.get_all_chat_peer_ids()
        kicked = 0
        for pid in all_peers:
            if pid <= 2000000000:
                continue
            try:
                vk.messages.removeChatUser(chat_id=pid - 2000000000, user_id=target_id)
                storage.add_ban(target_id, pid, reason, "Глобальный бан",
                                from_user_id, by_name, is_gban=True)
                kicked += 1
            except Exception as e:
                print(f"[WARN] gban {pid}: {e}")
        storage.add_gban(target_id, reason, by_name)
        target_mod = storage.get_moderator(target_id)
        target_label = target_mod["nick"] if target_mod else get_user_name(target_id)
        return (f"🌐 Глобальный бан: {make_mention(target_id, target_label)}\n"
                f"Причина: {reason}\nКикнут из {kicked} бесед")

    if cmd in ("/ungban", "!ungban"):
        if not is_owner:
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        if storage.remove_gban(target_id):
            return "✅ Глобальный бан снят"
        return "❌ Бан не найден"

    if cmd in ("/checkban", "!checkban", "/чекбан", "!чекбан"):
        if not is_moder and not is_owner:
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            target_id = from_user_id
        target_name = get_user_name(target_id)
        target_mod = storage.get_moderator(target_id)
        target_label = target_mod["nick"] if target_mod else target_name
        gban = storage.get_gban(target_id)
        chat_bans = storage.get_bans_in_chat(target_id, peer_id)
        banned_chats_count = storage.count_banned_chats(target_id)
        all_bans = storage.get_bans(target_id)
        recent_bans = [b for b in all_bans if not b.get("gban")][-10:]
        lines = [f"Информация о блокировках {make_mention(target_id, target_label)}\n"]
        lines.append(f"Общая блокировка JORDANS: {'🔴 ' + gban['reason'] if gban else '✅ отсутствует'}")
        if gban:
            lines.append(f"Выдал: {gban['by_name']} | {gban['date']}")
        lines.append("")
        if chat_bans:
            b = chat_bans[-1]
            lines.append(f"Блокировка в беседе: 🔴 {b['reason']}")
            lines.append(f"Срок: {b['term']} | Выдал: {b['by_name']} | {b['date']}")
        else:
            lines.append("Блокировка в беседе: ✅ отсутствует")
        lines.append("")
        lines.append(f"Заблокирован в {banned_chats_count} беседах")
        if recent_bans:
            lines.append(f"\nПоследние блокировки ({len(recent_bans)}):\n")
            for i, b in enumerate(reversed(recent_bans), 1):
                issuer_mod = storage.get_moderator(b["by"])
                mod_info = f" | {issuer_mod['position']}" if issuer_mod else ""
                lines.append(f"{i}) {b['by_name']}{mod_info} | {b['reason']} | {b['term']} | {b['date']}")
        return "\n".join(lines)

    # ══════════════════════════════════════
    #   WARN
    # ══════════════════════════════════════
    if cmd in ("/warn", "!warn"):
        if not is_moder and not is_owner:
            return no_access()
        target_id, rest = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        reason = rest.strip()
        if not reason:
            return "❌ Укажи причину"
        issuer_name = get_user_name(from_user_id)
        count = storage.add_warning(target_id, reason, from_user_id, issuer_name)
        mod = storage.get_moderator(target_id)
        name = mod["nick"] if mod else get_user_name(target_id)
        return f"⚠️ Выговор {make_mention(target_id, name)}\nПричина: {reason}\nВыговоров: {count}"

    if cmd in ("/warns", "!warns"):
        if not is_moder and not is_owner:
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя"
        warns = storage.get_warnings(target_id)
        mod = storage.get_moderator(target_id)
        name = mod["nick"] if mod else get_user_name(target_id)
        active = [w for w in warns if w.get("active")]
        if not warns:
            return f"✅ У {make_mention(target_id, name)} нет выговоров"
        lines = [f"⚠️ Выговоры {make_mention(target_id, name)} (активных: {len(active)}):"]
        for w in warns[-5:]:
            status = "🔴" if w.get("active") else "⚫"
            lines.append(f"{status} {w['date']} — {w['reason']}")
        return "\n".join(lines)

    if cmd in ("/clearwarns", "!clearwarns"):
        if not is_moder and not is_owner:
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя"
        storage.clear_warnings(target_id)
        mod = storage.get_moderator(target_id)
        name = mod["nick"] if mod else get_user_name(target_id)
        return f"✅ Выговоры {make_mention(target_id, name)} сброшены"

    # ══════════════════════════════════════
    #   MSTATS
    # ══════════════════════════════════════
    if cmd in ("/mstats", "!mstats", "/мстатс", "!мстатс"):
        if not is_moder and not is_owner:
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            target_id = from_user_id
        net_name, net_chats = storage.find_network_by_chat(peer_id)
        peer_ids = net_chats if net_chats else None
        stats_net = storage.get_user_stats(target_id, peer_ids)
        mod = storage.get_moderator(target_id)
        active_warns = storage.get_active_warnings(target_id)
        all_warns = storage.get_warnings(target_id)
        gban = storage.get_gban(target_id)
        net_bans = []
        if net_chats:
            for pid in net_chats:
                net_bans += storage.get_bans_in_chat(target_id, pid)
        mute = storage.get_mute(target_id, peer_id)
        vk_name = get_user_name(target_id)
        lines = [f"📊 Статистика {make_mention(target_id, mod['nick'] if mod else vk_name)}\n"]
        lines.append(f"Роль: {mod['position'] if mod else '—'}")
        lines.append(f"Общая блокировка в чатах JORDANS: {'🔴 есть' if gban else 'Нет'}")
        lines.append(f"Общая блокировка в сетке беседы: {'🔴 есть' if net_bans else 'Нет'}")
        lines.append(f"Активные наказания: {len(active_warns)}/{len(all_warns)}")
        lines.append(f"Последнее наказание выдал: {all_warns[-1]['issued_by_name'] if all_warns else '—'}")
        lines.append(f"Nick_Name: {mod['nick'] if mod else vk_name}")
        scope = f"сетка «{net_name}»" if net_name else "все беседы"
        lines.append(f"Всего сообщений в {scope}: {stats_net['total']}")
        lines.append(f"Сообщений за сегодня в {scope}: {stats_net['today']}")
        lines.append(f"Последнее сообщение: {stats_net['last_time'] or '—'}")
        return "\n".join(lines)

    # ══════════════════════════════════════
    #   STATS
    # ══════════════════════════════════════
    if cmd in ("/stats", "!stats"):
        if not is_moder and not is_owner:
            return no_access()
        period_map = {"день": 1, "сутки": 1, "d": 1, "1": 1,
                      "неделя": 7, "w": 7, "7": 7, "месяц": 30, "m": 30, "30": 30}
        days = period_map.get(args.lower(), 7)
        period_name = {1: "сутки", 7: "неделю", 30: "месяц"}.get(days, f"{days} дн.")
        chat_stats = storage.get_chat_stats(peer_id, days)
        mods = storage.get_all_moderators()
        if not chat_stats:
            return "Статистика пуста"
        lines = [f"Активность за {period_name}:\n"]
        for i, s in enumerate(chat_stats[:15], 1):
            uid = s["user_id"]
            mod = mods.get(str(uid))
            name = mod["nick"] if mod else get_user_name(uid)
            lines.append(f"{i}. {name} — {s['period']} сообщ.")
        return "\n".join(lines)

    # ══════════════════════════════════════
    #   STAFF
    # ══════════════════════════════════════
    if cmd in ("/gstaff", "!gstaff", "/гстафф", "!гстафф"):
        caller_mod = storage.get_moderator(from_user_id)
        caller_pos = caller_mod.get("position", "") if caller_mod else ""
        if not is_owner and caller_pos not in GSTAFF_POSITIONS:
            return no_access()
        all_mods = storage.get_all_moderators()
        staff_by_pos = {pos: [] for pos in GSTAFF_POSITIONS}
        for uid, m in all_mods.items():
            pos = m.get("position", "")
            if pos in staff_by_pos:
                staff_by_pos[pos].append({"id": int(uid), "nick": m["nick"]})
        lines = ["👑 Руководство JORDANS\n"]
        for pos in GSTAFF_POSITIONS:
            people = staff_by_pos[pos]
            lines.append(f"{pos}:")
            lines.append(f"  {make_mention(people[0]['id'], people[0]['nick'])}" if people else "  Отсутствуют")
            lines.append("")
        return "\n".join(lines)

    if cmd in ("/mstaff", "!mstaff", "/мстафф", "!мстафф"):
        if not is_moder and not is_owner:
            return no_access()
        all_mods = storage.get_all_moderators()
        staff_by_pos = {pos: [] for pos in MSTAFF_POSITIONS}
        for uid, m in all_mods.items():
            pos = m.get("position", "")
            if pos in staff_by_pos:
                staff_by_pos[pos].append({"id": int(uid), "nick": m["nick"]})
        lines = ["🛡 Состав модерации\n"]
        for pos in MSTAFF_POSITIONS:
            people = staff_by_pos[pos]
            lines.append(f"{pos}:")
            if people:
                for p in people:
                    lines.append(f"  {make_mention(p['id'], p['nick'])}")
            else:
                lines.append("  Отсутствуют")
            lines.append("")
        return "\n".join(lines)

    if cmd in ("/staff", "!staff", "/стафф", "!стафф"):
        if not is_moder and not is_owner:
            return no_access()
        all_mods = storage.get_all_moderators()
        staff_by_pos = {pos: [] for pos in STAFF_POSITIONS}
        for uid, m in all_mods.items():
            pos = m.get("position", "")
            if pos in staff_by_pos:
                staff_by_pos[pos].append({"id": int(uid), "nick": m["nick"]})
        lines = ["👥 Состав беседы\n"]
        for pos in STAFF_POSITIONS:
            people = staff_by_pos[pos]
            lines.append(f"{pos}:")
            if people:
                for p in people:
                    lines.append(f"  {make_mention(p['id'], p['nick'])}")
            else:
                lines.append("  Отсутствуют")
            lines.append("")
        return "\n".join(lines)

    # ══════════════════════════════════════
    #   ПРОЧЕЕ
    # ══════════════════════════════════════
    if cmd in ("/id", "!id"):
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            target_id = from_user_id
        name = get_user_name(target_id)
        return f"🔎 {name}\nID: {target_id}\nСсылка: vk.com/id{target_id}"

    if cmd in ("/chatid", "!chatid"):
        net_name, _ = storage.find_network_by_chat(peer_id)
        chat_type = storage.get_chat_type(peer_id)
        net_str = f"Сетка: {net_name}" if net_name else "Сетка: не задана"
        return f"peer_id: {peer_id}\nТип: {chat_type}\n{net_str}"

    if cmd in ("/type", "!type"):
        if not is_moder and not is_owner:
            return no_access()
        if args.strip():
            chat_type = args.strip().lower()
            if chat_type not in ("moder", "chat"):
                return "❌ Допустимые типы: moder, chat"
            storage.set_chat_type(peer_id, chat_type)
            return f"✅ Тип беседы: {chat_type}"
        return f"Тип беседы: {storage.get_chat_type(peer_id)}"

    if cmd in ("/addnet", "!addnet"):
        if not is_owner:
            return no_access()
        m = re.match(r"(\S+)(?:\s+(\d+))?", args)
        if not m:
            return "❌ Формат: /addnet [название] [peer_id]"
        net_name = m.group(1)
        target_peer = int(m.group(2)) if m.group(2) else peer_id
        storage.add_network(net_name, target_peer)
        return f"✅ Беседа добавлена в сетку {net_name}"

    if cmd in ("/delnet", "!delnet"):
        if not is_owner:
            return no_access()
        m = re.match(r"(\S+)", args)
        if not m:
            return "❌ Формат: /delnet [название]"
        storage.delete_network(m.group(1))
        return "✅ Сетка удалена"

    if cmd in ("/nets", "!nets"):
        if not is_owner:
            return no_access()
        nets = storage.get_all_networks()
        if not nets:
            return "Сеток нет"
        lines = ["Сетки:"]
        for name, chats in nets.items():
            lines.append(f"• {name}: {', '.join(map(str, chats))}")
        return "\n".join(lines)

    if cmd in ("/help", "!help"):
        if not is_moder and not is_owner:
            return no_access()
        return (
            "📋 Команды модерации:\n\n"
            "🛡 Модерация:\n"
            "/ban /unban /kick /gban /ungban\n"
            "/мут /размут /warn /warns /clearwarns\n"
            "/checkban /mstats /stats\n\n"
            "👥 Стафф:\n"
            "/staff /mstaff /gstaff\n"
            "/snick /rnick /delstaff\n"
            "/ср /зср /рс /рм /зрм /гм /згм /км /са /мод /мм\n\n"
            "🎮 Игры: /gamehelp\n"
            "🍺 Пиво: /пиво /пивозавры\n"
        )

    return None
