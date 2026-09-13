import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    symbol: str
    direction: str       # SHORT / LONG
    entry_low: float     # нижняя граница диапазона входа
    entry_high: float    # верхняя граница диапазона входа
    entry: float         # середина (для логов)
    tp1: float
    tp2: Optional[float]
    sl: float
    risk: float
    raw_text: str


def parse_signal(text: str) -> Optional[Signal]:
    try:
        # 1. Тикер
        symbol_match = re.search(r'#([A-Z0-9]+)[\*\s]*/[\*\s]*USDT', text, re.IGNORECASE)
        if not symbol_match:
            return None
        symbol = f"{symbol_match.group(1).upper()}_USDT"

        # 2. Направление
        direction_match = re.search(r'\b(LONG|SHORT)\b', text, re.IGNORECASE)
        if not direction_match:
            return None
        direction = direction_match.group(1).upper()

        # 3. Диапазон входа — берём обе границы
        entry_match = re.search(
            r'Диапазон входа[:\s]+([\d.]+)[–\-]+([\d.]+)\$', text
        )
        if not entry_match:
            return None
        a = float(entry_match.group(1))
        b = float(entry_match.group(2))
        entry_high = max(a, b)
        entry_low  = min(a, b)
        entry      = round((entry_high + entry_low) / 2, 10)

        # 4. TP
        tp_match   = re.search(r'TP[:\s]+([\d.]+)\$?\s*[–\-]+\s*([\d.]+)\$', text)
        tp_single  = re.search(r'TP[:\s]+([\d.]+)\$', text)
        if tp_match:
            tp1 = float(tp_match.group(1))
            tp2 = float(tp_match.group(2))
        elif tp_single:
            tp1 = float(tp_single.group(1))
            tp2 = None
        else:
            return None

        # 5. SL (необязателен — бот его не использует, но парсим для лога)
        sl_match = re.search(r'SL[:\s]+([\d.]+)\$', text)
        sl = float(sl_match.group(1)) if sl_match else 0.0

        # 6. Риск
        risk_match = re.search(r'Риск[:\s]+([\d.]+)%', text)
        risk = float(risk_match.group(1)) if risk_match else 1.0

        return Signal(
            symbol=symbol,
            direction=direction,
            entry_low=entry_low,
            entry_high=entry_high,
            entry=entry,
            tp1=tp1,
            tp2=tp2,
            sl=sl,
            risk=risk,
            raw_text=text.strip()
        )

    except Exception as e:
        print(f"[Parser] Ошибка парсинга: {e}")
        return None
