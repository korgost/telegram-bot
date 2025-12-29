import requests
import time
import logging
from typing import Dict
from config import BOT_TOKEN, OWNER_ID
from aiogram import Bot

logger = logging.getLogger(__name__)

class APIMonitor:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.last_alert_time = {}
        self.alert_cooldown = 3600  # 1 час между уведомлениями
        self.api_status = {}
        
        # ТОЛЬКО ПРОВЕРЕННЫЕ И РАБОЧИЕ API
        self.providers = {
            "Binance": self.check_binance,
            "CoinGecko": self.check_coingecko,
            "CBR": self.check_cbr,   # Центробанк России
            "NBRB": self.check_nbrb  # Нацбанк Беларуси
            # Frankfurter убрали, используем exchangerate.host без мониторинга
        }

    
    async def check_all_apis(self) -> Dict[str, bool]:
        """Проверяет все API и отправляет уведомления если что-то упало"""
        results = {}
        down_apis = []
        
        for name, check_func in self.providers.items():
            is_working = check_func()
            results[name] = is_working
            
            if not is_working:
                down_apis.append(name)
                await self.send_alert_if_needed(name)
        
        self.api_status = results
        return results
    

    def check_binance(self) -> bool:
        """Проверяет Binance API - самый надежный"""
        try:
            response = requests.get(
                "https://api.binance.com/api/v3/ping", 
                timeout=5
            )
            return response.status_code == 200
        except:
            return False
    
    def check_coingecko(self) -> bool:
        """Проверяет CoinGecko API"""
        try:
            response = requests.get(
                "https://api.coingecko.com/api/v3/ping", 
                timeout=5
            )
            return response.status_code == 200
        except:
            return False
    
    def check_cbr(self) -> bool:
        """Проверяет API Центробанка России"""
        try:
            response = requests.get(
                "https://www.cbr-xml-daily.ru/daily_json.js", 
                timeout=5
            )
            return response.status_code == 200
        except:
            return False
    
    def check_nbrb(self) -> bool:
        """Проверяет API Нацбанка Беларуси"""
        try:
            response = requests.get(
                "https://www.nbrb.by/api/exrates/rates/USD?parammode=2", 
                timeout=5
            )
            return response.status_code == 200
        except:
            return False
    
    def check_frankfurter(self) -> bool:
        """Проверяет Frankfurter API для фиатных валют"""
        try:
            response = requests.get(
                "https://api.frankfurter.app/currencies", 
                timeout=5
            )
            return response.status_code == 200
        except:
            return False
    
    async def send_alert_if_needed(self, api_name: str):
        """Отправляет уведомление гаранту если API упал"""
        now = time.time()
        last_alert = self.last_alert_time.get(api_name, 0)
        
        if now - last_alert > self.alert_cooldown:
            try:
                await self.bot.send_message(
                    OWNER_ID,
                    f"🚨 <b>ВНИМАНИЕ ГАРАНТ!</b>\n\n"
                    f"🔴 API <b>{api_name}</b> недоступен!\n"
                    f"📉 Курсы могут быть неактуальными\n"
                    f"⏰ Время: {time.strftime('%H:%M:%S')}\n\n"
                    f"<i>Бот перешел на запасные курсы</i>"
                )
                self.last_alert_time[api_name] = now
                logger.warning(f"Отправлено уведомление о падении {api_name}")
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление: {e}")
    
    async def get_api_health_report(self) -> str:
        """Отчет о состоянии API"""
        await self.check_all_apis()
        working = sum(1 for status in self.api_status.values() if status)
        total = len(self.providers)
        
        report = f"📊 <b>Статус API провайдеров:</b>\n\n"
        
        # Сначала показываем работающие API
        for name, status in self.api_status.items():
            if status:
                icon = "🟢"
                report += f"{icon} {name}: РАБОТАЕТ\n"
        
        # Затем неработающие
        for name, status in self.api_status.items():
            if not status:
                icon = "🔴"
                report += f"{icon} {name}: НЕДОСТУПЕН\n"
        
        report += f"\n📈 Работают: {working}/{total}"
        
        # Добавляем рекомендации
        if working == total:
            report += "\n\n✅ Все системы работают нормально"
        elif working >= 3:
            report += "\n\n⚠️ Некоторые API недоступны, но есть резерв"
        else:
            report += "\n\n🚨 Критическое количество API недоступно!"
        
        return report

# Глобальный экземпляр монитора
api_monitor = APIMonitor()