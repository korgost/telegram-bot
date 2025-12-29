# exchange_rates_new.py
import aiohttp
import asyncio
import time
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ExchangeRateAPI:
    def __init__(self):
        self.cache: Dict[str, tuple[float, float]] = {}
        self.cache_timeout = 30
        self.fallback_rates = self._load_fallback_rates()
        self.timeout = aiohttp.ClientTimeout(total=10)
        self.session: Optional[aiohttp.ClientSession] = None

    async def ensure_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession(timeout=self.timeout)

    def _load_fallback_rates(self) -> Dict:
        return {
            "USDT": {
                "RUB": 91.1, "BYN": 3.27, "USD": 1.0, "EUR": 0.92,
                "UAH": 42.0, "KZT": 460.0, "PLN": 4.15
            },
            "BTC": {
                "USDT": 91500, "RUB": 8330000, "BYN": 299000, "USD": 91500
            },
            "ETH": {
                "USDT": 3034, "RUB": 276000, "BYN": 9900, "USD": 3034
            },
            "BYN": {
                "RUB": 29.22, "USDT": 0.305, "USD": 0.305, "EUR": 0.28,
                "UAH": 12.1, "KZT": 140.5, "PLN": 0.79,
                "BTC": 0.0000109, "ETH": 0.000329
            },
            "RUB": {
                "BYN": 0.0342, "USDT": 0.01098, "USD": 0.01098, "EUR": 0.0101,
                "UAH": 0.46, "KZT": 5.05, "PLN": 0.045,
                "BTC": 0.00000012, "ETH": 0.0000036
            }
        }

    async def get_binance_rate_async(self, from_currency: str, to_currency: str) -> Optional[float]:
        try:
            await self.ensure_session()

            binance_pairs = {
                "USDT": {
                    "RUB": "USDTRUB", "BYN": "USDTBYN", "USD": "USDTUSDT",
                    "EUR": "EURUSDT", "UAH": "USDTUAH", "KZT": "USDTKZT"
                },
                "BTC": {"USDT": "BTCUSDT", "RUB": "BTCRUB"},
                "ETH": {"USDT": "ETHUSDT", "RUB": "ETHRUB"},
            }

            symbol = binance_pairs.get(from_currency, {}).get(to_currency)
            if not symbol:
                return None

            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    rate = float(data['price'])
                    logger.info(f"✅ Binance: {from_currency}->{to_currency} = {rate}")
                    return rate
            return None
        except Exception as e:
            logger.debug(f"Binance API error for {from_currency}/{to_currency}: {e}")
            return None

    async def get_coingecko_rate_async(self, from_currency: str, to_currency: str) -> Optional[float]:
        try:
            await self.ensure_session()

            coin_mapping = {
                "USDT": "tether", "BTC": "bitcoin", "ETH": "ethereum",
                "LTC": "litecoin", "BNB": "binancecoin", "BUSD": "binance-usd"
            }

            currency_mapping = {
                "RUB": "rub", "BYN": "byn", "USD": "usd", "EUR": "eur",
                "UAH": "uah", "KZT": "kzt", "PLN": "pln"
            }

            if from_currency in coin_mapping and to_currency in currency_mapping:
                coin_id = coin_mapping[from_currency]
                vs_currency = currency_mapping[to_currency]

                url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies={vs_currency}"
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if coin_id in data and vs_currency in data[coin_id]:
                            rate = float(data[coin_id][vs_currency])
                            logger.info(f"✅ CoinGecko: {from_currency}->{to_currency} = {rate}")
                            return rate
            return None
        except Exception as e:
            logger.debug(f"CoinGecko API error: {e}")
            return None

    async def get_cbr_rate_async(self, from_currency: str, to_currency: str) -> Optional[float]:
        try:
            await self.ensure_session()

            if from_currency == "USD" and to_currency == "RUB":
                url = "https://www.cbr-xml-daily.ru/daily_json.js"
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        usd_rub = data['Valute']['USD']['Value']
                        logger.info(f"✅ ЦБ РФ: USD/RUB = {usd_rub}")
                        return float(usd_rub)

            elif from_currency == "RUB" and to_currency == "USD":
                url = "https://www.cbr-xml-daily.ru/daily_json.js"
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        usd_rub = data['Valute']['USD']['Value']
                        rate = 1.0 / float(usd_rub)
                        logger.info(f"✅ ЦБ РФ: RUB/USD = {rate}")
                        return rate

            return None
        except Exception as e:
            logger.debug(f"CBR API error: {e}")
            return None

    async def get_nbrb_rate_async(self, from_currency: str, to_currency: str) -> Optional[float]:
        try:
            await self.ensure_session()

            if from_currency == "USD" and to_currency == "BYN":
                url = "https://www.nbrb.by/api/exrates/rates/USD?parammode=2"
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        usd_byn = data['Cur_OfficialRate'] / data['Cur_Scale']
                        logger.info(f"✅ НБ РБ: USD/BYN = {usd_byn}")
                        return float(usd_byn)

            elif from_currency == "BYN" and to_currency == "USD":
                url = "https://www.nbrb.by/api/exrates/rates/USD?parammode=2"
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        usd_byn = data['Cur_OfficialRate'] / data['Cur_Scale']
                        rate = 1.0 / float(usd_byn)
                        logger.info(f"✅ НБ РБ: BYN/USD = {rate}")
                        return rate

            return None
        except Exception as e:
            logger.debug(f"NBRB API error: {e}")
            return None

    async def get_exchangerate_host_rate_async(self, from_currency: str, to_currency: str) -> Optional[float]:
        try:
            await self.ensure_session()

            supported_currencies = ["USD", "EUR", "GBP", "JPY", "CAD", "CHF", "AUD",
                                    "RUB", "UAH", "KZT", "PLN", "BYN"]
            if from_currency in supported_currencies and to_currency in supported_currencies:
                url = f"https://api.exchangerate.host/latest?base={from_currency}&symbols={to_currency}"
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        rates = data.get("rates", {})
                        if to_currency in rates:
                            rate = float(rates[to_currency])
                            logger.info(f"✅ ExchangeRate.host: {from_currency}->{to_currency} = {rate}")
                            return rate
            return None
        except Exception as e:
            logger.debug(f"ExchangeRate.host API error: {e}")
            return None

    async def get_cross_rate_via_usdt(self, from_currency: str, to_currency: str) -> Optional[float]:
        try:
            rate_from = None
            rate_to = None

            # from_currency -> USDT
            if from_currency in ["USDT", "USD"]:
                rate_from = 1.0
            elif from_currency == "BYN":
                usd_byn = await self.get_nbrb_rate_async("USD", "BYN")
                if usd_byn and usd_byn > 0:
                    rate_from = 1.0 / usd_byn
                    logger.info(f"✅ BYN/USDT через НБ РБ (from): {rate_from}")
            elif from_currency in ["RUB", "EUR", "UAH", "KZT", "PLN"]:
                usd_rate = await self.get_exchangerate_host_rate_async(from_currency, "USD")
                if usd_rate:
                    rate_from = usd_rate
                    logger.info(f"✅ {from_currency}/USD через exchangerate.host (from): {rate_from}")
            else:
                rate_from = await self.get_binance_rate_async(from_currency, "USDT")
                if not rate_from:
                    rate_from = await self.get_coingecko_rate_async(from_currency, "USDT")

            # to_currency -> USDT
            if to_currency in ["USDT", "USD"]:
                rate_to = 1.0
            elif to_currency == "BYN":
                usd_byn = await self.get_nbrb_rate_async("USD", "BYN")
                if usd_byn and usd_byn > 0:
                    rate_to = 1.0 / usd_byn
                    logger.info(f"✅ BYN/USDT через НБ РБ (to): {rate_to}")
            elif to_currency in ["RUB", "EUR", "UAH", "KZT", "PLN"]:
                usd_rate = await self.get_exchangerate_host_rate_async(to_currency, "USD")
                if usd_rate:
                    rate_to = usd_rate
                    logger.info(f"✅ {to_currency}/USD через exchangerate.host (to): {rate_to}")
            else:
                rate_to = await self.get_binance_rate_async(to_currency, "USDT")
                if not rate_to:
                    rate_to = await self.get_coingecko_rate_async(to_currency, "USDT")

            if rate_from and rate_to and rate_to > 0:
                cross_rate = rate_from / rate_to
                logger.info(f"✅ Кросс-курс через USDT: {from_currency}->{to_currency} = {cross_rate}")
                return cross_rate

            return None
        except Exception as e:
            logger.debug(f"Cross-rate error {from_currency}->{to_currency}: {e}")
            return None

    async def get_exchange_rate_async(self, from_currency: str, to_currency: str) -> tuple[float, str]:
        """Основной метод получения курса. Возвращает (курс, источник)."""
        if from_currency == to_currency:
            return 1.0, "same_currency"

        cache_key = f"{from_currency}_{to_currency}"

        # Кэш на 10 секунд
        if cache_key in self.cache:
            rate, timestamp = self.cache[cache_key]
            if time.time() - timestamp < 10:
                logger.info(f"✅ Курс из кэша: {from_currency}->{to_currency} = {rate}")
                return rate, "cache"

        logger.info(f"🔍 Запрашиваю реальный курс: {from_currency}->{to_currency}")

        rate: Optional[float] = None
        api_used = "none"

        try:
            crypto_currencies = {"BTC", "ETH", "USDT", "LTC", "BNB", "BUSD"}
            fiat_currencies = {"RUB", "BYN", "USD", "EUR", "UAH", "KZT", "PLN"}

            from_crypto = from_currency in crypto_currencies
            to_crypto = to_currency in crypto_currencies

            # 1. Спец.случай BYN<->USDT через НБ РБ
            if (from_currency, to_currency) in {("BYN", "USDT"), ("USDT", "BYN")}:
                usd_byn = await self.get_nbrb_rate_async("USD", "BYN")
                if usd_byn and usd_byn > 0:
                    if from_currency == "USDT":
                        rate = usd_byn
                        api_used = "nbrb_usd_byn"
                    else:  # BYN -> USDT
                        rate = 1.0 / usd_byn
                        api_used = "nbrb_usd_byn_inverse"

            # 2. Крипта/крипта или крипта/фиат (прямые пары)
            if rate is None and (from_crypto or to_crypto):
                r = await self.get_binance_rate_async(from_currency, to_currency)
                if r:
                    rate = r
                    api_used = "binance"

            # 3. Фиат/фиат
            if rate is None and (not from_crypto and not to_crypto):
                r = await self.get_exchangerate_host_rate_async(from_currency, to_currency)
                if r:
                    rate = r
                    api_used = "exchangerate_host"

                # USD/RUB ≈ USDT/RUB
                if rate is None and from_currency == "USD" and to_currency == "RUB":
                    usdt_rub = await self.get_binance_rate_async("USDT", "RUB")
                    if usdt_rub:
                        rate = usdt_rub
                        api_used = "usd_rub_via_usdt"

                if rate is None and from_currency == "RUB" and to_currency == "USD":
                    usdt_rub = await self.get_binance_rate_async("USDT", "RUB")
                    if usdt_rub and usdt_rub > 0:
                        rate = 1.0 / usdt_rub
                        api_used = "rub_usd_via_usdt"

                # BYN<->RUB через USDT
                if rate is None and from_currency == "BYN" and to_currency == "RUB":
                    usdt_byn = await self.get_nbrb_rate_async("USD", "BYN")
                    usdt_rub = await self.get_binance_rate_async("USDT", "RUB")
                    if usdt_byn and usdt_rub and usdt_byn > 0:
                        rate = usdt_rub / usdt_byn
                        api_used = "byn_rub_via_usdt"

                if rate is None and from_currency == "RUB" and to_currency == "BYN":
                    usdt_byn = await self.get_nbrb_rate_async("USD", "BYN")
                    usdt_rub = await self.get_binance_rate_async("USDT", "RUB")
                    if usdt_byn and usdt_rub and usdt_rub > 0:
                        rate = usdt_byn / usdt_rub
                        api_used = "rub_byn_via_usdt"

                # EUR/RUB через Binance
                if rate is None and from_currency == "EUR" and to_currency == "RUB":
                    eur_usdt = await self.get_binance_rate_async("USDT", "EUR")
                    usdt_rub = await self.get_binance_rate_async("USDT", "RUB")
                    if eur_usdt and usdt_rub:
                        rate = eur_usdt * usdt_rub
                        api_used = "eur_rub_via_binance"

                if rate is None and from_currency == "RUB" and to_currency == "EUR":
                    eur_usdt = await self.get_binance_rate_async("USDT", "EUR")
                    usdt_rub = await self.get_binance_rate_async("USDT", "RUB")
                    if eur_usdt and usdt_rub and eur_usdt * usdt_rub > 0:
                        eur_rub = eur_usdt * usdt_rub
                        rate = 1.0 / eur_rub
                        api_used = "rub_eur_via_binance"

                # Если ещё не нашли и затронут BYN — пробуем НБРБ
                if rate is None and (from_currency == "BYN" or to_currency == "BYN"):
                    r = await self.get_nbrb_rate_async(from_currency, to_currency)
                    if r:
                        rate = r
                        api_used = "nbrb_direct"

            # 4. Кросс-курсы через USDT (для BYN->BTC и т.п.)
            if rate is None:
                r = await self.get_cross_rate_via_usdt(from_currency, to_currency)
                if r:
                    rate = r
                    api_used = "cross_usdt"

            # 5. CoinGecko как крайний вариант для крипта->фиат
            if rate is None and from_crypto and not to_crypto:
                r = await self.get_coingecko_rate_async(from_currency, to_currency)
                if r:
                    rate = r
                    api_used = "coingecko"

            # 6. СПЕЦИАЛЬНАЯ ОБРАБОТКА ДЛЯ BYN→BTC и BYN→ETH
            if from_currency == "BYN" and to_currency in ["BTC", "ETH"]:
                logger.info(f"🎯 Специальная обработка для {from_currency}→{to_currency}")
                r = await self.get_byn_to_crypto_cross_rate(from_currency, to_currency)
                if r and r > 0:
                    rate = r
                    api_used = "byn_crypto_cross"
                    logger.info(f"✅ Использован кросс-курс: {from_currency}→{to_currency} = {rate:.10f}")

            # 7. Крипта/крипта или крипта/фиат (прямые пары)
            if rate is None and (from_crypto or to_crypto):
                r = await self.get_binance_rate_async(from_currency, to_currency)
                if r:
                    rate = r
                    api_used = "binance"

        except Exception as e:
            logger.error(f"❌ Ошибка получения курса {from_currency}->{to_currency}: {e}")

        # 8. Запасной курс
        if not rate or rate <= 0:
            rate = self.fallback_rates.get(from_currency, {}).get(to_currency, 1.0)
            api_used = "fallback"
            logger.warning(f"⚠️ Используем запасной курс: {from_currency}->{to_currency} = {rate}")
        else:
            logger.info(f"✅ Получен реальный курс от {api_used}: {from_currency}->{to_currency} = {rate}")

        # Кэшируем
        self.cache[cache_key] = (rate, time.time())
        return rate, api_used

    async def close_session(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def get_byn_to_crypto_cross_rate(self, from_currency: str, to_currency: str) -> Optional[float]:
        try:
            logger.info(f"🔍 Рассчитываю кросс-курс: {from_currency}→{to_currency}")
            
            # 1. Получаем BYN→USDT (через НБ РБ)
            usd_byn = await self.get_nbrb_rate_async("USD", "BYN")
            if not usd_byn or usd_byn <= 0:
                usd_byn = 3.27
            
            byn_usdt = 1.0 / usd_byn
            logger.info(f"📊 1 BYN = {byn_usdt:.6f} USDT")
            
            # 2. Получаем BTC/USDT или ETH/USDT из Binance
            if to_currency == "BTC":
                btc_usdt = await self.get_binance_rate_async("BTC", "USDT")
                if not btc_usdt or btc_usdt <= 0:
                    btc_usdt = 91500.0
                
                if btc_usdt > 0:
                    rate = byn_usdt / btc_usdt
                    logger.info(f"✅ Рассчитан курс BYN/BTC: {rate:.10f}")
                    return rate
            
            elif to_currency == "ETH":
                eth_usdt = await self.get_binance_rate_async("ETH", "USDT")
                if not eth_usdt or eth_usdt <= 0:
                    eth_usdt = 3034.0
                
                if eth_usdt > 0:
                    rate = byn_usdt / eth_usdt
                    logger.info(f"✅ Рассчитан курс BYN/ETH: {rate:.10f}")
                    return rate
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета кросс-курса: {e}")
            return None


# Глобальный экземпляр
exchange_api = ExchangeRateAPI()