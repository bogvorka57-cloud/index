import hmac
import hashlib
import time
import json
import requests
from config import MEXC_API_KEY, MEXC_API_SECRET, LEVERAGE

BASE_URL = "https://api.mexc.com"


def _ts() -> int:
    return int(time.time() * 1000)


def _sign(ts: int, param_str: str) -> str:
    """MEXC Futures: HMAC-SHA256(accessKey + timestamp + requestParam)"""
    msg = MEXC_API_KEY + str(ts) + param_str
    return hmac.new(
        MEXC_API_SECRET.encode(),
        msg.encode(),
        hashlib.sha256
    ).hexdigest()


def _headers(ts: int, sig: str) -> dict:
    return {
        "Content-Type": "application/json",
        "ApiKey": MEXC_API_KEY,
        "Request-Time": str(ts),
        "Signature": sig,
    }


# ──────────────────────────────────────────────
#  Публичные методы
# ──────────────────────────────────────────────

def get_contract_detail(symbol: str) -> dict:
    r = requests.get(f"{BASE_URL}/api/v1/contract/detail",
                     params={"symbol": symbol}, timeout=10)
    r.raise_for_status()
    data = r.json().get("data", [])
    for item in (data if isinstance(data, list) else [data]):
        if item["symbol"] == symbol:
            return item
    raise ValueError(f"Контракт {symbol} не найден")


def get_current_price(symbol: str) -> float:
    r = requests.get(f"{BASE_URL}/api/v1/contract/ticker",
                     params={"symbol": symbol}, timeout=10)
    r.raise_for_status()
    data = r.json().get("data", {})
    if isinstance(data, list):
        for item in data:
            if item.get("symbol") == symbol:
                return float(item["lastPrice"])
    elif isinstance(data, dict):
        return float(data["lastPrice"])
    raise ValueError(f"Цена {symbol} не найдена")


# ──────────────────────────────────────────────
#  Приватные методы
# ──────────────────────────────────────────────

def set_leverage(symbol: str, leverage: int = LEVERAGE) -> dict:
    ts = _ts()
    body = {
        "symbol": symbol,
        "leverage": leverage,
        "openType": 1,
        "positionType": 1,
    }
    body_str = json.dumps(body, separators=(',', ':'))
    sig = _sign(ts, body_str)
    r = requests.post(
        f"{BASE_URL}/api/v1/private/position/change_leverage",
        data=body_str,
        headers=_headers(ts, sig),
        timeout=10
    )
    r.raise_for_status()
    result = r.json()
    print(f"[MEXC] set_leverage: {result}")
    return result


def place_market_order(symbol: str, side: int, vol: int,
                       tp_price: float = None) -> dict:
    """
    side: 1=открыть лонг, 2=закрыть лонг, 3=открыть шорт, 4=закрыть шорт
    TP передаётся прямо в теле ордера как float (takeProfitPrice).
    Перед отправкой проверяем что TP логически корректен:
      LONG  → TP должен быть ВЫШЕ цены входа
      SHORT → TP должен быть НИЖЕ цены входа
    Если некорректен — TP не ставим и логируем предупреждение.
    Возвращает доп. поля: entry_price, tp_accepted.
    """
    price = get_current_price(symbol)

    body = {
        "symbol": symbol,
        "price": price,
        "vol": vol,
        "side": side,
        "type": 5,       # market
        "openType": 1,   # изолированная маржа
        "leverage": LEVERAGE,
    }

    tp_accepted = False
    if tp_price:
        is_long  = (side == 1)
        tp_valid = (tp_price > price) if is_long else (tp_price < price)
        if tp_valid:
            body["takeProfitPrice"] = float(tp_price)
            tp_accepted = True
            print(f"[MEXC] TP={tp_price} {'>' if is_long else '<'} price={price} ✅")
        else:
            print(f"[MEXC] ⚠️ TP={tp_price} некорректен для {'LONG' if is_long else 'SHORT'} "
                  f"при цене {price} — TP пропущен")

    ts = _ts()
    body_str = json.dumps(body, separators=(',', ':'))
    sig = _sign(ts, body_str)
    r = requests.post(
        f"{BASE_URL}/api/v1/private/order/create",
        data=body_str,
        headers=_headers(ts, sig),
        timeout=10
    )
    r.raise_for_status()
    result = r.json()
    result["entry_price"]  = price
    result["tp_accepted"]  = tp_accepted
    print(f"[MEXC] place_market_order: {result}")
    return result


def calc_contracts(symbol: str, usdt_amount: float, leverage: int) -> int:
    detail        = get_contract_detail(symbol)
    contract_size = float(detail.get("contractSize", 1))
    price         = get_current_price(symbol)
    print(f"[MEXC] {symbol}: price={price}, contractSize={contract_size}")
    vol = (usdt_amount * leverage) / (price * contract_size)
    return max(1, int(vol))


# ──────────────────────────────────────────────
#  Статус / мониторинг
# ──────────────────────────────────────────────

def get_open_positions() -> list:
    """Возвращает список открытых позиций."""
    ts = _ts()
    sig = _sign(ts, "")
    r = requests.get(
        f"{BASE_URL}/api/v1/private/position/open_positions",
        headers=_headers(ts, sig),
        timeout=10
    )
    r.raise_for_status()
    data = r.json()
    return data.get("data", [])


def get_closed_positions(page_size: int = 10) -> list:
    """Последние закрытые позиции (история)."""
    ts = _ts()
    params = {"pageSize": page_size, "pageNum": 1}
    param_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    sig = _sign(ts, param_str)
    r = requests.get(
        f"{BASE_URL}/api/v1/private/position/list/history_positions",
        params=params,
        headers=_headers(ts, sig),
        timeout=10
    )
    r.raise_for_status()
    data = r.json()
    return data.get("data", {}).get("resultList", [])


def get_account_assets() -> dict:
    """Возвращает баланс и нереализованный PnL по аккаунту."""
    ts = _ts()
    sig = _sign(ts, "")
    r = requests.get(
        f"{BASE_URL}/api/v1/private/account/assets",
        headers=_headers(ts, sig),
        timeout=10
    )
    r.raise_for_status()
    data = r.json()
    # Ищем USDT среди активов
    assets = data.get("data", [])
    if isinstance(assets, list):
        for a in assets:
            if a.get("currency") == "USDT":
                return a
    elif isinstance(assets, dict):
        return assets
    return {}
