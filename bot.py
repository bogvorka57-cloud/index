import asyncio
import logging
import requests
from telethon import TelegramClient, events

import config
from parser import parse_signal, Signal
from mexc_api import (
    set_leverage, place_market_order, calc_contracts,
    get_open_positions, get_account_assets, get_current_price,
    get_closed_positions
)
from logger import log_signal, log_error, log_info

client = TelegramClient("session_bot", config.TG_API_ID, config.TG_API_HASH)

# Глушим спам от Telethon про незнакомые entity (апдейты от юзеров не в кэше)
logging.getLogger("telethon.client.updates").setLevel(logging.CRITICAL)


# ──────────────────────────────────────────────
#  Уведомления
# ──────────────────────────────────────────────

def send_notify(text: str):
    if not config.NOTIFY_BOT_TOKEN or not config.NOTIFY_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{config.NOTIFY_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": config.NOTIFY_CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }, timeout=5)
    except Exception as e:
        log_error(f"Уведомление не отправлено: {e}")


# ──────────────────────────────────────────────
#  Исполнение сигнала
# ──────────────────────────────────────────────

async def execute_signal(signal: Signal):
    sym = signal.symbol
    log_info(
        f"▶ Новый сигнал: {sym} {signal.direction} "
        f"диапазон=[{signal.entry_low}–{signal.entry_high}] TP={signal.tp1}"
    )

    try:
        # 0. Проверяем цену относительно диапазона входа
        current_price = get_current_price(sym)
        in_range = signal.entry_low <= current_price <= signal.entry_high

        if signal.direction == "LONG":
            # LONG: заходим если цена НИЖЕ или ВНУТРИ диапазона (дешевле = лучше)
            # Пропускаем только если цена УЖЕ ВЫШЕ диапазона
            price_ok = current_price <= signal.entry_high
            skip_reason = f"цена {current_price} уже ВЫШЕ диапазона [{signal.entry_low}–{signal.entry_high}]"
        else:
            # SHORT: заходим если цена ВЫШЕ или ВНУТРИ диапазона (дороже = лучше)
            # Пропускаем только если цена УЖЕ НИЖЕ диапазона
            price_ok = current_price >= signal.entry_low
            skip_reason = f"цена {current_price} уже НИЖЕ диапазона [{signal.entry_low}–{signal.entry_high}]"

        range_str = "✅ В диапазоне" if in_range else ("✅ Лучше диапазона" if price_ok else "⛔ Пропускаем")
        log_info(
            f"Текущая цена {sym}: {current_price} | "
            f"Диапазон: [{signal.entry_low}–{signal.entry_high}] | {range_str}"
        )

        if not price_ok:
            send_notify(
                f"⛔ <b>Сигнал пропущен</b>\n"
                f"<b>{sym}</b> {signal.direction}\n"
                f"{skip_reason}"
            )
            return

        # 1. Плечо
        set_leverage(sym, config.LEVERAGE)
        log_info(f"Плечо {config.LEVERAGE}x установлено для {sym}")

        # 2. Объём
        vol = calc_contracts(sym, config.TRADE_SIZE_USDT, config.LEVERAGE)
        log_info(f"Объём: {vol} контрактов (${config.TRADE_SIZE_USDT} × {config.LEVERAGE}x)")

        # 3. Открыть ордер (только TP, без SL)
        side = 3 if signal.direction == "SHORT" else 1
        order_result = place_market_order(
            sym, side, vol,
            tp_price=signal.tp1,
        )

        if not order_result.get("success"):
            raise RuntimeError(f"Ошибка ордера: {order_result}")

        order_id     = order_result["data"]["orderId"]
        entry_price  = order_result["entry_price"]
        tp_accepted  = order_result["tp_accepted"]
        log_info(f"✅ Позиция открыта. Order ID: {order_id}, вход={entry_price}, TP={'✅' if tp_accepted else '⚠️ не установлен'}")

        tp_line = (f"TP: <code>{signal.tp1}</code>" if tp_accepted
                   else f"⚠️ TP не установлен (TP={signal.tp1} некорректен для {signal.direction} при цене {entry_price})")

        # 4. Регистрируем позицию для мониторинга закрытия
        track_position(sym, entry_price, signal.direction, signal.tp1 if tp_accepted else None)

        # 5. Лог и уведомление
        log_signal(signal, order_result, {})
        send_notify(
            f"✅ <b>Сделка открыта</b>\n"
            f"<b>{sym}</b> {signal.direction}\n"
            f"Вход: <code>{entry_price}</code>\n"
            f"{tp_line}\n"
            f"Объём: {vol} контр. (${config.TRADE_SIZE_USDT} × {config.LEVERAGE}x)\n"
            f"Order ID: <code>{order_id}</code>"
        )

    except Exception as e:
        err = f"❌ Ошибка исполнения {sym}: {e}"
        log_error(err)
        send_notify(err)


# ──────────────────────────────────────────────
#  Команды мониторинга (через личку нотифай-бота)
# ──────────────────────────────────────────────

async def cmd_positions():
    """Показать открытые позиции."""
    try:
        positions = get_open_positions()
        if not positions:
            send_notify("📭 Открытых позиций нет")
            return

        lines = ["📊 <b>Открытые позиции:</b>\n"]
        total_pnl = 0.0
        for p in positions:
            sym        = p.get("symbol", "?")
            side_raw   = p.get("positionType", 0)
            side_str   = "LONG" if side_raw == 1 else "SHORT"
            vol        = p.get("holdVol", "?")
            entry      = p.get("openAvgPrice", "?")
            cur_price  = p.get("closeAvgPrice") or p.get("markPrice", "?")
            pnl        = float(p.get("unrealisedPNL", 0))
            margin     = float(p.get("im", 0))
            roe        = (pnl / margin * 100) if margin else 0
            total_pnl += pnl

            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(
                f"{pnl_emoji} <b>{sym}</b> {side_str}\n"
                f"  Объём: {vol} | Вход: <code>{entry}</code>\n"
                f"  Текущая: <code>{cur_price}</code>\n"
                f"  PnL: <code>{pnl:+.4f} USDT</code> ({roe:+.2f}%)\n"
            )

        total_emoji = "🟢" if total_pnl >= 0 else "🔴"
        lines.append(f"\n{total_emoji} <b>Итого PnL: {total_pnl:+.4f} USDT</b>")
        send_notify("\n".join(lines))
        log_info(f"[CMD] /positions — {len(positions)} позиций, total PnL={total_pnl:+.4f}")

    except Exception as e:
        err = f"❌ Ошибка /positions: {e}"
        log_error(err)
        send_notify(err)


async def cmd_pnl():
    """Показать баланс и PnL аккаунта."""
    try:
        asset = get_account_assets()
        if not asset:
            send_notify("⚠️ Не удалось получить данные аккаунта")
            return

        equity      = float(asset.get("equity", 0))
        balance     = float(asset.get("availableBalance", asset.get("balance", 0)))
        unrealised  = float(asset.get("unrealisedPNL", 0))
        realised    = float(asset.get("realisedPNL", asset.get("todayProfit", 0)))

        unr_emoji = "🟢" if unrealised >= 0 else "🔴"
        rea_emoji = "🟢" if realised >= 0 else "🔴"

        send_notify(
            f"💼 <b>Аккаунт MEXC Futures</b>\n\n"
            f"Баланс:       <code>{balance:.4f} USDT</code>\n"
            f"Эквити:       <code>{equity:.4f} USDT</code>\n"
            f"{unr_emoji} Нереализ. PnL: <code>{unrealised:+.4f} USDT</code>\n"
            f"{rea_emoji} Реализ. PnL:   <code>{realised:+.4f} USDT</code>"
        )
        log_info(f"[CMD] /pnl — equity={equity:.4f}, unrealised={unrealised:+.4f}, realised={realised:+.4f}")

    except Exception as e:
        err = f"❌ Ошибка /pnl: {e}"
        log_error(err)
        send_notify(err)


# ──────────────────────────────────────────────
#  Монитор закрытия позиций
# ──────────────────────────────────────────────

# Храним символы открытых нами позиций: { "ETHFI_USDT": {"entry": 0.71, "direction": "SHORT", "tp": 0.61} }
_tracked: dict = {}

def track_position(sym: str, entry: float, direction: str, tp: float | None):
    """Регистрируем позицию для мониторинга."""
    _tracked[sym] = {"entry": entry, "direction": direction, "tp": tp}


async def position_monitor():
    """
    Каждые 30 сек проверяет открытые позиции.
    Если отслеживаемая позиция пропала — значит закрылась (TP/ликвидация/ручное закрытие).
    Берём реализованный PnL из истории и шлём уведомление.
    """
    POLL_INTERVAL = 30
    log_info("[Monitor] Монитор позиций запущен")

    while True:
        await asyncio.sleep(POLL_INTERVAL)
        if not _tracked:
            continue
        try:
            open_syms = {p["symbol"] for p in get_open_positions()}
            closed = [sym for sym in list(_tracked) if sym not in open_syms]

            for sym in closed:
                info = _tracked.pop(sym)
                log_info(f"[Monitor] Позиция {sym} закрылась — ищем в истории")

                # Пытаемся найти в истории и взять PnL
                pnl_str = ""
                try:
                    history = get_closed_positions(page_size=20)
                    for h in history:
                        if h.get("symbol") == sym:
                            pnl   = float(h.get("realised", h.get("realisedPNL", 0)))
                            close_price = h.get("closeAvgPrice", "?")
                            roe   = h.get("roe", "")
                            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
                            pnl_str = (
                                f"{pnl_emoji} PnL: <code>{pnl:+.4f} USDT</code>"
                                + (f" ({float(roe)*100:+.2f}%)" if roe else "")
                                + f"\nЗакрыто по: <code>{close_price}</code>"
                            )
                            log_info(f"[Monitor] {sym} PnL={pnl:+.4f}, close={close_price}")
                            break
                except Exception as e:
                    log_error(f"[Monitor] Не удалось получить историю для {sym}: {e}")

                send_notify(
                    f"🏁 <b>Позиция закрыта</b>\n"
                    f"<b>{sym}</b> {info['direction']}\n"
                    f"Вход: <code>{info['entry']}</code>\n"
                    f"TP был: <code>{info['tp'] or '—'}</code>\n"
                    + (pnl_str if pnl_str else "ℹ️ PnL не найден в истории")
                )

        except Exception as e:
            log_error(f"[Monitor] Ошибка: {e}")




# Все каналы сигналов — можно мешать username и int ID
SIGNAL_CHANNELS = [config.TG_CHANNEL, -1002088626562]


@client.on(events.NewMessage(chats=SIGNAL_CHANNELS))
async def on_new_message(event):
    text = event.message.text or ""
    if "SHORT" not in text.upper() and "LONG" not in text.upper():
        return
    if "Диапазон входа" not in text:
        return
    # Определяем из какого канала пришло
    chat = await event.get_chat()
    chat_id   = event.chat_id
    chat_name = getattr(chat, "title", None) or getattr(chat, "username", None) or str(chat_id)
    log_info(f"[Signal] Сообщение из канала: {chat_name} (id={chat_id})")

    signal = parse_signal(text)
    if signal is None:
        log_error(f"Не удалось распарсить:\n{text[:200]}")
        return
    asyncio.create_task(execute_signal(signal))


@client.on(events.NewMessage(pattern=r'^/(positions|pnl)(\s|$)'))
async def on_command(event):
    """
    Пиши /positions или /pnl в Избранное (Saved Messages) — бот ответит уведомлением.
    """
    # Принимаем только от себя
    me = await client.get_me()
    if event.sender_id != me.id:
        return

    text = (event.message.text or "").strip().lower().split()[0]
    if text == "/positions":
        log_info("[CMD] Получена команда /positions")
        asyncio.create_task(cmd_positions())
    elif text == "/pnl":
        log_info("[CMD] Получена команда /pnl")
        asyncio.create_task(cmd_pnl())


# ──────────────────────────────────────────────
#  Запуск
# ──────────────────────────────────────────────

async def main():
    log_info("Бот запущен. Ожидаем сигналы...")
    await client.start(phone=config.TG_PHONE)
    log_info("Подключён к Telegram.")

    # Резолвим названия каналов
    log_info(f"Слушаем каналы ({len(SIGNAL_CHANNELS)}):")
    for ch in SIGNAL_CHANNELS:
        try:
            entity = await client.get_entity(ch)
            name   = getattr(entity, "title", None) or getattr(entity, "username", None) or str(ch)
            cid    = getattr(entity, "id", ch)
            log_info(f"  • {name}  (id={cid})")
        except Exception as e:
            log_info(f"  • {ch}  (не удалось получить название: {e})")

    log_info("Команды в чате уведомлений: /positions, /pnl")
    asyncio.create_task(position_monitor())
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
