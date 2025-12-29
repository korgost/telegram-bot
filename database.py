import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from config import GROUP_IDS, DEFAULT_CURRENCIES, CURRENCY_TYPES
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.db_path = Path(__file__).parent / "data" / "exchange_bot.db"
        self.db_path.parent.mkdir(exist_ok=True)
        self.init_db()
    
    def get_connection(self):
        """Получение соединения с базой"""
        return sqlite3.connect(self.db_path)
    


    
    def init_db(self):
        """Инициализация базы данных"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Таблица онлайн пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS online_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_online BOOLEAN DEFAULT 1
            )
        ''')
        
        # Таблица валют
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS currencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица обменников
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS exchangers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT NOT NULL,
                full_name TEXT,
                deposit_amount REAL DEFAULT 0,
                commission_rate REAL DEFAULT 0.03,
                directions TEXT DEFAULT '',
                total_deals INTEGER DEFAULT 0,
                successful_deals INTEGER DEFAULT 0,
                total_volume REAL DEFAULT 0,
                total_income REAL DEFAULT 0,
                owner_income REAL DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица настроек бота
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Добавляем запись о последней очистке статистики
        cursor.execute('''
            INSERT OR IGNORE INTO bot_settings (key, value)
            VALUES ('last_stats_reset', NULL)
        ''')
        
        # Таблица направлений обменников
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS exchanger_directions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchanger_id INTEGER NOT NULL,
                sell_currency TEXT NOT NULL,
                buy_currency TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (exchanger_id) REFERENCES exchangers(user_id) ON DELETE CASCADE,
                UNIQUE(exchanger_id, sell_currency, buy_currency)
            )
        ''')
        
        # Таблица сделок
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deal_id TEXT UNIQUE NOT NULL,
                client_id INTEGER NOT NULL,
                client_name TEXT NOT NULL,
                exchanger_id INTEGER NOT NULL,
                sell_currency TEXT NOT NULL,
                buy_currency TEXT NOT NULL,
                sell_amount REAL NOT NULL,
                final_amount REAL NOT NULL,
                exchange_rate REAL NOT NULL,
                owner_fee REAL NOT NULL,
                exchanger_fee REAL NOT NULL,
                chat_id INTEGER NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                completion_reason TEXT
            )
        ''')
                
        # Таблица статистики групп
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS group_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER UNIQUE NOT NULL,
                total_deals INTEGER DEFAULT 0,
                last_used TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                cooldown_until TIMESTAMP
            )
        ''')
        
        # Добавляем валюты по умолчанию
        for currency_type, currencies in DEFAULT_CURRENCIES.items():
            for code, name in currencies.items():
                cursor.execute('''
                    INSERT OR IGNORE INTO currencies (type, code, name, is_active)
                    VALUES (?, ?, ?, ?)
                ''', (currency_type, code, name, 1))
        
        # Добавляем группы
        for chat_id in GROUP_IDS:
            cursor.execute('''
                INSERT OR IGNORE INTO group_stats (chat_id, total_deals, last_used)
                VALUES (?, 0, CURRENT_TIMESTAMP)
            ''', (chat_id,))
        
        # Тестовые обменники
        test_exchangers = [
            (123, 'ilya.k', 'Обменник 1', 900.0, 0.03),
            (987654321, 'Obmennik2', 'Обменник 2', 500.0, 0.025),
            (555555555, 'Obmennik3', 'Обменник 3', 1000.0, 0.035),
        ]
        
        for exchanger in test_exchangers:
            cursor.execute('''
                INSERT OR IGNORE INTO exchangers 
                (user_id, username, full_name, deposit_amount, commission_rate)
                VALUES (?, ?, ?, ?, ?)
            ''', exchanger)
        
        conn.commit()
        conn.close()
        print("✅ База данных инициализирована")
    
    # === МЕТОДЫ ДЛЯ ВАЛЮТ ===
    
    def get_all_currencies(self) -> List[Dict]:
        """Получение всех валют"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT type, code, name, is_active 
            FROM currencies 
            ORDER BY type, code
        ''')
        
        currencies = []
        for row in cursor.fetchall():
            currencies.append({
                'type': row[0],
                'code': row[1], 
                'name': row[2],
                'is_active': bool(row[3])
            })
        
        conn.close()
        return currencies
    
    def add_currency(self, currency_type: str, code: str, name: str) -> bool:
        """Добавление новой валюты"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO currencies (type, code, name, is_active)
                VALUES (?, ?, ?, 1)
            ''', (currency_type, code, name))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def toggle_currency(self, code: str, is_active: bool) -> bool:
        """Активация/деактивация валюты"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE currencies SET is_active = ? WHERE code = ?
        ''', (is_active, code))
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success
    
    def get_currency_by_code(self, code: str) -> Optional[Dict]:
        """Получение информации о валюте по коду"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT type, code, name, is_active, created_at
            FROM currencies WHERE code = ?
        ''', (code,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'type': row[0],
                'code': row[1],
                'name': row[2],
                'is_active': bool(row[3]),
                'created_at': row[4]
            }
        return None
    
    def update_currency(self, code: str, name: str = None, 
                       currency_type: str = None, is_active: bool = None) -> bool:
        """Обновление информации о валюте"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        
        if currency_type is not None:
            updates.append("type = ?")
            params.append(currency_type)
        
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(int(is_active))
        
        if not updates:
            conn.close()
            return False
        
        params.append(code)
        
        query = f"UPDATE currencies SET {', '.join(updates)} WHERE code = ?"
        cursor.execute(query, params)
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success
    
    def delete_currency(self, code: str) -> bool:
        """Удаление валюты (только если не используется в направлениях)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Проверяем, используется ли валюта в направлениях
        cursor.execute('''
            SELECT COUNT(*) FROM exchanger_directions 
            WHERE sell_currency = ? OR buy_currency = ?
        ''', (code, code))
        
        count = cursor.fetchone()[0]
        if count > 0:
            conn.close()
            return False  # Нельзя удалить, используется в направлениях
        
        cursor.execute('DELETE FROM currencies WHERE code = ?', (code,))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success
    
    def get_currencies_by_type(self, currency_type: str) -> List[Dict]:
        """Получение валют по типу"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT type, code, name, is_active
            FROM currencies 
            WHERE type = ? AND is_active = 1
            ORDER BY name
        ''', (currency_type,))
        
        currencies = []
        for row in cursor.fetchall():
            currencies.append({
                'type': row[0],
                'code': row[1],
                'name': row[2],
                'is_active': bool(row[3])
            })
        
        conn.close()
        return currencies
    
    def get_active_currencies_count(self) -> Dict[str, int]:
        """Получение количества активных валют по типам"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT type, COUNT(*) 
            FROM currencies 
            WHERE is_active = 1
            GROUP BY type
        ''')
        
        result = {}
        for row in cursor.fetchall():
            result[row[0]] = row[1]
        
        conn.close()
        return result
    
    # === МЕТОДЫ ДЛЯ ОБМЕННИКОВ ===
    
    def get_all_exchangers(self) -> List[Dict]:
        """Получение всех обменников"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, username, full_name, deposit_amount, commission_rate,
                   total_deals, successful_deals, total_volume, total_income, owner_income, is_active
            FROM exchangers 
            ORDER BY is_active DESC, total_volume DESC
        ''')
        
        exchangers = []
        for row in cursor.fetchall():
            exchangers.append({
                'user_id': row[0],
                'username': row[1],
                'full_name': row[2],
                'deposit_amount': row[3],
                'commission_rate': row[4],
                'total_deals': row[5],
                'successful_deals': row[6],
                'total_volume': row[7],
                'total_income': row[8],
                'owner_income': row[9],
                'is_active': bool(row[10])
            })
        
        conn.close()
        return exchangers
    
    def add_exchanger(self, user_id: int, username: str, full_name: str, 
                     deposit_amount: float, commission_rate: float) -> bool:
        """Добавление нового обменника"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO exchangers 
                (user_id, username, full_name, deposit_amount, commission_rate)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, full_name, deposit_amount, commission_rate))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def update_exchanger_deposit(self, user_id: int, deposit_amount: float) -> bool:
        """Обновление залога обменника"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE exchangers SET deposit_amount = ? WHERE user_id = ?
        ''', (deposit_amount, user_id))
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success
    
    def update_exchanger_commission(self, user_id: int, commission_rate: float) -> bool:
        """Обновление комиссии обменника"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE exchangers SET commission_rate = ? WHERE user_id = ?
        ''', (commission_rate, user_id))
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success
    
    def toggle_exchanger(self, user_id: int, is_active: bool) -> bool:
        """Активация/деактивация обменника"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE exchangers SET is_active = ? WHERE user_id = ?
        ''', (is_active, user_id))
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success
    
    def get_exchanger_stats(self, user_id: int) -> Optional[Dict]:
        """Получение статистики обменника"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT username, deposit_amount, commission_rate, total_deals, 
                   successful_deals, total_volume, total_income, owner_income, is_active
            FROM exchangers WHERE user_id = ?
        ''', (user_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'username': row[0],
                'deposit_amount': row[1],
                'commission_rate': row[2],
                'total_deals': row[3],
                'successful_deals': row[4],
                'total_volume': row[5],
                'total_income': row[6],
                'owner_income': row[7],
                'is_active': bool(row[8])
            }
        return None
    
    # === МЕТОДЫ ДЛЯ НАПРАВЛЕНИЙ ОБМЕННИКОВ ===
    
    def get_exchanger_directions_list(self, exchanger_id: int) -> List[Dict]:
        """Получение всех направлений обменника - возвращает список словарей"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT sell_currency, buy_currency, is_active
            FROM exchanger_directions
            WHERE exchanger_id = ?
            ORDER BY sell_currency, buy_currency
        ''', (exchanger_id,))
        
        directions = []
        for row in cursor.fetchall():
            directions.append({
                'sell': row[0],
                'buy': row[1],
                'is_active': bool(row[2])
            })
        
        conn.close()
        return directions
    
    def add_exchanger_direction(self, exchanger_id: int, sell_currency: str, buy_currency: str) -> bool:
        """Добавление направления обменнику"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO exchanger_directions (exchanger_id, sell_currency, buy_currency)
                VALUES (?, ?, ?)
            ''', (exchanger_id, sell_currency, buy_currency))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def remove_exchanger_direction(self, exchanger_id: int, sell_currency: str, buy_currency: str) -> bool:
        """Удаление направления у обменника"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM exchanger_directions
            WHERE exchanger_id = ? AND sell_currency = ? AND buy_currency = ?
        ''', (exchanger_id, sell_currency, buy_currency))
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success
    
    def toggle_exchanger_direction(self, exchanger_id: int, sell_currency: str, buy_currency: str, is_active: bool) -> bool:
        """Активация/деактивация направления обменника"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE exchanger_directions
            SET is_active = ?
            WHERE exchanger_id = ? AND sell_currency = ? AND buy_currency = ?
        ''', (is_active, exchanger_id, sell_currency, buy_currency))
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success
    
    def check_exchanger_supports_direction(self, exchanger_id: int, sell_currency: str, buy_currency: str) -> bool:
        """Проверяет, поддерживает ли обменник направление (и оно активно)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) FROM exchanger_directions
            WHERE exchanger_id = ? AND sell_currency = ? AND buy_currency = ? AND is_active = 1
        ''', (exchanger_id, sell_currency, buy_currency))
        
        result = cursor.fetchone()[0] > 0
        conn.close()
        return result
    
    def exchanger_has_directions(self, exchanger_id: int) -> bool:
        """Проверяет, есть ли у обменника хоть одно направление"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) FROM exchanger_directions
            WHERE exchanger_id = ?
        ''', (exchanger_id,))
        
        count = cursor.fetchone()[0]
        conn.close()
        
        return count > 0
    
    def get_exchanger_directions(self, user_id: int) -> Optional[str]:
        """Получение направлений обменника (строка вроде 'RUB->USDT,BYN->BTC')"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT directions FROM exchangers WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row and row[0] is not None else ""
    
    def update_exchanger_directions(self, user_id: int, directions: str) -> bool:
        """Обновление направлений обменника"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('UPDATE exchangers SET directions = ? WHERE user_id = ?', (directions, user_id))
        success = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        return success
    
    def update_exchanger_stats(self, user_id: int, deal_amount: float, 
                             owner_fee: float, exchanger_fee: float, success: bool):
        """Обновление статистики обменника после сделки"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if success:
            cursor.execute('''
                UPDATE exchangers 
                SET total_deals = total_deals + 1,
                    successful_deals = successful_deals + 1,
                    total_volume = total_volume + ?,
                    total_income = total_income + ?,
                    owner_income = owner_income + ?
                WHERE user_id = ?
            ''', (deal_amount, exchanger_fee, owner_fee, user_id))
        else:
            cursor.execute('''
                UPDATE exchangers 
                SET total_deals = total_deals + 1,
                    total_volume = total_volume + ?
                WHERE user_id = ?
            ''', (deal_amount, user_id))
        
        conn.commit()
        conn.close()
    
    def delete_exchanger(self, user_id: int) -> bool:
        """Полное удаление обменника из базы данных"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('DELETE FROM exchangers WHERE user_id = ?', (user_id,))
            
            success = cursor.rowcount > 0
            conn.commit()
            
            if success:
                logger.info(f"✅ Обменник {user_id} удален из базы данных")
            else:
                logger.warning(f"⚠️ Обменник {user_id} не найден для удаления")
                
            return success
            
        except Exception as e:
            logger.error(f"❌ Ошибка удаления обменника {user_id}: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    # === МЕТОДЫ ДЛЯ СДЕЛОК ===
    
    def get_available_exchangers(self, amount: float) -> List[Dict]:
        """Получение доступных обменников для суммы"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, username, deposit_amount, commission_rate
            FROM exchangers 
            WHERE deposit_amount >= ? AND is_active = 1
            ORDER BY commission_rate ASC, deposit_amount DESC
        ''', (amount,))
        
        exchangers = []
        for row in cursor.fetchall():
            exchangers.append({
                'user_id': row[0],
                'username': row[1],
                'deposit_amount': row[2],
                'commission_rate': row[3]
            })
        
        conn.close()
        return exchangers
    
    def get_best_group(self) -> Optional[int]:
        """Получение лучшей группы для сделки"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT chat_id FROM group_stats 
            WHERE is_active = 1 
            AND (cooldown_until IS NULL OR cooldown_until < CURRENT_TIMESTAMP)
            ORDER BY total_deals ASC, last_used ASC
            LIMIT 1
        ''')
        
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def update_group_stats(self, chat_id: int, max_deals: int = 3):
        """Обновление статистики группы"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE group_stats 
            SET total_deals = total_deals + 1, 
                last_used = CURRENT_TIMESTAMP
            WHERE chat_id = ?
        ''', (chat_id,))
        
        cursor.execute('SELECT total_deals FROM group_stats WHERE chat_id = ?', (chat_id,))
        current_deals = cursor.fetchone()[0]
        
        if current_deals >= max_deals:
            cooldown_until = datetime.now() + timedelta(hours=2)
            cursor.execute('''
                UPDATE group_stats 
                SET cooldown_until = ?, is_active = 0
                WHERE chat_id = ?
            ''', (cooldown_until, chat_id))
        
        conn.commit()
        conn.close()
    
    def reset_group_cooldown(self, chat_id: int):
        """Сброс коудауна группы"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE group_stats 
            SET cooldown_until = NULL, is_active = 1, total_deals = 0
            WHERE chat_id = ?
        ''', (chat_id,))
        
        conn.commit()
        conn.close()
    
    # === СТАТИСТИКА ===
    
    def get_owner_total_income(self) -> float:
        """Общий доход гаранта"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT SUM(owner_income) FROM exchangers')
        result = cursor.fetchone()
        conn.close()
        return result[0] or 0.0
    
    def get_total_deals_count(self) -> int:
        """Общее количество сделок"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM deals')
        result = cursor.fetchone()
        conn.close()
        return result[0] or 0
    
    def get_online_users_count(self) -> int:
        """Количество онлайн пользователей за последние 10 минут"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) FROM online_users 
            WHERE last_seen > datetime('now', '-10 minutes')
        ''')
        
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0
    
    def update_user_online(self, user_id: int, username: str):
        """Обновление статуса онлайн пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO online_users (user_id, username, last_seen, is_online)
            VALUES (?, ?, CURRENT_TIMESTAMP, 1)
        ''', (user_id, username))
        
        conn.commit()
        conn.close()
    
    def cleanup_old_users(self):
        """Очистка устаревших записей пользователей"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM online_users 
            WHERE last_seen < datetime('now', '-1 day')
        ''')






    # === МЕТОДЫ ДЛЯ НАСТРОЕК БОТА ===
    
    def get_bot_setting(self, key: str) -> Optional[str]:
        """Получение настройки бота"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT value FROM bot_settings WHERE key = ?
        ''', (key,))
        
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    
    def set_bot_setting(self, key: str, value: str) -> bool:
        """Установка настройки бота"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO bot_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (key, value))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка установки настройки {key}: {e}")
            return False
        finally:
            conn.close()
    
    def clear_all_stats(self) -> bool:
        """Полная очистка всей статистики (сделки, доходы, счетчики)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Очищаем статистику обменников
            cursor.execute('''
                UPDATE exchangers 
                SET total_deals = 0,
                    successful_deals = 0,
                    total_volume = 0,
                    total_income = 0,
                    owner_income = 0
            ''')
            
            # Очищаем таблицу сделок
            cursor.execute('DELETE FROM deals')
            
            # Сбрасываем статистику групп
            cursor.execute('''
                UPDATE group_stats 
                SET total_deals = 0,
                    is_active = 1,
                    cooldown_until = NULL
            ''')
            
            # Сбрасываем онлайн пользователей
            cursor.execute('DELETE FROM online_users')
            
            # Сохраняем дату очистки
            from datetime import datetime
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('''
                INSERT OR REPLACE INTO bot_settings (key, value, updated_at)
                VALUES ('last_stats_reset', ?, CURRENT_TIMESTAMP)
            ''', (current_time,))
            
            conn.commit()
            logger.info("✅ Вся статистика очищена")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки статистики: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()








        
        conn.commit()
        conn.close()

# Глобальный экземпляр
db = Database()