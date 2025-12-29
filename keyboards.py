from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import CURRENCY_TYPES
from database import db
from typing import List, Dict

def get_main_menu(is_owner: bool = False):
    """Главное меню"""
    buttons = [
        [KeyboardButton(text="🔄 Начать обмен")],
        [KeyboardButton(text="ℹ️ О боте"), KeyboardButton(text="👤 Профиль")]
    ]
    
    if is_owner:
        buttons.append([KeyboardButton(text="🛡️ Панель гаранта")])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_back_button():
    """Кнопка возврата"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Назад", callback_data="back")
    ]])

def get_currency_type_keyboard():
    """Выбор типа валюты для продажи"""
    builder = InlineKeyboardBuilder()
    
    for type_key, type_name in CURRENCY_TYPES.items():
        builder.button(text=type_name, callback_data=f"type:{type_key}")
    
    builder.button(text="◀️ Назад", callback_data="back")
    builder.adjust(1)
    return builder.as_markup()

def get_currency_keyboard(currency_type: str):
    """Выбор конкретной валюты"""
    builder = InlineKeyboardBuilder()
    
    currencies = db.get_all_currencies()
    for currency in currencies:
        if currency['type'] == currency_type and currency['is_active']:
            builder.button(
                text=currency['name'], 
                callback_data=f"currency:{currency_type}:{currency['code']}"
            )
    
    builder.button(text="◀️ Назад", callback_data="back_to_types")
    builder.adjust(1)
    return builder.as_markup()

def get_buy_currency_keyboard(sell_currency_type: str, sell_currency_code: str):
    """Выбор валюты для покупки"""
    builder = InlineKeyboardBuilder()
    
    currencies = db.get_all_currencies()
    for currency in currencies:
        if currency['type'] != sell_currency_type and currency['is_active']:
            builder.button(
                text=currency['name'],
                callback_data=f"buy_currency:{currency['code']}"
            )
    
    builder.button(text="◀️ Назад", callback_data=f"back_to_sell:{sell_currency_type}")
    builder.adjust(1)
    return builder.as_markup()

def get_confirmation_keyboard():
    """Подтверждение обмена"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="cancel")
    ]])

def get_exchanger_list_keyboard(exchangers: List[Dict]) -> InlineKeyboardMarkup:
    """Клавиатура выбора обменника"""
    buttons = []
    for i, exchanger in enumerate(exchangers):
        button_text = f"{i+1}. @{exchanger['username']}"
        callback_data = f"choose_exchanger:{i}"  
        buttons.append([InlineKeyboardButton(
            text=button_text,
            callback_data=callback_data
        )])
    
    buttons.append([InlineKeyboardButton(
        text="◀️ Назад",
        callback_data="back_to_amount"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_deal_control_keyboard(deal_id: str, user_role: str):
    """Клавиатура управления сделкой для разных ролей"""
    if user_role == "client":
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Деньги пришли, закрыть чат", callback_data=f"success:{deal_id}"),
        ], [
            InlineKeyboardButton(text="🛡️ Сделка не удалась, Вызвать гаранта", callback_data=f"dispute:{deal_id}"),
        ]])
    
    elif user_role == "exchanger":
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🛡️ Возникли проблемы, Вызвать гаранта", callback_data=f"dispute:{deal_id}"),
        ]])
    
    return None

def get_success_confirmation_keyboard(deal_id: str):
    """Подтверждение успешного обмена"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да, всё получено", callback_data=f"confirm_success:{deal_id}"),
        InlineKeyboardButton(text="❌ Нет, есть проблемы", callback_data=f"cancel_success:{deal_id}")
    ]])

# === КЛАВИАТУРЫ ДЛЯ ГАРАНТА ===

def get_admin_keyboard():
    """Главное меню гаранта"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton(text="👥 Обменники", callback_data="admin_exchangers")
    ], [
        InlineKeyboardButton(text="💰 Валюты", callback_data="admin_currencies"),
    ], [
        InlineKeyboardButton(text="🔄 Сбросить группы", callback_data="admin_reset_groups")
    ]])

def get_admin_currencies_keyboard():
    """Управление валютами"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="➕ Добавить валюту", callback_data="add_currency")
    builder.button(text="📋 Все валюты", callback_data="list_all_currencies")
    builder.button(text="🎛️ По типам", callback_data="currencies_by_type")
    builder.button(text="🔍 Найти валюту", callback_data="search_currency")
    builder.button(text="📡 Статус API", callback_data="admin_api_status")
    builder.button(text="💹 Курсы", callback_data="admin_rates")
    builder.button(text="🔍 Тест любой пары", callback_data="admin_test_any_pair") 
    builder.button(text="◀️ Назад", callback_data="admin_back")
    
    builder.adjust(2, 2, 2, 1, 1)
    return builder.as_markup()

def get_admin_exchangers_keyboard():
    """Управление обменниками"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="➕ Добавить обменника", callback_data="add_exchanger")
    builder.button(text="📋 Список обменников", callback_data="list_exchangers")
    builder.button(text="◀️ Назад", callback_data="admin_back")
    
    builder.adjust(1)
    return builder.as_markup()

def get_exchangers_list_keyboard(exchangers: list):
    """Список обменников для админки"""
    builder = InlineKeyboardBuilder()
    
    for exchanger in exchangers:
        status = "✅" if exchanger['is_active'] else "❌"
        text = f"{status} @{exchanger['username']} ({exchanger['deposit_amount']} BYN)"
        builder.button(text=text, callback_data=f"manage_exchanger:{exchanger['user_id']}")
    
    builder.button(text="◀️ Назад", callback_data="admin_exchangers")
    builder.adjust(1)
    return builder.as_markup()

def get_exchanger_management_keyboard(exchanger_id: int, is_active: bool):
    """Управление конкретным обменником с удалением"""
    status_text = "❌ Деактивировать" if is_active else "✅ Активировать"
    status_data = f"deactivate_exchanger:{exchanger_id}" if is_active else f"activate_exchanger:{exchanger_id}"
    
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✏️ Изменить залог", callback_data=f"edit_deposit:{exchanger_id}"),
        InlineKeyboardButton(text="⚙️ Изменить комиссию", callback_data=f"edit_commission:{exchanger_id}")
    ], [
        InlineKeyboardButton(text="🔄 Направления", callback_data=f"manage_directions:{exchanger_id}")
    ], [
        InlineKeyboardButton(text=status_text, callback_data=status_data),
        InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_exchanger:{exchanger_id}")
    ], [
        InlineKeyboardButton(text="◀️ Назад к списку", callback_data="list_exchangers")
    ]])

def get_currencies_list_management_keyboard():
    """Клавиатура для управления списком валют"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить валюту", callback_data="add_currency"),
            InlineKeyboardButton(text="📋 Все валюты", callback_data="list_all_currencies")
        ],
        [
            InlineKeyboardButton(text="🎛️ По типам", callback_data="currencies_by_type"),
            InlineKeyboardButton(text="🔍 Найти валюту", callback_data="search_currency")
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="currencies_stats")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="admin_currencies")
        ]
    ])

def get_currencies_by_type_keyboard():
    """Выбор типа валют для просмотра"""
    builder = InlineKeyboardBuilder()
    
    for type_key, type_name in CURRENCY_TYPES.items():
        builder.button(text=type_name, callback_data=f"view_currencies_type:{type_key}")
    
    builder.button(text="📊 Статистика", callback_data="currencies_stats")
    builder.button(text="◀️ Назад", callback_data="admin_currencies")
    builder.adjust(1)
    return builder.as_markup()






def get_currencies_list_keyboard(currencies: List[Dict], page: int = 0, page_size: int = 10):
    """Список валют с пагинацией и кнопками управления - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    builder = InlineKeyboardBuilder()
    
    # Вычисляем начальный и конечный индексы для текущей страницы
    start_idx = page * page_size
    end_idx = start_idx + page_size
    page_currencies = currencies[start_idx:end_idx]
    
    for currency in page_currencies:
        status = "✅" if currency['is_active'] else "❌"
        
        # Формируем текст кнопки без эмодзи или с их ограничением
        name = currency['name']
        
        # Если есть эмодзи в начале, сохраняем их (обычно 1-2 символа)
        # и добавляем код валюты и сокращенное название
        if any(c in name for c in ['🇧🇾', '🇷🇺', '🇺🇸', '🇪🇺', '🇺🇦', '🇰🇿', '🇵🇱']):
            # Убираем флаги для более компактного отображения
            clean_name = name.replace('🇧🇾', '').replace('🇷🇺', '').replace('🇺🇸', '').replace('🇪🇺', '')\
                            .replace('🇺🇦', '').replace('🇰🇿', '').replace('🇵🇱', '').strip()
            
            # Берем только первые слова, без деталей
            parts = clean_name.split()
            if len(parts) > 1:
                # Оставляем только первое слово (например, "Белорусские" вместо "Белорусские рубли")
                clean_name = parts[0]
            
            # Формируем кнопку: статус + код + краткое название
            button_text = f"{status} {currency['code']}: {clean_name[:10]}"
        elif '₿' in name or '🔷' in name or '⚡' in name or '🟡' in name or '💲' in name or '🐕' in name or '🔶' in name:
            # Для криптовалют: статус + код + эмодзи + краткое название
            emoji = ''
            if '₿' in name:
                emoji = '₿'
            elif '🔷' in name:
                emoji = '🔷'
            elif '⚡' in name:
                emoji = '⚡'
            elif '🟡' in name:
                emoji = '🟡'
            elif '💲' in name:
                emoji = '💲'
            elif '🐕' in name:
                emoji = '🐕'
            elif '🔶' in name:
                emoji = '🔶'
            
            clean_name = name.replace(emoji, '').strip()
            parts = clean_name.split()
            if len(parts) > 1:
                clean_name = parts[0]
            
            button_text = f"{status} {currency['code']}: {emoji}{clean_name[:8]}"
        elif '💳' in name or '📱' in name:
            # Для электронных платежей
            emoji = '💳' if '💳' in name else '📱'
            clean_name = name.replace(emoji, '').strip()
            parts = clean_name.split()
            if len(parts) > 1:
                clean_name = parts[0]
            
            button_text = f"{status} {currency['code']}: {emoji}{clean_name[:8]}"
        else:
            # Для остальных случаев
            clean_name = name
            parts = clean_name.split()
            if len(parts) > 1:
                clean_name = parts[0]
            
            button_text = f"{status} {currency['code']}: {clean_name[:12]}"
        
        builder.button(
            text=button_text,
            callback_data=f"manage_currency:{currency['code']}"
        )
    
    # Кнопки пагинации
    pagination_row = []
    if page > 0:
        pagination_row.append(InlineKeyboardButton(text="⬅️ Предыдущая", callback_data=f"currencies_page:{page-1}"))
    
    if end_idx < len(currencies):
        pagination_row.append(InlineKeyboardButton(text="Следующая ➡️", callback_data=f"currencies_page:{page+1}"))
    
    if pagination_row:
        builder.row(*pagination_row)
    
    builder.row(InlineKeyboardButton(text="➕ Добавить валюту", callback_data="add_currency"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_currencies"))
    
    return builder.as_markup()









def get_currencies_list_simple_keyboard(currencies: List[Dict], page: int = 0, page_size: int = 10):
    """ПРОСТОЙ список валют - только код и статус"""
    builder = InlineKeyboardBuilder()
    
    # Вычисляем начальный и конечный индексы для текущей страницы
    start_idx = page * page_size
    end_idx = start_idx + page_size
    page_currencies = currencies[start_idx:end_idx]
    
    for currency in page_currencies:
        status = "✅" if currency['is_active'] else "❌"
        button_text = f"{status} {currency['code']}"
        
        builder.button(
            text=button_text,
            callback_data=f"manage_currency:{currency['code']}"
        )
    
    # Кнопки пагинации
    pagination_row = []
    if page > 0:
        pagination_row.append(InlineKeyboardButton(text="⬅️ Предыдущая", callback_data=f"currencies_page:{page-1}"))
    
    if end_idx < len(currencies):
        pagination_row.append(InlineKeyboardButton(text="Следующая ➡️", callback_data=f"currencies_page:{page+1}"))
    
    if pagination_row:
        builder.row(*pagination_row)
    
    builder.row(InlineKeyboardButton(text="➕ Добавить валюту", callback_data="add_currency"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_currencies"))
    
    return builder.as_markup()








def get_currency_management_keyboard(currency_code: str, is_active: bool, source: str = "all"):
    """Управление конкретной валютой с возвратом к источнику"""
    status_text = "❌ Деактивировать" if is_active else "✅ Активировать"
    status_data = f"deactivate_currency:{currency_code}" if is_active else f"activate_currency:{currency_code}"
    
    # Определяем кнопку возврата на основе источника
    if source == "all":
        back_callback = "list_all_currencies"
        back_text = "◀️ Назад к списку"
    elif source.startswith("type:"):
        currency_type = source.split(":")[1]
        back_callback = f"view_currencies_type:{currency_type}"
        back_text = f"◀️ Назад к типу"
    else:
        back_callback = "admin_currencies"
        back_text = "◀️ Назад к валютам"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"edit_currency_name:{currency_code}"),
            InlineKeyboardButton(text="🔄 Изменить тип", callback_data=f"edit_currency_type:{currency_code}")
        ],
        [
            InlineKeyboardButton(text=status_text, callback_data=status_data),
            InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_currency:{currency_code}")
        ],
        [
            InlineKeyboardButton(text="📊 Где используется", callback_data=f"currency_usage:{currency_code}")
        ],
        [
            InlineKeyboardButton(text=back_text, callback_data=back_callback)
        ]
    ])









def get_currency_delete_confirmation_keyboard(currency_code: str):
    """Подтверждение удаления валюты"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_currency:{currency_code}"),
            InlineKeyboardButton(text="❌ Нет, отменить", callback_data=f"manage_currency:{currency_code}")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад к списку", callback_data="list_all_currencies")
        ]
    ])

def get_currency_type_selection_keyboard(currency_code: str):
    """Выбор типа валюты при редактировании"""
    builder = InlineKeyboardBuilder()
    
    for type_key, type_name in CURRENCY_TYPES.items():
        builder.button(
            text=type_name,
            callback_data=f"update_currency_type:{currency_code}:{type_key}"
        )
    
    builder.button(text="◀️ Назад", callback_data=f"manage_currency:{currency_code}")
    builder.adjust(1)
    return builder.as_markup()

def get_back_to_currency_management_keyboard(currency_code: str):
    """Клавиатура для возврата к управлению валютой"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к валюте", callback_data=f"manage_currency:{currency_code}")]
    ])

def get_exchanger_delete_confirmation_keyboard(exchanger_id: int):
    """Подтверждение удаления обменника"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_exchanger:{exchanger_id}"),
        InlineKeyboardButton(text="❌ Нет, отменить", callback_data=f"manage_exchanger:{exchanger_id}")
    ], [
        InlineKeyboardButton(text="◀️ Назад к списку", callback_data="list_exchangers")
    ]])

def get_add_currency_keyboard():
    """Клавиатура для добавления валюты"""
    builder = InlineKeyboardBuilder()
    
    for type_key, type_name in CURRENCY_TYPES.items():
        builder.button(text=type_name, callback_data=f"add_currency_type:{type_key}")
    
    builder.button(text="◀️ Назад", callback_data="admin_currencies")
    builder.adjust(1)
    return builder.as_markup()

def get_back_to_currencies_keyboard():
    """Возврат к валютам"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Назад к валютам", callback_data="admin_currencies")
    ]])

def get_back_to_exchangers_keyboard():
    """Возврат к обменникам"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Назад к обменникам", callback_data="admin_exchangers")
    ]])

def get_back_to_admin_keyboard():
    """Возврат в админку"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ В панель гаранта", callback_data="admin_back")
    ]])

def get_currency_management_keyboard_old():
    """Клавиатура для управления валютами (старая версия)"""
    keyboard = [
        [InlineKeyboardButton("📥 Добавить валюту", callback_data="add_currency")],
        [InlineKeyboardButton("📤 Удалить валюту", callback_data="remove_currency")],
        [InlineKeyboardButton("📋 Список валют", callback_data="list_currencies")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_exchanger_directions_keyboard(exchanger_id: int):
    """Клавиатура управления направлениями обменника"""
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить направление", callback_data=f"add_direction:{exchanger_id}")],
        [InlineKeyboardButton(text="📋 Список направлений", callback_data=f"list_directions:{exchanger_id}")],
        [InlineKeyboardButton(text="◀️ Назад к обменнику", callback_data=f"manage_exchanger:{exchanger_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_directions_list_keyboard(exchanger_id: int, directions: List[Dict]):
    """Список направлений обменника с кнопками управления"""
    builder = InlineKeyboardBuilder()
    
    for direction in directions:
        status = "✅" if direction['is_active'] else "❌"
        text = f"{status} {direction['sell']}->{direction['buy']}"
        builder.button(
            text=text,
            callback_data=f"toggle_direction:{exchanger_id}:{direction['sell']}:{direction['buy']}"
        )
        builder.button(
            text="🗑️",
            callback_data=f"remove_direction:{exchanger_id}:{direction['sell']}:{direction['buy']}"
        )
    
    builder.button(text="➕ Добавить направление", callback_data=f"add_direction:{exchanger_id}")
    builder.button(text="◀️ Назад", callback_data=f"manage_directions:{exchanger_id}")
    
    builder.adjust(2, 1)
    return builder.as_markup()

def get_currency_selection_keyboard(exchanger_id: int, step: str, selected_sell_currency: str = None):
    """Выбор валюты для направления"""
    builder = InlineKeyboardBuilder()
    
    currencies = db.get_all_currencies()
    for currency in currencies:
        if currency['is_active']:
            if step == "select_sell":
                builder.button(
                    text=currency['name'],
                    callback_data=f"select_sell:{exchanger_id}:{currency['code']}"
                )
            elif step == "select_buy":
                if currency['code'] != selected_sell_currency:
                    builder.button(
                        text=currency['name'],
                        callback_data=f"select_buy:{exchanger_id}:{selected_sell_currency}:{currency['code']}"
                    )
    
    builder.button(text="◀️ Назад", callback_data=f"manage_directions:{exchanger_id}")
    builder.adjust(2)
    return builder.as_markup()

def get_confirm_reset_groups_keyboard():
    """Клавиатура подтверждения сброса групп"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, сбросить все группы", callback_data="confirm_reset_groups"),
            InlineKeyboardButton(text="❌ Нет, отменить", callback_data="admin_back")
        ]
    ])

def get_main_inline_menu(is_owner: bool = False):
    """Главное меню в inline-формате для редактирования сообщений"""
    buttons = [
        [InlineKeyboardButton(text="🔄 Начать обмен", callback_data="start_exchange")],
        [InlineKeyboardButton(text="ℹ️ О боте", callback_data="about_bot"), 
         InlineKeyboardButton(text="👤 Профиль", callback_data="profile")]
    ]
    
    if is_owner:
        buttons.append([InlineKeyboardButton(text="🛡️ Панель гаранта", callback_data="guarantor_panel")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_to_exchanger_keyboard(exchanger_id: int):
    """Клавиатура для возврата к управлению обменником"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Назад к обменнику", callback_data=f"manage_exchanger:{exchanger_id}")
    ]])

def get_currency_search_results_keyboard(currencies: List[Dict], search_query: str):
    """Клавиатура для результатов поиска валюты"""
    builder = InlineKeyboardBuilder()
    
    for currency in currencies[:10]:  # Ограничим 10 результатами
        status = "✅" if currency['is_active'] else "❌"
        button_text = f"{status} {currency['code']} - {currency['name'][:15]}"
        builder.button(
            text=button_text,
            callback_data=f"manage_currency:{currency['code']}"
        )
    
    builder.button(text="🔍 Новый поиск", callback_data="search_currency")
    builder.button(text="📋 Все валюты", callback_data="list_all_currencies")
    builder.button(text="◀️ Назад", callback_data="admin_currencies")
    
    builder.adjust(1, 1, 2, 1)
    return builder.as_markup()

def get_currencies_type_view_keyboard(currency_type: str, currencies: List[Dict]):
    """Клавиатура для просмотра валют по типу"""
    builder = InlineKeyboardBuilder()
    
    for currency in currencies:
        status = "✅" if currency['is_active'] else "❌"
        button_text = f"{status} {currency['code']} - {currency['name'][:15]}"
        builder.button(
            text=button_text,
            callback_data=f"manage_currency:{currency['code']}"
        )
    
    builder.button(text="◀️ Назад к типам", callback_data="currencies_by_type")
    builder.adjust(1)
    return builder.as_markup()


def get_back_to_currencies_type_keyboard():
    """Возврат к типам валют"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Назад к типам", callback_data="currencies_by_type")
    ]])






def get_currencies_list_with_source(currencies: List[Dict], page: int = 0, source: str = "all", page_size: int = 10):
    """Список валют с указанием источника"""
    builder = InlineKeyboardBuilder()
    
    # Вычисляем начальный и конечный индексы для текущей страницы
    start_idx = page * page_size
    end_idx = start_idx + page_size
    page_currencies = currencies[start_idx:end_idx]
    
    for currency in page_currencies:
        status = "✅" if currency['is_active'] else "❌"
        
        # Упрощаем текст кнопки - только статус и код
        button_text = f"{status} {currency['code']}"
        
        # Формируем callback_data с источником
        if source == "all":
            callback_data = f"manage_currency:{currency['code']}:all"
        else:
            callback_data = f"manage_currency:{currency['code']}:type:{source}"
        
        builder.button(
            text=button_text,
            callback_data=callback_data
        )
    
    # Располагаем кнопки по 2 в ряд
    builder.adjust(2)
    
    # Кнопки пагинации с указанием источника
    pagination_row = []
    if page > 0:
        pagination_row.append(InlineKeyboardButton(
            text="⬅️ Назад", 
            callback_data=f"currencies_page:{page-1}:{source}"
        ))
    
    if end_idx < len(currencies):
        pagination_row.append(InlineKeyboardButton(
            text="Вперед ➡️", 
            callback_data=f"currencies_page:{page+1}:{source}"
        ))
    
    if pagination_row:
        # Добавляем пагинацию в отдельный ряд
        builder.row(*pagination_row)
    
    # Кнопки управления с учетом источника
    if source == "all":
        builder.row(InlineKeyboardButton(text="➕ Добавить валюту", callback_data="add_currency"))
        builder.row(InlineKeyboardButton(text="◀️ Назад к валютам", callback_data="admin_currencies"))
    else:
        builder.row(InlineKeyboardButton(text="◀️ Назад к типам", callback_data="currencies_by_type"))
    
    return builder.as_markup()