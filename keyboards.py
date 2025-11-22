# keyboards.py
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import CURRENCIES

def get_main_menu():
    """Главное меню"""
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text="🔄 Начать обмен"),
            KeyboardButton(text="ℹ️ О боте")
        ], [
            KeyboardButton(text="👤 Профиль"),
            KeyboardButton(text="🛡️ Гарант")
        ]],
        resize_keyboard=True
    )

def get_back_button():
    """Кнопка возврата"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Назад", callback_data="back")
    ]])

def get_currency_type_keyboard():
    """Выбор типа валюты для продажи"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="💳 Банковская карта", callback_data="type:card")
    builder.button(text="₿ Криптовалюта", callback_data="type:crypto")
    builder.button(text="📱 Электронные кошельки", callback_data="type:ewallet")
    builder.button(text="◀️ Назад", callback_data="back")
    
    builder.adjust(1)
    return builder.as_markup()

def get_currency_keyboard(currency_type: str):
    """Выбор конкретной валюты"""
    builder = InlineKeyboardBuilder()
    
    currencies = CURRENCIES.get(currency_type, {})
    for code, name in currencies.items():
        builder.button(text=name, callback_data=f"currency:{currency_type}:{code}")
    
    builder.button(text="◀️ Назад", callback_data="back_to_types")
    builder.adjust(1)
    return builder.as_markup()

def get_buy_currency_keyboard(sell_currency_type: str, sell_currency_code: str):
    """Выбор валюты для покупки"""
    builder = InlineKeyboardBuilder()
    
    # Исключаем валюту продажи из доступных для покупки
    for currency_type, currencies in CURRENCIES.items():
        if currency_type != sell_currency_type:
            for code, name in currencies.items():
                builder.button(text=name, callback_data=f"buy_currency:{code}")
    
    builder.button(text="◀️ Назад", callback_data=f"back_to_sell:{sell_currency_type}")
    builder.adjust(1)
    return builder.as_markup()

def get_confirmation_keyboard():
    """Клавиатура подтверждения"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да", callback_data="confirm"),
        InlineKeyboardButton(text="❌ Нет", callback_data="cancel")
    ]])

def get_deal_control_keyboard(deal_id: str, user_role: str):
    """Клавиатура управления сделкой с проверкой ролей"""
    keyboard = []
    
    if user_role == "client":
        keyboard.append([
            InlineKeyboardButton(text="✅ Обмен прошёл успешно", callback_data=f"success:{deal_id}"),
        ])
        keyboard.append([
            InlineKeyboardButton(text="🛡️ Вызвать гаранта", callback_data=f"dispute:{deal_id}"),
        ])
    elif user_role == "guarantor":
        keyboard.append([
            InlineKeyboardButton(text="🔒 Завершить сделку", callback_data=f"force_complete:{deal_id}"),
        ])
    # Для обменника - пустая клавиатура (без кнопок)
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None

def get_success_confirmation_keyboard(deal_id: str):
    """Подтверждение успешного обмена"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтверждаю", callback_data=f"confirm_success:{deal_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel_success:{deal_id}")
    ]])

def get_exchanger_list_keyboard(exchangers: list):
    """Список обменников"""
    builder = InlineKeyboardBuilder()
    
    for i, exchanger in enumerate(exchangers, 1):
        builder.button(
            text=f"{i}. @{exchanger['username']}",
            callback_data=f"choose_exchanger:{i-1}"
        )
    
    builder.button(text="◀️ Назад", callback_data="back_to_amount")
    builder.adjust(1)
    return builder.as_markup()

def get_admin_keyboard():
    """Клавиатура администратора"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton(text="🔄 Сбросить группы", callback_data="admin_reset_groups")
    ], [
        InlineKeyboardButton(text="👥 Обменники", callback_data="admin_exchangers"),
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings")
    ]])

def get_exchanger_management_keyboard(exchanger_id: int):
    """Управление конкретным обменником"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✏️ Изменить залог", callback_data=f"edit_deposit:{exchanger_id}"),
        InlineKeyboardButton(text="⚙️ Изменить комиссию", callback_data=f"edit_commission:{exchanger_id}")
    ], [
        InlineKeyboardButton(text="✅ Активировать", callback_data=f"toggle_exchanger:{exchanger_id}:1"),
        InlineKeyboardButton(text="❌ Деактивировать", callback_data=f"toggle_exchanger:{exchanger_id}:0")
    ], [
        InlineKeyboardButton(text="◀️ Назад к списку", callback_data="admin_exchangers")
    ]])

def get_exchangers_list_keyboard(exchangers: list):
    """Список обменников для админки"""
    builder = InlineKeyboardBuilder()
    
    for exchanger in exchangers:
        status = "✅" if exchanger['is_active'] else "❌"
        builder.button(
            text=f"{status} {exchanger['username']} ({exchanger['deposit_amount']})",
            callback_data=f"manage_exchanger:{exchanger['user_id']}"
        )
    
    builder.button(text="➕ Добавить обменника", callback_data="add_exchanger")
    builder.button(text="◀️ Назад", callback_data="admin_back")
    
    builder.adjust(1)
    return builder.as_markup()

def get_admin_settings_keyboard():
    """Клавиатура настроек админа"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚙️ Изменить комиссию гаранта", callback_data="change_owner_commission"),
        InlineKeyboardButton(text="📊 Лимит сделок на группу", callback_data="change_max_deals")
    ], [
        InlineKeyboardButton(text="⏰ Время коудауна групп", callback_data="change_cooldown_time"),
        InlineKeyboardButton(text="🔧 Основные настройки", callback_data="general_settings")
    ], [
        InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")
    ]])

def get_back_to_settings_keyboard():
    """Кнопка возврата к настройкам"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Назад к настройкам", callback_data="admin_settings")
    ]])