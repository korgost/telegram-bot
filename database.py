# database.py
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

class Database:
    def __init__(self):
        self.db_path = Path(__file__).parent / "data" / "exchange_bot.db"
        self.db_path.parent.mkdir(exist_ok=True)
        self.init_db()
    
    def init_db(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Таблица обменников
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS exchangers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                username TEXT,
                full_name TEXT,
                deposit_amount REAL DEFAULT 0,
                commission_rate REAL DEFAULT 0.03,
                rating REAL DEFAULT 5.0,
                total_deals INTEGER DEFAULT 0,
                successful_deals INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица сделок
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deal_id TEXT UNIQUE,
                client_id INTEGER,
                client_name TEXT,
                exchanger_id INTEGER,
                sell_currency TEXT,
                buy_currency TEXT,
                amount REAL,
                final_amount REAL,
                chat_id INTEGER,
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
                chat_id INTEGER UNIQUE,
                total_deals INTEGER DEFAULT 0,
                last_used TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                cooldown_until TIMESTAMP
            )
        ''')
        
        # Таблица настроек бота
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE,
                value TEXT,
                description TEXT
            )
        ''')
        
        # Добавляем тестовых обменников
        test_exchangers = [
            (123456789, 'ilya.k', 'Обменник 1', 6000.0, 0.03, 4.3),
            (987654321, 'Obmennik2', 'Обменник 2', 300.0, 0.025, 4.7),
            (555555555, 'Obmennik3', 'Обменник 3', 250.0, 0.035, 4.5),
            (666666666, 'Obmennik4', 'Обменник 4', 500.0, 0.028, 4.8),
            (777777777, 'Obmennik5', 'Обменник 5', 1000.0, 0.022, 4.9)
        ]
        
        for exchanger in test_exchangers:
            cursor.execute('''
                INSERT OR IGNORE INTO exchangers 
                (user_id, username, full_name, deposit_amount, commission_rate, rating)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', exchanger)
        
        # Добавляем настройки по умолчанию
        default_settings = [
            ('owner_commission', '0.01', 'Комиссия гаранта (1%)'),
            ('max_deals_per_group', '3', 'Максимум сделок на группу'),
            ('group_cooldown_hours', '2', 'Время коудауна групп в часах'),
            ('default_exchanger_commission', '0.03', 'Комиссия обменника по умолчанию')
        ]
        
        for key, value, description in default_settings:
            cursor.execute('''
                INSERT OR IGNORE INTO bot_settings (key, value, description)
                VALUES (?, ?, ?)
            ''', (key, value, description))
        
        conn.commit()
        conn.close()
        print("✅ База данных инициализирована")
    
    def init_groups(self, group_ids: List[int]):
        """Инициализация групп (вызывается после загрузки конфига)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for chat_id in group_ids:
            cursor.execute('''
                INSERT OR IGNORE INTO group_stats (chat_id, total_deals, last_used)
                VALUES (?, 0, CURRENT_TIMESTAMP)
            ''', (chat_id,))
        
        conn.commit()
        conn.close()
        print(f"✅ Инициализировано {len(group_ids)} групп")
    
    def get_available_exchangers(self, amount: float) -> List[Dict]:
        """Получение доступных обменников"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, username, deposit_amount, commission_rate, rating 
            FROM exchangers 
            WHERE deposit_amount >= ? AND is_active = 1
            ORDER BY rating DESC, commission_rate ASC
        ''', (amount,))
        
        exchangers = []
        for row in cursor.fetchall():
            exchangers.append({
                'user_id': row[0],
                'username': row[1],
                'max_amount': row[2],
                'commission_rate': row[3],
                'rating': row[4]
            })
        
        conn.close()
        return exchangers
    
    def get_all_exchangers(self) -> List[Dict]:
        """Получение всех обменников для админки"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, username, full_name, deposit_amount, commission_rate, 
                   rating, total_deals, successful_deals, is_active
            FROM exchangers 
            ORDER BY is_active DESC, rating DESC
        ''')
        
        exchangers = []
        for row in cursor.fetchall():
            exchangers.append({
                'user_id': row[0],
                'username': row[1],
                'full_name': row[2],
                'deposit_amount': row[3],
                'commission_rate': row[4],
                'rating': row[5],
                'total_deals': row[6],
                'successful_deals': row[7],
                'is_active': bool(row[8])
            })
        
        conn.close()
        return exchangers
    
    def get_exchanger_commission(self, user_id: int) -> float:
        """Получение комиссии конкретного обменника"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT commission_rate FROM exchangers WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        conn.close()
        return result[0] if result else 0.03  # Возвращаем комиссию обменника или 3% по умолчанию
    
    def update_exchanger_deposit(self, user_id: int, new_deposit: float):
        """Обновление залога обменника"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE exchangers 
            SET deposit_amount = ?
            WHERE user_id = ?
        ''', (new_deposit, user_id))
        
        conn.commit()
        conn.close()
    
    def update_exchanger_commission(self, user_id: int, new_commission: float):
        """Обновление комиссии обменника"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE exchangers 
            SET commission_rate = ?
            WHERE user_id = ?
        ''', (new_commission, user_id))
        
        conn.commit()
        conn.close()
    
    def toggle_exchanger_active(self, user_id: int, is_active: bool):
        """Активация/деактивация обменника"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE exchangers 
            SET is_active = ?
            WHERE user_id = ?
        ''', (is_active, user_id))
        
        conn.commit()
        conn.close()
    
    def get_bot_settings(self) -> Dict:
        """Получение настроек бота"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Получаем все настройки
        cursor.execute('SELECT key, value, description FROM bot_settings')
        settings = {}
        for row in cursor.fetchall():
            settings[row[0]] = {
                'value': row[1],
                'description': row[2]
            }
        
        conn.close()
        return settings
    
    def update_setting(self, key: str, value: str):
        """Обновление настройки"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE bot_settings 
            SET value = ?
            WHERE key = ?
        ''', (value, key))
        
        conn.commit()
        conn.close()
    
    def add_exchanger(self, user_id: int, username: str, full_name: str, deposit_amount: float):
        """Добавление нового обменника"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        from config import DEFAULT_EXCHANGER_COMMISSION
        
        cursor.execute('''
            INSERT OR REPLACE INTO exchangers 
            (user_id, username, full_name, deposit_amount, commission_rate, rating)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, full_name, deposit_amount, DEFAULT_EXCHANGER_COMMISSION, 5.0))
        
        conn.commit()
        conn.close()
    
    def get_best_group(self) -> Optional[int]:
        """Получение лучшей группы для новой сделки"""
        conn = sqlite3.connect(self.db_path)
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
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Увеличиваем счетчик сделок
        cursor.execute('''
            UPDATE group_stats 
            SET total_deals = total_deals + 1, 
                last_used = CURRENT_TIMESTAMP
            WHERE chat_id = ?
        ''', (chat_id,))
        
        # Проверяем是否需要 охлаждения
        cursor.execute('''
            SELECT total_deals FROM group_stats WHERE chat_id = ?
        ''', (chat_id,))
        
        current_deals = cursor.fetchone()[0]
        
        if current_deals >= max_deals:
            from datetime import datetime, timedelta
            cooldown_until = datetime.now() + timedelta(hours=2)
            cursor.execute('''
                UPDATE group_stats 
                SET cooldown_until = ?, is_active = 0
                WHERE chat_id = ?
            ''', (cooldown_until, chat_id))
        
        conn.commit()
        conn.close()
    
    def reset_group_cooldown(self, chat_id: int):
        """Сброс охлаждения группы"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE group_stats 
            SET cooldown_until = NULL, is_active = 1, total_deals = 0
            WHERE chat_id = ?
        ''', (chat_id,))
        
        conn.commit()
        conn.close()
    
    def get_group_stats(self) -> List[Dict]:
        """Получение статистики всех групп"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT chat_id, total_deals, last_used, is_active, cooldown_until
            FROM group_stats 
            ORDER BY chat_id
        ''')
        
        stats = []
        for row in cursor.fetchall():
            stats.append({
                'chat_id': row[0],
                'total_deals': row[1],
                'last_used': row[2],
                'is_active': bool(row[3]),
                'cooldown_until': row[4]
            })
        
        conn.close()
        return stats

# Глобальный экземпляр базы данных
db = Database()