# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Основные настройки
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", ""))

# Настройки по умолчанию
OWNER_COMMISSION = 0.01
MAX_DEALS_PER_GROUP = 3
GROUP_COOLDOWN_HOURS = 2
DEFAULT_EXCHANGER_COMMISSION = 0.03

# Валюты для обмена
CURRENCIES = {
    "card": {
        "BYN": "🇧🇾 Белорусские рубли",
        "RUB": "🇷🇺 Российские рубли"
    },
    "crypto": {
        "USDT": "USDT (TRC-20)",
        "BTC": "Bitcoin", 
        "ETH": "Ethereum",
        "LTC": "Litecoin"
    },
    "ewallet": {
        "YANDEX": "Яндекс.Деньги",
        "QIWI": "QIWI",
        "PAYPAL": "PayPal"
    }
}

# ID приватных групп для сделок (ЗАМЕНИТЕ НА РЕАЛЬНЫЕ!)
PRIVATE_GROUP_IDS = [
    -1003246450829,
    -1003239468072,
    -1003254719739,
]

def load_settings_from_db():
    """Функция для перезагрузки настроек из базы данных"""
    try:
        from database import db
        settings = db.get_bot_settings()
        global OWNER_COMMISSION, MAX_DEALS_PER_GROUP, GROUP_COOLDOWN_HOURS, DEFAULT_EXCHANGER_COMMISSION
        
        OWNER_COMMISSION = float(settings.get('owner_commission', {'value': '0.01'})['value'])
        MAX_DEALS_PER_GROUP = int(settings.get('max_deals_per_group', {'value': '3'})['value'])
        GROUP_COOLDOWN_HOURS = int(settings.get('group_cooldown_hours', {'value': '2'})['value'])
        DEFAULT_EXCHANGER_COMMISSION = float(settings.get('default_exchanger_commission', {'value': '0.03'})['value'])
        
        print("✅ Настройки перезагружены из базы данных")
    except Exception as e:
        print(f"⚠️ Ошибка перезагрузки настроек: {e}")

print("✅ Конфиг загружен!")
print(f"🤖 Токен: {BOT_TOKEN[:10]}...")
print(f"👑 Владелец: {OWNER_ID}")
print(f"📊 Групп: {len(PRIVATE_GROUP_IDS)}")
print(f"⚙️ Комиссия гаранта: {OWNER_COMMISSION*100}%")

print(f"🔢 Максимум сделок на группу: {MAX_DEALS_PER_GROUP}")
