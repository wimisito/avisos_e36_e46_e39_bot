#!/usr/bin/env python3
"""
Avisos de Wallapop por Telegram para BMW E36 / E46 / E39.

Uso:
  pip install requests
  export TELEGRAM_TOKEN="123456:ABC..."
  export TELEGRAM_CHAT_ID="123456789"
  python wallapop_bmw_alertas.py

Opcional:
  export WALLAPOP_LAT="..."  WALLAPOP_LON="..."   (para priorizar tu zona)
  export MAX_PRICE="6000"                         (precio máximo en euros)

La primera vez guarda los anuncios que ya existen SIN avisarte,
y a partir de ahí solo te avisa de los nuevos.
"""
import json
import os
import random
import time
from pathlib import Path

import requests

# ---------- CONFIGURACIÓN ----------
# (texto a buscar, texto que debe aparecer en el título o descripción)
SEARCHES = [
    ("bmw e36", "e36"),
    ("bmw e39", "e39"),
    ("bmw e46", "e46"),
]
INTERVAL_SECONDS = 420  # ~7 min. No lo bajes mucho para que no te bloqueen.
SEEN_FILE = Path(__file__).with_name("seen.json")
API_URL = "https://api.wallapop.com/api/v3/general/search"

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
LAT = os.environ.get("WALLAPOP_LAT")
LON = os.environ.get("WALLAPOP_LON")
MAX_PRICE = os.environ.get("MAX_PRICE")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "X-DeviceOS": "0",
    "Accept": "application/json",
}


def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return None  # None = primera ejecución


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(sorted(seen)))


def extract_items(data):
    """Wallapop ha cambiado el formato varias veces: probamos los conocidos."""
    try:
        return data["data"]["section"]["payload"]["items"]
    except (KeyError, TypeError):
        pass
    try:
        return data["search_objects"]
    except (KeyError, TypeError):
        pass
    return []


def search(keywords):
    params = {
        "keywords": keywords,
        "order_by": "newest",
        "source": "search_box",
    }
    if LAT and LON:
        params["latitude"] = LAT
        params["longitude"] = LON
    if MAX_PRICE:
        params["max_sale_price"] = MAX_PRICE
    r = requests.get(API_URL, params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return extract_items(r.json())


def price_text(item):
    p = item.get("price")
    if isinstance(p, dict):
        return f"{p.get('amount', '?')} {p.get('currency', '€')}"
    if p is not None:
        return f"{p} €"
    return "sin precio"


def send_telegram(text):
    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text},
        timeout=20,
    )
    r.raise_for_status()


def check_once(seen):
    first_run = seen is None
    seen = set() if first_run else seen
    new_count = 0

    for keywords, must_contain in SEARCHES:
        try:
            items = search(keywords)
        except Exception as e:
            print(f"[aviso] fallo buscando '{keywords}': {e}")
            continue

        for item in items:
            item_id = str(item.get("id"))
            if item_id in seen:
                continue
            seen.add(item_id)

            text = f"{item.get('title', '')} {item.get('description', '')}".lower()
            if must_contain not in text:
                continue  # ruido: no es del modelo que buscas
            if first_run:
                continue

            slug = item.get("web_slug") or item_id
            msg = (
                f"🚗 {item.get('title', 'Sin título')}\n"
                f"💶 {price_text(item)}\n"
                f"https://es.wallapop.com/item/{slug}"
            )
            try:
                send_telegram(msg)
                new_count += 1
            except Exception as e:
                print(f"[aviso] fallo enviando a Telegram: {e}")

        time.sleep(random.uniform(2, 5))  # pausa entre búsquedas

    save_seen(seen)
    if first_run:
        print(f"Primera ejecución: guardados {len(seen)} anuncios existentes.")
    else:
        print(f"Revisión hecha. Anuncios nuevos avisados: {new_count}")
    return seen


def main():
    if not TOKEN or not CHAT_ID:
        raise SystemExit("Faltan TELEGRAM_TOKEN y/o TELEGRAM_CHAT_ID.")
    seen = load_seen()
    if os.environ.get("RUN_ONCE"):  # modo nube: una revisión y salir
        check_once(seen)
        return
    while True:
        seen = check_once(seen)
        time.sleep(INTERVAL_SECONDS + random.uniform(0, 60))


if __name__ == "__main__":
    main()
