import re, os
from datetime import datetime

OWNER_ID = int(os.getenv("OWNER_ID", "0"))


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


def get_user_role_priority(position: str) -> int:
    """Возвращает приоритет должности (чем выше, тем больше прав)"""
    hierarchy = {
        "Специальный руководитель": 100,
        "Заместитель специального руководителя": 90,
        "Руководитель сообщества": 85,
        "Руководитель модерации": 80,
        "Заместитель руководителя модерации": 70,
        "Главный модератор": 60,
        "Заместитель главного модератора": 50,
        "Куратор модерации": 40,
    }
    return hierarchy.get(position, 0)


def can_assign(assigner_id: int, target_position: str, storage) -> bool:
    """Может ли assigner_id назначить должность target_position"""
    
    # Владелец может всё
    if assigner_id == OWNER_ID:
        return True
    
    assigner = storage.get_moderator(assigner_id)
    if not assigner:
        return False
    
    assigner_pos = assigner.get("position", "")
    assigner_priority = get_user_role_priority(assigner_pos)
    target_priority = get_user_role_priority(target_position)
    
    # Можно назначать только тех, кто ниже по иерархии
    return assigner_priority > target_priority and target_priority > 0


def handle_command(text, from_user_id, peer_id, storage, vk, get_user_name,
                   stats_chat_id, reply_user_id=None):
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""
    is_admin = storage.is_admin(from_user_id, OWNER_ID)
    is_moder = storage.get_moderator(from_user_id) is not None
    is_owner = from_user_id == OWNER_ID

    def no_access():
        return "⛔ Нет прав."

    # ══════════════════════════════════════
    #   Функция добавления/обновления сотрудника
    # ══════════════════════════════════════
    def set_user_position(user_id: int, position: str):
        existing = storage.get_moderator(user_id)
        vk_name = get_user_name(user_id)
        nick = existing["nick"] if existing else vk_name
        role = existing["role"] if existing else "Сотрудник"
        
        storage.set_moderator(user_id, nick, role, position)
        return f"✅ {make_mention(user_id, nick)} назначен на должность: {position}"

    # ══════════════════════════════════════
    #   /snick - установить ник
    # ══════════════════════════════════════
    if cmd in ("/snick", "!snick", "/сник", "!сник"):
        if not is_moder:
            return no_access()
        
        target_id, rest = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        
        nick = rest.strip()
        if not nick:
            return "❌ Укажи никнейм."
        
        existing = storage.get_moderator(target_id)
        if not existing:
            return "❌ Пользователь не найден в системе."
        
        storage.set_moderator(target_id, nick, existing["role"], existing["position"])
        return f"✅ Ник для {make_mention(target_id, get_user_name(target_id))} изменён на: {nick}"

    # ══════════════════════════════════════
    #   /rnick - снять ник
    # ══════════════════════════════════════
    if cmd in ("/rnick", "!rnick", "/рник", "!рник"):
        if not is_moder:
            return no_access()
        
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        
        existing = storage.get_moderator(target_id)
        if not existing:
            return "❌ Пользователь не найден в системе."
        
        vk_name = get_user_name(target_id)
        storage.set_moderator(target_id, vk_name, existing["role"], existing["position"])
        return f"✅ Ник для {make_mention(target_id, vk_name)} сброшен."

    # ══════════════════════════════════════
    #   /delstaff - удалить сотрудника
    # ══════════════════════════════════════
    if cmd in ("/delstaff", "!delstaff", "/удалить", "!удалить"):
        if not is_owner:
            return no_access()
        
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        
        if storage.remove_moderator(target_id):
            return f"✅ Сотрудник удалён."
        return "❌ Сотрудник не найден."

    # ══════════════════════════════════════
    #   Назначение должностей (/gstaff)
    # ══════════════════════════════════════
    
    if cmd in ("/ср", "!ср"):  # Специальный руководитель
        if not is_owner:
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        return set_user_position(target_id, "Специальный руководитель")
    
    if cmd in ("/зср", "!зср"):  # Заместитель специального руководителя
        if not is_owner:
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        return set_user_position(target_id, "Заместитель специального руководителя")
    
    if cmd in ("/рс", "!рс"):  # Руководитель сообщества
        if not is_owner:
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        return set_user_position(target_id, "Руководитель сообщества")

    # ══════════════════════════════════════
    #   Назначение должностей (/mstaff)
    # ══════════════════════════════════════
    
    if cmd in ("/рм", "!рм"):  # Руководитель модерации
        if not can_assign(from_user_id, "Руководитель модерации", storage) and not is_owner:
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        return set_user_position(target_id, "Руководитель модерации")
    
    if cmd in ("/зрм", "!зрм"):  # Заместитель руководителя модерации
        if not can_assign(from_user_id, "Заместитель руководителя модерации", storage) and not is_owner:
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        return set_user_position(target_id, "Заместитель руководителя модерации")
    
    if cmd in ("/гм", "!гм"):  # Главный модератор
        if not can_assign(from_user_id, "Главный модератор", storage) and not is_owner:
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        return set_user_position(target_id, "Главный модератор")
    
    if cmd in ("/згм", "!згм"):  # Заместитель главного модератора
        if not can_assign(from_user_id, "Заместитель главного модератора", storage) and not is_owner:
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        return set_user_position(target_id, "Заместитель главного модератора")
    
    if cmd in ("/км", "!км"):  # Куратор модерации
        if not can_assign(from_user_id, "Куратор модерации", storage) and not is_owner:
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        return set_user_position(target_id, "Куратор модерации")

    # ══════════════════════════════════════
    #   /ban
    # ══════════════════════════════════════
    if cmd in ("/ban", "!ban"):
        if not is_moder:
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
            vk.messages.removeChatUser(
                chat_id=peer_id - 2000000000,
                user_id=target_id
            )
        except Exception as e:
            print(f"[WARN] kick failed: {e}")

        storage.add_ban(target_id, peer_id, reason, term, from_user_id, by_label)

        target_mod = storage.get_moderator(target_id)
        target_label = target_mod["nick"] if target_mod else get_user_name(target_id)

        return f"🔨 {make_mention(target_id, target_label)} заблокирован\nПричина: {reason}\nСрок: {term}\nВыдал: {by_label}"

    # ══════════════════════════════════════
    #   /unban
    # ══════════════════════════════════════
    if cmd in ("/unban", "!unban"):
        if not is_moder:
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        storage.unban(target_id, peer_id)
        return f"✅ {make_mention(target_id, get_user_name(target_id))} разбанен"

    # ══════════════════════════════════════
    #   /kick
    # ══════════════════════════════════════
    if cmd in ("/kick", "!kick", "/кик", "!кик"):
        if not is_moder:
            return no_access()

        target_id, rest = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."

        reason = rest.strip() or "Без причины"

        try:
            vk.messages.removeChatUser(
                chat_id=peer_id - 2000000000,
                user_id=target_id
            )
        except Exception as e:
            return f"❌ Ошибка: {e}"

        mod = storage.get_moderator(from_user_id)
        by_label = mod["nick"] if mod else get_user_name(from_user_id)
        target_mod = storage.get_moderator(target_id)
        target_label = target_mod["nick"] if target_mod else get_user_name(target_id)

        return f"👢 {make_mention(target_id, target_label)} кикнут\nПричина: {reason}\nВыдал: {by_label}"

    # ══════════════════════════════════════
    #   /gban
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
                vk.messages.removeChatUser(
                    chat_id=pid - 2000000000,
                    user_id=target_id
                )
                storage.add_ban(target_id, pid, reason, "Глобальный бан",
                                from_user_id, by_name, is_gban=True)
                kicked += 1
            except Exception as e:
                print(f"[WARN] gban kick {pid}: {e}")

        storage.add_gban(target_id, reason, by_name)
        target_mod = storage.get_moderator(target_id)
        target_label = target_mod["nick"] if target_mod else get_user_name(target_id)

        return f"🌐 Глобальный бан: {make_mention(target_id, target_label)}\nПричина: {reason}\nКикнут из {kicked} бесед"

    # ══════════════════════════════════════
    #   /ungban
    # ══════════════════════════════════════
    if cmd in ("/ungban", "!ungban"):
        if not is_owner:
            return no_access()
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            return "❌ Укажи пользователя."
        if storage.remove_gban(target_id):
            return f"✅ Глобальный бан снят"
        return "❌ Активный бан не найден"

    # ══════════════════════════════════════
    #   /checkban
    # ══════════════════════════════════════
    if cmd in ("/checkban", "!checkban", "/чекбан", "!чекбан"):
        if not is_moder:
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

        lines = [f"Информация о блокировках {make_mention(target_id, target_label)}\n"]

        if gban:
            lines.append(f"Глобальный бан: {gban['reason']}")
            lines.append(f"Выдал: {gban['by_name']} | {gban['date']}")
        else:
            lines.append("Глобальный бан: отсутствует")

        lines.append("")

        if chat_bans:
            b = chat_bans[-1]
            lines.append(f"Бан в этой беседе: {b['reason']}")
            lines.append(f"Срок: {b['term']} | Выдал: {b['by_name']} | {b['date']}")
        else:
            lines.append("Бан в этой беседе: отсутствует")

        lines.append("")
        lines.append(f"Заблокирован в {banned_chats_count} беседах")

        return "\n".join(lines)

    # ══════════════════════════════════════
    #   /warn
    # ══════════════════════════════════════
    if cmd in ("/warn", "!warn"):
        if not is_moder:
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

    # ══════════════════════════════════════
    #   /warns
    # ══════════════════════════════════════
    if cmd in ("/warns", "!warns"):
        if not is_moder:
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

    # ══════════════════════════════════════
    #   /clearwarns
    # ══════════════════════════════════════
    if cmd in ("/clearwarns", "!clearwarns"):
        if not is_moder:
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
        if not is_moder:
            return no_access()

        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            target_id = from_user_id

        stats_chat = storage.get_user_stats_in_chat(target_id, peer_id)
        mod = storage.get_moderator(target_id)
        active_warns = storage.get_active_warnings(target_id)
        all_warns = storage.get_warnings(target_id)
        gban = storage.get_gban(target_id)
        vk_name = get_user_name(target_id)

        lines = []
        lines.append("╔════════════════════════════════╗")
        lines.append(f"║ Карточка пользователя           ║")
        lines.append("╠════════════════════════════════╣")
        lines.append(f"║ Имя: {make_mention(target_id, vk_name):<26}║")
        lines.append(f"║ ID: {target_id:<27}║")
        lines.append("║────────────────────────────────║")
        if mod:
            lines.append(f"║ Ник: {mod['nick']:<28}║")
            lines.append(f"║ Должность: {mod['position']:<22}║")
        else:
            lines.append("║ Не в системе                     ║")
        lines.append("║────────────────────────────────║")
        lines.append(f"║ Глобальный бан: {'есть' if gban else 'нет':<18}║")
        lines.append(f"║ Выговоров: {len(active_warns)}/{len(all_warns):<20}║")
        lines.append("║────────────────────────────────║")
        lines.append(f"║ Сообщений в беседе: {stats_chat['total']:<16}║")
        lines.append(f"║ Сегодня: {stats_chat['today']:<22}║")
        lines.append(f"║ Посл. актив: {stats_chat['last_time'] or '—':<20}║")
        lines.append("╚════════════════════════════════╝")

        return "\n".join(lines)

    # ══════════════════════════════════════
    #   /staff - список всех сотрудников
    # ══════════════════════════════════════
    if cmd in ("/staff", "!staff"):
        if not is_moder:
            return no_access()
        
        mods = storage.get_all_moderators()
        if not mods:
            return "Список сотрудников пуст"
        
        lines = ["Список сотрудников:"]
        for uid, m in mods.items():
            mention = make_mention(int(uid), m['nick'])
            lines.append(f"• {mention} — {m['position']}")
        
        return "\n".join(lines)

    # ══════════════════════════════════════
    #   /mstaff - состав модерации
    # ══════════════════════════════════════
    if cmd in ("/mstaff", "!mstaff", "/мстафф", "!мстафф"):
        if not is_moder:
            return no_access()

        all_mods = storage.get_all_moderators()
        
        positions_order = [
            "Руководитель модерации",
            "Заместитель руководителя модерации",
            "Главный модератор",
            "Заместитель главного модератора",
            "Куратор модерации"
        ]
        
        staff_by_position = {pos: [] for pos in positions_order}
        
        for uid, mod_data in all_mods.items():
            position = mod_data.get("position", "").strip()
            if position in staff_by_position:
                staff_by_position[position].append({"id": int(uid), "nick": mod_data["nick"]})
        
        lines = ["Состав модерации:"]
        lines.append("")
        
        for position in positions_order:
            staff_list = staff_by_position[position]
            if staff_list:
                for s in staff_list:
                    lines.append(f"{position}\n- {make_mention(s['id'], s['nick'])}")
            else:
                lines.append(f"{position}\n- —")
            lines.append("")
        
        return "\n".join(lines)

    # ══════════════════════════════════════
    #   /gstaff - глобальный состав
    # ══════════════════════════════════════
    if cmd in ("/gstaff", "!gstaff", "/гстафф", "!гстафф"):
        if not is_moder:
            return no_access()

        all_mods = storage.get_all_moderators()
        
        positions_order = [
            "Специальный руководитель",
            "Заместитель специального руководителя",
            "Руководитель сообщества"
        ]
        
        staff_by_position = {pos: [] for pos in positions_order}
        
        for uid, mod_data in all_mods.items():
            position = mod_data.get("position", "").strip()
            if position in staff_by_position:
                staff_by_position[position].append({"id": int(uid), "nick": mod_data["nick"]})
        
        lines = []
        
        for position in positions_order:
            staff_list = staff_by_position[position]
            lines.append(position)
            if staff_list:
                for s in staff_list:
                    lines.append(f"- {make_mention(s['id'], s['nick'])}")
            else:
                lines.append("- —")
            lines.append("")
        
        return "\n".join(lines)

    # ══════════════════════════════════════
    #   /stats
    # ══════════════════════════════════════
    if cmd in ("/stats", "!stats"):
        if not is_moder:
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

        lines = [f"Активность в беседе за {period_name}:\n"]
        for i, s in enumerate(chat_stats[:15], 1):
            uid = s["user_id"]
            mod = mods.get(str(uid))
            name = mod["nick"] if mod else get_user_name(uid)
            lines.append(f"{i}. {name} — {s['period']} сообщ.")

        return "\n".join(lines)

    # ══════════════════════════════════════
    #   /id
    # ══════════════════════════════════════
    if cmd in ("/id", "!id"):
        target_id, _ = resolve_target(args, reply_user_id)
        if not target_id:
            target_id = from_user_id

        name = get_user_name(target_id)
        return f"🔎 {name}\nID: {target_id}\nСсылка: vk.com/id{target_id}"

    # ══════════════════════════════════════
    #   /type - тип беседы
    # ══════════════════════════════════════
    if cmd in ("/type", "!type"):
        if not is_moder:
            return no_access()
        
        if args.strip():
            chat_type = args.strip().lower()
            if chat_type not in ("moder", "chat"):
                return "❌ Допустимые типы: moder, chat"
            storage.set_chat_type(peer_id, chat_type)
            return f"✅ Тип беседы установлен: {chat_type}"
        else:
            chat_type = storage.get_chat_type(peer_id)
            return f"Тип этой беседы: {chat_type}"

    # ══════════════════════════════════════
    #   /chatid
    # ══════════════════════════════════════
    if cmd in ("/chatid", "!chatid"):
        net_name, _ = storage.find_network_by_chat(peer_id)
        chat_type = storage.get_chat_type(peer_id)
        net_str = f"Сетка: {net_name}" if net_name else "Сетка: не задана"
        return f"peer_id: {peer_id}\nТип: {chat_type}\n{net_str}"

    # ══════════════════════════════════════
    #   /addnet, /delnet, /nets - сетки
    # ══════════════════════════════════════
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
        m = re.match(r"(\S+)(?:\s+(\d+))?", args)
        if not m:
            return "❌ Формат: /delnet [название]"
        net_name = m.group(1)
        storage.delete_network(net_name)
        return f"✅ Сетка {net_name} удалена"

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
        if not is_moder:
            return no_access()

        return (
            "📋 Команды бота:\n\n"
            "👤 Пользователи:\n"
            "/id [цель] — ID пользователя\n"
            "/stats [день|неделя|месяц] — активность\n"
            "/checkban [цель] — проверка банов\n\n"
            "🛡 Модерация:\n"
            "/ban [цель] [срок] [причина] — бан\n"
            "/unban [цель] — разбан\n"
            "/kick [цель] [причина] — кик\n"
            "/warn [цель] [причина] — выговор\n"
            "/warns [цель] — список выговоров\n"
            "/clearwarns [цель] — сброс выговоров\n\n"
            "⭐ Сотрудники:\n"
            "/staff — список сотрудников\n"
            "/mstaff — состав модерации\n"
            "/gstaff — глобальное руководство\n"
            "/snick [цель] [ник] — установить ник\n"
            "/rnick [цель] — снять ник\n"
            "/delstaff [цель] — удалить сотрудника\n\n"
            "⚡ Назначение должностей:\n"
            "/ср [цель] — Специальный руководитель\n"
            "/зср [цель] — Зам. спец. руководителя\n"
            "/рс [цель] — Руководитель сообщества\n"
            "/рм [цель] — Руководитель модерации\n"
            "/зрм [цель] — Зам. руководителя модерации\n"
            "/гм [цель] — Главный модератор\n"
            "/згм [цель] — Зам. главного модератора\n"
            "/км [цель] — Куратор модерации\n\n"
            "👑 Владельцу:\n"
            "/gban [цель] [причина]\n"
            "/ungban [цель]\n"
            "/addnet [название] [peer_id]\n"
            "/delnet [название]\n"
            "/nets"
        )

    return None