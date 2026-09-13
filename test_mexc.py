"""
Тестовый скрипт - проверяем подпись MEXC Futures API
Запусти: python test_mexc.py
"""
import hmac
import hashlib
import time
import json
import requests

# Вставь свои ключи прямо сюда для теста
API_KEY    = "mx0vgl3hp6JSGArs2W"
API_SECRET = "583d6864eb7d4f21a8217e200578d341"
BASE_URL   = "https://api.mexc.com"

def ts():
    return int(time.time() * 1000)

# ── Вариант 1: api_key + timestamp + body ──────────────
def sign_v1(body: dict, t: int) -> str:
    body_str = json.dumps(body, separators=(',', ':'))
    msg = API_KEY + str(t) + body_str
    return hmac.new(API_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()

# ── Вариант 2: timestamp + body ───────────────────────
def sign_v2(body: dict, t: int) -> str:
    body_str = json.dumps(body, separators=(',', ':'))
    msg = str(t) + body_str
    return hmac.new(API_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()

# ── Вариант 3: sorted query string ────────────────────
def sign_v3(body: dict, t: int) -> str:
    body["timestamp"] = t
    qs = "&".join(f"{k}={v}" for k, v in sorted(body.items()))
    return hmac.new(API_SECRET.encode(), qs.encode(), hashlib.sha256).hexdigest()

# Тест - читаем позиции (простой GET с авторизацией)
def test_get_positions(sign_fn, label):
    t = ts()
    params = {"timestamp": t}
    sig = sign_fn(params.copy(), t)
    headers = {
        "Content-Type": "application/json",
        "ApiKey": API_KEY,
        "Request-Time": str(t),
        "Signature": sig,
    }
    url = f"{BASE_URL}/api/v1/private/position/open_positions"
    r = requests.get(url, params=params, headers=headers, timeout=10)
    print(f"\n[{label}] Status: {r.status_code}")
    print(f"[{label}] Response: {r.text[:300]}")

# Тест leverage (POST)
def test_leverage(sign_fn, label):
    t = ts()
    body = {
        "symbol": "PYTH_USDT",
        "leverage": 20,
        "openType": 1,
        "positionType": 1,
    }
    sig = sign_fn(body.copy(), t)
    headers = {
        "Content-Type": "application/json",
        "ApiKey": API_KEY,
        "Request-Time": str(t),
        "Signature": sig,
    }
    url = f"{BASE_URL}/api/v1/private/position/change_leverage"
    r = requests.post(url, json=body, headers=headers, timeout=10)
    print(f"\n[{label}] Status: {r.status_code}")
    print(f"[{label}] Response: {r.text[:300]}")

print("=== Тест вариантов подписи ===")
test_leverage(sign_v1, "v1: apikey+ts+body")
test_leverage(sign_v2, "v2: ts+body")
test_leverage(sign_v3, "v3: query_string")
