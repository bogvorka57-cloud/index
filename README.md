# MEXC Signal Bot

Читает сигналы из Telegram-канала и автоматически торгует фьючерсами на MEXC.

## Что делает бот

1. Слушает указанный TG-канал
2. Парсит сигналы формата `#SYMBOL/USDT SHORT/LONG`
3. Открывает рыночный ордер на MEXC Futures
4. Выставляет TP (первый уровень) и SL
5. Логирует всё в `logs/signals.log`
6. Отправляет уведомление в ваш чат

---

## Установка

```bash
pip install -r requirements.txt
```

---

## Настройка config.py

### 1. Telegram API
Зайди на https://my.telegram.org → «API development tools»  
Создай приложение, получи `api_id` и `api_hash`

```python
TG_API_ID   = "12345678"
TG_API_HASH = "abcdef1234567890abcdef1234567890"
TG_PHONE    = "+79001234567"       # номер аккаунта который читает канал
TG_CHANNEL  = "имя_канала"        # без @ (например: mysignals)
```

### 2. Уведомления
Создай бота через @BotFather, получи токен.  
Свой chat_id узнай через @userinfobot

```python
NOTIFY_BOT_TOKEN = "1234567890:ABCdef..."
NOTIFY_CHAT_ID   = "123456789"
```

### 3. MEXC API
Зайди на MEXC → Профиль → API Management  
Создай ключ с правами на **Futures Trading** (требуется KYC)

```python
MEXC_API_KEY    = "mx0v..."
MEXC_API_SECRET = "..."
```

### 4. Параметры торговли
```python
TRADE_SIZE_USDT = 15    # сумма позиции в USDT
LEVERAGE        = 20    # плечо
TP_LEVEL        = 1     # брать TP1
```

---

## Запуск

```bash
python bot.py
```

При первом запуске Telethon попросит ввести код из Telegram — это нормально.  
После авторизации создастся файл `session_bot.session` — храни его в безопасности.

---

## Формат сигналов (поддерживаемый)

```
#CHIP/USDT 📉 SHORT

Диапазон входа: 0.04030-0.03970$
TP: 0.03883$ - 0.03672$
SL: 0.04396$

Риск: 1%

...текст аналитики...
```

Поддерживаются `SHORT` и `LONG`, один или два TP.

---

## Структура проекта

```
mexc-signal-bot/
├── bot.py          # главный файл, TG listener
├── parser.py       # парсинг сигналов
├── mexc_api.py     # MEXC Futures API
├── logger.py       # логирование
├── config.py       # все настройки
├── requirements.txt
└── logs/
    └── signals.log
```

---

## Важно

- **Тестируй на маленьких суммах** — MEXC API работает только с реальным счётом (sandbox нет)
- Первый вход потребует Telegram-авторизации (введи код из SMS/приложения)
- Бот не управляет открытыми позициями после выставления TP/SL — всё на бирже
