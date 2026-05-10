import random
from datetime import datetime, timedelta

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
