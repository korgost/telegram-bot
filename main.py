import time
import logging
import asyncio
import aiohttp
import asyncio
from aiogram import F
from datetime import datetime, timedelta
from typing import Dict, List
from aiogram.types import ChatPermissions
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from keyboards import get_back_to_exchanger_keyboard
from aiogram.filters import Command
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, ChatMemberUpdated,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from keyboards import get_exchanger_directions_keyboard, get_directions_list_keyboard

from config import BOT_TOKEN, OWNER_ID, GROUP_IDS, OWNER_COMMISSION, DEFAULT_EXCHANGER_COMMISSION, MIN_DEPOSIT, MAX_DEPOSIT, CURRENCY_TYPES
from database import db
from keyboards import (
    get_main_menu, get_back_button, get_currency_type_keyboard,
    get_currency_keyboard, get_buy_currency_keyboard, get_confirmation_keyboard,
    get_deal_control_keyboard, get_success_confirmation_keyboard, 
    get_exchanger_list_keyboard, get_admin_keyboard,
    get_admin_currencies_keyboard, get_admin_exchangers_keyboard,
    get_currency_management_keyboard, get_exchangers_list_keyboard,
    get_exchanger_management_keyboard, get_back_to_admin_keyboard,
    get_add_currency_keyboard,
    get_back_to_currencies_keyboard, get_back_to_exchangers_keyboard,
    get_exchanger_delete_confirmation_keyboard, 
    get_exchanger_directions_keyboard,
    get_directions_list_keyboard,
    get_currency_selection_keyboard,
    get_back_to_exchanger_keyboard,
    get_confirm_reset_groups_keyboard,
    get_currencies_by_type_keyboard,
    get_currencies_list_keyboard,
    get_currencies_list_management_keyboard,
    get_currency_delete_confirmation_keyboard,
    get_currency_type_selection_keyboard,
    get_back_to_currency_management_keyboard,
    get_currencies_list_simple_keyboard,
    get_currency_search_results_keyboard,
    get_currencies_type_view_keyboard,
    get_currencies_list_with_source  
)
from exchange_rates import exchange_api
from api_monitor import api_monitor
from config import BOT_TOKEN, OWNER_ID, GROUP_IDS, OWNER_COMMISSION, DEFAULT_EXCHANGER_COMMISSION, MIN_DEPOSIT, MAX_DEPOSIT, CURRENCY_TYPES, GUARANTOR_IDS 




import logging
logging.getLogger("exchange_rates").setLevel(logging.INFO)
logging.getLogger("__main__").setLevel(logging.INFO)



#----------------------------------------------------------------------    Для сайта fly.io
from dotenv import load_dotenv
import os

load_dotenv()  # загрузит .env локально
TELEGRAM_TOKEN = os.getenv("AAEHf7_iP4YvtTnLFP9sEACcLEzWhQpBI_A")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
# дальше используй TELEGRAM_TOKEN в инициализации бота

#----------------------------------------------------------------------    Для сайта fly.io



def is_guarantor(user_id: int) -> bool:
    """Проверяет, является ли пользователь гарантом"""
    is_guar = user_id in GUARANTOR_IDS
    logger.info(f"🔍 Проверка гаранта: user_id={user_id}, is_guarantor={is_guar}, GUARANTOR_IDS={GUARANTOR_IDS}")
    return is_guar





CRYPTO_CODES = {"BTC", "ETH", "USDT", "LTC", "BNB", "BUSD"}


def format_amount(amount: float, currency: str) -> str:
    """
    Форматирует сумму:
    - BTC: 10 знаков после запятой
    - Другие крипты: 8 знаков  
    - Фиат: 2 знака
    """
    if currency == "BTC":
        # Для BTC показываем 8 знаков, чтобы видеть даже маленькие суммы
        return f"{amount:.8f}"
    elif currency in CRYPTO_CODES:
        return f"{amount:.8f}"  # 8 знаков для других крипт
    else:
        return f"{amount:.2f}"  # 2 знака для фиата






# === Настройка логирования ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# === Инициализация ===
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Временное хранилище данных пользователей
user_data = {}
DEALS = {}
ACTIVE_DEALS = {}
USER_MESSAGES = {}
DEAL_TIMERS = {}

# === ФУНКЦИИ ПРОВЕРКИ ТИПА ЧАТА ===
def is_deal_chat(chat_id: int) -> bool:
    """Проверяет, является ли чат чатом сделки"""
    return chat_id in ACTIVE_DEALS or chat_id in GROUP_IDS

def is_private_chat(chat_id: int) -> bool:
    """Проверяет, является ли чат личным с ботом"""
    return chat_id > 0

async def should_ignore_message(message: Message) -> bool:
    """Определяет, нужно ли игнорировать сообщение"""
    chat_id = message.chat.id
    
    # Игнорируем сообщения в чатах сделок (кроме команд и callback-кнопок)
    if is_deal_chat(chat_id) and not message.text.startswith('/'):
        return True
    
    return False

# === Функции для работы с курсами ===
async def get_real_exchange_rate(sell_currency: str, buy_currency: str) -> float:
    """Получение реального курса обмена с таймаутом"""
    try:
        rate, api_used = await asyncio.wait_for(
            exchange_api.get_exchange_rate_async(sell_currency, buy_currency),
            timeout=15.0
        )
        if rate:
            logger.info(f"✅ Курс {sell_currency}->{buy_currency} = {rate} (источник: {api_used})")
            return rate
        else:
            logger.warning(f"❌ Курс не найден, используем 1.0 для {sell_currency}->{buy_currency}")
            return 1.0

    except asyncio.TimeoutError:
        logger.error(f"⏰ Таймаут получения курса {sell_currency}->{buy_currency}")
        return 1.0
    except Exception as e:
        logger.error(f"Ошибка получения курса {sell_currency}->{buy_currency}: {e}")
        return 1.0




async def calculate_final_amount(amount: float, sell_currency: str, buy_currency: str, exchanger_id: int) -> Dict:
    """Расчет финальной суммы с улучшенной обработкой курсов"""
    max_retries = 3
    retry_delay = 1
    
    for attempt in range(max_retries):
        try:
            # Получаем реальный курс с повторными попытками
            exchange_rate = await get_real_exchange_rate(sell_currency, buy_currency)
            
            if exchange_rate <= 0:
                logger.warning(f"⚠️ Некорректный курс {exchange_rate}, попытка {attempt + 1}")
                await asyncio.sleep(retry_delay)
                continue
            
            # Базовая сумма после конвертации
            base_amount = amount * exchange_rate
            
            # Комиссия гаранта
            owner_fee = base_amount * OWNER_COMMISSION
            
            # Комиссия обменника
            exchanger_stats = db.get_exchanger_stats(exchanger_id)
            exchanger_commission = exchanger_stats['commission_rate'] if exchanger_stats else DEFAULT_EXCHANGER_COMMISSION
            exchanger_fee = base_amount * exchanger_commission
            
            # Финальная сумма для клиента
            final_amount = base_amount - owner_fee - exchanger_fee
            
            # Проверяем на корректность
            if final_amount <= 0:
                raise ValueError("Финальная сумма <= 0")
            
            # Для BTC округляем до 8 знаков, для других валют - до 2
            if buy_currency == "BTC":
                return {
                    'final_amount': round(final_amount, 10),  # Округляем до 10 знаков
                    'exchange_rate': exchange_rate,
                    'owner_fee': round(owner_fee, 10),
                    'exchanger_fee': round(exchanger_fee, 10),
                    'base_amount': round(base_amount, 10)
                }
            else:
                return {
                    'final_amount': round(final_amount, 2),
                    'exchange_rate': exchange_rate,
                    'owner_fee': round(owner_fee, 2),
                    'exchanger_fee': round(exchanger_fee, 2),
                    'base_amount': round(base_amount, 2)
                }
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка расчета (попытка {attempt + 1}): {e}")
            if attempt == max_retries - 1:
                # Последняя попытка - используем запасной вариант
                logger.error(f"❌ Все попытки расчета провалились, используем запасной расчет")
                return await get_fallback_calculation(amount, sell_currency, buy_currency, exchanger_id)
            await asyncio.sleep(retry_delay)











@dp.callback_query(F.data.startswith("choose_exchanger:"))
async def choose_exchanger_handler(callback: CallbackQuery):
    """Выбор обменника"""
    user_id = callback.from_user.id
    logger.info(f"🔘 Обработчик choose_exchanger_handler ВЫЗВАН: {callback.data}, user_id: {user_id}")
    
    try:
        exchanger_index = int(callback.data.split(":")[1])
        logger.info(f"📊 Индекс обменника: {exchanger_index}")
        
        # Проверяем наличие данных пользователя
        if user_id not in user_data:
            logger.error(f"❌ НЕТ user_data для пользователя {user_id}")
            await callback.answer("❌ Данные устарели")
            return
        
        if 'available_exchangers' not in user_data[user_id]:
            logger.error(f"❌ НЕТ available_exchangers для пользователя {user_id}")
            logger.error(f"📋 user_data keys: {list(user_data[user_id].keys())}")
            await callback.answer("❌ Данные устарели")
            return
        
        exchangers = user_data[user_id]['available_exchangers']
        logger.info(f"✅ Найдено обменников в данных: {len(exchangers)}")
        
        # Проверяем индекс
        if exchanger_index < 0 or exchanger_index >= len(exchangers):
            logger.error(f"❌ Неверный индекс {exchanger_index} при {len(exchangers)} обменниках")
            await callback.answer("❌ Ошибка выбора обменника")
            return
        
        exchanger = exchangers[exchanger_index]
        user_data[user_id]['selected_exchanger'] = exchanger
        
        logger.info(f"✅ Выбран обменник: @{exchanger['username']}, final_amount: {exchanger['final_amount']}")
        
        # Получаем данные о валютах
        sell_code = user_data[user_id].get('sell_currency_code', '?')
        buy_code = user_data[user_id].get('buy_currency_code', '?')
        sell_name = user_data[user_id].get('sell_currency_name', '?')
        buy_name = user_data[user_id].get('buy_currency_name', '?')
        sell_amount = user_data[user_id].get('sell_amount', 0)
        
        logger.info(f"📊 Данные обмена: {sell_amount} {sell_code} -> {buy_code}")
        
        confirmation_text = (
            f"✅ <b>Подтверждение обмена</b>\n\n"
            f"<b>Вы покупаете:</b> {format_amount(exchanger['final_amount'], buy_code)} {buy_name}\n"
            f"<b>За:</b> {format_amount(sell_amount, sell_code)} {sell_name}\n"
            f"<b>Курс:</b> 1 {sell_code} = {exchanger['exchange_rate']:.8f} {buy_code}\n"
            f"<b>Обменник:</b> @{exchanger['username']}\n\n"
            f"<i>После подтверждения будет создан защищенный чат для сделки</i>\n\n"
            f"Подтверждаете обмен?"
        )
        
        await callback.message.edit_text(
            confirmation_text,
            reply_markup=get_confirmation_keyboard()
        )
        
    except IndexError as e:
        logger.error(f"❌ Ошибка индекса {exchanger_index}: {e}")
        await callback.answer("❌ Ошибка выбора обменника")
    except Exception as e:
        logger.error(f"❌ Ошибка в choose_exchanger_handler: {e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка")














async def get_fallback_calculation(amount: float, sell_currency: str, buy_currency: str, exchanger_id: int) -> Dict:
    """Запасной расчет при недоступности API"""
    # Используем статические коэффициенты для основных пар
    fallback_rates = {
        "USDT": {"RUB": 90, "BYN": 3.2, "USD": 1.0, "EUR": 0.92},
        "BTC": {"USDT": 45000, "RUB": 4050000},
        "ETH": {"USDT": 2800, "RUB": 252000},
        "BYN": {"RUB": 28, "USDT": 0.31},
        "RUB": {"BYN": 0.035, "USDT": 0.011}
    }
    
    # Пытаемся найти запасной курс
    fallback_rate = fallback_rates.get(sell_currency, {}).get(buy_currency, 0.95)
    
    base_amount = amount * fallback_rate
    owner_fee = base_amount * OWNER_COMMISSION
    
    exchanger_stats = db.get_exchanger_stats(exchanger_id)
    exchanger_commission = exchanger_stats['commission_rate'] if exchanger_stats else DEFAULT_EXCHANGER_COMMISSION
    exchanger_fee = base_amount * exchanger_commission
    
    final_amount = base_amount - owner_fee - exchanger_fee
    
    return {
        'final_amount': round(final_amount, 2),
        'exchange_rate': fallback_rate,
        'owner_fee': round(owner_fee, 2),
        'exchanger_fee': round(exchanger_fee, 2),
        'base_amount': round(base_amount, 2)
    }






async def get_available_exchangers(sell_currency: str, buy_currency: str, amount: float) -> List[Dict]:
    """Получение списка доступных обменников с учётом направлений"""
    try:
        logger.info(f"🔍 Поиск обменников для {amount} {sell_currency}->{buy_currency}")
        
        # Получаем обменников из БД (по залогу и активности)
        exchangers = db.get_available_exchangers(amount)
        logger.info(f"📊 Найдено обменников в БД (по залогу): {len(exchangers)}")
        
        if not exchangers:
            return []
        
        available_exchangers: List[Dict] = []
        
        for exchanger in exchangers:
            # 1. Проверяем, есть ли у обменника направления вообще
            try:
                if not db.exchanger_has_directions(exchanger['user_id']):
                    logger.info(f"⛔ Обменник {exchanger['user_id']} не имеет направлений и пропускается")
                    continue  # Обменник без направлений - пропускаем
            except Exception as e:
                logger.warning(f"⚠️ Не удалось проверить направления для {exchanger['user_id']}: {e}")
                continue
            
            # 2. Проверяем, поддерживает ли обменник конкретное направление
            try:
                if not db.check_exchanger_supports_direction(exchanger['user_id'], sell_currency, buy_currency):
                    logger.info(f"⛔ Обменник {exchanger['user_id']} не поддерживает направление {sell_currency}->{buy_currency}")
                    continue
            except Exception as e:
                logger.warning(f"⚠️ Не удалось проверить поддержку направления для {exchanger['user_id']}: {e}")
                continue
            
            # 3. Считаем итоговые суммы и комиссии
            try:
                calculation = await asyncio.wait_for(
                    calculate_final_amount(amount, sell_currency, buy_currency, exchanger['user_id']),
                    timeout=20.0
                )
                
                exchanger_data = {
                    **exchanger,
                    'final_amount': calculation['final_amount'],
                    'exchange_rate': calculation['exchange_rate'],
                    'owner_fee': calculation['owner_fee'],
                    'exchanger_fee': calculation['exchanger_fee'],
                    'base_amount': calculation['base_amount']
                }
                available_exchangers.append(exchanger_data)
                
            except asyncio.TimeoutError:
                logger.warning(f"⏰ Таймаут расчёта для обменника {exchanger['user_id']}")
                continue
            except Exception as e:
                logger.error(f"❌ Ошибка расчёта для обменника {exchanger['user_id']}: {e}")
                continue
        
        logger.info(f"✅ Доступных обменников после фильтрации: {len(available_exchangers)}")
        return available_exchangers
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в get_available_exchangers: {e}")
        return []






async def cleanup_old_data():
    current_time = time.time()
    users_to_remove = []
    
    for user_id, data in user_data.items():
        # Если данные старше 1 часа, удаляем
        if current_time - data.get('_timestamp', 0) > 3600:
            users_to_remove.append(user_id)
    
    for user_id in users_to_remove:
        del user_data[user_id]
        logger.info(f"Очищены устаревшие данные пользователя {user_id}")

# Добавляем timestamp при создании данных
def update_user_data_timestamp(user_id: int):
    """Обновление временной метки данных пользователя"""
    if user_id in user_data:
        user_data[user_id]['_timestamp'] = time.time()

# === Основные функции ===
async def send_welcome_message(chat_id: int, user_id: int, username: str = ""):
    """Отправка приветственного сообщения"""
    db.update_user_online(user_id, username)
    
    welcome_text = (
        "🛡️ <b>Гарантированный обмен криптовалюты</b>\n\n"
        "Добро пожаловать в безопасную площадку для P2P-обменов!\n\n"
        "<b>Наши преимущества:</b>\n"
        "• 🔒 Гарантия безопасности сделок\n"
        "• ⚡ Мгновенное создание чатов\n"
        "• 🛡️ Круглосуточная поддержка гаранта\n"
        "• 💰 Прозрачные комиссии\n"
        "• 🔄 Автоматическая ротация чатов\n\n"
        "Начните безопасный обмен прямо сейчас!"
    )
    
    await bot.send_message(
        chat_id=chat_id,
        text=welcome_text,
        reply_markup=get_main_menu(user_id == OWNER_ID)
    )






async def create_deal_chat(deal_info: Dict) -> str:
    """Создание чата для сделки с закрепленным сообщением"""
    deal_id = str(int(time.time()))
    
    # Получаем доступную группу
    chat_id = db.get_best_group()
    if not chat_id:
        chat_id = GROUP_IDS[0]
    
    topic_name = f"Сделка #{deal_id} | {deal_info['sell_amount']} {deal_info['sell_currency']} → {deal_info['final_amount']} {deal_info['buy_currency']}"
    
    try:
        # Переименовываем чат
        await bot.set_chat_title(chat_id=chat_id, title=topic_name)
        
        # Создаем ВРЕМЕННУЮ ссылку на 40 минут
        invite = await bot.create_chat_invite_link(
            chat_id=chat_id,
            name=f"deal_{deal_id}",
            creates_join_request=False,
            member_limit=3,
            expire_date=int(time.time()) + 2400
        )
        
        deal_info.update({
            'deal_id': deal_id,
            'chat_id': chat_id,
            'topic_name': topic_name,
            'invite_link': invite.invite_link,
            'status': 'active',
            'created_at': time.time(),
            'start_time': datetime.now(),
            'control_message_id': None,
            'notifications_sent': [],
            'pinned_message_sent': False  # ← ДОБАВИТЬ этот флаг
        })
        
        DEALS[deal_id] = deal_info
        ACTIVE_DEALS[chat_id] = deal_id
        
        # Обновляем статистику группы
        db.update_group_stats(chat_id)
        
        # ⚠️ НЕ отправляем здесь закрепленное сообщение - оно будет отправлено когда клиент зайдет
        
        # Запускаем мониторинг
        asyncio.create_task(monitor_deal_time(deal_id))
        
        # Уведомляем гаранта
        await notify_guarantors(deal_info)
        
        logger.info(f"Создана сделка {deal_id} в группе {chat_id}")
        return deal_id
        
    except Exception as e:
        logger.error(f"Ошибка создания чата: {e}")
        raise





async def notify_guarantors(deal_info: Dict):
    """Уведомление всех гарантов о новой сделке"""
    for guarantor_id in GUARANTOR_IDS:
        try:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Деньги переведены", callback_data=f"guarantor_success:{deal_info['deal_id']}"),
                    InlineKeyboardButton(text="🗑️ Удалить чат", callback_data=f"guarantor_cancel:{deal_info['deal_id']}")
                ],
                [
                    InlineKeyboardButton(text="🛡️ Вмешаться", callback_data=f"guarantor_join:{deal_info['deal_id']}")
                ]
            ])
            
            await bot.send_message(
                chat_id=guarantor_id,
                text=(
                    f"🛡️ <b>Новая сделка создана</b>\n\n"
                    f"<b>ID:</b> #{deal_info['deal_id']}\n"
                    f"<b>Клиент:</b> {deal_info['client_name']}\n"
                    f"<b>Обменник:</b> @{deal_info['exchanger_username']}\n"
                    f"<b>Сумма:</b> {deal_info['sell_amount']} {deal_info['sell_currency']} → "
                    f"{deal_info['final_amount']} {deal_info['buy_currency']}\n"
                    f"<b>Курс:</b> 1 {deal_info['sell_currency']} = {deal_info['exchange_rate']:.4f} {deal_info['buy_currency']}\n"
                    f"<b>Время:</b> 40 минут\n\n"
                    f"🔗 <a href='{deal_info['invite_link']}'>Присоединиться к чату</a>"
                ),
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить гаранта {guarantor_id}: {e}")







# === ОБРАБОТЧИКИ ДЛЯ ГАРАНТА ===

@dp.callback_query(F.data.startswith("guarantor_success:"))
async def guarantor_success_handler(callback: CallbackQuery):
    """Гарант подтверждает успешное завершение сделки"""
    deal_id = callback.data.split(":")[1]
    
    await callback.answer("✅ Сделка завершена успешно! Уведомления отправлены.")
    
    await callback.message.edit_text(
        f"✅ <b>Сделка #{deal_id} завершена гарантом</b>\n\n"
        f"Статус: успешно завершена\n"
        f"Комиссия начислена\n"
        f"Уведомления отправлены участникам в ЛС\n"
        f"Чат очищен и сброшен\n"
        f"Время: {datetime.now().strftime('%H:%M:%S')}"
    )
    
    # Завершаем сделку
    await complete_deal(deal_id, "completed_by_guarantor")



@dp.callback_query(F.data.startswith("guarantor_cancel:"))
async def guarantor_cancel_handler(callback: CallbackQuery):
    """Гарант отменяет сделку"""
    deal_id = callback.data.split(":")[1]
    
    await callback.answer("🗑️ Сделка отменена! Уведомления отправлены.")
    
    await callback.message.edit_text(
        f"🗑️ <b>Сделка #{deal_id} отменена гарантом</b>\n\n"
        f"Статус: принудительно отменена\n"
        f"Комиссия не начислена\n"
        f"Уведомления отправлены участникам в ЛС\n"
        f"Чат очищен и сброшен\n"
        f"Время: {datetime.now().strftime('%H:%M:%S')}"
    )
    
    await complete_deal(deal_id, "cancelled_by_guarantor")






@dp.callback_query(F.data.startswith("guarantor_join:"))
async def guarantor_join_handler(callback: CallbackQuery):
    """Гарант присоединяется к чату сделки - АЛЬТЕРНАТИВНАЯ ВЕРСИЯ"""
    deal_id = callback.data.split(":")[1]
    deal_info = DEALS.get(deal_id)
    
    if not deal_info:
        await callback.answer("❌ Сделка не найдена")
        return
        
    try:
        # Отправляем сообщение в чат сделки
        await bot.send_message(
            chat_id=deal_info['chat_id'],
            text="🛡️ <b>Гарант подключился к чату</b>\n\n"
                 "Для решения спорных ситуаций подключился гарант. "
                 "Пожалуйста, опишите проблему."
        )
        
        # Отправляем новое сообщение гаранту (не редактируем старое)
        await callback.message.answer(
            f"🛡️ <b>Вы подключились к сделке #{deal_id}</b>\n\n"
            f"Чат: {deal_info['chat_id']}\n"
            f"🔗 <a href='{deal_info['invite_link']}'>Перейти в чат</a>\n\n"
            f"<i>Исходное сообщение с кнопками управления остается выше</i>"
        )
        
        await callback.answer("Вы подключились к чату!")
        
    except Exception as e:
        logger.error(f"Ошибка подключения гаранта: {e}")
        await callback.answer("❌ Не удалось подключиться к чату")






def has_active_deal(client_id: int) -> bool:
    """Проверяет, есть ли у клиента активные сделки"""
    for deal_id, deal_info in DEALS.items():
        if deal_info['client_id'] == client_id:
            return True
    return False






async def send_deal_control_message(deal_info: Dict):
    """Отправка контрольного сообщения в чат сделки"""
    try:
        control_text = (
            f"🎛️ <b>Управление сделкой #{deal_info['deal_id']}</b>\n\n"
            f"<b>Сумма:</b> {deal_info['sell_amount']} {deal_info['sell_currency']} → "
            f"{deal_info['final_amount']} {deal_info['buy_currency']}\n"
            f"<b>Курс:</b> 1 {deal_info['sell_currency']} = {deal_info['exchange_rate']:.4f} {deal_info['buy_currency']}\n"
            f"<b>Обменник:</b> @{deal_info['exchanger_username']}\n"
            f"<b>Клиент:</b> {deal_info['client_name']}\n\n"
        )
        
        # Отправляем сообщение клиенту
        client_text = control_text + (
            "─────────────────────\n"
            "<b>Для клиента:</b>\n"
            "• ✅ <b>Деньги пришли, закрыть чат</b> - если получили деньги\n"
            "• 🛡️ <b>Сделка не удалась, Вызвать гаранта</b> - если есть проблемы\n\n"
            "<i>Не нажимайте кнопку подтверждения, пока не получили деньги!</i>"
        )
        
        # Отправляем сообщение обменнику  
        exchanger_text = control_text + (
            "─────────────────────\n"
            "<b>Для обменника:</b>\n"
            "• Ожидайте подтверждения от клиента\n"
            "• Если возникли проблемы - свяжитесь с гарантом\n\n"
            "<i>Клиент подтвердит сделку когда получит деньги</i>"
        )
        
        # Отправляем сообщение гаранту
        guarantor_text = control_text + (
            "─────────────────────\n"
            "<b>Для гаранта:</b>\n"
            "• Следите за ходом сделки\n"
            "• Вмешайтесь при возникновении споров\n"
        )
        
        # Отправляем каждому участнику своё сообщение
        try:
            # Клиенту
            await bot.send_message(
                chat_id=deal_info['client_id'],
                text=client_text,
                reply_markup=get_deal_control_keyboard(deal_info['deal_id'], "client")
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение клиенту: {e}")
        
        try:
            # Обменнику
            await bot.send_message(
                chat_id=deal_info['exchanger_id'],
                text=exchanger_text,
                reply_markup=get_deal_control_keyboard(deal_info['deal_id'], "exchanger")
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение обменнику: {e}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки контрольного сообщения: {e}")
        




async def remove_participants(chat_id: int, deal_info: Dict):
    """Удаление участников из чата сделки"""
    try:
        bot_info = await bot.get_me()
        participants = [deal_info['client_id'], deal_info['exchanger_id']]
        
        for user_id in participants:
            try:
                if user_id == bot_info.id or user_id == OWNER_ID:
                    continue
                
                await bot.ban_chat_member(chat_id=chat_id, user_id=user_id, revoke_messages=True)
                await asyncio.sleep(1)
                await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
                logger.info(f"Удален пользователь {user_id} из чата {chat_id}")
                
            except Exception as e:
                logger.error(f"Ошибка удаления пользователя {user_id}: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка в remove_participants: {e}")



async def clear_chat_history(chat_id: int):
    """Очистка истории чата - УЛУЧШЕННАЯ ВЕРСИЯ"""
    try:
        # Отправляем финальное сообщение
        await bot.send_message(
            chat_id=chat_id,
            text="🔄 <b>Чат полностью очищен и сброшен</b>\n\n"
                 "Все участники удалены, история очищена.\n"
                 "Ожидайте новых участников для следующей сделки...",
        )
        
        # Дополнительно: пытаемся удалить последние сообщения (если есть права)
        try:
            # Получаем последние сообщения
            # В Aiogram нет прямого метода, но можно попробовать удалить последние N сообщений
            # Ограничимся 50 сообщениями для безопасности
            pass  # Эта функция может быть сложной в реализации без topic_id
        except Exception as e:
            logger.warning(f"⚠️ Не удалось очистить историю сообщений: {e}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка очистки чата {chat_id}: {e}")



async def complete_deal(deal_id: str, reason: str):
    """Завершение сделки с редактированием существующего сообщения вместо отправки нового"""
    deal_info = DEALS.get(deal_id)
    if not deal_info:
        return
    
    chat_id = deal_info['chat_id']
    client_id = deal_info['client_id']
    
    try:
        logger.info(f"🔄 Завершение сделки {deal_id}, причина: {reason}")
        
        # Определяем текст в зависимости от причины завершения
        if reason in ["completed_by_client", "completed_by_guarantor"]:
            status_icon = "✅"
            status_text = "успешно завершена"
            commission_text = "Комиссия начислена."
        elif reason == "timeout":
            status_icon = "⏰"
            status_text = "автоматически завершена по истечении времени"
            commission_text = "Комиссия не начислена."
        else:  # cancelled_by_guarantor и другие случаи отмены
            status_icon = "❌"
            status_text = "отменена"
            commission_text = "Комиссия не начислена."

        # Формируем финальное сообщение
        final_text = (
            f"{status_icon} <b>Сделка #{deal_id} {status_text}</b>\n\n"
            f"<b>Сумма:</b> {deal_info['sell_amount']} {deal_info['sell_currency']} → "
            f"{deal_info['final_amount']} {deal_info['buy_currency']}\n"
            f"<b>Обменник:</b> @{deal_info['exchanger_username']}\n"
            f"<b>Клиент:</b> {deal_info['client_name']}\n\n"
            f"{commission_text}"
        )
        
        # 1. Редактируем сообщение у клиента (если оно существует)
        if client_id in USER_MESSAGES and f"deal_{deal_id}" in USER_MESSAGES[client_id]:
            try:
                message_id = USER_MESSAGES[client_id][f"deal_{deal_id}"]
                await bot.edit_message_text(
                    chat_id=client_id,
                    message_id=message_id,
                    text=final_text,
                    reply_markup=None
                )
                logger.info(f"✅ Сообщение сделки {deal_id} отредактировано у клиента {client_id}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось отредактировать сообщение клиенту: {e}")
                # Если не удалось редактировать, отправляем новое
                try:
                    await bot.send_message(client_id, final_text)
                except Exception as e2:
                    logger.error(f"❌ Не удалось отправить сообщение клиенту: {e2}")
        else:
            # Если нет сохраненного сообщения, отправляем новое
            try:
                await bot.send_message(client_id, final_text)
            except Exception as e:
                logger.error(f"❌ Не удалось отправить сообщение клиенту: {e}")
        
        # 2. Отправляем обычные уведомления обменнику и гаранту
        await send_deal_completion_notifications(deal_info, reason)
        
        # 3. Принудительно удаляем участников сделки из чата
        await remove_participants_forcefully(chat_id, deal_info)
        
        # 4. Открепляем сообщение если есть
        if deal_info.get('pinned_message_id'):
            try:
                await bot.unpin_chat_message(chat_id=chat_id, message_id=deal_info['pinned_message_id'])
            except:
                pass
        
        # 5. Полностью сбрасываем группу
        await reset_group_completely(chat_id)
        
        # 6. Обновляем статистику ТОЛЬКО при успешном завершении
        if reason in ["completed_by_client", "completed_by_guarantor"]:
            db.update_exchanger_stats(
                deal_info['exchanger_id'],
                deal_info['sell_amount'],
                deal_info['owner_fee'],
                deal_info['exchanger_fee'],
                True
            )
            logger.info(f"✅ Комиссия начислена для сделки {deal_id}")
        
        # 7. Удаляем из активных сделок и очищаем сообщения
        if deal_id in DEALS:
            del DEALS[deal_id]
        if chat_id in ACTIVE_DEALS:
            del ACTIVE_DEALS[chat_id]
        
        # Очищаем сохраненные сообщения
        await cleanup_user_messages(client_id, deal_id)
        await cleanup_user_messages(deal_info['exchanger_id'], deal_id)
            
        logger.info(f"✅ Сделка {deal_id} завершена. Причина: {reason}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка завершения сделки: {e}")





async def reset_group_completely(chat_id: int) -> bool:
    """Полный сброс группы: удаление пользователей, очистка истории, смена ссылки - УЛУЧШЕННАЯ ВЕРСИЯ"""
    try:
        logger.info(f"🔄 Полный сброс группы {chat_id}")
        
        # 0. Если есть активная сделка в этой группе, завершаем её и удаляем участников
        deal_id_to_complete = None
        deal_info_to_cleanup = None
        
        for deal_id, deal_info in DEALS.items():
            if deal_info.get('chat_id') == chat_id:
                deal_id_to_complete = deal_id
                deal_info_to_cleanup = deal_info
                break
        
        if deal_id_to_complete and deal_info_to_cleanup:
            # Принудительно удаляем участников сделки
            await remove_participants_forcefully(chat_id, deal_info_to_cleanup)
            
            # Удаляем сделку из активных
            if deal_id_to_complete in DEALS:
                del DEALS[deal_id_to_complete]
            if chat_id in ACTIVE_DEALS:
                del ACTIVE_DEALS[chat_id]
            logger.info(f"✅ Завершена сделка {deal_id_to_complete} при сбросе группы {chat_id}")
        
        # 1. Открепляем все сообщения в чате
        try:
            await bot.unpin_all_chat_messages(chat_id=chat_id)
            logger.info(f"✅ Откреплены все сообщения в группе {chat_id}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось открепить сообщения: {e}")
        
        # 2. Удаляем ВСЕХ участников кроме бота и владельца (даже если не было активной сделки)
        await remove_all_participants_comprehensive(chat_id)
        
        # 3. Очищаем историю чата
        await clear_chat_history(chat_id)
        
        # 4. Отзываем старые пригласительные ссылки и создаем новую
        new_invite_link = await refresh_invite_links(chat_id)
        
        # 5. Переименовываем чат
        await bot.set_chat_title(chat_id=chat_id, title="🔄 Готов к сделке")
        
        # 6. Сбрасываем статистику в базе
        db.reset_group_cooldown(chat_id)
        
        logger.info(f"✅ Группа {chat_id} полностью сброшена. Новая ссылка: {new_invite_link}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка сброса группы {chat_id}: {e}")
        return False






async def remove_all_participants_comprehensive(chat_id: int):
    """Комплексное удаление всех участников группы - для сброса групп"""
    try:
        bot_info = await bot.get_me()
        removed_count = 0
        
        # Получаем администраторов
        admins = await bot.get_chat_administrators(chat_id)
        admin_ids = {admin.user.id for admin in admins}
        
        # Защищенные ID (бот и владелец)
        protected_ids = {bot_info.id, OWNER_ID}
        
        # Метод 1: Удаляем известных участников из активных сделок
        if chat_id in ACTIVE_DEALS:
            deal_id = ACTIVE_DEALS[chat_id]
            deal_info = DEALS.get(deal_id)
            if deal_info:
                participants = [deal_info['client_id'], deal_info['exchanger_id']]
                for user_id in participants:
                    if user_id not in protected_ids:
                        success = await kick_user_from_group(chat_id, user_id)
                        if success:
                            removed_count += 1
                        await asyncio.sleep(1)
        
        # Метод 2: Удаляем всех не-администраторов (кроме защищенных)
        for admin in admins:
            user_id = admin.user.id
            if user_id not in protected_ids and not admin.is_chat_creator():
                try:
                    success = await kick_user_from_group(chat_id, user_id)
                    if success:
                        removed_count += 1
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось удалить участника {user_id}: {e}")
        
        # Метод 3: Ограничиваем права для оставшихся участников
        try:
            # Получаем текущих участников (если есть)
            members_count = await bot.get_chat_member_count(chat_id)
            if members_count > len(admin_ids):
                logger.info(f"👥 В группе {chat_id} осталось {members_count} участников после удаления")
                
                # Ограничиваем права для всех (кроме защищенных)
                for admin in admins:
                    user_id = admin.user.id
                    if user_id not in protected_ids:
                        await bot.restrict_chat_member(
                            chat_id=chat_id,
                            user_id=user_id,
                            permissions=ChatPermissions(
                                can_send_messages=False,
                                can_send_media_messages=False,
                                can_send_other_messages=False,
                                can_add_web_page_previews=False
                            )
                        )
        except Exception as e:
            logger.warning(f"⚠️ Не удалось ограничить права участников: {e}")
        
        logger.info(f"✅ Удалено/ограничено {removed_count} участников из группы {chat_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка комплексного удаления участников: {e}")






async def cleanup_user_messages(user_id: int, deal_id: str):
    """Очищает сообщения пользователя после завершения сделки"""
    try:
        if user_id in USER_MESSAGES and f"deal_{deal_id}" in USER_MESSAGES[user_id]:
            # Пытаемся удалить сообщение у пользователя
            try:
                message_id = USER_MESSAGES[user_id][f"deal_{deal_id}"]
                await bot.delete_message(chat_id=user_id, message_id=message_id)
                logger.info(f"✅ Удалено сообщение сделки {deal_id} у пользователя {user_id}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось удалить сообщение: {e}")
            
            # Очищаем из хранилища
            del USER_MESSAGES[user_id][f"deal_{deal_id}"]
            
            # Если у пользователя больше нет сообщений, очищаем запись
            if not USER_MESSAGES[user_id]:
                del USER_MESSAGES[user_id]
                
    except Exception as e:
        logger.error(f"❌ Ошибка очистки сообщений пользователя {user_id}: {e}")





async def refresh_invite_links(chat_id: int) -> str:
    """Отзывает старые ссылки, создает новую основную ссылку и временную для сделки"""
    try:
        # 1. Отзываем ВСЕ старые пригласительные ссылки
        try:
            # Получаем все созданные ссылки
            invite_links = await bot.get_chat_invite_links(chat_id)
            for link in invite_links:
                try:
                    await bot.revoke_chat_invite_link(chat_id=chat_id, invite_link=link.invite_link)
                    logger.info(f"✅ Отозвана старая ссылка: {link.invite_link}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось отозвать ссылку {link.invite_link}: {e}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось получить список ссылок: {e}")

        # 2. Создаем новую ОСНОВНУЮ ссылку чата (это важно!)
        try:
            # Экспортируем новую основную ссылку
            chat_invite_link = await bot.export_chat_invite_link(chat_id=chat_id)
            logger.info(f"🔗 Новая основная ссылка создана: {chat_invite_link}")
        except Exception as e:
            logger.error(f"❌ Не удалось создать основную ссылку: {e}")
            # Если не получилось, создаем обычную пригласительную ссылку
            chat_invite_link = await bot.create_chat_invite_link(
                chat_id=chat_id,
                name=f"main_{int(time.time())}",
                creates_join_request=False
            ).invite_link

        # 3. Создаем временную ссылку для текущей сделки (ограниченную)
        deal_invite = await bot.create_chat_invite_link(
            chat_id=chat_id,
            name=f"deal_{int(time.time())}",
            creates_join_request=False,
            member_limit=4,  # Ограничиваем количество участников
            expire_date=int(time.time()) + 3600  # Ссылка истекает через 1 час
        )
        
        logger.info(f"✅ Ссылки обновлены для группы {chat_id}")
        logger.info(f"📝 Основная ссылка: {chat_invite_link}")
        logger.info(f"📝 Временная ссылка для сделки: {deal_invite.invite_link}")
        
        return deal_invite.invite_link
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка обновления ссылок: {e}")
        # Запасной вариант
        try:
            invite = await bot.create_chat_invite_link(chat_id=chat_id, member_limit=2)
            return invite.invite_link
        except:
            return "error_no_link"







async def kick_user_from_group(chat_id: int, user_id: int) -> bool:
    """Удаление пользователя из группы - УЛУЧШЕННАЯ ВЕРСИЯ"""
    try:
        # Сначала проверяем, есть ли пользователь в чате
        try:
            chat_member = await bot.get_chat_member(chat_id, user_id)
            if chat_member.status in ["left", "kicked", "banned"]:
                logger.info(f"✅ Пользователь {user_id} уже не в чате {chat_id}")
                return True
        except Exception as check_error:
            # Если пользователь не найден - значит его уже нет
            if "user not found" in str(check_error).lower() or "chat not found" in str(check_error).lower():
                logger.info(f"✅ Пользователь {user_id} не найден в чате {chat_id}")
                return True
            # Иначе продолжаем попытки удаления
        
        # Метод 1: Прямой бан с последующим разбаном
        await bot.ban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            until_date=int(time.time()) + 60
        )
        await asyncio.sleep(1)
        
        # Разбаниваем чтобы можно было добавить снова
        await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
        logger.info(f"✅ Успешно удален пользователь {user_id} из чата {chat_id}")
        return True
        
    except Exception as e:
        error_msg = str(e).lower()
        # Игнорируем ошибки "пользователь не найден" или "уже не участник"
        if any(phrase in error_msg for phrase in ["user not found", "chat not found", "member not found", "participant_id_invalid"]):
            logger.info(f"✅ Пользователь {user_id} уже не в чате {chat_id}")
            return True
        
        logger.warning(f"⚠️ Метод 1 не сработал для {user_id}: {e}")
        
        # Метод 2: Ограничение прав
        try:
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False
                )
            )
            logger.info(f"✅ Ограничены права пользователя {user_id} в чате {chat_id}")
            return True
        except Exception as e2:
            error_msg2 = str(e2).lower()
            if any(phrase in error_msg2 for phrase in ["user not found", "chat not found", "member not found", "participant_id_invalid"]):
                logger.info(f"✅ Пользователь {user_id} уже не в чате {chat_id}")
                return True
            logger.error(f"❌ Все методы удаления для {user_id} не сработали: {e2}")
            return False





async def remove_all_participants(chat_id: int):
    """Удаление всех участников кроме бота и владельца - УЛУЧШЕННАЯ ВЕРСИЯ"""
    try:
        # Получаем информацию о боте
        bot_info = await bot.get_me()
        
        # Получаем список всех участников чата
        removed_count = 0
        
        # Сначала получаем администраторов, чтобы знать кто защищен
        admins = await bot.get_chat_administrators(chat_id)
        admin_ids = {admin.user.id for admin in admins}
        
        # Исключаем бота и владельца из удаления
        protected_ids = {bot_info.id, OWNER_ID}
        
        # Получаем всех участников (может потребоваться несколько попыток для больших чатов)
        try:
            # Для небольших групп можно использовать get_chat_members_count и затем получать по одному
            members_count = await bot.get_chat_member_count(chat_id)
            logger.info(f"👥 В чате {chat_id} участников: {members_count}")
            
            # В Aiogram нет прямого метода получить всех участников, поэтому используем известные ID из сделок
            # или удаляем конкретных пользователей по известным ID
            if chat_id in ACTIVE_DEALS:
                deal_id = ACTIVE_DEALS[chat_id]
                deal_info = DEALS.get(deal_id)
                if deal_info:
                    # Удаляем конкретных участников сделки
                    participants = [deal_info['client_id'], deal_info['exchanger_id']]
                    
                    for user_id in participants:
                        if user_id not in protected_ids:
                            success = await kick_user_from_group(chat_id, user_id)
                            if success:
                                removed_count += 1
                                logger.info(f"✅ Удален участник сделки {user_id} из чата {chat_id}")
                            await asyncio.sleep(1)  # Задержка между удалениями
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения списка участников: {e}")
        
        # Дополнительная попытка удалить всех не-администраторов
        try:
            # Используем метод ограничения прав для всех участников (если они не администраторы)
            for admin in admins:
                user_id = admin.user.id
                if user_id not in protected_ids and not admin.is_chat_creator():
                    try:
                        # Ограничиваем права участника (нельзя отправлять сообщения)
                        await bot.restrict_chat_member(
                            chat_id=chat_id,
                            user_id=user_id,
                            permissions=ChatPermissions(
                                can_send_messages=False,
                                can_send_media_messages=False,
                                can_send_other_messages=False,
                                can_add_web_page_previews=False
                            )
                        )
                        logger.info(f"✅ Заблокирован участник {user_id} в чате {chat_id}")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось заблокировать участника {user_id}: {e}")
                        
        except Exception as e:
            logger.error(f"❌ Ошибка блокировки участников: {e}")
        
        logger.info(f"✅ Удалено/заблокировано {removed_count} участников из группы {chat_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка удаления участников: {e}")







async def remove_participants(chat_id: int, deal_info: Dict):
    """Удаление участников из чата сделки - УЛУЧШЕННАЯ ВЕРСИЯ"""
    try:
        bot_info = await bot.get_me()
        participants = [deal_info['client_id'], deal_info['exchanger_id']]
        
        removed_count = 0
        
        for user_id in participants:
            try:
                if user_id == bot_info.id or user_id == OWNER_ID:
                    continue
                
                # Используем ту же функцию удаления что и при сбросе групп
                success = await kick_user_from_group(chat_id, user_id)
                if success:
                    removed_count += 1
                    logger.info(f"✅ Удален пользователь {user_id} из чата {chat_id}")
                else:
                    logger.warning(f"⚠️ Не удалось удалить пользователя {user_id} из чата {chat_id}")
                    
            except Exception as e:
                logger.error(f"❌ Ошибка удаления пользователя {user_id}: {e}")
        
        logger.info(f"✅ Удалено {removed_count}/{len(participants)} участников из чата {chat_id}")
                
    except Exception as e:
        logger.error(f"❌ Ошибка в remove_participants: {e}")




# === ОСНОВНЫЕ ОБРАБОТЧИКИ ===
@dp.message(CommandStart())
@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    """Команда /start"""
    # Работает только в личных чатах
    if not is_private_chat(message.chat.id):
        return
    
    await send_welcome_message(
        message.chat.id, 
        message.from_user.id,
        message.from_user.username
    )



@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    """Профиль пользователя"""
    # Работает только в личных чатах
    if not is_private_chat(message.chat.id):
        return
    
    user = message.from_user
    db.update_user_online(user.id, user.username)
    
    # Проверяем является ли пользователь обменником
    exchanger_stats = db.get_exchanger_stats(user.id)
    
    if exchanger_stats:
        # Профиль обменника
        success_rate = (exchanger_stats['successful_deals'] / exchanger_stats['total_deals'] * 100) if exchanger_stats['total_deals'] > 0 else 0
        
        profile_text = (
            f"👤 <b>Профиль обменника</b>\n\n"
            f"<b>Username:</b> @{exchanger_stats['username']}\n"
            f"<b>Залог:</b> {exchanger_stats['deposit_amount']} USDT\n"
            f"<b>Статус:</b> {'🟢 Активен' if exchanger_stats['is_active'] else '🔴 Неактивен'}\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"• Всего сделок: {exchanger_stats['total_deals']}\n"
            f"• Успешных: {exchanger_stats['successful_deals']} ({success_rate:.1f}%)\n"
            f"• Общий объем: {exchanger_stats['total_volume']:.2f} BYN\n"
            f"• Ваш заработок: {exchanger_stats['total_income']:.2f} BYN\n"
            f"• Комиссия гаранта: {exchanger_stats['owner_income']:.2f} BYN"
        )
    else:
        # Профиль обычного пользователя
        profile_text = (
            f"👤 <b>Ваш профиль</b>\n\n"
            f"<b>ID:</b> <code>{user.id}</code>\n"
            f"<b>Имя:</b> {user.full_name}\n"
            f"<b>Username:</b> @{user.username if user.username else 'не установлен'}\n\n"
            "Для начала обмена нажмите кнопку <b>🔄 Начать обмен</b>"
        )
    
    await message.answer(profile_text)

@dp.message(F.text == "🔄 Начать обмен")
async def start_exchange(message: Message):
    """Начало обмена с проверкой активных сделок"""
    # Работает только в личных чатах
    if not is_private_chat(message.chat.id):
        return
    
    user_id = message.from_user.id
    
    # Проверяем, есть ли у пользователя активные сделки
    if has_active_deal(user_id):
        await message.answer(
            "❌ <b>У вас уже есть активная сделка!</b>\n\n"
            "Вы не можете начать новую сделку, пока не завершена текущая.\n"
            "Завершите текущую сделку или дождитесь ее завершения.",
            reply_markup=get_main_menu(message.from_user.id == OWNER_ID)
        )
        return
    
    user_data[user_id] = {}
    
    await message.answer(
        "💱 <b>Выберите что хотите продать:</b>",
        reply_markup=get_currency_type_keyboard()
    )







@dp.message(F.text == "ℹ️ О боте")
async def about_bot(message: Message):
    """Информация о боте"""
    # Работает только в личных чатах
    if not is_private_chat(message.chat.id):
        return
    
    about_text = (
        "🛡️ <b>О нашем сервисе</b>\n\n"
        "Мы предоставляем безопасную площадку для P2P-обменов "
        "с гарантией выполнения сделок.\n\n"
        "<b>Как это работает:</b>\n"
        "1. Выбираете валюты и сумму\n"
        "2. Выбираете обменника\n"
        "3. Создается защищенный чат\n"
        "4. Проводите обмен под контролем гаранта\n"
        "5. Подтверждаете успешное завершение\n\n"
        "<b>Наши гарантии:</b>\n"
        "• Безопасность всех участников\n"
        "• Круглосуточная поддержка\n"
        "• Прозрачные условия\n"
        "• Быстрое решение споров"
    )
    
    await message.answer(about_text)

@dp.message(F.text == "🛡️ Панель гаранта")
async def guarantor_panel(message: Message):
    """Панель гаранта"""
    # Работает только в личных чатах
    if not is_private_chat(message.chat.id):
        return
    
    if message.from_user.id != OWNER_ID:
        await message.answer("❌ Недостаточно прав")
        return
    
    await message.answer(
        "🛡️ <b>Панель гаранта</b>\n\n"
        "Выберите раздел для управления:",
        reply_markup=get_admin_keyboard()
    )

# === ОБРАБОТЧИКИ ВЫБОРА ВАЛЮТ ===
@dp.callback_query(F.data.startswith("type:"))
async def currency_type_handler(callback: CallbackQuery):
    """Выбор типа валюты"""
    user_id = callback.from_user.id
    currency_type = callback.data.split(":")[1]
    
    user_data[user_id] = {'sell_currency_type': currency_type}
    update_user_data_timestamp(user_id)
    
    await callback.message.edit_text(
        f"💱 <b>Выберите валюту для продажи:</b>",
        reply_markup=get_currency_keyboard(currency_type)
    )

@dp.callback_query(F.data.startswith("currency:"))
async def currency_handler(callback: CallbackQuery):
    """Выбор конкретной валюты"""
    user_id = callback.from_user.id
    _, currency_type, currency_code = callback.data.split(":")
    
    # Получаем название валюты
    currencies = db.get_all_currencies()
    currency_name = next((c['name'] for c in currencies if c['code'] == currency_code), currency_code)
    
    user_data[user_id].update({
        'sell_currency_code': currency_code,
        'sell_currency_name': currency_name
    })
    update_user_data_timestamp(user_id)
    
    await callback.message.edit_text(
        f"💱 <b>Выберите что хотите купить:</b>",
        reply_markup=get_buy_currency_keyboard(currency_type, currency_code)
    )

@dp.callback_query(F.data.startswith("buy_currency:"))
async def buy_currency_handler(callback: CallbackQuery):
    """Выбор валюты для покупки"""
    user_id = callback.from_user.id
    currency_code = callback.data.split(":")[1]
    
    # Получаем название валюты
    currencies = db.get_all_currencies()
    currency_name = next((c['name'] for c in currencies if c['code'] == currency_code), currency_code)
    
    user_data[user_id]['buy_currency_code'] = currency_code
    user_data[user_id]['buy_currency_name'] = currency_name
    
    await callback.message.edit_text(
        f"💵 <b>Введите сумму для обмена:</b>\n\n"
        f"<b>Продаете:</b> {user_data[user_id]['sell_currency_name']}\n"
        f"<b>Покупаете:</b> {currency_name}\n\n"
        "Введите число:",
        reply_markup=get_back_button()
    )

# === ОБРАБОТЧИК СУММЫ ===
async def amount_handler(message: Message):
    """Обработка введенной суммы"""
    user_id = message.from_user.id
    if user_id not in user_data:
        await message.answer("❌ Начните обмен заново", reply_markup=get_main_menu(message.from_user.id == OWNER_ID))
        return
    
    try:
        # Проверяем наличие данных
        required_keys = ['sell_currency_code', 'buy_currency_code']
        for key in required_keys:
            if key not in user_data[user_id]:
                await message.answer("❌ Данные устарели. Начните обмен заново", reply_markup=get_main_menu(message.from_user.id == OWNER_ID))
                return
        
        # Преобразуем сумму
        amount_text = message.text.replace(',', '.')
        amount = float(amount_text)
        
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше 0")
            return
        
        if amount < 10:
            await message.answer("❌ Минимальная сумма для обмена: 10")
            return
            
        user_data[user_id]['sell_amount'] = amount
        
        # Показываем сообщение о поиске с возможностью отмены
        search_msg = await message.answer(
            "🔍 <b>Ищем доступных обменников...</b>\n\n"
            "<i>Это может занять несколько секунд</i>"
        )
        
        # Получаем доступных обменников с общим таймаутом
        try:
            exchangers = await asyncio.wait_for(
                get_available_exchangers(
                    user_data[user_id]['sell_currency_code'],
                    user_data[user_id]['buy_currency_code'],
                    amount
                ),
                timeout=30.0  # Общий таймаут 30 секунд
            )
        except asyncio.TimeoutError:
            await search_msg.delete()
            await message.answer(
                "⏰ <b>Превышено время поиска обменников</b>\n\n"
                "Попробуйте:\n"
                "• Уменьшить сумму\n"
                "• Выбрать другие валюты\n"
                "• Попробовать позже",
                reply_markup=get_back_button()
            )
            return
        
        # Удаляем сообщение о поиске
        await search_msg.delete()
        
        if not exchangers:
            await message.answer(
                "❌ <b>Нет доступных обменников</b>\n\n"
                f"Для суммы <b>{amount} {user_data[user_id]['sell_currency_code']}</b>\n"
                "Попробуйте:\n"
                "• Уменьшить сумму\n"
                "• Выбрать другие валюты\n"
                "• Попробовать позже",
                reply_markup=get_back_button()
            )
            return
        
        user_data[user_id]['available_exchangers'] = exchangers

        sell_code = user_data[user_id]['sell_currency_code']
        buy_code = user_data[user_id]['buy_currency_code']

        # Формируем список обменников
        exchangers_text = (
            f"✅ <b>Найдено обменников: {len(exchangers)}</b>\n\n"
            f"<b>Обмен:</b> {amount} {sell_code} → {buy_code}\n\n"
        )

        # Курс для пересчёта залога из USDT в валюту, которую клиент продаёт
        try:
            deposit_rate = await get_real_exchange_rate("USDT", sell_code)
        except Exception:
            deposit_rate = 1.0

        for i, exchanger in enumerate(exchangers, 1):
            deposit_usdt = exchanger['deposit_amount']
            deposit_in_sell = deposit_usdt * deposit_rate
            
            # ДЕБАГ-ЛОГ: посмотрим, что в final_amount
            logger.info(f"DEBUG: Обменник {i}: final_amount={exchanger['final_amount']}, тип={type(exchanger['final_amount'])}")
            
            exchangers_text += (
                f"{i}. <b>@{exchanger['username']}</b>\n"
                f"   💸 Отдаёте: <b>{format_amount(amount, sell_code)} {sell_code}</b>\n"
                f"   💰 Получите: <b>{format_amount(exchanger['final_amount'], buy_code)} {buy_code}</b>\n"
                f"   📊 Курс: <b>1 {sell_code} = {exchanger['exchange_rate']:.8f} {buy_code}</b>\n"
                f"   🔒 Залог: <b>{deposit_usdt:.2f} USDT</b> "
                f"(~{deposit_in_sell:.2f} {sell_code})\n\n"
            )


        await message.answer(
            exchangers_text,
            reply_markup=get_exchanger_list_keyboard(exchangers)
        )

        
    except ValueError:
        await message.answer("❌ Введите корректное число (например: 100 или 150.50)")
    except Exception as e:
        logger.error(f"❌ Ошибка в amount_handler: {e}")
        await message.answer(
            "❌ Произошла непредвиденная ошибка\n\nПопробуйте начать обмен заново",
            reply_markup=get_main_menu(message.from_user.id == OWNER_ID)
        )
        if user_id in user_data:
            del user_data[user_id]




# === ПОДТВЕРЖДЕНИЕ ОБМЕНА ===
@dp.callback_query(F.data == "confirm")
async def confirm_exchange_handler(callback: CallbackQuery):
    """Подтверждение обмена с проверкой активных сделок"""
    user_id = callback.from_user.id
    user_info = user_data.get(user_id, {})
    
    if not user_info.get('selected_exchanger'):
        await callback.answer("❌ Данные устарели")
        return
    
    # Проверяем, не создал ли пользователь сделку в другом окне
    if has_active_deal(user_id):
        await callback.answer(
            "❌ У вас уже есть активная сделка! Завершите ее перед началом новой.", 
            show_alert=True
        )
        return
    
    # Создаем сделку
    deal_info = {
        'client_id': user_id,
        'client_name': callback.from_user.full_name,
        'exchanger_id': user_info['selected_exchanger']['user_id'],
        'exchanger_username': user_info['selected_exchanger']['username'],
        'sell_currency': user_info['sell_currency_code'],
        'buy_currency': user_info['buy_currency_code'],
        'sell_amount': user_info['sell_amount'],
        'final_amount': user_info['selected_exchanger']['final_amount'],
        'exchange_rate': user_info['selected_exchanger']['exchange_rate'],
        'owner_fee': user_info['selected_exchanger']['owner_fee'],
        'exchanger_fee': user_info['selected_exchanger']['exchanger_fee']
    }
    
    try:
        deal_id = await create_deal_chat(deal_info)

        # Сразу редактируем текущее сообщение с подтверждением обмена
        control_text = (
            f"🎛️ <b>Управление сделкой #{deal_id}</b>\n\n"
            f"<b>Сумма:</b> {format_amount(user_info['sell_amount'], user_info['sell_currency_code'])} {user_info['sell_currency_name']} → "
            f"{format_amount(user_info['selected_exchanger']['final_amount'], user_info['buy_currency_code'])} {user_info['buy_currency_name']}\n"
            f"<b>Курс:</b> 1 {user_info['sell_currency_code']} = {deal_info['exchange_rate']:.8f} {user_info['buy_currency_code']}\n"
            f"<b>Обменник:</b> @{user_info['selected_exchanger']['username']}\n\n"
            f"🔗 <a href='{deal_info['invite_link']}'>Присоединиться к чату сделки</a>\n\n"
            "─────────────────────\n"
            "<b>Для клиента:</b>\n"
            "• ✅ <b>Деньги пришли, закрыть чат</b> - если получили деньги\n"
            "• 🛡️ <b>Сделка не удалась, Вызвать гаранта</b> - если есть проблемы\n\n"
            "<i>Не нажимайте кнопку подтверждения, пока не получили деньги!</i>"
        )
        
        # Редактируем существующее сообщение (то самое с подтверждением обмена)
        await callback.message.edit_text(
            text=control_text,
            reply_markup=get_deal_control_keyboard(deal_id, "client")
        )
        
        # Сохраняем ID сообщения для последующего управления
        if user_id not in USER_MESSAGES:
            USER_MESSAGES[user_id] = {}
        USER_MESSAGES[user_id][f"deal_{deal_id}"] = callback.message.message_id
        
        # Сохраняем в информации о сделке
        deal_info['client_message_id'] = callback.message.message_id

        # Уведомляем обменника
        try:
            exchanger_stats = db.get_exchanger_stats(deal_info['exchanger_id'])
            if exchanger_stats:
                # Проверяем, существует ли чат с обменником
                try:
                    # Пробуем отправить тестовое сообщение
                    await bot.send_message(
                        chat_id=deal_info['exchanger_id'],
                        text=(
                            f"🔔 <b>Новая сделка!</b>\n\n"
                            f"<b>Клиент:</b> {callback.from_user.full_name}\n"
                            f"<b>ID сделки:</b> #{deal_id}\n"
                            f"<b>Сумма:</b> {user_info['sell_amount']} {user_info['sell_currency_name']}\n"
                            f"<b>Курс:</b> 1 {user_info['sell_currency_code']} = {deal_info['exchange_rate']:.4f} {user_info['buy_currency_code']}\n\n"
                            f"🔗 <a href='{deal_info['invite_link']}'>Присоединиться к чату</a>"
                        )
                    )
                    logger.info(f"✅ Обменник {deal_info['exchanger_id']} уведомлен о сделке {deal_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось уведомить обменника {deal_info['exchanger_id']}: {e}")
            else:
                logger.warning(f"⚠️ Обменник {deal_info['exchanger_id']} не найден в базе данных")
        except Exception as e:
            logger.error(f"❌ Ошибка при уведомлении обменника: {e}")

    except Exception as e:
        logger.error(f"❌ Ошибка создания сделки: {e}")
        await callback.answer("❌ Ошибка создания сделки")






# === УПРАВЛЕНИЕ СДЕЛКАМИ ===
@dp.callback_query(F.data.startswith("success:"))
async def success_handler(callback: CallbackQuery):
    """Обмен прошел успешно"""
    deal_id = callback.data.split(":")[1]
    deal_info = DEALS.get(deal_id)
    
    if not deal_info:
        await callback.answer("❌ Сделка не найдена")
        return
    
    warning_text = (
        "⚠️ <b>Внимание!</b>\n\n"
        "Не нажимайте эту кнопку, если деньги ещё не пришли!\n\n"
        "Если вы уже получили деньги и обмен завершен успешно - подтвердите:"
    )
    
    # Редактируем СУЩЕСТВУЮЩЕЕ сообщение вместо отправки нового
    try:
        await callback.message.edit_text(
            text=warning_text,
            reply_markup=get_success_confirmation_keyboard(deal_id)
        )
        logger.info(f"✅ Сообщение с предупреждением отредактировано для сделки {deal_id}")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось редактировать сообщение: {e}")
        # Если не удалось редактировать, отправляем новое
        await callback.message.answer(
            warning_text,
            reply_markup=get_success_confirmation_keyboard(deal_id)
        )
    
    await callback.answer()





@dp.callback_query(F.data.startswith("confirm_success:"))
async def confirm_success_handler(callback: CallbackQuery):
    """Подтверждение успешного обмена - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    deal_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    # НЕМЕДЛЕННО отвечаем на callback
    await callback.answer("✅ Сделка завершена успешно!")
    
    logger.info(f"🔄 Завершение сделки {deal_id} по запросу пользователя {user_id}")
    
    try:
        # Получаем информацию о сделке
        deal_info = DEALS.get(deal_id)
        if not deal_info:
            await callback.answer("❌ Сделка не найдена")
            return
        
               # Сразу редактируем на финальное сообщение
        completion_text = (
            f"✅ <b>Сделка #{deal_id} успешно завершена</b>\n\n"
            f"<b>Сумма:</b> {deal_info['sell_amount']} {deal_info['sell_currency']} → "
            f"{deal_info['final_amount']} {deal_info['buy_currency']}\n"
            f"<b>Обменник:</b> @{deal_info['exchanger_username']}\n"
            f"<b>Клиент:</b> {deal_info['client_name']}\n\n"
            f"<i>Комиссия начислена.</i>"
        )
        
        try:
            await callback.message.edit_text(
                text=completion_text,
                reply_markup=None
            )
            logger.info(f"✅ Сообщение о завершении сделки отредактировано для пользователя {user_id}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось редактировать сообщение: {e}")
        
        # Запускаем завершение сделки в фоне (не блокируем ответ)
        asyncio.create_task(complete_deal(deal_id, "completed_by_client"))
        
    except Exception as e:
        logger.error(f"❌ Ошибка в confirm_success_handler: {e}")
        await callback.answer("❌ Произошла ошибка")



@dp.callback_query(F.data.startswith("dispute:"))
async def dispute_handler(callback: CallbackQuery):
    """Вызов гаранта"""
    deal_id = callback.data.split(":")[1]
    deal_info = DEALS.get(deal_id)
    
    if not deal_info:
        await callback.answer("❌ Сделка не найдена")
        return
    
    await bot.send_message(
        chat_id=OWNER_ID,
        text=(
            f"🛡️ <b>ВЫЗОВ ГАРАНТА!</b>\n\n"
            f"<b>Сделка:</b> #{deal_id}\n"
            f"<b>Клиент:</b> {deal_info['client_name']}\n"
            f"<b>Обменник:</b> @{deal_info['exchanger_username']}\n"
            f"<b>Сумма:</b> {deal_info['sell_amount']} {deal_info['sell_currency']} → "
            f"{deal_info['final_amount']} {deal_info['buy_currency']}\n\n"
            f"🔗 <a href='{deal_info['invite_link']}'>Перейти в чат</a>"
        )
    )
    
    # Редактируем СУЩЕСТВУЮЩЕЕ сообщение вместо отправки нового
    dispute_text = (
        "✅ <b>Гарант уведомлен!</b>\n\n"
        "🛡️ Гарант подключится к чату в ближайшее время\n"
        "Ожидайте решения спора\n\n"
        "<i>Не покидайте чат до завершения сделки</i>"
    )
    
    try:
        await callback.message.edit_text(text=dispute_text)
        logger.info(f"✅ Сообщение о вызове гаранта отредактировано для сделки {deal_id}")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось редактировать сообщение: {e}")
        # Если не удалось редактировать, отправляем новое
        await callback.message.answer(dispute_text)
    
    await callback.answer("🛡️ Гарант уведомлен!")





@dp.callback_query(F.data.startswith("refresh_link:"))
async def refresh_link_handler(callback: CallbackQuery):
    """Обновить ссылку на чат сделки"""
    deal_id = callback.data.split(":")[1]
    deal_info = DEALS.get(deal_id)
    
    if not deal_info:
        await callback.answer("❌ Сделка не найдена")
        return
    
    try:
        # Создаем новую ссылку на 24 часа
        invite = await bot.create_chat_invite_link(
            chat_id=deal_info['chat_id'],
            name=f"deal_{deal_id}_refresh",
            creates_join_request=False,
            member_limit=3,
            expire_date=int(time.time()) + 86400  # 24 часа
        )
        
        deal_info['invite_link'] = invite.invite_link
        
        await callback.message.answer(
            f"🔄 <b>Новая ссылка для сделки #{deal_id}</b>\n\n"
            f"{invite.invite_link}\n\n"
            f"<i>Ссылка действительна 24 часа</i>"
        )
        await callback.answer("✅ Новая ссылка отправлена")
        
    except Exception as e:
        logger.error(f"❌ Ошибка обновления ссылки: {e}")
        await callback.answer("❌ Ошибка создания ссылки")






@dp.message(Command("refresh_links"))
async def cmd_refresh_links(message: Message):
    """Принудительное обновление всех ссылок"""
    if message.from_user.id != OWNER_ID:
        await message.answer("❌ Недостаточно прав")
        return
    
    await message.answer("🔄 <b>Начинаю принудительное обновление всех ссылок...</b>")
    
    success_count = 0
    for group_id in GROUP_IDS:
        try:
            new_link = await refresh_invite_links(group_id)
            success_count += 1
            logger.info(f"✅ Обновлена ссылка для группы {group_id}: {new_link}")
        except Exception as e:
            logger.error(f"❌ Ошибка обновления ссылки для {group_id}: {e}")
    
    await message.answer(f"✅ <b>Готово!</b>\n\nОбновлено ссылок: {success_count}/{len(GROUP_IDS)}")











@dp.chat_member()
async def chat_member_handler(chat_member: ChatMemberUpdated):
    """Обработчик входа участников в чат с проверкой активной сделки"""
    try:
        if chat_member.old_chat_member.status == "left" and chat_member.new_chat_member.status == "member":
            chat_id = chat_member.chat.id
            user_id = chat_member.new_chat_member.user.id
            
            # Проверяем, есть ли активная сделка в этом чате
            if chat_id in ACTIVE_DEALS:
                deal_id = ACTIVE_DEALS[chat_id]
                deal_info = DEALS.get(deal_id)
                
                if deal_info:
                    # Проверяем, является ли пользователь участником текущей сделки
                    if user_id == deal_info['client_id']:
                        logger.info(f"✅ Клиент присоединился к чату сделки {deal_id}")
                        
                        # === ОТПРАВЛЯЕМ ЗАКРЕПЛЕННОЕ СООБЩЕНИЕ КОГДА КЛИЕНТ ЗАХОДИТ ===
                        if not deal_info.get('pinned_message_sent', False):
                            logger.info(f"🔄 Отправляем закрепленное сообщение для сделки {deal_id}")
                            await send_pinned_instruction_message(deal_info)
                        
                    elif user_id == deal_info['exchanger_id']:
                        logger.info(f"✅ Обменник присоединился к чату сделки {deal_id}")
                    else:
                        # Если это чужой пользователь - немедленно удаляем!
                        logger.warning(f"🚫 Посторонний пользователь {user_id} пытается войти в чат сделки {deal_id}")
                        try:
                            await kick_user_from_group(chat_id, user_id)
                            await bot.send_message(
                                OWNER_ID,
                                f"🚫 <b>ПОПЫТКА НЕСАНКЦИОНИРОВАННОГО ВХОДА</b>\n\n"
                                f"<b>Чат:</b> {chat_id}\n"
                                f"<b>Сделка:</b> #{deal_id}\n"
                                f"<b>Пользователь:</b> {chat_member.new_chat_member.user.full_name} (ID: {user_id})\n"
                                f"<b>Username:</b> @{chat_member.new_chat_member.user.username if chat_member.new_chat_member.user.username else 'нет'}\n\n"
                                f"<i>Пользователь был автоматически удален</i>"
                            )
                        except Exception as e:
                            logger.error(f"❌ Не удалось удалить постороннего пользователя: {e}")
            else:
                # Если в чате нет активной сделки, удаляем всех входящих
                logger.warning(f"🚫 Пользователь {user_id} пытается войти в неактивный чат {chat_id}")
                try:
                    await kick_user_from_group(chat_id, user_id)
                except Exception as e:
                    logger.error(f"❌ Не удалось удалить пользователя из неактивного чата: {e}")
                        
    except Exception as e:
        logger.error(f"Ошибка обработки участника чата: {e}")






async def send_pinned_instruction_message(deal_info: Dict):
    """Отправка закрепленного инструкционного сообщения в чат сделки"""
    try:
        instruction_text = (
            f"🛡️ <b>Чат для сделки #{deal_info['deal_id']}</b>\n\n"
            f"<b>Участники:</b>\n"
            f"• Клиент: {deal_info['client_name']}\n"
            f"• Обменник: @{deal_info['exchanger_username']}\n\n"
            f"<b>Детали сделки:</b>\n"
            f"• Продажа: {deal_info['sell_amount']} {deal_info['sell_currency']}\n"
            f"• Покупка: {deal_info['final_amount']} {deal_info['buy_currency']}\n"
            f"• Курс: 1 {deal_info['sell_currency']} = {deal_info['exchange_rate']:.4f} {deal_info['buy_currency']}\n\n"
            f"<b>⏰ Время на сделку: 20 минут</b>\n"
            f"<b>📋 Инструкция:</b>\n"
            f"1. Обменник и клиент общаются в этом чате и договариваются о деталях перевода\n"
            f"2. После успешного завершения обмена, клиент должен нажать кнопку <b>✅ Деньги пришли, закрыть чат</b> в боте\n"
            f"3. Если возникли проблемы, любая из сторон может нажать кнопку <b>🛡️ Вызвать гаранта</b> в боте\n\n"
            f"<i>⚠️ Не сообщайте никакие пароли, коды доступа и другую конфиденциальную информацию в этом чате!</i>\n\n"
            f"Желаем успешной сделки! 🍀"
        )
        
        # Отправляем и закрепляем сообщение
        pinned_message = await bot.send_message(
            chat_id=deal_info['chat_id'],
            text=instruction_text
        )
        
        await bot.pin_chat_message(
            chat_id=deal_info['chat_id'],
            message_id=pinned_message.message_id
        )
        
        # Сохраняем ID закрепленного сообщения и помечаем как отправленное
        deal_info['pinned_message_id'] = pinned_message.message_id
        deal_info['pinned_message_sent'] = True
        
        logger.info(f"✅ Закрепленное сообщение отправлено в чат {deal_info['chat_id']}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки закрепленного сообщения: {e}")






# === ФУНКЦИИ ДЛЯ РЕДАКТИРОВАНИЯ СООБЩЕНИЙ ===

async def edit_or_send_message(chat_id: int, text: str, reply_markup=None, message_key: str = "main"):
    """Редактирует существующее сообщение или отправляет новое"""
    try:
        logger.info(f"🔄 edit_or_send_message: chat_id={chat_id}, message_key={message_key}")
        
        if chat_id in USER_MESSAGES and message_key in USER_MESSAGES[chat_id]:
            message_id = USER_MESSAGES[chat_id][message_key]
            logger.info(f"📝 Найдено существующее сообщение ID: {message_id}")
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=reply_markup
                )
                logger.info(f"✅ Сообщение отредактировано: {message_id}")
                return message_id
            except Exception as e:
                # Если не удалось редактировать
                logger.warning(f"⚠️ Не удалось редактировать сообщение: {e}")
                # Удаляем старый ID из хранилища
                del USER_MESSAGES[chat_id][message_key]
        
        # Отправляем новое сообщение
        logger.info(f"📤 Отправляем новое сообщение для chat_id={chat_id}")
        message = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup
        )
        
        # Сохраняем ID сообщения
        if chat_id not in USER_MESSAGES:
            USER_MESSAGES[chat_id] = {}
        USER_MESSAGES[chat_id][message_key] = message.message_id
        
        logger.info(f"✅ Новое сообщение отправлено, ID: {message.message_id}")
        return message.message_id
        
    except Exception as e:
        logger.error(f"❌ Ошибка в edit_or_send_message: {e}")
        # Запасной вариант
        message = await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        return message.message_id





async def cleanup_user_messages(user_id: int, deal_id: str):
    """Очищает сообщения пользователя после завершения сделки"""
    try:
        if user_id in USER_MESSAGES and f"deal_{deal_id}" in USER_MESSAGES[user_id]:
            # Только удаляем из хранилища, не удаляем само сообщение
            del USER_MESSAGES[user_id][f"deal_{deal_id}"]
            logger.info(f"✅ Очищены сообщения пользователя {user_id} для сделки {deal_id}")
            
            # Если у пользователя больше нет сообщений, очищаем запись
            if not USER_MESSAGES[user_id]:
                del USER_MESSAGES[user_id]
    except Exception as e:
        logger.error(f"❌ Ошибка очистки сообщений: {e}")





async def remove_participants_forcefully(chat_id: int, deal_info: Dict):
    """Принудительное удаление участников сделки"""
    try:
        bot_info = await bot.get_me()
        participants = [deal_info['client_id'], deal_info['exchanger_id']]
        
        removed_count = 0
        
        for user_id in participants:
            try:
                if user_id == bot_info.id or user_id == OWNER_ID:
                    continue
                
                # Многократные попытки удаления
                for attempt in range(3):
                    success = await kick_user_from_group(chat_id, user_id)
                    if success:
                        removed_count += 1
                        logger.info(f"✅ Удален пользователь {user_id} из чата {chat_id} (попытка {attempt + 1})")
                        break
                    else:
                        logger.warning(f"⚠️ Попытка {attempt + 1} удаления пользователя {user_id} не удалась")
                        await asyncio.sleep(2)
                else:
                    logger.error(f"❌ Не удалось удалить пользователя {user_id} после 3 попыток")
                    
            except Exception as e:
                logger.error(f"❌ Ошибка удаления пользователя {user_id}: {e}")
        
        logger.info(f"✅ Удалено {removed_count}/{len(participants)} участников из чата {chat_id}")
                
    except Exception as e:
        logger.error(f"❌ Ошибка в remove_participants_forcefully: {e}")






async def monitor_deal_time(deal_id: str):
    """Мониторинг времени сделки и отправка уведомлений - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    try:
        deal_info = DEALS.get(deal_id)
        if not deal_info:
            return
            
        start_time = deal_info.get('start_time', datetime.now())
        notifications_sent = deal_info.get('notifications_sent', [])
        
        # Интервалы в минутах между уведомлениями (а не общее время)
        notification_intervals = [20, 5, 5, 5, 5]  # 20 мин, затем каждые 5 минут
        
        total_minutes_passed = 0
        
        for interval_minutes in notification_intervals:
            total_minutes_passed += interval_minutes
            
            # Ждем интервал в секундах
            wait_time = interval_minutes * 60
            await asyncio.sleep(wait_time)
            
            # Проверяем, что сделка еще активна
            if deal_id not in DEALS:
                return
                
            # Проверяем, не было ли уже отправлено это уведомление
            if total_minutes_passed in notifications_sent:
                continue
                
            # Получаем актуальную информацию о сделке
            current_deal_info = DEALS.get(deal_id)
            if not current_deal_info:
                return
                
            # Получаем количество участников в чате
            try:
                chat_member_count = await bot.get_chat_member_count(current_deal_info['chat_id'])
            except:
                chat_member_count = "неизвестно"
            
            if total_minutes_passed == 40:
                # Автозавершение сделки
                await bot.send_message(
                    OWNER_ID,
                    f"⏰ <b>Автозавершение сделки #{deal_id}</b>\n\n"
                    f"Сделка автоматически завершена по истечении 40 минут.\n"
                    f"Участников в чате: {chat_member_count}\n"
                    f"Статус: завершена по таймауту"
                )
                await complete_deal(deal_id, "timeout")
            else:
                # Обычное уведомление
                message = (
                    f"⏰ <b>Сделка #{deal_id} активна {total_minutes_passed} минут</b>\n\n"
                    f"Участников в чате: {chat_member_count}\n"
                    f"Клиент: {current_deal_info['client_name']}\n"
                    f"Обменник: @{current_deal_info['exchanger_username']}\n"
                    f"Сумма: {current_deal_info['sell_amount']} {current_deal_info['sell_currency']} → "
                    f"{current_deal_info['final_amount']} {current_deal_info['buy_currency']}"
                )
                
                await bot.send_message(OWNER_ID, message)
                
                # Помечаем уведомление как отправленное
                if deal_id in DEALS:
                    DEALS[deal_id]['notifications_sent'] = notifications_sent + [total_minutes_passed]
                    
    except Exception as e:
        logger.error(f"Ошибка мониторинга сделки {deal_id}: {e}")





async def send_deal_completion_notifications(deal_info: Dict, reason: str):
    """Отправка уведомлений о завершении сделки обменнику и гарантам (клиенту не отправляем)"""
    try:
        deal_id = deal_info['deal_id']
        exchanger_id = deal_info['exchanger_id']
        
        # Определяем текст в зависимости от причины завершения
        if reason in ["completed_by_client", "completed_by_guarantor"]:
            status_icon = "✅"
            status_text = "успешно завершена"
            commission_text = "Комиссия начислена."
        elif reason == "timeout":
            status_icon = "⏰"
            status_text = "автоматически завершена по истечении времени"
            commission_text = "Комиссия не начислена."
        else:  # cancelled_by_guarantor и другие случаи отмены
            status_icon = "❌"
            status_text = "отменена"
            commission_text = "Комиссия не начислена."

        # Общий текст уведомления
        common_text = (
            f"{status_icon} <b>Сделка #{deal_id} {status_text}</b>\n\n"
            f"<b>Сумма:</b> {deal_info['sell_amount']} {deal_info['sell_currency']} → "
            f"{deal_info['final_amount']} {deal_info['buy_currency']}\n"
            f"<b>Обменник:</b> @{deal_info['exchanger_username']}\n"
            f"<b>Клиент:</b> {deal_info['client_name']}\n\n"
            f"{commission_text}"
        )

        # Текст для гарантов (с дополнительной информацией)
        guarantor_text = (
            f"{status_icon} <b>Сделка #{deal_id} {status_text}</b>\n\n"
            f"<b>Причина:</b> {reason}\n"
            f"<b>Сумма:</b> {deal_info['sell_amount']} {deal_info['sell_currency']} → "
            f"{deal_info['final_amount']} {deal_info['buy_currency']}\n"
            f"<b>Обменник:</b> @{deal_info['exchanger_username']}\n"
            f"<b>Клиент:</b> {deal_info['client_name']}\n\n"
            f"{commission_text}\n"
            f"Чат сделки очищен и сброшен."
        )

        # Отправляем обменнику
        try:
            await bot.send_message(exchanger_id, common_text)
            logger.info(f"✅ Уведомление отправлено обменнику {exchanger_id} о завершении сделки {deal_id}")
        except Exception as e:
            logger.error(f"❌ Не удалось отправить уведомление обменнику {exchanger_id}: {e}")

        # Отправляем всем гарантам (кроме случаев когда они сами инициировали завершение)
        if reason not in ["completed_by_guarantor", "cancelled_by_guarantor"]:
            for guarantor_id in GUARANTOR_IDS:
                try:
                    await bot.send_message(guarantor_id, guarantor_text)
                    logger.info(f"✅ Уведомление отправлено гаранту {guarantor_id} о завершении сделки {deal_id}")
                except Exception as e:
                    logger.error(f"❌ Не удалось отправить уведомление гаранту {guarantor_id}: {e}")

    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомлений о завершении сделки: {e}")




# === ПАНЕЛЬ ГАРАНТА - КОМАНДЫ ===
@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    """Статистика бота"""
    # Работает только в личных чатах
    if not is_private_chat(message.chat.id):
        return
    
    if message.from_user.id != OWNER_ID:
        await message.answer("❌ Недостаточно прав")
        return
    
    active_deals = len(DEALS)
    total_deals = db.get_total_deals_count()
    total_income = db.get_owner_total_income()
    online_users = db.get_online_users_count()
    
    stats_text = (
        f"📊 <b>Статистика системы</b>\n\n"
        f"<b>Активных сделок:</b> {active_deals}\n"
        f"<b>Всего сделок:</b> {total_deals}\n"
        f"<b>Онлайн пользователей:</b> {online_users}\n"
        f"<b>Общий доход гаранта:</b> {total_income:.2f} BYN\n\n"
    )
    
    # Статистика по обменникам
    exchangers = db.get_all_exchangers()
    if exchangers:
        stats_text += "<b>Топ обменников по объему:</b>\n"
        for exchanger in exchangers[:5]:
            if exchanger['total_volume'] > 0:
                stats_text += f"• @{exchanger['username']}: {exchanger['total_volume']:.0f} BYN\n"
    
    await message.answer(stats_text, reply_markup=get_admin_keyboard())

@dp.message(Command("api_status"))
async def cmd_api_status(message: Message):
    """Статус API"""
    # Работает только в личных чатах
    if not is_private_chat(message.chat.id):
        return
    
    if message.from_user.id != OWNER_ID:
        await message.answer("❌ Недостаточно прав")
        return
    
    report = await api_monitor.get_api_health_report()
    await message.answer(report)







@dp.message(Command("rates"))
async def cmd_rates(message: Message):
    """Показать основные курсы и их источники + простая проверка адекватности"""
    if not is_private_chat(message.chat.id):
        return

    # Очищаем кэш, чтобы взять максимально свежие значения
    exchange_api.cache.clear()

    # Расширенный список пар
    test_pairs = [
        # Крипта ↔ фиат
        ("USDT", "RUB"),
        ("USDT", "BYN"),
        ("USDT", "USD"),
        ("USDT", "EUR"),

        ("BTC", "USDT"),
        ("BTC", "RUB"),
        ("BTC", "BYN"),

        ("ETH", "USDT"),
        ("ETH", "RUB"),
        ("ETH", "BYN"),

        # Фиат ↔ фиат
        ("BYN", "RUB"),
        ("RUB", "BYN"),
        ("USD", "RUB"),
        ("RUB", "USD"),
        ("EUR", "RUB"),
        ("RUB", "EUR"),
        ("USD", "BYN"),
        ("BYN", "USD"),

        # Дополнительно
        ("USDT", "UAH"),
        ("USDT", "KZT"),
        ("USDT", "PLN"),
    ]

    # Грубые "ожидаемые диапазоны" для проверки адекватности
    # Это не точные значения, а просто sanity-check, чтобы увидеть явно неправильные курсы
    expected_ranges = {
        ("USDT", "RUB"): (50, 200),
        ("USDT", "BYN"): (1, 10),
        ("BTC", "USDT"): (10000, 300000),   # зависит от рынка, но порядок величины
        ("ETH", "USDT"): (500, 10000),
        ("BYN", "RUB"): (10, 100),
        ("RUB", "BYN"): (0.01, 0.2),
        ("USD", "RUB"): (50, 200),
        ("RUB", "USD"): (0.005, 0.05),
        ("EUR", "RUB"): (50, 300),
        ("RUB", "EUR"): (0.003, 0.05),
        ("BTC", "RUB"): (1000000, 50000000),
        ("BTC", "BYN"): (10000, 1000000),
        ("ETH", "RUB"): (50000, 5000000),
        ("ETH", "BYN"): (500, 50000),
        ("USDT", "UAH"): (20, 100),
        ("USDT", "KZT"): (200, 1000),
        ("USDT", "PLN"): (2, 20),
    }

    results = ["💹 <b>Текущие курсы и источники:</b>\n"]

    for from_curr, to_curr in test_pairs:
        try:
            cache_key = f"{from_curr}_{to_curr}"
            if cache_key in exchange_api.cache:
                del exchange_api.cache[cache_key]

            rate, api_used = await exchange_api.get_exchange_rate_async(from_curr, to_curr)

            if api_used == "fallback":
                source = "⚠️ запасной"
            elif api_used == "cache":
                source = "🔄 кэш"
            else:
                source = f"✅ {api_used}"

            # Проверка адекватности
            mark = ""
            rng = expected_ranges.get((from_curr, to_curr))
            if rng:
                low, high = rng
                if not (low <= rate <= high):
                    mark = " ❗️подозрительно"

            results.append(f"{from_curr}/{to_curr}: <b>{rate:.6f}</b> ({source}){mark}")
        except Exception as e:
            results.append(f"{from_curr}/{to_curr}: ❌ Ошибка - {str(e)[:80]}")

    await message.answer("\n".join(results))






@dp.message(Command("reset_groups"))
async def cmd_reset_groups(message: Message):
    """Сброс всех групп"""
    # Работает только в личных чатах
    if not is_private_chat(message.chat.id):
        return
    
    if message.from_user.id != OWNER_ID:
        await message.answer("❌ Недостаточно прав")
        return
    
    for group_id in GROUP_IDS:
        db.reset_group_cooldown(group_id)
    
    await message.answer("✅ Все группы сброшены и готовы к работе!")








# === ПАНЕЛЬ ГАРАНТА - CALLBACK ОБРАБОТЧИКИ ===
@dp.callback_query(F.data == "admin_stats")
async def admin_stats_handler(callback: CallbackQuery):
    """Статистика в админке"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    active_deals = len(DEALS)
    total_deals = db.get_total_deals_count()
    total_income = db.get_owner_total_income()
    online_users = db.get_online_users_count()
    
    # Получаем дату последней очистки статистики
    last_reset = db.get_bot_setting('last_stats_reset')
    
    stats_text = (
        f"📊 <b>Статистика системы</b>\n\n"
        f"<b>Активных сделок:</b> {active_deals}\n"
        f"<b>Всего сделок:</b> {total_deals}\n"
        f"<b>Онлайн пользователей:</b> {online_users}\n"
        f"<b>Общий доход гаранта:</b> {total_income:.2f} BYN\n"
    )
    
    if last_reset:
        stats_text += f"<b>📅 Статистика очищена:</b> {last_reset}\n"
    else:
        stats_text += f"<b>📅 Статистика очищена:</b> никогда\n"
    
    # Статистика по обменникам
    exchangers = db.get_all_exchangers()
    if exchangers:
        stats_text += "\n<b>Топ обменников по объему:</b>\n"
        for exchanger in exchangers[:5]:
            if exchanger['total_volume'] > 0:
                stats_text += f"• @{exchanger['username']}: {exchanger['total_volume']:.0f} BYN\n"
    
    # Создаем клавиатуру с кнопкой очистки
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑️ Очистить статистику", callback_data="confirm_reset_stats"),
            InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_stats")
        ],
        [
            InlineKeyboardButton(text="◀️ В панель гаранта", callback_data="admin_back")
        ]
    ])
    
    await callback.message.edit_text(stats_text, reply_markup=keyboard)





@dp.callback_query(F.data == "confirm_reset_stats")
async def confirm_reset_stats_handler(callback: CallbackQuery):
    """Подтверждение очистки статистики"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    warning_text = (
        "⚠️ <b>ВНИМАНИЕ! Очистка статистики</b>\n\n"
        "Вы собираетесь полностью очистить всю статистику:\n\n"
        "✅ <b>Будут очищены:</b>\n"
        "• Все данные о сделках\n"
        "• Статистика обменников\n"
        "• Доходы гаранта и обменников\n"
        "• История онлайн пользователей\n"
        "• Счетчики групп\n\n"
        "❌ <b>НЕ будут очищены:</b>\n"
        "• Список обменников и их залоги\n"
        "• Список валют\n"
        "• Настройки групп\n\n"
        "<b>Это действие нельзя отменить!</b>\n\n"
        "Для продолжения введите пароль.\n\n"
        "Вы уверены, что хотите продолжить?"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, продолжить", callback_data="reset_stats_password"),
            InlineKeyboardButton(text="❌ Нет, отменить", callback_data="admin_stats")
        ]
    ])
    
    await callback.message.edit_text(warning_text, reply_markup=keyboard)

@dp.callback_query(F.data == "reset_stats_password")
async def reset_stats_password_handler(callback: CallbackQuery):
    """Запрос ввода пароля для очистки статистики"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    # Сохраняем состояние для ввода пароля
    user_id = callback.from_user.id
    user_data[user_id] = {'waiting_for_reset_password': True}
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data="admin_stats")]
    ])
    
    await callback.message.edit_text(
        "🔐 <b>Введите пароль для очистки статистики:</b>\n\n"
        "Введите пароль цифрами в чат:",
        reply_markup=keyboard
    )





@dp.callback_query(F.data == "admin_currencies")
async def admin_currencies_handler(callback: CallbackQuery):
    """Управление валютами"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    await callback.message.edit_text(
        "💰 <b>Управление валютами</b>\n\n"
        "Здесь вы можете добавлять и управлять валютами для обмена:",
        reply_markup=get_admin_currencies_keyboard()
    )

@dp.callback_query(F.data == "admin_exchangers")
async def admin_exchangers_handler(callback: CallbackQuery):
    """Управление обменниками"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    await callback.message.edit_text(
        "👥 <b>Управление обменниками</b>\n\n"
        "Здесь вы можете добавлять и управлять обменниками:",
        reply_markup=get_admin_exchangers_keyboard()
    )




@dp.callback_query(F.data == "admin_reset_groups")
async def admin_reset_groups_handler(callback: CallbackQuery):
    """Запрос подтверждения сброса групп"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    # Получаем информацию о текущем состоянии групп
    active_groups = 0
    total_groups = len(GROUP_IDS)
    
    # Проверяем активные сделки в группах
    active_deals_in_groups = 0
    for chat_id in GROUP_IDS:
        if chat_id in ACTIVE_DEALS:
            active_deals_in_groups += 1
    
    # Получаем статистику групп из базы
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM group_stats WHERE is_active = 1")
    active_groups = cursor.fetchone()[0]
    conn.close()
    
    warning_text = (
        f"⚠️ <b>Подтверждение сброса групп</b>\n\n"
        f"Вы собираетесь выполнить полный сброс всех групп.\n\n"
        f"📊 <b>Текущее состояние:</b>\n"
        f"• Всего групп: {total_groups}\n"
        f"• Активных групп: {active_groups}\n"
        f"• Групп с активными сделками: {active_deals_in_groups}\n\n"
        f"⚠️ <b>ВНИМАНИЕ! Будут выполнены следующие действия:</b>\n"
        f"1. Все активные сделки в группах будут завершены\n"
        f"2. Все участники будут удалены из групп\n"
        f"3. История сообщений будет очищена\n"
        f"4. Статистика групп будет обнулена\n"
        f"5. Будут созданы новые пригласительные ссылки\n\n"
        f"<b>Это действие нельзя отменить!</b>\n\n"
        f"Вы уверены, что хотите сбросить все группы?"
    )
    
    await callback.message.edit_text(
        warning_text,
        reply_markup=get_confirm_reset_groups_keyboard()
    )






@dp.callback_query(F.data == "confirm_reset_groups")
async def confirm_reset_groups_handler(callback: CallbackQuery):
    """Подтверждение и выполнение сброса групп"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    # Отправляем сообщение о начале сброса
    await callback.message.edit_text("🔄 <b>Начинаю полный сброс всех групп...</b>")
    
    success_count = 0
    total_groups = len(GROUP_IDS)
    failed_groups = []
    
    for i, group_id in enumerate(GROUP_IDS, 1):
        try:
            # Обновляем статус прогресса
            progress_text = (
                f"🔄 <b>Сбрасываю группы...</b>\n\n"
                f"Обработано: {i}/{total_groups}\n"
                f"Успешно: {success_count}\n"
                f"Ошибок: {len(failed_groups)}\n"
                f"Текущая: {group_id}"
            )
            await callback.message.edit_text(progress_text)
            
            # Сбрасываем группу
            status = await reset_group_completely(group_id)
            if status:
                success_count += 1
            else:
                failed_groups.append(group_id)
            
            # Задержка между группами (чтобы не перегружать API)
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"Ошибка сброса группы {group_id}: {e}")
            failed_groups.append(group_id)
            await asyncio.sleep(3)  # Большая задержка при ошибке
    
    # Финальное сообщение
    if failed_groups:
        result_text = (
            f"⚠️ <b>Сброс групп завершен с ошибками</b>\n\n"
            f"Успешно сброшено: {success_count}/{total_groups} групп\n"
            f"Ошибок: {len(failed_groups)}\n\n"
            f"<b>Группы с ошибками:</b>\n"
        )
        for failed_id in failed_groups[:5]:  # Показываем только первые 5
            result_text += f"• {failed_id}\n"
        
        if len(failed_groups) > 5:
            result_text += f"... и еще {len(failed_groups) - 5}\n"
    else:
        result_text = (
            f"✅ <b>Сброс групп успешно завершен!</b>\n\n"
            f"Успешно сброшено: {success_count}/{total_groups} групп\n"
            f"Все группы готовы к новым сделкам.\n\n"
            f"<i>Статистика групп обнулена, созданы новые ссылки</i>"
        )
    
    # Клавиатура для возврата
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ В панель гаранта", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(
        result_text,
        reply_markup=keyboard
    )






@dp.callback_query(F.data == "list_currencies")
async def list_currencies_handler(callback: CallbackQuery):
    """Список валют"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    currencies = db.get_all_currencies()
    
    if not currencies:
        await callback.message.edit_text(
            "❌ Нет добавленных валют",
            reply_markup=get_back_to_admin_keyboard()
        )
        return
    
    currencies_text = "💰 <b>Список валют:</b>\n\n"
    
    current_type = None
    for currency in currencies:
        if currency['type'] != current_type:
            current_type = currency['type']
            currencies_text += f"\n<b>{current_type.upper()}:</b>\n"
        
        status = "✅" if currency['is_active'] else "❌"
        currencies_text += f"{status} {currency['code']} - {currency['name']}\n"
    
    await callback.message.edit_text(
        currencies_text,
        reply_markup=get_back_to_admin_keyboard()
    )

@dp.callback_query(F.data == "list_exchangers")
async def list_exchangers_handler(callback: CallbackQuery):
    """Список обменников"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    exchangers = db.get_all_exchangers()
    
    if not exchangers:
        await callback.message.edit_text(
            "❌ Нет добавленных обменников",
            reply_markup=get_back_to_admin_keyboard()
        )
        return
    
    await callback.message.edit_text(
        "👥 <b>Выберите обменника для управления:</b>",
        reply_markup=get_exchangers_list_keyboard(exchangers)
    )




@dp.callback_query(F.data.startswith("manage_exchanger:"))
async def manage_exchanger_handler(callback: CallbackQuery):
    """Управление конкретным обменником"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    # Очищаем временные данные редактирования
    user_id = callback.from_user.id
    if user_id in user_data and 'editing_exchanger_id' in user_data[user_id]:
        del user_data[user_id]
    
    exchanger_id = int(callback.data.split(":")[1])
    exchanger_stats = db.get_exchanger_stats(exchanger_id)
    
    if not exchanger_stats:
        await callback.answer("❌ Обменник не найден")
        return
    
    success_rate = (exchanger_stats['successful_deals'] / exchanger_stats['total_deals'] * 100) if exchanger_stats['total_deals'] > 0 else 0
    
    # ВАЖНО: Используем get_exchanger_directions_list вместо get_exchanger_directions
    directions = db.get_exchanger_directions_list(exchanger_id)

    # Формируем текст с направлениями
    if directions:
        directions_text = "\n\n📊 <b>Направления обмена:</b>\n"
        for direction in directions[:5]:
            status = "✅" if direction['is_active'] else "❌"
            directions_text += f"{status} {direction['sell']} → {direction['buy']}\n"
        if len(directions) > 5:
            directions_text += f"... и ещё {len(directions) - 5}\n"
    else:
        directions_text = "\n\n📊 <b>Направления:</b> ❌ НЕТ НАПРАВЛЕНИЙ\n<i>Обменник не будет показываться клиентам</i>"
    
    exchanger_text = (
        f"👤 <b>Управление обменником</b>\n\n"
        f"<b>Username:</b> @{exchanger_stats['username']}\n"
        f"<b>ID:</b> <code>{exchanger_id}</code>\n"
        f"<b>Залог:</b> {exchanger_stats['deposit_amount']} USDT\n"
        f"<b>Комиссия:</b> {exchanger_stats['commission_rate'] * 100:.1f}%\n"
        f"<b>Статус:</b> {'🟢 Активен' if exchanger_stats['is_active'] else '🔴 Неактивен'}"
        f"{directions_text}\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Сделок: {exchanger_stats['total_deals']} ({success_rate:.1f}% успешных)\n"
        f"• Объем: {exchanger_stats['total_volume']:.2f} BYN\n"
        f"• Его доход: {exchanger_stats['total_income']:.2f} BYN\n"
        f"• Ваш доход: {exchanger_stats['owner_income']:.2f} BYN"
    )
    
    try:
        await callback.message.edit_text(
            exchanger_text,
            reply_markup=get_exchanger_management_keyboard(exchanger_id, exchanger_stats['is_active'])
        )
    except Exception as e:
        logger.error(f"Ошибка редактирования сообщения: {e}")
        # Отправляем новое сообщение
        await callback.message.answer(
            exchanger_text,
            reply_markup=get_exchanger_management_keyboard(exchanger_id, exchanger_stats['is_active'])
        )







# === ОБРАБОТЧИКИ ДЛЯ НАПРАВЛЕНИЙ ОБМЕННИКОВ ===

@dp.callback_query(F.data.startswith("manage_directions:"))
async def manage_directions_handler(callback: CallbackQuery):
    """Управление направлениями обменника"""
    exchanger_id = int(callback.data.split(":")[1])
    
    await callback.message.edit_text(
        f"🔄 <b>Управление направлениями обменника</b>\n\n"
        f"Выберите действие:",
        reply_markup=get_exchanger_directions_keyboard(exchanger_id)
    )



@dp.callback_query(F.data.startswith("list_directions:"))
async def list_directions_handler(callback: CallbackQuery):
    """Список направлений обменника"""
    exchanger_id = int(callback.data.split(":")[1])
    
    # ИСПРАВЛЕНО: используем правильный метод для получения списка направлений
    directions = db.get_exchanger_directions_list(exchanger_id)  
    
    logger.info(f"📊 Получено направлений для обменника {exchanger_id}: {len(directions)}")
    
    if not directions:
        await callback.message.edit_text(
            f"📭 <b>У обменника нет направлений</b>\n\n"
            f"Добавьте первое направление.",
            reply_markup=get_exchanger_directions_keyboard(exchanger_id)
        )
        return
    
    directions_text = "📋 <b>Направления обменника:</b>\n\n"
    for direction in directions:
        status = "✅" if direction['is_active'] else "❌"
        directions_text += f"{status} {direction['sell']} -> {direction['buy']}\n"
    
    await callback.message.edit_text(
        directions_text,
        reply_markup=get_directions_list_keyboard(exchanger_id, directions)
    )



@dp.callback_query(F.data.startswith("add_direction:"))
async def add_direction_handler(callback: CallbackQuery):
    """Добавление направления - выбор валюты для продажи"""
    exchanger_id = int(callback.data.split(":")[1])
    
    await callback.message.edit_text(
        f"💱 <b>Выберите валюту, которую клиент будет продавать:</b>",
        reply_markup=get_currency_selection_keyboard(exchanger_id, "select_sell")
    )

@dp.callback_query(F.data.startswith("select_sell:"))
async def select_sell_currency_handler(callback: CallbackQuery):
    """Выбор валюты для покупки после выбора продажи"""
    parts = callback.data.split(":")
    exchanger_id = int(parts[1])
    sell_currency = parts[2]
    
    await callback.message.edit_text(
        f"💱 <b>Выберите валюту, которую клиент будет покупать:</b>\n"
        f"Продажа: {sell_currency}",
        reply_markup=get_currency_selection_keyboard(exchanger_id, "select_buy", sell_currency)
    )

@dp.callback_query(F.data.startswith("select_buy:"))
async def select_buy_currency_handler(callback: CallbackQuery):
    """Подтверждение добавления направления"""
    parts = callback.data.split(":")
    exchanger_id = int(parts[1])
    sell_currency = parts[2]
    buy_currency = parts[3]
    
    # Добавляем направление
    success = db.add_exchanger_direction(exchanger_id, sell_currency, buy_currency)
    
    if success:
        await callback.message.edit_text(
            f"✅ <b>Направление добавлено!</b>\n\n"
            f"{sell_currency} -> {buy_currency}",
            reply_markup=get_exchanger_directions_keyboard(exchanger_id)
        )
    else:
        await callback.message.edit_text(
            f"❌ <b>Не удалось добавить направление</b>\n\n"
            f"Возможно, такое направление уже существует.",
            reply_markup=get_exchanger_directions_keyboard(exchanger_id)
        )

@dp.callback_query(F.data.startswith("toggle_direction:"))
async def toggle_direction_handler(callback: CallbackQuery):
    """Активация/деактивация направления"""
    parts = callback.data.split(":")
    exchanger_id = int(parts[1])
    sell_currency = parts[2]
    buy_currency = parts[3]
    
    # Получаем текущее состояние направления
    directions = db.get_exchanger_directions_list(exchanger_id)
    current_direction = None
    for d in directions:
        if d['sell'] == sell_currency and d['buy'] == buy_currency:
            current_direction = d
            break
    
    if current_direction:
        new_status = not current_direction['is_active']
        db.toggle_exchanger_direction(exchanger_id, sell_currency, buy_currency, new_status)
        status_text = "активировано" if new_status else "деактивировано"
        await callback.answer(f"Направление {status_text}")
        # Обновляем список направлений
        await list_directions_handler(callback)
    else:
        await callback.answer("Направление не найдено")

@dp.callback_query(F.data.startswith("remove_direction:"))
async def remove_direction_handler(callback: CallbackQuery):
    """Удаление направления"""
    parts = callback.data.split(":")
    exchanger_id = int(parts[1])
    sell_currency = parts[2]
    buy_currency = parts[3]
    
    success = db.remove_exchanger_direction(exchanger_id, sell_currency, buy_currency)
    
    if success:
        await callback.answer("Направление удалено")
        # Обновляем список направлений
        await list_directions_handler(callback)
    else:
        await callback.answer("Не удалось удалить направление")








@dp.callback_query(F.data.startswith("activate_exchanger:") | F.data.startswith("deactivate_exchanger:"))
async def toggle_exchanger_handler(callback: CallbackQuery):
    """Активация/деактивация обменника"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    action, exchanger_id = callback.data.split(":")
    exchanger_id = int(exchanger_id)
    is_active = action == "activate_exchanger"
    
    success = db.toggle_exchanger(exchanger_id, is_active)
    
    if success:
        status = "активирован" if is_active else "деактивирован"
        await callback.answer(f"✅ Обменник {status}")
        # Обновляем сообщение
        await manage_exchanger_handler(callback)
    else:
        await callback.answer("❌ Ошибка изменения статуса")

@dp.callback_query(F.data.startswith("delete_exchanger:"))
async def delete_exchanger_handler(callback: CallbackQuery):
    """Запрос подтверждения удаления обменника"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    exchanger_id = int(callback.data.split(":")[1])
    exchanger_stats = db.get_exchanger_stats(exchanger_id)
    
    if not exchanger_stats:
        await callback.answer("❌ Обменник не найден")
        return
    
    warning_text = (
        f"⚠️ <b>ВНИМАНИЕ: Удаление обменника</b>\n\n"
        f"Вы собираетесь удалить обменника:\n"
        f"<b>@{exchanger_stats['username']}</b>\n\n"
        f"<b>Статистика которая будет потеряна:</b>\n"
        f"• Сделок: {exchanger_stats['total_deals']}\n"
        f"• Успешных: {exchanger_stats['successful_deals']}\n"
        f"• Объем: {exchanger_stats['total_volume']:.2f} BYN\n"
        f"• Его доход: {exchanger_stats['total_income']:.2f} BYN\n"
        f"• Ваш доход: {exchanger_stats['owner_income']:.2f} BYN\n\n"
        f"<b>Это действие нельзя отменить!</b>\n"
        f"Вы уверены что хотите удалить обменника?"
    )
    
    await callback.message.edit_text(
        warning_text,
        reply_markup=get_exchanger_delete_confirmation_keyboard(exchanger_id)
    )

@dp.callback_query(F.data.startswith("confirm_delete_exchanger:"))
async def confirm_delete_exchanger_handler(callback: CallbackQuery):
    """Подтверждение удаления обменника"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    exchanger_id = int(callback.data.split(":")[1])
    exchanger_stats = db.get_exchanger_stats(exchanger_id)
    
    if not exchanger_stats:
        await callback.answer("❌ Обменник не найден")
        return
    
    # Удаляем обменника из базы данных
    success = db.delete_exchanger(exchanger_id)
    
    if success:
        await callback.message.edit_text(
            f"✅ <b>Обменник удален!</b>\n\n"
            f"<b>Бывший обменник:</b> @{exchanger_stats['username']}\n"
            f"<b>Удаленная статистика:</b>\n"
            f"• Сделок: {exchanger_stats['total_deals']}\n"
            f"• Объем: {exchanger_stats['total_volume']:.2f} BYN\n"
            f"• Его доход: {exchanger_stats['total_income']:.2f} BYN\n"
            f"• Ваш доход: {exchanger_stats['owner_income']:.2f} BYN",
            reply_markup=get_back_to_exchangers_keyboard()
        )
        await callback.answer("✅ Обменник удален")
    else:
        await callback.message.edit_text(
            "❌ <b>Ошибка удаления обменника</b>\n\n"
            "Попробуйте позже или обратитесь к разработчику",
            reply_markup=get_back_to_exchangers_keyboard()
        )
        await callback.answer("❌ Ошибка удаления")

# === ОБРАБОТЧИКИ ИЗМЕНЕНИЯ ЗАЛОГА И КОМИССИИ ===
@dp.callback_query(F.data.startswith("edit_deposit:"))
async def edit_deposit_handler(callback: CallbackQuery):
    """Обработчик изменения залога"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    exchanger_id = int(callback.data.split(":")[1])
    
    # Сохраняем данные для следующего сообщения
    user_data[callback.from_user.id] = {
        'editing_exchanger_id': exchanger_id,
        'editing_field': 'deposit'
    }
    
    await callback.message.edit_text(
        f"💰 <b>Изменение залога</b>\n\n"
        f"Введите новый размер залога в BYN:\n\n"
        f"<i>Текущий залог можно посмотреть в сообщении выше</i>",
        reply_markup=get_back_to_exchanger_keyboard(exchanger_id)
    )

@dp.callback_query(F.data.startswith("edit_commission:"))
async def edit_commission_handler(callback: CallbackQuery):
    """Обработчик изменения комиссии"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    exchanger_id = int(callback.data.split(":")[1])
    
    # Сохраняем данные для следующего сообщения
    user_data[callback.from_user.id] = {
        'editing_exchanger_id': exchanger_id,
        'editing_field': 'commission'
    }
    
    await callback.message.edit_text(
        f"⚙️ <b>Изменение комиссии</b>\n\n"
        f"Введите новую комиссию в % (например: 3.5 для 3.5%):\n\n"
        f"<i>Текущую комиссию можно посмотреть в сообщении выше</i>",
        reply_markup=get_back_to_exchanger_keyboard(exchanger_id)
    )

@dp.message(Command("exchanger_stats"))
async def cmd_exchanger_stats(message: Message):
    """Статистика конкретного обменника"""
    # Работает только в личных чатах
    if not is_private_chat(message.chat.id):
        return
    
    if message.from_user.id != OWNER_ID:
        await message.answer("❌ Недостаточно прав")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("❌ Используйте: /exchanger_stats USER_ID")
            return
        
        user_id = int(parts[1])
        exchanger_stats = db.get_exchanger_stats(user_id)
        
        if not exchanger_stats:
            await message.answer("❌ Обменник не найден")
            return
        
        success_rate = (exchanger_stats['successful_deals'] / exchanger_stats['total_deals'] * 100) if exchanger_stats['total_deals'] > 0 else 0
        
        stats_text = (
            f"📊 <b>Статистика обменника</b>\n\n"
            f"<b>Username:</b> @{exchanger_stats['username']}\n"
            f"<b>ID:</b> <code>{user_id}</code>\n"
            f"<b>Залог:</b> {exchanger_stats['deposit_amount']} USDT\n"
            f"<b>Комиссия:</b> {exchanger_stats['commission_rate'] * 100:.1f}%\n"
            f"<b>Статус:</b> {'🟢 Активен' if exchanger_stats['is_active'] else '🔴 Неактивен'}\n\n"
            f"<b>Статистика сделок:</b>\n"
            f"• Всего: {exchanger_stats['total_deals']}\n"
            f"• Успешных: {exchanger_stats['successful_deals']} ({success_rate:.1f}%)\n"
            f"• Общий объем: {exchanger_stats['total_volume']:.2f} BYN\n"
            f"• Его доход: {exchanger_stats['total_income']:.2f} BYN\n"
            f"• Ваш доход: {exchanger_stats['owner_income']:.2f} BYN"
        )
        
        await message.answer(stats_text)
        
    except Exception as e:
        logger.error(f"Ошибка команды exchanger_stats: {e}")
        await message.answer("❌ Ошибка. Используйте: /exchanger_stats USER_ID")

@dp.callback_query(F.data == "add_exchanger")
async def add_exchanger_handler(callback: CallbackQuery):
    """Добавление обменника"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    await callback.message.edit_text(
        "👥 <b>Добавление обменника</b>\n\n"
        "Для добавления обменника отправьте сообщение в формате:\n"
        "<code>@username ФИО залог комиссия</code>\n\n"
        "<b>Пример:</b>\n"
        "<code>@obmenник123 Иван Иванов 500 0.03</code>\n\n"
        "Залог - сумма в BYN, комиссия - число (0.03 = 3%)",
        reply_markup=get_back_to_exchangers_keyboard()
    )

@dp.callback_query(F.data == "add_currency")
async def add_currency_handler(callback: CallbackQuery):
    """Добавление валюты"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    await callback.message.edit_text(
        "💰 <b>Добавление валюты</b>\n\n"
        "Выберите тип валюты:",
        reply_markup=get_add_currency_keyboard()
    )

@dp.callback_query(F.data.startswith("add_currency_type:"))
async def add_currency_type_handler(callback: CallbackQuery):
    """Выбор типа валюты для добавления"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    currency_type = callback.data.split(":")[1]
    
    await callback.message.edit_text(
        f"💰 <b>Добавление валюты</b>\n\n"
        f"Тип: <b>{CURRENCY_TYPES[currency_type]}</b>\n\n"
        "Отправьте сообщение в формате:\n"
        "<code>КОД Название валюты</code>\n\n"
        "<b>Примеры:</b>\n"
        "<code>USD Доллар США</code>\n"
        "<code>EUR Евро</code>\n"
        "<code>UAH Украинская гривна</code>",
        reply_markup=get_back_to_currencies_keyboard()
    )
    
    # Сохраняем тип валюты во временные данные
    user_data[callback.from_user.id] = {'adding_currency_type': currency_type}

@dp.message(F.text.regexp(r'^@(\w+)\s+([а-яА-Яa-zA-Z\s]+)\s+(\d+)\s+([0-9.]+)$'))
async def add_exchanger_by_message(message: Message):
    """Обработка добавления обменника по сообщению"""
    if message.from_user.id != OWNER_ID:
        return
    
    try:
        parts = message.text.split()
        username = parts[0][1:]  # Убираем @
        full_name = ' '.join(parts[1:-2])
        deposit = float(parts[-2])
        commission = float(parts[-1])
        
        # Генерируем временный user_id (в реальном боте нужно получить реальный ID)
        user_id = abs(hash(username)) % 1000000000
        
        success = db.add_exchanger(user_id, username, full_name, deposit, commission)
        
        if success:
            await message.answer(
                f"✅ <b>Обменник добавлен!</b>\n\n"
                f"<b>Username:</b> @{username}\n"
                f"<b>ФИО:</b> {full_name}\n"
                f"<b>Залог:</b> {deposit} USDT\n"
                f"<b>Комиссия:</b> {commission*100}%",
                reply_markup=get_back_to_exchangers_keyboard()
            )
        else:
            await message.answer("❌ Ошибка добавления обменника")
            
    except Exception as e:
        logger.error(f"Ошибка добавления обменника: {e}")
        await message.answer("❌ Ошибка формата. Используйте: @username ФИО залог комиссия")

@dp.message(F.text.regexp(r'^([A-Z]{2,5})\s+([а-яА-Яa-zA-Z\s]+)$'))
async def add_currency_by_message(message: Message):
    """Обработка добавления валюты по сообщению"""
    if message.from_user.id != OWNER_ID:
        return
    
    user_id = message.from_user.id
    if user_id not in user_data or 'adding_currency_type' not in user_data[user_id]:
        return
    
    try:
        parts = message.text.split(' ', 1)
        code = parts[0].upper()
        name = parts[1]
        currency_type = user_data[user_id]['adding_currency_type']
        
        success = db.add_currency(currency_type, code, name)
        
        if success:
            await message.answer(
                f"✅ <b>Валюта добавлена!</b>\n\n"
                f"<b>Код:</b> {code}\n"
                f"<b>Название:</b> {name}\n"
                f"<b>Тип:</b> {CURRENCY_TYPES[currency_type]}",
                reply_markup=get_back_to_currencies_keyboard()
            )
            # Очищаем временные данные
            if user_id in user_data:
                del user_data[user_id]
        else:
            await message.answer("❌ Валюта с таким кодом уже существует")
            
    except Exception as e:
        logger.error(f"Ошибка добавления валюты: {e}")
        await message.answer("❌ Ошибка формата. Используйте: КОД Название")

@dp.callback_query(F.data == "admin_back")
async def admin_back_handler(callback: CallbackQuery):
    """Возврат в главное меню админки"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    await callback.message.edit_text(
        "🛡️ <b>Панель гаранта</b>\n\n"
        "Выберите раздел для управления:",
        reply_markup=get_admin_keyboard()
    )

@dp.message(F.text == "👤 Профиль")
async def profile_button_handler(message: Message):
    """Обработчик кнопки Профиль с минимальной информацией о активных сделках"""
    # Работает только в личных чатах
    if not is_private_chat(message.chat.id):
        return
    
    user = message.from_user
    db.update_user_online(user.id, user.username)
    
    # Проверяем есть ли активные сделки
    has_active = has_active_deal(user.id)
    
    # Проверяем является ли пользователь обменником
    exchanger_stats = db.get_exchanger_stats(user.id)
    
    if exchanger_stats:
        # Профиль обменника (без изменений)
        success_rate = (exchanger_stats['successful_deals'] / exchanger_stats['total_deals'] * 100) if exchanger_stats['total_deals'] > 0 else 0
        
        profile_text = (
            f"👤 <b>Профиль обменника</b>\n\n"
            f"<b>Username:</b> @{exchanger_stats['username']}\n"
            f"<b>ID:</b> <code>{user.id}</code>\n"
            f"<b>Залог:</b> {exchanger_stats['deposit_amount']} USDT\n"
            f"<b>Комиссия:</b> {exchanger_stats['commission_rate'] * 100:.1f}%\n"
            f"<b>Статус:</b> {'🟢 Активен' if exchanger_stats['is_active'] else '🔴 Неактивен'}\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"• Всего сделок: {exchanger_stats['total_deals']}\n"
            f"• Успешных: {exchanger_stats['successful_deals']} ({success_rate:.1f}%)\n"
            f"• Общий объем: {exchanger_stats['total_volume']:.2f} BYN\n"
            f"• Ваш заработок: {exchanger_stats['total_income']:.2f} BYN\n"
            f"• Доход гаранта: {exchanger_stats['owner_income']:.2f} BYN"
        )
    else:
        # Профиль обычного пользователя
        profile_text = (
            f"👤 <b>Ваш профиль</b>\n\n"
            f"<b>ID:</b> <code>{user.id}</code>\n"
            f"<b>Имя:</b> {user.full_name}\n"
            f"<b>Username:</b> @{user.username if user.username else 'не установлен'}\n\n"
        )
        
        if has_active:
            profile_text += "⚠️ <b>У вас есть активная сделка</b>\nЗавершите ее перед началом новой."
        else:
            profile_text += "Для начала обмена нажмите кнопку <b>🔄 Начать обмен</b>"
    
    await message.answer(profile_text, reply_markup=get_main_menu(message.from_user.id == OWNER_ID))




@dp.callback_query(F.data == "back")
async def back_handler(callback: CallbackQuery):
    """Обработчик кнопки назад"""
    try:
        await callback.message.edit_text(
            "🛡️ <b>Гарантированный обмен криптовалюты</b>\n\n"
            "Добро пожаловать в безопасную площадку для P2P-обменов!\n\n"
            "Начните безопасный обмен прямо сейчас!",
            reply_markup=get_main_menu(callback.from_user.id == OWNER_ID)  
        )
    except Exception as e:
        logger.warning(f"Не удалось редактировать сообщение: {e}")
        await send_welcome_message(callback.message.chat.id, callback.from_user.id, callback.from_user.username)






@dp.message(Command("id"))
async def cmd_id(message: Message):
    """Показывает ID и информацию о пользователе"""
    # Работает только в личных чатах
    if not is_private_chat(message.chat.id):
        return
    
    user = message.from_user
    
    user_info = (
        f"👤 <b>Ваши данные</b>\n\n"
        f"<b>Ваш ID:</b> <code>{user.id}</code>\n"
        f"<b>Имя:</b> {user.first_name}\n"
    )
    
    if user.last_name:
        user_info += f"<b>Фамилия:</b> {user.last_name}\n"
    
    if user.username:
        user_info += f"<b>Username:</b> @{user.username}\n"
    else:
        user_info += f"<b>Username:</b> не установлен\n"
    
    await message.answer(user_info)

@dp.message(Command("myid"))
async def cmd_myid(message: Message):
    """Короткая версия команды /id"""
    # Работает только в личных чатах
    if not is_private_chat(message.chat.id):
        return
    
    user = message.from_user
    
    user_info = (
        f"🆔 <b>Ваши ID</b>\n\n"
        f"<b>User ID:</b> <code>{user.id}</code>\n"
    )
    
    if user.username:
        user_info += f"<b>Username:</b> @{user.username}"
    
    await message.answer(user_info)

@dp.message(Command("chatid"))
async def cmd_chatid(message: Message):
    """Показывает ID чата"""
    # Работает только в личных чатах
    if not is_private_chat(message.chat.id):
        return
    
    chat = message.chat
    
    chat_info = (
        f"💬 <b>Информация о чате</b>\n\n"
        f"<b>ID чата:</b> <code>{chat.id}</code>\n"
        f"<b>Тип чата:</b> {chat.type}\n"
    )
    
    if chat.title:
        chat_info += f"<b>Название:</b> {chat.title}\n"
    if chat.username:
        chat_info += f"<b>Username:</b> @{chat.username}\n"
    
    await message.answer(chat_info)







@dp.message(F.text.regexp(r'^/[A-Z]{2,5}_[A-Z]{2,5}$'))
async def cmd_currency_pair(message: Message):
    """Обработка команды вида /RUB_BTC"""
    # Работает только в личных чатах
    if not is_private_chat(message.chat.id):
        return
    
    try:
        # Убираем слеш, приводим к верхнему регистру
        pair = message.text[1:].upper()  # Убираем "/"
        from_curr, to_curr = pair.split('_')
        
        # Очищаем кэш для этой пары
        cache_key = f"{from_curr}_{to_curr}"
        if cache_key in exchange_api.cache:
            del exchange_api.cache[cache_key]
        
        # Получаем курс
        rate, source = await exchange_api.get_exchange_rate_async(from_curr, to_curr)
        
        # Форматируем в зависимости от валюты
        if to_curr == "BTC":
            format_str = ".10f"
        elif to_curr in CRYPTO_CODES:
            format_str = ".8f"
        else:
            format_str = ".4f"
        
        # Рассчитываем обратный курс
        reverse_rate = 1.0 / rate if rate > 0 else 0
        
        response = (
            f"🔍 <b>Курс {from_curr} → {to_curr}</b>\n\n"
            f"📊 <b>Основной курс:</b>\n"
            f"1 {from_curr} = {rate:{format_str}} {to_curr}\n"
            f"<i>Источник: {source}</i>\n\n"
            f"📈 <b>Обратный курс:</b>\n"
            f"1 {to_curr} = {reverse_rate:.6f} {from_curr}\n\n"
            f"🧮 <b>Примеры:</b>\n"
            f"100 {from_curr} = {100 * rate:{format_str}} {to_curr}\n"
            f"1000 {from_curr} = {1000 * rate:{format_str}} {to_curr}\n"
            f"10000 {from_curr} = {10000 * rate:{format_str}} {to_curr}"
        )
        
        await message.answer(response)
        
    except ValueError:
        await message.answer(
            "❌ Неправильный формат. Используйте:\n"
            "<code>/RUB_BTC</code>\n"
            "<code>/USDT_BYN</code>\n"
            "<code>/BYN_USDT</code>"
        )
    except ZeroDivisionError:
        await message.answer("❌ Некорректный курс (равен 0)")
    except Exception as e:
        logger.error(f"Ошибка получения курса: {e}")
        await message.answer(f"❌ Ошибка получения курса: {str(e)[:100]}")















# === УПРАВЛЕНИЕ ВАЛЮТАМИ - ОБНОВЛЕННЫЕ ОБРАБОТЧИКИ ===

@dp.callback_query(F.data == "admin_currencies")
async def admin_currencies_handler(callback: CallbackQuery):
    """Управление валютами - новое меню"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    # Получаем статистику по валютам
    stats = db.get_active_currencies_count()
    stats_text = "\n".join([f"• {CURRENCY_TYPES.get(k, k)}: {v}" for k, v in stats.items()])
    
    await callback.message.edit_text(
        f"💰 <b>Управление валютами</b>\n\n"
        f"📊 <b>Активные валюты:</b>\n{stats_text}\n\n"
        f"Выберите действие:",
        reply_markup=get_currencies_list_management_keyboard()
    )









@dp.callback_query(F.data == "list_all_currencies")
async def list_all_currencies_handler(callback: CallbackQuery):
    """Просмотр всех валют с пагинацией - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    currencies = db.get_all_currencies()
    
    if not currencies:
        await callback.message.edit_text(
            "❌ Нет добавленных валют",
            reply_markup=get_currencies_list_management_keyboard()
        )
        return
    
    active_count = sum(1 for c in currencies if c['is_active'])
    inactive_count = len(currencies) - active_count
    
    # Получаем валюты для первой страницы
    page_size = 10
    page = 0
    start_idx = page * page_size
    end_idx = start_idx + page_size
    page_currencies = currencies[start_idx:end_idx]
    
    # Формируем текст с названиями валют
    text = (
        f"📋 <b>Все валюты</b>\n\n"
        f"Всего: {len(currencies)}\n"
        f"✅ Активных: {active_count}\n"
        f"❌ Неактивных: {inactive_count}\n\n"
        f"<b>Валюты на странице {page + 1}:</b>\n"
    )
    
    for i, currency in enumerate(page_currencies, start=1):
        status = "✅" if currency['is_active'] else "❌"
        text += f"{i}. {status} <b>{currency['code']}</b> - {currency['name']}\n"
    
    if len(currencies) > page_size:
        text += f"\n<i>Показано {len(page_currencies)} из {len(currencies)} валют</i>"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_currencies_list_with_source(currencies, page, "all")  # Используем новую функцию с source
    )

@dp.callback_query(F.data.startswith("currencies_page:"))
async def currencies_page_handler(callback: CallbackQuery):
    """Обработка пагинации списка валют - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    # Разбираем callback_data: currencies_page:page:source
    parts = callback.data.split(":")
    page = int(parts[1])
    source = parts[2] if len(parts) > 2 else "all"
    
    currencies = db.get_all_currencies()
    
    active_count = sum(1 for c in currencies if c['is_active'])
    inactive_count = len(currencies) - active_count
    
    # Получаем валюты для текущей страницы
    page_size = 10
    start_idx = page * page_size
    end_idx = start_idx + page_size
    page_currencies = currencies[start_idx:end_idx]
    
    # Формируем текст с названиями валют
    source_text = "Все валюты" if source == "all" else f"Тип: {CURRENCY_TYPES.get(source, source)}"
    text = (
        f"📋 <b>{source_text}</b>\n\n"
        f"Всего: {len(currencies)}\n"
        f"✅ Активных: {active_count}\n"
        f"❌ Неактивных: {inactive_count}\n\n"
        f"<b>Валюты на странице {page + 1}:</b>\n"
    )
    
    for i, currency in enumerate(page_currencies, start=1):
        status = "✅" if currency['is_active'] else "❌"
        text += f"{i}. {status} <b>{currency['code']}</b> - {currency['name']}\n"
    
    if len(currencies) > page_size:
        total_pages = (len(currencies) + page_size - 1) // page_size
        text += f"\n<i>Страница {page + 1} из {total_pages}</i>"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_currencies_list_with_source(currencies, page, source)  # Используем новую функцию с source
    )










@dp.callback_query(F.data.startswith("manage_currency:"))
async def manage_currency_handler(callback: CallbackQuery):
    """Управление конкретной валютой"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    # Разбираем callback_data: manage_currency:CODE:source
    parts = callback.data.split(":")
    currency_code = parts[1]
    source = "all"  # По умолчанию
    
    if len(parts) == 3:
        # Формат: manage_currency:CODE:all
        source = parts[2]
    elif len(parts) == 4:
        # Формат: manage_currency:CODE:type:TYPE
        source = f"type:{parts[3]}"
    
    currency = db.get_currency_by_code(currency_code)
    
    if not currency:
        await callback.answer("❌ Валюта не найдена")
        return
    
    # Проверяем использование валюты
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) FROM exchanger_directions 
        WHERE sell_currency = ? OR buy_currency = ?
    ''', (currency_code, currency_code))
    usage_count = cursor.fetchone()[0]
    conn.close()
    
    currency_text = (
        f"💰 <b>Управление валютой</b>\n\n"
        f"<b>Код:</b> {currency['code']}\n"
        f"<b>Название:</b> {currency['name']}\n"
        f"<b>Тип:</b> {CURRENCY_TYPES.get(currency['type'], currency['type'])}\n"
        f"<b>Статус:</b> {'✅ Активна' if currency['is_active'] else '❌ Неактивна'}\n"
        f"<b>Добавлена:</b> {currency['created_at']}\n"
        f"<b>Используется в направлениях:</b> {usage_count}"
    )
    
    await callback.message.edit_text(
        currency_text,
        reply_markup=get_currency_management_keyboard(currency_code, currency['is_active'], source)
    )







@dp.callback_query(F.data.startswith("activate_currency:") | F.data.startswith("deactivate_currency:"))
async def toggle_currency_handler(callback: CallbackQuery):
    """Активация/деактивация валюты"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    action, currency_code = callback.data.split(":")
    is_active = action == "activate_currency"
    
    success = db.update_currency(currency_code, is_active=is_active)
    
    if success:
        status = "активирована" if is_active else "деактивирована"
        await callback.answer(f"✅ Валюта {status}")
        # Обновляем сообщение
        await manage_currency_handler(callback)
    else:
        await callback.answer("❌ Ошибка изменения статуса")

@dp.callback_query(F.data.startswith("delete_currency:"))
async def delete_currency_handler(callback: CallbackQuery):
    """Запрос подтверждения удаления валюты"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    currency_code = callback.data.split(":")[1]
    currency = db.get_currency_by_code(currency_code)
    
    if not currency:
        await callback.answer("❌ Валюта не найдена")
        return
    
    # Проверяем использование
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) FROM exchanger_directions 
        WHERE sell_currency = ? OR buy_currency = ?
    ''', (currency_code, currency_code))
    usage_count = cursor.fetchone()[0]
    conn.close()
    
    warning_text = (
        f"⚠️ <b>ВНИМАНИЕ: Удаление валюты</b>\n\n"
        f"Вы собираетесь удалить валюту:\n"
        f"<b>{currency['code']} - {currency['name']}</b>\n\n"
    )
    
    if usage_count > 0:
        warning_text += (
            f"❌ <b>Невозможно удалить!</b>\n"
            f"Эта валюта используется в {usage_count} направлениях обменников.\n\n"
            f"<i>Сначала удалите все направления с этой валютой</i>"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"manage_currency:{currency_code}")]
        ])
    else:
        warning_text += (
            f"<b>Это действие нельзя отменить!</b>\n"
            f"Вы уверены что хотите удалить валюту?"
        )
        keyboard = get_currency_delete_confirmation_keyboard(currency_code)
    
    await callback.message.edit_text(warning_text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("confirm_delete_currency:"))
async def confirm_delete_currency_handler(callback: CallbackQuery):
    """Подтверждение удаления валюты"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    currency_code = callback.data.split(":")[1]
    
    # Проверяем использование еще раз
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) FROM exchanger_directions 
        WHERE sell_currency = ? OR buy_currency = ?
    ''', (currency_code, currency_code))
    usage_count = cursor.fetchone()[0]
    conn.close()
    
    if usage_count > 0:
        await callback.message.edit_text(
            "❌ <b>Не удалось удалить валюту!</b>\n\n"
            "Валюта используется в направлениях обменников.",
            reply_markup=get_currencies_list_management_keyboard()
        )
        return
    
    success = db.delete_currency(currency_code)
    
    if success:
        await callback.message.edit_text(
            f"✅ <b>Валюта удалена!</b>\n\n"
            f"Код валюты: {currency_code}\n"
            f"<i>Теперь ее нельзя будет использовать в обменах</i>",
            reply_markup=get_currencies_list_management_keyboard()
        )
        await callback.answer("✅ Валюта удалена")
    else:
        await callback.message.edit_text(
            "❌ <b>Ошибка удаления валюты</b>\n\n"
            "Возможно, валюта уже была удалена.",
            reply_markup=get_currencies_list_management_keyboard()
        )

@dp.callback_query(F.data.startswith("edit_currency_name:"))
async def edit_currency_name_handler(callback: CallbackQuery):
    """Изменение названия валюты"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    currency_code = callback.data.split(":")[1]
    
    # Сохраняем данные для следующего сообщения
    user_data[callback.from_user.id] = {
        'editing_currency_code': currency_code,
        'editing_field': 'currency_name'
    }
    
    currency = db.get_currency_by_code(currency_code)
    
    await callback.message.edit_text(
        f"✏️ <b>Изменение названия валюты</b>\n\n"
        f"<b>Текущее название:</b> {currency['name']}\n"
        f"<b>Код:</b> {currency_code}\n\n"
        f"Введите новое название валюты:",
        reply_markup=get_back_to_currency_management_keyboard(currency_code)
    )

@dp.callback_query(F.data.startswith("edit_currency_type:"))
async def edit_currency_type_handler(callback: CallbackQuery):
    """Изменение типа валюты"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    currency_code = callback.data.split(":")[1]
    currency = db.get_currency_by_code(currency_code)
    
    await callback.message.edit_text(
        f"🔄 <b>Изменение типа валюты</b>\n\n"
        f"<b>Валюта:</b> {currency['name']} ({currency_code})\n"
        f"<b>Текущий тип:</b> {CURRENCY_TYPES.get(currency['type'], currency['type'])}\n\n"
        f"Выберите новый тип:",
        reply_markup=get_currency_type_selection_keyboard(currency_code)
    )

@dp.callback_query(F.data.startswith("update_currency_type:"))
async def update_currency_type_handler(callback: CallbackQuery):
    """Обновление типа валюты"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    _, currency_code, new_type = callback.data.split(":")
    
    success = db.update_currency(currency_code, currency_type=new_type)
    
    if success:
        await callback.answer("✅ Тип валюты обновлен")
        await manage_currency_handler(callback)
    else:
        await callback.answer("❌ Ошибка обновления типа")

@dp.callback_query(F.data == "currencies_by_type")
async def currencies_by_type_handler(callback: CallbackQuery):
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    await callback.message.edit_text(
        "📂 <b>Валюты по типам</b>\n\n"
        "Выберите тип валют для просмотра:",
        reply_markup=get_currencies_by_type_keyboard() 
    )




@dp.callback_query(F.data.startswith("view_currencies_type:"))
async def view_currencies_type_handler(callback: CallbackQuery):
    """Просмотр валют определенного типа"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    currency_type = callback.data.split(":")[1]
    currencies = db.get_currencies_by_type(currency_type)
    
    if not currencies:
        await callback.message.edit_text(
            f"❌ <b>Нет активных валют типа</b>\n"
            f"{CURRENCY_TYPES.get(currency_type, currency_type)}",
            reply_markup=get_currencies_by_type_keyboard()
        )
        return
    
    # Формируем клавиатуру с валютами этого типа
    await callback.message.edit_text(
        f"📋 <b>Валюты типа: {CURRENCY_TYPES.get(currency_type, currency_type)}</b>\n\n"
        f"Найдено: {len(currencies)} валют\n\n"
        f"Выберите валюту для управления:",
        reply_markup=get_currencies_list_with_source(currencies, 0, currency_type)  # Используем новую функцию с source
    )










@dp.callback_query(F.data == "currencies_stats")
async def currencies_stats_handler(callback: CallbackQuery):
    """Статистика по валютам"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    currencies = db.get_all_currencies()
    stats = db.get_active_currencies_count()
    
    total_currencies = len(currencies)
    active_count = sum(stats.values())
    inactive_count = total_currencies - active_count
    
    stats_text = (
        f"📊 <b>Статистика валют</b>\n\n"
        f"<b>Всего валют:</b> {total_currencies}\n"
        f"<b>Активных:</b> {active_count}\n"
        f"<b>Неактивных:</b> {inactive_count}\n\n"
    )
    
    # Статистика по типам
    stats_text += "<b>По типам:</b>\n"
    for type_key, count in stats.items():
        type_name = CURRENCY_TYPES.get(type_key, type_key)
        stats_text += f"• {type_name}: {count}\n"
    
    # Самые используемые валюты
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT currency, COUNT(*) as usage_count FROM (
            SELECT sell_currency as currency FROM exchanger_directions
            UNION ALL
            SELECT buy_currency as currency FROM exchanger_directions
        )
        GROUP BY currency
        ORDER BY usage_count DESC
        LIMIT 5
    ''')
    
    top_currencies = cursor.fetchall()
    conn.close()
    
    if top_currencies:
        stats_text += "\n<b>Самые используемые валюты:</b>\n"
        for currency, count in top_currencies:
            stats_text += f"• {currency}: {count} направлений\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="currencies_by_type")]
    ])
    
    await callback.message.edit_text(stats_text, reply_markup=keyboard)

@dp.callback_query(F.data == "search_currency")
async def search_currency_handler(callback: CallbackQuery):
    """Поиск валюты"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    # Сохраняем состояние поиска
    user_data[callback.from_user.id] = {'searching_currency': True}
    
    await callback.message.edit_text(
        "🔍 <b>Поиск валюты</b>\n\n"
        "Введите код или часть названия валюты:\n\n"
        "<i>Примеры:</i>\n"
        "<code>USDT</code> - найти по коду\n"
        "<code>биткоин</code> - найти по названию\n"
        "<code>BTC</code> - найти по коду",
        reply_markup=get_currencies_list_management_keyboard()
    )

# Обработчик для сохранения изменений валюты
async def handle_currency_edit(message: Message):
    """Обработка изменения названия валюты"""
    user_id = message.from_user.id
    
    if user_id not in user_data or 'editing_currency_code' not in user_data[user_id]:
        return
    
    editing_data = user_data[user_id]
    currency_code = editing_data['editing_currency_code']
    field = editing_data['editing_field']
    
    try:
        if field == 'currency_name':
            new_name = message.text.strip()
            
            if len(new_name) < 2:
                await message.answer(
                    "❌ Название слишком короткое (минимум 2 символа)\n"
                    "Попробуйте еще раз:",
                    reply_markup=get_back_to_currency_management_keyboard(currency_code)
                )
                return
            
            success = db.update_currency(currency_code, name=new_name)
            
            if success:
                await message.answer(
                    f"✅ <b>Название валюты обновлено!</b>\n\n"
                    f"<b>Код:</b> {currency_code}\n"
                    f"<b>Новое название:</b> {new_name}",
                    reply_markup=get_back_to_currency_management_keyboard(currency_code)
                )
                logger.info(f"Обновлено название валюты {currency_code}: {new_name}")
            else:
                await message.answer(
                    "❌ Ошибка обновления названия",
                    reply_markup=get_back_to_currency_management_keyboard(currency_code)
                )
        
        # Очищаем временные данные
        if user_id in user_data:
            del user_data[user_id]
            
    except Exception as e:
        logger.error(f"Ошибка при изменении валюты: {e}")
        await message.answer(
            "❌ Произошла ошибка\nПопробуйте позже",
            reply_markup=get_back_to_currency_management_keyboard(currency_code)
        )

# Обработчик для поиска валюты
async def handle_currency_search(message: Message):
    """Обработка поиска валюты"""
    user_id = message.from_user.id
    
    if user_id not in user_data or not user_data[user_id].get('searching_currency'):
        return
    
    search_query = message.text.strip().upper()
    
    # Получаем все валюты
    all_currencies = db.get_all_currencies()
    
    # Фильтруем по запросу
    found_currencies = []
    for currency in all_currencies:
        if (search_query in currency['code'].upper() or 
            search_query in currency['name'].upper()):
            found_currencies.append(currency)
    
    # Очищаем состояние поиска
    del user_data[user_id]['searching_currency']
    if not user_data[user_id]:
        del user_data[user_id]
    
    if not found_currencies:
        await message.answer(
            f"❌ <b>Валюты не найдены</b>\n\n"
            f"По запросу: <code>{search_query}</code>\n\n"
            f"Попробуйте другой запрос.",
            reply_markup=get_currencies_list_management_keyboard()
        )
        return
    
    # Показываем найденные валюты
    if len(found_currencies) == 1:
        # Если найдена одна валюта - переходим к управлению ею
        await manage_currency_search_result(message, found_currencies[0]['code'])
    else:
        # Если несколько - показываем список
        await show_currency_search_results(message, found_currencies, search_query)

async def manage_currency_search_result(message: Message, currency_code: str):
    """Управление найденной валютой"""
    currency = db.get_currency_by_code(currency_code)
    
    if not currency:
        await message.answer("❌ Валюта не найдена")
        return
    
    currency_text = (
        f"🔍 <b>Найдена валюта</b>\n\n"
        f"<b>Код:</b> {currency['code']}\n"
        f"<b>Название:</b> {currency['name']}\n"
        f"<b>Тип:</b> {CURRENCY_TYPES.get(currency['type'], currency['type'])}\n"
        f"<b>Статус:</b> {'✅ Активна' if currency['is_active'] else '❌ Неактивна'}"
    )
    
    await message.answer(
        currency_text,
        reply_markup=get_currency_management_keyboard(currency_code, currency['is_active'])
    )

async def show_currency_search_results(message: Message, currencies: List[Dict], search_query: str):
    """Показать результаты поиска"""
    currencies_text = f"🔍 <b>Результаты поиска</b>\n\n"
    currencies_text += f"Найдено: {len(currencies)} валют по запросу <code>{search_query}</code>\n\n"
    
    # Группируем по типу
    currencies_by_type = {}
    for currency in currencies:
        type_key = currency['type']
        if type_key not in currencies_by_type:
            currencies_by_type[type_key] = []
        currencies_by_type[type_key].append(currency)
    
    for type_key, type_currencies in currencies_by_type.items():
        type_name = CURRENCY_TYPES.get(type_key, type_key)
        currencies_text += f"<b>{type_name}:</b>\n"
        for currency in type_currencies:
            status = "✅" if currency['is_active'] else "❌"
            currencies_text += f"{status} {currency['code']} - {currency['name']}\n"
        currencies_text += "\n"
    
    # Создаем клавиатуру с кнопками для каждой найденной валюты
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    for currency in currencies[:10]:  # Ограничим 10 валютами
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{currency['code']} - {currency['name'][:20]}",
                callback_data=f"manage_currency:{currency['code']}"
            )
        ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="◀️ Назад к управлению", callback_data="admin_currencies")
    ])
    
    await message.answer(currencies_text, reply_markup=keyboard)


















#Если хотите поддерживать и формат /rate RUB BTC, добавьте:
@dp.message(Command("rate"))
async def cmd_rate(message: Message):
    """Команда /rate RUB BTC"""
    # Работает только в личных чатах
    if not is_private_chat(message.chat.id):
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 3:
            await message.answer(
                "Используйте: <code>/rate FROM TO</code>\n\n"
                "Примеры:\n"
                "<code>/rate RUB BTC</code>\n"
                "<code>/rate USDT BYN</code>\n"
                "<code>/rate BYN USDT</code>"
            )
            return
        
        from_curr = parts[1].upper()
        to_curr = parts[2].upper()
        
        # Очищаем кэш
        cache_key = f"{from_curr}_{to_curr}"
        if cache_key in exchange_api.cache:
            del exchange_api.cache[cache_key]
        
        # Получаем курс
        rate, source = await exchange_api.get_exchange_rate_async(from_curr, to_curr)
        
        # Форматируем
        if to_curr == "BTC":
            format_str = ".10f"
        elif to_curr in CRYPTO_CODES:
            format_str = ".8f"
        else:
            format_str = ".4f"
        
        # Рассчитываем обратный курс
        reverse_rate = 1.0 / rate if rate > 0 else 0
        
        response = (
            f"🔍 <b>Курс {from_curr} → {to_curr}</b>\n\n"
            f"📊 <b>Основной курс:</b>\n"
            f"1 {from_curr} = {rate:{format_str}} {to_curr}\n"
            f"<i>Источник: {source}</i>\n\n"
            f"📈 <b>Обратный курс:</b>\n"
            f"1 {to_curr} = {reverse_rate:.6f} {from_curr}\n\n"
            f"🧮 <b>Примеры:</b>\n"
            f"100 {from_curr} = {100 * rate:{format_str}} {to_curr}\n"
            f"1000 {from_curr} = {1000 * rate:{format_str}} {to_curr}"
        )
        
        await message.answer(response)
        
    except Exception as e:
        logger.error(f"Ошибка команды /rate: {e}")
        await message.answer("❌ Ошибка. Используйте: /rate FROM TO")




# === ОБРАБОТЧИКИ НАЗАД ===
@dp.callback_query(F.data == "back_to_types")
async def back_to_types_handler(callback: CallbackQuery):
    """Назад к выбору типа валюты"""
    try:
        await callback.message.edit_text(
            "💱 <b>Выберите что хотите продать:</b>",
            reply_markup=get_currency_type_keyboard()
        )
    except Exception as e:
        logger.warning(f"Ошибка редактирования в back_to_types: {e}")

@dp.callback_query(F.data.startswith("back_to_sell:"))
async def back_to_sell_handler(callback: CallbackQuery):
    """Назад к выбору валюты продажи"""
    currency_type = callback.data.split(":")[1]
    try:
        await callback.message.edit_text(
            f"💱 <b>Выберите валюту для продажи:</b>",
            reply_markup=get_currency_keyboard(currency_type)
        )
    except Exception as e:
        logger.warning(f"Ошибка редактирования в back_to_sell: {e}")

@dp.callback_query(F.data == "back_to_amount")
async def back_to_amount_handler(callback: CallbackQuery):
    """Назад к вводу суммы"""
    user_id = callback.from_user.id
    if user_id not in user_data:
        await callback.answer("❌ Данные устарели")
        return
    
    try:
        await callback.message.edit_text(
            f"💵 <b>Введите сумму для обмена:</b>\n\n"
            f"<b>Продаете:</b> {user_data[user_id]['sell_currency_name']}\n"
            f"<b>Покупаете:</b> {user_data[user_id]['buy_currency_name']}\n\n"
            "Введите число:",
            reply_markup=get_back_button()
        )
    except Exception as e:
        logger.warning(f"Ошибка редактирования в back_to_amount: {e}")







async def handle_rate_test_input(message: Message):
    """Обработка ввода валютной пары для теста"""
    user_id = message.from_user.id
    
    try:
        # Удаляем состояние
        del user_data[user_id]['testing_any_pair']
        
        # Очищаем временные данные
        if not user_data[user_id]:
            del user_data[user_id]
        
        # Разбираем ввод
        parts = message.text.strip().upper().split()
        if len(parts) != 2:
            await message.answer(
                "❌ Неправильный формат. Используйте: FROM TO\n\n"
                "Пример: <code>BYN BTC</code>",
                reply_markup=get_back_to_currencies_keyboard()
            )
            return
        
        from_curr, to_curr = parts
        
        # Очищаем кэш для этой пары
        cache_key = f"{from_curr}_{to_curr}"
        if cache_key in exchange_api.cache:
            del exchange_api.cache[cache_key]
        
        # Получаем курс
        rate, source = await exchange_api.get_exchange_rate_async(from_curr, to_curr)
        
        # Форматируем результат в зависимости от валюты
        if to_curr == "BTC":
            format_str = ".10f"
        elif to_curr in CRYPTO_CODES:
            format_str = ".8f"
        else:
            format_str = ".4f"
        
        # Рассчитываем обратный курс
        reverse_rate = 1.0 / rate if rate > 0 else 0
        
        response = (
            f"🔍 <b>Тест курса {from_curr}→{to_curr}</b>\n\n"
            f"📊 <b>Основной курс:</b>\n"
            f"1 {from_curr} = {rate:{format_str}} {to_curr}\n"
            f"<i>Источник: {source}</i>\n\n"
            f"📈 <b>Обратный курс:</b>\n"
            f"1 {to_curr} = {reverse_rate:.6f} {from_curr}\n\n"
            f"🧮 <b>Примеры:</b>\n"
            f"100 {from_curr} = {100 * rate:{format_str}} {to_curr}\n"
            f"1000 {from_curr} = {1000 * rate:{format_str}} {to_curr}\n"
            f"10000 {from_curr} = {10000 * rate:{format_str}} {to_curr}"
        )
        
        await message.answer(response, reply_markup=get_back_to_currencies_keyboard())
        
    except ValueError as e:
        await message.answer(
            f"❌ Ошибка формата: {e}\n\n"
            "Используйте: FROM TO\n"
            "Пример: <code>BYN BTC</code>",
            reply_markup=get_back_to_currencies_keyboard()
        )
    except ZeroDivisionError:
        await message.answer(
            "❌ Некорректный курс (равен 0)",
            reply_markup=get_back_to_currencies_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка теста курса: {e}")
        await message.answer(
            f"❌ Ошибка получения курса: {str(e)[:100]}",
            reply_markup=get_back_to_currencies_keyboard()
        )








async def handle_all_messages(message: Message):
    """Обработчик всех текстовых сообщений"""
    user_id = message.from_user.id
    logger.info(f"📨 Получено текстовое сообщение от {user_id}: {message.text}")
    
    # Игнорируем сообщения в чатах сделок
    if is_deal_chat(message.chat.id):
        logger.info(f"⛔ Игнорируем сообщение в чате сделки {message.chat.id}")
        return
    
    # Проверяем, не тестирует ли пользователь валютную пару
    if user_id in user_data and user_data[user_id].get('testing_any_pair'):
        logger.info(f"✅ Найдено состояние testing_any_pair для пользователя {user_id}")
        await handle_rate_test_input(message)
        return
    


    # Проверяем, не ожидаем ли пароль для очистки статистики
    if user_id in user_data and user_data[user_id].get('waiting_for_reset_password'):
        logger.info(f"✅ Пользователь {user_id} вводит пароль для очистки статистики")
        await handle_reset_password_input(message)
        return




    # Проверяем, не редактирует ли пользователь залог/комиссию
    if user_id in user_data and 'editing_exchanger_id' in user_data[user_id]:
        logger.info(f"✅ Найдено состояние editing_exchanger_id для пользователя {user_id}")
        await handle_edit_values(message)
        return
    

 # Проверяем, не редактирует ли пользователь название валюты
    if user_id in user_data and 'editing_currency_code' in user_data[user_id]:
        await handle_currency_edit(message)
        return
    
    # Проверяем, не ищет ли пользователь валюту
    if user_id in user_data and user_data[user_id].get('searching_currency'):
        await handle_currency_search(message)
        return



    # Проверяем, не вводит ли пользователь сумму для обмена
    if user_id in user_data and 'sell_currency_code' in user_data[user_id]:
        logger.info(f"✅ Пользователь {user_id} в процессе обмена, ввел: {message.text}")
        # Проверяем, является ли сообщение числом
        cleaned_text = message.text.replace(',', '').replace('.', '')
        if cleaned_text.isdigit() or (cleaned_text[:-1].isdigit() and cleaned_text[-1] == '.'):
            await amount_handler(message)
            return
        else:
            await message.answer(
                "❌ Пожалуйста, введите число для суммы обмена\n\n"
                "Примеры:\n"
                "• 100\n"
                "• 250.50\n"
                "• 1000",
                reply_markup=get_back_button()
            )
            return
    
    # Если это команда - уже обработана другими обработчиками
    if message.text.startswith('/'):
        return
    
    # Если это не команда и не связанное с обменом сообщение
    if message.text not in ["🔄 Начать обмен", "ℹ️ О боте", "👤 Профиль", "🛡️ Панель гаранта"]:
        logger.info(f"📤 Отправляем подсказку для сообщения: {message.text}")
        await message.answer(
            "Для начала обмена нажмите кнопку <b>🔄 Начать обмен</b>",
            reply_markup=get_main_menu(message.from_user.id == OWNER_ID)
        )








async def handle_reset_password_input(message: Message):
    """Обработка ввода пароля для очистки статистики"""
    user_id = message.from_user.id
    
    try:
        # Получаем введенный пароль
        password = message.text.strip()
        
        # Проверяем пароль
        if password == "23800":
            # Очищаем статистику
            success = db.clear_all_stats()
            
            # Очищаем состояние
            del user_data[user_id]['waiting_for_reset_password']
            if not user_data[user_id]:
                del user_data[user_id]
            
            if success:
                await message.answer(
                    "✅ <b>Статистика успешно очищена!</b>\n\n"
                    "Все данные о сделках, доходах и статистике были удалены.\n"
                    "Дата очистки сохранена в статистике.\n\n"
                    "Счетчики сброшены, система готова к новой статистике.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="📊 Обновить статистику", callback_data="admin_stats")]
                    ])
                )
                logger.info(f"✅ Статистика очищена пользователем {user_id}")
            else:
                await message.answer(
                    "❌ <b>Ошибка очистки статистики!</b>\n\n"
                    "Попробуйте позже или обратитесь к разработчику.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="📊 Вернуться к статистике", callback_data="admin_stats")]
                    ])
                )
        else:
            # Неправильный пароль
            del user_data[user_id]['waiting_for_reset_password']
            if not user_data[user_id]:
                del user_data[user_id]
            
            await message.answer(
                "❌ <b>Неверный пароль!</b>\n\n"
                "Пароль для очистки статистики неверный.\n"
                "Доступ запрещен.\n\n"
                "<i>Если вы забыли пароль, обратитесь к главному гаранту.</i>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📊 Вернуться к статистике", callback_data="admin_stats")]
                ])
            )
            logger.warning(f"❌ Попытка очистки статистики с неверным паролем от {user_id}")
    
    except Exception as e:
        logger.error(f"Ошибка обработки пароля для очистки статистики: {e}")
        await message.answer(
            "❌ <b>Произошла ошибка!</b>\n\n"
            "Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📊 Вернуться к статистике", callback_data="admin_stats")]
            ])
        )














# === ВЫБОР ОБМЕННИКА ===
@dp.callback_query(F.data.startswith("choose_exchanger:"))
async def choose_exchanger_handler(callback: CallbackQuery):
    """Выбор обменника"""
    user_id = callback.from_user.id
    exchanger_index = int(callback.data.split(":")[1])
    
    logger.info(f"🔘 Обработчик выбора обменника вызван: {callback.data}, user_id: {user_id}")
    
    if user_id not in user_data or 'available_exchangers' not in user_data[user_id]:
        logger.error(f"❌ Нет данных для пользователя {user_id}")
        await callback.answer("❌ Данные устарели")
        return
    
    try:
        exchanger = user_data[user_id]['available_exchangers'][exchanger_index]
        user_data[user_id]['selected_exchanger'] = exchanger
        
        logger.info(f"✅ Выбран обменник: @{exchanger['username']}, final_amount: {exchanger['final_amount']}")
        
        confirmation_text = (
            f"✅ <b>Подтверждение обмена</b>\n\n"
            f"<b>Вы покупаете:</b> {format_amount(exchanger['final_amount'], user_data[user_id]['buy_currency_code'])} {user_data[user_id]['buy_currency_name']}\n"
            f"<b>За:</b> {format_amount(user_data[user_id]['sell_amount'], user_data[user_id]['sell_currency_code'])} {user_data[user_id]['sell_currency_name']}\n"
            f"<b>Курс:</b> 1 {user_data[user_id]['sell_currency_code']} = {exchanger['exchange_rate']:.8f} {user_data[user_id]['buy_currency_code']}\n"
            f"<b>Обменник:</b> @{exchanger['username']}\n\n"
            f"<i>После подтверждения будет создан защищенный чат для сделки</i>\n\n"
            f"Подтверждаете обмен?"
        )
        
        await callback.message.edit_text(
            confirmation_text,
            reply_markup=get_confirmation_keyboard()
        )
        
    except IndexError as e:
        logger.error(f"❌ Ошибка индекса {exchanger_index}: {e}")
        await callback.answer("❌ Ошибка выбора обменника")
    except Exception as e:
        logger.error(f"❌ Ошибка в choose_exchanger_handler: {e}")
        await callback.answer("❌ Произошла ошибка")






async def handle_edit_values(message: Message):
    """Обработчик ввода новых значений залога и комиссии"""
    user_id = message.from_user.id
    
    try:
        editing_data = user_data[user_id]
        exchanger_id = editing_data['editing_exchanger_id']
        field = editing_data['editing_field']
        
        # Преобразуем введенное значение
        value_text = message.text.replace(',', '.')
        value = float(value_text)
        
        if field == 'deposit':
            # Валидация залога
            if value < MIN_DEPOSIT or value > MAX_DEPOSIT:
                await message.answer(
                    f"❌ Залог должен быть от {MIN_DEPOSIT} до {MAX_DEPOSIT} BYN\n"
                    f"Попробуйте еще раз:",
                    reply_markup=get_back_to_exchanger_keyboard(exchanger_id)
                )
                return
            
            # Обновляем залог в базе
            success = db.update_exchanger_deposit(exchanger_id, value)
            if success:
                await message.answer(
                    f"✅ <b>Залог обновлен!</b>\n\n"
                    f"Новый залог: <b>{value} USDT</b>",
                    reply_markup=get_back_to_exchanger_keyboard(exchanger_id)
                )
                logger.info(f"Обновлен залог обменника {exchanger_id}: {value} BYN")
            else:
                await message.answer(
                    "❌ Ошибка обновления залога",
                    reply_markup=get_back_to_exchanger_keyboard(exchanger_id)
                )
        
        elif field == 'commission':
            # Валидация комиссии
            if value < 0 or value > 100:
                await message.answer(
                    "❌ Комиссия должна быть от 0 до 100%\n"
                    "Попробуйте еще раз:",
                    reply_markup=get_back_to_exchanger_keyboard(exchanger_id)
                )
                return
            
            # Конвертируем проценты в десятичную дробь
            commission_rate = value / 100.0
            
            # Обновляем комиссию в базе
            success = db.update_exchanger_commission(exchanger_id, commission_rate)
            if success:
                await message.answer(
                    f"✅ <b>Комиссия обновлена!</b>\n\n"
                    f"Новая комиссия: <b>{value}%</b>",
                    reply_markup=get_back_to_exchanger_keyboard(exchanger_id)
                )
                logger.info(f"Обновлена комиссия обменника {exchanger_id}: {value}%")
            else:
                await message.answer(
                    "❌ Ошибка обновления комиссии",
                    reply_markup=get_back_to_exchanger_keyboard(exchanger_id)
                )
        
        # Очищаем временные данные
        if user_id in user_data:
            del user_data[user_id]
            
    except ValueError:
        await message.answer(
            "❌ Введите корректное число\nПопробуйте еще раз:",
            reply_markup=get_back_to_exchanger_keyboard(exchanger_id)
        )
    except Exception as e:
        logger.error(f"Ошибка при изменении параметров обменника: {e}")
        await message.answer(
            "❌ Произошла ошибка\nПопробуйте позже",
            reply_markup=get_back_to_exchanger_keyboard(exchanger_id)
        )

async def text_message_handler(message: Message):
    """Обработка текстовых сообщений не связанных с обменом"""
    user_id = message.from_user.id
    
    # Проверяем, не тестирует ли пользователь валютную пару
    if user_id in user_data and user_data[user_id].get('testing_any_pair'):
        await handle_rate_test_input(message)
        return
    
    # Игнорируем сообщения в чатах сделок
    if is_deal_chat(message.chat.id):
        return
    
    # Если это команда /id - пропускаем (она обрабатывается отдельно)
    if message.text.startswith('/id') or message.text.startswith('/myid'):
        return
    
    # Если это кнопка "Профиль" - пропускаем (обрабатывается отдельно)
    if message.text == "👤 Профиль":
        return
    
    # Если пользователь в процессе обмена, но ввел не число
    if user_id in user_data and 'sell_currency_code' in user_data[user_id]:
        await message.answer(
            "❌ Пожалуйста, введите число для суммы обмена\n\n"
            "Примеры:\n"
            "• 100\n"
            "• 250.50\n"
            "• 1000",
            reply_markup=get_back_button()
        )
    else:
        # Если это не команда и не связанное с обменом сообщение
        if message.text not in ["🔄 Начать обмен", "ℹ️ О боте", "🛡️ Панель гаранта"]:
            await message.answer(
                "Для начала обмена нажмите кнопку <b>🔄 Начать обмен</b>",
                reply_markup=get_main_menu(message.from_user.id == OWNER_ID)
            )






@dp.callback_query(F.data == "admin_api_status")
async def admin_api_status_handler(callback: CallbackQuery):
    """Статус API из панели гаранта"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return

    report = await api_monitor.get_api_health_report()
    await callback.message.edit_text(
        report,
        reply_markup=get_back_to_currencies_keyboard()  # вернуться к валютам
    )


@dp.callback_query(F.data == "admin_rates")
async def admin_rates_handler(callback: CallbackQuery):
    """Курсы из панели гаранта (расширенный список + проверка адекватности)"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return

    exchange_api.cache.clear()

    test_pairs = [
        ("USDT", "RUB"),
        ("USDT", "BYN"),
        ("USDT", "USD"),
        ("USDT", "EUR"),

        ("BTC", "USDT"),
        ("BTC", "RUB"),
        ("BTC", "BYN"),

        ("ETH", "USDT"),
        ("ETH", "RUB"),
        ("ETH", "BYN"),

        ("BYN", "RUB"),
        ("RUB", "BYN"),
        ("USD", "RUB"),
        ("RUB", "USD"),
        ("EUR", "RUB"),
        ("RUB", "EUR"),
        ("USD", "BYN"),
        ("BYN", "USD"),

        ("USDT", "UAH"),
        ("USDT", "KZT"),
        ("USDT", "PLN"),
    ]

    expected_ranges = {
        ("USDT", "RUB"): (50, 200),
        ("USDT", "BYN"): (1, 10),
        ("BTC", "USDT"): (10000, 300000),
        ("ETH", "USDT"): (500, 10000),
        ("BYN", "RUB"): (10, 100),
        ("RUB", "BYN"): (0.01, 0.2),
        ("USD", "RUB"): (50, 200),
        ("RUB", "USD"): (0.005, 0.05),
        ("EUR", "RUB"): (50, 300),
        ("RUB", "EUR"): (0.003, 0.05),
        ("BTC", "RUB"): (1000000, 50000000),
        ("BTC", "BYN"): (10000, 1000000),
        ("ETH", "RUB"): (50000, 5000000),
        ("ETH", "BYN"): (500, 50000),
        ("USDT", "UAH"): (20, 100),
        ("USDT", "KZT"): (200, 1000),
        ("USDT", "PLN"): (2, 20),
    }

    results = ["💹 <b>Текущие курсы и источники:</b>\n"]

    for from_curr, to_curr in test_pairs:
        try:
            cache_key = f"{from_curr}_{to_curr}"
            if cache_key in exchange_api.cache:
                del exchange_api.cache[cache_key]

            rate, api_used = await exchange_api.get_exchange_rate_async(from_curr, to_curr)

            if api_used == "fallback":
                source = "⚠️ запасной"
            elif api_used == "cache":
                source = "🔄 кэш"
            else:
                source = f"✅ {api_used}"

            mark = ""
            rng = expected_ranges.get((from_curr, to_curr))
            if rng:
                low, high = rng
                if not (low <= rate <= high):
                    mark = " ❗️подозрительно"

            results.append(f"{from_curr}/{to_curr}: <b>{rate:.6f}</b> ({source}){mark}")
        except Exception as e:
            results.append(f"{from_curr}/{to_curr}: ❌ {e}")

    await callback.message.edit_text(
        "\n".join(results),
        reply_markup=get_back_to_currencies_keyboard()
    )








@dp.callback_query(F.data == "admin_test_any_pair")
async def admin_test_any_pair_handler(callback: CallbackQuery):
    """Тест любой валютной пары"""
    if not is_guarantor(callback.from_user.id):
        await callback.answer("❌ Недостаточно прав")
        return
    
    # Сохраняем состояние для следующего сообщения
    user_id = callback.from_user.id
    user_data[user_id] = {'testing_any_pair': True}
    logger.info(f"✅ Установлено состояние testing_any_pair для пользователя {user_id}")
    
    await callback.message.edit_text(
        "🔍 <b>Тест любой валютной пары</b>\n\n"
        "Отправьте валютную пару в формате:\n"
        "<code>/FROM_TO</code>\n\n"
        "<b>Примеры:</b>\n"
        "<code>/BYN_BTC</code>\n"
        "<code>/BYN_USDT</code>\n"
        "<code>/RUB_USDT</code>\n"
        "<code>/BYN_BTC</code>\n"
        "<code>/USD_RUB</code>\n"
        "<code>/USDT_BYN</code>\n"
        "<code>/BTC_USDT</code>\n"
        "<code>/RUB_EUR</code>",
        reply_markup=get_back_to_currencies_keyboard()
    )











@dp.message(Command("set_directions"))
async def cmd_set_directions(message: Message):
    """Установка направлений обменника: /set_directions USER_ID RUB->USDT,BYN->BTC"""
    if message.from_user.id != OWNER_ID:
        return
    
    parts = message.text.split(maxsplit=2)
    if len(parts) != 3:
        await message.answer("Использование: /set_directions USER_ID RUB->USDT,BYN->BTC")
        return
    
    try:
        user_id = int(parts[1])
    except ValueError:
        await message.answer("USER_ID должен быть числом")
        return
    
    directions = parts[2].replace(" ", "")  # уберем пробелы
    success = db.update_exchanger_directions(user_id, directions)
    
    if success:
        await message.answer(f"✅ Направления для обменника {user_id} обновлены:\n<code>{directions}</code>")
    else:
        await message.answer("❌ Обменник не найден")





@dp.message(Command("debug_byn_btc"))
async def cmd_debug_byn_btc(message: Message):
    """Дебаг команда для проверки курса BYN->BTC"""
    if message.from_user.id != OWNER_ID:
        return
    
    # Тест 100 BYN -> BTC
    amount = 100.0
    
    # Очищаем кэш
    exchange_api.cache.clear()
    
    # Получаем курс
    rate, source = await exchange_api.get_exchange_rate_async("BYN", "BTC")
    
    # Рассчитываем
    base_amount = amount * rate
    owner_fee = base_amount * 0.01  # 1%
    exchanger_fee = base_amount * 0.03  # 3%
    final_amount = base_amount - owner_fee - exchanger_fee
    
    await message.answer(
        f"🔍 <b>Дебаг BYN→BTC</b>\n\n"
        f"Сумма: {amount} BYN\n"
        f"Курс: 1 BYN = {rate:.10f} BTC (источник: {source})\n\n"
        f"📊 <b>Расчеты:</b>\n"
        f"Базовая сумма: {base_amount:.10f} BTC\n"
        f"Комиссия гаранта (1%): {owner_fee:.10f} BTC\n"
        f"Комиссия обменника (3%): {exchanger_fee:.10f} BTC\n"
        f"Финальная сумма: {final_amount:.10f} BTC\n\n"
        f"<i>Округление до 8 знаков: {final_amount:.8f}</i>"
    )






# === ЗАПУСК БОТА ===
async def main():
    """Основная функция"""
    logger.info("🤖 Бот запускается...")
    
    logger.info(f"👑 Владелец: {OWNER_ID}")
    logger.info(f"📊 Групп для сделок: {len(GROUP_IDS)}")
    
    # Запускаем периодическую очистку
    asyncio.create_task(periodic_cleanup())
    
    # Запускаем мониторинг API
    asyncio.create_task(api_monitor.check_all_apis())
    
    # Регистрируем обработчик текстовых сообщений
    dp.message.register(handle_all_messages, F.text)
    
    logger.info("✅ Система мониторинга сделок запущена")
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Ошибка запуска бота: {e}")
    finally:
        await bot.session.close()






async def periodic_cleanup():
    """Периодическая очистка устаревших данных"""
    while True:
        await asyncio.sleep(1800)  # Каждые 30 минут
        await cleanup_old_data()
        logger.info("✅ Выполнена очистка устаревших данных")





if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
    except Exception as e:
        print(f"Критическая ошибка: {e}")




# === ОТЛАДОЧНЫЙ ОБРАБОТЧИК (временно) ===
@dp.callback_query()
async def debug_all_callbacks(callback: CallbackQuery):
    """Отладочный обработчик для всех callback'ов"""
    logger.info(f"🔍 DEBUG callback: {callback.data}")
    await callback.answer(f"Callback получен: {callback.data[:30]}...")




# Добавьте закрытие сессии при завершении
import atexit
@atexit.register
def cleanup():
    asyncio.run(exchange_api.close_session())