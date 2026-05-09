import re, os, random
from datetime import datetime, timedelta

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


def handle_command(text, from_user_id, peer_id, storage, vk, get_user_name,
                   stats_chat_id, reply_user_id=None):
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""
    is_moder = storage.get_moderator(from_user_id) is not None
    is_owner = from_user_id == OWNER_ID
    from_priority = get_priority(from_user_id, storage, OWNER_ID)

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
    #   /пиво
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

        return (
            f"🍺 {make_mention(from_user_id, name)}, ты выпил {amount} литра пива!\n\n"
            f"Выпито за месяц — {month_amount} л. 🍺\n"
            f"Следующая попытка через час."
        )

    # ══════════════════════════════════════
    #   /пивозавры
    # ══════════════════════════════════════
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

    # ══════════════════════════════════════
    #   /обнулитьпиво
    # ══════════════════════════════════════
    if cmd in ("/обнулитьпиво", "!обнулитьпиво", "/resetbeer", "!resetbeer"):
        if not is_owner:
            return no_access()
        storage.reset_beer()
        return "✅ Статистика пива обнулена."

    # ══════════════════════════════════════
    #   /мут
    # ══════════════════════════════════════
    if cmd in ("/мут", "!мут", "/mute", "!mute"):
        if not is_moder and not is_owner:
            return no_access()
        target_id, rest = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        minutes, label, reason = parse_duration(rest)
        if not minutes:
            return "❌ Формат: /мут [цель] [срок] [причина]\nПример: /мут @ник 30 мин оффтоп"
        reason = reason.strip() or "Без причины"
        until = (datetime.now() + timedelta(minutes=minutes)).strftime("%d/%m/%Y %H:%M:%S")
        mod = storage.get_moderator(from_user_id)
        by_label = mod["nick"] if mod else get_user_name(from_user_id)
        target_mod = storage.get_moderator(target_id)
        target_label = target_mod["nick"] if target_mod else get_user_name(target_id)
        storage.add_mute(target_id, peer_id, until, reason, by_label)
        return (
            f"🔇 {make_mention(target_id, target_label)} замучен\n"
            f"Причина: {reason}\n"
            f"Мут выдан до: {until}\n"
            f"Выдал: {by_label}"
        )

    # ══════════════════════════════════════
    #   /размут
    # ══════════════════════════════════════
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
    #   /snick, /rnick, /delstaff
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
    #   Назначение должностей
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
    #   /ban, /unban, /kick
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
            rest, re.IGNORECASE
        )
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

    # ══════════════════════════════════════
    #   /gban, /ungban
    # ══════════════════════════════════════
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

    # ══════════════════════════════════════
    #   /checkban
    # ══════════════════════════════════════
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
    #   /warn, /warns, /clearwarns
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
    #   /mstats
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
        lines.append(f"Последнее сообщение отправлено в: {stats_net['last_time'] or '—'}")
        return "\n".join(lines)

    # ══════════════════════════════════════
    #   /stats
    # ══════════════════════════════════════
    if cmd in ("/stats", "!stats"):
        if not is_moder and not is_owner:
            return no_access()
        period_map = {
            "день": 1, "сутки": 1, "d": 1, "1": 1,
            "неделя": 7, "w": 7, "7": 7,
            "месяц": 30, "m": 30, "30": 30
        }
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
    #   /gstaff
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
            if people:
                for p in people:
                    lines.append(f"  {make_mention(p['id'], p['nick'])}")
            else:
                lines.append("  Отсутствуют")
            lines.append("")
        return "\n".join(lines)

    # ══════════════════════════════════════
    #   /mstaff
    # ══════════════════════════════════════
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

    # ══════════════════════════════════════
    #   /staff
    # ══════════════════════════════════════
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
    #   /id, /chatid, /type, /addnet, /delnet, /nets
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

    # ══════════════════════════════════════
    #   /help
    # ══════════════════════════════════════
    if cmd in ("/help", "!help"):
        if not is_moder and not is_owner:
            return no_access()
        return (
            "📋 Команды:\n\n"
            "🍺 Развлечения:\n"
            "/пиво — выпить пиво (раз в час)\n"
            "/пивозавры — топ пивоманов\n\n"
            "📊 Статистика:\n"
            "/stats [день|неделя|месяц]\n"
            "/mstats [цель]\n"
            "/staff | /mstaff | /gstaff\n\n"
            "🛡 Модерация:\n"
            "/ban [цель] [срок] [причина]\n"
            "/unban [цель]\n"
            "/kick [цель] [причина]\n"
            "/мут [цель] [срок] [причина]\n"
            "/размут [цель]\n"
            "/warn [цель] [причина]\n"
            "/warns [цель]\n"
            "/clearwarns [цель]\n"
            "/checkban [цель]\n\n"
            "⭐ Должности:\n"
            "/ср /зср /рс /рм /зрм\n"
            "/гм /згм /км /са /мод /мм\n"
            "/snick [цель] [ник]\n"
            "/rnick [цель]\n"
            "/delstaff [цель]\n\n"
            "🔧 Прочее:\n"
            "/id [цель]\n"
            "/chatid\n"
        )

    return None
