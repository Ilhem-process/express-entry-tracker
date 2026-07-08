#!/usr/bin/env python3
"""
Vérifie UNE FOIS s'il y a un nouveau tirage Entrée express (Express Entry)
IRCC, et envoie une notification Telegram si c'est le cas.

Conçu pour être exécuté périodiquement par GitHub Actions (cron), plutôt
qu'en boucle infinie sur un PC local.

Configuration requise (secrets GitHub Actions ou variables d'environnement) :
  - TELEGRAM_BOT_TOKEN
  - TELEGRAM_CHAT_ID
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

EE_JSON_URL = "https://www.canada.ca/content/dam/ircc/documents/json/ee_rounds_123_en.json"
STATE_FILE = "dernier_tirage.json"


def envoyer_telegram(message: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        print(f"Erreur envoi Telegram (HTTP {e.code}) : {detail}")
        sys.exit(1)
    except Exception as e:
        print(f"Erreur envoi Telegram : {e}")
        sys.exit(1)


def recuperer_dernier_tirage():
    req = urllib.request.Request(
        EE_JSON_URL, headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    rounds = data.get("rounds", [])
    return rounds[0] if rounds else None


def charger_dernier_numero_connu():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("drawNumber")
    return None


def sauvegarder_dernier_numero(numero: str) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"drawNumber": numero}, f)


def formater_message(tirage: dict) -> str:
    return (
        "🇨🇦 <b>Nouveau tirage Entrée express !</b>\n\n"
        f"Numéro du tirage : {tirage.get('drawNumber')}\n"
        f"Date : {tirage.get('drawDate')}\n"
        f"Type de tirage : {tirage.get('drawName')}\n"
        f"Score CRS minimum : {tirage.get('drawCRS')}\n"
        f"Invitations émises : {tirage.get('drawSize')}\n"
    )


def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Erreur : TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant.")
        sys.exit(1)

    dernier_connu = charger_dernier_numero_connu()
    tirage = recuperer_dernier_tirage()

    if tirage is None:
        print(f"[{datetime.now()}] Aucune donnée reçue depuis IRCC.")
        return

    numero_actuel = tirage.get("drawNumber")

    if dernier_connu is None:
        # Premier lancement : on enregistre sans notifier.
        sauvegarder_dernier_numero(numero_actuel)
        print(f"Référence initialisée sur le tirage #{numero_actuel}.")
    elif numero_actuel != dernier_connu:
        print(f"Nouveau tirage détecté : #{numero_actuel}")
        envoyer_telegram(formater_message(tirage))
        sauvegarder_dernier_numero(numero_actuel)
    else:
        print(f"Pas de nouveau tirage (dernier connu : #{dernier_connu}).")


if __name__ == "__main__":
    main()
