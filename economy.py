import random
from datetime import datetime, timedelta

# ── Константы ──
CURRENCY = "монет"
START_BALANCE = 0
VIP_PRICE = 1000
HIDE_BALANCE_PRICE = 1500
ROULETTE_MIN = 50
PRIZE_AMOUNT = 25
PRIZE_COOLDOWN = 3600  # 1 час в секундах

DEPOSIT_DAYS = 10
DEPOSIT_RATE = 0.03  # 3%

BUSINESS = {
    "завод": {
        "price": 5000,
        "income": 100,        # монет в сутки
        "products_per_day": 100,  # продуктов на 24 часа
        "product_price": 1,   # цена 1 продукта
    }
}

PROMO_MAX_AMOUNT = 50
PROMO_MAX_USES = 10


def fmt(amount) -> str:
    """Форматирует число с разделителями"""
    return f"{int(amount):,}".replace(",", " ")


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def seconds_until(dt_str: str, fmt_str="%Y-%m-%d %H:%M:%S") -> int:
    try:
        dt = datetime.strptime(dt_str, fmt_str)
        diff = (dt - datetime.now()).total_seconds()
        return max(0, int(diff))
    except Exception:
        return 0


def format_time(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}ч {m}мин"
    elif m > 0:
        return f"{m}мин {s}сек"
    return f"{s}сек"
