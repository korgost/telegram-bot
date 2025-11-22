import time
import logging
import asyncio
from pathlib import Path
from typing import Dict, List
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, ChatMemberUpdated,
    ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.client.default import DefaultBotProperties

from config import OWNER_ID, BOT_TOKEN, CURRENCIES, OWNER_COMMISSION, PRIVATE_GROUP_IDS, MAX_DEALS_PER_GROUP
from database import db
from keyboards import (
    get_main_menu, get_back_button, get_currency_type_keyboard,
    get_currency_keyboard, get_buy_currency_keyboard, get_confirmation_keyboard,
    get_deal_control_keyboard, get_success_confirmation_keyboard, 
    get_exchanger_list_keyboard, get_admin_keyboard,
    get_exchanger_management_keyboard, get_exchangers_list_keyboard,
    get_admin_settings_keyboard, get_back_to_settings_keyboard
)

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

# === Загрузка настроек из базы данных ===
def load_settings_from_db():
    """Загружаем настройки из базы данных"""
    try:
        settings = db.get_bot_settings()
        
        # Обновляем глобальные переменные
        global OWNER_COMMISSION, MAX_DEALS_PER_GROUP
        
        if 'owner_commission' in settings:
            OWNER_COMMISSION = float(settings['owner_commission']['value'])
        if 'max_deals_per_group' in settings:
            MAX_DEALS_PER_GROUP = int(settings['max_deals_per_group']['value'])
        
        logger.info("✅ Настройки загружены из базы данных")
        logger.info(f"⚙️ Комиссия гаранта: {OWNER_COMMISSION*100}%")
        logger.info(f"🔢 Максимум сделок на группу: {MAX_DEALS_PER_GROUP}")
        
    except Exception as e:
        logger.error(f"⚠️ Ошибка загрузки настроек: {e}")

# Инициализируем группы в базе данных
db.init_groups(PRIVATE_GROUP_IDS)

# Загружаем настройки при запуске
load_settings_from_db()

# === Вспомогательные функции ===
async def send_welcome_message(chat_id: int):
    """Отправка приветственного сообщения"""
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
        reply_markup=get_main_menu()
    )

async def calculate_final_amount(amount: float, exchanger_id: int) -> float:
    """Расчет финальной суммы с учетом комиссий гаранта и обменника"""
    # Получаем комиссию обменника из БД
    exchanger_commission = db.get_exchanger_commission(exchanger_id)
    
    # Суммарная комиссия
    total_commission = OWNER_COMMISSION + exchanger_commission
    
    # Финальная сумма для клиента
    final_amount = amount * (1 - total_commission)
    
    logger.info(f"💰 Расчет комиссий: сумма {amount}, комиссия гаранта {OWNER_COMMISSION*100}%, "
                f"комиссия обменника {exchanger_commission*100}%, итого: {final_amount:.2f}")
    
    return final_amount

async def get_available_exchangers(sell_currency: str, buy_currency: str, amount: float) -> List[Dict]:
    """Получение списка доступных обменников"""
    exchangers = db.get_available_exchangers(amount)
    
    for exchanger in exchangers:
        # Используем ID обменника для получения его индивидуальной комиссии
        exchanger['final_amount'] = await calculate_final_amount(amount, exchanger['user_id'])
    
    return exchangers

async def get_available_group() -> int:
    """Получение доступной группы для сделки"""
    group_id = db.get_best_group()
    
    if not group_id:
        # Если все группы в коудауне, сбрасываем самую старую
        oldest_group = await get_oldest_cooldown_group()
        if oldest_group:
            db.reset_group_cooldown(oldest_group)
            group_id = oldest_group
            logger.info(f"Сброшена группа {group_id} из коудауна")
        else:
            # Если совсем нет групп, используем первую
            group_id = PRIVATE_GROUP_IDS[0]
            logger.warning(f"Используется резервная группа {group_id}")
    
    return group_id

async def get_oldest_cooldown_group() -> int:
    """Получение самой старой группы в коудауне"""
    stats = db.get_group_stats()
    cooldown_groups = [s for s in stats if s['cooldown_until']]
    
    if not cooldown_groups:
        return None
    
    # Сортируем по времени коудауна (самые старые первыми)
    cooldown_groups.sort(key=lambda x: x['cooldown_until'] or datetime.min)
    return cooldown_groups[0]['chat_id']

async def create_deal_chat(deal_info: Dict) -> str:
    """Создание чата для сделки с ротацией групп"""
    deal_id = str(int(time.time()))
    
    # Получаем лучшую доступную группу
    chat_id = await get_available_group()
    
    topic_name = f"Сделка #{deal_id} | {deal_info['sell_amount']} {deal_info['sell_currency']} → {deal_info['final_amount']:.2f} {deal_info['buy_currency']}"
    
    try:
        # Переименовываем чат
        await bot.set_chat_title(chat_id=chat_id, title=topic_name)
        
        # Создаем пригласительную ссылку
        invite = await bot.create_chat_invite_link(
            chat_id=chat_id,
            name=f"deal_{deal_id}",
            creates_join_request=False,
            member_limit=4
        )
        
        deal_info.update({
            'deal_id': deal_id,
            'chat_id': chat_id,
            'topic_name': topic_name,
            'invite_link': invite.invite_link,
            'status': 'active',
            'created_at': time.time(),
            'control_message_id': None
        })
        
        DEALS[deal_id] = deal_info
        ACTIVE_DEALS[chat_id] = deal_id
        
        # Обновляем статистику группы
        db.update_group_stats(chat_id, MAX_DEALS_PER_GROUP)
        
        # Приглашаем гаранта
        await notify_guarantor(deal_info)
        
        logger.info(f"Создана сделка {deal_id} в группе {chat_id}")
        return deal_id
        
    except Exception as e:
        logger.error(f"Ошибка создания чата: {e}")
        raise

async def notify_guarantor(deal_info: Dict):
    """Уведомление гаранта о новой сделке"""
    try:
        group_stats = db.get_group_stats()
        current_group = next((g for g in group_stats if g['chat_id'] == deal_info['chat_id']), None)
        
        stats_text = ""
        if current_group:
            stats_text = f"\n<b>Группа:</b> {current_group['total_deals']}/{MAX_DEALS_PER_GROUP} сделок"
        
        await bot.send_message(
            chat_id=OWNER_ID,
            text=(
                f"🛡️ <b>Новая сделка создана</b>\n\n"
                f"<b>ID:</b> #{deal_info['deal_id']}\n"
                f"<b>Клиент:</b> {deal_info['client_name']}\n"
                f"<b>Обменник:</b> @{deal_info['exchanger_username']}\n"
                f"<b>Сумма:</b> {deal_info['sell_amount']} {deal_info['sell_currency']} → "
                f"{deal_info['final_amount']:.2f} {deal_info['buy_currency']}"
                f"{stats_text}\n\n"
                f"🔗 <a href='{deal_info['invite_link']}'>Присоединиться к чату</a>"
            )
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить гаранта: {e}")

async def send_control_message_to_client(deal_info: Dict):
    """Отправка контрольного сообщения клиенту (только когда клиент в чате)"""
    try:
        # Ждем пока клиент присоединится к чату
        await asyncio.sleep(3)
        
        # Проверяем, что клиент действительно в чате
        try:
            chat_member = await bot.get_chat_member(deal_info['chat_id'], deal_info['client_id'])
            if chat_member.status not in ['member', 'administrator', 'creator']:
                logger.info(f"Клиент еще не присоединился к чату {deal_info['chat_id']}")
                return
        except Exception as e:
            logger.error(f"Ошибка проверки участника чата: {e}")
            return
        
        # Отправляем сообщение с кнопками ТОЛЬКО для клиента
        control_text = (
            f"🎛️ <b>Управление сделкой #{deal_info['deal_id']}</b>\n\n"
            f"<b>Сумма:</b> {deal_info['sell_amount']} {deal_info['sell_currency']} → "
            f"{deal_info['final_amount']:.2f} {deal_info['buy_currency']}\n"
            f"<b>Обменник:</b> @{deal_info['exchanger_username']}\n\n"
            "<b>Используйте кнопки ниже для управления сделкой:</b>\n"
            "• ✅ <b>Обмен прошёл успешно</b> - если получили деньги\n"
            "• 🛡️ <b>Вызвать гаранта</b> - если есть проблемы\n\n"
            "<i>Не нажимайте кнопку подтверждения, пока не получите деньги!</i>"
        )
        
        control_message = await bot.send_message(
            chat_id=deal_info['chat_id'],
            text=control_text,
            reply_markup=get_deal_control_keyboard(deal_info['deal_id'], "client")
        )
        
        # Закрепляем сообщение
        await bot.pin_chat_message(
            chat_id=deal_info['chat_id'],
            message_id=control_message.message_id
        )
        
        # Сохраняем ID контрольного сообщения
        deal_info['control_message_id'] = control_message.message_id
        logger.info(f"✅ Контрольное сообщение закреплено в чате {deal_info['chat_id']} для клиента")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки контрольного сообщения: {e}")

async def send_welcome_to_exchanger(deal_info: Dict):
    """Приветственное сообщение для обменника (без кнопок управления)"""
    try:
        welcome_text = (
            f"👋 <b>Добро пожаловать в сделку #{deal_info['deal_id']}</b>\n\n"
            f"<b>Клиент:</b> {deal_info['client_name']}\n"
            f"<b>Сумма:</b> {deal_info['sell_amount']} {deal_info['sell_currency']} → "
            f"{deal_info['final_amount']:.2f} {deal_info['buy_currency']}\n\n"
            "<i>Ожидайте подтверждения завершения от клиента</i>"
        )
        
        await bot.send_message(
            chat_id=deal_info['chat_id'],
            text=welcome_text
        )
        
    except Exception as e:
        logger.error(f"Ошибка отправки приветствия обменнику: {e}")

async def complete_deal(deal_id: str, reason: str):
    """Завершение сделки - ПОЛНАЯ ВЕРСИЯ"""
    deal_info = DEALS.get(deal_id)
    if not deal_info:
        return
    
    chat_id = deal_info['chat_id']
    
    try:
        # 1. Открепляем контрольное сообщение если есть
        if deal_info.get('control_message_id'):
            try:
                await bot.unpin_chat_message(
                    chat_id=chat_id,
                    message_id=deal_info['control_message_id']
                )
            except Exception as e:
                logger.error(f"Ошибка открепления сообщения: {e}")
        
        # 2. Удаляем пользователей
        await remove_participants(chat_id, deal_info)
        
        # 3. Очищаем историю
        await clear_chat_history_full(chat_id)
        
        # 4. Отправляем финальное сообщение
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"🏁 <b>Сделка завершена</b>\n\n"
                f"<b>ID:</b> #{deal_id}\n"
                f"<b>Причина:</b> {reason}\n"
                f"<b>Время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                "<i>Чат готов для следующей сделки</i>"
            )
        )
        
        # 5. Удаляем из активных сделок
        if deal_id in DEALS:
            del DEALS[deal_id]
        if chat_id in ACTIVE_DEALS:
            del ACTIVE_DEALS[chat_id]
            
        logger.info(f"Сделка {deal_id} завершена")
            
    except Exception as e:
        logger.error(f"Ошибка завершения сделки: {e}")

async def remove_participants(chat_id: int, deal_info: Dict):
    """Удаление участников из чата"""
    try:
        bot_info = await bot.get_me()
        participants = [deal_info['client_id'], deal_info['exchanger_id']]
        
        for user_id in participants:
            try:
                # Пропускаем бота и владельца
                if user_id == bot_info.id or user_id == OWNER_ID:
                    continue
                
                # Кикаем пользователя
                await bot.ban_chat_member(
                    chat_id=chat_id, 
                    user_id=user_id,
                    revoke_messages=True
                )
                
                # Сразу разбаниваем
                await asyncio.sleep(1)
                await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
                
                logger.info(f"Пользователь {user_id} удален из чата {chat_id}")
                
            except Exception as e:
                logger.error(f"Ошибка удаления пользователя {user_id}: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка в remove_participants: {e}")

async def clear_chat_history_full(chat_id: int):
    """Полная очистка истории чата"""
    try:
        # Удаляем последние сообщения
        await delete_recent_messages(chat_id)
        
        # Отправляем маркер очистки
        await bot.send_message(
            chat_id=chat_id,
            text="🔄 <b>Чат полностью очищен</b>\n\n"
                 "Все сообщения и участники удалены. "
                 "Ожидайте новых участников для следующей сделки...",
        )
        
    except Exception as e:
        logger.error(f"Ошибка очистки чата {chat_id}: {e}")

async def delete_recent_messages(chat_id: int, limit: int = 50):
    """Удаление последних сообщений"""
    try:
        deleted_count = 0
        
        # Получаем историю сообщений
        async for message in bot.get_chat_history(chat_id=chat_id, limit=limit):
            try:
                # Не удаляем служебные сообщения бота
                if message.from_user and message.from_user.id == (await bot.get_me()).id:
                    continue
                    
                await bot.delete_message(chat_id=chat_id, message_id=message.message_id)
                deleted_count += 1
                await asyncio.sleep(0.1)
                
            except Exception:
                continue
                
        logger.info(f"Удалено {deleted_count} сообщений в чате {chat_id}")
        
    except Exception as e:
        logger.error(f"Ошибка удаления сообщений: {e}")

# === ОБРАБОТЧИК НОВЫХ УЧАСТНИКОВ ЧАТА ===
@dp.chat_member()
async def chat_member_handler(chat_member: ChatMemberUpdated):
    """Обработчик входа участников в чат"""
    try:
        # Проверяем, что это добавление в чат
        if chat_member.old_chat_member.status == "left" and chat_member.new_chat_member.status == "member":
            chat_id = chat_member.chat.id
            user_id = chat_member.new_chat_member.user.id
            
            # Проверяем, есть ли активная сделка в этом чате
            if chat_id in ACTIVE_DEALS:
                deal_id = ACTIVE_DEALS[chat_id]
                deal_info = DEALS.get(deal_id)
                
                if deal_info:
                    # Если вошел клиент - отправляем контрольное сообщение
                    if user_id == deal_info['client_id']:
                        logger.info(f"Клиент {user_id} вошел в чат сделки {deal_id}")
                        await send_control_message_to_client(deal_info)
                    
                    # Если вошел обменник - отправляем ему сообщение без кнопок
                    elif user_id == deal_info['exchanger_id']:
                        logger.info(f"Обменник {user_id} вошел в чат сделки {deal_id}")
                        await send_welcome_to_exchanger(deal_info)
                        
    except Exception as e:
        logger.error(f"Ошибка обработки участника чата: {e}")

# === ОБРАБОТЧИКИ КОМАНД ===
@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Команда /start"""
    await send_welcome_message(message.chat.id)

@dp.message(Command("id"))
async def cmd_id(message: Message):
    """Показ ID"""
    await message.answer(f"🆔 Ваш ID: <code>{message.from_user.id}</code>")

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    """Статистика бота"""
    if message.from_user.id != OWNER_ID:
        await message.answer("❌ Недостаточно прав")
        return
    
    active_deals = len(DEALS)
    group_stats = db.get_group_stats()
    
    active_groups = len([g for g in group_stats if g['is_active']])
    cooldown_groups = len([g for g in group_stats if g['cooldown_until']])
    
    stats_text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"<b>Активных сделок:</b> {active_deals}\n"
        f"<b>Всего групп:</b> {len(group_stats)}\n"
        f"<b>Активных групп:</b> {active_groups}\n"
        f"<b>Групп в коудауне:</b> {cooldown_groups}\n\n"
    )
    
    # Статистика по группам
    for group in group_stats[:10]:
        status = "✅" if group['is_active'] else "⏸️"
        stats_text += f"{status} Группа {group['chat_id']}: {group['total_deals']} сделок\n"
    
    if len(group_stats) > 10:
        stats_text += f"\n... и еще {len(group_stats) - 10} групп"
    
    await message.answer(stats_text, reply_markup=get_admin_keyboard())

@dp.message(Command("cleanup"))
async def cmd_cleanup(message: Message):
    """Принудительная очистка чата"""
    if message.from_user.id != OWNER_ID:
        await message.answer("❌ Недостаточно прав")
        return
    
    chat_id = message.chat.id
    try:
        await clear_chat_history_full(chat_id)
        await message.answer("✅ Чат очищен")
    except Exception as e:
        await message.answer(f"❌ Ошибка очистки: {e}")

@dp.message(Command("reset_groups"))
async def cmd_reset_groups(message: Message):
    """Сброс всех групп"""
    if message.from_user.id != OWNER_ID:
        await message.answer("❌ Недостаточно прав")
        return
    
    for group in db.get_group_stats():
        db.reset_group_cooldown(group['chat_id'])
    
    await message.answer("✅ Все группы сброшены и активированы")

@dp.message(F.text == "🔄 Начать обмен")
async def start_exchange(message: Message):
    """Начало обмена"""
    user_id = message.from_user.id
    if user_id not in user_data:
        user_data[user_id] = {}
    
    await message.answer(
        "💱 <b>Выберите что хотите продать:</b>",
        reply_markup=get_currency_type_keyboard()
    )

@dp.message(F.text == "ℹ️ О боте")
async def about_bot(message: Message):
    """Информация о боте"""
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
        "<b>Комиссии:</b>\n"
        "• Комиссия сервиса: 1%\n"
        "• Комиссия обменника: индивидуальная\n\n"
        "<b>Система ротации:</b>\n"
        "• Автоматическая смена чатов\n"
        "• Полная очистка после сделок\n"
        "• Гарантия анонимности\n\n"
        "Все обменники проходят проверку и вносят залог!"
    )
    
    await message.answer(about_text)

@dp.message(F.text == "👤 Профиль")
async def profile_handler(message: Message):
    """Профиль пользователя"""
    user = message.from_user
    
    profile_text = (
        f"👤 <b>Ваш профиль</b>\n\n"
        f"<b>ID:</b> <code>{user.id}</code>\n"
        f"<b>Имя:</b> {user.full_name}\n"
        f"<b>Username:</b> @{user.username if user.username else 'не установлен'}\n\n"
        "Для начала обмена нажмите кнопку <b>🔄 Начать обмен</b>"
    )
    
    await message.answer(profile_text)

@dp.message(F.text == "🛡️ Гарант")
async def guarantor_handler(message: Message):
    """Информация для гаранта"""
    if message.from_user.id != OWNER_ID:
        await message.answer("❌ Эта функция доступна только гаранту")
        return
    
    active_deals = len(DEALS)
    group_stats = db.get_group_stats()
    active_groups = len([g for g in group_stats if g['is_active']])
    
    guarantor_text = (
        f"🛡️ <b>Панель гаранта</b>\n\n"
        f"<b>Активных сделок:</b> {active_deals}\n"
        f"<b>Активных групп:</b> {active_groups}/{len(group_stats)}\n\n"
        "<b>Доступные команды:</b>\n"
        "• /stats - Статистика системы\n"
        "• /cleanup - Очистка текущего чата\n"
        "• /reset_groups - Сброс всех групп\n"
        "• Присоединяйтесь к чатам по ссылкам\n"
        "• Используйте кнопки управления в чатах"
    )
    
    await message.answer(guarantor_text, reply_markup=get_admin_keyboard())

# === ОБРАБОТЧИКИ CALLBACK ===
@dp.callback_query(F.data == "back")
async def back_handler(callback: CallbackQuery):
    """Обработка кнопки назад"""
    await callback.message.delete()
    await send_welcome_message(callback.from_user.id)

@dp.callback_query(F.data == "back_to_types")
async def back_to_types_handler(callback: CallbackQuery):
    """Возврат к выбору типа валюты"""
    await callback.message.edit_text(
        "💱 <b>Выберите что хотите продать:</b>",
        reply_markup=get_currency_type_keyboard()
    )

@dp.callback_query(F.data.startswith("back_to_sell:"))
async def back_to_sell_handler(callback: CallbackQuery):
    """Возврат к выбору валюты продажи"""
    currency_type = callback.data.split(":")[1]
    await callback.message.edit_text(
        f"💱 <b>Выберите валюту для продажи:</b>",
        reply_markup=get_currency_keyboard(currency_type)
    )

@dp.callback_query(F.data == "back_to_amount")
async def back_to_amount_handler(callback: CallbackQuery):
    """Возврат к вводу суммы"""
    user_id = callback.from_user.id
    if user_id in user_data:
        await callback.message.edit_text(
            f"💵 <b>Введите сумму для обмена:</b>\n\n"
            f"<b>Продаете:</b> {user_data[user_id]['sell_currency_name']}\n"
            f"<b>Покупаете:</b> {user_data[user_id]['buy_currency_name']}\n\n"
            "Введите число:",
            reply_markup=get_back_button()
        )

@dp.callback_query(F.data == "cancel")
async def cancel_handler(callback: CallbackQuery):
    """Отмена обмена"""
    user_id = callback.from_user.id
    if user_id in user_data:
        del user_data[user_id]
    
    await callback.message.edit_text("❌ Обмен отменен")
    await send_welcome_message(callback.from_user.id)

@dp.callback_query(F.data.startswith("cancel_success:"))
async def cancel_success_handler(callback: CallbackQuery):
    """Отмена подтверждения успеха"""
    await callback.message.delete()
    await callback.answer("❌ Подтверждение отменено")

@dp.callback_query(F.data.startswith("type:"))
async def currency_type_handler(callback: CallbackQuery):
    """Выбор типа валюты"""
    user_id = callback.from_user.id
    if user_id not in user_data:
        user_data[user_id] = {}
    
    currency_type = callback.data.split(":")[1]
    user_data[user_id]['sell_currency_type'] = currency_type
    
    await callback.message.edit_text(
        f"💱 <b>Выберите валюту для продажи:</b>",
        reply_markup=get_currency_keyboard(currency_type)
    )

@dp.callback_query(F.data.startswith("currency:"))
async def currency_handler(callback: CallbackQuery):
    """Выбор конкретной валюты"""
    user_id = callback.from_user.id
    if user_id not in user_data:
        user_data[user_id] = {}
    
    _, currency_type, currency_code = callback.data.split(":")
    
    user_data[user_id].update({
        'sell_currency_type': currency_type,
        'sell_currency_code': currency_code,
        'sell_currency_name': CURRENCIES[currency_type][currency_code]
    })
    
    await callback.message.edit_text(
        f"💱 <b>Выберите что хотите купить:</b>",
        reply_markup=get_buy_currency_keyboard(currency_type, currency_code)
    )

@dp.callback_query(F.data.startswith("buy_currency:"))
async def buy_currency_handler(callback: CallbackQuery):
    """Выбор валюты для покупки"""
    user_id = callback.from_user.id
    if user_id not in user_data:
        user_data[user_id] = {}
    
    currency_code = callback.data.split(":")[1]
    
    # Находим название валюты
    currency_name = None
    currency_type = None
    for curr_type, currencies in CURRENCIES.items():
        if currency_code in currencies:
            currency_name = currencies[currency_code]
            currency_type = curr_type
            break
    
    if not currency_name:
        await callback.answer("❌ Валюта не найдена")
        return
    
    user_data[user_id].update({
        'buy_currency_code': currency_code,
        'buy_currency_name': currency_name,
        'buy_currency_type': currency_type
    })
    
    # Проверяем, что все необходимые данные есть
    required_keys = ['sell_currency_code', 'sell_currency_name']
    for key in required_keys:
        if key not in user_data[user_id]:
            await callback.message.edit_text("❌ Данные устарели. Начните обмен заново")
            return
    
    await callback.message.edit_text(
        f"💵 <b>Введите сумму для обмена:</b>\n\n"
        f"<b>Продаете:</b> {user_data[user_id]['sell_currency_name']}\n"
        f"<b>Покупаете:</b> {currency_name}\n\n"
        "Введите число:",
        reply_markup=get_back_button()
    )

@dp.message(F.text.regexp(r'^\d+([,.]\d+)?$'))
async def amount_handler(message: Message):
    """Обработка введенной суммы (с запятой или точкой)"""
    user_id = message.from_user.id
    if user_id not in user_data:
        await message.answer("❌ Начните обмен заново")
        return
    
    try:
        # Проверяем наличие необходимых данных
        required_keys = ['sell_currency_code', 'buy_currency_code', 'sell_currency_name', 'buy_currency_name']
        for key in required_keys:
            if key not in user_data[user_id]:
                await message.answer("❌ Данные устарели. Начните обмен заново")
                return
        
        # Заменяем запятую на точку для корректного преобразования
        amount_text = message.text.replace(',', '.')
        amount = float(amount_text)
        
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше 0")
            return
            
        user_data[user_id]['sell_amount'] = amount
        
        # Получаем доступных обменников
        exchangers = await get_available_exchangers(
            user_data[user_id]['sell_currency_code'],
            user_data[user_id]['buy_currency_code'],
            amount
        )
        
        if not exchangers:
            await message.answer(
                "❌ Нет доступных обменников для данной суммы и валюты",
                reply_markup=get_back_button()
            )
            return
        
        user_data[user_id]['available_exchangers'] = exchangers
        
        # Формируем список обменников с их индивидуальными комиссиями
        exchangers_text = "📊 <b>Доступные обменники:</b>\n\n"
        for i, exchanger in enumerate(exchangers, 1):
            exchanger_commission = exchanger['commission_rate'] * 100
            total_commission = (OWNER_COMMISSION + exchanger['commission_rate']) * 100
            
            exchangers_text += (
                f"{i}. <b>@{exchanger['username']}</b>\n"
                f"   💰 Вы получите: <b>{exchanger['final_amount']:.2f} {user_data[user_id]['buy_currency_code']}</b>\n"
                f"   📈 Общая комиссия: {total_commission:.1f}% "
                f"(гарант: {OWNER_COMMISSION*100}% + обменник: {exchanger_commission:.1f}%)\n"
                f"   ⭐ Рейтинг: {exchanger['rating']}/5\n\n"
            )
        
        await message.answer(
            exchangers_text,
            reply_markup=get_exchanger_list_keyboard(exchangers)
        )
        
    except ValueError:
        await message.answer("❌ Введите корректное число")
    except Exception as e:
        logger.error(f"Ошибка в amount_handler: {e}")
        await message.answer("❌ Произошла ошибка. Начните обмен заново")

@dp.callback_query(F.data.startswith("choose_exchanger:"))
async def choose_exchanger_handler(callback: CallbackQuery):
    """Выбор обменника"""
    user_id = callback.from_user.id
    exchanger_index = int(callback.data.split(":")[1])
    
    if user_id not in user_data or 'available_exchangers' not in user_data[user_id]:
        await callback.answer("❌ Данные устарели")
        return
    
    exchanger = user_data[user_id]['available_exchangers'][exchanger_index]
    user_data[user_id]['selected_exchanger'] = exchanger
    
    confirmation_text = (
        f"✅ <b>Подтверждение обмена</b>\n\n"
        f"<b>Вы покупаете:</b> {exchanger['final_amount']:.2f} {user_data[user_id]['buy_currency_name']}\n"
        f"<b>За:</b> {user_data[user_id]['sell_amount']} {user_data[user_id]['sell_currency_name']}\n"
        f"<b>Обменник:</b> @{exchanger['username']}\n\n"
        f"Подтверждаете обмен?"
    )
    
    await callback.message.edit_text(
        confirmation_text,
        reply_markup=get_confirmation_keyboard()
    )

@dp.callback_query(F.data == "confirm")
async def confirm_exchange_handler(callback: CallbackQuery):
    """Подтверждение обмена"""
    user_id = callback.from_user.id
    user_info = user_data.get(user_id, {})
    
    if not user_info.get('selected_exchanger'):
        await callback.answer("❌ Данные устарели")
        return
    
    # Создаем сделку
    deal_info = {
        'client_id': user_id,
        'client_name': callback.from_user.full_name,
        'exchanger_id': user_info['selected_exchanger']['user_id'],
        'exchanger_username': user_info['selected_exchanger']['username'],
        'sell_currency': user_info['sell_currency_name'],
        'buy_currency': user_info['buy_currency_name'],
        'sell_amount': user_info['sell_amount'],
        'final_amount': user_info['selected_exchanger']['final_amount']
    }
    
    try:
        deal_id = await create_deal_chat(deal_info)
        
        # Предупреждение
        warning_text = (
            "⚠️ <b>Внимание!</b>\n\n"
            "Не переводите суммы более той что указали выше "
            f"({user_info['sell_amount']} {user_info['sell_currency_code']})! "
            "Только в таком случае мы сможем гарантировать безопасную сделку."
        )
        
        await callback.message.edit_text(warning_text)
        
        # Отправляем базовое сообщение в чат (без кнопок)
        chat_info = (
            f"🔔 <b>Новая сделка создана!</b>\n\n"
            f"<b>ID:</b> #{deal_id}\n"
            f"<b>Клиент:</b> {callback.from_user.full_name}\n"
            f"<b>Обменник:</b> @{user_info['selected_exchanger']['username']}\n"
            f"<b>Сумма:</b> {user_info['sell_amount']} {user_info['sell_currency_name']} → "
            f"{user_info['selected_exchanger']['final_amount']:.2f} {user_info['buy_currency_name']}\n\n"
            "<i>Ожидайте присоединения участников...</i>"
        )
        
        await bot.send_message(
            chat_id=deal_info['chat_id'],
            text=chat_info
        )
        
        # Отправляем ссылку клиенту
        await callback.message.answer(
            f"✅ <b>Сделка создана!</b>\n\n"
            f"<b>ID:</b> #{deal_id}\n"
            f"🔗 <a href='{deal_info['invite_link']}'>Присоединиться к чату сделки</a>\n\n"
            "<i>После входа в чат вам будут доступны кнопки управления</i>"
        )
        
        # Уведомляем обменника
        try:
            await bot.send_message(
                chat_id=deal_info['exchanger_id'],
                text=(
                    f"🔔 <b>Новая сделка!</b>\n\n"
                    f"Клиент: {callback.from_user.full_name}\n"
                    f"ID: #{deal_id}\n"
                    f"Сумма: {user_info['sell_amount']} {user_info['sell_currency_name']}\n\n"
                    f"🔗 <a href='{deal_info['invite_link']}'>Присоединиться к чату</a>"
                )
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить обменника: {e}")
        
        # Очищаем данные пользователя
        if user_id in user_data:
            del user_data[user_id]
            
    except Exception as e:
        logger.error(f"Ошибка создания сделки: {e}")
        await callback.message.answer("❌ Ошибка при создании сделки")

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
        "Если всё получено — подтвердите:"
    )
    
    await callback.message.answer(
        warning_text,
        reply_markup=get_success_confirmation_keyboard(deal_id)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("confirm_success:"))
async def confirm_success_handler(callback: CallbackQuery):
    """Подтверждение успешного обмена"""
    deal_id = callback.data.split(":")[1]
    deal_info = DEALS.get(deal_id)
    
    if not deal_info:
        await callback.answer("❌ Сделка не найдена")
        return
    
    # Завершаем сделку
    await complete_deal(deal_id, "completed_by_client")
    await callback.answer("✅ Сделка завершена!")

@dp.callback_query(F.data.startswith("dispute:"))
async def dispute_handler(callback: CallbackQuery):
    """Вызов гаранта"""
    deal_id = callback.data.split(":")[1]
    deal_info = DEALS.get(deal_id)
    
    if not deal_info:
        await callback.answer("❌ Сделка не найдена")
        return
    
    # Уведомляем гаранта
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
    
    await callback.answer("🛡️ Гарант уведомлен!")

@dp.callback_query(F.data.startswith("force_complete:"))
async def force_complete_handler(callback: CallbackQuery):
    """Принудительное завершение гарантом"""
    deal_id = callback.data.split(":")[1]
    
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Недостаточно прав")
        return
    
    await complete_deal(deal_id, "completed_by_guarantor")
    await callback.answer("✅ Сделка завершена!")

@dp.callback_query(F.data == "admin_stats")
async def admin_stats_handler(callback: CallbackQuery):
    """Статистика для админа"""
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Недостаточно прав")
        return
    
    active_deals = len(DEALS)
    group_stats = db.get_group_stats()
    
    active_groups = len([g for g in group_stats if g['is_active']])
    cooldown_groups = len([g for g in group_stats if g['cooldown_until']])
    
    stats_text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"<b>Активных сделок:</b> {active_deals}\n"
        f"<b>Всего групп:</b> {len(group_stats)}\n"
        f"<b>Активных групп:</b> {active_groups}\n"
        f"<b>Групп в коудауне:</b> {cooldown_groups}\n\n"
    )
    
    # Статистика по группам
    for group in group_stats[:10]:
        status = "✅" if group['is_active'] else "⏸️"
        stats_text += f"{status} Группа {group['chat_id']}: {group['total_deals']} сделок\n"
    
    if len(group_stats) > 10:
        stats_text += f"\n... и еще {len(group_stats) - 10} групп"
    
    try:
        await callback.message.edit_text(stats_text, reply_markup=get_admin_keyboard())
    except Exception as e:
        if "message is not modified" in str(e):
            await callback.answer("✅ Статистика актуальна")
        else:
            raise e

@dp.callback_query(F.data == "admin_reset_groups")
async def admin_reset_groups_handler(callback: CallbackQuery):
    """Сброс групп для админа"""
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Недостаточно прав")
        return
    
    for group in db.get_group_stats():
        db.reset_group_cooldown(group['chat_id'])
    
    await callback.message.edit_text("✅ Все группы сброшены и активированы", reply_markup=get_admin_keyboard())
    await callback.answer()

# === ДОПОЛНИТЕЛЬНЫЕ ОБРАБОТЧИКИ ДЛЯ АДМИНКИ ===

@dp.callback_query(F.data == "admin_exchangers")
async def admin_exchangers_handler(callback: CallbackQuery):
    """Управление обменниками"""
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Недостаточно прав")
        return
    
    exchangers = db.get_all_exchangers()
    
    if not exchangers:
        await callback.message.edit_text(
            "📊 <b>Управление обменниками</b>\n\n"
            "Нет зарегистрированных обменников",
            reply_markup=get_exchangers_list_keyboard([])
        )
        return
    
    text = "📊 <b>Управление обменниками</b>\n\n"
    for ex in exchangers:
        status = "✅ Активен" if ex['is_active'] else "❌ Неактивен"
        text += (
            f"<b>@{ex['username']}</b> ({ex['full_name']})\n"
            f"Залог: {ex['deposit_amount']} | Комиссия: {ex['commission_rate']*100}%\n"
            f"Рейтинг: {ex['rating']} | Сделки: {ex['successful_deals']}/{ex['total_deals']}\n"
            f"Статус: {status}\n\n"
        )
    
    await callback.message.edit_text(
        text,
        reply_markup=get_exchangers_list_keyboard(exchangers)
    )

@dp.callback_query(F.data.startswith("manage_exchanger:"))
async def manage_exchanger_handler(callback: CallbackQuery):
    """Управление конкретным обменником"""
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Недостаточно прав")
        return
    
    exchanger_id = int(callback.data.split(":")[1])
    exchangers = db.get_all_exchangers()
    exchanger = next((ex for ex in exchangers if ex['user_id'] == exchanger_id), None)
    
    if not exchanger:
        await callback.answer("❌ Обменник не найден")
        return
    
    text = (
        f"👤 <b>Управление обменником</b>\n\n"
        f"<b>Username:</b> @{exchanger['username']}\n"
        f"<b>Имя:</b> {exchanger['full_name']}\n"
        f"<b>ID:</b> {exchanger['user_id']}\n"
        f"<b>Залог:</b> {exchanger['deposit_amount']}\n"
        f"<b>Комиссия:</b> {exchanger['commission_rate']*100}%\n"
        f"<b>Рейтинг:</b> {exchanger['rating']}/5\n"
        f"<b>Успешные сделки:</b> {exchanger['successful_deals']}/{exchanger['total_deals']}\n"
        f"<b>Статус:</b> {'✅ Активен' if exchanger['is_active'] else '❌ Неактивен'}"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=get_exchanger_management_keyboard(exchanger_id)
    )

@dp.callback_query(F.data.startswith("edit_deposit:"))
async def edit_deposit_handler(callback: CallbackQuery):
    """Изменение залога обменника"""
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Недостаточно прав")
        return
    
    exchanger_id = int(callback.data.split(":")[1])
    await callback.message.edit_text(
        f"💰 <b>Изменение залога</b>\n\n"
        f"Введите новую сумму залога для обменника {exchanger_id}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"manage_exchanger:{exchanger_id}")
        ]])
    )
    
    user_data[callback.from_user.id] = {'waiting_for': 'edit_deposit', 'exchanger_id': exchanger_id}

@dp.callback_query(F.data.startswith("edit_commission:"))
async def edit_commission_handler(callback: CallbackQuery):
    """Изменение комиссии обменника"""
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Недостаточно прав")
        return
    
    exchanger_id = int(callback.data.split(":")[1])
    await callback.message.edit_text(
        f"⚙️ <b>Изменение комиссии</b>\n\n"
        f"Введите новую комиссию для обменника {exchanger_id} (в процентах, например 3.5):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"manage_exchanger:{exchanger_id}")
        ]])
    )
    
    user_data[callback.from_user.id] = {'waiting_for': 'edit_commission', 'exchanger_id': exchanger_id}

@dp.callback_query(F.data.startswith("toggle_exchanger:"))
async def toggle_exchanger_handler(callback: CallbackQuery):
    """Активация/деактивация обменника"""
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Недостаточно прав")
        return
    
    _, exchanger_id, action = callback.data.split(":")
    exchanger_id = int(exchanger_id)
    is_active = bool(int(action))
    
    db.toggle_exchanger_active(exchanger_id, is_active)
    
    status = "активирован" if is_active else "деактивирован"
    await callback.answer(f"✅ Обменник {status}!")
    await manage_exchanger_handler(callback)

@dp.callback_query(F.data == "admin_settings")
async def admin_settings_handler(callback: CallbackQuery):
    """Раздел настроек админа"""
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Недостаточно прав")
        return
    
    from config import OWNER_COMMISSION, MAX_DEALS_PER_GROUP, GROUP_COOLDOWN_HOURS, DEFAULT_EXCHANGER_COMMISSION
    
    settings_text = (
        "⚙️ <b>Настройки бота</b>\n\n"
        f"<b>Текущие настройки:</b>\n"
        f"• Комиссия гаранта: {OWNER_COMMISSION*100}%\n"
        f"• Комиссия обменника по умолчанию: {DEFAULT_EXCHANGER_COMMISSION*100}%\n"
        f"• Максимум сделок на группу: {MAX_DEALS_PER_GROUP}\n"
        f"• Время коудауна групп: {GROUP_COOLDOWN_HOURS} ч.\n\n"
        "<i>Выберите настройку для изменения:</i>"
    )
    
    await callback.message.edit_text(
        settings_text,
        reply_markup=get_admin_settings_keyboard()
    )

@dp.callback_query(F.data == "change_owner_commission")
async def change_owner_commission_handler(callback: CallbackQuery):
    """Изменение комиссии гаранта"""
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Недостаточно прав")
        return
    
    from config import OWNER_COMMISSION
    
    await callback.message.edit_text(
        f"💰 <b>Изменение комиссии гаранта</b>\n\n"
        f"Текущая комиссия: <b>{OWNER_COMMISSION*100}%</b>\n\n"
        "Введите новое значение комиссии (в процентах, например: <code>1.5</code> для 1.5%):",
        reply_markup=get_back_to_settings_keyboard()
    )
    
    user_data[callback.from_user.id] = {'waiting_for': 'owner_commission'}

@dp.callback_query(F.data == "change_max_deals")
async def change_max_deals_handler(callback: CallbackQuery):
    """Изменение лимита сделок на группу"""
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Недостаточно прав")
        return
    
    from config import MAX_DEALS_PER_GROUP
    
    await callback.message.edit_text(
        f"📊 <b>Изменение лимита сделок на группу</b>\n\n"
        f"Текущий лимит: <b>{MAX_DEALS_PER_GROUP}</b> сделок\n\n"
        "Введите новое значение (целое число, например: <code>5</code>):",
        reply_markup=get_back_to_settings_keyboard()
    )
    
    user_data[callback.from_user.id] = {'waiting_for': 'max_deals'}

@dp.callback_query(F.data == "change_cooldown_time")
async def change_cooldown_time_handler(callback: CallbackQuery):
    """Изменение времени коудауна групп"""
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Недостаточно прав")
        return
    
    from config import GROUP_COOLDOWN_HOURS
    
    await callback.message.edit_text(
        f"⏰ <b>Изменение времени коудауна групп</b>\n\n"
        f"Текущее время: <b>{GROUP_COOLDOWN_HOURS}</b> часов\n\n"
        "Введите новое значение в часах (целое число, например: <code>3</code>):",
        reply_markup=get_back_to_settings_keyboard()
    )
    
    user_data[callback.from_user.id] = {'waiting_for': 'cooldown_time'}

@dp.callback_query(F.data == "general_settings")
async def general_settings_handler(callback: CallbackQuery):
    """Общие настройки"""
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Недостаточно прав")
        return
    
    from config import DEFAULT_EXCHANGER_COMMISSION
    
    await callback.message.edit_text(
        f"🔧 <b>Общие настройки</b>\n\n"
        f"Текущая комиссия обменника по умолчанию: <b>{DEFAULT_EXCHANGER_COMMISSION*100}%</b>\n\n"
        "Введите новое значение комиссии (в процентах, например: <code>2.5</code> для 2.5%):",
        reply_markup=get_back_to_settings_keyboard()
    )
    
    user_data[callback.from_user.id] = {'waiting_for': 'default_exchanger_commission'}

@dp.callback_query(F.data == "add_exchanger")
async def add_exchanger_handler(callback: CallbackQuery):
    """Добавление нового обменника"""
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Недостаточно прав")
        return
    
    await callback.message.edit_text(
        "👤 <b>Добавление нового обменника</b>\n\n"
        "Для добавления обменника отправьте его данные в формате:\n\n"
        "<code>user_id username полное_имя залог</code>\n\n"
        "<b>Пример:</b>\n"
        "<code>123456789 ivan_obmen Иван Обменник 1000</code>\n\n"
        "Где:\n"
        "• <b>user_id</b> - ID пользователя в Telegram\n"
        "• <b>username</b> - username (без @)\n"  
        "• <b>полное_имя</b> - ФИО обменника\n"
        "• <b>залог</b> - сумма залога в BYN",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ Назад к списку", callback_data="admin_exchangers")
        ]])
    )
    
    user_data[callback.from_user.id] = {'waiting_for': 'add_exchanger'}

@dp.callback_query(F.data == "admin_back")
async def admin_back_handler(callback: CallbackQuery):
    """Возврат в главное меню админки"""
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Недостаточно прав")
        return
    
    await callback.message.edit_text(
        "🛡️ <b>Панель гаранта</b>\n\n"
        "Выберите действие:",
        reply_markup=get_admin_keyboard()
    )

async def handle_settings_input(message: Message):
    """Обработка ввода настроек"""
    user_id = message.from_user.id
    
    if user_id not in user_data or 'waiting_for' not in user_data[user_id]:
        await message.answer("❌ Сессия устарела. Используйте панель админа")
        return
    
    setting_data = user_data[user_id]
    setting_type = setting_data['waiting_for']
    
    try:
        # Преобразуем ввод в число
        value_text = message.text.replace(',', '.')
        value = float(value_text)
        
        if setting_type == 'owner_commission':
            if value > 100 or value < 0:
                await message.answer("❌ Комиссия должна быть от 0% до 100%")
                return
            
            db.update_setting('owner_commission', str(value / 100))
            setting_name = "комиссия гаранта"
            
        elif setting_type == 'default_exchanger_commission':
            if value > 100 or value < 0:
                await message.answer("❌ Комиссия должна быть от 0% до 100%")
                return
            
            db.update_setting('default_exchanger_commission', str(value / 100))
            setting_name = "комиссия обменника по умолчанию"
            
        elif setting_type == 'max_deals':
            if value < 1 or value > 50:
                await message.answer("❌ Лимит должен быть от 1 до 50")
                return
            
            db.update_setting('max_deals_per_group', str(int(value)))
            setting_name = "лимит сделок на группу"
            
        elif setting_type == 'cooldown_time':
            if value < 1 or value > 24:
                await message.answer("❌ Время коудауна должно быть от 1 до 24 часов")
                return
            
            db.update_setting('group_cooldown_hours', str(int(value)))
            setting_name = "время коудауна групп"
            
        elif setting_type == 'edit_commission':
            exchanger_id = setting_data.get('exchanger_id')
            if not exchanger_id:
                await message.answer("❌ Ошибка: ID обменника не найден")
                return
            
            if value > 100 or value < 0:
                await message.answer("❌ Комиссия должна быть от 0% до 100%")
                return
            
            db.update_exchanger_commission(exchanger_id, value / 100)
            setting_name = f"комиссия обменника {exchanger_id}"
            
        elif setting_type == 'edit_deposit':
            exchanger_id = setting_data.get('exchanger_id')
            if not exchanger_id:
                await message.answer("❌ Ошибка: ID обменника не найден")
                return
            
            if value < 0:
                await message.answer("❌ Залог не может быть отрицательным")
                return
            
            db.update_exchanger_deposit(exchanger_id, value)
            setting_name = f"залог обменника {exchanger_id}"
            
        elif setting_type == 'add_exchanger':
            # Обработка добавления обменника
            parts = message.text.split()
            if len(parts) != 4:
                await message.answer(
                    "❌ <b>Неверный формат данных!</b>\n\n"
                    "Используйте формат: <code>user_id username полное_имя залог</code>\n\n"
                    "<b>Пример:</b>\n"
                    "<code>123456789 ivan_obmen Иван Обменник 1000</code>"
                )
                return
            
            user_id_ex = int(parts[0])
            username = parts[1]
            full_name = parts[2]
            deposit_amount = float(parts[3])
            
            db.add_exchanger(user_id_ex, username, full_name, deposit_amount)
            
            # Очищаем состояние
            del user_data[user_id]
            
            await message.answer(
                f"✅ <b>Обменник успешно добавлен!</b>\n\n"
                f"<b>ID:</b> {user_id_ex}\n"
                f"<b>Username:</b> @{username}\n"
                f"<b>Имя:</b> {full_name}\n"
                f"<b>Залог:</b> {deposit_amount} BYN",
                reply_markup=get_admin_keyboard()
            )
            return
        
        else:
            await message.answer("❌ Неизвестный тип настройки")
            return
        
        # Перезагружаем настройки из БД
        from config import load_settings_from_db
        load_settings_from_db()
        
        # Очищаем состояние
        del user_data[user_id]
        
        # Для настроек обменников возвращаемся к управлению обменником
        if setting_type in ['edit_commission', 'edit_deposit']:
            from aiogram.types import CallbackQuery
            callback = CallbackQuery(
                data=f"manage_exchanger:{exchanger_id}",
                from_user=message.from_user,
                message=message
            )
            await manage_exchanger_handler(callback)
        else:
            await message.answer(
                f"✅ <b>Настройка успешно обновлена!</b>\n\n"
                f"<b>Параметр:</b> {setting_name}\n"
                f"<b>Новое значение:</b> {value}",
                reply_markup=get_admin_keyboard()
            )
        
    except ValueError:
        await message.answer("❌ Введите корректное число")
    except Exception as e:
        logger.error(f"Ошибка в handle_settings_input: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def debug_settings_input(message: Message):
    """Отладочная функция для проверки ввода настроек"""
    user_id = message.from_user.id
    logger.info(f"=== DEBUG SETTINGS INPUT ===")
    logger.info(f"User ID: {user_id}")
    logger.info(f"Message text: {message.text}")
    logger.info(f"User data: {user_data.get(user_id, 'NO DATA')}")
    
    if user_id in user_data:
        logger.info(f"Waiting for: {user_data[user_id].get('waiting_for', 'NOT SET')}")
    
    # Проверяем, является ли это числом
    if message.text and message.text.replace(',', '.').replace('.', '').isdigit():
        logger.info(f"Это число: {message.text}")
    else:
        logger.info(f"Это НЕ число: {message.text}")
    
    # Проверяем, находится ли пользователь в процессе обмена
    if user_id in user_data and 'sell_currency_code' in user_data[user_id]:
        logger.info(f"Пользователь в процессе обмена")
    else:
        logger.info(f"Пользователь НЕ в процессе обмена")
    
    logger.info(f"=== END DEBUG ===")

# Временно замените handle_all_messages на эту версию:
@dp.message()
async def handle_all_messages(message: Message):
    """Обработка всех сообщений с отладкой"""
    user_id = message.from_user.id
    
    # Сначала выводим отладочную информацию
    await debug_settings_input(message)
    
    # 1. Проверяем, не вводит ли пользователь настройки
    if user_id in user_data and 'waiting_for' in user_data[user_id]:
        logger.info(f"Вызываем handle_settings_input для {user_data[user_id]['waiting_for']}")
        await handle_settings_input(message)
        return
    
    # 2. Проверяем, не является ли это числом (суммой для обмена)
    if message.text and message.text.replace(',', '.').replace('.', '').isdigit():
        # Проверяем, находится ли пользователь в процессе обмена
        if user_id in user_data and 'sell_currency_code' in user_data[user_id] and 'buy_currency_code' in user_data[user_id]:
            logger.info("Вызываем amount_handler")
            await amount_handler(message)
            return
    
    # 3. Если это админ и он ввел число без контекста
    if message.from_user.id == OWNER_ID and message.text.replace(',', '.').replace('.', '').isdigit():
        await message.answer(
            "ℹ️ <b>Ввод числа без контекста</b>\n\n"
            "Для изменения настроек используйте панель админа:\n"
            "🛡️ Гарант → ⚙️ Настройки"
        )
        return
    
    # 4. Обработка неизвестных сообщений
    if message.chat.type == "private":
        await message.answer(
            "🤔 <b>Неизвестная команда</b>\n\n"
            "Используйте кнопки меню для навигации или /start для начала работы",
            reply_markup=get_main_menu()
        )





@dp.message()
async def handle_all_messages(message: Message):
    """Обработка всех сообщений"""
    user_id = message.from_user.id
    
    # 1. Проверяем, не вводит ли пользователь настройки
    if user_id in user_data and 'waiting_for' in user_data[user_id]:
        await handle_settings_input(message)
        return
    
    # 2. Проверяем, не является ли это числом (суммой для обмена)
    if message.text and message.text.replace(',', '.').replace('.', '').isdigit():
        # Проверяем, находится ли пользователь в процессе обмена
        if user_id in user_data and 'sell_currency_code' in user_data[user_id] and 'buy_currency_code' in user_data[user_id]:
            await amount_handler(message)
            return
    
    # 3. Если это админ и он ввел число без контекста
    if message.from_user.id == OWNER_ID and message.text.replace(',', '.').replace('.', '').isdigit():
        await message.answer(
            "ℹ️ <b>Ввод числа без контекста</b>\n\n"
            "Для изменения настроек используйте панель админа:\n"
            "🛡️ Гарант → ⚙️ Настройки"
        )
        return
    
    # 4. Обработка неизвестных сообщений
    if message.chat.type == "private":
        await message.answer(
            "🤔 <b>Неизвестная команда</b>\n\n"
            "Используйте кнопки меню для навигации или /start для начала работы",
            reply_markup=get_main_menu()
        )

# Обработчик для любых неизвестных callback-ов
@dp.callback_query()
async def handle_unknown_callback(callback: CallbackQuery):
    """Обработка неизвестных callback-ов"""
    await callback.answer("❌ Эта функция пока не реализована")

# === ЗАПУСК БОТА ===

async def main():
    """Основная функция"""
    logger.info("🤖 Бот запускается...")
    
    # Проверяем конфигурацию
    logger.info(f"👑 Владелец: {OWNER_ID}")
    logger.info(f"📊 Доступно групп: {len(PRIVATE_GROUP_IDS)}")
    logger.info(f"🔄 Максимум сделок на группу: {MAX_DEALS_PER_GROUP}")
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Ошибка запуска бота: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())